# Differential testing runbook

Practical guide to running the pipeline-level differential testing methodology against captured Scout dumps + Cricbuzz commentary ground truth.

## What this is

Per-delivery diff of pipeline UI state against Cricbuzz commentary ground truth, run programmatically against a captured Scout dump. No live replay required. No video watching required. Closes the watch-match-then-screenshot bottleneck that dominated the first 4 weeks of investigation.

Three components run in sequence:

1. **Ingester** — parses Cricbuzz ball-by-ball commentary markdown into `UIBallSnapshot` JSONL records (the canonical ground-truth fixture format).
2. **Pipeline snapshotter** — drives the full SM/pipeline against a captured Scout dump and emits one `UIBallSnapshot` per legal-ball boundary (= per `DIRECT-SCORE-COMMIT` / `trace_beta_sm_wicket_dispatch` event).
3. **Diff harness** — pairs the two JSONL streams by `over_ball` + `event_index`, classifies divergences across the defect-surface ledger, emits a 5-section markdown report.

For full design rationale see `files/docs/investigations/differential_testing_methodology_design.md`. This runbook is the operational view.

## Why use it (vs live replay)

- Runs in seconds, not 45-min match windows.
- Same Scout dump validates multiple fix iterations — no fresh broadcast capture per cycle.
- Diff is machine-checkable and surfaces every UI element per ball, not just the γ-bundle's 3 assertions.
- Catches cross-surface bug-class signatures (one bug manifesting on multiple surfaces simultaneously) that single-assertion live-replay misses.

When live replay IS still required: performance/lag defects (Obs 10 — workstream G), ad-occlusion timing (Obs 6 — workstream F sub-class B), Scout-extraction-timing at wicket-commit frames (commit 8/N cascade defer rate). These depend on UDP timing the captured dump doesn't preserve.

## File locations

| Path | Purpose |
|---|---|
| `files/scripts/ingest_cricbuzz_ground_truth.py` | Cricbuzz commentary → `UIBallSnapshot` JSONL |
| `files/scripts/replay_captured_scout_trace.py` | Scout dump → pipeline `UIBallSnapshot` JSONL (with `--snapshot-output`) |
| `files/scripts/replay_diff_harness.py` | Pipeline JSONL + GT JSONL → markdown diff report |
| `files/score_manager_derivation.py` | Pure derivation module (wicket/striker/this_over) — referenced by the snapshotter |
| `files/tests/fixtures/dckkr_innings_1_cricbuzz_commentary.md` | Raw Cricbuzz commentary, DCKKR match 51 innings 1 (full 20 overs) |
| `files/tests/fixtures/dckkr_ground_truth_ui_snapshots.jsonl` | Normalized GT snapshots (output of ingester) |
| `files/logs/deliveries/validate_dckkr_*/scout_raw.jsonl` | Captured Scout dumps from prior live replays |

## Prerequisites

- Project venv at `files/.venv/bin/python` (Python 3.12). System `python3` (3.9 on macOS) will fail on Python 3.10+ syntax in `eyes/agent.py`.
- Pre-commit hook installed per `scripts/setup_precommit.sh` (Layer 1.5 + Layer 2 gates).
- Scout dump available — either in `files/logs/deliveries/` from a prior replay session, or freshly captured.
- Cricbuzz commentary for the fixture — markdown file in `files/tests/fixtures/`.

## Quick start — DCKKR end-to-end

Single command sequence, fixture already present:

```bash
cd ~/Projects/SportsComm

# 1. Ingest ground truth (idempotent; re-run when commentary fixture changes)
files/.venv/bin/python files/scripts/ingest_cricbuzz_ground_truth.py \
  --commentary files/tests/fixtures/dckkr_innings_1_cricbuzz_commentary.md \
  --output files/tests/fixtures/dckkr_ground_truth_ui_snapshots.jsonl

# 2. Generate pipeline snapshots from captured Scout dump
files/.venv/bin/python files/scripts/replay_captured_scout_trace.py \
  --dump files/logs/deliveries/validate_dckkr_20260521_155356/scout_raw.jsonl \
  --session-id dckkr_diff_$(date +%Y%m%d_%H%M%S) \
  --fixture dckkr \
  --snapshot-output /tmp/dckkr_pipeline_snapshots.jsonl

# 3. Diff against ground truth, emit markdown report
files/.venv/bin/python files/scripts/replay_diff_harness.py \
  --pipeline /tmp/dckkr_pipeline_snapshots.jsonl \
  --ground-truth files/tests/fixtures/dckkr_ground_truth_ui_snapshots.jsonl \
  --report /tmp/dckkr_diff_report.md

# 4. Read the report
open /tmp/dckkr_diff_report.md
```

End-to-end runtime: under 60 seconds on dev hardware. Report is human-readable markdown + structured for grep/awk.

