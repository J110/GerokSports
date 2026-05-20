# Cold-start initial-striker derivation design (S5b-3, 2026-05-20)

**Status.** Design memo. No code commits. Output is per-context verdicts that
inform future execution decisions.

> **REVISION 2026-05-20 (post-validate_gtrr_20260520_180715 analysis).** The
> Context A "already addressed" verdict in §6 of this memo is **EMPIRICALLY
> FALSIFIED**. See §11 for the audit findings and the corrected fix path. The
> failure is *not* detection-bounded — it's a stale-field-name dead code path.
> Original §1–§10 retained as written; §11 is the appended correction.

**Scope.** Determine whether `broadcast_striker`'s residual authority — the
Priority 3 path at `score_manager.py:4283-4293` in `_identify_and_set`, which
only fires when `self.striker is None` — can be replaced with derivation, or
whether it's structurally required at one or more of three boundary contexts:

1. **Cold-start exit** (`_accept_initial`)
2. **Hot-resume from cache** (`_resume_from_cache_hot`)
3. **Post-wicket gap** (between dismissal and new-batter announcement)

**Why this is design-memo scope.** S5b-1 (observability cleanup) and S5b-2
(ambiguity tiebreaker, shipped `3dbace9`) were single-call-site disposable. S5b-3
touches three architecturally distinct paths that each set `self.striker`
differently and reach `_identify_and_set` Priority 3 under different invariants.
The memo treats each independently per the lesson from Queue B / `_ScoutRetryBuffer`
/ S5a / S5b: a single verdict across heterogeneous call sites is the failure
pattern; per-context audit is the discipline.

## 1. Current architecture

### 1.1 `_identify_and_set` Priority 3 (the field consumer)

`score_manager.py:4283-4293`:

```python
if not new and card.get("broadcast_striker"):
    ind = card["broadcast_striker"].lower().strip()
    b1_first = ((b1_internal or "").split() or [""])[0].lower()
    b2_first = ((b2_internal or "").split() or [""])[0].lower()
    if b1_first and b2_first and b1_first != b2_first:
        if b1_first in ind and b2_first not in ind:
            new = b1_internal
            method = "broadcast_first_name"
        elif b2_first in ind and b1_first not in ind:
            new = b2_internal
            method = "broadcast_first_name"
```

The deterministic rotation override at `:4295-4325` then gates the write: if
`self.striker is not None`, the broadcast write is *rejected* with a
`STRIKER-SM-BROADCAST-DISAGREES-DETERMINISTIC` trace. So Priority 3's write
authority is restricted to `self.striker is None` — the cold-start condition.

The `else` branch at `:4326-4331` calls `_set_slot_pair(new, _ns, source="identify_and_set.broadcast_first_name")`.

### 1.2 Where `self.striker` becomes `None`

Five sites in `score_manager.py` set `self.striker = None`:

| Line | Site | Trigger |
|---|---|---|
| `:1399` | `_reset_per_innings` | full reset between innings |
| `:2469, :2486, :2497, :2508` | `_cold_start_plausible` rejection | cold-start absolute / inn1 sanity guards reject the read; striker cleared as part of |
| `:2599` | `_set_innings_2` | innings-2 transition |
| `:5052-5054` | `_apply_event` wicket handler | dismissed batter was on strike — slot set to `(None, survivor)` |
| (implicit at start) | `ScoreManager.__init__` | `self.striker = None` by default |

The `_identify_and_set` Priority 3 path can fire to recover striker after any of
these. The three boundary contexts of interest are the most common ones in
production traffic.

### 1.3 Three boundary contexts

**Context A — cold-start exit (`_accept_initial`, `:2698`)**

`_accept_initial` is the canonical cold-start exit. The current path:

1. Sets `self.bat1_name = card.get("bat1_name")` (line 2783)
2. Sets `self.bat2_name = card.get("bat2_name")` (line 2785)
3. Sets `self.bowler_name = card.get("bowler_name")` (line 2787)
4. **Sets `self.striker` via `_set_slot_pair`** based on `card.get("broadcast")` (the broadcast strip indicator) at `:2789-2808`:
   - If `broadcast` matches `bat1_name`: `_set_slot_pair(bat1, bat2, source="init_from_card.striker")`
   - If `broadcast` matches `bat2_name`: `_set_slot_pair(bat2, bat1, source="init_from_card.non")`
   - Else: `_set_slot_pair(bat1, bat2, source="init_from_card.combined")` (arbitrary ordering)
   - No `broadcast` field: `_set_slot_pair(bat1, bat2, source="cold_start")` (arbitrary ordering)

`_set_slot_pair` writes both `self.striker` and `self.non` together. So **after
`_accept_initial`, `self.striker` is non-None** — assigned to either bat1 or
bat2 deterministically (broadcast-disambiguated when possible, else by slot
order).

If `card.get("broadcast")` is None (no broadcast strip read), the cold-start
path arbitrarily assigns bat1 as striker. The first ball event then validates or
rotates via `_apply_event`'s balls-delta logic.

**Question for the audit.** Does `_identify_and_set` Priority 3 ever fire *after*
`_accept_initial` has already set striker? Only if the cold-start assignment was
wrong and a later evidence frame can correct it. But the deterministic override
blocks the correction unless `self.striker is None`, which `_accept_initial`
ensures is not the case post-cold-start.

**Verdict preview**: Priority 3 should be unreachable post-cold-start in Context A.

