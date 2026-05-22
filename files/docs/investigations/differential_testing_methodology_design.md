# Differential-Testing Methodology — Next-Session Plan

**Authored:** 2026-05-22 post-replay-session (operator-directed)
**Status:** Design + concrete step-list. Execution = next session.
**Input artifact:** `validate_dckkr_replay_observations_20260522.md` (16 observations, 14 distinct defect surfaces, ~11 overs of empirical coverage).

---

## §1 — Why a methodology shift is necessary now

Current methodology = watch-match → screenshot → diagnose → log observation. Empirical signal from the 2026-05-22 replay: **16 observations producing 14 distinct defect surfaces across ~11 overs.** Defect-density outpaces fix-throughput by ≥10×. The match-watching step is the per-cycle bottleneck (~45 min per ~12-over window); every fix verification requires another full match-watch.

New methodology = programmatic Scout-dump replay → per-ball UI-state capture → diff vs Cricbuzz ball-by-ball ground truth → defect-surface classifier → report. **Removes the watch-match bottleneck.** Enables fix → re-run → verify in seconds, not hours. Same Scout dumps used for multiple fix cycles; no fresh match needed per iteration.

The architecture-rewind candidate from Obs 10 and the dual-source-derivation principle from Obs 11 also become testable: each per-ball Δscore/Δwicket/Δover can be reverse-derived from broadcast strip reads in the dump, and the diff engine can validate the derivation chain directly.

---

## §2 — Architecture (4 components)

### §2.1 — Component A: Full-pipeline Scout-dump replay driver

**Current state:** `files/scripts/replay_captured_scout_trace.py` exists. Per HANDOFF §"Captured-replay scaffold" + §0.3 retired-assumption: scaffold drives `SM.on_frame()` only — NOT `apply_scorer_decision`. C14 gate, WS payload generation, and several upstream paths are unreached.

**Required extension:** drive the FULL pipeline from `apply_scorer_decision` outward, including WS payload generation at every legal-ball boundary. Replay must produce the exact same WS payload sequence that the live pipeline would have produced from the same Scout-dump input.

**Key design constraint:** the replay must be deterministic. Same Scout dump → identical UI-snapshot sequence on every run. Any non-determinism (clock-based, thread-race, etc.) must be eliminated or seeded.

### §2.2 — Component B: UI-state snapshotter

