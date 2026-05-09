# Pre-live match monitoring plan — IPL (live ops)

**As of:** 2026-05-02  
**Purpose:** Single-page operator reference for IPL broadcasts: metrics to watch, historical tee baselines, **post–frame-source** expectations, innings scorecard UI verification, live playbook, and post-match comparison (pipeline logs + trace analyzer).

**Changelog — Updated 2026-05-03**

- **P12 innings-2 cold-start hardening shipped** (`files/score_manager.py`, `files/test_pipeline.py`, `files/trace_emitter.py`, `files/tests/test_inn2_transition_hardening.py`): `ScoreManager.in_inn2_transition(frame_idx)` exposes a hybrid window (frames < `INN2_TRANSITION_FRAMES` AND wall < `INN2_TRANSITION_SECONDS`) OR safety net (wall < `INN2_TRANSITION_CEILING_SECONDS`); auto-clears on `mark_inn2_first_commit()`. Six in-window content gates wired before existing GUARD pipeline via `_apply_inn2_transition_gates`: score > 30, wickets > 2, overs > 5.0, bowler ∉ bowling-team XI, batter ∉ batting-team XI, plus null-team advisory log. Cold-start commit lockout inside `_handle_cold_start` requires 3 consecutive in-window passes on numeric bounds before `cold_candidate` is seeded; on successful seed, `mark_inn2_first_commit()` clears the window. CORRECTION_BLOCKED storm hook adjacent to the `apply_scorer_decision` emission: ≥5 blocks within 60 s of the inn2 reset extends `_inn2_reset_wall` back by 60 s (cumulative cap +300 s per stop-condition S4). Telemetry tags (registered in `files/trace_emitter.py` `KNOWN_TAGS`): `[INN2-TRANSITION-REJECT]`, `[INN2-TRANSITION-NULL-TEAM]`, `[INN2-COLD-START-LOCKOUT]`, `[INN2-COLD-START-CONSENSUS]`, `[INN2-TRANSITION-PHANTOM-STORM]`. Env vars: `INN2_TRANSITION_FRAMES` (250), `INN2_TRANSITION_SECONDS` (900), `INN2_TRANSITION_CEILING_SECONDS` (1200) — set any to 0 to disable that clause. Rollback: revert the four edits or zero the env vars; gates are additive guards behind the boolean window check, so disabling restores 2026-05-02 behaviour. Desk-validation against `logs/pipeline-2026-05-02-2049-csk-vs-mi-44th-match-ipl-2026-innings2.log` F640–F870: every documented phantom in diagnosis §1 (49/3, 89/3, 96/3, 96/4, 47/3, 77/5, 74/5, 77/3, 101/0; off-XI Will Jacks / K.L. Rahul / A. Kishore / Karun-as-bowler) is rejected by ≥1 gate; **F799 phantom seed `47/3` is blocked by cold-start lockout**; **F864 legitimate seed proceeds at the correct 9/0 (1.4)** instead of the F864 raw 7.0-over misread (lockout defers seed ~12 frames until overs are plausible). 19/19 unit tests passing. Two follow-ups deferred: typed `P12-A/B/C` Anomaly subclass in `anomaly_rules.py` (KNOWN_TAGS + histogram coverage already shipped); `_handle_cold_start` end-to-end integration test (Phase G replay covered the integration path). Diagnosis: [`innings_transition_hardening_diagnosis.md`](innings_transition_hardening_diagnosis.md).
- **P3 replay-inset detector shipped** (`files/test_pipeline.py`, `files/trace_emitter.py`, `files/tests/test_recap_inset_detection.py`): extends the existing P2 GRAPHIC-FILTER substrate with **Mode-C** (`team=null` + `|extracted_score − tracker_score| > RECAP_INSET_SCORE_DELTA_THRESHOLD` OR `RECAP_FINGERPRINT_REGEX` match) and an **N-frame debounce** that arms after any Mode A/B/C firing — every following SCOREBOARD frame with `team=null` inside the window is poison-suspected. Env vars: `OVERLAY_WINDOW_FRAMES` (default `5`), `RECAP_INSET_SCORE_DELTA_THRESHOLD` (default `10`), `RECAP_FINGERPRINT_REGEX` (optional; e.g. `\b(47|49)-3\b` for the 2026-05-02 CSK–MI recap banner). Trace records gain `pipeline.inset_suspected` and `pipeline.overlay_window_active`. Cold-start phantom (F8-class) deferred to **P12**. Diagnosis: [`replay_inset_detection_diagnosis.md`](replay_inset_detection_diagnosis.md).
- **P19 strip-overlay sentinel pre-filters shipped** (`files/test_pipeline.py`, `files/tests/test_strip_overlay_filter.py`): two text/membership pre-filters (`_detect_overlay_strip_sentinels`, `_detect_overlay_via_active_batting`) run BEFORE `apply_comparison_strip_batter_row_delta_guard`; the existing row-pair guard becomes the backstop. Sentinel list (head-to-head `>`, `RUN-RATE`, `SPEED kph`, `IN T20`, …) is env-tunable via `STRIP_OVERLAY_SENTINELS`. New WARN tag `[STRIP-OVERLAY-DETECTED]` (registered in `files/trace_emitter.py`) and analyzer rule `P19` in `files/anomaly_rules.py` split firings into `OVERLAY-PRE-FILTERED` (info) vs `ROW-DELTA-FALLBACK` (warn) so we can measure pre-filter coverage. Diagnosis: [`strip_rows_misaligned_diagnosis.md`](strip_rows_misaligned_diagnosis.md). Threshold tuning (>20 → >15) deferred until post-fix telemetry from one match.
- **Track A mechanical batch** (CSK–MI innings-2 post-mortem follow-up): **P11** XI + bench + impact-substitution gate (`[XI-GATE]`, `[IMPACT-PLAYER-ACTIVATED]`), **P14** batter slot identity consensus reset (`[BATTER-CONSENSUS-RESET]`), **P15** bowler spell vs team overs (`[BOWLER-STATS-SANITY-REJECT]`), **P16** DIRECT run-rate pair veto (`[SCORE-OVERS-RR-REJECT]`), **P10** `this_over` gap padding after strip resumes (`[TIMEOUT-GAP-INFER]`), **P20** bowler stale hard-cap (`[BOWLER-LATENCY-HARDCAP]`). Tests: `files/tests/test_track_a_mechanical_batch.py`. Squad bench exposed via `squad_membership_by_team_name` in `files/eyes/squad_scraper.py`. TODO: max-4 overseas on field.

