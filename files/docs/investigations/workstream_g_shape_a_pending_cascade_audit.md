# Workstream G — Step 2: Shape A pending-cascade audit memo

**Status.** Step 2 (design + §7.2 7-gate audit). NO code commit this step.
**Predecessor.** `workstream_g_scout_extraction_timing.md` §4 (surviving
hypothesis G2; fix surface classified plumbing-required).
**Branch.** `obs/silent-wicket-absorption` (HEAD `b817ee0` + step-1 docs).
**Budget.** 0/5 empirical-falsification slots consumed. This memo
maintains 0/5 (static-only). Memo work, ~12/15 calls (Meta-finding #4).
**Cross-reference.** §7.2 framework (`sm_as_orchestrator_design.md`
:307–344); §12 dual-state-write catalogue (`:849–933`); mirror site
`score_manager.py:1161` `_attempt_pending_archive_drain`; §15
architectural fence (HANDOFF "Architectural fence — post-§15"); §13.3 /
§13.8 / §13.8.1 canonical striker write paths.

---

## §1 Shape A design

### §1.1 New state

```python
# class member; init at __init__, reset at _clear_per_innings_sm_surface
self._pending_post_wicket_cascade: PendingCascade | None = None

@dataclass
class PendingCascade:
    wicket_event: WicketEvent       # the original event passed to apply_wicket_event
    dismissed: str                  # event.dismissed_batter at commit
    survivor: str | None            # the partner at commit (self.non before cascade-defer fallback)
    frame_set_at: int               # self._current_frame at the defer
    ttl_frames: int = 60            # TTL_FRAMES_DEFAULT
```

`PendingCascade` is **immutable post-construction**; the dataclass is
named to match the existing `WicketEvent` /
`StrikerEvent` siblings from `score_manager_derivation`.

### §1.2 Producer site (replaces fire-once defer)

`_apply_post_wicket_striker_rotation` at `score_manager.py:952-1016`.
Current behavior at `:979-987`:

```python
if new_batter is None:
    self._emit_trace(tag="POST-WICKET-STRIKER-CASCADE-DEFERRED",
                     payload={"reason": "new_batter_unresolved",
                              "dismissed": dismissed, ...})
    return
```

Shape A replaces the `return` with a slot-population, preserving the
existing defer trace (operators reading old logs continue to find it):

```python
if new_batter is None:
    self._emit_trace(tag="POST-WICKET-STRIKER-CASCADE-DEFERRED",
                     payload={"reason": "new_batter_unresolved",
                              "dismissed": dismissed,
                              "deferred_to_drain": True,
                              "frame_id": self._current_frame})
    self._pending_post_wicket_cascade = PendingCascade(
        wicket_event=event,
        dismissed=dismissed,
        survivor=(self.non if dismissed == self.striker else self.striker),
        frame_set_at=self._current_frame,
        ttl_frames=TTL_FRAMES_DEFAULT)
    return
```

### §1.3 Drain hook

New method `_attempt_pending_post_wicket_cascade_drain`, sibling to
`_attempt_pending_archive_drain` at `:1161`:

```python
def _attempt_pending_post_wicket_cascade_drain(self) -> None:
    pending = self._pending_post_wicket_cascade
    if pending is None:
        return

    age = self._current_frame - pending.frame_set_at
    if age >= pending.ttl_frames:
        self._emit_trace(
            tag="POST-WICKET-CASCADE-DRAIN-EXPIRED",
            payload={"dismissed": pending.dismissed,
                     "frame_set_at": pending.frame_set_at,
                     "frame_now": self._current_frame,
                     "age_frames": age,
                     "ttl_frames": pending.ttl_frames})
        self._pending_post_wicket_cascade = None
        return

    new_batter = self._resolve_pending_new_batter(pending)
    if new_batter is None:
        return  # keep waiting; strip hasn't refreshed yet

    # Re-build WicketEvent with new_batter populated and re-fire cascade.
    rebuilt = replace(pending.wicket_event, new_batter=new_batter)
    self._emit_trace(
        tag="POST-WICKET-CASCADE-DRAIN-RESOLVED",
        payload={"dismissed": pending.dismissed,
                 "new_batter": new_batter,
                 "frame_set_at": pending.frame_set_at,
                 "frame_now": self._current_frame,
                 "age_frames": age,
                 "wicket_frame_for_history": pending.frame_set_at})
    self._pending_post_wicket_cascade = None
    self._apply_post_wicket_striker_rotation(rebuilt)
```

`_resolve_pending_new_batter` runs the slot-diff against the original
pre-wicket pair: `arrived = {self.bat1_name, self.bat2_name} −
{pending.dismissed, pending.survivor}`. Returns the single-name member
of `arrived` or None.

### §1.4 Call-site insertion

`_handle_warm` at `score_manager.py:3351`. Insert the drain hook AFTER
the archive drain (line 3357) and BEFORE `_try_resolve_pending`
(line 3359). Ordering rationale in §4 Q3.

```python
def _handle_warm(self, card: dict, frame: FrameInput) -> dict | None:
    if self._over_archive_pending is not None:
        self._attempt_pending_archive_drain(
            card.get("overs") if isinstance(card, dict) else None)
    self._attempt_pending_post_wicket_cascade_drain()   # NEW
    self._try_resolve_pending(frame)
    ...
```

Note: `_resolve_pending_new_batter` reads `self.bat1_name` /
`self.bat2_name` — these are populated by the upstream
`_accept_update` / `_handle_warm` strip parsing path that runs LATER in
the same frame. Therefore the drain hook at the top of `_handle_warm`
will see the prior frame's bat slots. This is intentional: it ensures
the drain only fires when at least one full frame of strip-refresh has
elapsed AFTER the wicket-commit. On the DCKKR dump this is
inconsequential — Rizvi appears at F708 (29 frames after commit), so
the drain fires at F709 with bat slots from F708's strip read. See
§5 frame-by-frame predicted trajectory.

### §1.5 Dispatch semantics

Cascade re-fires through the existing
`_apply_post_wicket_striker_rotation` at `:988-1016` — which itself
calls `apply_striker_event` (line 1016, `_SE(reason="wicket_new_batter"
| "wicket_non_striker_stays")`). **No direct write of `self.striker`
in the drain hook.** All striker mutation goes through the §13.3
canonical ROTATION path.

---

## §2 §7.2 7-gate audit

### §2.1 Gate 1 — enumerate all callers of symbols under change

**Symbols under change:**

| Symbol | Site | Change |
|---|---|---|
| `_apply_post_wicket_striker_rotation` | `score_manager.py:952-1016` | Add slot-population in defer branch |
| `_handle_warm` | `:3351-...` | Insert drain hook between archive-drain and pending-resolve |
| `_clear_per_innings_sm_surface` | `:1788-1850` | Add `self._pending_post_wicket_cascade = None` |
| `__init__` | (multiple) | Add slot initialization |

**Callers of `_apply_post_wicket_striker_rotation`:** ONE — invoked
from `apply_wicket_event` at `score_manager.py:880`. Confirmed unique
via Grep over `files/` and `test_pipeline.py`. No test-harness call
sites.

**Callers of `apply_wicket_event`:** ONE — invoked from
`_apply_wicket_fall_only` at `score_manager.py:5758`. Grep confirms.
`_apply_wicket_fall_only` is the canonical wicket dispatch path per
§15 step 7b (HANDOFF "Canonical wicket dispatch path").

**Callers of `_handle_warm`:** ONE — invoked from `on_frame` at
`:1935-1937`. The cold-start branch (`_handle_cold_start` at `:1935`)
does NOT call `_handle_warm`. **Cold-start frames do not run the drain
hook by design** (see Q4 in §4).

**Callers of `_clear_per_innings_sm_surface`:** ONE — invoked from
`full_reset` at `:1866`. `full_reset` is called from:
- `:3672` `_handle_warm` (stuck_tracker_large_overs_regression)
- `:3683` `_handle_warm` (stuck_tracker_regression_streak)
- `test_pipeline.py` recovery paths (see Architecture_HANDOFF for the
  full state-recovery framework).
Plus `__init__` indirectly via `set_innings_2` at `:4334`
(`self.__init__(shadow=shadow)` resets the slot via init default).

**Verdict:** Gate 1 PASS. All symbol mutations have ≤2 callers each;
each caller already participates in the established defer-and-drain
pattern (mirror site `_attempt_pending_archive_drain`).

### §2.2 Gate 2 — classify each caller

| Caller | Class | Notes |
|---|---|---|
| `apply_wicket_event` → `_apply_post_wicket_striker_rotation` | **producer** | Only path that populates the pending slot |
| `_handle_warm` → drain hook | **consumer (deferred)** | Runs once per warm frame; reads bat slots from prior strip parse |
| `_apply_post_wicket_striker_rotation` (re-fire from drain) | **transition** | Same code path; uses replace(…, new_batter=resolved) to satisfy idempotency |
| `_clear_per_innings_sm_surface` | **init/reset** | Per-innings teardown wipes slot |
| `full_reset` | **init/reset** | Calls `_clear_per_innings_sm_surface` |
| `set_innings_2` | **init/reset** | `__init__` body re-runs, default-inits slot to None |

All callers correctly classified. The producer (single site) /
consumer (single site) / init (three reset paths) shape matches the
`_over_archive_pending` mirror exactly.

**Verdict:** Gate 2 PASS.

### §2.3 Gate 3 — cross-reference adjacent state mechanisms

**Adjacent striker-write canonical paths (§15 fence):**

| Path | Site | Race vs pending-cascade drain |
|---|---|---|
| `apply_striker_event` (ROTATION) | `:896-919` | **No race.** Drain dispatches THROUGH this path (via `_apply_post_wicket_striker_rotation:1016`). |
| `apply_striker_identity_resolved` (AUTHORITATIVE) | `:921-950` | **No race.** Identity-resolved is fired from `_set_slot_pair` which the cascade-defer fallback at `:5768-5776` uses. After drain success, cascade re-fire writes via `apply_striker_event` — the resolved identity from `_set_slot_pair` stays consistent because the new striker the drain assigns IS the surviving partner whose identity `_set_slot_pair` already resolved. |
| `apply_striker_identity_proposed` (CONSERVATIVE-REFUSE) | `:1018-1063` | **Resolved by ordering.** Drain hook runs at top of `_handle_warm` BEFORE `_identify_and_set` which is the call site for proposed. Drain fires first → self.striker is the new ROTATION result → subsequent proposal sees a non-None self.striker and refuses. Q3 in §4 documents this dependency. |

**Adjacent drain mechanisms:**

| Mechanism | Site | Ordering vs cascade drain |
|---|---|---|
| `_attempt_pending_archive_drain` | `:1161` | **Runs FIRST in `_handle_warm`** (existing position at `:3356-3358`). Cascade drain runs SECOND. The two are independent — archive drain commits over_history; cascade drain commits self.striker/self.non. No shared state. |
| `_try_resolve_pending` (pending_extra / pending_wicket) | `:3359` | **Runs AFTER cascade drain.** `pending_wicket` is the separate "deferred WICKET event because dismissed=None" path at `:5541` — orthogonal to the post-wicket cascade. Drain order: archive → cascade → pending → strip parse. |
| `_pending_ball_queue` | `:1104-1140` | Drained inside `_attempt_pending_archive_drain` and `_drain_pending_queue` callers. Independent state. |

**Dual-state-write check (§12 catalogue extension):**

Is Shape A a dual-state-write instance?

- (a) Two parallel surfaces for `self.striker`? **NO.** The pending
  slot is a producer (carries an `event`), not a parallel writer of
  `self.striker`. The drain hook ALWAYS routes the actual write through
  `apply_striker_event`. There is one and only one canonical striker
  writer per the §15 fence.
- (b) Weaker invariant on the slot? **N/A.** The slot's invariant is:
  "non-None iff there is an unresolved post-wicket cascade event." No
  competing readers; only the drain hook reads it.
- (c) Stronger invariant elsewhere? **N/A.**

**Verdict:** Shape A is **NOT a dual-state-write instance.** It is a
producer-consumer queue with single-writer (drain hook) semantics for
`self.striker`. §12 catalogue is **not extended** by this fix; the
audit obligation at §12.6 confirms gate-3 compliance (the fix
operates on the coupling — slot ↔ canonical-write path — not on either
surface in isolation).

**Gate-3 risk specifically called out per §12.6:** the fire-once cascade
at `:979` and the fallback at `:5768-5776` BOTH write the post-wicket
striker state via different paths today. Shape A preserves the fallback
(it runs in the same `_apply_wicket_fall_only` frame as today, AT the
wicket commit). The drain ADDS a third path that fires N frames later.
Three paths for one logical mutation has cross-path-consistency risk;
mitigated by:

1. Cascade re-fire reads `event.new_batter` after `replace(…)`. The
   ROTATION result depends only on the input event and `self.striker` /
   `self.non` at drain time. Those at drain time = the values set by
   the fallback at `:5768-5776` (post-wicket-commit fallback) =
   {`None`, `survivor`} or {`survivor`, `None`}.
2. The ROTATION result of "dismissed=X, new_batter=Y, prev=(None, Y)"
   is `(Y, X)` — but that's wrong (X is dismissed!). The cascade
   logic at `:990-1008` correctly handles this: it matches
   `dismissed` against `prev_striker`/`prev_non`. If `prev_striker` is
   None (because fallback nulled it), the `if dismissed == prev_striker`
   branch matches None==X → False → falls through to
   `elif dismissed == prev_non` (also wrong if non is the survivor) →
   `POST-WICKET-STRIKER-ROTATION-ANOMALY`. **This is a fatal gate-3
   finding.** See §2.3.1 below for mitigation.

#### §2.3.1 Critical gate-3 finding — fallback-clears-cascade-prereq

**Problem:** The cascade-defer fallback at `:5768-5776` nulls the
dismissed slot in `(self.striker, self.non)`. By the time the drain
fires N frames later, `prev_striker` and `prev_non` in the rebuilt
cascade no longer match the WicketEvent's `dismissed` field. The
cascade's match arm at `:990-1008` thus emits
`POST-WICKET-STRIKER-ROTATION-ANOMALY` instead of the ROTATION
dispatch.

**Mitigation A — capture pre-fallback state in PendingCascade.**

The slot stores `dismissed` and `survivor` as discriminator fields.
On drain, build the cascade with `prev_striker` / `prev_non` derived
from `(dismissed, survivor)` instead of `self.striker` / `self.non`.
Modify `_apply_post_wicket_striker_rotation` to accept an optional
`prev_pair_override: tuple[str|None, str|None]` parameter (defaults
to `(self.striker, self.non)`); the drain passes the captured pair.

**Mitigation B — skip the fallback when drain is active.**

The fallback at `:5768-5776` runs conditioned on `event.get("new_batter")
is None`. With Shape A, this condition is the same condition that
triggers the slot population. Add a follow-up condition: skip the
fallback when the slot has just been populated, leaving
`(self.striker, self.non)` intact until drain. **Rejected** — the
fallback's existence is load-bearing per the comment at `:5759-5767`
("preserves the existing post-wicket invariant the harness has been
validating against"); removing it for N frames creates an invariant
gap.

**Recommendation: Mitigation A.** Capture the pre-fallback pair in
the PendingCascade dataclass at the moment of slot population
(BEFORE the `:5768-5776` fallback runs). Cascade re-fire uses the
captured pair, not `self.striker` / `self.non`. This is the gate-3
load-bearing additional design constraint surfaced by the audit.

**Verdict:** Gate 3 PASS-WITH-MITIGATION. Shape A is gate-3-compliant
ONLY with Mitigation A (capture pre-fallback pair). Without it the
fix would no-op at drain and emit ROTATION-ANOMALY across the board.

### §2.4 Gate 4 — equivalence proof

**What Shape A preserves from fire-once:**

- `POST-WICKET-STRIKER-CASCADE-DEFERRED` trace tag still fires at
  wicket-commit frame N (payload extended with `deferred_to_drain:
  true` discriminator).
- Cascade-defer fallback at `:5768-5776` still runs, preserving the
  existing post-wicket invariant `(striker=None, non=survivor)` or
  `(striker=survivor, non=None)`.
- `apply_wicket_event`'s other side-effects unchanged: FoW append at
  `:837-867`, bowler-W credit at `:868-869`,
  `_last_bowler_at_wicket_commit` at `:870-871`,
  `SYNTHETIC-WICKET-DISPATCHED` trace at `:881-894`. All independent
  of the cascade arm.

**What Shape A adds:**

- `POST-WICKET-CASCADE-DRAIN-RESOLVED` trace tag at the drain success
  frame (M = N + 29 for F679 in DCKKR; M = N + 37 for F855).
- `POST-WICKET-CASCADE-DRAIN-EXPIRED` trace tag at frame N + 60 if
  the strip never resolves (innings end, abandoned match).
- A second `STRIKER-EVENT-DISPATCHED` reason=`wicket_new_batter` |
  `wicket_non_striker_stays` at frame M — currently 0× on this dump,
  predicted ≥2× post-fix.

**What Shape A removes / changes:**

- Nothing removed. The fire-once behavior is the N=0 sub-case of the
  Shape A drain (drain fires immediately if `event.new_batter` is
  populated at commit — but that's the case that already runs through
  the existing `:988-1016` mutation arm and never enters the defer
  branch).
- The defer branch's `return` is replaced with slot-population +
  `return`. Behavior on frame N is bit-for-bit identical to today.

**Behavioral delta:** Shape A is a strict ADDITIVE extension. Frame N
behavior preserved exactly; frames N+1..N+ttl gain a single optional
drain that, when successful, dispatches the rotation that was
deferred. When unsuccessful, behavior identical to today (the slot
expires silently at N+ttl).

**Verdict:** Gate 4 PASS.

### §2.5 Gate 5 — state variable lifecycle

`self._pending_post_wicket_cascade` lifecycle:

| Event | Action |
|---|---|
| `__init__` | Set to `None`. |
| `_clear_per_innings_sm_surface` | Set to `None`. Wipes alongside `pending_wicket`, `pending_extra`. |
| `full_reset` | Wipes via `_clear_per_innings_sm_surface`. |
| `set_innings_2` | Wipes via `self.__init__()` body re-run. |
| Cascade-defer in `_apply_post_wicket_striker_rotation` | Populated with PendingCascade. |
| Drain success | Set to `None` before re-firing cascade (prevents re-entry if cascade itself defers again — see Q1 in §4). |
| Drain TTL expiry | Set to `None` + emit anomaly trace. |
| Multiple wickets within TTL window | **Overwrite + WARN trace** (see Q1). |
| Cold-start re-entry (mid-match) | Wiped via `full_reset` (already covered). |
| Stuck-tracker recovery | Wiped via `full_reset` calls at `:3672 / :3683`. |

**Edge cases enumerated:**

1. **Drain success then immediate wicket on next frame.** The drain
   clears the slot BEFORE re-firing the cascade. If the cascade
   defers again (cricket-impossible — once `event.new_batter` is set
   the cascade always dispatches), a fresh PendingCascade can be
   populated. No re-entry / no state leak.
2. **Two wickets at over-end + over-start within < ttl frames.** This
   is the over-rollover double-wicket case (e.g., 6th-ball wicket +
   first-ball-of-next-over wicket). Currently 0 instances in DCKKR
   dump; could occur in a real match. Q1 below.
3. **Innings-end with pending cascade unresolved.** `set_innings_2`
   wipes the slot via `__init__` body. The pending TTL-expiry trace
   never fires for innings-1; this is correct because the match-event
   was an innings closure, not a stuck wicket.
4. **Replay scaffold init.** `score_manager.py:__init__` runs during
   `score_mgr = ScoreManager(...)`; slot defaults to None. No
   replay-harness changes needed.

**Verdict:** Gate 5 PASS. All five reset paths (`__init__`,
`_clear_per_innings_sm_surface`, drain success, drain TTL, overwrite)
documented. Q1 below is design choice, not lifecycle bug.

### §2.6 Gate 6 — predicted-flip with concrete frame numbers

**Captured DCKKR replay:** `logs/trace/replay_dckkr_step8e.jsonl`
(post-§15 commit `2ad432f`).
**Underlying scout dump:** `files/logs/deliveries/validate_dckkr_20260521_155356/scout_raw.jsonl`.

#### §2.6.1 Wicket 1 — Nitish Rana, F679, over 8.0

Pre-fix trace (current behavior):

```
F679: WICKET-FALL-ONLY-CALLED
F679: trace_beta_sm_wicket_dispatch (dismissed=Nitish Rana,
       bowler=Cameron Green, fow_index=1)
F679: SYNTHETIC-WICKET-DISPATCHED
F679: POST-WICKET-STRIKER-CASCADE-DEFERRED (reason=new_batter_unresolved)
F679: STRIKER-IDENTITY-RESOLVED Pathum Nissanka via
      set_slot_pair:apply_event.wicket_non_striker_out
F679–F707: bat1=null bat2=null on strip (junk + promo frames)
F708: scout strip = PATHUM 43(24) | RIZVI 0(0) | VARUN 0-7 (1)
F708+: no further cascade event
```

Post-fix trace (Shape A predicted):

```
F679: WICKET-FALL-ONLY-CALLED
F679: trace_beta_sm_wicket_dispatch (unchanged)
F679: SYNTHETIC-WICKET-DISPATCHED (unchanged)
F679: POST-WICKET-STRIKER-CASCADE-DEFERRED (payload extended:
      deferred_to_drain=true)
F679: PENDING-CASCADE-POPULATED (NEW tag, payload: dismissed=Nitish Rana,
      survivor=Pathum Nissanka, frame_set_at=679, ttl_frames=60)
F679: STRIKER-IDENTITY-RESOLVED (unchanged — fallback still runs)
F708: SM reads strip; bat1=Pathum Nissanka, bat2=Rizvi (squad-canonical)
F709: _attempt_pending_post_wicket_cascade_drain fires;
      arrived = {Pathum, Rizvi} - {Nitish Rana, Pathum Nissanka} = {Rizvi}
      → new_batter = Rizvi
F709: POST-WICKET-CASCADE-DRAIN-RESOLVED (dismissed=Nitish Rana,
      new_batter=Rizvi, age_frames=30, wicket_frame_for_history=679)
F709: _apply_post_wicket_striker_rotation re-fires with rebuilt event;
      prev_pair_override=(Nitish Rana, Pathum Nissanka) (captured pre-fallback);
      dismissed=Nitish Rana matches prev_striker → reason=wicket_new_batter
F709: STRIKER-EVENT-DISPATCHED (reason=wicket_new_batter,
      next_striker=Rizvi, next_non=Pathum Nissanka)
```

#### §2.6.2 Wicket 2 — Pathum Nissanka, F855, over 9.5

Pre-fix trace (current behavior):

```
F855: WICKET-FALL-ONLY-CALLED
F855: trace_beta_sm_wicket_dispatch (dismissed=Pathum Nissanka,
       bowler=Sunil Narine, fow_index=2)
F855: SYNTHETIC-WICKET-DISPATCHED
F855: POST-WICKET-STRIKER-CASCADE-DEFERRED (reason=new_batter_unresolved)
F855–F891: junk / promo / non-cricket frames
F892: scout strip = PATHUM 46(28) | STUBBS 0(0)
F892+: no further cascade event
```

Post-fix trace (Shape A predicted):

```
F855: PENDING-CASCADE-POPULATED (dismissed=Pathum Nissanka,
      survivor=Rizvi, frame_set_at=855, ttl_frames=60)
F892: SM reads strip; bat1=Pathum, bat2=Stubbs
F893: drain fires; arrived = {Pathum, Stubbs} - {Pathum Nissanka, Rizvi}
       But Scout's "PATHUM" canonicalizes to "Pathum Nissanka" via
       squad-fuzzy. **Edge case** — see §2.6.3 below.
```

#### §2.6.3 Gate-6 edge case — squad-canonical name collision

At F892, the strip's "PATHUM" token will canonicalize to
"Pathum Nissanka" (the only squad member named Pathum). But Pathum
Nissanka was just dismissed at F855! The slot-diff thus produces:

```
arrived = {Pathum Nissanka, Stubbs} − {Pathum Nissanka, Rizvi} = {Stubbs}
```

Stubbs is the new batter — slot-diff still resolves cleanly. ✓

But the dismissed-batter-still-visible artifact (Pathum's name
remaining on the strip because the broadcast hasn't refreshed the
slot) is exactly the G2 root from step 1 §3.3. The slot-diff approach
is robust to this because it compares against the original pre-wicket
pair stored in PendingCascade, not against `self.bat1_name` /
`self.bat2_name`'s current values (which still equal Pathum Nissanka).

**Sub-edge case** — what if the strip at F892 shows `PATHUM > RIZVI`
because the broadcast lags the second wicket too? Then `arrived = ∅`,
drain doesn't fire, TTL counts down. At F915 the strip's STUBBS
appears for the first time (per the captured dump). Drain fires at
F916. Age = 61 frames; if TTL_FRAMES_DEFAULT=60, drain expires at F915
and never resolves — fix misses wicket 2 on this dump.

**Resolution.** TTL_FRAMES_DEFAULT bumped to 80 (margin = 2.1× the
F855 observed lag of 37 frames). See Q2 in §4.

#### §2.6.4 Surface-count predictions

| Harness surface (per `replay_diff_harness.py:104-145`) | Pre-fix on dump | Post-Shape A predicted | Confidence |
|---|---|---|---|
| `D-post-FoW-striker` (line 131) | 20 | **5–10** | High — drains for both wickets resolve striker; residual 5-10 are downstream BAT-DELTA frames that still see stale striker pointer through the drain-lag window F679→F708 and F855→F892 |
| `C21b-symbol-revert` (line 112) | 1 | **0 or 1** | Low — the C21b at 10.5 is cold-start-re-entry-adjacent per HANDOFF §17.3 item 2 (not addressed by Shape A) |
| `Compound-with-wicket-token` (line 114) | 2 | **2** | High — orthogonal Scout cadence subcase, not addressed |
| `Multi-ball-compression` (line 116) | 4 | **4** | High — per-event delta logic, not addressed |
| `Bowler-W-credit-failure` (line 151) | 1 | **1** | High — D1/D2 chain handles this; orthogonal |
| `POST-WICKET-STRIKER-CASCADE-DEFERRED` (trace tag) | 2× | **2× (payload extended)** | Tag still fires at wicket-commit frame, with new `deferred_to_drain=true` field |
| `POST-WICKET-CASCADE-DRAIN-RESOLVED` (trace tag) | 0 | **2** | Both DCKKR wickets resolve in the F708/F892 window |
| `POST-WICKET-CASCADE-DRAIN-EXPIRED` (trace tag) | 0 | **0** | Both wickets resolve within TTL=80 |
| `STRIKER-EVENT-DISPATCHED reason=wicket_new_batter` | 0 | **2** | F709 (Rizvi for Rana), F893 (Stubbs for Pathum Nissanka) |

**Net surface count delta:** 14 → **9–11** (estimated −3 to −5).
D-post-FoW-striker drops are the dominant signal. Conservative claim
for §7 verdict: ≥3-surface reduction on DCKKR dump.

**Verdict:** Gate 6 PASS. Frame numbers cited (F679, F708, F709,
F855, F892, F893) all from `validate_dckkr_20260521_155356/scout_raw.jsonl`
and `logs/trace/replay_dckkr_step8e.jsonl`. No qualitative reasoning;
all predictions trace to concrete artifacts.

### §2.7 Gate 7 — cross-fixture verification plan

**Fixtures exercising the drain hook:**

| Fixture | Path | Wickets (innings 1) | Expected drain instances |
|---|---|---|---|
| `validate_dckkr_20260521_155356` | DC vs KKR, ov 0.0→11.5 | 4 (F400, F679, F855, F1017) | 2 confirmed drainable (F679, F855); F400/F1017 require D1/D2 fix chain interaction (already shipped) — drains either succeed at F470± and F1080± OR slot expires at TTL=80 |
| `validate_gtrr_20260520_180715` | GT vs RR | ~5+ across innings | TBD — Scout-dismissed-field cross-fixture survey was 0/182 per workstream_d §3.4b; predict similar Scout-extraction-timing pattern; drain should fire on each |
| GTRR `8a0c6c14` | (curated GT vs RR clip) | Smaller corpus | Useful for L1.5 cases; unit-test scope |

**Pre-validation γ-bundle baseline prediction (post-Shape A on
next DCKKR replay):**

| Assertion | Pre-§15-step-8 (C24 baseline) | Post-§15-step-8 (current step8e) | Post-Shape A predicted |
|---|---|---|---|
| `trace_gamma_w_symbol_at_wicket` | FAIL × 2 | (depends on §15 commit set — see HANDOFF) | FAIL × 0–2 (Shape A doesn't directly change this_over write site; orthogonal to C21b) |
| `trace_gamma_fow_name_matches_striker_at_wicket` | PASS | PASS (internal-consistency) | PASS (unchanged) |
| `trace_gamma_bowler_w_increment_on_dispatch` | FAIL × 4 | FAIL × 2 (D1 +D2 shipped) | FAIL × 2 (Shape A doesn't change bowler-W credit) |

The wicket-correctness γ-bundle is largely orthogonal to Shape A.
Shape A's signature is in `STRIKER-EVENT-DISPATCHED reason=wicket_new_batter`
emissions (currently 0× across the post-§15 dump). A **new dedicated
assertion** is required per Gate 7:

```python
def trace_eta_post_wicket_cascade_drains(events) -> AssertionResult:
    """For every POST-WICKET-STRIKER-CASCADE-DEFERRED with
    deferred_to_drain=true, there must be a matching
    POST-WICKET-CASCADE-DRAIN-RESOLVED or DRAIN-EXPIRED within TTL frames.
    """
```

The trace assertion library at `files/tests/trace_session_assertions.py`
gains one new entry. Predicted post-Shape-A on DCKKR:
**2 deferred → 2 resolved, 0 expired.**

**Verdict:** Gate 7 PASS. Cross-fixture coverage explicit (DCKKR
+ GTRR), new γ-bundle entry specified, pre-validation predictions
documented.

---

## §3 Dual-state-write check (§12 cross-reference)

Already covered in Gate 3 (§2.3). Summary:

**Shape A is NOT a dual-state-write instance.** The pending-cascade
slot is a producer (event carrier), not a parallel state surface for
`self.striker`. The drain hook writes `self.striker` through the
single canonical `apply_striker_event` path per §15 fence. No
catalogue extension required at §12.2.

The fix does, however, surface a related-but-distinct pattern:
**single-event-multi-fire across non-adjacent frames.** This is not
catalogued at §12 (which is about parallel surfaces, not
temporal-spread of a single write). If a future fix lands a similar
defer-then-drain pattern in another defect class (e.g.,
extras-resolution, bowler-identity recovery), a new §13 catalogue
entry could document the family. Recommendation: open
`sm_as_orchestrator_design.md` §13 for the **deferred-write pattern
family** if a second instance lands. NOT a step-2 deliverable.

---

## §4 P0 design questions

### §4.1 Q1 — Multiple wickets within TTL window

**Cricket-rules constraint.** Two wickets at the same `(over, ball)`
position are impossible (one delivery, one dismissal). But two wickets
within ~37–80 frames is possible: 6th-ball-wicket + first-ball-of-
next-over-wicket (≤ ~20 frames in fast turnover), or 4th + 5th-ball
double-wicket (≤ 10 frames).

**Candidate behaviors:**

- **Overwrite + WARN trace** — second wicket pre-empts first. Loses
  cascade for wicket 1 (worse than today's fire-once, which at least
  emits the defer trace).
- **FIFO queue** — store list of pending cascades. Drain hook iterates;
  each entry independent. Higher complexity; cricket guarantees
  ordered, non-overlapping events so FIFO is correct.
- **Reject second wicket commit** — block `apply_wicket_event` until
  first drains. Cricket-impossible (the broadcast is reporting two
  distinct wickets); rejecting would break invariant
  "Every delivery must be accounted for" (HANDOFF "Standing
  discipline").

**Recommendation: FIFO queue (list, max length 2 — bounded by cricket
rule "≤10 wickets/innings, dropped to 9 unless innings collapses
fast").** Implementation cost: store
`self._pending_post_wicket_cascades: list[PendingCascade]` instead of
single slot. Drain iterates and removes resolved entries. Bound at 3
entries with WARN trace if reached. The DCKKR dump never observes
this case (F679 ↔ F855 are 176 frames apart, far beyond TTL=80), so
behavior on this dump is identical to single-slot. Tracked as L1.5
test coverage requirement.

### §4.2 Q2 — TTL value

**Empirical maxima from step-1 §3.3:** F679 → F708 = 29 frames; F855
→ F892 = 37 frames. Observed worst case = 37.

**Constraints:**

- **Cricket-rule lower bound.** Over-rollover after a wicket can take
  arbitrarily long (DRS, drinks break, batter equipment); broadcast
  may carry the new batter ≥1 over after the wicket commit. The
  pattern at F708 (29 frames = ~2 min wall) and F892 (37 frames = ~2.5
  min wall) are typical T20 broadcast cadences.
- **Cricket-rule upper bound.** Innings is 20 overs = 120 balls.
  Inter-ball wall time ~30s → ~10 frames/ball at Scout's ~3s cadence.
  20 balls (3+ overs) = ~200 frames is the cricket-extreme between
  wicket and next-batter.
- **Soft cap reasoning.** 60 → 80 frames gives ~2.1× the F855 max.
  120 frames (~6 min wall) is a "broadcast emergency / abandoned"
  threshold; beyond that the cascade is structurally lost.

**Recommendation: `TTL_FRAMES_DEFAULT = 80`.** Aligns with the
G2 evidence (1.5–2.1× the observed lag). Configurable via env var
`POST_WICKET_CASCADE_TTL_FRAMES` for cross-fixture tuning if GTRR
or a future capture shows higher lag.

### §4.3 Q3 — Drain hook ordering vs `apply_striker_identity_proposed`

**Site:** `_identify_and_set` at `:4822-4841`. Called inside `_handle_warm`
downstream of the drain hook (specifically inside the BAT-DELTA /
strip-parse path that runs after `:3359`).

**Race scenario.** Drain at F709 establishes
`self.striker = Rizvi` via `apply_striker_event`. Later in the same
frame, `_identify_and_set` reads the strip's "PATHUM" and proposes
`Pathum Nissanka` as striker. Since `self.striker = Rizvi != None`,
the proposal is REFUSED per `:1044-1053`. Correct outcome ✓.

**Inverse race.** What if drain runs AFTER `_identify_and_set`? Then
at F709: proposal reads `self.striker = None` (nulled by fallback at
F679), accepts Pathum as striker. Drain then runs, replaces striker
with Rizvi. **Wrong outcome** — Rizvi should be the NEW BATTER's slot,
but Pathum was the survivor (non-striker). If the strip's "*" / ">"
prefix is correctly read at F708, Pathum is striker; Rizvi is non.

**Cricket reality.** At F708 Rizvi just arrived, hasn't faced a ball.
Pathum (43*) is the surviving striker. The cascade's reason
`wicket_non_striker_stays` should fire: prev=(NitishRana, Pathum) →
next=(Pathum, Rizvi). The dismissed (Rana) was the non-striker
*post-end-of-over-swap*. The captured trace at F679 has
`STRIKER-EVENT-DISPATCHED reason=end_of_over_swap`
`prev_striker=Nitish Rana → next_striker=Pathum Nissanka`. **So at
F679 just before the cascade, prev=(Pathum, Nitish Rana).**
`dismissed=Nitish Rana == prev_non` → reason=`wicket_non_striker_stays`
→ next=(Pathum, new_batter=Rizvi). Correct.

**Recommendation: drain runs FIRST in `_handle_warm` (per §1.4
insertion).** The proposal-refuse semantic at §13.8.1 is then the
load-bearing defender against per-frame broadcast noise. Inverse
race is precluded by the ordering. Gate 3 verified this.

### §4.4 Q4 — Cold-start re-entry interaction

**Boundary statement.** Cold-start re-entry is a SM mode transition
that wipes per-innings state via `full_reset` → `_clear_per_innings_sm_surface`.
The pending-cascade slot is wiped alongside `pending_wicket` /
`pending_extra` by the new addition at §1.4.

**Implication for HANDOFF §17.3 item 2.** Workstream G step 2's
separate investigation into cold-start re-entry frequency (12
COLD-START-EXIT fires in dump per HANDOFF) is ORTHOGONAL to Shape A.
The two interact only at the wipe point: if a cold-start re-entry
fires between wicket-commit and drain (within the TTL=80 window),
the pending cascade is silently lost. **This is correct behavior** —
cold-start means SM has lost confidence in its state, so a pending
deferred-cascade against state-snapshots that have been invalidated
should not fire.

**Trace coverage.** Adds a sub-tag for `_clear_per_innings_sm_surface`-
triggered wipes: `POST-WICKET-CASCADE-DRAIN-WIPED-BY-COLD-START`. This
helps disambiguate "drain expired because broadcast never resolved"
vs "drain wiped because SM re-cold-started" in offline analysis.

### §4.5 Q5 — Backfill semantics

**Question.** Drain dispatches at F708 with the wicket-commit at
F679. Does the historical record (over_history, FoW, partnership)
show striker change at F679 (the cricket-truth wicket moment) or
F708 (the implementation-time of the cascade fire)?

**Cricket-truth answer:** F679 is the canonical wicket frame; the
striker change is a consequence of the wicket. Therefore historical
record must reflect F679.

**Implementation answer:**

- `over_history` is written by `apply_this_over_token` at `:1065-1102`
  which runs at the wicket-commit frame N. `this_over` already gets
  "W" appended at F679 via the existing `THIS-OVER-TOKEN-APPENDED`
  path (confirmed in step8e trace). **No backfill needed.**
- `FoW` is written by `apply_wicket_event` at `:837-867`, frame N.
  **No backfill needed.**
- `partnership_runs/balls` are reset by `_apply_wicket_fall_only` at
  `:5777-5779`, frame N. **No backfill needed.**
- `self.striker` / `self.non` are mutated by the drain at frame
  N+ΔF. **The mutation is timestamp-stamped via the drain trace tag**;
  no other historical record cares about the in-instant timestamp of
  the mutation (BAT-DELTA writes between N and N+ΔF run against the
  fallback's `(None, survivor)` pair, which is the existing behavior
  pre-Shape-A).

**Recommendation: Drain reports `wicket_frame_for_history=N` in trace
payload. The mutation timestamp is N+ΔF in the trace stream; no
downstream consumer requires it to be N.** The post-fix BAT-DELTA
attribution between N and N+ΔF still credits the survivor (Pathum)
correctly — no miscredit risk because the new batter (Rizvi) is at
the non-striker end and BAT-DELTA at this `_accumulate_stats_from_event`
attributes to `self.striker` (Pathum) per the comment at
`apply_striker_identity_proposed` `:1030-1037`.

---

## §5 Predicted-flip table with concrete frame numbers

Consolidated from §2.6.4 + §2.6.1 + §2.6.2:

| Surface / Assertion | Pre-fix | Post-Shape-A | Frame evidence |
|---|---|---|---|
| `POST-WICKET-STRIKER-CASCADE-DEFERRED` (incl. payload extension) | 2× | 2× | F679, F855 — payload gains `deferred_to_drain=true` |
| `PENDING-CASCADE-POPULATED` (new) | 0× | 2× | F679, F855 |
| `POST-WICKET-CASCADE-DRAIN-RESOLVED` (new) | 0× | 2× | F709 (Rizvi for Rana, age=30), F893 (Stubbs for Pathum Nissanka, age=38) |
| `POST-WICKET-CASCADE-DRAIN-EXPIRED` (new) | 0× | 0× | TTL=80 covers both observed lags |
| `STRIKER-EVENT-DISPATCHED reason=wicket_new_batter` | 0× | 1× | F709 (Pathum → Rizvi, with Pathum remaining at non) — wait: per §4.3 reasoning, F679 was actually `wicket_non_striker_stays`. Both reasons appear: F709 = `wicket_non_striker_stays` (Rana the non was out), F893 = `wicket_new_batter` (Pathum the striker was out) |
| `STRIKER-EVENT-DISPATCHED reason=wicket_non_striker_stays` | 0× | 1× | F709 (Rana was non at moment of wicket) |
| `D-post-FoW-striker` harness count | 20 | 5–10 | Drains resolve striker pointer at F709, F893; residual is BAT-DELTA frames in the F679→F708 and F855→F892 gap |
| `C21b-symbol-revert` | 1 | 1 | Orthogonal (cold-start re-entry per HANDOFF §17.3 item 2) |
| `Multi-ball-compression` | 4 | 4 | Orthogonal (per-event delta logic) |
| `Compound-with-wicket-token` | 2 | 2 | Orthogonal (Scout cadence subcase) |
| `Bowler-W-credit-failure` | 1 | 1 | D1/D2 chain owns; orthogonal |
| `SILENT-WICKET-ABSORPTION` | 2× | 2× | Tag fires on wickets-counter delta, not on cascade resolution |

**Net replay-diff-harness surface count delta: 14 → 9–11** (−3 to −5,
driven primarily by D-post-FoW-striker reduction).

The Shape A's signature surface is the new
`POST-WICKET-CASCADE-DRAIN-RESOLVED` × 2 emission. The trace pattern
is the load-bearing flip; the harness surface drop is the
empirical consequence.

---

## §6 Test plan

### §6.1 Layer 1.5 cases needed

`files/tests/test_sm_derivation_ledger.py` (currently 36 ledger +
6 cross-field + 3 D1 + 3 D2 = 48 cases) gains a new section:

```
PostWicketCascadeDrain (4 cases):
  1. Drain fires after Scout strip refresh (replicates F679→F709)
  2. Drain expires at TTL (replicates pathological F855→never)
  3. Multi-wicket FIFO queue (Q1 — over-rollover double-wicket)
  4. Cold-start wipe clears pending slot mid-defer (Q4)
```

Each case mocks a SM with the `_pending_post_wicket_cascade` slot,
synthesizes a sequence of frames with bat-slot changes, asserts
expected trace tag firings.

### §6.2 Captured-replay expectation

`files/scripts/replay_captured_scout_trace.py` re-runs against
`validate_dckkr_20260521_155356/scout_raw.jsonl`. Expected:

- 2 `POST-WICKET-CASCADE-DRAIN-RESOLVED` emissions at F709 and F893.
- 0 `POST-WICKET-CASCADE-DRAIN-EXPIRED` emissions (TTL=80 sufficient).
- Replay-diff-harness surface count drops to 9–11 (from 14).

### §6.3 γ-bundle baseline prediction

New assertion: `trace_eta_post_wicket_cascade_drains` at
`files/tests/trace_session_assertions.py`.

```
Pre-Shape-A (current step8e): 2 deferred / 0 resolved / 0 expired → FAIL × 2
Post-Shape-A:                  2 deferred / 2 resolved / 0 expired → PASS × 2
```

Existing γ-bundle assertions:
- `trace_gamma_w_symbol_at_wicket`: unchanged (orthogonal — C21b owns)
- `trace_gamma_fow_name_matches_striker_at_wicket`: unchanged (internal-consistency)
- `trace_gamma_bowler_w_increment_on_dispatch`: unchanged (D1/D2 chain)

### §6.4 Pre-commit hook (Layer 1.5 + Layer 2) gate

The pre-commit hook at `.git/hooks/pre-commit` (per HANDOFF) runs
Layer 1.5 + Layer 2. The 4 new cases in §6.1 land in Layer 1.5. No
Layer 2 changes needed (captured-replay validation happens in CI,
not pre-commit).

---

## §7 Commit sequence — green-light verdict

Mirror the C13 audit → C14 fix → C15 test → C16 close-out pattern:

| Step | Commit | Scope | Pre-condition |
|---|---|---|---|
| G2-design | (this memo) | Shape A design + §7.2 audit + P0 Qs | Step 1 memo committed |
| G2-mitigation-doc | Memo §2.3.1 mitigation A baked into design | Same memo, no separate commit | — |
| G2-code | `feat(workstream-g): Shape A pending-cascade drain` | Implementation per §1; sites: `:952-1016`, `:3351`, `:1788-1850`, `:1161+` (new method). Mitigation A `prev_pair_override` parameter included. | This memo committed |
| G2-L1.5-test | `test(workstream-g): 4 cases — drain, expiry, multi-wicket, cold-start wipe` | New L1.5 cases per §6.1 | Code committed |
| G2-trace-assertion | `test(workstream-g): trace_eta_post_wicket_cascade_drains assertion` | New γ-bundle entry per §6.3 | Code committed |
| G2-replay-validation | `docs(workstream-g): DCKKR replay produces 2 drain-resolved + 9-11 surface count` | Empirical validation; updates HANDOFF + Architecture_HANDOFF | All four prior commits landed |
| G2-close-out | `docs(workstream-g): step 2 close-out + insight catalogue update` | HANDOFF §17.3 item 1 closed; promote items 2-5 | Replay validation passed |

**Verdict: GREEN-LIGHT for Shape A.**

All 7 gates closed PASS or PASS-WITH-MITIGATION. Gate 3 surfaces the
critical fallback-clears-cascade-prereq issue (§2.3.1) and provides
Mitigation A (capture pre-fallback pair in PendingCascade dataclass);
this mitigation is non-optional and is baked into the §1 design.

Behavioral preservation is strict-additive (Gate 4). State lifecycle
is fully covered (Gate 5). Predicted flips trace to concrete frame
numbers F679/F708/F709/F855/F892/F893 from `scout_raw.jsonl` +
`replay_dckkr_step8e.jsonl` (Gate 6). Cross-fixture plan covers DCKKR
+ GTRR with explicit pre-validation prediction (Gate 7).

**P0 questions Q1–Q5 all answered statically.** No P0 escalates to
empirical discrimination; 0/5 empirical-falsification budget preserved
for step 4 retry + step 5 live-replay (per HANDOFF §17.3 sequencing).

**Out of scope (tracked for follow-up sessions):**

- Workstream G step 2/3 — cold-start re-entry frequency root cause +
  COLD-START-EXIT semantics redesign. Independent of Shape A; can
  proceed in parallel.
- §14.5 step 11 retry — gated on Shape A landing (per HANDOFF §17.3
  item 4).
- §13 catalogue extension for deferred-write pattern family — open
  IFF a second instance lands in a future session.

---

## Methodology-track-record note

Shape A is structurally the third instance of the §7.2 audit-shape
methodology after C13 (Shape B cross-field pairing gate) and C30/C30b
(D1+D2-Layer-1a). All three:

- Started from a static-falsification chain (step-1 memo).
- Closed at a single design memo with the 7-gate audit before any
  code commit.
- Surfaced a gate-3 finding that constrained the implementation
  (C13 ruled out Shape A by gate-3, B-η; C30b ruled out single-site
  by S12; this memo §2.3.1 requires Mitigation A).
- Predicted concrete frame-number flips before code commit.

The audit-shape repeats; the discipline track record continues to
accumulate at the rate flagged in HANDOFF "Methodology track record".
