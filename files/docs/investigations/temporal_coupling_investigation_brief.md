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

---

## 11. C11 static-analysis pass — predicate semantics + UDP-frozen distribution audit

Per §7 decision tree, the C11 deliverable is reading the three predicate definitions + auditing the production UDP-STREAM-FROZEN distribution near f300-f320.

### 11.1 Predicate semantics — applied to f304's exact values

`files/eyes/consistent_tracker.py`:

**`_is_drs_pattern` (line 765-780)** — accepts only narrow decrements:
- score: `abs(new - old) <= 2`
- overs: `0 < old - new <= 0.1` (backwards by at most 0.1)
- wickets: `old - new == 1` (exact -1)

Applied to f304:
- score (old=49, new=54): `abs(54-49) = 5` > 2 → **False**
- overs (old=4.5, new=6.3): `4.5 - 6.3 = -1.8`, not in (0, 0.1] → **False**
- wickets (old=0, new=0): `0 - 0 = 0`, not == 1 → **False**

**FC1 DRS-grace falsified for all three fields at f304.** Failure mode α (§5.1) is **statically disproven**. The 5-frame `_no_data_streak` does activate `_post_gap_grace`, but the `_is_drs_pattern` predicate is too narrow to admit the f304 value-shapes.

**`_is_natural_overs_increment` (line 717-746)** — exactly +0.1 within-over or X.5→(X+1).0 rollover.

Applied to f304: overs 4.5 → 6.3 has new_whole=6 ≠ old_whole=4 and ≠ old_whole+1 → **False**. **FC4 falsified for f304's overs.** (FC4 did fire at f302 for the legitimate 4.4→4.5 — confirmed in the trace — but cannot accept the f304 jump.)

**`_is_suspicious` (line 518-683)** — the critical predicate:

| Field | Rule | f304 case (old → new) | Result |
|---|---|---|---|
| score, decrease | `new_f < old_f` | 49 → 54 | False (no decrease) |
| score, huge jump | `new_f - old_f > 30` | 49 → 54 | False (delta=5, well under 30) |
| overs, backwards | `new_f < old_f` | 4.5 → 6.3 | False (forward) |
| wickets, regression | `new_f < old_f` | 0 → 0 | False |

**`_is_suspicious` returns False for f304's score=49→54 AND overs=4.5→6.3.** This is the decisive empirical finding.

### 11.2 FC5 post-event grace — confirmed wired to per-ball commits

`test_pipeline.py:12953` calls `scoreboard._tracker.on_ball_event()` on every legal-ball commit. `on_ball_event` at `consistent_tracker.py:782-786` sets `self._post_event_grace = 2`.

Decrement semantics (line 302): `_post_event_grace -= 1` ONLY when FC5 actually commits a value. The counter does NOT decrement on tracker.update calls that reach other paths (cold-start, suspicious-consensus, pending-defer).

**Production f300-f304 sequence reconstruction:**

| Frame | Event | Effect on `_post_event_grace` |
|---|---|---|
| f300 (or earlier) | First legal-ball commit (after warm seed) → `on_ball_event()` | grace = 2 |
| f300 | Score 45 (ov=4.4) confirms | Grace persists or decrements per FC5 fire |
| f302 | Score 45→49 ball commit → `on_ball_event()` | grace = 2 (reset) |
| f302 | OVERS-NATURAL-INCREMENT-FAST-CONFIRM fires for overs 4.4→4.5 | FC4 fires, not FC5; grace unchanged |
| f302 | Score commit 45→49 — likely via FC5 (post-event grace + not suspicious) | grace = 1 |
| f303 | POISONED — score=89 hallucination blocked upstream of sb.set; tracker.update never called | grace unchanged = 1 |
| f304 | tracker.update("score", 54, 304): _post_event_grace=1 AND _is_suspicious returns False → FC5 commits | sb._inn["score"]=54, grace=0 |
| f304 | tracker.update("overs", "6.3", 304): _post_event_grace=0 → FC5 path skipped | sb._inn["overs"] stays 4.5 (other paths reject) |

**Wait — that decrement sequence puts grace at 0 by the second f304 call.** If grace is 0 when `tracker.update("overs", "6.3", 304)` fires, FC5 cannot accept overs. Yet production trace at f318 shows `tracker_overs=6.3`. So overs landed via a different path.