**Changelog — Updated 2026-05-02**

- **OpenScout output persistence shipped** (`files/eyes/openscout_persistence.py`, `files/eyes/open_scout.py`, `files/eyes/span_aggregator.py`, `files/ball_analyzer.py`, `files/delivery_window_recorder.py`): per-frame JSONL at `logs/openscout-<SESSION>.jsonl` (every classification + every rate-gate skip) + per-span clip + metadata + classifications under `files/logs/openscout_spans/<SESSION>/span_<NNNN>/`. `matched_to_event` patched onto metadata when DWR's matcher resolves a span to a score event. Manual review path via `files/logs/openscout_spans/`; per-frame analysis via `logs/openscout-<SESSION>.jsonl`. Setup + schema in [`parallel_scout_setup.md`](../operations/parallel_scout_setup.md). Closes the data-loss blind spot called out in [`youtube_test_delivery_detection_analysis.md`](youtube_test_delivery_detection_analysis.md) §10.
- **Lever 1 STRIP prompt fix shipped** (`files/eyes/vision.py`): `team=null` + `overs=null` instructions, optional `extras` / `this_over` fields on the STRIP line, KKR example removed — rationale and failure modes in [`strip_ocr_failure_mode_analysis.md`](strip_ocr_failure_mode_analysis.md).
- **Frame source:** UGREEN HDMI capture card (`cv2.VideoCapture` default index), **not** Firefox window capture — see [`frame_source_setup.md`](../operations/frame_source_setup.md).
- **Fixes shipped:** P3-A/B/C (CricketLogger → trace, bowler bootstrap bypass tag, bowler rule/tag renames); **extras source-of-truth** (`inferred_total` vs monotonic `total`); **P8** (`this_over` bounded + alphabet + floor cap tags); **P4** anomaly identity fix; **P7** narrower score-cap suppression (when landed — trace tags listed below with note).
- **Trace-and-detect:** JSONL at `logs/trace/<SESSION>.jsonl`; post-match **`files/analyze_trace.py`** reports — [`trace_and_detect_setup.md`](../operations/trace_and_detect_setup.md).
- **Parallel-Scout:** shadow telemetry **`USE_OPEN_SCOUT=1`** default; **`USE_OPEN_SCOUT_SPANS=0`** default (legacy drives windows); both windows in **`window_debug.json`** — [`parallel_scout_setup.md`](../operations/parallel_scout_setup.md).

**Tee corpora**

| Role | Path |
|------|------|
| Pre-fix | `logs/pipeline-2026-04-29-194416-mi-srh-live.log` |
| Pre-fix | `logs/pipeline-2026-04-28-pbks-rr-live.log` |
| Partial post-fix (§P0-C validation session) | `logs/pipeline-2026-04-30-gt-rcb-live.log` |

**Cross-check:** `[POISON-RECAL]` totals **4 + 7 + 24 = 35** across these three tees — matches [`poison_recal_threshold_analysis.md`](poison_recal_threshold_analysis.md) Phase A inventory (**STOP S1 cleared** for chase splits: **16 / 24** chase enqueues match [`score_event_coverage_audit.md`](score_event_coverage_audit.md) §3.4).

---

## §1 Quick reference (one screen)

| # | Area | Verdict metric(s) | Expected (mechanism-based) |
|---|------|-------------------|----------------------------|
| 1 | **§P0-C** innings transition | **M2** chase enqueue rate vs scorecard chase balls | **≥ ~80%** of expected chase balls enqueue (historic pre-fix **~14% / ~21%** on MI/PBKS); GT steady session reference **215/215** internal parity |
| 2 | **Cause 4** graphic-OCR / poison pre-empt | **M3** `POISON-RECAL` vs tee band; **M6** preempt tags | **`POISON-RECAL`** vs anchor tees; **`[POISON-RECAL-PRE-EMPTED]`** non-zero when strips would have fed poison ladder |
| 3 | **Cause 3** cold-start watchdog | **M8** + recovery shape | **`[COLD-START-FORCED-RECOVER]`** on stalls that previously hung past **25–45** frames ([`cold_start_recovery_fix_implementation.md`](cold_start_recovery_fix_implementation.md)); scoring resumes |
| 4 | **Issue 2 Task B** batter alignment | Tags + spot-check | **`[STRIKER-ALIGN-FALLBACK]` / `[BATTER-ALIGN]`** — **post capture-card baseline** should be **far lower** than Firefox-as-source nights; validate with spot-checks |
| 5 | **Issue 3** `MULTI_BALL` decomposition | **M4** + **`ABSORBED_LEGAL`** | **`MULTI_BALL`** row pattern; **`ABSORBED_LEGAL` ≈ Σ Δballs** (**no Layer 2 enqueue** per D2) |
| 6 | **UI:** innings sub-tabs + `innings_history` | Visual **+** WS / trace | **[ Innings 1 ]** snapshot after innings **2** starts; pills work; **`§4.4`** |

**Hard-stop (consider interrupting the pipeline)**

Existing:

- Score **wrong or regressing** for **5+ consecutive frames** vs broadcast.
- **`[POISON-RECAL]`** roughly **every ~30s**, sustained **≥ 5 minutes**.
- **No `[DELIVERY ENQUEUED]`** for **≥ 5 minutes** during active play.
- Tracker / WS shows **impossible state** (negative runs, nonsense overs).
- **UI freezes / disconnects** (stuck **“Connecting…”**, blank scorecard, no WS) **> 1 minute** during active play.

**Post–frame-source baselines — lowered rate thresholds** (Firefox-window starvation no longer dominates):

- **`[STRIKER-ALIGN-FALLBACK]`** **more than 5/minute sustained** → hard-stop signal (was tolerated at much higher sustained rates under screen capture).
- **`MULTI_BALL`** (**`DETAIL`** / **`ball_event=MULTI_BALL`** per your tee convention) **more than 3/minute sustained** → hard-stop signal.

**New tag-based hard-stop signals:**

