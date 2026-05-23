# Workstream G — Scout-extraction timing at wicket-commit frames

**Status.** Step 1 (static-falsification root-localization). 0/5 empirical-
falsification budget consumed.
**Branch.** `obs/silent-wicket-absorption` (HEAD `b817ee0` at memo open).
**Entry data.** DCKKR captured dump `validate_dckkr_20260521_155356/` (749
scout reads, ~58 min wall) + post-§15 replay trace
`logs/trace/replay_dckkr_step8e.jsonl` (step 8/N final state — commit
`2ad432f`).
**Cross-reference.** HANDOFF §17.3 (Workstream G investigation queue);
`workstream_d_rotation_root_investigation.md` §3.4b (Scout-dismissed
field cross-fixture absence, 0/182 wicket-signal frames — adjacent
finding).

## §1 Problem statement + cascade-defer-rate evidence

Post-§15 commit 8/N (`1af2bd9` — `feat(8): post-wicket striker cascade
wired into apply_wicket_event`) the structural cascade in
`_apply_post_wicket_striker_rotation` (`score_manager.py:952–1016`) is
wired but **defers 100% of the time on this dump**. Empirical evidence
from `logs/trace/replay_dckkr_step8e.jsonl`:

```
2× WICKET-FALL-ONLY-CALLED events (frame 679, frame 855)
2× POST-WICKET-STRIKER-CASCADE-DEFERRED, both reason="new_batter_unresolved"
0× STRIKER-EVENT-DISPATCHED reason=wicket_new_batter / wicket_non_striker_stays
```

The two wicket-commit frames:

| Frame | Over | Dismissed | New batter (ground truth) | Cascade outcome |
|---|---|---|---|---|
| 679 | 8.0 | Nitish Rana | Sameer Rizvi | DEFERRED (new_batter_unresolved) |
| 855 | 9.5 | Pathum Nissanka | Tristan Stubbs | DEFERRED (new_batter_unresolved) |

The structural completion of §15 commit 8/N is real (cascade-defer trace
fires, anomaly tag never fires). The empirical drop on
**D-post-FoW-striker / C21b-symbol-revert / Compound-with-wicket-token**
does not land because the cascade never executes its mutation arm.

The hypothesis under audit: Scout's `new_batter` primitive is unavailable
at the moment `apply_wicket_event` runs. This memo root-localizes WHY.

## §2 Hypothesis enumeration

Per the operator brief:

- **G1** — Scout extraction cadence too low. Wicket frame N has no
  Scout read in the [N−k, N] window for any reasonable k.
- **G2** — Broadcast-strip render lag. The new-batter graphic appears on-
  screen M frames AFTER the wicket frame; Scout reads correctly but the
  source data isn't on the strip yet.
- **G3** — VLM prompt schema gap. `SCOUT_PROMPT` / `SCOUT_PROMPT_SHORT`
  does not request `new_batter` explicitly; LLM returns null even when a
  new-batter graphic is present. Cross-reference workstream D §3.4b
  (Scout-dismissed-field 0/182 across 4 fixtures).
- **G4** — Lock-mechanism gating. Striker/bowler `ConfidenceTracker` lock
  state suppresses identity reads during the wicket-commit window.
- **G5** — Cascade-defer condition predicate too strict.
  `apply_wicket_event` cascade-defer rejects reads that are actually
  present.

## §3 Static falsification pass

### §3.1 G5 (cascade-defer predicate) — **STATICALLY FALSIFIED**

`_apply_post_wicket_striker_rotation` at `score_manager.py:952–1016`. The
defer predicate is:

```python
# score_manager.py:970-987
dismissed = event.dismissed_batter
new_batter = event.new_batter
if dismissed is None:
    self._emit_trace(tag="POST-WICKET-STRIKER-CASCADE-DEFERRED",
                     payload={"reason": "dismissed_unresolved", ...})
    return
if new_batter is None:
    self._emit_trace(tag="POST-WICKET-STRIKER-CASCADE-DEFERRED",
                     payload={"reason": "new_batter_unresolved", ...})
    return
```

No strictness. Any non-None `event.new_batter` would proceed to the
rotation arm at `:988-1016`. The 100% defer rate on this dump is
**entirely upstream** — `event.new_batter` arrives None at every
wicket-commit invocation. G5 is not the surviving hypothesis.

