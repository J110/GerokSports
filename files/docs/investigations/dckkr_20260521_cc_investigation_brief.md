# Claude Code investigation brief — DC vs KKR session post-replay sweep

> **REFRAME NOTICE (2026-05-21, post-C7).** The investigation sequence below is the original brief as authored. **The Step 1 framing (B-η stream-gap reconciliation) has been empirically superseded — see §0 below before reading further.** Original brief preserved verbatim for audit-trail continuity; do not re-execute Steps 1-3 as written. The C7 memo at `files/docs/investigations/stream_gap_reconciliation_design.md` §11-§13 carries the current direction.

**Session under investigation.** `validate_dckkr_20260521_070545`
**Branch.** `derive-not-detect` (HEAD `ccbf054` at brief authorship; current HEAD after C7: `e19f72a`)
**Trace.** `logs/trace/validate_dckkr_20260521_070545.jsonl` (341 records, sha256 in `files/logs/deliveries/validate_dckkr_20260521_070545/checksums.txt`)
**Scout dump.** `files/logs/deliveries/validate_dckkr_20260521_070545/scout_raw.jsonl`
**Observations log.** `files/docs/investigations/dckkr_20260521_session_observations.md` — 11 issues + empirical trace-assertion results
**Entry context.** `HANDOFF.md` and `Architecture_HANDOFF.md` at repo root, then `files/docs/investigations/sm_as_orchestrator_design.md` §7

---

## §0. Reframe — investigation-strategy pivot (2026-05-21, post-C7)

**Status of original Step 1 / Step 2 / Step 3.** The original brief's three-step decomposition (B-η root → B-ι resync → B-θ over-boundary) is **partially falsified and structurally retargeted**. Do not open new design memos for B-η / B-ι / B-θ as originally framed. The C7 memo §11-§13 documents five empirical falsifications produced by the original investigation path:

1. `STREAM-GAP-TOO-LARGE-TO-DECOMPOSE` falsified on gate-7 cross-fixture
2. Shape α single-axis frame-trust falsified at replay f138
3. Shape α' dual-axis frame-trust at `_decompose_multi_ball` falsified — gate never reached
4. Shape β streak-gate tightening falsified — gate fires correctly
5. B-κ split-commit via `sb.set` falsified — 48+81 firings across DCKKR+GTRR, no anomalous signature

The pattern: **every proposed mechanism at a single code site has been falsified by either replay evidence or production-trace evidence.** This is not a methodology problem; it is the empirical signature of a **temporal / async coupling defect class** — the defect lives in the interaction between consensus-tracker confirmation behavior, UDP-stream-frozen windows, Scout 429-retry ordering, and `_handle_warm`'s streak gate state, not at any one of those sites in isolation.

### §0.1 Retargeted Step 1

**OLD:** "Confirm the f304 absorption mechanism" — instrumentation-driven, instrument-then-replay-then-fix.

**NEW:** Static cataloguing of state-mutation sites + invariant classification. Concrete deliverable spec at C7 memo §12.3:

- Enumerate every write site for the five primitive fields (`score`, `wickets`, `overs`, batter identities, bowler identity) across `test_pipeline.py`, `score_manager.py`, `eyes/scoreboard.py`, and any other files that mutate them.
- For each site, classify on four dimensions: mutation target, gate protection, invocation pattern (sync inline / async callback / external-event-driven), source of authority.
- Identify gate-bypass / invariant-violation classes (sites that mutate `sm.score` bypassing the streak gate; sites that mutate `sb._inn["score"]` bypassing the tracker; etc.).
- Output is a catalogue table in `files/docs/investigations/state_mutation_site_catalogue.md`. **No fixes proposed. Pure observability of the system surface.** This is C9 in the post-C7 commit chain.

### §0.2 Retargeted Steps 2 and 3 — same block, stronger reason

**Steps 2 (B-ι resync-prevention) and 3 (B-θ over-boundary bowler credit) remain blocked.** Original rationale: cascade-closure pattern per §7.2 gate 7 — wait until B-η root is confirmed because B-ι and B-θ may be cascade symptoms.