- **`[THIS-OVER-BCAST-REJECT]`** in bursts **> 5/minute sustained** → strip parsing pathological pattern not fully gated.
- **`[BOWLER-BOOTSTRAP-REJECT]`** repeating **without** a successful bowler change for **> 3 overs** → broadcast strip not converging on bowler transitions.
- **`[FLOOR-CAP]`** firing **repeatedly** → **`this_over`** pushing against cap; overs detection stale or ribbon desync (**P8** path); investigate.

**One-line tag watch** (adjust log path after rotate):

```bash
tail -f logs/pipeline-2026-05-*-live.log 2>/dev/null | grep -E 'POISON-RECAL|FRAME_POISONED|GRAPHIC-FILTER|POISON-RECAL-PRE-EMPTED|COLD-START-FORCED-RECOVER|STRIKER-ALIGN-FALLBACK|BATTER-ALIGN|ABSORBED_LEGAL|BOWLER-OVERRIDE|BOWLER-BOOTSTRAP-REJECT|THIS-OVER-BCAST-REJECT|FLOOR-CAP|SCORE-CAP-SUPPRESS-NARROW|CONSENSUS-PRESERVED-VIA-GRAPHIC|EXTRAS-INF|\[DELIVERY ENQUEUED\]'
```

**2026-05-03 new tags** (covered by `KNOWN_TAGS`, `anomaly_rules.py`, and `live_match_monitor.py`):

```
[TIMEOUT-GAP-INFER]            (P10 — info)
[INN2-TRANSITION-REJECT]        (P12 — warn)
[INN2-TRANSITION-NULL-TEAM]     (P12 — info)
[INN2-COLD-START-LOCKOUT]       (P12 — warn)
[INN2-COLD-START-CONSENSUS]     (P12 — info)
[INN2-TRANSITION-PHANTOM-STORM] (P12 — error)
[BATTER-CONSENSUS-RESET]        (P14 — info)
[BOWLER-STATS-SANITY-REJECT]    (P15 — warn; replaces legacy [GUARD])
[SCORE-OVERS-RR-REJECT]         (P16 — warn)
[BOWLER-LATENCY-HARDCAP]        (P20 — warn)
[LATENCY-STUCK]                 (P20 — info)
[STRIP-OVERLAY-DETECTED]        (P19 — info pre-filter / warn fallback)
[SHADOW] / [SHADOW-STATS]       (OpenScout shadow runner)
```

**Shadow-mode deployment** (Component 3):

```bash
# Enable OpenScout shadow runner for the next match (default: off).
SHADOW_MODE=1 python3 files/test_pipeline.py
# JSONL output:    files/logs/openscout_shadow/<SESSION>.jsonl
# Heartbeat log:   [SHADOW-STATS] every 1800 frames (~60 s @ 30 fps)
# Live monitor panel: live_match_monitor.py § "OpenScout shadow runner"
```

**P7-not-yet-shipped:** `[SCORE-CAP-SUPPRESS-NARROW]` and `[CONSENSUS-PRESERVED-VIA-GRAPHIC]` remain on the grep line for readiness; **expect in trace `decisions[]` once P7 lands** — not absent-by-default until then.

**Stop the pipeline:** Foreground terminal **Ctrl+C** (SIGINT). Detached: `pgrep -af test_pipeline` then **`kill -INT <pid>`**. Logs **`logs/`** at repo root ([`MONITORING_CHARTER.md`](../MONITORING_CHARTER.md) §2).

---

## §2 Pre-fix baselines (Phase A)

### A2 — Reproducible commands (run from repo root)

Substitute **`$LOG`** with each tee path.

| ID | Metric | Command(s) |
|----|--------|------------|
| **M1** | Total `[DELIVERY ENQUEUED]` | `grep -c '\[DELIVERY ENQUEUED\]' "$LOG"` |
| **M2** | Chase enqueues | See **§2.1** — line-number boundary from first chasing-side `DETAIL`. |
| **M3** | `POISON-RECAL` trips | `grep -c 'POISON-RECAL' "$LOG"` |
| **M4** | `MULTI_BALL` (`DETAIL`) | `grep -c 'ball_event=MULTI_BALL' "$LOG"` |
| **M5** | Cold-start signal density | `grep -c 'COLD_START' "$LOG"` and/or `grep -ci 'cold-start' "$LOG"` |
| **M6** | Cause 4 tags | `grep -c '\[GRAPHIC-FILTER\]' "$LOG"`; `grep -c '\[POISON-RECAL-PRE-EMPTED\]' "$LOG"` |
| **M7** | Issue 2 tags | `grep -c '\[STRIKER-ALIGN-FALLBACK\]' "$LOG"`; `grep -c '\[BATTER-ALIGN\]' "$LOG"` |
| **M8** | Cause 3 tag | `grep -c '\[COLD-START-FORCED-RECOVER\]' "$LOG"` |
| **M9** | `AFTER_score` sanity | `grep 'DETAIL|' "$LOG" \| sed -n 's/.*\(AFTER_score=[^|]*\).*/\1/p' \| sort -u` |
| **M10** | Ball-event totals | `grep -c 'ball_event=DOT' "$LOG"` (repeat `FOUR`, `SIX`, `WICKET`). |
| **M3b** | Σ Δballs (`MULTI_BALL`) | `grep 'COMMENTARY.*MULTI_BALL.*Δballs=' "$LOG" \| sed -n 's/.*Δballs=\([0-9]*\).*/\1/p' \| awk '{s+=$1} END {print s}'` |
| **M3c** | `ABSORBED_LEGAL` | `grep -c 'ABSORBED_LEGAL' "$LOG"` |

### §2.1 M2 — Chase boundary methodology ([`score_event_coverage_audit.md`](score_event_coverage_audit.md) §3.4)

**Rule:** First **`DETAIL`** with **`batting_team=`** = chasing team canonical name → count **`[DELIVERY ENQUEUED]`** with **`NR ≥ boundary_line`**.

**Authoritative boundaries**

```bash
# MI–SRH — chase = Sunrisers Hyderabad
grep -n 'batting_team=Sunrisers Hyderabad' logs/pipeline-2026-04-29-194416-mi-srh-live.log | grep DETAIL | head -1
# → line 31498

awk '/\[DELIVERY ENQUEUED\]/ && NR>=31498 {c++} END {print c+0}' logs/pipeline-2026-04-29-194416-mi-srh-live.log
# → 16

# PBKS–RR — chase = Rajasthan Royals
grep -n 'batting_team=Rajasthan Royals' logs/pipeline-2026-04-28-pbks-rr-live.log | grep DETAIL | head -1
# → line 37378

awk '/\[DELIVERY ENQUEUED\]/ && NR>=37378 {c++} END {print c+0}' logs/pipeline-2026-04-28-pbks-rr-live.log
# → 24
```

