# No-MULTI_BALL Architecture — Design Memo

**Status:** Draft / pending approval
**Author:** derive-not-detect branch (Issue 1 scope)
**Date:** 2026-05-15
**Predecessors:** Investigation #1 (4-issue forensic), Investigation #2 (pre-design groundwork)

---

## 1. Motivation

Issue 1 from Investigation #1: during the "BE UNSTOPPABLE" promotional overlay
covering overs 4.0–4.3 of validation match `match_4621b9f8`, the pipeline
produced a `this_over` UI token sequence of `. . 5` (wrong) instead of `4 . 1`
(broadcast truth). Root cause was traced to two interacting failures:

- **Gap inference fired during overlay window** before bowler identity stabilised.
  Frame 276 (4.3 ov) decision: `GAP-TOKEN-INFERENCE n_balls=3 total_runs=5 →
  ['.', '.', '5']`. The heuristic in `infer_gap_tokens` distributes runs across
  unseen balls using a back-loaded policy (singles first, boundary last) that
  has no grounding in the actual ball-by-ball reality.
- **Bowler attribution lagged the synthesis.** `BOWLER-OVERRIDE-PENDING`
  accumulated 4 times at frame 276 with Tyagi not yet locked; Tyagi first
  appeared in scout text at frame 280+. The synthesised tokens were committed
  under Roy and permanently archived into `over_history[4]` before Tyagi
  resolved.

Investigation #2 established three structural facts that shape the redesign:

- **Strip recovery is unreliable.** `scout.raw_text_120` does not consistently
  emit a parseable `this_over=` field during/after overlay clears. A
  post-resume single-frame backfill cannot be trusted — token-parse confidence
  is low.
- **Gap depth is small.** In the 4.0–4.5 segment the deferred-ball depth was
  typically 1, never exceeded 3. A bounded pending queue (depth ≤6, typical
  ≤3) is sufficient.
- **`over_history` is first-write-wins.** Once `check_over_change()` archives
  `over_history[N]`, the entry is immutable. Any corrupt synthesis at over-end
  is baked in. The new architecture must defer the archive until pending
  resolution completes.

The fix shape: stop *inferring* ball tokens we did not observe. Defer commit
of ambiguous deltas into a per-ball pending queue. Render `"?"` placeholders
to the UI until the bowler/striker trackers lock and resolve the queue. If
trackers never resolve before a hard deadline, force-flush with placeholders
intact rather than fabricate tokens.

## 2. Architecture

### 2.1 Queue schema

```python
@dataclass
class PendingBall:
    frame_id: int
    runs_delta: int
    balls_delta: int = 1
    wickets_delta: int = 0
    observed_strip_tokens: list[str] = field(default_factory=list)
    bowler: Optional[str] = None
    striker: Optional[str] = None
    placeholder_token: str = "?"
    committed: bool = False
    slot_idx: Optional[int] = None  # index into this_over.this_over
```

ScoreManager holds: `self._pending_ball_queue: deque[PendingBall] = deque(maxlen=6)`.

### 2.2 Enqueue path

When `_infer_event` receives a delta that the validator classifies as
`DEFERRED_MULTI` (replacement for the deleted `MULTI_BALL` event_type), SM
fans out N `ABSORBED_LEGAL` events with `bowler=None`, `striker=None`. Each
calls `_enqueue_pending_ball(...)`, which:

1. Appends a `PendingBall` to the queue.
2. Calls `over_mgr.append_token("?")`; records the returned `slot_idx` on
   the queue entry and in `over_mgr._pending_slots[slot_idx] = pending_ball`.
3. Emits trace tag `PENDING-BALL-ENQUEUED`.

### 2.3 Drain triggers

`_drain_pending_queue(reason: str)` walks the queue head→tail (FIFO). For
each entry where both `bowler` and `striker` are non-None:

