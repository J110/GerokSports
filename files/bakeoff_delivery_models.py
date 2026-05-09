"""Delivery-detection bakeoff harness.

Compares FOUR systems on the same set of delivery clips:

  1. `current`  — whatever the live pipeline already classified (read
                  back from each delivery's ``predictions.json``).
                  This is Gemini 3 Flash Preview running the production
                  `GEMINI_PROMPT`.
  2. `layer2`   — the production Q+G (Qwen-30B + Gemini-3-Flash)
                  routed spatial classifier.  Fires both models in
                  parallel on a 16-frame burst, routes each field to
                  the owner from ``layer2_routing.json``, applies the
                  confidence-floor abstain.  Re-run here against the
                  same mp4s so we have apples-to-apples comparison.
  3. `claude`   — Claude Opus 4.7 reading 16 evenly-spaced frames from
                  the same clip.  (Claude models don't take mp4 input
                  natively, so we extract stills.)
  4. `gemini31` — Gemini 3.1 Pro Preview reading the mp4 directly.

For each delivery we run the `layer2`, `claude`, and `gemini31`
models THREE times (with temperature=1.0 where configurable) so we
can measure intra-model consistency alongside cross-model agreement.

All results land in ``files/bakeoff_out/<delivery_id>.json``; a
self-contained HTML report gets written to
``files/bakeoff_out/index.html``.

Secrets handling
----------------
The Anthropic API key is read from the ``ANTHROPIC_API_KEY``
environment variable.  It is NOT written to any file, baked into the
HTML, or logged.  Gemini uses the same ``GEMINI_API_KEY`` already
loaded from ``eyes.config`` for the production classifier.

Usage
-----
    ANTHROPIC_API_KEY=sk-ant-... python3 bakeoff_delivery_models.py

Optional env:
    BAKEOFF_SESSION     source session under logs/deliveries/<NAME>
                        (default 20260420_202239).
    BAKEOFF_DELIVERIES  comma-separated delivery folder names
                        (default: a hand-picked 10-delivery mix).
    BAKEOFF_RUNS_PER_MODEL   runs per model per delivery (default 3).
    BAKEOFF_WORKERS     parallel worker pool size (default 6).
"""
from __future__ import annotations

import base64
import concurrent.futures as cf
import io
import json
import os
import shutil
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

# Keep imports from the prod codebase small — we reuse the exact same
# classification prompt so the three systems are judged on the same
# schema, same rubric.
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from gemini_delivery_classifier import GEMINI_PROMPT, _parse_json  # noqa: E402
# Layer 2 (Q+G) is imported lazily from inside call_layer2 — the
# module pulls in torch / google-genai at import and we want the
# ModuleNotFoundError (if any) to surface per-call, not at harness
# startup.

DEFAULT_SESSION = "20260420_202239"
DEFAULT_DELIVERIES = [
    "d005",  # DOT
    "d009",  # 1_RUN
    "d010",  # WICKET
    "d013",  # DOT
    "d018",  # 2_RUNS
    "d020",  # SIX
    "d021",  # FOUR
    "d024",  # EXTRA
    "d028",  # DOT
    "d033",  # SIX
]

SESSION = os.environ.get("BAKEOFF_SESSION", DEFAULT_SESSION)
DELIVERIES = [d.strip() for d in os.environ.get(
    "BAKEOFF_DELIVERIES", ",".join(DEFAULT_DELIVERIES)
).split(",") if d.strip()]
RUNS_PER_MODEL = int(os.environ.get("BAKEOFF_RUNS_PER_MODEL", "3"))
WORKERS = int(os.environ.get("BAKEOFF_WORKERS", "6"))

CLAUDE_MODEL = "claude-opus-4-7"
GEMINI_MODEL = "gemini-3.1-pro-preview"
LAYER2_MODEL = "layer2-qwen30b+gem3flash"

# The fields we will score on — a subset of the prompt schema that's
# actually comparable across the three systems.
CMP_FIELDS = [
    "is_valid_delivery",
    "bowling_angle",
    "bowling_type",
    "length",
    "line",
    "bounce",
    "shot_played",
    "shot_type",
    "shot_side",
    "shot_angle",
    "elevation",
    "contact_quality",
    "confidence",
]

SESSION_DIR = ROOT / "logs" / "deliveries" / SESSION
OUT_DIR = ROOT / "bakeoff_out"
VIDEOS_DIR = OUT_DIR / "videos"
OUT_DIR.mkdir(parents=True, exist_ok=True)
VIDEOS_DIR.mkdir(parents=True, exist_ok=True)


# ── Frame extraction for Claude ─────────────────────────────────────