### §3.2 G3 (VLM prompt schema gap) — **PARTIALLY CONFIRMED (architectural; coupled to G2)**

`eyes/vision.py:115-397`. Both `SCOUT_PROMPT_VERBOSE` (`:115-304`) and
`SCOUT_PROMPT_SHORT` (`:316-387`, the default per `:393-397`) define a
strict 7-field STRIP schema:

```
STRIP: <team> <runs>-<wkts> (<overs>) | extras=<n> | this_over=<symbols>
       | <striker> <r>(<b>) | <nonstriker> <r>(<b>) | <bowler> <w>-<r> (<o>)
```

No `dismissed` field. No `new_batter` field. No `incoming` field. No
`last_wicket` semantic. The contract treats batter identity as the
**current striker/non-striker on the bottom strip**, not as an event-
level wicket payload.

The pipeline derives `new_batter` via slot-diff: `_infer_wicket` at
`score_manager.py:5425-5454`:

```python
prev_batters = {n for n in [prev.get("bat1_name"),
                            prev.get("bat2_name")] if n}
curr_batters = {n for n in [card.get("bat1_name"),
                            card.get("bat2_name")] if n}
departed = prev_batters - curr_batters
arrived  = curr_batters - prev_batters
...
new_batter = arrived.pop() if len(arrived) == 1 else None
```

The slot-diff approach **requires the post-wicket strip to be visible in
the wicket-commit frame**. If the strip at frame N still shows the dismissed
batter (no slot change), `arrived = ∅` → `new_batter = None`.

G3 is partially confirmed: the prompt schema does not give Scout an
event-level new-batter primitive. But the fix is not localized to the
prompt — even with a `new_batter` field added, **Scout cannot extract
data that is not yet rendered on the strip** (see §3.3). G3 and G2
share the same upstream cause.

### §3.3 G2 (broadcast-strip render lag) — **EMPIRICALLY CONFIRMED (the surviving hypothesis)**

Raw scout reads from `validate_dckkr_20260521_155356/scout_raw.jsonl`
around each wicket-commit frame:

**Wicket 1 — Frame 679, Nitish Rana out at over 8.0:**

| Frame | STRIP striker | STRIP non-striker | Notes |
|---|---|---|---|
| 673 | PATHUM 43(24) | N RANA 8(9) | pre-wicket, ball 7.5 |
| 675 | PATHUM N RANA 43(24) | null | post-shot ambiguity |
| 676 | PATHUM 43(24) | N RANA 8(9) | pre-wicket repeat |
| 677 | null | null | "VISIBLE_TEXT: WICKET" (graphic) |
| 678 | null | null | "VISIBLE_TEXT: WICKET" (graphic) |
| **679** | **PATHUM 43(24)** | **N RANA 8(10)** | **wicket commit; strip still shows Rana** |
| 680 | null 8(10) | null | wicket-summary graphic |
| 688–707 | junk / DC 74-2 8 / ads / promos | | |
| **708** | **PATHUM 43(24)** | **RIZVI 0(0)** | **first frame with new batter on strip** |

**Lag: ~29 frames between wicket commit (679) and new-batter graphic (708).**

**Wicket 2 — Frame 855, Pathum Nissanka out at over 9.5:**

| Frame | STRIP striker | STRIP non-striker | Notes |
|---|---|---|---|
| 853 | PATHUM 46(28) | RIZVI 3(6) | pre-wicket, 80-2(9.4) |
| 854 | PATHUM > RIZVI 46(28) | null 3(6) | side_on with arrow |
| **855** | **PATHUM 46(28)** | **RIZVI 3(7)** | **wicket commit; strip still shows Nissanka (the dismissed batter)** |
| 856–860 | DC 90-3 (junk) / RCB 47-0 (junk) | | mid-cut promo content |
| 869 | wicket-summary graphic | | "SAMEER RIZVI c POWELL b NARINE" (note: bogus, not the actual wicket) |
| 873–875 | non-cricket cuts | | chutney jar, office, etc. |
| **892** | **PATHUM 46(28)** | **STUBBS 0(0)** | **first frame with new batter on strip** |

**Lag: ~37 frames between wicket commit (855) and new-batter graphic (892).**