**Strengthened rationale (post-C7):** the cascade root is a temporal-coupling defect *class*, not a single defect. B-ι and B-θ may collapse as cascade symptoms of that class once the static catalogue (§0.1) surfaces the temporal-coupling interactions. Opening B-ι or B-θ memos now would repeat the falsification-treadmill pattern at a different code site.

Steps 2 and 3 remain blocked until **(a)** the C9 catalogue lands AND **(b)** the catalogue surfaces an empirically-grounded candidate site (not just a structurally plausible one).

### §0.3 Retired assumption — "captured-replay drives investigation"

The original brief implicitly assumed the captured-replay path (`scout_raw.jsonl` → `parse_strip` → SM → trace) could drive root-localization. **This assumption is empirically retired.** Five falsifications established that the captured-replay path:

- ✅ Faithfully reproduces parse_strip's regex extraction
- ✅ Faithfully invokes the LLM-fallback extractor at the same frames production used
- ✅ Faithfully exercises `sb.set` tracker / `_handle_warm` streak gate / `_decompose_multi_ball` decomposer
- ❌ **Does not reach the `tracker_score=54` state production reached at the same frame indices**

The captured-replay scaffold remains canonical as **(i)** a falsification mechanism, **(ii)** a regression detector for the trace-session assertion library, and **(iii)** the substrate for Layer 1.5 / Layer 2 pre-commit gates. It cannot drive root-localization for temporal-coupling defects. The next-session investigator should use replay to FALSIFY proposed fixes, not to LOCALIZE proposed roots.

### §0.4 Retained from the original brief

The following standing principles, lists, and references **remain in force** unchanged:

- Standing principles §1 (deduction over detection), §2 (no speculative fixes), §3 (§7.2 seven-gate audit)
- The "What NOT to touch" list at the bottom of the brief
- The empirical baseline (trace assertions on DCKKR, the 3 PASS / 2 FAIL results)
- The cascade map and observations log — useful as historical evidence even though the cascade-mechanism explanation in the original §"Cascade map" section is partially superseded (the f304→f318 chain is real; the mechanism explanation under it is what C7 §10-§11 reframes)

### §0.5 Next-session entry sequence (replaces original "Order of operations")

1. Read this brief (including §0).
2. Read C7 memo `files/docs/investigations/stream_gap_reconciliation_design.md` §10-§13 in full — the empirical record + pivot.
3. Read `HANDOFF.md` + `Architecture_HANDOFF.md` (will be updated post-C7+C8 to reflect the pivot).
4. Run `git log --oneline derive-not-detect | head -10` to see the eight-commit investigation chain (`b49e48b` through C8).
5. **Do not re-execute the original Step 1/2/3.** Begin C9: state-mutation-site catalogue per §0.1.

---

> *Below: original brief content, preserved verbatim. Per §0.5, do not re-execute the Investigation Sequence as written.*

---

## Standing principles (non-negotiable)

1. **Deduction over detection.** When a choice exists between richer Scout primitives and deducing the same fact from existing primitives + per-frame delta math, choose deduction. The contract is 5 primitives (runs, overs, batter identities, bowler identity, first-striker-after-start/post-wicket). Everything else is derived.

2. **No speculative fixes.** Every fix commit must cite specific trace evidence — concrete frame numbers from `logs/trace/validate_dckkr_20260521_070545.jsonl` — that confirms the diagnosed root cause. "Likely" / "probably" language is investigation-only, never authorization to commit. If diagnosis can't be confirmed from existing trace data, **add instrumentation first, re-run, then fix**. This rule applies recursively to bug-class hypotheses, NOT-A-DEFECT verdicts, fix-feasibility claims, and "already addressed" verdicts.

3. **§7.2 seven-gate audit** is the standing precondition for any code change. Read `files/docs/investigations/sm_as_orchestrator_design.md` §7.2 in full before opening any design memo.