**GT–RCB (partial post-fix):** First **`DETAIL`** with **`batting_team=Gujarat Titans`** at **`≥1223`**:

```bash
grep -n 'batting_team=Gujarat Titans' logs/pipeline-2026-04-30-gt-rcb-live.log | grep DETAIL | awk -F: '$1>=1223 {print; exit}'
# → line 24611

awk '/\[DELIVERY ENQUEUED\]/ && NR>=1223 && NR<24611 {c++} END {print "pre-chase (steady):", c+0}' logs/pipeline-2026-04-30-gt-rcb-live.log
awk '/\[DELIVERY ENQUEUED\]/ && NR>=24611 {c++} END {print "chase from boundary:", c+0}' logs/pipeline-2026-04-30-gt-rcb-live.log
```

**Note:** Boundary **24611** is **mid-chase**; **do not** divide **131** by **116** chase balls as coverage % — use GT for steady **215/215** parity and tag shapes.

### A3 — Baseline table (historical tees — not tonight’s expected tag floors)

| Metric | MI–SRH (Apr 29) | PBKS–RR (Apr 28) | GT–RCB (Apr 30, partial) |
|--------|-----------------|------------------|---------------------------|
| **M1** `[DELIVERY ENQUEUED]` | **120** | **142** | **218** file (**215** if **`NR≥1223`**) |
| **M2** chase enqueues | **16** (≥ **31498**) | **24** (≥ **37378**) | **131** (≥ **24611**; qualitative) |
| **M2 % vs card chase balls** | **~14.3%** | **~20.7%** | §2.1 |
| **M3** `POISON-RECAL` | **4** | **7** | **24** |
| **M4** `ball_event=MULTI_BALL` | **6** | **2** | **6** |
| **M5a/b** cold-start | **5 / 39** | **8 / 41** | **31 / 151** |
| **M6** `[GRAPHIC-FILTER]` / `[POISON-RECAL-PRE-EMPTED]` | **0 / 0** | **0 / 0** | **0 / 0** |
| **M7** striker/batter alignment | **0 / 0** | **0 / 0** | **0 / 0** |
| **M8** `[COLD-START-FORCED-RECOVER]` | **0** | **0** | **0** |
| **ABSORBED_LEGAL** | **0** | **0** | **0** |
| **Σ Δballs** | **13** | **7** | **41** |

**Tonight:** Prefer comparison to **YouTube replay baseline** (**trace `866ce150`**, table **§5.6**) and **RR–DC**-style overnight session for **`MULTI_BALL`**, **`STRIKER-ALIGN-FALLBACK`**, fps — **not** “these zeros are healthy” absent capture-card context.

**STOP S2 / S3:** Historical tees show **M6–M8 / M7 / ABSORBED** counts as recorded; **`POISON-RECAL`** band **4–7** MI vs PBKS — use both anchors.

---

## §3 Expected targets (Phase B — mechanisms)

| Fix | Mechanism (docs) | Metric expectation |
|-----|------------------|-------------------|
| **B1 §P0-C** | Innings latch + coverage ([`mi_srh_post_match_architectural_review.md`](mi_srh_post_match_architectural_review.md), coverage audit) | **Chase enqueue ≥ ~80%** vs card vs **~14% / ~21%** legacy tees; GT **215/215** |
| **B2 Cause 4** | Graphic gate ([`graphic_strip_fix_implementation.md`](graphic_strip_fix_implementation.md)); **~8.3%** ([`poison_recal_threshold_analysis.md`](poison_recal_threshold_analysis.md)) | **`POISON-RECAL`** vs anchors; preempt tags |
| **B3 Cause 3** | Watchdog **25 / 45** ([`cold_start_recovery_fix_implementation.md`](cold_start_recovery_fix_implementation.md)) | **`[COLD-START-FORCED-RECOVER]`** on stalls |
| **B4 Issue 2** | [`batter_stats_flipping_fix_implementation.md`](batter_stats_flipping_fix_implementation.md) | Spot-check vs broadcast |
| **B5 Issue 3** | [`multi_ball_decomposition_fix_implementation.md`](multi_ball_decomposition_fix_implementation.md) | **`ABSORBED_LEGAL` vs Σ Δballs** |

**Extras (2026-05-02):** Inference writes **`extras['inferred_total']`**; **`extras['total']`** monotonic via **`record_extra`** only — [`extras_source_of_truth_diagnosis.md`](extras_source_of_truth_diagnosis.md). **`EXTRAS-INF`** grep remains useful as **diagnostic-only**.

**COLOR:** **`FRAME_COLOR_TRUE_BGR=0`** default (V2 path) — documented; no nightly operator change unless toggling experiments.

---

## §4 Live monitoring playbook (Phase C)

### C0 — Pre-match checklist

**A — HDMI capture path** (not Firefox as frame source):

- Apple **AirPlay** receiver (or equivalent) showing **Firefox fullscreen** broadcast.
- Air **HDMI out** → **UGREEN capture card** → **USB** to M1 Max.
- Verify device (example — **ffmpeg index 1 ⇔ OpenCV index 0** on this Mac):

```bash
ffplay -f avfoundation -framerate 30 -pixel_format uyvy422 -i "1"
```

- Pipeline: **`cv2.VideoCapture(0)`** default — [`frame_source_setup.md`](../operations/frame_source_setup.md).
- **Mac may be locked / backgrounded** — capture is hardware-rate; **no** “keep Firefox foreground” requirement.

**B — Config flags** (defaults should match):

```bash
cd /Users/anmolmohan/Projects/SportsComm/files
grep -E 'USE_OPEN_SCOUT|FRAME_SOURCE|CAPTURE_DEVICE_INDEX' eyes/config.py | head -10
```

Expect **`USE_OPEN_SCOUT=1`** (shadow telemetry on), **`USE_OPEN_SCOUT_SPANS=0`** (legacy windows authoritative for delivery window) unless you deliberately changed them.

### C1 — Visual sanity