def extract_evenly_spaced_frames(mp4_path: Path,
                                 n_frames: int = 16,
                                 max_dim: int = 768,
                                 ) -> list[bytes]:
    """Read ``n_frames`` evenly spaced JPEGs from an mp4 file.

    Returned bytes list is suitable for direct inline image upload to
    Anthropic's Messages API.  ``max_dim`` is the long-edge cap — we
    downscale to keep each image under the per-image token budget
    (smaller images = cheaper + faster, with minimal loss on the
    bowler's-end wide shots we're classifying).
    """
    cap = cv2.VideoCapture(str(mp4_path))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total <= 0:
        cap.release()
        return []
    # Evenly spaced indices from 0..total-1
    if n_frames >= total:
        idxs = list(range(total))
    else:
        step = (total - 1) / float(n_frames - 1)
        idxs = [int(round(i * step)) for i in range(n_frames)]
    want = sorted(set(idxs))
    out: list[bytes] = []
    cur = -1
    for target in want:
        if target != cur + 1:
            cap.set(cv2.CAP_PROP_POS_FRAMES, target)
        ok, fr = cap.read()
        if not ok:
            break
        cur = target
        # Downscale long edge
        h, w = fr.shape[:2]
        if max(h, w) > max_dim:
            s = max_dim / float(max(h, w))
            fr = cv2.resize(fr, (int(w * s), int(h * s)),
                            interpolation=cv2.INTER_AREA)
        ok2, buf = cv2.imencode(".jpg", fr,
                                [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok2:
            out.append(buf.tobytes())
    cap.release()
    return out


# ── Model callers ───────────────────────────────────────────────────


@dataclass
class ModelRun:
    """One classification attempt."""
    model: str
    run_index: int
    ok: bool
    parsed: dict = field(default_factory=dict)
    raw: str = ""
    error: str = ""
    wall_ms: int = 0


def call_claude(frame_jpegs: list[bytes], runs: int = 0) -> ModelRun:
    from anthropic import Anthropic
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return ModelRun(model=CLAUDE_MODEL, run_index=-1, ok=False,
                        error="ANTHROPIC_API_KEY unset")
    c = Anthropic(api_key=api_key)

    # One user message: the prompt text followed by 16 frames.
    content: list[dict] = [{"type": "text", "text": GEMINI_PROMPT}]
    for jpg in frame_jpegs:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": base64.b64encode(jpg).decode("ascii"),
            },
        })

    t0 = time.time()
    try:
        resp = c.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            temperature=1.0,
            messages=[{"role": "user", "content": content}],
        )
        raw = "".join(b.text for b in resp.content
                      if getattr(b, "type", None) == "text")
        ms = int((time.time() - t0) * 1000)
        parsed = _parse_json(raw) or {}
        return ModelRun(model=CLAUDE_MODEL, run_index=-1, ok=bool(parsed),
                        parsed=parsed, raw=raw, wall_ms=ms)
    except Exception as e:  # noqa: BLE001
        ms = int((time.time() - t0) * 1000)
        return ModelRun(model=CLAUDE_MODEL, run_index=-1, ok=False,
                        error=f"{type(e).__name__}: {e}"[:400],
                        wall_ms=ms)


def call_layer2(mp4_path: Path) -> ModelRun:
    """Production Q+G routed spatial classifier on the same mp4.

    The Layer2Classifier returns a legacy-schema dict plus an internal
    ``_layer2_routed`` dict keyed by the same spatial fields Claude
    and Gemini 3.1 Pro emit (length / line / bounce / shot_type /
    shot_side / shot_angle / elevation / contact_quality / ...).  We
    project onto the comparison schema by reading ``_layer2_routed``
    first, falling back to the legacy keys so nothing gets lost.
    """
    try:
        from layer2_classifier import Layer2Classifier  # noqa: WPS433
    except Exception as e:  # noqa: BLE001
        return ModelRun(model=LAYER2_MODEL, run_index=-1, ok=False,
                        error=f"import_fail: {e}"[:400])

    clf = Layer2Classifier()
    if not clf.available():
        return ModelRun(model=LAYER2_MODEL, run_index=-1, ok=False,
                        error=f"l2_unavailable: "
                              f"{clf._init_error}"[:400])

    t0 = time.time()
    try:
        legacy = clf.classify_video(str(mp4_path), runs=0, save_dir=None)
    except Exception as e:  # noqa: BLE001
        ms = int((time.time() - t0) * 1000)
        return ModelRun(model=LAYER2_MODEL, run_index=-1, ok=False,
                        error=f"{type(e).__name__}: {e}"[:400],
                        wall_ms=ms)
    ms = int((time.time() - t0) * 1000)

    routed = legacy.get("_layer2_routed") or {}
    if not routed:
        return ModelRun(model=LAYER2_MODEL, run_index=-1, ok=False,
                        raw=json.dumps(legacy)[:1500],
                        error=legacy.get("_untrackable_reason")
                        or "no_routed_output",
                        wall_ms=ms)

    # Project routed + legacy dict onto the comparison schema.
    parsed = {
        "is_valid_delivery": bool(
            routed.get("is_valid_delivery", True)),
        "bowling_angle":  routed.get("bowling_angle") or "unknown",
        "bowling_type":   routed.get("bowling_type") or "unknown",
        "length":         routed.get("length") or "unknown",
        "line":           routed.get("line") or "unknown",
        "bounce":         routed.get("bounce") or "unknown",
        "shot_played":    bool(routed.get("shot_played", True)),
        "shot_type":      routed.get("shot_type") or "unknown",
        "shot_side":      routed.get("shot_side") or "unknown",
        "shot_angle":     routed.get("shot_angle") or "no_shot",
        "elevation":      routed.get("elevation") or "no_shot",
        "contact_quality": routed.get("contact_quality") or "unknown",
        "confidence":     _confidence_from_committed(
            legacy.get("_layer2_committed")),
        "narrative":      legacy.get("commentary_line") or "",
        "_committed":     legacy.get("_layer2_committed"),
        "_agreements":    legacy.get("_layer2_agreements"),
        "_qwen_ms":       legacy.get("_qwen_ms"),
        "_gemini_ms":     legacy.get("_gemini_ms"),
    }
    raw = json.dumps({"routed": routed,
                      "diag_summary": {
                          "committed": legacy.get("_layer2_committed"),
                          "agreements": legacy.get("_layer2_agreements"),
                      }}, default=str)
    return ModelRun(model=LAYER2_MODEL, run_index=-1, ok=True,
                    parsed=parsed, raw=raw[:3000], wall_ms=ms)