---

## Empirical baseline (do not re-derive — already established)

Trace-session assertion run against `validate_dckkr_20260521_070545.jsonl`:

```
trace_epsilon_initial_striker    PASS    F1 direct fix held
trace_compound_tokens            PASS    F1 cascade held
trace_extras_total               PASS    better than predicted
trace_alpha_bowler_runs_sum      FAIL gap=4 (was 24 on GTRR → major improvement)
trace_beta_sm_wicket_dispatch    FAIL — 3 misses (frames 371, 521, 636)
```

**B-β cascade-closure falsified on this fixture.** Per §7.2 gate 7, B-β returns to the engineering queue with its own design memo target. F1 collapse held on GTRR captured-dump replay but did not generalize to this fresh fixture.

**Cascade trigger frame.** f304. Pipeline absorbed ov=4.5 → ov=6.3 (a ~1.8-over gap covering ~10 missed scoreboard frames) as a single `ABSORBED_LEGAL` commit with +5 phantom runs. Pre-f304 the pipeline was clean. Post-f304 every wicket dispatch deferred and every dismissed-batter resolution picked up stale identity.

---

## Cascade map (deduced from trace + observations)

```
f302  ov=4.5  s=49/0  EVT=FOUR              <- broadcast DC 49/0, correct
f303  POISONED                              <- frame guard rejected (root unknown)
f304  ov=6.3  s=54/0  EVT=ABSORBED_LEGAL    <- B-η: gap absorbed as one event, +5 phantom
                                             |
                                             v
                                          SM state {score=54, overs=6.3, striker=stale}
                                          diverges from broadcast truth
                                             |
                                             v
                                          B-ι: deterministic-rotation override at
                                          score_manager.py:4295-4325 locks SM and
                                          rejects every fresh broadcast striker write
                                             |
                                             v
f371  WICKET emitted by Scout, NOT dispatched by SM (B-β-1)
f521  WICKET (bowled) emitted by Scout, NOT dispatched by SM (B-β-2)
f636  WICKET emitted by Scout, NOT dispatched by SM (B-β-3)
                                             |
                                             v
                                          When dispatch finally fires at a later frame,
                                          dismissed-batter resolver reads stale SM striker
                                             |
                                             v
                              FOW chain corrupted (Issues 5, 6, 7, 9)
                              over_history archived rows corrupted (Issue 10)
                              this_over panel corrupted (Issues 4, 8)
                              delivery-metadata channel frozen (Issue 11)
```

Single root: **f304 absorption**. Everything else is cascade.

---

## Investigation sequence (mandatory order — root first, symptoms last)

### Step 1 — Confirm the f304 absorption mechanism

**Hypothesis to confirm.** When the UDP-frame-source has a gap (here: ~1.8 overs of scoreboard frames missing between the FOUR at ov=4.5 and the next-captured frame at ov=6.3), the multi-ball-gap decomposer in `_decompose_multi_ball` does not handle deltas this large and falls back to `_apply_absorbed_event` with a single `ABSORBED_LEGAL` + score delta.

**Confirm by inspecting:**
- `files/score_manager.py:4427+` (`_decompose_multi_ball`) — find the threshold above which decomposition is skipped
- `files/score_manager.py:5176+` (`_apply_absorbed_event`) — confirm the fallback path commits a score delta without per-ball decomposition
- Trace `decisions` at f303 (POISONED) — what guard fired? Why? Was the POISON a symptom of the missing frames or a contributor?
- `UDP-STREAM-FROZEN` tag fired 113× this session — quantify which periods of the stream had how many freezes. Was f303 inside a freeze window?

**Predicted flip if root is confirmed.** A `STREAM-GAP-TOO-LARGE-TO-DECOMPOSE` trace tag (new) should be emit-able at f304 with `delta_balls=10, delta_runs=5, delta_wickets=1`. The fact that wickets=1 is in the delta but never showed up in commits is the root signal.

