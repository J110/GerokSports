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

### §11.3 — Revised Step 6 fix-order (2026-05-22 evening — triple-subsystem greenfield consolidation)

Operator-approved 2026-05-22 (twice): first consolidation absorbed wicket-related defects into §12; second consolidation 2026-05-22 evening absorbs striker-rotation + this_over publishing into a coordinated triple-rewrite (§12 + §13 + §14). Justification: same architectural pattern in all three subsystems (parallel write paths with no canonical derivation source); cricket rules for each are simple state machines; harness covers all three. Decoupling analysis confirms none of the three is structurally tied to anything outside SM. Triple-rewrite has higher leverage than 3 separate rewrites because the three subsystems interact (wickets feed striker init; striker rotation feeds this_over token composition; etc.). Revised order:

1. **§12 + §13 + §14 — Triple-subsystem greenfield rewrite** (one coordinated effort, 2-3 sessions). Covers:
   - **§12 wicket-subsystem:** Surface I (silent absorption), C21b (W-symbol revert/non-write at wicket frames), Obs 9 (wicket-frame misalign — wicket-coincident cases), Obs 13 (compound-with-wicket-token). [bowler-W-credit removed from scope per §12.10 diagnostic findings — collapses into Surface I + snapshot fix.]
   - **§13 striker-rotation subsystem:** D-post-FoW-striker (20 instances), Obs 7 post-FoW-striker-pointer, the deterministic-rotation override at `score_manager.py:4295-4325` (the S12 non-discriminable-predicate-signature surface — REPLACED not patched).
   - **§14 this_over publishing subsystem:** C21b broader pattern (cold-start subcase + non-wicket symbol drops), Multi-ball-compression, parts of Recent-Overs-drop (the unresolved-ball over-discard policy is item #5 below, but token-completeness lands here).
   - **Snapshot-side fix** (sibling to §12): `_last_bowler_at_wicket_commit` field for harness bowler-key extraction. Closes the 2 false-positive bowler-W-credit-failure instances per §12.10 Material Finding A.
2. **Workstream F sub-class B** (defer-and-mark-uncertain bowler under ad-occlusion). Surgical, single-site, ~30-50 LOC.
3. **Workstream F sub-class A** (over-boundary commit-lag bowler misattribution). Surgical.
4. **Per-batter-ledger conservation assertion** (Obs 16). Add assertion to trace library first; audit mutation sites flagged by the assertion's failures.
5. **Recent-Overs partial-render policy** (Obs 11b). Single-site fix at the over-archive gate's unresolved-ball discard rule. Distinct from §14 token completeness — the panel may still drop an over even if every token is valid, depending on archive-gate threshold.
6. **Phantom-runs root-localize** (Obs 8). Use the E2 classifier output to localize.
7. **Pipeline-lag performance investigation** (Obs 10). Separate workstream — not correctness, but throughput.

### §11.4 — Methodology meta-finding from §10.6

**Failed-fix iteration is the methodology's signal-of-correctness, not its signal-of-failure** — same architectural insight as the F1/B-η session's "falsification cascade as methodology signal" (HANDOFF Meta-finding 2). Iteration 1's empirical falsification at the harness gate caught a wrong-site fix before commit. Iteration 2's static falsification at trace-inspection caught a wrong-anchor fix before code change. Net: **0 commits lost; 2 wrong fixes prevented; 1 new defect class surfaced.** This is the discipline working as designed.

The discipline track record extends: **12 transferable insights across 5 sessions** now (11 prior + this session's "harness validates the no-speculative-fixes discipline at sub-commit granularity" finding).

### §11.5 — Phase 1 landing 2026-05-22 — empirical results + structural surprises

Commit `4b30503 obs(workstream-i): silent-wicket-absorption observability tag + classifier` on branch `obs/silent-wicket-absorption`. 11 files / +4419 / -2.

**Acceptance criteria met (all 4):** Surface I detects 2 (wickets at 4.6 Rahul + 10.5 Stubbs); C21b unchanged at 1; all other 13 surfaces identical; `SILENT-WICKET-ABSORPTION` trace tag fired 2× (frames 679 + 855).

**Surprise 1 — detected absorptions diverge from §11 prediction.** §11 predicted wickets 4 (Nissanka 10.2) + 5 (Stubbs 10.5). Actual detection: wicket 1 (Rahul 4.6) + wicket 5 (Stubbs 10.5). Pipeline's two valid FoW entries are `(74, Rana, 7.6)` and `(80, Nissanka, 9.5)` — the second is wrong-attribution: FoW3 Rizvi 9.5 is mislabeled as Nissanka by `score_manager.py:5306` `new_entry["dismissed"] = best_dismissed`.

Surface I count is correct by chance: **3 real silent absorptions exist** (wickets 1, 4, 5), but the wrong-attribution at 9.5 masks the Surface I detection at 10.2 — harness pairs pipeline's Nissanka-9.5 with GT's Nissanka-10.2 within ±N frame tolerance and skips the Surface I flag.

Defect-class taxonomy: the wrong-attribution at 9.5 is D2 (broadcast-override at WICKET-ATTRIB) reproducing in the dump, structurally identical to Obs 9's live finding — wicket WAS dispatched but with a name borrowed from a downstream broadcast-strip frame where Nissanka's stumping animation was already on-screen. Not a new defect surface; existing D2-falsification surface, different frame.

**Surprise 2 — `self.wickets` has at least two mutation paths.** Phase 1's SM-FEEDER-SYNC trace tag fires at frames 679 + 855 — the WORKING dispatches where WICKET-FALL-ONLY-CALLED also fires. The silent absorptions at frames 946 + 1062 reach `self.wickets` via a DIFFERENT mutation path that doesn't traverse the Phase 1 instrumentation point.

Structural implication for §12.4 entry-point #4: Phase 2 cannot rely on hooking SM-FEEDER-SYNC alone. **§12.6 Session N step 1 amended: enumerate ALL paths that mutate `self.wickets` and identify which fires at frames 946/1062.** The §12.4 #4 spec's "verify at execution time whether (3) alone is sufficient" hedge is now empirically confirmed insufficient — Path B must be found before §12.4 entry-point #4 can be specified.

Concrete read targets for Path B identification (CC next):

```
grep -n 'self\.wickets\s*=' files/score_manager.py
grep -n 'self\.wickets\s*+=' files/score_manager.py
grep -n 'scoreboard\.set\("wickets"' files/score_manager.py files/eyes/
grep -n '_inn\[.*wickets' files/score_manager.py files/eyes/scoreboard.py
```

Cross-reference output with `WICKET-FALL-ONLY-CALLED` trace tag firings at frames 946 + 1062 (operator confirmed those frames have no tag fire). The mutation path that fires at those frames without a wicket-event dispatch is Path B.

These two surprises do NOT block §12 work but sharpen §12.6 Session N step 1's read-before-write scope. Update §12.6 step 1 inline: "Enumerate all `self.wickets` mutation paths; identify Path B (the one that fires at frames 946/1062 in the captured dump)."

### §11.6 — §12.6 Session N step 1 read-pass complete 2026-05-22 evening

CC executed the 5-target read pass. Findings landed as §12.10 below. Headline: Bowler-W-credit-failure has zero independent root causes — 2 instances are snapshot-extraction artifacts, 5 share root with Surface I. §12 scope shrinks; the saved budget reallocates to §13 + §14 triple-rewrite expansion per §11.3 second consolidation.

## §12.10 — §12.6 Session N step 1 read-pass findings (2026-05-22 evening)

CC's 5-target diagnostic read produced two material findings that materially adjust §12's scope.

### §12.10.1 — Path B identified

The second `self.wickets` mutation path (per §11.5 Surprise 2) is **direct `scoreboard.set("wickets", N, frame)` called from OUTSIDE SM**. In the replay scaffold this is `files/scripts/replay_captured_scout_trace.py:327`; in production `test_pipeline.py` the upstream sb-hydration does the same. This bypasses SM's `@wickets.setter` entirely (where Phase 1's `SILENT-WICKET-ABSORPTION` trace tag lives), explaining why frames 946 + 1062 never fire the tag despite incrementing the wickets counter.

The §12.4 entry-point #4 spec direction: hook at `scoreboard.set` itself when `field == "wickets"` and new value > prior. This is the centralized intercept — one site covers both replay-scaffold and production-test-pipeline callers. Alternative is to hook each caller (replay scaffold + test_pipeline), which duplicates the dispatch logic across paths.

**Decision:** centralize at `scoreboard.set`'s wickets-field branch. Dispatch the synthetic WICKET event from there, routing into `apply_wicket_event` per §12.3.

### §12.10.2 — Material Finding A: Bowler-W-credit-failure 7 instances decompose into 2 + 5 + 0

| Sub-class | Count | Root cause |
|---|---|---|
| Snapshot-extraction artifact at successfully-dispatched wickets (7.6, 9.5) | 2 | `bowling_card` HAS the credit; harness snapshotter reads `bowling_card[canonical_name(sm.bowler_name)]` but `sm.bowler_name` is `None` at extraction time due to `BOWLER-LOCK-RELEASED` at over-end. Snapshot reads `bowling_card[None] = {}` → reports 0W. **The credit is correct; the snapshot can't see it.** |
| Same-root-as-Surface-I (10.2, 10.3, 10.5, 11.1, 11.2, 11.3) | 5 | Path B silent absorption skips `_apply_event` → skips `_accumulate_stats_from_event` at `:5767` → bowler-W increment never fires. Auto-closes when Surface I Phase 2 Candidate A (dispatch synthetic WICKET on Path B) lands. |
| Genuinely independent | 0 | After subtracting the 2 snapshot artifacts and the 5 Surface-I-overlap instances, the residual is zero. |

### §12.10.3 — Material Finding B: Bowler-W-credit is structurally subsumed

The §12.4 entry-point design absorbs the 5 Surface-I-overlap instances automatically (Path B dispatch → `apply_wicket_event` → canonical `scoreboard.update_bowler(..., wickets_delta=1, ...)` call). The 2 snapshot artifacts are closed by a separate small-scope sibling fix on the SM/snapshot contract.

**Sibling fix specification — `_last_bowler_at_wicket_commit` field:**
- Capture `self.bowler_name` (or canonical-resolved equivalent) into `self._last_bowler_at_wicket_commit` at the moment `apply_wicket_event` fires.
- Field survives `BOWLER-LOCK-RELEASED` over-end clearing (NOT cleared on over-boundary).
- Harness snapshotter (in `files/scripts/replay_captured_scout_trace.py` snapshot-emit hook) reads `sm._last_bowler_at_wicket_commit` as fallback when `sm.bowler_name is None` at wicket-coincident snapshot frames.
- Net: 2 false-positive Bowler-W-credit-failure instances close. No SM behavior change beyond a single field write.

### §12.10.4 — `_increment_bowler_wickets` is mythical; 7 inline sites are the real surface

§12.3 step 4 named `_increment_bowler_wickets` as the canonical commit-path function. CC's grep confirmed **no such function exists today.** Bowler-W credit is inline at 7 call sites, all via `self.scoreboard.update_bowler(name, ..., wickets_delta=N, frame=...)` (sites: `:2057, :5456, :5691, :5767, :5853, :6267, :6348`).

The §12 rewrite creates `_increment_bowler_wickets` as the canonical path (or wires `apply_wicket_event` to call `scoreboard.update_bowler` once). Either shape works; the architectural intent is "ONE call site, called from `apply_wicket_event` exclusively, all 7 prior inline sites removed." This is itself an architectural fence — the post-§12 codebase should fail a linter rule that flags any `scoreboard.update_bowler(.., wickets_delta=...)` call outside `apply_wicket_event`'s call graph.

### §12.10.5 — §12.7 out-of-scope addition

Add to §12.7: **"Bowler-W-credit at `gap_finalize_wicket` as a standalone defect — empirically subsumed by Surface I + a snapshot-extraction bug per §12.10 read pass; no independent root cause exists. Closing Surface I + landing the `_last_bowler_at_wicket_commit` sibling fix auto-closes the entire 7-instance count without §12.4 needing a dedicated entry-point or `apply_wicket_event` field for bowler-W."**

This inverts the §11 estimate that put Bowler-W-credit as Step 6 #2 priority. The diagnostic eliminated a candidate workstream by absorbing it structurally.

---

## §13 — Striker-rotation subsystem greenfield rewrite spec

**Operator decision 2026-05-22 evening (post-§12 diagnostic):** expand greenfield-rewrite scope to include striker rotation. Same architectural pattern as wicket-handling (parallel write paths, no canonical derivation source). Cricket rules are simple state machine; complexity is accumulated entanglement.

### §13.1 — Scope: what goes, what stays

**Goes (replaced):**
- Inline `self.striker = ...` assignments scattered across `score_manager.py` (estimated 8-12 sites; CC must grep at execution time).
- Deterministic-rotation override at `score_manager.py:4295-4325`. **CRITICAL: this is currently in `Architecture_HANDOFF.md`'s "What NOT to touch" list — the §13 rewrite explicitly removes that fence and REPLACES the override with `derive_striker_event`. The S12 non-discriminable-predicate-signature defect (from C30b) lives in this override; rewriting eliminates the surface entirely.**
- Post-wicket striker-init logic inside `_apply_wicket_fall_only` and `_apply_event` wicket-branch.
- Cold-start striker-init (currently F1 fix at `:2789-2808`). F1's intent is preserved but reimplemented via the canonical derivation.

**Stays (untouched):**
- Scout 5-primitive extraction including `first_striker` and per-frame `bat1_name`/`bat2_name`.
- Broadcast-striker indicator field on cards (input to derivation, not authoritative).
- `_handle_warm` streak gate (unrelated to striker pointer).

### §13.2 — Derivation contract

```python
@dataclass(frozen=True)
class StrikerEvent:
    prev_striker: Optional[str]
    next_striker: str
    reason: str   # "first_striker_init" | "odd_run_rotation" | "end_of_over_swap" |
                  # "wicket_new_batter" | "wicket_non_striker_stays" | "no_change"

def derive_striker_event(
    prior: SnapshotPrimitives,
    current: SnapshotPrimitives,
    wicket_event: Optional[WicketEvent],   # from §12.2
    over_boundary_crossed: bool,            # current.over % 1 == 0 and prior wasn't
    legal_ball_completed: bool,             # current.balls > prior.balls
) -> StrikerEvent:
    """
    Pure derivation. No side effects. Cricket rules:

    1. Cold-start (prior.striker is None): next = current.first_striker per Scout primitive.
    2. Wicket event with set-difference dismissed:
         - dismissed_batter exists in prior_at_crease + missing from current_at_crease
         - new_batter = (current_at_crease - prior_at_crease).pop()
         - If dismissed_batter == prior.striker: next = new_batter (new batter takes strike)
           [exception: run-out-on-completed-Nth-run — see Edge Case 3]
         - Else (dismissed was non-striker): next = prior.striker (striker stays)
         - Then apply post-wicket end-of-over swap if legal_ball_completed completes an over.
    3. Over-boundary crossed (legal_ball_completed AND current.over % 1 == 0): swap.
    4. Legal-ball with delta_score odd (delta excludes extras-only Δ): swap.
    5. Else: no change.
    """
```

### §13.3 — Canonical commit

```python
def apply_striker_event(self, event: StrikerEvent) -> None:
    """Single mutation path for self.striker."""
    if event.reason == "no_change":
        return
    self.striker = event.next_striker
    self._emit_trace(
        tag="STRIKER-EVENT-DISPATCHED",
        payload={
            "prev": event.prev_striker,
            "next": event.next_striker,
            "reason": event.reason,
        },
    )
```

### §13.4 — Entry-point replacements

Every site that currently writes to `self.striker` becomes a call to `derive_striker_event` → `apply_striker_event` chain. CC must grep at execution time:
```
grep -n 'self\.striker\s*=' files/score_manager.py
```
Estimated 8-12 sites; all consolidate to one call-graph through `apply_striker_event`.

### §13.5 — Harness acceptance gates

| Surface | Pre-rewrite count | Post-rewrite target | Notes |
|---|---|---|---|
| D-post-FoW-striker | 20 | ≤ 4 | Wicket-coincident cases close via §13.2 rule 2. Residual ≤ 4 from non-wicket post-FoW propagation drift (lag/race issues, Workstream G territory). |
| Obs 7 striker-pointer (this-replay live) | live-only | live-confirms-via-replay | Live-replay validation per §10.4 mandatory. |

Non-regression invariant: all other 12 surfaces unchanged.

### §13.6 — Edge cases (cricket rules at the boundary)

1. **Run-out on completed Nth run.** Cricket rule: striker is the batter who didn't complete the final run. Pipeline cannot determine "who didn't complete" from primitives alone — both batters' positions during the run are unknown. **Acceptable simplification:** treat as standard rotation per Δscore parity. Cricket-truth diverges in ~1% of cases; harness will flag if it matters via a `STRIKER-AFTER-RUNOUT-AMBIGUOUS` trace tag. Bound the residual to <1% case.
2. **Wicket on no-ball (free-hit).** Free-hit applies to next delivery; striker rotation for the wicket-ball itself follows normal rules. Wicket-on-no-ball is rare for stumpings (no-balls don't count) but possible for run-outs.
3. **Wicket-on-wide with stumping (the 10.2 case in DCKKR).** Wide doesn't advance ball-count; rotation does NOT fire on the wide itself. But the wicket changes the at-the-crease set. Apply rule 2 (wicket new-batter logic) without rule 4 (no legal-ball rotation since extras-only).
4. **Bye/leg-bye on odd runs.** Batters DO cross during byes/leg-byes if odd runs scored. The runs go to extras (not batter), but rotation fires. Distinguish from wides/no-balls (no crossing).
5. **Lost-frames between snapshots.** If pipeline missed frames (Workstream G lag-consequence), Δscore + Δwickets + Δover may bundle multiple deliveries into one snapshot. Striker rotation cannot be fully derived. Emit `STRIKER-LOST-FRAMES-AMBIGUOUS` and refuse to derive; let the next confident snapshot re-anchor.

Each edge case has a unit test in the new module.

### §13.7 — Out-of-scope

- Bowler-pointer rotation (separate subsystem, Workstream F territory).
- Per-batter-ledger drift (Obs 16 — independent).
- Phantom-runs (Obs 8 — independent).
- Pipeline-lag (Obs 10 — independent).

---

## §14 — This_over publishing subsystem greenfield rewrite spec

**Operator decision 2026-05-22 evening:** expand greenfield-rewrite scope to include this_over publishing. Same architectural pattern. Cricket rule is literally `Δscore + Δwickets + Δextras → token`.

### §14.1 — Scope: what goes, what stays

**Goes (replaced):**
- `_rewrite_eyes_this_over_from_event` at `score_manager.py:695` (and all call sites).
- `_fix_last_this_over_token` at `:6491` (retry/recovery path).
- `_synthesize_cold_start_ball_events` token-distribution heuristic at `:1892-1938` — replaced with the new derivation function called per-frame from cold-start exit forward.
- All inline `self.this_over.append(...)` sites in `_apply_event` (`:5907`, `:6032`, others).
- Compound-token rendering logic (currently absent for wicket-on-extras per Obs 13 #4 — added in §14.2).

**Stays (untouched):**
- `over_mgr` interface (this_over feeds over_mgr's display, contract unchanged).
- WS payload's reading of over_history (SM remains canonical authority).
- Over-archive policy at the over-rollover boundary (Recent-Overs-drop is Step 6 #5, separate from token completeness).

### §14.2 — Derivation contract

```python
@dataclass(frozen=True)
class ThisOverToken:
    raw: str                       # ".", "1", "2", "4", "6", "W", "wd", "nb", "1wd",
                                   # "4+W", "Wd+W", "Nb+W", etc.
    delta_score: int
    delta_legal_balls: int         # 0 or 1
    wicket_flag: bool
    extras_type: Optional[str]     # "wd", "nb", "b", "lb", or None

def derive_this_over_token(
    prior: SnapshotPrimitives,
    current: SnapshotPrimitives,
    wicket_event: Optional[WicketEvent],
) -> Optional[ThisOverToken]:
    """
    Pure derivation. Returns None on idle frames (no delivery between prior + current).

    Token-composition rules:
      - delta_legal_balls == 0 and delta_extras == 0 and delta_wickets == 0 → None (idle)
      - delta_legal_balls == 1, delta_score in 0..6, no wicket → "." | "1" | "2" | "3" | "4" | "5" | "6"
      - delta_legal_balls == 0, delta_extras > 0 → "wd" | "nb" | "Nwd" | "Nnb" (prefix with run count)
      - delta_legal_balls == 1, delta_score > 0, no wicket, byes → "Nb" | "Nlb" (legal ball, extras runs)
      - wicket present, delta_score == 0, delta_extras == 0 → "W"
      - wicket present, delta_score > 0, delta_legal_balls == 1 → f"{delta_score}+W" (run-out on scoring ball)
      - wicket present, delta_extras > 0, delta_legal_balls == 0 → "Wd+W" | "Nb+W"
      - Edge: multiple legal balls in one snapshot transition (lost frames) → return cluster token "MULTI" with payload, caller collapses or defers per Edge Case below.
    """
```

### §14.3 — Canonical commit

```python
def apply_this_over_token(self, token: ThisOverToken) -> None:
    """Append token to current over. Trigger over-rollover when 6 legal balls complete."""
    self.this_over.append(token.raw)
    if token.delta_legal_balls > 0:
        self.legal_balls_in_over += 1
        if self.legal_balls_in_over >= 6:
            self._archive_over()
            self.this_over = []
            self.legal_balls_in_over = 0
    self._emit_trace(
        tag="THIS-OVER-TOKEN-APPENDED",
        payload={
            "raw": token.raw,
            "delta_score": token.delta_score,
            "delta_legal_balls": token.delta_legal_balls,
            "wicket_flag": token.wicket_flag,
            "extras_type": token.extras_type,
        },
    )
```

### §14.4 — Entry-point replacements

Replace all sites that mutate `self.this_over`:
- `_apply_event` token-append sub-branches → call `derive_this_over_token` + `apply_this_over_token`.
- `_apply_wicket_fall_only` (currently doesn't write this_over — that's the C21b bug) → wired via `apply_wicket_event` from §12.3, which calls `derive_this_over_token` for the wicket-frame token.
- `_synthesize_cold_start_ball_events` → at cold-start exit, prime `prior_primitives` from Scout's current frame, then derive per-frame forward from N+1. **No wholesale wipe + heuristic distribution. No backfill speculation.** The first cold-start-post frame produces `None` (idle) because there's no prior to derive Δ from; from the second frame onward, derivation produces tokens normally.

### §14.5 — Cold-start architectural note

The current synthesizer's behavior — wholesale wipe of `self.this_over` + heuristic token distribution — is architecturally wrong. It speculates about which ball carried which token, including dropping W tokens because "no observation basis for which ball" (its own docstring). The fix is not "smarter distribution"; it's "don't backfill speculatively at all."

Cold-start contract under §14:
- At cold-start entry (Scout first-confident-read after boot), capture current primitives as initial state. `self.this_over` remains `[]` (empty); the pre-cold-start balls are lost (we don't know them — that's accepted).
- From frame N+1 forward, derive per-frame Δ tokens normally.
- Recent-Overs panel will show `?` placeholders for the cold-start-bypassed over until next over starts cleanly. This is the correct behavior — we genuinely don't know what happened before pipeline booted.

This is the derivation-first principle taken to cold-start: refuse to invent state where primitives don't justify it.

### §14.6 — Harness acceptance gates

| Surface | Pre-rewrite count | Post-rewrite target | Notes |
|---|---|---|---|
| C21b-symbol-revert | 1 | 0 | Cold-start subcase closes — no wholesale wipe means no W loss. Live-replay confirms broader pattern. |
| Compound-with-wicket-token | 2 | 0 | §14.2 composition rules handle Wd+W, Nb+W, 4+W. |
| Multi-ball-compression | 4 | ≤ 1 | Token-compression cases close; the 1 residual is the cold-start-window "lost balls" case which §14.5 explicitly accepts. |
| Extras-counter-drop | 16 | ≤ 4 | Δextras-anchored derivation propagates correctly to extras counter via standard `apply_this_over_token` flow. Residual ≤ 4 from independent extras-state race conditions. |

Non-regression invariant: all other 10 surfaces unchanged.

### §14.7 — Edge cases

1. **Idle frame (no Δ).** Return `None`. Caller skips.
2. **Multi-ball gap in single snapshot transition** (Workstream G lag-consequence). Δlegal_balls > 1. Acceptable answers: (a) emit `THIS-OVER-CLUSTER-LOST-FRAMES` and append `?` token per missed ball; (b) collapse into single compound token with a `LOST_FRAMES_N` annotation. Pick (a) — preserves Recent-Overs panel's `?` rendering for unresolved balls (Obs 11b's existing behavior).
3. **Wicket on free-hit (post no-ball).** Standard wicket token; free-hit context is a separate state (not part of this_over token).
4. **Extras with byes/leg-byes credited to extras + advancing ball count.** Token is `Nb` or `Nlb` (legal ball + extras score). Rotation in §13 handles cross-during-byes correctly.
5. **Scout-extracted score ambiguous.** Defer derivation; emit `THIS-OVER-TOKEN-DEFERRED` and wait for next confident read.

### §14.8 — Out-of-scope

- Recent-Overs panel render policy (Step 6 #5 — independent).
- Phantom-runs root cause (Step 6 #6 — Δscore correctness is upstream of this_over derivation).
- Pipeline-lag (Step 6 #7 — performance).

---

## §15 — Unified execution sequence for §12 + §13 + §14 triple rewrite

The three subsystems share enough plumbing that they should land in coordinated commits, NOT three independent feature branches. Recommended sequence (2-3 sessions):

```
Session A — derivation modules + first canonical commit path:
  1. Implement derive_wicket_event + derive_striker_event + derive_this_over_token
     in a single new module files/score_manager_derivation.py (or as section inside
     score_manager.py — operator pick).
  2. Implement apply_wicket_event + apply_striker_event + apply_this_over_token.
     Each is a thin method on SM that calls scoreboard mutators + emits trace.
  3. Unit tests for all three derivation functions, covering happy paths + edge cases
     from §12.2/§13.6/§14.7.
  4. Commit (1/N) "feat(derivation): pure functions + canonical commit paths for
     wicket / striker / this_over (no call-site changes yet)".

Session B — wire entry points + harness diff per commit:
  5. Wire _apply_event paths: wicket branch → apply_wicket_event; rotation
     decision → derive_striker_event → apply_striker_event; token append →
     derive_this_over_token → apply_this_over_token. Pre-commit Layer 1.5 + Layer 2.
     Harness diff: working paths preserved.
  6. Commit (2/N).
  7. Wire _apply_wicket_fall_only through apply_wicket_event (which cascades to
     apply_striker_event for post-wicket strike-pointer + apply_this_over_token
     for W token). Harness diff.
  8. Commit (3/N).
  9. Replace deterministic-rotation override at :4295-4325 with derive_striker_event
     call. Harness diff: D-post-FoW-striker drops.
  10. Commit (4/N).
  11. Wire scoreboard.set("wickets", ...) hook for Path B (per §12.10.1).
     Cascades through apply_wicket_event. Harness diff: Surface I drops to 0.
  12. Commit (5/N).

Session C — cold-start + cleanup:
  13. Replace _synthesize_cold_start_ball_events token-distribution heuristic
      with the no-backfill policy per §14.5. Harness diff: C21b drops; Multi-ball-
      compression drops.
  14. Commit (6/N).
  15. Add _last_bowler_at_wicket_commit sibling field. Update harness snapshotter
      to read it. Harness diff: Bowler-W-credit-failure 2 false-positives close.
  16. Commit (7/N).
  17. Final acceptance run: all §12.5 + §13.5 + §14.6 gates met. Layer 1.5
      + Layer 2 green.
  18. Commit (8/N) "feat: triple-subsystem greenfield rewrite complete".

  19. Live-replay validation per §10.4 + §12.8 + §13.5 + §14.6. Mandatory before
      claiming closure on the operator-visible defect surfaces.
  20. Update HANDOFF / Architecture_HANDOFF. Add the three new functions to
      "What NOT to touch" (replacing the prior deterministic-rotation override
      entry which §13 explicitly retired).
```

Estimated total: 8-10 commits across 2-3 sessions. Surface count reduction predicted: 14 → 5-7 (closes ~50% of the surface ledger). The remaining surface fixes (Workstream F, Per-batter, Recent-Overs policy, phantom-runs, pipeline-lag) become each 1-session surgical fixes per §11.3 items 2-7.

---

## §12 — Wicket-subsystem greenfield rewrite spec

**Operator decision 2026-05-22:** consolidate wicket-handling defects (5-7 surfaces) into one coordinated rewrite rather than 5-7 surgical fixes that may interact unpredictably. Local-fix approach is fighting structural entropy (2 failed C21b iterations as evidence). Harness now covers every wicket surface, so a coordinated rewrite is validatable diff-by-diff.

### §12.1 — Scope: what goes, what stays

**Goes (replaced):**
- `_apply_event` wicket-branch (handles roughly 50% of wicket cases today).
- `_apply_wicket_fall_only` (gap-finalize path).
- `_synthesize_cold_start_ball_events` wicket-handling stub (currently distributes nothing per docstring).
- SM-FEEDER-SYNC `scoreboard.set("wickets", N)` silent-absorption callback (no wicket dispatch today).

**Stays (untouched):**
- Scout 5-primitive extraction (`eyes/agent.py`, `eyes/extract_regex.py`, `eyes/scoreboard.py` extraction-side).
- C14 cross-field pairing gate at `apply_scorer_decision`.
- F1 fix at `_accept_initial:2789-2808`.
- F-α-shadow / F-α-queue / Queue B mechanisms (the working post-wicket-credit machinery).
- ConsistentReadTracker (used for tracker-locked bowler-name input to derivation).
- WS payload builder / UI render path.
- Trace infrastructure, harness, ground-truth fixture.
- Layer 1.5 + Layer 2 test scaffolds (acceptance criteria below extend these, not replace).

### §12.2 — Derivation contract (the new module)

New file: `files/score_manager_wicket.py` (or inline as a section inside `score_manager.py` if operator prefers single-file scope — pick at execution time).

```python
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class SnapshotPrimitives:
    score: int
    wickets: int
    overs: str                  # "10.5"
    bat1_name: Optional[str]    # at-the-crease set, position-agnostic
    bat2_name: Optional[str]
    bowler_name: Optional[str]
    extras_total: int           # sum of wd/nb/b/lb

@dataclass(frozen=True)
class WicketEvent:
    delta_wickets: int                 # >= 1 (function returns None if 0)
    over_ball: str                     # "10.5" — pipeline's current over.ball at dispatch frame
    bowler_name: str                   # tracker-locked current bowler
    dismissed_batter: Optional[str]    # derived via set-difference; None on ambiguous case
    delta_score: int                   # current.score - prior.score
    delta_extras: int                  # current.extras_total - prior.extras_total
    this_over_token: str               # "W" / "<N>+W" / "Wd+W" / "Nb+W" — composed per rules below
    is_extras_dismissal: bool          # True if delta_extras > 0 in same frame
    is_runout_speculative: bool        # True if delta_score > 0 in same frame (run on the wicket ball)

def derive_wicket_event(
    prior: SnapshotPrimitives,
    current: SnapshotPrimitives,
    tracker_locked_bowler: Optional[str],
) -> Optional[WicketEvent]:
    """
    Pure derivation. No side effects. No Scout extension assumed.

    Returns None if current.wickets <= prior.wickets (no wicket fell).

    Set-difference rule for dismissed_batter:
      prior_set = {prior.bat1_name, prior.bat2_name} - {None}
      current_set = {current.bat1_name, current.bat2_name} - {None}
      diff = prior_set - current_set
      if len(diff) == 1: dismissed_batter = diff.pop()
      if len(diff) == 0: dismissed_batter = None  # defer per Edge Case 2
      if len(diff) >= 2: raise WicketAmbiguousDualChange  # Edge Case 3
    """
    ...
```

Token composition rules (this_over_token):
- `delta_wickets > 0 and delta_score == 0 and delta_extras == 0` → `"W"`
- `delta_wickets > 0 and delta_score > 0` → `f"{delta_score}+W"` (run-out on a scoring ball)
- `delta_wickets > 0 and delta_extras > 0 and delta_score == delta_extras` → `"Wd+W"` (or `"Nb+W"` based on extras_type — needs the prior.extras_wd / .extras_nb breakdown; extend `SnapshotPrimitives` if not already present)
- All cases: `is_extras_dismissal` and `is_runout_speculative` flags surface the compound nature for downstream consumers

### §12.3 — Canonical commit path

```python
def apply_wicket_event(self, event: WicketEvent) -> None:
    """Single mutation path for wicket state. All downstream effects fan out from here."""
    # 1. Mutate canonical state
    self.wickets += event.delta_wickets

    # 2. FoW append (single _add_fow path — replaces all current callers)
    self._add_fow(
        score=self.score,
        wickets=self.wickets,
        batter=event.dismissed_batter,  # may be None — UI renders as em-dash
        over_ball=event.over_ball,
    )

    # 3. this_over token append + over_mgr propagate
    self.this_over.append(event.this_over_token)
    self._rewrite_eyes_this_over_from_event(self.current_bowling_card, event.this_over_token)

    # 4. Bowler-W credit (single path — replaces the current 4-path mess)
    if event.bowler_name:
        self._increment_bowler_wickets(event.bowler_name)

    # 5. Striker rotation — new batter from prior_at_crease set difference's complement
    self._apply_post_wicket_striker_rotation(event)

    # 6. Trace emission (new tag)
    self._emit_trace(
        tag="SYNTHETIC-WICKET-DISPATCHED",
        payload={
            "over_ball": event.over_ball,
            "dismissed": event.dismissed_batter,
            "bowler": event.bowler_name,
            "delta_score": event.delta_score,
            "delta_extras": event.delta_extras,
            "this_over_token": event.this_over_token,
            "source": "<entry_point_id>",  # caller fills in
        },
    )
```

Edge case handling lives at the call sites (per Edge Cases 1-3 in §11.2), NOT in `apply_wicket_event` itself — the dispatch function trusts the event is well-formed. Callers that deferred dispatch (e.g., Edge Case 2 pending-queue) re-invoke when conditions resolve.

### §12.4 — Four entry-point replacements

Each entry point calls `derive_wicket_event` → if non-None, calls `apply_wicket_event`:

1. **`_apply_event` wicket-branch** (`score_manager.py:5862+`). Currently appends to `self.this_over` at `:5907`/`:6032` and calls `_rewrite_eyes_this_over_from_event`. Replace the wicket sub-branch with: build `SnapshotPrimitives` from pre-event + post-event SM state → `derive_wicket_event` → `apply_wicket_event`. Existing `_apply_event` other branches (legal-ball runs, extras, etc.) unchanged.

2. **`_apply_wicket_fall_only`** (`score_manager.py:5191+`). Currently handles FoW + partnership but no `this_over` write. Replace body with: build primitives → derive → apply. All 3 call sites (`:5562`, `:6094`, `:6458`) now go through the canonical path. **The 3-call-site guard problem from Iteration 1 dissolves** — `apply_wicket_event` is idempotent on this_over via tail-check.

3. **`_synthesize_cold_start_ball_events`** (`score_manager.py:1856+`). Currently wipes `this_over` and rewrites without W tokens. Modification: after the existing `self.this_over = list(tokens)` wipe-rewrite at `:1938`, iterate `self.fall_of_wickets` for entries in the current over and overlay their W tokens at the correct positions. **Plus** — for the silent-absorption case where FoW is itself incomplete, the synthesizer compares `prior_snapshot` (pre-cold-start-entry) vs `current_snapshot` (post-cold-start-entry) and calls `derive_wicket_event` to dispatch any missing wickets through `apply_wicket_event` BEFORE the synthesis. This means FoW is complete by the time the overlay runs.

4. **SM-FEEDER-SYNC `scoreboard.set("wickets", N)` site.** Currently silent absorption. Add a hook (likely in `scoreboard.set` itself or its caller in `score_manager.py`): when `field == "wickets"` and new value > prior, capture primitives before/after and call `derive_wicket_event`. The most architecturally clean version: the synthesizer modification in (3) above absorbs this case too, since cold-start re-entry is what triggers SM-FEEDER-SYNC's wicket-jump in the captured dump. Verify at execution time whether (3) alone is sufficient or (4) needs a separate hook.

### §12.5 — Harness acceptance gates per surface

After full rewrite lands, harness must show:

| Surface | Pre-rewrite count | Post-rewrite target | Notes |
|---|---|---|---|
| C21b-symbol-revert | 1 | 0 | Cold-start subcase auto-closes via (3). Live-replay confirms broader closure per §10.4. |
| Workstream I — silent-wicket-absorption | 2 | 0 | (3) or (4) dispatches the missing wickets via canonical path. |
| Obs 9 wicket-frame-misalign | 32 | ≤4 | Wicket-coincident cases close; non-wicket-frame lag-misalign remain (Workstream G territory). |
| Obs 13 compound-with-wicket-token | 2 | 0 | Token composition rules in §12.2 handle Wd+W / N+W. |
| Obs 14 bowler-W-credit-failure | 7 | 0 | Single canonical commit path always credits bowler. |
| D2-Layer-2 post-FoW striker init | 20 | ≤8 | Wicket-coincident striker-init cases close via §12.3 step 5; non-wicket post-FoW propagation drift remains. |

**Non-regression invariant:** all other 8 surfaces unchanged. F-A/F-B/Per-batter-ledger-drift/Recent-overs-drop/E2-phantom-runs/Boundary-counter/Multi-ball-compression/G-pipeline-lag counts must not increase.

### §12.6 — Execution sequence (1-2 sessions)

```
Session N — landing:
  1. Read-before-write — 30 min:
     - grep current 4 entry points for the exact mutation sites
     - confirm SnapshotPrimitives field availability
     - verify _prior_at_crease_set exists or design its placement
     - inspect _add_fow / _increment_bowler_wickets / _apply_post_wicket_striker_rotation signatures
  2. Implement derive_wicket_event + apply_wicket_event in new module (or inline section). No call-site changes yet.
  3. Add unit tests for derive_wicket_event covering: clean wicket, run-out-on-scoring-ball, Wd+W, set-difference empty (Edge Case 2 deferral), Δwickets > 1 (Edge Case 1), set-difference = 2 (Edge Case 3 raise).
  4. Pre-commit Layer 1.5 + Layer 2 green; commit "(1/5) derive_wicket_event module + tests".
  5. Wire entry point (1) — _apply_event wicket-branch. Smallest blast radius (path that works today).
  6. Harness diff: pre-rewrite baseline vs post-(1) report. Expected: no surface count change (path already works). Confirms (1) is behavior-preserving.
  7. Commit "(2/5) wire _apply_event wicket-branch through derive/apply".
  8. Wire entry point (2) — _apply_wicket_fall_only. Harness diff. Confirms (2) closes the gap-finalize C21b case if dump contains one.
  9. Commit "(3/5) wire _apply_wicket_fall_only through derive/apply".

Session N+1 — closing the cold-start case:
  10. Wire entry point (3) — _synthesize_cold_start_ball_events. This is the leveraged one — closes the silent-absorption path the entire iteration 1+2 chain investigated.
  11. Harness diff: target counts per §12.5. C21b 1→0; Workstream I 2→0; Bowler-W-credit 7→0; etc.
  12. Commit "(4/5) wire cold-start synthesizer through derive/apply + W-token overlay".
  13. Wire entry point (4) IF (3) didn't subsume it. Harness diff confirms idempotency or zero-effect.
  14. Commit "(5/5) wire SM-FEEDER-SYNC wicket-jump hook" (or skip if (3) covers it).
  15. Final acceptance run: all §12.5 gates met. Commit "wicket-subsystem greenfield complete".

  16. Live-replay validation per §10.4. Fresh UDP replay against DCKKR fixture (or any wicket-dense fixture).
      Confirm 5-7 surface counts on live trace match harness predictions.
  17. If live confirms: update HANDOFF / Architecture_HANDOFF with the rewrite-as-landed.
      If live diverges: open §13 retrospective with the new findings.
```

### §12.7 — What §12 explicitly does NOT fix

Out of scope for this rewrite (handled separately per §11.3 items 2-7):
- **Workstream F bowler misattribution** (over-boundary commit-lag, ad-occlusion fallback). Different surface — bowler identity at non-wicket frames.
- **Per-batter-ledger-drift** (Obs 16). Independent surface — runs attribution between live batters, no wicket dependency.
- **Recent-Overs drop** (Obs 11b). Independent — over-archive gate's unresolved-ball discard policy.
- **Phantom-runs** (Obs 8). Independent — score-state fabrication on non-wicket events.
- **Pipeline-lag** (Obs 10). Performance/throughput, not correctness.
- **Boundary-counter double-increment** (Obs 3). Independent — parallel-update-path on 4s/6s counter columns, no wicket dependency.

If §12 closes 5-7 surfaces as predicted, defect-density drops from 14 to 7-9 surfaces in 1-2 sessions. The remaining surgical fixes are individually smaller-scope than the unified rewrite and each have clear single-site fix candidates per the original Step 6 priority list.

### §12.8 — Live-replay confirmation gate (mandatory per §10.4)

Harness validates the cold-start-synth path. The other 4 C21b cases (4.5/4.6, 7.4, 10.1, over-11 wickets per Obs ledger) live in live-replay only — dump doesn't capture all the WICKET dispatches. After §12 lands, run a fresh DCKKR UDP replay and confirm γ-bundle assertions show:
- `trace_gamma_w_symbol_at_wicket`: pre-rewrite FAIL×3+ → PASS at every wicket
- `trace_gamma_bowler_w_increment_on_dispatch`: pre-rewrite FAIL×7 → PASS at every wicket
- `trace_gamma_fow_name_matches_striker_at_wicket`: PASS (unchanged invariant)
- FoW entries match cricket truth at all 8 wickets

Live-replay is the FINAL acceptance gate for §12. Until live confirms, §12 is "harness-passed, live-pending" status — record this on the HANDOFF.

### §12.9 — Architecture HANDOFF entry (write at end of §12 landing)

Add to `Architecture_HANDOFF.md` under §"What NOT to touch":
- **NEW: `derive_wicket_event` + `apply_wicket_event` (post-§12)** — single canonical wicket-handling path. Any future wicket-related fix must go through these two functions; do not add parallel write paths to `self.wickets` / `self.fall_of_wickets` / `self.this_over` wicket-token append. Adding a 5th entry point would re-introduce exactly the structural entropy §12 was designed to eliminate.

This is the architectural fence that prevents future regression of the wicket subsystem.
