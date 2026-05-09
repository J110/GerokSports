# State-Recovery Phase 2 — enablement analysis (2026-04-29)

## Decision

**REFINE before enablement.**

Strengthen Phase 1 coherence/suppression (two narrow changes documented below) and re-validate against another match before flipping `STATE_RECOVERY_PHASE_2_ENABLED`.

- **Do not** enable Phase 2 mutation in this task.
- The current candidate pipeline produces **20.8 %** mutation-unsafe candidates (`PARTIAL_SIGNAL`) at the configured `N=5` threshold — at the edge of the **20 %** acceptance line in the task brief.
- Two small refinements drop the unsafe rate to **0 %** and leave only ambiguous cold-start cases, which can then be suppressed cleanly.
- Once refined, Phase 2 is **likely worth enabling at `N=5`** based on this match's signal: the dominant TP class would have started recovering ~5 minutes earlier than the existing `[POISON-RECAL]` path on the same corruption window.

---

## Inputs

| Source | Detail |
|--------|--------|
| Code | `files/test_pipeline.py` — `STATE_RECOVERY_PHASE_2_ENABLED = False`, `StateRecoveryAggregator(threshold=5, min_guard_families=2, telemetry_only=True)`, `_apply_state_recovery_phase2_mutation` (would call `score_mgr.full_reset(reason="state_recovery_consensus_override")`) |
| Logs scanned | `files/logs/machine-1-2026-04-2{3,4,5,6,7,8,9}.log` |
| Production candidate fires (real, excluding `F0 TEST` / `reason=fixture`) | **64** total — all in `machine-1-2026-04-28.log`; remaining logs **0** |
| Production override fires | **0** (Phase 2 disabled; only synthetic `F0 TEST` test fixtures present) |
| Suppression contract (caller) | `_state_recovery_suppressed = not batting_team or frame_type=="GRAPHIC" or frame_count <= _state_recovery_suppress_until_frame or not scoreboard._inn`. `_state_recovery_suppress_until_frame` is bumped on AUTO-SWAP / innings transition (`+5` frames). |

The analyzer’s pre-existing `STATE_RECOVERY_CANDIDATE` regex uses `\S+` for `candidate_json` etc., which silently drops candidates whose JSON contains string literals with spaces (e.g. `"Cooper Connolly"`). The analysis here used a brace-balanced parser to read all 64 candidates correctly. Recommend a follow-up to harden the analyzer regex (small task; not required for this decision).

---

## Aggregate signal — `machine-1-2026-04-28.log`

| Metric | Value |
|--------|------:|
| Candidates (real) | **64** |
| Distinct signatures | **28** |
| Guard-families touched | `slot_scrub_rejected` × 64 · `slot_collision_rejected` × 42 · `poison_score` × 29 · `batter_row_rejected` × 9 |
| `frames=` distribution | `5` × 62 · `6` × 1 · `10` × 1 |
| Candidates that would also fire at `N=3` | 64 (every event satisfies ≥ N) |
| Candidates that would still fire at `N=8` | **2** (the two with `frames ≥ 8`) |
| Proposed reset scopes (top) | `slot:striker` × 53 · `status:Suryansh` × 49 · `slot:non_striker` × 38 · `score` × 25 · `bat:Marcus` × 7 |

`N=3` would not increase TP yield meaningfully because the same signatures already accumulate to ≥ 5 frames; `N=8` would suppress ~97 % of fires including the dominant TP class — too tight.

---

## Per-signature categorization (28 distinct signatures, 64 events)

Each candidate was classified using only log fields (no replay):

- **PARTIAL_SIGNAL** — `candidate.score is None` (and/or wickets/overs absent). Mutation today is `score_mgr.full_reset`, regardless of `proposed_reset` scope. Resetting on a row that does not even carry a score is **mutation-unsafe**: the consensus is on stripped/batter-only rows, not a competing score truth.
- **TRUE_POSITIVE_LIKELY** — candidate carries a coherent `(score, wickets, overs)` triple AND large drift vs `current` (Δscore ≥ 20, **or** the classic stale-baseline `cand=0/0/≤1.0` while `current.score ≥ 20`).
- **AMBIGUOUS** — candidate has full signal but `current.score is None` (cold-start). Truth-wise plausible, but `full_reset` is the wrong corrective tool here (it wipes — would not seed the candidate value).