**Context B — hot-resume from cache (`_resume_from_cache_hot`, `:2630+`)**

The hot-resume path reads from a cache snapshot:

```python
_striker = cached.get("striker")
_non = cached.get("non")
if _striker and _non:
    self._set_slot_pair(_striker, _non, source="hot_resume")
elif _active:
    # Fall back to active-pair ordering if striker/non weren't cached
    # (older cache shapes).
    self._set_slot_pair(
        _active[0], _active[1] if len(_active) > 1 else None,
        source="hot_resume")
```

Two sub-cases:

- **B-i (modern cache shape)**: cache has both `striker` and `non` — `_set_slot_pair` assigns directly. Post-resume, `self.striker` is non-None.
- **B-ii (older cache shape, striker/non absent)**: cache has only `active` list — `_set_slot_pair` assigns by ordering (active[0] as striker, active[1] as non). Post-resume, `self.striker` is non-None but possibly wrong.
- **B-iii (cache empty / no `_active`)**: neither branch fires; `self.striker` stays at whatever pre-resume value it had (typically `None` for fresh process).

For sub-case B-ii, `_identify_and_set` Priority 3 could correct the
misassignment — IF the deterministic override allowed broadcast writes when
`self.striker is set but wrong`. Currently the override rejects all such
writes. So Priority 3 is **effectively dead in B-ii** (override blocks it) and
**unreachable in B-i** (striker already set correctly).

For B-iii, `self.striker` stays None. Priority 3 then fires on the next frame
with a broadcast indicator.

**Verdict preview**: Priority 3 is load-bearing only in sub-case B-iii (empty
cache / no `_active`), which is a degenerate hot-resume path — possibly a
process-restart with no prior session data, in which case hot-resume itself
should re-enter COLD_START rather than partial-resume.

**Context C — post-wicket gap (`_apply_event:5045-5059`)**

Post-wicket striker handling:

```python
if self._same_player_canon(best_dismissed, self.striker):
    self._set_slot_pair(
        None, survivor,
        source="apply_event.wicket_striker_out")
elif self._same_player_canon(best_dismissed, self.non):
    self._set_slot_pair(
        survivor, None,
        source="apply_event.wicket_non_striker_out")
```

Two sub-cases:

- **C-i (striker dismissed)**: `_set_slot_pair(None, survivor)`. After this, `self.striker is None` and `self.non = survivor`. The next frame might fire `_identify_and_set` Priority 3 if the broadcast strip names a new batter.
- **C-ii (non-striker dismissed)**: `_set_slot_pair(survivor, None)`. `self.striker = survivor` (the previous non-striker, now on strike). `self.non is None`. Priority 3 doesn't fire because `self.striker` is set.

Sub-case C-i is the canonical post-wicket gap. The new batter's name has to
come from somewhere; until then, `self.striker` stays None and Priority 3 is
the path that establishes the new striker once Scout reads the new batter into
the broadcast strip.

**Verdict preview**: Priority 3 is **load-bearing in C-i** — it's the
canonical mechanism for assigning a new-batter striker post-dismissal.

### 1.4 The S5b-2 lesson re-applied

S5b-2's audit found `_identify_striker:4689-4698` was dead/harmful because the
deterministic override at a sibling site blocked the same write pattern at
`_identify_and_set`. The override IS the architecture — broadcast-driven
striker writes are deprecated mid-over.

S5b-3 asks the inverse question: are there sites where broadcast-driven writes
are NOT deprecated? Yes — when `self.striker is None`. That's the cold-start
condition, and Context C-i is the most frequent occurrence: every post-wicket
gap reopens the condition until the new batter arrives.

## 2. Six-gate audit per context

### 2.1 Context A — cold-start exit

**Gate 1 — enumerate callers.** `_identify_and_set` Priority 3 fires
post-`_accept_initial` only if `self.striker is None`. `_accept_initial` itself
calls `_set_slot_pair` with bat1/bat2 (with broadcast disambiguation), so
post-call `self.striker` is non-None. Priority 3 should not fire in this
context.

**Gate 2 — classify.** Unreachable in normal flow. Could be reached only if a
separate code path nullified `self.striker` between `_accept_initial` and the
next `_identify_and_set` call. No such path is present in the current code.

**Gate 3 — adjacent state.** `_accept_initial` uses `card.get("broadcast")`
(the broadcast strip indicator, not `broadcast_striker`) to disambiguate.
These are two different fields:

- `card.get("broadcast")`: legacy broadcast strip text (free-form)
- `card.get("broadcast_striker")`: the dedicated striker indicator (\*-marked
  player from the strip)

Both are populated from Scout's OCR output. The `_accept_initial` path uses
the legacy field for initial disambiguation; the Priority 3 path uses the
dedicated field.

**Gate 4 — equivalence proof.** Since Priority 3 doesn't fire in normal
Context A flow, deleting it has no effect here. Equivalence trivially holds.

**Gate 5 — lifecycle.** `_accept_initial` sets `self.striker` via
`_set_slot_pair`; the lifecycle from that point is event-driven rotation in
`_apply_event`. No gap.

**Gate 6 — predicted flip.** Zero. Priority 3 doesn't fire post-cold-start in
the corpus (S5b-2 confirmed: zero invocations with `self.striker is None`).

**Verdict A**: Priority 3 has NO authority in Context A. The `_accept_initial`
path is the canonical cold-start striker assignment; it uses `card.get("broadcast")`
(not `broadcast_striker`). Priority 3 is unreachable here.