**Outcome A (qualified): FC5 confirmed for the score commit at f304. The overs commit requires a separate static-evidence trail.**

### 11.3 Refined Outcome A — the cascade is FC5-on-score + something-else-on-overs

The f304 cascade is now empirically anchored on the SCORE side:

- **sm.scoreboard._inn["score"] = 54** is **statically confirmed** to land via FC5 at f304 with the post-event grace inherited from f302's ball event. Predicate semantics verified, on_ball_event wiring verified.

For the overs side, three sub-candidates:

1. **FC5 fired at f303 instead of f304.** If at f303 some non-suspicious overs value triggered FC5 (unlikely since f303 was POISONED, but worth verifying the upstream gate path).
2. **A different FC path admitted the overs jump.** FC2 / FC3 / FC4 all falsified for the overs value-shape; this leaves the cold-start `_initial_consensus` path (only fires if `field not in self.confirmed` — false post-warm-seed) or the 4-frame `[CONSENSUS]` override (would need 4 consecutive (6.3) reads, which the production trace doesn't show).
3. **The overs got committed later, after the score was at 54.** Production sequence between f304 and f318 may have a frame where FC5 fired for overs (after another on_ball_event reset). The C9 catalogue shows `test_pipeline.py:11750` is an end-of-over wickets/overs hook that calls sb.set without going through the streak gate — possibly fires between f311 and f318.

### 11.4 UDP-STREAM-FROZEN distribution audit (f290-f325)

Per-frame UDP-STREAM-FROZEN counts in production:

```
f299: 1 frozen, cadence 9062ms, scout 8017ms, ext=(45, 4.4)
f300: 0 frozen, cadence 1992ms, ext=(45, 4.4)
f301: 2 frozen, cadence 9345ms, ext=(None, None)  ← STANDINGS-ROW-GATE
f302: 2 frozen, cadence 5533ms, ext=(None, None)  ← STANDINGS-ROW-GATE + FC4 fires for overs
f303: 2 frozen, cadence 4619ms, ext=(89, 10.2)    ← POISONED
f304: 2 frozen, cadence 10601ms, ext=(54, 6.3)    ← the bad anchor
f308: 0 frozen
f311: 3 frozen, ext=(None, None)                  ← STANDINGS-ROW-GATE
f318: 1 frozen
```

**The `_no_data_streak` interpretation needs clarification.** The streak counter increments in `tracker.update` when `value is None`. STANDINGS-ROW-GATE strips score/overs/wickets to None upstream of sb.set, but the production-pipeline code may or may not call sb.set with the stripped values. If sb.set is NOT called when extractor returns None, the streak doesn't increment. **This is the unresolved upstream-trace question** — and resolving it is part of C12.

Importantly: §11.1 already falsified FC1 DRS-grace via `_is_drs_pattern`, so the `_no_data_streak >= 5` activation question is moot for failure mode α. The mode-γ (FC5 post-event grace) candidate does NOT depend on `_no_data_streak`.

### 11.5 The FC4-at-f302 → FC5-at-f304 interaction (operator's sequencing observation)

Per the operator's note: "the candidate may not be α/β/γ as currently named but a specific interaction between FC4 at f302 and FC1 (DRS grace) at f303-f304."

Static analysis confirms a refined version of that interaction, but the late-stage is FC5 not FC1:

- **f302 FC4 fire**: legitimate overs 4.4→4.5 fast-confirm. Sets the stage for `on_ball_event()` to fire after the score-side commit (45→49) at the same frame.
- **f302 on_ball_event**: triggered by the legitimate ball commit at this frame. Resets `_post_event_grace = 2`.
- **f303 POISONED**: blocks score read upstream of sb.set; tracker.update never called for score; `_post_event_grace` does not decrement.
- **f304 FC5 fire**: the inherited grace, combined with `_is_suspicious("score", 49, 54) = False`, admits score=54 on single read.

**The cascade is a legitimate-ball-event-at-f302 grace-priming feeding the bad-overlay-frame-at-f304 single-read score commit.** Two normal mechanisms (FC4 fast-confirm + on_ball_event grace + non-suspicious upward jump) composing into the cascade root via a one-frame-delayed bad-overlay read that the SM-level streak gate cannot undo (because the streak gate is downstream of sb.set's tracker).

### 11.6 Discipline nuance — static falsification vs empirical falsification

Per operator directive after C10: the distinction between **empirical falsification** (the captured-replay or live-instrumentation cycle empirically disproves a hypothesis — counts against the §1.2 falsification budget) and **static falsification** (a code-reading pass conclusively proves the hypothesis is impossible at the proposed site — zero-cost, does NOT count against the budget) is the right framing.

**Static falsifications surfaced in C11:**

| # | Hypothesis | Static-falsification mechanism | Budget impact |
|---|---|---|---|
| §3.5 | C9 §7.2 on_lock async-decoupling | observe() fires synchronously; on_lock callbacks don't mutate score/overs/wickets | Zero |
| §11.1.α | FC1 DRS-grace for f304's score=54 | `_is_drs_pattern` requires `abs(delta) <= 2`; f304's delta is 5 | Zero |
| §11.1.α | FC1 DRS-grace for f304's overs=6.3 | `_is_drs_pattern` requires backwards-by-at-most-0.1; f304's delta is +1.8 | Zero |
| §11.1.β | Cross-field gate at f304 | Cold-start path only; sb._inn fields already in `confirmed` post-warm-seed | Zero |

**Total static falsifications this brief: 4. Budget impact: 0.** Hypothesis #6 (FC5 post-event grace + non-suspicious upward jump) survives as the standing candidate, with refined sub-questions about the overs commit path (§11.3).

The discipline rule made explicit: **apply static falsification liberally before any instrumentation commit.** A code-reading pass that can disprove a hypothesis is always cheaper than an instrumentation cycle. The catalogue at C9 is itself a static-falsification instrument (it enabled §3's on_lock disproof).

### 11.7 C11 verdict — Outcome A (qualified)

Per the C10 §7 decision tree:

- **Outcome A** — "Static evidence confirms one of §5's failure modes." The FC5 post-event grace candidate (a refined version of §5.3 mode γ) is statically confirmed for the **score side** of the f304 cascade. The **overs side** remains under-resolved — three sub-candidates in §11.3, each requiring either further static analysis or targeted unit-test exercise.

This is **Outcome A with a qualifier**: one of two halves of the cascade signature is empirically grounded; the other half is structurally constrained but not yet localized.

**Next deliverable (C12) — see §11.8.** No further instrumentation pending §7.2 7-gate audit on whatever code-shape eventually emerges.

### 11.8 C12 deliverable — open the §7.2 7-gate audit + close the overs-side question

Two work items, ordered:

1. **Static-analysis closure of the overs-side question.** Trace `test_pipeline.py:11750` (end-of-over hook) + the consensus-override path at `consistent_tracker.py:319-405` + verify whether any frame between f304 and f318 in the production trace had a 4-frame consensus run on overs=6.3. One static-analysis pass, no instrumentation.

2. **§7.2 7-gate audit applied to the candidate fix shape.** With both halves of the cascade root empirically grounded, propose ONE candidate fix shape (e.g., "tighten FC5's `_is_suspicious` to flag large upward score jumps OR couple FC5's commit to a cross-field gate that requires the matching overs to also be non-suspicious"). Apply all 7 gates. Predicted-flip claim must cite concrete frame numbers from the captured replay (now reproducible via the C4 LLM-extractor + warm-seed scaffold once instrumented to expose FC5 fires).

**Both work items must complete before any code commit.** The five-falsification track record means gate 6 (predicted-flip with concrete frame numbers) is non-negotiable.

### 11.9 What C11 explicitly does NOT decide

- **Does NOT authorize a fix to FC5.** Fix-shape design is C13+, gated on §7.2 audit.
- **Does NOT authorize new instrumentation.** The C11 static-analysis pass is the cheap discipline mechanism; further instrumentation only after the §7.2 audit identifies a specific predicted-flip claim.
- **Does NOT update HANDOFF.** Deferred per operator directive until next clean pause point (target: post-C12 audit completion OR sixth-falsification methodology retirement).

---

---

## 12. C12 static-analysis pass — overs-side closure

Per the operator's C12 directive: apply the same predicate-reading + sub-candidate-elimination methodology that produced C11's Outcome A. The three sub-candidates in §11.3 are each statically testable.

### 12.1 Sub-candidate (a) — FC5 fires at f304 for overs (re-derivation with correct grace arithmetic)

C11 §11.2 raised a concern that `_post_event_grace` would be 1 by the time the overs `sb.set` call ran at f304, blocking FC5 for overs. **That concern was based on an incorrect grace baseline.** Re-deriving:

`consistent_tracker.py:782-786` — `on_ball_event` sets `_post_event_grace = 2` (absolute assignment, not increment).

`consistent_tracker.py:302` — `_post_event_grace -= 1` decrement fires ONLY when FC5 actually commits a value (within the `if not suspicious_check:` block). No other code path decrements grace.

**Production f300-f304 timeline:**

| Frame | Event | grace value after |
|---|---|---|
| f300 | Ball commit (score 45 ov 4.4) → on_ball_event() | 2 |
| f300 | sb.set calls following the commit may or may not have fired FC5 (depends on _is_suspicious results) | 0, 1, or 2 |
| f302 | Ball commit (score 45→49) → **on_ball_event() RESETS to 2** | 2 |
| f302 | FC4 fires for overs 4.4→4.5 — does NOT decrement grace (FC4 has its own commit path, not FC5) | 2 |
| f302 | sb.set("score", 49, 302) FC5 path: grace=2 → fires → grace=1 | 1 |
| f303 | POISONED upstream of sb.set → tracker.update never called → no decrement | 1 |
| f304 | sb.set("score", 54, 304) FC5 path: grace=1>0, `_is_suspicious(score, 49, 54)`=False → fires → grace=0 | 0 |
| f304 | sb.set("overs", "6.3", 304) FC5 path: **grace=0** → FC5 path skipped | 0 |
| f304 | sb.set("wickets", 0, 304): current==value (both 0) → line 221 early return | 0 |

**Refined finding: at f304, FC5 fires ONLY for the score commit. The overs commit at f304 cannot land via FC5 because grace was already consumed by the score commit.** Sub-candidate (a) as stated in §11.3 is **partially falsified** — FC5 admits the score, but not the overs at the same frame.

The overs side requires either a different FC path OR a different f304-vs-other-frame ordering. Continuing through (b) and (c).

### 12.2 Sub-candidate (b) — alternate FC path for overs

All paths in `consistent_tracker.py:update` that can commit `field="overs"` on a single read:

| Path | Predicate gate | f304 overs (old=4.5, new=6.3) | Verdict |
|---|---|---|---|
| FC1 DRS-grace | `_is_drs_pattern("overs", "6.3")` requires `0 < 4.5-6.3 ≤ 0.1` | Δ = -1.8 (forward, not backward) | **Falsified** (§11.1) |
| FC2 batter-natural | doesn't apply to "overs" field | n/a | **Falsified by construction** |
| FC3 bowler-natural | doesn't apply to match-level "overs" | n/a | **Falsified by construction** |
| FC4 overs-natural | requires exactly +0.1 or X.5→(X+1).0 | 4.5→6.3 neither | **Falsified** (§11.1) |
| FC5 post-event | requires `_post_event_grace > 0 AND not _is_suspicious` | grace=0 by time overs call runs at f304 (§12.1) | **Falsified at f304 specifically** |
| Cold-start `_initial_consensus` | requires `field not in self.confirmed` | "overs" IS in confirmed (from f300/f302) | **Falsified** |
| 4-frame `[CONSENSUS]` override | requires 4 consecutive reads with `_values_close(a, b, "overs")` (Δ ≤ 0.3) | Only ONE production frame proposed 6.3 (f304) | **Falsified by trace count** |
| Pending-defer 2-frame | requires `pending_value == value` for 2 frames | Same — only one read of 6.3 | **Falsified** |

**Sub-candidate (b) statically falsifies all alternate `update()` paths.** No code path in `consistent_tracker.py:update()` can admit overs=6.3 from a single f304 read.

### 12.3 Sub-candidate (c) — `test_pipeline.py:11750` end-of-over hook

Read at `:11742-11753`:

```python
_ext_overs = extracted.get("match_overs")
if not _direct_block_all and _ext_overs is not None:
    _eos = str(_ext_overs).strip()
    if "/" in _eos: _eos = _eos.split("/")[0].strip()
    try:
        _eof = float(_eos)
        if _eof < 20.0:
            if scoreboard.set("overs", _eos, frame_count):
                log.info(f"  [DIRECT] overs→{_eos}")
    except (ValueError, TypeError):
        pass
```

This is a **catch-up/end-of-over reconciliation** path that calls `sb.set("overs", ...)` from a different code site than `commit_decision`. **But it routes through the same `sb.set` → `tracker.update` → FC1/FC2/...FC5 dispatch as the main path.** Sub-candidate (c) is NOT a structurally distinct FC path — it's a different *caller* of the same `tracker.update`. Since §12.2 already falsified all FC paths for f304's overs value-shape, sub-candidate (c) inherits the same falsifications.

**Sub-candidate (c) falsified by inheritance from (b).** Same code, different caller.

### 12.4 Where does sb._tracker.confirmed["overs"] = 6.3 actually come from?

§12.1-12.3 establish that no single-frame FC path in `consistent_tracker.py` can admit overs=6.3 from f304's single read. Yet production f318 trace shows `tracker_overs=6.3`. There are two remaining structural explanations:

**(A) Multi-frame consensus accumulates 6.3 between f304 and f318.**

The 4-frame `[CONSENSUS]` override at `consistent_tracker.py:319` accepts a "suspicious" value after 4 frames where the proposed value clears `_values_close`. But §12.2 noted only f304 proposed 6.3 in the SCOREBOARD-typed frames. **However** — non-SCOREBOARD-typed frames may still call `sb.set("overs", ...)` from the DIRECT path catch-up branch (§12.3). The production trace filters non-SCOREBOARD frames out of `scorer.decisions[]` but the sb.set calls still happen.

Verifying this requires counting all sb.set("overs", "6.3", X) invocations across the full 1000+ frames of the session, NOT just the 341 SCOREBOARD-typed records in the trace. **Without that count, sub-candidate (A) cannot be statically falsified.**

**(B) The pending-defer path fires after grace expires.**

`consistent_tracker.py:411-450` (after FC5): the pending defer path accumulates a `(value, _)` candidate per field. If two consecutive frames propose the same overs=6.3, the second commits via pending-defer (the standard 2-frame consensus). The same trace-count question applies.

### 12.5 Production trace reality check — what _values_close admits

`_values_close("overs", a, b)` at line 759-760: `return abs(fa - fb) <= 0.3`. So 6.3 and 6.2 are "close"; 6.3 and 6.0 are close; 6.3 and 6.4 are close.

If between f304 and f318 ANY 4 frames proposed overs in the range [6.0, 6.6], the consensus override at line 319 would fire. The production trace shows the broadcast strip reading at f318 as "DC 49-1 (5)" — so the broadcast itself was at overs=5.0 by that point, but Scout's hallucinated overlay reads (PANT/WARD/SHAMI at f304, and possibly similar at intermediate frames not captured as SCOREBOARD) could have produced 6.3-class readings.

**The static analysis is insufficient to localize the overs commit timing.** What is statically clear:

- Single-frame FC paths at f304 cannot admit overs=6.3 (§12.1-12.3 confirmed).
- Multi-frame consensus paths CAN admit it, but require counting all sb.set calls across the full session — including non-SCOREBOARD-typed frames — to verify which mechanism fires.

### 12.6 Status — Outcome A (refined further) + a half-localized question

| Cascade-root half | Static-evidence status |
|---|---|
| **Score side** — `sb._inn["score"] = 54` at f304 via FC5 | **Statically CONFIRMED** (§11.2, §12.1) |
| **Overs side** — `sb._inn["overs"] = 6.3` at some frame ≥ f304 | **Mechanism narrowed to multi-frame consensus** (§12.4); exact triggering frame not localizable from the 341-record SCOREBOARD-typed trace alone |

The overs-side question requires a deeper trace audit: parse the full pipeline.log (or instrument sb.set with the C6 DIRECT-SCORE-COMMIT tag extended to ALL fields, not just score) to count overs-related sb.set calls between f304 and f318. This is one additional static / re-replay pass, OR a follow-up commit extending DIRECT-SCORE-COMMIT to cover overs and wickets.

### 12.7 Operator's reframe — the F-α-shadow pattern empirically validated

Per operator directive: "C12's overs-side analysis should look for the same pattern — which surface admits the overs jump that `_handle_warm`'s streak gate would otherwise reject?"

**Two parallel state surfaces with different invariants, empirically confirmed:**

- **`sb._tracker.confirmed` (Scoreboard tracker)** — gated by `_is_suspicious` which is permissive for upward score jumps under +30 (`(new - old) > 30` required to suspect) AND for forward overs jumps (only `new < old` triggers suspicion). FC5 + post-event grace admit anything that clears `_is_suspicious`. Multi-frame consensus admits a 6.3-class value if 4 reads agree within ±0.3.
- **SM's `_handle_warm` streak gate** — gated by 3-frame consensus on `(new_overs, c_score)` tuple AND a hard `_BALLS_JUMP_TOLERANCE = 3` threshold. Strict.

The weaker surface (`sb._tracker`) admits the values; the stronger surface (`_handle_warm`) rejects them. Both stay live in production state simultaneously, producing the divergence signature `sb._inn["score"]=54 sb._inn["overs"]="6.3"` vs `sm.self.score=54 sm.self.overs=4.5` observed at f318.

This is **structurally identical to F-α-shadow from the F1 session** (commit `37f63ad`): `sb.bowling_card` (the canonical store) vs `sb._inn["bowling_card"]` (an unused parallel surface) had different invariants; the snapshot code read the wrong one. Here: `sb._tracker.confirmed` (canonical Scoreboard store) vs `_handle_warm` streak gate (SM-side gate) have different invariants; FC5's weaker invariant admits what the streak gate would reject.

**Architectural class: dual-state-write defect** — a pattern worth cataloguing in `sm_as_orchestrator_design.md` post-C15 per the operator's note (deferred).

### 12.8 C13 deliverable

The user authorized C13 as the §7.2 7-gate audit on the candidate fix shape. **C13 cannot proceed cleanly yet** — the overs-side trace gap surfaced in §12.4/12.6 means the predicted-flip claim for the overs side cannot cite a single frame number. Gate 6 (predicted-flip with concrete frame numbers, recursively applied) would not close cleanly without that data.

**Recommended C13 prerequisite: extend the C6 DIRECT-SCORE-COMMIT instrumentation to overs and wickets fields (one additive commit), re-run the warm-seeded + LLM-enabled replay, and capture the exact frame where `sb._inn["overs"] = 6.3` lands.** This is a small instrumentation pass — clearly authorized under "C12 prerequisites" not "C13 fix design" — and produces the empirical frame number needed for gate 6.

Alternatively: parse the full production pipeline.log (if retained) for all `[DIRECT] overs→` log lines between the f304 timestamp and the f318 timestamp. This is a zero-commit static-evidence step.

**Awaiting operator decision on C12.5: extend DIRECT-SCORE-COMMIT (small additive commit), OR parse pipeline.log for overs-DIRECT lines, OR proceed to C13 audit with the score-side concrete and the overs-side structurally-argued.**

### 12.9 Discipline status — falsification budget tally

C11 + C12 static falsifications:

| # | Hypothesis | Status |
|---|---|---|
| C11 §3.5 | on_lock async-decoupling (C9 §7.2 candidate) | Static-falsified |
| C11 §11.1.α-score | FC1 DRS-grace for f304 score | Static-falsified |
| C11 §11.1.α-overs | FC1 DRS-grace for f304 overs | Static-falsified |
| C11 §11.1.β | Cross-field gate at f304 | Static-falsified |
| C11 §11.1.γ (FC4) | Natural-overs-increment for f304 overs | Static-falsified |
| **C12 §12.1** | **FC5 at f304 for overs** (concern raised in §11.2 confirmed) | **Static-falsified** |
| C12 §12.2 | All single-frame FC paths for f304 overs | Static-falsified |
| C12 §12.3 | end-of-over hook as distinct path | Static-falsified-by-inheritance |

**Total static falsifications: 8. Empirical-falsification budget impact: 0.** Per operator directive: static-falsification mechanism is doing its job. Each rejected sub-candidate prevented a wasted instrumentation cycle or commit.

**Surviving candidates after C12:**

- **Score side: FC5 at f304 (statically CONFIRMED).** Cascade-root for the score half.
- **Overs side: multi-frame consensus (FC5-or-pending-defer across multiple frames between f304 and f318)** — narrowed but not yet localized; requires C12.5 prerequisite step before C13.

---

---

## 13. C12.5b — pipeline.log audit closes gate 6 for both halves

Operator authorized C12.5b first per zero-commit-cost dominance. `/tmp/pipeline.log` was retained from the production session (2.9 MB, May 21 08:14, exactly matching the session window). Header line confirms `SESSION-CONFIG session_id=validate_dckkr_20260521_070545`.

### 13.1 The four production TRACK lines that close the cascade

Direct grep of pipeline.log for F302-F317 TRACK lines (the consistent_tracker.update log path):

```
F302 TRACK score: 45 → 49 (post-event immediate, grace=1)
F302 TRACK overs: 4.4 → 4.5 (fast-confirm, natural overs increment F302)
F304 TRACK score: 49 → 54 (post-event immediate, grace=1)
F304 TRACK overs: 4.5 → 6.3 (post-event immediate, grace=0)
F317 TRACK [SUSPICIOUS] overs: 6.3→5.0 (backwards)  ← later regression attempt blocked
F317 TRACK [SUSPICIOUS] overs: 6.3→5.0 (backwards)  ← repeat
```

The **`(post-event immediate, grace=N)`** suffix is the FC5 log signature from `consistent_tracker.py:304-305`. Three FC5 fires across f302+f304; one FC4 fire at f302 (overs natural increment); one POISONED frame at f303 that does not invoke tracker.update.

### 13.2 Corrected `_post_event_grace` arithmetic

C12 §12.1 had the grace baseline wrong by one. The correct production sequence:

| Frame | TRACK event | Grace before fire | Grace after fire | Notes |
|---|---|---|---|---|
| f300 | First ball commit | 0 or undefined | 2 (set by `on_ball_event()`) | warm-seed baseline |
| f302 | FC5 score 45→49 | 2 | 1 (log "grace=1") | decrement |
| f302 | `on_ball_event()` fires (score advance = ball event) | 1 | **2** (reset) | per `test_pipeline.py:12953` |
| f302 | FC4 overs 4.4→4.5 | 2 | 2 (FC4 doesn't decrement) | natural-overs path |
| f303 | POISONED upstream | 2 | 2 | tracker.update never called |
| f304 | FC5 score 49→54 | 2 | 1 (log "grace=1") | decrement |
| f304 | FC5 overs 4.5→6.3 | 1 | 0 (log "grace=0") | decrement |
| f304 | wickets 0==0 early return | 0 | 0 | line 221 |

**Production-log evidence matches the grace=1 / grace=0 sequence exactly.** §12.1's earlier derivation missed that `on_ball_event()` fires AFTER FC5 decrements grace, resetting it back to 2 for the next frame. The corrected arithmetic confirms BOTH halves of the cascade root land at **f304 via FC5** in **the same `commit_decision` execution sequence**.

### 13.3 The operator's F-α-shadow reframe — fully empirically validated

The §12.7 framing is now empirically grounded with concrete frame numbers:

- **Weaker invariant surface (`sb._tracker.confirmed` via FC5):** at f304, `_is_suspicious("score", 49, 54)` returns False (no rule for +5 upward jump) AND `_is_suspicious("overs", 4.5, 6.3)` returns False (no rule for forward overs jump). Grace=2 inherited from f302's on_ball_event. Both writes commit on single read.
- **Stronger invariant surface (SM `_handle_warm` streak gate):** at f304, `_d_balls = 11 > _BALLS_JUMP_TOLERANCE = 3` triggers `OVERS-JUMP-IMPLAUSIBLE-REJECTED`. SM rejects the proposal.

The weaker invariant commits to `sb._inn` first; the stronger invariant rejects when SM reads the same proposal from `sb._inn` as the "card" input. Result: divergence between `sb._inn["score"]=54 sb._inn["overs"]="6.3"` and `sm.self.overs=4.5` at f318.

### 13.4 Cascade-root fully localized — gate-6 closure for C13

**Predicted-flip claim with concrete frame numbers** (the prerequisite for the §7.2 7-gate audit):

If FC5's `_is_suspicious` check is tightened to flag large upward score jumps (e.g., delta > 5 within a single sb.set call without a corresponding overs +0.1 advance) OR if FC5 is removed entirely OR if FC5 is coupled to a cross-field gate requiring all three fields' proposals to clear suspicion together:

- **F302 TRACK score: 45 → 49** — Δ=+4 ≤ 5 → still admits (no regression on legitimate boundary)
- **F302 TRACK overs: 4.4 → 4.5** — FC4 path, unchanged (not gated by FC5)
- **F304 TRACK score: 49 → 54** — Δ=+5 with NO matching overs +0.1 → **rejected by tightened FC5**
- **F304 TRACK overs: 4.5 → 6.3** — large Δ=+1.8 overs → **rejected by tightened FC5**
- Result: sb._inn["score"] stays 49, sb._inn["overs"] stays 4.5. SM stays consistent. The B-η cascade (Issues 2, 3, 5, 6, 7, 9, 10, 11 from the session observations) collapses at root.

**Cross-fixture check (gate 7) preview:** the C6 GTRR replay produced 81 DIRECT-SCORE-COMMIT firings, all benign single-ball boundary advances (Δ ≤ 6 paired with normal overs +0.1 advances). A tightening that targets "large upward delta NOT paired with overs +0.1" would not regress GTRR's legitimate boundaries.

### 13.5 C13 prerequisite met — proceed to §7.2 7-gate audit

The static analysis (C11+C12) plus the pipeline.log empirical evidence (C12.5b) together close gate 6 for both halves of the cascade root **without an additional instrumentation commit**. The audit-budget cost was C12.5b's pipeline.log parse (zero commits, ~5 minutes investigator time) — the dominant choice over C12.5a's instrumentation cycle, validated empirically.

**C13 is now unblocked.** The next deliverable applies §7.2 7-gate audit to one or more candidate fix shapes targeting FC5. The audit must:

1. Enumerate every caller of `_is_suspicious` and the FC5 path
2. Classify each caller (will the tightening regress any legitimate write?)
3. Cross-reference with adjacent state (cross-field gate, post-event grace lifecycle, ball-event detection)
4. Equivalence proof: does the tightened FC5 preserve the legitimate-boundary cases (F302, F361, F488, etc.)?
5. State lifecycle: when is grace reset, when does FC5 fire, when does on_ball_event run
6. Predicted-flip gate: §13.4 satisfies this — both halves at f304 cited with TRACK-log evidence
7. Cross-fixture verification: GTRR's 81 benign firings (C6 trace) as the empirical regression-detection substrate

### 13.6 Discipline footnote — C12.5b vs C12.5a outcome

Per the operator's directive: C12.5b dominated C12.5a on the cost axis IF it produced gate-6 closure. **It did**, with zero commits and a 5-minute pipeline.log audit. The C12.5a instrumentation path was a legitimate fallback but is no longer needed — saved one diagnostic commit.

**Static-falsification tally + empirical-localization tally after C12.5b:**

- Static falsifications across C11+C12: 8 (zero budget impact)
- Empirical localizations at concrete frame numbers: 4 (F302×2, F304×2 TRACK lines)
- Empirical falsifications across whole chain: 5 (B-η chain) — unchanged

The discipline mechanism is now empirically validated as the right tool for temporal-coupling defect classes:

- **Static analysis** localizes the mechanism (FC5 path + predicate semantics + grace arithmetic).
- **Pipeline.log audit** (operator-side artifact, zero-commit-cost) localizes the exact frame.
- **Captured-replay scaffold** (commits b49e48b–237d227) serves as the falsification mechanism for the C14 fix.

Per operator directive — bake into HANDOFF post-C15.

---

**Replay paused at §13.5 C13-unblocked. Thirteen commits will be on the chain after this C12.5b update. The B-η cascade root is fully localized at frame F304 via FC5 in the production pipeline.log. C13 §7.2 7-gate audit proceeds on a candidate fix shape targeting FC5's `_is_suspicious` predicate or its post-event-grace gate.**