**Do not write code yet.** Open a design memo at `files/docs/investigations/stream_gap_reconciliation_design.md` documenting:
- The current decomposer threshold
- The current fallback path
- Frame numbers (302, 303, 304) with raw scorer.decisions payloads from the trace
- Three or more candidate fix shapes, with §7.2 7-gate audit applied to each
- Cross-fixture check (gate 7) — does this pattern exist in GTRR trace at `logs/trace/validate_gtrr_20260520_180715.jsonl`? Search for `ABSORBED_LEGAL` commits with `delta_overs > 0.6` and report findings.

### Step 2 — Confirm the B-ι resync-prevention mechanism

**Hypothesis to confirm.** The deterministic-rotation override at `score_manager.py:4295-4325` (commit `2105463`) rejects all broadcast striker writes once `self.striker is not None`. When SM state diverges from broadcast by >N runs / >M overs / wrong dismissed-batter, the override has no unlock condition, so SM stays stuck.

**Confirm by inspecting:**
- `score_manager.py:4295-4325` — read the override logic and find the audit-only `STRIKER-BROADCAST-DISAGREES-DETERMINISTIC` tag
- Count `STRIKER-LOCK-MID-OVER-SUPPRESSED` fires in the trace (76 already counted) and partition by frame range pre/post-f304
- Find every frame post-f304 where the broadcast strip's striker identity differs from SM's `striker` — these are the rejected-resync candidates
- Inspect `_identify_and_set` Priority 1/2/3 — is there ANY existing unlock path or is the override absolute?

**Predicted flip if root is confirmed.** Adding a divergence-threshold unlock condition (e.g., "if SM_score and broadcast_score differ by >5 runs across N consecutive frames, force resync") should allow B-β missed dispatches at frames 371/521/636 to be replayed correctly.

**Do not write code yet.** Open a design memo at `files/docs/investigations/sm_resync_unlock_design.md`. Address the standing principle: "Once high confidence reached, LOCKED — only explicit events unlock" needs a corollary: what counts as an explicit unlock event? Three or more candidate unlock-condition shapes; §7.2 7-gate audit on each.

### Step 3 — Confirm the B-θ over-boundary bowler credit defect

**Hypothesis to confirm.** End-of-over commits credit the next over's bowler (read at the over-crossing frame) for the final ball of the previous over. f176 (ov=2.0 s=17 EVT=1_RUNS bowler=ANUKUL) is the canonical example — the over-2 last ball was bowled by Vaibhav per ground truth but credited to Anukul.

**Confirm by inspecting:**
- Every frame in the trace where the committed `overs` value is `N.0` (integer boundary)
- For each, what's the proposed `bowler.name` vs the bowler at the prior frame `N-1.5` (last ball of previous over)?
- If they differ, that's a B-θ instance — count occurrences across the session

**Predicted flip if root is confirmed.** `trace_alpha_bowler_runs_sum` gap of 4 runs should reduce or close if B-θ is fixed correctly. Per-bowler over totals printed in the assertion failure (`Anukul Roy: 32, Vaibhav Arora: 9, ...`) cross-checked against Cricbuzz ball-by-ball will localize who got over-credited and by how much.

**Do not write code yet.** Open a design memo at `files/docs/investigations/over_boundary_bowler_credit_design.md`. §7.2 7-gate audit. Note: the fix may be cascade-closure of Issue 1 by fixing B-η/B-ι first — verify before opening engineering work.

### Step 4 — Cross-fixture verification (§7.2 gate 7) before any code

Before any code commit lands for B-η, B-ι, or B-θ:

```
python3 files/scripts/run_trace_session_assertions.py logs/trace/validate_dckkr_20260521_070545.jsonl
python3 files/scripts/run_trace_session_assertions.py logs/trace/validate_gtrr_20260520_180715.jsonl
```

Both must run; predicted-flip deltas must be cited in the commit message for each fix. If a fix flips B-β in DCKKR, it must also not regress GTRR. Layer 1.5 + Layer 2 pre-commit gates are non-negotiable; never `--no-verify`.

