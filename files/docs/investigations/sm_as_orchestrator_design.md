# SM-as-Orchestrator + Frame Fate Ledger — Design Memo

**Status:** Stage 1 + 2a + 2a' + 2c shipped. Stage 2b (Secondary LLM resolution) reverted 2026-05-19 — multi-ball gap resolution is the wrong abstraction; gaps are bugs to diagnose and fix at root cause, not classes the architecture must accommodate. Frame Fate Ledger (§4) shipped as `files/eyes/frame_ledger.py` with sm_outcome wiring at 5 sites (4 SM-side + 1 SB-side + 1 pipeline-side CORRECTION_BLOCKED). Dispatch-side scout_status wiring (PENDING/TIMEOUT/RESPONDED) deferred to a follow-up commit.
**Date:** 2026-05-19
**Author:** J110
**Supersedes:** the corpus + adversarial mutator foundation work paused as of this memo. Also supersedes the Secondary LLM design (former §4) and its eval-corpus / heuristic-fallback content.
**Related:** `files/docs/investigations/trace_and_detect_system_design.md` (trace schema), audit chat preceding this memo (5-primitive contract).

## 1. Problem

The current pipeline is *passive* relative to Scout: SM accepts whatever delta Scout reports per frame and back-fills missing structure via a pending-ball queue plus `?` placeholders that wait for `broadcast_this_over` to fill them in later. Three failure modes drove this proposal — all are now classified as **bugs to diagnose and fix at root cause**, not load-bearing conditions the architecture must accommodate:

1. **Multi-ball compression.** Camera-cut / overlay gaps cause Scout to skip from `(N.M)` to `(N.M+2)` in one frame. The Stage 1 retrospective showed every Δ≥2 commit decomposes into one of: (a) Scout cadence drop (rate-limit / latency / retry), (b) Scout response classified as non-SCOREBOARD (graphic / replay / overlay), (c) SCOREBOARD frame rejected by an SM/SB guard despite readable strip, (d) genuine OCR miss, (e) measurement artifact (no actual gap). Each category is a fix, not an accommodation.
2. **Deferred attribution drift.** Pending balls live across over boundaries; archive is parked in `_over_archive_pending` (`score_manager.py:5048, 5296`), and bowler/striker locks acquired late can credit the wrong over. Same treatment: fix the bowler-lock latency root cause, not the queue.
3. **Broadcast wholesale-accept hazards.** `on_broadcast_override` (`this_over.py:797-920`) trusts `this_over_broadcast` to fill gaps but the broadcast strip itself is flaky during ribbon overlays; the `MAX_THIS_OVER_LEN=9` guard and `_merge_broadcast` normalizer exist specifically to defend against this — the guards are the symptom. **Treatment:** ship the 5-primitive contract; derive `this_over` from per-frame deltas; delete the wholesale-accept path entirely.

The architectural shift:

- **SM becomes active.** SM holds `expected_next_ball` (shipped stage 1, `a57cdbd`) and emits diagnostic `[GAP-DETECTED]` whenever a Δ≥2 commit occurs. Stage 2a (`185bc39`) added `[GAP-AT-REJECTION]` at the three pre-`_accept_update` rejection sites. Stage 2a' (`ca85dd9`) closed the instrumentation hole at hot-resume + cold-exit. **All additive; no behavior change.**
- **Frame Fate Ledger** (§4) becomes the diagnostic surface that explains WHY each frame failed to commit. Every multi-ball-gap event is traced to its rejection class so root-cause fixes can target the dominant source.

A previously-proposed synchronous gap-resolution path (Secondary LLM via Groq llama-3.1-8b-instant) was implemented in stage 2b (`5fe6768`, `97671cc`) and evaluated against hand-labeled ground truth in `310bfe8`. **Both 8B and 70B failed the ≥80% case-level / ≥90% consistency gate** — root cause is data-bound, not prompt-bound: Scout's `THIS OVER` field is null at gap frames, so the LLM has start/end state but no per-ball sequence signal. Reverted 2026-05-19. The gaps shouldn't exist in the first place; resolving them after the fact is the wrong shape.

## 2. Architecture

```
Frame in → on_frame(FrameInput)
              │
              ├─ compute implied_ball from FrameInput.overs
              ├─ if implied_ball == expected_next_ball: accept (canonical path)
              ├─ if implied_ball < expected_next_ball: existing drift guards
              └─ if implied_ball > expected_next_ball: emit [GAP-DETECTED]
                     │
                     └─ (future) consult Frame Fate Ledger: emit
                        [GAP-EXPLAINED-BY-*] with the rejection class
                        (cold_exit / warm_consensus / scoreboard_jump_limit /
                        scout_failure / extractor_filter / etc.)
                     │
                     └─ accept the new state as before (instrumentation is
                        additive until root-cause fixes drive Δ≥2 to ~0)
```

No synchronous resolution. No deferred queue, no `?` placeholders, no secondary LLM, no deterministic heuristic. The architecture is to **diagnose** gaps (Stage 1 telemetry + Stage 2c ledger), **investigate** root causes per-class, and **fix** them at source until Δ≥2 rate falls to ~0. Any residual gap class that proves structurally unfixable (e.g., strip-not-visible during DRS pauses at <1% steady-state rate) is flagged explicitly and re-evaluated.

## 3. `expected_next_ball` state machine

### 3.1 State

```python
@dataclass
class ExpectedBall:
    over: int           # 0-indexed within innings (0..max_over-1)
    ball: int           # 1-indexed within over (1..6, can go higher with extras)
    legal_ball_count: int  # for striker-rotation derivation
```

`expected_next_ball: ExpectedBall | None` on `ScoreManager`. `None` only before the first ball of any innings is committed.

### 3.2 Init / reset

| Event | Effect | Site |
|---|---|---|
| `__init__()` | `expected_next_ball = None` initially; advances on first overs commit | `score_manager.py:337-465` |
| First legal ball of innings observed | Initialize from observed overs | `_track_overs_advance` |
| `set_innings_2()` | Reset via `self.__init__(shadow=self.shadow)` | `score_manager.py:3546` |
| `_accept_update()` commits ball | Advance `legal_ball_count` to match new committed overs | `_track_overs_advance` |
| `hot_resume_from_cache()` | Same advance call | stage 2a' wiring |
| `_accept_initial()` (cold-start exit) | Same advance call | stage 2a' wiring |

### 3.3 Advance rules

```
on each _accept_update / hot_resume / cold-exit commit of overs:
    prev_legal = legal_balls(prev_overs)
    new_legal  = legal_balls(new_overs)
    delta = new_legal - prev_legal
    if delta >= 2:
        log.info("[GAP-DETECTED] Δballs={delta} ...")  # diagnostic only
    if delta != 0:
        expected_next_ball.legal_ball_count = new_legal
        expected_next_ball.over = new_legal // 6
        expected_next_ball.ball = (new_legal % 6) + 1
```

Wicket commits **do not** reset `expected_next_ball` — the next ball is still expected, with a new striker. The "new batter to crease" delay is observable via Scout but doesn't change the ball-number expectation.

### 3.4 Gap detection (current, observation-only)

Today the state machine is purely additive: any Δ≥2 commit fires `[GAP-DETECTED]` (auto-promoted to `decisions[]`) and SM accepts the new state unchanged. The detection is a diagnostic surface, not a gate. Once root-cause fixes drive the Δ≥2 rate to ~0, the question of "should SM refuse Δ≥2 frames" can be revisited — but in the bug-fix framing, the goal is to never see them, not to handle them.