1. Apply `_apply_bowler_delta` (runs/balls/wickets to that bowler's card).
2. Apply `_apply_batter_delta` (runs/balls to that striker).
3. Derive the displayed token from `runs_delta` + `wickets_delta` (e.g.
   `"4"`, `"."`, `"W"`, `"6"`).
4. Call `over_mgr.rewrite_token(slot_idx, derived_token)` — in-place update.
5. Set `committed=True`; emit `PENDING-BALL-DRAINED`.

The walk halts at the first uncommitted entry (preserves FIFO ordering — a
later ball cannot commit before an earlier one even if its attribution
resolves first).

Three drain triggers:

- **bowler tracker on_lock callback:** resweep queue (fill `bowler=name` on
  matching role-pending entries), then drain.
- **striker tracker on_lock callback:** symmetric.
- **pre-archive retry:** at the top of `check_over_change()`, if a prior
  archive was deferred, attempt one drain before considering force-flush.

### 2.4 Resweep

`_resweep_pending_attribution(name, role)`: walks the queue, for each
uncommitted entry with `<role>=None` sets `<role>=name`. Distinct from drain
because attribution and commitment are decoupled — a queue entry may receive
its bowler from a lock event but still wait on striker, or vice versa.

### 2.5 UI rendering

`this_over.append_token("?")` appends literal `"?"` to `self.this_over` and
returns the slot index. The WS payload renders `"?"` as-is — the UI shows a
question mark in place of the unknown ball. On `rewrite_token(slot_idx,
token)` the slot is updated in place; existing WS broadcast machinery
publishes the change on the next frame.

`"?"` is distinct from `"·"` (centre dot, the existing "not yet bowled in
this over" placeholder). `"·"` means *no ball yet here*; `"?"` means *ball
was bowled but attribution is pending*.

### 2.6 Archive deferral

In `check_over_change()`, before archiving `over_history[N]`:

```python
if self._pending_ball_queue:
    emit_trace("OVER-ARCHIVE-DEFERRED-QUEUE-NONEMPTY",
               over=N, queue_depth=len(self._pending_ball_queue))
    self._over_archive_pending = N
    return  # skip archive this frame
```

On subsequent frames, the top of `check_over_change()` checks
`_over_archive_pending`; if set, attempt drain, archive if queue empty,
clear flag.

### 2.7 Force-flush deadline (tracker-state-aware)

Two-stage deadline.

**Soft deadline:** `ts_match.overs >= float(N + 1) + 0.3` (~2 balls into
the *following* over).

At the soft deadline, inspect `bowler_tracker.state`:

- If `state == PENDING_OVERRIDE` (an override candidate is accumulating
  streak but has not yet won the lock): emit
  `PENDING-BALL-FLUSH-EXTENDED-OVERRIDE-ACTIVE` with candidate name +
  current streak count; defer flush, extend deadline to the hard cap.
- Otherwise: proceed to force-flush.

**Hard cap:** `ts_match.overs >= float(N + 1) + 1.0` (one full over past
the deferred archive). At this point, force-flush regardless of tracker
state — absolute backstop, no further extensions.

Force-flush procedure (at whichever deadline fires):

- For each remaining entry, emit `PENDING-BALL-FORCED-FLUSH-UNRESOLVED` with
  the entry's known/unknown attribution fields.
- Commit each: runs/balls/wickets apply to the *current* tracker leader
  (best-guess bowler / first non-None striker in queue, falling back to
  `current_striker`). Token in `this_over` and `over_history[N]` remains
  `"?"` — we do not fabricate the displayed token.
- Archive `over_history[N]` with mixed real/`?` tokens; clear deferral flag.

Rationale: the soft deadline catches the common case (overlay clears, both
trackers lock within ~14s wall). The PENDING_OVERRIDE extension addresses
the §6.1 timing contradiction — typical override resolution takes 5–8
frames (~35–56s wall at observed 7s/frame cadence), which exceeds the soft
deadline. The hard cap (one full following over) backstops pathological
multi-over stalls without permitting unbounded queue growth.

### 2.8 Tracker hooks

`ConfidenceTracker` grows a single optional callback:

```python
on_lock: Optional[Callable[[str], None]] = None
```

invoked on the state transition that produces `LOCKED`. SM init wires:

```python
bowler_tracker.on_lock = lambda name: (
    self._resweep_pending_attribution(name, "bowler"),
    self._drain_pending_queue("bowler-lock"))
striker_tracker.on_lock = lambda name: (
    self._resweep_pending_attribution(name, "striker"),
    self._drain_pending_queue("striker-lock"))
```

No other tracker behaviour changes. Re-entrancy: the callback runs
synchronously during the tracker's state transition; SM operations triggered
inside it must not re-enter the tracker. The drain path calls
`_apply_bowler_delta` / `_apply_batter_delta`, which today do not invoke the
tracker — verify before STEP 3.

## 3. Deletion scope

From Investigation #2 Q3. Exact file:line list of code to delete or
replace:

**Delete (gap-synthesis path):**

| File | Lines | Symbol |
|------|-------|--------|
| `files/cricket_rules.py` | 37–38 | `MULTI_BALL_MAX_BALLS`, `MULTI_BALL_MAX_WKT` constants |
| `files/cricket_rules.py` | 372 | `ValidationResult(event_type="MULTI_BALL")` — change to `"DEFERRED_MULTI"` |
| `files/cricket_rules.py` | 649–704 | `infer_gap_tokens()` heuristic core |
| `files/score_manager.py` | 18 | import of MULTI_BALL_MAX_* constants |
| `files/score_manager.py` | 80–85 | `_warn_multi_ball_cap_if_cricket_reject` |
| `files/score_manager.py` | 3410 | `[MULTI_BALL_DECOMPOSED]` log tag |
| `files/score_manager.py` | 3441 | comment referencing MULTI_BALL synthesis |

**Replace with per-ball pending queue:**

| File | Lines | Symbol |
|------|-------|--------|
| `files/eyes/this_over.py` | 592–619 | `MULTI_BALL` consumer/decomposer (primary bug site) |

**Keep (cold-start synthesis is separate):**

| File | Lines | Symbol |
|------|-------|--------|
| `files/score_manager.py` | 238 | `COLD_START_MULTI_BALL_MAX_BALLS = 3` |
| `files/score_manager.py` | 1641–1722 | `_synthesize_cold_start_ball_events` |
| `files/eyes/this_over.py` | 1307–1316 | `fill_strip_coverage_gap` cold-start prefill |

Cold-start synthesis is the only allowed heuristic site. It addresses a
different problem (pipeline join mid-innings with non-zero scoreboard) and
does not suffer the bowler-identity bug because at cold-start, the bowler
*is* the current scoreboard bowler by construction.

## 4. Migration sequence

Four commits on `derive-not-detect`, no batching.

**B1.1 — `feat(no-multi-ball): pending ball queue infrastructure`**
- `PendingBall` dataclass + queue in SM
- `_enqueue_pending_ball`, `_drain_pending_queue`, `_resweep_pending_attribution`
- 6 new trace tags registered
- `files/tests/test_pending_ball_queue.py` (5 cases)

**B1.2 — `feat(no-multi-ball): replace MULTI_BALL producer with pending queue`**
- Delete constants + `infer_gap_tokens` + warn helper + import
- Rename validator event_type `MULTI_BALL` → `DEFERRED_MULTI`
- `_infer_event` fans out `DEFERRED_MULTI` → N×`ABSORBED_LEGAL` enqueues
- `this_over.py:592-619` MULTI_BALL handler deleted
- `this_over.py` gains `_pending_slots` map + `rewrite_token()`
- BED `commentary.py` MULTI_BALL advisory → per-ball ABSORBED_LEGAL
- Update `test_anomaly_rules.py` for rename
- New `files/tests/test_this_over_pending.py`

**B1.3 — `feat(no-multi-ball): write-deferred over_history archive + force-flush`**
- `_over_archive_pending` state + check_over_change deferral
- Two-stage force-flush deadline: soft (`overs >= N+1.3`) with
  tracker-state extension on PENDING_OVERRIDE, hard cap (`overs >= N+2.0`)
- 7th trace tag `PENDING-BALL-FLUSH-EXTENDED-OVERRIDE-ACTIVE` registered
- `confidence_tracker.py` gains `on_lock` callback hook
- SM init wires bowler/striker `on_lock`
- New `files/tests/test_over_archive_deferral.py` (4 cases — adds
  extension-active scenario)

**B1.4 — `chore(no-multi-ball): cleanup remaining refs + docs`**
- Grep MULTI_BALL across repo; clean non-test refs
- Update `files/docs/operations/trace_and_detect_setup.md` (6 new tags)
- Update `CLAUDE.md` trace-tag glossary
- Strike out MULTI_BALL line in `derivation_only_stats_design.md` §Deferred

## 5. Validation criteria

Replay `match_4621b9f8.mp4` from 10:40 timestamp through over 6.

**Trace-tag count expectations** (on the resulting `logs/trace/watch_*.jsonl`):

| Tag | Expected count |
|-----|---------------|
| `GAP-TOKEN-INFERENCE` | **0** (function deleted) |
| `MULTI-BALL-DERIVATION-EXPANDED` | **0** (path deleted) |
| `PENDING-BALL-ENQUEUED` | ≥3 (overs 4–5 overlay window) |
| `PENDING-BALL-DRAINED` | == `PENDING-BALL-ENQUEUED` minus force-flush count |
| `PENDING-BALL-FORCED-FLUSH-UNRESOLVED` | **0** (ideal) |
| `OVER-ARCHIVE-DEFERRED-QUEUE-NONEMPTY` | ≥1 (over 4 archive deferred) |
| `PENDING-BALL-FLUSH-EXTENDED-OVERRIDE-ACTIVE` | 0–2 (acceptable; safety-valve fires when PENDING_OVERRIDE outlasts soft deadline) |

**UI acceptance:**

- `bowling_card[Roy].overs` at `5.0` ov == `1.0` (NOT `2.0`)
- `bowling_card[Tyagi]` BOWLING-CARD-CREATED fires at over-5 start
- `this_over` at `4.3` progresses `1 → 1 4 → 1 4 . → ...`; NEVER `. . 5`
- `over_history[4]` final tokens match broadcast at archive time

Validation script: `python files/analyze_trace.py logs/trace/<latest>.jsonl
--report files/docs/match_reports/no_multiball_validation.md`.

## 6. Risks

### 6.1 Force-flush fires with wrong attribution

If the bowler tracker fails to lock within the 0.3-over deadline, queued
balls commit under the best-guess bowler (likely the prior over's bowler).
This is worse than current behaviour *for that one over* because runs/balls
get credited to the wrong card, but better in two ways: (a) the UI shows
`"?"` so the user knows something is unresolved; (b) it does not fabricate
fake ball tokens like `. . 5`.

**Mitigation:** the soft deadline at `(N+1)+0.3` (~14s wall) catches the
common case where the overlay clears quickly. For the §2.4 scenario where
`bowler_tracker.state == PENDING_OVERRIDE` is still accumulating at the
soft deadline, §2.7 extends to the hard cap `(N+1)+1.0` — this covers the
empirical 5–8 frame (~35–56s wall at 7s/frame cadence) override resolution
window observed in Investigation #2 Q4. Hard cap guarantees forward
progress without permitting unbounded queue growth.

### 6.2 Cold-start synth path interaction

`_synthesize_cold_start_ball_events` (`score_manager.py:1641-1722`) remains
unchanged. It runs on first ACCEPT when the pipeline joins mid-match with a
non-zero scoreboard. It does *not* enqueue into the pending queue — it
commits directly. This is correct because at cold-start the bowler is
already known (current scoreboard bowler) and there is no overlay-induced
attribution ambiguity. The two paths are mutually exclusive: pending-queue
fires during WARM mode overlay gaps; cold-start synth fires once during
COLD_START → WARM transition.

### 6.3 Tracker callback re-entrancy

The `on_lock` callback runs synchronously inside the tracker state
transition. If the drain path inside the callback transitively re-enters
the same tracker, behaviour is undefined. STEP 3 includes a verification:
inspect `_apply_bowler_delta` / `_apply_batter_delta` for tracker writes.
If any exist, the callback must be deferred via a flag-and-poll mechanism
rather than direct call.

### 6.4 Queue overflow

`deque(maxlen=6)` silently drops on overflow. STEP 1 must explicitly check
length before append and emit a trace warning + raise / log on overflow.
Investigation #2 Q2 shows queue depth ≤3 in normal operation, so overflow
indicates a much larger anomaly (multi-over overlay, network frame stall).

### 6.5 Rollback plan

**The 4 commits are not independently revertable.** B1.2 enqueues into a
queue whose only drain triggers are the `on_lock` callback hooks installed
in B1.3. Reverting B1.3 alone leaves B1.2's enqueues accumulating with no
drain path — every `over_history` archive blocks indefinitely (the
force-flush deadline also lives in B1.3). Similarly, B1.1 alone is inert
(infrastructure with no caller), but B1.2 without B1.1 has no queue to
push into.

**Correct procedure:** revert all four (B1.4 → B1.3 → B1.2 → B1.1) as an
atomic unit, in reverse order. Cold-start synth path is untouched, so
cold-start validation does not need re-running on rollback.

**Partial revert (debug only):** if isolating B1.1 + B1.2's enqueue path
is required for debugging, pair the partial revert with a temporary
`self._pending_ball_queue.clear()` shim in SM init or per-frame to prevent
unbounded accumulation. Treat this as a debug-only state, not a shippable
configuration.
