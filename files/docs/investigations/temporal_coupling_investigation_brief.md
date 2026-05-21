# Temporal-coupling investigation brief

**Status.** C10 — sixth hypothesis in the B-η investigation chain. Static-analysis-first. **No instrumentation, no replay, no fix.**
**Date.** 2026-05-21
**Author.** J110 via Claude Code
**Inherits.** The eight-commit B-η chain (`b49e48b` → `af19dd2`) and its **five empirical falsifications**.

---

## 1. Inheritance acknowledgement (mandatory pre-read)

This brief inherits an investigation chain whose previous five hypotheses have all been empirically falsified. **The candidate proposed here (temporal coupling inside `ConsistentReadTracker`'s fast-confirm bypasses) is the sixth hypothesis, treated as pending empirical verification, not as a confirmed root.**

### 1.1 Five-falsification track record

Per C7 memo §13:

| # | Hypothesis | Falsification mechanism |
|---|---|---|
| 1 | `STREAM-GAP-TOO-LARGE-TO-DECOMPOSE` | Gate-7 cross-fixture: GTRR has working 10/11-ball absorptions |
| 2 | Shape α single-axis frame-trust | Replay f138 mixed-signal benign gap |
| 3 | Shape α' dual-axis frame-trust at `_decompose_multi_ball` | §10.2 evidence: gate never reached at f304 |
| 4 | Shape β streak-gate tightening | §10.2 evidence: streak gate fires correctly |
| 5 | B-κ split-commit via `sb.set` | §11.2 evidence: 48+81 firings, no anomalous signature |

### 1.2 Falsification budget

**If C10 produces a sixth falsification, retire the methodology entirely.** Per C7 §13 and C9 §11, the next move after a sixth would be to expand the catalogue scope to `cricket_rules.py`, `eyes/this_over.py`, `eyes/confidence_tracker.py` (the team-confidence tracker, distinct from ConsistentReadTracker) before any further hypothesis is proposed.

### 1.3 The candidate as a hypothesis, not a root

C9 §8 surfaced `test_pipeline.py:7211-7234` (the bowler/striker `on_lock` callback bindings on `ConfidenceTracker`) as the leading match for "temporal coupling". **§3 of this brief partially falsifies that candidate via static analysis** — the on_lock fires synchronously, not async — and replaces it with a different, more empirically plausible candidate: `ConsistentReadTracker`'s post-gap grace + natural-increment fast-confirm paths. **Both candidates are hypotheses pending verification.** This brief's job is to make the static-analysis trail explicit so the next investigation pass can decide which (if either) to verify empirically.

---

## 2. C10 deliverable scope

Per the operator directive that authorized this brief:

- ✅ **Static analysis first.** Captured-replay is empirically established as unable to reproduce temporal coupling (C7 §0.3). A fresh live session is too expensive to authorize before the candidate is structurally grounded.
- ✅ **Trace the on_lock callback registration site** (`test_pipeline.py:7211-7234`) — what triggers it, threading/scheduling primitive, concurrency with main loop.
- ✅ **Trace `ConfidenceTracker.on_lock` invocation pathways** (`files/confidence_tracker.py`) — state held between reads, consensus-state-machine semantics under UDP-stream-frozen, repeated-read accumulation behavior.
- ✅ **Identify concrete ordering interleavings** that could produce SM `score=54` while broadcast `score=49`. With static-evidence trail.
- **Empirical step deferred.** Once §6 produces a concrete candidate failure mode with code-path-trace evidence, decide between (a) constructing a captured-replay variant with synthetic FrameInput timing perturbation, (b) authorizing live-session instrumentation, or (c) the static analysis itself disproves the candidate.

---

## 3. Static analysis — `ConfidenceTracker.on_lock` (C9 §7.2 candidate)

### 3.1 Registration site

`test_pipeline.py:7211-7234`:

```python
def _on_bowler_lock(_name: str) -> None:
    try:
        score_mgr._resweep_pending_attribution(_name, "bowler")
        score_mgr._drain_pending_queue("bowler_lock")
        score_mgr._drain_pending_bowler_ball_credits(_name)
    except Exception:
        pass

def _on_striker_lock(_name: str) -> None:
    try:
        score_mgr._resweep_pending_attribution(_name, "striker")
        score_mgr._drain_pending_queue("striker_lock")
    except Exception:
        pass

bowler_tracker.on_lock = _on_bowler_lock
striker_tracker.on_lock = _on_striker_lock
```

Two callbacks. Both mutate SM state via `_resweep_pending_attribution` and `_drain_*_queue` methods.

### 3.2 Invocation pathway

`files/confidence_tracker.py:168-174`:

```python
# B1.3 §2.8: fire on_lock on False→True transition of _locked.
if (self.on_lock is not None and not _pre_locked
        and self._locked and self._leader is not None):
    try:
        self.on_lock(self._leader)
    except Exception:
        pass
```

**The on_lock callback fires synchronously inside `observe()`** — same Python call stack, same thread, same event-loop tick. Not async-decoupled.

### 3.3 What invokes `observe()`?

`grep -n "bowler_tracker\.observe\|striker_tracker\.observe"` in `test_pipeline.py`:

- Line 13698: `bowler_tracker.observe(_sb_current_bowler, weight=5.0)` — bowler-tracker reseed on scoreboard override
- Line 13764: `striker_tracker.observe(...)` — striker-tracker per-frame observation
- Line 13786: `non_striker_tracker.observe(...)` — non-striker-tracker per-frame
- Line 13797: `bowler_tracker.observe(...)` — bowler per-frame

All four are inside the `async def run_test()` coroutine's main frame-processing loop. No `threading.Thread`, no `run_in_executor`, no `loop.create_task` for these calls. They are sync invocations from the single asyncio event loop.

### 3.4 Threading model verification

`grep -n "threading.Thread\|run_in_executor\|ThreadPoolExecutor"` in `test_pipeline.py / eyes/agent.py / eyes/vision.py` returns no matches in production code. The pipeline runs single-threaded in an asyncio event loop. Per-frame work is sequential. The only "concurrent" operations are awaited coroutines (Groq API calls, WebSocket sends) which yield control but do not run on a separate thread.

### 3.5 Partial falsification of C9 §7.2 as stated

C9 §7.2 hypothesized that the on_lock callbacks are "**temporally decoupled** from the main loop's frame-arrival ordering". **This is false as stated.** The callbacks fire on the same call stack as `observe()`, which fires from the main loop. There is no temporal decoupling.

**What remains true.** The callbacks fire *between* the `observe()` call and the subsequent SM processing within the same frame. They mutate SM state intra-frame. This is an **intra-frame ordering coupling**, not inter-frame async coupling. The cascade root, if at this site, would manifest as: an on_lock callback mutates state in a way that the subsequent same-frame SM logic does not anticipate.

### 3.6 What the on_lock callbacks actually mutate

- `_resweep_pending_attribution(_name, "bowler"|"striker")` — resweeps pending balls with a newly-locked identity. Mutates pending-ball-queue entries.
- `_drain_pending_queue(...)` — drains the pending-ball queue. Indirectly mutates `sb.batting_card[name]["runs"]`, `sb.bowling_card[name]["runs"]`, etc. via `_apply_*_delta`.
- `_drain_pending_bowler_ball_credits(_name)` — drains Queue B (`_pending_bowler_ball_credits`). Mutates `sb.bowling_card[name]["runs", "balls", "wickets"]`.

**Critically: none of these mutate `sb._inn["score"]`, `sb._inn["overs"]`, `sb._inn["wickets"]`, or the SM's `self.score`/`self.overs`/`self.wickets` primitives.** The on_lock callbacks operate on per-batter / per-bowler card stats and on pending-queue state, NOT on the five-primitive score/wickets/overs.

### 3.7 Conclusion for the C9 §7.2 candidate

**The on_lock callback hypothesis is falsified for the score-mutation route by static-evidence trail.** The callbacks (a) fire synchronously, not async (§3.2-§3.4), and (b) do not mutate the primitive fields whose divergence (sm.score=54 / sm.overs=4.5) is the f304 cascade signature (§3.6). The candidate cannot produce the observed B-η defect.

**This would be the sixth falsification if it were a deliberate hypothesis pursued via instrumentation.** Because the falsification is purely static (no instrumentation commit, no replay, no fix), it does not count against the falsification budget. Static analysis is doing exactly what the C7 §12 pivot called for — surfacing the wrong candidate cheaply before it becomes a commit chain.

---

## 4. Static analysis — `ConsistentReadTracker` (the actual candidate)

§3 surfaced that the on_lock route doesn't touch score/overs/wickets. The candidate must therefore be a path that DOES touch those — and `sb.set("score", ...)`'s consensus tracker is the only gate-protected path that reaches them. The instrumentation at C6 (`237d227`) showed `sb.set` works correctly when called once per frame. The temporal coupling, if any, lives **inside the tracker's state machine** — specifically in the conditions under which it accepts a value on a single read (bypassing the 2-frame consensus).

`files/eyes/consistent_tracker.py` is the tracker. Inspection reveals **five distinct fast-confirm paths** that can commit a value on a single read, bypassing the 2-frame consensus.

### 4.1 The five fast-confirm paths

| # | Site | Trigger condition | What gets bypassed |
|---|---|---|---|
| FC1 | Line 114-123 — **DRS grace** | `_post_gap_grace > 0` AND `_is_drs_pattern(field, value)` | 2-frame consensus; commits on single read |
| FC2 | Line 228-237 — **Natural batter increment** | `_is_natural_batter_increment(field, current, value)` returns True | 2-frame consensus |
| FC3 | Line 252-261 — **Natural bowler increment** | `_is_natural_bowler_increment(field, current, value)` returns True | 2-frame consensus |
| FC4 | Line 273-289 — **Natural overs increment** (`OVERS-NATURAL-INCREMENT-FAST-CONFIRM` trace tag) | `_is_natural_overs_increment(field, current, value)` — within-over +0.1 or rollover X.5 → (X+1).0 | 2-frame consensus |
| FC5 | Line 294-306 — **Post-event grace** | `_post_event_grace > 0` AND `not _is_suspicious(field, current, value)` | 2-frame consensus |

### 4.2 The trigger conditions matter

**FC1 (DRS grace).** `_post_gap_grace` is set to 3 at lines 108-111 when `_no_data_streak >= 5`. **UDP-STREAM-FROZEN produces no-data windows.** The production DCKKR session had 113 UDP-STREAM-FROZEN tags, distributed across the trace (per the analyzer output the operator captured earlier). Some bursts must reach ≥5 consecutive frames of no-data → grace mode is on → next non-suspicious value-matching-`_is_drs_pattern` commits on single read.

**FC5 (post-event grace).** `_post_event_grace` is set after a ball event. The trace shows ball events firing on legitimate deliveries; the grace counter would be positive in the frames immediately after a real ball commit.

**FC2, FC3, FC4** depend on `_is_natural_*_increment` matching the value-shape. f304's proposed score=54 (current was 49) is a +5 jump — NOT a natural single-ball increment for score (BATTER_SINGLE_BALL_RUN_MAX=6 but score moves via batter+extras), but POSSIBLY natural under specific conditions.

### 4.3 The fast-confirm + UDP-stream-frozen interaction

The production session's UDP-STREAM-FROZEN tags fire when the UDP frame source can't deliver a new frame within the read timeout. Scout subsequently retries (we see `SCOUT-RETRY-IN-CALL-QUEUED` + `SCOUT-RETRY-IN-CALL-SUCCESS` in the trace). During the retry window:

- The ConsistentReadTracker's `update()` is called from `sb.set()` whenever a score/overs/wickets value lands.
- If the retry window contains 5+ frames where `value is None` (Scout failed to extract anything), the tracker's `_no_data_streak >= 5` triggers and `_post_gap_grace = 3` is set.
- The next 3 non-None reads enter grace mode. If any matches `_is_drs_pattern`, it commits on a single read.

### 4.4 `_is_drs_pattern` — the gate's gate

The exact predicate determining what counts as a "DRS pattern" is the next static-analysis question. Without this code-path trace, the hypothesis "f304's score=54 was accepted via DRS grace" cannot be confirmed. **This is the concrete next-step deliverable** — read `_is_drs_pattern` and document what value-shapes it accepts post-gap.

### 4.5 The `_is_natural_overs_increment` already fired in production at f302

Production f302 trace had `OVERS-NATURAL-INCREMENT-FAST-CONFIRM` (visible in our earlier extraction). This confirms FC4 fires in the production session. f302 was an overs 4.4 → 4.5 increment — legitimate. **But the existence of fast-confirm at f302 establishes that the production session DID use fast-confirm paths. Whether f304's overs 4.5 → 6.3 jump matched any fast-confirm path is the cascade question.**

Looking at `_is_natural_overs_increment` semantics from the docstring (line 263-272): "within-over +0.1 or over-rollover X.5 → (X+1).0". The 4.5 → 6.3 jump is neither — it's +1.5 overs across two over-boundaries. **So FC4 should not have fired at production f304.** Need to read the actual `_is_natural_overs_increment` to verify.

---

## 5. Candidate failure modes for empirical pursuit

Three concrete ordering interleavings, ranked by static-evidence weight:

### 5.1 Failure mode α — DRS grace + score-only single-read commit (highest weight)

**Pre-condition.** A 5+ frame UDP-STREAM-FROZEN burst before f304 sets `_post_gap_grace = 3`.

**Sequence.**
1. Frames f300-f303 (or earlier): UDP-STREAM-FROZEN ≥5 times → `_no_data_streak ≥ 5` → grace = 3 at next non-None read.
2. f304: Scout returns `score=54, overs=6.3` (the bad PANT/WARD/SHAMI overlay anchor).
3. Test_pipeline.py calls `sb.set("score", 54, 304)` AND `sb.set("overs", "6.3", 304)` AND `sb.set("wickets", 0, 304)`.
4. For `score` field: tracker.update enters grace path (FC1). If `_is_drs_pattern("score", 54)` returns True → tracker confirms 54 on single read. **sb._inn["score"] becomes 54.**
5. For `overs` field: tracker.update enters grace path. If `_is_drs_pattern("overs", "6.3")` returns False (because 4.5 → 6.3 is too large a jump for DRS-pattern), tracker holds 6.3 as candidate. **sb._inn["overs"] stays at 4.5.**
6. Result: **sb._inn["score"]=54, sb._inn["overs"]=4.5** — exactly the split-commit signature the f318 trace cited.
7. SM's downstream processing reads sb._inn["score"]=54 → SM commits self.score=54. But SM's _handle_warm streak gate also runs on (overs jump) → rejects. SM's self.overs stays at 4.5.

**Static-evidence checks needed (next deliverable).**
- Read `_is_drs_pattern("score", 54)` actual semantics in `consistent_tracker.py`.
- Read `_is_drs_pattern("overs", "6.3")` actual semantics.
- Confirm the UDP-STREAM-FROZEN distribution in the production trace contains a 5+ frame burst immediately before f304.

### 5.2 Failure mode β — Cross-field gate partial satisfaction

**Pre-condition.** Cross-field gate at line 161-184 holds score/wickets/overs in `_gate_holding` until all three reach cold-start consensus.

**Sequence.**
1. Cold-start: tracker has no `confirmed` entries for score/wickets/overs. First reads enter `_initial_consensus`.
2. f304 + later frames: tracker accumulates consensus for `score=54` BUT not for `overs=6.3` (the streak gate keeps proposing 4.5).
3. At some point, the cross-field gate gets satisfied: `_gate_holding["score"]=54, _gate_holding["wickets"]=0, _gate_holding["overs"]=?`. If `overs` reaches consensus on `4.5` while `score` is at `54` in `_gate_holding`, all three commit together: `confirmed["score"]=54, confirmed["overs"]=4.5, confirmed["wickets"]=0`. **Split-commit by design.**

**Static-evidence checks needed.**
- Read the cross-field gate logic at lines 161-184 in full.
- Check whether the production session's `_initial_consensus` ever held score=54 while overs=4.5 at any same-frame moment.

### 5.3 Failure mode γ — Post-event grace + natural-batter-increment cascade

**Pre-condition.** A real ball event at f300/f302 sets `_post_event_grace > 0`. f304's batter rows (PANT, WARD, SHAMI) get squad-rejected (empty extracted batters), but the score=54 reading passes through some non-suspicious path.

**Static-evidence checks needed.**
- Read `_is_suspicious("score", 49, 54)` — would a +5 score delta with current=49 be suspicious?
- Confirm post-event grace was active at f304 (counter > 0).

---

## 6. §7.2 7-gate audit framework for any C11 instrumentation candidate

If §5's failure modes survive the next static-analysis pass (reading `_is_drs_pattern` + `_is_suspicious` + the cross-field gate), the next move would be either targeted instrumentation OR a replay variant with synthetic timing. **Whatever lands must pass §7.2 7-gate audit. The five-falsification track record means gate 6 (predicted-flip with concrete frame numbers) is non-negotiable.**

Pre-audit candidate instrumentation tags (NOT to be shipped without §7.2):

- `TRACKER-FAST-CONFIRM-FIRED` — at FC1/FC2/FC3/FC4/FC5 entry, emit `path`, `field`, `value_before`, `value_after`, `frame_id`, `grace_counter`, `no_data_streak`.
- `TRACKER-CROSS-FIELD-GATE-STATE` — at the gate-holding logic, emit `score_held`, `wickets_held`, `overs_held` per frame.
- `UDP-STREAM-FROZEN-CASCADE-RUN` — emit when consecutive UDP-STREAM-FROZEN reach 5 (the grace trigger).

**None of these should be added until §5's failure modes are either confirmed-plausible-by-static-evidence or disproven-by-static-evidence.** The discipline rule: instrumentation follows hypothesis confirmation, not the other way around. C6's instrumentation was the cheapest empirical step; further instrumentation is more expensive per falsification.

---

## 7. Decision tree after the next static-analysis pass

The next deliverable (C11, deferred until operator review) is a static-analysis read of:

1. `_is_drs_pattern` — file `eyes/consistent_tracker.py`, exact predicate semantics
2. `_is_suspicious` — same file, exact predicate semantics
3. `_is_natural_overs_increment` — same file, exact predicate semantics
4. Production UDP-STREAM-FROZEN distribution audit — `logs/trace/validate_dckkr_20260521_070545.jsonl`, find consecutive bursts ≥5

Three outcomes:

**Outcome A — Static evidence confirms one of §5's failure modes.** Open C12 with the failure mode named + the gate-6 predicted-flip claim. THEN audit candidate instrumentation against §7.2 7 gates. Land instrumentation. Re-replay. Verify or falsify.

**Outcome B — Static evidence disproves all three of §5's failure modes.** Either the static analysis revealed a fourth failure mode not anticipated here, or the candidate site (`ConsistentReadTracker` fast-confirm paths) is itself wrong. **Sixth falsification.** Retire the methodology per §1.2 budget. Expand catalogue scope (`cricket_rules.py`, `eyes/this_over.py`, `eyes/confidence_tracker.py`).

**Outcome C — Static evidence is ambiguous.** A predicate semantics can be read but its behavior on f304's specific values can't be determined without running the predicate. In this case: write a unit test that exercises the predicate with f304's exact values (score=49 current, score=54 proposed, overs=4.5 current, overs=6.3 proposed, _no_data_streak=5+). This is a one-commit deliverable that requires no production-pipeline change.

---

## 8. What this brief is NOT

- **Not a fix proposal.** Per §1.3 / C7 §12 / C9 §10 / discipline track record.
- **Not an instrumentation authorization.** §6/§7 explicitly defer.
- **Not a replay-variant authorization.** §2 reaffirms the C7 §0.3 retired-assumption: captured-replay does not drive root-localization for temporal coupling.
- **Not a live-session authorization.** Production-session expense gated on §7 Outcome A.
- **Not a HANDOFF update.** Per operator directive, HANDOFF rewrite deferred to next clean pause point.

---

## 9. Order of operations (strict — for the next investigation pass)

1. Read this brief + the C7 memo §11-§13 + the C9 catalogue.
2. Read `eyes/consistent_tracker.py` lines 108-310 in full (the fast-confirm paths + their gate predicates).
3. Read `_is_drs_pattern`, `_is_suspicious`, `_is_natural_overs_increment` definitions in full.
4. Audit production UDP-STREAM-FROZEN distribution against f300-f320 timestamps.
5. Apply §7 decision tree.
6. If Outcome A: open C12 with §7.2 7-gate audit. If Outcome B: declare sixth falsification, retire methodology. If Outcome C: write the unit test.
7. **Do not propose code shapes for `sb.set` / `_handle_warm` / `_decompose_multi_ball` / `ConsistentReadTracker` until Outcome A has been reached.**

---

## 10. Discipline closing

This brief is hypothesis #6. The previous five each looked architecturally reasonable when proposed. Each was empirically falsified before becoming a fix. The cost was six diagnostic/docs commits and one week of investigation; the alternative was multi-session cascade-symptom iteration after a wrong fix landed.

If hypothesis #6 falsifies too, the empirical signal is that the discipline-driven investigation methodology has exhausted its yield for this defect class. The next-session HANDOFF would then carry **the retirement of this methodology** as its headline architectural finding, paired with C9's expansion-scope recommendation. That is itself an architectural insight worth preserving — five falsifications saved five wrong fixes; a sixth would signal the methodology has done its job and the next defect class needs a different approach (likely production-pipeline reproduction against the captured video — the "fresh session" path the original brief explicitly avoided).

Read this brief honestly. Hypothesis #6 has more static-evidence weight than #1-#5 had at proposal time — but that is the criterion by which #1-#5 also looked reasonable at proposal. The discipline does not rest on proposal quality. It rests on empirical confirmation.
