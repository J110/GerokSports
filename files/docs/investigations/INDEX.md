# Investigations index

Markdown under `files/docs/investigations/`.

**File count:** `ls files/docs/investigations/*.md | wc -l` → **64** (includes this file).

Canonical match-day discipline: **`files/docs/MONITORING_CHARTER.md`**.

Each row reflects filesystem `mtime` local to the authoring machine (**2026-05-01** refresh).

---

## Match analyses & innings handoffs

| Document | mtime | Summary |
|----------|-------|---------|
| `match_monitoring_plan_pre_live.md` | 2026-05-01 — | **Pre-live operator sheet** — IPL **2026-05-01**: grepped baselines (**MI–SRH**, **PBKS–RR**, **GT–RCB**), five-fix verdict criteria, tail one-liner, hard-stop, post-match comparison (**M1–M10**). |
| `cold_start_recovery_fix_implementation.md` | 2026-05-01 — | **POISON `/` Cause 3 SHIPPED** — pipeline-frame watchdog (**Path B**) + **`[COLD-START-FORCED-RECOVER]`**; thresholds **25 `/` 45**; tests (**starvation**, flip-heavy **`carousel`**, T20-max block, consensus **`3/3`**); **does not** repair **scorer starvation** (**F5054-class no viable triple**) — **`Direction L`**. |
| `cold_start_recovery_analysis.md` | 2026-05-01 — | **POISON-RECAL `/` MULTI_BALL Cause 3** — recovery duration corpus (**49** trips), **`trip_to_warm`** distribution (**stall ~69 `%` among traced **`COLD_START→WARM`**), legacy **`cold_frames`** blind spot, forensic **`F5054→`F5247`** gap (**Direction L**) + **`Path B`** rationale. |
| `tracker_stuck_mechanism_analysis.md` | 2026-05-01 — | **Cause 5** — tracker starvation vs strip (**§A4** **7** trips): **H3** dominant (**comparison-strip guard** + team epoch); **H5** innings-edge poison; **Cause 3** overlap; fix scope **MEDIUM** — **implementation deferred** (**investigation-only**). |
| `multi_ball_decomposition_design.md` | 2026-05-01 — | **Issue 3 Direction B** — Q1–Q4 design memo: **F5054** INDEX ✓ (**Pattern X**, W LOW); SM vs BED **`MULTI_BALL`** shapes; consumer split + Layer 2 enqueue gate; **Policy U** attribution vs retrospective **~4%**; **MEDIUM** scope; **`ready_to_ship` NO** (strict SMALL gate). |
| `multi_ball_decomposition_fix_implementation.md` | 2026-05-01 — | **Issue 3 SHIPPED** — N × **`ABSORBED_LEGAL`** + **`ball_events`** (D1); Layer 2 skip **`absorbed`** (D2); fixed striker across gap (D3); **`wire`** gap summary; pytest **`multi_ball_decompose`** ×5 + **`align_extractor_batters_fixture`** regression. |
| `multi_ball_recovery_design.md` | 2026-05-01 — | **MULTI absorbed Layer 2 recovery** — deque forensics (**~60 s** `@` ~20 fps **`FRAME_BUFFER_MAXLEN=1200`**); **`POISON-RECAL` ∉ buffer wipe** (SM-only); **`retrospective_span`** recap; GT–RCB **6×** gap table (**81–1070 s Δwall**) vs disk; **`recover-after-buffer-extension` / defer** (**implementation deferred**). |
| `state_integrity_f5054_f5240.md` | 2026-05-01 — | **GT–RCB `F5054→F5240`** — single **POISON-RECAL** (**54501**), **9m15s** wall / **186** frames to **`MULTI_BALL Δballs=25`** (**56057**); **post-match carousel** (**S7**); **ScoreManager** silent until **`cold-start candidate` `F5247`** (**56255**); **`SM=None BED=MULTI_BALL MISSED`**; revises freq-analysis interpretation (**investigation-only**). |
| `poison_recal_frequency_analysis.md` | 2026-05-01 — | **POISON-RECAL frequency** across **3** tees (**35** fires): trip logic **`abs(Δ)>7` + 5-frame streak** vs shorthand “Δ=8”; GT-RCB **24** vs baselines; **`MULTI_BALL Δballs` 7 + 25** worst cases; threshold verdict **mixed / chase-heavy aggressive**; Direction **B** default (**investigation-only**). |
| `graphic_strip_pollution_analysis.md` | 2026-05-01 — | **Cause 4** graphic OCR — **35** POISON-RECAL/3 tees; Mode **A/B** + info-panel; leverage **≥50%**; Path 2 Qwen blocklist **not** wired (**investigation-only**). |
| `graphic_strip_fix_implementation.md` | 2026-05-01 — | **Cause 4 SHIPPED** — GRAPHIC mismatch strip; info-panel **`|Δ|>7`**; **`_gfx_phase_recal_skip`** streak pre-empt; **`[GRAPHIC-FILTER]`** / **`[POISON-RECAL-PRE-EMPTED]`**; pytest. |
| `poison_recal_threshold_analysis.md` | 2026-05-01 — | **Cause 2** trip tuning — **§A4** Cause‑4 leverage **1/12 (~8%)** live (**strict** graphic‑OCR attribution); **7** genuine divergence / **4** strip-row+layout; verdict **<20%** → **Direction L** + Causes **2/3**, not Cause‑4‑first (**investigation-only**). |
| `state_integrity_f3293_f3346.md` | 2026-05-01 — | **GT vs RCB F3293→F3346** forensic memo — POISON-STREAK/**POISON-RECAL**/SM cold-start/**MULTI_BALL** timeline with tee line cites; Pattern **Y** disposition; strip row misalignment + graphic skips; broadcast gap notes (**investigation-only**). |
| `batter_stats_flipping_fix_spec.md` | 2026-05-01 — | **Issue 2 Task A** — `_update_batters` **SAFE_FOR_REORDER** verdict; `_align_extractor_batters_for_sm` paste-ready Python + FrameInput hook; fixtures **A–F**; Task B **YES** (**investigation-only**). |
| `batter_stats_flipping_fix_implementation.md` | 2026-05-01 — | **Issue 2 Task B SHIPPED** — helper + `FrameInput` wiring in `test_pipeline.py`; six pytest fixtures **A–F** in `test_recent_fixes.py`; telemetry **`[STRIKER-ALIGN-FALLBACK]`** + **`[BATTER-ALIGN]`** scan INFO; rollback + validation notes. |
| `batter_stats_flipping_mechanism.md` | 2026-05-01 — | **Issue 2** — flipped batter stats: **`FrameInput` bat1/bat2 = extractor row order** vs **`striker`/`non`** (SM axis split); **`test_pipeline.py:9850–9861`** fix locus; H5 HIGH / H7 amplifier; ship **NO** today (**investigation-only**). |
| `strip_row_pairing_analysis.md` | 2026-05-01 — | **Direction M2** — strip-row OCR ↔ **`batting_card`** pairing; **`[STRIP-ROWS-MISALIGNED]`** emitted from **`test_pipeline.apply_comparison_strip_batter_row_delta_guard`** (not `scoreboard.py`); GT vs MI/PBKS counts; hypotheses **H1/H6** dominant; phased fix-scope (**investigation-only**). |
| `batter_stat_swapping_analysis.md` | 2026-05-01 — | **Direction M** — **`[WS-SLOT-INVARIANT]`** GT vs MI/PBKS inventory; **`[WS-SCRUB]`** ↔ **`enforce_ws_slot_invariant`** loop (Pattern **P**); **`[STRIP-ROWS-MISALIGNED]`** as flipped-stats class (Pattern **R**); Lever 1 disposition + **Direction M2** strip/pairing audit (**investigation-only**). |
| `match_postmortem_data_gt_rcb_20260430.md` | 2026-04-30 — | **GT vs RCB (Apr 30)** sealed-tee diagnostic dump + companion JSON — truncation **~22:17**, innings transition evidence, DWR spans, Lever/thread telemetry counts, Phase 2 integrity notes vs log replay; links ESPN/IPL scorecards for human verification. |
| `mi_srh_innings_break_analysis.md` | 2026-04-30 08:07 | Innings-break analysis, PRIMARY tag baselines vs PBKS, Phase 2 DEFER matrix (Section 5), escalation surface — cross-ref `MONITORING_CHARTER`. |
| `batters_invariant_cluster_innings1.md` | 2026-04-30 08:07 | Fire-by-fire `BATTERS-INVARIANT`; **rule=C** admission-window Cause C mechanism; **F2167 rule=A** NON-ADMISSION; monitoring categorization baseline. |
| `lever1_pr2_match_analysis.md` | 2026-04-30 08:07 | MI–SRH PR2 hypothesis vs telemetry (W8 **not** dominant WS-slot source). [Predictions superseded by lever1_pr3_redesign Section 14.5.] |
| `pending_validation_pbks_rr_2026-04-28.md` | 2026-04-30 08:07 | PBKS–RR log absence / pending-validation operator notes (`[WS-SLOT-INVARIANT]` archive ~2.4/min baseline context). |

## Lever 1 rotation & extraction contracts

| Document | mtime | Summary |
|----------|-------|---------|
| `sm_rotation_atomicity_design.md` | 2026-04-30 08:07 | PR1/`_set_slot_pair` atomicity PR1→PR3 roadmap; Section 7 rate predictions superseded — [Predictions superseded by lever1_pr3_redesign Section 14.5; refuted outcome in lever1_pr2_match_analysis.] |
| `lever1_pr3_redesign.md` | 2026-04-30 10:21 | **SHIPPED** Lever 1 PR3: dismissed-partner guard, batter-arrival `STRIKER-SM-CUTOVER`, W3–W7 routing; authoritative Section 14 / 14.5 production targets (supersedes earlier Section 9 estimates). |
| `execute_innings_change_extraction_design.md` | 2026-04-30 10:20 | **SHIPPED** `_execute_innings_change_from_state` harness; Section 13 F2660–F2900 replay; P0 call-order invariant. |

## Dual-broadcaster Path B/C & substrate

| Document | mtime | Summary |
|----------|-------|---------|
| `dual_broadcaster_substrate_audit.md` | 2026-04-30 08:07 | Item 5 field map: 12 LOW / 2 MEDIUM / 2 HIGH surfaces; feeder strategy. |
| `dual_broadcaster_path_b_migration_contract.md` | 2026-04-30 08:07 | Item 3 **SHIPPED** LOW-risk batch SM feeder + divergence telemetry (`[SM-FEEDER-*]`); Path A parity contract Section 12+. |
| `dual_broadcaster_path_c_audit.md` | 2026-04-30 08:07 | **`this_over` / `partnership_*`** — Path C audit; C1+C2 both **DEFER** recommended (`SM` mirror removable read-through ownership). |
| `get_broadcast_state_path_b_audit.md` | 2026-04-30 08:07 | Lever 2: `get_broadcast_state` deprecation vs `get_live_state`; `_project_active_batters` parity. |
| `striker_path_b_read_audit.md` | 2026-04-30 08:07 | Item 1 read-site audit `_inn striker/non_striker`; bounded migration ledger. |

## Thread 7 (strip / cam-graphic / multi-ball)

| Document | mtime | Summary |
|----------|-------|---------|
| `thread7_rediagnosis_multi_ball_gap.md` | 2026-04-30 08:21 | RE-DIAGNOSIS: strip persistent + row transpose H1+H2; supersedes 2026-04-29 cosmetic verdict; actionable vs `scout` OCR. |
| `thread7_fix2_cam_graphic_fast_path_design.md` | 2026-04-30 10:01 | **SHIPPED** Thread 7 Fix 2: `cam=graphic` strip-head eight-clause fast path; telemetry `[CAM-GRAPHIC-FAST-PATH-*]`; Section 17 implementation notes. |

## P0 innings transition & architectural review

| Document | mtime | Summary |
|----------|-------|---------|
| `mi_srh_post_match_architectural_review.md` | 2026-04-30 08:39 | **P0** design contract: Fix 16 gap taxonomy, **P0-C** section team latch + cricket-rules swap + poison-rate telemetry threading 1–6. |

## Payload, SCORER, gates & recovery

| Document | mtime | Summary |
|----------|-------|---------|
| `this_over_indicator_ground_truth_design.md` | 2026-05-01 — | **Design-only** — invert ball-event architecture: broadcast **this-over** circles as **primary** truth, score deltas as **validation**; Phase A current pipeline (BED + `ThisOverManager`); A3 OCR protocol + **S1/S2** stop conditions; B flow sketch + pseudocode; C phased rollout (**weeks**); Cause 4 priority interaction. |
| `trace_and_detect_system_design.md` | 2026-05-02 — | **Design-only** — RR-DC post-mortem driven trace + anomaly detector. Promotes per-frame `DETAIL` line + ~40 guard tags into structured JSONL (`logs/trace/<session>.jsonl`, ~4–16 MB gz/match at 1 fps). Captures `scorer.proposed` vs `committed` + typed `decisions[]` + server-side `useMatchSocket`-mirror `ui_before`/`ui_after`. Nine internal-consistency rules **P1–P9** (batter persistence after wicket, score regression, stale bowler, partnership math, phantom wkts, extras inconsistency, innings reset w/o handoff, this-over arithmetic, stuck UI fields). Mode-aware suppression (COLD_START, INNINGS_HANDOFF, ad/replay, DRS). Post-match analyzer + Markdown report (v1); real-time `[ANOMALY-Pn]` tags deferred to v1.1; no auto-hard-stop. **MEDIUM scope ~860 LOC + tests, 1 session v1**. **§7** carries 7 operator decisions. |
| `build_full_payload_extraction_design.md` | 2026-04-30 08:07 | Path A payload extraction regression harness; `_build_full_payload_from_state`; baseline signer contract. |
| `scorer_invariants_categorization.md` | 2026-04-30 08:07 | Item 2 schema taxonomy SCHEMA- vs STATE- vs PROMPT-guards; PR1 shadow + BATTERS Step 5 backstop integration plan Section 7+. |
| `phase2_auto_demote_refinement.md` | 2026-04-30 — | **Design-only** Phase 2 `BATTERS_INVARIANT_AUTOCORRECT` rule=A `auto_demote` refinement: FOW-first demotion, F2167 validation fixture, unresolvable telemetry, enablement gate remains DEFER. |
| `full_reset_fow_extras_verification.md` | 2026-04-30 08:07 | `full_reset` vs FOW/extras / **POISON-RECAL** interaction verification. |
| `new_batter_balls_gate_2026-04-28.md` | 2026-04-30 08:07 | Fresh-admission **`[NEW-BATTER-BALLS-GATE]`** ceiling behavior. |
| `state_recovery_phase2_enablement_analysis.md` | 2026-04-30 08:07 | State recovery FP rate + refinement prerequisites before Phase 2 mutation flip. |

## Scout pipeline & shadow eval

| Document | mtime | Summary |
|----------|-------|---------|
| `delivery_detection_baseline_phase2ab.md` | 2026-04-30 — | **Phase 2A:** RCB–GT IPL 2025 Match 14, **overs 5–10**, **36** deliveries ground truth. **Phase 2B:** blocked — `logs/runs/rcb_gt_rc9_commentary_203904.log` missing in workspace; **Outcome A/B/C/D** unclassified; `[DWR]` tag note (`window` not `span_assembled`). |
| `score_event_coverage_audit.md` | 2026-05-01 — | **`save_dir` ENABLED** (`files/logs/deliveries/<session>/dNNN`); GT-RCB steady session **BED→enqueue 100% parity** (**215**) vs **`MULTI_BALL`/DRS skew** vs card phantom **`~1.9%`**; MI-SRH **`120`** internal parity (**innings-scope caveat**); Path 1b window audit **unblocked**. |
| `delivery_extraction_audit.md` | 2026-05-01 — | **Step 1 Path 1 audit (refresh):** Q1 telescope **adequate + artifacts** (`window_debug.json`/`layer2.json`); Q2 **`_find_span`** retrospective Scout **`bowlers_end`+action-phase** walk + guards; **`[DWR]`/`[L2]` tee gap** (**S3**); burst tracker **deprecated**; proceed Path 2/3 bounded. |
| `window_content_audit.md` | 2026-05-01 — | **Path 1b:** GT-RCB **`20260430_195352`** (**215** folders) — `window_debug` **sparse** Scout tags (**flight** in **2** deliveries); **12.5 s / ~161** frames typical; **layer2** schema **stable** (**213**); **length** 100% fill vs **no** logged bounce-frame proof; **mixed** bottleneck. |
| `scout_codebase_discovery.md` | 2026-04-30 — | **Discovery only:** Scout locality (Groq + `files/eyes/`), prod model/prompt lineage, V6c prompt variant in `shadow_eval/`, pipeline touchpoints, shadow harness + corpus paths; gaps for combined-corpus shadow scoping. |
| `scout_v6c_shadow_run_scoping.md` | 2026-04-30 — | **Execution scoping:** combined-corpus assembly, shadow harness constraints (`run_shadow`/resume), promotion bands from corpus narrative, backlog adjacency grid (Pass-2/sampler/`debug_frames`/side_on), phased plan + Composer stop conditions + open questions. |
| `scout_v6c_first_shadow_run_results.md` | 2026-04-30 — | **Delivered rerun:** corpus_v1 `V6c` artifact `files/docs/shadow_run_v6c_20260430_140220.json` (timestamped **`--output`**), merged **V5/V6c** metrics via parameterized **`analyze.py`**. Verdict mixed — see doc §5. Machine tables: `files/docs/scout_v6c_first_shadow_analysis_autogen.md`. |
| `scout_v6c_replicate_runs_decision.md` | 2026-04-30 — | **Three independent `V6c` shadows** (`run2/run3` + original run1): migration hashes, cross-run flip, watch frames **`f941`/`f748`/`f205`**. Classification — net **19/41 stable** vs V5 **20**; paired runs **2≡3** hash; cross-run aggregates in `files/docs/scout_v6c_replicate_analysis_autogen.md`, tool **`files/shadow_eval/replicate_analysis.py`**. |
| `scout_v6c_determinism_decision.md` | 2026-04-30 — | **Five `V6c` shadows** (+ **`groq_*`** metadata on **`run_shadow`** rows since run4/5): **4** migration hashes observed; paired **`7dd84…`** state **did not** repeat on next paired batch; unique response IDs, pervasive silent retries (**`groq_attempt_count`** **>** **1**). Machine tables **`files/docs/scout_v6c_determinism_analysis_autogen.md`**. |
| `scout_v6d_design.md` | 2026-04-30 — | **Design candidate (`V6d`):** targets **`f941`** escalation while preserving **`f205`/`f748`** `closeup` gains; hypotheses + paste spec for **`variants.py`** (parallel Composer session). |
| `scout_v6d_first_shadow_run_results.md` | 2026-04-30 — | **Delivered:** **`V6d`** in **`variants.py`**, **K=5** ensemble (`shadow_run_v6d_*_run*.json`). **PRIMARY §8 all pass** — median net **27/41**, **`f941`→`other`×5**, **`f205`** preserved, median strict BE **35.7%**, BE TP recall **100%**. **`f748`** regresses (**`bowlers_end`×5**). Autogen **`files/docs/scout_v6d_ensemble_analysis_autogen.md`**. |
| `m2_combined_corpus_sampler.md` | 2026-04-30 — | **SHIPPED:** `files/scripts/select_combined_scout_corpus.py` — multi-inventory **phase×innings** stratification, M-2 **`bucket_coverage`** + **`UNDOCUMENTED_ZERO`** / `--strict`; complements **`select_corpus_candidates.py`**. |
| `combined_corpus_shadow_v6c_v6d_2026-04-30.md` | 2026-04-30 — | **Delivered:** 3 inventories + `scout_corpus_combined_v1` (**50** frames) + V6c/V6d **K=5** shadows + `discriminating_frames_v6c_vs_v6d_combined.md`; notes **`materialize_combined_corpus_frames.py`** flattening for `run_shadow`. |
| `scout_v6d_implementation_audit.md` | 2026-04-30 — | **Audit:** `scout_v6d_design.md` vs **`variants.py`** `PROMPT_V6D` (Edits A/B); **`f600`** → **V6e**‑style side_on discrimination (H1+H3), impl drift refuted (`f600` not f941‑class exclusion). |
| `scout_v6d_error_rate_investigation.md` | 2026-04-30 — | **Investigation:** V6d combined ~**6.3%** pooled errors / **~11%** peak-per-run vs V6c ~**0.4%**; **`TimeoutError`** cluster at **~7s** harness cap + infra (**429**/502/connection); no **`length`**/**`content_filter`**; hybrid **H1+H5** vs prompt-only failure. |
| `scout_v6d_postharness_rerun_results.md` | 2026-04-30 — | **Step 2:** **`V6d`** **`K=5`** on combined corpus **post-harness** — **~0.53%** pooled (**4**/750): **Outcome A**, no **`TimeoutError`**; residue **429** exhaust + **500**; wall **~143–198** s/run. |
| `scout_v6e_design.md` | 2026-04-30 — | **Design (`V6e`):** third **`NOT`** on bowlers_end STEP‑1 (side_on / boundary chase) preserving V6d/V6c; §4 paste Python + §8 acceptance. |
| `scout_v6e_first_shadow_run_results.md` | 2026-04-30 — | **Step 5 delivered:** **`V6e`** **`K=5`** combined shadow + ensemble tables (`scout_v6e_ensemble_analysis_autogen.md`). **`f600`→`side_on`**; **`rcb_gt_f1455`** `other`→`bowlers_end` regression; **503**-heavy errors — **ambiguous / no prod paste**. |
| `parallel_scout_delivery_window_design.md` | 2026-05-01 — | **Design memo (no code) — parallel-Scout per-frame open-prose narration + span aggregator for delivery-window placement.** B1–B8 answered: NEW `OpenScout` async fire-and-forget after primary Scout; **1 fps** rate-gated (paused in ads); **`SpanAggregator`** state machine (min 2-frame, 1-frame gap merge, **90 s** retention, soft 2.5 s close); `_find_span_open` picks **earliest sufficient `action` span** in `[event_ts−25s, event_ts−1.5s]` filtered by `MAX_END_TO_EVENT_GAP_S=8s`; reuses existing `_span_to_clip_bounds` + `_get_frames` + `compile_frames_to_mp4`; **C3 feature flag with telemetry-only shadow** (`USE_OPEN_SCOUT_SPANS`, `_alt_*` in `window_debug.json`); cost **+\$0.07–\$0.12/match** vs current **~\$0.09**; scope **MEDIUM ~430–650 LOC + tests**, **2 sessions**. Replay-disambiguation hypothesis explicitly limited (n=6 GT replay). |
| `scout_per_frame_classification_validation.md` | 2026-05-01 — | **Weak (JSON path)** + **§11 Mixed (prose wide-camera rules)** — **247** frames; prod **R≈0.28** action; **§11** binary v2 on open text **P≈0.77 R≈0.99**; span **14/15** (v1) vs **13/15** (v2 binary), multiclass span **14/15**; artifacts **`rule_iteration_metrics.json`**, **`classify_descriptions.py`**. |

## Meta

| Document | mtime | Summary |
|----------|-------|---------|
| `INDEX.md` | 2026-05-01 — | This consolidated directory listing (filesystem-accurate count + domain grouping). |

---

Re-run `ls files/docs/investigations/*.md | wc -l` after edits and realign the **File count** header when files are added or removed.