def _confidence_from_committed(committed: int | None) -> str:
    """Mirror Layer2Classifier's mean-confidence label mapping."""
    if not isinstance(committed, int):
        return "unknown"
    if committed >= 12:
        return "high"
    if committed >= 8:
        return "medium"
    return "low"


def call_gemini31(mp4_bytes: bytes) -> ModelRun:
    from google import genai
    from google.genai import types as gtypes
    from eyes.config import GEMINI_API_KEY
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:  # noqa: BLE001
        return ModelRun(model=GEMINI_MODEL, run_index=-1, ok=False,
                        error=f"client_init: {e}"[:400])

    parts = [
        gtypes.Part.from_bytes(data=mp4_bytes, mime_type="video/mp4"),
        gtypes.Part.from_text(text=GEMINI_PROMPT),
    ]
    t0 = time.time()
    try:
        resp = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=parts,
            config=gtypes.GenerateContentConfig(
                temperature=1.0,
                response_mime_type="application/json",
            ),
        )
        raw = resp.text or ""
        ms = int((time.time() - t0) * 1000)
        parsed = _parse_json(raw) or {}
        return ModelRun(model=GEMINI_MODEL, run_index=-1, ok=bool(parsed),
                        parsed=parsed, raw=raw, wall_ms=ms)
    except Exception as e:  # noqa: BLE001
        ms = int((time.time() - t0) * 1000)
        return ModelRun(model=GEMINI_MODEL, run_index=-1, ok=False,
                        error=f"{type(e).__name__}: {e}"[:400],
                        wall_ms=ms)


# ── Existing "current system" prediction ingestion ──────────────────


def load_current_prediction(delivery_dir: Path) -> dict:
    """Read predictions.json from the live pipeline run.

    The schema there is a little different (legacy delivery_info +
    Gemini raw), so we re-map onto the comparison schema so everything
    lines up in the HTML table.
    """
    pp = delivery_dir / "predictions.json"
    if not pp.exists():
        return {}
    try:
        pred = json.loads(pp.read_text())
    except Exception:
        return {}
    # The live pipeline stores the Gemini raw in _gemini_raw, which
    # IS a JSON blob that matches our CMP_FIELDS schema directly.  Try
    # to parse it first; fall back to the legacy fields.
    raw = pred.get("_gemini_raw") or ""
    reparsed = _parse_json(raw) if raw else None
    if reparsed:
        merged = dict(reparsed)
        merged["_source"] = "predictions.json._gemini_raw"
        merged["_wall_ms"] = pred.get("_gemini_ms") or pred.get("_wall_ms")
        merged["narrative"] = (
            reparsed.get("narrative")
            or pred.get("narrative") or "")
        return merged
    # Fallback: synthesize from legacy fields.
    return {
        "_source": "predictions.json.legacy",
        "bowling_angle": pred.get("bowling_angle"),
        "bowling_type": pred.get("bowling_type"),
        "length": pred.get("length"),
        "line": pred.get("line"),
        "bounce": pred.get("bounce"),
        "shot_type": pred.get("shot_type"),
        "contact_quality": pred.get("contact_quality"),
        "narrative": pred.get("narrative") or pred.get("commentary_line", ""),
        "confidence": pred.get("_gemini_confidence", "unknown"),
        "_wall_ms": pred.get("_gemini_ms") or pred.get("_wall_ms"),
    }