The pattern is identical at both wickets. The broadcast strip latches
the dismissed batter at the wicket-commit frame and does not update with
the incoming new batter until ~29–37 frames later — typically the moment
the new batter physically walks to the crease after the celebration /
sponsor / promo sequence.

G2 is confirmed empirically.

### §3.4 G1 (Scout extraction cadence) — **STATICALLY FALSIFIED**

`scout_raw.jsonl` records 749 reads over a 58-minute capture
(~13 reads/min, ~4.6 s/read). The wicket-commit window has ample
coverage: 8 reads in frames 672–680 around wicket 1; 7 reads in frames
851–860 around wicket 2. Cadence is not the limiting factor.

The constraint is **content**, not **rate**. Scout reads the strip at
frame 679 and produces a faithful transcription — but the strip itself
does not contain the new-batter information. Adding more reads in
[N−k, N] cannot recover a primitive the broadcast hasn't rendered.

### §3.5 G4 (lock-mechanism gating) — **STATICALLY FALSIFIED**

The trace at frames 679 and 855 shows identity-resolution paths firing
normally:

```
F679: STRIKER-IDENTIFY-FALLBACK-INVOKED branch="state_fallback"
      broadcast_striker="Pathum Nissanka" bat1="Pathum Nissanka"
      bat2="Nitish Rana"  ← strip names parsed cleanly
F679: STRIKER-IDENTITY-PROPOSAL-REFUSED existing="Nitish Rana"
      proposed="Pathum Nissanka"
      source="identify_and_set.broadcast_first_name"
F679: WICKET-RESOLVED-FROM-DETERMINISTIC-STRIKER dismissed="Nitish Rana"
F679: STRIKER-IDENTITY-RESOLVED name="Pathum Nissanka"
      source="set_slot_pair:apply_event.wicket_non_striker_out"
F679: BOWLER-LOCK-RELEASED reason="over_end_credit_complete"
      prev_bowler="Cameron Green"
```

The `STRIKER-IDENTITY-PROPOSAL-REFUSED` at frame 679 is the §13.8.1
conservative-refuse semantic operating as designed (commit 8/N
`2ad432f`) — refusing a per-frame broadcast proposal when self.striker
is already set. This is load-bearing protection against the +24/+9
boundary regression closed at commits 7c/9. The refuse is NOT
suppressing a new-batter read; it is suppressing a rotation proposal
for Pathum (who was already the non-striker becoming striker via the
end-of-over swap immediately preceding).

`BOWLER-LOCK-RELEASED` at frame 679 is the over-end credit completion
firing — orthogonal to striker-identity gating.

No lock-state evidence implicates G4 in suppressing new_batter reads.
The relevant constraint is upstream of any lock: the strip never
carries the new-batter name at the wicket-commit frame, so no lock can
gate a read that doesn't exist.

## §4 Surviving hypothesis

**G2 — broadcast-strip render lag** is the surviving hypothesis.

Concrete claim: at the moment `apply_wicket_event` runs (frame N where
the wickets counter increments), the broadcast strip's batter slots
**structurally cannot contain the new batter's name**. The new batter
walks to the crease ~29–37 frames later; until then, every Scout read
of the strip either shows the dismissed batter (rendered residual),
junk/promo content, or a wicket-summary graphic that names the
dismissed batter but not the incoming one.

The §15 commit 8/N cascade therefore defers correctly given the
information available at frame N — but the cascade is **fire-once**.
`apply_wicket_event` does not re-invoke when new-batter information
becomes available 29–37 frames later. The mutation arm of the cascade
(`:988-1016` building a `StrikerEvent` and calling
`apply_striker_event`) never executes for any wicket on this dump.

### Why this couples G2 with G3 (architectural)

Adding a `new_batter` field to `SCOUT_PROMPT` (G3 fix) cannot recover
the primitive from a frame that does not render it. The two
hypotheses share the upstream constraint: the broadcast does not
render new-batter information at the wicket-commit frame. G3 alone is
necessary-but-not-sufficient; the load-bearing change is on the SM
side — the cascade must retry as the strip refreshes.

### Fix surface classification (per S12 dichotomy)

**Plumbing-required, not single-site.** The cascade currently lives at
`score_manager.py:880` invoked from inside `apply_wicket_event`. To
retry across frames the SM needs:

1. A pending-cascade slot (`_pending_post_wicket_cascade: WicketEvent
   | None`) populated when `_apply_post_wicket_striker_rotation`
   defers with `new_batter_unresolved`.