| Check | Looks healthy | Looks wrong |
|-------|----------------|-------------|
| Score | Tracks broadcast | Stuck, backward jumps, **≥ 2 runs** persistent drift |
| Batters | Lineup / strip | Wrong pairing vs overlay |
| Bowler | Progressive | Frozen while balls bowled |
| Commentary | Near live cadence | Silent **minutes** in live overs |

### C2 — Tag meaning

| Token | Meaning | Good / bad |
|-------|---------|------------|
| **`POISON-RECAL`** | Poison reset path | Burst → **§1 hard-stop** |
| **`FRAME_POISONED`** | Strip/score disagree | Contextual |
| **`[GRAPHIC-FILTER]` / `[POISON-RECAL-PRE-EMPTED]`** | Cause **4** | Helpful when graphics lie |
| **`[COLD-START-FORCED-RECOVER]`** | Cold watchdog Path B | Good if was stalled |
| **`[STRIKER-ALIGN-FALLBACK]` / `[BATTER-ALIGN]`** | Alignment path | Low rate vs old Firefox baseline |
| **`[BOWLER-OVERRIDE]`** | Former **`[BOWLER OVERRIDE]`** | Informational; rule scan no longer **`BOWLER-LEAD`** (P3-C) |
| **`[BOWLER-BOOTSTRAP-REJECT]`** | Bootstrap bypass rejected (`scoreboard.py` ~2818–2839) | Repeat **§1** thresholds |
| **`[THIS-OVER-BCAST-REJECT]`** | Illegal `this_over` token dropped (P8) | Bursts → **§1** |
| **`[FLOOR-CAP]`** | `this_over` floor-pad capped (P8) | Repeat → ribbon/overs sync |
| **`EXTRAS-INF`** | Extras inference signal | Diagnostic — see extras doc |
| **`[DELIVERY ENQUEUED]`** | Layer **2** work | Missing in live overs → bad |
| **`[SCORE-CAP-SUPPRESS-NARROW]`** / **`[CONSENSUS-PRESERVED-VIA-GRAPHIC]`** | P7 suppression + consensus | **After P7 ships** — inspect trace **`decisions[]`** (CricketLogger **P3-A**); innings transition still works; problematic transitions may surface these |

### C3 — Hard-stop recap

**§1** full list — includes new tag thresholds.

### §4.4 — UI scoreboard (during match)

**Shipped:** Pills **[ Innings 1 ] [ Innings 2 ]**, default **current innings**; **Innings 1** chase = **`innings_history[0]`** snapshot. Backend `files/score_manager.py`; frontend **`scorecard-ui/`**.

**Setup:** **`npm run dev`** in **`scorecard-ui/`** → **`http://localhost:3000`** (optional phone/laptop).

**Innings 1:** **[ Innings 1 ]** default live; **[ Innings 2 ]** yet-to-bat placeholder; pills switch.

**Transition:** Default → **[ Innings 2 ]**; **[ Innings 1 ]** **frozen** (no further live mutations).

**Innings 2:** **[ Innings 2 ]** live; **[ Innings 1 ]** frozen.

**Wrong:** Empty **Innings 1** after transition; **Innings 1** mutates during chase; pills broken; default doesn’t track current innings; **Connecting…** **> 1 min**; wrong yet-to-bat team.

**Trace (2026-05-02+):** On a bad transition hypothesis, **`decisions[]`** in `logs/trace/<SESSION>.jsonl` should surface promoted tags (**P3-A**). Once **P7** lands: **`[SCORE-CAP-SUPPRESS-NARROW]`** reflects narrowed suppression vs the path that admitted the bad innings commit; **`[CONSENSUS-PRESERVED-VIA-GRAPHIC]`** when GRAPHIC poison preserves CORRECTION consensus — correlate with **`§5.6`** analyzer.

### §4.5 — Parallel-Scout shadow data (spot-check)

During play, skim **`window_debug.json`** verdict mix (latest deliveries session):

```bash
cd /Users/anmolmohan/Projects/SportsComm
LATEST=$(ls -dt files/logs/deliveries/*/ 2>/dev/null | head -1)
for f in "${LATEST}"/d*/window_debug.json; do
  [ -f "$f" ] || continue
  python3 -c "import json;d=json.load(open('$f'));print(d.get('open_scout_verdict'))"
done | sort | uniq -c
```

**Healthy:** Mixed verdicts. **Suspect:** **100% `no_match`** or **100% `aggregator_unavailable`** — investigate per [`parallel_scout_setup.md`](../operations/parallel_scout_setup.md).

### §4.6 — 2026-05-03 changes — what to watch

| Tag | Expected behaviour | Anomaly threshold |
|-----|--------------------|--------------------|
| **`[TIMEOUT-GAP-INFER]`** (P10) | Fires when strip OCR gaps trip the timeout — gap is *inferred*, not an anomaly. | Bursts (≥ 5 in <60 s) → strip OCR rate dropped; investigate. |
| **`[XI-GATE]` / `[IMPACT-PLAYER-ACTIVATED]`** (P11) | Tighter batter/bowler eligibility; expect *fewer* off-XI proposals than 2026-05-02. | Repeated `[IMPACT-PLAYER-ACTIVATED]` for the same name → squad scraper missed bench. |
| **`[INN2-TRANSITION-REJECT]` / `[INN2-COLD-START-*]`** (P12) | Burst at innings break + first ~5 min of innings 2; `[INN2-COLD-START-CONSENSUS]` should reach the lockout-clearing threshold. | Sustained `[INN2-COLD-START-LOCKOUT]` past ~5 min after the reset → real consensus failure (escalate). |
| **`[INN2-TRANSITION-PHANTOM-STORM]`** (P12) | Should be **rare** (cumulative window extension already capped at +300 s). | Any firing is critical — phantom-storm extension active. |
| **`[BATTER-CONSENSUS-RESET]`** (P14) | Fires on legitimate striker swaps; **1–2 per over** typical. | >5 per over → striker SM thrash; cross-check `[STRIKER-SM-CUTOVER] reason`. |
| **`[BOWLER-STATS-SANITY-REJECT]`** (P15) | Rare — replaces the legacy `[GUARD]` for stale bowler stats. | Bursts → upstream bowler attribution drift; was previously hidden by `[GUARD]`. |
| **`[SCORE-OVERS-RR-REJECT]`** (P16) | Occasional firings on OCR errors with implausible run rate. | Sustained → DIRECT proposals consistently misread; cross-check overs-string parser. |
| **`[STRIP-OVERLAY-DETECTED]`** (P19) | Pre-filter trips on graphics overlays *before* the row-delta backstop. | High `STRIP-ROWS-MISALIGNED` with low `STRIP-OVERLAY-DETECTED` → sentinels missed; tune `STRIP_OVERLAY_SENTINELS`. |
| **`[BOWLER-LATENCY-HARDCAP]`** (P20) | Expected ~once per 10+ overs; clears the bowler after 20-frame timeout. | More than ~3 per over → bowler attribution stuck; combine with **§C2** P3 bowler-stale signals. |
| **`[LATENCY-STUCK]`** (P20) | >8 frames stuck (advisory) — should resolve before HARDCAP fires. | Persistent without subsequent HARDCAP → check that the latency timer increments. |
| **`[SHADOW]` / `[SHADOW-STATS]`** (Component 3) | Heartbeat every ~60 s when `SHADOW_MODE=1`; counters monotonically increasing; `thread_alive=True`. | `thread_alive=False`, `exceptions_total > 0`, or stale `last_record_ts` (> 5 min) → shadow runner stalled (main pipeline still safe). |

