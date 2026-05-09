"""Shadow-mode v3 delivery detector. Taps into OpenScout's per-frame
prose stream (read-only side channel) and runs the v3 cluster pipeline
(signal_extraction + delivery_classifier + boundary_extractor) without
blocking the live thread.

Activation: env var SHADOW_DELIVERY_DETECTOR=1.

Decision log path: files/logs/deliveries/<session>/live_decision_log.jsonl
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
TUNING_DIR = REPO_ROOT / "files/scripts/broadcast_mode_tuning"

import sys
if str(TUNING_DIR) not in sys.path:
    sys.path.insert(0, str(TUNING_DIR))

from signal_extraction import extract_signals  # noqa: E402
from delivery_classifier import (  # noqa: E402
    FrameInfo, annotate, strong_post_action_match, pick_anchor,
)
from delivery_clip_pipeline import (  # noqa: E402
    REPLAY_CLUSTER_MARKERS, WICKET_REPLAY_FOLLOWUP_MARKERS,
    WICKET_CLUSTER_PATTERNS,
)

log = logging.getLogger("shadow_delivery_detector")

GAP_MAX = 3
MIN_RUN = 2
PHANTOM_LOOKAHEAD_S = 3.0
FIX5_GAP_S = 12.0
FIX5_WICKET_GAP_S = 30.0
RESCUE_DIST_S = 60.0
MERGE_DIST_S = 10.0


def _is_enabled() -> bool:
    return os.environ.get("SHADOW_DELIVERY_DETECTOR", "0").strip() == "1"


class ShadowDeliveryDetector:
    """Incremental v3 cluster builder. Run on a background thread to
    avoid any blocking on the OpenScout result_sink callback."""

    def __init__(self, session_id: str, log_path: Path,
                 match_start_ts: Optional[float] = None) -> None:
        self.session_id = session_id
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._match_start_ts = match_start_ts
        self._q: "queue.Queue[Optional[dict]]" = queue.Queue()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._frames: list[FrameInfo] = []
        self._frames_by_rel_t: dict[float, FrameInfo] = {}
        self._cluster_open: bool = False
        self._cluster_id_seq: int = 0
        self._cur_cluster_start_t: Optional[float] = None
        self._cur_cluster_last_d_t: Optional[float] = None
        self._cur_cluster_gap: int = 0
        self._pending_close: list[dict] = []
        # Tracks the previous accepted cluster for Fix 5 sequencing.
        self._kept: list[dict] = []  # list of {start_t,end_t,anchor_t,
                                      #          frames, is_wicket}
        self._fp = None

    # Public API ---------------------------------------------------------

    def start(self) -> None:
        self._fp = open(self.log_path, "a", buffering=1)
        self._thread = threading.Thread(target=self._worker, daemon=True,
                                         name="shadow-delivery-detector")
        self._thread.start()
        self._emit({"type": "detector_started",
                    "session_id": self.session_id})
        log.info("[SHADOW-DELIVERY] started, log=%s", self.log_path)

    def stop(self) -> None:
        self._stop.set()
        try:
            self._q.put_nowait(None)
        except Exception:
            pass
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        # Drain any pending closes.
        self._drain_pending(force=True)
        self._emit({"type": "detector_stopped"})
        if self._fp is not None:
            try:
                self._fp.close()
            except Exception:
                pass

    def set_match_start_ts(self, ts: float) -> None:
        if self._match_start_ts is None:
            self._match_start_ts = ts

    def add_scout_result(self, timestamp: float, frame_class: str,
                          raw_description: str) -> None:
        """Non-blocking enqueue. Called from the OpenScout result_sink
        on the asyncio loop thread."""
        try:
            self._q.put_nowait({
                "timestamp": float(timestamp),
                "frame_class": frame_class or "",
                "raw_description": raw_description or "",
            })
        except Exception:
            log.exception("[SHADOW-DELIVERY] enqueue failed")

    # Worker thread ------------------------------------------------------

    def _worker(self) -> None:
        while not self._stop.is_set():
            try:
                item = self._q.get(timeout=1.0)
            except queue.Empty:
                # Periodic flush of pending closes (phantom-rescue window
                # elapsed for buffered candidates).
                self._drain_pending()
                continue
            if item is None:
                break
            try:
                self._process_one(item)
            except Exception:
                log.exception("[SHADOW-DELIVERY] _process_one failed")
            self._drain_pending()

    def _rel_t(self, ts: float) -> float:
        if self._match_start_ts is None:
            self._match_start_ts = ts
        return round(ts - self._match_start_ts, 2)

    def _process_one(self, item: dict) -> None:
        rel_t = self._rel_t(item["timestamp"])
        text = item["raw_description"]
        if not text:
            return
        f = FrameInfo(t=rel_t, text=text)
        f.signals = extract_signals(text)
        annotate(f)
        self._frames.append(f)
        self._frames_by_rel_t[rel_t] = f

        # Per-frame log entry (signals + path).
        self._emit({
            "type": "frame_signal",
            "rel_t": rel_t,
            "ts": item["timestamp"],
            "frame_class": item["frame_class"],
            "signals": _signals_dict(f.signals),
            "path": f.path,
            "is_delivery": bool(f.is_delivery),
        })

        s = f.signals
        # HARD frames close any open cluster immediately.
        if s.HARD:
            if self._cluster_open:
                self._close_cluster(reason="hard_reject", at_t=rel_t)
            return

        if not self._cluster_open:
            if f.is_delivery:
                self._open_cluster(rel_t, f.path)
            return

        # Cluster currently open.
        if f.is_delivery:
            self._cur_cluster_last_d_t = rel_t
            self._cur_cluster_gap = 0
            self._emit({
                "type": "cluster_extend",
                "rel_t": rel_t,
                "cluster_id": self._cluster_id_seq,
                "path": f.path,
            })
            return
        self._cur_cluster_gap += 1
        if self._cur_cluster_gap > GAP_MAX:
            self._close_cluster(reason="gap_exceeded", at_t=rel_t)

    def _open_cluster(self, rel_t: float, path: str) -> None:
        self._cluster_id_seq += 1
        self._cluster_open = True
        self._cur_cluster_start_t = rel_t
        self._cur_cluster_last_d_t = rel_t
        self._cur_cluster_gap = 0
        self._emit({
            "type": "cluster_open",
            "rel_t": rel_t,
            "cluster_id": self._cluster_id_seq,
            "path": path,
        })

    def _close_cluster(self, reason: str, at_t: float) -> None:
        if not self._cluster_open:
            return
        cid = self._cluster_id_seq
        start_t = self._cur_cluster_start_t
        end_t = self._cur_cluster_last_d_t
        self._cluster_open = False
        self._cur_cluster_start_t = None
        self._cur_cluster_last_d_t = None
        self._cur_cluster_gap = 0
        if start_t is None or end_t is None:
            return
        cluster_frames = [fr for fr in self._frames
                          if start_t <= fr.t <= end_t]
        delivery_count = sum(1 for fr in cluster_frames if fr.is_delivery)
        any_v = any(fr.signals.V for fr in cluster_frames)
        delivery_paths = [fr.path for fr in cluster_frames if fr.is_delivery]
        all_c = bool(delivery_paths) and all(p == "C" for p in delivery_paths)
        self._emit({
            "type": "cluster_close",
            "cluster_id": cid,
            "start_t": start_t,
            "end_t": end_t,
            "delivery_count": delivery_count,
            "any_v": any_v,
            "all_path_c": all_c,
            "close_reason": reason,
        })
        if delivery_count < MIN_RUN:
            self._emit({
                "type": "cluster_dropped",
                "cluster_id": cid,
                "reason": "min_run",
                "start_t": start_t, "end_t": end_t,
                "delivery_count": delivery_count,
            })
            return
        if any_v:
            anchor_t = self._pick_anchor_t(cluster_frames)
            self._promote_cluster({
                "cluster_id": cid,
                "start_t": start_t, "end_t": end_t,
                "anchor_t": anchor_t,
                "frames": cluster_frames,
                "reason": "v_filter_passed",
            })
            return
        # No V — possible phantom rescue if Path-C-only. Defer the
        # decision until PHANTOM_LOOKAHEAD_S has elapsed since end_t.
        self._pending_close.append({
            "cluster_id": cid,
            "start_t": start_t,
            "end_t": end_t,
            "all_path_c": all_c,
            "deadline_t": end_t + PHANTOM_LOOKAHEAD_S,
        })

    def _drain_pending(self, force: bool = False) -> None:
        if not self._pending_close:
            return
        latest_t = max((fr.t for fr in self._frames), default=0.0)
        keep: list[dict] = []
        for pend in self._pending_close:
            if not force and latest_t < pend["deadline_t"]:
                keep.append(pend)
                continue
            self._resolve_pending(pend, latest_t)
        self._pending_close = keep

    def _resolve_pending(self, pend: dict, latest_t: float) -> None:
        cid = pend["cluster_id"]
        start_t = pend["start_t"]
        end_t = pend["end_t"]
        if not pend["all_path_c"]:
            self._emit({
                "type": "cluster_dropped",
                "cluster_id": cid,
                "reason": "v_filter",
                "start_t": start_t, "end_t": end_t,
            })
            return
        # Phantom rescue: search [start_t, end_t + 3s] for STRONG_POST_ACTION.
        rescue_hit_t: Optional[float] = None
        rescue_phrase: Optional[str] = None
        for fr in self._frames:
            if fr.t < start_t or fr.t > end_t + PHANTOM_LOOKAHEAD_S:
                continue
            hit = strong_post_action_match(fr.text)
            if hit is not None:
                rescue_hit_t = fr.t
                rescue_phrase = hit[2]
                break
        if rescue_hit_t is None:
            self._emit({
                "type": "cluster_dropped",
                "cluster_id": cid,
                "reason": "phantom_not_rescued",
                "start_t": start_t, "end_t": end_t,
            })
            return
        cluster_frames = [fr for fr in self._frames
                          if start_t <= fr.t <= end_t]
        anchor_t = self._pick_anchor_t(cluster_frames,
                                         phantom_rescued=True)
        self._emit({
            "type": "phantom_rescue",
            "cluster_id": cid,
            "start_t": start_t, "end_t": end_t,
            "anchor_t": anchor_t,
            "rescue_at_t": rescue_hit_t,
            "rescue_phrase": rescue_phrase,
        })
        self._promote_cluster({
            "cluster_id": cid,
            "start_t": start_t, "end_t": end_t,
            "anchor_t": anchor_t,
            "frames": cluster_frames,
            "reason": "phantom_rescued",
        })

    def _is_wicket_cluster(self, frames: list[FrameInfo]) -> bool:
        for f in frames:
            for p in WICKET_CLUSTER_PATTERNS:
                if p.search(f.text):
                    return True
        return False

    def _fix5_replay_followup(self, candidate: dict,
                               prev: dict) -> Optional[str]:
        gap = candidate["start_t"] - prev["end_t"]
        prev_is_wicket = bool(prev.get("is_wicket"))
        cap = FIX5_WICKET_GAP_S if prev_is_wicket else FIX5_GAP_S
        if gap > cap:
            return None
        for f in candidate["frames"]:
            m = REPLAY_CLUSTER_MARKERS.search(f.text)
            if m:
                tag = "wicket-replay" if prev_is_wicket else "replay"
                return (f"{tag}-marker '{m.group(0)}' at t={f.t:.1f}s, "
                        f"gap={gap:.1f}s")
            if prev_is_wicket:
                m = WICKET_REPLAY_FOLLOWUP_MARKERS.search(f.text)
                if m:
                    return (f"wicket-ball-speed '{m.group(0)}' at "
                            f"t={f.t:.1f}s, gap={gap:.1f}s")
        return None

    def _promote_cluster(self, cand: dict) -> None:
        prev = self._kept[-1] if self._kept else None
        # Fix 5 — replay-followup drop.
        if prev is not None:
            why = self._fix5_replay_followup(cand, prev)
            if why is not None:
                self._emit({
                    "type": "cluster_dropped",
                    "cluster_id": cand["cluster_id"],
                    "reason": "fix5_replay_followup",
                    "start_t": cand["start_t"], "end_t": cand["end_t"],
                    "detail": why,
                })
                return
        cand["is_wicket"] = self._is_wicket_cluster(cand["frames"])
        self._emit({
            "type": "cluster_kept",
            "cluster_id": cand["cluster_id"],
            "start_t": cand["start_t"], "end_t": cand["end_t"],
            "anchor_t": cand["anchor_t"],
            "reason": cand["reason"],
            "is_wicket": cand["is_wicket"],
        })
        self._kept.append({
            "cluster_id": cand["cluster_id"],
            "start_t": cand["start_t"], "end_t": cand["end_t"],
            "anchor_t": cand["anchor_t"],
            "frames": list(cand["frames"]),
            "is_wicket": cand["is_wicket"],
        })
        self._retroactive_rescue_and_merge(cand)

    def _retroactive_rescue_and_merge(self, just_kept: dict) -> None:
        """When a new cluster is kept, scan for high-signal singleton
        frames sandwiched between the previous kept cluster and this
        one. If sandwiched within RESCUE_DIST_S on both sides → rescue.
        If rescued and within MERGE_DIST_S of either side → merge."""
        if len(self._kept) < 2:
            return
        prev = self._kept[-2]
        curr = self._kept[-1]
        in_kept_t: set[float] = set()
        for c in self._kept:
            for fr in c["frames"]:
                in_kept_t.add(fr.t)
        for f in self._frames:
            if f.t in in_kept_t:
                continue
            if not f.is_delivery:
                continue
            if f.path not in ("A", "B"):
                continue
            s = f.signals
            if not (s.V and s.M2):
                continue
            if f.t <= prev["end_t"] or f.t >= curr["start_t"]:
                continue
            dist_before = f.t - prev["end_t"]
            dist_after = curr["start_t"] - f.t
            if dist_before > RESCUE_DIST_S or dist_after > RESCUE_DIST_S:
                continue
            # Rescue. Check merge: closer side within MERGE_DIST_S → merge.
            self._emit({
                "type": "singleton_rescued",
                "rescued_t": f.t,
                "rescue_dist_before": round(dist_before, 2),
                "rescue_dist_after": round(dist_after, 2),
                "path": f.path,
            })
            target = None
            if dist_before <= MERGE_DIST_S and dist_before <= dist_after:
                target = prev
            elif dist_after <= MERGE_DIST_S:
                target = curr
            if target is not None:
                target["start_t"] = min(target["start_t"], f.t)
                target["end_t"] = max(target["end_t"], f.t)
                target["frames"].append(f)
                target["frames"].sort(key=lambda x: x.t)
                # Recompute anchor with merged frame set (mirrors offline
                # pick_anchor on the merged cluster).
                new_anchor = self._pick_anchor_t(target["frames"])
                target["anchor_t"] = new_anchor
                in_kept_t.add(f.t)
                self._emit({
                    "type": "cluster_merged",
                    "cluster_id": target["cluster_id"],
                    "merged_t": f.t,
                    "new_start_t": target["start_t"],
                    "new_end_t": target["end_t"],
                    "new_anchor_t": new_anchor,
                })
                # Re-emit cluster_kept with the merged anchor so the
                # final kept-anchor list matches offline output.
                self._emit({
                    "type": "cluster_kept",
                    "cluster_id": target["cluster_id"],
                    "start_t": target["start_t"],
                    "end_t": target["end_t"],
                    "anchor_t": new_anchor,
                    "reason": "merged_rescued",
                    "is_wicket": target.get("is_wicket", False),
                })
            else:
                # Standalone rescued cluster (1-frame).
                self._cluster_id_seq += 1
                rid = self._cluster_id_seq
                self._kept.append({
                    "cluster_id": rid,
                    "start_t": f.t, "end_t": f.t,
                    "anchor_t": f.t,
                    "frames": [f],
                    "is_wicket": False,
                    "rescued": True,
                })
                self._kept.sort(key=lambda c: c["start_t"])
                in_kept_t.add(f.t)
                self._emit({
                    "type": "cluster_kept",
                    "cluster_id": rid,
                    "start_t": f.t, "end_t": f.t,
                    "anchor_t": f.t,
                    "reason": "singleton_rescued",
                    "is_wicket": False,
                })

    def _pick_anchor_t(self, frames: list[FrameInfo],
                        phantom_rescued: bool = False) -> float:
        # Mirror offline pick_anchor: prose-rank scoring for V-filter
        # clusters, last-delivery-frame for phantom-rescued.
        cluster_dict = {"frames": frames,
                        "phantom_rescued": phantom_rescued}
        try:
            return pick_anchor(cluster_dict).t
        except Exception:
            delivery = [fr for fr in frames if fr.is_delivery]
            return (delivery[-1].t if delivery else frames[-1].t)

    def _emit(self, payload: dict) -> None:
        if self._fp is None:
            return
        rec = dict(payload)
        rec.setdefault("session_id", self.session_id)
        rec.setdefault("wall_ts", time.time())
        try:
            self._fp.write(json.dumps(rec, default=str) + "\n")
        except Exception:
            log.exception("[SHADOW-DELIVERY] emit failed")


def _signals_dict(s) -> dict:
    return {
        "V": bool(s.V), "V_post": bool(s.V_post),
        "S": bool(s.S), "M": bool(s.M), "M2": bool(s.M2),
        "W": bool(s.W), "K": bool(s.K), "SS": bool(s.SS),
        "SS_via_loose": bool(getattr(s, "SS_via_loose", False)),
        "CG": bool(s.CG), "HARD": bool(s.HARD),
    }


_GLOBAL: Optional[ShadowDeliveryDetector] = None


def maybe_create(session_id: str,
                 log_dir: Path) -> Optional[ShadowDeliveryDetector]:
    """Return a started detector if SHADOW_DELIVERY_DETECTOR=1, else None.
    Idempotent — repeated calls return the same instance."""
    global _GLOBAL
    if _GLOBAL is not None:
        return _GLOBAL
    if not _is_enabled():
        return None
    log_path = log_dir / "live_decision_log.jsonl"
    det = ShadowDeliveryDetector(session_id=session_id, log_path=log_path)
    det.start()
    _GLOBAL = det
    return det


def get() -> Optional[ShadowDeliveryDetector]:
    return _GLOBAL