| sig (12-char) | n | category | candidate (score/wkts/overs) | current (score/wkts) | reading |
|---|---:|---|---|---|---|
| `8a1cfd5daec4` | 10 | TP_LIKELY (mostly) / AMBIG | `0 / 0 / 0.0` | `222 / 5` | classic stale-baseline; later confirmed by `[POISON-RECAL]` at 21:23:13 / 21:34:26 / 21:45:24 etc. on the same match |
| `a0d695b7ff25` | 8 | **PARTIAL_SIGNAL** | `None / None / None` | `222 / 5` | Marcus-Stoinis batter-only rows; no score in extracted |
| `f2ca58bb3ba0` | 6 | TP_LIKELY | `0 / 0 / 0.0` | `222 / 5` | same stale-baseline class as `8a1cfd5d…` |
| `f47468524715` | 4 | TP_LIKELY | `26 / 0 / 1.5` | `0 / 0` | innings-2 cold drift while board has no committed score yet, large Δ |
| `96cc1ebaf63b` | 3 | AMBIGUOUS | `16 / 0 / 1.2` | `None / None` | cold-start; would need a different seeding action |
| `b042466795d5` | 2 | **PARTIAL_SIGNAL** | `None / None / 0.3` | `None / None` | partial cold-start row |
| `966d1f070244` | 2 | AMBIGUOUS | `7 / 0 / 0.4` | `None / None` | cold-start |
| `11849d26334b` | 2 | TP / AMBIG | `37 / 0 / 2.2` | `0 / 0` | early innings |
| `f47516a29721` | 2 | TP_LIKELY | `51 / 0 / 3.1` | `0 / 0` | board lagging behind extracted |
| `86f862997e53` | 2 | TP_LIKELY | `73 / 1 / 5.2` | `0 / 0` | board lagging |
| `8675b64b14db` | 2 | TP_LIKELY | `73 / 1 / 5.3` | `0 / 0` | board lagging |
| `b2620a9b493e` | 2 | TP_LIKELY | `84 / 1 / 6.0` | `0 / 0` | board lagging |
| `92e19f6183e0` | 2 | TP_LIKELY | `90 / 1 / 7.0` | `0 / 0` | board lagging |
| `3e4c4f80fc79` | 2 | TP_LIKELY | `56 / 6 / 14.3` | `156 / 4` | inner-innings reset misread |
| `5464ea966838` | 2 | TP_LIKELY | `66 / 4 / 15.1` | `160 / 6` | inner-innings reset misread |
| `195c71397f89` | 1 | TP_LIKELY | `0 / 0 / 3.5` | `47 / 1` | regression strip |
| `9bf44af93666` | 1 | **PARTIAL_SIGNAL** | `None / None / None` | `222 / 5` | same Marcus class as `a0d695…` |
| `0a12205d4cb8` | 1 | AMBIGUOUS | `0 / 0 / 0.5` | `None / None` | cold-start |
| `9fe749b10cb5` | 1 | AMBIGUOUS | `16 / 0 / 1.3` | `None / None` | cold-start |
| `dc1ba9c9488c` | 1 | AMBIGUOUS | `20 / 0 / 1.4` | `None / None` | cold-start |
| `79cc512fde91` | 1 | AMBIGUOUS | `0 / 0 / 0.0` | `None / None` | cold-start |
| `10ff28fedd1c` | 1 | TP_LIKELY | `52 / 1 / 3.3` | `0 / 0` | board lagging |
| `647e7972a76a` | 1 | TP_LIKELY | `62 / 1 / 3.5` | `0 / 0` | board lagging |
| `2baeecdcca17` | 1 | TP_LIKELY | `84 / 1 / 6.0` | `0 / 0` | board lagging |
| `92ece97727e7` | 1 | TP_LIKELY | `86 / 1 / 6.3` | `0 / 0` | board lagging |
| `1119f2de60b6` | 1 | TP_LIKELY | `0 / 0 / 0.0` | `105 / 1` | reset-strip misread |
| `852271f13a32` | 1 | TP_LIKELY | `20 / 0 / 2.0` | `105 / 1` | reset-strip misread |
| `6c483b0b83d1` | 1 | TP_LIKELY | `66 / 4 / 6.0` | `160 / 6` | reset-strip misread |

**Per-event totals:**

| Category | Count |
|---|---:|
| TRUE_POSITIVE_LIKELY | **42** |
| PARTIAL_SIGNAL | **11** |
| AMBIGUOUS | **11** |
| **Total** | 64 |

---

## False-positive rate (mutation-safety framing)

Treating `PARTIAL_SIGNAL` as FPs (mutation today is `full_reset`, which is unsafe on a partial-signal candidate even when consensus is stable):

| Threshold | TP_likely | FP (PARTIAL) | AMBIG | FP/(TP+FP) | Verdict |
|---|---:|---:|---:|---:|---|
| **N=5 (current)** | 42 | 11 | 11 | **20.8 %** | **at the threshold edge** |
| N=8 | 2 | 0 | 0 | 0 % | suppresses the win class too |
| N=5 + coherence requires `candidate.score ≠ None` | 42 | **0** | 11 | **0 %** | **mutation-safe partition** |
| N=5 + coherence requires `candidate.score ≠ None` AND caller suppresses on `current.score is None` | 42 | 0 | 0 | 0 % | clean cold-start handling, full TP yield preserved |