# ── Bakeoff orchestration ───────────────────────────────────────────


@dataclass
class DeliveryResult:
    delivery_id: str
    over_number: float | None
    innings: int | None
    event_type: str | None
    runs: int | None
    duration_s: float
    video_rel: str
    current: dict = field(default_factory=dict)
    claude_runs: list[ModelRun] = field(default_factory=list)
    gemini_runs: list[ModelRun] = field(default_factory=list)
    layer2_runs: list[ModelRun] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "delivery_id": self.delivery_id,
            "over_number": self.over_number,
            "innings": self.innings,
            "event_type": self.event_type,
            "runs": self.runs,
            "duration_s": self.duration_s,
            "video_rel": self.video_rel,
            "current": self.current,
            "claude_runs": [r.__dict__ for r in self.claude_runs],
            "gemini_runs": [r.__dict__ for r in self.gemini_runs],
            "layer2_runs": [r.__dict__ for r in self.layer2_runs],
        }


def _hydrate_runs(raw_list, label: str) -> list[ModelRun]:
    """Rebuild ModelRun objects from the on-disk JSON list."""
    out: list[ModelRun] = []
    for r in raw_list or []:
        try:
            out.append(ModelRun(
                model=r.get("model") or label,
                run_index=int(r.get("run_index", -1)),
                ok=bool(r.get("ok", False)),
                parsed=r.get("parsed") or {},
                raw=r.get("raw") or "",
                error=r.get("error") or "",
                wall_ms=int(r.get("wall_ms") or 0),
            ))
        except Exception:  # noqa: BLE001
            continue
    return out


def process_delivery(delivery_id: str) -> DeliveryResult:
    ddir = SESSION_DIR / delivery_id
    wd_path = ddir / "window_debug.json"
    mp4_path = ddir / "delivery_window.mp4"
    if not mp4_path.exists():
        raise FileNotFoundError(f"missing mp4: {mp4_path}")

    wd = {}
    if wd_path.exists():
        try:
            wd = json.loads(wd_path.read_text())
        except Exception:
            pass

    duration = float(wd.get("clip_end_ts") or 0) - float(
        wd.get("clip_start_ts") or 0)

    # Copy mp4 into bakeoff_out/videos/ so the HTML can reference it
    # without a file:// CORS workaround.
    rel_video = f"videos/{delivery_id}.mp4"
    dst_mp4 = OUT_DIR / rel_video
    if not dst_mp4.exists():
        shutil.copy2(mp4_path, dst_mp4)

    res = DeliveryResult(
        delivery_id=delivery_id,
        over_number=wd.get("over_number"),
        innings=wd.get("innings"),
        event_type=wd.get("event_type"),
        runs=wd.get("runs"),
        duration_s=duration,
        video_rel=rel_video,
        current=load_current_prediction(ddir),
    )

    # Idempotent re-use: if we already persisted claude_runs /
    # gemini_runs from a prior invocation, hydrate them instead of
    # re-burning API credits.  Runs are only re-fired when we don't
    # yet have RUNS_PER_MODEL successful entries.
    cached_path = OUT_DIR / f"{delivery_id}.json"
    cached: dict = {}
    if cached_path.exists():
        try:
            cached = json.loads(cached_path.read_text())
        except Exception:
            cached = {}

    def _ok_runs(raw_list) -> list[ModelRun]:
        hydrated = _hydrate_runs(raw_list, "")
        return [r for r in hydrated if r.ok]

    cached_claude = _ok_runs(cached.get("claude_runs"))
    cached_gem = _ok_runs(cached.get("gemini_runs"))
    cached_l2 = _ok_runs(cached.get("layer2_runs"))

    need_claude = RUNS_PER_MODEL - len(cached_claude)
    need_gem = RUNS_PER_MODEL - len(cached_gem)
    need_l2 = RUNS_PER_MODEL - len(cached_l2)

    frame_jpegs: list[bytes] = []
    mp4_bytes: bytes = b""
    if need_claude > 0:
        frame_jpegs = extract_evenly_spaced_frames(mp4_path, n_frames=16)
    if need_gem > 0:
        mp4_bytes = mp4_path.read_bytes()

    print(f"  [{delivery_id}] dur={duration:.1f}s event={res.event_type} "
          f"runs={res.runs} need_claude={need_claude} "
          f"need_gem={need_gem} need_l2={need_l2}", flush=True)

    # Fire all required runs in parallel.  Layer-2 already runs Qwen
    # + Gemini in parallel per call, so capping pool = sum of pending
    # runs keeps things simple.
    pool_size = max(1, need_claude + need_gem + need_l2)
    with cf.ThreadPoolExecutor(max_workers=pool_size) as pool:
        c_futs = [pool.submit(call_claude, frame_jpegs, res.runs or 0)
                  for _ in range(need_claude)]
        g_futs = [pool.submit(call_gemini31, mp4_bytes)
                  for _ in range(need_gem)]
        l_futs = [pool.submit(call_layer2, mp4_path)
                  for _ in range(need_l2)]
        fresh_claude = [f.result() for f in c_futs]
        fresh_gem = [f.result() for f in g_futs]
        fresh_l2 = [f.result() for f in l_futs]

    res.claude_runs = (cached_claude + fresh_claude)[:RUNS_PER_MODEL]
    res.gemini_runs = (cached_gem + fresh_gem)[:RUNS_PER_MODEL]
    res.layer2_runs = (cached_l2 + fresh_l2)[:RUNS_PER_MODEL]
    for i, r in enumerate(res.claude_runs):
        r.run_index = i
    for i, r in enumerate(res.gemini_runs):
        r.run_index = i
    for i, r in enumerate(res.layer2_runs):
        r.run_index = i

    return res


