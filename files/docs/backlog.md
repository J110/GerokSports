# Backlog

Tracked improvements and known limitations that are explicitly deferred,
not forgotten.  When a new item lands here, link the originating commit
or analysis doc so future engineers can reconstruct context without
archaeology.

**Investigations index:** `files/docs/investigations/INDEX.md` — all `*.md`
in that directory with filesystem mtimes and one-line summaries.

**Match-day monitoring charter:** `files/docs/MONITORING_CHARTER.md` — resolver for **`logs/`** at repo root, analyzer invocation from `files/`, PRIMARY vs PENDING tags, escalation thresholds, per-run report template, innings-break routing, model selection.

**GT vs RCB post-mortem pack (2026-04-30 night):** **`files/docs/investigations/match_postmortem_data_gt_rcb_20260430.md`** + **`match_postmortem_data_gt_rcb_20260430.json`** — autonomous tee/machine aggregate showing **pipeline truncation ~22:17 IST-class brackets**, **`[SM-INNINGS-2-RESET]` zero hits** vs **`[INNINGS-TRANSITION-TELEMETRY]` present**, **`WS-SLOT-INVARIANT` ×345** (live ≥19:50), **`FRAME_POISONED` churn**, **`MULTI_BALL` bridge ~F3293→F3346**, DWR **`retrospective_span ≈3.94%`** on typed windows. **Priority 1 next session:** extend sealed tee + replay **state-integrity** (`AFTER_*` vs `scout`) matrix + innings telemetry parity audit — **defer Scout `V6d`/`V6e` disposition churn** behind that lane.

**Documentation hygiene snapshot (2026-04-30):** **`just test`** **949 PASS / 0 FAIL** (**+5** **`V6e`** variant tests atop prior baseline; **`Groq`** **1 SKIPPED**). **`V6e`** (`files/shadow_eval/variants.py`) adds bowlers_end third **`NOT`** clause per **`scout_v6e_design.md`**; combined-corpus **`K=5`** artifacts `shadow_run_v6e_combined_20260430_*_run*.json`; decision **`scout_v6e_first_shadow_run_results.md`** + autogen **`files/docs/scout_v6e_ensemble_analysis_autogen.md`**. **Outcome:** **`pbks_rr_f600`** plurality **`side_on`** (**P1 met** on combined **proxy** ensemble) but **`rcb_gt_f1455`** **`other→bowlers_end`** regression vs V6d + **Groq 503**-dominated **~16%** pooled errors during run window — **`V6e` not production‑ready**; rerun off‑peak / narrow clause (`V6f`) or discriminator path. Methodological progression narrative updated from earlier **937** baseline when **`V6e`** landed. **Work still conditional:** Lever 1 **PR4 production sign-off** on **PR3 live rate/class telemetry**; Item 2 enforce / prompt PRs gated on Phase 2 + production **a/b**; BATTERS autocorrect Phase 2 gated on clean match-day + **`auto_demote`** refinement (**re-open trigger**, see **`files/docs/investigations/mi_srh_innings_break_analysis.md` Section 5** + **`batters_invariant_cluster_innings1.md`** F2167 narrative); State Recovery Phase 2 still refine-before-flip; scout **`V6d`** **§8 PRIMARY** historically met on corpus_v1 (**`scout_v6d_first_shadow_run_results.md`**) with **`f748`** trade-off; **`V6e`** does **not** supersede **`V6d`** for paste pending **`f1455`** + **`f941`/`f205`** spot checks; combined corpus + prod paste still **M-2 / distribution gated**; maintenance backlog = this hygiene pass artifacts.

**Delivery detection Phase 2AB (2026-04-30):** **`files/docs/investigations/delivery_detection_baseline_phase2ab.md`** — **Phase 2A complete:** IPL **2025** **RCB vs GT** Match **14** (2 Apr 2025, Bengaluru), **RCB innings overs 5–10**, **36** scorecard deliveries tabulated (incl. **1 wicket**, **1 leg bye**). **Phase 2B blocked:** requested artifact **`logs/runs/rcb_gt_rc9_commentary_203904.log`** **absent** from repo workspace → **`[DELIVERY ENQUEUED]`** / **`[DWR]`** baseline **not computed**; **Outcome A/B/C/D unclassified** (<80% confidence). **V6d/V6e disposition:** unchanged vs hygiene paragraph above — **defer prod paste** until Phase **2B** proves **#1a** is non-binding or prioritize **`ball_detector`** if emissions fail threshold once log exists.

### UI / Frontend (shipped items)

- useCommentarySocket.ts useRef typing (`reconnectRef` initial `undefined`, matches useMatchSocket) + page.tsx `OverEntry.balls` — npm run build passes.

- **Scorecard innings split — SHIPPED 2026-04-30:** Backend `innings_history` archives full WS-shaped cards (batting/bowling, extras, partnerships, `fall_of_wickets`) with `deepcopy` at both append sites in `score_manager.py`. WebSocket payload exposes top-level `innings_history` from `test_pipeline._build_full_payload_from_state`. Path A baseline gained additive `innings_history` (empty list in §12.5 fixture). UI: pill sub-tabs **Innings 1 / Innings 2** on the Scorecard tab (`scorecard-ui/app/page.tsx`), default/follow current innings via `useEffect`, frozen inn1 from `innings_history[0]` when inn2 is live, inn2 placeholder during inn1 (`useMatchSocket` replaces `innings_history` arrays atomically). Four tests: `test_innings_history_*`, `test_ws_payload_*` in `test_recent_fixes.py`. **Refactor:** `_reconcile_bowler_overs` (and `_balls_to_overs_str`, shared `overs_to_balls` wiring) lives in `files/card_helpers.py` so `score_manager` does not import `test_pipeline` — removes ultralytics/YOLO import-chain failures (~109 tests) in lean environments.

Items are tagged by priority and rough sizing.  Priorities:
- **P0** — blocks downstream quality, should be next substantive work
- **P1** — quality improvement, schedule when bandwidth permits
- **P2** — hygiene / defensive, do when nearby

**Latest monitoring (2026-04-28 ~22:35 IST):** **Full stack restart** — stopped listeners on **8765/8766** (`python test_pipeline.py`) and **3000** (`npm run dev` in `scorecard-ui`); relaunched both.  **`ui_test_monitor.py --duration 900`** (~15 min, ≈3–4 overs of live wall time) against fresh WS: **208** snapshots.  **Post-restart log slice** `machine-1-2026-04-28.log` from **22:19** IST (join/cold tail of PBKS innings) through **22:35+** — see **Post-restart validation — 15 min window** below.

**SESSION CLOSED (2026-04-29, 22:21 IST).** Full stack shutdown: pipeline (`test_pipeline.py`), UI (`npm run dev`, Next.js port 3000), element checker (`element_checker.py`), parity monitor (`parity_monitor.py`) — all processes terminated, ports 8765/8766/3000 confirmed clear. Match log sealed: **`logs/pipeline-2026-04-29-194416-mi-srh-live.log`** — do not append to this file; use a new RUN_TAG for next session. **P0 remediation (Fix 16 / overs / strip trust) STATUS: SHIPPED 2026-04-30** — see backlog P0 rows + **`MONITORING_CHARTER.md`**. **Resume checklist (next session):** (1) Start fresh pipeline + UI + element checker + parity monitor with new RUN_TAG. (2) Update `SQUAD_URL` / CB URLs to tomorrow's match. (3) **Watch PENDING tags** Section 4 charter on next sealed production log (**`[SM-INNINGS-2-RESET]`**, Thread 7, PR3 CUTTOVER, **PR4 telemetry sign-off conditional on PR3 rates**). (4) Investigate P1 `STRIKER-COLLISION` background class (78% non-wicket-adjacent) — starts F47, separate mechanism from Fix 10.

**Live validation — MI vs SRH match 151954 (2026-04-29):** Active pipeline log is under repo-root **`logs/`** (tee from `files/`), not `files/logs/`. **Use:** `ls -t logs/pipeline-*.log | head -1` — sealed artifact **`logs/pipeline-2026-04-29-194416-mi-srh-live.log`**. Squad/parity/element-checker URLs: [151954 squads](https://www.cricbuzz.com/cricket-match-squads/151954/mi-vs-srh-41st-match-indian-premier-league-2026) (wired in `test_pipeline.py`, `parity_monitor.py`, `element_checker.py` — update for next match).

**Monitoring charter (canonical 2026-04-30):** Full discipline cadence — log path under repo-root **`logs/`**, analyzer flags, PRIMARY vs PENDING tags, escalation matrix, innings-break Composer → Sonnet/Opus handoff, templates — **`files/docs/MONITORING_CHARTER.md`**.

**Historical note (MI–SRH 2026-04-29 Final row):** After **Innings 1 Final**, routine Composer runs **paused until user-directed** replay; telemetry tables below remain authoritative for that artifact. Subsequent match-days follow **`MONITORING_CHARTER.md`** cadence (**15–20 min** nominal; **10–15 min** in hot windows).

**Brief triage takeaway (still true):** **`[BATTERS-INVARIANT]`** ×4 **F487–F506** = admission-window **`rule=C`** latency with Phase 2 off — not Lever 1 PR2 regression. Escalate per **`MONITORING_CHARTER.md` Section 5** (thresholds supersede older heuristic-only bullets).

| Run | Wall window (log) | Frames | Analyzer flags | Escalation |
|:---:|---|---:|---|---|
| **1** (baseline) | 19:44:25 → 19:46:35 (~**2.2 min**) | start **F0** → end **F41** (analyzer health tail; log grows past F44) | `--report-all-fixes --report-bundle-bc --report-pending-validation` | **None** — routine cold-start + expected Item 2 shadow coerces |
| **2** (~31 min wall) | 19:44:25 → **20:15:37** (~**31.2 min**) | **F0** → **F553+** (analyzer `latest STATE` tail) | same | Historical: prior **>3×`[BATTERS-INVARIANT]`** stop — **superseded** by triage + charter above. |
| **3** (~37 min wall) | 19:44:25 → **20:21:31** (~**37.1 min**) | **F0** → analyzer tail (e.g. **F724+**) | same | Superseded by **Innings 1 Final** below. |
| **Innings 1 Final** (2026-04-29) | **19:44:25 → 21:32:51** (**~108.4 min**) | **F0 → F2346+** (log continues; analyzer last ts **21:32:51**) | same | **STOP** routine monitoring — handoff pack in section below. **`[BATTERS-INVARIANT]`:** **12×`rule=C`** + **1×`rule=A`** (**F2167** `active_set_max_two`) — **`rule≠C`** for Sonnet triage. |

**Run 1 — match telemetry summary (2026-04-29, baseline).** Log: `logs/pipeline-2026-04-29-194416-mi-srh-live.log`. **Latest STATE (analyzer snapshot):** inn **1**, **MI 37-0 (3.0)**, RR **12.33** | bat **Ryan Rickelton\*** (19) **Will Jacks** (17) | bowl **None** in snapshot (transient; WS gap cleared at **F23** with **Pat Cummins**).

**PRIMARY validation (counts / first fire):**

| Tag / surface | Count | First fire | Notes |
|---|---:|---|---|
| `[SM-SLOT-INVARIANT]` | **0** | — | W8 collision not exercised yet (valid). |
| `[WS-SLOT-INVARIANT]` | **0** | — | Rate **0/min** vs PBKS **~2.4/min** — short cold slice; **not** >20% *increase* vs baseline. |
| `[SCORER-SCHEMA-WOULD-DROP]` | **0** | — | |
| `[SCORER-SCHEMA-WOULD-COERCE]` | **4** | **F1** | All `filter_caught_in_step3=false`; fields `score_update.from`, `score_update.accepted`, `overs_update.from`, `overs_update.accepted`. |
| `[BATTERS-INVARIANT]` | **0** | — | Target ~0. |
| `[SM-FEEDER-SYNC]` | **21** lines | **F6** | Top writable fields: **score**, **wickets**, **run_rate** (×2 each over the window); **batting_team** ×1; remainder `read_only_now` bowler/bat stat lines. **`sb_accepted=false`:** **0** (no scoreboard reject storm). |
| `[SM-SHADOW-PARITY]` | **0** | — | |
| `[SM-FEEDER-DIVERGENCE]` (`bowler_name`) | **1** | **F5** | **~0.45/min** ≪ **5/min** escalate threshold. |
| `[WS-PROJECTION-GAP]` | **1** WARN + **1** “cleared” INFO | WARN **F5**, clear **F23** | Transient null striker while `active_batting` populated; self-cleared — **not** treated as Lever 2 regression absent sustained rate. |
| `[STRIKER-SM-CUTOVER]` | **2** | **F24** | Over-change mirror (SM+`_inn` lockstep). |

**Other Bundle B/C / Fix telemetry (Run 1 only):** `[OVER-RESYNC]` ×1 first **F6** (over-2 cursor). `[SCORE-INF-GATE]` **floor** ×1 first **F24** (`proposed=37 < min=73`, `bat_sum=36`, `extras=37`) — **live-validated 2026-04-29** on this log (advance/cap arm still pending). `[WS-COLD-START-GATE]` Path D **OPEN** **F3**. **Fix 10 (Run 1):** **1** witnessed wicket vs **`POST-WICKET-ROTATION` 0** — superseded by **Run 2** below once the log grew.

---

**Run 2 — match telemetry summary (2026-04-29, ~31 min wall).** Same log: `logs/pipeline-2026-04-29-194416-mi-srh-live.log`. **Analyzer window:** **19:44:25 → 20:15:37** (**31.2 min**). **Latest STATE:** inn **1**, **MI 108-1 (7.5)**, RR **13.79** | bat **Ryan Rickelton** (54) **Will Jacks\*** (46) | bowl **Nitish Kumar Reddy 1-11**. **FOW:** **1** wicket in summary line; **Fix 10** witnessed transitions **2** with **`POST-WICKET-ROTATION` 2** (first **F474** Rickelton, **F488** Rohit Sharma) — rotation **fires on real wicket traffic**; analyzer **PARTIAL:** **`STRIKER-COLLISION` 86** (**43**/wicket vs target `<10`) — investigate separately from monitoring charter.

**`[WS-SLOT-INVARIANT]` vs PBKS baseline:** **22** fires → **~0.71/min** vs PBKS archive **~2.4/min** (**~70% reduction** vs that single-match baseline; **not** a >20% **increase** — **no PR2 “made it worse” escalation** on rate). First fire **F474** (`duplicate slots 'Will Jacks'`).

**PRIMARY validation (Run 2 cumulative counts / notable first fires):**

| Tag / surface | Count (full log to Run 2 window) | First fire | Notes |
|---|---:|---|---|
| `[SM-SLOT-INVARIANT]` | **0** | — | Still no Lever-1 repair fires. |
| `[WS-SLOT-INVARIANT]` | **22** | **F474** | See rate above. |
| `[SCORER-SCHEMA-WOULD-DROP]` | **7** | **F506** (per analyzer sample) | Shadow mode. |
| `[SCORER-SCHEMA-WOULD-COERCE]` | **4** | **F1** | Unchanged from cold-start. |
| `[BATTERS-INVARIANT]` | **4** | **F487**, **F488**, **F505**, **F506** | Superseded by Run 3 cumulative + triage note (`rule=C` admission window). |
| `[SM-FEEDER-SYNC]` | **475** lines | **F6** | High volume with innings progress. |
| `[SM-FEEDER-DIVERGENCE]` (`bowler_name`) | **9** | **F5** | **~0.29/min** ≪ **5/min** threshold. |
| `[WS-PROJECTION-GAP]` | **2** lines | WARN **F5**, clear **F23** | Same transient cold-start pair; **no sustained rate**. |
| `[STRIKER-SM-CUTOVER]` | **10** | **F24** (first) | Over-change / lockstep mirrors. |

**Other telemetry (Run 2):** `[SCORER-INVARIANT-FILTER]` **5**; `[SCORER-DISMISSED-RESURRECT]` **2**; `[BOWLER-TEAM-OVER-CONSENSUS]` **2**; `[BATTER-NORMALIZE]` **2**; `[NEW-BATTER-BALLS-GATE]` **3**; `[BOWLER-STATS-GRAPHIC-GATE]` **7**; `[EXTRAS-INF-GATE]` **2**; `[SCORE-INF-GATE]` **floor 6** (first **F24**); **FRAME_POISONED** **72**; **BOWLER-STALE** rejects **40**. **`sb_accepted=false`:** **0** in log (no SM→SB reject storm).

**Pending-validation harness (end of Run 2):** observed includes **`[WS-SLOT-INVARIANT]`**, **`[SCORER-SCHEMA-WOULD-DROP]`**, **`[BATTERS-INVARIANT]`**, **`[SCORER-INVARIANT-FILTER]`**, **`[SCORER-DISMISSED-RESURRECT]`**, **`[BOWLER-TEAM-OVER-CONSENSUS]`**, **`[BOWLER-STATS-GRAPHIC-GATE]`**, **`[SCORE-INF-GATE]` floor**, **`[OVER-RESYNC]`**; still zero-hit for **`[SM-SLOT-INVARIANT]`**, **`[BOWLER-BATTER-GATE]`**, **`[ALL-OUT-AUTHORITY]`**, innings **`[SM-INNINGS-2-RESET]`**, etc.

---

**Run 3 — match telemetry summary (2026-04-29, +~6 min wall since Run 2).** Same log: `logs/pipeline-2026-04-29-194416-mi-srh-live.log`. **Analyzer window:** **19:44:25 → 20:21:31** (**37.1 min**). **Latest STATE:** inn **1**, **MI 110-2 (8.3)**, RR **12.94** | bat **Ryan Rickelton\*** (56) **Naman Dhir** (0) | bowl **Eshan Malinga 1-6**. **Innings transitions:** **0** (still innings **1** — routine monitoring continues). **FOW** summary line: **[1, 2]**.

**`[WS-SLOT-INVARIANT]` vs PBKS:** **62** fires → **~1.67/min** vs PBKS **~2.4/min** (**~30% lower** — **not** a >20% **increase** vs baseline).

**Other PRIMARY (cumulative to Run 3):** **`[SM-SLOT-INVARIANT]`** **0**. **`[SM-FEEDER-DIVERGENCE]`** (`bowler_name`) **10** → **~0.27/min** ≪ **5/min**. **`[WS-PROJECTION-GAP]`** still **2** lines (cold-start **F5** / **F23** only). **`sb_accepted=false`:** **0**.

**Fix 10:** witnessed wicket transitions **3**; **`POST-WICKET-ROTATION` 4** (anchors **F474**, **F488**, **F663**, **F724** per log). **`STRIKER-COLLISION` 90** (**30**/wicket vs **<10** target) — **PARTIAL**, unchanged monitoring posture.

**`[BATTERS-INVARIANT]` — Run 3 drill-down**

| Frame | `rule` | Nearest wicket anchor (frame) | Δ frames | Strict ±5 adjacency |
|---|:---:|---|---:|:---:|
| F487 | **C** | F488 (`POST-WICKET-ROTATION` / cluster) | **1** | OK |
| F488 | **C** | F488 | **0** | OK |
| F505 | **C** | F488 | **17** | **>5** |
| F506 | **C** | F488 | **18** | **>5** |
| F684 | **C** | F663 | **21** | **>5** |
| F710 | **C** | F724 | **14** | **>5** |

**Counts (through Run 3 window):** **6** ×`rule=C` in **F487–F710** cluster — superseded by **Innings 1 Final** full list.

---

**Innings 1 Final — MI vs SRH `logs/pipeline-2026-04-29-194416-mi-srh-live.log` (2026-04-29).** **Routine monitoring STOP** after this snapshot — **do not** re-run `analyze_match_telemetry.py` until user directs. **Phase 2 / schema enforce / autocorrect:** unchanged (**off**).

**End-of-pass analyzer `latest STATE`:** inn **1**, **MI 239-5 (19.5)**, RR **12.05** | bat **Ryan Rickelton\*** (119) **Robin Minz** (1) | bowl **Praful Hinge 2-50**. **`Innings transitions`:** **0** (no **`SM-INNINGS-2-RESET`** / analyzer innings break yet). **Log tail:** **F2340** mid-innings **0-0(0.0)** strip poison / celebration overlay; **`[WS-PROJECTION-GAP]`** warns at **F2339**–**F2346** (late **non_striker**/**striker** null vs active card) — flag for UI/projection path review vs DETAIL.

**PRIMARY validation totals (full log window):**

| Tag | Total | Notes |
|-----|------:|-------|
| `[SM-SLOT-INVARIANT]` | **0** | No `source=identify_and_set.*` telemetry in log (**Lever 1 PR2** collision class not exercised). |
| `[WS-SLOT-INVARIANT]` | **122** | **~1.13/min** vs PBKS **~2.4/min** (**~53% lower** — not a rate *increase* vs baseline). First **F474**. |
| `[SCORER-SCHEMA-WOULD-DROP]` | **17** | First **F506**. |
| `[SCORER-SCHEMA-WOULD-COERCE]` | **4** | First **F1** (cold-start only). |
| `[BATTERS-INVARIANT]` | **13** | Frames: **F487, F488, F505, F506, F684, F710, F1288, F1323, F2104, F2105, F2124, F2167, F2285** — **12×`rule=C`**, **1×`rule=A`** (**F2167** `violation=active_set_max_two`). |
| `[SM-FEEDER-SYNC]` | **1364** lines | Top `field=` keys: **bat1_runs** 239, **bat1_balls** 238, **bat2_runs/balls** 237/237, **score/wickets/run_rate** 98 each, **bowler_wickets/overs/runs** 41/41/39, **batting_team** 1. |
| `[SM-FEEDER-DIVERGENCE]` | **21** | **~0.19/min** ≪ escalate threshold. |
| `[WS-PROJECTION-GAP]` | **4** | **F5** WARN + **F23** clear (cold); **F2339**/**F2346** late-innings (non/striker null). |
| `sb_accepted=false` | **0** | |

**Fix 10 (innings 1):** witnessed wicket transitions **6**; **`POST-WICKET-ROTATION` 10** log lines (**9** unique anchor frames — **F2285** double rotation); **`STRIKER-COLLISION` 300** (**50**/witnessed transition vs **<10** target) — **PARTIAL**.

**`STATE-RECOVERY-OVERRIDE-CANDIDATE`:** **13** (telemetry-only candidates — summarize on handoff).

**Pending-validation first fires (innings 1 log):** first observed **`[SCORE-INF-GATE]` floor** **F24** (×12); **`[BOWLER-BATTER-GATE]`** **F1323** (×37 per Bundle B/C); **`[BOWLER-STATS-GRAPHIC-GATE]`** **F254** (×8); **`[OVER-RESYNC]`** **F6** (×1); **`[WS-SLOT-INVARIANT]`** **F474** (×122); **`[SCORER-INVARIANT-FILTER]`** **F505** (×6); **`[SCORER-DISMISSED-RESURRECT]`** **F505** (×2); **`[BOWLER-TEAM-OVER-CONSENSUS]`** **F77** (×3); **`[SCORER-SCHEMA-WOULD-DROP]`** **F506** (×17); **`[SCORER-SCHEMA-WOULD-COERCE]`** **F1** (×4); **`[BATTERS-INVARIANT]`** **F487** (×13). Still **not observed:** `[WICKET-AUTO]`, `[POST-WICKET-CARD-PROPAGATE]`, `[BALLS-CEILING-GATE]`, `[SM-INNINGS-2-RESET]`, `[SCORE-INF-GATE]` advance, FOW internal placeholder regex, `[PRE-MATCH-GRAPHIC-GATE]`, `[PRE-MATCH-COLD-START-GATE]`, `[SM] cold-start zero`, partnership backstaged, `[ALL-OUT-AUTHORITY]`, `[SM-SLOT-INVARIANT]`, `[STRIKER-STATUS-GATE]`, `[BOWLER-CONSENSUS-INCONSISTENT]` (+ override).

**Wicket / admission pattern (±25 frames around each `POST-WICKET-ROTATION` anchor):**

| Anchor F | Event (log) | `BATTERS-INVARIANT` in ±25 | `[STRIKER-COLLISION]` in ±25 | `[POST-WICKET-ROTATION]` in ±25 |
|---:|---|---|---|---|
| **474** | non **Rickelton** cleared (1st cluster) | F487, F488 | 6 | 2 |
| **488** | **Rohit** out / **Naman** in | F487, F488, F505, F506 | 5 | 2 |
| **663** | non **Rickelton** cleared | F684 | 3 | 1 |
| **724** | **Will Jacks** out | F710 | 2 | 1 |
| **1281** | non **Rickelton** cleared | F1288 | 9 | 1 |
| **1348** | **Naman** out / **Hardik** in | F1323 | 1 | 1 |
| **2103** | non **Rickelton** cleared (late) | F2104, F2105, F2124 | 10 | 2 |
| **2105** | **Hardik** rotation | (same window) | 8 | 2 |
| **2285** | **Tilak** + **Rickelton** rotations (×2 lines) | F2285 | 4 | 2 |

**Pattern:** **`rule=C`** fires cluster around wicket/admission/joins; **F2167 `rule=A`** is a **separate** max-active-batters class (**not** wicket-adjacent in the same way) — **Sonnet** charter item.

**Sonnet/Opus handoff flags:** Lever 1 PR2 vs **`[WS-SLOT-INVARIANT]`** rate (**↓** vs PBKS); **`[BATTERS-INVARIANT]`** **`rule=C` vs `rule=A` split** + Phase 2 **`BATTERS_INVARIANT_AUTOCORRECT`** decision; Item 2 pending first-fires; Fix 10 **collision 50×/witness**; **13** state-recovery candidates; **late `[WS-PROJECTION-GAP]`** + **DETAIL vs strip poison** (F2340); **`[BOWLER-BATTER-GATE`** burst **~F1323+**.

---

**Innings 1 comprehensive analysis (2026-04-29, Sonnet 4.6).** Full handoff document: **`files/docs/investigations/mi_srh_innings_break_analysis.md`**.

Key findings:
- **Lever 1 PR2 hypothesis refuted:** `[SM-SLOT-INVARIANT]=0` proves W8 was not the dominant `[WS-SLOT-INVARIANT]` source. All 122 fires are Cause (C) WS-SCRUB rebuild class (SM `non_striker` stale after wicket until next over-end STRIKER-SM-CUTOVER). 53% reduction vs PBKS baseline likely reflects match-characteristic variance + Lever 2 contribution. PR2 safe. **Lever 1 PR3 SHIPPED (2026-04-30)** — dismissed-partner guard + deduped `[SM-W8-DISMISSED-GUARD]`, `[STRIKER-SM-CUTOVER] reason=batter-arrival` at `[REPLACE]` admission, W3–W7 routed through `_set_slot_pair` with named `source=`; production **[WS-SLOT-INVARIANT]** reduction target **73–87%** vs innings-1 baseline per redesign §14.5 (**not** §9’s 85–90%). **Lever 1 PR4 SHIPPED (2026-04-30)** — W11/W12 wicket cleanup paths route through `_set_slot_pair` (telemetry uniformity; **`sm_rotation_atomicity_design.md`** §1.1). Detail: `files/docs/investigations/lever1_pr3_redesign.md` §16 (`lever1_pr3_redesign.md` defers W11/W12 to PR4 in §1).
- **BATTERS-INVARIANT 13/13 admission-window class:** 12×`rule=C` within ±25 frames of wicket events; 1×`rule=A` at F2167 (Hardik Pandya graphic-overlay resurrection, Δ=62 frames, NON-ADMISSION). All fires action=noop_phase1 (Phase 2 off). **Phase 2 DEFER**: innings-break NON-ADMISSION cluster + **`auto_demote` risk post F2167** gates enablement (**`files/docs/investigations/mi_srh_innings_break_analysis.md` Section 5** decision matrix — primary cross-ref). Mechanics: **`files/docs/investigations/batters_invariant_cluster_innings1.md`**.
- **UI projection:** No duplication reached the UI WS payload. `enforce_ws_slot_invariant` in `build_full_payload` repairs the SM duplicate on every frame before the WS broadcast. The "Will Jacks duplicated" symptom was a blank non_striker during the admission window (F474–F486), not a true duplicate.
- **Phase 2 decision: DEFER per innings-break synthesis + F2167 finding** (see **`mi_srh_innings_break_analysis.md` Section 5**). Criteria for re-open: clean match-day Phase 1 telemetry + **`auto_demote`** prefers witnessed-out batter (not **"most recently activated"**). Config change when met: `BATTERS_INVARIANT_AUTOCORRECT = True` in `test_pipeline.py`. **Do not apply mid-match.**
- **Fix 10 STRIKER-COLLISION:** 302 total, but 236/302 (78%) are NON-wicket-adjacent (>50 frames from any wicket). Wicket-adjacent class (22%) shows 0–18 collisions per wicket cluster (mean ~7.3 — near <10 target). Background class (78%) is a separate investigation; starts at F47 before any wicket. Fix 10 is working for its intended scope; background class is a new investigation item.
- **New live-validated tags (first fires in this match):** `[EXTRAS-INF-GATE]` F487 (×10); `[BOWLER-BATTER-GATE]` F1323 (×38); `[SCORER-SCHEMA-WOULD-DROP]` F506 (×17); `[SCORER-SCHEMA-WOULD-COERCE]` F1 (×4); `[STATE-RECOVERY-OVERRIDE-CANDIDATE]` F493 (×13). **Awaiting prod / replay first-fire post 2026-04-30 ship:** P0 **`[SM-INNINGS-2-RESET]`**, **`[OVERS-TRACKER-RESET]`**, P0-C team tags, Thread 7 **`[STRIP-ROWS-MISALIGNED]`** / **`[CAM-GRAPHIC-FAST-PATH-*]`**, Lever 1 PR3 **`[SM-W8-DISMISSED-GUARD]`** + **`reason=batter-arrival`** CUTTOVER counts — see **`MONITORING_CHARTER.md` Section 4**. Still not observed innings 1: `[BALLS-CEILING-GATE]`, `[ALL-OUT-AUTHORITY]`, **`[SM-SLOT-INVARIANT]`** degenerate bootstrap (rarer until stressed paths).
- **Innings 2 monitoring:** routine monitoring handed to Composer 2. Watch `[SM-INNINGS-2-RESET]` first fire (validates Fix 16); SRH admission-window BATTERS-INVARIANT pattern; `[ALL-OUT-AUTHORITY]` if SRH all-out. Escalation thresholds in handoff doc §8. **BATTERS_INVARIANT_AUTOCORRECT stays OFF.**

**Innings 2 transition failure (2026-04-29, Sonnet 4.6 diagnosis, 22:05 IST).** Log: `logs/pipeline-2026-04-29-194416-mi-srh-live.log`, transition window F2421–F2998.

**Symptoms confirmed (all from log):**
1. `MI 0/0` persisted F2695–F2998 (~11 min) — innings change decided "no swap" because visible strip showed MI during innings break carousel.
2. Rickelton 123(67), Robin Minz in innings 2 — MI card not cleared (`SM.set_innings_2()` never fired).
3. De Kock (MI squad player, not SRH) appeared from innings-break MI scorecard graphic at F2980.
4. Praful Hinge as bowler — innings 1 bowler card not cleared, same root cause.
5. `(- ov)` = **overs `None` — ACTIVE NOW** (F3194 22:05:37): overs tracker stuck at `20.0` (innings 1 final); blocks all innings 2 overs as "regression". **Will not self-recover.** RR frozen at 12.15.
6. Target 244 **correctly** set (Fix 9a/9b working).
7. "Sharma" abbreviation from template-placeholder strip at F3009.

**Root cause: two concurrent failures.**

- **Fix 16 coverage gap (`SM.set_innings_2()` not called on `overs_complete_20` path):** The innings change at F2695 fired via `source=overs_complete_20` timeout (348 frames of innings break). This path does NOT call `SM.set_innings_2()`. Fix 16 only covers the SCORER `innings_change=True` path. `[SM-INNINGS-2-RESET]` = 0 in the entire log. Three `FORCE_COLD_START_RECALIBRATION` events (F2483, F2855, F2954) did NOT reset the TRACKING overs tracker (separate system).
- **Team identity: visible-strip trust during innings break:** `[INNINGS-CHANGE]` cold-start path checked the visible batting team from the strip. The strip at F2695 showed MI (innings-break carousel). Code concluded "no swap needed" → MI stayed batting for 11 min. Fix: do not trust visible strip team during innings break; use prior-innings batting team to determine swap direction.

**Mid-match action: RESTART PIPELINE.** Overs tracker will not self-recover. Current SRH state (score, batters, bowler) is clean — restart is safe. Expected recovery: ~30 frames (~2 min) cold-start.

**Backlog entries (new bugs filed):**

| Bug | Priority | Description |
|---|---|---|
| **Fix 16 coverage gap** | **P0** | **Status: SHIPPED 2026-04-30** — P0-A: `execute_innings_change()` + INIT innings-2 paths call `score_mgr.set_innings_2(...)` with `overs_complete_20` / `all_out_10` / `poison_recal_cold_start` / scorer reasons; idempotent guard in `ScoreManager.set_innings_2`. Tests `test_p0a_*`. Ordering: **`score_mgr.set_innings_2` before `scoreboard.set_innings_2`** on `_execute_innings_change_from_state` (harness-caught). See **`files/docs/investigations/execute_innings_change_extraction_design.md`** Section 13, **`files/docs/investigations/mi_srh_post_match_architectural_review.md`**. |
| **Overs tracker not reset on innings change** | **P0** | **Status: SHIPPED 2026-04-30** — P0-B: `ConsistentReadTracker.reset_overs_consensus()` + `[OVERS-TRACKER-RESET] source=…` from `reset_for_innings()` (and INIT poison path). Tests `test_p0b_*`. See **`files/docs/investigations/mi_srh_post_match_architectural_review.md`**. |
| **Team swap trusts visible strip during innings break** | **P0** | **Status: SHIPPED 2026-04-30** — P0-C: **P0-C** section contract in **`files/docs/investigations/mi_srh_post_match_architectural_review.md`** — `[INN1-TEAM-LATCH]`, `cold_start_inn2` suppression, cricket-rules swap with `[TEAM-ATTRIBUTION-CRICKET-RULES]` / strip fallback, rolling `[TEAM-ATTRIBUTION-POISON-RATE]` (threshold **0.56**, telemetry-only). Tests `test_p0c_fixture_*`. |
| **STRIKER-COLLISION background class (78%)** | **P1** | 236/302 fires not adjacent to wickets (starts F47). Separate from Fix 10 wicket-adjacent class. New investigation needed to identify source. |
| **Rule=A `BATTERS-INVARIANT` autocorrect logic** | **P1** | Before enabling Phase 2, revise `auto_demote` to prefer witnessed-out batter, not "most recently activated". F2167 Hardik Pandya case demonstrates incorrect demote risk. |

**Fix 16 revised status (2026-04-30):** `SHIPPED` for the MI vs SRH gap class — `execute_innings_change`, INIT innings-2 detect, and existing SCORER paths all align SM + overs tracker; see P0-A/P0-B rows above and Thread 1–6 diagnosis in `mi_srh_post_match_architectural_review.md`. **Live replay validation** (F2660–F2900) remains the operator checklist for the next seam.

**`execute_innings_change` extraction:** **Status: SHIPPED 2026-04-30** — module-scope `_execute_innings_change_from_state` wrapper; replay sentinel `files/f2660_f2900_transition_signature.txt`; tests named in fixtures table row. See **`files/docs/investigations/execute_innings_change_extraction_design.md`** Section 13.

**P0-A regression caught by harness extraction (2026-04-30):** Original P0-A shipped with **`[SM-INNINGS-2-RESET]`** never firing on the **actual** innings-change path because **`scoreboard.set_innings_2`** was invoked **before** **`score_mgr.set_innings_2`**. `ScoreManager.innings` reads `Scoreboard.current_innings`, so SM already saw **innings == 2** and **`set_innings_2`** idempotent-returned without logging. Unit tests passed because they **bypassed** the full innings-change path. **Harness extraction’s F2660–F2900 E2E replay** surfaced the bug.

**Fix:** Reorder so **`score_mgr.set_innings_2`** runs **first** on **both** the swap path and the cold-start relabel path (`files/test_pipeline.py` — `_execute_innings_change_from_state`).

**Test coverage:** **`test_p0_fixes_e2e_mi_srh_f2660_f2900_innings_transition`** asserts **`[SM-INNINGS-2-RESET]`** fires.

**Implication for next match-day validation:** P0-A production telemetry should now show **`[SM-INNINGS-2-RESET]`** during innings transitions. If the next match’s innings-2 transition still shows **MI 0/0** persistence after this fix, diagnostics return to telemetry — but the **call-ordering** question is resolved.

**Regression catches from methodological discipline (audit → clarification → execute → e2e validation) — 2026-04-30:** (**1**) **P0-A call-order:** `[SM-INNINGS-2-RESET]` silent on live path until **`score_mgr.set_innings_2`** precedes **`scoreboard.set_innings_2`** — caught by **`execute_innings_change`** F2660–F2900 harness (unit-only coverage missed coupling). (**2**) **PR3 INIT path:** **`init_from_card.non`** cold-start routing bug surfaced by **`test_recent_fixes`** **T6** clarification pass. (**3**) **Fix 2 G7:** ball-units / delta guard clarification round after **`cam=graphic`** fast-path design iteration (**`thread7_fix2_cam_graphic_fast_path_design.md`**). (**4**) **`[SM-W8-DISMISSED-GUARD]`** **dedup** requirement from PR3 review (per-match bounded fires). (**5**) **`non_striker` → `non_striker` bulk identifier corruption** — recovered earlier in session via audit → substring replace hygiene (prevent scoreboard-slot mass false positives).

**Fix 9a/9b status:** `WORKING` — target=244 correctly set at F2695.

**Overs/RR status post-restart:** Will recover to correct values within ~30 frames. Balls_remaining will follow once overs commits.

**Thread 7 — Ball-by-ball read gaps in innings 1 (2026-04-30 RE-DIAGNOSIS — supersedes 2026-04-29 entry below).** Original "H3: broadcaster removed strip → cosmetic" verdict invalidated by user domain knowledge (strip is broadcaster-persistent during deliveries) and by frame-level telemetry (scout reports `strip=True` on F2127, F2128, F2134, F2135 within the 18.1→18.3 gap window in `logs/pipeline-2026-04-29-194416-mi-srh-live.log`). **Validated mechanism (composite):** (a) at F2134/F2135, scout strip OCR transposes batter rows (TILAK ↔ RICKELTON cell pair) — **user-confirmed 2026-04-30: broadcast displayed `TILAK 6(1) | RICKELTON 109(50)`, our scout flipped them**; (b) **Fix 1 SHIPPED (2026-04-30):** batter-row Δ>20 still trips the same `[GUARD] … comparison strip for batting team` **info** line, but the response is narrowed to **`batters` only** via `apply_comparison_strip_batter_row_delta_guard()` (`files/test_pipeline.py` — extracted guard next to `_score_inf_floor_components`, invoked from the SCOREBOARD strip path). **`score` / `match_overs` / `bowler` are preserved**; new **`[STRIP-ROWS-MISALIGNED]`** `log.warn` carries `frame`, `row_delta`, `popped`, `preserved`, and `row_pair` diagnostics. Analyzer: `files/analyze_match_telemetry.py` (`STRIP_ROWS_MISALIGNED`, Bundle B/C + pending-validation catalog). Regression: `test_recent_fixes.py` (`test_thread7_fix1_*`). **Fix 2 SHIPPED (2026-04-30):** `cam=graphic` dead-time fast-path — regex strip-head read with eight-clause guard (`_cam_graphic_fast_path` in `files/test_pipeline.py`), commits **`score` and `overs` only** when Scout reports strip without stats overlay (`files/eyes/vision.py`: `last_strip_flag`, `last_overlay_flag`). Constants: `_FAST_PATH_SCORE_DELTA_MAX=6`, `_FAST_PATH_BALL_DELTA_MAX=3`, `_FAST_PATH_COOLDOWN_MAXLEN=4`. Telemetry: `[CAM-GRAPHIC-FAST-PATH-READ]`, `[CAM-GRAPHIC-FAST-PATH-NOOP]`, `[CAM-GRAPHIC-FAST-PATH-REJECT]` (`files/analyze_match_telemetry.py`). Fixtures: `test_thread7_fix2_*` in `files/test_recent_fixes.py`. Design + §17 ship notes: `files/docs/investigations/thread7_fix2_cam_graphic_fast_path_design.md`.

**Deferred:** Fix 3 P3 (`files/eyes/scoreboard.py` row-pairing audit). Full diagnosis: `files/docs/investigations/thread7_rediagnosis_multi_ball_gap.md`.

**MI vs SRH regression fixtures (2026-04-30, `test_recent_fixes.py`):** observational tests for Thread 7 Fix 1 / Fix 2 + Phase 1 behavior — update when Phase 2 ships (**Lever 1 PR3 shipped** — see `test_pr3_*` and §16 in `lever1_pr3_redesign.md`).

| Test | Source investigation |
|------|------------------------|
| `test_fixture_batters_invariant_admission_window_cluster` | `batters_invariant_cluster_innings1.md` §1.1 (F487/F488/F505/F506 rule=C admission window) |
| `test_fixture_batters_invariant_rule_a_resurrection_f2167` | same doc §5 (F2167 rule=A, `upstream_step3_fired=false`) |
| `test_fixture_striker_sm_cutover_intra_over_wicket_gap` | `lever1_pr2_match_analysis.md` §3.1 / §5 (WS-SLOT-INVARIANT + `[STRIKER-SM-CUTOVER]` over-end mirror) |
| `test_fixture_frame_poisoned_rate_innings_break_baseline` | innings-break window F2347–F2694 vs `mi_srh_post_match_architectural_review.md` §3.2 (P0-C rate input; observed **38** `FRAME_POISONED` hits / **348** nominal frames ≈ **10.9%**) |
| `test_fixture_multi_ball_gap_camera_state_transition` | `thread7_rediagnosis_multi_ball_gap.md` §1 (MULTI_BALL placeholders + score-gated `on_broadcast_override`; production `[THIS-OVER] Ball` wiring asserted in source) |
| `test_p0a_set_innings_2_idempotent`, `test_p0a_fix16_coverage_overs_complete_20`, `test_p0a_fix16_coverage_poison_recal_cold_start` | P0-A Fix 16 coverage + SM idempotency (`files/score_manager.py`, `files/test_pipeline.py`) |
| `test_p0b_overs_tracker_reset_after_innings_change`, `test_p0b_overs_tracker_reset_telemetry`, `test_p0b_overs_progression_after_reset` | P0-B `ConsistentReadTracker.reset_overs_consensus` + `[OVERS-TRACKER-RESET]` wiring |
| `test_p0c_fixture_a_poison_recal_innings_change_regression` … `test_p0c_fixture_e_recovery_to_strip_post_swap` | P0-C §P0-C contract (latch, cold-start override, cricket-rules swap, telemetry-only threshold) |
| `test_innings_transition_window_parser`, `test_pre_innings_2_transition_fixture_integrity`, `test_p0_fixes_e2e_mi_srh_f2660_f2900_innings_transition` | **`execute_innings_change` extraction SHIPPED (2026-04-30):** `_execute_innings_change_from_state` + MI–SRH log parser + `files/f2660_f2900_transition_signature.txt` sentinel — design `execute_innings_change_extraction_design.md` §13 |

**Path A baseline hygiene (2026-04-30):** `files/path_a_ws_payload_baseline.txt` had two JSON spellings that used an erroneous eleven-character slot name (field `positions[].name` and the `scorecard` key). They were normalized to the canonical three-letter `non` key so `test_path_b_low_risk_batch_path_a_regression_signature_match` matches the serializer after repo-wide identifier cleanup.

**Lever 1 PR3 — dismissed-partner guard + batter-arrival CUTOVER + W3–W7 `_set_slot_pair`:** **Status: SHIPPED 2026-04-30** — dismissed-partner guard + deduped **`[SM-W8-DISMISSED-GUARD]`**, intra-over **`[STRIKER-SM-CUTOVER] reason=batter-arrival`**, W3–W7 `_set_slot_pair` sources; production **`[WS-SLOT-INVARIANT]`** reduction target **73–87%** vs MI–SRH innings-1 baseline per redesign **Section 14.5** (supersedes earlier Section 9 envelope). See **`files/docs/investigations/lever1_pr3_redesign.md`**. Implementation notes: **`files/score_manager.py`** (`_sm_w8_partner_if_active`, `_w8_non_for_identified`, `_set_slot_pair` sources), **`files/test_pipeline.py`** (`_pr3_batter_arrival_slot_cutover`, innings-change **SM-before-SB** ordering), **`files/analyze_match_telemetry.py`** (`SM_W8_DISMISSED_GUARD`, `STRIKER_SM_CUTOVER_REASON_BATTER`), tests **`test_pr3_*`** (T1–T7) in **`files/test_recent_fixes.py`**. Path A snapshot unchanged.

**Lever 1 PR4 — W11/W12 wicket slot cleanup → `_set_slot_pair`:** **Status: SHIPPED 2026-04-30** — routing / telemetry uniformity on END-STATE-NULL-OK wicket hygiene branches (**`sm_rotation_atomicity_design.md`** W11–W12; deferred from PR3 per **`lever1_pr3_redesign.md`**). **`files/score_manager.py`:** `_apply_event` paths call **`_set_slot_pair`** with **`source=apply_event.wicket_striker_out`** / **`apply_event.wicket_non_striker_out`**. Tests **`test_pr4_w11_helper_routing`**, **`test_pr4_w12_helper_routing`**. Path A snapshot unchanged (behavioral no-op). **Formal production closeout / backlog burn-down for PR4 is CONDITIONAL** on **PR3 live telemetry validation** (rate + class confirmation vs Section 14.5 predictions — operator checklist on next sealed log).

**Lever 1 status:** **PR1** helper introduction — **SHIPPED** (`sm_rotation_atomicity_design.md`). **PR2** W8 migration — **SHIPPED**. **PR3** guard + CUTTOVER + W3–W7 — **SHIPPED** (`lever1_pr3_redesign.md`). **PR4** W11/W12 routing — **SHIPPED** in repo; **prod validation gate CONDITIONAL** on PR3 field data + rate checks. Next work: monitor next match; optional new classes only if telemetry diverges.

**Thread 7 — Ball-by-ball read gaps in innings 1 (2026-04-29, Sonnet 4.6 diagnosis, 22:15 IST). [SUPERSEDED 2026-04-30 — see entry above.]** Log: `logs/pipeline-2026-04-29-194416-mi-srh-live.log`, innings 1 (F0–F2421).

**Symptom confirmed:** "This Over" display showed `W ? ? 1 _ _` at MI 228/4 (18.4 ov). The `?` tokens at ball-positions 2 and 3 represent deliveries for which no individual ball data was captured. Observed 6 times across innings 1.

**Mechanism identified: Broadcast graphics overlay strips scoreboard during play (Hypothesis H3 — strip-read failure on specific frames).** Not network disconnects; not frame processing backlog; not over-cursor advance without detection. The cause is the broadcaster inserting wicket replay / over-end graphics / career-stat overlays that temporarily replace or shrink the scoreboard strip. During this ~1–3 minute blackout, the over cursor advances. When the scoreboard strip returns, the pipeline detects a multi-ball jump and issues a `MULTI_BALL` event that inserts one `?` placeholder per skipped ball into `this_over`.

**Confirmed telemetry at F2136 (over 18.1→18.3):**
- `[THIS-OVER] Ball MULTI_BALL appended to over 18`
- Internal log: `Missed 2 balls (+6 runs) — added 2 placeholders (capped from 2)`
- Camera log: `cam=closeup → resuming active play after dead-time gap (#207 skipped)`
- Broadcast "THIS OVER" strip during the gap (F2169–F2171): truncated garbage (`FULL SCORECARD:` only) — no ball tokens available for gap-fill
- `[THIS OVER] ['W', '?', '?', '1'] = 1 runs` at F2150 — exactly matches user-observed display

**Quantification across innings 1 (6 `MULTI_BALL` events):**

| Event | Over jump | Missing balls | Runs lost to gap | Trigger |
|---|---|---|---|---|
| F193 | 4.0→4.3 | 4.1, 4.2 | not isolated | Over-end/new-over graphics |
| F310 | 5.3→5.5 | 5.4 | not isolated | Unknown graphic |
| F1183 | 12.2→12.4 | 12.3 | not isolated | Unknown graphic |
| F1409 | 14.1→14.3 | 14.2 | not isolated | Post-wicket? |
| F2136 | 18.1→18.3 | 18.2, 18.3 | +6 runs | Post-wicket (Hardik Pandya) |
| F2339 | 19.3→19.5 | 19.4 | not isolated | Unknown graphic |

Total: 7 balls marked `?` across 6 events (out of ~120 innings 1 balls = **~5.8% ball-gap rate**).

**Gap-fill mechanism (existing):** `ThisOverManager.on_broadcast_override()` is designed to fill `?` placeholders from the broadcast strip's own "THIS OVER" token list. It did NOT fill any gaps in this match because the broadcast strip's "THIS OVER" section was also empty/garbage during and after the camera switch (F2169: `THIS OVER: FULL SCORECARD:`). The broadcaster itself does not retain individual ball tokens during graphics overlays.

**Severity: COSMETIC ONLY.**
- Cumulative state (score, wickets, overs) **remains accurate** throughout all 6 gaps. The pipeline commits the full run delta at the first post-gap frame (e.g., at F2136: score correctly advances from 221 to 227 as a batch).
- No functional impact: RR, target, batter scores, WS payload are all computed from cumulative state, not ball-by-ball data.
- The `?` tokens affect only the "This Over" display ribbon on the UI — a visual indicator only.

**Recommendation: ACCEPTED LIMITATION** (no hotfix, separate P3 investigation if broadcast source changes).
- The broadcaster controls the strip availability. The pipeline's `MULTI_BALL` + gap-fill mechanism is already the correct response.
- A potential improvement: if the broadcaster's "THIS OVER" strip does contain tokens after graphics end, `on_broadcast_override` would auto-fill the `?` gaps. This already works when the data is available.
- A deeper fix (e.g., inferring individual ball runs from score deltas when a 2-ball gap has non-zero run delta) is low-value: the 6 runs across 18.2+18.3 can't be split reliably without a source of truth.

**Backlog entry (P3, post-match filing):**

> **`[MULTI_BALL]` gap rate: 5.8% in MI-SRH innings 1 (broadcast graphics windows).** 7 balls marked `?` in 6 events. Root cause: broadcaster graphic overlays (wicket replays, over-end cards, career stats) remove the scoreboard strip for 1–3 min during active play. The pipeline's MULTI_BALL mechanism correctly flags these; gap-fill via `on_broadcast_override` cannot recover when the broadcast's own THIS OVER tokens are also absent. Severity: cosmetic. Cumulative state accurate. **No action required unless broadcaster strip behavior changes.** Monitor rate across future matches — if rate rises above ~10%, investigate whether `on_broadcast_override` gap-fill success rate can be improved (e.g. by buffering the last observed THIS OVER tokens and applying them on the next non-poisoned frame).

**Python 3.9:** `ui_test_monitor.py` needed `from __future__ import annotations` so PEP604 return types load; fixed in repo.

**Next session (monitoring):** **`[NEW-BATTER-BALLS-GATE]`** — empirical triage for 22:19–22:35 IST slice: **`files/docs/investigations/new_batter_balls_gate_2026-04-28.md`** (20 log lines; estimated FP rate **~17%** vs TP+FP → **no tune queued**).  Still watch volume after POISON/full_reset for drift.  Triage **`NO_ACTIVE_BATTERS` / `NO_CURRENT_BOWLER` / `SCORE_MISSING`** bursts in UI monitor; continue innings-end / **(22)** / **(17B+)** on full logs.

**State-recovery Phase 2 enablement:** **REFINE before flip.** See **`files/docs/investigations/state_recovery_phase2_enablement_analysis.md`** — `machine-1-2026-04-28.log` produced **64** real candidates (28 distinct sigs); FP / (TP+FP) = **20.8 %** at `N=5` today, drops to **0 %** with two narrow refinements: (a) `_check_coherence` requires `candidate.score is not None`; (b) caller suppression also keys on `scoreboard._inn.get("score") is None`. After refinement, expected production benefit is ~5 min recovery-latency improvement vs `[POISON-RECAL]` on the dominant stale-baseline class. Analyzer regex hardening (brace-balanced JSON parser) is a small follow-up — current `\S+` pattern silently drops candidates whose JSON contains string literals with spaces.

**Lever 1 PR1 — `ScoreManager._set_slot_pair` helper only (2026-04-29, shipped):** Per **`files/docs/investigations/sm_rotation_atomicity_design.md`** §8 PR1. Introduces **`_set_slot_pair(striker, non_striker, *, source)`** — canonicalize via existing **`_canonicalize_name`**, duplicate-slot repair with **`[SM-SLOT-INVARIANT]`** + **`source=`** telemetry, tuple-pack write. **No W1–W12 callsite migrations** in this PR; **PR2** migrates **`_identify_and_set`** (W8) — see next bullet. Tests: **`test_set_slot_pair_writes_both_slots_atomically`**, **`test_set_slot_pair_repairs_canonical_collision_with_telemetry`**, **`test_set_slot_pair_canonicalization_uses_existing_helper`**. Analyzer: **`SM_SLOT_INVARIANT`** regex, Bundle B/C key **`lever1_sm_slot_invariant`**, **`PENDING_VALIDATION_PATTERNS`** entry **`[SM-SLOT-INVARIANT] (Lever 1 helper repair)`** (distinct from Fix 18 **`[WS-SLOT-INVARIANT]`**).

**Lever 1 PR2 — W8 `_identify_and_set` → `_set_slot_pair` (2026-04-29, shipped):** Same design doc §3.3 / §6.3 W8 / §8 PR2. Partner resolution is **`_same_name`** for **`bat1_name` / `bat2_name`**; otherwise the §3.3 canon compare on **`new`** vs prior **`non_striker`** (keep distinct **`non_striker`**, else **`None`**). All writes route through **`_set_slot_pair(..., source=f"identify_and_set.{method}")`**. Scope is **W8 only** (no W3–W7 / W9–W12 in this PR). Tests: **`test_sm_pr2_w8_identify_and_set_routes_via_set_slot_pair`**, **`test_sm_pr2_w8_non_striker_keeps_distinct_prior_non_else_branch`**, **`test_sm_pr2_w8_partner_alias_collides_emits_sm_slot_invariant`**, **`test_sm_pr2_w8_balls_delta_happy_path_distinct_pair`**. **Path A** WS-payload baseline unchanged (`just test` Path A regression PASS).

**get_broadcast_state Option A — Lever 2 cleanup (2026-04-29, shipped):** Per **`files/docs/investigations/get_broadcast_state_path_b_audit.md`**. `Scoreboard.get_broadcast_state` is a **deprecated silent alias** of `get_live_state` (no `warnings.warn`). WS assembly uses **`get_live_state`** in **`_build_full_payload_from_state`**; **`_project_active_batters`** now runs when `state` is non-empty in **shadow and live** (§6.3); bowler SM write + WS-SCRUB + `enforce_ws_slot_invariant` stay gated on `not score_mgr.shadow`. Regression: **`test_get_broadcast_state_aliases_get_live_state`**, **`test_get_broadcast_state_shadow_mode_uses_canonical_projection`**, **`test_get_broadcast_state_back_compat_signature`**. Path A byte snapshot unchanged. **Lever 1 PR3 (2026-04-30)** closes the dominant Cause-(C) SM/non stale-window class; **Lever 1 PR4 (2026-04-30)** completes W11/W12 helper routing per **`lever1_pr3_redesign.md`** / **`sm_rotation_atomicity_design.md`**.

**Item 3 — Path B LOW-risk batch:** **Status: SHIPPED 2026-04-29** — SM feeder parity for 12 LOW-risk scalars/denorms per **`files/docs/investigations/dual_broadcaster_path_b_migration_contract.md`**.

**Implementation:** Executable spec **`files/docs/investigations/dual_broadcaster_path_b_migration_contract.md`**. `ScoreManager` now holds Path B properties for the LOW-risk scalar/denormalized fields (read-through from `Scoreboard` + feeder setters for `score` / `wickets` / `run_rate` / `target` / `batting_team`; frame threading via `_frame_int` / `_accept_update(card, frame)`). `build_full_payload` emits **`[SM-FEEDER-DIVERGENCE]`** when `score_mgr.bowler_name` and `scoreboard._inn["current_bowler"]` diverge (signature rate-limited to module-level **`_last_feeder_div_sig`**). Analyzer Bundle B/C adds **`path_b_sm_feeder_sync`**, **`path_b_sm_shadow_parity`**, **`path_b_bowler_feeder_divergence`**. **Path A WS-payload snapshot regression** (contract §12.5): **SHIPPED 2026-04-29** — `build_full_payload` body extracted to module-level **`_build_full_payload_from_state`** with a thin `run_test()` wrapper; **`test_path_b_low_risk_batch_path_a_regression_signature_match`** + **`files/path_a_ws_payload_baseline.txt`** (batters list canonicalized for compare). Design: **`files/docs/investigations/build_full_payload_extraction_design.md`**.

**Verification — `full_reset` + SB FOW/extras clear vs `[POISON-RECAL]` (2026-04-29):** **`files/docs/investigations/full_reset_fow_extras_verification.md`**. Finding: **CORRECT** for nuclear-recal intent and consumer (`sync_fow_to_wickets`) behavior; historical logs with `AFTER_fow_count>0` while headline `None` explained by **legacy SB FOW not cleared + immutability**. **Post–Item-3:** confirm `AFTER_fow_count=0` on poison frame on first match-day log; monitor extras/floor around POISON if needed. **No ANOMALY** filed from this pass.

**Dual-broadcaster Path B substrate audit — Item 5 (2026-04-29, summary 2026-04-30):** **`files/docs/investigations/dual_broadcaster_substrate_audit.md`**. **12 LOW-risk** FEEDER fields: **SHIPPED** via Item 3 (2026-04-29). **2 MEDIUM-risk** (`SM.overs` consensus; `SM.bat1_name`/`bat2_name` ordering): **DEFERRED** — opt-in flag PRs, low priority, **no production symptoms** observed on MI–SRH pass. **2 HIGH-risk** (`this_over`; `partnership_*`): **Path C audit complete** (`dual_broadcaster_path_c_audit.md`); **C1+C2 both DEFER** recommended — architectural cleanup, not rate-reducing. Original detail: SM 62 fields; SB 38 dual-path fields; **27 PARALLEL**. Path A unchanged.

**Dual-broadcaster Path B substrate audit (detail, 2026-04-29):** **`files/docs/investigations/dual_broadcaster_substrate_audit.md`**. SM has 62 instance fields; SB has 38 dual-broadcaster-relevant fields. **27 PARALLEL fields** identified, of which **12 are LOW-risk FEEDER conversions** suitable for Item 3's first PR (~250 LOC, ~140 callsites, single coherent change). **2 MEDIUM-risk fields** (`SM.overs` consensus baseline; `SM.bat1_name`/`bat2_name` slot ordering) require behavioural test gates and a flag-staged rollout. **2 HIGH-risk surfaces** (`this_over` ↔ SB ↔ over_mgr; `partnership_*` ↔ SB ↔ partnership_tracker) need their own dedicated audits — explicitly OUT of scope for Item 3. 3 FEEDER-existing fields (`striker`, `non_striker`, `bowler_name`) verified; recommend adding divergence telemetry to `bowler_name`. Path A WS-payload assembly contract unchanged across all of Item 3.

**Dual-broadcaster Path C audit — `this_over` and `partnership_*` (2026-04-29):** complete (audit only, no code changes); **`files/docs/investigations/dual_broadcaster_path_c_audit.md`**. **Corrected Item 5's "3 sources" count for both surfaces to "2 active + 1 dead":** `Scoreboard.this_over` / `SB.over_history` write methods (`update_this_over`, `on_new_over`, `initialize_this_over`, `get_this_over_runs`, `get_this_over_for_display`) are **only called from `test_offline.py:197`** (dead on the live path); `Scoreboard.current_partnership` / `SB.partnerships` are **never written with actual data anywhere** (only `None` / `[]` assignments in init / `setup_innings` / `_handle_innings_change`). Live divergence is **SM-internal mirror ↔ external manager**, not SM ↔ SB. **`this_over` → `PATH-C-CANONICAL-OWNER`** with `over_mgr` as owner: SM mirror removable via read-through `@property` (recommended PR **C2**, ~+60/-40 LOC, new tag `[SM-OVER-HISTORY-DIVERGENCE]`); `SM.completed_over` / `completed_over_runs` **must remain SM-owned** (sticky boundary-frame bridge for the over-rollover gap). **`partnership_*` → `INFEASIBLE` for migration**: `SM.partnership_*` and `PartnershipTracker` are **not redundant copies** — they are independently designed estimators with disjoint fault models (event accumulator vs anchor-and-delta) and disjoint capabilities (`partnership_known=False` gate vs `PT.override` broadcast capability); recommended PR **C1** is **telemetry-only** (`[SM-PARTNERSHIP-DIVERGENCE]`, +30 LOC, mirrors Item 3's `[SM-FEEDER-DIVERGENCE]` for `bowler_name`). Both WS-visible symptoms previously attributable to dual writers — `over_history` "stuffing" backlog (10) and mid-innings partnership backlog (20) — are **already shipped fixes** via Path A 2026-04-27 and 2026-04-28 respectively. **No `[WS-SLOT-INVARIANT]` traces to either surface** (Lever 1 territory). **No pending live-validation backlog item depends on Path C migration** — work is architectural-cleanup-grade, not rate-reducing; defer-indefinitely is an honestly supported alternative (§3.3). Surfaces are independent at the migration level; C1 and C2 can ship in any order or stand alone. Path A WS-payload byte-identity preserved by construction in all recommended PRs (over_mgr remains the canonical reader; `partnership` PR is telemetry-only).

**Striker Path B — `_inn[striker/non_striker]` READ audit (2026-04-29):** complete; one bounded migration shipped.

| Site | Cat | Disposition |
|---|---|---|
| `test_pipeline.py:_canonical_active_slot` (helper, ~L2289) | BACKSTOP | helper itself; SM-first read with `_inn` fallback — kept as documented |
| `test_pipeline.py:_build_state_recovery_current` (~L2440-2447) | AUTHORITATIVE | state-recovery aggregator compares against the **legacy projection**; reading SM here would defeat the consensus contract |
| `test_pipeline.py:7256-7257` DRS-FREEZE DETAIL `_after_striker / _after_non_striker` | **MIGRATED** | now SM-first with `_inn` fallback (mirrors canonical DETAIL site at ~L9663-9665); divergence-only `[STRIKER-READ-SM-CANONICAL]` telemetry |
| `scoreboard.py:2153, 2160` Fix 5 collision guards | AUTHORITATIVE | write-site `_inn` read; precondition for the immediately-following slot mutation |
| `scoreboard.py:3153-3155, 3187` `_post_witnessed_dismissal_slot_rotation` | AUTHORITATIVE | function is the `_inn` writer; reads choose the rotation target |
| `scoreboard.py:3402-3405` `dismiss_batter` slot clear | AUTHORITATIVE | write path; reads to decide which slot to clear |
| `scoreboard.py:3548-3549` `get_live_state` | AUTHORITATIVE | legacy projection consumer (LLM prompts, eyes/main.py) |
| `scoreboard.py:3640-3641, 3862-3863` `get_state` / cache snapshot | AUTHORITATIVE | snapshot of legacy projection for restore path |
| `scoreboard.py:4212` `get_current_batters` | DEFER | display helper consumed by `eyes/main.py:557` log line; scoreboard has no `score_mgr` reference — would require adding optional param or moving the formatter to caller. Low leverage; documented |
| `scoreboard.py:4260` `get_current_batsman_handed` | DEFER | delivery-classifier handedness lookup; same scoreboard-internal constraint; SM authority would only matter if striker name differs and styles differ — defensible after a deeper Path B refactor |

Migration test count delta: **+2** (`test_path_b_striker_read_sm_canonical_drs_detail_present_in_source`, `test_path_b_striker_read_sm_canonical_returns_sm_value_on_divergence`). Analyzer adds `striker_read_sm_canonical` label (Bundle B/C self-test fixture extended). Fix 5 collision guard remains in place as defense-in-depth.

---

## P0 — BallEventDetector silenced when team overs missing (`commentary.py`)

**Symptom:** No delivery / `ball_event` from **BallEventDetector (BED)** for whole **innings 2** — `DETAIL` lines show `ball_event=—` while score moves; SM may still emit shadow events.

**Root cause:** `BallEventDetector.detect` (`eyes/commentary.py`) used to do:

- `if self.prev_overs is None or overs is None: _save(..., overs); return None`

When `tracker.get("overs")` is **`None`** (strip without `match_overs`, consensus lag, innings-2 chase UI showing `overs: null` while score commits), `_save` was called with **`overs=None`**, which sets **`prev_overs = None`** and **wipes** the last legal-ball witness. Every subsequent frame repeats → **`balls_delta` logic never runs** → **zero BED firings** for the innings.

**Fix (2026-04-28, shipped):** If `prev_overs` is already set and this frame’s tracker `overs` is `None`, call **`_save(score, wickets, self.prev_overs, …)`** — refresh score/wicket witness but **preserve** `prev_overs`. Regression: `test_bed_preserves_prev_overs_when_team_overs_missing` in `test_recent_fixes.py`.

**Validation:** Replay innings-2 / close-up heavy logs; DETAIL should show intermittent `ball_event` again when overs reappear on the strip.

---

## BED `prev_overs` — adjacent save-site audit (2026-04-28)

**Scope:** `eyes/commentary.py` — all `BallEventDetector._save` call sites and the 2026-04-28 `detect` branch that preserves `prev_overs` when tracker `overs` is `None` (shipped).  `eyes/scoreboard.py` / `eyes/this_over.py` — no parallel `prev_overs` witness; state flows through `Scoreboard.set` and `ThisOverManager` resets (explicit reset paths only).  `score_manager.py` `_handle_warm` — `_val(card_v, self_v)` keeps prior `overs` when the card omits `overs` (`None`).

**Result:** **No GAP** found that mirrors the silenced-BED failure mode (wiping a committed overs witness on `None` input).  **UNCLEAR:** none flagged; deeper cross-call traces deferred unless production shows a new pattern.

---

## Live validation — PBKS vs RR (extended, 2026-04-28 ~22:12 IST)

**Log:** `logs/pipeline-2026-04-28-pbks-rr-live.log` (~41k lines).  **Analyzer** `--report-all-fixes --report-bundle-bc` + `--report-pending-validation`.

| Fix / tag | Δ vs ~20:16 checkpoint | Notes |
|-----------|-------------------------|-------|
| **Window** | 19:27:49 → 22:11:55 (**~164 min**) | Latest state: RR chase, 123/3, ~11.1 RR (strip overs sometimes null in snapshot) |
| **(11) EXTRAS-INF-GATE** | **9** fires | Same phantom class; active |
| **Fix 12** RUNS-REJECT | **40** streak / **4** release | +2 releases (Shreyas Iyer **F1726**, Marcus Stoinis **F1738**) |
| **(6) BATTER-NORMALIZE** | **12** | Additional surname-ghost drops |
| **(17A) BOWLER-BATTER-GATE** | **41** | Was 14 in short window |
| **(16) NEW-BATTER-BALLS-GATE** | **5** | Stoinis admission ceiling |
| **(14) score regression** | **1** (F169) | Unchanged |
| **Fix 18 L2/L3** | L2 **6**, L3 **1** | Same cluster as early match |
| **`[WS-SLOT-INVARIANT]`** | **387** fires | **Now live-validated at volume** (tail from ~F1603+); investigate duplicate striker/non projection vs strip churn |
| **Path B `[STRIKER-SM-CUTOVER]`** | **36** (analyzer) | Ongoing mirroring |
| **Cluster 1 `[SCORER-ACTIVE-GATE]`** | **2** | F1320 (witnessed-out reject) |
| **`[POISON-RECAL]`** | **7** | Graphic/strip POISON streak recovery; confirm redeployed **`full_reset`** path via log substring |
| **Fix 10 POST-WICKET** | **9** rotations / **344** collisions, **57.3**/wkt | Still partial vs <10 target |
| **(17B+)** inconsistent / override | **0** | Pending |
| **(19)(21)(22)** | **0** | Innings-2 join may bypass some transition detectors; keep monitoring |
| **STATE-RECOVERY** candidates / overrides | **0** / **0** | Phase 2 mutation remains **off** in repo default |

**`--report-pending-validation`:** still **not observed** — `[SCORER-INVARIANT-FILTER]`, `[SCORER-DISMISSED-RESURRECT]`, `(17B+)`, Fix 13/14/19/21/22, **SM-INNINGS-2-RESET**, etc.  **Observed** pending-catalog tags: **`[BOWLER-BATTER-GATE]`**, **`[WS-SLOT-INVARIANT]`**, **`[BOWLER-TEAM-OVER-CONSENSUS]`**.

---

## Post-restart validation — 15 min window (2026-04-28 ~22:19–22:35 IST)

**Context:** Full **pipeline + scorecard UI** restart; then **900 s** live WS sampling (`files/ui_test_monitor.py`).  **Log slice:** `files/logs/machine-1-2026-04-28.log` from timestamp **`[22:19:`** onward (~4576 lines).

### UI monitor (208 frames / 900 s)

| Signal | Severity | Notes |
|--------|----------|-------|
| **NO_ACTIVE_BATTERS** | HIGH | 14/208 (6.7%), streak 14 — likely strip/projection gap while cards still have rows; correlate with closeup/graphic |
| **NO_CURRENT_BOWLER** | HIGH | 29/208 (13.9%), streak 24 — same class |
| **SCORE_MISSING** | MEDIUM | 14/208 — `score=None wickets=None` while `phase=live` |
| **SCORE_FROZEN** | transient | 7 (self-corrected) |

**Score progression sample:** RR **137/3 (12.4)** → **160/6 (14.4)** across window — real play advanced; visible UI glitches are **burst-y**, not a fully frozen card.

### Telemetry counts (same log slice)

| Tag | Count | Note |
|-----|------:|------|
| **`[POISON-RECAL]`** | **3** | Pairs with **`reason=full_reset:poison_recal_consensus`** on `ScoreManager` — **POISON-RECAL → `full_reset` validated live** |
| **`[OVER-RESYNC]`** (Fix **21**) | **3** | E.g. F8, F127, F169 — `score_manager_mid_innings_recovery` |
| **`[SCORER-INVARIANT-FILTER]`** | **5** | Witnessed-out Parag rows skipped (**F65**, **F74**, **F75**, **F80**, **F81**) |
| **`[SCORER-DISMISSED-RESURRECT]`** | **2** | Non-witnessed-out Ferreira proposals skipped (**F75**, **F167**) |
| **`[WS-SLOT-INVARIANT]`** | **26** | Lower rate than pre-restart extended tail (387) but still active |
| **`[STRIKER-SM-CUTOVER]`** | **2** | Path B mirroring |
| **`[BOWLER-TEAM-OVER-CONSENSUS]`** | **2** | 17B accelerated path |
| **`[NEW-BATTER-BALLS-GATE]`** | **20** | **Triaged:** `files/docs/investigations/new_batter_balls_gate_2026-04-28.md` — mostly TP (implausible balls on `since_admit=0`); FP rate &lt; 20%; **no threshold change** |
| **EXTRAS-INF-GATE** | **0** | None in slice |
| **(17B+) / ALL-OUT / Fix 19** | **0** | No triggers in slice |

---

## Changes shipped today (2026-04-28, bounded + maintenance follow-up)

Follow-up implementation after Bundle B/C: bounded bowler/FOW fixes and
maintenance hygiene that do not require live monitoring.  Cluster 1
architectural cleanup remains in progress separately.

| # | Name | Files | Telemetry | Tests | Status |
|---|------|-------|-----------|-------|--------|
| **17B** | Bowler team/over consistency consensus | `eyes/scoreboard.py` `update_bowler()` | `[BOWLER-TEAM-OVER-CONSENSUS]`, `[BOWLER-CONSENSUS-INCONSISTENT]`, `[BOWLER-CONSENSUS-INCONSISTENT-OVERRIDE]` | 594 / 0 | ✅ shipped — accelerated promotion when the candidate spell ball matches the team strip while `current_bowler` is inconsistent; **2026-04-28** adds a ball-in-over plausibility gate on vanilla 3-frame flips (DC-vs-RCB wrong-bowler / stale cumulative figure class) with streak override. |
| **Fix 8+** | Bowler stats graphic guard keyword expansion | `test_pipeline.py` `_INFO_PANEL_KEYWORDS` | `[INFO-PANEL-GATE]` | 594 / 0 | ✅ shipped — existing content-based info-panel gate now also catches broader stats-overlay markers such as `ECONOMY`, `MATCHES`, `PLAYER STATS`, `BEST FIGURES`, `PURPLE CAP`, and `ORANGE CAP`. |
| **15** | FOW placeholder UI hygiene | `test_pipeline.py` `project_fow_for_payload()` | payload `fall_of_wickets_internal_count` | 594 / 0 | ✅ shipped — `_unwitnessed` placeholder FOW rows are hidden from live WS/UI payloads until enriched, while internal placeholder count remains available for cricket physics. |
| **P2** | Stratified sampler bucket coverage (M-2) | `select_corpus_candidates.py`, **`scripts/select_combined_scout_corpus.py`** | `[BUCKET-COVERAGE]` | 929 / 0 | ✅ shipped — subset buckets in **`corpus_candidates.json`**; **phase×innings** combined corpus JSON + **`UNDOCUMENTED_ZERO`** / **`--strict`** (**`m2_combined_corpus_sampler.md`**). |
| **P2** | CLOSEUP frame persistence | `test_pipeline.py` CLOSEUP branch | `debug_frames/f{frame}_closeup.jpg` | 594 / 0 | ✅ shipped — closeup short-circuit frames are now persisted for post-run visual audit. |
| **P2** | Element-checker stale header cleanup | `element_checker.py` | dynamic banner from `CB_LIVE` | 594 / 0 | ✅ shipped — live checker banner no longer hardcodes the old DC-vs-RCB match label. |
| **Path B** | Striker self-collision cutover completion | `test_pipeline.py` active-slot helpers/callsites | `[STRIKER-SM-CUTOVER]` | 594 / 0 | ✅ shipped — SM + `sb._inn` lockstep for legacy slot writes; **live extended**: **36** cutover firings on PBKS-vs-RR log through ~22:12 IST. |
| **SCORER** | Active-batter / dismissed-row filtering | `test_pipeline.py` `_scorer_batter_update_allowed()`, `_scorer_batter_row_is_dismissed_resurrection()` | `[SCORER-ACTIVE-GATE]`, `[SCORER-INVARIANT-FILTER]`, `[SCORER-DISMISSED-RESURRECT]` | 594 / 0 | ✅ shipped — witnessed-out and non-witnessed resurrection paths filtered before `update_batter()`; **live** `pipeline-2026-04-28-pbks-rr-live.log`: **2** `[SCORER-ACTIVE-GATE]`; invariant/resurrect **0** in that analyzer run. **Post-restart slice (~22:19 IST):** **5** + **2** respectively — see **Post-restart validation**. |
| **Audit refinement** | Role-flip status gate + SM-first auto-dismiss | `eyes/scoreboard.py`, `test_pipeline.py` | `[STRIKER-STATUS-GATE]` | 594 / 0 | ✅ shipped — `update_batter()` refuses striker/non_striker role flips unless the card is currently batting, and wicket auto-dismiss tests pin SM striker preference over stale `sb._inn`. |
| **POISON-RECAL** | Poison streak → `ScoreManager.full_reset` | `test_pipeline.py` | `[POISON-RECAL]` | 594 / 0 | ✅ shipped + **live-validated post-restart** — SM log shows `reason=full_reset:poison_recal_consensus` (**3** in ~16 min slice; pairs with `[POISON-RECAL]`). Legacy **`pipeline-2026-04-28-pbks-rr-live.log`** had **7** WARNs without `full_reset` substring (**older binary**). |
| **State recovery** | Phase 2 mutation (staged, default off) | `test_pipeline.py` `STATE_RECOVERY_PHASE_2_ENABLED`, `_apply_state_recovery_phase2_mutation` | `[STATE-RECOVERY-OVERRIDE]` | 594 / 0 | ⏳ **staged** — flag **False** in repo; overrides **0** on live log. |

**Validation**:
- `python -m py_compile files/test_pipeline.py files/eyes/scoreboard.py files/test_recent_fixes.py files/analyze_match_telemetry.py files/select_corpus_candidates.py files/scripts/select_combined_scout_corpus.py files/element_checker.py`
- `files/test_recent_fixes.py`: re-run `just test` for current PASS/FAIL totals (includes POISON-RECAL, Path B lockstep, SCORER filters, Phase 2 harness, PBKS replay telemetry block); omit Groq client test unless `--run-groq`.
- `analyze_match_telemetry.py --log ../logs/pipeline-2026-04-27-dc-rcb-live.log --report-bundle-bc --fix-validation-only` runs cleanly; historical log shows zero new tags because it predates these implementations, so replay/live validation remains the positive-fire path.
- `analyze_match_telemetry.py --log ../logs/pipeline-2026-04-28-pbks-rr-live.log --report-all-fixes --report-bundle-bc` (2026-04-28): see **Live validation — PBKS vs RR** and **(extended)** above.

### Live validation — PBKS vs RR (2026-04-28, match 151943)

**Log**: `logs/pipeline-2026-04-28-pbks-rr-live.log`.  **Monitoring checkpoint**
2026-04-28 **~20:16 IST** (analyzer window **19:27:49 → 20:16:31**, ~48.7 min; log grew **~11.1k → ~12.9k** lines over a 6‑minute tail watch).  **Tail through ~22:12 IST (~164 min)** is summarized in **Live validation — PBKS vs RR (extended)** above (`[WS-SLOT-INVARIANT]` **387**, Fix 12 **4** releases, `[POISON-RECAL]` **7**, etc.).

| Fix / tag | Result | Evidence |
|-----------|--------|----------|
| **(14) Score regression hard block** | ✅ live-validated | **F169** `Score regression rejected: 4→0` |
| **Fix 17 Path D** `[WS-COLD-START-GATE]` | ✅ live-validated (timeout) | **F125** `OPEN` (cold-start suppression path) |
| **Path B** `[STRIKER-SM-CUTOVER]` | ✅ live-validated (ongoing) | **F219** (over-change) + **14 total** fires through **F336+** (post-change churn) |
| **(17B) `[BOWLER-TEAM-OVER-CONSENSUS]`** | ✅ live-validated | **F1028** `20:08:20` accelerated accept (wrong-bowler recovery class) |
| **(17B+)** `[BOWLER-CONSENSUS-INCONSISTENT]` / override | ⌛ not observed | **0** in log — no vanilla 3-frame flip with spell/strip ball clash in window (or pipeline binary predates ship; either way safe silent) |
| **(6) `[BATTER-NORMALIZE]`** | ✅ live-validated | **5** fires (e.g. **F500**, **F542**, **F1195** — surname ghost `SINGH` paired with **Prabhsimran Singh**) |
| **(17A) `[BOWLER-BATTER-GATE]`** | ✅ live-validated | **14** fires (e.g. **F306**, **F708–709**) |
| **Fix 12** runs reject / release | ✅ active | **18** `[RUNS-REJECT-STREAK]` + **2** `[RUNS-REJECT-RELEASE]` (Prabhsimran Singh stuck-window releases **F315**, **F666**) |
| **Fix 10** `[POST-WICKET-ROTATION]` | ⚠️ partial | **2** fires in window — bundle report still lists other tags as REVIEW; tune per-wicket collision separately |
| **Fix 18 L2/L3** | ✅ active | **6** `[BAT-SUM-RECONCILER]` + **1** `[CAP-RESET-LAST-ADVANCE]` (**F318** Priyansh Arya) |
| **Fix 8+ / info panel (adjacent)** | ✅ prior slice | **F259** DETAIL; `scorer_changes=[]` on stats graphic |
| **Poison / bad-strip path** | ✅ prior slice | **F184** / **F187** class bounded recovery |
| **(19)** SM false 0-0 graphic gate | ⌛ zero-fire | No `[SM] cold-start zero candidate rejected…` in bundle tally (OK if no graphic false seed) |
| **(7)(13)(15)(16)(18)(21)(22)** WS slot invariant, innings-2 reset, etc. | ⌛ partial vs full log | **Fix 13** propagate **0**; **`[WS-SLOT-INVARIANT]`** (*Fix 18*) was *zero in this short window* — **extended** reports **387** in full log; **SM-INNINGS-2-RESET**, **OVER-RESYNC**, **ALL-OUT-AUTHORITY** still **0** in analyzer |

**Next action (P0)**: Same log or successor through **more wickets**, **innings break**, **all-out**, and any **mid-innings recovery** to clear remaining REVIEW rows in `--report-bundle-bc`. **`(17B+)`** mismatch telemetry validates after deploy or on a replay that forces plain-consensus flip under wrong overs. **P1**: CB HTML/API lag vs strip for bowler parity — not proof of **(17B+)** until strip disagrees.

---

## Changes shipped today (2026-04-28, Bundle B + clustered Bundle C)

Implemented the clustered Bundle B/C pass without editing the plan file:
admission hardening, mid-innings recovery hardening, physics-bound
consensus, and final WS slot hygiene.  Deferrals remain unchanged:
State Recovery Phase 2 mutation.

| # | Name | Files | Telemetry | Tests | Status |
|---|------|-------|-----------|-------|--------|
| **6** | Rinku/SINGH extracted-batter normalization | `test_pipeline.py` `normalize_extracted_batters()` | `[BATTER-NORMALIZE]` | 512 / 0 | ✅ shipped — drops surname-only ghost rows like `SINGH None(None)` when paired with canonical `Rinku Singh`, and merges duplicate canonical keys. Historical LSG-vs-KKR logs contain the fixture window but predate the new tag; use replay for positive-fire validation. |
| **16** | Fresh new-batter balls admission gate | `eyes/scoreboard.py` `update_batter()` | `[NEW-BATTER-BALLS-GATE]` | 512 / 0 | ✅ shipped — caps first reads for newly admitted batters by balls since admission plus grace, preventing `0(0) → 0(16)` from becoming monotonic sticky state. |
| **17A** | Bowler identity admission guard | `test_pipeline.py` `filter_bowler_batter_row_contamination()` | `[BOWLER-BATTER-GATE]` | 512 / 0 | ✅ shipped — suppresses bowler updates sourced from active batting rows or incomplete bowler-figure shapes. `(17)` Sub-bug B recovery/consensus for stale wrong-bowler windows remains deferred. |
| **19** | Mid-match false `0-0` cold-start gate | `score_manager.py` | `[SM] cold-start zero candidate rejected as contextual graphic` | 512 / 0 | ✅ shipped — rejects contextual DRS/review/full-scorecard/interview `0-0 (0.0)` candidates without valid player/bowler shape. |
| **20** | Mid-innings partnership anchor hardening | `score_manager.py` | payload partnership `runs=None, balls=None` until anchor | 512 / 0 | ✅ shipped — mid-innings recovery backstages partnership instead of displaying team score as partnership; first post-recovery legal ball establishes anchor. |
| **21** | This-over cursor resync after recovery | `eyes/this_over.py`, `test_pipeline.py` | `[OVER-RESYNC]` | 512 / 0 | ✅ shipped — when SM accepts a mid-innings cold-start/recovery state, `ThisOverManager` aligns to accepted team over and clears stale saturated buffers. |
| **22** | Final-wicket/all-out authority + lock | `eyes/scoreboard.py`, `test_pipeline.py` | `[ALL-OUT-AUTHORITY]` | 512 / 0 | ✅ shipped — at `wickets == 9`, dismissal/innings-break evidence can promote to 10 without a clean `75/10` strip; all-out lock rejects contextual wicket regressions until innings transition. |
| **14** | Team-score regression hard block | `eyes/scoreboard.py` | `Score regression rejected: old→new` | 512 / 0 | ✅ shipped — normal-play score regressions such as `36→35` are hard-blocked unless a separate reset/correction authority exists. **Live**: PBKS-vs-RR 2026-04-28 **F169** `4→0`. |
| **18** | Final WS active-slot invariant | `test_pipeline.py` `enforce_ws_slot_invariant()` | `[WS-SLOT-INVARIANT]` | 512 / 0 | ✅ shipped — final payload projection repairs duplicate striker/non-striker slots from active batting membership or clears the duplicate slot. |
| **harness** | Bundle B/C analyzer signatures | `analyze_match_telemetry.py` | `--report-bundle-bc` | 512 / 0 | ✅ shipped — analyzer now counts all new positive-fire signatures and reports zero-fire gaps. Historical DC-vs-RCB and LSG-vs-KKR logs currently show zero new tags because they predate this deployment; replay fixtures are needed for stronger pre-deploy validation. |

**Validation**:
- `python -m py_compile test_pipeline.py eyes/scoreboard.py eyes/this_over.py score_manager.py test_recent_fixes.py analyze_match_telemetry.py`
- `test_recent_fixes.py`: **512 PASS / 0 FAIL**
- Cursor lints: no errors on edited files
- `analyze_match_telemetry.py --report-bundle-bc` ran against
  `pipeline-2026-04-27-dc-rcb-live.log` and
  `pipeline-2026-04-26-212408-lsg-kkr-fixes-13-18-deploy-v7-vis-team-gate.log`.
  Both report zero new positive-fire tags, expected for pre-deploy logs;
  this is a replay-validation gap, not a failed guard.

---

## Changes shipped today (2026-04-26, LSG-vs-KKR ship + monitor day)

Compact catalog of every fix landed today, with telemetry
signature, scope, and test count.  Use this as the "what
changed since yesterday" reference; detailed reasoning lives in
the per-snapshot sections below.

| # | Name | Files | Telemetry | Tests | Status |
|---|------|-------|-----------|-------|--------|
| **9a** | AUTO-SWAP innings-1-total injection | `test_pipeline.py` | `[AUTO-SWAP-TARGET] target=N source=innings_1_total` | passing | ✅ shipped + **1 fire** at F686 (target=157 set on innings transition) |
| **9b** | AUTO-SWAP target-from-Scout fallback | `test_pipeline.py` | `[AUTO-SWAP-TARGET] source=scout_visible_target` | passing | ✅ shipped — correctly silent (9a did the job) |
| **10** | Post-witnessed-FOW slot rotation | `eyes/scoreboard.py` `_post_witnessed_dismissal_slot_rotation` | `[POST-WICKET-ROTATION]` | passing | ⚠️ shipped — **4 fires / 8 wickets**, collision rate **14.8/wkt** vs **72.4/wkt** baseline (~5x improvement, but residual cases above strict <10/wkt target — likely same `_unwitnessed`-only path as P0 (7), see below) |
| **11** | EXTRAS-INF admission gate (Layer 1) | `test_pipeline.py` `apply_scorer_decision` | `[EXTRAS-INF-GATE]` | 305 / 0 | ✅ shipped + **25 fires** end-of-day (heavy phantom-admission defence in death overs; F1377 `excess=10` strip-misread caught) |
| **12** | Runs-monotonic rejection-consensus release (Layer 4) | `eyes/scoreboard.py` `update_batter` | `[RUNS-REJECT-STREAK]`, `[RUNS-REJECT-RELEASE]` | passing | ✅ **VALIDATED** — **49 STREAK + 3 RELEASES** (Badoni F2453 `runs=0/cur=7`; Himmat F2864 `runs=6/cur=16`; +1) — first-ever Layer 4 production firings |
| **13** | Fix-10 Path D extension (placeholder→witnessed card propagation) | `eyes/scoreboard.py` `_post_witnessed_dismissal_slot_rotation` Case 5 | `[POST-WICKET-CARD-PROPAGATE]` | 375 / 0 | ⏳ shipped — **0 fires across 8 witnessed wickets**: this match's wickets all routed via `_auto_dismiss_for_new_batter` (Fix 10 fired directly) or stayed `_unwitnessed` permanently (P0 (7) gap). Awaits a future match for its specific code-path trigger. |
| **14** | Cricket-physics balls-ceiling gate | `test_pipeline.py` `apply_scorer_decision` | `[BALLS-CEILING-GATE]` | 384 / 0 | ✅ shipped — correctly silent (no impossible balls counts on this clean match) |
| **15** | Score-side admission gate (Layer 1.5) — **cap + floor** | `test_pipeline.py` `apply_scorer_decision`: unexplained advance gate + **`bat_sum+extras` floor** (cold-start / AUTO-SWAP suppress / `innings_transition_reset`); `analyze_match_telemetry.py` `FIX15_SCORE_INF` + **`FIX15_SCORE_INF_FLOOR`** | `[SCORE-INF-GATE]` | 614 / 0 | ✅ **floor shipped 2026-04-28** — complements Fix 11 (batter-side); phantom +N quartet **Layers 1 + 1.5** both score paths covered |
| **16** | SM scalar-field reset on innings-2 transition | `score_manager.py` new `set_innings_2()` | `[SM-INNINGS-2-RESET]` | 415 / 0 | ✅ shipped + **1 fire** at F688 (`reason=wickets_regressed`) — **but coverage gap surfaced: pipeline AUTO-SWAP path doesn't call SM.set_innings_2 — see (8) below** |
| **17 Path A** | Pre-match-graphic gate (cold-start) | `test_pipeline.py` | `[PRE-MATCH-GRAPHIC-GATE]` | 429 / 0 | ✅ shipped — **required 5 hotfixes during deployment**, see "Fix 17 ship-day hotfixes" below; correctly silent post-Hotfix-5 (no incorrect team commits observed) |
| **17 Path D** | WS cold-start gate | `test_pipeline.py` `_ws_cold_start_gate_check`, `broadcast_state` | `[WS-COLD-START-GATE]` open / suppress | 429 / 0 | ✅ shipped — **1 OPEN event** at F39 (timeout path; cold-start suppression worked) |
| **18 L2** | Bat-runs reconciler detection | `eyes/scoreboard.py` `validate_state_consistency` | `[BAT-SUM-RECONCILER]` | 441 / 0 | ✅ shipped + **3 fires** (Mukul Choudhary period F2832–F2837, `excess=8`) — Layer 2 detection working, divergences caught and held below L3 threshold |
| **18 L3** | Capping-batters reset (Path C hybrid) | `eyes/scoreboard.py` `validate_state_consistency`, `update_batter` `_last_runs_advance` | `[CAP-RESET-LAST-ADVANCE]` | 441 / 0 | ✅ shipped — correctly silent (excess<10 throughout, conservative behaviour as designed) |
| **Dual-broadcaster Path A** | Canonical WS emit boundary | `test_pipeline.py`, `test_recent_fixes.py` | regression: no `ws_payload = _sm_result` direct emit | 446 / 0 | ✅ **SHIPPED-pending-validation** — every WS frame now routes through `build_full_payload`; SM remains compute/event feeder for `ball_event` + `_wire_override`. Collapses P0 (4), P0 (5), P0 (10), and materially reduces P1 (8)/(9). Validate against LSG-vs-KKR F1009–F1053 and innings-transition F686–F688. |
| **Wire overs parser** | Fractional cricket-over strings in wire commentary | `wire.py`, `test_recent_fixes.py` | `comm_wire=8.1: ...`; no `ValueError` on `"X.Y"` overs | 469 / 0 | ✅ **SHIPPED-validated live** — fixes repeated `ValueError: invalid literal for int() with base 10: '6.5'` crashes from DC-vs-RCB. Live restart passed fractional overs `7.5`, `8.1`, `8.3` and emitted wire commentary without crashing. |
| **(harness)** | Telemetry analyzer extended for Fixes 13-18 | `analyze_match_telemetry.py` | regex patterns `FIX13_*` … `FIX18_*` + `--report-13`…`--report-18` + `--report-all-fixes` | n/a | ✅ shipped — produced the Fix-10 zero-fire finding that triggered Fix 13 spec; used end-to-end across the LSG-vs-KKR match for live validation |

**Final test suite**: 446 PASS / 0 FAIL after Dual-broadcaster Path A
(previously 443 PASS / 0 FAIL for Fixes 13-18).

**End-of-monitoring tally**: **8 fixes positively fired in production**
(9a, 10, 11, 12 incl. RELEASES, 16, 17 Path D, 18 L2, plus harness),
**4 correctly silent** (9b, 14, 15, 17 Path A, 18 L3), **1 awaiting trigger**
(13 — needs `_unwitnessed→_witnessed` upgrade pattern in a future match).
Full session details in `files/docs/session_summary_2026-04-26.md`.

**New backlog items filed today** from production
observation (full details below):
- (6) **P1 / SHIPPED-pending-replay-validation** — Extractor splits
  "Rinku Singh" into RINKU + SINGH ghost batter.  Shipped
  `normalize_extracted_batters()` on 2026-04-28 to resolve/merge
  canonical batter rows and drop surname-only ghost fragments.  Historical
  LSG-vs-KKR logs contain the fixture but predate `[BATTER-NORMALIZE]`;
  replay through patched code remains the stronger validation step.
- (7) **P0 / SHIPPED-pending-live-validation** — Fix 13
  placeholder-FOW coverage gap (live UX damage observed: 56+ s of
  dismissed-batter as "still batting").  Local Path B regression is in;
  still needs a live WICKET event with known dismissed batter.
- (8) **P1 / SHIPPED-pending-validation** — Fix 16 coverage gap:
  pipeline AUTO-SWAP now invokes `score_mgr.set_innings_2()` alongside
  `scoreboard.set_innings_2()`, using the injected target and canonical
  new batting team from AUTO-SWAP.
- (9) **P1 / SHIPPED-validated live** —
  `WS-PROJECTION-FALLBACK` status-check hardening.  Fallback now
  resolves `sb._inn` names through `batting_card` and requires
  `status == "batting"` before projecting into WS payload.  DC-vs-RCB
  restart window F58-F92 repeatedly used fallback for current active
  batters only (`Kuldeep Yadav`, `Abishek Porel`); after Kuldeep's W9
  dismissal, fallback no longer resurrected him.
- (10) **P0 / SHIPPED-pending-validation by Dual-broadcaster
  Path A** — `over_history` dual-writer over-key/shape collision:
  balls "stuffed" into wrong over (over-3 → over-4 transition observed
  live at 21:53:14 IST).  Validate against F1009–F1053.
- (11) **P1** — `this_over` cold-start placeholder persistence:
  first delivery can display as a dot-like placeholder, then degrade to
  `?` once the next observed ball appends.  DC-vs-RCB 2026-04-27
  fixture: F184 `Joined at 0.1, pre-filled 1 balls as '?'`; F188
  wicket appends, yielding `['?', 'W']` instead of `['.', 'W']`.
- (12) **P1 / SHIPPED-pending-validation** — standings-row
  contamination of score field:
  multi-row score strip interleaves canonical score with contextual
  standings row (`DC 7 STANDINGS RCB 2`).  DC-vs-RCB 2026-04-27
  restart fixture F2 committed `score→7` from `STRIP: DC 7-1 (0.3)
  | DC 7 | STANDINGS RCB 2`, displaying `DC 7-1` instead of the
  canonical `DC 1-1`.  Added `[STANDINGS-ROW-GATE]` to strip score,
  wickets, and overs from contextual standings/table/position rows.
- (13) **P0 / SHIPPED-validated live** — `wire.py` fractional-over
  crash: `_wire_override` passed `snap["overs"]` as cricket-over strings
  like `"6.5"`, while `format_wire()` did `int(overs)`.  Fixed by
  parsing cricket-over strings without base-10 arithmetic; regression
  added.  Live DC-vs-RCB validation emitted wire commentary at `8.1`,
  `8.3`, `13.2`, `13.5`, `14.2`, `14.3`, `15.4`, and `15.5` with no
  crash.
- (14) **P0 / SHIPPED-live-validated (2026-04-28 PBKS-vs-RR)** — team-
  score regression
  consensus can accept lower score
  in normal play.  DC-vs-RCB 2026-04-27 20:18 IST: pipeline held
  `36-6 (8.1)` after a wide/extras path, repeated strip reads of
  `35-6 (8.1)` reached consensus and committed `score: 36 -> 35`.
  This creates visible score/CRR rollback; extras rollback then refused
  because the last token was already `.` rather than the earlier `Wd+1`.
  Shipped 2026-04-28: `Scoreboard.set("score", ...)` now hard-blocks
  normal-play score regressions unless a separate reset/correction
  authority exists; generic consensus can no longer override monotonic
  score physics.  **Live**: `pipeline-2026-04-28-pbks-rr-live.log` **F169**
  `Score regression rejected: 4→0`.
- (15) **P1 / SHIPPED-pending-live-validation** — mid-innings cold-start FOW placeholders dominate UI.
  Joining at `wickets=6` pre-populates six `_unwitnessed` FOW entries;
  element checker reports `FOW_UNKNOWN: 6` continuously.  Honest but
  visually noisy.  Shipped 2026-04-28: `project_fow_for_payload()` hides
  `_unwitnessed` placeholder FOW rows from live WS/UI payloads until
  enriched, while retaining `fall_of_wickets_internal_count` for cricket
  physics.
- (16) **P0 / SHIPPED-pending-live-validation** — new-batter balls
  corruption becomes self-protecting.
  DC-vs-RCB 2026-04-27 fixture: after David Miller's wicket, Kyle
  Jamieson was correctly admitted at `0(0)` around F220, but F309 read
  `Jamieson 0(16)` and the tracker accepted `balls: 0 -> 16`
  (`post-event immediate, grace=1`).  From then on, correct reads
  `0(0)`, `1(1)`, and `7(2)` were rejected as impossible balls
  regressions (`17 -> 1`, `17 -> 2`), so the UI showed Jamieson as
  `1(17)` / `7(19)` while Cricbuzz had `1(1)` / `7(2)`.
  Root cause: the balls-regression guard is only protective after the
  bad value is admitted; the admission path trusts a large balls jump
  for a newly admitted batter because team score/overs advanced by one
  ball.  Shipped 2026-04-28: fresh newly admitted batters now carry an
  admission frame/team-balls anchor; early balls-faced reads above balls
  since admission plus grace are rejected via `[NEW-BATTER-BALLS-GATE]`
  before the normal monotonic guard can make the bad value sticky.
- (17) **P1 / SHIPPED-pending-live-validation** — bowler identity
  can be sourced from batting row /
  contextual strip, producing long wrong-bowler windows.  DC-vs-RCB
  2026-04-27 fixture: after over 10, ground truth bowler was Suyash
  Sharma, while UI remained on Rasikh Salam Dar, then changed to
  Romario Shepherd from an active strip (`Shepherd 0-9 (1)`) with
  `[LATENCY-HIGH] bowler card took 41 frames to update`.  Several
  frames also parsed `Jamieson` as `ext_bowl` from a batting row
  (`BOWL: Jamieson 0-0`), guarded only because Jamieson was not in the
  bowling card.  Root cause: bowler extraction still accepts
  trailing/contextual names when the strip is incomplete or ambiguous,
  and bowler-change consensus has no Cricbuzz-like team/over
  consistency check to prefer the actual new bowler.  Shipped 2026-04-28
  Sub-bug A: bowler admission now suppresses names that also parse as
  active batters or lack complete bowler-figure shape
  (`[BOWLER-BATTER-GATE]`).  Shipped 2026-04-28 Sub-bug B:
  `[BOWLER-TEAM-OVER-CONSENSUS]` promotes a candidate bowler after two
  reads when their individual-over ball count matches the team over and
  the current bowler is stale/inconsistent, reducing long wrong-bowler
  windows after over changes.  **Sub-bug B extension (2026-04-28,
  STAGED telemetry):** vanilla 3-frame identity flips additionally
  require spell ball-in-over alignment with the team strip, else
  `[BOWLER-CONSENSUS-INCONSISTENT]` (repeated frames →
  `[BOWLER-CONSENSUS-INCONSISTENT-OVERRIDE]`).
- (18) **P1 / SHIPPED-pending-live-validation** — same-player active-slot
  self-collision still reaches
  WS after post-wicket/new-batter churn.  DC-vs-RCB 2026-04-27 fixture:
  after Jamieson admission, multiple DETAIL rows show
  `AFTER_striker=Abishek Porel` and `AFTER_non_striker=Abishek Porel`;
  element checker then alternates between missing striker and swapped
  striker/non-striker.  Root cause: write-time `STRIKER-COLLISION`
  blocks some fresh writes, but existing duplicated slot state can
  survive into payload projection when the bad write comes from a
  direct slot assignment path rather than `update_batter`'s guarded
  writer.  Proposed fix: add a final scoreboard-slot invariant before
  WS payload build: if striker and non_striker are equal, keep the
  batter with the latest striker evidence and clear/reconstruct the
  other slot from active batting membership.  Shipped 2026-04-28:
  `enforce_ws_slot_invariant()` runs at the WS payload boundary and
  repairs/clears duplicate striker/non_striker slots via active batting
  membership (`[WS-SLOT-INVARIANT]`).  Reproduced again after
  Kuldeep Yadav's W9 at restart F380/F387: the old wicket cleanup path
  upgraded W9 and cleared Kuldeep, then DETAIL still emitted
  `AFTER_striker=Abishek Porel` and `AFTER_non_striker=Abishek Porel`.
- (19) **P1 / SHIPPED-pending-live-validation** — mid-match cold-start can
  accept a false `0-0`
  pre-match/DRS graphic before recovering.  DC-vs-RCB 2026-04-27
  restart fixture: after restart at the real score `63-8`, frames F6-F10
  parsed `DC 0-0 (0.0) | Shaw/Kuldeep | Khalid Ahmed` during DRS/review
  graphics and seeded `0-0`.  Real `63-8` / `65-8` reads were then
  treated as poisoned score jumps until `[POISON-STREAK]` reached 5/5
  and `[SM] FORCE_COLD_START_RECALIBRATION` fired at F56.  Recovery
  worked, but the UI spent roughly three minutes showing `0-0` /
  wrong active batters.  Root cause: cold-start accepts a zero-score
  pre-match-shaped graphic even when surrounding frames show a live
  mid-innings score and the bowler/name shape is invalid for the match.
  Shipped 2026-04-28: ScoreManager rejects `0-0 (0.0)` cold-start
  candidates when the vision/action text has DRS/review/full-scorecard/
  interview graphic markers and the scorecard lacks valid player/bowler
  shape (`[SM] cold-start zero candidate rejected as contextual graphic`).
- (20) **P1 / SHIPPED-pending-live-validation** — partnership display
  anchors from zero after mid-innings
  recovery.  DC-vs-RCB 2026-04-27 restart fixture: once score recovered
  to `65-8` at F59, parity monitor reported `live.partnership ui=65`
  while Cricbuzz had a new stand of `3-5` runs; later UI showed `67`
  while GT remained `5`.  Root cause: after a cold-start/recalibration
  at wickets > 0, the partnership module anchors the active pair at
  team score 0 / balls 0 rather than treating the current pair as an
  already-in-progress stand.  Proposed fix: on mid-innings cold-start,
  initialize partnership from active batter deltas when both active rows
  are known, or hide/backstage partnership until the first post-recovery
  legal delivery establishes a reliable anchor.  Shipped 2026-04-28:
  mid-innings recovery now backstages partnership (`runs=None`,
  `balls=None`) until the first post-recovery legal delivery anchors the
  stand.
- (21) **P1 / SHIPPED-pending-live-validation** — this-over rollover cursor
  can remain stuck after
  mid-innings recovery.  DC-vs-RCB 2026-04-27 restart fixture: after
  recovering at `65-8 (13.1)`, `ThisOverManager` kept appending to the
  same current-over buffer across over boundaries; by F380/F387 it held
  12 tokens while team overs were `15.4/15.5`, and
  `on_ball_event refused: this_over already has 12 tokens
  (>= MAX_OBSERVED_THIS_OVER_LEN)`.  Root cause: the over cursor still
  references recovery-time over 0/held state (`Over-jump rejected:
  0 -> 15`) even after scoreboard/scorer have accepted live overs, so
  legal events are dropped instead of rolling the buffer.  Proposed fix:
  when a mid-innings recovery is accepted by consensus/recalibration,
  resync ThisOverManager's current/held cursor to the accepted team
  over and clear/backstage pre-recovery observed tokens rather than
  preserving a cross-over buffer.  Shipped 2026-04-28:
  `ThisOverManager.resync_to_over()` is invoked when ScoreManager warms
  from a mid-innings cold-start/recovery state (`[OVER-RESYNC]`).
- (22) **P0 / SHIPPED-pending-live-validation** — all-out / final-wicket
  detection coverage gap.
  DC-vs-RCB 2026-04-27 restart fixture: Cricbuzz showed `75/10 in
  16.3` with `LAST WKT: Abishek Porel b Josh Hazlewood 30(33)`, but
  the pipeline remained at `75-9 (16.3)` with Abishek Porel still
  active.  AUTO-SWAP never fired because the upstream all-out
  precondition (`wickets == 10`) was never reached; this does **not**
  invalidate the Bundle A `(8)` `score_mgr.set_innings_2()` hook, which
  remains correct but unexercised in production.

  Diagnostic result (2026-04-28): searching
  `pipeline-2026-04-27-dc-rcb-live.log` for `BALL.*WICKET`,
  `INVARIANT`, `POISON-STREAK`, `FRAME_POISONED.*9.*10`,
  `wickets.*10`, `75/10`, `75-10`, and AUTO-SWAP markers found no
  `75/10`, no proposed `wickets→10`, no `9 -> 10` rejection, no
  `ALL OUT`, and no AUTO-SWAP attempt near the final wicket.  The log
  does show a dismissal signal (`[DISMISSAL-HINT] action says 'bowled'`
  at F458 and `[BROADCAST] Dismissal mode: bowled` at F460), but those
  were on poisoned graphic frames (`DC 0-0`, `DC * (0-0)`) rather than a
  clean canonical `75/10` strip.  Subsequent innings-break/context rows
  produced `75-3`, `75-0`, `75-2`, `75-6`, and phase-summary shapes; the
  generic wickets-regression consensus eventually logged
  `[WICKETS-REGRESS] Accepting 9→2 after 3 consecutive frames...` at
  F464.

  Current classification: mechanism #1/#3, not mechanism #2.  There is
  no evidence that the pipeline attempted and rejected a clean `9→10`
  update.  The likely gap is broadcast-side coverage or missing
  alternate trigger: the final wicket was represented by dismissal /
  celebration / innings-break graphics without a clean strip that the
  pipeline could promote to all-out.

  Shipped 2026-04-28: when current wickets are 9, final-dismissal /
  innings-break evidence can promote to 10 via `[ALL-OUT-AUTHORITY]`
  without needing a clean `75/10` strip.  An all-out lock then rejects
  contextual wicket regressions from phase-summary/context rows until a
  canonical innings-2 transition source fires.

**Pattern observation**: several issues filed today trace back to split
state authority at emit, admission, or recovery time.  Dual-broadcaster
Path A has shipped for the WS payload path, and the 2026-04-28 Bundle B/C
pass now hardens the upstream admission/recovery surfaces that remained:
new-batter stat admission, bowler-row contamination, false zero-score
cold-starts, partnership anchoring, this-over resync, final-wicket
authority, score monotonicity, and final WS slot invariants.  Remaining
work is validation-heavy: replay historical production fixture windows
through patched code and live-monitor the next innings transition.

---

## Snapshot — 2026-04-27 19:31 IST DC-vs-RCB first-over this_over placeholder downgrade

The UI briefly appeared to show the first delivery as a dot, but when
the second delivery became a wicket the first circle changed to `?`.
The log shows this was not a W-overwrite bug: the first delivery was
already stored as an unknown placeholder before the wicket arrived.

### (11) `this_over` cold-start placeholder persists when first legal delivery is missed

**P1 — user-visible current-over fidelity bug.**  This is separate
from Dual-broadcaster Path A.  The canonical WS payload is now using
`ThisOverManager`, but `ThisOverManager` itself can seed `?` placeholders
when the pipeline joins or confirms state mid-over before the ball-event
detector has emitted the missing delivery.

DC-vs-RCB 2026-04-27 first over:

| t (IST) | frame | state | `this_over` evidence |
|---|---|---|---|
| 19:31:44 | F184 | DC 0-0 (0.1) | `Joined at 0.1, pre-filled 1 balls as '?'`; `AFTER_this_over=['?']` |
| 19:31:57 | F188 | DC 0-1 (0.2) | `[BALL ✓] WICKET`; `[THIS-OVER] Ball WICKET appended`; `AFTER_this_over=['?', 'W']` |
| 19:35:39 | restart F12 | DC 1-1/7-1 drift window | first actual observed `Ball DOT` appears later and appends as `.`, proving observed dots are preserved once BED emits them |

**Root cause:** `ThisOverManager.initialize_mid_over()` and
`get_display()` both materialize missing legal deliveries as `?`
based on `team_overs`.  That is correct for mid-over joins, but in a
live first-over cold-start it means a missed first `DOT` event becomes a
sticky placeholder.  When the wicket arrives, `on_ball_event()` appends
`W` after the placeholder; no later broadcast override can safely infer
that the earlier `?` was a dot unless the broadcast `THIS OVER` strip
was read cleanly.  The apparent "dot → ?" flip is therefore a
placeholder exposure problem, not a second-ball mutation of a confirmed
dot.

**Likely fix path:** add a narrow backfill rule for zero-run legal
placeholders: when score is unchanged, wickets/overs advance by one
legal ball, and the previous slot is `?`, promote that previous `?` to
`.` before appending the new event.  Keep this bounded to score-neutral
legal deliveries so real unknown run/extras gaps are not fabricated as
dots.

**Validation fixture:** DC-vs-RCB 2026-04-27 live log
`pipeline-2026-04-27-dc-rcb-live.log`, frames F184-F188.  Expected
post-fix: F184/F188 sequence renders `['.', 'W']` for `0.2` when the
first ball was a score-neutral legal delivery and no broadcast token
contradicts it.

---

## Snapshot — 2026-04-27 19:34 IST DC-vs-RCB standings-row score contamination

The broadcast score banner carried two interleaved rows: the canonical
match score (`DC 1-1 P 0.3`) and a contextual IPL standings annotation
(`DC 7 STANDINGS RCB 2`).  The parser treated the standings value as
score-shaped match data and latched `7` into the score field.

### (12) Standings-row contamination of score field

**P1 — SHIPPED-pending-validation (2026-04-27 Bundle A).**
Same class as the F2461
`THIS OVER:` speed-track ingestion: a broadcast annotation label was
parsed as canonical cricket data.  Different detail: `7` is a plausible
score, so alphabet / physics gates cannot reject it by value shape.

DC-vs-RCB 2026-04-27 restart fixture:

| t (IST) | frame | strip / state evidence |
|---|---|---|
| 19:34:40 | F2 | `STRIP: DC 7-1 (0.3) | DC 7 | STANDINGS RCB 2` |
| 19:34:42 | F2 | extractor: `score=7-1 (0.3)` |
| 19:34:43 | F2 | tracker: `score: initial -> 7`, `wickets: initial -> 1` |
| 19:34:43 | F2 | state: `Delhi Capitals 7-1 (0.3)` |

**Observed failure mode:** row-2 score replacement, not concatenation.
The standings row's `DC 7` contaminated the canonical score read,
while wickets stayed `1` from the top row / first parsed shape.

**Why existing defenses missed it:**

- Fix 11 / Fix 15 are sum-violation oriented; `bat_sum < score` is
  plausible and not rejected.
- Fix 14 balls ceiling is unrelated; wickets happen to remain plausible.
- Runs-monotonic guards do not reject positive score advances.
- The value is cricket-shaped; only semantic context (`STANDINGS`) marks
  it as non-canonical.

**Immediate fix path (Path A):** add a standings/context keyword gate
near the existing info-panel contamination handling.  When a score strip
contains `STANDINGS`, `TABLE`, `RANK`, `RANKINGS`, `POSITION`, or
`IPL POSITION`, reject score/wicket/over extraction from the contextual
row, or discard the whole score extraction if the parser cannot isolate
the top canonical row.  Emit telemetry such as `[STANDINGS-ROW-GATE]`
with the matched keyword and stripped values.

**Fix shipped**: `filter_standings_row_contamination()` strips `score`,
`wickets`, and `match_overs` when the strip text contains standings /
table / rank / position keywords.  It is wired into both the closeup
hybrid extractor path and the main scorer path, adjacent to the existing
INFO-PANEL gate.

**Validation status**: local regression added for the DC-vs-RCB standings
fixture plus a normal-strip no-op test; `test_recent_fixes.py` reports
484 PASS / 0 FAIL.  Live validation requires the next standings graphic
after restart.

**Follow-up path (Path B):** if this pattern recurs with different
labels, add a multi-row semantic consistency check: when multiple
cricket-shaped rows mention the same team with conflicting numbers,
accept only the row consistent with current score/over progression and
ignore contextual rows.

**Validation fixture:** `pipeline-2026-04-27-dc-rcb-live.log` around
restart F2-F3.  Expected post-fix: the standings row is ignored and
`score=1`, `wickets=1`, `overs=0.3` remain canonical.

---

## Snapshot — 2026-04-26 22:00 IST innings-2 over-3 over_history stuffing

**`This Over` UI strip displayed last two balls of completed
over 3 (`1 1`) as if they were the start of over 4** during the
~50 s window between F1030 (over 3 closed cleanly at 17/1 (3.0))
and F1053 (Vaibhav Arora's first ball of over 4 surfaced).
Score-side state was correct throughout; the symptom is purely a
display-layer over-key collision between the dual `over_history`
writers.

### (10) `over_history` dual-writer over-key/shape collision causes "balls stuffed into wrong over"

**P0 — SHIPPED-pending-validation by Dual-broadcaster Path A
(2026-04-27), user-visible "ball-loss + ball-stuffing" pattern.**
Originating mechanism: same dual-broadcaster substrate as P0 (5)
and P1 (8), specialised to the `over_history` scalar.

LSG-vs-KKR 2026-04-26 over 3 → over 4 transition:

| t (IST) | frame | score | overs | scoreboard `this_over` | scoreboard `completed_over` | UI screenshot |
|---|---|---|---|---|---|---|
| 21:52:00 | F1009 | 15-1 | 2.4 | `[. . ? ?]` (4) | — | n/a |
| 21:52:13 | F1012 | 16-1 | 2.5 | `[. . ? ? 1]` (5) | — | n/a |
| 21:52:30 | (between) | 16-1 | 2.5 | `[. . ? ? 1]` (5) | — | `. . ? ? 1 .` (6 slots — last one rendered as empty filler, OK) |
| 21:53:00 | F1030 | 17-1 | 3.0 | `[. . ? ? 1 1]` (6) | `[. . ? ? 1 1]` (over 3 done) | n/a |
| **21:53:14** | (between) | **17-1** | **3.0** | **`[]` (over 4 not started)** | `[. . ? ? 1 1]` | **`1 1 . . . .`** ← **stuffing** |
| 21:53:56 | F1053 | 18-1 | 3.1 | `[1]` (over 4 ball 1) | — | n/a |

**Symptom**: the UI shows `1 1 . . . .` for `This Over` while
score is 17-1 (3.0) and over 4 has not yet had any balls bowled.
The `1 1` are the last two entries of the just-completed over 3.
The first four legitimate balls of over 3 (`. . ? ?`) have been
**lost** from the strip and the last two balls have been
**stuffed** into the front of the over-4 view.

**Why this happens — dual writer to `over_history`**:

1. **`score_manager.py:1715` and `:1903`** write the `list[str]`
   shape:
   ```python
   self.over_history[int(prev.get("overs", 0) or 0)] = list(self.this_over)
   ```
   - Key: `int(prev.overs)` (just-closed over-1 in IPL convention,
     e.g. `int(2.5)=2` means "over 3").
   - Value: flat list of tokens.
2. **`eyes/this_over.py:358` and `:1052`** write the dict shape:
   ```python
   self.over_history[held_int] = {
     "balls": self.this_over.copy(),
     "bowler": ...,
     "runs": ...,
     "wickets": ...,
   }
   ```
   - Key: `held_int` (a different cursor: the *currently-held*
     over rather than the just-closed one).
   - Value: structured dict.

The two writers run on independent state machines (SM owns
`SM.over_history`; ThisOverManager owns its own `over_history`).
At broadcast time both contribute to the same WS payload key
(`state.over_history`), with the dual-broadcaster select logic
in `test_pipeline.py:8110` (`_sm_result is not None and not
score_mgr.shadow`) deciding which writer wins per frame.  The UI
flips between two views of the same key.

**The "stuffing" mechanism** (hypothesis pending source-dive):
- ThisOverManager has a "hold window" at the over boundary
  (line 346 comment: `the hold window is still open`).  During
  hold, new balls *of the next over* are appended to the
  *previous* held over before the boundary commits.  This was
  the comment block's stated bug-fix, but it relies on the
  hold-window being correctly set.
- If the hold-window opens at over-3 close (F1030) but the
  `held_int` cursor hasn't yet advanced when `over_history[3]`
  is queried for "current over" (over 4), the UI may read the
  *same* held over-3 entry as the over-4 entry — explaining why
  the *last two* balls of over 3 (`1, 1`) appear as the *first
  two* of over 4.
- Specifically the empirical pattern (ball 5 = `1`, ball 6 =
  `1` of over 3, then UI shows `1 1` for over 4) matches
  "tail-of-N taken as head-of-N+1" — i.e. the held-over view
  has a 2-ball tail-trim buffer that the UI treats as the
  head of the next over.

**Live UX damage**:
- Confusing strip — fans see two 1s where there should be 0
  balls bowled, then watch them "shift right" as the real
  over 4 arrives, looking like balls are being scored that
  weren't.
- Score field is correct (17-1 (3.0)), so the discrepancy is
  *only* in the per-ball strip, but for the broadcast-comm
  layer this is the most visually-noisy of all the dual-
  writer bugs.
- Window observed: ~50 s on this transition.  Likely repeats
  on every over rollover when ThisOverManager and SM fall out
  of sync on `held_int`.

**Fix shipped**:
- **Dual-broadcaster Path A (2026-04-27)**: direct SM WS emits
  removed from `test_pipeline.py`; every WS frame now routes through
  `build_full_payload()`.  `over_history` is therefore always sourced
  from `ThisOverManager`'s structured dict shape at the emit boundary,
  while SM remains a compute/event feeder.  Regression test prevents
  `ws_payload = _sm_result` from returning.

**Historical fix-path candidates**:
- (A) **Single writer for `over_history`** (~40-80 lines): pick
  ThisOverManager as the canonical source (it has the richer
  shape including bowler), make SM stop writing `over_history`
  entirely and instead query ThisOverManager when it needs to
  populate the WS payload.  Largest scope but fully resolves
  the dual-writer substrate.
- (B) **Shape-canonicalize at WS payload build** (~15-25 lines):
  in `build_full_payload`, when reading `over_history`, prefer
  ThisOverManager's dict shape over SM's list shape; if dict
  is missing for a key, synthesise from list.  Doesn't fix the
  underlying state divergence but eliminates the UI-visible
  flip.
- (C) **Held-window cursor sync** (~10-15 lines): on every over
  rollover, ThisOverManager publishes its `held_int` and
  `current_int` cursors; SM consumes them and aligns its own
  `int(prev.overs)` write-key.  Lightweight but only works if
  the disagreement is a 1-frame phase-lag, not a structural
  fork.
- (D) **Strip rendering: ignore stale held entries** (~5-10
  lines, frontend): when the UI sees `over_history[N]` for
  `N == current_over_int` AND the strip-context shows score-
  overs at the boundary (`X.0` exactly), prefer empty over the
  stuffed-tail entry.  Treats the symptom; does not fix
  backend state divergence.

**Validation status**: SHIPPED-pending-validation.  Re-run against the
fixture below and verify no event-vs-idle shape flip reaches the UI.
Path C remains unnecessary unless validation shows a residual
ThisOverManager cursor issue independent of the dual emit path.

**Production fixture**: LSG-vs-KKR 2026-04-26 F1009 (15-1 2.4)
through F1053 (18-1 3.1).  Specifically F1030 (over-3 close
with `completed_over=['.', '.', '?', '?', '1', '1']`) and the
~50 s window before F1052 surfaces Vaibhav Arora as the new
bowler.  Add to `test_recent_fixes.py` as an integration test
that asserts `over_history[N]` is empty exactly during the
boundary frame after `completed_over` is published for over N.

**Composes with / collapsed by same fix**: P0 (5)
(dual-broadcaster shape collision), P0 (4) (team-name flip), and
P1 (8) (Fix 16 SM-set_innings_2 not invoked from AUTO-SWAP).

---

## Snapshot — 2026-04-26 21:48 IST innings-2 first-wicket monitoring

**Fix 13 coverage gap reproduced on a NEW match within ~1 minute
of innings 2 starting** — strongest empirical evidence yet that
the placeholder-FOW path needs Fix 13's card-propagation logic
extended.

### (7) Fix 13 placeholder-FOW coverage gap manifests as F704-style collision-stuck

**P0 — SHIPPED-pending-validation via Fix 13 Path B (2026-04-27).**
Originating commit: Fix 13 (Path D extension to
`_post_witnessed_dismissal_slot_rotation`).

LSG-vs-KKR 2026-04-26 innings 2, ball 1.1.  Sequence:

- **F775 21:43:42**: Mitchell Marsh dismissed, score advances
  `8/0 → 8/1 (1.1)`.  `[BALL EVENT WICKET]`, `[SM] WICKET
  dismissed=M Marsh`, `[BOARD] [FOW] Placeholder W1: _unwitnessed
  (no fabrication — awaiting real wicket event or CB scrape
  enrichment)`.
- **F775 same frame**: `AFTER_striker=Aiden Markram,
  AFTER_non_striker=Aiden Markram` ← **striker self-collision**
  (both slots latched to Markram because slot rotation tried to
  remove Marsh from non_striker, then upstream re-installed him
  via STRIKER-WRITE).
- **F776–F810** (56 seconds, ~35 frames): `[STRIKER-WRITE] non_striker
  Aiden Markram->Mitchell Marsh` repeats.  WS-PROJECTION-FALLBACK
  fires 21+ times surfacing Marsh from `sb._inn` because he's
  still in `active_batting`.  STATE log still shows
  `Bat: Aiden Markram(6) Mitchell Marsh(2)` for the entire
  window — UI displays the dismissed batter as currently
  batting.
- **F810**: `[DISMISS] 'Mitchell Marsh' missing from extractor
  (streak=1/2) — deferring one frame` — only now does the
  scoreboard start rectifying via the extractor-absence path,
  not via Fix 13.

**Why Fix 13 didn't fire**:
- Fix 13 is invoked from
  `_post_witnessed_dismissal_slot_rotation`.
- That method is called from `_add_fow` when `_witnessed=True`.
- F775's FOW is added with `_unwitnessed` (placeholder; awaiting
  CB-scrape enrichment or witness-stamp upgrade).
- The witness-stamp upgrade may arrive **minutes later**, or
  **never** during the live broadcast (CB enrichment is not
  always reliable).
- Therefore the dismissed batter remains in `active_batting` and
  `batting_card[name].status=batting` for the entire window.

**Live UX damage**:
- 56+ seconds (and counting) of UI showing `Mitchell Marsh(2)`
  as a current batter alongside `Aiden Markram(6)*`, when in
  truth Marsh has walked off and a new batter (Pooran or
  similar) is about to enter the crease.
- WS payload's `non_striker='Mitchell Marsh'` is wrong; UI
  header shows the dismissed batter beside the score.

**Fix-path candidates**:
- (A) **Extend Fix 13 to fire on placeholder add too** (~5-10
  lines): when `_add_fow` writes an `_unwitnessed=True`
  placeholder AND the dismissed-batter name *is* known (e.g.
  from `[SM] WICKET dismissed=X` upstream signal), still call
  `_post_witnessed_dismissal_slot_rotation`.  Requires routing
  the SM-side dismissed name into `_add_fow`.
- (B) **Sibling hook on `wickets++` itself** (~10-15 lines):
  when `update_wickets` increments and a known-batter is
  already in either slot, treat as a dismissal candidate and
  invoke the rotation+propagation hook with that batter.
  Doesn't require waiting for FOW witness stamp.
- (C) **Self-healing collision detection** (~10-20 lines):
  STRIKER-COLLISION counter — when same `non_striker=X`
  rejected via WS-PROJECTION-FALLBACK for >5 consecutive
  frames AND `wickets` recently incremented, force-clear `X`
  from `active_batters` and `batting_card[X].status='out'`.
  Treats the symptom; does not require knowing which witness
  path failed.

**Recommendation**: Path B is bounded and addresses the root
cause (dismissed-batter detection at wicket-increment time,
independent of FOW witness path).  Path A is closer to the
existing Fix 13 architecture but leaves Path C-style bugs
intact when SM also fails to identify the dismissed batter.
Path C is a safety net but doesn't help the first 5 frames
of bad UX.

**Fix shipped**: Path B adds `Scoreboard.apply_known_wicket_increment()`
and invokes it from the WICKET ball-event handler once a concrete
`ball_event["dismissed"]` name is known.  The helper marks the known
dismissed batter `status="out"` and reuses the existing
`_post_witnessed_dismissal_slot_rotation()` invariant immediately,
without fabricating FOW details; `_unwitnessed` placeholders remain
placeholders until a real witness/enrichment fills them.

**Validation status**: local regression fixture added for the
Mitchell-Marsh-style placeholder gap plus source wiring guard;
`files/test_recent_fixes.py` reports 466 PASS / 0 FAIL.  Live
validation still needs the next wicket where the WICKET handler knows
the dismissed batter before the FOW witness stamp arrives.

**Production fixture**: LSG-vs-KKR 2026-04-26 F775
(`[FOW] Placeholder W1`) → F810 (`[DISMISS] 'Mitchell Marsh'
missing from extractor`).  Add to test_recent_fixes.py as
the second test fixture for Fix 13 (alongside the existing
Powell F179→F258 case).

### (8) Fix 16 coverage gap: `score_manager.set_innings_2()` not invoked from pipeline-driven AUTO-SWAP

**P1 — SHIPPED-pending-validation by 2026-04-27 Bundle A.**
Originating commit: Fix 16 (canonical `set_innings_2()` method).
Dual-broadcaster Path A already removed UI damage from stale SM scalars;
Bundle A now also resets SM at the pipeline-driven AUTO-SWAP path.

LSG-vs-KKR 2026-04-26 innings transition (F686 → F688):

- **F686 21:39:57**: pipeline detects auto-swap,
  `[INNINGS-TRANSITION-TELEMETRY] source=set_innings_2
  caller=test_pipeline.py:5857`.  But that callsite only
  invokes **`scoreboard.set_innings_2(_injected_target)`**,
  not `score_manager.set_innings_2(...)`.
- **F688 21:40:02**: SM auto-detects `wickets_regressed`
  (its own state still inn=1/7w, new card 0w) and calls
  `_handle_innings_change`, which routes to canonical
  `SM.set_innings_2(target=None, batting_team='KKR',
  reason='wickets_regressed', archive=False)`.
  - `target=None` because Scout hasn't yet seen "157 NEED" in
    the broadcast graphic.
  - `batting_team='KKR'` because `frame.broadcast_team` was
    misread as KKR on the transition frame (a transient
    pre-match-style strip in the broadcast).
  - This means SM internal state ends innings-2 transition
    with `self.batting_team = 'KKR'` — **wrong direction**.

**Why this slipped Fix 16's net**: Fix 16 enumerated three
SM-internal leaky callsites and the canonical SM-internal
path, all rerouted through `SM.set_innings_2()`.  But the
**pipeline-driven AUTO-SWAP path** at
`test_pipeline.py:5857` calls only `scoreboard.set_innings_2`,
not `score_manager.set_innings_2`.  SM is left to auto-detect
later, with whatever `frame.broadcast_team` value happens to
be available at that moment — which may be wrong.

**Live UX damage after Dual-broadcaster Path A**: none expected from
this specific stale SM scalar.  Canonical `build_full_payload()`
sources `batting_team` from team-assignment (correct: LSG), not from
SM (wrong: KKR), and the direct SM emit branch no longer exists.  The
remaining damage is forensic / internal: SM-INNINGS-2-RESET telemetry
is misleading (`new_batting_team=KKR`), making analysis harder.

**Fix-path candidates**:
- (A) **Add `score_manager.set_innings_2(target, batting_team)`
  invocation at test_pipeline.py:5857 alongside the scoreboard
  call** (~5 lines).  Requires sourcing `batting_team` from
  team-assignment (which is correct at AUTO-SWAP time).
- (B) **Pipeline emits unified innings-transition signal that
  both scoreboard and score_manager subscribe to** (~30-50
  lines, broader refactor).  Future architecture, not the
  fast fix.

**Fix shipped**: AUTO-SWAP now calls
`score_mgr.set_innings_2(target=_injected_target, batting_team=_old_bowl,
reason="AUTO-SWAP")` immediately after `scoreboard.set_innings_2()` and
before `assign_teams()`.  This resets the Fix 16 scalar surface using
the same canonical transition signal instead of waiting for SM to infer
innings 2 later from a potentially noisy frame.

**Validation status**: source-level regression added to pin the
AUTO-SWAP call and argument source; `test_recent_fixes.py` reports
484 PASS / 0 FAIL.  Live validation requires next innings transition.

### (9) WS-PROJECTION-FALLBACK does not check `batting_card.status` before resurrecting from `active_batting`

**P1 — SHIPPED-validated live by 2026-04-27 Bundle A.**
Originating commit: Fix 7 (WS projection fallback for SM-null cases).
With direct SM emits removed, the fallback is no longer compensating for
event-frame SM/scoreboard projection flips, but it still protects
scoreboard-local active-batter corruption.

The fallback currently does: "if SM has null non_striker, and
sb._inn['non_striker'] is in `active_batting`, use it".  But
"active_batting" can include dismissed-but-not-cleaned batters
(per (7)).  **Adding `batting_card[X].status != 'out'` as a
filter would prevent resurrection.**

This is a sibling fix to (7) — even if (7) ships and Fix 13
catches every dismissal, this guard is cheap insurance.

**Fix shipped**: `_project_active_batters()` now resolves the `sb._inn`
slot through `scoreboard.resolve_name()`, looks up the canonical
`batting_card` entry, and requires `status == "batting"` before
projecting the fallback value into the WS payload.

**Validation status**: regression added for non-batting status rejection
and raw-name resolution before the status check; `test_recent_fixes.py`
reports 484 PASS / 0 FAIL.  Live DC-vs-RCB restart validation saw
multiple SM-null projection gaps (F58-F92) and fallback projected only
currently active `status="batting"` card entries (`Kuldeep Yadav`,
`Abishek Porel`).  After Kuldeep's W9 cleanup at F380/F387, fallback
did not resurrect the dismissed batter; the remaining issue was a
payload-level same-slot collision already tracked in (18).

---

## Snapshot — 2026-04-26 21:35 IST mid-innings-break monitoring

**Fixes 13-18 deployed cleanly during LSG-vs-KKR last-ball cold-
start.**  443 PASS / 0 FAIL unit tests; pipeline successfully
recovered KKR `155-7 (19.5)` end-of-innings state after a chaotic
5-minute cold-start window dominated by partial pre-match-style
graphics (`LSG 0-0(0.0)` strips).  After ~14 min of monitoring
with 322 frames processed:

- **Fix 13** (POST-WICKET-CARD-PROPAGATE): 0 fires (no wicket
  events captured post-restart — innings 1 wickets all preceded
  pipeline start)
- **Fix 14** (BALLS-CEILING-GATE): 0 fires (no impossible balls
  counts detected)
- **Fix 15** (SCORE-INF-GATE): 0 fires (no unexplained score
  inflations)
- **Fix 16** (SM-INNINGS-2-RESET): 0 fires (innings 2 has not
  transitioned yet — broadcast still in extended innings break)
- **Fix 17 Path A** (PRE-MATCH-GRAPHIC-GATE): 0 fires (gate
  correctly didn't engage because `batting_team=KKR` was set
  before any 0-0(0.0) graphic appeared); however **four hotfixes
  to Fix 17 were required** during deployment — see "Fix 17
  ship-day hotfixes" below.
- **Fix 17 Path D** (WS-COLD-START-GATE): 1 OPEN event (timeout-
  release path; the original `score >= 1` open-condition was too
  strict and got hotfixed to `batting_team set` mid-monitor).
- **Fix 18 L2/L3** (BAT-SUM-RECONCILER, CAP-RESET-LAST-ADVANCE):
  0 fires (no bat_sum > score+5 divergence).

Existing baseline noise (not regressions, **but one new P1 surfaced
during today's monitoring** — see (6) below):
- STRIKER-COLLISION: 2 (legitimate self-collision refusals;
  Fix 5 working as designed)
- WS-SCRUB: 229 fires — **all on `non_striker='SINGH'`** ←
  **new P1** filed below
- FRAME_POISONED: 24 (normal during chaotic innings break with
  partial / placeholder graphics)

### (6) Extractor splits "Rinku Singh" into two batters → persistent `non_striker='SINGH'` leak

**P1 — fix near-term, ~10-30 lines.**

LSG-vs-KKR 2026-04-26 21:27 F86 captured the originating event:

- Scout STRIP reads: `LSG | Rinku Singh 0(0) | | Digvesh Singh
  Rathi (0)`
- Extractor parses: `ext_bat=RINKU 0(0) | SINGH None(None)`
  ← **two batters from one underlying name**, the surname
  fragment "SINGH" splits into its own ghost batter.
- One ghost-batter slot writes through to scoreboard internal
  state for `non_striker = "SINGH"` (the canonical `Rinku
  Singh`'s `runs`/`balls` are correctly populated by the
  RINKU-side parse, but the SINGH ghost-write replaces the
  non_striker scalar field).
- WS-SCRUB correctly rejects the `non_striker='SINGH'` payload
  every frame (`reason=not_in_card`) but scoreboard internal
  state is not cleaned, so every subsequent frame emits the
  same scrub event.  After ~14 min the counter reached **229
  fires**, each one a discarded broadcast and a log line.

Damage:
- Log noise (229+ WARNINGs in single-innings window)
- Hidden CPU/network cost (rebuilding payload only to scrub it)
- WS payload `non_striker=Ajinkya Rahane` (the scrub fallback)
  is incorrect during the actual delivery — Rahane was striker,
  not non_striker; correct value should be `Rinku Singh`.

Hypothesised root causes:
- (a) Extractor prompt allows surname-only fragments to be
  surfaced as separate batter rows when the scout strip's
  `|`-delimiter parse is ambiguous (extra spaces around "Rinku
  Singh" between info-panel boundaries).
- (b) Strict canonicalization at the *batter-update* path
  resolves "RINKU" → `Rinku Singh` correctly via squad-fuzzy
  match, but the *non-striker scalar* assignment uses raw
  Scout name without the same canonicalization filter.

Fix-path candidates (need investigation to pick one):
- (A) Extractor-side dedupe: when two parsed batters share a
  surname, collapse to one (~5-15 lines in extractor prompt or
  post-processing)
- (B) Pipeline-side canonicalization at non_striker write-
  through path: route the non_striker scalar through the same
  `resolve_name → batting_card.contains` filter that batter
  updates use (~10-20 lines in `apply_scorer_decision` or
  `score_manager`)
- (C) Self-healing scoreboard scalar: when WS-SCRUB rejects
  `non_striker=X` for `not_in_card` for >5 consecutive frames,
  reset `scoreboard._inn["non_striker"] = None` and let the
  next legitimate scout read repopulate it (~5-10 lines in
  scoreboard, complements WS-SCRUB rather than replacing it)

Production fixture: LSG-vs-KKR 2026-04-26 F86 (first SINGH
fire) through F478+ (still active during innings break).
Test data: scout text containing `Rinku Singh 0(0)` with
extra spaces produces `RINKU 0(0) | SINGH None(None)` on
extractor — replay to validate.

### Fix 17 ship-day hotfixes (2026-04-26 21:09–21:23 IST)

Original Fix 17 shipped with four bugs, each surfaced and
patched within ~14 minutes during the LSG-vs-KKR last-ball
deployment.  Documented for future-engineer prevention:

- **v2 hotfix**: Path A pre-match-graphic gate referenced
  `extracted` before it was assigned (it lives at line ~5447,
  the gate at ~4862).  Symptom: pipeline crashed with
  `UnboundLocalError` 6 seconds after start.  Fix: parse the
  strip context directly from `description` (Scout text) using
  a regex `<ABBR>\s+\d+-\d+\s*\(\d+\.\d+\)` rather than
  consuming the not-yet-computed `extracted` dict.

- **v3 hotfix**: WS-COLD-START-GATE looked at `payload["score"]`
  and `payload["batting_team"]` but the canonical
  `build_full_payload()` shape places these under
  `payload["scorecard"]`.  Symptom: gate never opened on
  legitimate state (always took the 90s-timeout path).
  Fix: read both flat and nested shapes.

- **v5 hotfix**: WS-COLD-START-GATE required `score >= 1` to
  open.  Legitimate zero-score windows (innings-2 first ball,
  mid-match restart catching a between-overs graphic, DRS
  pause) blocked the UI for the full 90s on every restart.
  Fix: gate now opens as soon as `batting_team` is committed
  (the original sin Path D was designed to prevent — once team
  is right, score=0 is fine).

- **v6 hotfix**: Path A correctly identified pre-match graphic
  on F1 ("LSG 0-0(0.0)") and refused to assign teams, but
  `_broadcast_cache["team_abbr"]="LSG"` got cached anyway.
  On a later frame whose scout text contained a *different*
  match's strip (e.g. `RR 89-3 (10.4)` — broadcast highlight
  insert), the gate's strip-pattern guard didn't match, and
  the cached `LSG` flowed through to `assign_teams`.  Fix:
  evict the cached `team_abbr` whenever Path A fires.

- **v7 hotfix**: A second team-assignment path
  (extractor `visible_team`, lines 6193–6203) was uncovered
  by Path A.  Same pre-match-graphic shape produced
  `visible_team=Lucknow Super Giants` from the extractor,
  bypassing the gate entirely.  Fix: extend Path A logic to
  the `visible_team` branch — same `score=0, wkts=0,
  overs=0.0, current_innings==1, no batting_team` predicate.

Lesson for future "add an admission gate" tasks: **enumerate
every existing assignment / write path for the gated field
before claiming bounded scope.**  The pre-match-graphic gate
appears bounded ("just block one if-branch") but the field
under defence (`batting_team`) has multiple writers; gating
one without the others creates a false-confidence trap.

---

## Snapshot — post-2026-04-25 RR-vs-SRH match-2 inter-match commit bundle

Last cleaned: 2026-04-27 19:05 IST after **Dual-broadcaster Path A**
shipped.  The live-UX dual-emit items below are now
**SHIPPED-pending-validation**: direct SM WS emits were removed from
`test_pipeline.py`, all WS frames route through `build_full_payload()`,
and a regression test prevents `ws_payload = _sm_result` from
returning.

(5) **Recent Overs (and occasionally This Over) flips
between two render shapes** — **SHIPPED-pending-validation by
Dual-broadcaster Path A.**  UI alternately showed
`Ov 12: Markram . ? ? 1 . .` (with bowler + `?`
placeholder tokens) and `Ov 12: 1 . .` (no bowler,
fewer/different tokens) on consecutive frames ~30 s
apart.  Root cause traced to `test_pipeline.py:8110`
branch: when `_sm_result is not None` and `not
score_mgr.shadow`, the SM payload broadcasts
(`over_history[N] = list[str]`, written at
`score_manager.py:1655`/`:1843`); otherwise
`build_full_payload()` broadcasts (`over_history[N] =
{balls, bowler, runs, wickets}`, written at
`this_over.py:358`/`:1052`).  Same `state.over_history`
field, **two incompatible shapes**, alternating per-
frame on event-vs-idle.  UI accepts both shapes
(`page.tsx:748-755` falls through `Array.isArray ||
entry?.balls || entry?.broadcast_balls`), so the flip
visibly mutates the rendered overs grid.  Three fix
paths (A SM-shape canonicalize, B SM-emit-without-
over_history, C SM-cutover bundle).  Path A at the emit boundary
has now removed the event-vs-idle source flip; validate with the
LSG-vs-KKR F1009-F1053 over-history fixture.

Earlier in the same monitoring window — **two prior P0
(live UX) filings**:
(3) **Striker self-collision in `sb._inn` becomes stuck**
— both slots latched to `Cameron Green` from F704 onwards
because Fix 5's write-time guard correctly blocks fresh
writes but cannot heal the corruption created by an
upstream rotation/re-install path; Fix 7 fallback also
correctly refuses to use the collided value, leaving WS
payload `non_striker=None`; UI header shows `● Green —`
despite Singh visible in AT THE CREASE table for 7+
minutes and counting.  Three fix paths (A heal-on-collision,
B identify upstream defect, C Path-B-cutover completion).
(4) **Team-name `LSG` ↔ `KKR` flip in BIG-header score
line** — **SHIPPED-pending-validation by Dual-broadcaster
Path A.**  Same dual-broadcaster pattern as the previously-
filed inn1/inn2 flicker, now extended to the
`batting_team` scalar.  SM emits its own `batting_team` in
`score_dict()` which gets overwritten to `LSG` on noisy
strip reads (squad/ad/pre-match graphic windows) and
flickers against `build_full_payload()`'s correct `KKR`.
Three fix paths (A 3-frame consensus on SM batting_team,
B source from team-assignment, C bundle into SM-reset
fix).  Direct SM emits are now gone; validate against the
F686-F688 innings-transition team-name window.

Earlier 2026-04-26 20:30 IST:
**`analyze_match_telemetry.py` extension** for Fix 9-12
validation: 5 per-fix report functions (`--report-9a` through
`--report-12`, `--report-all-fixes`), per-wicket histogram
mode (`--per-wicket`), `BASELINE_COUNTERFACTUALS` dict
anchoring expected pre/post-fix behaviour, ~250 lines source +
~270 lines tests in 12 new tests / 35 sub-checks; **371 PASS /
0 FAIL**.  Validated against historical CSK-vs-GT log: 652
STRIKER-COLLISION across 9 wickets (72.4/wicket pre-fix);
validated against current LSG-vs-KKR log: 43 collisions on
wicket 4 (post-fix), 2 RUNS-REJECT-STREAK fires on Cameron
Green (max 2/5, well below release threshold).  Analyzer
**surfaced** finding (3) above by showing 70 STRIKER-
COLLISION fires on the wicket-4 window with 0 POST-WICKET-
ROTATION fires.

Earlier 2026-04-26 20:15 IST: **two new P0 (live UX)
filings** during LSG-vs-KKR live monitoring: (1) Cold-start
mid-match-join initial-team-misassignment producing ~3-min
window of visibly-wrong UI (`LSG 0/0` displayed while broadcast
showed `KKR 28/3`); (2) Phantom batter-stats injection
producing impossible `Powell 14(56)` at over 6.1.  Both are
defence-in-depth admission gaps with proposed fix paths.

Earlier: 2026-04-26 19:55 IST **Fix 12 staged**
(rejection-consensus release on runs-monotonic guard, Layer 4
of phantom +N quartet, ~110 lines source + ~290 lines tests
in 10 new tests / 31 sub-checks; **371 PASS / 0 FAIL** after
analyzer-extension addendum).
Earlier today: Fix 11 staged (EXTRAS-INF admission gate,
Layer 1 of phantom +N quartet,
~150 lines source + ~280 lines tests in 8 new tests / 20
sub-checks).  Earlier today: dual-
broadcaster fluctuation surfaced (Inn 1 / Inn 2 + target=159 /
target=None flicker on every ball event during GT chase, post-
Fix-9/10 restart).  Root cause is the already-tracked **P1
SM-reset gap** manifesting visibly via the SM-broadcast vs
`build_full_payload` path mismatch — entry below has been
enriched with the production-damage evidence and the broadened
scalar-field set that needs reset (`innings`, `target`,
`batting_team`, `bowling_team`, in addition to the original 14).
No hotfix — deferred to the proper P1 fix at next inter-match
seam.

Earlier today: Fix 10 staged (post-witnessed-FOW slot rotation
hook — closes the Sarfaraz/Dube/Overton stuck-non_striker
class) and Fix 11 staged (EXTRAS-INF admission gate, Layer 1 of
phantom +N quartet — closes the batter-side sum-violation
admission path that produced Brevis +10 / Hosein +21 / Dube
+9 phantoms).  Detail entries below; this section is the dense
surface for "what's the state of the queue right now."

**Currently SHIPPED + running (landed via the 2026-04-25 18:36
bowler-stale-fix hotfix restart):**
- BOWLER-STALE defense (bowler-context disambiguator)
- Pass-2 enrichment async-split (foreground returns Pass-1 immediately)
- Debug frame archival on pipeline startup (instead of deletion)

**STAGED, awaits next inter-match seam restart**
(`staged_fixes_2026-04-25/` bundle + Fix 9a/9b/10/11/12
2026-04-26 addendum; 13 production fixes + test-hygiene
addendum + analyzer-extension addendum;
92 new tests; **371 PASS / 0 FAIL**.  Rollback tag
`pre-restart-bundle-2026-04-25` at `b5471c7` in `files/` —
covers Fixes 6/7/8 + test-hygiene rewrites + docs, Fixes 1-5
baked into the tag's snapshot per the README's accuracy-
corrected rollback section.  Fix 9a/9b/10/11 will be tagged at
the next inter-match commit):
- Fix 1: P0 target=640 innings-1-final latch sanity bound
- Fix 2: P0 `this_over` token-alphabet validation
- Fix 3: P1 `this_over` chronological reorder on FOW upgrade
- Fix 4: P0 `[CONSENSUS-BLOCKED] overs:` regression guard
- Fix 5: P1 striker self-collision guard in `update_batter` (Path A)
- Fix 6: P1 Pass-2 client config (`timeout=240.0, max_retries=0`)
- Fix 7: P2 WS-PROJECTION-GAP fallback to `sb._inn` (extracted module-
  level `_project_active_batters` helper; fallback gated on
  `active_batting` membership; defence-in-depth `_other_slot`
  collision check; positive-firing `[WS-PROJECTION-FALLBACK]`
  telemetry)
- Fix 8: P1 INFO-PANEL bowler-strip gate (rewrote
  `filter_info_panel_contamination` from log-only no-op to active
  content-based gate; strips `bowler` / `bowler_name` /
  `bowler_figures` when `_INFO_PANEL_KEYWORDS` matches `vision_desc`;
  closes F619 future-bowler-locked-in-too-early class; positive-
  firing `[INFO-PANEL-GATE]` telemetry)
- Fix 9a: P1 AUTO-SWAP target injection ordering + source
  (`test_pipeline.py`).  Moves `set_innings_2(target)` BEFORE
  `assign_teams` (whose `current_innings = 2` side effect was
  gating the target injection out entirely) and sources score
  from latched `innings_1_total` rather than live
  `scoreboard._inn.score` (which can be None due to
  FRAME_POISONED).  Closes the F2503 mechanism that left
  target=None at AUTO-SWAP.  New telemetry:
  `[AUTO-SWAP-TARGET]`.
- Fix 9b: P1 target monotonic + sanity guards at
  `team_assignment.target` write site (`test_pipeline.py`).
  Replaces unconditional `scoreboard.set("target", ...)` in the
  `current_innings == 2` branch with a two-layer guard:
  `[TARGET-MONOTONIC]` refuses overwrite when target already
  set; `[TARGET-SANITY]` requires proposed target > current
  team score when target is unset.  Closes the F2504 mechanism
  by which a misread `GT 66-4 (11.5)` strip overwrote the
  correct `target=159`.  Composes with Fix 9a as the second
  defense layer.
- Fix 10: P1 post-witnessed-FOW slot rotation hook
  (`scoreboard.py`).  Centralized at `_add_fow`'s
  `_witnessed=True` stamp (both placeholder-upgrade and
  new-entry creation paths); fires
  `_post_witnessed_dismissal_slot_rotation(batter)` which
  implements four-case behaviour (striker-only / non_striker-
  only / neither / anomaly).  Closes the upstream rotation
  gap producing 88 / 443+ / 240+ defensive cascade fires per
  stuck-non_striker window (Sarfaraz F1670, Dube F1813,
  Overton F2410+).  Hooks at the canonical "wicket
  confirmed" event covers `dismiss_batter` and
  `_auto_dismiss_for_new_batter` main paths without per-
  callsite touch-ups; validate-resurrection demote paths
  (lines 3091, 3124) deferred to "Complete the SM-cutover"
  follow-up (no production damage observed).  New telemetry:
  `[POST-WICKET-ROTATION]`.
- Fix 11: P1 EXTRAS-INF admission gate, Layer 1 of phantom
  +N quartet (`test_pipeline.py`).  Pre-commit cricket-
  physics gate inside `apply_scorer_decision`: when proposed
  `bat_sum > current score` (impossible — would require
  negative extras), reject the entire batter-figure proposal
  for this frame.  Hard-rejects both the `batter_ups` update
  loop AND the extractor INIT-loop side channel by zeroing
  both dicts; phantom never enters scoreboard state.
  **Coverage scope (verified against today's CSK-vs-GT log
  fixtures):** catches batter-side sum-violation phantoms
  cleanly — F732 (wkts=3 score=30 bat_sum=47, +17 excess —
  Brevis-era), F1276 (wkts=4 score=46 bat_sum=71, +25),
  F2400 (wkts=7 score=154 bat_sum=155, +1 residual),
  Hosein +21 admission at F2408 (would-be bat_sum=176 >
  score=154, +22 — explicit replay test).  **Honest scope
  limitations:** batter-side only — score-side phantoms (F52/F53
  +4 inflation; bat_sum below inflated score) are covered by
  **Fix 15** `[SCORE-INF-GATE]` (Layer 1.5 advance/floor in
  `apply_scorer_decision`), not this gate; does NOT catch name-figure swap phantoms
  (signature 5; total sum stays valid but row attribution
  swaps; separate mechanism).  v1 hard-rejects entire batter
  slate (one frame's legitimate concurrent updates lost per
  fire — acceptable trade-off vs admitting phantom);
  per-batter rejection deferred to v2.  v1 uses
  `known_extras = 0` (strict physics) to avoid feedback loops
  with the post-commit `[EXTRAS-INF]` reconciler at frame-
  loop ~line 4540 (which stays as diagnostic).  Completeness
  gate (mirrored from existing block):
  `_dismissed_count == wickets` AND all dismissed/active
  runs are known — abstain otherwise to prevent false
  positives during transient state.  New telemetry:
  `[EXTRAS-INF-GATE]` (WARN-level), `EXTRAS-INF-GATE:bat_sum=X>Y`
  in `apply_scorer_decision` changes log for parity-monitor
  counting.  8 new tests / 20 sub-checks (simple fixture,
  legitimate-passthrough, incomplete-data abstention,
  unknown-runs abstention, INIT-path neutralisation,
  F2408 production replay, score-side scope-doc, source-
  level wiring).
- Fix 12: P1 rejection-consensus release on runs-monotonic
  guard, Layer 4 of phantom +N quartet (`scoreboard.py`).
  POISON-STREAK template applied at the per-batter runs
  level: tracks consecutive rejections of the same proposed
  value via `Scoreboard._runs_reject_streak`; at threshold
  `_RUNS_REJECT_RELEASE_N = 5` (POISON-STREAK precedent),
  force-sets the tracker baseline + entry to the rejected
  value (and the captured balls counterpart, field-specific
  release).  Refactored the two existing rejection clauses
  inside `update_batter` to record the rejection sentinel +
  value + balls; the new Layer 4 block immediately downstream
  drives the streak counter and threshold-fires.  Streak
  resets on a different rejected value (OCR-jitter
  protection — consensus must be on the *same* value) and
  on legitimate acceptance (phantom window closed
  naturally).  `set_innings_2` clears the streak dict for
  innings hygiene.  **Production grounding:** Dube case
  F1767-F1812 (357 rejections of `runs=22` over 41:50 with
  zero releases under detection-only guard) — at N=5 the
  release would have fired at ~F1772, **35 minutes
  earlier**.  POISON-STREAK released a comparable score-
  level stuck window in 90s with the same threshold; same
  template, different guard.  **Honest scope:** field-
  specific to runs (balls have their own guards; CLONE-
  REJECT and balls-regression-too-deep clauses
  intentionally NOT extended — different rejection
  semantics).  Doesn't catch slowly-advancing truth where
  the rejected value drifts (each frame's value differs);
  Layer 2/3 sum-check correction handles that.  10 new
  tests / 31 sub-checks (streak increment, threshold fire,
  reset-on-different-value, clear-on-acceptance, zero-
  regression clause, F1767+ Dube production replay, row-
  rejected-flag clear, per-batter independence, innings-2
  reset, source-level wiring).  New telemetry:
  `[RUNS-REJECT-STREAK]` (INFO, per-rejection ramp) and
  `[RUNS-REJECT-RELEASE]` (WARN, threshold fire).
- **Analyzer extension (validation harness for Fixes 9-12)** —
  `analyze_match_telemetry.py` extended with five per-fix
  report functions (`report_fix_9a` ... `report_fix_12`),
  CLI flags (`--report-9a`, `--report-9b`, `--report-10`,
  `--report-11`, `--report-12`, `--report-all-fixes`,
  `--per-wicket`, `--fix-validation-only`), six new telemetry
  regexes (`FIX9A_AUTOSWAP`, `FIX9B_TGT_MONO`,
  `FIX9B_TGT_SAN`, `FIX10_POST_WKT`, `FIX11_EXTRAS_INF`,
  `FIX12_REJ_STREAK`, `FIX12_REJ_RELEASE`), `STRIKER_COLLISION`
  for Fix 10's per-wicket counterfactual, `WKT_TRANSITION` for
  per-wicket binning, eight new `Snapshot` fields for the
  captured events, `_bin_by_wicket` partitioning helper,
  and `BASELINE_COUNTERFACTUALS` dict anchoring expected
  pre/post-fix behaviour for each layer.  Each report
  produces a positive-fire count, an interpretation status
  line (SILENT / FIRED / VALIDATED / TRIGGER OCCURRED but no
  fire), per-event detail rows, and (Fix 10) per-wicket
  histogram of rotations vs collisions.  Validated
  end-to-end against historical CSK-vs-GT log (652
  STRIKER-COLLISION across 9 wickets = 72.4/wicket pre-fix;
  matches Sarfaraz/Dube/Overton documented baselines) and
  current LSG-vs-KKR log (43 collisions on wicket 4 post-
  Fix-10, 2 RUNS-REJECT-STREAK fires on Cameron Green at
  max 2/5).  12 new tests / 35 sub-checks (regex parsing
  for each tag, kind-classification for POST-WICKET-ROTATION,
  wicket-transition deduplication, `_bin_by_wicket`
  partitioning correctness, `report_fix_10` per-wicket
  histogram rendering, silent-on-pre-trigger status lines,
  `report_fix_9b` Fix-9a-credit when silent,
  `BASELINE_COUNTERFACTUALS` dict completeness).
  **First-run finding (LSG-vs-KKR):** Fix 10 fired 0
  POST-WICKET-ROTATION on the witnessed Powell wicket at
  6.1 despite expected fire; STRIKER-COLLISION rate
  reduced from 72.4/wicket baseline to 43/wicket but
  rotation hook itself silent.
  **Investigation closed 2026-04-26 20:33 IST:**
  source-trace at `scoreboard.py:2697` confirms the
  upgrade path DOES invoke
  `_post_witnessed_dismissal_slot_rotation()`
  (Hypothesis 1 ruled out).  Hook no-ops at line 2842
  because the F179→F258 placeholder→witness gap (~2 min,
  79 frames) outlives the crease state — Powell already
  rotated out of `_inn["striker"]`/`["non_striker"]` by
  the time the witness arrives (Hypothesis 2 confirmed).
  Second related gap: `_add_fow` doesn't propagate the
  dismissal to `batting_card[name].status`, leaving the
  phantom-stats Powell entry visible in DETAIL rows.
  Test fixture
  `test_fix10_powell_f179_f258_placeholder_upgrade_with_
  drifted_slots` added (4 sub-checks documenting current
  no-op behaviour; flips when coverage-gap fix lands).
  Recommended fix: **Path D** (broaden hook to also clear
  `batting_card.status` + `active_batters` when dismissed
  not in slots, ~10-15 lines).  Full diagnosis and three
  fix paths (D/E/F) recorded in the Fix 10 entry below.
  Total tests: 375 PASS / 0 FAIL.

**Newly surfaced 2026-04-26 during CSK-vs-GT match-3 (live monitoring,
post-bundle deployment):**

- **P2/P3** SM lacks `set_innings_2()` / `reset()` — discovered during
  innings-transition hygiene audit; `score_manager.ScoreManager` only
  flips `self.innings = 2` directly (4 callsites) without resetting
  cached `bat1_runs`/`bat2_runs`/`bowler_*`/computed metrics.
  Currently inert (different teams = different name keys) but a real
  side channel for same-named-player edge cases and shadow-mode
  parity.  Detail entry below; in-code doc comment added at
  `score_manager.py:130`.
- **BOWLER-AUTO mechanism clarification (closed, no fix)** — earlier
  framing as "team-score → bowler-stats mirror" was correct; later
  "only auto-bumps overs, not runs" was wrong.  BOWLER-AUTO mirrors
  both fields; deferral-when-Scout-is-active is the dominant fire
  pattern (~50+ deferrals/match).  Operational note added at
  `eyes/scoreboard.py:1207`; backlog entry under "Held / observation-
  only" below.
- **Phantom +N P0 entry: decay-via-scoring assumption empirically
  refuted (F1767+, most important finding of the day)** — Dube
  case produced 357 whole-row rejections by dismissal (F1813), 0
  decay achieved despite Dube actually scoring 19→22 in real play.
  The WARN logs literally say "**dropping runs=22 too (whole-row
  invalidation)**" — pipeline has truth in hand and discards it.
  Final metrics: 41:50 wall-clock window, 6 balls faced, ~100%
  rejection-rate-per-Dube-read.  Phantom closed only via dismissal,
  never via decay.  **Framing change:** the prior mental model
  ("phantom decays when holder scores past inflated value") is
  empirically wrong for the modal Dube-shaped case where balls
  also diverged.  Decay-only correction works only when the truth
  state's balls value happens to stay close to the phantom's;
  Gaikwad +4 decayed (balls stayed close), Dube +9 didn't (balls
  diverged 35→13).  "Decay handles the common case" was a comfort
  the data has revoked.  Detail entries updated with both
  sub-findings (whole-row symmetry, explicit-cost telemetry) and
  field-level vs whole-row reset semantics for the cap-reset fix.
  Today's data is the regression-test fixture for the future
  triad implementation.
- **Signature 5 (name-figure swap) confirmed firing in production
  F1842** — Scout strip read `Kartik 48(4) | Gaikwad 48(2)`
  (transposed values).  Pipeline correctly rejected via Gaikwad's
  runs regression caught by monotonic guard + whole-row
  invalidation incidentally blocking Kartik's phantom inflation.
  Validates that the phantom-signature design framework is
  descriptive of observed production failures, not speculative.
  Annotation added to signature-5 design note.
- **Architectural principle named (2026-04-26 17:15):  every
  guard with detection semantics should have a corresponding
  release mechanism.**  Surfaced from the empirical contrast
  between FRAME_POISONED + POISON-STREAK (released the F2240+
  over-18 stuck window in 90s with 5-frame consensus) and the
  runs-monotonic guard (held Dube phantom for 41:50 with 357
  rejections and zero releases).  Same architectural pattern,
  different implementation completeness.  POISON-STREAK is the
  template; the runs-monotonic guard violates the principle.
  Triad cluster promoted to **quartet** with Layer 4
  (rejection-consensus release on runs-monotonic guard,
  POISON-STREAK template, ~110 lines as shipped Fix 12,
  Path 1 per-field consensus).  **Layer 4 STAGED 2026-04-26
  19:55 as Fix 12;** detail entry below.
  Future guards should be evaluated against this principle:
  "if this guard rejects truth, what causes it to let go?"
  Without an answer, the guard is incomplete.
- **SM-reset gap promoted P2/P3 → P1 (2026-04-26 17:24).**
  CSK-vs-GT innings transition F2503 AUTO-SWAP empirically
  confirmed the gap firing in production: SM cached striker
  name `Jamie Overton` (CSK) persisted into GT's innings-2,
  triggering 8+ `[WS-SCRUB] striker rejected reason=not_in_card`
  fires in the first 12 frames.  WS-SCRUB defensively rescued
  the user-visible UI; underlying state corruption confirmed.
  Refined diagnosis: scalar fields (striker, bat1_runs, etc.)
  persist; keyed caches reset cleanly via key-distinction
  (Hosein 21(6) phantom didn't carry over because GT batters
  have different name keys).  Fix scope narrowed to ~14 scalar
  fields, ~30-50 lines.  Justification for promotion:
  empirical confirmation + bounded fix + masked-by-defense
  argument (defenses can rot, underlying bug needs fixing).
- **STAGED Fix 9a + Fix 9b: Target-source-confusion at
  AUTO-SWAP boundary — broader-than-target blast radius
  (2026-04-26 17:55, enriched 18:00 after live overs-stuck
  finding).**  Initially diagnosed as innings-break-graphic
  ingestion; source dive refined the root cause to a 3-step
  ordering bug at AUTO-SWAP: (1) AUTO-SWAP fires; (2)
  `assign_teams(...innings=2)` runs first, flipping
  `scoreboard.current_innings = 2` as a side effect; (3) the
  next-line `set_innings_2(target)` is gated on
  `current_innings == 1` — already flipped — so the **entire
  innings-2 reset path is a no-op**, not just target
  injection.  Live monitoring confirmed: 0 occurrences of
  `[INNINGS] Set to 2` in 38k+ log lines.  Symptoms in
  current match: target=66 stuck (set by misread once, never
  corrected), overs stuck at innings-1's 20.0 (63
  `[CONSENSUS-BLOCKED]` + 409 `[SUSPICIOUS]` rejects of
  legitimate innings-2 reads), innings-1's 7 FOW persisting,
  extras/this_over/over_history all stale.  **Fix 9a** moves
  the `set_innings_2` call before `assign_teams` (restoring
  the entire reset path) and sources target from latched
  `innings_1_total` (max with live `sb._inn.score` to handle
  FRAME_POISONED gaps).  **Fix 9b** adds `[TARGET-MONOTONIC]`
  + `[TARGET-SANITY]` guards at the team_assignment target
  write site so misreads cannot overwrite a correctly-
  injected target.  Path (c) (innings-break graphic gate)
  deferred — Fix 9b's monotonic guard contains the immediate
  graphic-misread damage.  One fix closes target=66 +
  overs-stuck + FOW-carryover + the entire "innings-1
  tracker state leaks into innings-2" class.  16 new
  source-level tests added; all 256 tests pass.  Awaits
  inter-match seam restart for live validation.
- **Cold-start coverage gap hypothesis collapsed (2026-04-26
  17:31).**  Initial diagnosis "pipeline missed innings-2
  from over 0.0-11.4" turned out to be wrong; the pipeline
  did tail GT from over 0.1.  The earlier `GT 66-4 (11.5)`
  read was a graphic misread, not a coverage gap.  Lesson:
  when strip reads show unexpected state at innings
  transitions, rule out graphic-misread before assuming
  coverage gaps.  No separate filing.
- **WICKETS-REGRESS guard with 3-frame consensus release —
  third confirmed example of detection+release principle
  (2026-04-26 17:31 F2665).**  At innings flip, wickets=7
  carried over from innings-1 into innings-2 state (another
  scalar-field SM-reset gap symptom).  Broadcast read 0
  three consecutive times, guard accepted the regression:
  `[WICKETS-REGRESS] Accepting 7→0 after 3 consecutive
  frames of broadcast reading 0`.  Adds to the architectural
  pattern: **POISON-STREAK** (5-frame), **WICKETS-REGRESS**
  (3-frame), proposed **runs-monotonic Layer 4** (N-frame).
  Three guards with detection+release semantics; the
  runs-monotonic violator stands out more sharply.  The
  3-frame vs 5-frame difference suggests the threshold can
  be tuned per-guard based on how strong the structural
  signal is (innings-2 wickets=0 is a near-certain regression
  → tighter consensus; over-completion runs is more
  ambiguous → wider consensus).
- **Phantom +21 confirmed on Akeal Hosein at innings-1 close
  (F2408, CSK-vs-GT 19.5 over).**  Strip OCR reported `Hosein
  21(6)` for a fresh batter (CB ground truth: 0(0)).  Pipeline
  accepted the commit (0→21 not a regression, no runs-monotonic
  guard fires).  This is **Layer-1/Layer-2 territory of the
  quartet** (admission gate + reconciler), not Layer 4
  (release).  Hosein didn't visibly carry into innings-2
  because GT batters have different name keys ⇒ keyed caches
  return fresh state.  Two phantom +N instances in this match's
  innings-1: Dube +9 (release-layer evidence) and Hosein +21
  (prevention-layer evidence).  Both layer types empirically
  validated for the quartet design.
- **SM-reset gap escalation: dual-broadcaster fluctuation
  (2026-04-26 18:25, post-Fix-9/10 deploy).**  Live monitoring
  during GT chase showed the UI alternating between
  `Inn 2 / target 159 / "Need 85 from 67 balls"` and
  `Inn 1 / target=None / no chase context` on every ball event
  (over 8.5 → 9.0).  Pipeline-side state is consistent
  (`AFTER_innings=2` + `AFTER_target=159` on **every** DETAIL
  log line from F40 onwards) — the fluctuation is purely on the
  WS-payload boundary.  Root cause is the dual-broadcaster
  architecture in `test_pipeline.py`:
    - **Event-firing frames** (`_sm_result is not None`,
      i.e. every ball event) → SM-broadcast path
      (`ws_payload = _sm_result` at line 7961) → emits SM's
      stale internal `innings=1` and `target=None`.
    - **Quiet frames** (`_sm_result is None`) → legacy path
      (`build_full_payload()` at line 8011) → reads
      `scoreboard.current_innings` (=2) and `state.target`
      (=159) — emits correct values.
  Smoking-gun signature in screenshots: Inn-1 frames carry
  `Partnership` and `Extras` panels (SM-only fields); Inn-2
  frames don't (legacy `build_full_payload` doesn't surface
  those panels).  Path attribution confirmed.  This is the
  **same SM-reset gap promoted to P1 yesterday** (Overton
  striker-name persisting), but with much stronger production
  evidence — no longer masked by WS-SCRUB; directly user-
  visible on the chase-context UI for the entire innings.
  The hotfix path (override `match.innings` / `match.target`
  in `ws_payload` at the SM-broadcast site, mirroring the
  existing `session_id` namespace patch at line 7969-7970) was
  **explicitly rejected by the user — "no temporary work."**
  Proper fix only.  Detail enrichment merged into the P1
  "SM lacks `set_innings_2()` / `reset()`" entry below
  (broadened scalar-field set, dual-broadcaster manifestation,
  per-ball-event cadence, validation surface for the fix).
  This is now the **highest-leverage P1 in the queue**:
  bounded scope (~30-50 lines), production damage actively
  visible, and the existing entry already has 90% of the
  diagnosis.

**Newly surfaced 2026-04-26 during CSK-vs-GT match-3 startup:**
- **P2** Pass-2 verify returns UNPARSEABLE JSON (different failure
  mode than yesterday's deterministic 271s timeout) — F42 15:36:31
  `[ENRICH] WARN: Pass-2 returned unparseable JSON — keeping
  pass-1 styles` followed by `Pass-2 background failed — cached
  Pass-1 as fallback`.  Fix 6's `timeout=240.0, max_retries=0`
  config validated for its stated purpose (no timeout fired —
  Pass-2 returned within ~2 minutes), but the response body
  itself failed `_extract_json_blob()`'s parse.

  **First action item — observability before fix selection.**  The
  current `WARN` log records that the parse failed but not WHAT
  was returned.  Without seeing the malformed response shape, the
  four fix candidates below are speculation.  Add the raw response
  body (truncated to ~2 KB to keep log size sane) to the WARN
  line.  ~3 lines in `player_enrichment.py` around the
  `Pass-2 returned unparseable JSON` log call.  Run for one match-
  day, observe the actual failure shape, then choose the
  appropriate path from below.

  **Fix candidates (rank-ordered probable cost):**
  1. **Preamble-strip** (likely cheapest, addresses common
     failure mode) — search for first `{` in response body and
     parse from there, robust to websearch preambles or
     conversational openers.  Doesn't help if the body is truly
     malformed.  ~5 lines.
  2. **Prompt tightening** — output-format constraints in the
     system prompt to force JSON-only responses.  Cheap if
     `groq/compound` honours format directives; depends on the
     model's instruction-following at this layer.  ~5-10 lines.
  3. **Wider blob extractor** — regex-based JSON extraction
     tolerating various structural issues (embedded JSON in
     prose, missing closing brace, etc.).  Most robust, most
     complex.  ~20-30 lines.
  4. **Parse-retry** — re-prompt on parse failure.  Adds latency,
     may not improve if the failure is deterministic for a given
     match's player set.  Last-resort fallback.  ~10-15 lines.

  Less urgent than the phantom-+4 P0 above but worth pairing
  with Fix 6 telemetry now that we have one match-day of Fix 6
  data.  Sequence: ship the response-body logging first (alone),
  observe one match, then pick the right fix.
- **P0 (live UX)** Phantom +N committed on single-frame OCR misread
  under `_post_event_grace` — **recurring class, not one-off**.
  Confirmed instances in CSK vs GT (2026-04-26):

  **Instance 1: phantom +4 score (F52, 15:36:52)** — over
  rollover 0.6→1.0, strip OCR misread CSK score `1` as `5`,
  `consistent_tracker._post_event_grace` was active (set to 2 by a
  prior ball event) and accepted the +4 jump on a single frame
  bypassing consensus.  Pipeline emitted `score: 1 → 5 (post-event
  immediate, grace=1)` and `ball_event=FOUR | ball_event_runs=4 |
  ball_event_over=1.0 | completed_over_runs=4`, fabricating a
  boundary at the over-rollover.  The actual cricbuzz boundary
  came **4 balls later at 1.2** (recent `0 4` at iter#21 vs
  pipeline's `0 4 0 W` projection), and registered as a dot
  because pipeline already had score=5.  Cascade: false `score=5`
  + false `wickets=1` (Samson "out" at 1.3 per pipeline, still
  batting per CB at 7(10) by 1.4); striker/non-striker rotation
  also misaligned.  Self-reinforced by pipeline-authored
  `comm_wire="1.0: ... 5 runs"` (LLM matched the misread; no
  external CB confirmation).  Visible sanity-check that should
  have rejected: F53 `[EXTRAS-INF] wkts=0: score=5 - bat_sum=1 =
  extras=4` — physically impossible after a single wide bowled,
  yet emitted only as a log line, not gated.  Fix candidates
  (in priority order):
  1. Cross-validate score commits against `bat_sum + known_extras`
     in `_post_event_grace` path — refuse to commit a score that
     produces an impossible extras count (`>` legal extras observed
     this innings).
  2. Tighten `_post_event_grace` for the `score` field
     specifically — require either a matching VLM-detected
     event (`FOUR`/`SIX`/`WICKET`/`EXTRA`) of consistent magnitude
     OR 2-frame consensus, even during grace.  Currently any
     non-suspicious change is accepted on first read.
  3. Down-vote score deltas at over-rollover boundaries (high-
     OCR-noise zone where strip is mid-update) — short cool-off
     of grace in the 1-2 frames bracketing an over change.
  Damage: rest-of-innings parity is broken until a fresh
  external state injection or restart; recommend a same-innings
  hot recovery path (separate item).  ~30-80 lines for option (1);
  ~10-20 for option (2) alone.  Trace lives in
  `logs/pipeline-2026-04-26-153428-csk-gt-v5-eight-fix-bundle.log`
  F52-F96 and `logs/parity-monitor-*csk-gt*.log` iter#13-iter#24.

  **Instance 2: phantom +12 batter inflation (F656+, ~16:01:36).**
  Strip at F656 read `Brevis 12(12) | Gaikwad 0(3)` while
  pipeline state had `Gaikwad 14(12), Brevis 0(2)`.  Likely a
  name-figure SWAP misread (Scout transposed names with figures
  across the two-batter region) plus a `14`→`12` digit
  confusion.  Pipeline correctly rejected the F656 read via
  consistency tracker (`AFTER_bat2=Dewald Brevis 0(2)` unchanged
  on that frame), but the misread persisted and was eventually
  accepted on a subsequent frame: by F786 (16:07:45),
  `BEFORE_bat2=Dewald Brevis 12(13)` was committed.  Brevis went
  on to remain at `12(13)` for the rest of his innings; CB ground
  truth was `Brevis 2(8)` at the same moment — an inflation of
  +10 runs and +5 balls that never auto-corrected.  Same `_post_
  event_grace` mechanism, different field (per-batter runs vs
  total score), confirming this is a class of bug rather than a
  field-specific edge.

  Both instances share: single-frame OCR misread of an integer
  field, accepted by `_post_event_grace` under a window that was
  opened by a recent legitimate event.  Fix candidates 1-3
  apply to both; the instance-2 case also benefits from the
  bat-runs reconciler (P1 above) which can detect the inflation
  even after the bad frame committed.

  **Instance 3: phantom +17 batter inflation (F975, ~16:19:37) —
  newly-arrived-batter variant.**  Shivam Dube came in to bat
  cleanly at F922 (16:15:08) via the REPLACE protocol with
  scout reading `DUBE 0(0) | GAIKWAD 18(22)`.  Over the next ~4
  minutes Dube faced 2-3 balls and scored 1 run (CB ground
  truth: `Shivam Dube 1(2)` at the equivalent moment).  At
  F975 scout misread `DUBE 18(23) | GAIKWAD 2(2)` — the same
  name-figure swap pattern as instance-2 (Gaikwad's `18(22)`
  got attributed to Dube; Dube's `1(2)` got attributed to
  Gaikwad as `2(2)` with a digit confusion).  Pipeline
  correctly defended Gaikwad via the runs-monotonic guard
  (proposed regression `18→2` rejected; AFTER_bat1 stayed at
  `18(22)`).  But the symmetric guard on Dube *fired in the
  wrong direction*: Dube's prior monotonic baseline was `1`,
  so the proposed jump `1→18` was accepted under
  `_post_event_grace` despite being a +17 inflation.

  **Asymmetric-defense gap (called out 2026-04-26 post-Dube):**
  the runs-monotonic guard protects established batters
  (rejects regressions) but provides **no protection for
  newly-arrived batters** because they have no prior baseline
  to compare against.  A name-figure swap that misattributes a
  high-run batter's figures to a freshly-arrived one will
  always commit on the inflated direction.  This is a
  different mechanism from instance-1's (`1→5` digit
  confusion under grace) — it doesn't require a digit
  confusion at all; the *swap* alone is sufficient.

  All three instances share: single-frame OCR misread of an
  integer field, accepted by `_post_event_grace` (or by
  initial-admission for new batters) when no prior baseline
  exists.  Fix candidates 1-3 apply to all; the instance-2/3
  cases also benefit from the bat-runs reconciler (P1 above)
  which catches inflation post-commit.  All three together
  have produced today's parity drift (Gaikwad +2 carryover,
  Brevis +10 inflation, Dube +17 inflation, plus knock-on
  striker/non-striker assignment errors).

  **Empirical confirmation of the lock-in mechanism (16:25-16:27,
  CSK vs GT):** with Dube's phantom `18` committed at F975, the
  runs-monotonic guard subsequently fired **11+ times in 90
  seconds** rejecting correct values: `Batter 'Shivam Dube' runs
  regression 18→6 (-12) rejected — dropping balls 6 too (whole-
  row invalidation)` (F1136, F1137×2, F1161×2, F1162×2, F1163×2,
  F1176×2, F1177×2).  The guard is working perfectly to prevent
  regression — but **the regression is the truth**.  CB ground
  truth at the same moment: Dube `6(6)` then `7(13)`.  Each
  rejection cements the phantom further; there is no recovery
  path until either (a) Dube legitimately scores past 18 or (b)
  he gets out and the next batter starts fresh.

  **Whole-row-invalidation collateral cost (called out
  2026-04-26 post-Dube):** the `dropping balls 6 too (whole-row
  invalidation)` clause means the guard rejects the *entire*
  batter row when any single field regresses, not just the
  suspicious field.  Two values are lost per rejection: the
  runs (which is what the guard is defending against) and the
  balls (which has nothing to do with the phantom but is part
  of the rejected row).  Eleven rejections × 2 values = 22
  pieces of correct data discarded in 90 seconds, only 11 of
  which were actually under attack.  The current rejection
  unit is row-level; the actual phantom signature is
  field-level.

  **Hardest empirical evidence yet (2026-04-26 ~16:54, F1767+):**
  the same rejection path now rejects Dube *truth values that
  would have decayed the phantom*.  Sequence of WARN logs:

  ```
  F1767 Batter 'Shivam Dube' balls regression 35→16 rejected
        (>2 balls backward) — dropping runs=22 too (whole-row
        invalidation)
  F1768 same, runs=22 dropped
  F1769 same, runs=22 dropped
  F1770 same
  F1771 runs regression 19→0 rejected — dropping balls 35 too
  F1772 balls regression 35→17 rejected — dropping runs=22
  ```

  CB ground truth at this exact moment: Dube `22(14)`.  Pipeline
  state: Dube `19(35)` (phantom).  Scout was *correctly* reading
  `DUBE 22(15)`, `DUBE 22(16)`, `DUBE 22(17)` from the broadcast
  strip 20+ times in this window.  Every single one was rejected
  *with the runs=22 truth value attached* — and the WARN log
  message explicitly says "**dropping runs=22 too (whole-row
  invalidation)**".  The pipeline is literally telling us what
  it is throwing away.  The decay-only correction story is
  worse than previously framed: even when the phantom holder
  scores legitimately, the truth is rejected because the balls
  field gives away the phantom (35-phantom vs 13-17-truth), and
  whole-row invalidation discards the runs increase along with
  the balls regression.  **There is no decay path** until either
  (a) Dube faces 36+ balls (then balls becomes monotonic and
  the row clears), or (b) Dube is dismissed and the slot
  resets.  By F1776 the rejection count for Dube alone is 359.

  **Two specific sub-findings worth surfacing:**

  - **Whole-row invalidation operates symmetrically** in both
    directions.  When *runs* is the suspicious field (F1771
    `runs regression 19→0 rejected — dropping balls 35 too`),
    balls gets dropped.  When *balls* is the suspicious field
    (F1772 `balls regression 35→17 rejected — dropping runs=22`),
    runs gets dropped.  This isn't a unidirectional defense
    quirk; it's symmetric whole-row rejection regardless of
    which field triggered the suspicion.  Architecturally the
    same defense pattern; behaviorally it means the cost of the
    collateral discard is doubled — the row is treated as
    atomic for rejection purposes, but the data-flow assumption
    that fields fail or succeed together is violated whenever
    only one field is corrupted (which is the modal failure
    mode for OCR misreads).
  - **The rejection logs include `dropping <field>=<value> too`
    as explicit telemetry.**  This is unusual and good
    observability — most defenses don't expose their collateral
    damage this cleanly.  Engineers reading `dropping runs=22
    too (whole-row invalidation)` see exactly what truth was
    sacrificed for the defense.  Worth preserving this log
    semantics when the field-level rejection fix lands — the
    new behavior should still emit a similar telemetry line
    when a rejected row contains accepted-able fields, e.g.
    `accepted runs=22, rejected balls=35→17`.  Future debugging
    benefits from continuing to see what was sacrificed and
    what was preserved.

  **Decay-via-scoring assumption empirically refuted.**  The
  prior mental model held that phantom +N decays when the
  phantom holder scores legitimately past the inflated value.
  Today's F1767+ data overturns this: when Dube actually scored
  19→22 in real play, every Scout read of the truth was
  rejected because the balls field also gave away the phantom.
  **Truth was rejected; the phantom was reinforced by every
  legitimate scoring event rather than eroded by it.**  The
  conditions for decay-only correction to work are jointly:
  (1) phantom holder faces enough balls to score past the
  phantom runs value, AND (2) the truth state's balls value is
  close enough to the phantom's balls value to not trigger
  ball-regression rejection.  Both conditions failing
  simultaneously (Dube's case) means decay doesn't operate at
  all — window closes only on dismissal.  This explains the
  Gaikwad +4 case (decayed because his runs caught up while
  balls stayed close) vs the Dube +9 case (didn't decay
  because balls diverged).  The "decay handles the common case"
  assumption was a comfort that the data has now revoked.

  This argues for two distinct fix shapes:

  - **Bounded fix: field-level rejection.**  Rework the
    rejection unit so only the suspicious field (runs) is
    discarded, while other fields from the same proposal
    (balls, status) can still be accepted on their own merits
    if they pass their respective consistency checks.
    Mechanical scope (~20-40 lines in the rejection path),
    eliminates the collateral cost without changing the
    detection logic.  Doesn't address the root phantom
    commit, but at least stops the secondary damage.
  - **Architectural fix: phantom-signature gating at admission.**
    Implement signatures 1-5 above so the original phantom
    commit never happens, eliminating the rejection cascade
    entirely.  Larger scope (multi-signature framework + ring
    buffer + provisional-admission state machine), addresses
    the root cause rather than the secondary damage.

  Both have merit.  The bounded fix is recommended as the
  immediate-relief slice (next-session-eligible); the
  architectural fix is the proper long-term answer and is
  already scoped above as the phantom-signature design note.

  **EXTRAS-INF telemetry already provides signature-4 data,
  just ungated.**  At F732 (16:05:18), pipeline emitted
  `[EXTRAS-INF] wkts=3: score=30 - bat_sum=47 = extras=0` — i.e.
  bat_sum (47) exceeds score (30) by 17 runs.  This is signature
  4 (cross-batter sum-check) firing with full information; the
  log line records the impossibility but doesn't gate the
  underlying batter values.  Same as the F53 `extras=4 after a
  single wide` case from the score phantom.  Both `[EXTRAS-INF]`
  log emissions are direct admission-time evidence that
  signature 4 is implementable today by routing the existing
  computation into a guard rather than just a log.

  **Structural gap in the runs-monotonic guard (called out
  2026-04-26 post-Brevis):** the guard correctly rejects
  regressions but doesn't distinguish "this proposal is wrong
  because it regresses from real state" from "this proposal is
  wrong because it inflates from a phantom."  Once the phantom
  commits, every legitimate value gets rejected as regression,
  locking in the inflation permanently — which is exactly the
  Brevis-stuck-at-12(13) and Gaikwad-stuck-at-14 mechanism.  The
  bat-runs reconciler (P1) detects the divergence post-commit;
  this entry is about preventing the commit in the first place.

  **Design note: phantom signatures worth detecting at
  admission time.**  Before committing a proposed integer-field
  change under `_post_event_grace`, check for these three
  signatures and downgrade the proposal to "suspicious /
  provisional" requiring stronger evidence (e.g. 2-frame
  consensus, witnessed event of matching magnitude, or
  cross-field consistency):

  1. **Recently-rejected match.**  The proposed value matches a
     value already rejected on a recent frame (within last N
     frames) — strong signal that the same misread is
     re-asserting itself.  Maintain a small ring buffer of
     recently-rejected proposals per field; on a fresh proposal,
     check membership before accepting.
  2. **Non-canonical-context match.**  The proposed value
     appeared in a recent graphic overlay, info-panel, or
     between-innings stats panel (i.e. tag != SCOREBOARD or
     `_INFO_PANEL_KEYWORDS` matched on a recent frame).  Today's
     F786 Jason Holder career graphic showed `WICKETS 54
     ECONOMY 8.8` — if those numerals had bled into the
     subsequent strip read, this signature would catch it.
     Cross-references Fix 8's defense layer.
  3. **Digit-confusion patterns.**  The proposed value differs
     from prior accepted state by a single-digit substitution
     in known-confused pairs (`1↔5`, `4↔1`, `0↔O↔D`, `12↔14`,
     `8↔3↔B`).  Today's two phantoms both fit: F52 was `1→5`,
     F656 was `14→12`.  A small heuristic table of known OCR
     confusions on the digit alphabet, flagged when the delta
     is exactly one digit position.
  4. **Cross-batter sum-check at admission time.**  Newly-
     arrived batters have no prior baseline so signatures 1-3
     don't apply (instance-3 Dube case: a name-figure swap
     committed +17 because the monotonic guard had nothing to
     reject against).  Cross-batter consistency is the right
     admission-time signal here: if `proposed_bat1_runs +
     bat2_runs + extras > score_total`, reject.  Today's Dube
     case would have been caught: proposed Dube 18 + Gaikwad
     18 + extras (~5) = 41, but score was 38 — a 3-run
     impossibility.  Same invariant as the bat-runs reconciler
     (P1) but applied at admission time rather than post-
     commit.  Cheap (4 fields, one comparison); composes with
     signatures 1-3 to cover both established-batter and
     newly-arrived-batter cases.
  5. **Name-figure swap detection.**  Both instance-2 (Brevis)
     and instance-3 (Dube) involved Scout transposing two
     batters' figures — the established batter's value got
     attributed to the new batter's name (and vice versa,
     creating a regression on the established side that the
     monotonic guard caught).  Detect the pattern explicitly:
     if a proposed update *both* regresses bat1 AND inflates
     bat2 in the same frame, reject the entire frame's
     batter-figure update (require fresh consensus).  The
     monotonic guard already catches the bat1 regression; this
     extends the rejection to bat2's matching inflation, which
     would otherwise commit silently.

     **Production confirmation 2026-04-26 F1842 (CSK vs GT,
     16:57:16):** Scout strip read `Kartik 48(4) | Gaikwad
     48(2)` — exact name-figure swap (Gaikwad's true value 48
     attributed to Kartik, Kartik's true value 6/3 partially
     attributed to Gaikwad as 48/2).  Pipeline correctly
     rejected the swap: AFTER state preserved
     `Gaikwad 48(48), Kartik 0(0)` (Kartik's truth at that
     moment was 0(0); the swap would have inflated him to 48
     while regressing Gaikwad to 4).  The runs-monotonic guard
     caught Gaikwad's runs regression `48 → 4` and discarded
     the whole row via whole-row invalidation, which incidentally
     also blocked Kartik's phantom inflation to 48.  Validation
     point: signature-5's pattern is real and recurring; the
     design note's signatures framework is **descriptive of
     observed production failures, not speculative**.  The
     current defense (runs-monotonic guard with whole-row
     invalidation) does catch this signature when the
     established batter has a non-zero baseline; a dedicated
     signature-5 detector would also catch it when both
     batters are early-innings (no established baseline to
     trigger the regression check).

  Provisional admission semantics: tag the value as
  `_provisional=True` (mirroring the FOW `_unwitnessed`
  placeholder pattern), accept into state but require
  retroactive confirmation on the next frame; if not
  confirmed, roll back.  This is closer to the FOW placeholder
  pattern than the consensus override — provisional admission
  with retroactive confirmation.

  Implementation can wait until the consensus override
  architectural piece (P0, ~2-3h) since both layers are about
  "wrong values that committed and can't be corrected" —
  consensus override is the recovery slice, this is the
  prevention slice.  Together they're defense-in-depth.
  ~30-50 lines for the signature detector + ring buffer; the
  provisional rollback layer is the substantive piece (~50-100
  lines).
### P1 cluster: Phantom +N recovery-time quartet (was triad, expanded 2026-04-26)

**Four** small fixes that compose to address the phantom +N class
at prevention, detection, correction, and **release** layers
respectively.  Each individually small (~5-25 lines); together
they form the bounded counterpart to the architectural consensus
override (P0).  Captured as a cluster so future implementation
treats them as a coherent unit rather than four independent fixes.

> **Promoted from triad to quartet 2026-04-26 17:15 IST** after
> the FRAME_POISONED + POISON-STREAK guard self-released the
> over-18 stuck window in 90s (F2240 → F2265, 5-frame consensus).
> The architectural contrast with the runs-monotonic guard's
> 41:50-minute Dube lock-in produced the design principle: **every
> guard should have both detection AND release semantics**.  Layer
> 4 below brings the runs-monotonic guard up to the same standard.

1. **EXTRAS-INF admission gate** — **STAGED 2026-04-26
   18:55 IST as Fix 11**.  Final scope was ~150 lines of
   source (not the original ~10 estimate — the gate had to
   live pre-commit at `apply_scorer_decision` rather than be
   an in-place conversion of the post-commit `[EXTRAS-INF]`
   block at line 4540, which stays as diagnostic).
   **Prevents** batter-side sum-violation phantoms from
   entering state.  **Honest scope:** Fix 11 is batter-side only;
   score-side phantoms (F52/F53 shape) are handled by **Fix 15**
   `[SCORE-INF-GATE]` (Layer 1.5 advance/floor — see staged grid).
   **Does not** catch name-figure swap
   phantoms (signature 5) — those need separate layers.
   F732 (Brevis-era) and F2408 (Hosein +21) production
   fixtures both confirmed caught.  See "STAGED" snapshot
   at top of this file and the standalone P1 entry below
   for the full scope claim and the test-fixture matrix.
2. **Bat-runs reconciler detection** (~10-15 lines) — sum
   invariant `bat_runs + extras ≤ score_total` checked on
   every commit cycle.  **Detects** divergence post-commit
   and surfaces for investigation when prevention fails.
   Detection-only; correction handled by item 3.  Detail
   entry below.
3. **Capping-batters reset threshold** (~5-25 lines depending
   on path) — replace the too-lax `if runs > score` reset
   condition in `validate_state_consistency()` with a
   hybrid last-write-tracking + iterative-correction
   approach.  **Corrects via sum-check failure path** when
   total inflation exceeds bounded threshold.  Today's data:
   199 cap warnings fired with **zero resets** in 31 min —
   detection works, correction is structurally impossible.
   Detail entry below.
4. **Rejection-consensus release on runs-monotonic guard**
   (~15-25 lines, **NEW 2026-04-26**) — mirrors the
   POISON-STREAK pattern that already exists for FRAME_POISONED.
   When the runs-monotonic guard rejects the same proposed
   value N times consecutively for a given batter, accept it
   as the new truth and force-set the tracker.  **Releases
   via rejection-consensus path** when phantom commit was the
   bug rather than truth being the bug.  Validation evidence:
   POISON-STREAK released today's stuck-window in ~90s with
   N=5; the runs-monotonic guard held Dube phantom for 41:50
   with 357 rejections of identical truth values (`runs=22`
   on 20+ consecutive frames F1767-F1812).  Same template,
   different implementation completeness.  Detail entry
   below.

**Architectural principle (called out 2026-04-26):**  every
guard with detection semantics should have a corresponding
release mechanism.  Detection without release converts
"phantom commits" (which is bad) into "phantom locks in
permanently" (which is worse — the guard *prevents* recovery).
FRAME_POISONED has POISON-STREAK release.  ROTATION-counter
guards have wicket-event release.  BOWLER-STALE has consensus
re-arming.  The runs-monotonic guard has detection only and
this is the architectural defect today's Dube case exposed.
Future guards added to the codebase should be evaluated against
this principle: "if this guard rejects truth, what causes it to
let go?"  Without an answer, the guard is incomplete.

**Why the quartet framing matters:**  today's CSK vs GT match
demonstrated all four layers as broken, absent, or asymmetric:
F52 phantom admitted (no admission gate / Layer 1 absent),
Brevis/Dube divergences not flagged by any internal cross-check
(no reconciler / Layer 2 absent), 199-fires-0-resets cap
mechanism (broken correction / Layer 3 broken), 357 rejections
of identical truth without release (no release / Layer 4 absent).
The inflation persisted for 31+ minutes because every layer of
the quartet was missing or non-functional.  Even one of the four
working would have bounded the user-visible window substantially:

- With (1) alone: phantom never commits → no rejection cascade.
- With (3) alone: phantom commits but resets within 1-2 frames
  of the cap warning → ~3-5 second user-visible window.
- With (2) alone: divergence is logged for postmortem but UI
  remains wrong until decay completes.
- With (4) alone: phantom commits, holds until N consecutive
  truth reads accumulate, then releases.  At N=5 the Dube
  window would have closed at ~F980 instead of F1813 (35
  minutes earlier).  At N=10, ~F985 (still ~35 min earlier).

Recommended landing order if shipped together: **(1)+(3)+(4) as
the high-leverage trio**, (2) follows as observability afterwards.
Combined cost: ~30-50 lines plus tests, single commit.  Layer 4
is small enough and structurally analogous enough to POISON-STREAK
that it belongs in the same shipment as Layers 1 and 3.

**Sum-check correction vs rejection-consensus release — different
mechanisms for different failure modes:**

| Layer | Trigger | Failure mode addressed |
|---|---|---|
| 3 (sum-check correction) | `bat_sum > score + 10` invariant fires | Phantom inflated *total* beyond legitimate bound; identifies which batter to reset via last-write tracking |
| 4 (rejection-consensus release) | Same value rejected N times consecutively for one batter | Scout consistently reads truth; pipeline keeps rejecting; release accepts the rejected value as new truth |

The Dube case would have been caught by either layer if
implemented.  Layer 3 would have flagged the 199 cap warnings
into actionable resets; Layer 4 would have accepted Scout's
repeated truth reads after N rejections.  Both layers shipping
gives true defense-in-depth across distinct failure shapes.

**Layer 4 implementation paths considered:**

- **Path 1 (per-field, recommended for this slice):** add a
  `rejected_proposals` ring buffer to each batter's card; when
  the same value gets rejected N consecutive times, accept it
  as the new truth and force-set the tracker.  ~15-25 lines,
  scoped specifically to the batter-runs case.  Direct mirror
  of POISON-STREAK template.  Threshold tuning starts at N=5
  (POISON-STREAK precedent), then refine empirically against
  match data — N=8-10 is more conservative (fewer false
  resets, longer phantom windows), N=3-4 is faster recovery
  (more aggressive, risk of legitimate transient OCR misreads
  triggering spurious resets).
- **Path 2 (generalized, defer until consensus override):**
  build a reusable "rejection consensus" mechanism that any
  guard can plug into; each guard tracks its own consensus
  state; when threshold reached, the guard's release callback
  fires.  ~50-100 lines of architectural plumbing.  Composes
  with the consensus override P0 piece (which would be the
  cross-field correlation layer above per-field consensus).
  Closer to 2-3 hours.

Path 1 ships the immediate fix.  Path 2 builds the architectural
foundation that the consensus override would use anyway.  These
operate at different layers and don't make each other redundant:
Path 1 handles single-field phantoms (Dube +N), the future
generalized version (Path 2 + consensus override) handles
cross-field corruption (state poisoning that affects multiple
fields simultaneously).  Recommend Path 1 for the immediate
quartet shipment; Path 2 falls out of the consensus override
work later.

**Composes with** the state-recovery consensus override (P0
architectural, 2-3h) — that piece addresses the broader class
of "any guard rejecting truth without recovery"; the triad is
the bounded subset specifically for monotonic-counter phantoms.
Triad ships first as the cheap slice; consensus override is the
catch-all for cases the triad doesn't cover (e.g., wickets,
bowler attribution).

**Success metrics framework (for pre-deploy baseline and
post-deploy validation):**  the triad's value can be quantified
with four metrics that are derivable from existing telemetry,
no new instrumentation needed.  Capture these on a few baseline
matches before shipping; the same metrics post-deploy show the
recovery-time reduction.

| Metric | Telemetry source | Today's CSK-vs-GT data point (FINAL — Dube dismissed F1813) |
|---|---|---|
| Rejection-of-truth count per match | `Batter '<name>' runs regression N→M (-X) rejected` and `balls regression ... whole-row invalidation` count, where the proposed value matched CB ground truth at the same wall-clock | **357 for Dube alone** at dismissal (F1813); the run-up from F1767 onwards even logged the truth value Scout was reading: `dropping runs=22 too (whole-row invalidation)` × 20+ frames |
| Rejection rate **per Dube-read attempt** *(preferred unit)* | rejection count / number of Scout frames where Dube's runs were proposed | **~100%** in CSK-vs-GT — every Scout read of Dube during the 42-min inflation window was rejected.  Broadcast-cadence-independent; same lock-in property would manifest at any cadence |
| Cap warnings without reset | `[INVARIANT] Capping batters` count minus `[INVARIANT] <name> runs <N> > score <S> — reset` count (the latter is the actual reset log line; was 0 today) | **344 fires, 0 resets** across the entire Dube phantom window |
| Inflation duration in wall-clock time | First commit of phantom value → first frame where pipeline value matches CB ground truth (or phantom-holder dismissal closes the window) | **F975 (16:14) → F1813 (16:55:50) — 41 min 50s.**  Closed only by dismissal; never decayed |
| Inflation duration in **balls faced** by the phantom holder | Balls the phantom batter actually faced during the inflation window (decay only happens when phantom holder bats) | **Dube faced ~6 legal balls** during the 42-min window.  In the final ~5 min Scout was reading the correct `22(15)` value continuously but every read was discarded by whole-row invalidation.  Decay achieved: **0** |
| **Decay-via-scoring success rate** *(new metric, derived from F1767+ evidence)* | `truth-value commits` / `truth-value Scout reads` during inflation window | **0 / 20+ for Dube on F1767-F1812.**  Even when phantom holder scored legitimately (Dube went 19→22 in actual play), decay was blocked because the balls field gave away the phantom and whole-row invalidation discarded the runs increase.  This is empirical evidence that decay-only correction is structurally impossible under whole-row rejection — overturns the prior "phantom decays when holder scores" assumption. |

The "balls faced" metric is the **most meaningful unit** because
phantom decay only operates when the phantom holder legitimately
scores.  Lower-order batters or accumulators in the middle overs
can have very long phantom windows even when wall-clock time
isn't extreme — they just don't face many balls.  Dube's case
illustrates this: 70+ min of wall-clock inflation but only ~6
balls faced means decay-only correction has barely advanced.
The triad should reduce the wall-clock metric to seconds (admission
gate prevents commit) or single-digit-frames (cap reset fires
within 1-2 frames of the cap warning).

**Why rejection-rate-per-read-attempt is the preferred unit
over rejections-per-minute:**  the raw rejection count scales
with broadcast cadence (more close-ups → more Scout reads → more
rejections), not with the underlying lock-in mechanism.  Today's
235 in 25 min was driven partly by Gaikwad's scoring streak
producing dense between-ball close-ups of both batters.  The
underlying lock-in property is constant: 100% of Scout reads of
the inflated batter get rejected by the runs-monotonic guard.
Pre-fix vs post-fix comparison should use the rate, not the
absolute count, to avoid being noisy on broadcast-intensity
variation between matches.

Recommended: capture these metrics on the next 2-3 baseline
matches before triad lands, again on the first match post-deploy.
The delta is the empirical case for the work.

---

- **P1** Bat-runs reconciler against scoreboard total — detect
  internal-state inflation **without** an external API.  After
  the F52 phantom-+4 cascade, Gaikwad's individual tally drifted
  to UI=14 vs CB=10 (visible damage).  The current
  `runs-monotonic` guard correctly accepts a real boundary
  arriving at the same moment as a phantom (good) but provides
  **no recovery path** when no real event fires after the
  phantom — inflation persists permanently.  This is the same
  failure-mode class the state-recovery consensus override (P0
  architectural, ~2-3h, still queued) addresses; this entry is
  the cheaper *detection* slice that surfaces divergence even
  without the heavy recovery machinery.

  Detection invariant (pipeline-internal only):
  `sum(batting_card[*].runs) + extras_total ≤ score_total`
  for the current innings — equality when both batters' tallies
  are observed; `<` only by the unobserved-batter's runs (rare
  edge: incoming batter not yet on strip).  If the sum **exceeds**
  the score total, something inflated.  Detect with a periodic
  check (e.g. every accepted score commit), emit
  `[BAT-RUNS-RECONCILE] inflated bat_sum=X extras=Y total=Z
  delta=+N batter_candidates=[...]` for investigation.

  Correction is harder (which batter to deflate? — over-rollover
  attribution; recent-ball tokens; who was on strike per FOW
  history).  For now scope is detection only; correction can be
  layered on later or routed through the consensus-override
  recovery path.  Witnessed-event check (FOW-style `_witnessed=
  True` pattern) is an alternative defense for the *commit* path
  but doesn't help with already-corrupted state — this reconciler
  is complementary, not a replacement.

  ~40-60 lines in `test_pipeline.py` near the score-commit /
  ball-event hook; emits a single warn with structured fields for
  parity_monitor to surface.  Worth wiring before next match.
- **P1 — STAGED 2026-04-26 18:55 IST as Fix 11** Convert
  `[EXTRAS-INF]` cross-batter sum-check from log-only to
  admission gate — **shipped as Fix 11**.  Pre-commit gate
  at `apply_scorer_decision` (NOT at the existing post-
  commit `[EXTRAS-INF]` site at frame-loop line 4540, which
  stays as diagnostic).  See "STAGED" snapshot at top of
  this file for full Fix 11 entry.

  **Scope refinement vs. original framing (correction worth
  preserving):** the original "convert log-only to gate"
  shorthand was structurally inaccurate — line 4540 reads
  *post-commit* state and reconciles `extras["total"]`
  AFTER batter writes have committed.  By the time line
  4540 fires, the phantom is already in state.  A real
  admission gate has to live *pre-commit*, which means
  inside `apply_scorer_decision` (called at frame-loop
  line 7027) before the batter_ups loop runs.  Fix 11
  adds the gate as a *sibling* mechanism, not a conversion
  of the existing block.  The line-4540 reconciler stays
  in place for clean-frame extras inference.

  **Honest coverage scope (verified against today's
  fixtures, 2026-04-26 CSK vs GT):**

  | Phantom shape | Layer 1 catches? | Production fixture |
  |---|---|---|
  | Batter-side sum violation (proposed `bat_sum > score`) | ✅ Yes | F732 (Brevis-era +17 excess), F1276 (+25), F2400 (+1 residual), F2408 Hosein +21 (+22) |
  | Score-side phantom (score inflated **or** misread-low vs `bat_sum+extras`) | ✅ **Partial** (Layers 1.5 cap + floor, 2026-04-28) | **F52/F53**-class +N cap; **inverse** misread-low floor (`proposed < bat_sum+extras`); name-swap / graphic class may still need other layers |
  | Name-figure swap (rows misattributed, total sum stays valid) | ❌ No | F1842 signature 5 (Kartik 48(4) ↔ Gaikwad 48(2)) |

  Layer 1 is therefore a **subset** of phantom +N coverage
  — specifically the batter-side sum-violation slice.  The
  triad cluster's full coverage requires:
  - **Layer 1 (this fix):** batter-side sum-violation prevention
  - **Layer 1.5 (shipped 2026-04-28):** `[SCORE-INF-GATE]` —
    **(a)** unexplained single-frame score advance vs bat delta +
    extras headroom; **(b)** **floor:** reject `proposed_score <
    bat_sum + extras["total"]` (with cold-start / innings-transition
    suppression).  Wired to telemetry analyzer + Bundle-B/C
    `15_score_inf_floor` rollup.
  - **Signature 5 detection (separate mechanism):** name-
    figure swap detection at the name-resolution layer
  - **Layer 2 (still queued):** post-commit bat-runs
    reconciler — detects whatever Layer 1 misses
  - **Layer 3 (still queued):** capping-batters reset —
    corrects when detection fires
  - **Layer 4 (still queued):** rejection-consensus release
    — releases lock-in when truth is rejected post-phantom

  **Implementation choices recorded for v1:**
  - **Hard-reject all batter updates this frame** (Option 1
    from original framing) — per-batter rejection deferred
    to v2 because the heuristics for identifying *which*
    proposed value is the phantom are exactly the heuristics
    that failed to prevent the phantom; one frame's worth of
    legitimate concurrent updates lost per gate fire is the
    acceptable trade-off.
  - **`known_extras = 0`** in the formula (strict
    `bat_sum > score`) — tighter version using current
    `extras["total"]` as a floor deferred to v2 due to
    feedback-loop risk with the post-commit reconciler
    (which itself derives extras from possibly-corrupted
    state).
  - **Completeness gate** (mirroring existing
    `_ei_dismissed_count == _ei_wkts_i` invariant):
    abstain when dismissed-batter count doesn't match
    wickets OR any dismissed/active runs are unknown.
    Prevents false positives during transient states
    (wicket fired but FOW row not yet upgraded).
  - **WARN-level telemetry** (`[EXTRAS-INF-GATE]`) so
    fires surface in standard monitoring without grep
    tuning, matching `BOWLER-STALE` and `FRAME_POISONED`
    rejection severity.
  - **`changes.append("EXTRAS-INF-GATE:bat_sum=X>Y")`** —
    matches existing `CORRECTION_BLOCKED:` pattern, enables
    parity_monitor counting per match for the success-
    metrics framework (phantom-admission-rate-per-match).

  **Hosein verification result (the unknown going into
  implementation):**  F2408 BEFORE state was score=154,
  wickets=7, Gaikwad 70(59), Hosein 0(0), dismissed_sum=85
  (per F2400 EXTRAS-INF: bat_sum=155 = 70+0+85).  With
  Hosein 21 proposed: `bat_sum = 85 + 70 + 21 = 176 > 154`
  (excess=22).  **Layer 1 catches Hosein +21 cleanly.**
  Test fixture `test_fix11_gate_hosein_f2408_production_replay`
  asserts exact excess=22 detail.

  Composes with the architectural phantom-signature framework
  (this is signature 4 from the design note above) and
  cross-references the **bat-runs reconciler** (Layer 2,
  still queued) which is the recovery-time slice for the
  same invariant.
## P1: Post-wicket `sb._inn` slot rotation — STAGED as Fix 10 (2026-04-26)

**Status:** **STAGED 2026-04-26 18:08 IST as Fix 10 in
`scoreboard.py`** (Path A — centralized hook at `_add_fow`'s
`_witnessed=True` stamp).  All 285 tests in
`test_recent_fixes.py` pass (10 new Fix 10 tests added,
covering all five behavioural cases plus end-to-end auto-
dismiss / dismiss_batter integration).  Awaits inter-match
seam restart for live validation against the next post-
wicket window.

**Final root-cause diagnosis (after source dive):** The
"stuck non_striker" class is the symptom of a **multi-
callsite slot-clear gap**.  Five distinct callsites in
`scoreboard.py` flip `batting_card[name]["status"] = "out"`,
but only **one** of them (`dismiss_batter`, line 2788) also
clears `_inn["striker"]` / `["non_striker"]`:

| Callsite | Sets `status="out"` | Calls `_add_fow` | Clears `_inn` slots |
|---|---|---|---|
| `dismiss_batter` (line 2788) | yes | yes (line 2795) | **yes (lines 2800-2803)** |
| `_auto_dismiss_for_new_batter` main (line 1528) | yes | yes (line 1530) | **NO** ← gap |
| `_auto_dismiss_for_new_batter` re-assert (line 1470) | yes | no (FOW already exists) | **NO** ← gap |
| `validate_state_consistency` Inv-2 (line 3091) | yes | no | **NO** ← gap |
| `validate_state_consistency` Inv-3 (line 3124) | yes | no | **NO** ← gap |

The dominant production path in CSK-vs-GT 2026-04-26 was
`_auto_dismiss_for_new_batter` (the broadcast surfaced new
batters via extractor before the broadcast graphic landed,
so dismissals committed via the auto-path rather than
`dismiss_batter`).  That path bypassed slot-clear entirely,
leaving the dismissed name lingering in `_inn["non_striker"]`
for the rest of the over and triggering the 88 / 443+ /
240+ defensive cascade fires per stuck-window.

**Fix as shipped (Fix 10, Path A — centralized at `_add_fow`):**

Rather than touching each of the five callsites, the fix
hooks the rotation logic at `_add_fow`'s **`_witnessed=True`
stamp** — the canonical "wicket confirmed" event.  Both
stamp sites (placeholder upgrade at line 2557, new-entry
creation at line 2622) invoke the new helper
`_post_witnessed_dismissal_slot_rotation(batter)` which
implements the four-case behaviour:

  1. **Striker dismissed only** → rotate non_striker into
     striker slot, non_striker = None pending new-batter
     admission.  Mirrors typical post-wicket broadcast
     state at end-of-over and converges to the correct
     mid-over state within 1-2 strip reads.
  2. **Non_striker dismissed only** → non_striker = None,
     striker unchanged.  Run-out at the non-striker end is
     the most common path here.
  3. **Dismissed name in neither slot** (e.g. cold-start
     placeholder upgrade for an early wicket) → no-op.
  4. **Anomaly (both slots)** → defensive double-clear
     with WARN log; covers prior collision states Fix 5
     didn't catch.

New telemetry: `[POST-WICKET-ROTATION] striker '<X>'
dismissed → rotated non_striker '<Y>' into striker slot;
non_striker cleared pending new-batter admission.` (and
analogous variants for the other three cases).

**Coverage scope:**

Covers the **primary dismissal flow** (rows 1, 2, 3 in the
table above): both `dismiss_batter` and
`_auto_dismiss_for_new_batter`'s main path route through
`_add_fow`, so the hook fires.  The
`validate_state_consistency` resurrection-demote paths
(rows 4 and 5) do NOT call `_add_fow` (the FOW entry
already exists from the original witnessing); for those
paths the slot would have been cleared at the *original*
witnessing when this hook first ran.  If a resurrection
re-populates the slot before validate demotes it back,
the slot will not be re-cleared — filed as a follow-up
under the **"Complete the SM-cutover"** architectural
item (no production damage observed today; rare path).

**Composition with existing defenses:**

  * `dismiss_batter`'s explicit clear (lines 2800-2803)
    becomes a no-op because the hook fired earlier inside
    `_add_fow` at line 2795.  No double-clear corruption
    (verified by `test_fix10_dismiss_batter_path_compatible_with_hook`).
  * Fix 5 (STRIKER-COLLISION guard) stays as backstop;
    expected post-fix fire count approaches 0 because the
    upstream rotation gap closes.
  * WS-SCRUB defensive layer stays as backstop; expected
    post-fix reject count approaches 0 for the same reason.
  * Fix 7 (WS-PROJECTION-FALLBACK) unchanged; the cleared-
    slot transient state (None pending new-batter
    admission) is identical to FOW's `_unwitnessed`
    placeholder pattern — known-empty state pending real
    evidence, which Fix 7 already handles correctly.

**Validation evidence (from logs):**

Pre-fix per-wicket cost (CSK-vs-GT 2026-04-26):

  * Sarfaraz dismissal (W3, 4.4 ov, F1670): 88 SM
    rewrite attempts over ~6 minutes, all rejected by
    WS-SCRUB.
  * Dube dismissal (W5, 15.3 ov, F1813): 443+
    STRIKER-COLLISION fires by F2017 (Fix 5 firing
    actively).
  * Overton dismissal (W7, 18.6 ov, F2392): 240+
    WS-SCRUB rejects in ~3 minutes (~50 fires/min)
    until AUTO-SWAP at F2503 closed the window.

Post-fix expectation: rotation succeeds at the
`_witnessed=True` stamp, downstream defensive layers stay
silent.  Live validation deferred to next match's wicket
events.

**Coverage gap discovered 2026-04-26 LSG-vs-KKR (post-deploy,
analyzer-surfaced):**

The new telemetry harness reported **0
`POST-WICKET-ROTATION` fires on the witnessed Powell wicket
(W4)** despite `STRIKER-COLLISION` events accumulating.
Source dive plus log-trace analysis pinpointed the cause:

  * **F179 (20:06:07):** `_unwitnessed` placeholder W4 added
    when broadcast strip registered `wickets→4` without a
    batter name.
  * **F258 (20:08:09, ~2 minutes / 79 frames later):**
    `[FOW] Upgraded placeholder W4: Rovman Powell at 31/4
    (6.1) (was _unwitnessed)`.
  * At F258, `sb._inn["striker"]` is `None` and
    `sb._inn["non_striker"]` is `Cameron Green` — Powell is
    no longer in either crease slot because the broadcast had
    already moved past Powell's tenure during the 79-frame
    gap.

**Hypothesis 1 (`_witnessed` stamp bypass) → ruled out.**
Source confirmed at `scoreboard.py:2697`: the placeholder-
upgrade path DOES call `_post_witnessed_dismissal_slot_
rotation()` after stamping `_witnessed=True`.  The hook
fires; it just no-ops.

**Hypothesis 2 (slot-membership check) → confirmed, with
nuance.**  Line 2842 (`if not (striker_dismissed or
non_striker_dismissed): return`) returns silently — Case 3
of the docstring (*"dismissed name in **neither** slot:
no-op"*).  The docstring framed Case 3 as legitimate-only
("cold-start back-fill of historic wickets where current
crease state reflects a much later innings stage").  Powell
shows it ALSO fires for **recent** wickets when the
placeholder→witness gap (~2 min in production) outlives
the crease state.  The original test fixtures (CSK-vs-GT
Sarfaraz/Dube/Overton) all had crease slots populated at
the moment of the witness — Powell is the first observed
case of a real-time but delayed witness arrival.

**Related deeper gap (second-order finding):**
`_add_fow` does NOT update
`batting_card[dismissed].status = "out"` on the
placeholder→witness upgrade — only `dismiss_batter`
(line 1558) and `_auto_dismiss_for_new_batter` (line 1500)
set the status flag.  After the F258 upgrade Powell stays
in `batting_card` with status `batting`, which is why the
phantom `Powell 14(56)` BEFORE_bat2 line continued
appearing in DETAIL rows for several minutes after F258.
This compounds with the rotation-hook silence: even if
the hook had no slot to clear, the downstream UI/payload
would still be emitting Powell as an active batter.

**Test fixtures:**

  * `test_fix10_powell_f179_f258_placeholder_upgrade_with_
    drifted_slots` (added 2026-04-26): reproduces the F179
    `_unwitnessed` placeholder + F258 upgrade with
    striker=None, non_striker=Green, and asserts the current
    no-op behaviour.  When the coverage-gap fix lands, the
    assertions flip to the new expected behaviour.
  * Production fixture preserved: F179→F258 sequence in
    `pipeline-2026-04-26-195909-lsg-kkr-fix12-v6-validation.
    log` (lines 2076-2237) for trace-based verification.

**Fix scope (depending on chosen path):**

  * **Path D (broaden hook coverage to active-batter set,
    ~10-15 lines):** extend
    `_post_witnessed_dismissal_slot_rotation` to also clear
    `batting_card[dismissed].status` and remove
    `dismissed` from `active_batters` when it's not in
    crease slots but IS in the active set with status=
    `"batting"`.  This converts the no-op into a card-only
    update, closing both the slot and the batting-card
    propagation gap in a single hook.
  * **Path E (route witnessed FOW upgrades through
    `dismiss_batter`, ~5-10 lines):** call
    `dismiss_batter()` from inside `_add_fow`'s placeholder-
    upgrade branch (after the witness stamp) to ensure all
    canonical dismissal-side effects fire (status flip, slot
    clear, partnership reset).  Cleaner architecturally but
    requires care to avoid recursive `_add_fow` invocation
    via `dismiss_batter`'s own callsite.
  * **Path F (architectural — single canonical dismissal
    routine):** restructure so that all three dismissal
    entrypoints (`dismiss_batter`, `_auto_dismiss_for_new_
    batter`, `_add_fow` upgrades) converge on a single
    private `_apply_dismissal()` that updates FOW, card
    status, slots, and partnership atomically.  Larger
    scope but eliminates the entire class of partial-
    propagation bugs.

**Recommendation:** Path D as the next-session bounded fix
(narrowest scope, directly addresses the analyzer-surfaced
gap, no risk of recursive-call surprises from Path E).
Path F gets bundled with the SM-cutover architectural item.

**Connection to the live `striker-collision-stuck` P0
(filed earlier today):** the rotation-hook silence at F258
is plausibly causally upstream of the F704 collision
lock-in.  If Powell's dismissal had cleared the
`batting_card` and the active-batters set at F258, the
subsequent strike-rotation logic at F704 would have had a
clean state to install Rinku Singh into the non_striker
slot — instead it installed `Cameron Green` again into
both slots (collision), which Fix 5 then correctly
refused to heal.  Worth chasing the upstream rotation bug
(Path B in the collision-stuck entry) AFTER Path D lands —
the post-Path-D state may resolve the collision-stuck
symptom without needing the heal-on-collision patch.

**Tests added (10 functions, ~30 sub-checks):**

```python
test_fix10_striker_dismissed_rotates_non_striker_into_striker
test_fix10_non_striker_dismissed_clears_non_striker_only
test_fix10_run_out_at_striker_end_handled_via_name_match
test_fix10_dismissed_name_in_neither_slot_is_noop
test_fix10_anomaly_both_slots_dismissed_clears_both
test_fix10_placeholder_upgrade_path_also_fires_hook
test_fix10_powell_f179_f258_placeholder_upgrade_with_drifted_slots
test_fix10_auto_dismiss_path_clears_slot_via_hook
test_fix10_dismiss_batter_path_compatible_with_hook
test_fix10_helper_method_exists_on_scoreboard
test_fix10_hook_call_present_in_source
```

---

- **P1** Post-wicket `sb._inn` non_striker rotation — bounded fix
  for the Sarfaraz-stuck-as-non_striker class.  Caught
  2026-04-26 CSK vs GT after wicket-3 (Sarfaraz Khan dismissed
  at 26/3, 4.4 overs): `sb._inn["non_striker"]` was never
  rotated to the surviving active batter (Brevis), so SM kept
  proposing `non_striker=Sarfaraz Khan` for ~88 frames
  (~6 minutes wall-clock), each correctly rejected by WS-SCRUB
  (`reason=status_out`) and Fix 5 (when collision arose).  The
  defenses prevented damage but the loop never auto-resolved —
  same "no recovery path" failure mode as the phantom-+N
  inflations.

  **Per-wicket cost quantified across THREE events in one match
  (CSK vs GT 2026-04-26):** the pattern is *per-wicket overhead*,
  not edge-case behavior.  Confirmed firing on every wicket
  observed.

  | Wicket | Outcome | Defensive overhead |
  |---|---|---|
  | Sarfaraz dismissal (W3, 4.4 ov) | `non_striker` stuck for ~88 frames / ~6 min until next state change | 88 SM rewrite attempts, all correctly rejected |
  | Dube dismissal (W5, 15.3 ov, F1813) | `non_striker` *still* stuck post-Kartik-arrival; Fix 5 firing actively | 443 STRIKER-COLLISION fires by F2017 (≥24 of which post-Dube-wicket); rate climbing |
  | Overton dismissal (W7, 18.6 ov, F2392) | `striker='Jamie Overton'` rejected via WS-SCRUB for entire post-dismissal window | **240+ WS-SCRUB rejects by F2502** in ~3 min (~50 fires/min sustained); window closed only by AUTO-SWAP at F2503 (innings transition) |

  Three distinct wickets, same pattern, same defensive load.
  Three-for-three on observed wickets in this match means "every
  wicket triggers the gap" is the right model rather than
  "edge cases trigger the gap."

  Extrapolating: a typical T20 innings with 6-10 wickets per
  side would generate **roughly `wickets × 100-400` collision
  fires** per match in defensive overhead — 1200-8000 fires
  per match purely to compensate for the rotation gap.  Each
  fire is cheap individually (refusal log + no state change)
  but the volume signals the underlying rotation gap is firing
  on every wicket, not edge cases.  Today's match: **at least
  771 fires across three wickets** (88 + 443 + 240), and that's
  only counting frames before AUTO-SWAP closed each window.

  Path A (post-wicket `sb._inn` rotation hook below) would
  convert this from "Fix 5 catches every wicket's rotation
  failure" to "rotation succeeds, Fix 5 stays silent."  This
  matches the framing pattern from yesterday's BOWLER-STALE
  work: defensive layer doing its job is correct, but if the
  defensive layer is firing every wicket event, there is an
  upstream issue worth fixing.

  **Path A (bounded, ~10-15 lines).**  Add a hook at the wicket
  detection callsite: when a witnessed wicket fires for the
  current `sb._inn["striker"]` or `sb._inn["non_striker"]`,
  immediately overwrite that slot with the surviving active
  batter (whichever of `active_batting` is not the dismissed
  player).  Single test scenario: simulate FOW witnessed event
  for non_striker → assert `sb._inn["non_striker"]` updated to
  the surviving batter.  Telemetry: `[POST-WICKET-ROTATE]`
  `dismissed='X' new_non_striker='Y'`.

  **Path B (architectural, larger scope).**  SM-authoritative
  override of `sb._inn`: when SM has a valid striker/non_striker
  that disagrees with `sb._inn`'s stale value, write SM's value
  into `sb._inn`.  Connects to **striker-collision Path B**
  (full SM cutover, queued behind Fix 5/Path A from yesterday) —
  both pieces are about "make SM the canonical source for
  active-batter identity, retire the legacy `sb._inn` writes."
  Combined scope is the right place to land Path B; not worth
  doing as a one-off.

  Recommendation: ship Path A as the immediate-relief slice
  (next-session-eligible, single match-day's testing to
  validate); revisit Path B when the striker-collision Path B
  cutover is queued.  Prevents the user-visible "dismissed
  player shown as on-field" symptom we saw today via the Fix 7
  fallback layer.
- **P2/P3** `SQUAD_URL` hardcoded in `test_pipeline.py:585` — every
  match requires editing the source file and restarting.  Caught at
  match-3 launch when `team_a/team_b` came up `Rajasthan Royals /
  Sunrisers Hyderabad` from yesterday's match-2 squad URL.  Cheap fix:
  read from `argv[1]` or env var `SPORTSCOMM_SQUAD_URL`, fall back to
  the constant.  Saves ~1 minute and one restart per match;
  eliminates a foot-gun where someone forgets to update before the
  toss.  ~5 lines.
- **P2/P3** Cold-start mid-over batter ball-count attribution — at
  match-3 cold start (joined at 0.4), the first 4 balls were
  attributed to Gaikwad before the strip's striker-asterisk was
  detected, then striker flipped to Samson but the 4-ball history
  stuck on Gaikwad.  Cricbuzz had the ground truth (`Samson 0(5),
  Gaikwad 0(0)`).  Score / wickets / overs all correct; only per-
  batter balls are wrong, and the gap doesn't auto-close.  Fix
  candidate: scrape cricbuzz `live-cricket-scores/<id>` on cold start
  (already happening for SQUAD_URL anyway) and seed
  `batting_card[name].balls` if the broadcast strip parser hasn't
  yet locked the asterisk.  ~30-50 lines if we reuse the existing
  parity_monitor cricbuzz parser.

**Top of the next-session queue (genuinely ready, no blockers):**
- **P1 cluster: Phantom +N recovery-time quartet** (~40-75
  lines combined, single coherent commit) — **four** composing
  fixes for prevention + detection + correction + release of
  phantom +N inflations.  See "P1 cluster" section above for
  the detailed quartet framing (promoted from triad to quartet
  2026-04-26 17:15 IST after FRAME_POISONED + POISON-STREAK
  empirical contrast).  Highest-leverage bounded slice: closes
  the "no recovery path" gap demonstrated by today's 41:50-min
  Dube inflation persistence.
  - ~~(a) EXTRAS-INF admission gate (~10 lines)~~ —
    **STAGED 2026-04-26 as Fix 11** (final scope ~150
    lines source — see entry above; covers batter-side
    sum-violation slice only)
  - (b) Bat-runs reconciler detection (~10-15 lines)
  - (c) Capping-batters reset threshold, Path C hybrid
    (~10-15 lines)
  - (d) **Rejection-consensus release on runs-monotonic
    guard** (~15-25 lines, Path 1 per-field consensus,
    POISON-STREAK template, **NEW 2026-04-26**)
- ~~**P1** Post-wicket `sb._inn` non_striker rotation (Path A)~~ —
  **STAGED 2026-04-26 18:08 IST as Fix 10.**  Centralized
  at `_add_fow`'s `_witnessed=True` stamp covering both
  placeholder-upgrade and new-entry paths.  Five-case
  behaviour (striker-only / non_striker-only / neither /
  anomaly / run-out via name match).  10 new tests pass
  (285/0 total).  See "P1: Post-wicket `sb._inn` slot
  rotation — STAGED as Fix 10" entry above for full
  diagnosis and rollout details.
- **P1** Tighten `[INVARIANT] Capping batters` reset threshold
  in `Scoreboard.validate_state_consistency()` — **third
  broken recovery layer surfaced 2026-04-26**.  The invariant
  warning fires when `total_batter_runs > score + 10`, but
  the per-batter reset only triggers when an *individual*
  batter's `runs > score`.  In practice, a Dube-class +17
  phantom on a team total of 47 leaves Dube at runs=18 ≤
  score=47, so the reset never executes.  Today's match
  produced **199 cap warnings across 31 minutes (F673 → F1338,
  16:02-16:33), zero actual resets.**  Diagnostic shows the
  total-batter-runs-vs-score gap stays roughly constant at
  ~19-22 throughout the inflation window: phantom commits at
  16:02 (gap=19), Dube phantom at 16:18 (gap jumps to 27),
  settles to 21 with no recovery.

  **Fix:** change the per-batter reset condition from `if
  runs > score` to a magnitude-aware check.  Three
  implementation paths considered:

  - **Path A (cheap, single-write):** when total exceeds
    score+10, identify the batter whose `runs` was most
    recently updated and reset only that one to its previous
    known-good value.  Bounded scope.  Failure mode: if
    multiple batters have wrong values from cascading
    phantoms, this corrects only the most recent and leaves
    earlier ones untouched.  ~5-10 lines plus a
    `last_runs_update_frame` field on each card.
  - **Path B (proportional):** compute `excess = total -
    (score + 10)` and distribute the deflation across all
    `batting`-status batters proportionally to their runs.
    More fair distribution but harder to validate (which
    batter "owns" the inflation?).  Failure mode: if only
    one batter is inflated, this incorrectly deflates the
    innocent batter.  ~15-25 lines.
  - **Path C (hybrid: last-write + iterative — recommended):**
    Path A on the first invariant fire; if the cap warning
    persists on the next frame after the reset (suggesting
    other batters are also inflated), repeat the reset for
    the next-most-recent batter write.  Iterative
    correction.  ~10-15 lines plus the same
    `last_runs_update_frame` tracker as Path A.  This
    correctly attributes the most-likely source first and
    propagates only when evidence demands.  Better
    properties than either pure path: doesn't punish the
    innocent (unlike B), doesn't leave earlier phantoms
    untouched (unlike A in the multi-phantom case).

  **Implementation notes for Path C:**
  - Add `card["last_runs_update_frame"] = frame_id` on every
    successful runs write in `update_batter`.
  - In `validate_state_consistency`, when the cap-warning
    branch fires, find `argmax(card.last_runs_update_frame)`
    among `batting`-status cards, reset that one's `runs`
    and `balls` to `None` (matching the existing reset
    semantics), and force-set the tracker.
  - The cap-warning branch will re-fire on the next frame
    if the inflation persists; the next-most-recent batter
    is then targeted.  Bounded iteration: at most N
    iterations for N inflated batters across N frames.

  **Implementation decision: field-level vs whole-row reset
  semantics (called out 2026-04-26 from F1767+ findings).**
  When the cap-reset fires, should it clear only the
  suspicious field (runs only, leave balls intact) or the
  whole row (runs + balls together, matching today's reset
  semantics)?  Both have arguments:
  - **Whole-row reset (current proposal above).**  Simpler,
    matches existing `runs=None, balls=None` semantics, no
    new code paths.  But it discards the balls value even
    when the balls field is uncorrupted (i.e. inflated runs
    with correct balls; rare but real).  At admission time
    this is correct (uncertain which field is wrong); at
    correction time it's strictly worse than necessary.
  - **Field-level reset (recommended).**  Reset only the
    field identified as suspicious by the cap mechanism.
    Last-write tracking already identifies the runs-write
    that pushed the total over the cap, so the suspicious
    field is known.  Balls progress correctly while runs
    gets reset to a placeholder.  Closer to "preserve what
    we can verify."  Slightly more code (~5 extra lines to
    track which field triggered) but composes cleanly with
    the field-level rejection P1 (which moves
    admission-time defenses in the same direction).
  Field-level reset is recommended because at correction
  time you have **more information** than at admission time —
  the cap-mechanism has already failed, last-write tracking
  has already fingered the offending write, and you know
  which field is wrong.  Whole-row makes sense for the
  runs-monotonic guard at admission (uncertain which field
  is wrong); at correction time the uncertainty is gone.
  This decision compounds with the field-level rejection P1
  to give a coherent two-layer story: field-level discipline
  at both admission and correction.

  Path C is recommended.  Either A, B, or C makes the
  existing cap mechanism actually effective rather than
  log-only.  Composes with the
  EXTRAS-INF gate (admission-time prevention), the
  bat-runs reconciler (cross-source detection), and the
  rejection-consensus release (Layer 4 below).  **Together
  these four are the recovery-time quartet for the phantom
  +N P0 class** — admission gate prevents commit, reconciler
  detects post-commit divergence, invariant cap performs the
  sum-check correction, rejection-consensus performs the
  release when truth is repeatedly rejected.  All four are
  individually small and cheaply-testable.
- **P1 — STAGED 2026-04-26 19:55 IST as Fix 12.**
  Rejection-consensus release on the runs-monotonic guard
  (`scoreboard.py`, ~110 lines including extensive in-code doc
  comments + 31 sub-checks across 10 new tests).  POISON-STREAK
  template applied to per-batter runs.  Layer 4 of the phantom
  +N quartet.  Mirrors the existing FRAME_POISONED → POISON-
  STREAK pattern: when the runs-monotonic guard rejects the
  same proposed value N times consecutively for a given batter,
  accept it as the new truth and force-set the tracker
  baseline.

  **Implementation summary as shipped:**
  - State: `Scoreboard._runs_reject_streak: dict[str, dict]`
    maps batter name → `{"value": int, "count": int}`.
    Threshold: `Scoreboard._RUNS_REJECT_RELEASE_N = 5`
    (POISON-STREAK precedent; tunable from production data).
  - Wiring: refactored the two existing rejection clauses
    inside `update_batter` (`runs == 0 with cur > 5` and
    `cur − new > 5`) to record a `_runs_regression_rejected`
    sentinel + the rejected value + balls counterpart.  New
    Layer 4 block immediately downstream:
    - Match-or-different value comparison drives count++/reset.
    - At threshold, `tracker.force_set(bat:{name}:runs, value)`
      + `entry["runs"] = value`; balls counterpart force-set
      too iff captured (field-specific release matches field-
      specific guard).  `_last_row_rejected_frame = -1` to
      undo the row-suppression side-effect.
    - On legitimate (non-rejected) run write, drop the streak
      entry entirely.
  - Innings hygiene: `set_innings_2` clears
    `_runs_reject_streak = {}` so an innings-1 stuck-window
    cannot leak into innings-2 (cross-name-key resets are
    natural; this is defensive).
  - New telemetry: `[RUNS-REJECT-STREAK]` (INFO, every
    rejection — `name=val streak=count/N (cur=held)`) and
    `[RUNS-REJECT-RELEASE]` (WARN, threshold fire — `name:
    count consecutive rejections of runs=val (cur=held) —
    accepting as new truth`).  Distinct severity matches
    POISON-RECAL precedent (INFO for streak progress, WARN
    for the release event).

  **Honest scope claim:**
  Catches the modal Dube-shaped failure (357 rejections of
  identical truth values, no release path).  Does NOT catch:
  slowly-advancing truth where the rejected value drifts
  (each frame's value differs from the previous, breaking
  consensus — though Layer 2/3 sum-check correction catches
  this); the CLONE-REJECT clause (different rejection
  semantics, intentionally not extended); the balls-
  regression-too-deep clause at line 1754 (whole-row
  invalidation triggered by balls, not runs — separate
  failure mode).  These are explicit non-goals; Layer 4 is
  field-specific to runs as designed.

  **Test fixtures (all from today's CSK-vs-GT data):**
  - F1767+ Dube replay: phantom Dube=31(28), 5 frames of
    runs=22 → release at frame 5 (vs 357-rejection pre-fix
    baseline).  35 minutes earlier release at N=5 threshold.
  - Per-batter independence test (Dube streak doesn't trip
    Other's release).
  - Streak-reset on different rejected value (OCR jitter
    protection).
  - Streak-clear on legitimate acceptance (phantom window
    closed naturally).
  - Zero-regression clause coverage (`runs == 0 with cur > 5`
    also feeds Layer 4).
  - Source-level wiring (telemetry tags, threshold constant,
    state attribute, force_set call, innings-2 reset, block
    ordering relative to regression-rejection marker).

  Awaits inter-match seam for live validation.  First Dube-
  shape stuck-non_striker window in upcoming match should
  show `[RUNS-REJECT-STREAK]` ramp followed by
  `[RUNS-REJECT-RELEASE]` at frame 5; pre-fix baseline was
  357 cycles of "rejected" with zero releases.

  **Original design notes preserved below for reference.**
  Mirrors the existing FRAME_POISONED → POISON-STREAK pattern: when the
  runs-monotonic guard rejects the same proposed value N times
  consecutively for a given batter, accept it as the new
  truth and force-set the tracker.

  **Architectural framing:** every guard with detection
  semantics should have a corresponding release mechanism.
  Detection without release converts "phantom commits" (bad)
  into "phantom locks in permanently" (worse — the guard
  *prevents* recovery).  POISON-STREAK satisfies this
  principle (5-frame consensus releases FRAME_POISONED).  The
  runs-monotonic guard violates it (no release path; phantoms
  persist until dismissal).  Layer 4 brings the runs-monotonic
  guard up to the same standard.

  **Validation evidence (today's match):**
  - POISON-STREAK released the F2240+ over-18 stuck window in
    ~90 seconds (5-frame threshold, F2240 → F2265).  User-
    visible cost: 90s of UI showing 125/6 instead of 135/6.
    Tolerable.
  - Runs-monotonic guard held Dube phantom for **41:50** with
    **357 rejections** of identical truth values — Scout read
    `runs=22(15)` 20+ times consecutively in F1767-F1812 and
    every read was discarded by whole-row invalidation.  No
    release path exists; closed only by dismissal.  User-
    visible cost: 42 minutes of inflated UI.  Not tolerable.
  - Same architectural pattern, different implementation
    completeness.  Layer 4 = symmetry restoration.

  **Implementation (Path 1, per-field consensus, recommended
  for this slice):**
  - Add `card["rejected_proposals"]` ring buffer (frame_id +
    proposed_value tuples) sized to the consensus threshold.
  - On every runs-monotonic rejection, append `(frame_id,
    proposed_value)` to the ring buffer.
  - On any successful runs write or any rejection where the
    proposed value differs from the previous, **clear** the
    ring buffer (consensus must be on identical values).
  - When the buffer reaches N consecutive rejections of the
    same value, accept it as the new truth: force-set
    `card["runs"] = proposed_value`, log
    `[RUNS-CONSENSUS-RELEASE] <name> runs <old> → <proposed>
    after N consecutive rejections`, clear the buffer.
  - Threshold tuning: start at **N=5** (POISON-STREAK
    precedent; the Dube case would have released at ~F980
    instead of F1813, **35 minutes earlier**).  Refine
    empirically against match data:
      - **N=3-4 (faster recovery):** more aggressive release;
        risk of legitimate transient OCR misreads triggering
        spurious resets that revise correct values downward.
      - **N=8-10 (more conservative):** fewer false resets;
        phantom windows stay open longer.  At N=10 the Dube
        window still closes ~35 min earlier (~F985); the
        threshold choice is not very sensitive in this case
        because Scout was reading truth on every frame.
  - The buffer-clear-on-different-value rule is critical:
    the consensus must be on the **same** value, not just
    **any** rejection.  This prevents OCR jitter (where Scout
    reads 22 then 23 then 22 then 24...) from triggering
    spurious releases.  Five identical reads in a row is a
    much stronger signal than five rejections of various
    values.

  **Path 2 alternative (deferred, generalized consensus):**
  Build a reusable rejection-consensus mechanism that any
  guard plugs into; each guard tracks its own consensus
  state; threshold-reached fires a release callback.  ~50-100
  lines of architectural plumbing.  Composes with the
  consensus override P0 (which would be the cross-field
  correlation layer above per-field consensus).  Closer to
  2-3 hours.  These layers do not make each other redundant:
  Path 1 handles single-field phantoms (Dube +N); Path 2 +
  consensus override handles cross-field corruption (state
  poisoning that affects multiple fields simultaneously).
  Recommend Path 1 for the immediate quartet shipment; Path
  2 falls out of the consensus override work later.

  **Composes with Layer 3 (sum-check correction):** the two
  layers address distinct failure modes and form
  defense-in-depth.

  | Layer | Trigger | Failure mode addressed |
  |---|---|---|
  | 3 (sum-check) | `bat_sum > score + 10` invariant fires | Phantom inflated *total* beyond legitimate bound; identifies which batter to reset via last-write tracking |
  | 4 (rejection-consensus) | Same value rejected N times consecutively for one batter | Scout consistently reads truth; pipeline keeps rejecting; release accepts the rejected value as new truth |

  The Dube case would have been caught by either layer if
  implemented.  Layer 3 would have flagged the 199 cap
  warnings into actionable resets.  Layer 4 would have
  accepted Scout's repeated truth reads after N rejections.
  Both layers shipping covers distinct failure shapes.

  **Test plan:**
  - Unit: synthetic batter card; rejection N-1 times at same
    value → no release; rejection at Nth time → release fires,
    buffer clears, runs updates to proposed value.
  - Unit: rejection at varying values → no release (buffer
    clears on each different value).
  - Unit: rejection N-1 times at same value, then a successful
    runs write at a different value → buffer clears, no
    release.
  - Replay (regression-fixture quality): F1767-F1813 segment
    of CSK-vs-GT log.  Pre-fix: 357 rejections, 0 releases.
    Post-fix at N=5: 1-2 releases at ~F980 / ~F990, total
    rejections drop to <50, Dube's runs converges to 22 within
    seconds of the first consensus.

  Future guards added to the codebase should be evaluated
  against this principle: "if this guard rejects truth, what
  causes it to let go?"  Without an answer, the guard is
  incomplete.
- **P0 / SHIPPED-pending-live-validation (2026-04-28)** SCORER batter
  invariants (F339 Pathum resurrection).  `apply_scorer_decision()` now
  pre-gates SCORER/extractor batter writes via
  `_scorer_batter_update_allowed()` and rejects witnessed-out batters
  with `[SCORER-ACTIVE-GATE]` before `update_batter()` can mutate active
  state.  Follow-up audit refinement added `[STRIKER-STATUS-GATE]` so
  `update_batter()` refuses active-slot role flips unless the card is
  currently batting, plus a regression proving wicket auto-dismiss uses
  SM's active striker over stale `sb._inn`.  Local regression covers
  witnessed-FOW exclusion; live validation tail is a future
  resurrected-dismissed-batter attempt.
- **P0** State-recovery deadlock — three guards compound (FRAME_POISONED,
  runs-delta-guard, WS-SCRUB) — 2-3 h, needs sustained focus + may
  benefit from a brief design-doc prep pass first.  **Evidence
  strengthening 2026-04-26:** today's CSK vs GT match surfaced
  Gaikwad's +4 inflated tally (UI=14 vs CB=10) as a "guards
  correctly reject delta but no path forward" failure — exactly
  the class consensus override would unwind.  Each match-day
  occurrence adds to the case; the bat-runs reconciler (P1 above)
  is the cheaper detection-only slice but still routes corrected
  state through this same recovery path once built.
- **P2** Sampler bucket-coverage M-2 — **subset path shipped** in
  **`select_corpus_candidates.py`**; **phase×innings combined path
  shipped** in **`files/scripts/select_combined_scout_corpus.py`**
  (**`m2_combined_corpus_sampler.md`**). Operational next step: run on
  real multi-inventory inputs + optional **`--strict`** in CI or pre–shadow
  checklist.
- **P2** SM ingest-latency reduction (the underlying cause of the
  ~24 s catch-up gap that creates Fix 7's fallback opportunity) —
  Fix 7 papers over the user-visible symptom, so this work is
  **less urgent** post-bundle but still valuable for clean state-
  consistency; size unbounded, queue when bandwidth permits
- **P1 (promoted from P2/P3 2026-04-26 17:24 IST after empirical
  production confirmation)** SM lacks `set_innings_2()` /
  `reset()` hook (filed 2026-04-26 during innings-transition
  hygiene audit; **promoted to P1** after live observation of
  the gap firing in CSK-vs-GT innings transition).
  `score_manager.ScoreManager` has 4 callsites that flip
  `self.innings = 2` directly (lines 693, 1054, 1157, 1259) but
  no method that resets cached per-innings state:
  `bat1_runs/balls/name`, `bat2_runs/balls/name`, `bowler_runs/
  overs/wickets/name`, `striker`/`non_striker`, computed
  `run_rate`/`bat1_sr`/`bat2_sr`/`bowler_economy`, etc.  By
  contrast `scoreboard.set_innings_2()` at `eyes/scoreboard.py:423`
  is a comprehensive reset (replaces `_tracker`, blanks innings,
  clears all per-innings dicts).

  **Empirical production confirmation (2026-04-26, F2503-F2515,
  CSK-vs-GT innings transition).**  At the AUTO-SWAP boundary
  (F2503 17:24:18 — `[AUTO-SWAP] Innings 1 ended at 20.0 ov / 7
  wkts AND bowling team 'Gujarat Titans' visible on strip`):

  - **SM cached striker name persisted across the flip.**  At
    F2504 onwards, pipeline emits
    `[WS-SCRUB] striker='Jamie Overton' rejected reason=not_in_card
    (#2) → fallback='Sai Sudharsan' active=['Sai Sudharsan',
    'Shubman Gill']` and the rejection count climbs every frame.
    Jamie Overton is a **CSK** batter (innings-1, dismissed at
    18.6); GT's batting card has Gill+Sudharsan.  The rejection-
    reason changed cleanly from `status_out` (innings-1 last
    frames F2480-F2502) to `not_in_card` (innings-2 first frames
    F2504+), confirming the **batting card flipped correctly but
    SM's cached striker name did not reset**.

  - **WS-SCRUB defensively rescues the UI** by falling back to
    `active_batting`.  User-visible UI shows Sudharsan correctly.
    But the underlying state corruption is firing every frame.
    If WS-SCRUB ever fails or its conditions change, the
    corruption would surface immediately as "Jamie Overton on
    strike during GT's innings."  Defenses can rot; the
    underlying bug needs to be fixed.

  - **Refined diagnosis: scalar fields persist, keyed caches
    reset via key-distinction.**  The Hosein +21(6) phantom from
    innings-1's last frames did **not** carry into innings-2
    because Hosein is not a key in GT's batting card lookup —
    the per-batter card is keyed by name and innings-2 uses
    different names, so the lookup naturally returns fresh
    state.  But SM's **scalar fields** (`striker`,
    `non_striker`, `bat1_runs`, `bat2_runs`, `bowler_*`,
    computed metrics) are not keyed; they retain the innings-1
    values until overwritten.  This sharpens the fix scope: the
    keyed caches don't need explicit reset, only the ~14
    scalar fields do.

  - **Per-frame cost of the gap:** ~1 WS-SCRUB warning per
    incoming frame for the duration that SM's striker remains
    stale.  Innings-2 first ~12 frames already produced 8+
    rejections before any innings-2 ball event hit SM.  The
    cadence resolves only when SM receives a fresh `bat1_name`
    or `striker` write, which depends on which scorer path
    triggers first in the new innings.

  - **Dual-broadcaster manifestation (2026-04-26 18:25, post-
    Fix-9/10 deploy, GT chase mid-flight, additional empirical
    confirmation that escalates production damage from "masked"
    to "user-visibly flickering").**  After the restart that
    deployed Fix 9 + Fix 10, the pipeline cold-started innings-2
    with `current_innings=1` (cold-start default) and self-
    corrected at F40 via the existing `[CODE] HIGH-CONF` regex
    on a "TO WIN 96 OFF 75" overlay (computed `target=159`,
    triggered `[INNINGS-CHANGE]`).  From F40 onwards every
    DETAIL log line emits `AFTER_innings=2 | AFTER_target=159`
    — pipeline-side state is correct and consistent.  But the
    UI started flickering between `Inn 2 / target 159 /
    "Need 85 from 67 balls"` and `Inn 1 / target=None / no
    chase context` on every ball event (observed during over
    7.5→8.0 and 8.5→9.0 transitions; identical signature on
    each ball).

    Root cause attribution traced to two payload-emission
    paths in `test_pipeline.py`:

    1. **Event-firing frames** (`_sm_result is not None`,
       fires on every ball event) — Phase 2 / non-shadow
       path at line 7959-8004 sets `ws_payload = _sm_result`.
       SM's `_build_payload()` emits SM's internal scalars,
       which include `innings=1` (never reset) and
       `target=None` (never set, since SM has no
       `set_innings_2(target)` method).  The UI receives the
       SM payload directly, sees `Inn 1 / target=None /
       Partnership 40 runs / Extras panel visible`.
    2. **Quiet frames** (`_sm_result is None`, between
       deliveries) — falls to the legacy path at line
       8011-8021: `ws_payload = build_full_payload(...)`,
       which reads `scoreboard.current_innings` (=2 since
       F40) and `state.get("target")` (=159 since F40).  The
       UI receives the legacy payload, sees `Inn 2 / target
       159 / "Need 85 from 67 balls" / no Partnership panel
       / no Extras panel`.

    Smoking-gun signature: the **Partnership** and **Extras**
    panels appear only on Inn-1 frames in the UI screenshots
    (SM-only fields; legacy `build_full_payload` doesn't
    surface them as separate panels).  This anti-correlation
    deterministically identifies which path emitted any given
    frame, confirming attribution.

    The pre-existing `session_id` namespace patch
    (line 7969-7970, `f"{SESSION_ID}_inn{scoreboard.current_innings}"`)
    correctly stamps innings=2 on the SM-broadcast envelope —
    but the **payload body** (`match.innings`, `match.target`,
    `scorecard.batting_team`, `scorecard.bowling_team`,
    plus all the per-batter/per-bowler scalars) still carries
    SM's stale innings-1 internal state.  The session-change-
    triggered UI reset path doesn't rescue the per-frame
    fields because every event frame re-asserts the stale
    values.

    **This is the same bug as the Overton case, but with the
    masking removed.**  Overton was hidden by WS-SCRUB
    falling back to `active_batting`; the fluctuation is
    visible because `match.innings` and `match.target` have
    no equivalent defensive fallback at the WS boundary.

  - **Broadened scalar-field reset scope (escalation
    2026-04-26 18:25):** the original ~14-field list in this
    entry was striker/non_striker + per-batter/per-bowler
    scalars.  The dual-broadcaster manifestation surfaces
    additional fields that need reset:
      - `innings` (SM's internal innings flag, the field that
        emits as `match.innings` in `_build_payload`)
      - `target` (SM has no setter for this; needs explicit
        seeding from AUTO-SWAP)
      - `batting_team` / `bowling_team` (SM's cached team
        names — would emit as `scorecard.batting_team` and
        flicker the team-role display the same way innings
        flickers; not yet observed in this match because GT
        is also the cold-start default but would surface in
        any chase that requires a swap from cold-start)
      - `match_phase` (SM's cached value, distinct from
        `scoreboard._inn["match_phase"]`)
      - any chase-derived computed metrics
        (`balls_remaining`, `runs_required`, `rrr`) if SM
        caches them — these are derived but would reflect
        innings-1 inputs until reset.
    Net additional ~3-5 scalar fields beyond the original
    14, depending on what `_build_payload` actually emits.
    Fix scope grows modestly: still bounded ~30-50 lines.

  - **Wider validation surface for the fix** (post-fix
    success criteria expanded by the dual-broadcaster
    finding):
      1. Original criterion: post-innings-2 frames produce
         **zero** `[WS-SCRUB] reason=not_in_card` fires for
         innings-1 batter names.
      2. **New criterion:** UI never flickers `Inn 1`/
         `target=None` after the AUTO-SWAP for the entire
         innings-2.  Telemetry: every ball-event-frame
         `state_update` payload emitted to broadcast_state
         carries `match.innings == 2` and
         `match.target == innings_1_total + 1` once SM has
         been reset.  Failure mode: any single SM-broadcast
         frame in innings-2 emitting `match.innings = 1`
         is a regression.
      3. **Secondary criterion:** `scorecard.batting_team`
         + `scorecard.bowling_team` consistent across
         consecutive frames (SM-broadcast and legacy paths
         agree on team-role labels).

  Real architectural side channels (still apply, now with
  empirical evidence backing each):

  - **Same-named players across innings** (e.g. team A bowler
    promoted to opener in innings 2, or two players sharing a
    surname across both teams) would surface stale runs/balls
    as a phantom — *the failure mode that would expose this
    gap user-visibly is now confirmed via the Overton case
    above; only the name-distinction in CSK-vs-GT prevented it
    from being user-visible.*
  - **Shadow-mode parity comparison `[SHADOW-MODE-CAVEAT]`** —
    any tooling that compares current SM state against scoreboard
    state in innings 2 will see stale SM fields as spurious
    divergence WARNs that look like pipeline bugs but are
    reset-hygiene artifacts.  Anyone running SM-vs-scoreboard
    parity analysis post-innings-transition should interpret
    divergences with this gap in mind: an `bat1_runs` mismatch in
    innings-2 frame 1 is not necessarily a state corruption — it
    could be the innings-1 final value that SM never cleared.
    Until the reset hook lands, parity tools should either
    (a) skip the first N frames of innings 2 to let new values
    overwrite, or (b) explicitly forgive divergences when the SM
    field equals the innings-1 final value.
  - **Computed metrics** (`run_rate`, `match_phase`,
    `balls_remaining`) carry innings-1 inputs into innings-2
    arithmetic until refreshed.

  **Fix shape:** add `ScoreManager.reset_for_innings_2()` that
  blanks **only the ~14 scalar fields** (keyed caches reset
  cleanly via key-distinction, no work needed there), called
  from each of the 4 callsites.  ~30-50 lines.  In-code
  documentation has been added at `score_manager.py:130` (NOTE
  block above `self.innings = 1`) flagging the gap so future
  engineers don't assume `innings == 2` implies "all per-innings
  state has been reset."  Test fixture: replay innings-1 frames,
  invoke set_innings_2, assert all 14+ scalar cached fields
  revert to None and that batter-card-keyed reads return fresh
  state by virtue of innings-2 batter names not matching
  innings-1 keys.

  **Justification for promotion (originally promoted P2/P3 →
  P1 2026-04-26 17:24, severity escalated 18:25):**
  (1) Production damage real, **and as of the 18:25 dual-
  broadcaster finding it is no longer masked** — the UI
  flickers `Inn 1 / target=None / no chase context` on every
  ball event.  WS-SCRUB hid the striker-name corruption; no
  defensive layer hides the `match.innings` / `match.target`
  flicker, so the chase-context UI is corrupted on every
  ball.  (2) Fix scope bounded (~30-50 lines, comparable to
  today's shipped fixes; the broadened scalar set adds 3-5
  fields, not a structural change).  (3) Empirical
  confirmation across two manifestations now (Overton-masked
  + chase-flicker-visible) removes any "speculative
  architectural concern" framing — this is a confirmed bug
  with multiple production manifestations in a single match,
  and the fix is small and high-leverage.  (4) The
  fluctuation has user-visible cadence of one flicker per
  ball — for an innings of ~120 balls that's ~120 user-
  observable corruption events per chase, all addressable by
  one fix.

  **Hotfix path explicitly rejected (2026-04-26 18:29).** A
  bounded ~10-line patch at the SM-broadcast site (line
  7959-8004 of `test_pipeline.py`, mirroring the `session_id`
  namespace override pattern at line 7969-7970) was proposed
  to override `match.innings` / `match.target` /
  `scorecard.batting_team` / `scorecard.bowling_team` from
  scoreboard authoritative values on every SM payload.  User
  declined ("no temporary work, lets do proper fixing") in
  favour of the proper P1 reset method.  The hotfix would
  have left SM's internal state stale and only patched the
  WS boundary; the proper fix rotates SM's state at the
  AUTO-SWAP / cold-start innings-2 detection callsites,
  closing the root cause.  Rejection rationale aligns with
  the "complete the SM-cutover" architectural item — adding
  another boundary patch deepens the technical debt of "SM
  state isn't trustworthy, override at the edge"; the proper
  fix moves SM toward being trustworthy.

**Held / observation-only (insufficient signal):**
- Archer stuck-figures pattern — needs more occurrences before
  code-level recovery options become evaluable; one match's data
  isn't enough
- Rabada ↔ Siraj "OCR confusion" 2026-04-26 — investigation
  showed Scout reads both names **correctly** when each is on
  (Over 1 = Rabada, Over 2 = Siraj, Over 3 = Rabada, etc.).
  The vs-CB divergence is **CB reporting lag** — CB shows the
  previous over's bowler at the start of a new over, then catches
  up.  Not a pipeline bug; not actionable.  Filed here to prevent
  re-investigation if the pattern surfaces again.
- Suthar ↔ Holder bowler transition 2026-04-26 (over 7) — what
  initially looked like a cross-team misread (Jason Holder is GT,
  not CSK as I'd misread the squad blob) turned out to be a real
  bowler change handled correctly by the pipeline.  Scout's
  "Holder" / "Suthar" read distribution (65/67 frames roughly
  even) reflects the actual transition between two bowlers
  during over 7-8, not a single-bowler OCR confusion.  Pipeline
  detected the change at F790 (16:08:04) via 40-frame consensus;
  Cricbuzz caught up to the same transition by 16:11:46.
  **Pipeline was ahead of CB by ~3 minutes.**  Validates the
  consensus-based bowler detection logic.  Filed here as a
  positive case study — pipeline-first detection working as
  designed; CB lag (not pipeline error) was the divergence
  source.
- BOWLER-AUTO ingest-paths clarification 2026-04-26 — the visible
  "bowler stats lag team stats" pattern is **not a bug**, and the
  earlier framing ("BOWLER-AUTO only auto-bumps overs, not runs")
  was wrong.  BOWLER-AUTO is designed to mirror **both** score
  and overs deltas to the current bowler (see
  `_mirror_team_delta_to_bowler` in `eyes/scoreboard.py:1228`).
  What live logs actually show is the **deferral** mechanism
  firing as designed: when Scout is reading the bowler card at
  high cadence (typical mid-innings), BOWLER-AUTO defers most
  mirrors so the authoritative Scout value commits cleanly
  without race (`[BOWLER-AUTO] {field} delta deferred — Scout
  active`, ~50+ deferral events per match).  Net effect: Scout
  is the dominant ingest path, BOWLER-AUTO is the fallback when
  Scout is briefly silent, and bowler stats trail team stats by
  a few seconds (one Scout cadence interval).  Two ingest paths
  with different cadences for related fields is bounded but
  visible.  Operational note added to `eyes/scoreboard.py:1207`
  inline (search "OPERATIONAL NOTE (2026-04-26)") so future
  engineers seeing "Holder runs=22 but team total advanced past
  that" don't chase it as a bug.  Composing fix at architectural
  level is the **P2 SM ingest-latency reduction** entry above —
  closes the cadence gap rather than papering over it.

**Striker-collision Path B (full SM cutover)** — **SHIPPED — partial
live-validation (2026-04-28)**.  Pipeline active-slot reads now go through
`_canonical_active_slot()` (SM first, `sb._inn` projection fallback only
when the card is actively batting), and direct pipeline `sb._inn`
striker/non_striker writes are routed through `_set_legacy_active_slot()`,
which suppresses the write when SM is live and logs
`[STRIKER-SM-CUTOVER]`.  Scoreboard-owned internal helpers still maintain
their local projection; UI/broadcast and pipeline consumers now prefer
SM canonical slots.  **Live**: PBKS-vs-RR, log `pipeline-2026-04-28-pbks-rr-live.log`, **F219** (double `[STRIKER-SM-CUTOVER]` on over-change rotation).
**Pending**: post-wicket churn positive-fire on the same path.

**Architectural (tracked technical debt, not urgent): Complete the
SM-cutover for legacy write paths.**  Filed 2026-04-26 after the
post-wicket `sb._inn` rotation gap surfaced on **three** wicket
events in the same match (Sarfaraz at W3 / 88 fires, Kartik
post-Dube at W5 / 443 fires, Overton at W7 / 240+ fires —
three-for-three on observed wickets), following yesterday's
BOWLER-STALE shipment and today's Fix 5 striker self-collision
defense.

Three "structural rotation gap" issues are now identified across
the codebase, each defended by a layer that fires on **every
event of the relevant class** rather than on edge cases:

| # | Rotation gap | Defensive layer | Fix shape |
|---|---|---|---|
| 1 | **Bowler identity rotation** | BOWLER-STALE disambiguator | **SHIPPED** 2026-04-25 hotfix |
| 2 | **Striker self-collision via legacy `update_batter` writes** | Fix 5 (`STRIKER-COLLISION` refusal) | Path A SHIPPED; Path B SM-first cutover **live-validated** on over-change (**F219**); post-wicket churn still pending |
| 3 | **Post-wicket non_striker rotation** in `sb._inn` | Fix 5 indirectly + WS-SCRUB | Path A bounded fix shipped; Path B SM-first cutover **live-validated** on over-change (**F219**); post-wicket churn still pending |

All three share a single structural pattern: **legacy write paths
that should have been retired during a previous SM cutover but
weren't.**  The defensive layer catches the resulting wrong-state
proposals, but the underlying code health degrades incrementally
with each unmigrated path.

**Why this matters as tracked debt rather than urgent work:**
- Production damage is bounded today; the defenses work.
- Each individual gap has its own bounded P1 fix queued.
- But each new bug discovered in legacy paths gets a defensive
  patch, defenses accumulate over time, and the legacy paths
  become harder to remove because more things depend on the
  defensive layer being in place.
- Incremental defensive work *increases* the cost of eventual
  cleanup.

**Cutover narrative (the "after" picture):**
- SM is the sole canonical source for `striker`, `non_striker`,
  `current_bowler`, and `batting_card[*].is_striker`.
- `sb._inn`'s active-batter slots become *projections* of SM
  state, not independent writes.
- Fix 5, BOWLER-STALE, and the post-wicket rotation hook all
  negative-fire (rotation succeeds, defenses stay silent).
- New rotation-related bugs become detectable as "an SM write
  was wrong" rather than "two writers disagreed."

**Estimated scope:** larger than any single P1.  Probably a
3-5 hour audit pass — enumerate every direct write to
`sb._inn["striker"]` / `sb._inn["non_striker"]` / `current_bowler`
outside SM's authoritative path, decide retire-vs-rewrite for
each, then rip out the retired paths and update Fix 5 / BOWLER-
STALE / WS-SCRUB to reflect the new invariants.

**Why filed now even though not urgent:** today's CSK-vs-GT
match showed three instances of the same pattern across three
wickets (Sarfaraz: 88 fires, Dube post-rotation: 443 fires,
Overton: 240+ fires before AUTO-SWAP closure), totaling **771+
defensive fires** in a single match.  Three-for-three on
observed wickets is a frequency signal, not edge-case behavior.
Without a tracking entry, future engineers will continue
defensive-patching individual gaps without seeing the meta-
pattern.  Tracked-debt status: **revisit when next defensive
patch is needed against the same class** — at that point the
audit work pays for itself.

**Reinforcement 2026-04-26 18:29 (SM-broadcast-site hotfix
explicitly rejected):** when the dual-broadcaster fluctuation
surfaced (UI flickering Inn 1/Inn 2 every ball event during GT
chase), a bounded ~10-line hotfix was proposed at line
7959-8004 of `test_pipeline.py` to override `match.innings` /
`match.target` / `scorecard.batting_team` /
`scorecard.bowling_team` from scoreboard authoritative values
on every SM payload — mirroring the existing `session_id`
namespace patch at line 7969-7970.  User declined ("no
temporary work, lets do proper fixing") in favour of the
proper P1 SM-reset method.  The user's framing is exactly
this entry's framing: **the hotfix would have added another
boundary patch instead of fixing SM's state hygiene at its
source, increasing the cost of the eventual cutover.**  Two
boundary overrides at the SM-broadcast site already exist
(`session_id` namespace + `this_over` ↔ `completed_over`
fallback at line 7980-7983); a third would have made the
pattern entrenched.  The proper P1 fix
(`ScoreManager.reset_for_innings_2()`) is on the cutover side
of the wall — SM owns its scalars correctly, no boundary
patch needed.

Composes with the **state-recovery consensus override (P0
architectural)** but is structurally different: that piece
addresses *recovery* from wrong values that committed; this
piece addresses *prevention* by retiring the duplicate write
paths that allow such inconsistency to arise in the first
place.  Together: prevent at the write layer (cutover),
recover at the read layer (consensus override), defense-in-
depth across the stack.

**Pass-2 non-grounded fallback** — defence-in-depth follow-up filed
when Fix 6 was investigated; do not file as a formal entry until Fix
6 has at least one match-day of telemetry (need empirical timeout-rate
data, not speculation).

**Blocked / queued externally** — see the section at the bottom of
this file (RC-1/RC-2 corpus, L2 re-bakeoff, Step-1/Step-2 densification).

---

## Architectural pattern note (2026-04-26): defense-in-depth layers

Today's CSK vs GT match surfaced three active bugs that share a
common shape, and the recovery story for the project is converging
on a two-layer architecture worth naming explicitly:

```
                  ┌─────────────────────────────┐
                  │  Wrong value enters state   │
                  └───────────┬─────────────────┘
                              │
              ┌───────────────┴────────────────┐
              ▼                                ▼
   ┌───────────────────────┐     ┌─────────────────────────┐
   │  ADMISSION-TIME       │     │  RECOVERY-TIME          │
   │  defenses             │     │  defenses               │
   │  (prevent commit)     │     │  (correct after commit) │
   └───────────────────────┘     └─────────────────────────┘
   • Phantom-signature           • Multi-guard consensus
     detector (P0 above)           override (P0 deep-dive)
   • Post-wicket sb._inn         • Bat-runs reconciler (P1)
     rotation (P1 above)         • State-recovery hot path
   • Existing: Fix 8 INFO-         (architectural)
     PANEL gate, Fix 5
     STRIKER-COLLISION,
     consensus + grace
```

**The bugs observed today fit the layers as follows:**

| Bug | Admission-time fix | Recovery-time fix |
|---|---|---|
| Phantom score +4 (F52) | Phantom-signature detector (sigs 1-3) | Bat-runs reconciler |
| Phantom batter +10 Brevis (F656) | EXTRAS-INF gate (sig 4) + name-swap (sig 5) | Bat-runs reconciler |
| Phantom batter +17 Dube (F975) | EXTRAS-INF gate (sig 4) + name-swap (sig 5) | Bat-runs reconciler |
| Sarfaraz stuck non_striker | Post-wicket sb._inn rotation | SM-authoritative override (Path B) |
| Gaikwad +2/+4 carryover | (covered by phantom signatures above) | Bat-runs reconciler |
| Dube row-rejection collateral (balls dropped) | Field-level rejection (vs row-level) | (none — prevention-only concern) |
| Cumulative batter-total inflation (199 cap fires, 0 resets) | (n/a) | Tighten `validate_state_consistency` reset threshold |

**Implementation cost ordering (cheapest first):**

1. **EXTRAS-INF gate (sig 4 prevention slice).**  ~10 lines.
   Signal already computed in current logs; convert log-only
   to gate-and-log.  Catches Brevis-class and Dube-class
   phantom commits at admission.  Standalone P1, ships
   without architectural prerequisites.
2. **Post-wicket `sb._inn` rotation (Path A).**  ~10-15 lines.
   Closes the Sarfaraz-stuck-non_striker class.  Single test
   scenario.  Standalone P1.
3. **Field-level rejection (vs row-level).**  ~20-40 lines.
   Eliminates the 22-data-points-lost-per-90s collateral cost
   without changing detection logic.  Standalone P1.
3a. **Tighten invariant-cap reset threshold (Path C
    hybrid recommended).**  ~10-15 lines (last-write
    tracker + iterative correction).  Activates an
    existing 199-fires-zero-resets layer.  Standalone
    P1, but ships best as part of the **Phantom +N
    recovery-time triad** (clusters with items 1 and 4
    in this list as a single coherent commit).
4. **Bat-runs reconciler (recovery slice).**  ~40-60 lines.
   Detection-only; correction is harder.  Standalone P1.
5. **Phantom-signature framework + provisional admission.**
   ~80-150 lines.  Comprehensive admission-time prevention
   covering all five signatures.  Architectural P0.
6. **Multi-guard consensus override.**  ~2-3 hours of focused
   work.  Comprehensive recovery-time correction.
   Architectural P0.

Items 1-3 together address the bulk of today's match-day
damage at a combined cost of ~40-65 lines.  Recommend landing
1+2 in next inter-match window if a similar 1-1.5h slot is
available.

**Why both layers matter:**  Admission-time defenses prevent the
"no recovery path" trap from being reached (Brevis-stuck-at-12,
Sarfaraz-rejected-88-times, Gaikwad-baseline-shifted) but cannot
correct corruption that happened before the defense existed.
Recovery-time defenses can correct any corrupted state but burn
ongoing CPU and risk false-positives on legitimate state changes.
The two layers compose: admission-time catches the easy cases
cheaply; recovery-time provides the safety net for novel
corruption modes.  Today's data is direct evidence for each layer
— the phantom-+N class needs admission prevention, the
"defenses-correctly-reject-but-no-path-forward" class needs
recovery correction.  Filing this as a design note rather than a
work item; individual fixes (post-wicket rotation, phantom-
signature detector, bat-runs reconciler, consensus override) are
the actual implementation pieces and are listed above in priority
order.

---

## P0 (live UX): match-`overs` consensus override accepts hallucinated regression (6.0 → 0.5) → cascading scoreboard corruption — **SHIPPED-pending-validation** (Fix 4, 2026-04-25 bundle)

**Status: STAGED 2026-04-25 inter-match commit bundle as Fix 4 — `[CONSENSUS-BLOCKED] overs:` guard at `consistent_tracker.py`. Awaits seam restart; transitions to SHIPPED at land time per `staged_fixes_2026-04-25/README.md` step 6.**

**Discovered (2026-04-25 RR vs SRH match-2 innings 2, ~over 7):** at
F3120 22:23:43, the match `overs` field regressed from `6.0` to
`0.5`.  The pipeline was on a bowler-end break / over-completion
cutaway, the broadcast strip read `SUNRISERS 89-1 (POWERPLAY)` (no
overs digits visible), the Scout extractor parsed the `(POWERPLAY)`
slot as `(0.5)`, and after 4 consecutive frames of agreement the
`ConsistentReadTracker` consensus path **overrode its own
`[SUSPICIOUS] backwards` warnings** and committed `overs = 0.5`
into confirmed state.

**Trace from `logs/pipeline-2026-04-25-203819-rr-srh-v5-bowler-stale-fix.log`:**

| frame | time     | event |
|-------|----------|-------|
| F3117 | 22:23:29 | `STRIP: SUNRISERS 89-1 (POWERPLAY)` → `ext_score=89-1(0.5)`; `[SUSPICIOUS] overs: 6.0→0.5 (backwards)` (×2, blocks) |
| F3118 | 22:23:33 | same strip; `[SUSPICIOUS] overs: 6.0→0.5 (backwards)` (×2, blocks) |
| F3119 | 22:23:38 | same strip; `[SUSPICIOUS] overs: 6.0→0.5 (backwards)` (×2, blocks) |
| F3120 | 22:23:43 | `STRIP: SUNRISERS 89-1 (POWERPLAY) | - - | ...`; `[SUSPICIOUS]` ×2 → **`[CONSENSUS] overs: 6.0 → 0.5 (extractor agreed 4 frames)`** → `BOARD: overs: 6.0 -> 0.5 [F3120]`; `[FLOOR] Padded 5 '?' placeholders to this_over (team_overs=0.5 expects 5 legal, observed only 0)` |

After F3120, all downstream consumers locked into the corrupted
state.  Subsequent legitimate Scout reads of `89-1 (7.0+)` arrived
as `[SUSPICIOUS] balls regression` against the wrongly-stuck
`overs=0.5`, and Kishan's strip line `41(17)` was rejected as
"balls regression" from the frozen `22(29)` baseline.  `this_over`
accumulated `?` placeholders for a phantom over 1.  `target=640`
(separate P0 below) compounded the UI nonsense — UI displayed
`Need 540 from 115 balls` while broadcast showed `129 from 79`.

**Root cause:** `files/eyes/consistent_tracker.py:230-291`.  The
consensus-override block has explicit `[CONSENSUS-BLOCKED]` guards
for the analogous failure modes that have already been hardened
against extractor hallucinations:
- batter `runs` regression while `balls` unchanged (L237-247)
- bowler `runs`/`wickets`/`overs` regression mid-spell (L270-281)

But the **match `overs` field has no equivalent
`[CONSENSUS-BLOCKED]` guard** — only a `[SUSPICIOUS]` log
marker at L420-424 of `_is_suspicious()` that returns `True` to
*route* into the consensus path, then doesn't block it from
committing.  4 same-value reads → `confirmed[overs] = 0.5` even
though every single one fired the backwards warning.  The
defensive logic is half-built; what was added for individual
batter/bowler stats was never replicated for the team-level overs
counter, where the same hallucination pattern is even more
damaging because it cascades into balls-regression rejects on
every other field.

**Pre-existing latent bug.**  Not caused by today's fixes
(BOWLER-STALE bowler-context disambiguator, frame-archival, P0-A
four-layer defense).  The half-broadcast strip + `(POWERPLAY)`
badge + Scout misparse pattern is broadcast-conditioned; this is
the first time today's match has produced 4+ consecutive
mis-extractions on the overs slot.

**Damage scope (live, until restart):**
- match `overs` frozen at 0.5 (real ~7.0)
- Required Run Rate / chase-progress UI catastrophically wrong
  (compounds with target=640 P0)
- partnership balls → 0 ("82(0)")
- Kishan's strip read `41(17)` rejected → batter card frozen
  at last pre-corruption value
- `this_over` chip shows `?,?,?,?,?` for phantom over 1 instead
  of true over (~7) state
- bowler card writes deferred / mis-attributed because
  `[BOWLER-AUTO] overs delta deferred` and downstream `[GUARD]
  Bowler ... overs 1 > match overs 0.5+0.3 — cumulative stat,
  dropping all figures` blocks the legitimate bowler stats
- Wire / storyteller / analyst commentary stays correct (read
  `ext_score`/`ext_bowl` directly), but everything UI-side is wrong
- self-reinforcing: each new legitimate strip read is rejected
  as a "regression" against the stuck baseline, cementing the
  corruption until manual restart

**Why existing defenses didn't catch it:**
- `[SUSPICIOUS] overs: backwards` fired 8 times across F3117-F3120
  but only as a routing signal, not a hard block (the actual gate
  for bowlers fires inside the `streak[1] >= CONSENSUS_THRESHOLD`
  branch; team overs has no equivalent gate)
- `cam=bowlers_end phase=between_play` correctly classified the
  frame as a scoreboard view, so frame wasn't poisoned upstream
- `[FLOOR]` correctly padded `this_over` to match the new (wrong)
  overs — defense doing exactly what it's coded for, against the
  wrong baseline

**Fix candidate (~10 source lines, 3 tests):** mirror the bowler
regression guard at `consistent_tracker.py:270-281` for the
team-level `overs` field within the consensus-override block.
A team's `overs` cannot regress within an innings; the only
legitimate reset is via `set_innings_2` which clears `confirmed`
wholesale, never via the consensus path.

```python
# Match overs cannot regress within an innings; legitimate
# resets clear confirmed[] wholesale via set_innings_2(),
# never through the per-field consensus override.  Without
# this guard, 4 consecutive (POWERPLAY)-misparse frames
# silently overwrite a real over-7 reading with 0.5
# (RR-vs-SRH 2026-04-25 F3120).
if field == "overs" and _new_f < _old_f:
    log.info(
        f"[CONSENSUS-BLOCKED] {field}: "
        f"{current}→{value} — match overs cannot regress "
        f"within an innings (likely dead-time / "
        f"placeholder-graphic misread)")
    self._reject_streak.pop(field, None)
    return current
```

Place inside the `streak[1] >= self.CONSENSUS_THRESHOLD` branch,
adjacent to the existing batter and bowler regression guards.

The same guard is also needed on the **pending-consensus
promotion path** (L312-360) to prevent the SRH-vs-DC F113 class
of leak (`SUSPICIOUS …count=3/3` → confirm).  ~5 more lines.

**Tests to add (using log-replay fixture from F3117-F3120):**
1. Replay 4 consecutive `89-1 (0.5)` extractor reads against a
   tracker with `confirmed[overs]=6.0`; assert
   `confirmed[overs]` stays 6.0, `[CONSENSUS-BLOCKED]` fires.
2. Boundary: legitimate over-completion (5.6 → 6.0); assert
   accepted on first read (no regression, no SUSPICIOUS).
3. Innings reset path: `set_innings_2()` clears `confirmed`,
   then first read of `0.0` against an empty tracker is
   accepted via cold-start consensus (3 frames); assert
   `[CONSENSUS-BLOCKED]` does NOT fire on the cold-start path.

**Operational note:** because the corruption is
self-reinforcing (legitimate post-corruption reads get
rejected as "regression"), a process-level pipeline restart
is the only recovery once committed.  The fix prevents
commit; once committed, only restart cleans state.

**Status:** P0 documented, immediate restart taken (user
approval, see chat).  Fix queued for inter-match commit
together with the other three deferred fixes (target=640,
this_over reorder, this_over speed-token validation).
Combined commit estimate now: ~45-50 source lines, 11 tests,
3 files (`test_pipeline.py`, `this_over.py`,
`consistent_tracker.py`).

---

## P0 (live UX): `this_over` ingests 3-digit speed values as run-tokens (no token-alphabet validation) — **SHIPPED-pending-validation** (Fix 2, 2026-04-25 bundle)

**Status: STAGED 2026-04-25 inter-match commit bundle as Fix 2 — token-alphabet validation in `this_over.py`. Awaits seam restart; transitions to SHIPPED at land time per `staged_fixes_2026-04-25/README.md` step 6.**

**Discovered (2026-04-25 RR vs SRH match-2 innings 2 over 2):** at the
start of Archer's second over, the pipeline wrote
`['139', '148', '143', '147', '145', '140']` into `this_over` and
archived `Over 2 complete: ... = 862 runs, 0 wkts (by Jofra Archer)`.

**Trace from `logs/pipeline-2026-04-25-203819-rr-srh-v5-bowler-stale-fix.log`:**

```
F2461 22:02:24 OVER: Broadcast replaces all-placeholder local: ['139', '148', '143', '147', '145', '140']
F2461 22:02:26 TEST: [THIS OVER] ['139', '148', '143', '147', '145', '140'] = 862 runs
F2461 SCOREBOARD strip: "SRH 34-1 (2.5) | Kishan 14(6) | Abhishek 4(6) | Archer 0-14 (1)
                         SPEED: 145 THIS OVER: 139 148 143 147 145 140"
F2473 22:02:38 TEST: [THIS_OVER] Ignored broadcast tokens [...] from GRAPHIC frame (only SCOREBOARD honoured)
F2578 22:04:39 OVER: Over 2 complete: ['139', '148', '143', '147', '145', '140'] = 862 runs, 0 wkts
F2579 22:04:42 OVER: Completed over flushed (new bowler 'Nandre Burger' replaces 'Jofra Archer')
```

**Root cause:** the broadcast strip on this match's production overlay
literally labels the **per-ball-speed track** with the field name
"`THIS OVER:`".  Scout faithfully extracted whatever followed that
label.  `OverManager._handle_broadcast_tokens` accepted the 6-token
list verbatim because:
1.  Frame F2461 was classified as `cam=scoreboard` (not `cam=graphic`),
    so the "ignore GRAPHIC frame" defense did not fire.
2.  The local `this_over` was all-`?` placeholders, so the
    `Broadcast replaces all-placeholder local` path triggered.
3.  **No token-alphabet validation** — 3-digit integers (categorically
    invalid as a single-ball outcome; max possible is 7) were accepted
    as legal run-tokens.

The defense at F2473 (`from GRAPHIC frame`) did fire on subsequent
frames once Scout re-classified them — but by then the local had
already been written, and **no path clears once-written tokens**.

**Damage scope:**
- "This Over" UI chip displayed `[139, 148, 143, 147, 145, 140]` for
  ~2 m 15 s (F2461 22:02:24 → F2578 22:04:39)
- Over-history archive permanently records `Over 2 complete: ... = 862 runs`
- **Bowling card NOT corrupted** — `BOWLER-STALE` defense correctly
  held Archer at his pre-over figures because the bouncing strip reads
  during dead-time (`Archer 0-14 (1)`, `Archer None-None (None)`)
  failed consensus.  `BOWLER-AUTO` never consumed the 862-run delta.
- Score totals NOT corrupted (absolute score ticker is independent)
- Wire commentary unaffected (per-ball, doesn't read `this_over`)

**Latency:** the bug has been latent for at least 9 days.  Earlier
matches show the same `Broadcast replaces all-placeholder local` log
firing with garbage payloads:
- 2026-04-16: `['2161']` × 7, `['11']` × 3, `['41']`, `['11', '.', '41']`
- 2026-04-25 (today): `['139', '148', '143', '147', '145', '140']`

Today's match is the first time the corruption was actually caught
end-to-end (UI chip + over-history archive); earlier occurrences may
have been masked by subsequent legal observations or by short-list
filters that incidentally rejected single-token lists.

**Fix shape — aligned with existing `_merge_broadcast` semantics in `files/eyes/this_over.py:635-663`:**

The normalizer at L635 already enumerates the legal token set
(`Wd`/`Nb`/`W`/`{N}lb`/`{N}b`/`.`/digit) but has two open doors:
1.  L659: `elif t.isdigit(): result.append(t)` — accepts any digit
    string, no range constraint.
2.  L661-662: `else: result.append(t)` — appends unknown tokens as-is.

Plus the `_apply_broadcast` path has three sites that wholesale-write
broadcast into `self.this_over` (lines 570, 584, 606) without a
shared sanity gate.

**Production-observed alphabet (verified across 5 days of logs):**
- `.`, `?`, `W`, `Wd`, `Nb` — bare singles
- `1`, `2`, `4`, `6` — single-digit runs (0/3/5/7 legal but not seen)
- `Wd+1`, `Wd+3`, `Wd+4`, `Wd+5`, `Nb+5` — **compound extras** (wide
  or no-ball that went for additional runs).  This form is emitted
  by the ball-event handler, not by `_merge_broadcast`, but appears
  in `this_over` arrays nonetheless — the validator must accept.
- `{N}lb`, `{N}b` — byes/leg-byes (rare; supported by parser, not
  seen in last 5 days)

**Fix (~18 source lines, 5 tests):**

```python
# files/eyes/this_over.py — new helper near _merge_broadcast
@staticmethod
def _is_legal_run_token(t: str) -> bool:
    """Strict cricket-notation alphabet for single-ball outcomes."""
    if t in {".", "?", "W", "Wd", "Nb"}:
        return True
    if t.isdigit() and 0 <= int(t) <= 7:
        return True
    # Compound extras: Wd+N, Nb+N (wide/no-ball with runs)
    for prefix in ("Wd+", "Nb+"):
        if t.startswith(prefix):
            rest = t[len(prefix):]
            return rest.isdigit() and 0 <= int(rest) <= 7
    # Byes / leg-byes: {N}lb, {N}b
    if t.endswith("lb") and len(t) > 2 and t[:-2].isdigit():
        return 0 <= int(t[:-2]) <= 7
    if (t.endswith("b") and not t.endswith("nb")
            and len(t) > 1 and t[:-1].isdigit()):
        return 0 <= int(t[:-1]) <= 7
    return False

# Add at each of the 3 self.this_over = broadcast sites:
if any(not self._is_legal_run_token(t) for t in broadcast):
    invalid = [t for t in broadcast
               if not self._is_legal_run_token(t)]
    log.warn(
        f"[TOKEN-VALIDATE] Rejecting broadcast tokens "
        f"{broadcast} — invalid token(s) {invalid} "
        f"(speed-track or graphic mislabel suspected)")
    return
```

**Tests to add:**
1.  Replay F2461 (2026-04-25 match-2): assert
    `['139','148','143','147','145','140']` rejected, local stays
    `['?', '?', '?', '?', '?']`.
2.  Older fixture (2026-04-16 F122): assert `['2161']` rejected.
3.  Compound-extras accept: `['Wd+4', '.', '4', '1']` accepted (real
    production sequence from match-2 over 4).
4.  Boundary: `['7']` accepted (legal max single-ball runs), `['8']`
    rejected.  `['Wd+5']` accepted, `['Wd+8']` rejected.
5.  Mixed-list: `['1', '2', '139']` rejected as a whole, not silently
    dropping one bad token.

**Status:** Documented during live monitoring.  Same defer profile as
the target=640 and W/6-swap items — bounded damage, no
write-corruption to bowling card, fix scope known, log-replay test
fixtures available across multiple matches (earlier `2161` /  `41` /
`11` payloads provide additional regression material beyond today's).

---

## P1 (live UX): deferred-extras + next-ball-runs collapsed into `Wd+N` (2-deliveries-as-1)

**Discovered (2026-04-25 RR vs SRH match-2 innings 2 over 5):** for
SRH's 5th over (Burger→Deshpande), broadcast scored:

```
4.0 Wd  +1   (52→53)
4.1 4   +4   (53→57)
4.2 1lb +1   (57→58)
4.3 4   +4   (58→62)
4.4 4   +4   (62→66)
4.5 4   +4   (66→70)
```

Pipeline emitted `['Wd+4', '.', '4', '1', '4', '4']` — a `Wd+N`
compound at 4.0 that swallowed the **next ball's** 4-run boundary,
followed by a phantom `.` filling the position that the 4.1 boundary
should have occupied.  Then 4.2's leg-bye → recorded as `4`, 4.3's
boundary → recorded as `1`, 4.4 and 4.5 boundaries shifted into
correct positions only because the run values converged.  Three of
six balls per-delivery wrong; total runs sum invariant (18=18) so
score and chase math hold, but commentary, last-delivery panel, and
the over ticker all describe the wrong events.

**Trace from `logs/pipeline-2026-04-25-203819-rr-srh-v5-bowler-stale-fix.log`:**

```
F2776 22:10:04 BOARD:       score 52→53 [+1]
F2776 22:10:05 COMMENTARY:  [EXTRA] method=deferred reason=no_corroboration
                            score+1 at overs=4.0 — will confirm next frame
F2789 22:11:01 BOARD:       score 53→57 [+4]
F2789 22:11:01 TEST:        ball_event=EXTRA, ball_event_runs=5,
                            ball_event_extra=wide → this_over=['Wd+4']
F2789 22:11:01 COMMENTARY:  [EXTRA-IMMEDIATE] wide: score +5,
                            overs unchanged (4.0)
F2814 22:12:17 BOARD:       score 57→61 [+4] (ball_event_over=4.2;
                            phantom dot inserted at 4.1 to fill gap)
```

**Root cause:** the deferred-extras consolidation logic merges a
recently-deferred `+1` extra with a fresh `+N` runs-delta if both
arrive within the consolidation window, treating the pair as a
single `Wd+N` (or `Nb+N`) compound delivery.  The merge decision has
no signal that distinguishes:

- **Genuine wide-with-byes**: `Wd+4` = one delivery, +1 wide + +4
  byes from misfield.  Both signals arrive close in time (<10s)
  because the byes are scored on the same ball.
- **Wide + next-ball boundary**: `Wd` then `4` = two deliveries.
  The +1 wide is scored, then the bowler bowls a fresh delivery and
  the batter hits a boundary off it.  Signals arrive ~30-60s apart.

In this incident the gap was **57 seconds** (F2776 22:10:04 →
F2789 22:11:01), strongly indicating two deliveries.  The merge
fired anyway because the consolidation window doesn't enforce a
tight time-gap upper bound.

**Damage scope:**

- `this_over` chip: 3 of 6 balls misclassified per-delivery (UI shows
  wrong outcome glyphs in 3 positions).
- Last-delivery panel (`LAST DELIVERY`): describes the wrong event
  for the affected ball.
- Wire commentary for the merged ball: invents a "5 extra runs from
  a wide" story that didn't actually happen on broadcast.
- Storyteller commentary: anchors on the merged event and produces
  fictional narrative.
- Over-archive (`completed_over`): wrong per-ball breakdown stored.
- Score totals: **correct** (sum-invariant).
- Bowling card runs: **correct** (aggregates over the over).
- Bowling card balls-bowled: potentially off-by-one because the
  phantom `.` at 4.1 may consume a legal-ball slot that the real
  4.1 boundary should have.
- Striker balls-faced: at this incident, Abhishek went 22(12)→22(15)
  across the over, which actually matches reality (3 legal balls
  faced as non-striker rotated), so individual cards likely OK on
  this specific instance.

**Disambiguator signals available:**

1.  **Time gap** (primary): same-ball wide-byes resolve in <10s on
    the broadcast strip; separate deliveries are 30-60s apart.  The
    consolidation window should reject merges with gap >15s.
2.  **Striker balls-faced increment**: byes from a wide do not
    increment striker balls-faced; a fresh legal ball does.  If the
    striker's `balls` field incremented between the two signals, it
    was a separate ball.
3.  **Broadcast `THIS OVER` ticker count**: if the ticker shows two
    distinct ball icons in the window, two deliveries occurred.
    Sampling the ticker at the consolidation decision point gives a
    strong signal (but adds vision dependency to a scorer-loop
    decision, which is architecturally awkward).

**Fix shape (~25-30 source lines, 3 tests):**

Tighten the deferred-extras consolidation predicate.  Currently
something like:

```python
if deferred_extra_pending and runs_delta in (4, 6):
    consolidate_as_wide_with_byes(deferred_extra, runs_delta)
```

Becomes:

```python
if (deferred_extra_pending
        and runs_delta in (4, 6)
        and (time.time() - deferred_extra_ts) < 15.0
        and striker_balls_unchanged_since_defer):
    consolidate_as_wide_with_byes(deferred_extra, runs_delta)
else:
    # Two separate deliveries: emit the deferred extra as its own
    # token first, then handle the runs_delta as a fresh ball.
    flush_deferred_extra_as_standalone()
    handle_runs_delta_as_fresh_ball(runs_delta)
```

**Tests to add:**

1.  Replay 2026-04-25 over-5 fixture (F2776 + F2789, 57s gap):
    assert two tokens emitted (`Wd` then `4`), no `Wd+4` compound,
    no phantom `.` at 4.1.
2.  Genuine wide-with-byes fixture (synthetic or replay): +1 then
    +4 within 8s gap, striker balls unchanged → assert single
    `Wd+4` token emitted.
3.  Boundary case: 14s gap → still consolidate (within window).
    16s gap → split into two tokens.

**Defer rationale:** mid-match heuristic-window tuning needs replay
testing across multiple matches; today's match-2 fixture is the
primary regression material but a synthetic genuine-`Wd+4` fixture
also needed.  No write-corruption (totals invariant), bounded
damage (per-over UI artifact), inter-match commit appropriate.

---

## P1 (live UX): `this_over` token order reflects detection time, not chronological ball time

**Status: STAGED 2026-04-25 inter-match commit bundle as Fix 3 — `Scoreboard.on_fow_upgrade` callback drives `this_over` chronological reorder; wired in `test_pipeline.py` main loop. Awaits seam restart; transitions to SHIPPED at land time per `staged_fixes_2026-04-25/README.md` step 6.**

**Discovered (2026-04-25 RR vs SRH match-2 innings 2 over 0):** the
"This Over" chip on the UI displayed `[., ., ., Wd, W, 6]` for SRH's
opening over.  Real broadcast order was `[., ., ., Wd, 6, W]` — Sharma
hit a six on ball 0.4, Travis Head was dismissed on ball 0.5.

**Trace from `logs/pipeline-2026-04-25-203819-rr-srh-v5-bowler-stale-fix.log`:**

| frame | time     | event detected | tokens after |
|-------|----------|---------------|--------------|
| F2027 | 21:47:51 | `score 0→1`, `Extra detected — added 'Wd'` | `[., ., Wd]` |
| F2034 | 21:48:26 | `score regressed 1→0`, `[ROLLBACK] popped extra token 'Wd'` | `[., ., .]` (Wd reverted on broadcast oscillation) |
| F2043 | 21:48:48 | `score 0→1` again (re-tick) | unchanged |
| F2047 | 21:48:54 | `Extra detected — added 'Wd'` (re-add) | `[., ., ., Wd]` |
| F2048 | **21:49:00** | `wickets 0→1`, FOW W1 placeholder | `[., ., ., Wd, W]` ← W appended |
| F2049–F2067 | 21:49:00–21:49:44 | 45 s of `FRAME_POISONED` / `cam=graphic` / `dead-time skip` (wicket replay/celebration) | (unchanged) |
| F2068 | **21:49:45** | `score 1→7`, `Abhishek Sharma: 0(0)→6(4)` | `[., ., ., Wd, W, 6]` ← 6 appended |
| F2117 | 21:51:23 | `[FOW] Upgraded placeholder W1: Travis Head at 7/1 (0.5)` (wicket retroactively pinned to 0.5) | unchanged — token order not re-sorted |

**Root cause:** `OverManager.this_over` orders tokens by **broadcast-ticker detection time**, not by **ball.over event time**.  The broadcast updated the wickets ticker before the strip score (the wicket overlay animates immediately, while the strip score lags through replay/celebration).  Pipeline appended W at F2048, then 6 at F2068.  When the FOW was retroactively pinned to 0.5 at F2117, `this_over` was not re-sorted — the token order is frozen as observed.

**Damage scope:** any wicket-ball over where a boundary happens immediately before the wicket and the broadcast updates the wickets ticker faster than the score ticker.  Estimated 5–15 % of wicket-ball overs based on production cadence.  Affects:
- "This Over" UI chip (visible swap in screenshot)
- Per-ball commentary attribution if commentary indexes by `this_over`
- Match analytics if computed from per-ball history
- Highlight-reel ordering if any tool consumes the over sequence

**Not affected:** total runs / wickets / score, final scorecard, bowling figures (`BOWLER-AUTO` uses absolute deltas), Wire commentary (each event described independently with its own ball reference).

**Fix candidates:**

1.  **Reorder on FOW assignment.**  When `[FOW] Upgraded placeholder W{N}` pins a wicket to ball X.Y, walk `this_over` and move the W token to position X.Y.  ~10–15 source lines, but needs careful indexing so legal-ball positions stay aligned with extras.
2.  **Use `ball_event_over` for insertion ordering.**  When appending a token, insert at the position implied by `ball_event_over` rather than at the end.  Requires every event source to carry over.ball; `BOWLER-AUTO` increments don't.
3.  **Defer token-emit until strip catches up.**  If a wickets-tick fires while the score is in `FRAME_POISONED` / `dead-time` and a score-jump is pending, hold the W token until the score resolves, then emit in correct order.  Complex state machine, possible deadlock if score never resolves.
4.  **Snapshot wicket-context at detection.**  Capture `striker_at_wicket` and `non_striker_at_wicket`; if later evidence shows the dismissed batter wasn't on strike at detection time (boundary by the other batter happened first), reorder.  Heuristic; depends on accurate striker tracking (which has its own collision bug).

**Recommended path:** Fix 1 (reorder on FOW assignment) — has narrowest blast radius, well-defined trigger, and the FOW upgrade event is already the natural rendezvous where the pipeline knows the wicket's true ball index.  Implementation lives in `files/eyes/this_over.py` (the `OverManager` class) plus the FOW-upgrade callsite in `files/eyes/scoreboard.py`.

**Empirical FOW vs over-completion timing (verified 2026-04-25, 6 wickets):**
all 6 FOW upgrades fired **before** over completion, with lead times
ranging 19 s (W1 inn2) to 4 m 04 s (W6 inn1).  So Fix 1's trigger is
reliable in production today.

**Residual race risk:** wicket on **ball X.6** (last legal ball of
over) could theoretically have FOW upgrade race over completion.
Defensive backup: add a sort step inside `_complete_over()` before
archival, keyed by per-token `ball_event_over`.  ~3 extra lines,
eliminates the residual race.

**Status:** Documented during live monitoring, not yet shipped.  Same trade-off as the target=640 bug: defer to between-matches for clean ship.

---

## P0 (live UX): Innings-1-final latch poisoned by extractor hallucination → wrong `target` in innings 2 — **SHIPPED-pending-validation** (Fix 1 + Fix 9a/9b target hygiene, 2026-04-25..26 bundles)

**Status: STAGED 2026-04-25 inter-match commit bundle as Fix 1 — innings-1-final latch sanity bound (target ≤ 350 / overs ≤ 20.0) at `test_pipeline.py`. Awaits seam restart; transitions to SHIPPED at land time per `staged_fixes_2026-04-25/README.md` step 6.**

**Discovered (2026-04-25 RR vs SRH match-2 innings 2):** at innings
transition the pipeline injected `target=640` instead of the correct
`229` (228 + 1).  Trace from
`logs/pipeline-2026-04-25-203819-rr-srh-v5-bowler-stale-fix.log`:

| frame | time     | event |
|-------|----------|-------|
| F921  | 21:12:02 | `[INNINGS-END] Latched innings 1 final candidate: 639-4 (76.5).` — bogus extraction (T20 caps at 20 overs; impossible) latched while scoreboard was at 17.1 overs |
| F921  | 21:12:02 | `[INNINGS-END] overs=76.5 reached in innings 1 (scoreboard 17.1) — letting frame through to register final + trigger transition.` |
| F1445 | 21:30:01 | `[INNINGS-BREAK] Innings 1 end detected (overs_complete_20: overs=20.0 wickets=6) — latched_final=639 target=640. ...` |
| F1445 | 21:30:01 | `[INNINGS-CHANGE] inn1 final=228/6 (20.0) target=640 cold_start_inn2=False` — real final 228 ignored, phantom 639 used |
| F1445 | 21:30:01 | `[INNINGS] Set to 2. Target: 640. All trackers reset.` |
| F2019+ | 21:47:12+ | innings-2 frames carry `AFTER_target=640|AFTER_innings=2` |

**Root cause:** `test_pipeline.py:5392-5404` latches the running
innings-1 final using **max-score-wins** (to handle "digits torn
across multiple end-zone frames" — where e.g. `159` is OCR'd as
`15` then `159`).  The heuristic has no upper sanity bound, so an
upward extractor hallucination (`639-4 (76.5)`) gets latched and
then locks out the real final because `228 < 639`.

**Impact:** all innings-2 derived UI fields are wrong:
- `target` displayed as 640 (vs correct 229)
- Required Run Rate inflated catastrophically (`(640 - score) / overs_left`)
- Chase-progress percentage wrong
- Any "X to win" / "X needed off Y balls" UI lies

**Not affected:**
- Wire / storyteller / analyst commentary (read `ext_score`,
  `ext_bowl` directly; they describe individual deliveries
  correctly without target context)
- Bowling cards, batting cards, FOW (no target dependency)
- Innings-1 record (228/6 in 20.0 stays correct in the rollup)

**Fix candidate (~8 source lines, 2 tests):**

```python
# T20 caps at 20 overs and historical max ~263; reject
# extractor hallucinations before letting them poison the
# latched target.  Without this guard, an upward outlier
# locks out subsequent legitimate finals via max-wins.
try:
    _cand_overs_f = float(_ext_overs_raw)
except (TypeError, ValueError):
    _cand_overs_f = -1.0
if _cand_overs_f > 20.0 or _cand_score_i > 350:
    log.info(
        f"  [INNINGS-END] Rejecting bogus latch candidate "
        f"{_cand_score_i}-{_cand_wkts_i} ({_ext_overs_raw}) "
        f"— exceeds T20 sanity bounds")
else:
    # existing max-wins block, unchanged
    if (_cand_score_i > _existing_score_i
            or (_cand_score_i == _existing_score_i
                and _cand_wkts_i > _existing_wkts_i)):
        innings_1_total = {...}
```

**Tests to add:**
1. Replay F921 phantom (`639-4 (76.5)`) against fresh pipeline state;
   assert `innings_1_total` not updated.
2. Replay normal F1445 sequence (`228-6 (20.0)`); assert latched.
3. Boundary: `350-10 (19.6)` — below threshold, latched.
   `351-10 (19.6)` — above threshold, rejected.

**Status decision:** match-2 chase is mid-flight at the time of
discovery.  Hot-fix vs defer trade-off documented in chat
transcript.  User decision pending.

**Related broadcast-target fallback gap (P2 follow-up):**
the trigger first checks `_bcast_target_now` (broadcast TARGET
ticker overlay).  At F1445 it was None, falling back to the
poisoned latch.  If the innings-break broadcast graphic could
be parsed for "229" / "to win 229" / "TARGET 229", that would
provide a second corroboration channel.  Smaller leverage than
the sanity-bound fix.

---

## P1: Target-source-confusion at AUTO-SWAP boundary — STAGED as Fix 9a + Fix 9b (2026-04-26)

**Status:** **STAGED 2026-04-26 17:55 IST as Fix 9a + Fix 9b
in `test_pipeline.py`** (paths a + b shipped together; path c
deferred as architectural follow-up).  All 256 tests in
`test_recent_fixes.py` pass (16 new Fix 9 tests added).
Awaits inter-match seam restart for live validation against
the next innings transition.

**Original filing (2026-04-26 17:24 IST):** initially diagnosed
as mid-innings join confusion.  **Reframed at 17:31 IST after
subsequent observation showed GT actually starting innings-2
at over 0.1 (F2665).**  The F2504 strip read of
`GT 66-4 (11.5)` was **not live play** — it was a misread
of a scorecard/season-stats panel or promo graphic shown
during the innings break.  The pipeline's strip parser
cannot distinguish live broadcast strips from
scorecard/promo graphics, and ingested the panel as live
state.

**Blast radius is broader than initially scoped (live-monitoring
update 2026-04-26 17:51 IST).**  During post-staging live
monitoring, the user surfaced a separate symptom: **overs not
advancing in innings-2 UI** (stuck at 0, broadcast moving
through 0.1, 0.5, 1.5).  Source dive showed this is the **same
root cause** — `set_innings_2()` never running means the
`Scoreboard.set_innings_2()` reset path is a complete no-op,
not just the target-injection sub-step.  The reset path at
`scoreboard.py:466-499` does much more than set target:

- `self._tracker = ConsistentReadTracker()` — fresh tracker with
  `confirmed["overs"] = None`.  Without this, `confirmed["overs"]
  = 20.0` from innings-1 persists.  Every legitimate innings-2
  overs read (2.3, 2.4, 2.5, 3.0) regresses from confirmed=20.0
  → `[CONSENSUS-BLOCKED]` rejects it.  Match log: **63
  hard `[CONSENSUS-BLOCKED]` overs rejects + 409 `[SUSPICIOUS]
  overs: 20.0→X (backwards)` rejects + 0 successful overs writes
  in innings-2** during live monitoring window.  UI overs stuck
  at innings-1's final.
- `self.fall_of_wickets = []` reset — without this, innings-1's 7
  FOW entries persist (the `[FOW] Length 7 > wickets counter 0
  — keeping all FOW entries (immutable). Wickets counter likely
  regressed.` log fired at F2503 confirms the carryover).
- `self.extras = self._blank_extras()` / `self.this_over = []` /
  `self.over_history = {}` / `self.bowler_speeds = {}` /
  `self._dismissed_recovery = {}` — all carry-over.
- `self.innings[2] = self._blank()` — innings-2 dict initialized
  fresh.  Without this, innings-2 may share state with whatever
  innings[2] was at module-init or an inadvertent earlier write.

So Fix 9a's blast radius is closer to **"the entire
`set_innings_2()` reset path was a no-op for this match"** rather
than just "target injection failed."  This raises the value of
shipping Fix 9a substantially: one fix closes the target=66
symptom, the overs-stuck symptom, the FOW-carryover symptom, and
the entire class of "innings-1 tracker state leaks into
innings-2" bugs.  Live UX impact is severe in the current match
(target wrong, overs frozen, RR/RRR/balls-remaining all wrong).

**Final root-cause diagnosis (after source dive):** the
target=66 commit was the result of a **3-step interaction**:

1. **F2503 AUTO-SWAP fires** with strip showing genuine GT
   cold-start `GT 0-0 (0.0)`.
2. **`assign_teams(...innings=2)` runs first** at AUTO-SWAP
   handler line 5343.  This has a side effect at
   `assign_teams` line 2799: `scoreboard.current_innings =
   innings`.  Now `current_innings = 2`.
3. **The `set_innings_2(target)` call at line 5347 is gated
   by `if scoreboard.current_innings == 1`** — but
   `current_innings` was just flipped to 2 by `assign_teams`
   in step 2.  So `set_innings_2` is **never called**, and
   target remains None in `scoreboard._inn`.
4. **F2504 LLM scorer's `team_assignment.target = 66`**
   parsed from misread strip showing `GT 66-4 (11.5)`.  The
   `elif scoreboard.current_innings == 2:` branch at line
   6855 had **unconditional** `scoreboard.set("target", _tv,
   frame_count)` — wrote target = None → 66.

So Fix 1's correct `latched_final=158 target=159` at F2421
was never *committed* due to the assign_teams ordering bug.
The actual fix has nothing to do with broadcast-graphic
detection; it's a clean ordering + monotonic-guard fix.

**Different bug shape than Fix 1** — Fix 1 catches "target
inflated to absurd value via OCR misread" (upper bound > 350);
this catches "target latched to wrong value via promo-graphic
ingestion during innings break" (lower bound, wrong-field, or
wrong-frame-context).

**Symptom (live, F2503-F2665+, 17:24:18-17:31:26+):** at the
AUTO-SWAP innings transition, pipeline emitted:

```
[17:24:18 F2503] [AUTO-SWAP] Innings 1 ended at 20.0 ov / 7 wkts
                 AND bowling team 'Gujarat Titans' visible on
                 strip — swapping teams immediately
[17:24:21 F2504] STRIP: GT 66-4 (11.5) | Gill 50(39) | Sudharsan 6(14) | Thakur 1-4 (2)
                 ← misread of innings-break scorecard/promo, not live play
[17:24:24 F2504 BOARD] target: None -> 66 [F2504]
                 ← target latched from misread; subsequent frames carry this
[17:31:13 F2657] STRIP: GT 6-0 (0.5)    ← real GT live play begins here
[17:31:26 F2665] STRIP: GT 0-0 (0.1)    ← actual innings-2 over 0.1
```

The pipeline saw a scorecard-panel-like strip during the
innings break and committed target=66 from it.  When real GT
play started at F2657-F2665, the bogus target=66 was already
cached and persisted (target field doesn't get rewritten by
subsequent strip reads in the same innings).  Net effect:
**innings-2 UI shows target=66 throughout GT's actual chase**
— RR, RRR, balls-remaining, "X to win" all wrong.

**Why Fix 1 doesn't catch this.**  Fix 1 is an upper sanity
bound (target > 350 or overs > 20.0 → reject).  66 < 350, so
Fix 1 correctly didn't fire — the value isn't absurd, it's
just *the wrong field*.  This is a complementary failure shape
that needs its own guard.

**Impact (live, currently manifesting in innings-2):**
- `target = 66` displayed in UI (correct: 159)
- Required Run Rate computed as `(66 - 66) / overs_left ≈ 0`
  (correct: `(159 - 66) / overs_left ≈ 11.0+`)
- "GT need 0 to win" type UI corruption for innings-2 duration
  unless target gets corrected by another path
- Chase-progress percentage wrong (GT shown as having reached
  target before they have)

**Fix as shipped (Fix 9a + Fix 9b, 2026-04-26):**

**Fix 9a — AUTO-SWAP target injection ordering + source.**
Two changes in the AUTO-SWAP handler (`test_pipeline.py`
lines ~5343-5410):

1. **Move `set_innings_2(target)` BEFORE `assign_teams`** so
   the `current_innings == 1` gate hasn't been flipped by
   `assign_teams`'s side effect.
2. **Source the target from `innings_1_total` (latched in
   the `[INNINGS-END]` block) rather than the live
   `scoreboard._inn.get("score")`.**  The live score can be
   None at AUTO-SWAP time due to FRAME_POISONED guards
   stripping late innings-1 reads showing the team's final.
   Use `max(latched, live)` to ensure the latched value
   wins when both are available.

New telemetry: `[AUTO-SWAP-TARGET] Injecting target=N
(latched_final=X, sb_score_live=Y) — sourced from latched
innings_1_total`.  Fall-through warning if both sources are
zero: `[AUTO-SWAP-TARGET] Target injection skipped`.

**Fix 9b — Target monotonic + sanity guards.**  At the
`team_assignment.target` write site (line ~6908):

1. **`[TARGET-MONOTONIC]`:** if `curr_target > 0` already
   set, refuse overwrite (warn-log only, idempotent same-
   value writes silently accepted).
2. **`[TARGET-SANITY]`:** if `curr_target == 0`, require
   proposed `_tv > _curr_score` (otherwise impossible in
   valid chase).  Else reject.

This is the original Path (a) + Path (b) combined.  Path
(c) (gate strip ingestion during innings breaks) was
deferred — Fix 9b's monotonic guard makes graphic-misreads
ineffective in steady-state innings-2, removing most of
path (c)'s urgency.

```python
# At the [AUTO-SWAP] trigger after innings detection
if scoreboard.target is None and innings_1_final_score is not None:
    scoreboard.target = innings_1_final_score + 1
    log.info(f"[AUTO-SWAP] Injecting target={scoreboard.target} "
             f"from innings-1 final {innings_1_final_score}")
```

**Path (b) — backstop sanity bound.**  Add `target >
current_team_score` as a guard at target-write time.  In a
valid chase, the target must exceed the chasing team's current
score by at least 1 (otherwise the chase is already complete or
the value is nonsense).  Catches the specific shape of this bug
(target ≤ current score is impossible in a live chase) without
addressing other potential field confusions.

```python
# Inside the target-write path
if (current_team_score is not None
        and proposed_target <= current_team_score):
    log.warn(f"[TARGET-SANITY] Rejecting target={proposed_target} "
             f"≤ current_team_score={current_team_score} — "
             f"impossible in valid chase")
    return  # don't commit
```

**Path (c) — DEFERRED as architectural follow-up:** root-
cause gate of strip ingestion during innings breaks.  The
deepest fix is preventing strip ingestion when the pipeline
is between innings.  Adds an `is_innings_break` gate that
suppresses scorebar processing until innings-2 is confirmed
live.  Larger scope (~30-50 lines).  Composes with the
existing **innings-break dead-time skip** logic.  After Fix
9b's monotonic guard ships, the immediate damage from
graphic-misreads is contained, and path (c) becomes a
quality-of-pipeline improvement rather than a P1 fix.
File for a future architectural session.

**Why combine all three:** path (a) is the principled fix at
the canonical hook; path (b) is the write-site backstop that
catches *any* target-source confusion regardless of cause;
path (c) addresses the root cause (don't ingest non-live
frames in the first place).  Path (a) addresses *this bug*;
path (b) addresses the *target-value class*; path (c)
addresses the *broader class of innings-break-frame
ingestion* (which would also affect any other field — score,
batters, bowler — if a similar misread happened during a
break).  Recommend (a) + (b) for the immediate ship as ~15-30
lines combined; (c) as the architectural follow-up worth
auditing separately.

**Tests:**
1. Replay F2503 AUTO-SWAP fixture; assert `target` injected as
   `innings_1_final + 1 = 159` regardless of whether innings-2
   strip is observed first or after.
2. Replay F2504 strip with `STRIP: GT 66-4 (11.5)`; assert the
   target-write of 66 is rejected by path (b)'s sanity bound
   (current GT score = 66, proposed target = 66, 66 ≤ 66).
3. Boundary: target=159 with current_score=66 (legitimate
   live chase) — accepted.  target=66 with current_score=66 —
   rejected.  target=159 with current_score=159 (already
   reached) — rejected by sanity bound (would be a chase
   complete event handled separately).
4. Pre-existing Fix 1 test still passes (target=640, overs=76.5
   rejected by Fix 1 upper bound, never reaches the sanity bound).

**Composes with Fix 1:** Fix 1 catches upper-bound absurd values
(`target > 350` or `overs > 20.0`); this catches lower-bound
confusion (`target ≤ current_team_score`).  Together they
bracket the target-value space: `current_team_score < target ≤
350` is the only valid range for a live target.  Both fixes
shipping gives bracketed validity at both ends.

**Composes with the AUTO-SWAP-cold-join coverage gap (P2,
filed below):** if the cold-join coverage gap is closed
(pipeline tails innings-2 from over 0), this bug becomes harder
to trigger because the first innings-2 strip would show `GT 0-0
(0.0)`, and target-inference at that frame would latch 0 as
target — still wrong, but path (b) would reject (0 ≤ 0).
Path (a) is the principled fix regardless of cold-join coverage.

---

## P2 (observation): Cold-start mid-innings-2 join — RE-RESOLVED 2026-04-26 18:20

**Status:** Filed 2026-04-26 17:24 IST during CSK-vs-GT
transition; collapsed at 17:31 IST when GT was found to
have started from over 0.1.  Re-opened briefly at 18:18 IST
after the Fix 9/10 restart appeared to re-expose the gap
(pipeline cold-started at ~7 overs into GT's chase with
`current_innings=1, target=None`).  **RE-RESOLVED at
18:20 IST** when investigation showed the existing
`[CODE] HIGH-CONF` regex path *does* handle this case
correctly — at F40 (~2 min after the 18:16 restart), the
pipeline detected a "TO WIN 96 OFF 75" overlay, computed
`target = score + runs_needed = 63 + 96 = 159`, and self-
corrected:

```
[CODE] HIGH-CONF: score=63 runs_needed=96 balls_remaining=75
       → target=159  pattern=TO\s+WIN[\s:]+(\d{1,3})\s+OFF
[CODE] HIGH-CONF target 159 — instant innings 2 swap
       (TO WIN N OFF M regex).
[INNINGS-CHANGE] source=to_win_N_off_M  inn1 final=63/1 (7.3)
                 target=159  cold_start_inn2=True
                 (by_frame=False by_state=True)  frame=40
[INNINGS] Trackers reset for innings 2
```

**Resolution:** the cold-start path is well-handled by the
existing `TO\s+WIN[\s:]+(\d{1,3})\s+OFF\s+(\d{1,3})`
regex with `cold_start_inn2=True` mode.  The brief window
between cold-start (F2 in our case) and target-overlay
detection (F40) is bounded by how often the broadcast
surfaces the chase overlay — empirically ~2 minutes in
this match.  No standalone fix needed.

**Useful lessons captured:**

1. The pipeline has *three* paths to set
   `current_innings = 2` and target:
   - **AUTO-SWAP transition** (Fix 9a strengthens this):
     fires at innings-1 → innings-2 boundary when pipeline
     is alive across the seam.
   - **`TO WIN N OFF M` regex with `cold_start_inn2=True`**
     (this resolution): fires at cold-start mid-chase when
     the chase overlay surfaces.
   - **`team_assignment.target` write** (Fix 9b guards
     this): fires when the LLM scorer parses a target value
     from the strip.  Now monotonic-guarded.
2. Diagnosis order for unexpected mid-innings state must
   include "is the pipeline still in cold-start mode and
   waiting for an overlay?" before either "graphic misread"
   (the 17:31 collapse hypothesis) or "missing reset path"
   (the 18:18 re-open hypothesis).

**Carry-over lesson from the original collapse:** when a
strip read shows unexpected mid-innings state at innings
transition, the diagnosis order should be: (1) is this
live play or a scorecard/promo graphic? (2) if a graphic,
why didn't the camera-state gate suppress it? (3) only
after ruling out graphic-misread, consider coverage gap.

---

## P0 (live UX): Cold-start mid-match-join initial-team-misassignment causes ~3-minute window of visibly-wrong UI — **SHIPPED-partial-pending-validation** (Fix 17 Paths A+D + related cold-start gates; residual join edge may remain)

**Filed 2026-04-26 20:15 IST during LSG-vs-KKR live monitoring.**
The user observed (and reported as "enough for user to notice
the bad state") that on pipeline start the UI showed
`LSG 0/0` for ~3 minutes before recovering to the correct
`KKR ~30/3`.  Forensic timeline from
`logs/pipeline-2026-04-26-194909-lsg-kkr-fix12-v6-validation.log`:

```
F0  19:59:17  PIPELINE STARTED — NO TEAM ASSUMPTION
F2  19:59:28  No batting team set — skipping all updates
F3  19:59:33  No batting team set — skipping all updates
F4  19:59:36  AD (skipped)
F5  19:59:44  GRAPHIC cam=graphic → dead-time skip
F6  19:59:49  [TEAM] From broadcast abbr: LSG → Lucknow Super Giants
              STRIP: LSG 0-0 (0.0) |
              === TEAMS SET: LSG batting (inn 1) vs KKR bowling ===
F7  19:59:56  STRIP: KKR 0-0 (0.0)
              [GUARD] Visible team 'KKR' is bowling team — ALL data stripped (1/30)
F8-F90 …      [GUARD] … (counter slowly climbs while live KKR strips arrive)
F104 20:03:01 [TEAM-LOCK ESCAPE] Stripped 20 consecutive KKR frames
              AND zero ball events ever fired for current batting team 'LSG'
              — team assignment was the misread, not the strip.  Forcing swap.
              === TEAMS SET: KKR batting (inn 1) vs LSG bowling ===
F105 20:03:04 (cold-start tracker accepts Cameron Green/Powell)
F113 20:03:20 (score 28/3 finally seeded; SM cold-start consensus 1/3)
F122 20:04:05 STATE: KKR 29-3 — first correct UI emission
```

**Total bad-UX window: F6 19:59:49 → F122 20:04:05 = 4:16 minutes.**
The most acute portion (UI showing `LSG 0/0` actively-broadcast)
ran from F6 → F104 ≈ **3:12 minutes**.  After F104 the pipeline
correctly identified KKR but score was still null until F113.

**Why the misread happened (F6):**
Single-frame strip `LSG 0-0 (0.0) | ` accepted as authoritative.
This is almost certainly a pre-match comparison/team-reveal graphic
("LSG vs KKR" with team-side scoreboard showing 0/0) that the
camera-state gate did not flag as a graphic.  The previous frame
(F5) WAS gated as `cam=graphic → dead-time skip`, so the
detection logic *can* identify these — F6's just slipped through
on the same broadcast pattern.

**Why recovery took so long (F6 → F104):**

1. **`TEAM-LOCK ESCAPE` threshold is 20 consecutive
   wrong-team strips.** Counter prints `(1/30)` through `(19/30)`
   then forces swap at 20.  At ~5-15s/frame cadence (close-ups,
   ads, replays interleave with live SCOREBOARD frames), 20
   live-strip reads takes 2-4 minutes wallclock.

2. **First-team-set has no consensus requirement.**
   Score, overs, batter-runs, bowler-stats all use 3-frame
   cold-start consensus before committing.  Team assignment
   is single-frame (F6 set TEAMS SET on one observation).
   This is asymmetric: a misread `score=0` would have waited
   for 2 corroborating reads, but a misread `team=LSG`
   committed instantly and then poisoned everything downstream.

3. **The wrong-team GUARD goes UP only.**  Counter increments
   `(1/30)`, `(2/30)`, … but never resets when intervening
   ad/closeup frames break the streak — so a single live-strip
   read every 30s contributes one increment, slowly climbing.

4. **`FRAME_POISONED` rejections (F56-F90) don't go through
   `POISON-STREAK` consensus.**  POISON-STREAK fires on the
   extractor-driven path with non-null `_ext_score_int`; F56
   onward had `ext_score=None-None(None)` because the GUARD
   stripped data before extractor-merge.  Consensus mechanism
   intended exactly for this case never engaged.

5. **WS broadcast emits the bad state immediately.**  From
   F6 onwards the WS payload sends `batting_team='Lucknow Super
   Giants', score=0/0` to all connected clients.  No
   "still-initialising / loading" gate before first
   committed-consensus state.

**User-observable impact:**
Whoever is watching the UI at pipeline-start sees "LSG 0/0"
displayed prominently for ~3 minutes despite the broadcast
clearly showing "KKR 28/3 (5.1)".  This is the most visible
correctness failure the pipeline currently has at startup;
once converged, the system is well-defended against most
in-match anomalies, but cold-start has no equivalent guard.

**Proposed fix paths (composable, all three together = full
defence-in-depth):**

**Path A: Pre-match graphic gate at strip-text level
(small, ~10-20 lines, highest leverage).**
Reject any SCOREBOARD strip read of form
`<TEAM_ABBR> 0-0 (0.0)` (or trivial variants `0/0`, `0 - 0`)
when the pipeline has not yet seen any non-zero score.  Pre-
match team-reveal/toss graphics universally show this pattern;
no live-cricket frame would legitimately have all three of
`score=0, wickets=0, overs=0.0` mid-match-join.  Combine with
the existing `cam=graphic` gate as an AND-fallback —
`(strip_is_zero_zero_zero) AND (no committed score yet)` →
treat as graphic, don't run TEAM extraction.  Closes F6
exactly.

**Path B: First-team-set consensus requirement
(medium, ~25-40 lines, structural fix).**
Mirror the cold-start tracker's 3-frame consensus pattern
for `batting_team` assignment.  Buffer the first ≥3 candidate
team observations; commit only when 3-of-N agree (or when an
authoritative confirmation arrives, e.g. a live ball event).
Cost: adds ~30s-2min to time-to-first-team-set on a clean
start; benefit: a single misread can't poison downstream
state.  The asymmetry between "score requires consensus, team
does not" is itself a smell — this fix makes them symmetric.

**Path C: Lower TEAM-LOCK ESCAPE threshold (tiny, ~3-5 lines,
fast but partial).**
Drop the threshold from 20 consecutive wrong-team strips to
~5 (matching POISON-STREAK precedent).  Composes with Path A
(if A catches the misread, C never fires; if A misses,
C escapes faster).  At 5-frame threshold, recovery would
have been ~30-90s instead of ~3min.  Doesn't fix root cause
but materially reduces the bad-UX window when other paths
fail.

**Path D: WS broadcast gate during cold-start
(small, ~10-15 lines, decouples UX from state-correction
time).**
Don't push state to WS clients until either:
(a) first committed cold-start consensus completes, OR
(b) a "loading…" / "warming up" placeholder until
sufficient state is acquired.
Even if recovery takes minutes, the UI never displays
visibly-wrong state during the window.  This is the most
direct user-experience-improving fix; the others reduce
the *duration* of the bad state, this one prevents it from
ever being shown.

**Recommended ordering:** Path A first (smallest, highest
leverage, closes the originating misread).  Path D second
(decouples UX impact from internal recovery time).
Path B third (structural correctness).  Path C as
defensive backstop.  All four together = robust cold-start.

**Test fixture available:**
`logs/pipeline-2026-04-26-194909-lsg-kkr-fix12-v6-validation.log`
F6-F104 captures the full mechanism end-to-end.  Path A
unit test: replay F6 strip → expect graphic-skip not
TEAMS SET.  Path B unit test: replay F6 + F7-F8 alternating
LSG/KKR → expect KKR (majority of first 3) wins.
Path C unit test: replay F7-F77 wrong-team strips →
expect TEAM-LOCK ESCAPE at strip-5 not strip-20.
Path D unit test: WS-broadcast subscriber receives no
emission before first SM commit completes.

**Severity:** P0 (live UX), because it directly produces
user-visible-wrong state on every cold-start mid-match-join
where the broadcast happens to surface a pre-match team-
reveal graphic in the first SCOREBOARD frame.  This is the
common case for any mid-match join (broadcaster cycles such
graphics regularly).

**Cross-references:**
- The cold-start mid-innings-2 join entry (P2 above, RE-RESOLVED
  2026-04-26 18:20) handles a *different* cold-start case
  (target/innings recovery via `TO WIN N OFF M` regex).  This
  entry covers the team-assignment cold-start case which
  has no equivalent recovery overlay.
- Composes with the existing `[CACHE]` mechanism — when cache
  is fresh (<30 min), the fresh-cache path bypasses cold-start.
  This entry only matters for stale-cache or no-cache
  starts, which is the common real-world case for a pipeline
  restart in the middle of a match.
- The Path A heuristic ("strip showing `0-0 (0.0)` mid-match
  is a graphic") would also catch the broader class of
  pre-match team-reveal graphics that surface during innings
  breaks — connects to the P1 SM-reset gap entry's
  observation that scalar fields persist across innings
  transitions.

---

## P0 (live UX, surveillance): Phantom batter-stats injection from squad/season-aggregate readout — Powell `14(56)` at over 6.1 (impossible balls count) — **SHIPPED-pending-validation** (Fix 14 `BALLS-CEILING-GATE`, 2026-04-28 bundle)

**Surfaced 2026-04-26 20:06 IST during LSG-vs-KKR validation.**
At F191 the SCOREBOARD strip read `Powell 14(56)` and was
accepted into state.  This is impossible: Powell came in at
over 5.3 and got out at 6.1 (balls 33-37 of innings, max 4
balls faced).  The `(56)` is almost certainly Powell's
season-aggregate balls-faced or career figure leaked into
the live-stats strip via a stat-overlay transition.

**Why it bypassed existing guards:**
- `runs-monotonic` guard: 14 > 5, no regression, accepted.
- Fix 11 EXTRAS-INF gate: `bat_sum = 8 + 14 = 22 < score = 31`,
  no sum violation, accepted.
- `balls-monotonic` guard: 56 > 4, no regression, accepted.
- No "balls cannot exceed innings-total-balls-faced" check.
- No "balls delta cannot exceed wallclock delta" check.
- No "cap balls at innings_overs * 6" check.

**Self-corrected at F258** when batter-swap detected
(Powell → Rinku Singh).  Window of bad state: F191 → F258 =
~2:20 minutes.  CB-side ground truth showed Powell had been
dismissed at 1(4) since 6.1, but pipeline kept Powell active
with ever-increasing phantom figures until Rinku's name
surfaced and forced the swap.

**Proposed fix sketch:**
Cricket-physics ceiling check at admission time: per-batter
`balls` cannot exceed `current_innings_overs * 6 + extras_balls`.
For T20, `balls` field is bounded by 120; for any single batter,
bounded by `min(120, current_innings_balls_remaining_for_this_batter)`.
A batter at over 6.1 with `balls=56` is detectable as
impossible.  Reject the runs-and-balls update (similar to the
EXTRAS-INF gate's whole-row reject pattern, but on the
cricket-physics-ceiling axis instead of the bat-sum-vs-score
axis).

**Connects to:** Fix 11 EXTRAS-INF admission gate (same code
path in `apply_scorer_decision`, this would be a sibling check
on a different cricket-physics dimension).  Adding here
would round out the admission-time defence battery.

**Severity:** P0 (live UX) — produced visibly-wrong batter
figures on a primary scorecard tile for ~2 minutes during
live play.  Same severity class as the cold-start
team-misassignment above.

---

## P0 (live UX): Striker self-collision in `sb._inn` becomes stuck — both slots latched to one batter, blocks WS non_striker projection (UI shows `● Green —` despite Singh in AT THE CREASE) — **SHIPPED-pending-validation** (Fix 5 + Cluster 1 SM cutover + Fix 18)

**Surfaced 2026-04-26 20:25 IST during LSG-vs-KKR live
monitoring.**  User-visible damage observable in two
side-by-side screenshots from 20:25:24 and 20:25:31: the BIG
header shows the active batter (Cameron Green) with a green-
dot on-strike indicator, but the partner slot renders as `—`
even though `Rinku Singh` is plainly visible in the
**AT THE CREASE** table directly below with R/B/4s/6s/SR
populated.  The crease table is sourced from a different
payload field than the header indicators.

**Root cause (forensically traced from `pipeline-…-fix12-
v6-validation.log`):**

1. F703 (20:25:11): `[WS-PROJECTION-FALLBACK]` fires
   correctly, surfacing `striker='Rinku Singh'` from
   `sb._inn` (SM-null path).  Resulting `AFTER_striker=
   Rinku Singh, AFTER_non_striker=Cameron Green` — clean
   state.
2. F704 (20:25:17, ball_event=1_RUNS at 10.1): a single is
   scored.  Strike rotation logic engages.  After this
   frame, **both** `sb._inn.striker` and
   `sb._inn.non_striker` end up = `Cameron Green`.  Fix 5
   `[STRIKER-COLLISION]` correctly refuses the prior
   `non_striker=Rinku Singh` write (the sequencing is
   striker-first), but a downstream path then writes
   non_striker=Cameron Green again, locking in the
   collision.
3. F705 onwards (20:25:24+): every subsequent frame is
   stuck.  Fix 5 fires `[STRIKER-COLLISION] Refusing
   non_striker=Rinku Singh — already striker; would self-
   collide` on each scout-broadcast read attempting to
   re-install Rinku Singh, **preventing the truth from
   healing the corruption**.  SM stays null
   (`[SM] RUNS  65/4 (10.1)  striker=None`).
4. Fix 7 `[WS-PROJECTION-FALLBACK]` evaluates: `sb._inn.
   non_striker='Cameron Green' sm.non_striker=None
   active_batting=['Cameron Green', 'Rinku Singh']`.  The
   fallback's defence-in-depth `_other_slot` collision
   check correctly refuses to install `Cameron Green` as
   non_striker (would collide with payload striker
   `Cameron Green`), so non_striker remains `None` in the
   payload.  `[WS-PROJECTION-GAP]` warning fires.
5. UI receives `non_striker=None` → renders `—`.  Crease
   table rendered from a different field
   (`active_batting` or full scoreboard payload) which has
   both names → both batters show.  Header inconsistent
   with crease table.

**Why this is different from prior striker-collision bug
(filed P1 2026-04-23):**  The prior entry covered the
write-time guard (Fix 5, shipped); that guard correctly
prevents a fresh write from creating a collision but cannot
heal one that's already present.  This new finding is about
a DIFFERENT path that creates the collision after rotation
— the post-rotation `non_striker` re-install path.  Likely
candidates from source inspection:
- `assign_active_batters()` — rebuilds slots from scout-
  read order; if scout reads "Green | Rinku" but rotation
  already swapped striker, the non_striker write may end up
  duplicating striker.
- `update_batter()` non_striker-write path — when the
  rotation transition is in progress, may install the
  same name.
- A specific edge case at over-rollover or strike-rotation-
  on-completed-over (10.0 → 10.1 with 1 run is a
  rotation event, and 10.1 → 10.2 with 6 → no rotation;
  the boundary reads here are noisy).

Empirical evidence the truth path is being blocked, not
absent: scout strip on every subsequent frame says
`Green 26(17) | Rinku 15(14)` (correct, both batters
named).  The `[STRIKER-COLLISION]` rejections fire 70+
times in a 30-min window post-collision (per the
analyzer's `--report-10 --per-wicket` output: 70 fires on
wicket 4 window).

**User-visible window:** at least 7 minutes (F704 to
F800+) and counting; the collision does not self-heal
through the existing guards because each healing-attempt
is rejected.  Any user looking at the BIG header during
this window sees Green's partner as `—`.

**Sibling concern (architectural):** Fix 7's `_other_slot`
collision check is **correctly** refusing to use a
collided `sb._inn.non_striker` because it would just
re-emit the collision into the payload.  But Fix 7 is
defence-in-depth FOR `sb._inn` — when `sb._inn` itself
is corrupted, neither the WS projection nor the rotation
guard can help.  The architectural answer is **Path B
cutover (existing P1 entry, "Striker self-collision
Path B (cutover completion)")**: route all striker /
non_striker writes through a single canonical setter
(`set_striker(name, frame_count)` on
`ScoreManager`) that holds the invariant
"striker ≠ non_striker" at the source-of-truth level,
not at every downstream guard.

**Proposed fix paths (smallest first):**

**Path A — Heal-on-collision in `sb._inn`.**  When Fix 5
detects a would-be collision AND the existing slot
holds the same name as the proposed write target, **clear
the conflicting slot first**, then accept the new write.
Mechanism: in `update_batter`, when
`sb._inn["striker"] == sb._inn["non_striker"]`
(detected via cheap pre-write check) AND the proposed
batter is one of `active_batting`, treat the existing
collided state as poisoned and force-set both slots from
`active_batting` (one to the proposed name, the other
to the remaining active name).  ~10-15 lines.  Acts as a
self-healing patch without changing source-of-truth
ownership.  **Risk:** masks an upstream bug that should
be fixed at the writer level; healer becomes load-bearing
if real bug recurs.

**Path B — Identify and fix the post-rotation non_striker
re-install path.**  Trace the F704 sequence with
additional logging (one frame's worth, easy to add).
Either:
(i) the rotation calls `set_non_striker(non_striker_name)`
   with `non_striker_name == new_striker_name` (logic
   bug — should pass the OTHER active batter), or
(ii) `assign_active_batters` runs after rotation and
    reinstalls slots in the wrong order using stale
    striker information.

Once identified, the fix is a single-site adjustment.
~5-10 lines + targeted test.  **Risk:** lower bound on
scope is unknown until the trace runs.

**Path C — Path B cutover completion.**  Route all writes
through `ScoreManager.set_striker / set_non_striker` and
remove the `sb._inn` direct-write paths.  This is the
already-filed P1 architectural item.  Largest scope,
deepest fix.  **Risk:** large refactor; defer to a
focused session.

**Recommendation:** ship **Path A** as a self-healing
hotfix-grade patch alongside **Path B** as the proper
fix, both targeted at the sb._inn level.  Path A
prevents the user-visible damage immediately; Path B
removes the upstream defect.  Path C remains the
long-term architectural answer.

**Severity:** P0 (live UX) — primary header tile shows
incorrect/incomplete information for arbitrary multi-
minute windows.  Same severity class as the cold-start
team-misassignment.  Surfaced by the analyzer's
`--report-10 --per-wicket` mode (70 STRIKER-COLLISION
fires on wicket 4 window with 0 POST-WICKET-ROTATION
fires — the rotation hook's silence is correlated, not
coincidental).

**Connects to:** P1 striker-collision Path B cutover
(architectural), P1 SM-reset gap (different mechanism,
same family of "scoreboard-side state desync from SM"),
Fix 5 Path A (write-time guard, shipped), Fix 7 WS-
PROJECTION-FALLBACK (defence-in-depth, shipped).

---

## P0 (live UX): Team-name `LSG` ↔ `KKR` flip in BIG-header score line — dual-broadcaster manifestation in `batting_team` field

**Surfaced 2026-04-26 20:25 IST during LSG-vs-KKR live
monitoring.**  Two screenshots taken 7 seconds apart
(20:25:24, 20:25:31) show the same score `65/4` with
identical batter / bowler tables, but the LARGE header line
flips between `LSG 65/4 (10.0 ov)` and `KKR 65/4 (10.1 ov)`
on successive frames.  The `(10.0)` vs `(10.1)` over count
shows the LSG-version payload is half a step behind in
addition to having the wrong team prefix — a one-frame-
prior cached state being re-broadcast under stale
`batting_team`.

**Root cause (traced via DETAIL field inspection):**
- Every DETAIL line in the F701-F710 window reads
  `batting_team=Kolkata Knight Riders` (correct).
  Scoreboard-side state is stable.
- `ScoreManager.batting_team` is updated via
  `self.batting_team = frame.broadcast_team` (line ~702 of
  `score_manager.py`).  This means SM tracks the *most
  recently observed* broadcast team string.  Whenever the
  scout reads a noisy strip / pre-match graphic / squad
  panel that contains `LSG`, SM flips `batting_team` to
  `LSG`.  When the scout reads the live `KKR` strip, SM
  flips back.
- SM's `score_dict()` (lines 1060, 2014 of
  `score_manager.py`) emits `"batting_team":
  self.batting_team` in its broadcast payload.
- The WS broadcaster emits two payloads per ball event /
  frame: one from SM (with SM's `batting_team`, possibly
  `LSG`) and one from `build_full_payload()` (with
  scoreboard's `batting_team`, always `KKR`).  The UI
  re-renders alternately.

**Connects to (and extends):** P1 SM-reset gap entry —
the dual-broadcaster fluctuation that previously
manifested as `Inn 1 / Inn 2` and `target=159 / target=
None` flicker now extends to the `batting_team` scalar.
This is the **second visible manifestation** of the same
underlying SM-side scalar-field reset gap.  The P1 entry
already lists `batting_team` in the broadened-scope
field set; this filing is the *evidence* of damage.  The
SM `batting_team` field has neither (a) a consensus
mechanism to reject one-frame misreads, nor (b) a reset-
on-known-team-set mechanism to align with the
authoritative side.

**Why it's resilient on most matches:**  When the broadcast
strip is reliably `KKR …` for many consecutive frames,
SM stays at `KKR` and the two payloads agree.  The flip
becomes user-visible during noisy strip windows: pre-
match graphic carry-overs (this match's cold-start
issue), squad-panel overlays, ad/promo cuts (the F701
window's `venue=this frame is an advertisement` field
agrees with this hypothesis), and innings-break overlays
(the previously-filed inn1/inn2 flip).

**Proposed fix paths (smallest first):**

**Path A — Reject single-frame `batting_team` flips below
consensus threshold.**  Mirror the existing 3-frame
consensus pattern from `ConsistentReadTracker`: SM only
adopts a new `batting_team` after seeing it on N
consecutive frames (N=3 matches the existing
cold-start consensus).  Single-frame misreads are
ignored.  ~15-25 lines in `score_manager.py`.  Closes the
flip mechanism without architectural change.  **Risk:**
slows down legitimate batting_team transitions at innings
boundaries by N frames (~1-3 seconds) — acceptable
given user-visible damage of unguarded flips.

**Path B — Source `batting_team` from the same path as
score / overs / wickets.**  Don't track it on SM at all;
have SM resolve `batting_team` from the scoreboard's
team-assignment state on demand at `score_dict()` call
time.  ~10 lines.  **Risk:** introduces a coupling SM
was designed to avoid; defer to the architectural
SM-reset fix.

**Path C — Hold the broadcaster bundle as part of the
broader SM-reset fix already queued.**  Bundle this
finding into the P1 SM-reset gap entry's scope so the
reset hygiene work covers this scalar at the same time.
Largest scope, but cleanest because all the scalar-
field gaps get resolved together.

**Recommendation:** Path A as a near-term consensus
hotfix (closes the visible flip immediately, ~15-25
lines, no architectural change), then bundle the
remaining scalar-field hygiene under Path C for the
proper cleanup.

**Severity:** P0 (live UX) — primary header shows the
wrong team name for arbitrary single-frame windows that
the user will see flicker.  Same severity class as the
cold-start team-misassignment (which is the *static*
form of this bug; this entry is the *dynamic* flicker
form).

**Connects to:** P0 cold-start team-misassignment (same
field, different trigger condition — cold-start is
"first read wrong, takes long to recover"; flicker is
"already-correct field gets overwritten by a noisy single
frame and recovers next frame"), P1 SM-reset gap (same
SM-side scalar-state hygiene problem).

---

## P0 (live UX): `Recent Overs` (and `This Over`) flips between two render shapes — dual-broadcaster manifestation in `over_history` field

**Filed 2026-04-26 20:42 IST** during LSG-vs-KKR live
monitoring.  User-reported with paired screenshots
spanning ~30 s (12.2 → 12.3 of innings 1).

**User-visible symptom:**

The "Recent Overs" panel and (occasionally) "This Over"
panel alternate between two completely different render
shapes from one broadcast frame to the next:

| Frame at 12.2 (idle/scoreboard payload) | Frame at 12.3 (event/SM payload) |
|---|---|
| `Ov 12  Markram  .  ?  ?  1  .  .` | `Ov 12  1  .  .` |
| `Ov 11  Khan     1  6  2  .  W  W` | `Ov 11  1  6  2  .  W  W` |
| `Ov 10  Markram  1  1  1  1  .  1` | `Ov 10  1  1  1  1  .  1` |
| `Ov 9   Linde    1  1  6  6  1  1` | `Ov 9   1  1  6  6  1  1` |

Bowler name appears/disappears each tick; Ov-12 ball-
list contents differ in length (6 entries with `?`
placeholders vs. 3 resolved-only entries); the entire
visual structure of the panel mutates per-frame.

**Root cause: two writers, two shapes, one field.**

The `state.over_history` map has two independent writers
that publish **different value shapes** for each over:

  * **SM-shape (`list[str]`, no bowler):** written in
    `score_manager.py:1655` (inline rollover) and
    `score_manager.py:1843` (`_complete_over`):
    ```python
    self.over_history[int(prev.get("overs", 0) or 0)] = (
        list(self.this_over))   # → ["1", ".", "W", ...]
    ```
    Emitted via `_build_payload()` at
    `score_manager.py:2051` with `source="score_manager"`.
  * **Scoreboard-shape (`dict`, with bowler + tokens):**
    written in `this_over.py:358` (held-over late
    append) and `this_over.py:1052` (canonical archive):
    ```python
    self.over_history[held_int] = {
        "balls": [...],          # may contain "?" placeholders
        "bowler": "Markram",
        "runs": 5,
        "wickets": 0,
    }
    ```
    Emitted via `scoreboard.to_dict()` at
    `scoreboard.py:3269` and via `build_full_payload()`.

The dispatcher at `test_pipeline.py:8110` selects which
writer's payload broadcasts each frame:

```python
if not score_mgr.shadow and _sm_result is not None:
    ws_payload = _sm_result          # SM-shape
else:
    ws_payload = build_full_payload(...)  # scoreboard-shape
```

Since `ScoreManager(shadow=False)` is in production
(`test_pipeline.py:3401`), event-bearing frames take
the SM branch and idle/poll frames fall through to the
scoreboard branch — producing the per-frame shape
flip the user sees.

**UI accepts both shapes (mistake on the frontend
side):** `scorecard-ui/app/page.tsx:748-755` falls
through three array sources:

```tsx
const balls: string[] = Array.isArray(entry)
  ? entry                              // SM-shape
  : Array.isArray(entry?.balls)
    ? entry.balls                       // scoreboard-shape canonical
    : Array.isArray(entry?.broadcast_balls)
      ? entry.broadcast_balls           // legacy/alt scoreboard-shape
      : [];
```

The frontend's permissive accept-both-shapes design is
masking the upstream incoherence: a strict frontend
(only one shape, fail loudly on mismatch) would have
surfaced this bug on day-one of the SM-broadcaster
rollout.

**This is the same dual-broadcaster pattern as:**

  * Team-name `LSG ↔ KKR` flip (filed 20:35) — SM-
    side `batting_team` scalar updated unconditionally;
    UI flips between SM and scoreboard payloads.
  * Score `inn1 / inn2` flicker (P1 SM-reset gap, pre-
    existing) — SM's `bat1_runs/bat2_runs` carry stale
    inn-1 values into inn-2 payloads.

All three are surface manifestations of the same
architectural problem: SM and Scoreboard maintain
*partial* and *non-isomorphic* views of the same
state, and the broadcast layer alternates between the
two without canonicalising shape or value.

**Also affects `this_over` field (user noted):**

User reported the same flicker occasionally extending
to the "This Over" pill.  Same root cause: SM's
`this_over` (line 1666: `event.get("this_over_token",
"?")`) can include `"?"` placeholders for unclassified
tokens that the `this_over.py`-side writer never
produces.  When SM payload broadcasts, the pill gets
the `?` tokens; when scoreboard broadcasts, the pill
gets the resolved tokens.  Same alternation.

**Fix paths (three options, scoped):**

  * **Path A (smallest, ~15-25 lines): SM-shape
    canonicalise.**  Change `score_manager.py:1655`
    and `:1843` to write the *dict* shape:
    ```python
    self.over_history[over_int] = {
        "balls": list(self.this_over),
        "bowler": self.bowler_name,
        "runs": self.completed_over_runs,
        "wickets": sum(1 for t in self.this_over
                       if t == "W"),
    }
    ```
    SM and scoreboard then publish the same shape.
    UI's permissive code handles both today, but with
    canonicalised SM-shape the frontend can be tightened
    to a single shape in a follow-up.  Lowest-risk
    bounded fix; doesn't touch the broadcaster
    selection logic.  Trade-off: SM still doesn't have
    bowler-tokens for unresolved balls (would emit `"?"`
    in `balls` list, which the scoreboard-shape doesn't
    do — scoreboard's archived balls are always
    resolved).  Acceptable as a first cut; tightens
    in Path B.
  * **Path B (~30-50 lines): SM-omits-over_history.**
    Don't include `over_history` in SM's
    `_build_payload()` at all.  The dispatcher at
    `test_pipeline.py:8110` always overlays
    scoreboard's authoritative `over_history` onto the
    SM payload before broadcast (small post-process at
    8120-8150).  Shape becomes single-source-truth,
    and the SM branch becomes leaner (it doesn't need
    to maintain `over_history` at all → also addresses
    Path A's "SM doesn't have bowler tokens" gap by
    eliminating SM's claim on the field).
  * **Path C (architectural): SM-cutover completion.**
    Already filed as the umbrella "complete the SM
    cutover" item.  Both SM and Scoreboard converge to
    a single canonical state object that's written
    once per frame and broadcast once per frame.
    Eliminates the entire dual-broadcaster pattern
    (this entry + team-flip P0 + SM-reset P1 + striker-
    collision Path C all close together).  Larger scope.

**Recommendation:** Path A as the immediate-relief slice
(can ship in a single bounded session with regression
tests for both writer paths producing identical
shape).  Path B follow-up after Path A validates.
Path C remains the architectural endgame.

**Tests to add (Path A scope):**

```python
test_sm_complete_over_emits_dict_shape_with_bowler
test_sm_inline_rollover_emits_dict_shape_with_bowler
test_sm_and_scoreboard_over_history_shapes_match
test_ws_payload_over_history_shape_invariant_across_branches
```

The last test pins the regression: synthesise an event
frame and an idle frame, take both branches at
`test_pipeline.py:8110`, assert that
`payload["over_history"]` keys map to identical shapes
in both branches.

**Test fixture (production):** the F-frames around
20:39:28 → 20:39:58 in
`pipeline-2026-04-26-…-fix12-v6-validation.log`
contain the alternating broadcasts; can be replayed as
a deterministic regression scenario.

**Connects to:**

  * P0 team-name flip (same dual-broadcaster pattern,
    different field — `batting_team` scalar)
  * P0 striker-collision-stuck (Fix-7 fallback masks
    SM's collided `non_striker`; Path C of THAT entry
    converges with Path C of THIS entry)
  * P1 SM-reset gap (same SM-side state-hygiene issue —
    Path C of any of these entries collapses all three)

**No production damage observed on state correctness**
— both writers produce *valid* over data; only the
shape disagrees, and the UI's permissive renderer keeps
the panel from breaking entirely.  But the user-visible
visual flicker is severe (the panel mutates structure
each tick) and undermines trust in the displayed score
state.  Worth fixing before next match-day if Path A is
elected; can also defer to the SM-cutover bundle if
Path C is queued.

---

## Part B follow-ups (Scout prompt V5, 2026-04-24)

### P1: Phase regression from V5 multi-example prompt

V5's closeup example uses `"frame_phase": "between_play"` as its
example value.  On bowlers_end true-positive frames in the shadow run,
frame_phase emission dropped from 2/5 (V0) to 0/5 (V5) — the closeup
example's phase is bleeding into delivery-context frames the same way
the old single-example's `"release"` used to over-apply.

**Acceptable short-term** because:
1. DWR primarily consumes `camera_view`, not `frame_phase`.
2. Phase precision was already 40% at V0 baseline — not high-quality.
3. Part A's RC-7 phase gate has fallback handling for missing phases.

**Potential fixes** (either alone or combined):
- Add a fourth delivery-context example with `"frame_phase":
  "release"` to balance the phase distribution the same way V5
  balanced camera_view.
- Remove `frame_phase` from the STEP 1 examples entirely and let it
  derive from context + rulebook (risky — may cause a different
  collapse).
- Bundle with the "stronger model / post-hoc verification /
  temperature ensembling" escalation tracks if any of those land.

**Size:** 30–45 min prompt iteration + mini shadow run (~3-4 variants
× 3 reps on the existing 41-frame corpus, ~$0.05).

**Evidence:** `docs/scout_shadow_run_v1_analysis.md` §"Frame-phase
regression".

**Live confirmation (2026-04-25 DC vs PBKS, first ~2 min of capture):**
Of 7 `bowlers_end` frames emitted by V5, only 1 had a delivery-
context phase (`runup`); 6 emitted `between_play` — same value as the
V5 closeup STEP-1 example.  9 of 9 `closeup` frames also emitted
`between_play`.  Bias is consistent with the shadow-run prediction
and is now reproducible against live broadcast frames.

### P1: Scout camera_view precision ceiling (31.2% shadow / 34.8% prod)

**V6c corpus_v1 regression filter result (2026-04-25):** V6c clears
all four corpus_v1 regression criteria.  Strict bowlers_end precision
31.2% (V5) → 33.3% (V6c, +2.1 pp).  Recall on the 5 human-labeled BE
frames stays 100%.  Closeup recall unchanged at 83.3%.  Closeup-share
distribution shift +4.9 pp (39.0% → 43.9%) — modest, within
tolerance.  Net frame accuracy unchanged at 48.8% (V6c reshapes
errors rather than reducing them on this corpus).  Per-frame
migrations: 2 side_on frames moved from BE-FP to closeup-FP (matches
V6c's targeted Pattern 1 fix), 1 `other` frame moved from closeup-FP
to BE-FP (regression on f941 to watch on prod), 1 `other` frame
moved graphic-FP to closeup-FP (neutral).  V6c proceeds to
**combined-corpus shadow run tomorrow** for the ship/no-ship
decision.  See `docs/scout_v6c_shadow_run_corpus_v1_2026-04-25.md`
for the full per-frame breakdown, watch-list, and decision
framework.

V6c is **not** shipped to `vision.py` from the corpus_v1 run.
Production prompt remains V5 until the combined-corpus result clears
ship criteria.

**V6c shadow run on 41-frame corpus (offline harness, shipped 2026-04-30):**
Path-parameterization **S4** — `shadow_eval/run_shadow.py` now supports
`--corpus`, `--output` / `-o`, `--frames-dir`, `--resume` (default on) /
`--no-resume`; `shadow_eval/analyze.py` supports `--shadow`,
`--baseline-shadow` (merged overlay semantics), `--out-md`, `--variants`.
`shadow_eval/run_shadow.py` persists additive **`groq_*`** telemetry per row
(**`groq_response_id`**, **`groq_model`**, **`groq_finish_reason`**,
 **`groq_created`**, **`groq_attempt_count`**, **`groq_latency_ms`**) alongside
canonical camera/phase captures.
Fresh corpus_v1 **`V6c`** artifact: `files/docs/shadow_run_v6c_20260430_140220.json`
(123 Groq completions, **`error`** field empty on all rows; ~107s wall-clock).
Interpretation summary: **`files/docs/investigations/scout_v6c_first_shadow_run_results.md`**.
Automated Markdown tables: **`files/docs/scout_v6c_first_shadow_analysis_autogen.md`**.
**Recommendation (executive):** Mixed caution — **`bowlers_end` strict precision** still tracks the
historical ~**+2 pp** uplift vs **`V6c`** corpus-doc narrative, but **this rerun shows net labeling drift
(20→19/41)** and **higher replicate flip-rate (7.3%→14.6%)** with **`f941`→`bowlers_end` escalation**;
reconcile repeatability/provider variance before **`SCOUT_PROMPT`** swap / combined‑corpus spend.

**V6c second + third corpus_v1 shadows (2026-04-30):** **`files/docs/shadow_run_v6c_20260430_141433_run2.json`**, **`files/docs/shadow_run_v6c_20260430_141629_run3.json`** — each **123 / 123** successes, **`--no-resume`** from **`files/`** with **`docs/scout_corpus_v1.json`**. **`replicate_analysis`:** runs **2** and **3** share migration hash **`7dd8483e30258c16`**; run **1** **`b0b1d9c701d48100`** (**cross-run disagreement 2 / 41**). **Strict BE 33.3%** and **net 19 / 41** on **all three** runs ⇒ **stable** trade-off vs V5 **20 / 41**; **f941→`bowlers_end` stable** across runs **1–3**; **f748** **`closeup`** on runs **2–3**, **`bowlers_end`** run **1** (paired state tracks **04-25** remediation only on newer pair). Decision memo: **`files/docs/investigations/scout_v6c_replicate_runs_decision.md`** • tables: **`files/docs/scout_v6c_replicate_analysis_autogen.md`**.

**V6c fourth + fifth paired shadows (`groq_*` metadata, 2026-04-30):**
**`files/docs/shadow_run_v6c_20260430_143705_run4.json`** (119 s wall) &
**`files/docs/shadow_run_v6c_20260430_143910_run5.json`** (140 s wall) —
**123 / 123** successes each. Five-run pooled autogen (**`files/docs/scout_v6c_determinism_analysis_autogen.md`**): **four** distinct migration hashes across **five** runs (**`7dd8483…` only on historic runs **2–3**; next paired batch **≠** **`7dd…`**). Telemetry: **`groq_response_id`** unique per row, **`finish_reason=stop`** on **run4/run5**, many **`groq_attempt_count`** **>** **1** with empty **`error`** (429 retry path). Decision memo: **`files/docs/investigations/scout_v6c_determinism_decision.md`**.

**V6d corpus_v1 ensemble (K=5, 2026-04-30):** **`PROMPT_V6D`** in **`files/shadow_eval/variants.py`**; five fresh shadows **`docs/shadow_run_v6d_*_run*.json`**, each **123/**0 errors, full **`groq_*`** rows. **Design §8 PRIMARY all pass** — median net **27/41** (**+7** vs single-file V5 **20**; **+8** vs **`V6c`** ensemble median **19**), **`f941` → `other`** on **all five** runs, **`f205` → `closeup`×5**, median strict **`bowlers_end` precision 35.7%**, human-BE TP recall **100%**. **Two** distinct migration hashes / five runs (**narrower** than **`V6c`**’s four). **Regression:** **`f748`** stuck **`bowlers_end`×5** ( **`V6c`** had **`closeup`** plurality). Write-up: **`files/docs/investigations/scout_v6d_first_shadow_run_results.md`** • tool output **`files/docs/scout_v6d_ensemble_analysis_autogen.md`**.

**Scout-side queue (post‑2026‑04‑30 refresh — operational cadence notes):**
- **Harness reliability fix (`shadow_eval/run_shadow.py`, validate-first Step 1, 2026-04-30):**
  **`TIMEOUT_S`** default **7s → 15s**, **`--timeout-s`**, **retry on per-attempt `TimeoutError`**
  (same **`MAX_ATTEMPTS`** as **429**); **`groq_attempt_count`** counts either retry kind —
  **`scout_v6d_error_rate_investigation.md`** (**~6.27% pooled** combined **V6d** errors).
  **Step 2 (2026‑04‑30):** **`V6d`** **K=5** **post-harness** combined corpus → **`scout_v6d_postharness_rerun_results.md`**
  — **~0.53% pooled** (**4**/750 errors; **Outcome A**, **\<1%** vs **~0.40% V6c**); **Step 3:** proceed cautiously toward **V6e** (**`scout_v6d_implementation_audit.md`**); optional retry **four** triples / tune **`--concurrency`** vs **429** exhaust.
- **Production `SCOUT_PROMPT` / combined corpus:** **`V6d` ship-candidate on corpus_v1 §8** — do **not** skip **sampler M‑2** or distribution review; explicit sign-off on **`f748`** **`bowlers_end`** trade vs **`f941`** / net-accuracy win (**`scout_v6d_first_shadow_run_results.md`** §7–8).
- **Sampler M‑2 bucket coverage enforcement:** **SHIPPED** — combined
  corpus path **`files/scripts/select_combined_scout_corpus.py`**
  (**`m2_combined_corpus_sampler.md`**). **2026-04-30 combined run**
  (**`combined_corpus_shadow_v6c_v6d_2026-04-30.md`**): **3** match
  inventories (**rcb_gt**, **mi_srh** slice, **pbks_rr**), **`docs/scout_corpus_combined_v1.json`
  (50 frames)** + **`materialize_combined_corpus_frames.py`**, V6c/V6d **K=5**
  shadows (**historic** **`docs/shadow_run_v6{c,d}_combined_20260430_*`**, **`postharness` V6d** **`docs/shadow_run_v6d_combined_postharness_*_run*.json`**), discriminating
  list **`docs/discriminating_frames_v6c_vs_v6d_combined.md`** (**3** frames to
  label first). **Validated 2026‑04‑30:** **post‑harness** **V6d** **K=5** pooled **`error` ~0.53%**
  (**`scout_v6d_postharness_rerun_results.md`**) vs **historic** spike **~6.3%**/run peak **~11%**
  (**`scout_v6d_error_rate_investigation.md`**) dominated by timeouts — **timeouts cleared** after harness;
  residue **429** exhaust + **`500`** (retry / lower concurrency discretionary). Human labeling + **`f748`** sign-off still open.
- **`side_on` canary (**`### P1: Scout never emits side_on`**, backlog ~L6384+):** **UNCHANGED DEFER** per **`scout_v6c_shadow_run_scoping.md`**.
**Production validation (2026-04-25 DC vs PBKS, 23 stratified
bowlers_end frames):** strict precision **34.8% (8/23)**, vs V0
baseline ~15% — meaningful 1.85x improvement but lands in the
**marginal** band (25-40%) of the pre-committed thresholds. V6 work
justified, not urgent. Decision: keep V5 in production, do not roll
back, queue V6 as P1. See `docs/scout_v5_prod_eval_2026-04-25.md`
for full per-phase breakdown, failure-mode analysis, and TP-only
phase regression confirmation (75% delivery-context, vs the 24%
shadow-run figure that conflated FP-driven `between_play`).

**Two failure modes for V6** (also tracked in P1 entries below):
1. **Closeup with bowler's-end direction (40% of FPs)** — prompt
   fix via STEP-1 negative-example pair contrasting "full pitch
   receding + bowler in frame" vs "camera direction only".
2. **Hero / wide aerial (33% of FPs)** — architectural fix via a
   downstream "is-bowler-in-frame" sub-check on bowlers_end-tagged
   frames.

**Original shadow-run framing (preserved for comparison):**

V5 doubles bowlers_end strict precision from 15.2% to 31.2% but cannot
reach the ≥90% target via prompt engineering alone on
`meta-llama/llama-4-scout-17b-16e-instruct`.  The 11 remaining false
positives in the corpus are frames where pitch-receding geometry is
genuinely visible even though consumer-alignment requires a different
label (usually `side_on` on elevated square shots, or `closeup` on
over-the-shoulder batter frames with pitch in background).

**Escalation paths** (in cost order, cheapest first):

1. **Temperature > 0 with majority-vote ensembling.**  Run Scout 3x
   per frame at t=0.3 and take the mode.  Marginal per-call latency,
   no architectural change.  Worth testing before anything else.
2. **Post-hoc verification layer.**  Second cheap LLM call receives
   only bowlers_end-tagged frames and confirms pitch-axis geometry.
   Adds one call of latency on ~85% of frames (today's emission
   rate) or the post-V5 rate once measured.
3. **Stronger vision model.**  `llama-4-maverick` if Groq exposes it,
   `gpt-5-vision` via OpenAI, or similar.  Highest expected quality
   lift but operational cost: different vendor contract, different
   API shape, potentially higher per-call cost.

**Do not start** until production V5 behavior is observed for long
enough to know whether downstream quality (commentary correctness,
DWR window hit rate) actually requires the lift.  If V5 is sufficient
downstream, the escalations are unnecessary.

**Evidence:** `docs/scout_shadow_run_v1_analysis.md` §"Remaining FP
breakdown".

---

## Infrastructure

### P2: Stratified sampler must flag empty buckets with non-empty pools

**Status: SHIPPED (2026-04-30).** **`select_corpus_candidates.py`**
emits `bucket_coverage` in **`corpus_candidates.json`** and prints
`[BUCKET-COVERAGE]` warnings for subset pools. **Combined-corpus
phase×innings path:** **`files/scripts/select_combined_scout_corpus.py`**
corpus-shaped JSON with **`metadata.bucket_coverage`**, **`WARN`** vs
**`UNDOCUMENTED_ZERO`**, optional **`--strict`**, and **`--document-empty`**
(see **`files/docs/investigations/m2_combined_corpus_sampler.md`**).
**Operational follow-up:** validate on real multi-match inventories before
**`SCOUT_PROMPT`** / distribution sign-off.

**Historical urgency note (2026-04-26):** subset-bucket enforcement landed
before V6c shadow queue; combined-corpus tool extends M-2 to innings
stratification.

If a future sampler runs without bucket-coverage enforcement, the run
risks a repeat of the death_inn1 silent-zero pattern, contaminating
shadow precision numbers.

The V5 production-precision sampler used in the 2026-04-25 DC vs PBKS
evaluation silently under-sampled `death_inn1`: pool size 5, frames
sampled = 0. Death-overs precision is therefore unknown from that
run. The discrepancy was caught manually, not by the tool.

**M-2 codification:** `docs/scout_labeling_rubric_v1.md` — implemented in
`select_corpus_candidates.py` (subset buckets) and
`scripts/select_combined_scout_corpus.py` (phase×innings buckets).

**Done (2026-04-30).** Earlier scheduling discussion (fix #7 on the
2026-04-25 inter-match bundle): eval-harness work does not gate on seam
timing; superseded by land of both subset-bucket enforcement and combined
sampler.

### SHIPPED 2026-04-25: Pass-2 enrichment async (P1)

**Original symptom:** `enrich_squad_styles` ran Pass-1 *and* Pass-2
inline in `run_test()`/`main_loop()` before frame capture started.
Pass-2 took 4:30 (or timed out at 4:30) on 2026-04-24 / 2026-04-25
sessions, blocking the first ~4 overs of every fresh-team-pairing
match. Evidence: `logs/pipeline-2026-04-25-153247-dc-pbks-v5.log`
(15:32:54 Pass-1 done → 15:37:25 Pass-2 timeout → 15:37:28 first
SCOUT frame).

**Fix shipped:**
1. `enrich_squad_styles(raw_data, pass2_background=True)` — runs
   Pass-1 inline (~3s), merges into `raw_data`, returns immediately
   without invoking Pass-2.
2. New `enrich_squad_styles_pass2_async(raw_data, pass1_styles,
   on_complete=...)` — runs Pass-2 in the background, merges results
   into `raw_data`, calls `on_complete(pass2_styles)` for downstream
   sinks. On Pass-2 failure: caches Pass-1 as fallback, callback not
   fired (no rollback needed since `raw_data` already has Pass-1).
3. New `Scoreboard.update_player_styles(styles)` — retro-patches
   `_player_styles`, `batting_card`, and `bowling_card` without
   wiping live runtime stats. Used as the on_complete callback in
   both call sites.
4. Both `test_pipeline.py:run_test()` and `eyes/main.py:main_loop()`
   updated: Pass-1 stays foreground (cheap, ~3s), Pass-2 fires
   non-blocking after `Scoreboard()` exists. Cache-hit fast path
   unchanged.

**Tests added** (`test_recent_fixes.py`):
- `test_update_player_styles_patches_existing_cards` — Pass-2
  corrections applied to both card types
- `test_update_player_styles_preserves_runtime_stats` — runs/balls/
  wickets unchanged when styles are patched mid-innings
- `test_update_player_styles_handles_missing_or_empty` — empty/None/
  unknown-name cases tolerated
- `test_enrich_squad_styles_pass2_background_skips_pass2` — verifies
  Pass-2 is NOT invoked when `pass2_background=True`
- `test_enrich_squad_styles_pass2_async_invokes_callback` —
  end-to-end: Pass-2 completes, callback fires, raw_data + cache
  updated
- `test_enrich_squad_styles_pass2_async_failure_caches_pass1` —
  Pass-2 raise → returns None, callback NOT fired, Pass-1 cached as
  fallback, raw_data preserved

All 6 tests pass; full test count 102 PASS / 2 FAIL (2 unrelated
pre-existing failures).

**Verify on next launch:** first SCOUT frame should arrive within
~5-10s of pipeline start (capture-source detection latency only).
Look for `[ENRICH] Pass-1 (infer) complete in <3000ms` followed by
`[ENRICH] Pass-2 (verify) complete in ...` *after* frames begin.
Then `[STYLES-PATCH] Updated N card slots from background Pass-2
enrichment` confirms retro-patch applied.

### P1: Pass-2 enrichment retry/timeout policy (STAGED 2026-04-26 → pending-validation post-restart)

**Status: STAGED 2026-04-26 inter-match commit bundle as Fix 6 — `_make_client()` config: `timeout=240.0, max_retries=0`. Awaits seam restart; transitions to SHIPPED at land time per `staged_fixes_2026-04-25/README.md` step 6. Then transitions to SHIPPED-pending-validation pending first-restart positive-firing telemetry (`[ENRICH] Pass-2 (verify) complete` → `[STYLES-PATCH] Updated N card slots`); SHIPPED-confirmed once that telemetry lands.**

Lifecycle to date: was P2 → promoted P1 on 2026-04-25 → investigation
closed 2026-04-26 14:30 IST → fix staged into bundle 2026-04-26 14:55
IST.

**Implementation (2026-04-26 14:55):**

- `files/eyes/player_enrichment.py:218` — `AsyncGroq(api_key=...,
  timeout=240.0, max_retries=0)` (was `timeout=90.0`, `max_retries`
  inherited as SDK default 2).
- `files/test_recent_fixes.py` — `test_pass2_client_timeout_config
  _explicit` added (config-shape assertion, 3 sub-checks; uses public
  `client.timeout` / `client.max_retries` attrs).
- Bundled as fix #6 in `staged_fixes_2026-04-25/`.  Per-fix README:
  `staged_fixes_2026-04-25/fix6_pass2_client_config/README.md`.
- Test suite: 207 PASS / 2 FAIL (both pre-existing; `test_this_over
  _late_boundary_ball_appends_to_held` and source-text check for the
  old `>= 18.0` over cap).

**Promotion evidence (2026-04-25):**  3/3 timeouts across three
separate restarts, all clustered tightly at the same wall:

| session                                     | Pass-1 → fail |
|---------------------------------------------|---------------|
| `pipeline-2026-04-25-153247-dc-pbks-v5`     | 271 s         |
| `pipeline-2026-04-25-183644-dc-pbks-v5-restart` | 271 s     |
| `pipeline-2026-04-25-195304-rr-srh-v5-archival` | 272 s     |

Variance ±1 s across three independent sessions confirmed a
deterministic timeout in the Pass-2 chain.

---

**Investigation result (2026-04-26): root cause identified.**

The 271 s ±1 s ceiling is **the composition of two configuration
choices made by us — not a Groq gateway behaviour**:

| component | source | value |
|-----------|--------|-------|
| per-attempt timeout | `files/eyes/player_enrichment.py:218` (explicit `timeout=90.0` on `AsyncGroq(...)`) | 90 s |
| total attempts | Groq SDK 1.1.2 `AsyncGroq.__init__` default `max_retries=2` (never overridden) | 1 + 2 retries = 3 |
| per-retry backoff | Groq SDK exponential w/ jitter, ~0.5 s starting | ~0.5–1 s × 2 = ~1 s |

`3 × 90 s + ~1 s ≈ 271 s` — matches observation deterministically.

Hypothesis from the original promotion entry — that 271 s "isn't the
Groq SDK default" — was correct in spirit but slightly off in
attribution: the **per-attempt** value is ours (90 s), but the
**multiplier** that turns 90 s into 271 s is the SDK retry default
(2 retries, never explicitly set in `_make_client()`).  No
`asyncio.wait_for` wrapper, no gateway proxy timeout, no
`tenacity` retry — just `timeout=90.0` interacting with
`max_retries=2`.

Verification commands (rerun any time):

```bash
.venv/bin/python -c "import inspect, groq; \
  print(inspect.signature(groq.AsyncGroq.__init__))"
# → max_retries=2 default

rg -n "timeout|max_retries|asyncio.wait_for" files/eyes/player_enrichment.py
# → only hit is L218 timeout=90.0; no other timeout source in the chain
```

The Pass-2 call is `_call_groq_with_search()` → single
`client.chat.completions.create(model=VERIFY_MODEL, ...)` against
`groq/compound` (web-search-grounded).  No app-level retry wraps it.
The grounded model with web-search fan-out genuinely takes longer
than the source comment ("10–30 s") on current Groq prod load —
every call exceeds 90 s, so all three SDK attempts hit the per-call
timeout, exhausting the budget.

---

**Concrete proposal — single client-config change, two-line diff:**

```python
# files/eyes/player_enrichment.py:218
return AsyncGroq(
    api_key=GROQ_API_KEY,
    timeout=240.0,      # was 90.0 — single-attempt headroom for
                        # groq/compound's actual prod latency band
    max_retries=0,      # was SDK default 2 — disable SDK retry;
                        # single shot, total budget = 240 s.  Pipeline
                        # already runs Pass-2 background-async with
                        # graceful Pass-1 fallback on failure, so a
                        # second SDK attempt only triples wall-clock
                        # cost without changing failure semantics.
)
```

**Why this shape:**

-   240 s single-attempt > 271 s 3-attempt budget: gives **one** call
    enough headroom to actually return, instead of three calls each
    timing out at 90 s.  Net wall-clock: shorter (240 s ≤ 271 s) and
    it can actually succeed.
-   `max_retries=0` removes the silent SDK retry that currently burns
    the budget.  We trade SDK auto-retry-on-5xx for a deterministic
    single-shot — and that trade is fine because (a) Pass-2 is
    background-async (no user-visible cost on failure), (b) Pass-1
    fallback is already cached, and (c) the next match's pipeline
    run will redo Pass-2 anyway.
-   No new dependency (no `tenacity`).  No new code paths.  Just two
    keyword args.

**Rejected alternatives (with reasoning):**

| path | proposal | why rejected |
|------|----------|--------------|
| (a-bump) | raise `timeout` only, keep `max_retries=2` | wastes 480 s on retries when the failure mode is timeout, not 5xx — retry of a known-slow path is just three serial timeouts |
| (b-tenacity) | add explicit tenacity retry (60 → 90 → 120, budget 270 s) | duplicates the SDK's already-present retry; net effect identical to today's broken state; adds dependency |
| (c-non-grounded-fallback) | on timeout, retry with plain Llama (no web search) as `verified_via=heuristic` | useful but **separate** P2 item; today's fix should restore the grounded path first, then this becomes a defence-in-depth layer.  Filed as follow-up below. |

---

**Test plan (must ship with the fix):**

1.  `test_pass2_client_timeout_config_explicit` — assert
    `_make_client()` returns a client with `timeout==240.0` and
    `max_retries==0`.  Pure config-shape test; catches accidental
    revert.
2.  `test_pass2_async_callback_fires_on_happy_path` (already exists
    as `test_enrich_squad_styles_pass2_async_invokes_callback` —
    extend) — mock `_call_groq_with_search` to return a verified
    JSON blob in <1 s; assert callback fires and `[STYLES-PATCH]`
    log line emitted.
3.  `test_pass2_async_callback_silent_on_timeout` (already exists
    as `test_enrich_squad_styles_pass2_async_failure_caches_pass1` —
    extend) — mock `_call_groq_with_search` to raise
    `groq.APITimeoutError`; assert callback NOT fired, Pass-1 cached
    as fallback, `[ENRICH] Pass-2 (verify) LLM call failed` log line
    emitted.
4.  Production verification on first restart after deploy: search
    logs for `[ENRICH] Pass-2 (verify) complete in <N>ms` — N should
    land in the 30 000–120 000 ms band (i.e. 30–120 s) on the happy
    path.  If N is consistently >200 000 ms across three sessions,
    bump `timeout` to 360 s and re-evaluate.

**Telemetry to capture on first three deploys:**

-   median + p95 of `Pass-2 (verify) complete in Nms` across all
    successful runs
-   timeout rate (count of `LLM call failed: APITimeoutError` ÷
    total Pass-2 invocations)
-   if timeout rate >20 % after a full match-day, escalate to path
    (c) (non-grounded fallback)

**Fix scope:** 2-line source change + 3 tests = ~30 min implement,
~15 min review.  Down from the original "1–3 hour" estimate now
that investigation is closed.

**Don't ship this without:** the three tests above, the
configuration-shape assertion in particular (test 1) — it's the
cheapest insurance against silent regressions when the SDK is
upgraded and `max_retries` defaults change.

**Follow-up filed (P2):** non-grounded LLM fallback on Pass-2
timeout — see "P2: Pass-2 non-grounded fallback layer" below (to
be appended when this fix lands).

### SHIPPED 2026-04-25: Debug frame archival instead of deletion on pipeline startup (P2)

**Original symptom:** `test_pipeline.py:3715-3719` wiped `debug_frames/`
on every pipeline launch.  Forced a corpus rebuild on a single RC9
session for Part B and — more acutely — wiped the 23 freshly labeled
prod-eval frames from the V5 evaluation when we restarted the pipeline
at 18:36:49 (DC vs PBKS) to deploy the P0-A / P0-B / Pass-2 fixes.
The prod-eval JSON's `frame_archive` field literally pointed at
`files/debug_frames/`, so the loss was total: all 23 paths went 404
between V5 evaluation and V6c shadow run.  Surfaced when the V6c run
tried to load the combined corpus and every prod-eval path missed.

**Fix shipped:**
1. New `_archive_old_debug_frames(src, archive_root, *, keep_last_n,
   session_id)` helper at module scope: moves every `*.jpg` from
   `debug_frames/` into `debug_frames_archive/<YYYY-MM-DD_HHMMSS>/`,
   no-ops cleanly if the source dir is missing or empty (no empty
   session subdirs left behind), tolerates per-file move failures by
   logging and falling through to delete.
2. New `_enforce_archive_retention(archive_root, *, keep_last_n)`:
   removes the oldest session subdirs once the cap is exceeded.
   Lex sort matches chronological sort given the session-id format,
   so the oldest are always at the front of the list.  Defaults
   `keep_last_n=10`.
3. The startup cleanup at `run_test()` is now a single call to
   `_archive_old_debug_frames()`; `[CLEANUP] Cleared old debug frames`
   is replaced with `[CLEANUP] Archived N frames to <dest>`.

**Tests added** (`test_recent_fixes.py`):
- `test_archival_noop_when_src_dir_missing` — returns 0, archive root
  not created.
- `test_archival_noop_when_src_empty` — returns 0, no empty session
  subdir created.
- `test_archival_moves_existing_frames` — frames moved to dated
  subdir, source dir empty after.
- `test_archival_preserves_eval_path_resolution` — verifies an
  archived `f976_scoreboard.jpg` is readable from
  `archive/<sid>/f976_scoreboard.jpg`, mirroring the prod-eval JSON
  resolution path.
- `test_archival_retention_drops_oldest_sessions` — 6 sessions with
  `keep_last_n=3` retains the 3 newest.
- `test_archival_retention_noop_when_under_cap` — 2 sessions with
  `keep_last_n=10` retains both.

All 6 tests pass.  Test count: 118 PASS / 2 FAIL (2 unrelated
pre-existing failures).

**Verify on next launch:** the `[CLEANUP] Cleared old debug frames`
log line is replaced by `[CLEANUP] Archived N frames to
debug_frames_archive/<timestamp>` (or no log if the live capture dir
was empty).  After multiple restarts, `debug_frames_archive/` should
have at most 10 dated subdirs.

**One operational note:** The first restart after this ships still
loses any frames in `debug_frames/` because the running process
predates the fix.  Match-2 onwards is durable — see the
`scout_v6c_shadow_run_corpus_v1_2026-04-25.md` watch-list for the
combined-corpus evaluation that this enables.

### P2: CLOSEUP frames not persisted to `debug_frames/`

**Status: SHIPPED-pending-launch-validation (2026-04-28).**
The CLOSEUP short-circuit path now writes
`debug_frames/f{frame_count}_closeup.jpg` before returning, so closeup
misclassifications are visually auditable after a run.

`test_pipeline.py` has an explicit `imwrite` for `SCOREBOARD` frames
but not for `CLOSEUP` frames.  This means closeup misclassifications
are not visually auditable after the fact.  Part B worked around this
by using SCOREBOARD frames as a substrate (they're often the same
camera_view in practice), but a clean fix would add CLOSEUP to the
persistence list.

**Size:** 5-10 min.

---

## Pipeline behavior

### P0: State-recovery deadlock — three guards compound to prevent recovery from corrupted SM state

**Severity:** once SM hits an internally inconsistent state (e.g. via the
P0 active-batter resurrection bug below), the pipeline cannot recover
even when scout/extractor/scorer all subsequently emit correct data.

**Repro (2026-04-25 DC vs PBKS):**
After the F339 active-batter resurrection (see P0 below), the next
44 minutes of the run blocked every recovery attempt with one of
three guards:

1. **`FRAME_POISONED:<score>`** — Scorer LLM rejects the frame when
   the new broadcast score is too far from SM's score.  At F1215:
   broadcast says DC 120-1 (11.1), SM has DC ~76; scorer marks
   `Changes: ['FRAME_POISONED:120']` and the SM never updates.

2. **`[GUARD] Nitish Rana diff 11→43 — comparison strip for batting team`**
   — runs-delta guard treats the broadcast strip as a "comparison /
   graphic" because Rana's runs jumped from SM's stale 11 to the
   broadcast's 43.  The strip is correctly read but its update is
   discarded.

3. **`[WS-SCRUB] non_striker='Nitish Rana' rejected reason=status_yet_to_bat`**
   — WS payload scrubber rejects Rana as non_striker because his
   `batting_card[name]["status"]` is still `yet_to_bat`.  Logged
   **299 consecutive times** over 38 minutes.  The audit (2026-04-25)
   corrected an earlier mis-framing here: there is **no separate
   "squad" data structure with its own status field**.  WS-SCRUB
   queries `scoreboard.batting_card[name]["status"]` directly
   (`test_pipeline.py:3293-3311`); that is the single canonical
   field.  Rana stayed `yet_to_bat` because `update_batter("Rana", ...)`
   was repeatedly rejected upstream by the auto-dismiss replacement
   path's wicket-tick gate (see fix path 1 below for the actual
   mechanism).

**Why this is a recovery deadlock — architectural framing:** every
individual guard is sensible in isolation:
- FRAME_POISONED prevents wild jumps from misread strips.
- Runs-delta guard prevents stat-graphic misreads.
- WS-SCRUB ensures only batting-status players appear in
  striker/non_striker.

Composed they create a deadlock with no exit:
- FRAME_POISONED rejects updates that would correct SM (because they
  look like jumps from SM's stale value).
- Runs-delta guard rejects strips showing the new batter's
  progressive runs (because SM's stale record has wrong runs to
  compare against).
- WS-SCRUB rejects the new batter's name because squad-status
  hasn't been updated.

The architectural pattern is the issue.  Tightening any individual
guard wouldn't fix the deadlock; loosening any would re-open the
failure modes those guards exist to prevent.  Parallel to the
rotation-guard override pattern from earlier sessions: each guard
rejects in isolation, but **cross-guard agreement on the rejection
target is a positive signal that the guards' reference state is
the wrong thing.**

**Suggested fix paths (in priority order):**

1. **(Shipped 2026-04-25, ~20 min)  Wicket-tick gate bypass for
   witnessed-FOW re-assertion.**  *Originally framed as "squad-status
   patch on auto-dismiss replacement", but audit found the underlying
   premise was wrong: there is no parallel squad data structure with
   a separate status field.  `batting_card[name]["status"]` is the
   single canonical field, queried directly by WS-SCRUB.  The actual
   deadlock mechanism is different and lives one layer up.*

   Live trace of the F832 chain: F339 corruption left Pathum
   resurrected in the active set; her real dismissal had already
   advanced `_last_autodismiss_wickets` to 1.  When Rana's strip
   arrived at F832, `update_batter` entered the `yet_to_bat` path,
   saw `len(active)=2`, called `_auto_dismiss_for_new_batter`, and
   the **wicket-tick gate at line 1316 blocked the re-assertion**
   because `_cur_wk=1 ≤ _last_dismiss_wk=1`.  Returns `None` →
   `update_batter` returns False → Rana stays `yet_to_bat` →
   WS-SCRUB rejects.  Repeats 1330 times.

   The gate's intent is to block phantom *new* wickets from
   extractor hallucinations.  It can't distinguish "phantom new
   wicket" from "re-applying canonical dismissal".  Fix: when
   exactly one missing-from-extractor active batter has a witnessed
   FOW entry, bypass the gate (FOW is canonical — no new wicket is
   created, just enforcing one that already happened).  Do not
   bump `_last_autodismiss_wickets` and do not call `_add_fow`
   (entry exists; immutable witnessed-rule would refuse the
   rewrite anyway).  Telemetry: `[INVARIANT] Re-asserting
   witnessed dismissal of '<name>' (wicket-tick gate bypassed —
   FOW canonical, ...)`.

   Composes with P0-A (Fix 1+2+3) as defense-in-depth at a fourth
   choke point.  P0-A prevents resurrection at the `update_batter`
   un-dismiss path and via the `validate_state_consistency`
   per-frame check; this fix ensures the auto-dismiss replacement
   path also recovers cleanly if any future code path re-introduces
   resurrection.

   Code: `eyes/scoreboard.py:_auto_dismiss_for_new_batter` lines
   ~1322-1370.  Tests: `test_recent_fixes.py` section 8 (4 tests,
   15 sub-checks) covering F832 replay, no-FOW phantom-wicket
   regression, multi-missing fall-through, and end-to-end
   `update_batter` chain.

2. **(Phase 1 shipped 2026-04-27, Phase 2 pending)  Multi-guard
   consensus override.**
   When N consecutive frames produce internally-consistent proposed
   states (batter exists in squad, runs progress monotonically,
   score monotonic, bowler in either team's bowling list) that
   get rejected by all three guards *simultaneously and in
   agreement on the alternative state*, treat that cross-guard
   agreement as evidence that **SM is wrong, not the reads**.
   Phase 1 logs telemetry-only
   `[STATE-RECOVERY-OVERRIDE-CANDIDATE]` lines and never mutates state.
   Phase 2 will accept the proposed state and reset SM only after
   candidate quality is validated.

   Implementation outline:
   - Each guard reports its rejection reason + the proposed
     alternative state to a central `RejectionAggregator`.
   - Aggregator detects "all guards rejecting in agreement on a
     coherent alternative" (≥ N=5 frames, ≥ 2 guards agreeing,
     proposed state internally consistent).
   - On trigger in Phase 1: log candidate/current state, guard
     families, proposed reset scope, coherence-check details, and
     N=3/N=5/N=8 threshold-frame telemetry. Clear accumulated counter.
   - On trigger in Phase 2: log `[STATE-RECOVERY-OVERRIDE]`, reset
     only the fields covered by the coherent proposal, and clear each
     guard's accumulated counter.

   **Phase 2 mutation — STAGED not enabled (2026-04-28):**
   Implementation lives behind ``STATE_RECOVERY_PHASE_2_ENABLED = False``
   in ``test_pipeline.py`` (module constant).  When set True after
   production validation, consensus events call ``ScoreManager.full_reset``
   and apply only candidate ``score`` / ``wickets`` / ``overs`` to
   ``scoreboard._inn``.  Phase 1 candidate logging is unchanged when the
   flag is False.  **Enablement:** set constant True after N matches show
   candidates only on known corruption windows and zero false fires
   during AUTO-SWAP / cold-start.

   **Phase 2 prerequisite — RESOLVED (2026-04-28):**
   `ScoreManager.full_reset()` (`[SM-FULL-RESET]`) runs
   `force_cold_start_recalibration()` then clears the same per-innings
   scalar surface Fix 16 resets (`bat1_*`, `bat2_*`, `bowler_*`, `striker` /
   `non_striker`, computed rates, `this_over`, `over_history`,
   `partnership_*`, `extras_*`, `fow_list`, pending tokens, etc.) while
   preserving `innings`, `target`, `batting_team`, `venue`, `match_info`,
   and `innings_history`.  Phase 2 mutation should call `full_reset()`;
   existing POISON-RECAL path in ``test_pipeline.py`` now calls
   ``ScoreManager.full_reset()`` (completed 2026-04-28) so Fix-16 scalars
   and ``_last_warm_state`` clear alongside cold-start recalibration.

   **Phase 1 validation expectations:**
   - Clean match / no corruption: 0 candidates expected.
   - AUTO-SWAP / innings transition windows: 0 candidates expected.
   - Chaotic cold-start: 0 candidates expected while cold-start gate is
     active.
   - Known stuck-state windows (Dube-class, F704/F775 active-batter
     corruption): candidates should line up with the stuck window.
   - If multiple historical corruption logs produce 0 candidates, the
     trigger is too conservative.  If clean/transition windows produce
     candidates, Phase 2 mutation would be unsafe.

   **Historical validation surface before live promotion:** run
   `analyze_match_telemetry.py --report-state-recovery` against
   archived CSK-vs-GT and LSG-vs-KKR logs.  These cover Dube-style
   runs lock-in, F704/F775 active-batter corruption, clean play
   stretches, and innings transitions without requiring live mutation.

3. **(Optional, post-step-2)  Frame-poison threshold age-decay.**
   If SM hasn't moved in N frames, drop the poison threshold so a
   single fresh read can override.  Today it appears to be a fixed
   delta.  Step 2's consensus override may make this unnecessary.

**Immediate mitigation (no code change, while this is unfixed):**
when this deadlock is detected (e.g. WS-SCRUB count > 50 or
FRAME_POISONED > 5 in last 60s), surface an alert and trigger a
hard SM reset that pulls fresh state from the next valid scout
strip.  Manual operator-led recovery is the temporary safety net.

**Size summary:** step 1 shipped 2026-04-25 (~20 min).  Step 2 is
the substantive piece (2–3 h including telemetry, consensus
thresholds, and validation tests).  Step 3 may not be needed.

**Priority:** P0 → P1 *for the specific F339→F832 mechanism* (closed
by P0-A Fix 1+2+3 plus P0-B step 1).  Step 2 remains P0 until shipped:
without it, any *future* resurrection mechanism that bypasses both
P0-A and P0-B could still produce a deadlock.  The architectural
fragility is the persistent risk, even though the specific mechanism
that surfaced today is closed.

**Evidence:** `logs/pipeline-2026-04-25-153247-dc-pbks-v5.log`
F339 (entry to bad state), F1215 (FRAME_POISONED), 299 WS-SCRUB warns
through F1227.  By innings 1 end (F2621 / DC 264/2 at 20 overs)
the deadlock had survived the entire innings; SM still showed
`inn=1, score=None-0 (19.5), Bat: KL Rahul Pathum Nissanka*, Bowl: Yuzvendra Chahal 1-12`.
**The innings boundary did not trigger a state reset** — confirming
that innings change isn't a recovery path for this deadlock either.

**Additional evidence 2026-04-26 (CSK vs GT, F52 phantom-+4
cascade):** Gaikwad's individual run tally drifted to UI=14 vs
CB=10 after a single-frame OCR misread under `_post_event_grace`
fabricated a +4 boundary at over rollover.  The `runs-monotonic`
guard correctly rejects further deltas but provides **no
recovery path** — inflation persists for the rest of the
innings.  This is structurally identical to the F832 deadlock
(guards correctly reject; nothing unwinds) and adds a second
match-day instance of the same class.  The bat-runs reconciler
(P1, see "Bat-runs reconciler against scoreboard total" above)
is the cheaper detection slice; correction routes through the
consensus override implemented in step 2.  Each new match-day
occurrence of "guards correctly reject but no path forward" is
direct evidence that step 2 is the right architectural lever.
WS-SCRUB lifetime count at innings end: **1330**.

### P0: SCORER doesn't enforce active-batter invariants (resurrects dismissed batters)

**Status — STAGED 2026-04-28:** `apply_scorer_decision` pre-filters `batter_updates` via `_scorer_batter_row_is_dismissed_resurrection`: witnessed outs → `[SCORER-INVARIANT-FILTER]`; non-witnessed `status=out` → `[SCORER-DISMISSED-RESURRECT]`. Wicket auto-dismiss only runs when canonical striker card is `status=batting`. Max-two-active enforcement remains future work (see suggested fix below).

**Item 2 — PR 1:** **Status: SHIPPED 2026-04-29** — SCORER schema helper + BATTERS invariant Phase 1 (noop autocorrect); shadow **`[SCORER-SCHEMA-WOULD-DROP]`** / **`[SCORER-SCHEMA-WOULD-COERCE]`** (`SCORER_SCHEMA_ENFORCE=False`). Design contract **`files/docs/investigations/scorer_invariants_categorization.md`**. Code **`files/scorer_decision_schema.py`**, **`files/test_pipeline.py`** (`process_scorer_decision_schema` after GRAPHIC strip; `finalize_schema_shadow_logs` with `filter_caught_in_step3`; `_batters_invariant_backstop` → `[BATTERS-INVARIANT]`, **`BATTERS_INVARIANT_AUTOCORRECT=False`**). Dependency **`pydantic>=2.5,<3`** in **`files/eyes/requirements.txt`**. Analyzer bundle B/C **`item2_scorer_schema_*`**, **`item2_batters_invariant`**; **`--report-pending-validation`**. Defense-in-depth Step 3 filters unchanged. **`SCORER_SCHEMA_ENFORCE` / BATTERS autocorrect Phase 2 flip:** **GATED** jointly with BATTERS prerequisites in **`files/docs/investigations/mi_srh_innings_break_analysis.md` Section 5** (same enablement envelope as backlog MI–SRH Phase 2). **PR 2** (prompt / Section 7.4): **GATED on Phase 2 enablement decision**. **PR 3+:** **GATED on production telemetry after schema enforce.** Do not modify **`SCORER_PROMPT`** inside the schema PR lane without prompt PR.

**§10.7:** helper-vs-root deviation — live path uses `process_scorer_decision_schema`; `ScorerDecision` is not load-bearing in production (see design contract).

### Item 2 PR 1 verification — 2026-04-28 (post-ship)

Post-ship review confirmed the live schema path matches **§10.7**: whole-decision normalization runs in **`process_scorer_decision_schema`** (`files/scorer_decision_schema.py`); the **`ScorerDecision`** root model is a public, importable symbol but is **not** invoked in production. Shadow telemetry **`[SCORER-SCHEMA-WOULD-DROP]`** and **`[SCORER-SCHEMA-WOULD-COERCE]`** are emitted from **`finalize_schema_shadow_logs`** in the same module (wired via `test_pipeline.py` `_apply_scorer_item2_cleanup`). **Operational defaults:** `SCORER_SCHEMA_ENFORCE=False`, `BATTERS_INVARIANT_AUTOCORRECT=False`. **Test harness:** `just test` → **860 PASS / 0 FAIL** (Groq client test still skipped unless `--run-groq`). **Analyzer:** bundle B/C keys `item2_scorer_schema_would_drop`, `item2_scorer_schema_would_coerce`, `item2_batters_invariant`; pending-validation catalog includes the same tags. **Still queued:** schema **Phase 2** (**GATED**: joint enablement envelope with BATTERS prerequisites per **`files/docs/investigations/mi_srh_innings_break_analysis.md` Section 5** + **`auto_demote`** refinement — not purely “watch A/B telemetry and flip blindly”) and **Phase 3** (optional filter deprecation) below; aligns with **`MONITORING_CHARTER.md` pending tag watch list** vs PR **2**/PR **3+** header above — distinct from standalone **§7.4 prompt** PR sequencing until Phase 2 is credible.

**Item 2 follow-on phasing:** PR **2** (**`SCORER_PROMPT`**, contract Section **7.4**) is **GATED on Phase 2 enablement planning** (`SCORER_SCHEMA_ENFORCE` / BATTERS flip — joint gate with **`mi_srh_innings_break_analysis.md` Section 5**). PR **3+** (optional per-filter deprecation) is **GATED on production telemetry** after Phase 2 enforce + A/B. Section **10.6** Phase 2 flip remains the near-term coordination point with BATTERS prerequisites.

**Item 2 design doc (spec reference):** `files/docs/investigations/scorer_invariants_categorization.md` — full inventory of SCHEMA-ENFORCEABLE vs STATE-DEPENDENT vs PROMPT-EXPRESSIBLE guards; validation order Parse → Schema → filters → apply → `[BATTERS-INVARIANT]`.

**Severity:** scorecard-fundamentally-wrong.  Observed for 22+ continuous
minutes of the 2026-04-25 DC-vs-PBKS run after a single confused strip
read at 15:50:05.

**Repro:**
- F141 (15:43:03): wicket fell at DC 28/1 (2.4), Pathum Nissanka out.
- F190 (15:44:31): FOW correctly upgraded to `Pathum Nissanka` and
  `[WICKET] Auto-dismissed Pathum Nissanka — Nitish Rana replacing`.
- F328–F330 (15:49:24–15:49:31): Scout reads the proper strip
  `RANA 11(5) | RAHUL 23(10) | JANSEN 0-10 (0.4)` and SM has
  `bat1=KL Rahul 23(10), bat2=Nitish Rana 11(5)`.  **State correct.**
- F339 (15:50:05): broadcast cuts to a phase-economy stats panel.
  Scout emits a malformed strip line.  SM scorer change list: `[
  'bat:KL Rahul=23(10)', 'bat:Pathum Nissanka=11(7)',
  'bat:Nitish Rana=11(5)', 'bowl:Marco Jansen' ]` — **three batters
  active** with Pathum (dismissed 7 minutes earlier) reinserted with
  her final dismissal figures.
- Subsequent frames push Rana out.  By F435 only Rahul and Pathum
  remain in active batters.  Pipeline runs another 22+ minutes with
  the dismissed batter shown to UI.

**Root cause:** SCORER merges scout/extractor input into active batter
state without enforcing cricket-physics invariants:
1. **Max 2 active batters.**  If a third name appears, at least one
   read must be wrong — the scorer should reject the third or pick
   the most recent two and log a warning.
2. **No batter resurrection.**  Once a player has a FOW entry their
   name must not be re-inserted into the active batter list.  The
   FOW list is the source of truth for "who is out".

**Suggested fix:**
- After SM applies scorer changes, run two assertions:
  - `len(active_batters) <= 2`
  - `active_batters.intersection(dismissed_batters) == empty`
- On violation: drop the offending change, log a `[BATTERS-INVARIANT]`
  warning with the SM state and the rejected delta, and let the next
  frame's scout re-confirm.

**Size:** 30–60 min.  The invariants are simple; the trickier part is
making sure the assertion site sees the right state — wherever the
SCORER's "merge into active list" logic lives.  Add unit test that
replays the F339 scenario.

**Evidence:** `logs/pipeline-2026-04-25-153247-dc-pbks-v5.log`
F141, F190, F328–F330, F339, F435.

### P1: Bowler stats graphic misread as bowler-change

**Status: STAGED 2026-04-28 — Scoreboard admission gate `[BOWLER-STATS-GRAPHIC-GATE]` in `files/eyes/scoreboard.py` `update_bowler()`: reject when `vision_desc` matches strong phase/career phrases (`IN T20`, `IN IPL`, `ALL FORMATS`, `OVERS 1-6` / `7-15` / `16-20`, `POWERPLAY`, `DEATH OVERS`, `IPL CAREER`, `T20 CAREER`, …) **or** proposed figures are impossible for one T20 spell (`wickets>10`, `runs>80`, `overs>4.0`). Bare `CAREER` without those phrases does not reject if figures are plausible. Vision wired via `apply_scorer_decision(..., vision_desc=)` (`test_pipeline.py`, `eyes/main.py`). Analyzer: `bowler_stats_graphic_gate` in bundle B/C report. Adjacent: **Fix 8** `[INFO-PANEL-GATE]` (strip stripping — unchanged), **17A** `[BOWLER-BATTER-GATE]`, **17B** / **17B+** consensus (unchanged).**

**Earlier (2026-04-26):** Fix 8 content-based gate via `filter_info_panel_contamination` in `test_pipeline.py` (`_INFO_PANEL_KEYWORDS` strips bowler fields from `extracted`). Awaits seam restart; transitions to SHIPPED at land time per `staged_fixes_2026-04-25/README.md` step 6.

**Validation 2026-04-26 CSK vs GT match:** Fix 8 has now produced its first active strip-fire at F1034 (16:22:12): `[INFO-PANEL-GATE] bowler stripped — name='HOLDER' panel_keyword='IN T20'`.  A Jason Holder career graphic was about to commit `bowler=Jason Holder`; Fix 8's content-based gate caught the `IN T20` keyword and stripped the bowler field before commit.  This is the active path validation we wanted; complemented by 5+ silent-path catches earlier in the match (where upstream `FRAME_POISONED` caught the same kind of frame before Fix 8's path was reached).  Status confidence: SHIPPED-confirmed once the bundle lands.

**Path-vs-value discipline (note for future readers):** at F1034, Jason Holder happened to be the *correct* bowler for the match (he's GT's bowl_allrounder, came on at over 7 and was bowling around over 10 when this frame fired).  Fix 8 stripped the bowler field anyway — and that is the structurally correct behaviour.  **The path is the bug, not the value.**  A bowler commit sourced from a stats-graphic overlay is wrong regardless of whether the value happens to be right, because accepting wrong-path-right-value invites accepting wrong-path-wrong-value the next time (yesterday's F619 case where Yuzvendra Chahal — who wasn't even bowling — got committed via the same path).  Fix 8 enforces "bowler must come from an active SCOREBOARD frame, never from a graphic," and the value-correctness on any given frame is irrelevant to that discipline.  If a future reader sees the F1034 telemetry and questions why Fix 8 rejected a "correct" value, this paragraph is the answer.

Observed 2026-04-25 DC vs PBKS, F619 (16:02:04):

Scout output: `STRIP: DC 68-1 (6) |   INFO_PANEL: YUZVENDRA CHAHAL IPL CAREER MATCHES 181 WICKETS 225 ECONOMY 8.0`

Camera_view tagged `graphic` correctly.  But the scorer pipeline still
ran on this frame (graphic gate apparently doesn't block bowler-update
path) and the `INFO_PANEL`'s "YUZVENDRA CHAHAL" got interpreted as
"bowler=Yuzvendra Chahal".  At this point Marco Jansen was still
bowling per the broadcast (Chahal hadn't been introduced yet).
The SM picked up Chahal-as-bowler from this graphic, then later when
Chahal *was* introduced the change had already been (mis)applied.

This means the pipeline can pick up a future bowler ahead of the
broadcast purely because they were name-dropped in a stats graphic.
(The original "compounds with the bowler-change pickup latency P1"
framing is now stale — that latency item was collapsed into the
BOWLER-STALE defense fix shipped 2026-04-25; see the resolved entry
below. The P1 here is about graphic-gate not blocking bowler updates,
which is independent of the disambiguator that BOWLER-STALE shipped.)

**Fix:** when `camera_view == 'graphic'` and the strip is degraded to
just `<team> <score>-<wickets> (<overs>) | <some name + stats>` (i.e.
no batter pair, no over runs digits), block bowler updates.  Today the
graphic-gate appears to apply to score/over updates but not bowler.

**Size:** 15-30 min (single guard inversion).

**Evidence:** `logs/pipeline-2026-04-25-153247-dc-pbks-v5.log`
F619, F643 (Chahal ECON graphic before Chahal bowls).

### SHIPPED (2026-04-25): BOWLER-STALE defense logic flaw — bowler-context disambiguator

**Status:** shipped mid-match-2 (between innings 1 over ~10 and end of
innings 1) after damage-scope re-evaluation.  Original deferral to
Path 2 was revoked when match-2 analyzer telemetry revealed 54+
rejects across 4 distinct bowlers (Shivang / Sakib / Hinge / Cummins),
not the single-bowler scope the deferral assumed.

**Fix shipped (Option 2, bowler-context disambiguator):**
1.  `Scoreboard.__init__` (around L305) — added
    `_bowling_card_active_write_frame: dict[str, int]`,
    `_bowling_card_active_write_bowler: dict[str, str | None]`, and
    `_BOWLER_STALE_FRESH_FRAMES = 180`.
2.  `update_bowler` write site (around L2285) — after a meaningful
    write (when the rendered figure string changed), stamp the
    above two dicts with the current frame and the
    `current_bowler` at write time.
3.  `update_bowler` same-figures gate (around L2060) — bypass the
    rejection iff `(frame - last_w_frame) <= 180` AND
    `last_w_bowler == current_bowler`.  When EITHER fails, the
    original stale-graphic defense fires unchanged.
4.  `set_innings_2` — reset the two tracking dicts so innings-2 has
    no carried-over write history.

**Threshold rationale:** 180 frames (~9 s @ 20 fps).  Disambiguator
removes the threshold-tuning uncertainty the original P2-deferral
flagged; the bowler-context check carries the actual semantic
separation, so the freshness window can be permissive.  Match-2
empirical interval distribution (within-bowler median 14 / p95 207;
across-bowler min 35 / median 103.5) overlaps and was therefore
not separable by threshold alone.

**Tests added (5):** in `test_recent_fixes.py`, registered after
the archival block:
1.  `test_bowler_stale_replay_shivang_f311_f500_trap` — Shivang
    F311-F500 trap replay; asserts `current_bowler` flips after 3
    same-figures reads.
2.  `test_bowler_stale_replay_sakib_second_trap_general` — Sakib
    F527-style sequence; asserts the fix is general across bowlers.
3.  `test_bowler_stale_genuine_stale_graphic_still_rejected` —
    write at F100 with current_bowler=Shivang, advance to F1000
    with current_bowler=Pat Cummins, replay Shivang figures;
    asserts rejection still fires.
4.  `test_bowler_stale_boundary_within_freshness_same_context` —
    repeat read 1 frame later with same `current_bowler`;
    asserts not rejected.
5.  `test_bowler_stale_boundary_within_freshness_different_context`
    — repeat read 1 frame later under different `current_bowler`;
    asserts rejection (rapid stale-graphic across context change).

**Test-suite state post-ship:** 130 PASS / 2 FAIL.  Both failures
are pre-existing and unrelated (`OverManager._pending_clear` and a
`>= 18.0` legacy-cap leftover); neither touches `Scoreboard.update_bowler`.

**Live validation (2026-04-25 RR vs SRH match-2 innings 1, post-fix
restart):** 7 inter-bowler transitions confirmed cleanly with 0
`[BOWLER-STALE]` rejects:

| over | transition | frames-to-confirm | total latency | notes |
|------|------------|-------------------|---------------|-------|
| 13.0 | None → Reddy (cold-start) | +23 | 32.6 s | normal |
| 14.0 | Sakib → Reddy | +39 | **118.8 s** | broadcast pause outlier |
| 15.0 | Reddy → Hinge | +14 | 42.1 s | normal |
| 16.0 | Hinge → Cummins | +21 | 43.7 s | normal |
| 17.0 | Cummins → Sakib | +33 | 44.1 s | normal |
| 18.1 | Sakib → Malinga | +68 | **115.9 s** | broadcast pause outlier |
| 19.0 | Malinga → Hinge | +9 | 38.3 s | normal |

**Latency decomposition (RCA on the 18.1 outlier):** the 115.9 s
total breaks down as 99 s of broadcast pause (`digits=False` for
F1077–F1109, ~30 frames where Scout sees the strip but the
broadcast obscures the digits via graphic overlay / sponsor break /
DRS review / drinks break) plus ~17 s of pipeline 3-frame consensus
once digits resume.  The 14.0 outlier follows the same pattern.
Median pipeline-only contribution: ~10–15 s (within 3-frame
consensus window).  **The original "Bowler-change pickup latency
30–72 s" backlog item collapses into this fix** — what looked like
a pipeline bug was a composition of (a) the BOWLER-STALE rejection
path (now fixed) and (b) irreducible broadcast cadence + 3-frame
consensus floor.  Items merged.

### Resolved (2026-04-25, collapsed into BOWLER-STALE fix above): Bowler-change pickup latency (~30-72s)

Known latency on detecting a bowler change event.  No action taken yet;
belongs with the next Scout iteration.  (Captured from prior
conversations — no analysis doc yet.)

**Live confirmation (2026-04-25 DC vs PBKS):**
At the over-3 → over-4 transition, the pipeline picked up
`Arshdeep Singh → Marco Jansen` after **+37 frames / 72481 ms**
(over rolled at 3.0).  This is at the high end of the previously
observed 30–45s window.

**RCA promotion (2026-04-25 RR vs SRH match-2):** the latency turned
out to be only the surface symptom — the deeper bug is a logic flaw
in the `[BOWLER-STALE]` defense in `Scoreboard` that **actively
rejects** legitimate bowler-identity transitions, not just delays
them.  Trace from
`logs/pipeline-2026-04-25-195304-rr-srh-v5-archival.log`:

| frame | time     | scout reads      | recorded bowler | what happens |
|-------|----------|------------------|-----------------|--------------|
| F307  | 20:03:58 | "Shivang 0-0 (0)"  | Sakib 1-13 (1) | first read of new bowler |
| F309  | 20:04:08 | "Shivang 0-1 (0.1)"| Sakib 1-13 (1) | TRACK consensus 2/3 |
| F311  | 20:04:20 | "Shivang 0-1 (0.1)"| Sakib 1-13 (1) | TRACK 3/3, BOARD writes Shivang stats, **then BOWLER-STALE rejects bowler-identity** with `proposed 0-1(0.1) exactly matches recorded None-1(0.1); no handoff grace` |
| F312–F317+ | 20:04–20:05 | "Shivang 0-1 (0.1)" | Sakib 1-13 (1) | BOWLER-STALE keeps rejecting (16+ consecutive defense fires) |
| F341  | 20:05:47 | "Shivang 0-5 (0.3)"| Sakib 1-17 (1.1) | runs flip 1→5, BOARD writes stats, BOWLER-STALE rejects again on next read |
| F407  | 20:08:01 | (over 7 begins, over-end flush) | — ?-? (?) | bowler tracker reset by over-completion logic |
| F408  | 20:08:02 | "Cummins 0-20 (2)" | Cummins 0-20 (2) | new bowler (Cummins) confirmed via `[BOWLER SEED]` mid-spell entry path |

**Root cause:**  the BOWLER-STALE check fires when (a) the proposed
bowler is not the current bowler, AND (b) the proposed read exactly
matches what we just recorded for that bowler.  Condition (b) is
trivially true on every read after the first, because the first read
is what *populated* the recorded value.  The defense was designed to
catch end-of-spell graphics flashing the previous bowler's final
figures, but it has no freshness check on `recorded`, so it can't
distinguish "stale graphic" from "newly-locked-in active bowler whose
stats haven't ticked yet."

**Worst-case impact:**  a 1-over spell from a new bowler is
**100 % mis-attributed** to the previous bowler.  In match 2 today
Shivang Kumar bowled all of over 6 (Scout read him on every
scoreboard frame); his figures `0-10` were instead absorbed into
Sakib Hussain's tracker (`1-13 → 1-23`).  Wire commentary used
`ext_bowl` directly so it was correct, but the scoreboard / UI
state, fielding-template trigger, and post-match analysis all saw
Sakib bowling the over.

**Precise write-path characterization (verified against
`scoreboard.py`, 2026-04-25):**  during the trap, two write paths
behave asymmetrically:

1.  *`update_bowler("Shivang", ...)` direct path* — same-figures
    rejection at line 2082 returns `False` **before** the tracker
    writes at line 2198, so during a rejected call **no** writes
    land on either bowler's card.  Shivang's card therefore
    receives writes only on frames where his proposed figures
    actually differ from `recorded` (the first read after a stats
    tick, which then locks them in for the next several frames).
    Net: Shivang's card holds partial first-frame snapshots, not
    his real over-end figures.
2.  *`BOWLER-AUTO` path (lines 1180-1305)* — the team-score →
    bowler-stats mirror targets `self._inn.get("current_bowler")`,
    which stays Sakib because consensus never accumulates.  The
    over-boundary guard at lines 1238-1243 / 1282-1287 only skips
    the *first* ball of a new over (team overs `X.0 → X.1`); balls
    2-6 hit BOWLER-AUTO with `_team_balls_in_over ≥ 1`, so each
    legal delivery in Shivang's over ticks Sakib's card by one ball
    plus any runs delta.  This is where the Sakib inflation
    actually originates.

**Implication for the fix:** because BOWLER-AUTO consults
`current_bowler` on every increment, **fixing the identity flip
alone is sufficient.**  No separate stats-migration is required —
once `current_bowler` flips to Shivang, BOWLER-AUTO targets the
correct bowler from that frame onwards.  Damage from before the
fix-takes-effect frame is residual and bounded to the trapped
spell; not worth retroactive correction.

**Downstream symptom (also seen today):**  `[FIELD-MONITOR]` fired
for 376+ frames warning "field-state updater is the bug."  It is
not the bug — the field-state updater's "bowler-change" trigger
never fires while BOWLER-STALE traps the bowler-identity.  Once
the over-end flush released the trap at F407, the field correctly
transitioned `pace_powerplay → pace_middle`.  Fixing this item
should silence the FIELD-MONITOR false-positive at the same time.

**Fix candidates:**

1.  Stamp `recorded_at_frame` on every bowler-stat write; in the
    BOWLER-STALE check, only treat `recorded` as "stale graphic
    candidate" when it was written more than N frames ago (e.g.
    N = 30, ≥1 over).  Just-recorded values are by definition
    not stale.
2.  Gate the staleness rejection on bowler identity equality.  If
    the proposed bowler matches `current_bowler`, never reject the
    read; if it doesn't, only treat as stale when there's been no
    fresh write to that bowler's tracker in the past N frames.
3.  Add a `must_change` handoff grace at over-end:  when overs
    advance, give the next observed bowler N frames of "any-read-
    accepted" before re-engaging the staleness defense.

Path 2 is probably the cleanest; the freshness check from path 1 is
the underlying mechanism either way.

**Recommended implementation sketch (path 1 + path 2 hybrid):** add
`self._bowling_card_active_write_frame: dict[str, int] = {}` in
`__init__`; update it after the tracker writes around line 2212
when any of `runs/wickets/overs` was actively written; expand the
gate at line 2060 with `not recently_written` and tighten it to
require `hist_w is not None and hist_o is not None` (removing the
`hist_w or 0` coercion that masks None as 0).  ~8 source lines, 1
file (`scoreboard.py`), 3 touch points (init, write site, gate).
No existing tests assert the same-figures rejection on this
pattern (verified via `rg "BOWLER-STALE|same_figures|stale.*graphic"
files/test_*.py`), so existing tests are unaffected.

**Size:** investigation 30 min (already done above), fix + tests
60–120 min.  Regression test must cover both the original failure
mode (true stale end-of-spell graphic should still be rejected) and
the new failure mode (1-over new-bowler spell should be attributed
correctly).

**Pre-ship checklist (added 2026-04-25, post-Path 2 deferral):**

1.  **Empirical freshness threshold from match-2 data.**  The
    120-frame default in the implementation sketch above was a
    reasoning estimate (~6 s @ 20 fps).  Before shipping, extract
    the actual distribution of inter-bowler-strip-read intervals
    from match 2's innings 1 log:
    *   *Within-over interval distribution* — time gaps between
        consecutive Scout reads of the same bowler's strip during a
        single over.  Pick threshold ≥ 95th percentile so
        between-delivery reads are never false-rejected.
    *   *Across-over interval distribution* — time gap between
        last bowler read of over N and first bowler read of over
        N+1 (different bowler).  Validate that the chosen threshold
        sits comfortably below this distribution so genuine stale
        end-of-spell graphics still trip the defense.
    Source: `logs/pipeline-2026-04-25-195304-rr-srh-v5-archival.log`
    or successor session.  Tool: `analyze_match_telemetry.py` plus
    a small inter-arrival-interval extraction.

2.  **Log-replay regression test (not hand-constructed).**  Build
    a fixture from the F311–F500 sequence in the same log file.
    Replay the captured `update_bowler(...)` call sequence against
    a fresh `Scoreboard` instance and assert:
    *   `current_bowler` flips to `Shivang Kumar` within
        `CONSENSUS_N` reads after the first Scout sighting.
    *   No `[BOWLER-STALE]` rejection log line is emitted for
        `Shivang Kumar` during this sequence.
    *   Negative test: replay a synthetic "genuine 2-over-stale
        Shivang" sequence (write his over-1 figures, advance frame
        counter by ≥ N+threshold frames, then replay the same
        figures with a different `current_bowler`).  Assert the
        rejection still fires.
    Plus capture additional trap events from the rest of match 2 —
    every bowler-change in the remaining innings is a candidate
    fixture for broader coverage than just F311–F500.

3.  **Tracker stats-write assertion (verified above).**  This entry
    initially conjectured "stats writes go to Shivang's card during
    the trap; only identity flip is broken."  The audit (above,
    "Precise write-path characterization") shows that's wrong:
    direct `update_bowler` writes are blocked by the early `return
    False`, and the inflation actually comes from BOWLER-AUTO
    targeting the still-current `current_bowler`.  The fix
    implication is unchanged (identity flip propagates correctly)
    but the **damage model on Shivang's card is different** —
    Shivang's card holds partial first-frame snapshots, not "writes
    that work but get assigned to the wrong owner."  Make sure the
    log-replay test asserts the correct *post-fix* state: Shivang's
    card should converge to his real over-end figures via
    BOWLER-AUTO once `current_bowler` flips.

### P1: Scout never emits `side_on` (V5 third-example canary failing)

V5's third STEP-1 example covers `graphic`; the rulebook describes
`side_on` (square / side-on field camera, e.g. third-man or fine-leg
angle on a boundary chase) but `side_on` is not in the example set.
After 300 SCOUT calls in the first 27 minutes of live DC-vs-PBKS
play, **zero `side_on` emissions** — including from raw Scout JSON
output (no `wide_shot`/`wide`/`side_on` token has ever appeared in
the unaliased stream).

This is consistent with yesterday's "the example is the dominant
control surface" insight: side_on isn't an example, so Scout never
considers it.  The V1 alias re-point (`wide_shot`/`wide` →
`side_on`) is therefore inert in production — Scout never produces
the source tokens to alias.

**Implications:**
- The V5 "key qualitative signal" (side_on becoming nonzero) is
  likely unreachable on this prompt configuration.
- Wide elevated square shots are being absorbed by `closeup` (overshoot)
  or `bowlers_end` (false-positive of the kind the V5 rubric tried to
  fix).

**Potential fix paths (both contingent on V5 production precision eval):**
1. **Add `side_on` as a fourth STEP-1 example.**  Most likely
   effective per yesterday's insight.  Risks: a fourth example could
   destabilize the bowlers_end / closeup balance V5 reached.  Worth a
   shadow run.
2. **Keep `side_on` in schema but accept low rate.**  If V5 absorbs
   wide-elevated shots into `bowlers_end` correctly (precision eval
   confirms), the distinction matters less than overall bowlers_end
   precision.

**Path 0 (drop `side_on` from taxonomy entirely) is rejected.**
`side_on` has real downstream consumers and is *not* redundant with
`other`:
- `files/test_pipeline.py:683` —
  `_ACTIVE_PLAY_VIEWS = ("bowlers_end", "side_on")` gates the DWR
  active-play interval and dead-time skip logic.
- `files/ball_analyzer.py:627` —
  `if camera_view not in ("bowlers_end", "side_on", "replay"):`
  gates delivery-detection paths.
Removing `side_on` would collapse it into `other` (dead-time-skipped),
closing DWR windows mid-action on wide-elevated shots like
boundary chases / third-man fielder chases.

**Decision gate:** do the V5 production precision eval first
(see session_summary_2026-04-25.md §6 step 3).  If precision eval
shows wide-elevated shots are being correctly absorbed by
`bowlers_end` (low cost), no action needed.  If they are being
misclassified (closeup or other, breaking DWR), pursue Path 1.

**Size:** ~30 min variant + ~15 min mini shadow run on existing
41-frame corpus, *if* the precision eval indicates a path 1 need.

**Evidence:** `logs/pipeline-2026-04-25-153247-dc-pbks-v5.log`
(1250 SCOUT calls full innings 1, 3 side_on / 0 wide / 0 wide_shot
tokens).  Downstream consumer references in `test_pipeline.py:683`
and `ball_analyzer.py:627`.

### P2: WS-PROJECTION-GAP — striker / non_striker null in payload — **superseded / SHIPPED-pending-validation** (Fix 7 `[WS-PROJECTION-FALLBACK]` + Dual-broadcaster Path A)

**Status: STAGED 2026-04-26 inter-match commit bundle as Fix 7 — module-level `_project_active_batters` helper extracted from `build_full_payload`'s SM-cutover block; falls back to `sb._inn` when state[slot] is None AND sb._inn[slot] is in active_batting AND it doesn't collide with the already-resolved other slot. Active-batting check preserves S18's dismissed-batter-leak prevention. Awaits seam restart; transitions to SHIPPED at land time per `staged_fixes_2026-04-25/README.md` step 6. Then transitions to SHIPPED-pending-validation pending first-restart positive-firing telemetry (`[WS-PROJECTION-FALLBACK]` on next wicket); SHIPPED-confirmed once that telemetry lands.**

After ScoreManager has resolved striker/non_striker (e.g. via
broadcast strip read), the WS payload sometimes still emits
`striker=null, non_striker=null` for several frames.  Observed on
2026-04-25 (multiple WARN lines like
`[WS-PROJECTION-GAP] non_striker=None (payload) sb._inn.non_striker='Pathum Nissanka' sm.non_striker=None active_batting=['KL Rahul', 'Pathum Nissanka']`).

The warn line itself confirms the data source has the value but the
payload projection isn't reading it.  Almost certainly a
`build_full_payload` slot mismatch.

**Size:** 15-20 min (likely a single field rename / fallback).

**Live re-confirmation (2026-04-25 RR-vs-SRH, post-bowler-stale-fix
restart):** 14 fires across ~340 frames, concentrated around wickets
and over rollovers.  Pattern at W2 (F145, dismissal of Jurel):
`striker=None (payload) sb._inn.striker='Riyan Parag' sm.striker=None
active_batting=['Vaibhav Sooryavanshi', 'Riyan Parag']`. Scoreboard
correctly identified Parag as new striker, ScoreManager hadn't caught
up yet, payload uses SM → UI showed `—` / `incoming batter…` for
~24 s after the wicket (F145 → F31 catch-up was 24 s for W1; W2
catch-up similar).  User-visible during the most attention-grabbing
moment of the match (the wicket itself).  Reinforces P1 priority on
shortening the SM catch-up gap or having `build_full_payload` fall
back to `sb._inn` when SM is null *and* the scoreboard value is
present in `active_batting`.

**Reframed by Fix 5 (2026-04-25 inter-match bundle, striker self-
collision guard):** `sb._inn` is now collision-protected — it is
guaranteed never to hold `striker == non_striker` after Fix 5 lands
at the seam restart. This makes `sb._inn` a strictly safer fallback
source for the proposed `build_full_payload` fix. Pre-Fix-5, falling
back to `sb._inn` risked surfacing the collision class to the WS
payload (one bug class swapped for another); post-Fix-5, `sb._inn`
holds either the correct pair or the previous correct pair (from
idempotent re-assertion no-ops), never a self-collided pair. Promotes
the proposed fallback path from "consider with caution" to "preferred
fix shape." Fix size estimate unchanged (~15-20 min).

### P1: Striker self-collision in `update_batter` (`scoreboard._inn["striker"] == _inn["non_striker"]`) — **SHIPPED-partial-pending-validation** (Fix 5 Path A + Cluster 1 Path B live on over-change; post-wicket churn pending)

**Status: STAGED 2026-04-25 inter-match commit bundle as Fix 5 — Path A (conservative collision guard) shipped at `scoreboard.py:update_batter`. Path B (legacy striker-write removal / SM cutover completion) remains queued as a separate longer-arc cleanup. Awaits seam restart; transitions to SHIPPED at land time per `staged_fixes_2026-04-25/README.md` step 6.**

**Discovered 2026-04-25 RR-vs-SRH, post-bowler-stale-fix restart.**
27 of ~340 telemetry frames (~7.9%) emitted DETAIL lines with
`AFTER_striker == AFTER_non_striker` — i.e. the scoreboard's
`_inn["striker"]` and `_inn["non_striker"]` slots both held the same
name.  Concrete example: F174–F176 and again F290+ all show
`AFTER_striker=Vaibhav Sooryavanshi|AFTER_non_striker=Vaibhav Sooryavanshi`
even though the STATE renderer simultaneously prints
`Bat: Vaibhav Sooryavanshi(103) Riyan Parag*(2)` (Parag is the actual
striker per ScoreManager).

**Root cause.** `files/eyes/scoreboard.py:1802-1805` (inside
`update_batter`):

```python
if striker is True:
    self._inn["striker"] = name
elif striker is False:
    self._inn["non_striker"] = name
```

The write has no collision guard.  Sequence that produces the bug
(F170 → F173 in the live log):

1. F170 swap: extractor flags Parag as striker.  `update_batter`
   writes `striker=Parag` then the post-swap callsite writes
   `striker=Sooryavanshi, non_striker=Parag` (legacy code path).
2. F173: extractor reads a transitional review-graphic where the two
   batter rows are listed in the wrong order.  Pipeline calls
   `update_batter("Sooryavanshi", striker=False, …)` because
   Sooryavanshi appears in the lower row.  Line 1805 unconditionally
   writes `non_striker=Sooryavanshi`.
3. End-state: `striker=Sooryavanshi`, `non_striker=Sooryavanshi`.

The current scoreboard.py comment (lines 2122-2128) acknowledges the
legacy striker writes "should have been removed during cutover —
ScoreManager is now the sole authority", but the writes are still
firing and now produce a real correctness issue (not just diagnostic
flap).

**User-facing impact.**

- WS payload uses ScoreManager so the *primary* UI projection is
  unaffected (renders `—` instead, which is the WS-PROJECTION-GAP
  bug above).
- Commentary subsystem (`comm_storyteller`, `comm_analyst`,
  `comm_colour`) and any downstream analytics that read
  `sb._inn["striker"]` / `_inn["non_striker"]` directly receive
  collided values for ~8% of frames — they'll narrate "Sooryavanshi
  faces Sooryavanshi" or compute zero-length partnerships against
  the wrong reference.
- Telemetry / DETAIL records persisted for replay/analysis are
  corrupted at those frames; future log-replay tests will see
  `striker=non_striker` and either crash assertion-style or be hand-
  patched.

**Recommended fix scope (~30 min).** Two paths:

- **Conservative — collision guard.** At lines 1802-1805, refuse the
  write when it would create `striker == non_striker`:

  ```python
  if striker is True:
      if self._inn.get("non_striker") == name:
          log.warn(f"  [STRIKER-GUARD] Refusing striker={name} — "
                   f"already non_striker; would self-collide")
      else:
          self._inn["striker"] = name
  elif striker is False:
      if self._inn.get("striker") == name:
          log.warn(f"  [STRIKER-GUARD] Refusing non_striker={name} — "
                   f"already striker; would self-collide")
      else:
          self._inn["non_striker"] = name
  ```

- **Aggressive — finish the SM cutover.** Delete lines 1802-1805
  entirely and let ScoreManager own striker/non_striker.  The
  scoreboard.py:2122-2128 comment is the engineer's prior
  recommendation to do exactly this.  Risk: any consumer still
  reading `sb._inn["striker"]` directly would now get `None`
  whenever SM hasn't resolved yet — which is the same state the
  WS-PROJECTION-GAP bug already exhibits, so the surface area is
  bounded by that work.

**Tests to add (mirroring the bowler-stale fix pattern):**

1. Reproduce F170→F173 sequence: swap then transitional misread,
   assert `_inn["striker"] != _inn["non_striker"]`.
2. Direct collision attempt: pre-state striker=A, non_striker=B,
   call `update_batter(A, striker=False)` — assert refused, log
   warning fired.
3. Symmetric: pre-state striker=A, non_striker=B, call
   `update_batter(B, striker=True)` — assert refused.
4. Legitimate swap still works: pre-state striker=A, non_striker=B,
   call `update_batter(A, striker=False)` then `update_batter(B,
   striker=True)` in same frame — assert ends with striker=B,
   non_striker=A.

**Evidence.** `logs/pipeline-2026-04-25-203819-rr-srh-v5-bowler-stale-fix.log`,
27 self-collision frames detected via DETAIL parsing.  Sample frames
F174, F175, F176, F290.

### P2: Element checker stale header cleanup

**Status: SHIPPED (2026-04-28).**  `element_checker.py` now derives its
console banner from `CB_LIVE` instead of hardcoding the stale
`DC vs RCB (151935)` label.  No production validation needed; this is
operator-output hygiene.

### P2: FOW placeholder upgrade mechanism

Captured from prior conversations — no analysis doc yet.

---

## Test hygiene (P3)

**Status: CLOSED (2026-04-29).**  Both items below are resolved in
`test_recent_fixes.py`; re-verify with `just test` (exact PASS count
varies with suite growth).  Cross-ref:
`files/docs/investigations/INDEX.md` for investigation navigation.

These were stale-test mismatches against current production logic, not
production bugs.  They had been carried as the "2 pre-existing
baseline failures" through several fix landings (BOWLER-STALE hotfix,
the original 4-fix bundle 2026-04-25, the 6-fix bundle 2026-04-25/26
with Fix 5 + Fix 6, and the 8-fix bundle 2026-04-26 with Fix 7 + Fix
8).  Both have now been rewritten to match current production
semantics.

**Original bundle:** `staged_fixes_2026-04-25/README.md` "Test hygiene
addendum" section (test-only).

### P3: `test_this_over_late_boundary_ball_appends_to_held` asserts a no-longer-current `_pending_clear` invariant

**File**: `files/test_recent_fixes.py` (`test_this_over_late_boundary_ball_appends_to_held`, ~L244–287)
**Symptom**: `AssertionError: expected pending_clear=True` at L238,
**before** any of the actual late-boundary-ball logic runs.

**What it tests**: the BED→OverManager race where the closing event
of over 5 is popped from the BED queue *after* `check_over_change`
has already ticked team-overs to `6.0`.  The intended assertion: a
late `1_RUNS` event with `event.over="6.0"` should append to the
HELD over-5 token list, not start over 6.

**Why it fails**: the test was written against an earlier
`check_over_change` shape.  After the 2026-04-20 deferred-rollover
work (`ROLLOVER_MAX_DEFER_FRAMES`, see `files/eyes/this_over.py:60-80`),
the rollover from a 5-token state now routes through the deferred
path and does **not** immediately set `_pending_clear=True`.  The
test's pre-condition assertion fails before the late-event append
logic is exercised, so we don't actually know whether the late-ball
behaviour is correct under current code or not.

**Fix candidate (~10 lines)**: either
1. update the test to drive `om` through the deferred-rollover code
   path explicitly (call `check_over_change` `ROLLOVER_MAX_DEFER_FRAMES`
   times, or short-circuit by setting `_pending_clear=True` directly
   and asserting only the late-event append behaviour), **or**
2. rewrite the test to use the BED → OverManager integration shape
   that production now uses.

**Impact if untouched**: 1 test failure on every full-suite run,
masking real regressions in the same test class.  Zero production
impact.

**Resolution (2026-04-26)**: applied option (1).  Test now imports
`ROLLOVER_MAX_DEFER_FRAMES` and loops `(N + 1)` calls of
`check_over_change("6.0", ...)` to exhaust the defer budget and reach
the force-archive branch that sets `_pending_clear=True`.  All three
sub-checks (hold-not-flushed, late-ball appended to END, archive re-
written with late ball included) now pass — these were previously
masked by the failing pre-condition assertion, so the late-event-
append behaviour the test was designed around is finally being
exercised.

### P3: `test_twenty_over_invariant_check_in_source` flags an intentional `>= 18.0` threshold as a Bug-#16 leftover

**File**: `files/test_recent_fixes.py` (`test_twenty_over_invariant_check_in_source`, ~L730–752)
**Symptom**: `assert ">= 18.0" not in content` finds a single match at
`files/test_pipeline.py:5052`.

**What it tests**: a source-grep guard.  Bug #16 revision moved the
innings-end-detection auto-swap threshold from `>= 18.0` to `>= 20.0`
overs, and the test asserts no `>= 18.0` references survive.

**Why it fails**: a single intentional `>= 18.0` remains at
`test_pipeline.py:5052`, in the **relaxed-consensus** path
(`_inn1_near_end` predicate, L5050-5053).  The surrounding comment
(L5040-5049) explicitly documents this: the strict `>= 20.0` is the
threshold for the fast-path swap (1 frame is enough), while the
relaxed `>= 18.0` is the threshold for the consensus path (30+
sustained frames).  The grep can't distinguish "leftover" from
"intentional second tier".

**Fix candidate (~3 lines)**: tighten the test to match exactly one
expected occurrence inside the `_inn1_near_end` consensus block, or
exclude the documented relaxed-consensus block from the grep.  Do
**not** delete the production line.

**Impact if untouched**: 1 test failure per full-suite run,
co-located with the genuine 20-over invariant assertions, easy to
mistake for a real regression in someone else's PR.  Zero production
impact.

**Resolution (2026-04-26)**: dropped the negative-grep sub-check.
Re-investigation found that `>= 18.0` now appears legitimately at
**three** sites (not one): the `_inn1_near_end` consensus block at
`test_pipeline.py:5181`, plus two cold-start innings-2 detection
predicates at `test_pipeline.py:2559` and `:3170` that use
`< 18.0` (substring still matches the bare `18.0` literal).  All
three are intentional non-rollover uses; the bare grep can't
distinguish them from a Bug-#16 leftover.  Replaced the negative
sub-check with a docstring explaining the history; the two remaining
positive sub-checks (`>= 20.0` present, `>= 10` present) provide the
actual regression protection for the auto-swap trigger.  The Bug-#16
production line at `test_pipeline.py:5181` is preserved — it was
intentional all along and needed nothing changed.

---

## Blocked / queued

- **RC-1 / RC-2 corpus building** — queued, not blocked.
- **L2 re-bakeoff on post-Part-B clips** — queued, depends on Part A
  + Part B having shipped and produced enough clips to evaluate.
  Now unblocked on the Part B side.
- **Step 1 / Step 2 densification decision** — blocked on L2
  re-bakeoff.