2. A per-frame hook (`_attempt_pending_post_wicket_cascade_drain`)
   invoked from the warm-frame entry path (sibling to the existing
   `_attempt_pending_archive_drain` at `score_manager.py:1161`)
   that:
     - reads current `self.bat1_name` / `self.bat2_name`
     - computes `arrived = {bat1, bat2} − {dismissed, prior_partner}`
     - on `len(arrived) == 1`, populates `WicketEvent.new_batter` and
       invokes `_apply_post_wicket_striker_rotation` with the saved
       event
     - clears the pending slot
3. A timeout / force-flush deadline mirroring the soft/hard cap
   pattern at `score_manager.py:1187-1241` so the slot doesn't leak
   if the broadcast never resolves a new batter (innings end,
   abandoned match).

This is the same architectural shape as the existing pending-archive
mechanism in `_attempt_pending_archive_drain` — proven safe for
2-stage deadline patterns and unblocked from S12 plumbing audit.

## §5 Next-step plan

Per §17.3 (gated on §7.2 audit), two options:

**Option A — Direct fix (preferred per the static-analysis closure).**
The conclusion is conclusive on this dump: the cascade defers because
the upstream primitive is structurally unavailable at frame N, and no
single-site relaxation of the predicate can recover it. The fix is
plumbing-required (pending-cascade slot + per-frame drain hook). Open
a `workstream_g_pending_cascade_design.md` step-2 memo with §7.2 audit
on candidate shapes:

- **Shape A** — pending slot + warm-frame hook + soft/hard deadlines
  (mirrors `_attempt_pending_archive_drain`)
- **Shape B** — re-derive on subsequent `_infer_wicket` calls
  (rejected — only fires on wickets-counter delta, won't re-trigger)
- **Shape C** — sm-frame-level cascade reconciliation in
  `_handle_warm` (broader surface, higher risk)

Predicted-flip claim (gated on next DCKKR replay after fix):

| Assertion | Pre-fix | Post-fix predicted |
|---|---|---|
| `POST-WICKET-STRIKER-CASCADE-DEFERRED` reason="new_batter_unresolved" | 2× | 0× |
| `STRIKER-EVENT-DISPATCHED` reason="wicket_new_batter" | 0× | ≥ 2× (F679, F855) |
| D-post-FoW-striker surface count (replay_diff_harness) | 20 | < 20 (target: ≤ 5) |
| C21b-symbol-revert | 1 | depends on §17.3 item 2 (cold-start re-entry) — orthogonal |

**Option B — Empirical-pressure instrumentation (consumes 1/5 budget).**
Only if the §7.2 audit on Option A surfaces an ambiguity that needs
empirical discrimination. Candidate instrumentation: log
`new_batter_resolved_at_frame` for each pending cascade, measuring
distribution of the 29–37 frame lag across more wickets in
future replays. Not required by the static evidence here.

**Recommendation: Option A.** §3.1–§3.5 produce a conclusive single-
surviving-hypothesis (G2) with a plumbing-required fix classification.
No empirical discrimination is needed to begin Shape A. The audit
budget (8/5 in this memo step) and falsification budget (0/5) both
remain on-mission.

### Coupled work (out of step-2 scope, tracked elsewhere)

- **G3 (Scout prompt extension)** — orthogonal but reinforcing. A
  `new_batter` primitive in `SCOUT_PROMPT` would let the pending-
  cascade drain hook use Scout-extracted data directly rather than
  slot-diff. Tracked as the C29b candidate in HANDOFF (Scout prompt
  schema extension); reaches the same surface from a different
  pipeline-stage.
- **Cold-start re-entry frequency root cause** — HANDOFF §17.3 item
  2 (12 COLD-START-EXIT fires in dump). Distinct from G2; can land in
  parallel. Touches the C21b-symbol-revert surface independently.

### Discipline note (Meta-finding #15 reuse)

The Meta-finding #15 pattern from §15 (Layer 1.5 catches isolated
mutation-correctness; harness diff catches cross-surface composition)
applies here: a Shape A fix's correctness will be caught by an
extended Layer 1.5 case (post-wicket cascade with new_batter arriving
N frames later) AND by the harness diff D-post-FoW-striker delta
between pre- and post-fix replays. Both should be wired before the
fix lands.