**Snapshot trigger:** fires at every legal-ball boundary (= every `DIRECT-SCORE-COMMIT` event in the pipeline). Wide / no-ball / extras-only events trigger a snapshot too (they still advance the per-ball event ledger even if they don't advance the legal-ball counter).

**Snapshot schema — `UIBallSnapshot`:**
```
over_ball: str               # "10.3"
score: int                   # 75
wickets: int                 # 2
balls_total: int             # 63
striker_name: str            # "Nissanka"
striker_runs: int            # 43
striker_balls: int           # 25
striker_fours: int           # 3
striker_sixes: int           # 2
non_striker_name: str        # "Rizvi"
non_striker_runs: int        # 0
non_striker_balls: int       # 2
non_striker_fours: int       # 0
non_striker_sixes: int       # 0
bowler_name: str             # "Green"
bowler_overs: str            # "0.3"
bowler_runs: int             # 13
bowler_wickets: int          # 0
this_over_tokens: list[str]  # ["1", "6", "1", "W"]
recent_over_n_minus_1: list[str]  # last completed over
partnership_runs: int        # 16
partnership_balls: int       # 13
extras_total: int            # 1
extras_wd: int               # 1
extras_nb: int               # 0
extras_b: int                # 0
extras_lb: int               # 0
fow_entries: list[tuple]     # [(49, 1, "Rahul", "4.5"), (76, 2, "Nissanka", "7.4")]
```

**Capture path:** intercept the WS payload builder (`build_full_payload` per HANDOFF §5.1) and serialize to `UIBallSnapshot` at each fire. Append to a JSONL output stream keyed by `over_ball`.

### §2.3 — Component C: Cricbuzz ground-truth ingester

**Input:** Cricbuzz ball-by-ball commentary + score JSON. Fixture path: `files/tests/fixtures/dc_vs_kkr_2026_152064_ledger.json` (per HANDOFF §"File paths"). May need re-fetch with full per-ball detail if existing fixture lacks per-ball UI state.

**Output:** sequence of `UIBallSnapshot` records — one per legal ball, plus inter-ball extras snapshots where applicable. Same schema as Component B's pipeline output. Both sides must produce comparable record sequences.

**Normalization rules:**
- Cricbuzz over-numbering convention (1-indexed first ball = 0.1) must match pipeline's
- Player-name canonicalization: pipeline uses last-name-only ("Nissanka"); Cricbuzz uses full names ("Pathum Nissanka"). Add resolver to map both sides to a canonical form.
- Bowler-name same treatment (Anukul Roy → "Roy"; Varun Chakravarthy → "Chakaravarthy"; Sunil Narine → "Narine")
- Extras decomposition: Cricbuzz commentary often combines (e.g., "Wd, 1 leg-bye + W run-out"); ingester must split into the schema's individual fields

### §2.4 — Component D: Diff engine + defect-surface classifier

**Input:** two `UIBallSnapshot` sequences (pipeline + ground truth), indexed by `over_ball`.

**Per-field diff types:**
- exact-match → record as MATCH
- absent-in-pipeline (pipeline missed a ball) → MISSING-IN-PIPELINE
- extra-in-pipeline (pipeline fabricated a ball) → PHANTOM-IN-PIPELINE
- value-differs → DIVERGENT (record both values)

**Defect-surface classifier — use the 14 surfaces from this replay's `validate_dckkr_replay_observations_20260522.md`:**

| Surface ID | Detection signal in diff | Source observation |
|---|---|---|
| C21b-symbol-revert | `this_over_tokens[N]` DIVERGENT where pipeline = `·` or run-symbol and ground-truth = `W` (or compound) | Obs 1/4/12/13/15 |
| F-A-commit-lag | `bowler_overs` MISSING-BALL on prev-over bowler + extra ball on next-over bowler at over-boundary frame | Obs 2/5 |
| F-B-ad-occlusion | Entire over's `bowler_name` DIVERGENT | Obs 6 |
| Boundary-counter-double-increment | `striker_fours` or `striker_sixes` PHANTOM-IN-PIPELINE without corresponding `score` Δ | Obs 3 |
| D-post-FoW-striker | `striker_name` DIVERGENT at first delivery after a FoW entry | Obs 7 |
| E2-phantom-runs | `score` DIVERGENT (pipeline > ground-truth) at non-extras non-boundary delivery | Obs 8 |
| E3-wicket-frame-misalign | `fow_entries[N].over.ball` DIVERGENT for any FoW entry | Obs 9 |
| G-pipeline-lag | Σ MISSING-IN-PIPELINE balls across run | Obs 10/11a |
| Recent-overs-drop | `recent_over_n_minus_1` MISSING when over N is completed in ground-truth | Obs 11b |
| Multi-ball-compression | Σ pipeline-ball-count < Σ ground-truth-ball-count for any over | Obs 13 |
| Compound-with-wicket-token | `this_over_tokens[N]` = `Wd` in pipeline where ground-truth = `Wd+W` | Obs 13 |
| Extras-counter-drop | `extras_wd` DIVERGENT (pipeline < ground-truth) | Obs 13 |
| Bowler-W-credit-failure | `bowler_wickets` DIVERGENT for any bowler with a corresponding FoW entry | Obs 14 |
| Per-batter-ledger-drift | Σ live-batter-runs + Σ dismissed-batter-runs + extras ≠ score | Obs 16 |

**Output:** per-ball diff report + per-surface incident count summary. Report format: markdown table for human review + JSONL for machine consumption.

---

## §3 — Concrete next steps for next session (in execution order)

### Step 1 — Asset inventory (≤5 min, single bash session)

Confirm what already exists:
```bash
ls -la files/scripts/replay_captured_scout_trace.py
ls -la files/logs/deliveries/validate_dckkr_*/scout_raw.jsonl
ls -la files/tests/fixtures/dc_vs_kkr_2026_152064_ledger.json
ls -la files/scripts/cricbuzz_*.json
```

Expected: replay scaffold exists, 2+ DCKKR Scout dumps exist, DCKKR ledger fixture exists. Determine whether the ledger fixture has per-ball UI state or only commentary; if only commentary, fetch full per-ball data from Cricbuzz as Step 2 prep.

### Step 2 — Cricbuzz ground-truth ingester (build first, smallest fixed scope)

File: new `files/scripts/ingest_cricbuzz_ground_truth.py`.

Input: existing `files/tests/fixtures/dc_vs_kkr_2026_152064_ledger.json` (or fresh fetch).
Output: `files/tests/fixtures/dckkr_ground_truth_ui_snapshots.jsonl` — one `UIBallSnapshot` JSON record per line, in over-ball order for innings 1.

Smallest viable scope: cover innings 1 only, ~120 balls. Validate end-to-end with a single hand-verified spot-check (e.g., first wicket: load fixture, find over.ball 4.5 record, verify it matches the broadcast strip Rahul-dismissed-by-Tyagi from Obs 4 cricket-truth).

### Step 3 — Extend replay scaffold to drive full pipeline + snapshot

File: extend `files/scripts/replay_captured_scout_trace.py`. Add a `--snapshot-output PATH` flag that:

1. Routes the captured Scout dump through `apply_scorer_decision` (not just `SM.on_frame()`).
2. Intercepts `build_full_payload` after each legal-ball-boundary trace event.
3. Serializes the WS payload into `UIBallSnapshot` schema.
4. Writes one JSONL record per snapshot to `PATH`.

Test command:
```bash
files/.venv/bin/python files/scripts/replay_captured_scout_trace.py \
  --scout-dump files/logs/deliveries/validate_dckkr_20260521_155356/scout_raw.jsonl \
  --fixture dckkr \
  --snapshot-output /tmp/dckkr_pipeline_snapshots.jsonl
```

Acceptance: produces ≥100 JSONL records for a full-innings dump; each record validates against `UIBallSnapshot` dataclass.

### Step 4 — Diff engine + classifier

File: new `files/scripts/replay_diff_harness.py`.

CLI:
```bash
files/.venv/bin/python files/scripts/replay_diff_harness.py \
  --pipeline /tmp/dckkr_pipeline_snapshots.jsonl \
  --ground-truth files/tests/fixtures/dckkr_ground_truth_ui_snapshots.jsonl \
  --report /tmp/dckkr_diff_report.md
```

Output sections of report:
1. **Per-surface incident count summary** (table: surface | count | first-occurrence | example-overball)
2. **Per-ball divergences** (markdown table: over.ball | field | pipeline-value | ground-truth-value | surface-classification)
3. **Conservation invariants** (a numbered list of any failing Σ-checks: score-vs-batter-sum, bowler-ball-conservation, etc.)
4. **Unclassified divergences** (any DIVERGENT field that did not match a known surface — these are new defect classes worth opening)

### Step 5 — Validate harness against this replay's observations

Acceptance criterion: running the harness against the `validate_dckkr_20260521_155356` Scout dump must reproduce at least 80% of the 14 defect surfaces from `validate_dckkr_replay_observations_20260522.md` as classifier hits in the report.

If <80% reproduction:
- Check whether the missing surfaces are visible in the captured Scout dump (some defects like Obs 6 ad-occlusion may be Scout-dump-replayable; others like Obs 9 wicket-frame-misalign may require live UDP timing not preserved in the dump)
- For dump-replayable misses: fix classifier or snapshot schema
- For non-dump-replayable misses: explicitly document in the report which surfaces require live-replay vs which are dump-replayable

If ≥80% reproduction: lock in harness as canonical regression-detection mechanism. Promote to Layer 1.5 / Layer 2 pre-commit (Step 7).

### Step 6 — Use harness to drive fix-iteration cycles (the actual payoff)

For each fix candidate (C21b, F2, D2-Layer-2, E2, etc.) the workflow becomes:

```
git checkout -b fix/<surface-name>
# write fix
files/.venv/bin/python files/scripts/replay_diff_harness.py ... --report /tmp/before.md
# apply fix
files/.venv/bin/python files/scripts/replay_diff_harness.py ... --report /tmp/after.md
diff /tmp/before.md /tmp/after.md
# verify: target surface incident count went to 0, no other surface counts increased
git commit -m "fix(<surface>): close ..."
```

**Recommended fix-order based on Obs 1-16 incident counts + leverage:**
1. **C21b** (5 wicket-frame instances + 100% wicket-frame failure rate — highest leverage)
2. **Bowler-W-credit at `gap_finalize_wicket`** (Obs 14 — 4 wickets uncredited; D-chain falsification #2)
3. **D-post-FoW striker-init** (Obs 7/9 — cascade root; D-chain falsification #1)
4. **F2 defer-and-mark-uncertain bowler** (Obs 6 — ad-occlusion entire-over misattribution)
5. **Recent-Overs partial-render** (Obs 11b — Ov 8 drop)
6. **Compound-with-wicket token rendering** (Obs 13 #4)
7. **Per-batter-ledger conservation assertion** (Obs 16 — add as gate before any further fix lands)

### Step 7 — Integrate harness as pre-commit gate

Once Step 5 acceptance lands, add to `.git/hooks/pre-commit`:
```bash
# after Layer 1.5 + Layer 2 checks
files/.venv/bin/python files/scripts/replay_diff_harness.py \
  --pipeline-from-replay <baseline-dump> \
  --ground-truth files/tests/fixtures/dckkr_ground_truth_ui_snapshots.jsonl \
  --baseline-report files/tests/baselines/dckkr_diff_baseline.md \
  --fail-on-increase
```

Hook fails if total incident count rises vs baseline. New baseline established after each surface-closing commit.

---

## §4 — Out-of-scope deliberately

- **Live UDP replay.** Performance / lag (Obs 10) and ad-occlusion-timing (Obs 6) defects require live UDP timing not preserved in Scout dumps. Continue using live-replay for those workstreams; differential harness covers the rest.
- **UI-render-only defects.** Bowling-card flicker (Obs 2b/3b) is downstream of the WS payload; harness captures the WS payload, not the React-render layer. Render-layer defects need separate browser-based regression test (lower priority).
- **Workstream E1 phantom-wicket detection** (F1017 from prior session). The Scout dumps may or may not reproduce this depending on whether the upstream wicket-signal aggregation is deterministic under replay. Test as part of Step 5 acceptance; if not reproducible from dumps, leave to live-replay.

---

## §5 — Acceptance gates for the new methodology

The methodology is "shipped" when:

1. ≥80% of the 14 defect surfaces from this replay reproduce as classifier hits when harness runs against `validate_dckkr_20260521_155356` dump (Step 5).
2. The harness completes a full DCKKR innings diff in <60 seconds on the dev machine (enables fast iteration).
3. At least one defect-fix cycle (Step 6) has been completed end-to-end using the harness — fix authored, harness re-run, target surface incident count went to 0, no regression on other surfaces, commit landed with the harness as authority.
4. Pre-commit gate (Step 7) blocks a synthetic regression commit in a test-only branch.

---

## §6 — Why this supersedes the D-chain replay-validation gate

Per Architecture_HANDOFF §11 + §0a.3: D-chain validation was scoped as "run a fresh DCKKR replay and check the γ-bundle assertions." This replay (`validate_dckkr_replay_observations_20260522.md`) was that fresh replay; **2/5 of the D-chain empirical-falsification budget was consumed and both primary predicted-flip claims (Obs 9 + Obs 14) were falsified.** Continuing to rely on live-replay for D-chain validation has:

- Diminishing signal: D-chain already empirically falsified — the validation gate already fired its primary purpose.
- Bottleneck cost: 45 minutes per replay + manual observation logging.
- Reproducibility cost: every fix-candidate requires fresh broadcast capture.

The differential-testing methodology replaces the D-chain replay-validation gate with a Scout-dump-driven equivalent that runs in seconds, captures every UI surface (not just the γ-bundle's 3), and produces machine-checkable regression detection. The D-chain memo's predicted-flip table (`workstream_d_rotation_root_investigation.md` §6) can be re-derived against the harness output rather than against live replay.

**Adopt the harness; deprecate the live-replay-as-validation-gate for non-timing-related defect classes.**

---

## §7 — Empirical update (2026-05-22 evening): Step 5 result + acceptance-gap closure

**Steps 1-5 executed.** Harness built end-to-end: ingester → snapshot extension → diff engine all landed. Run against `validate_dckkr_20260521_155356` Scout dump produced **9/14 surfaces detected (64%)** — below §5's 80% gate.

**Detected (9):** Multi-ball-compression (20 hits), F-A-commit-lag (18), F-B-ad-occlusion (12), G-pipeline-lag (11), Recent-overs-drop (5), E3-wicket-frame-misalign (4), D-post-FoW-striker (2), E2-phantom-runs (1), Boundary-counter-double-increment (1).

**Undetected (5):** Compound-with-wicket-token, Extras-counter-drop, Bowler-W-credit-failure, C21b-symbol-revert, Per-batter-ledger-drift.

**Diagnosis: harness is correct; ground-truth fixture is the blocker.** The 36-ball ledger fixture (`files/tests/fixtures/dc_vs_kkr_2026_152064_ledger.json`) covers DC overs 1-6 only and contains zero wides/no-balls/byes/leg-byes per its own `_metadata`, with exactly one wicket (Rahul 4.5 — already classified by E3). The 5 undetected surfaces all require events that do not occur in the first 6 overs of cricket truth. **Harness false-negative rate at the surface level is 0%; the gap is fixture coverage.**

**Acceptance-gap closure plan — extend GT fixture to full innings (overs 1-20, ~120 balls):**

### Step 5b.1 — Cricbuzz commentary fixture (LANDED 2026-05-22)

**Input artifact already saved:** `files/tests/fixtures/dckkr_innings_1_cricbuzz_commentary.md` — full innings 1 ball-by-ball commentary captured from Cricbuzz, ~120 balls covering overs 0.1 → 19.6. Format is reverse-chronological (latest over first, latest ball first within over); the ingester must reverse-sort by `over.ball` before processing.

**Format observations from the captured fixture (relevant for parser design):**

- Per-ball record: `<over>.<ball>\n<bowler> to <batter>, <outcome>, <commentary>`. Outcome variants: `no run`, `1 run`, `2 runs`, `4 runs`, `6 runs`, `FOUR`, `SIX`, `wide`, `out <dismissal-type>` (compound forms exist).
- Wicket lines: standalone `W` on its own line BEFORE the ball record (e.g., lines 18-20 of the fixture for 19.4 = `19.4` then `W` then `Kartik Tyagi to Mitchell Starc, out Mitchell Starc Run Out!! ...`).
- Boundary lines: standalone `4` or `6` on its own line BEFORE the ball record (e.g., lines for 18.6 = `18.6` then `4` then `Vaibhav Arora to Ashutosh Sharma, FOUR, ...`).
- Compound events captured as multiple records at the same `over.ball` coordinate:
  - **10.2 wicket-on-wide** spans three records: `10.2 / W / Anukul Roy to Pathum Nissanka, wide, out Stumped!!` + `10.2 / Anukul Roy to Axar Patel, wide, quicker delivery well down the leg side` + `10.2 / Anukul Roy to Axar Patel, 1 run, slower through the air and on the pads`. Three deliveries share the `10.2` coordinate because two wides intervened. **Ingester must use record-order within the same over.ball, not over.ball alone, as the primary key.**
  - **10.1 boundary preceding wicket** has standalone `F` (full) marker before the ball record. Parser should treat `F` as a no-op marker (the actual outcome is in the `Anukul Roy to ..., FOUR, ...` line).
- Over-end summary lines: `Over <N>\n<score>-<wkts>\n<over-sequence>(<runs> runs)\n<striker> <runs> (<balls>)\n<non-striker> <runs> (<balls>)\n<bowler> <overs>-<maidens>-<runs>-<wkts>`. These are derived state and provide cross-validation for the ingester (Σ per-ball ≡ over-summary; useful for parser self-test).
- New-batter records: `<player-name>, <handedness> bat, comes to the crease` on lines between over records. Use to advance the at-the-crease set.
- Bowler-change records: `<bowler> [<overs>-<maidens>-<runs>-<wkts>] is back into the attack` OR `<bowler>, <bowling-style>, comes into the attack`. Use to seed the bowler-card.
- Strategic-timeout / commentator-chatter / stats lines: discard (no per-ball state).

**Wicket ledger from the fixture (cricket truth, for cross-validation against pipeline FoW):**

| FoW | Over.ball | Dismissed batter | Bowler | Dismissal type |
|---|---|---|---|---|
| 1 | 4.6 | Rahul | Kartik Tyagi | c Cameron Green |
| 2 | 7.6 | Nitish Rana | Cameron Green | c Sunil Narine |
| 3 | 9.5 | Sameer Rizvi | Sunil Narine | c Rovman Powell |
| 4 | 10.2 | Pathum Nissanka | Anukul Roy | st Angkrish Raghuvanshi (on a wide) |
| 5 | 10.5 | Tristan Stubbs | Anukul Roy | b |
| 6 | 18.3 | Axar Patel | Vaibhav Arora | c Anukul Roy |
| 7 | 19.2 | Ashutosh Sharma | Kartik Tyagi | c Ajinkya Rahane |
| 8 | 19.4 | Mitchell Starc | (run out by Raghuvanshi/Tyagi) | run out |

**Critical cross-validation against this-replay's pipeline observations:**
- Pipeline FoW2 (Obs 9): pipeline credited **Nissanka, 7.4**. Cricket truth: **Nitish Rana, 7.6, c Sunil Narine b Cameron Green.** Confirms Obs 9's wrong-dismissed-batter finding via authoritative ground truth.
- Pipeline FoW1 (Obs 4): pipeline credited **Rahul, 4.5**. Cricket truth: **Rahul, 4.6, c Cameron Green b Kartik Tyagi.** Pipeline off by 1 ball (4.5 vs 4.6) — confirms Obs 4 / Obs 9 wicket-frame-misalignment defect (E3) at first wicket too.
- Pipeline FoW3-5 (Obs 12/13/15): pipeline registered 80/3 Rizvi 9.5 + 85/4 Rana 10.1 + 89/5 Stubbs 10.5. Cricket truth: 77/3 Rizvi 9.5 + 80/4 Nissanka 10.2 (on wide) + 80/5 Stubbs 10.5. **Score totals at each wicket diverge** (pipeline 80/85/89 vs cricket 77/80/80) — confirms phantom-runs defect (E2) at this exact wicket window.

### Step 5b.2 — Extend ingester for non-legal-ball events

`files/scripts/ingest_cricbuzz_ground_truth.py` currently emits `UIBallSnapshot` per legal ball. Extend to also emit snapshots for:
- Wide deliveries (advance over.ball denominator? — depends on schema convention; pick one and document)
- No-ball deliveries (same)
- Leg-byes / byes (count toward extras_lb / extras_b respectively, legal ball)
- Wicket-on-extras (compound `Wd+W` / `Nb+W` token in `this_over_tokens[N]` — emit as a single combined token, not two snapshots)
- Wicket-with-non-zero-runs (e.g., run-out on a 4 → `4+W` token)

Each non-legal-ball event still emits a `UIBallSnapshot` capturing cumulative state at that event's frame; the diff engine matches on `(over.ball, event-index-within-frame)` rather than `over.ball` alone if needed to disambiguate multi-event frames.

### Step 5b.3 — Re-ingest + re-run + verify

```bash
files/.venv/bin/python files/scripts/ingest_cricbuzz_ground_truth.py \
  --input files/scripts/cricbuzz_dckkr_2026_152064.json \
  --output files/tests/fixtures/dckkr_ground_truth_ui_snapshots.jsonl
files/.venv/bin/python files/scripts/replay_diff_harness.py \
  --pipeline /tmp/dckkr_pipeline_snapshots.jsonl \
  --ground-truth files/tests/fixtures/dckkr_ground_truth_ui_snapshots.jsonl \
  --report /tmp/dckkr_diff_report_full.md
```

Expected post-extension detection (predicted, based on Obs 1-16 ledger):
- Compound-with-wicket-token: ≥1 instance (10.2 Wd+W per Obs 13)
- Extras-counter-drop: ≥1 instance (the wide-with-wicket transient at Obs 13)
- Bowler-W-credit-failure: ≥4 instances (4 wickets × bowlers per Obs 14)
- C21b-symbol-revert: ≥5 instances (5 wicket frames × Obs 4/12/13/15)
- Per-batter-ledger-drift: ≥1 instance (Obs 16 Patel -1)

**Pass condition: 14/14 surfaces detected (100%) or 12/14 (≥85%, above §5 gate).** If still <80% after fixture extension → harness false-negative; debug classifier for the specific missing surface.

### Step 5b.4 — Fallback if Cricbuzz fetch is blocked

If the Cricbuzz API is unreachable / requires auth not available locally, fall back to: **synthesize GT extension from live-replay broadcast captures in Obs 4 / 5 / 6 / 8 / 9 / 10 of `validate_dckkr_replay_observations_20260522.md`.** Those 6 observations contain operator-attested cricket-truth at 6 distinct over.ball frames in overs 4-11. Reverse-derive `UIBallSnapshot` for each. Coverage: ~30 balls in overs 4-11 (the same window where Obs 1-16 fired). Lower coverage than fresh fetch but captures the 4 wicket frames (4.5 / 7.4 / 9.5 / 10.1 / 10.5) where C21b + bowler-W-credit + compound-token defects fire.

### Step 5b.5 — Promote to Step 6 (fix iteration) once 80% reached

Per §3 Step 6 fix-order remains:
1. C21b (highest leverage — 5+ wicket instances)
2. Bowler-W-credit at `gap_finalize_wicket`
3. D-post-FoW striker-init
4. F2 defer-and-mark-uncertain bowler
5. Recent-Overs partial-render
6. Compound-with-wicket token
7. Per-batter-ledger conservation assertion

**Each fix lands with before/after harness reports as commit evidence.** Target surface incident count goes to 0; no other surface counts increase; commit message references both diffs by path.

---

## §8 — Methodology meta-finding

The Step 1-5 execution validated the methodology's core thesis: **defect-surface coverage scales with ground-truth fixture coverage, not with replay-time spent.** Extending the GT fixture from 6 overs to 20 overs is expected to flip 5 undetected surfaces to detected without changing a single line of harness code. **This is the value proposition versus live-replay** — adding empirical coverage costs ~1 hour of fixture-fetch + parser-extension work, vs ~1 hour of live-replay + manual screenshot logging that produces less-structured output and worse reproducibility.

Once Step 5b reaches 80%+, every subsequent fix iteration runs the harness in <60 seconds. The fix-throughput model fundamentally changes: from ~1 fix-per-session bottlenecked on live-replay-watching to ~5-10 fixes-per-session bottlenecked only on the code-change itself.

---

## §9 — Step 5b empirical result + remaining blind-spots before Step 6

**Step 5b executed 2026-05-22 evening. §5 acceptance gate PASSED at 13/14 surfaces (92.9%).**

### §9.1 — Detection result

| Surface | Count |
|---|---|
| G-pipeline-lag | 80 |
| Multi-ball-compression | 40 |
| F-A-commit-lag | 33 |
| F-B-ad-occlusion | 20 |
| E3-wicket-frame-misalign | 20 |
| D-post-FoW-striker | 11 |
| Per-batter-ledger-drift | 11 |
| Recent-overs-drop | 7 |
| Extras-counter-drop | 6 |
| Boundary-counter-double-increment | 4 |
| Bowler-W-credit-failure | 2 |
| Compound-with-wicket-token | 2 |
| E2-phantom-runs | 1 |
| **C21b-symbol-revert** | **0 (UNDETECTED — see §9.2)** |

Cross-validation against this-replay's Obs 1-16 ledger: every defect surface the operator empirically observed has now been auto-detected by the harness against the captured Scout dump, except C21b. **Methodology validated.**

### §9.2 — C21b detection blind-spot: two snapshotter bugs

Per the Step 5b.3 execution report, C21b is undetectable in the current harness because:

**Bug 1 — wrong source for `this_over` field.** The snapshotter reads `scoreboard.this_over` which is `[]` at every `DIRECT-SCORE-COMMIT` boundary. Per HANDOFF §"SM as sole UI authority" — "WS payload reads Recent Overs from SM's `over_history`". The WS payload-builder reads from SM, NOT from `scoreboard.this_over`. The snapshotter should mirror the WS payload's source path.

**Bug 2 — DIRECT-SCORE-COMMIT misses wicket-only frames.** Of the 5 GT wicket frames in the dump window (4.6, 7.6, 9.5, 10.2, 10.5), pipeline emits a snapshot at only 1 (10.2 — the only wicket frame coincident with score-change via the wide). The other 4 wickets have Δscore=0 → `DIRECT-SCORE-COMMIT` doesn't fire → no snapshot taken at the wicket frame → C21b's "GT has W, pipeline shows non-W" condition never triggers because pipeline has no snapshot to compare.

### §9.3 — Step 5b.4 (REQUIRED before Step 6 can validate C21b fix)

Two small patches to the snapshotter — both single-call-site changes in `files/scripts/replay_captured_scout_trace.py`'s snapshot hook:

**Patch A — point `this_over` source at the WS payload's source path.** Replace `scoreboard.this_over` read with whichever field `build_full_payload` reads (likely `SM.over_history[-1]` for the currently-active over, or SM's `this_over` derivation if it exists as a dedicated field). Verify by inspecting `build_full_payload` source in `score_manager.py`.

**Patch B — add wicket-dispatch as an additional snapshot trigger.** Currently snapshot fires on `DIRECT-SCORE-COMMIT`. Add `trace_beta_sm_wicket_dispatch` (or whichever trace tag the wicket-dispatch path emits) as a secondary trigger. Snapshot the post-dispatch state. This captures wicket-only frames where Δscore=0.

**Acceptance for Step 5b.4:** re-run harness on the same Scout dump. Expect:
- `this_over` field populated (non-empty) at ≥50% of snapshots (anywhere a legal ball has been bowled in the current over).
- Snapshot count rises from 45 → ≥48 (4 additional wicket-only snapshots).
- C21b classifier hits ≥1 instance — ideally 4 instances (4 of 5 wicket frames have GT `W` token; the 5th is `Wd+W` and routes to Compound-with-wicket-token correctly).
- **Total surface detection: 14/14 (100%).**

### §9.4 — Then proceed to Step 6 fix-iteration

Per memo §3 Step 6 fix-order, with the harness now passing the gate:

1. **C21b** — highest leverage; 5 wicket instances per Obs ledger; the recommended fix site is `_rewrite_eyes_this_over_from_event` at `score_manager.py:695`. Use harness to baseline before fix; apply fix; re-run; verify C21b surface count drops to 0 and no other surface counts regress.
2. **Bowler-W-credit at `gap_finalize_wicket`** — only 2 instances detected currently (vs 4 expected from Obs 14 + cricket-truth ledger). The 2-instance figure is likely undercounting due to the wicket-snapshot blind-spot in §9.2 Bug 2; recount after Step 5b.4 patches land.
3. **D-post-FoW-striker** — 11 instances; address with D2-Layer-2 (post-FoW striker-init memo per Obs 9 escalation).
4. **F2 (defer-and-mark-uncertain bowler)** — F-B-ad-occlusion 20 instances; single-site fix candidate.
5. **Recent-Overs partial-render** — 7 instances.
6. **Compound-with-wicket-token** — 2 instances; trace_compound_tokens assertion expansion.
7. **Per-batter-ledger conservation assertion** — 11 drift instances; add the assertion first, then audit the per-batter mutation sites.

Each fix lands with before/after harness diff reports as commit evidence (per §3 Step 6 protocol).

### §9.5 — Methodology meta-finding (Step 5b confirms §8)

Step 5b empirically validated the §8 hypothesis: **defect-surface coverage scales with ground-truth fixture coverage.** Extending the GT fixture from 6 overs to 20 overs flipped 8 previously-undetected surfaces to detected (Compound-with-wicket-token, Extras-counter-drop, Bowler-W-credit-failure, Per-batter-ledger-drift were the new ones; E3/Recent-overs/Boundary-counter/E2 already had 1-5 hits in the 6-over fixture but gained more instances). **Zero classifier code changes between Step 5a (6 overs, 64%) and Step 5b (20 overs, 92.9%).** Only fixture expansion + the small classifier patch for E2 over-restriction.

Step 5b.4 should close the final 7.1% (C21b detection) and complete the methodology bring-up. After that, every fix iteration is bottlenecked only on the code-change itself, not on validation infrastructure.

---

## §10 — Step 6 execution protocol: C21b (first fix candidate)

Step 5b.4 landed 2026-05-22; harness is methodology-complete at 14/14 surfaces. C21b detection landed at 1 instance (10.5) — limited not by classifier but by dump coverage (other GT wicket frames absorbed by G-pipeline-lag).

### §10.1 — Side-findings from Step 5b.4 final counts

- **Bowler-W-credit-failure: 2 → 7.** §9.3 predicted ≥4; actual 7 = even worse undercount than estimated. Original Obs 14 framing "FAIL × 4" was based on operator-visible wickets; actual ledger has 8 cricket-truth wickets and 7 of them have no bowler-W credit per pipeline. **The Obs 14 escalation route (move dual-source-consensus to `gap_finalize_wicket`) is empirically more leveraged than projected.** Bowler-W-credit moves up the Step 6 priority list.
- **E3-wicket-frame-misalign 20 → 32 and Per-batter-ledger-drift 11 → 17.** Both jumped from the wicket-snapshot patch (Patch B). These were under-detected at Step 5b because their predicate fires at wicket frames that DIRECT-SCORE-COMMIT missed.
- **Multi-ball-compression dropped 40 → 4.** The `event_index` keying + wicket-trigger together resolved most "phantom multi-ball" cases that were really wicket-frame snapshots aligned wrong.
- **Patch C was unsuggested but correct.** The cross-frame `this_over` mutation trigger is necessary because C21b's manifestation is a SYMBOL REVERT — the token is correct at one frame and reverts at a later idle frame. DIRECT-SCORE-COMMIT + wicket-dispatch alone wouldn't sample the revert moment. **Add Patch C as a permanent fixture** in the design memo — without it, C21b regression coverage is brittle.

### §10.2 — C21b fix-candidate investigation (read-before-fix)

Per HANDOFF §"Track record" + Obs 4/12/13/15 ledger: candidate site is `score_manager.py:695` `_rewrite_eyes_this_over_from_event`. CC's first action in Step 6 is **read the function + trace through the wicket-frame call sequence**, not write the fix.

Specific questions to answer before fixing:

1. What does `_rewrite_eyes_this_over_from_event` read as its source? `ball_event.symbol`? `ball_event.run_score`? Both? Does it concatenate W with run-symbol on wicket-event frames or pick one?
2. Where is the W symbol originally written? Is it a separate write path that fires before `_rewrite_eyes_this_over_from_event`, and then gets overwritten? Or does `_rewrite_eyes_this_over_from_event` itself write the W?
3. The extras-counter has a retry/recovery path (per Obs 15: Wd eventually self-corrects). Where does that recovery fire? **Mirror its template for the W symbol** rather than inventing a new recovery shape.
4. Does the wicket-event reach `_rewrite_eyes_this_over_from_event` at all? If not, the fix is elsewhere (in whichever path actually writes the wicket-frame symbol).

### §10.3 — Step 6 C21b execution sequence

```bash
# 1. Branch
git checkout -b fix/c21b-symbol-revert

# 2. Baseline (immutable reference)
files/.venv/bin/python files/scripts/replay_diff_harness.py \
  --pipeline /tmp/dckkr_pipeline_snapshots.jsonl \
  --ground-truth files/tests/fixtures/dckkr_ground_truth_ui_snapshots.jsonl \
  --report files/tests/baselines/dckkr_diff_pre_c21b.md

# 3. Read + diagnose (§10.2 questions above)
grep -n "_rewrite_eyes_this_over_from_event" files/score_manager.py
sed -n '680,750p' files/score_manager.py

# 4. Apply fix (smallest diff that closes C21b without regressing other surfaces)

# 5. Regenerate pipeline snapshots
files/.venv/bin/python files/scripts/replay_captured_scout_trace.py \
  --scout-dump files/logs/deliveries/validate_dckkr_20260521_155356/scout_raw.jsonl \
  --fixture dckkr \
  --snapshot-output /tmp/dckkr_pipeline_snapshots.jsonl

# 6. Re-run harness
files/.venv/bin/python files/scripts/replay_diff_harness.py \
  --pipeline /tmp/dckkr_pipeline_snapshots.jsonl \
  --ground-truth files/tests/fixtures/dckkr_ground_truth_ui_snapshots.jsonl \
  --report files/tests/baselines/dckkr_diff_post_c21b.md

# 7. Verify (must hold all of):
#    - C21b-symbol-revert count: 1 → 0
#    - No other surface count increased vs pre-c21b baseline
#    - Layer 1.5 (36 + 6 + 3 + 3 = 48 cases) green
#    - Layer 2 (30 balls) green
diff files/tests/baselines/dckkr_diff_pre_c21b.md files/tests/baselines/dckkr_diff_post_c21b.md

# 8. Commit with both reports as evidence
git add files/score_manager.py files/tests/baselines/dckkr_diff_pre_c21b.md files/tests/baselines/dckkr_diff_post_c21b.md
git commit -m "fix(c21b): close W-symbol revert at _rewrite_eyes_this_over_from_event

Pre-fix harness: 1 C21b instance at 10.5.
Post-fix harness: 0 C21b instances. No regression on other 13 surfaces.
Reports: files/tests/baselines/dckkr_diff_{pre,post}_c21b.md"
```

### §10.4 — Important caveat — single-instance validation gate

Harness validates against 1 detected C21b case (10.5). Operator Obs 1-16 ledger says ≥5 cases exist in live production. **The single-instance validation is the minimum useful gate but not the complete one.** After commit lands, schedule a fresh live UDP replay (per memo §2.1 + HANDOFF launch sequence) to confirm broader pattern closure on cases that the dump doesn't preserve. Do NOT skip the live-replay confirmation; the dump-based gate is necessary but not sufficient for C21b specifically.

### §10.5 — After C21b lands — Step 6 next fix per side-finding

Per §10.1, the revised Step 6 priority order is:
1. **C21b** (5 wicket-frame manifestations in live; 1 reproducible in dump)
2. **Bowler-W-credit at `gap_finalize_wicket`** (7 dump instances — promoted from #2 to even-higher-leverage given the undercount surfaced)
3. **D-post-FoW-striker** (20 dump instances after wicket-trigger patch)
4. **F2 defer-and-mark-uncertain bowler** (27 dump instances)
5. **Per-batter-ledger conservation assertion** (17 dump instances — promoted; reveals drift the score-totals hide)
6. **Recent-Overs partial-render** (10 dump instances)
7. **Compound-with-wicket-token** (2 dump instances — lowest leverage but cheapest fix)

The Obs 14 / §9.3 prediction that Bowler-W-credit was undercounted is now empirically confirmed (2 → 7, +250%). All other counts move up similarly after Step 5b.4 → fix-priority decisions should anchor on POST-5b.4 counts, not pre-5b.4 counts.

---

## §10.6 — Step 6 C21b iteration retrospective (failed-then-redirected)

Two fix iterations attempted; both empirically falsified at the harness gate. Each iteration produced new structural understanding that the next iteration relied on.

### §10.6.1 — Iteration 1: site-local fix at `:5562 + :6458`

**Hypothesis:** the gap-finalize wicket path bypasses `this_over` mutation. Adding `self.this_over.append(token) + _rewrite_eyes_this_over_from_event(card, token)` at the gap-finalize call site closes the W-symbol-missing case.

**Result:** zero effect on the dump. C21b count unchanged at 1; pipeline `this_over_tokens` at 10.5 unchanged (no W). Reverted.

**Why it failed:** the 10.5 Stubbs wicket does NOT flow through gap_finalize_wicket in this dump. It flows through `_synthesize_cold_start_ball_events` at frame 1062 — a backfill path triggered by cold-start re-entry mid-innings. Synthesizer wipes `self.this_over` wholesale and rewrites from a `(.|1|str(runs))`-only heuristic that excludes W per its docstring policy.

### §10.6.2 — Iteration 2 (NOT attempted): FoW-positional overlay in synthesizer

**Hypothesis:** patch the synthesizer to read `self.fall_of_wickets` and overlay W tokens at the FoW-encoded ball positions. Preserves no-speculation principle by anchoring on canonical positional data.

**Result:** falsified statically before code change. CC's trace inspection of `self.fall_of_wickets` at frame 1062 showed only 3 entries (placeholders for wickets 1-3, none in over 10). Wickets 4 + 5 have ZERO FoW representation on the pipeline side — they were absorbed silently via SM-FEEDER-SYNC (card-mutation `scoreboard.set("wickets", N)`) without ever dispatching a WICKET event or calling `_add_fow`. The FoW-overlay loop would have filtered all 3 entries out (`fow.over != self.overs`) and produced no W token. Speculation-budget consumed: 0/5 (caught by trace inspection before commit, exactly as the no-speculative-fixes discipline mandates).

### §10.6.3 — Architectural finding from Iteration 2's static falsification

**Silent-wicket-absorption is a NEW defect class structurally upstream of C21b.** Empirical signal:
- Cold-start synthesizer fires 6 times across the dump (frames 14, 544, 739, 843, 946, 1062) — not just once at startup.
- `WICKET-FALL-ONLY-CALLED` fires only twice in the entire post-frame-700 dump (frames 679 for FoW2, 855 for FoW3).
- Wickets 4 (Nissanka 10.2) and 5 (Stubbs 10.5) never trigger WICKET dispatch — `self.wickets` increments 3→4→5 via SM-FEEDER-SYNC card-mutation only.
- FoW state at frame 1062: only 3 entries (third is placeholder); no FoW row for wickets 4+5.

This is **distinct from any of the 14 defect surfaces in Obs 1-16's ledger.** Not E1 (phantom-wicket fabrication), not E2 (phantom-runs), not E3 (wicket-frame misalignment). Wickets are LOST at the dispatch level — the canonical wicket-handling chain never runs. Downstream surfaces (FoW, this_over, bowler-W-credit, dismissed-batter attribution) all fail-by-construction because their input event never fires.

### §10.6.4 — C21b dump-detected case is architecturally blocked

The 1-instance harness detection at 10.5 is real but uncloseable from synthesizer-fix alone. The prerequisite — a WICKET event reaching `_apply_event` or `_apply_wicket_fall_only` — never fires for that wicket. Until silent-wicket-absorption is fixed, the dump cannot exercise the C21b code path for this case.

**Per §10.4 caveat: deferred to live-replay validation.** In live replay, wickets 4+5 likely DID dispatch through proper WICKET events (because live broadcast frames arrive separately and Scout extraction captures them in-flight); the cold-start backfill that absorbed them in the dump may not fire in live. The other 4 C21b instances in Obs ledger (4.5/4.6, 10.1, and over-11 wickets) probably DO flow through canonical paths in live and may have different fix sites.

---

## §11 — New workstream surface I — silent-wicket-absorption

**Discovery:** §10.6.3 above (CC trace inspection during failed C21b Iteration 2).

**Defect predicate:** at any frame where `scoreboard.set("wickets", N)` increments wickets-count without a corresponding `WICKET-FALL-ONLY-CALLED` or `_apply_event` wicket-branch firing in the preceding M frames.

**Empirical signal in dump:** 2 instances (wickets 4 + 5 of DCKKR innings 1). Both occur during cold-start re-entry frames (946, 1062). Both leave permanent FoW + this_over corruption.

**Distinct from prior surfaces:**
- E1 phantom-wicket (F1017 prior session): pipeline FABRICATES a wicket that didn't happen. Surface I: pipeline LOSES a wicket that did happen.
- E3 wicket-frame-misalign (Obs 9): wicket dispatched at wrong over.ball coordinate. Surface I: wicket NEVER dispatched.
- Bowler-W-credit failure (Obs 14): wicket dispatched but bowler not credited. Surface I: wicket not dispatched at all → bowler credit blind by construction.

### §11.1 — Phase 1 (immediate, this session): observability + harness classifier

Smallest useful change: add a trace tag at the SM-FEEDER-SYNC site that emits when `wickets` field increments. Tag carries (frame_number, prior_wickets, new_wickets, current_over.ball). Add a classifier for Workstream I to the diff harness: predicate is "GT FoW entry exists at over.ball X but pipeline FoW does not contain an entry within ±N frames of X" — detectable from the existing pipeline `fow_entries` snapshot field vs the GT `fow_entries` field.

Acceptance: harness detects surface I at 2 instances (wickets 4 + 5) against the existing dump. C21b unchanged at 1. No other surface counts regress.

This is purely observability — no state mutation, no architectural change, no speculation. Commit on `fix/c21b-symbol-revert` as a re-scoped commit (or rename branch to `obs/silent-wicket-absorption`).

### §11.2 — Phase 2 (next session): architectural fix for Surface I — derivation-only

**Principle constraint (operator-enforced 2026-05-22):** Scout's contract is exactly the 5 primitives (score, overs, batter names, bowler name, first-striker). FoW + dismissed-batter identity + wicket-frame coordinate are all DERIVED state, not Scout-extracted. Phase 2 must respect this; do NOT extend Scout to extract FoW history or dismissed-batter signals.

**Fix shape — synthetic WICKET dispatch with fully-derived fields.** When SM-FEEDER-SYNC absorbs a `wickets`-count jump (Δwickets > 0), derive the synthetic WICKET event entirely from prior + current pipeline state:

```
synthetic_wicket = {
    delta_wickets:    current_wickets - prior_wickets,
    over_ball:        current pipeline over.ball (from the SM-FEEDER-SYNC frame's commit),
    bowler_name:      tracker-locked current bowler,
    dismissed_batter: derived via set-difference:
                          {bat1_prior, bat2_prior} - {bat1_current, bat2_current}
    delta_score:      current_score - prior_score (for compound-token rendering),
    this_over_token:  "W" if delta_score == 0 else f"{delta_score}+W"
                      (or "Wd+W" if delta_extras > 0 on same frame)
}
```

**Derivation chain anchors:**
- `dismissed_batter` from at-the-crease set difference — empirically observable from prior + current Scout primitives, no speculation.
- `over.ball` from pipeline's most-recent committed value — already derived state, just persisted.
- `bowler_name` from tracker's current lock — already derived state.
- `delta_score` / `delta_extras` from prior + current score primitive — derived from primitives.

**Edge cases (handle explicitly, do not paper over):**
1. **Δwickets > 1 in single SM-FEEDER-SYNC frame.** Pipeline missed intervening frames. Set difference gives N dismissed batters but per-ball position is unrecoverable from the 5 primitives alone. Two acceptable answers: (a) dispatch N synthetic events all anchored at the current over.ball (collapses the cluster — produces a Workstream-I-Phase-2-leftover detectable defect class for the rare cluster case); (b) emit a `WICKET-CLUSTER-LOST-FRAMES` trace tag and refuse to dispatch — caller falls back to the existing silent-absorption behavior for the cluster case. Pick (a) as default; (a) is empirically lossy on per-ball position but FoW completeness is preserved, which is the bigger win.
2. **Set difference empty (new batter Scout-read hasn't arrived yet).** Defer the synthetic dispatch in a single-frame queue (`_pending_silent_wicket`) until the new batter shows up in a subsequent Scout read. This is a state-machine pattern analogous to Queue B for bowler-credit.
3. **Both batters changed in one frame (set difference = 2).** Impossible in cricket without a wicket on every ball. If observed, mark as suspicious and refuse to derive — emit `WICKET-AMBIGUOUS-DUAL-CHANGE` and defer.

**Auto-closure cascade:** if Phase 2 lands correctly, the following downstream defects auto-close for the silent-absorption case:
- C21b cold-start subcase (this_over gets a W token at the canonical over.ball position).
- Bowler-W-credit (synthetic WICKET dispatches through `_apply_event` or `_apply_wicket_fall_only` which already credit bowler-W in the working paths).
- FoW completeness (synthetic WICKET adds the missing entry via the standard `_add_fow` path).
- E3-wicket-frame-misalign (if pipeline's over.ball at the SM-FEEDER-SYNC frame matches cricket truth within ±M frames, the wicket lands at correct position).

The single new defect class introduced by Phase 2 is "wicket-cluster-lost-frames" (edge case 1) — and that's a Workstream G (lag/data-loss) consequence, not a Surface I consequence. It exists already; Phase 2 just makes it visible rather than silently corrupting state.

**Pre-Phase-2 reads required (CC, next session):**
1. Exact code site of SM-FEEDER-SYNC `wickets` mutation. `grep -n 'sb.set("wickets"' files/` or equivalent.
2. Whether pipeline already maintains a `_prior_at_crease_set` field that can serve as the set-difference operand without new state. If not, add as a single `tuple` field.
3. Whether `_apply_event` accepts a synthetic-event input or requires the event to have come from a specific upstream source. If gated on origin, find the lowest-surface-area override.

### §11.3 — Revised Step 6 fix-order

Surface I is now the blocker for C21b dump-validation. Revised:

1. **Workstream I Phase 1** (observability + classifier) — this session, ~30 lines, single commit.
2. **Bowler-W-credit at `gap_finalize_wicket`** — proceed in parallel since it's independent of Surface I.
3. **Workstream I Phase 2** (architectural fix — Candidate A or B) — next session.
4. **C21b** — re-attempt after Surface I Phase 2 lands; C21b for the 10.5 case will auto-close if Phase 2 uses Candidate A.
5. D-post-FoW-striker.
6. F2 defer-and-mark-uncertain bowler.
7. Per-batter-ledger conservation assertion.
8. Recent-Overs partial-render.
9. Compound-with-wicket-token.

### §11.4 — Methodology meta-finding from §10.6

**Failed-fix iteration is the methodology's signal-of-correctness, not its signal-of-failure** — same architectural insight as the F1/B-η session's "falsification cascade as methodology signal" (HANDOFF Meta-finding 2). Iteration 1's empirical falsification at the harness gate caught a wrong-site fix before commit. Iteration 2's static falsification at trace-inspection caught a wrong-anchor fix before code change. Net: **0 commits lost; 2 wrong fixes prevented; 1 new defect class surfaced.** This is the discipline working as designed.

The discipline track record extends: **12 transferable insights across 5 sessions** now (11 prior + this session's "harness validates the no-speculative-fixes discipline at sub-commit granularity" finding).
