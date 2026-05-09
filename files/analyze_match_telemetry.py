"""One-shot match-telemetry analyzer.

Scans a live (or completed) ``test_pipeline.py`` log and produces a
structured snapshot of pipeline behaviour — designed for use during
match 2 monitoring (2026-04-25 onward) and re-runnable at any time
(end-of-innings, end-of-match, end-of-day rollup).

Outputs:
- Human-readable text summary on stdout.
- ``--json`` flag dumps the same data as JSON for downstream tooling.

Intentionally a single self-contained script (no shadow_eval imports)
so it stays usable as the pipeline / harness evolves.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


ANSI = re.compile(r"\x1b\[\d+m")
TS = re.compile(r"\[(\d{2}):(\d{2}):(\d{2})\s+(F\d+)")
SCOUT = re.compile(
    r"\[SCOUT\] (\w+)\s+(\d+)ms .* cam=(\w+) phase=(\w+)"
)
DETAIL = re.compile(
    r"DETAIL\|(F\d+)\|(\w+)\|tag=(\w+)\|"
    r".*?\|scorer_changes=\[([^\]]*)\]"
    r".*?\|BEFORE_bowl=([^|]*?)\s*\(\d.*?\|"
    r".*?\|AFTER_bowl=([^|]*?)(?=\|)"
)
DETAIL_ANY = re.compile(
    r"DETAIL\|(F\d+)\|.*?\|scout=([^|]*)\|"
)
INVARIANT = re.compile(r"\[INVARIANT\]\s*(.*?)\x1b|\[INVARIANT\]\s*(.*)")
STYLES_PATCH = re.compile(
    r"\[STYLES-PATCH\]\s*Updated\s+(\d+)\s+card slots"
)
PASS1_DONE = re.compile(r"Pass-1 \(infer\) complete in (\d+)ms")
PASS2_DONE = re.compile(r"Pass-2 \(verify\) complete")
PASS2_FAIL = re.compile(r"Pass-2 \(verify\) LLM call failed:\s*(.*?)\x1b|Pass-2 \(verify\) LLM call failed:\s*(.*)")
ARCHIVED = re.compile(
    r"\[CLEANUP\] Archived (\d+) frames to (\S+)"
)
INNINGS2 = re.compile(r"setup_innings|set_innings_2|innings\s*[→=]\s*2")
WICKET = re.compile(r"\[FOW\].*W(\d+)")
VISION_TO = re.compile(r"\[F\d+\] Vision timeout")

# --- Fix 9-12 validation telemetry tags --------------------------------
# Format strings here mirror the source emissions (see test_pipeline.py
# lines ~2280, ~5536, ~7094, ~7105 and scoreboard.py lines ~1813, ~1820,
# ~2849).  Anchored to "[TAG]" rather than full message because phrasing
# may evolve while the tag stays stable.
FIX9A_AUTOSWAP = re.compile(
    r"\[AUTO-SWAP-TARGET\]\s+"
    r"(?:Injecting target=(\d+)\s+"
    r"\(latched_final=(\w+),\s+sb_score_live=(\w+)\)"
    r"|Target injection skipped)"
)
FIX9B_TGT_MONO = re.compile(
    r"\[TARGET-MONOTONIC\]\s+Refusing inn2 target overwrite\s+"
    r"(\d+)\s*→\s*(\d+)"
)
FIX9B_TGT_SAN = re.compile(
    r"\[TARGET-SANITY\]\s+Rejecting target=(\d+)\s+≤\s+"
    r"current_team_score=(\d+)"
)
FIX10_POST_WKT = re.compile(
    r"\[POST-WICKET-ROTATION\]\s+"
    r"(?:striker '([^']+)'|non\s+'([^']+)'|anomaly:\s+'([^']+)')"
)
FIX11_EXTRAS_INF = re.compile(
    r"\[EXTRAS-INF-GATE\]\s+wkts=(\d+):\s+proposed bat_sum=(\d+)\s+>\s+"
    r"score=(\d+)\s+\(excess=(\d+)\)"
)
FIX12_REJ_STREAK = re.compile(
    r"\[RUNS-REJECT-STREAK\]\s+([^=]+)=(\d+)\s+streak=(\d+)/(\d+)"
)
FIX12_REJ_RELEASE = re.compile(
    r"\[RUNS-REJECT-RELEASE\]\s+([^:]+):\s+(\d+)\s+consecutive\s+"
    r"rejections of runs=(\d+)"
)
STRIKER_COLLISION = re.compile(
    r"\[STRIKER-COLLISION\]\s+Refusing\s+(striker|non)="
)
# Wicket-event detection in Changes lines: "['..., 'wickets→4', ...]"
WKT_TRANSITION = re.compile(r"'wickets→(\d+)'")

# --- New 2026-04-26 telemetry (Fixes 13-18) -------------------
FIX13_CARD_PROPAGATE = re.compile(
    r"\[POST-WICKET-CARD-PROPAGATE\]\s+'([^']+)'"
)
FIX14_BALLS_CEILING = re.compile(
    r"\[BALLS-CEILING-GATE\]\s+overs=([\d\.]+)\s+\(legal_balls="
    r"(\d+),\s+ceiling=(\d+)\)"
)
FIX15_SCORE_INF = re.compile(
    r"\[SCORE-INF-GATE\]\s+score\s+(\d+)→(\d+)\s+\(advance=\+(\d+)\)"
    r"\s+>\s+explained\s+\(bat_delta=(\d+)\s+\+\s+extras_max="
    r"(\d+)\s+=\s+(\d+)\)"
)
FIX15_SCORE_INF_FLOOR = re.compile(
    r"\[SCORE-INF-GATE\]\s+proposed=(\d+)\s+<\s+"
    r"min_score_from_batters_and_extras\s+\(bat_sum=(\d+),\s+"
    r"extras=(\d+),\s+min=(\d+)\)"
)
FIX16_SM_RESET = re.compile(
    r"\[SM-INNINGS-2-RESET\]\s+reason=([^:]+):"
)
FIX17_PREMATCH_GATE = re.compile(
    r"\[PRE-MATCH-GRAPHIC-GATE\]\s+team_abbr=(\S+)\s+present"
)
FIX17_WS_GATE = re.compile(
    r"\[WS-COLD-START-GATE\]\s+(OPEN|OPEN \(timeout\))"
)
FIX18_L2_RECONCILER = re.compile(
    r"\[BAT-SUM-RECONCILER\]\s+divergence detected:\s+bat_sum="
    r"(\d+)\s+>\s+score\+\d+=\d+\s+\(excess=(\d+)\)"
)
FIX18_L3_CAP_RESET = re.compile(
    r"\[CAP-RESET-LAST-ADVANCE\]\s+iter=(\d+)\s+reset\s+'([^']+)'"
)
NEW_BATTER_BALLS_GATE = re.compile(r"\[NEW-BATTER-BALLS-GATE\]\s+([^:]+):")
BOWLER_BATTER_GATE = re.compile(r"\[BOWLER-BATTER-GATE\]\s+bowler stripped")
BOWLER_STATS_GRAPHIC_GATE = re.compile(
    r"\[BOWLER-STATS-GRAPHIC-GATE\]\s+rejecting\s+.+\s+-\s+reason=(\w+)")
BATTER_NORMALIZE = re.compile(r"\[BATTER-NORMALIZE\]\s+(.*?)$")
SM_ZERO_GRAPHIC_GATE = re.compile(r"cold-start zero candidate rejected")
OVER_RESYNC = re.compile(r"\[OVER-RESYNC\]\s+Cursor aligned to over\s+(\d+)")
ALL_OUT_AUTHORITY = re.compile(r"\[ALL-OUT-AUTHORITY\]\s+Promoted wickets")
SCORE_REGRESSION_REJECTED = re.compile(r"Score regression rejected:\s+(\d+)→(\d+)")
WS_SLOT_INVARIANT = re.compile(r"\[WS-SLOT-INVARIANT\]\s+duplicate slots")
# Lever 1 (ScoreManager _set_slot_pair) — same slot-pair class as Fix 18
# but emitted at SM write boundary; distinct tag from WS-payload repair.
SM_SLOT_INVARIANT = re.compile(
    r"\[SM-SLOT-INVARIANT\]\s+duplicate slots")
SM_W8_DISMISSED_GUARD = re.compile(r"\[SM-W8-DISMISSED-GUARD\]\s+")
STRIKER_SM_CUTOVER_REASON_BATTER = re.compile(
    r"\[STRIKER-SM-CUTOVER\].*reason=batter-arrival")
BOWLER_TEAM_OVER_CONSENSUS = re.compile(
    r"\[BOWLER-TEAM-OVER-CONSENSUS\]\s+accepting")
FIX17B_CONSENSUS_INCONSISTENT = re.compile(
    r"\[BOWLER-CONSENSUS-INCONSISTENT\]")
FIX17B_CONSENSUS_OVERRIDE = re.compile(
    r"\[BOWLER-CONSENSUS-INCONSISTENT-OVERRIDE\]")
SCORER_ACTIVE_GATE = re.compile(r"\[SCORER-ACTIVE-GATE\]\s+rejecting")
SCORER_INVARIANT_FILTER = re.compile(r"\[SCORER-INVARIANT-FILTER\]")
SCORER_DISMISSED_RESURRECT = re.compile(r"\[SCORER-DISMISSED-RESURRECT\]")
STRIKER_SM_CUTOVER = re.compile(r"\[STRIKER-SM-CUTOVER\]\s+")
STRIKER_READ_SM_CANONICAL = re.compile(r"\[STRIKER-READ-SM-CANONICAL\]\s+")
STRIKER_STATUS_GATE = re.compile(r"\[STRIKER-STATUS-GATE\]\s+Refusing")
# Path B Item 3 (dual-broadcaster LOW-risk batch telemetry)
SM_FEEDER_SYNC = re.compile(r"\[SM-FEEDER-SYNC\]")
SM_SHADOW_PARITY = re.compile(r"\[SM-SHADOW-PARITY\]")
SM_FEEDER_DIVERGENCE_BOWLER = re.compile(
    r"\[SM-FEEDER-DIVERGENCE\]\s+field=bowler_name")
# Item 2 PR 1 — SCORER schema shadow + batters invariant backstop
SCORER_SCHEMA_WOULD_DROP = re.compile(r"\[SCORER-SCHEMA-WOULD-DROP\]")
SCORER_SCHEMA_WOULD_COERCE = re.compile(r"\[SCORER-SCHEMA-WOULD-COERCE\]")
BATTERS_INVARIANT = re.compile(r"\[BATTERS-INVARIANT\]")
STRIP_ROWS_MISALIGNED = re.compile(r"\[STRIP-ROWS-MISALIGNED\]")
CAM_GRAPHIC_FP_READ = re.compile(r"\[CAM-GRAPHIC-FAST-PATH-READ\]")
CAM_GRAPHIC_FP_NOOP = re.compile(r"\[CAM-GRAPHIC-FAST-PATH-NOOP\]")
CAM_GRAPHIC_FP_REJECT = re.compile(r"\[CAM-GRAPHIC-FAST-PATH-REJECT\]")

WICKET_AUTO = re.compile(r"\[WICKET-AUTO\]")
# Fix 15 payload hygiene: visible FOW trimmed vs internal placeholder count.
FOW_INTERNAL_COUNT_LOG = re.compile(
    r"fall_of_wickets_internal_count\b")
# Fix 20 partnership backstaging (mid‑recovery) — payload fingerprint.
PARTNERSHIP_BACKSTAGED = re.compile(
    r"runs\s*=\s*None,\s*balls\s*=\s*None|"
    r"['\"]runs['\"]\s*:\s*None[^}]*['\"]balls['\"]\s*:\s*None")

# Tags monitored for `--report-pending-validation` (harness-only rollups).
PENDING_VALIDATION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("[WICKET-AUTO] (Fix 13 adjacent)", WICKET_AUTO),
    ("[POST-WICKET-CARD-PROPAGATE] (Fix 13)", FIX13_CARD_PROPAGATE),
    ("[BALLS-CEILING-GATE] (Fix 14)", FIX14_BALLS_CEILING),
    ("[SM-INNINGS-2-RESET] (Fix 16)", FIX16_SM_RESET),
    ("[SCORE-INF-GATE] advance (Layer 1.5 cap)", FIX15_SCORE_INF),
    ("[SCORE-INF-GATE] floor / physics min (Layer 1.5)",
     FIX15_SCORE_INF_FLOOR),
    ("[BOWLER-BATTER-GATE] / row suppress (17A)", BOWLER_BATTER_GATE),
    ("[BOWLER-STATS-GRAPHIC-GATE] career/aggregate strip (2026-04-28)",
     BOWLER_STATS_GRAPHIC_GATE),
    ("fall_of_wickets_internal_count / FOW placeholders (Fix 15)",
     FOW_INTERNAL_COUNT_LOG),
    ("[PRE-MATCH-GRAPHIC-GATE] (17 Path A)", FIX17_PREMATCH_GATE),
    ("[PRE-MATCH-COLD-START-GATE] (alias — may be unused)", re.compile(
        r"\[PRE-MATCH-COLD-START-GATE\]")),
    ("[SM] cold-start zero / graphic (Fix 19)", SM_ZERO_GRAPHIC_GATE),
    ("partnership backstaged runs=None (Fix 20)", PARTNERSHIP_BACKSTAGED),
    ("[OVER-RESYNC] / this-over cursor (Fix 21)", OVER_RESYNC),
    ("[ALL-OUT-AUTHORITY] (Fix 22)", ALL_OUT_AUTHORITY),
    ("[WS-SLOT-INVARIANT] (Fix 18)", WS_SLOT_INVARIANT),
    ("[SM-SLOT-INVARIANT] (Lever 1 helper repair)", SM_SLOT_INVARIANT),
    ("[STRIKER-STATUS-GATE]", STRIKER_STATUS_GATE),
    ("[BOWLER-CONSENSUS-INCONSISTENT] (17B+)", FIX17B_CONSENSUS_INCONSISTENT),
    ("[BOWLER-CONSENSUS-INCONSISTENT-OVERRIDE] (17B+)",
     FIX17B_CONSENSUS_OVERRIDE),
    ("[SCORER-INVARIANT-FILTER] (P0 staging)", SCORER_INVARIANT_FILTER),
    ("[SCORER-DISMISSED-RESURRECT] (P0 staging)", SCORER_DISMISSED_RESURRECT),
    ("[BOWLER-TEAM-OVER-CONSENSUS] (17B accelerated)", BOWLER_TEAM_OVER_CONSENSUS),
    ("[SCORER-SCHEMA-WOULD-DROP] (Item 2 shadow)", SCORER_SCHEMA_WOULD_DROP),
    ("[SCORER-SCHEMA-WOULD-COERCE] (Item 2 shadow)", SCORER_SCHEMA_WOULD_COERCE),
    ("[BATTERS-INVARIANT] backstop (Item 2)", BATTERS_INVARIANT),
    ("[STRIP-ROWS-MISALIGNED] (Thread 7 Fix 1)", STRIP_ROWS_MISALIGNED),
    ("[CAM-GRAPHIC-FAST-PATH-READ] (Thread 7 Fix 2)", CAM_GRAPHIC_FP_READ),
    ("[CAM-GRAPHIC-FAST-PATH-NOOP] (Thread 7 Fix 2)", CAM_GRAPHIC_FP_NOOP),
    ("[CAM-GRAPHIC-FAST-PATH-REJECT] (Thread 7 Fix 2)", CAM_GRAPHIC_FP_REJECT),
)
STATE_RECOVERY_CANDIDATE = re.compile(
    r"\[STATE-RECOVERY-OVERRIDE-CANDIDATE\]\s+"
    r"sig=(\S+)\s+guards=(\S+)\s+frames=(\d+)\s+"
    r"candidate_json=(\S+)\s+current_json=(\S+)\s+"
    r"coherence_json=(\S+)\s+thresholds_json=(\S+)\s+"
    r"proposed_reset=(\S+)\s+reason=(\S+)\s+"
    r"telemetry_only=(\w+)"
)
STATE_RECOVERY_OVERRIDE = re.compile(
    r"\[STATE-RECOVERY-OVERRIDE\]\s+"
    r"sig=(\S+)\s+guards=(\S+)\s+frames=(\d+)\s+"
    r"candidate_json=(\S+)\s+current_json=(\S+)\s+"
    r"coherence_json=(\S+)\s+thresholds_json=(\S+)\s+"
    r"proposed_reset=(\S+)\s+reason=(\S+)\s+"
    r"telemetry_only=(\w+)"
)

# --- Pre-fix counterfactual baselines (for validation comparison) -----
# Numbers captured from match-3 (CSK-vs-GT 2026-04-26) before Fix 9-12
# deployment.  Used to show "expected reduction" alongside post-fix
# fire counts.  When a baseline reads "—", validation passes simply by
# observing the fix fire / not fire as designed.
BASELINE_COUNTERFACTUALS: dict[str, dict[str, str | int]] = {
    "fix_9a": {
        "pre_fix_target_at_autoswap": "None or misread (F2503 in match-3)",
        "expected_post_fix": "1 fire per innings transition with "
                             "correct target value",
    },
    "fix_9b": {
        "pre_fix_target_overwrite": "F2504 misread overwrote target=159 → 66",
        "expected_post_fix": "silent on happy path; fires only when "
                             "broadcast misread proposes wrong target",
    },
    "fix_10": {
        "per_wicket_striker_collision_pre_fix":
            "Sarfaraz=88, Dube=443+, Overton=240+ (match-3 windows)",
        "expected_post_fix":
            "<10 [STRIKER-COLLISION] per witnessed wicket; "
            "[POST-WICKET-ROTATION] fires once per witnessed FOW",
    },
    "fix_11": {
        "pre_fix_phantom_admissions":
            "Brevis F732, Hosein F2408 / F1276 / F2400 / F2420 "
            "(match-3, 4-5 confirmed)",
        "expected_post_fix":
            "every sum-violation phantom hard-rejected; phantom "
            "never enters scoreboard state",
    },
    "fix_12": {
        "pre_fix_dube_window":
            "357 rejections of runs=22, 0 releases, 41:50 stuck window",
        "expected_post_fix":
            "release within RUNS_REJECT_RELEASE_N (5) consecutive "
            "rejections; stuck window collapses to ~10s",
    },
}


def strip_ansi(s: str) -> str:
    return ANSI.sub("", s)


def parse_ts(line: str, day_anchor: datetime) -> datetime | None:
    m = TS.search(line)
    if not m:
        return None
    h, m_, s, _ = m.groups()
    return day_anchor.replace(
        hour=int(h), minute=int(m_), second=int(s), microsecond=0)


@dataclass
class Snapshot:
    log_path: str
    log_first_ts: str | None = None
    log_last_ts: str | None = None
    duration_min: float = 0.0
    archive_event: str | None = None
    pass1_ms: int | None = None
    pass2_status: str = "pending"  # pending | success | timeout | other_error
    pass2_detail: str | None = None
    styles_patch_events: int = 0
    cam_total: Counter = field(default_factory=Counter)
    phase_total: Counter = field(default_factory=Counter)
    cam_phase_xtab: dict[tuple[str, str], int] = field(
        default_factory=lambda: defaultdict(int))
    cam_window_5min: Counter = field(default_factory=Counter)
    phase_window_5min: Counter = field(default_factory=Counter)
    frames_scoreboard: int = 0
    frames_graphic: int = 0
    frame_poisoned_count: int = 0
    frame_poisoned_reasons: Counter = field(default_factory=Counter)
    vision_timeouts: int = 0
    invariant_fires: Counter = field(default_factory=Counter)
    innings_transitions: int = 0
    wickets_seen: list[int] = field(default_factory=list)
    bowler_change_events: list[dict] = field(default_factory=list)
    state_latest: str | None = None
    notable_anomalies: list[str] = field(default_factory=list)
    bowler_stale_rejects: int = 0
    bowler_stale_targets: Counter = field(default_factory=Counter)
    field_monitor_warns: int = 0
    cam_by_tag: dict[tuple[str, str], int] = field(
        default_factory=lambda: defaultdict(int))
    # Detailed BOWLER-STALE rejection events for log-replay test
    # fixture construction (frame, ts, target, proposed, recorded).
    bowler_stale_events: list[dict] = field(default_factory=list)
    # Bowler-strip read events: (frame_int, ts, bowler_name) for any
    # frame where update_bowler() actively wrote to the card (BOARD
    # log "name: old -> new" with new != old). Used to derive the
    # within-over inter-ball read interval distribution and the
    # across-over inter-bowler gap distribution that inform the
    # freshness-window threshold for the BOWLER-STALE fix.
    bowler_strip_reads: list[dict] = field(default_factory=list)

    # Fix 9-12 telemetry events.  Each list captures (frame, ts, ...)
    # tuples for the corresponding tag.  Used by the per-fix report
    # functions (--report-9a, --report-9b, --report-10, --report-11,
    # --report-12) to compute positive-fire counts, negative-fire
    # validation, and per-wicket / per-innings-transition breakdowns.
    fix9a_autoswap_events: list[dict] = field(default_factory=list)
    fix9b_target_monotonic_events: list[dict] = field(default_factory=list)
    fix9b_target_sanity_events: list[dict] = field(default_factory=list)
    fix10_post_wicket_events: list[dict] = field(default_factory=list)
    fix11_extras_inf_events: list[dict] = field(default_factory=list)
    fix12_reject_streak_events: list[dict] = field(default_factory=list)
    fix12_reject_release_events: list[dict] = field(default_factory=list)
    striker_collision_events: list[dict] = field(default_factory=list)
    # Fix 13-18 telemetry events (added 2026-04-26 ship day).
    fix13_card_propagate_events: list[dict] = field(default_factory=list)
    fix14_balls_ceiling_events: list[dict] = field(default_factory=list)
    fix15_score_inf_events: list[dict] = field(default_factory=list)
    fix15_score_inf_floor_events: list[dict] = field(default_factory=list)
    fix16_sm_reset_events: list[dict] = field(default_factory=list)
    fix17_prematch_gate_events: list[dict] = field(default_factory=list)
    fix17_ws_gate_events: list[dict] = field(default_factory=list)
    fix18_l2_reconciler_events: list[dict] = field(default_factory=list)
    fix18_l3_cap_reset_events: list[dict] = field(default_factory=list)
    bundle_bc_events: dict[str, list[dict]] = field(
        default_factory=lambda: defaultdict(list))
    pending_validation_hits: dict[str, int] = field(default_factory=dict)
    state_recovery_candidate_events: list[dict] = field(
        default_factory=list)
    state_recovery_override_events: list[dict] = field(default_factory=list)
    # Wicket-transition frames (where Changes contained 'wickets→N').
    # Used as bin boundaries for per-wicket Fix 10 reporting.
    wicket_transition_frames: list[dict] = field(default_factory=list)


def analyze(log_path: Path, window_min: int = 5) -> Snapshot:
    snap = Snapshot(log_path=str(log_path))
    if not log_path.exists():
        snap.notable_anomalies.append(f"log not found: {log_path}")
        return snap

    day_anchor = datetime.fromtimestamp(log_path.stat().st_mtime).replace(
        hour=0, minute=0, second=0, microsecond=0)
    last_ts: datetime | None = None
    first_ts: datetime | None = None
    states: list[str] = []
    for raw in log_path.read_text(errors="replace").splitlines():
        line = strip_ansi(raw)
        ts = parse_ts(line, day_anchor)
        if ts:
            if first_ts is None:
                first_ts = ts
            last_ts = ts

        if m := SCOUT.search(line):
            _tag, _ms, cam, phase = m.groups()
            snap.cam_total[cam] += 1
            snap.phase_total[phase] += 1
            snap.cam_phase_xtab[(cam, phase)] += 1

        if "SCOREBOARD — #" in line:
            snap.frames_scoreboard += 1

        if "GRAPHIC — #" in line:
            snap.frames_graphic += 1

        if "FRAME_POISONED" in line:
            snap.frame_poisoned_count += 1
            mp = re.search(r"FRAME_POISONED:(\w+)", line)
            if mp:
                snap.frame_poisoned_reasons[mp.group(1)] += 1

        if VISION_TO.search(line):
            snap.vision_timeouts += 1

        if "[BOWLER-STALE] Rejecting" in line:
            snap.bowler_stale_rejects += 1
            mn = re.search(r"Rejecting '([^']+)'", line)
            if mn:
                snap.bowler_stale_targets[mn.group(1)] += 1
            mfig = re.search(
                r"proposed (\S+) exactly matches recorded (\S+)", line)
            mframe = re.search(r"\[(\d{2}:\d{2}:\d{2})\s+(F\d+)", line)
            if mn and mframe:
                snap.bowler_stale_events.append({
                    "ts": mframe.group(1),
                    "frame": mframe.group(2),
                    "target": mn.group(1),
                    "proposed": mfig.group(1) if mfig else None,
                    "recorded": mfig.group(2) if mfig else None,
                })
        if "[FIELD-MONITOR] Field unchanged" in line:
            snap.field_monitor_warns += 1
        # BOARD-line bowler-strip-read tracking.  Format example:
        # "[20:08:39 F425 BOARD] INFO: Pat Cummins: 0/20 (2) -> 0/20 (2.1) [F425]"
        # i.e. <name>: <w>/<r> (<ov>) -> <w>/<r> (<ov>) [F##].  Any
        # line where old != new is an active write event triggered
        # by Scout's broadcast read.  We use these as proxies for
        # "bowler-strip read events" — the interval distribution
        # informs the BOWLER-STALE freshness-window threshold.
        mboard_bowl = re.search(
            r"\[(\d{2}:\d{2}:\d{2})\s+(F\d+)\s+BOARD\]\s+INFO:\s+"
            r"([A-Z][\w. '-]+?):\s+"
            r"(\d+/\d+\s*\([\d.]+\))\s+->\s+(\d+/\d+\s*\([\d.]+\))",
            line)
        if mboard_bowl:
            old_v = mboard_bowl.group(4)
            new_v = mboard_bowl.group(5)
            if old_v != new_v:
                snap.bowler_strip_reads.append({
                    "ts": mboard_bowl.group(1),
                    "frame": mboard_bowl.group(2),
                    "frame_int": int(mboard_bowl.group(2)[1:]),
                    "name": mboard_bowl.group(3).strip(),
                    "from": old_v,
                    "to": new_v,
                })

        if m := INVARIANT.search(line):
            msg = (m.group(1) or m.group(2) or "").strip()
            tag = "other"
            for needle, label in [
                ("Refusing to un-dismiss", "p0a-fix1-undismiss"),
                ("max two active", "p0a-fix2-max-two"),
                ("after dismissal", "p0a-fix3-post-dismissal"),
                ("Re-asserting witnessed", "p0b-path2-reassert"),
                ("active_batters", "p0a-active-set"),
            ]:
                if needle in msg:
                    tag = label
                    break
            snap.invariant_fires[tag] += 1

        if STYLES_PATCH.search(line):
            snap.styles_patch_events += 1
            snap.pass2_status = "success"
        if PASS2_DONE.search(line):
            snap.pass2_status = "success"
        if m := PASS2_FAIL.search(line):
            detail = (m.group(1) or m.group(2) or "").strip()
            snap.pass2_status = (
                "timeout" if "timed out" in detail.lower() else "other_error")
            snap.pass2_detail = detail
        if m := PASS1_DONE.search(line):
            snap.pass1_ms = int(m.group(1))
        if m := ARCHIVED.search(line):
            snap.archive_event = (
                f"archived {m.group(1)} frames → {m.group(2)}")
        if INNINGS2.search(line) and "setup_innings" in line:
            snap.innings_transitions += 1
        if m := WICKET.search(line):
            n = int(m.group(1))
            if n not in snap.wickets_seen:
                snap.wickets_seen.append(n)

        if "STATE: " in line:
            states.append(line.split("STATE: ", 1)[1].strip())

        # Fix 9-12 telemetry capture (single-pass, additive).
        ts_str = ""
        frame_str = ""
        mts = re.search(r"\[(\d{2}:\d{2}:\d{2})\s+(F\d+)", line)
        if mts:
            ts_str = mts.group(1)
            frame_str = mts.group(2)

        if m := FIX9A_AUTOSWAP.search(line):
            snap.fix9a_autoswap_events.append({
                "ts": ts_str, "frame": frame_str,
                "target": m.group(1),
                "latched_final": m.group(2),
                "sb_score_live": m.group(3),
                "skipped": m.group(1) is None,
            })
        if m := FIX9B_TGT_MONO.search(line):
            snap.fix9b_target_monotonic_events.append({
                "ts": ts_str, "frame": frame_str,
                "current": int(m.group(1)),
                "proposed": int(m.group(2)),
            })
        if m := FIX9B_TGT_SAN.search(line):
            snap.fix9b_target_sanity_events.append({
                "ts": ts_str, "frame": frame_str,
                "proposed_target": int(m.group(1)),
                "current_team_score": int(m.group(2)),
            })
        if m := FIX10_POST_WKT.search(line):
            kind = ("striker" if m.group(1) else
                    "non" if m.group(2) else "anomaly")
            snap.fix10_post_wicket_events.append({
                "ts": ts_str, "frame": frame_str,
                "kind": kind,
                "batter": m.group(1) or m.group(2) or m.group(3),
            })
        if m := FIX11_EXTRAS_INF.search(line):
            snap.fix11_extras_inf_events.append({
                "ts": ts_str, "frame": frame_str,
                "wkts": int(m.group(1)),
                "bat_sum": int(m.group(2)),
                "score": int(m.group(3)),
                "excess": int(m.group(4)),
            })
        if m := FIX12_REJ_STREAK.search(line):
            snap.fix12_reject_streak_events.append({
                "ts": ts_str, "frame": frame_str,
                "batter": m.group(1).strip(),
                "value": int(m.group(2)),
                "count": int(m.group(3)),
                "threshold": int(m.group(4)),
            })
        if m := FIX12_REJ_RELEASE.search(line):
            snap.fix12_reject_release_events.append({
                "ts": ts_str, "frame": frame_str,
                "batter": m.group(1).strip(),
                "consecutive": int(m.group(2)),
                "released_value": int(m.group(3)),
            })
        if STRIKER_COLLISION.search(line):
            snap.striker_collision_events.append({
                "ts": ts_str, "frame": frame_str,
            })
        if m := FIX13_CARD_PROPAGATE.search(line):
            snap.fix13_card_propagate_events.append({
                "ts": ts_str, "frame": frame_str,
                "batter": m.group(1),
            })
        if m := FIX14_BALLS_CEILING.search(line):
            snap.fix14_balls_ceiling_events.append({
                "ts": ts_str, "frame": frame_str,
                "overs": m.group(1),
                "legal_balls": int(m.group(2)),
                "ceiling": int(m.group(3)),
            })
        if m := FIX15_SCORE_INF.search(line):
            snap.fix15_score_inf_events.append({
                "ts": ts_str, "frame": frame_str,
                "score_before": int(m.group(1)),
                "score_after": int(m.group(2)),
                "advance": int(m.group(3)),
                "bat_delta": int(m.group(4)),
                "extras_max": int(m.group(5)),
                "explained": int(m.group(6)),
            })
        if m := FIX15_SCORE_INF_FLOOR.search(line):
            snap.fix15_score_inf_floor_events.append({
                "ts": ts_str, "frame": frame_str,
                "proposed": int(m.group(1)),
                "bat_sum": int(m.group(2)),
                "extras": int(m.group(3)),
                "min": int(m.group(4)),
            })
        if m := FIX16_SM_RESET.search(line):
            snap.fix16_sm_reset_events.append({
                "ts": ts_str, "frame": frame_str,
                "reason": m.group(1),
            })
        if m := FIX17_PREMATCH_GATE.search(line):
            snap.fix17_prematch_gate_events.append({
                "ts": ts_str, "frame": frame_str,
                "team_abbr": m.group(1),
            })
        if m := FIX17_WS_GATE.search(line):
            snap.fix17_ws_gate_events.append({
                "ts": ts_str, "frame": frame_str,
                "kind": m.group(1),
            })
        if m := FIX18_L2_RECONCILER.search(line):
            snap.fix18_l2_reconciler_events.append({
                "ts": ts_str, "frame": frame_str,
                "bat_sum": int(m.group(1)),
                "excess": int(m.group(2)),
            })
        if m := FIX18_L3_CAP_RESET.search(line):
            snap.fix18_l3_cap_reset_events.append({
                "ts": ts_str, "frame": frame_str,
                "iter": int(m.group(1)),
                "batter": m.group(2),
            })
        for key, rx in (
                ("6_batter_normalize", BATTER_NORMALIZE),
                ("16_new_batter_balls", NEW_BATTER_BALLS_GATE),
                ("17a_bowler_batter_gate", BOWLER_BATTER_GATE),
                ("bowler_stats_graphic_gate", BOWLER_STATS_GRAPHIC_GATE),
                ("19_zero_graphic_gate", SM_ZERO_GRAPHIC_GATE),
                ("21_over_resync", OVER_RESYNC),
                ("22_all_out_authority", ALL_OUT_AUTHORITY),
                ("14_score_regression", SCORE_REGRESSION_REJECTED),
                ("18_ws_slot_invariant", WS_SLOT_INVARIANT),
                ("lever1_sm_slot_invariant", SM_SLOT_INVARIANT),
                ("17b_bowler_team_over", BOWLER_TEAM_OVER_CONSENSUS),
                ("17b_bowler_consensus_inconsistent", FIX17B_CONSENSUS_INCONSISTENT),
                ("17b_bowler_consensus_override", FIX17B_CONSENSUS_OVERRIDE),
                ("15_score_inf_floor", FIX15_SCORE_INF_FLOOR),
                ("cluster1_scorer_active_gate", SCORER_ACTIVE_GATE),
                ("cluster1_striker_sm_cutover", STRIKER_SM_CUTOVER),
                ("striker_read_sm_canonical", STRIKER_READ_SM_CANONICAL),
                ("cluster1_striker_status_gate", STRIKER_STATUS_GATE),
                ("path_b_sm_feeder_sync", SM_FEEDER_SYNC),
                ("path_b_sm_shadow_parity", SM_SHADOW_PARITY),
                ("path_b_bowler_feeder_divergence",
                 SM_FEEDER_DIVERGENCE_BOWLER),
                ("item2_scorer_schema_would_drop", SCORER_SCHEMA_WOULD_DROP),
                ("item2_scorer_schema_would_coerce", SCORER_SCHEMA_WOULD_COERCE),
                ("item2_batters_invariant", BATTERS_INVARIANT),
                ("thread7_strip_rows_misaligned", STRIP_ROWS_MISALIGNED),
                ("thread7_cam_graphic_fp_read", CAM_GRAPHIC_FP_READ),
                ("thread7_cam_graphic_fp_noop", CAM_GRAPHIC_FP_NOOP),
                ("thread7_cam_graphic_fp_reject", CAM_GRAPHIC_FP_REJECT)):
            if m := rx.search(line):
                snap.bundle_bc_events[key].append({
                    "ts": ts_str,
                    "frame": frame_str,
                    "match": m.group(0),
                })
        for lbl, rx in PENDING_VALIDATION_PATTERNS:
            if rx.search(line):
                snap.pending_validation_hits[lbl] = (
                    snap.pending_validation_hits.get(lbl, 0) + 1)
        for _rx, _dest in (
                (STATE_RECOVERY_CANDIDATE,
                 snap.state_recovery_candidate_events),
                (STATE_RECOVERY_OVERRIDE,
                 snap.state_recovery_override_events)):
            if m := _rx.search(line):
                try:
                    candidate = json.loads(m.group(4))
                except json.JSONDecodeError:
                    candidate = {"_parse_error": m.group(4)}
                try:
                    current = json.loads(m.group(5))
                except json.JSONDecodeError:
                    current = {"_parse_error": m.group(5)}
                try:
                    coherence = json.loads(m.group(6))
                except json.JSONDecodeError:
                    coherence = {"_parse_error": m.group(6)}
                try:
                    thresholds = json.loads(m.group(7))
                except json.JSONDecodeError:
                    thresholds = {"_parse_error": m.group(7)}
                reset = [] if m.group(8) == "-" else m.group(8).split(",")
                _dest.append({
                    "ts": ts_str, "frame": frame_str,
                    "sig": m.group(1),
                    "guards": m.group(2).split(","),
                    "frames_seen": int(m.group(3)),
                    "candidate": candidate,
                    "current": current,
                    "coherence": coherence,
                    "threshold_frames": thresholds,
                    "proposed_reset": reset,
                    "reason": m.group(9),
                    "telemetry_only": m.group(10).lower() == "true",
                })
        if m := WKT_TRANSITION.search(line):
            wkts_n = int(m.group(1))
            # Only record the *first* observation of each wicket count
            # (subsequent re-emissions of the same Changes are
            # duplicates from the same wicket event).
            if not any(w["wickets"] == wkts_n
                       for w in snap.wicket_transition_frames):
                snap.wicket_transition_frames.append({
                    "ts": ts_str, "frame": frame_str,
                    "wickets": wkts_n,
                })

    snap.state_latest = states[-1] if states else None
    if first_ts:
        snap.log_first_ts = first_ts.strftime("%H:%M:%S")
    if last_ts:
        snap.log_last_ts = last_ts.strftime("%H:%M:%S")
    if first_ts and last_ts:
        snap.duration_min = round(
            (last_ts - first_ts).total_seconds() / 60.0, 1)

    if last_ts is not None:
        cutoff = last_ts - timedelta(minutes=window_min)
        for raw in log_path.read_text(errors="replace").splitlines():
            line = strip_ansi(raw)
            ts = parse_ts(line, day_anchor)
            if ts is None or ts < cutoff:
                continue
            if m := SCOUT.search(line):
                _tag, _ms, cam, phase = m.groups()
                snap.cam_window_5min[cam] += 1
                snap.phase_window_5min[phase] += 1

    bowler_events: list[tuple[datetime, str, str]] = []
    for raw in log_path.read_text(errors="replace").splitlines():
        line = strip_ansi(raw)
        ts = parse_ts(line, day_anchor)
        if ts is None:
            continue
        if "ext_bowl=" in line and "BEFORE_bowl=" in line and "AFTER_bowl=" in line:
            ext = re.search(r"ext_bowl=([^|]*?)\|", line)
            after = re.search(r"AFTER_bowl=([^|]*?)\|", line)
            if not ext or not after:
                continue
            ext_v = ext.group(1).strip()
            aft_v = after.group(1).strip()
            ext_name = ext_v.split()[0] if ext_v and ext_v != "—" else ""
            aft_name = aft_v.split()[0] if aft_v and aft_v != "—" else ""
            if ext_name and aft_name and ext_name != aft_name and "?" not in aft_v:
                bowler_events.append((ts, ext_v, aft_v))

    seen_pairs: set[tuple[str, str]] = set()
    for ts, ext_v, aft_v in bowler_events[:30]:
        key = (ext_v, aft_v)
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        snap.bowler_change_events.append({
            "ts": ts.strftime("%H:%M:%S"),
            "scout_reads": ext_v,
            "scoreboard_state": aft_v,
        })

    return snap


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    if len(s) == 1:
        return float(s[0])
    k = (len(s) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return float(s[f])
    return float(s[f] + (s[c] - s[f]) * (k - f))


def compute_interval_distributions(
    snap: Snapshot,
) -> dict[str, dict[str, float | int | None]]:
    """Inter-read interval distributions in frames.

    Two distinct populations:
    - within_bowler: gaps between consecutive BOARD writes for the
      *same* bowler (proxy for inter-ball strip-read intervals
      during a single spell).
    - across_bowler: gaps between the last BOARD write of bowler A
      and the first BOARD write of the next-different bowler B
      (proxy for inter-over handoff gaps — the genuine stale-
      graphic window the BOWLER-STALE defense exists to cover).

    Returns dict with min / median / p95 / max / n for each.
    """
    within: list[int] = []
    across: list[int] = []
    last_frame_per_bowler: dict[str, int] = {}
    last_global_bowler: str | None = None
    last_global_frame: int | None = None
    for ev in snap.bowler_strip_reads:
        f = ev["frame_int"]
        name = ev["name"]
        if name in last_frame_per_bowler:
            within.append(f - last_frame_per_bowler[name])
        last_frame_per_bowler[name] = f
        if (last_global_bowler is not None
                and name != last_global_bowler
                and last_global_frame is not None):
            across.append(f - last_global_frame)
        last_global_bowler = name
        last_global_frame = f

    def stats(xs: list[int]) -> dict[str, float | int | None]:
        return {
            "n": len(xs),
            "min": (min(xs) if xs else None),
            "median": _percentile([float(x) for x in xs], 50),
            "p95": _percentile([float(x) for x in xs], 95),
            "max": (max(xs) if xs else None),
        }

    return {
        "within_bowler_frames": stats(within),
        "across_bowler_frames": stats(across),
    }


def _frame_int(frame_str: str) -> int:
    """Parse 'F123' → 123; returns -1 if malformed."""
    try:
        return int(frame_str[1:]) if frame_str.startswith("F") else -1
    except (ValueError, IndexError):
        return -1


def _bin_by_wicket(
    events: list[dict],
    wicket_frames: list[dict],
) -> dict[int, list[dict]]:
    """Bin events into [wicket_n_start, wicket_(n+1)_start) windows.

    Wicket 0 covers the pre-first-wicket window; wicket N covers the
    window after the Nth wicket transition until the next.  Used by
    the Fix 10 per-wicket counterfactual report.
    """
    if not wicket_frames:
        return {0: events[:]}
    sorted_wkts = sorted(wicket_frames, key=lambda w: _frame_int(w["frame"]))
    bins: dict[int, list[dict]] = {0: []}
    for w in sorted_wkts:
        bins[w["wickets"]] = []
    for ev in events:
        ev_f = _frame_int(ev["frame"])
        owner = 0
        for w in sorted_wkts:
            if ev_f >= _frame_int(w["frame"]):
                owner = w["wickets"]
            else:
                break
        bins.setdefault(owner, []).append(ev)
    return bins


def report_fix_9a(s: Snapshot) -> str:
    out: list[str] = ["## Fix 9a validation: AUTO-SWAP-TARGET injection"]
    base = BASELINE_COUNTERFACTUALS["fix_9a"]
    out.append(f"  baseline (pre-fix): {base['pre_fix_target_at_autoswap']}")
    out.append(f"  expected post-fix:  {base['expected_post_fix']}")
    out.append(f"  positive fires:     {len(s.fix9a_autoswap_events)}")
    if s.innings_transitions:
        out.append(f"  innings transitions: {s.innings_transitions}")
    if s.fix9a_autoswap_events:
        for ev in s.fix9a_autoswap_events:
            if ev["skipped"]:
                out.append(f"    {ev['ts']} {ev['frame']}  SKIPPED "
                           "(both latched_final and sb_score=0)")
            else:
                out.append(f"    {ev['ts']} {ev['frame']}  "
                           f"target={ev['target']}  "
                           f"latched_final={ev['latched_final']}  "
                           f"sb_score_live={ev['sb_score_live']}")
        out.append("  status: FIRED — validate target value matches "
                   "(innings_1_final + 1)")
    elif s.innings_transitions:
        out.append("  status: TRIGGER OCCURRED but no fire — "
                   "investigate coverage gap")
    else:
        out.append("  status: trigger condition (innings transition) "
                   "not yet observed in this log")
    return "\n".join(out) + "\n"


def report_fix_9b(s: Snapshot) -> str:
    out: list[str] = ["## Fix 9b validation: TARGET-MONOTONIC + TARGET-SANITY"]
    base = BASELINE_COUNTERFACTUALS["fix_9b"]
    out.append(f"  baseline (pre-fix): {base['pre_fix_target_overwrite']}")
    out.append(f"  expected post-fix:  {base['expected_post_fix']}")
    n_mono = len(s.fix9b_target_monotonic_events)
    n_san = len(s.fix9b_target_sanity_events)
    out.append(f"  TARGET-MONOTONIC fires: {n_mono}")
    out.append(f"  TARGET-SANITY fires:    {n_san}")
    for ev in s.fix9b_target_monotonic_events[:5]:
        out.append(f"    [MONO] {ev['ts']} {ev['frame']}  "
                   f"current={ev['current']} proposed={ev['proposed']} "
                   f"(rejected)")
    for ev in s.fix9b_target_sanity_events[:5]:
        out.append(f"    [SAN]  {ev['ts']} {ev['frame']}  "
                   f"proposed={ev['proposed_target']} ≤ "
                   f"score={ev['current_team_score']} (rejected)")
    if n_mono == 0 and n_san == 0:
        out.append("  status: SILENT — Fix 9a doing its job, no "
                   "downstream misreads to backstop (correct)")
    else:
        out.append("  status: ACTIVE BACKSTOP — Fix 9a missed something "
                   "and 9b caught it; investigate misread upstream")
    return "\n".join(out) + "\n"


def report_fix_10(s: Snapshot, per_wicket: bool = False) -> str:
    out: list[str] = ["## Fix 10 validation: POST-WICKET-ROTATION hook"]
    base = BASELINE_COUNTERFACTUALS["fix_10"]
    out.append(f"  baseline (pre-fix): "
               f"{base['per_wicket_striker_collision_pre_fix']}")
    out.append(f"  expected post-fix:  {base['expected_post_fix']}")
    n_rot = len(s.fix10_post_wicket_events)
    n_col = len(s.striker_collision_events)
    n_wkt = len(s.wicket_transition_frames)
    out.append(f"  witnessed wicket transitions: {n_wkt}")
    out.append(f"  POST-WICKET-ROTATION fires:   {n_rot}")
    out.append(f"  STRIKER-COLLISION fires:      {n_col}")
    if n_wkt:
        ratio = n_col / n_wkt
        out.append(f"  STRIKER-COLLISION per wicket: "
                   f"{ratio:.1f} (target: <10)")
    if per_wicket and (s.fix10_post_wicket_events
                       or s.striker_collision_events):
        rot_bins = _bin_by_wicket(
            s.fix10_post_wicket_events, s.wicket_transition_frames)
        col_bins = _bin_by_wicket(
            s.striker_collision_events, s.wicket_transition_frames)
        out.append("  per-wicket histogram:")
        all_keys = sorted(set(rot_bins) | set(col_bins))
        for k in all_keys:
            r = len(rot_bins.get(k, []))
            c = len(col_bins.get(k, []))
            out.append(f"    wicket {k}: rotations={r}  collisions={c}")
    if n_rot == 0 and n_wkt > 0:
        out.append("  status: TRIGGER OCCURRED (witnessed FOW seen) "
                   "but no rotation fire — investigate")
    elif n_rot == 0:
        out.append("  status: trigger condition (witnessed wicket) "
                   "not yet observed")
    elif n_wkt > 0 and n_col / max(n_wkt, 1) < 10:
        out.append("  status: VALIDATED — collision rate well below "
                   "pre-fix baseline, rotation closing the gap")
    else:
        out.append("  status: PARTIAL — rotation fires but collision "
                   "rate still elevated; investigate residual cases")
    return "\n".join(out) + "\n"


def report_fix_11(s: Snapshot) -> str:
    out: list[str] = ["## Fix 11 validation: EXTRAS-INF admission gate"]
    base = BASELINE_COUNTERFACTUALS["fix_11"]
    out.append(f"  baseline (pre-fix): {base['pre_fix_phantom_admissions']}")
    out.append(f"  expected post-fix:  {base['expected_post_fix']}")
    n = len(s.fix11_extras_inf_events)
    out.append(f"  EXTRAS-INF-GATE fires: {n}")
    for ev in s.fix11_extras_inf_events[:10]:
        out.append(f"    {ev['ts']} {ev['frame']}  "
                   f"bat_sum={ev['bat_sum']} > score={ev['score']} "
                   f"(excess={ev['excess']}, wkts={ev['wkts']})")
    if n > 10:
        out.append(f"    ... +{n - 10} more")
    if n == 0:
        out.append("  status: SILENT — no sum-violation phantoms "
                   "proposed in this log (correct on clean match)")
    else:
        out.append("  status: ACTIVE GATE — phantom admissions "
                   "blocked; verify scoreboard state unchanged on "
                   "fire frames")
    return "\n".join(out) + "\n"


def report_fix_12(s: Snapshot) -> str:
    out: list[str] = ["## Fix 12 validation: RUNS-REJECT-RELEASE (Layer 4)"]
    base = BASELINE_COUNTERFACTUALS["fix_12"]
    out.append(f"  baseline (pre-fix): {base['pre_fix_dube_window']}")
    out.append(f"  expected post-fix:  {base['expected_post_fix']}")
    n_streak = len(s.fix12_reject_streak_events)
    n_release = len(s.fix12_reject_release_events)
    out.append(f"  RUNS-REJECT-STREAK fires:  {n_streak}")
    out.append(f"  RUNS-REJECT-RELEASE fires: {n_release}")
    if n_release > 0:
        for ev in s.fix12_reject_release_events[:5]:
            out.append(f"    {ev['ts']} {ev['frame']}  "
                       f"{ev['batter']}: released runs="
                       f"{ev['released_value']} after "
                       f"{ev['consecutive']} rejections")
    # Per-batter streak summary
    by_batter: dict[str, list[dict]] = defaultdict(list)
    for ev in s.fix12_reject_streak_events:
        by_batter[ev["batter"]].append(ev)
    if by_batter:
        out.append("  per-batter streak summary:")
        for name, evs in sorted(
                by_batter.items(), key=lambda x: -len(x[1])):
            max_streak = max(e["count"] for e in evs)
            out.append(f"    {name}: {len(evs)} rejection events, "
                       f"max streak={max_streak}/{evs[0]['threshold']}")
    if n_streak == 0:
        out.append("  status: SILENT — no runs-regression rejections "
                   "in this log (correct on clean match)")
    elif n_release == 0:
        out.append("  status: STREAK ACTIVE BUT NO RELEASE — Layer 4 "
                   "tracking phantom rejections; release pending "
                   "consensus threshold")
    else:
        out.append("  status: VALIDATED — Layer 4 fired releases on "
                   "stuck-window phantoms (compare consecutive count "
                   "against pre-fix Dube 357 baseline)")
    return "\n".join(out) + "\n"


def report_fix_13(s: Snapshot) -> str:
    out: list[str] = ["## Fix 13 validation: POST-WICKET-CARD-PROPAGATE (Path D)"]
    out.append("  baseline (pre-fix): rotation hook silent on placeholder→"
               "witnessed upgrade (Powell F258, LSG-vs-KKR Apr 26)")
    out.append("  expected post-fix:  fires once per delayed-witness path "
               "where dismissed batter is no longer in slots")
    n = len(s.fix13_card_propagate_events)
    out.append(f"  POST-WICKET-CARD-PROPAGATE fires: {n}")
    for ev in s.fix13_card_propagate_events[:10]:
        out.append(f"    {ev['ts']} {ev['frame']}  batter='{ev['batter']}'")
    if n == 0:
        out.append("  status: SILENT — no placeholder→witnessed upgrades "
                   "with delayed-witness pattern in this log.  Note: "
                   "P0 (7) backlog item — this fix does NOT cover "
                   "_unwitnessed-only FOWs (e.g. Marsh F775 in this match)")
    else:
        out.append("  status: FIRED — Path D engaged on delayed-witness "
                   "card-propagation path (validates against Powell F258 "
                   "fixture)")
    return "\n".join(out) + "\n"


def report_fix_14(s: Snapshot) -> str:
    out: list[str] = ["## Fix 14 validation: BALLS-CEILING-GATE (cricket-physics)"]
    out.append("  baseline (pre-fix): impossible balls counts admitted "
               "(e.g. Powell 95 balls on 0.5 overs in match-3)")
    out.append("  expected post-fix:  rejects per-batter balls > "
               "overs*6+ball+tolerance(2)")
    n = len(s.fix14_balls_ceiling_events)
    out.append(f"  BALLS-CEILING-GATE fires: {n}")
    for ev in s.fix14_balls_ceiling_events[:10]:
        out.append(f"    {ev['ts']} {ev['frame']}  overs={ev['overs']} "
                   f"legal_balls={ev['legal_balls']} ceiling={ev['ceiling']}")
    if n == 0:
        out.append("  status: SILENT — no impossible balls counts in this "
                   "log (correct on clean match)")
    else:
        out.append("  status: ACTIVE GATE — phantom balls counts "
                   "blocked at admission")
    return "\n".join(out) + "\n"


def report_fix_15(s: Snapshot) -> str:
    out: list[str] = ["## Fix 15 validation: SCORE-INF-GATE (Layer 1.5 score-side)"]
    out.append("  baseline (pre-fix): unexplained score advances "
               "admitted (sibling phantom path to Fix 11 batter side)")
    out.append("  expected post-fix:  (a) cap-gate rejects advances "
               "> bat_delta + extras_max(6) + wkt_headroom")
    out.append("                      (b) floor-gate rejects "
               "proposed score < bat_sum + extras['total']")
    n_adv = len(s.fix15_score_inf_events)
    n_floor = len(s.fix15_score_inf_floor_events)
    out.append(f"  SCORE-INF-GATE advance fires: {n_adv}")
    for ev in s.fix15_score_inf_events[:10]:
        out.append(f"    {ev['ts']} {ev['frame']}  "
                   f"score {ev['score_before']}→{ev['score_after']} "
                   f"(advance=+{ev['advance']}) > "
                   f"bat_delta={ev['bat_delta']}+extras_max={ev['extras_max']}"
                   f"={ev['explained']}")
    out.append(f"  SCORE-INF-GATE floor fires: {n_floor}")
    for ev in s.fix15_score_inf_floor_events[:10]:
        out.append(
            f"    {ev['ts']} {ev['frame']}  proposed={ev['proposed']} < "
            f"min={ev['min']} (bat_sum={ev['bat_sum']}, extras={ev['extras']})")
    if n_adv == 0 and n_floor == 0:
        out.append("  status: SILENT — no score-side INF gate fires in "
                   "this log (correct on clean match)")
    elif n_adv or n_floor:
        out.append("  status: ACTIVE GATE — at least one Layer 1.5 path "
                   "blocked a score commit at admission")
    return "\n".join(out) + "\n"


def report_fix_16(s: Snapshot) -> str:
    out: list[str] = ["## Fix 16 validation: SM-INNINGS-2-RESET (canonical scalar reset)"]
    out.append("  baseline (pre-fix): SM scalar fields (batting_team, "
               "this_over, etc.) leaked across innings transitions via "
               "3 separate callsites")
    out.append("  expected post-fix:  fires exactly once per innings "
               "transition with reason=auto_swap | wickets_regressed | "
               "manual")
    n = len(s.fix16_sm_reset_events)
    out.append(f"  SM-INNINGS-2-RESET fires: {n}")
    for ev in s.fix16_sm_reset_events[:5]:
        out.append(f"    {ev['ts']} {ev['frame']}  reason={ev['reason']}")
    if n == 0 and s.innings_transitions == 0:
        out.append("  status: trigger condition (innings transition) "
                   "not yet observed in this log")
    elif n == 0 and s.innings_transitions:
        out.append("  status: TRIGGER OCCURRED but no fire — "
                   "investigate SM-internal vs pipeline-driven path "
                   "(see backlog P1 (8))")
    elif n >= 1:
        out.append("  status: FIRED — canonical reset path engaged")
    return "\n".join(out) + "\n"


def report_fix_17(s: Snapshot) -> str:
    out: list[str] = ["## Fix 17 validation: cold-start (Path A + Path D)"]
    out.append("  baseline (pre-fix): 4:16 min UI bad-state window in "
               "match-3 from pre-match LSG 0-0(0.0) graphics latching "
               "wrong batting_team")
    out.append("  expected post-fix:  Path A blocks team_abbr commit on "
               "0-0 strips during cold-start; Path D suppresses WS "
               "broadcast until first stable state")

    n_a = len(s.fix17_prematch_gate_events)
    out.append(f"  PRE-MATCH-GRAPHIC-GATE (Path A) fires: {n_a}")
    for ev in s.fix17_prematch_gate_events[:10]:
        out.append(f"    {ev['ts']} {ev['frame']}  team_abbr="
                   f"{ev['team_abbr']}")

    n_d = len(s.fix17_ws_gate_events)
    out.append(f"  WS-COLD-START-GATE (Path D) events:    {n_d}")
    for ev in s.fix17_ws_gate_events[:10]:
        out.append(f"    {ev['ts']} {ev['frame']}  kind={ev['kind']}")

    if n_a == 0 and n_d == 0:
        out.append("  status: SILENT — no cold-start chaos in this log "
                   "(correct on clean restart with batting_team "
                   "established before any 0-0 graphic)")
    else:
        if n_a:
            out.append("  status: PATH A ACTIVE — pre-match graphic gate "
                       "blocked stale team-assignment")
        if n_d:
            out.append("  status: PATH D ACTIVE — WS broadcast suppressed "
                       "during cold-start window")
    return "\n".join(out) + "\n"


def report_fix_18(s: Snapshot) -> str:
    out: list[str] = ["## Fix 18 validation: L2 reconciler + L3 cap-reset (phantom +N quartet)"]
    out.append("  baseline (pre-fix): bat_sum > score divergence "
               "uncorrected (cap-reset broken by `if runs > score` "
               "condition; reset on capped batter never fired)")
    out.append("  expected post-fix:  L2 detects (bat_sum > score+5); "
               "L3 resets last-advanced batter (bat_sum > score+10)")

    n_l2 = len(s.fix18_l2_reconciler_events)
    out.append(f"  BAT-SUM-RECONCILER (L2) fires:  {n_l2}")
    for ev in s.fix18_l2_reconciler_events[:5]:
        out.append(f"    {ev['ts']} {ev['frame']}  "
                   f"bat_sum={ev['bat_sum']} excess={ev['excess']}")

    n_l3 = len(s.fix18_l3_cap_reset_events)
    out.append(f"  CAP-RESET-LAST-ADVANCE (L3) fires: {n_l3}")
    for ev in s.fix18_l3_cap_reset_events[:5]:
        out.append(f"    {ev['ts']} {ev['frame']}  "
                   f"iter={ev['iter']} batter='{ev['batter']}'")

    if n_l2 == 0 and n_l3 == 0:
        out.append("  status: SILENT — no bat_sum vs score divergence in "
                   "this log (correct on clean match; composes with "
                   "Fix 11/15 admission gates)")
    elif n_l2 > 0 and n_l3 == 0:
        out.append("  status: L2 DETECTED, L3 NOT TRIGGERED — divergence "
                   "below 10-run cap-reset threshold (correct: small "
                   "divergence flagged but not aggressively reset)")
    else:
        out.append("  status: ACTIVE — L2/L3 cascade engaged on phantom "
                   "+N divergence")
    return "\n".join(out) + "\n"


def report_state_recovery(s: Snapshot) -> str:
    out: list[str] = [
        "## State-recovery consensus override telemetry",
    ]
    n_cand = len(s.state_recovery_candidate_events)
    n_fire = len(s.state_recovery_override_events)
    out.append(f"  CANDIDATE would-fire events: {n_cand}")
    out.append(f"  OVERRIDE mutation events:    {n_fire}")
    if n_cand:
        guard_counts: Counter = Counter()
        reset_counts: Counter = Counter()
        for ev in s.state_recovery_candidate_events:
            guard_counts.update(ev.get("guards") or [])
            reset_counts.update(ev.get("proposed_reset") or [])
        out.append(f"  guard families: {guard_counts.most_common()}")
        out.append(f"  proposed reset scopes: {reset_counts.most_common()}")
        out.append("  first candidates:")
        for ev in s.state_recovery_candidate_events[:5]:
            out.append(
                f"    {ev.get('frame')} guards={ev.get('guards')} "
                f"frames={ev.get('frames_seen')} "
                f"thresholds={ev.get('threshold_frames')} "
                f"reset={ev.get('proposed_reset')} "
                f"coherence={ev.get('coherence')} "
                f"candidate={ev.get('candidate')} "
                f"current={ev.get('current')}")
    else:
        out.append("  no recovery candidates observed")
    if n_fire:
        out.append("  WARNING: mutation events observed; audit false-trigger "
                   "indicators against subsequent accepted frames.")
    return "\n".join(out) + "\n"


def report_pending_validation(s: Snapshot) -> str:
    """List monitored telemetry tags with zero vs non-zero hits."""
    lines: list[str] = [
        "## Pending-validation monitor (harness catalog)",
        "Tags with **zero** hits are still awaiting trigger conditions "
        "in this log.",
        "",
    ]
    pending: list[str] = []
    fired: list[str] = []
    for lbl, _ in PENDING_VALIDATION_PATTERNS:
        n = s.pending_validation_hits.get(lbl, 0)
        if n == 0:
            pending.append(f"  (pending) {lbl}")
        else:
            fired.append(f"  (fired×{n}) {lbl}")
    lines.append(f"**Not yet observed** ({len(pending)} tags):")
    lines.extend(pending if pending else ["  — none —"])
    lines.append("")
    lines.append(f"**Observed in log** ({len(fired)} tags):")
    lines.extend(fired if fired else ["  — none —"])
    lines.append("")
    return "\n".join(lines) + "\n"


def report_bundle_bc(s: Snapshot) -> str:
    out: list[str] = ["## Bundle B/C validation: positive-fire signatures"]
    expected = [
        ("6_batter_normalize", "(6) Rinku/SINGH normalization"),
        ("16_new_batter_balls", "(16) fresh-batter balls gate"),
        ("17a_bowler_batter_gate", "(17A) bowler-from-batter-row gate"),
        ("bowler_stats_graphic_gate",
         "(stats graphic) aggregate / phase overlay gate"),
        ("19_zero_graphic_gate", "(19) false 0-0 cold-start gate"),
        ("21_over_resync", "(21) this-over recovery resync"),
        ("22_all_out_authority", "(22) final-wicket/all-out authority"),
        ("14_score_regression", "(14) score regression hard block"),
        ("18_ws_slot_invariant", "(18) WS slot duplicate invariant"),
        ("lever1_sm_slot_invariant",
         "Lever 1 SM slot duplicate invariant ([SM-SLOT-INVARIANT])"),
        ("17b_bowler_team_over", "(17B) bowler team-over consensus"),
        ("17b_bowler_consensus_inconsistent",
         "(17B+) plain-consensus overs mismatch reject"),
        ("17b_bowler_consensus_override",
         "(17B+) plain-consensus streak override"),
        ("15_score_inf_floor", "(15) SCORE-INF-GATE floor (bat_sum+extras)"),
        ("cluster1_scorer_active_gate", "Cluster 1 SCORER active gate"),
        ("cluster1_striker_sm_cutover", "Cluster 1 striker SM cutover"),
        ("striker_read_sm_canonical",
         "Path B striker READ SM-canonical (DETAIL divergence)"),
        ("cluster1_striker_status_gate", "Cluster 1 striker status gate"),
        ("path_b_sm_feeder_sync",
         "Path B SM→SB feeder sync ([SM-FEEDER-SYNC])"),
        ("path_b_sm_shadow_parity",
         "Path B shadow parity ([SM-SHADOW-PARITY])"),
        ("path_b_bowler_feeder_divergence",
         "Path B bowler_name SM/SB divergence ([SM-FEEDER-DIVERGENCE])"),
        ("item2_scorer_schema_would_drop",
         "Item 2 schema shadow would-drop ([SCORER-SCHEMA-WOULD-DROP])"),
        ("item2_scorer_schema_would_coerce",
         "Item 2 schema shadow would-coerce ([SCORER-SCHEMA-WOULD-COERCE])"),
        ("item2_batters_invariant",
         "Item 2 batters invariant backstop ([BATTERS-INVARIANT])"),
        ("thread7_strip_rows_misaligned",
         "Thread 7 strip row misalignment ([STRIP-ROWS-MISALIGNED])"),
    ]
    for key, label in expected:
        events = s.bundle_bc_events.get(key, [])
        out.append(f"  {label}: {len(events)}")
        for ev in events[:3]:
            out.append(f"    {ev.get('ts')} {ev.get('frame')}  "
                       f"{ev.get('match')}")
        if len(events) > 3:
            out.append(f"    ... +{len(events) - 3} more")
    zero = [label for key, label in expected
            if not s.bundle_bc_events.get(key)]
    if zero:
        out.append("  zero-fire signatures:")
        for label in zero:
            out.append(f"    - {label}")
        out.append("  status: REVIEW — zero-fire is OK only when the "
                   "fixture trigger is absent; if the production window is "
                   "known present, add/replay a fixture before deploy.")
    else:
        out.append("  status: VALIDATED — every Bundle B/C signature fired")
    return "\n".join(out) + "\n"


def render_text(s: Snapshot) -> str:
    out: list[str] = []
    out.append(f"# Match-telemetry snapshot")
    out.append(f"log:    {s.log_path}")
    out.append(f"window: {s.log_first_ts} → {s.log_last_ts} ({s.duration_min} min)")
    if s.archive_event:
        out.append(f"archive: {s.archive_event}")
    out.append(f"latest STATE: {s.state_latest or '—'}")
    out.append("")

    out.append(f"## Health")
    out.append(f"  Pass-1 latency:        {s.pass1_ms} ms"
               if s.pass1_ms else "  Pass-1 latency:        —")
    out.append(f"  Pass-2 status:         {s.pass2_status}"
               + (f" ({s.pass2_detail})" if s.pass2_detail else ""))
    out.append(f"  STYLES-PATCH events:   {s.styles_patch_events}")
    out.append(f"  SCOREBOARD frames:     {s.frames_scoreboard}")
    out.append(f"  GRAPHIC frames:        {s.frames_graphic}")
    out.append(f"  FRAME_POISONED:        {s.frame_poisoned_count}")
    if s.frame_poisoned_reasons:
        top = s.frame_poisoned_reasons.most_common(5)
        out.append(f"    by reason: {top}")
    out.append(f"  STATE-RECOVERY candidates: "
               f"{len(s.state_recovery_candidate_events)}")
    out.append(f"  STATE-RECOVERY overrides:  "
               f"{len(s.state_recovery_override_events)}")
    out.append(f"  Vision timeouts:       {s.vision_timeouts}")
    out.append(f"  Innings transitions:   {s.innings_transitions}")
    out.append(f"  Wickets in FOW:        {sorted(s.wickets_seen)}")
    out.append("")

    out.append(f"## INVARIANT fires (P0-A/P0-B four-layer defense)")
    if s.invariant_fires:
        for tag, n in s.invariant_fires.most_common():
            out.append(f"  {tag}: {n}")
    else:
        out.append("  (none)")
    out.append("")

    out.append(f"## Bowler-tracker telemetry")
    out.append(f"  BOWLER-STALE rejects:  {s.bowler_stale_rejects}")
    if s.bowler_stale_targets:
        for name, n in s.bowler_stale_targets.most_common():
            out.append(f"    {name}: {n} rejects")
    out.append(f"  FIELD-MONITOR warns:   {s.field_monitor_warns}")
    out.append("")

    if s.bowler_stale_events:
        out.append(f"## BOWLER-STALE event sequences (for log-replay test fixture)")
        # Group by target name, list F-numbers
        by_target: dict[str, list[dict]] = defaultdict(list)
        for ev in s.bowler_stale_events:
            by_target[ev["target"]].append(ev)
        for target, evs in sorted(by_target.items(), key=lambda x: -len(x[1])):
            frames = [ev["frame"] for ev in evs]
            first_ts = evs[0]["ts"]
            last_ts = evs[-1]["ts"]
            out.append(f"  {target}: {len(evs)} rejects "
                       f"({first_ts}..{last_ts})")
            preview = " ".join(frames[:6])
            if len(frames) > 6:
                preview += f" ... +{len(frames) - 6}"
            out.append(f"    frames: {preview}")
            sample = evs[0]
            if sample.get("proposed"):
                out.append(f"    sample: proposed={sample['proposed']}  "
                           f"recorded={sample['recorded']}")
        out.append("")

    out.append(f"## Bowler-strip read intervals (informs freshness window)")
    if s.bowler_strip_reads:
        intervals = compute_interval_distributions(s)
        wb = intervals["within_bowler_frames"]
        ab = intervals["across_bowler_frames"]
        out.append(f"  Total active BOARD writes: {len(s.bowler_strip_reads)}")
        out.append(f"  Within-bowler (inter-ball proxy):")
        out.append(f"    n={wb['n']}  min={wb['min']}  "
                   f"median={wb['median']}  p95={wb['p95']}  "
                   f"max={wb['max']}  (frames)")
        out.append(f"  Across-bowler (handoff proxy, genuine-stale window):")
        out.append(f"    n={ab['n']}  min={ab['min']}  "
                   f"median={ab['median']}  p95={ab['p95']}  "
                   f"max={ab['max']}  (frames)")
        out.append(f"  Recommended freshness threshold: ~p95 of within-bowler,")
        out.append(f"  must sit < min of across-bowler for clean separation.")
    else:
        out.append("  (no BOARD bowler writes parsed)")
    out.append("")

    out.append(f"## camera_view distribution (cumulative)")
    total = sum(s.cam_total.values())
    if total:
        for cam, n in s.cam_total.most_common():
            pct = 100.0 * n / total
            out.append(f"  {cam:18s} {n:5d} ({pct:5.1f} %)")
        out.append(f"  ----")
        out.append(f"  total              {total}")
    else:
        out.append("  (no SCOUT lines parsed)")
    out.append("")

    out.append(f"## camera_view distribution (last 5 min)")
    total5 = sum(s.cam_window_5min.values())
    if total5:
        for cam, n in s.cam_window_5min.most_common():
            pct = 100.0 * n / total5
            out.append(f"  {cam:18s} {n:5d} ({pct:5.1f} %)")
    else:
        out.append("  (no SCOUT lines in window)")
    out.append("")

    out.append(f"## frame_phase distribution (cumulative)")
    ptotal = sum(s.phase_total.values())
    if ptotal:
        for ph, n in s.phase_total.most_common():
            out.append(f"  {ph:18s} {n:5d} ({100.0 * n / ptotal:5.1f} %)")
    out.append("")

    out.append(f"## phase × camera_view cross-tab (top 10)")
    rows = sorted(s.cam_phase_xtab.items(), key=lambda x: -x[1])[:10]
    for (cam, ph), n in rows:
        out.append(f"  {cam:18s} | {ph:18s} {n}")
    out.append("")

    out.append(f"## bowler-change pickup (Scout vs Scoreboard divergence)")
    if s.bowler_change_events:
        for ev in s.bowler_change_events[:6]:
            out.append(
                f"  {ev['ts']}  scout='{ev['scout_reads']}'  "
                f"sb='{ev['scoreboard_state']}'")
        if len(s.bowler_change_events) > 6:
            out.append(f"  ... +{len(s.bowler_change_events) - 6} more")
    else:
        out.append("  (no divergence events)")
    out.append("")

    if s.notable_anomalies:
        out.append(f"## anomalies")
        for a in s.notable_anomalies:
            out.append(f"  - {a}")
        out.append("")

    return "\n".join(out)


def render_json(s: Snapshot) -> str:
    def _serial(v: Any) -> Any:
        if isinstance(v, Counter):
            return dict(v)
        if isinstance(v, defaultdict):
            return {f"{k[0]}|{k[1]}" if isinstance(k, tuple) else k: vv
                    for k, vv in v.items()}
        return v

    payload = {k: _serial(v) for k, v in s.__dict__.items()}
    return json.dumps(payload, indent=2, default=str)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default=None,
                    help="path to pipeline log; defaults to most recent "
                    "logs/pipeline-*.log")
    ap.add_argument("--json", action="store_true",
                    help="output JSON instead of text")
    ap.add_argument("--out", default=None,
                    help="write to file instead of stdout")
    ap.add_argument("--window", type=int, default=5,
                    help="recent-window minutes (default 5)")
    ap.add_argument("--report-9a", action="store_true",
                    help="print Fix 9a (AUTO-SWAP-TARGET) validation report")
    ap.add_argument("--report-9b", action="store_true",
                    help="print Fix 9b (TARGET-MONOTONIC + SANITY) report")
    ap.add_argument("--report-10", action="store_true",
                    help="print Fix 10 (POST-WICKET-ROTATION) report")
    ap.add_argument("--report-11", action="store_true",
                    help="print Fix 11 (EXTRAS-INF-GATE) report")
    ap.add_argument("--report-12", action="store_true",
                    help="print Fix 12 (RUNS-REJECT-RELEASE) report")
    ap.add_argument("--report-13", action="store_true",
                    help="print Fix 13 (POST-WICKET-CARD-PROPAGATE) report")
    ap.add_argument("--report-14", action="store_true",
                    help="print Fix 14 (BALLS-CEILING-GATE) report")
    ap.add_argument("--report-15", action="store_true",
                    help="print Fix 15 (SCORE-INF-GATE) report")
    ap.add_argument("--report-16", action="store_true",
                    help="print Fix 16 (SM-INNINGS-2-RESET) report")
    ap.add_argument("--report-17", action="store_true",
                    help="print Fix 17 (cold-start Path A + D) report")
    ap.add_argument("--report-18", action="store_true",
                    help="print Fix 18 (L2 reconciler + L3 cap-reset) report")
    ap.add_argument("--report-state-recovery", action="store_true",
                    help="print state-recovery override candidate report")
    ap.add_argument("--report-bundle-bc", action="store_true",
                    help="print Bundle B/C positive-fire signature report")
    ap.add_argument("--report-pending-validation", action="store_true",
                    help="list pending-validation telemetry tags vs this log")
    ap.add_argument("--report-all-fixes", action="store_true",
                    help="print all fix-validation reports (Fixes 9-18)")
    ap.add_argument("--per-wicket", action="store_true",
                    help="for Fix 10 report, bin POST-WICKET-ROTATION "
                    "and STRIKER-COLLISION counts per wicket")
    ap.add_argument("--fix-validation-only", action="store_true",
                    help="suppress the default snapshot, print only "
                    "the fix-validation reports requested")
    args = ap.parse_args()

    if args.log:
        log = Path(args.log)
    else:
        candidates = sorted(
            Path(__file__).resolve().parent.parent.glob(
                "logs/pipeline-*.log"),
            key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidates:
            print("no logs/pipeline-*.log found", file=sys.stderr)
            sys.exit(1)
        log = candidates[0]

    snap = analyze(log, window_min=args.window)

    fix_reports: list[str] = []
    want_all = args.report_all_fixes
    if want_all or args.report_9a:
        fix_reports.append(report_fix_9a(snap))
    if want_all or args.report_9b:
        fix_reports.append(report_fix_9b(snap))
    if want_all or args.report_10:
        fix_reports.append(report_fix_10(snap, per_wicket=args.per_wicket))
    if want_all or args.report_11:
        fix_reports.append(report_fix_11(snap))
    if want_all or args.report_12:
        fix_reports.append(report_fix_12(snap))
    if want_all or args.report_13:
        fix_reports.append(report_fix_13(snap))
    if want_all or args.report_14:
        fix_reports.append(report_fix_14(snap))
    if want_all or args.report_15:
        fix_reports.append(report_fix_15(snap))
    if want_all or args.report_16:
        fix_reports.append(report_fix_16(snap))
    if want_all or args.report_17:
        fix_reports.append(report_fix_17(snap))
    if want_all or args.report_18:
        fix_reports.append(report_fix_18(snap))
    if args.report_state_recovery:
        fix_reports.append(report_state_recovery(snap))
    if args.report_bundle_bc:
        fix_reports.append(report_bundle_bc(snap))
    if args.report_pending_validation:
        fix_reports.append(report_pending_validation(snap))

    if args.json:
        out = render_json(snap)
    elif args.fix_validation_only and fix_reports:
        header = (f"# Fix-validation report\n"
                  f"log:    {snap.log_path}\n"
                  f"window: {snap.log_first_ts} → {snap.log_last_ts} "
                  f"({snap.duration_min} min)\n\n")
        out = header + "\n".join(fix_reports)
    else:
        out = render_text(snap)
        if fix_reports:
            out = out + "\n" + "\n".join(fix_reports)

    if args.out:
        Path(args.out).write_text(out)
    else:
        print(out)


if __name__ == "__main__":
    main()