### 2.2 Context B — hot-resume from cache

**Gate 1 — enumerate callers.** Three sub-cases:

- B-i (modern cache, striker/non present): `_set_slot_pair` assigns directly.
  Priority 3 unreachable.
- B-ii (older cache, only `active` list): `_set_slot_pair` assigns by order.
  Priority 3 cannot correct because the deterministic override blocks
  broadcast writes mid-existing-striker.
- B-iii (cache empty / no `_active`): `_set_slot_pair` doesn't fire.
  `self.striker` stays at its pre-resume value (typically None). Priority 3
  fires on next frame with broadcast indicator.

**Gate 2 — classify.**

- B-i: unreachable (Priority 3 doesn't fire).
- B-ii: blocked by override (Priority 3 fires but write rejected).
- B-iii: load-bearing if hot-resume is allowed to enter WARM with empty state.

**Gate 3 — adjacent state.** What does `_resume_from_cache_hot` do in
sub-case B-iii? Looking at the code: if neither `_striker`/`_non` nor `_active`
is present, neither branch fires. `self.mode = "WARM"` is still set, which
means the next frame goes through `_handle_warm` with `self.striker = None`.

Is B-iii a real production path or a defensive case? The cache shape is owned
by `MatchStateCache`, and the "older cache shape" comment suggests the
`_active`-only branch is legacy. The "no `_active`" case implies an even older
or corrupt cache state.

**Gate 4 — equivalence proof.** For B-iii, if Priority 3 is deleted,
`self.striker` stays None until the first ball event commits and the rotation
logic assigns it. Until then, the UI shows no striker. Is that worse than
showing a broadcast-derived guess?

This depends on the SLA. If the UI tolerates a 1-frame striker=None gap before
the first ball lands, deletion is fine. If not, Priority 3 is the only
mechanism that fills the gap pre-event.

**Gate 5 — lifecycle.** B-iii is the only path where `self.striker = None`
post-`_resume_from_cache_hot`. The lifecycle for striker after that depends on
when the first ball event arrives. Could be many frames (the broadcast
backoff window).

**Gate 6 — predicted flip.** Production-only. The L2 corpus exercises cold-start,
not hot-resume — so the S5b-2 corpus check doesn't cover this case. Predicted
flip count cannot be derived from the test corpus alone.

**Verdict B**: Priority 3 is load-bearing **only in sub-case B-iii**, which is a
degenerate hot-resume that should arguably re-enter COLD_START rather than
partial-resume. The right fix here is NOT to keep Priority 3 — it's to fix
`_resume_from_cache_hot` to either populate striker reliably (require modern
cache shape) or refuse to enter WARM with empty state. Priority 3 is patching
a hot-resume defect downstream.

### 2.3 Context C — post-wicket gap

**Gate 1 — enumerate callers.** Sub-case C-i (striker dismissed): post-wicket
`_apply_event` clears `self.striker`, leaves `self.non = survivor`. Next
`_identify_and_set` call fires Priority 3 because `self.striker is None`.

**Gate 2 — classify.** Load-bearing. The new batter's name comes from
`broadcast_striker` (the dedicated striker indicator on the broadcast strip,
which the broadcaster updates when the new batter walks in).

**Gate 3 — adjacent state.** Alternative derivation sources for "new batter
identity":

- `card.bat1_name` / `card.bat2_name`: Scout's batter rows. The new batter
  may appear here once Scout reads the updated strip.
- `card.broadcast`: legacy free-form broadcast text — same source as Context A.
- Tracker `on_lock` callback (`test_pipeline.py:7227`): the striker tracker
  fires `_resweep_pending_attribution(name, "striker")` when its streak
  threshold trips.

The `bat1_name`/`bat2_name` path is the most natural derivation source for the
new batter's identity. Post-wicket, Scout reads the updated strip and one of
the bat slots changes from the dismissed batter to the new batter. The
question is whether `_identify_and_set`'s Priority 1 (balls-delta) and
Priority 2 (runs-delta) can resolve the new striker without consulting
`broadcast_striker`.

**Priority 1 (balls-delta)** requires both batters' ball counts to be
available with d_balls=1 / 0. Post-wicket, the new batter has `balls=0` from
Scout's first read; the surviving batter has the same balls as the prior frame.
If the first post-wicket ball commits with a new-batter ball-count delta of 0
(new batter hasn't faced yet), and the surviving batter's ball count is also
flat (they weren't on strike for the wicket ball), then d_balls is `(0, 0)` —
ambiguous.

**Priority 2 (runs-delta)** has the same problem: post-wicket, both
batters' runs are typically flat until the first non-wicket ball commits.

So Priority 1+2 cannot resolve the immediate post-wicket striker. Priority 3's
broadcast indicator is the path that fills this gap UNTIL a ball commits.

**Gate 4 — equivalence proof.** Two derivation alternatives:

1. **Defer striker assignment until first post-wicket ball event.** The UI
   shows `striker=None` (or the prior pair with one slot empty) until a ball
   commits, at which point `_apply_event`'s rotation logic resolves.
2. **Bind new striker from `bat1_name`/`bat2_name` slot diff.** Post-wicket,
   one slot changed; the new value is the new batter. But which one is on
   strike? Without `broadcast_striker`, defaulting to "the new batter is on
   strike" is conventionally correct (the new batter takes the dismissed
   batter's place, so they're on strike if the dismissed batter was on strike).
   But this requires knowing which batter was dismissed (which we have: it's
   the cleared slot).

Option 2 is the architectural derivation: after `_set_slot_pair(None, survivor,
source="apply_event.wicket_striker_out")` runs, the cleared slot was the
striker. The new batter who replaces that slot will be the new striker. So
when Scout reads the updated strip and one of bat1/bat2 changes to a new name,
that new name becomes the striker by definition.

This derivation does NOT require `broadcast_striker`. It requires:
- Knowing which slot was cleared (the cleared one was the striker — call this
  `_last_cleared_striker_slot`)
- Diffing `card.bat1_name` / `card.bat2_name` against the prior frame to find
  the new name in the cleared slot

**Gate 5 — lifecycle.** The `_last_cleared_striker_slot` state would need to
be tracked across frames between the wicket event and the new-batter arrival.
Cleared by the first frame where the new batter is identified.

**Gate 6 — predicted flip.** Without production data, unclear. The L2 corpus
has a wicket event (frame 361 in watch_20260519_121701) but the dump window
ends before the new batter arrives — so the post-wicket gap path isn't fully
exercised in L2. L1.5 has wicket events but they're hand-derived ledger
balls; the new-batter resolution is supplied directly in the ledger, not
inferred. **Production traffic is the only available evidence source.**

**Verdict C**: Priority 3 is **load-bearing** in Context C-i, but it can be
replaced with a slot-diff derivation IF `_last_cleared_striker_slot` is
tracked and the `bat1_name`/`bat2_name` diff is wired into a new derivation
path. This is NOT a simple deletion — it requires a small new derivation
helper.

## 3. Derivation alternatives

### 3.1 Post-wicket new-batter slot-diff

Proposed addition to `_apply_event` wicket handler:

```python
if self._same_player_canon(best_dismissed, self.striker):
    self._set_slot_pair(None, survivor,
                       source="apply_event.wicket_striker_out")
    self._last_cleared_striker_slot = ...  # which of bat1/bat2 was cleared
```

Then in `_identify_and_set`, add Priority 3' before the current Priority 3:

```python
# Priority 3' (post-wicket new-batter detection): if self.striker is
# None due to a prior wicket clearing the slot, and bat1/bat2 slot
# diff shows a new name in the cleared position, that's the new
# striker.
if not new and self.striker is None and self._last_cleared_striker_slot:
    cleared_key = self._last_cleared_striker_slot
    new_name_in_cleared_slot = card.get(cleared_key)
    prior_name = (prev_b1_name if cleared_key == "bat1_name"
                  else prev_b2_name)
    if (new_name_in_cleared_slot
            and new_name_in_cleared_slot != prior_name
            and new_name_in_cleared_slot != self.non):
        new = new_name_in_cleared_slot
        method = "post_wicket_slot_diff"
        self._last_cleared_striker_slot = None
```

This derivation uses only primitives (slot names, prior values, the survivor
held in `self.non`). No `broadcast_striker` consulted.

### 3.2 Hot-resume Context B fix

For sub-case B-iii (no `_active` in cache), the right fix is at
`_resume_from_cache_hot`, not at `_identify_and_set`: refuse to enter WARM if
cache lacks both `striker`/`non` AND `_active`. Re-enter COLD_START instead.
This eliminates the gap that Priority 3 currently patches.

For sub-case B-ii (older cache shape, only `_active` present), the current
ordering-based fallback (`active[0]` as striker) is already in place. If
production observation shows B-ii produces wrong striker frequently, the fix
is to populate the cache with `striker`/`non` properly so B-ii becomes B-i.
Again, not a Priority 3 concern.

### 3.3 Cold-start Context A — no change needed

`_accept_initial` already uses `card.get("broadcast")` (the legacy free-form
broadcast text). This is a separate consumer from `broadcast_striker`. Cold-start
striker assignment doesn't depend on the dedicated `broadcast_striker` field at
all — Priority 3 is unreachable post-cold-start.

## 4. Equivalence proof summary

| Context | Priority 3 deletable? | Replacement | Risk |
|---|---|---|---|
| A — cold-start exit | Already effectively dead; `_accept_initial` uses `card.broadcast` (free-form), not `broadcast_striker` | None needed | Zero |
| B-i — modern cache | Already unreachable | None needed | Zero |
| B-ii — older cache | Blocked by deterministic override | Fix at `_resume_from_cache_hot` (populate striker properly) | Stale assignment until ball commits |
| B-iii — empty cache | Load-bearing; fixing this needs `_resume_from_cache_hot` to refuse partial resume | Fix at `_resume_from_cache_hot` (re-enter COLD_START on empty cache) | UI shows no striker briefly during the broadcast backoff window |
| C-i — striker dismissed | Load-bearing; replaceable with `_last_cleared_striker_slot` derivation | New `Priority 3'` slot-diff path | Need to track cleared-slot state across frames |
| C-ii — non-striker dismissed | `self.striker` already set; Priority 3 doesn't fire | None needed | Zero |

**Equivalence claim**: With the two replacements (3.1 slot-diff for C-i, 3.2
hot-resume hardening for B), `broadcast_striker`'s consumption at
`_identify_and_set` can be deleted without losing any current functionality.

## 5. Risk register

**The Queue B / `_ScoutRetryBuffer` / S5a / S5b pattern**: a field that looks
like a detection signal but is actually playing a structural role visible only
under audit. Where might `broadcast_striker` be subtly load-bearing here?

1. **Multi-frame ambiguity windows during hot-resume.** B-iii's "empty cache"
   case may be a production reality if the cache was wiped between sessions or
   if a process restart raced with a checkpoint write. The replacement (3.2
   re-enter COLD_START) changes the semantic — fast restarts now go through
   the cold-start gate again, which has its own latency. Is that acceptable?
2. **Post-wicket new-batter where Scout reads ambiguous slot.** If post-wicket
   the new batter's name doesn't immediately appear in `bat1_name`/`bat2_name`
   (Scout's strip is still showing the dismissed batter's name due to OCR
   lag), the slot-diff derivation can't fire until the strip refreshes.
   Meanwhile, `broadcast_striker` updates faster because it's the
   broadcaster's authoritative indicator. This is the "broadcast leads
   derivation by 1-3 frames" pattern — the same pattern that justified
   Queue B's keep verdict.
3. **The `card.broadcast` vs `card.broadcast_striker` distinction.** These
   are two different fields surfaced by Scout. The cold-start path uses
   `broadcast` (free-form); `_identify_and_set` Priority 3 uses
   `broadcast_striker`. Confirming they don't have hidden overlap requires
   reading parse_strip's full output schema.
4. **Striker-tracker `on_lock` callback** at `test_pipeline.py:7227`. The
   tracker fires `_resweep_pending_attribution` when its streak threshold
   trips. Could this be the canonical event-driven initialization for striker?
   If so, broadcast_striker is just a faster (but noisier) proxy for the same
   signal.

**Failure modes if we delete and a corner case wasn't enumerated:**

- Post-wicket frames between dismissal and slot-diff identifying the new batter
  show `striker=None` in the UI for longer than they currently do.
- Hot-resume from empty cache lengthens cold-start re-entry latency.
- Phantom-wicket cases (frame 245 of watch_20260519_121701, already documented)
  no longer get the broadcast-driven wrong-striker tagging that could be used
  for downstream divergence detection. The
  `STRIKER-SM-BROADCAST-DISAGREES-DETERMINISTIC` trace would lose one source.

## 6. Per-context verdict

| Context | Verdict | Action |
|---|---|---|
| A — cold-start exit | **Already addressed** | `_accept_initial` doesn't use `broadcast_striker`; Priority 3 doesn't fire post-cold-start. No code change. |
| B-i — modern cache | **Already addressed** | `_resume_from_cache_hot` sets striker directly. No code change. |
| B-ii — older cache | **Migration path** | Long-term, populate the cache with `striker`/`non` so all instances are B-i. No immediate code change. |
| B-iii — empty cache | **Hot-resume hardening** | Refuse to enter WARM if cache lacks both `striker`/`non` AND `_active`; re-enter COLD_START instead. Small targeted fix at `_resume_from_cache_hot`. |
| C-i — striker dismissed | **Replace with slot-diff derivation** | Add `_last_cleared_striker_slot` state + `Priority 3'` in `_identify_and_set`. Track the cleared slot at wicket commit; use it on next frame's slot-diff. |
| C-ii — non-striker dismissed | **Already addressed** | `_set_slot_pair(survivor, None)` sets striker non-None. No code change. |

**Aggregate verdict**: S5b-3 is **executable as a sequenced refactor**, not as
a single deletion. The right shape:

1. **Phase S5b-3a**: Land the post-wicket slot-diff derivation (Priority 3'
   addition). This is additive — both broadcast-driven and slot-diff paths
   coexist behind a feature flag. Instrument both with traces; aggregate
   divergence patterns across production data.
2. **Phase S5b-3b**: Land hot-resume hardening (refuse empty-cache WARM
   entry). Independent of S5b-3a.
3. **Phase S5b-3c**: After both replacements have production data confirming
   equivalence, delete `broadcast_striker` consumption at `_identify_and_set`
   Priority 3 entirely. Bundle with S5b-1 (observability cleanup) — the field
   itself can also be removed from FrameInput at this point if no other
   consumer remains.

The pattern mirrors the dispatch-loop redesign: additive scaffold first, shadow
comparison data accumulates, then the deletion ships as one coordinated commit
after equivalence is empirically validated.

## 7. Risk-adjusted recommendation

**Ship S5b-3a first.** Post-wicket slot-diff derivation is the highest-value
replacement (Context C-i is the most frequent occurrence of Priority 3 firing)
and the most clearly derivation-eligible (slot-diff is a 5-primitive-contract
derivation, no broadcast input needed). The corpus-comparison pattern from
S5b-2 + the dispatch-loop scaffold applies directly: instrument both paths,
let shadow data accumulate, ship the deletion only after equivalence holds.

**Defer S5b-3b and S5b-3c.** Hot-resume hardening (B-iii) is operationally
narrow — production data should confirm B-iii is actually exercised before
investing engineering capacity. S5b-3c (final deletion) requires both S5b-3a
shadow data AND production confirmation that B-iii doesn't matter; it's the
last commit, not the first.

**Do NOT pursue a wholesale `broadcast_striker` deletion** without S5b-3a's
shadow data first. The S4b regression pattern is exactly what this memo is
designed to prevent.

## 8. Out of scope

- **Initial-striker SLA**: how long can `self.striker = None` persist before
  the UI must show *something*? This is a product decision that informs
  whether B-iii's "refuse partial resume" is acceptable.
- **Striker-tracker `on_lock` as the canonical initialization event**: a
  larger refactor that would route ALL striker assignments through the
  tracker callback. Worth considering after S5b-3a/b/c land, not before.
- **Class 9 assertion rename**: stays on the cleanup queue.

## 9. Sequence recommendation

| Stage | Action | Gates | Predicted flips |
|---|---|---|---|
| S5b-3a | Add `_last_cleared_striker_slot` state + Priority 3' slot-diff path behind `SM_POST_WICKET_SLOT_DIFF` feature flag (default off). Instrument both paths with `STRIKER-POST-WICKET-DERIVATION` trace. | Pre-commit L1.5 + L2 hold; trace data aggregates across observability run. | Zero (additive, flag-default-off). |
| Observability gate | Production session accumulates `STRIKER-POST-WICKET-DERIVATION` traces. Compare broadcast-driven vs slot-diff for every post-wicket gap event. | Zero divergence across N consecutive post-wicket events. | n/a (observation only). |
| S5b-3a flag flip | Default-on `SM_POST_WICKET_SLOT_DIFF`; broadcast path becomes secondary. | One full session at default-on with no class 9 / class 12 regressions. | Zero. |
| S5b-3b | Hot-resume hardening: refuse empty-cache WARM entry. | Independent — only ships if production data confirms B-iii is exercised. | Possibly small (added cold-start re-entry cycles for that path). |
| S5b-3c | Delete `broadcast_striker` consumption at `_identify_and_set:4283-4293` + `FrameInput.broadcast_striker` field. Bundle with S5b-1 observability cleanup. | S5b-3a flipped + S5b-3b shipped + no other consumer remains. | Zero (consumers replaced or eliminated). |

The discipline is the same one applied throughout this workstream: additive
scaffold → shadow data → equivalence proof → deletion. The five §7 audits to
date (Queue B / `_ScoutRetryBuffer` / S5a / S5b-2 / S5b-3) have produced four
Keep verdicts and one Delete; the Delete (S5b-2) followed exactly this
pattern. S5b-3a is the next instance of the same pattern.

## 10. What this memo deliberately does NOT do

- **No code commits.** S5b-3a's scaffold is the next deliverable, not this
  memo's output.
- **No assertion library additions.** Class 9's misnamed assertion stays
  unchanged here; rename is a separate cleanup.
- **No FrameInput.broadcast_striker deletion proposal.** That's S5b-3c, gated
  on observability data that doesn't exist yet.
- **No claim that the slot-diff derivation is bug-free.** The shadow-comparison
  scaffold is what produces that evidence; this memo only proposes the shape.

The memo's contribution is the per-context decomposition and the explicit
sequencing: S5b-3 is not a deletion, it's a three-phase refactor that ends in
a deletion. Treating it as a deletion (as the original §7 framing did) is the
same pattern that produced S4b's regression. The discipline is what changed.

## 11. Revision — Context A re-audit against validate_gtrr_20260520_180715 (2026-05-20)

The original Context A verdict — "Priority 3 doesn't fire in normal Context A flow; `_accept_initial`'s `card.get("broadcast")` matching covers initial-striker disambiguation; **already addressed**, zero predicted flips" — is empirically falsified by the
`validate_gtrr_20260520_180715` production session. First BAT-DELTA at frame 12 credits Shubman Gill +4 runs +1 ball, but the Cricbuzz commentary opens with "Sai Sudharsan on strike, Shubman Gill non-striker." Gill received credit for Sai's first FOUR.

This section documents the actual failure mechanism, replaces the §6 verdict for
Context A, and proposes the corrected fix path.

### 11.1 Data gathering — frames 1–13 of validate_gtrr

| Frame | pipeline.striker | extractor.batters[0] | extractor.batters[1] | scoreboard.striker tracker |
|---|---|---|---|---|
| 3 | `'—'` | (no batters yet) | — | (uninitialised) |
| 4 | `'—'` | `Sai Sudharsan {0,0,striker:False}` | `Shubman Gill {None,None,striker:None}` | `[STRIKER-OBSERVE] cand='Sai' leader='Sai' state=TENTATIVE` |
| 8 | `'Shubman Gill'` | (no batter data extracted) | — | (no observation this frame) |
| 11 | `'Shubman Gill'` | `Sai Sudharsan {4,1,striker:True,_raw='SUDHARSAN'}` | `Shubman Gill {0,0,striker:False,_raw='GILL'}` | `[STRIKER-OBSERVE] cand='Gill' leader='Sai' state=TENTATIVE flipped=False` |
| 12 | `'Shubman Gill'` | (extractor saw both but `striker:False` on both — Scout dropped the indicator) | — | `[STRIKER-OBSERVE] cand='Gill' leader='Gill' state=PUBLISHABLE flipped=True` |
| 13 | `'Shubman Gill'` | `'Shubman Gill 4(1)' is_striker=True` in `batting_card_at_crease` | — | locked Gill |

**Key signals.**

- **Frame 4: Scout / extractor correctly identifies Sai as striker.** The
  `striker:True` flag on `batters[0]` (Sai) at frame 11 confirms Scout's `*`-marker
  detection working. Scoreboard tracker also sees Sai as leader.
- **Frame 8: pipeline.striker = Shubman Gill is already set.** Between frame 4 and
  frame 8, SM transitioned through some path that committed Gill as striker.
- **Frame 11: Scout's broadcast indicator says Sai, but SM's `self.striker`
  is already Gill.** The deterministic rotation override at `:4295-4325` blocks
  the broadcast write because `self.striker is not None` — the wrong striker is
  *locked*.
- **Frame 12: COLD_START → WARM consensus committed**, marked as re-entry
  (`is_reentry: True`). `_accept_initial` ran but inherited the prior
  `self.striker = Gill` because re-entry preserves striker.
- **Frame 12 BAT-DELTA: Gill +4 runs +1 ball.** The cold-start synth event
  credited the wrong batter for the first ball.

### 11.2 Code path inspection — `_accept_initial:2789-2808`

```python
# Striker identification (W3–W6 → Lever 1 `_set_slot_pair`)
_strip_bc = card.get("broadcast")          # ← READS A FIELD NEVER WRITTEN
if _strip_bc:
    ind = str(_strip_bc).lower().strip()
    if self.bat1_name and ind in self.bat1_name.lower():
        self._set_slot_pair(self.bat1_name, self.bat2_name,
                           source="init_from_card.striker")
    elif self.bat2_name and ind in self.bat2_name.lower():
        self._set_slot_pair(self.bat2_name, self.bat1_name,
                           source="init_from_card.non")
    else:
        self._set_slot_pair(self.bat1_name, self.bat2_name,
                           source="init_from_card.combined")
else:
    self._set_slot_pair(self.bat1_name, self.bat2_name,
                       source="cold_start")
```

**`card.get("broadcast")` is unwritten.** Grep across `score_manager.py` for
`card["broadcast"]` / `card.get("broadcast")` returns exactly one hit — this
read. **No producer ever sets `card["broadcast"]`.** The field is dead.

The chain that *should* feed the striker discriminator:

```
Scout text (with *-marker)
  → extract_regex.py:1781-1783 result["striker_broadcast"] = first-name
  → test_pipeline.py:13823 FrameInput.broadcast_striker = _bcast.get("striker_broadcast")
  → score_manager.py:1616   card["broadcast_striker"] = frame.broadcast_striker
  → consumed by _identify_and_set Priority 3 (`:4283-4293`)
  → NOT consumed by _accept_initial (which reads card["broadcast"] instead)
```

`_accept_initial`'s broadcast-text branch is dead because it reads the wrong
field name. Every cold-start run falls through to the `else` branch with
`source="cold_start"`, which sets striker = bat1 regardless of who's actually
on strike.

### 11.3 Failure mode classification

This is **not** a detection bug. Scout's strip parsing correctly identifies
the striker via the `*`-marker; the information reaches `card["broadcast_striker"]`.
This is a **stale field name** bug in `_accept_initial` — the consumer reads a
name (`"broadcast"`) that no producer writes.

History of how this drifted: pre-2026, the Scout output schema used
`result["broadcast"]` as the free-form broadcast text. Schema rename to
`result["striker_broadcast"]` happened (probably in the §7 broadcast G work or
earlier), but `_accept_initial`'s consumer never updated.

### 11.4 Per-context verdict update

| Context | Original verdict | **Revised verdict (2026-05-20)** | Action |
|---|---|---|---|
| A — cold-start exit | "Already addressed" | **FALSIFIED — stale field name** | Fix: replace `card.get("broadcast")` with `card.get("broadcast_striker")` at `_accept_initial:2789-2808`; align matching logic with `_identify_and_set` Priority 3 (first-name match, skip when batters share first name). |
| B-i — modern cache | unchanged: already addressed | unchanged | none |
| B-ii — older cache | unchanged: blocked by override | unchanged | unchanged |
| B-iii — empty cache | unchanged: hot-resume hardening | unchanged | unchanged |
| C-i — striker dismissed | replace with slot-diff (S5b-3a) | unchanged | S5b-3a scaffold shipped `6aea92f` |
| C-ii — non-striker dismissed | unchanged: already addressed | unchanged | none |

**Context A is the highest-blast-radius bug class in this session** — `B-ε`'s
mis-resolution cascades to every BAT-DELTA event for the rest of the innings
(Gill credited Sai's runs throughout). The empirical regression detector
`trace_epsilon_initial_striker` (commit `1d92101`) catches it.

### 11.5 Proposed fix path

Three execution options, in order of increasing scope:

**Option F1 — direct field rename (smallest).**

Single-edit: replace `card.get("broadcast")` with `card.get("broadcast_striker")`
at `score_manager.py:2798` and update the matching logic to use first-name
substring (matching the Priority 3 `:4283-4293` style):

```python
_strip_bc = card.get("broadcast_striker")
if _strip_bc:
    ind = _strip_bc.lower().strip()
    b1_first = ((self.bat1_name or "").split() or [""])[0].lower()
    b2_first = ((self.bat2_name or "").split() or [""])[0].lower()
    if b1_first and b2_first and b1_first != b2_first:
        if b1_first in ind and b2_first not in ind:
            self._set_slot_pair(self.bat1_name, self.bat2_name,
                               source="init_from_card.striker")
        elif b2_first in ind and b1_first not in ind:
            self._set_slot_pair(self.bat2_name, self.bat1_name,
                               source="init_from_card.non")
        else:
            self._set_slot_pair(self.bat1_name, self.bat2_name,
                               source="init_from_card.combined_ambiguous")
    else:
        self._set_slot_pair(self.bat1_name, self.bat2_name,
                           source="init_from_card.combined")
else:
    self._set_slot_pair(self.bat1_name, self.bat2_name,
                       source="cold_start_no_indicator")
```

This is a real-fix-with-low-risk commit. Predicted flips: `trace_epsilon_initial_striker` flips from FAIL to PASS for sessions where Scout's `*`-marker was detected at cold-start (the common case). For sessions where Scout missed the indicator entirely (no `striker_broadcast` populated), behavior is unchanged from current (cold-start default = bat1).

**Option F2 — additive scaffold like S5b-3a (matches established pattern).**

Add `SM_COLD_START_INITIAL_STRIKER_DERIVE` feature flag + `STRIKER-COLD-START-DERIVATION` trace tag. With flag off, current `card.get("broadcast")` (dead) branch unchanged; shadow trace records what F1's logic *would have* picked. With flag on, F1's logic takes precedence. Same shape as `SM_INLINE_MULTI_BALL` and `SM_POST_WICKET_SLOT_DIFF`.

**This is over-engineering for a stale-field-name fix.** Option F2's shadow comparison is valuable when the proposed alternative path's correctness is uncertain. Here the proposed path is *just reading the field that already exists and is consumed correctly by `_identify_and_set` Priority 3* — there's nothing speculative to shadow-compare against. Recommended skip; F2 is documented for completeness.

**Option F3 — derive from extracted batters' `striker:True` flag (architecturally cleanest).**

Bypass `card["broadcast_striker"]` entirely; consume `extracted["batters"][i]["striker"]` directly. This requires the `striker` flag to be propagated through `_build_scorecard` so `card.bat1_is_striker` (or equivalent) reaches `_accept_initial`. Larger scope; pushes the derivation source up to where parse_strip already has the answer.

F3 is the right long-term architecture but requires `card`-shape changes that ripple through the pipeline. F1 is the surgical fix that closes B-ε empirically; F3 can follow in a separate workstream.

### 11.6 Risk register

- **Scout misses the `*`-marker.** When `striker_broadcast` is None, F1 falls
  through to the same `source="cold_start"` default as today (bat1 as striker).
  No regression vs current behavior; just no improvement on those frames.
- **First-name shared between batters.** F1 handles this via the
  `b1_first != b2_first` guard, matching Priority 3's design. Same-first-name
  pairs default to `init_from_card.combined` (bat1 striker by order). Same as
  current behavior for those edge cases.
- **`broadcast_striker` value disagrees with derivation later.** Frames 8-11
  of validate_gtrr show the deterministic rotation override blocking
  broadcast writes once `self.striker` is locked. F1 doesn't change that —
  it only affects the initial assignment. If the initial assignment is wrong
  (e.g., Scout's `*`-marker landed on the non-striker due to OCR error), the
  override prevents broadcast from later correcting it. This is the residual
  detection-boundedness risk. Frequency unknown; production data with F1
  shipped + trace_epsilon_initial_striker as gate will surface it.
- **Re-entry path.** `is_reentry: True` (frame 12 in validate_gtrr) means
  `_accept_initial` runs but `self.striker` may already be set from prior
  WARM activity. F1's `_set_slot_pair` call would overwrite it — but the
  question is whether that's correct. If WARM established a striker via
  legitimate balls-faced evidence and SM dropped to COLD_START, the re-entry
  should preserve the existing striker. **F1 needs a guard: only fire the
  broadcast-striker disambiguation when `self.striker is None`.** Otherwise
  re-entry could clobber a correctly-derived striker with a stale broadcast
  hint.

### 11.7 Updated sequence recommendation

| Stage | Action | Gate | Predicted flips |
|---|---|---|---|
| F1 | Replace `card.get("broadcast")` with `card.get("broadcast_striker")` at `_accept_initial:2789-2808` with first-name match logic + `self.striker is None` guard for re-entry case. | Pre-commit L1.5 + L2 hold; `trace_epsilon_initial_striker` flips FAIL → PASS for validate_gtrr_20260520_180715 (and any other session where Scout detected the striker indicator at cold-start). | Zero for fixture corpus (L2 dc-vs-kkr fixture starts with both batters at 0/0 — no `*`-marker context to test against). Beneficial for production data with Scout-detected indicator. |
| F3 (later) | Propagate `extracted["batters"][i]["striker"]` flag through `_build_scorecard` → `card.bat1_is_striker` → consumed directly by `_accept_initial`. Cleaner derivation source. | Separate workstream; depends on `card`-shape design. | n/a |
| S5b-3a (already shipped) | Post-wicket slot-diff scaffold | `STRIKER-POST-WICKET-DERIVATION` accumulates in production | Zero (additive, flag default off) |

### 11.8 Why the original audit missed this

The §7.6 / §6 verdict was reached via code reading, not production-data
verification. The §7.2 gate 6 ("predicted flip gate — predict the
assertion-library flip count BEFORE the dry-run") was met *qualitatively*
("zero, Priority 3 doesn't fire post-cold-start") but the prediction was based
on the *assumption* that `_accept_initial`'s broadcast-text branch handled
disambiguation correctly. That assumption never got an empirical check.

The S5b-2 audit succeeded because it ran the §7.2 checklist against a
captured corpus AND predicted flips with concrete frame numbers. The S5b-3
Context A audit reached its verdict without the same empirical step — exactly
the failure mode the discipline is designed to prevent.

**Lesson baked permanently into §7.2.** "Predicted flip gate" must include a
concrete frame-by-frame audit against captured trace data — not a qualitative
"this code path doesn't fire" claim. The five-observability-streams convergence
+ `trace_epsilon_initial_striker` baseline are the operational mechanism that
will catch any future audit's hypothesis that fails empirical verification.