### Step 5 — Address symptom-tier issues only after roots fix

Issues 4 (this_over overflow), 8 (`?` placeholders), 10 (archived over_history corruption), 11 (delivery-metadata frozen) are all downstream symptoms. **Do not touch them until B-η + B-ι are confirmed fixed via cross-fixture assertion flips.** Cascade-closure pattern (per §7.2 gate 7) likely collapses several of these into the root fix.

---

## What NOT to touch

Per `HANDOFF.md` "What NOT to touch" + this session's findings:

- F1's field-name fix at `_accept_initial:2789-2808` — the cascade-closer. Do not revert, do not edit.
- Queue B (`_pending_bowler_ball_credits`) — load-bearing 3-way-race resolver per §7.1
- `_ScoutRetryBuffer` — active queue across Groq 429 backoff per §7.1
- `broadcast_extra` / `extras_type` — parallel fields per §7.5, not aliases
- Cold-start synth token-distribution heuristic in `_synthesize_cold_start_ball_events` — the only allowed heuristic site
- `confidence_tracker.py` ConfidenceTracker class — foundational
- Pre-commit hook — Layer 1.5 + Layer 2 gates
- F-α-shadow fix in `_capture_multi_ball_shadow_state:4515+`
- F-α-queue in the new `_apply_absorbed_event` elif branch

---

## Deliverables expected from this investigation

For each of B-η, B-ι, B-θ (in that order):

1. **Design memo** at `files/docs/investigations/<bug_name>_design.md` with:
   - Empirical evidence section citing concrete frame numbers from the trace
   - Mechanism section showing how the bug produces the observed symptom
   - §7.2 7-gate audit applied to the candidate fix(es)
   - Predicted flip claims with concrete frame numbers (gate 6)
   - Cross-fixture check result against GTRR trace (gate 7)
   - Three or more candidate fix shapes — choose only after audit
2. **Trace-tag additions** if instrumentation is needed before a fix can be authorized — instrumentation commits go first, re-run replay, then fix.
3. **New trace-session assertion** in `files/tests/trace_session_assertions.py` covering the bug class. Add to `SESSION_CONTEXT` discipline.
4. **Fix commit** only after design memo + audit + predicted-flip-with-frame-numbers + cross-fixture check + new assertion are in place. Commit message cites the trace evidence.

---

## Order of operations (strict)

1. Read this brief in full
2. Read `HANDOFF.md`, then `Architecture_HANDOFF.md`, then `sm_as_orchestrator_design.md` §7.2 (the seven-gate audit)
3. Read `dckkr_20260521_session_observations.md` (11 issues + assertion results)
4. `git log --oneline derive-not-detect | head -30` for full session-2 commit context
5. Begin Step 1 above — do not jump to Step 2 or beyond until Step 1's design memo and gate-7 cross-fixture check are complete
6. Pause for user review after each design memo. Do not chain memo → code without explicit authorization.

---

## Quick reference — falsified hypotheses from this session

The next agent should treat these as discipline anchors, not as code to revisit:

- B-β was "cascade-closed by F1" on GTRR captured-dump replay (HANDOFF §8.2 prediction). **Falsified on DCKKR** — predicted-flip violation. Per §7.2 gate 7, returns to engineering queue with own design memo.
- B-α "significant gap reduction" prediction held — gap from 24 to 4 runs. Not closure though; B-θ over-boundary credit is the likely residual contributor.
- `trace_extras_total` "stays FAIL (UI render layer)" prediction was **better than predicted** — flipped to PASS. UI render layer claim needs revisiting.

The discipline rule: predictions are hypotheses, every claim is testable, gate 7 catches them when they fail to generalize.

---

## Session wrap

Replay paused at ov=14.0. Workstream now has empirically-grounded next steps with concrete frame numbers. No engineering work should land until Step 1's design memo lands first. The next move is investigation, then audit, then memo, then maybe code.