# ── HTML report rendering ───────────────────────────────────────────


def _esc(s) -> str:
    if s is None:
        return ""
    return (str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def _consistency(runs: list[ModelRun], field_name: str) -> tuple[float, int]:
    """Fraction of runs that agree on the modal value, plus #distinct."""
    vals = []
    for r in runs:
        if not r.ok:
            continue
        v = r.parsed.get(field_name)
        if v is None:
            continue
        vals.append(str(v).strip().lower())
    if not vals:
        return 0.0, 0
    from collections import Counter
    c = Counter(vals)
    top, n_top = c.most_common(1)[0]
    return n_top / len(vals), len(c)


def render_html(results: list[DeliveryResult]) -> str:
    lines = []
    lines.append(
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        "<title>Delivery Detection Bakeoff</title>"
        "<style>"
        "body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;"
        "margin:0;background:#0b0e14;color:#e6e6e6;}"
        "header{padding:20px 28px;background:#151a24;"
        "border-bottom:1px solid #2a3140;position:sticky;top:0;"
        "z-index:5;}"
        "h1{margin:0;font-size:20px;}"
        ".summary{font-size:13px;color:#9aa4b2;margin-top:4px;}"
        ".delivery{margin:24px 28px;padding:18px;background:#151a24;"
        "border-radius:10px;border:1px solid #2a3140;}"
        ".dhead{display:flex;gap:24px;align-items:baseline;"
        "margin-bottom:12px;flex-wrap:wrap;}"
        ".did{font-size:18px;font-weight:600;}"
        ".dmeta{color:#9aa4b2;font-size:13px;}"
        ".grid{display:grid;grid-template-columns:480px 1fr;gap:20px;}"
        "video{width:100%;background:#000;border-radius:6px;}"
        "table{border-collapse:collapse;width:100%;font-size:12px;}"
        "th,td{padding:4px 8px;border:1px solid #2a3140;"
        "text-align:left;vertical-align:top;}"
        "th{background:#1c2230;font-weight:500;color:#9aa4b2;"
        "font-size:11px;text-transform:uppercase;letter-spacing:0.05em;}"
        "td.field{background:#1c2230;color:#9aa4b2;font-weight:500;"
        "font-size:11px;text-transform:uppercase;letter-spacing:0.05em;"
        "width:120px;}"
        ".cur{background:#1a2340;}"
        ".c1,.c2,.c3{background:#1a2e1f;}"
        ".g1,.g2,.g3{background:#2e1e1a;}"
        ".l1,.l2,.l3{background:#2a1f36;}"
        ".consis-ok{color:#7fd18c;font-weight:600;}"
        ".consis-warn{color:#ffb86b;}"
        ".consis-bad{color:#ff7a7a;font-weight:600;}"
        "td.mismatch{box-shadow:inset 0 0 0 2px #ff7a7a;}"
        ".narrative{font-size:12px;color:#b8c1cc;font-style:italic;"
        "padding:6px 8px;}"
        ".raw{font-family:ui-monospace,Menlo,monospace;font-size:11px;"
        "color:#8b95a3;white-space:pre-wrap;margin-top:8px;"
        "max-height:220px;overflow:auto;background:#0d1016;"
        "padding:8px;border-radius:4px;}"
        "details{margin-top:10px;}"
        "summary{cursor:pointer;color:#7fb0ff;font-size:12px;}"
        ".legend{display:flex;gap:14px;margin-top:6px;font-size:11px;}"
        ".legend .sw{display:inline-block;width:12px;height:12px;"
        "vertical-align:middle;margin-right:4px;border-radius:2px;}"
        ".toc{margin:6px 0 0 0;display:flex;gap:8px;flex-wrap:wrap;}"
        ".toc a{color:#7fb0ff;text-decoration:none;padding:2px 8px;"
        "border:1px solid #2a3140;border-radius:4px;font-size:12px;}"
        ".toc a:hover{background:#1c2230;}"
        ".agg{margin:24px 28px 0 28px;padding:14px 18px;"
        "background:#151a24;border:1px solid #2a3140;border-radius:10px;}"
        ".agg h2{margin:0 0 10px 0;font-size:16px;}"
        ".agg-table{max-width:760px;}"
        ".table-wrap{overflow-x:auto;}"
        "</style></head><body>"
    )
    total = len(results)
    c_ok = sum(sum(1 for r in d.claude_runs if r.ok) for d in results)
    g_ok = sum(sum(1 for r in d.gemini_runs if r.ok) for d in results)
    l_ok = sum(sum(1 for r in d.layer2_runs if r.ok) for d in results)
    c_tot = sum(len(d.claude_runs) for d in results)
    g_tot = sum(len(d.gemini_runs) for d in results)
    l_tot = sum(len(d.layer2_runs) for d in results)
    lines.append(
        f"<header><h1>Delivery Detection Bakeoff — "
        f"{SESSION} · {total} deliveries</h1>"
        f"<div class=\"summary\">"
        f"<b>current</b> = production Gemini 3 Flash Preview (from "
        f"predictions.json).  "
        f"<b>layer2_*</b> = production Q+G routed "
        f"(Qwen30B + Gemini3Flash, {l_ok}/{l_tot} calls ok).  "
        f"<b>claude_*</b> = {CLAUDE_MODEL} on 16 evenly-spaced frames "
        f"({c_ok}/{c_tot} calls ok).  "
        f"<b>gemini31_*</b> = {GEMINI_MODEL} on mp4 "
        f"({g_ok}/{g_tot} calls ok).  "
        f"Each challenger was run {RUNS_PER_MODEL}× (temperature=1.0 "
        f"for Claude / Gemini 3.1 Pro; Layer-2 sub-models run at "
        f"their production settings)."
        f"</div>"
        f"<div class=\"legend\">"
        f"<span><span class=\"sw\" style=\"background:#1a2340\"></span>"
        f"current</span>"
        f"<span><span class=\"sw\" style=\"background:#2a1f36\"></span>"
        f"layer2 (Q+G)</span>"
        f"<span><span class=\"sw\" style=\"background:#1a2e1f\"></span>"
        f"claude</span>"
        f"<span><span class=\"sw\" style=\"background:#2e1e1a\"></span>"
        f"gemini 3.1 pro</span>"
        f"<span><span class=\"consis-ok\">green</span> = 3/3 agree</span>"
        f"<span><span class=\"consis-warn\">orange</span> = 2/3 agree</span>"
        f"<span><span class=\"consis-bad\">red</span> = all disagree</span>"
        f"</div>"
        f"<div class=\"toc\">"
        + "".join(f"<a href=\"#{_esc(d.delivery_id)}\">"
                  f"{_esc(d.delivery_id)} · {_esc(d.event_type)}</a>"
                  for d in results)
        + "</div>"
        f"</header>"
    )

    # Aggregate per-field intra-model consistency across all deliveries
    agg_claude = {f: [] for f in CMP_FIELDS}
    agg_gem = {f: [] for f in CMP_FIELDS}
    agg_l2 = {f: [] for f in CMP_FIELDS}
    for d in results:
        for fname in CMP_FIELDS:
            cc, _ = _consistency(d.claude_runs, fname)
            gg, _ = _consistency(d.gemini_runs, fname)
            ll, _ = _consistency(d.layer2_runs, fname)
            if any(r.ok for r in d.claude_runs):
                agg_claude[fname].append(cc)
            if any(r.ok for r in d.gemini_runs):
                agg_gem[fname].append(gg)
            if any(r.ok for r in d.layer2_runs):
                agg_l2[fname].append(ll)
    lines.append(
        "<div class=\"agg\"><h2>Intra-model consistency "
        "(mean across deliveries)</h2>"
        "<table class=\"agg-table\"><tr><th>field</th>"
        "<th>Layer-2 (Q+G) 3/3 %</th>"
        "<th>Claude 3/3 %</th>"
        "<th>Gemini 3.1 Pro 3/3 %</th></tr>"
    )
    for fname in CMP_FIELDS:
        ls = agg_l2[fname]
        cs = agg_claude[fname]
        gs = agg_gem[fname]
        lavg = sum(ls) / len(ls) if ls else 0
        cavg = sum(cs) / len(cs) if cs else 0
        gavg = sum(gs) / len(gs) if gs else 0
        lines.append(
            f"<tr><td class=\"field\">{_esc(fname)}</td>"
            f"<td>{lavg*100:.0f}%</td>"
            f"<td>{cavg*100:.0f}%</td>"
            f"<td>{gavg*100:.0f}%</td></tr>"
        )
    lines.append("</table></div>")

    # Per-delivery blocks
    for d in results:
        lines.append(_render_delivery(d))
    lines.append("</body></html>")
    return "".join(lines)


def _render_delivery(d: DeliveryResult) -> str:
    rows = []
    rows.append(f"<div class=\"delivery\" id=\"{_esc(d.delivery_id)}\">")
    rows.append(
        f"<div class=\"dhead\"><span class=\"did\">"
        f"{_esc(d.delivery_id)}</span>"
        f"<span class=\"dmeta\">inn={_esc(d.innings)} "
        f"over={_esc(d.over_number)} "
        f"event={_esc(d.event_type)} runs={_esc(d.runs)} "
        f"dur={d.duration_s:.1f}s</span></div>"
    )
    rows.append("<div class=\"grid\">")
    rows.append(
        f"<div><video controls preload=\"metadata\" "
        f"src=\"{_esc(d.video_rel)}\"></video></div>"
    )
    rows.append("<div>")
    # Results table — wrap in a scroll container because we now have
    # current + 3×layer2 + 3×claude + 3×gem31 = 10 value columns plus
    # consistency.
    header_cells = ["<th>field</th>", "<th>current</th>"]
    for i in range(RUNS_PER_MODEL):
        header_cells.append(f"<th>layer2 #{i+1}</th>")
    for i in range(RUNS_PER_MODEL):
        header_cells.append(f"<th>claude #{i+1}</th>")
    for i in range(RUNS_PER_MODEL):
        header_cells.append(f"<th>gem31 #{i+1}</th>")
    header_cells.append("<th>consistency</th>")
    rows.append("<div class=\"table-wrap\">"
                "<table><tr>" + "".join(header_cells) + "</tr>")

    for fname in CMP_FIELDS:
        cur_val = _nv(d.current.get(fname))
        l2_vals = [_nv(r.parsed.get(fname) if r.ok else None)
                   for r in d.layer2_runs]
        claude_vals = [_nv(r.parsed.get(fname) if r.ok else None)
                       for r in d.claude_runs]
        gem_vals = [_nv(r.parsed.get(fname) if r.ok else None)
                    for r in d.gemini_runs]
        c_ratio, _ = _consistency(d.claude_runs, fname)
        g_ratio, _ = _consistency(d.gemini_runs, fname)
        l_ratio, _ = _consistency(d.layer2_runs, fname)
        c_cls = _consis_class(c_ratio)
        g_cls = _consis_class(g_ratio)
        l_cls = _consis_class(l_ratio)
        # Cross-model mismatch highlighting: mark cells whose value
        # differs from the modal "reference" across all columns.
        all_vals = [cur_val] + l2_vals + claude_vals + gem_vals
        from collections import Counter
        non_empty = [v for v in all_vals if v and v != "—"]
        modal = Counter(non_empty).most_common(1)[0][0] if non_empty else None
        cells = [f"<td class=\"field\">{_esc(fname)}</td>"]
        for v, css in [(cur_val, "cur")]:
            cls = css + (" mismatch" if modal and v and v != modal else "")
            cells.append(f"<td class=\"{cls}\">{_esc(v)}</td>")
        for i, v in enumerate(l2_vals):
            css = f"l{i+1}"
            cls = css + (" mismatch" if modal and v and v != modal else "")
            cells.append(f"<td class=\"{cls}\">{_esc(v)}</td>")
        for i, v in enumerate(claude_vals):
            css = f"c{i+1}"
            cls = css + (" mismatch" if modal and v and v != modal else "")
            cells.append(f"<td class=\"{cls}\">{_esc(v)}</td>")
        for i, v in enumerate(gem_vals):
            css = f"g{i+1}"
            cls = css + (" mismatch" if modal and v and v != modal else "")
            cells.append(f"<td class=\"{cls}\">{_esc(v)}</td>")
        cells.append(
            f"<td>L:<span class=\"{l_cls}\">"
            f"{l_ratio*100:.0f}%</span>  "
            f"C:<span class=\"{c_cls}\">"
            f"{c_ratio*100:.0f}%</span>  "
            f"G:<span class=\"{g_cls}\">"
            f"{g_ratio*100:.0f}%</span></td>"
        )
        rows.append("<tr>" + "".join(cells) + "</tr>")
    rows.append("</table></div>")

    # Narratives
    rows.append("<table style=\"margin-top:10px;\">"
                "<tr><th>source</th><th>narrative</th>"
                "<th>ms</th></tr>")
    cur_narr = d.current.get("narrative") or ""
    cur_ms = d.current.get("_wall_ms") or ""
    rows.append(f"<tr><td class=\"field\">current</td>"
                f"<td class=\"narrative\">{_esc(cur_narr)}</td>"
                f"<td>{_esc(cur_ms)}</td></tr>")
    for i, r in enumerate(d.layer2_runs):
        narr = r.parsed.get("narrative") if r.ok else (r.error or "ERR")
        rows.append(f"<tr><td class=\"field\">layer2 #{i+1}</td>"
                    f"<td class=\"narrative\">{_esc(narr)}</td>"
                    f"<td>{r.wall_ms}</td></tr>")
    for i, r in enumerate(d.claude_runs):
        narr = r.parsed.get("narrative") if r.ok else (r.error or "ERR")
        rows.append(f"<tr><td class=\"field\">claude #{i+1}</td>"
                    f"<td class=\"narrative\">{_esc(narr)}</td>"
                    f"<td>{r.wall_ms}</td></tr>")
    for i, r in enumerate(d.gemini_runs):
        narr = r.parsed.get("narrative") if r.ok else (r.error or "ERR")
        rows.append(f"<tr><td class=\"field\">gem31 #{i+1}</td>"
                    f"<td class=\"narrative\">{_esc(narr)}</td>"
                    f"<td>{r.wall_ms}</td></tr>")
    rows.append("</table>")

    # Raw payloads collapsed
    rows.append("<details><summary>raw JSON (all runs)</summary>"
                "<div class=\"raw\">")
    blob = {
        "current": d.current,
        "layer2": [r.__dict__ for r in d.layer2_runs],
        "claude": [r.__dict__ for r in d.claude_runs],
        "gemini31": [r.__dict__ for r in d.gemini_runs],
    }
    rows.append(_esc(json.dumps(blob, indent=2, default=str)))
    rows.append("</div></details>")

    rows.append("</div></div></div>")
    return "".join(rows)


def _nv(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v).strip().lower()


def _consis_class(ratio: float) -> str:
    if ratio >= 0.999:
        return "consis-ok"
    if ratio >= 0.5:
        return "consis-warn"
    return "consis-bad"


# ── Main ────────────────────────────────────────────────────────────


def main():
    if not (ROOT / "logs" / "deliveries" / SESSION).exists():
        print(f"[FATAL] session dir not found: "
              f"{ROOT / 'logs' / 'deliveries' / SESSION}")
        sys.exit(2)

    # ANTHROPIC_API_KEY is only required when Claude runs are actually
    # pending (i.e. not already cached in per-delivery JSON).  This
    # lets us re-run the harness to layer on new models without
    # re-paying for Claude calls.
    claude_pending = False
    for d in DELIVERIES:
        cp = OUT_DIR / f"{d}.json"
        if not cp.exists():
            claude_pending = True
            break
        try:
            cached = json.loads(cp.read_text())
            ok = sum(1 for r in cached.get("claude_runs", [])
                     if r.get("ok"))
            if ok < RUNS_PER_MODEL:
                claude_pending = True
                break
        except Exception:
            claude_pending = True
            break
    if claude_pending and not os.environ.get("ANTHROPIC_API_KEY"):
        print("[FATAL] ANTHROPIC_API_KEY env var is not set and "
              "Claude runs are still missing. Export the key and "
              "re-run (or delete bakeoff_out/*.json to restart).")
        sys.exit(2)

    deliveries = [d for d in DELIVERIES
                  if (SESSION_DIR / d / "delivery_window.mp4").exists()]
    print(f"Bakeoff: session={SESSION} deliveries={len(deliveries)} "
          f"runs_per_model={RUNS_PER_MODEL} workers={WORKERS}",
          flush=True)

    t0 = time.time()
    results: list[DeliveryResult] = []
    with cf.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futs = {pool.submit(process_delivery, d): d for d in deliveries}
        for fut in cf.as_completed(futs):
            d = futs[fut]
            try:
                r = fut.result()
                # Persist per-delivery JSON as we go so a crash
                # doesn't lose everything.
                (OUT_DIR / f"{d}.json").write_text(
                    json.dumps(r.to_dict(), indent=2, default=str))
                results.append(r)
                c_ok = sum(1 for x in r.claude_runs if x.ok)
                g_ok = sum(1 for x in r.gemini_runs if x.ok)
                l_ok = sum(1 for x in r.layer2_runs if x.ok)
                print(f"  done {d} layer2={l_ok}/{RUNS_PER_MODEL} "
                      f"claude={c_ok}/{RUNS_PER_MODEL} "
                      f"gem={g_ok}/{RUNS_PER_MODEL}", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"  FAIL {d}: {e}", flush=True)
                traceback.print_exc()

    results.sort(key=lambda r: r.delivery_id)
    html = render_html(results)
    (OUT_DIR / "index.html").write_text(html)
    print(f"\nWrote {OUT_DIR / 'index.html'}")
    print(f"Total wall: {time.time() - t0:.1f}s")
    print("Open with: "
          f"open file://{OUT_DIR / 'index.html'}")


if __name__ == "__main__":
    main()