The two refinements are independent and both small. They convert the ambiguous classes into either suppressed cold-start (correct) or non-events (correct) without removing any TP-class candidate.

---

## Suppression-gap findings

The two FP/AMBIG classes correspond to two real gaps in the suppression contract:

1. **Partial-signal gap.** `_check_coherence` accepts a candidate even when `score`, `wickets`, and `overs` are all `None`. Consensus then forms on a batter-row-only signal (often 5 frames of stripped Marcus rows), but the mutation (`full_reset`) needs more than a row signal to be safe. — Fix in `_check_coherence`.

2. **Cold-start gap.** Caller suppression keys off `not scoreboard._inn` (innings dict missing) and AUTO-SWAP windows, but **not** `scoreboard._inn.get("score") is None` while batting_team is set (the “board has no committed score yet” case). Candidates with `current.score is None` cannot be evaluated as “drift” and `full_reset` would wipe seeding state. — Fix at the caller-side suppression check.

Neither change removes the dominant TP class (`current.score ≥ 20` while candidate shows the new innings-2 baseline / fresh strip).

---

## Overlap with `[POISON-RECAL]`

The dominant TP class on this match (`8a1cfd5d…` × 10 + `f2ca58b…` × 6 + the `… / 0` series) is the **same corruption pattern** that `[POISON-RECAL]` recovers from — “5 consecutive POISON'd reads of score=0; tracker baseline 222 is stale”, observed at 21:23:13 (F2807), 21:34:26 (F3074), 21:45:24 (F3358), 21:50:51 (F3474), 21:54:02 (F3547), 21:57:54 (F3604). The state-recovery aggregator’s first matching candidate (`8a1cfd5daec4`, 10 fires) starts at **F2608 (21:18:34)** — **~5 minutes ahead** of the first `POISON-RECAL` on this window.

If Phase 2 ships at `N=5` after refinement, expected behaviour:

- **TP path:** state-recovery fires `full_reset` first (~F2608), POISON-RECAL’s first instance (~F2807) becomes a no-op because the score has been cleanly recalibrated already.
- **Redundancy path:** in matches where state-recovery does not fire (e.g. PBKS-vs-RR 164-min log: 0 candidates), POISON-RECAL remains the recovery path. **Defense-in-depth preserved.**

This is the production benefit of enabling Phase 2: ~5 min of recovery latency improvement on the dominant corruption class, without removing the existing recovery layer.

---

## Recommended refinement (specific changes)

**Both changes are small (≤ 5 lines each), local, and ship with regression tests using the existing `test_state_recovery_*` suite.**

1. `files/test_pipeline.py` — `StateRecoveryAggregator._check_coherence`:

   - Add a new check `score_present` that fails if `candidate.get("score") is None`.
   - Reason: candidates without a score-side claim cannot be safely turned into `full_reset` mutations.

2. `files/test_pipeline.py` — caller block that builds `_state_recovery_suppressed`:

   - Extend with `or scoreboard._inn.get("score") is None` (after the existing `not scoreboard._inn` clause).
   - Reason: cold-start window has no committed-score reference for drift comparison; `full_reset` would wipe seeding and create a worse outcome than waiting one more frame.

3. **Out of scope for this task** (separate implementation): once (1) and (2) ship and another match log is captured cleanly, set `STATE_RECOVERY_PHASE_2_ENABLED = True`. Keep `min_guard_families = 2` and `threshold = 5`.

4. **Analyzer hardening (small follow-up):** replace the `\S+` regex in `STATE_RECOVERY_CANDIDATE` / `STATE_RECOVERY_OVERRIDE` with a brace-balanced JSON extractor; otherwise candidates with string literals containing spaces (`"Cooper Connolly"`, `"Marcus Stoinis"`) are silently dropped from analyzer reports.

---

## What additional data would change the decision

- A **second match log** with a witnessed corruption window after refinement (1) + (2) ships. If FP / partial-signal counts stay at zero and TP yield holds, Phase 2 is safe to enable at `N=5`.
- A **suppression-aware replay** of `machine-1-2026-04-28.log` confirming that all 11 cold-start AMBIGUOUS candidates would have been suppressed by the new caller check. (Trivial replay; can be added to `test_recent_fixes.py` against the parsed events.)

Until then: **DO NOT** enable Phase 2.

---

## Files touched by this investigation

- **New:** `files/docs/investigations/state_recovery_phase2_enablement_analysis.md` (this file)
- **No code changes** in this task. Refinements (1) and (2) and the analyzer regex hardening are separate, bounded follow-ups.