**Cross-checks:**

- The `live_match_monitor.py` "Today's shipments validation" table surfaces all rows above plus per-over rate; the "OpenScout shadow runner" panel renders the latest `[SHADOW-STATS]` heartbeat snapshot.
- Post-match, `analyze_trace.py` rolls every tag into the **Decision-tag histogram** + per-rule anomalies (P10/P12/P14/P15/P16/P20 + SHADOW); see **§5.8** for shadow JSONL inspection.

---

## §5 Post-match comparison (Phase D)

### D1 — Mechanical replay

1. Locate tee: `logs/pipeline-2026-05-*-*-live.log` (newest).
2. Re-run **§2** helpers with **`$LOG`** tonight.
3. Recompute **M2** boundary (`grep -n …` → **`awk`**).

### D2 — Legacy comparison sheet template

| Metric | MI–SRH | PBKS–RR | GT–RCB | Tonight | Expected | Verdict |
|--------|--------|---------|--------|---------|----------|---------|
| M1 | 120 | 142 | 218 (215 steady) | | Order-of-magnitude vs balls captured | |
| M2 chase % | ~14% | ~21% | (parity not %) | | **≥ ~80%** | |
| M3 | 4 | 7 | 24 | | vs anchors | |
| M4 | 6 | 2 | 6 | | **§1 MULTI_BALL rate guard** | |
| M7 | 0 | 0 | 0 | | **Low vs RR–DC / YouTube cols (§D3)** — not legacy **0 == healthy** alone | |

### D3 — Baseline comparison table (**YouTube replay + RR–DC + tonight`)

Compare each live match to **YouTube replay baseline** (**~12:25–12:35 PM local 2026-05-02**, trace **`866ce150`**, report [`2026-05-02_youtube_test.md`](../match_reports/2026-05-02_youtube_test.md)) and **yesterday RR–DC** tee-style session.

| Metric | RR–DC | YouTube test | Tonight |
|--------|-------|---------------|---------|
| Total enqueues | 108 | ~1 (short) | |
| STRIKER-ALIGN-FALLBACK | 217 | 0 | |
| POISON-RECAL | 10 | 0 | |
| MULTI_BALL | 15 | 0 | |
| Highest **F** (Scout calls) | 5524 | 80 | |
| Pipeline fps (BallAnalyzer stopped line) | 0.5 | 61 | |
| Anomaly **P8** firings | N/A | 26 | **0** (post-fix) |
| Anomaly **P4** advisory | N/A | 7 | **0** (post-fix) |
| Chase coverage % | 23% | N/A | |

**Interpretation:** Tonight should **move toward the YouTube column** on tag volumes / fps (**post-frame-source + fixes**); **chase coverage** materially above legacy **23%**.

### §5.6 — Trace analyzer (post-match)

```bash
cd /Users/anmolmohan/Projects/SportsComm
TRACE=$(ls -t logs/trace/*.jsonl | head -1)
python3 files/analyze_trace.py "$TRACE" \
  --report "files/docs/match_reports/$(date +%Y-%m-%d)_<MATCH_NAME>.md" \
  --match-name "<Full Match Name>"
```

**Inspect report:**

- **Errors:** Any → investigate.
- **Warnings:** Tune thresholds if noisy.
- **Decision-tag histogram:** Should include **`BOWLER-*`**, **`GUARD-*`**, **`EXTRAS-*`**, **`WICKET-*`** after **P3-A** — if absent, regression.
- **Mode timeline**, **latency p50/p95/p99**.
- **Advisory §P4:** **0** firings expected post-P4 fix; non-zero → partnership tracker investigation.

### D4 — Per-fix checks

1. **Issue 2** — 5-delivery spot-check.
2. **Issue 3** — **`grep -c ABSORBED_LEGAL`** vs Σ **Δballs** (`MULTI_BALL` commentary).
3. **Cause 3** — cold recover vs **`[COLD-START-FORCED-RECOVER]`**.
4. **Cause 4** — **`POISON-RECAL`** vs anchors + preempt tags.
5. **§P0-C** — chase rate **≥ ~80%**.
6. **Extras** — align logs/UI with **`inferred_total` vs `total`** ([`extras_source_of_truth_diagnosis.md`](extras_source_of_truth_diagnosis.md)).

### §5.7 — UI / WS verification

Same as prior **§5.5**: **`innings_history`**, **`set_innings_2`** once; adjust log glob to **`logs/pipeline-2026-05-*-live.log`**.

### §5.8 — Shadow runner JSONL inspection (Component 3)

**File location:**

```bash
ls -lt files/logs/openscout_shadow/*.jsonl | head -1
# → files/logs/openscout_shadow/<SESSION_ID>.jsonl
```

**Schema** (per [`openscout_shadow_runner.md`](openscout_shadow_runner.md) — Component 3 memo):