### Snapshotter coverage scope — SM-ONLY (load-bearing caveat)

**The snapshotter (`replay_captured_scout_trace.py`) runs an SM-only subset of the pipeline.** Per the script's docstring + verified at WS-M step-3 (commit `b11f000` arc close-out): `parse_strip` feeds directly into `ScoreManager.on_frame`; `test_pipeline.py`'s upstream guards (POISONED / GRAPHIC-FILTER-POISON / STANDINGS-ROW-GATE / FS-REJECT / etc.) do NOT run, and crucially **`over_mgr.attach_score_manager` is NOT called** in the snapshotter's `build_sm` helper at `files/tests/test_pipeline_captured_replay.py`.

**Implication for fix-iteration use (§8 below).** Fix-surface classes that span SM-internal logic ONLY are validated correctly via this workflow (e.g., `_accumulate_stats_from_event`, `apply_wicket_event`, `apply_striker_event`, canonical `self.striker` writers). Fix-surface classes that span **cross-module wiring** — specifically the `over_mgr` ↔ `score_manager` `bind_pending_slot` path used by ABSORBED_LEGAL events — are **NOT exercised** by this workflow. The PendingBall orphan-bind path (per WS-M step-1 memo `cfbd2f5`) doesn't fire in snapshotter runs; mechanism-confirmation tags emit count = 0.

**Pre-screen rule for empirical replay authorization** (per WS-M step-4 candidate methodology, single-instance footprint awaiting promotion): "Validate replay-tool fitness for the hypothesis fix-surface category BEFORE authorizing empirical replay budget consumption. Cross-module wiring fixes cannot be validated via this SM-only workflow." When fix surface is cross-module wiring → defer empirical to **natural production session traces** (`logs/trace/validate_*.jsonl` from live captures); shipped assertions can re-run against new traces budget-neutrally to confirm fix mechanism actually fires.

**Validation classes covered by this workflow:** SM-internal correctness fixes, assertion-side additions, single-module producer/consumer fixes within `score_manager.py`.

**Validation classes NOT covered:** cross-module wiring (over_mgr / PendingBall queue lifecycle), test_pipeline.py upstream guards, UI render layer (Phase 3), Scout extractor / external-corroboration paths.

## Reading the report

Five sections:

### 1. Per-surface incident count summary

Table of surface name → hit count → first occurrence over.ball → example. Use this as the headline metric. After a fix lands, the targeted surface should drop to 0 (or close); other surfaces should not increase.

### 2. Per-ball divergences