## 4. Frame fate ledger

(Originally framed as "Frame accounting queue" — a Scout response tracker. Stage 1 retrospective on the DC-vs-KKR Tier 1 corpus reframed the role: existing SM/SB rejection guards silently drop ~6.3% of frames (66 SM-level + 45 SB-level vs 5 surfaced gaps in the same corpus), an order of magnitude more than the visible commit-side gaps. The ledger's primary job is therefore tracking every frame's **fate across all rejection paths** — Scout-level, SM-level, SB-level — not just Scout response/timeout. Without that ledger, root-cause investigation can't attribute Δ≥2 gaps to their actual source.)

Every frame dispatched to Scout, AND every Scout response processed by SM, gets a tracked fate. Root-cause investigation queries the ledger to attribute each `[GAP-DETECTED]` to one of: (a) ball was skipped on a frame we accepted (commit-side gap — investigate extractor reject or measurement artifact), (b) ball happened during a frame whose Scout response was lost/late (`TIMEOUT`/`ERROR` — investigate Scout cadence/retry), (c) ball happened during a frame whose response SM/SB rejected (`REJECTED_BY_*` — investigate the guard threshold), (d) frame was normal between-balls observation (`ACCEPTED_NOOP`).

### 4.1 Schema

```python
@dataclass
class FrameLedgerEntry:
    frame_id: int
    dispatched_at: float                # wall time
    scout_response: dict | None
    scout_status: Literal["PENDING", "RESPONDED", "TIMEOUT",
                          "ERROR", "CORRUPT", "RETRY-EXHAUSTED"]
    sm_outcome: Literal["NOT_YET_SEEN", "ACCEPTED_COMMIT",
                        "ACCEPTED_NOOP", "REJECTED_COLD_EXIT",
                        "REJECTED_WARM_CONSENSUS",
                        "REJECTED_SB_JUMP_LIMIT",
                        "REJECTED_DISMISSED_GUARD",
                        "REJECTED_STRIP_ROW_MISMATCH",
                        "REJECTED_OTHER"]
    rejection_payload: dict | None      # proposed/current overs+score, delta_balls
    retry_count: int
    resolved_at: float | None
```

Two-dimensional fate: `scout_status` × `sm_outcome`. A frame can be `RESPONDED` + `REJECTED_WARM_CONSENSUS` (Scout came back fine; SM rejected the jump). A frame can be `TIMEOUT` + `NOT_YET_SEEN` (no response, SM never got to evaluate).

### 4.2 Lifecycle

| Event | Effect on entry |
|---|---|
| Scout dispatch | Create entry; `scout_status=PENDING`, `sm_outcome=NOT_YET_SEEN`, `dispatched_at=now()` |
| Scout response (200, valid JSON) | `scout_status=RESPONDED`; store response; set `resolved_at` |
| Timeout (default 5s — `_SCOUT_TIMEOUT` at `files/eyes/vision.py:31`) | `scout_status=TIMEOUT`; if `retry_count < N`, re-dispatch with backoff |
| Non-recoverable error (5xx, network) | `scout_status=ERROR`; same retry policy |
| Response unparseable | `scout_status=CORRUPT`; same retry policy |
| Retry budget exhausted | `scout_status=RETRY-EXHAUSTED`; emit `FRAME-ACCOUNTING-UNRESOLVED` |
| SM commits the frame (`_accept_update` advances state) | `sm_outcome=ACCEPTED_COMMIT` |
| SM accepts but no state advance (between-balls observation) | `sm_outcome=ACCEPTED_NOOP` |
| SM cold-start-exit rejects (`OVERS-JUMP-IMPLAUSIBLE-REJECTED source=cold_start_exit_vs_last_warm`) | `sm_outcome=REJECTED_COLD_EXIT`; store `[GAP-AT-REJECTION]` payload (shipped stage 2a) |
| SM warm-consensus rejects (`source=warm_consensus`) | `sm_outcome=REJECTED_WARM_CONSENSUS`; store `[GAP-AT-REJECTION]` payload |
| SB jump-limit rejects (`source=scoreboard_jump_limit`) | `sm_outcome=REJECTED_SB_JUMP_LIMIT`; store `[GAP-AT-REJECTION]` payload |
| Other SM rejects (dismissed-batter, strip-row mismatch) | `sm_outcome=REJECTED_*` with specific tag |

Capacity bounded; oldest entries beyond N (default ~200, ~10 min of frames) evicted with `FRAME-ACCOUNTING-EVICTED`.

### 4.3 Stage 2a foundation

The `[GAP-AT-REJECTION]` trace tag (shipped in stage 2a, `185bc39`) is the ledger's down-payment: surfaces SM-level + SB-level rejections with a uniform structured payload (`delta_balls`, `proposed_overs`, `current_overs`, `proposed_score`, `current_score`, `source`) without yet building the full ledger data structure. Three emission sites: `score_manager.py` cold-start-exit (`source=cold_start_exit_vs_last_warm`), `score_manager.py` warm-consensus (`source=warm_consensus`), `eyes/scoreboard.py` jump-limit (`source=scoreboard_jump_limit`). Stage 2c turns these emissions into ledger entries.

### 4.4 Integration with existing retry infrastructure

Both existing retry paths fold into the ledger, not the other way around:

- **Track 1 — in-call retry** (commit `5e4ff8a`, single retry on Groq 429 inside `Vision.describe`, `files/eyes/vision.py:512`). Today invisible to SM. After ledger lands, both attempts are recorded so retry rate is observable.
- **Track 2 — `_ScoutRetryBuffer`** (`files/eyes/openscout_loop.py:74`; capacity 3, staleness 5s, max attempts 2; constants at `:60-62`; instantiated at `:262`). Recommendation: delete after ledger lands — ledger subsumes the buffer's role; one source of truth. Existing tests at `files/tests/test_openscout_loop.py:346` port to ledger-status assertions.

### 4.5 Diagnostic consultation pattern

When `[GAP-DETECTED]` fires, the ledger is consulted to attribute the gap:

```python
gap_window = ledger.entries_between(
    expected_next_ball.legal_ball_count,
    implied_ball.legal_ball_count,
)
scout_failures = [e for e in gap_window
                  if e.scout_status in {"TIMEOUT", "ERROR",
                                        "CORRUPT", "RETRY-EXHAUSTED"}]
sm_rejections = [e for e in gap_window
                 if e.sm_outcome.startswith("REJECTED_")]
emit("GAP-EXPLAINED",
     scout_failure_count=len(scout_failures),
     sm_rejection_count=len(sm_rejections),
     rejection_classes=[e.sm_outcome for e in sm_rejections])
```

This is diagnostic-only — feeds the root-cause investigation. No resolution, no remediation at runtime.

### 4.6 Trace tags

| Tag | When emitted |
|---|---|
| `FRAME-DISPATCHED` | Per dispatch (high volume; opt-in via verbose flag) |
| `FRAME-RESOLVED` | Per successful response, with latency_ms |
| `FRAME-ACCOUNTING-TIMEOUT` | On timeout, with retry_count |
| `FRAME-ACCOUNTING-UNRESOLVED` | On retry exhaustion |
| `FRAME-ACCOUNTING-EVICTED` | On capacity eviction |
| `GAP-EXPLAINED` | Diagnostic consultation result |

## 5. Integration points

| Site | Change | File:line (today) |
|---|---|---|
| `ScoreManager.__init__` | `self._expected_next_ball: ExpectedBall \| None = None` (shipped) | `score_manager.py:415` area |
| `set_innings_2` | Auto-resets via `self.__init__()` (shipped) | `score_manager.py:3546` |
| `_accept_update` | Calls `_track_overs_advance` after overs mutation (shipped) | `score_manager.py:3686` area |
| `hot_resume_from_cache` | Same advance call (shipped stage 2a') | `score_manager.py:2455` area |
| `_accept_initial` | Same advance call (shipped stage 2a') | `score_manager.py:2535` area |
| Rejection sites (×3) | Emit `[GAP-AT-REJECTION]` (shipped stage 2a) | `score_manager.py:2376, 2863`; `eyes/scoreboard.py:1418` |
| **Stage 2c**: new `frame_ledger.py` module | `class FrameLedger` with dispatch/response/reject hooks | new under `files/eyes/` |
| **Stage 2c**: dispatch wrap | `Vision.describe` opens a ledger entry; response closes it | `files/eyes/vision.py:512` |
| **Stage 2c**: SM consultation | `[GAP-DETECTED]` triggers `ledger.explain_window(...)` | `score_manager.py:_track_overs_advance` |
| `trace_emitter.py` | Tags listed in §4.6 | `:54-106` |

## 6. Harness implications

| Layer | Today | After Stage 2c |
|---|---|---|
| Layer 1 (unit) | per-method tests | + `FrameLedger` unit tests |
| Layer 1.5 (derivation ledger) | ledger ↔ SM committed-state parity | unchanged; ledger consultation is observation-only |
| Layer 2 (captured-replay) | Scout JSONL replay + WS assertion | + ledger consistency assertion (every frame has an entry; no orphan rejections) |
| Adversarial mutators (paused) | broadcast-strip mutations, ribbon overlays | scope shrinks — many mutator targets (`this_over_broadcast`, `broadcast_striker`) deleted by the 5-primitive contract pass; remaining mutators focus on rejection-class triggers |

## 7. Scar tissue obsolescence (revised from prior audit)

**Per-item audit gate (2026-05-20).** The §7 list below is a *candidate* set, not a pre-approved
deletion queue. Every item requires its own bounded audit before removal: enumerate all
callers, classify each as init / transition / preserved, cross-reference against any drain or
trigger mechanism it participates in, and produce an equivalence proof for the proposed
replacement. The S4b attempt (see §7.1) failed precisely because this audit step was skipped
on first pass: the queue under attack turned out to be load-bearing, not scar tissue.

**Delete (pending per-item audit):**

- `PendingBall` dataclass and `_pending_ball_queue` (`score_manager.py:238-250, 405, 553-604, 669-710`)
- `_over_archive_pending` deferred archive (`:5048, 5296`)
- `_pending_slots` dict + "?" placeholder logic (`this_over.py:85-91, 847-920, 1340-1360`)
- `on_broadcast_override` wholesale-accept (`this_over.py:797-920`)
- `_merge_broadcast` normalizer (`this_over.py:1134-1161`)
- `MAX_THIS_OVER_LEN=9` anti-ribbon guard (`this_over.py:1089-1115`)
- MULTI_BALL gap decomposition (`score_manager.py:2095-2125` and downstream)
- `MULTI-BALL-DERIVATION-EXPANDED` trace tag (`trace_emitter.py:64`, already deprecated)
- ~~P1 striker-indicator matcher (`score_manager.py:4368, 4484`)~~ — already removed 2026-05-19 (semantically backwards; see §7.6 audit)
- `[SM-W8-DISMISSED-GUARD]` re-introduction suppression (`:3870`)
- `broadcast_this_over`, `broadcast_striker`, `broadcast_extra` fields from Scout output (`extract_regex.py:390-392, 317, 386-388`)
- `_ScoutRetryBuffer` (`files/eyes/openscout_loop.py:74`) — subsumed by Frame Fate Ledger

**Conditional (deletion gated on production telemetry):**

- `_PENDING_BOWLER_BALL_CREDIT_MAX_LAG = 40` (`score_manager.py:100`, used at `:5721`) — the
  lag bound itself can shrink or be removed only if production traces show
  `PENDING-BOWLER-BALL-CREDIT-ORPHANED` events are rare. If ORPHAN-rate stays at or near zero
  across a full session, the bound is unused configuration. Gated on the same observability
  run that gates Path B deletion (§7.1 step S4a (ii)).

**Keep:**

- `_pending_bowler_ball_credits` queue + producer (`score_manager.py:5249`) + consumer
  (`_drain_pending_bowler_ball_credits` at `:5714`, drain triggers D1 at `:5028-5030` and D2
  at `test_pipeline.py:7223`). **Reclassified Keep on 2026-05-20 (see §7.1).** Canonical
  resolver for the 3-way race between (a) bowler-name resolution, (b) legal-ball commit, and
  (c) bowler-tracker on_lock. No transition-driven replacement is equivalent — see §7.1.
- `_pending_bowler_wickets` queue (F381 wicket backfill) — structural analog of the
  bowler-ball-credits queue; same 3-way-race resolution logic applies.
- `_PENDING_WICKET_MAX_FRAME_LAG=40` (`:65, 5363`) — orthogonal to Scout schema; bowler-lock latency from tracker is independent. Recent tuning commits (5638eb4, 5b25e59, 31dc8b9) stand.
- `broadcast_team`, `broadcast_target`, `broadcast_venue`, `broadcast_match_info` — cold-start metadata, not frame-by-frame; out of scope.
- `broadcast_extra` (frame-level OCR discriminator, values `"WD"/"NB"/None`) — drives the WIDE-vs-NO_BALL event-type classification in `_infer_extra` and gates deferred-fire confirmation in `_infer_event`. Reclassified Keep on 2026-05-20 per §7.5 — distinct role from `extras_type`.
- `extras_type` (event-level subtype label, values `"leg_bye_or_bye"/None`) — refines attribution on committed regular-run events so this_over rendering can emit `{r}lb` tokens. Reclassified Keep on 2026-05-20 per §7.5 — distinct role from `broadcast_extra`; the two fields sit on opposite sides of the legal/illegal delivery axis and cannot be unified.

### 7.1 S4b reclassification: Queue B is structural, not scar tissue (2026-05-20)

**Verdict: NOT-A-DEFECT.** Two dry-run attempts (one bundling cold-start hook + queue
producer deletion, one limited to a single cold-start transition hook) both regressed at
`test_pipeline_captured_replay.py` ball 3.1 of `watch_20260519_121701`. Sunil Narine's
first-ball credit was lost because no path covered the case where the ball event committed
before either the bowler-name re-set or the bowler-tracker lock fired.

**The 3-way race.** Bowler attribution for a legal ball needs three pieces of state to
align: bowler-name set on `ScoreManager`, the legal-ball event commit, and the
bowler-tracker `_locked` streak threshold. In the cricket-broadcast data we observe, all six
orderings of these three events occur. The pre-S4b architecture handled all six via two
drain triggers — D1 (`_accumulate_stats_from_event` inline drain when a ball commits with a
resolved bowler) and D2 (`bowler_tracker.on_lock` callback when the streak threshold trips
before any intervening commit). The queue itself acts as the buffer between these triggers
and any earlier ball commits.

**Why a transition-driven hook does not replace it.** S4b's Option (R) proposed firing a
drain at every `self.bowler_name =` non-None assignment. This adds a third trigger
("bowler-resolution → drain"), which collapses two of the six race orderings into the same
moment. The remaining four orderings still require the queue: a ball event that commits at
frame F with `bowler_name=None` has no future trigger to credit it unless the queue holds
the credit until the bowler appears later. The transition hook only changes WHEN D1's drain
body executes; it does not eliminate the need for the queue.

**Audit (2026-05-20) — sites enumerated.**

| Site | Function | Class |
|---|---|---|
| `score_manager.py:1395` | `_reset_per_innings` | → None (init) |
| `score_manager.py:2687` | `_resume_from_cache_hot` | None → X (transition) |
| `score_manager.py:2785` | `_accept_initial` (cold-start adoption) | None → X (transition) |
| `score_manager.py:3922` | `_accept_update` (warm-mode bowler refresh) | None → X (transition) |
| `score_manager.py:5384` | over-archive post-credit clear | → None (clear) |

**Drain trigger inventory.**

- D1 (`score_manager.py:5028-5030`) — inline drain on next ball commit
- D2 (`test_pipeline.py:7223`) — bowler-tracker `on_lock` callback

D1 and D2 cover two of the three possible "bowler resolves" mechanisms. The queue producer
at `:5249` covers the remaining race ordering: ball-commit before either trigger fires.

**Action.** Queue B and its surrounding mechanism (producer at `:5249`, drain at `:5714`,
both trigger sites) are reclassified from the §7 Delete list to §7 Keep. The lag bound
constant `_PENDING_BOWLER_BALL_CREDIT_MAX_LAG=40` is moved to §7 Conditional, gated on
production ORPHAN-rate telemetry — if ORPHANED traces are rare, the constant becomes unused
configuration.

**S4a step (ii) (Path B deletion) remains in scope** but is gated on the same production
observability run: a full session producing zero `PATH-B-FIRED` traces is the precondition
for removing the COLD_START_PHYSICS_PROMOTE construction at `score_manager.py:2266-2290`.

### 7.2 Audit checklist for any §7 deletion

Before any item moves from "candidate" to "shipped deletion":

1. **Enumerate all callers** of the symbol under deletion (Grep, exhaustive).
2. **Classify each caller** as init / transition / preserved / consumer / producer.
3. **Cross-reference with adjacent state mechanisms** (queues, drains, tracker callbacks,
   archive hooks). If the symbol participates in a race, enumerate every ordering.
4. **Equivalence proof.** If the proposed replacement collapses N callers into 1 hook,
   demonstrate that all N's preconditions / postconditions are preserved.
5. **State variable lifecycle.** For every helper variable introduced or affected, trace
   reset / clear / accumulation points.
6. **Predicted flip gate.** Predict the assertion-library flip count BEFORE the dry-run. If
   the dry-run diverges from the predicted band, pause and re-audit — do not ship.

The S4b cycle violated steps 3 and 4 (the first attempt assumed a single trigger; the
second attempt assumed a single transition site covered all orderings). Both regressed at
Layer 2 in ways the audit would have caught.

### 7.3 Pre-emptive audit of remaining §7 targets (2026-05-20)

Applying the §7.2 checklist to S5 (Scout output schema shrink) and S6 (`_ScoutRetryBuffer`)
before either ships, to avoid repeating the S4b cycle.

**S5 — broadcast field deletion is three sub-deletions, not one.**

Callers enumerated across `files/score_manager.py`, `files/test_pipeline.py`,
`files/cricket_rules.py`, and the test fixtures (`test_recent_fixes.py`,
`test_pipeline_reliability_batch.py`, `test_extras_inference_hardening.py`,
`verify_frames.py`). Three sub-items, three distinct consumer chains:

- **`broadcast_extra` → S5a CLOSED NOT-A-DEFECT (see §7.5).** Initial classification as a
  zero-flip rename was wrong. `broadcast_extra` and `extras_type` are not aliases — they
  occupy opposite sides of the legal/illegal-delivery axis (frame-level WIDE/NO_BALL
  discriminator vs event-level bye/leg-bye subtype label). Both fields moved to §7 Keep.

- **`broadcast_striker` → S5b (gated on striker-derivation equivalence proof).** Consumer
  threads through `test_pipeline.py:11296-11320` into `_set_slot_pair` for W3–W6 striker
  identification. Before deletion, enumerate every other striker-derivation source
  (`_set_slot_pair` call sites, broadcast-strip-independent paths) and prove the 9-fixture
  Layer 2 corpus still resolves striker correctly with `broadcast_striker=None` at every
  frame. The current striker tracker has separate lock semantics; the broadcast field
  contributes a parallel signal that the tracker may depend on for cold-start.

- **`broadcast_this_over` → S5c (gated on S3 shipping first).** Consumer is the `?`-slot
  backfill in `_update_supplements` and downstream `_pending_slots` paths. Both of those are
  already on the §7 Delete list (under the S3 dispatch-loop redesign). If S3 lands, S5c's
  consumers shrink to zero and the field deletion becomes mechanical. If S3 does not land
  (Queue A turns out to also be load-bearing — same risk as S4b), S5c blocks.

**Split S5 into S5a / S5b / S5c.** Each gets its own audit + flip-prediction + dry-run.

**S6 — `_ScoutRetryBuffer` is mis-classified; move to Keep.**

Callers: `files/eyes/openscout_loop.py:74` (class), `:262` (instantiation), `:292`
(`drop_stale` during backoff sweep), `:309` (`peek_oldest` for retry preference),
`files/tests/test_openscout_loop.py:344-347` (unit test).

Original §7 rationale: "subsumed by Frame Fate Ledger." This is wrong. The ledger answers
*"what happened to frame F?"* (a passive observability record). The retry buffer answers
*"which frames need re-classification after a Groq 429 clears?"* (an active queue that
survives backoff across producer-slot overwrites). These are orthogonal concerns. The
ledger does not hold frames for retry; deleting the buffer would drop un-scouted frames on
the next producer tick during any 429 backoff window.

**Action.** Move `_ScoutRetryBuffer` from §7 Delete to §7 Keep with the orthogonal-concern
rationale. Same lesson as Queue B: the §7 list inherited a "subsumed by X" claim that did
not survive enumeration of its actual callers.

**Memo §7 Delete-list status after this pass.**

| Item | Verdict | Next action |
|---|---|---|
| `PendingBall` + `_pending_ball_queue` (Queue A) | Audit pending | S3 dispatch-loop redesign first |
| `_over_archive_pending` | Audit pending | per-item audit before deletion |
| `_pending_slots` + `?` placeholder | Audit pending | S3 territory |
| `on_broadcast_override` wholesale-accept | Already shipped (broadcast G) | mark Done |
| `_merge_broadcast` normalizer | Audit pending | enumerate callers |
| `MAX_THIS_OVER_LEN=9` | Audit pending | enumerate callers |
| MULTI_BALL gap decomposition | Audit pending | S3 territory |
| `MULTI-BALL-DERIVATION-EXPANDED` trace tag | Already deprecated | mark Done |
| P1 striker-indicator matcher | **Done** (removed 2026-05-19) | per §7.6 — the P1 fallback in `_apply_wicket_fall_only` was deleted as semantically backwards |
| `[SM-W8-DISMISSED-GUARD]` | Audit pending | enumerate callers |
| `broadcast_extra` | **Reclassified Keep** | per §7.5 — frame-level WIDE/NO_BALL discriminator, distinct role from `extras_type` |
| `broadcast_this_over` | **Split S5c** | per §7.3 above; gated on dispatch-loop redesign + ?-slot path removal |
| `broadcast_striker` | **Split S5b-1/2/3** | per §7.6 — observability cleanup (S5b-1, clean delete), ambiguity-tiebreaker (S5b-2, audit-pending corpus check), initial-striker resolution (S5b-3, audit-pending cold-start equivalence) |
| `_ScoutRetryBuffer` | **Reclassify Keep** | per §7.3 above |
| `_PENDING_BOWLER_BALL_CREDIT_MAX_LAG = 40` | Conditional | gated on production ORPHAN-rate |
| `_pending_bowler_ball_credits` queue (Queue B) | **Reclassified Keep** | §7.1 |

### 7.4 Audit-pending sweep results (2026-05-20)

Applied the §7.2 six-gate checklist to every "Audit pending" item from §7.3. Net result:
three items were already shipped, three reclassified to Conditional (gated on
architectural changes that haven't shipped), one bundled with S5b, one Keep, one deferred.
Zero items survived as "ready to delete now."

The §7 list, post-sweep, is no longer a deletion queue — it is a dependency graph keyed on
two upstream pieces of work (MULTI_BALL deletion + observability run) and one orthogonal
audit (S5b striker-derivation equivalence). Reading it as a deletion queue is what drove
S4b's regression; the sweep makes the dependency structure explicit.

**Item-by-item findings.**

- **Queue A (`PendingBall` + `_pending_ball_queue`) → Conditional.** Structurally identical
  to Queue B: producer (`_enqueue_pending_ball` at `score_manager.py:602-653`, canonical
  caller `_decompose_multi_ball`) + drain (`_drain_pending_queue` at `:718-754`) wired into
  the same on_lock callbacks (`test_pipeline.py:7211-7232`). Multi-trigger consumer set:
  bowler-lock resweep, striker-lock resweep, pre-archive retry
  (`_attempt_pending_archive_drain` at `:775-854`), force-flush deadlines. The queue
  mechanism itself is load-bearing for the current MULTI_BALL/ABSORBED_LEGAL handling path.
  **Deletion is gated on MULTI_BALL gap decomposition deletion shipping first.** Once
  MULTI_BALL events stop firing, the producer has no input and the queue can be removed
  mechanically.

- **`_over_archive_pending` → Conditional.** Direct dependency on Queue A — exists solely
  to defer over-history archive when Queue A is non-empty at over rollover
  (`_attempt_pending_archive_drain` at `:780, :785`, set at `:5325, :5573`, cleared at
  `:891`). Sibling of Queue A; same deletion gate.

- **`_pending_slots` (this_over.py) → Conditional.** Producer at `this_over.py:673, :718`
  (ABSORBED_LEGAL + MULTI_BALL handlers), consumer at `:757` (`rewrite_token`, called by
  SM's `_drain_pending_queue`). Tied to the same MULTI_BALL/ABSORBED_LEGAL producers as
  Queue A — without those event types, no `?` placeholder is appended and `_pending_slots`
  has no entries. Same deletion gate.

- **`_merge_broadcast` → Done.** Already removed 2026-05-20 (broadcast G, option G).
  Confirmed absent from `eyes/this_over.py` and `score_manager.py`. Stale comment-only
  references remain in `test_recent_fixes.py:5173, :5218, :5375`; cleanup is orthogonal.

- **`MAX_THIS_OVER_LEN` → Done (stale test import).** Already removed 2026-05-20.
  Confirmed absent from `eyes/this_over.py`. **Broken import** at
  `test_recent_fixes.py:1057` — will fail on next test run. Stale-import cleanup needed.

- **`on_broadcast_override` → Done (stale test call).** Already removed 2026-05-20.
  Confirmed only `audit_scar_tissue_targets.py` references the name. **Broken call** at
  `test_recent_fixes.py:1060` — will fail on next test run. Stale-test cleanup needed.

- **MULTI_BALL gap decomposition → Audit pending, deferred.** 17 files reference. Wired
  through `score_manager.py`, `eyes/this_over.py`, `eyes/commentary.py`, `cricket_rules.py`,
  `wire.py`, `eyes/agent.py`, plus test fixtures. The `_apply_event(event, prev, card)`
  dispatch loop passes the same `(prev, card)` for every event in a frame's event list,
  which means `_decompose_multi_ball` cannot be cleanly extracted without the dispatch-loop
  redesign called out in the conversation summary as the "S3 / S4c" blocker. **Deferred
  pending dispatch-loop redesign workstream.**

- **`MULTI-BALL-DERIVATION-EXPANDED` trace tag → Done (deprecated).** Already marked
  deprecated in `trace_emitter.py`. No live emission sites.

- **`on_broadcast_override` wholesale-accept → Done.** See above.

- **P1 striker-indicator matcher → Bundle with S5b.** Already neutralized at
  `score_manager.py:4241-4269`: deterministic striker rotation suppresses broadcast/strip
  writes mid-over (the `STRIKER-SM-BROADCAST-DISAGREES-DETERMINISTIC` log path keeps SM's
  rotation as the sole authority). The broadcast indicator is still *read*, but its
  authority is gone. True deletion of the matcher overlaps directly with S5b's
  `broadcast_striker` deletion audit (S5b must enumerate every striker derivation site;
  the matcher is one such site). **Bundle into S5b.**

- **`[SM-W8-DISMISSED-GUARD]` re-introduction suppression → Keep.** The guard itself
  (`_sm_w8_partner_if_active` at `score_manager.py:4101-4122`) prevents re-introducing
  dismissed batters as partner names — load-bearing for the Lever 1 PR3 dismissal
  invariants. The `_w8_guard_fired` dedup set (`:481`) is one variable + one membership
  check; no meaningful scar tissue to remove. Production monitoring at
  `live_match_monitor.py:1058-1060` alerts when this fires more than expected, so the
  telemetry has an active consumer.

**Final §7 candidate list (post-sweep).**

| Status | Items |
|---|---|
| **Keep** (load-bearing) | `_pending_bowler_ball_credits` (Queue B), `_pending_bowler_wickets` (F381 queue), `_PENDING_WICKET_MAX_FRAME_LAG=40`, `_ScoutRetryBuffer`, `[SM-W8-DISMISSED-GUARD]` guard + dedup, `broadcast_extra` (frame-level discriminator), `extras_type` (event-level subtype label), other §7 Keep items |
| **Done** (already shipped) | `_merge_broadcast`, `MAX_THIS_OVER_LEN`, `on_broadcast_override`, `MULTI-BALL-DERIVATION-EXPANDED` trace tag |
| **Conditional** (gated on architectural changes) | Queue A + `_over_archive_pending` + `_pending_slots` (gated on MULTI_BALL deletion), `_PENDING_BOWLER_BALL_CREDIT_MAX_LAG=40` (gated on production ORPHAN-rate) |
| **Deferred** (blocks on workstream) | MULTI_BALL gap decomposition (dispatch-loop redesign) |
| **Split** (sub-audits required) | S5b-1 / S5b-2 / S5b-3 / S5c (S5a closed NOT-A-DEFECT per §7.5; P1 striker-indicator matcher already Done per §7.6) |

**Predicted-flip impact for executable deletions.**

After the sweep + the deeper 6-gate audit run on 2026-05-20:

1. **S5a (`broadcast_extra` → `extras_type` rename/unification) — CLOSED NOT-A-DEFECT
   per §7.5.** The §7.3 zero-flip classification was wrong and the deeper audit confirmed
   the fields cannot be unified at all: they sit on opposite sides of the legal/illegal
   delivery axis. Both moved to §7 Keep with explicit role labels.

2. **Stale-test cleanup (shipped 2026-05-20).** Eight dead tests in
   `test_recent_fixes.py` exercised removed APIs (`on_broadcast_override`,
   `MAX_THIS_OVER_LEN`, `_merge_broadcast`-canonicalisation behavior, the
   `_update_supplements` broadcast backfill block deleted under broadcast G). Removed:
   `test_this_over_multi_over_recap_rejected`,
   `test_this_over_cold_start_short_broadcast_accepted`,
   `test_this_over_alphabet_rejects_speed_tokens_f2461`,
   `test_this_over_alphabet_rejects_2026_04_16_garbage`,
   `test_this_over_alphabet_accepts_legal_sequence`,
   `test_this_over_alphabet_rejects_mixed_list`,
   `test_p8_score_mgr_backfill_validates_alphabet`,
   `test_p8_score_mgr_backfill_accepts_legal_alphabet`. Also trimmed the dead
   `on_broadcast_override` half of `test_fixture_multi_ball_gap_camera_state_transition`,
   keeping its surviving MULTI_BALL placeholder assertions. Predicted flips: 0 (test
   removal only; no production code touched).

Every other §7 item is gated on upstream work. The "deletion plan" in §7's original
framing is, post-audit, mostly a *cleanup follow-up* for two architectural workstreams
(dispatch-loop redesign, production observability run) plus two orthogonal audits (S5a
re-audit, S5b striker-derivation audit). There is no shortcut path that lets us collapse
the §7 list ahead of those.

### 7.5 S5a architectural-unification audit — verdict NOT-A-DEFECT (2026-05-20)

Followed the §7.2 six-gate checklist against the underlying premise of S5a (that
`broadcast_extra` and `extras_type` are duplicate fields suitable for unification).
Verdict: **NOT-A-DEFECT.** The two fields serve distinct, non-overlapping roles in the
dispatch architecture and cannot be unified without losing semantic precision.

**Gate 1+2 — caller enumeration and classification.**

| Field | Role | Sites |
|---|---|---|
| `broadcast_extra` | discriminator | producer: `test_pipeline.py:1804-1806` (Scout result → `result["broadcast_extra"] = "WD"/"NB"`); consumers: `score_manager.py:3303-3322` (deferred-fire gate), `:4636-4647` (`_infer_event` hard-signal classifier), `:4744-4750` (`_infer_extra` returns WIDE vs NO_BALL based on value), `:6023-6028` (`_try_resolve_pending` post-deferral resolver); `eyes/commentary.py:63-127` (frame-level OCR signal storage + freshness check) |
| `extras_type` | subtype label | producer: `eyes/commentary.py:485` (sets `event["extras_type"] = "leg_bye_or_bye"` on regular-run events when bowler runs flat but score moved); consumers: `score_manager.py:5169` (subtype read for context), `eyes/this_over.py:696` (renders `{r}lb` token instead of raw digit), `commentary/context_builder.py:143` (commentary context) |

**Gate 3 — cross-reference adjacent state.** The two fields are at different positions
in the event-classification pipeline:

- `broadcast_extra ∈ {"WD", "NB", None}` is an *OCR-detected discriminator* read from
  the broadcast strip. Its value picks between two **event types**: `event.type =
  "WIDE"` (illegal delivery, doesn't count as legal ball) vs `event.type = "NO_BALL"`
  (illegal delivery, free hit next). The discriminator role IS the value.

- `extras_type ∈ {"leg_bye_or_bye", None}` is a *subtype label* on a committed
  regular-run event whose `event.type` is already classified as a legal delivery. The
  subtype refines attribution (run went to extras column, not batter) without changing
  event type or legality.

The fields sit on opposite sides of the **legal/illegal delivery axis**: `broadcast_extra`
discriminates illegal-delivery subtypes (WD/NB); `extras_type` labels a legal-delivery
attribution variant (bye/leg-bye). Collapsing them would require either promoting WIDE
and NO_BALL from event types to `extras_type` subtypes (losing the legal/illegal axis) or
splitting `broadcast_extra` into separate signals (same complexity, different shape).
Neither move adds clarity.

**Gate 4 — equivalence proof.** No unified field can carry both semantics. A field with
values `{wide, no_ball, bye, leg_bye, none}` collapses the legal/illegal distinction; the
consumers that currently key on event.type (`score_manager.py:5169-5180` subtype dispatch
plus the entire legal-ball-count derivation) would need a parallel signal anyway.
Equivalence fails by construction.

**Gate 5 — lifecycle.** `broadcast_extra` is frame-bound (cleared on next frame's read,
freshness tracked via `_broadcast_extra_changed_at`). `extras_type` is event-bound
(persists for the lifetime of the committed event in `over_history`). The lifecycle
mismatch confirms the abstraction-level mismatch from gate 3.

**Gate 6 — predicted flips.** Moot; the unification is rejected at gate 4.

**Verdict.** Both fields move to §7 Keep with explicit role labels. The §7 memo's
"renamed from wholesale `broadcast_extra`" framing was based on an incomplete reading of
the two fields' roles — it conflated the OCR-detection-signal field with the
event-subtype-label field because both occupy the "extras" lexical region.

**Same lesson as Queue B and `_ScoutRetryBuffer`** (now confirmed three times across
this workstream): the §7 memo inherited "scar tissue" labels that assumed semantic
duplication. Each per-item audit has reclassified the labelled item to Keep with a
distinct architectural role. The §7.2 six-gate checklist as standing precondition is
load-bearing; without it, all three would have been speculative deletions matching the
S4b regression pattern.

**Optional cosmetic improvement (not S5a).** A mechanical rename
`broadcast_extra → extras_discriminator` or `broadcast_wide_no_ball_signal` would surface
the asymmetry with `extras_type` and prevent future readers from repeating the
unification mistake. That is a small, isolated rename — audit-clean if pursued, but
zero leverage on §7's actual goal. Park unless a future reader trips on the same
confusion.

**Closing.** S5a is closed as NOT-A-DEFECT. The Keep table is updated. No code change
this turn; memo-only output per the audit's expectation.

### 7.6 S5b audit — `broadcast_striker` derivation equivalence (2026-05-20)

Six-gate checklist applied to S5b. Verdict: **SPLIT.** Field's write authority is already
neutralized by the deterministic rotation override; remaining consumers split into pure
observability (clean delete) and load-bearing fallbacks for cold-start / ambiguity
edge cases (audit-pending).

**Gate 1 — caller enumeration.**

| Site | Role | Authority |
|---|---|---|
| `test_pipeline.py:1783, :8374, :13823` | producer (Scout strip OCR `m.group(1).strip()` → frame.broadcast_striker) | input source |
| `score_manager.py:238-243` | FrameInput dataclass field | container |
| `score_manager.py:1616` | frame→card propagation | plumbing |
| `score_manager.py:1633` | canonicalisation allowlist (squad-key resolver) | defense-in-depth |
| `score_manager.py:4283-4293` | `_identify_and_set` Priority 3 striker resolution | **gated by deterministic override at `:4295-4325`** |
| `score_manager.py:4689-4698` | `_identify_striker` ambiguity tiebreaker | active fallback when balls-delta cross-match ambiguous |
| `score_manager.py:4318-4325` | `STRIKER-SM-BROADCAST-DISAGREES-DETERMINISTIC` trace | observability only |
| `score_manager.py:4994` | `_apply_wicket_fall_only` log message | debug only (P1 path REMOVED 2026-05-19) |
| `tests/symptom_class_assertions.py:369` | class 9 assertion (misnamed) | **does NOT read broadcast_striker** — compares ws_payload.striker to ledger's striker_after_rotation |

**Gate 2 — classification.**

- (a) **Detection-of-striker-identity** (active write authority): `:4283-4293` Priority 3
  in `_identify_and_set` + `:4689-4698` fallback in `_identify_striker`. The first is
  WARM-mode re-identification; the second is event-inference ambiguity tiebreaker.
- (b) **Corroboration-of-derived-state**: `STRIKER-SM-BROADCAST-DISAGREES-DETERMINISTIC`
  trace at `:4318-4325`. Records *when* the broadcast disagrees with derivation; the
  disagreement is resolved in favor of derivation. Pure observability.
- (c) **Other / debug**: `:4994` log message in `_apply_wicket_fall_only` (P1 path
  already deleted 2026-05-19 — the remaining log line just echoes the field for
  context), `:1633` canonicalisation allowlist (defense-in-depth).
- Class 9 assertion is misnamed: it's a *derivation-correctness* assertion, not a
  *broadcast-vs-derivation* assertion. Removing `broadcast_striker` does not affect it.

**Gate 3 — cross-reference adjacent state.** The deterministic rotation override
(`:4295-4325`, committed 2026-05-19 / 2105463) is the load-bearing architectural change
here. Once `self.striker is not None`, every broadcast-derived striker write is
**rejected** with the disagreement trace. So `broadcast_striker`'s residual write
authority is restricted to:

1. **Initial-striker resolution when `self.striker is None`** at WARM re-entry — the
   `else` branch at `:4326-4331` calls `_set_slot_pair(new, _ns, source="...")`.
2. **`_identify_striker` ambiguity tiebreaker** when balls-delta cross-match gives no
   unique striker AND state hasn't locked yet — same cold-start condition.

Both authoritative consumers share a single condition: **`self.striker` is `None` at
the moment of inference**. Outside that condition, the deterministic override neutralizes
the field.

**Gate 4 — equivalence proof.** Can derivation alone cover the residual authority?

The residual authority handles the cold-start initial-striker case. Pure derivation
cannot produce an initial striker — it has to come from somewhere upstream
(`_accept_initial:2785` sets bat1/bat2 from card; `_resume_from_cache_hot:2687` restores
`current_bowler` from cache but does not necessarily restore the striker). The cases
where `self.striker is None` at WARM event inference:

- **Cold-start → WARM transition.** `_accept_initial` sets bat1/bat2 but doesn't always
  resolve which is on strike — broadcast_striker first-name match at `:4283-4293` fills
  this in on the first frame where Scout sees the striker indicator.
- **Hot-resume from cache.** `_resume_from_cache_hot` restores `current_bowler` from
  cache but the striker slot might be empty depending on cache shape.
- **Post-wicket pre-new-batter.** Between wicket commit and new-batter announcement, the
  striker slot can be transiently None.

Removing broadcast_striker would leave each of these without a fallback path; the
SM-derived striker would stay None until a ball-event commits and `_apply_event`'s
rotation logic can derive from balls-delta. Whether this matters in practice depends on
whether downstream consumers (UI, commentary) tolerate transient None.

**Equivalence verdict**: derivation alone covers (a) consumers IF and ONLY IF the
upstream initial-striker resolution paths (`_accept_initial`, `_resume_from_cache_hot`)
are themselves load-bearing enough to set striker before WARM event inference fires.
**That equivalence is not currently proven** — it requires its own audit.

**Gate 5 — lifecycle.** `broadcast_striker` is frame-bound (set by Scout per frame,
consumed within the same frame's `on_frame`). `self.striker` is event-bound (set at
innings init, rotated per ball event). The deterministic override makes derivation
authoritative once locked; broadcast_striker lags after the first ball event.

**Gate 6 — predicted flip.**

- **Class 9 assertion**: zero flip (misnamed; doesn't read broadcast_striker).
- **Layer 1.5 / Layer 2 baseline**: unknown without execution. The L2 fixture's 29-ball
  corpus has cold-start in the early frames; if `_accept_initial`'s striker resolution
  is sufficient, baseline holds. If not, frames before the first ball commit might lose
  striker resolution and flip downstream invariants.
- **Production observability**: cold-start corner cases may surface striker = None
  transients that broadcast_striker currently smooths over.

**Verdict — SPLIT into three sub-audits.**

| Sub-item | Scope | Disposition |
|---|---|---|
| **S5b-1** | Observability/debug consumers: trace at `:4318-4325`, log at `:4994`, canonicalisation allowlist at `:1633`, FrameInput dataclass field plumbing | Clean delete eligible — zero authority; observability removal is intentional cleanup once the field is gone elsewhere. Predicted flips zero. Gate: comes LAST in the deletion sequence, not first. |
| **S5b-2** | `_identify_striker` ambiguity tiebreaker (`:4689-4698`) | Removal needs equivalence proof that state-fallback (`self.striker, self.non, ...`) covers every cross-match-ambiguous case. Likely safe IF deterministic locks early; needs corpus-level confirmation. |
| **S5b-3** | `_identify_and_set` Priority 3 (`:4283-4293`) — initial-striker resolution | **Load-bearing fallback** for cold-start / hot-resume / post-wicket-pre-new-batter cases where `self.striker is None`. Removal requires auditing `_accept_initial`, `_resume_from_cache_hot`, and the post-wicket gap to confirm initial-striker is set via another path. This is the cold-start striker derivation audit the §7 memo's S5b originally implied — substantially larger scope than a field-deletion. |

**Same lesson as Queue B / `_ScoutRetryBuffer` / S5a, now confirmed four times.** The §7
memo framed broadcast_striker as "wholesale delete" because the deterministic rotation
override (2105463) made it look authoritative-redundant. The deeper audit reveals: the
override deprecates broadcast_striker *mid-over* but leaves it load-bearing *at the
boundary frames* (cold-start, hot-resume, post-wicket gap). Wholesale deletion is not
the right shape — the right shape is sub-decomposition with the cold-start audit as the
load-bearing gate.

**P1 striker-indicator matcher.** §7.4 listed it as "Bundle with S5b." Per this audit,
the P1 matcher in `_apply_wicket_fall_only` (`:4960-4978`) was already **removed
2026-05-19** as semantically backwards (a striker indicator points at a still-at-the-
crease batter, not a dismissed one). The remaining "P1 striker-indicator matcher" entry
in §7 Delete is **already Done**. Marked complete.

**Memo state.** S5b moves from "Split S5a/b/c" to "Split S5b-1/2/3" with explicit
disposition per sub-item. S5b-1 is clean-delete eligible (comes last); S5b-2 needs a
corpus equivalence check; S5b-3 requires a cold-start initial-striker derivation audit
that is substantially larger than a field deletion.

**Sequence recommendation** (updated 2026-05-20 after the sweep + early execution):

1. ✅ Shipped: stale-test cleanup (`192be39`). Memo updates + dispatch-loop scoping doc
   (`8f8a7c7`). Dispatch-loop scaffold with shadow comparison (`95e6ff5`). S5a closed
   NOT-A-DEFECT per §7.5 (memo-only, no code commit).
2. **In progress (operational waiting):** production observability run. Two signals
   accumulating in parallel — `PATH-B-FIRED` rate (gates S4a step (ii)),
   `PENDING-BOWLER-BALL-CREDIT-ORPHANED` rate (gates `_PENDING_BOWLER_BALL_CREDIT_MAX_LAG`
   decision), `DISPATCH-LOOP-SHADOW-COMPARISON` divergence patterns (gates
   `SM_INLINE_MULTI_BALL` flag flip).
3. **S5b audit complete per §7.6 (2026-05-20).** Split into S5b-1 (observability cleanup,
   clean delete eligible), S5b-2 (ambiguity tiebreaker, needs corpus check), S5b-3
   (initial-striker resolution, needs cold-start derivation audit). P1 striker-indicator
   matcher confirmed Done. Next concrete deliverable in this thread: S5b-2 corpus
   equivalence check or S5b-3 cold-start audit, depending on which gates the
   observability run does not already cover.
4. **After observability data settles:** flag flip for `SM_INLINE_MULTI_BALL` if zero
   shadow divergence, followed by coordinated deletion of Queue A + `_over_archive_pending`
   + `_pending_slots` + MULTI_BALL decomposition.

The sweep's biggest output is *not* a deletion to ship — it is the dependency graph that
prevents the next S4b. Future per-item audits start from this map.

## 8. Risks and edge cases

1. **Innings-1 to innings-2 transition.** The first frame of innings 2 looks like a massive regression (`expected_next_ball` was 19.6, frame says 0.1). `set_innings_2()` reset must precede gap detection; existing detection at `score_manager.py:3335-3486` handles this.
2. **Free-hit balls.** A free-hit can produce 6 runs without a legal ball counting. Sub-primitive `is_free_hit: bool` may need promotion. Not blocking for diagnostic infrastructure; relevant for the eventual root-cause fixes.
3. **DRS reviews and TV-umpire pauses.** Scout pauses emitting STRIP for 10-30 seconds. No new balls during pause, no Δ≥2 at resume (same overs). Common-case acceptance.
4. **Bowler-change-mid-over edge cases** (injury, mankad, suspended over): bowler-lock latency handled by the preserved `_PENDING_WICKET_MAX_FRAME_LAG` path. Tunable independently.
5. **Rejection-source distribution varies across broadcasts (observed 2026-05-19).** DC-vs-KKR Tier 1 ~60/40 `warm_consensus` / `scoreboard_jump_limit`; GT-vs-RR 8a0c6c14 was 97/3. Dominant rejection source (`warm_consensus`) generalizes; broadcast-style variance affects only the SB hard-guard tail. Root-cause investigation should sample both broadcasts to avoid bias toward one rejection class.
6. **Structurally unfixable Δ≥2 residual.** If after root-cause fixes a small residual remains (e.g., DRS pause-resume frames where Scout legitimately couldn't read scoreboard for 10+ seconds), flag explicitly. Until proven unfixable, treat every Δ≥2 as a bug.

## 9. Phased rollout

| Stage | Scope | Status |
|---|---|---|
| **1** | `expected_next_ball` state + `[GAP-DETECTED]` trace tag (additive, no behavior change) | **shipped** `a57cdbd` |
| **2a** | `[GAP-AT-REJECTION]` tag at the three pre-`_accept_update` rejection sites | **shipped** `185bc39` |
| **2a'** | Route hot-resume + cold-exit commits through `_track_overs_advance` (close Stage 1 instrumentation hole) | **shipped** `ca85dd9` |
| **2b** | Secondary LLM resolution via Groq llama-3.1-8b-instant | **reverted** `5fe6768` / `97671cc` / `310bfe8` — failed eval gate (8B 33% / 70B 17% case-level vs 80% target). Root cause data-bound: Scout's `THIS OVER` null at gap frames. |
| **2c** | Frame Fate Ledger module + SM-side outcome wiring at 5 sites (`_accept_update` ACCEPTED_COMMIT, 2 OVERS-JUMP-IMPLAUSIBLE-REJECTED sites, SB jump-limit, pipeline CORRECTION_BLOCKED, team-change-pending). Audit hook shows 0 NOT_YET_SEEN across 9 fixtures = wiring complete. | **shipped** |
| **2d** | Dispatch-side scout_status wiring: `Vision.describe` records dispatch + response/timeout/error; `parse_strip` stamps extractor_outcome + scout_response_class (incl. DEGENERATE_NULL); SM `on_frame` lagged-by-one ACCEPTED_NOOP backfill. Audit refresh: 0 silent drops across 9 fixtures (3077/3077 frames have ledger entries). `_ScoutRetryBuffer` deletion deferred — orthogonal refactor, separate commit. | **shipped** |
| **3** | Steady-state Δ≥2 root-cause investigation: sample 20-30 events from the audit's 114, group by rejection class, propose per-class fix. | shipped (Stage 3 sample showed bimodal 52% scout_cadence_drop / 48% ocr_miss; Stage 3a sub-classification of ocr_miss showed 75% extractor/VLM-prompt fixable, of which the c-1 sub-class turned out to already be handled by current `parse_strip`) |
| **4** | Per-class root-cause fixes based on Ledger production data. Targets surface as ledger entries accumulate in real runs: `REJECTED_SCORE_CONSENSUS` → tune scorer correction threshold; `REJECTED_WARM_CONSENSUS` → tune `_OVERS_JUMP_CONSENSUS_FRAMES`; etc. | follows stage 2d + production-data collection |
| **5** | 5-primitive contract cutover. Delete pending-queue, `?` placeholder, wholesale-accept paths, MULTI_BALL infrastructure listed in §7. | follows stage 4 |

## 10. Open questions for review

1. **Structurally unfixable residual policy.** If a Δ≥2 class proves unfixable (e.g., DRS pauses), what's the SLA? Tag-and-accept, or fail-loud?
2. **Ledger persistence.** Per-session in-memory only, or written alongside trace records for post-hoc analysis? Recommend in-memory + dump-on-session-end for trace correlation.
3. **Root-cause investigation sample size.** 20-30 events is the minimum signal; more if any one class dominates. Should we also sample DC-vs-KKR rejection events (~111) since they're 3× the volume of GT-vs-RR rejection events (~38)?

## 11. Out of scope

- Crossed-batters-on-catch detection (rare; tag `STRIKER-DERIVATION-AMBIGUOUS` and accept).
- Retired-hurt / retired-out (low frequency; existing logic suffices).
- Innings-2 super-over / DLS recalculation (separate subsystem).
- Player-style commentary data flow.
- Synchronous gap resolution (deleted — see Stage 2b revert).

---

**Decision sought:** approval to proceed with stage 2c (Frame Fate Ledger build) and concurrent stage 3 (root-cause investigation of the audit's 114 steady-state Δ≥2 events).