- Line 1: `{"_header": true, "session_id", "started_ts", "schema_version": 1}`
- Records: `{"session_id", "delivery_id", "stage1_window_open_ts", "stage1_window_close_ts", "stage2_span_start_ts", "stage2_span_end_ts", "stage2_span_padded_start", "stage2_span_padded_end", "stage2_max_consecutive_action", "stage2_action_ratio", "stage2_hard_close_count", "stage3_qwen_details", "stage3_qwen_latency_ms", "stage3_qwen_error"}`
- Footer: `{"_footer": true, "stopped_ts", "n_frames", "n_scouts", "n_dropped_inactive", "n_dropped_overflow", "n_emitted", "n_qwen_errors"}`

**Comparison query templates:**

```bash
SHADOW=$(ls -t files/logs/openscout_shadow/*.jsonl | head -1)
MAIN=$(ls -t logs/pipeline-2026-05-*-live.log | head -1)

# (a) Count shadow deliveries vs main pipeline [DELIVERY ENQUEUED]
SHADOW_N=$(jq -c 'select(.delivery_id)' "$SHADOW" | wc -l | tr -d ' ')
MAIN_N=$(grep -c '\[DELIVERY ENQUEUED\]' "$MAIN")
echo "shadow=$SHADOW_N main=$MAIN_N ratio=$(awk "BEGIN{print $SHADOW_N/$MAIN_N}")"

# (b) Stage-2 padded-span duration distribution (ms)
jq -r 'select(.delivery_id) | (.stage2_span_padded_end - .stage2_span_padded_start) * 1000' "$SHADOW" \
  | sort -n | awk 'BEGIN{c=0} {a[c++]=$1} END{print "p50=" a[int(c*0.5)], "p95=" a[int(c*0.95)], "max=" a[c-1]}'

# (c) Qwen classification agreement (when classifier wired)
jq -r 'select(.delivery_id) | .stage3_qwen_details.classification // "none"' "$SHADOW" \
  | sort | uniq -c | sort -rn

# (d) Span timestamp drift vs main DWR window (cross-stream sanity)
jq -r 'select(.delivery_id) | [.delivery_id, .stage2_span_padded_start, .stage2_span_padded_end] | @tsv' "$SHADOW" \
  | head -20
```

**Live heartbeat** (during the match): the `[SHADOW-STATS]` lines in the main pipeline log carry `OpenScoutShadowRunner.stats()` — counters there should match (within one heartbeat) the JSONL footer counters when the session ends. `live_match_monitor.py` renders the latest snapshot as a panel.

---

## §6 Triage if regressions detected

1. Segment at innings boundary (`batting_team` flip — coverage audit §3.4).
2. Map hypothesis (don’t chase-starve → Cause **4** without **`POISON-RECAL` / `FRAME_POISONED`).
3. Delivery windows: **`files/logs/deliveries/<session>/dNNN/`**.
4. **`files/analyze_trace.py`** on **`logs/trace/*.jsonl`** (**§5.6**) + **`cd files && python analyze_match_telemetry.py --log "$(ls -t ../logs/pipeline-*.log | head -1)" --report-all-fixes --report-bundle-bc`** ([`MONITORING_CHARTER.md`](../MONITORING_CHARTER.md) §2).
5. Escalation [`MONITORING_CHARTER.md`](../MONITORING_CHARTER.md) §5 — attach tee + trace path + **`POISON-RECAL` / `MULTI_BALL`** anchors.

---

## §7 P20 bowler hardcap tuning (2026-05-03)

### Context

U1 reported a noticeable delay in detecting the bowler at over **6.1** during `srh-vs-kkr-RESTART2` (`logs/pipeline-2026-05-03-1808-srh-vs-kkr-RESTART2.log`). The hardcap at `files/test_pipeline.py:10832` (`if _lag_bc > 20:`) fires only after **20 frames** since the over-change request, with `[LATENCY-STUCK]` warnings starting at **>8 frames**.

Frame interval distribution for tonight's match (n=70 intervals from `F<n> TEST … Total: <ms>` timestamps):

| Stat | Interval |
|------|----------|
| mean | 7.04 s |
| median | 6.00 s |
| p90 | 10.00 s |
| p99 | 49.00 s (stalls) |
| min / max | 2 s / 49 s |

At median 6 s/frame the **20-frame** hardcap implies **~120 s** of stale `current_bowler` broadcast to the UI; the actual incident measured **F29 → F53 = 97 s** (over-change at `18:10:49`, HARDCAP at `18:12:26`), with the UI showing `Bowl: None` for that whole window. A second firing at **F122** waited **31 frames** because the hardcap branch only runs on frames where the over-change tracker is still armed, so the lag counter can overshoot the `>20` boundary.

### Root cause

The thresholds (`>8` for `[LATENCY-STUCK]`, `>20` for `[BOWLER-LATENCY-HARDCAP]`) are pure frame counts. They were tuned when the pipeline ran closer to **2–3 s/frame** (~40–60 s of tolerance). Tonight's **6 s** median frame interval (Vision ~800 ms + Extract ~1.2 s + Scorer ~1 s + idle gap) inflates the same frame budget into **~100–200 s** of stale UI — roughly **2× the operator-noticeable threshold** identified in `MONITORING_CHARTER.md` §C2.

### Recommended fix

**Option (c) — hybrid earliest trigger** at `files/test_pipeline.py:10832`:

```python
_lag_bc_frames = frame_count - _bowler_change_request_at_frame
_lag_bc_secs = time.time() - _bowler_change_request_at_time
if _lag_bc_frames > 6 or _lag_bc_secs > 30:
    ...
elif _lag_bc_frames > 3 or _lag_bc_secs > 15:
    [LATENCY-STUCK]
```

Decisive factor: a wallclock cap (**30 s**) bounds the user-visible stale window even when frame rate degrades to p99, while the frame floor (**6**) preserves the original "wait for a few real reads before clearing" safety net if frame rate ever returns to ~2 s. Pure seconds (option a) loses the frame-floor protection during stalls; pure frame reduction (option b) regresses the moment frame rate recovers; option (d) (`score_delta != 0`) is orthogonal and should be tracked separately because mid-over score deltas don't always imply bowler change.

**Risk:** legitimate between-over breaks (drinks, strategic timeouts, **DRS**) can exceed 30 s with no bowler card visible. Mitigation: the hardcap only **clears** `current_bowler` to `None` (it does not assert a wrong bowler), and the next valid OCR read repopulates it. The user impact is identical to today's clear, just delivered ~70 s earlier. No change to `[BOWLER-STALE]` rejection logic (out of scope).