Markdown table indexed by `over.ball | event_index | field | pipeline_value | ground_truth_value | surface_classification`. Use this to localize defects by over.ball and to inspect specific divergences. The `event_index` disambiguates multi-event frames (e.g., 10.2's wicket-on-wide has 3 records at the same over.ball).

### 3. Conservation invariants

Numbered list of any failing Σ-checks:
- `Σ live_batter_runs + Σ dismissed_batter_runs + extras == score` (per-batter ledger conservation, Obs 16)
- `Σ bowler_balls per over == 6 + non-advancing-extras` (over-boundary ball conservation, Obs 2/5)
- Others as added.

Failing invariants are higher-leverage signals than individual surface hits — they indicate aggregate accounting corruption that span multiple per-ball events.

### 4. Unclassified divergences

Any DIVERGENT field that didn't match a known surface classifier. **These are new defect classes worth opening.** When a fix lands, audit the unclassified section first — it surfaces bug classes the existing classifier doesn't cover yet.

### 5. Methodology metadata

Counts of MATCHED / MISSING-IN-PIPELINE / PHANTOM-IN-PIPELINE / DIVERGENT records, total snapshot counts on both sides, and tagged classifier coverage percentage.

## Defect surface ledger (16 surfaces)

Each surface has a classifier predicate in `replay_diff_harness.py`. Counts are post-§15 commit (8/N) baseline against DCKKR dump.

| Surface | Predicate | Baseline count |
|---|---|---|
| G-pipeline-lag | Σ MISSING-IN-PIPELINE balls across run | 61 |
| F-A-commit-lag | `bowler_overs` MISSING-BALL on prev-over bowler + extra ball on next-over bowler at over-boundary | 49 |
| E3-wicket-frame-misalign | `fow_entries[N].over_ball` DIVERGENT for any FoW entry | 32 |
| F-B-ad-occlusion | Entire over's `bowler_name` DIVERGENT | 23 |
| D-post-FoW-striker | `striker_name` DIVERGENT at first delivery after a FoW entry | 20 |
| Per-batter-ledger-drift | Σ live-batter-runs + Σ dismissed-batter-runs + extras ≠ score | 17 |
| Extras-counter-drop | `extras_wd` DIVERGENT (pipeline < ground-truth) | 16 |
| Boundary-counter-double-increment | `striker_fours`/`striker_sixes` PHANTOM-IN-PIPELINE without corresponding `score` Δ | 10 |
| Recent-overs-drop | `recent_over_n_minus_1` MISSING when over N is completed in ground-truth | 10 |
| Bowler-W-credit-failure | `bowler_wickets` DIVERGENT for any bowler with corresponding FoW entry | 1 (post-7b) |
| Multi-ball-compression | Σ pipeline-ball-count < Σ ground-truth-ball-count for any over | 4 |
| Compound-with-wicket-token | `this_over_tokens[N]` = `Wd` in pipeline where ground-truth = `Wd+W` | 2 |
| C21b-symbol-revert | `this_over_tokens[N]` DIVERGENT where pipeline = `·` or run-symbol and ground-truth = `W` | 1 |
| E2-phantom-runs | `score` DIVERGENT (pipeline > ground-truth) at non-extras non-boundary delivery | 1 |
| Surface I — silent-wicket-absorption | GT FoW entry exists at over.ball X but pipeline FoW doesn't within ±N frames | 2 |
| Surface J — pipeline-missed-delivery | `derive_*` functions emit `PIPELINE-MISSED-DELIVERY` alert outside cold-start window | 0 (pending classifier landing) |

For surface semantics in depth see `validate_dckkr_replay_observations_20260522.md` (Obs 1-16 ledger) + the design memo §2.4.

## Adding a new fixture (different match)

### Step 1 — capture Cricbuzz commentary

Save the raw ball-by-ball commentary as markdown at `files/tests/fixtures/<match-slug>_innings_<N>_cricbuzz_commentary.md`. Format is the same as `dckkr_innings_1_cricbuzz_commentary.md` — reverse-chronological (latest over first, latest ball first within over), standalone `W` / `4` / `6` markers before ball records, over-end summary lines. The ingester handles the reverse-sort and the multi-event-per-frame disambiguation (see §7 Step 5b.1 in the design memo for the parse spec).

### Step 2 — capture (or locate) a Scout dump

Either run a fresh live replay against the match video to capture `scout_raw.jsonl` (see `HANDOFF.md` "Launch sequence" for the UDP/ffmpeg pipeline), or use an existing dump from `files/logs/deliveries/`.

### Step 3 — run the three commands

```bash
files/.venv/bin/python files/scripts/ingest_cricbuzz_ground_truth.py \
  --commentary files/tests/fixtures/<match-slug>_innings_<N>_cricbuzz_commentary.md \
  --output files/tests/fixtures/<match-slug>_ground_truth_ui_snapshots.jsonl

files/.venv/bin/python files/scripts/replay_captured_scout_trace.py \
  --dump <path-to-scout-dump.jsonl> \
  --session-id <match-slug>_diff_$(date +%Y%m%d_%H%M%S) \
  --fixture <match-slug> \
  --snapshot-output /tmp/<match-slug>_pipeline_snapshots.jsonl

files/.venv/bin/python files/scripts/replay_diff_harness.py \
  --pipeline /tmp/<match-slug>_pipeline_snapshots.jsonl \
  --ground-truth files/tests/fixtures/<match-slug>_ground_truth_ui_snapshots.jsonl \
  --report /tmp/<match-slug>_diff_report.md
```

### Step 4 — inspect the unclassified section

New fixtures often surface defect classes the existing classifier doesn't cover. Audit the report's "Unclassified divergences" section; if a pattern emerges, add a new classifier predicate to `replay_diff_harness.py`.

## Fix-iteration workflow

For each fix candidate (e.g., closing a specific defect surface):

```bash
git checkout -b fix/<surface-name>

# Capture pre-fix baseline (immutable reference)
files/.venv/bin/python files/scripts/replay_diff_harness.py \
  --pipeline /tmp/dckkr_pipeline_snapshots.jsonl \
  --ground-truth files/tests/fixtures/dckkr_ground_truth_ui_snapshots.jsonl \
  --report files/tests/baselines/dckkr_diff_pre_<surface>.md

# Apply fix
# ...

# Regenerate pipeline snapshots (the fix changes SM/pipeline behavior).
# NOTE: snapshotter is SM-only — see "Snapshotter coverage scope" caveat in §5.
# If your fix is cross-module wiring (e.g., over_mgr ↔ score_manager
# bind_pending_slot path), this workflow CANNOT validate it; defer to
# natural production session traces + shipped assertion re-run.
files/.venv/bin/python files/scripts/replay_captured_scout_trace.py \
  --dump files/logs/deliveries/validate_dckkr_20260521_155356/scout_raw.jsonl \
  --session-id dckkr_fix_<surface>_$(date +%Y%m%d_%H%M%S) \
  --fixture dckkr \
  --snapshot-output /tmp/dckkr_pipeline_snapshots.jsonl

# Capture post-fix report
files/.venv/bin/python files/scripts/replay_diff_harness.py \
  --pipeline /tmp/dckkr_pipeline_snapshots.jsonl \
  --ground-truth files/tests/fixtures/dckkr_ground_truth_ui_snapshots.jsonl \
  --report files/tests/baselines/dckkr_diff_post_<surface>.md

# Verify: target surface count dropped to 0; no other surface count increased
diff files/tests/baselines/dckkr_diff_pre_<surface>.md \
     files/tests/baselines/dckkr_diff_post_<surface>.md

# Layer 1.5 + Layer 2 pre-commit gate
git add files/<changed-files>.py files/tests/baselines/
git commit -m "fix(<surface>): close <description>

Pre-fix: <surface> N hits.
Post-fix: <surface> 0 hits. No regression on other 15 surfaces.
Reports: files/tests/baselines/dckkr_diff_{pre,post}_<surface>.md"
```

Commit messages should reference both before/after report paths as evidence. The reports themselves become the regression-detection artifact for future audits.

## Troubleshooting

### Layer 1.5 fails after pipeline snapshotter changes

The snapshotter's hooks into `_apply_event` / `_apply_wicket_fall_only` / `_synthesize_cold_start_ball_events` are sensitive to SM-class field placement. If you added/renamed an SM field, the snapshotter may read stale data. Check `replay_captured_scout_trace.py`'s snapshot-emit hook for hardcoded field names.

### Ingester emits fewer records than expected

The Cricbuzz commentary format has edge cases (e.g., wicket-on-wide creates 3 records at the same over.ball — see §7 Step 5b.1 parse spec). The ingester uses `event_index` within over.ball as a secondary key. If your fixture has new edge cases, the parser may need extension — inspect the unclassified divergences in the diff report for clues.

### `this_over` field empty in pipeline snapshots

Pre-§15-commit-(8/N) state: snapshotter read `scoreboard.this_over` which is always `[]`. Post-§15: the snapshotter reads `sm.this_over` with fallbacks. If you see empty `this_over` in current commits, check `replay_captured_scout_trace.py`'s snapshot-emit hook for the Patch A fix (per §9.3 / §5b.4 in the design memo).

### Snapshot count drops between runs

Snapshot triggers are `DIRECT-SCORE-COMMIT` + `trace_beta_sm_wicket_dispatch` + cross-frame `this_over` mutation. If wickets with Δscore=0 (e.g., clean bowled, 0 runs) don't snapshot, check `_SNAPSHOT_TRIGGER_TAGS` in the snapshotter — should include `trace_beta_sm_wicket_dispatch` per Patch B (§9.3).

### Surface count goes UP after a fix

Two common causes:
- Fix removed a silent fallback that was compensating for an upstream gap (see §13.8.1 commit (7/N) iteration — removing the conservative-refuse override regressed +24 boundary-counter). Restore the fallback (now under a canonical method) before retrying.
- Fix changed behavior at a different surface from the intended target. Inspect the report's per-ball divergences in the affected over.ball range for the unintended change.

### Cricbuzz commentary has new format quirks

The ingester targets Cricbuzz's 2026 format. If a fresh fetch has format drift, the parser may miss records. Spot-check by inspecting the GT JSONL output against the raw commentary for the first 5 overs; if records are missing, the parser's per-ball-record regex needs extension.

## Extending the harness

### Add a new classifier predicate

Edit `replay_diff_harness.py`'s `CLASSIFIERS` registry. Each entry is `(surface_name, predicate_fn, example_payload_builder)`. Predicate takes `(pipeline_snapshot, gt_snapshot, prev_pipeline, prev_gt)` and returns bool; example builder takes the same and returns a markdown string for the report.

### Add a new conservation invariant

Edit `replay_diff_harness.py`'s `CONSERVATION_INVARIANTS` registry. Each entry is `(invariant_name, check_fn)`. Check function takes the full snapshot sequence and returns a list of failure descriptions (empty list = invariant holds).

### Add a new `UIBallSnapshot` field

Update the dataclass schema in `files/scripts/replay_captured_scout_trace.py` AND `files/scripts/ingest_cricbuzz_ground_truth.py` simultaneously — both sides must produce comparable records. Re-run all three commands; check that ingester + snapshotter both emit the new field. The classifier may need updating to consume the new field.

## References

- Full design: `files/docs/investigations/differential_testing_methodology_design.md`
- Defect surface origin observations: `validate_dckkr_replay_observations_20260522.md` (Obs 1-16 ledger)
- Architectural principles: HANDOFF.md "Standing discipline" section
- Pre-commit gate spec: `scripts/setup_precommit.sh` + `.git/hooks/pre-commit`
- §15 wicket/striker/this_over rewrite arc: design memo §12 + §13 + §14 + §17 closure