### Test gap

No regression test asserts hardcap timing across realistic frame intervals. Before shipping, validate against:

1. **`logs/pipeline-2026-05-03-1808-srh-vs-kkr-RESTART2.log`** — replay should fire HARDCAP at F35 (≈ over-change frame + 6) instead of F53.
2. **`logs/pipeline-2026-05-02-*-youtube-test.log`** (61 fps) — must **not** regress; with 6-frame floor and 30 s ceiling, the ceiling dominates → unchanged behaviour.
3. **`logs/pipeline-2026-05-03-srh-vs-kkr-45th-match-ipl-2026-innings2.log`** — confirm no spurious HARDCAP during legitimate between-over breaks; expect ≤ current count per innings.

Add a unit test in `files/tests/test_track_a_mechanical_batch.py` parameterised over `(frame_interval_s, expected_hardcap_frame)` covering 2 s / 6 s / 10 s frame rates. Track via the **§4.6** row for `[BOWLER-LATENCY-HARDCAP]` (anomaly threshold also needs a wallclock companion: "or > 30 s wall stale on >3 over-changes per innings").

---

## References

**Operations**

- [`frame_source_setup.md`](../operations/frame_source_setup.md)
- [`parallel_scout_setup.md`](../operations/parallel_scout_setup.md)
- [`trace_and_detect_setup.md`](../operations/trace_and_detect_setup.md)

**Investigations (2026-05-02)**

- [`p3_diagnosis.md`](p3_diagnosis.md)
- [`p4_diagnosis.md`](p4_diagnosis.md)
- [`p7_diagnosis.md`](p7_diagnosis.md)
- [`p8_diagnosis.md`](p8_diagnosis.md)
- [`extras_source_of_truth_diagnosis.md`](extras_source_of_truth_diagnosis.md)

**Design**

- [`parallel_scout_delivery_window_design.md`](parallel_scout_delivery_window_design.md)
- [`trace_and_detect_system_design.md`](trace_and_detect_system_design.md)

**Match reports**

- [`2026-05-02_youtube_test.md`](../match_reports/2026-05-02_youtube_test.md)

**Historical (still applicable)**

- [`score_event_coverage_audit.md`](score_event_coverage_audit.md)
- [`graphic_strip_fix_implementation.md`](graphic_strip_fix_implementation.md)
- [`cold_start_recovery_fix_implementation.md`](cold_start_recovery_fix_implementation.md)
- [`cold_start_recovery_analysis.md`](cold_start_recovery_analysis.md)
- [`multi_ball_decomposition_fix_implementation.md`](multi_ball_decomposition_fix_implementation.md)
- [`batter_stats_flipping_fix_implementation.md`](batter_stats_flipping_fix_implementation.md)
- [`poison_recal_threshold_analysis.md`](poison_recal_threshold_analysis.md)
- [`MONITORING_CHARTER.md`](../MONITORING_CHARTER.md)

## §8 Round 2/3 tags — expected behavior + monitoring (2026-05-04)

Five batches shipped 2026-05-04 (F, G, H, I, J) added new tags that
the live monitor and trace anomaly analyzer now surface explicitly.

### 8.1 Per-tag expected counts and meaning

| Tag | Source batch | Expected count | Meaning |
| --- | --- | --- | --- |
| `[INVARIANT] Refusing to un-dismiss` | Batch F | ≤5/match | Post-wicket strip flap suppression. Bursts → broadcaster timing / extractor flap. |
| `[OVERLAY-LOCKOUT-BREAKOUT]` | Batch G | ≤5/match | Fallback path. Frequent firing means Batch J is not pre-empting the lockout. |
| `[BOWLER-STATS-REGRESSION]` | Batch H | ≤3/match | Cross-match contamination guard. >3 → real contamination or guard FP. |
| `[INCOMING-BATTER-PROMOTED]` | Batch J | ≈ wickets-per-innings minus 1 | Wicket → SM promotion hook. Last wicket of an innings does not promote. |

### 8.2 Anomaly thresholds (`rule_round_2_3_fixes` in `files/anomaly_rules.py`)

| Anomaly id | Severity | Trigger |
| --- | --- | --- |
| `R23-A` WICKETS_WITHOUT_INCOMING_PROMOTION | error (HIGH) | `INCOMING-BATTER-PROMOTED` count < (wickets - 1). Indicates Batch J wiring broken. |
| `R23-B` OVERLAY_LOCKOUT_BREAKOUT_FREQUENT | warn (MEDIUM) | `OVERLAY-LOCKOUT-BREAKOUT` count > 5. Batch J failing to pre-empt. |
| `R23-C` BOWLER_STATS_REGRESSION_FREQUENT | warn (MEDIUM) | `BOWLER-STATS-REGRESSION` count > 3. Manual review required. |
| `R23-D` SCORE_EVENTS_NOT_ADVANCING | error (HIGH) | `SHADOW-STATS.score_events_marked == 0` for >3 consecutive heartbeats. Batch E.2 broken. |
| `R23-E` SHADOW_FRAMES_LOW | warn (MEDIUM) | `SHADOW-STATS.frames_received` delta < 200/30s heartbeat. Option α throughput shortfall. |
| `R23-F` UN_DISMISS_REFUSAL_FREQUENT | info (LOW) | `[INVARIANT] Refusing to un-dismiss` count > 5. Informational. |

Each anomaly fires once per match (dedup via `state.fired_once`).

### 8.3 BMF telemetry path + verification

Batch I writes per-frame BMF debug rows to
`files/logs/bmf_debug/<session>.jsonl`.  Expected throughput is
~5 rows/sec at the 5 fps effective ingest, i.e. ~150 rows per 30 s
heartbeat window.

Verification (also rendered in the live monitor "BMF debug telemetry"
panel):

1. `files/logs/bmf_debug/` exists (pre-created at pipeline start).
2. At least one `*.jsonl` file appears within the first heartbeat.
3. File size grows monotonically between successive monitor refreshes.
   No growth → Batch I writer is not wired.

### 8.4 Live monitor parsing

`files/scripts/live_match_monitor.py` adds the 4 tags above to its
`rows_ship` list, ship-notes table, and a dedicated
**"### Round 2/3 fixes — tag activity"** panel rendering count plus
the first 6 notable timestamps and the expected behavior summary per
tag.  No production code paths were modified.
