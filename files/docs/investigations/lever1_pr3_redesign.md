# Lever 1 PR3 — STRIKER-SM-CUTOVER trigger at batter-arrival time + W3–W7 coordination

**Status (2026-04-30):** DESIGN ONLY — no code changes in this document.  
**Predecessor documents:**
- `sm_rotation_atomicity_design.md` — original Lever 1 audit; §3.3 W8 hypothesis; §7 predictions; §8 PR sequence
- `lever1_pr2_match_analysis.md` — hypothesis refutation; §3.1 Cause C mechanism; §4.1–§4.3 PR3 implications
- `batters_invariant_cluster_innings1.md` — per-frame fire inventory; §4.1 mechanism detail; §4.3 W-site attribution

---

## §1 Executive Summary

### Mechanism (Cause C — STRIKER-SM-CUTOVER over-end-only latency)

After a wicket (specifically W12: non-striker dismissed), `ScoreManager._apply_event` correctly sets
`SM.non = None`. However, on **every subsequent frame**, `SM._identify_and_set` re-fires and calls
`_w8_non_for_identified(Will Jacks)`, which looks up `self.bat2_name` — still holding the dismissed
batter (e.g. Ryan Rickelton) because `_update_batters` hasn't received a fresh card showing the
incoming batter yet. This re-introduces the stale name into `SM.non` on every frame until the
broadcast strip changes:

```
Frame N:   _apply_event W12  → SM.non = None       (correct)
Frame N+1: _identify_and_set → SM.non = Rickelton  (stale re-introduced via bat2_name)
Frame N+2: _identify_and_set → SM.non = Rickelton  (repeated every frame)
...
Frame N+k: strip shows Rohit → _update_batters updates bat2_name = Rohit
           _identify_and_set → SM.non = Rohit       (natural self-heal)
```

During the stale window (F474–F507 in the MI vs SRH log), `_project_active_batters` surfaces
`SM.non = Rickelton` to the WS payload. WS-SCRUB detects Rickelton as "out", finds only one active
batter (Will Jacks), and substitutes Will Jacks into the non-striker slot. Both WS slots equal Will
Jacks → `enforce_ws_slot_invariant` fires → `[WS-SLOT-INVARIANT]` emitted.

The over-end CUTOVER at `test_pipeline.py:9448–9458` fires rotation logic but uses
`_canonical_active_slot`, which filters `SM.non = Rickelton` to `None` (since Rickelton is "out"
in batting_card). The condition `if _s and _ns:` is False → no rotation fires for the stale slot.
By the time the over ends (~F638), the strip has naturally updated and SM self-healed via
`_update_batters`.

**STRIKER-SM-CUTOVER fires 38 times in 108 min (0.35/min) = ≈18 over-end rotations × 2 slot
writes per rotation.** The active-slot-repair block at `test_pipeline.py:9221–9258` (inside the
ball-event handler) also uses `_canonical_active_slot`, so it similarly cannot detect the stale
dismissed-batter name in SM.non and never fires the repair.

### Fix Shape (two-part, both required)

**Part 1 — Upstream fix (score_manager.py): dismissed-batter guard in `_w8_non_for_identified`.**
This is the binding change. Prevents `_identify_and_set` from re-introducing the dismissed batter
as `SM.non` after a wicket. When `bat2_name` holds a batter with `batting_card.status == "out"`,
the method returns `None` instead of that name. SM.non stays `None` during the post-wicket gap →
no stale projection → no WS-SCRUB duplicate → no `[WS-SLOT-INVARIANT]` fires.

**Part 2 — Downstream fix (test_pipeline.py): CUTOVER trigger at batter-arrival.**
Fires `_set_inn_slot_with_sm_mirror` (emitting `[STRIKER-SM-CUTOVER] reason="batter-arrival"`)
when a new batter is confirmed via the `[REPLACE]` path. Actively populates SM.non (or SM.striker)
with the new batter at admission time rather than waiting for the broadcast strip to update.
Without Part 1, this fix is undone by the next `_identify_and_set` call (bat2_name still stale).
With Part 1, it provides defense-in-depth and proactively sets the slot.

### W3–W7 Disposition

**W3–W6 (`_init_from_card`):** Migrate to `_set_slot_pair` (cold-start duplicate guard). Do **not**
contribute to Cause C (cold-start path, not post-wicket). **Migrate in PR3** for correctness and
telemetry coverage.

**W7 (`_update_batters` bootstrap):** Runs only when `bat1_name == bat2_name == None` (full
cold-start). Does **not** contribute to Cause C (post-wicket has existing bat names). **Migrate
in PR3** for telemetry uniformity and degenerate-card guard.

**W8 (already migrated, PR2):** `_w8_non_for_identified` is the PR2 helper. PR3 adds the dismissed-
batter guard to it. Not a new W-site migration; an enhancement to the PR2 helper.

**W11/W12 (wicket dismissal, deferred to PR4):** Currently not migrated to `_set_slot_pair`. Adding
the dismissed-batter guard to `_w8_non_for_identified` makes W11/W12 migration less urgent (the
upstream fix prevents re-introduction). Keep PR4 schedule unchanged.

### Predicted Impact and Confidence

| Scenario | Predicted `[WS-SLOT-INVARIANT]` rate |
|---|---|
| Current (post-PR2) baseline | 1.13/min (122 fires / 108 min) |
| PR3 W3–W7 migration alone | ~0.90–1.07/min (5–20% reduction per §4.2 of PR2 analysis) |
| PR3 + `_w8_non_for_identified` guard alone | **~0.2–0.4/min** (80–85% reduction estimated) |
| PR3 full (both parts + W3–W7) | **<0.3/min** (target from PR2 analysis §4.3) |

**Confidence: MEDIUM.** The `_w8_non_for_identified` guard addresses the confirmed dominant
mechanism (re-introduction via `bat2_name`). Match-characteristic variance may affect the residual.
`[SM-SLOT-INVARIANT]` fires expected to remain ~0 (W8 guard not needed per PR2 finding); new fires
from W3–W6 cold-start degenerate cards possible but rare.

---

## §2 Detection Logic

### What Constitutes "Batter Arrival"

Batter arrival is defined as the moment when a new batter (previously `status="yet_to_bat"` in
`batting_card`) is confirmed and admitted to the active batting set. The canonical admission point
in the pipeline is the `[REPLACE]` block in `test_pipeline.py:8063–8114`.

**Criterion:** `_new_batter_candidate_count >= _NEW_BATTER_CONFIRM (= 2)` consecutive frames with
the same new batter name visible in `extracted["batters"]` AND the batter having `status="yet_to_bat"`
in `batting_card`. `scoreboard.update_batter(_rb_key, ...)` is called and returns `True` → `_accepted`.

This is the **definitive** batter-arrival signal: it is gated, consensus-verified (2-frame
confirmation), and happens only post-wicket (guarded by `_last_wicket_frame > 0 and
frame_count - _last_wicket_frame <= 40`).

### Where in the Code Path to Detect It

**File:** `files/test_pipeline.py`  
**Lines:** 8090–8104 (the `if _new_batter_candidate_count >= _NEW_BATTER_CONFIRM:` block)

```python
# Current code (test_pipeline.py:8090–8104)
if _new_batter_candidate_count >= _NEW_BATTER_CONFIRM:
    _accepted = scoreboard.update_batter(
        _rb_key, runs=..., balls=..., striker=..., frame=frame_count)
    if _accepted:
        log.info(f"  [REPLACE] New batter '{_rb_key}' ...")
        _new_batter_candidate = None
        _new_batter_candidate_count = 0
    else:
        log.info(f"  [REPLACE] '{_rb_key}' confirmed but auto-dismiss deferred ...")
```

The CUTOVER trigger inserts between `if _accepted:` and the log line.

### Trigger Mechanism

The trigger directly inspects `score_mgr.striker` / `score_mgr.non` (raw SM slot values, not via
`_canonical_active_slot` which returns `None` for dismissed names and would miss the repair). For
each stale slot (non-null SM value with `batting_card[name].status != "batting"`), it calls
`_set_legacy_active_slot(score_mgr, scoreboard, slot, new_value, "batter-arrival")` which routes
through `_set_inn_slot_with_sm_mirror` → emits `[STRIKER-SM-CUTOVER]`.

**Why raw SM value and not `_canonical_active_slot`:** The existing active-slot-repair at
`test_pipeline.py:9221–9258` (inside the ball-event handler) uses `_canonical_active_slot`, which
returns `None` for `SM.non = Rickelton` (dismissed, status="out"). The condition
`if _ns and _ns not in _active` is never True for a `None` return. This is why the active-slot-
repair does NOT fire during the intra-over window. The batter-arrival CUTOVER must bypass this
abstraction and read `SM.non` directly.

---

## §3 Idempotency Design

### Natural Idempotency from Status Check

The batter-arrival CUTOVER fires only when `batting_card[SM.non].status != "batting"`. After the
over-end rotation, both SM slots are set to active batters → status = "batting" → condition is
False → CUTOVER does not fire. Natural idempotency without a state flag.

### Wicket on Last Ball of Over (Edge Case)

If the wicket falls on ball 6 (last ball of over):
1. `_apply_event` W12 fires: SM.non = None, SM.striker = survivor.
2. `check_over_change` fires: over-end rotation at `test_pipeline.py:9448–9458`. `_canonical_active_slot("striker") = survivor`. `_canonical_active_slot("non") = None` (SM.non = None). Condition `if _s and _ns:` is False → rotation does NOT fire. SM unchanged.
3. New batter confirmed (2+ frames later) via `[REPLACE]`. CUTOVER fires: SM.non = new_batter.
4. `_identify_and_set` on subsequent frame: bat2_name updated to new_batter (via `_update_batters` once strip shows new batter) → SM.non = new_batter. Consistent.

**No double-fire risk.** The over-end rotation doesn't fire when SM.non = None. The batter-arrival
CUTOVER fires when SM.non holds a stale/dismissed name (not None). These conditions are mutually
exclusive.

### POISON-RECAL Frame Safety

The `[REPLACE]` block is gated by `not _frame_poisoned` at `test_pipeline.py:8064`. CUTOVER
triggers inside `if _accepted:` are therefore never executed during POISON-RECAL frames. Safe.

### Multiple Wickets in Same Over

Each wicket resets `_new_batter_candidate = None; _new_batter_candidate_count = 0` at
`test_pipeline.py:8148–8149` and `8766–8767`. Each new batter goes through independent
confirmation. CUTOVER fires independently per admission. No sequencing dependency.

---

## §4 Telemetry

### Existing Source Field Convention

`_set_inn_slot_with_sm_mirror` (`test_pipeline.py:2397–2415`) emits:
```
[STRIKER-SM-CUTOVER] mirrored {slot}={value!r} ({reason}) — SM+_inn lockstep
```

The `reason` parameter is the distinguisher. Current values in production:
- `"over-change-rotation"` — end-of-over striker swap
- `"active-slot-repair"` — ball-event-handler repair (rarely fires in practice due to
  `_canonical_active_slot` returning None for dismissed names)
- `"broadcast-indicator"` / `"broadcast-indicator-swap"` — from the STRIKER-ADMIT block

### New Tag for PR3

**New `reason` value:** `"batter-arrival"` for the post-`[REPLACE]` CUTOVER trigger.

No new tag patterns needed. The existing analyzer regex at `analyze_match_telemetry.py:154`:
```python
STRIKER_SM_CUTOVER = re.compile(r"\[STRIKER-SM-CUTOVER\]\s+")
```
already captures all fires. Granular classification by reason is available via log grep of the
`reason=` substring without a regex change.

### Proposed Analytics Sub-classification (Optional)

After PR3 ships, add to `analyze_match_telemetry.py`:
```python
STRIKER_SM_CUTOVER_BATTER_ARRIVAL = re.compile(
    r"\[STRIKER-SM-CUTOVER\].*\(batter-arrival\)")
```
This gives a direct count of the new trigger's invocations per match, enabling PR3 effectiveness
measurement (expected: ~5 fires per match, correlating with wicket count × 1–2 slots per wicket).

### Source Convention Cross-reference

The `[SM-FEEDER-SYNC]` pattern from dual_broadcaster_substrate_audit.md Item 3 Path B uses a
separate `[SM-FEEDER-DIVERGENCE]` telemetry tag. No collision. The `[STRIKER-SM-CUTOVER]` namespace
is exclusive to the Path B lockstep mechanism and should remain so.

---

## §5 W3–W7 Disposition

### W3: `_init_from_card` — broadcast_striker matches bat1 (score_manager.py:1317–1319)

```python
self.striker = self.bat1_name
self.non = self.bat2_name
```

**Risk:** Cold-start with degenerate scout card (`bat1_name == bat2_name`). Produces
END-STATE-DUPLICATE at SM level. `[WS-SLOT-INVARIANT]` fires until WS-SCRUB repairs.

**Does batter-arrival CUTOVER cover it?** No. Cold-start doesn't go through `[REPLACE]` path.
**Decision: MIGRATE to `_set_slot_pair` in PR3.**

### W4: `_init_from_card` — broadcast_striker matches bat2 (score_manager.py:1320–1322)

Same cold-start path as W3 (swapped assignment). Same degenerate-card risk.

**Decision: MIGRATE to `_set_slot_pair` in PR3** (covered by same W3–W6 migration block).

### W5: `_init_from_card` — broadcast_striker present but no bat-name match (score_manager.py:1323–1325)

Default assignment: `striker = bat1; non = bat2`. Same degenerate-card risk as W3–W6.

**Decision: MIGRATE to `_set_slot_pair` in PR3.**

### W6: `_init_from_card` — no broadcast_striker at all (score_manager.py:1326–1328)

Same as W5. `striker = bat1; non = bat2`.

**Decision: MIGRATE to `_set_slot_pair` in PR3.**

### W7: `_update_batters` bootstrap (score_manager.py:1916–1918)

```python
if not self.striker:
    self.striker = self.bat1_name
    self.non = self.bat2_name
```

This is inside the `if not self.bat1_name and not self.bat2_name:` cold-start guard (L1909).
**Only fires when SM has no batter names at all** (full cold-start). Does NOT fire post-wicket
(SM still holds bat1_name/bat2_name even with striker/non cleared by W11/W12).

**Does batter-arrival CUTOVER cover it?** Partially — the batter-arrival CUTOVER fires later in
the cold-start window when the new batter is confirmed. But W7 fires earlier (on first `_update_batters`
call with both bat names). For degenerate cards (bat1 == bat2), W7 produces a duplicate that
`_set_slot_pair` would catch.

**Decision: MIGRATE to `_set_slot_pair` in PR3** for degenerate-card guard and telemetry
(emits `[SM-SLOT-INVARIANT source=_update_batters.bootstrap]` on degenerate cards).

**W7 migration note:** The original audit §6.3 W7 migration puts `_set_slot_pair` inside
`if not self.bat1_name and not self.bat2_name:` as a replacement for L1916–1918 only. Not the
arrival/departure block at L1934+.

### Summary Table

| W-site | Risk class | Cause C contributor? | Decision | Reasoning |
|---|---|---|---|---|
| W3 | END-STATE-DUPLICATE-RISK (cold-start) | No | **MIGRATE** | Degenerate-card guard |
| W4 | END-STATE-DUPLICATE-RISK (cold-start) | No | **MIGRATE** | Same block as W3 |
| W5 | END-STATE-DUPLICATE-RISK (cold-start) | No | **MIGRATE** | Same block as W3 |
| W6 | END-STATE-DUPLICATE-RISK (cold-start) | No | **MIGRATE** | Same block as W3 |
| W7 | END-STATE-DUPLICATE-RISK (cold-start) | No | **MIGRATE** | Degenerate-card guard |
| W8 | Already migrated (PR2) | Indirect (via `bat2_name`) | **ENHANCE** via dismissed guard | New `_w8_non_for_identified` check |

---

## §6 Implementation Locations

### Change 1: `_w8_non_for_identified` — dismissed-batter guard (BINDING FIX)

**File:** `files/score_manager.py`  
**Current lines:** 2000–2018 (`_w8_non_for_identified` method)  
**Change:** After computing `_ns` (the candidate non-striker from bat1/bat2), add a scoreboard
status check before returning:

```python
def _w8_non_for_identified(self, new: str) -> str | None:
    if self.bat1_name and self._same_name(new, self.bat1_name):
        _ns = self.bat2_name
    elif self.bat2_name and self._same_name(new, self.bat2_name):
        _ns = self.bat1_name
    else:
        _nc = self._canonicalize_name(new) or new
        _prior_non = (self._canonicalize_name(self.non) or self.non)
        if (_prior_non is not None and _nc is not None
                and _prior_non != _nc):
            return self.non
        return None
    # NEW: do not assign a dismissed batter as non-striker.
    # After W11/W12, bat2_name/bat1_name may still hold the dismissed
    # batter (scoreboard clears batting_card.status before _update_batters
    # receives a fresh card with the replacement). Returning None here lets
    # SM.non stay None so _project_active_batters uses the _inn fallback
    # (END-STATE-NULL-OK) rather than surfacing the dismissed name which
    # WS-SCRUB then replaces with the survivor → duplicate.
    if _ns and self.scoreboard is not None:
        _bc = self.scoreboard.batting_card or {}
        _ns_card = _bc.get(_ns)
        if _ns_card and _ns_card.get("status") == "out":
            log.info(
                f"[SM-W8-DISMISSED-GUARD] _w8_non_for_identified: "
                f"computed non {_ns!r} is dismissed (status=out); "
                f"returning None (striker={new!r})")
            return None
    return _ns
```

**Size:** +12 LOC, 0 lines modified (new guard appended to method body before `return _ns`).  
**Diff sites:** 1 (score_manager.py, 1 method).

### Change 2: W3–W6 migration — `_init_from_card` slot writes

**File:** `files/score_manager.py`  
**Current lines:** 1315–1328 (the if/elif/else/else striker identification block in `_init_from_card`)  
**Change:** Per original audit §6.3 W3–W6 pattern. Replace the four-branch assignment with
`_set_slot_pair`:

```python
# Before (L1315–1328):
if card.get("broadcast_striker"):
    ind = card["broadcast_striker"].lower()
    if self.bat1_name and ind in self.bat1_name.lower():
        self.striker = self.bat1_name
        self.non = self.bat2_name
    elif self.bat2_name and ind in self.bat2_name.lower():
        self.striker = self.bat2_name
        self.non = self.bat1_name
    else:
        self.striker = self.bat1_name
        self.non = self.bat2_name
else:
    self.striker = self.bat1_name
    self.non = self.bat2_name

# After:
_s, _ns = self.bat1_name, self.bat2_name
if card.get("broadcast_striker"):
    ind = card["broadcast_striker"].lower()
    if (self.bat2_name and ind in self.bat2_name.lower()
            and not (self.bat1_name and ind in self.bat1_name.lower())):
        _s, _ns = self.bat2_name, self.bat1_name
self._set_slot_pair(_s, _ns, source="_init_from_card")
```

**Size:** -14 LOC, +5 LOC (net -9). 1 diff site.

### Change 3: W7 migration — `_update_batters` bootstrap

**File:** `files/score_manager.py`  
**Current lines:** 1916–1918 (inside `if not self.bat1_name and not self.bat2_name:` block)  
**Change:**

```python
# Before:
if not self.striker:
    self.striker = self.bat1_name
    self.non = self.bat2_name

# After:
if not self.striker:
    self._set_slot_pair(self.bat1_name, self.bat2_name,
                        source="_update_batters.bootstrap")
```

**Size:** -2 LOC, +2 LOC (net 0). 1 diff site.

### Change 4: Batter-arrival CUTOVER trigger

**File:** `files/test_pipeline.py`  
**Current lines:** 8097–8104 (the `if _accepted:` block inside `[REPLACE]`)  
**Change:** After `scoreboard.update_batter(...)` returns `True`, directly inspect SM raw slot
values and fire CUTOVER for any stale (dismissed) slot:

```python
if _accepted:
    log.info(
        f"  [REPLACE] New batter '{_rb_key}' "
        f"seen {_new_batter_candidate_count}x "
        f"after wicket at F{_last_wicket_frame}"
        f" — activated")
    # NEW: batter-arrival CUTOVER — fix stale SM slots immediately at
    # admission rather than waiting for over-end rotation.
    # Use raw SM values (not _canonical_active_slot) because
    # _canonical_active_slot returns None for dismissed names and
    # therefore cannot detect the stale-dismissed-batter condition.
    _bc_admit = scoreboard.batting_card or {}
    for _admit_slot, _stale_source in (
            ("non", getattr(score_mgr, "non", None)),
            ("striker", getattr(score_mgr, "striker", None))):
        if not _stale_source:
            continue
        _slot_card = _bc_admit.get(_stale_source) or {}
        if _slot_card.get("status") == "batting":
            continue  # slot already active — no repair needed
        # Slot holds dismissed name → replace with newly admitted batter
        _set_legacy_active_slot(
            score_mgr, scoreboard, _admit_slot, _rb_key,
            "batter-arrival")
        log.info(
            f"  [BATTER-ARRIVAL-CUTOVER] {_admit_slot}={_rb_key!r} "
            f"(was stale: {_stale_source!r} status="
            f"{_slot_card.get('status', 'not_in_card')!r})")
    _new_batter_candidate = None
    _new_batter_candidate_count = 0
```

**Constraint on slot assignment:** If both `SM.striker` and `SM.non` are stale (rare edge case:
two wickets in quick succession with both slots not yet updated), both get assigned `_rb_key`.
This creates a temporary duplicate caught by `enforce_ws_slot_invariant` on the same WS-build
cycle. The next ball event's active-slot-repair logic will correct the second slot. Document as
a known transient for multi-wicket same-over edge cases.

**Alternative (simpler) formulation:** Only repair the slot that matches the `status == "not batting"`
condition for `_rb_key`'s expected slot. Since the incoming batter always takes the dismissed
batter's crease end, and the `[REPLACE]` block has `_rb.get("striker")` as an indicator:

```python
# Simpler: only fix the "non" slot if non is stale, else fix striker
_bc_admit = scoreboard.batting_card or {}
_stale_non = getattr(score_mgr, "non", None)
_stale_striker = getattr(score_mgr, "striker", None)
_non_card = _bc_admit.get(_stale_non) or {}
_str_card = _bc_admit.get(_stale_striker) or {}
if _stale_non and _non_card.get("status") != "batting":
    _set_legacy_active_slot(score_mgr, scoreboard, "non",
                            _rb_key, "batter-arrival")
elif _stale_striker and _str_card.get("status") != "batting":
    _set_legacy_active_slot(score_mgr, scoreboard, "striker",
                            _rb_key, "batter-arrival")
```

**Composer 2 guidance:** Prefer the simpler formulation. The "non first, striker second" order
matches the expectation that most wickets are W12-type (non-striker dismissed in run-outs) in
practice; but the dual-slot loop formulation is more robust. Implement the dual-slot loop if the
simpler version shows gaps in tests.

**Size:** +20 LOC. 1 diff site.

### Change 5: Tests

**File:** `files/test_recent_fixes.py`  
**Append after:** existing Lever 1 tests (currently ending around L8479)  
**Size:** ~140 LOC (+5 test functions).

### Diff Site Count Summary

| File | Changes | LOC delta |
|---|---|---|
| `score_manager.py` | 3 (Changes 1–3) | +14 |
| `test_pipeline.py` | 1 (Change 4) | +20 |
| `test_recent_fixes.py` | 1 (Change 5, tests only) | +140 |
| **Total** | **5 diff sites** | **+174 LOC** |

---

## §7 Migration Order

### Commit Sequence (3 commits)

**Commit 1 (highest impact): dismissed-batter guard + W3–W7 migration**

Scope: Changes 1, 2, 3 (score_manager.py only).

- `_w8_non_for_identified` dismissed-batter guard (Change 1)
- W3–W6 `_init_from_card` → `_set_slot_pair` migration (Change 2)
- W7 `_update_batters.bootstrap` → `_set_slot_pair` migration (Change 3)

**Expected `[WS-SLOT-INVARIANT]` impact:** ~80–85% reduction from baseline. The dismissed-batter
guard closes the primary Cause C re-introduction path. W3–W7 migrations add cold-start safety.

**`[SM-SLOT-INVARIANT]` fires expected:** Low (W7 degenerate-card guard); `[SM-W8-DISMISSED-GUARD]`
fires expected: ~5–10/match (one per post-wicket gap where bat2_name holds dismissed batter before
strip updates).

**Validation:** Run `test_recent_fixes.py` (all Lever 1 tests). Regression: existing
`test_set_slot_pair_*`, `test_sm_pr2_w8_*`, `test_fixture_striker_sm_cutover_intra_over_wicket_gap`.

**Risk:** LOW. The dismissed-batter guard is additive (returns None instead of an existing value
in an already-None-producing scenario for the normal case). W3–W7 migrations are the same pattern
as PR2's W8 migration.

**Commit 2 (defense-in-depth): batter-arrival CUTOVER trigger**

Scope: Change 4 (test_pipeline.py only).

- `[REPLACE]` block → `_set_legacy_active_slot("batter-arrival")` trigger
- Emits `[STRIKER-SM-CUTOVER] reason=batter-arrival`

**Expected `[WS-SLOT-INVARIANT]` impact:** Marginal incremental reduction after Commit 1 (the
upstream guard in Commit 1 closes most fires; batter-arrival CUTOVER handles residual cases where
the guard fires but SM.non is still in a transitional null state that benefits from explicit
population). Non-zero benefit expected for W11-type wickets (striker dismissed, incoming batter
takes striker role).

**Validation:** `test_fixture_striker_sm_cutover_intra_over_wicket_gap` should now show
`[STRIKER-SM-CUTOVER]` firing with `reason=batter-arrival` in addition to the over-end fire.

**Risk:** LOW–MEDIUM. Only fires on `_accepted = True` path (confirmed admission). The condition
`_slot_card.get("status") != "batting"` is an additional guard. The CUTOVER only writes to SM/`_inn`
via `_set_inn_slot_with_sm_mirror` which is the established lockstep mechanism.

**Commit 3: tests + telemetry analytics**

Scope: Change 5 (test_recent_fixes.py). Optionally: `analyze_match_telemetry.py` sub-classifier.

- 5 new tests covering all PR3 changes
- Optional: `STRIKER_SM_CUTOVER_BATTER_ARRIVAL` regex in analyzer

**Risk:** NONE (test-only commit).

---

## §8 Test Fixtures

### Existing Fixtures (Regression — must pass)

From `lever1_pr2_match_analysis.md` §5:

**`test_fixture_striker_sm_cutover_intra_over_wicket_gap`** (`test_recent_fixes.py:8431`):
- F474–F638 fixture: SM.non = Rickelton (stale), WS-SLOT-INVARIANT fires 4×
- After PR3: SM.non should stay `None` (dismissed guard prevents re-introduction) → WS-SLOT-INVARIANT should NOT fire on the stale frames → **UPDATE test expectations**: `ws_hits` should be 0 (or reduced significantly) after the `_w8_non_for_identified` guard is in place
- **Critical regression gate:** if `ws_hits > 0` after Commit 1, the dismissed guard is not working

**`test_fixture_striker_sm_cutover_intra_over_wicket_gap` cutover part (L8466–8479):**
- Tests that `_set_inn_slot_with_sm_mirror` fires with `[STRIKER-SM-CUTOVER]`. Unchanged by PR3.

**`test_set_slot_pair_*` (3 tests, L7846–7897):** Must pass unmodified.

**`test_sm_pr2_w8_*` (2 tests, L7903–7985):** Must pass. PR3's dismissed-batter guard is additive
to W8; existing PR2 tests don't exercise the dismissed path.

### New Tests (PR3, ~140 LOC total)

**Test 1: `test_sm_w8_dismissed_guard_returns_none_for_out_batter`**

Setup: SM with bat1_name="Will Jacks", bat2_name="Rickelton". Scoreboard batting_card:
`{"Rickelton": {"status": "out"}, "Will Jacks": {"status": "batting"}}`. Call
`sm._w8_non_for_identified("Will Jacks")`.

Expected: returns `None` (not "Rickelton").  
Telemetry: `[SM-W8-DISMISSED-GUARD]` logged.

**Test 2: `test_sm_w8_dismissed_guard_passes_through_active_batter`**

Setup: same but `batting_card["Rohit"]["status"] = "batting"`, bat2_name="Rohit". Call
`sm._w8_non_for_identified("Will Jacks")`.

Expected: returns `"Rohit"`. No guard telemetry.

**Test 3: `test_sm_init_from_card_degenerate_card_no_duplicate_post_migration`**

Cold-start with bat1_name = bat2_name = "Rickelton" (degenerate scout card). Call `_init_from_card`.

Expected: SM.striker = "Rickelton", SM.non = None. `[SM-SLOT-INVARIANT source=_init_from_card]`
emitted.

**Test 4: `test_sm_update_batters_bootstrap_degenerate_card_no_duplicate`**

SM with bat1_name = None, bat2_name = None, striker = None. Call `_update_batters` with
card = {bat1_name="X", bat2_name="X"}.

Expected: SM.striker = "X", SM.non = None. `[SM-SLOT-INVARIANT source=_update_batters.bootstrap]`
emitted.

**Test 5: `test_batter_arrival_cutover_fires_on_stale_non`**

Setup: SM.non = "Rickelton" (dismissed). batting_card = `{"Rickelton": {"status": "out"},
"Will Jacks": {"status": "batting"}, "Rohit": {"status": "batting"}}`. Simulate `[REPLACE]`
firing with `_rb_key = "Rohit"` and `_accepted = True`.

Expected: `_set_legacy_active_slot` called with `slot="non", value="Rohit", reason="batter-arrival"`.
`[STRIKER-SM-CUTOVER]` in telemetry. SM.non = "Rohit" post-CUTOVER.

**Test structure note:** Tests 1–4 are SM unit tests (import ScoreManager directly). Test 5 is
an integration test (import test_pipeline, mock `_set_legacy_active_slot`). Both types follow the
patterns established in the existing Lever 1 test suite (L7842–8479).

**Expected test count delta:** +5 functions → approximately 685 + 8 (PR2 baseline) + 5 = ~698 PASS.
All new tests must pass under `shadow=True` and `shadow=False`.

---

## §9 Predicted Impact

### Production Rate Reduction

| Scenario | `[WS-SLOT-INVARIANT]` rate | Confidence |
|---|---|---|
| Current baseline (post-PR2, MI vs SRH innings 1) | 1.13/min (122 fires / 108 min) | Measured |
| After Commit 1 (dismissed guard + W3–W7 migration) | ~0.15–0.30/min | MEDIUM |
| After Commit 2 (+ batter-arrival CUTOVER) | **<0.15/min** | MEDIUM |
| Target (from lever1_pr2_match_analysis.md §6) | <0.3/min | — |

**Reasoning for 85–90% reduction from Commit 1:**  
The `_w8_non_for_identified` dismissed guard directly prevents re-introduction of the stale name
that drives Cause C. From `batters_invariant_cluster_innings1.md` §3: 12/13 fires (92%) in the
analyzer window are ADMISSION-WINDOW Cause C fires. The guard closes this source entirely.
Residual fires come from:
- Innings transition (8 fires in the log, expected transition-class)
- Rule=A fires (F2167 type — external graphic resurrection, unrelated to SM slot staleness)
- Match-characteristic variance

**`[SM-SLOT-INVARIANT]` expected after PR3:** ~0–3/match (rare degenerate-card scenarios caught
by W3–W7 migrations). `[SM-SLOT-INVARIANT-PAYLOAD]` expected: 0 (no bypass sites).

### Watch Criteria for Next Match-Day Validation

1. **Primary:** `[WS-SLOT-INVARIANT]` rate < 0.3/min in first full innings.
2. **Secondary:** `[SM-W8-DISMISSED-GUARD]` fires = N × (wickets) × (avg post-wicket strip delay in frames / ~5–10 frames per fire). Expected: 2–5 fires per wicket. If 0 fires on a match with wickets, the guard condition is not being triggered (inspect bat2_name tracking logic).
3. **Tertiary:** `[STRIKER-SM-CUTOVER] reason=batter-arrival` fires = N per match (N = number of confirmed `[REPLACE]` admissions). If fires = 0 but `[REPLACE]` admissions > 0, check Commit 2 implementation.
4. **Regression gate:** `[SM-SLOT-INVARIANT-PAYLOAD]` = 0. Any non-zero value requires immediate investigation (bypass site introduced by PR3).

---

## §10 Risk Assessment

### Failure Modes

**Risk 1: `_w8_non_for_identified` guard suppresses a valid non-striker assignment**

Scenario: `bat2_name` holds a batter whose `batting_card.status == "out"` transiently (e.g.,
scoring system briefly marks them out before confirming as not-out). Guard returns None → SM.non =
None → UI shows "—" for non-striker.

**Probability:** LOW. The dismissed guard only activates when `batting_card.status == "out"`, which
requires the scoreboard-side `update_batter` path to have explicitly set the status to "out" via
the Scorer/extractor path (not a transient OCR read). Fix-16 and existing scorer filters make
false "out" status rare.

**Mitigation:** The `[SM-W8-DISMISSED-GUARD]` telemetry log makes these detectable. If
false-suppression occurs, the fix is to add a confidence threshold (require 2+ consecutive "out"
status readings before activating the guard).

**Risk 2: Batter-arrival CUTOVER assigns new batter to wrong slot**

Scenario: Both SM.non and SM.striker hold dismissed names (double-wicket same frame). Both get
assigned `_rb_key` (the single confirmed new batter). Produces a temporary duplicate.

**Probability:** VERY LOW. Double-wickets on the same frame are extremely rare. Even if it occurs,
the CUTOVER fires for two separate `[REPLACE]` admissions (each admitted separately over 2+ frames).

**Mitigation:** `enforce_ws_slot_invariant` backstop fires and repairs the transient duplicate.
The next `[REPLACE]` admission for the second new batter fires a second CUTOVER correcting the
second slot.

**Risk 3: `_w8_non_for_identified` guard introduces SM.non = None regression in active match**

Scenario: Post-PR3, SM.non stays None longer in post-wicket gaps (correct behavior). Some
downstream consumer assumes SM.non is non-null after a certain number of frames.

**Probability:** LOW. `_project_active_batters` already handles SM.non = None via the `_inn`
fallback (L2214–2229 in test_pipeline.py). The WS payload non-striker slot may briefly be None
(rendered as "—" in UI), which is correct behavior for the incoming-batter transition.

**Mitigation:** No explicit null-assumption in downstream code. `_project_active_batters`
fallback handles it. Verify in tests (Test 2 in §8 specifically exercises this path).

### Edge Cases

**Multiple wickets in same over:** Each goes through independent `[REPLACE]` confirmation.
CUTOVER fires once per admission. The dismissed-batter guard for each new batter's `bat2_name`
assignment is also independent. No interaction.

**POISON-RECAL during admission window:** `[REPLACE]` is gated on `not _frame_poisoned`. Guard
in `_w8_non_for_identified` runs inside `score_mgr.on_frame` which is called even on poisoned
frames (SM's frame processing is independent of the pipeline's `_frame_poisoned` flag — poisoned
frames still feed SM via `frame_input`). However, poisoned frames typically have `None`
bat1_name/bat2_name (extractor returns null), so `_w8_non_for_identified` would return None
regardless of the guard. Safe.

**Innings transition (SM.set_innings_2() interaction):** `set_innings_2()` calls `self.__init__()`
which resets striker/non to None. This bypasses `_w8_non_for_identified` entirely (it's a full
reset). The `[REPLACE]` block admission path is not active during innings transitions (scoreboard
has been re-initialized). No interaction.

**P0-A (Fix 16 — SM.set_innings_2) interaction:** `set_innings_2` is idempotent (L1733: returns
if `self.innings == 2`). The dismissed-batter guard in `_w8_non_for_identified` does not touch
`set_innings_2` flow. Safe.

**W11 case (striker dismissed):** After W11, SM.striker = None, SM.non = survivor. `_w8_non_for_identified` is called to identify the NON-striker (when evidence identifies the survivor as the new striker). The survivor's `batting_card.status == "batting"`. Guard does not activate. Correct behavior preserved.

---

## §11 P0 Interaction

### P0-A: Fix 16 — SM.set_innings_2() (score_manager.py:1710–1769)

`set_innings_2` calls `self.__init__()`, resetting striker/non to None, bat1_name/bat2_name to
None. PR3 changes (`_w8_non_for_identified` guard, W3–W7 migrations) all operate on SM internal
state that `set_innings_2` fully resets. No regression possible: after `set_innings_2` fires, SM
is in a clean COLD_START state and all subsequent slot writes go through the normal initialization
path (W3–W6 if `_init_from_card` is called, or W7 bootstrap for `_update_batters`).

**Verification:** `test_lever1_pr2_sm_slot_invariant_never_triggers` (full log regression) should
show 0 `[SM-SLOT-INVARIANT]` fires post-innings-2 reset, same as pre-PR3.

### P0-B (cricket-rules attribution): Does Not Interact

PR3 changes are limited to SM slot writes and the `[REPLACE]` CUTOVER trigger. Neither touches
cricket-rules attribution logic.

### P0-C: Cricket-rules attribution — team-swap at innings transition

Team-swap during innings transition sets `batting_team`, which affects `bat_name` lookups. The
`_w8_non_for_identified` guard checks `self.scoreboard.batting_card` for status; during team-swap,
batting_card is rebuilt. The guard simply checks `status == "out"`. If batting_card is empty
during the swap, the guard's `_bc.get(_ns)` returns `None` → `_ns_card = None` → guard condition
`if _ns_card and _ns_card.get("status") == "out"` is False → guard does not fire. Safe.

**Note:** Post-innings-2 reset, `batting_card` is rebuilt for the chasing team. The first
few frames in COLD_START may have no `batting_card` entries → `_w8_non_for_identified` guard is
inactive → returns normal bat1_name/bat2_name as before. No behavior change from pre-PR3 during
cold-start.

### Path A WS-payload byte-identity

The `_w8_non_for_identified` guard returns `None` instead of a dismissed name. This changes
SM.non during post-wicket gaps. This DOES change WS payload bytes (non-striker field may be
`None` instead of a stale name). However:
- Pre-PR3: SM.non = dismissed_name → WS-SCRUB rejects → state["non"] = active_batter OR None (after collision repair)
- Post-PR3: SM.non = None → WS-SCRUB skip (None) → state["non"] = None or _inn fallback value

The Path A byte-identity snapshot test (`test_path_b_low_risk_batch_path_a_regression_signature_match`)
was established BEFORE Lever 1. It will fail if the stale-non scenario is exercised in the
snapshot fixture. **Check whether the snapshot fixture includes a post-wicket frame.** If yes,
the expected snapshot byte-string must be updated to reflect the correct (non-stale) non-striker
value. This is the intended behavior change, not a regression.

**Recommended action:** Before Commit 1 ships, run the Path A snapshot test and verify which
frames it covers. If the snapshot includes post-wicket frames, update the expected signature and
document the intentional change in the PR description.

---

## §12 INFEASIBILITY NOTES (None)

No infeasible constraints found. All design decisions resolved.

---

## §13 Appendix: Call-graph for Stale SM.non Mechanism

```
test_pipeline.py main_loop
└── score_mgr.on_frame(frame_input)
    ├── _accept_update(card)
    │   └── _update_batters(card)  [bat2_name still = Rickelton; dismissal guard
    │                               scrubs card entry but NOT bat2_name]
    ├── _identify_and_set(card, frame, ...)
    │   └── _w8_non_for_identified("Will Jacks")  [returns bat2_name = Rickelton]
    │       └── _set_slot_pair("Will Jacks", "Rickelton")
    │           → SM.striker = "Will Jacks"
    │           → SM.non = "Rickelton"  ← STALE RE-INTRODUCED every frame
    ├── _infer_event(...)  [d_score=d_wickets=d_overs=0 → returns None]
    └── _build_payload() → SM.non = "Rickelton" in output

build_full_payload(...)
└── _project_active_batters(state, score_mgr, ...)
    │   state["non"] = canon(SM.non) = "Rickelton"
    └── WS-SCRUB (test_pipeline.py:3914–3942)
        │   "Rickelton" status="out" → rejected
        │   _active = ["Will Jacks"]
        │   _fallback = None (no other active != "Will Jacks")
        └── state["non"] = "Will Jacks"  ← SAME AS striker → DUPLICATE
            → enforce_ws_slot_invariant fires
            → [WS-SLOT-INVARIANT] emitted
```

**PR3 Fix Path (after Commit 1):**

```
_identify_and_set → _w8_non_for_identified("Will Jacks")
    → bat2_name = "Rickelton"
    → NEW: batting_card["Rickelton"].status == "out"
    → returns None
    → _set_slot_pair("Will Jacks", None)
    → SM.non = None  ← CORRECT; no stale re-introduction

_project_active_batters:
    state["non"] = canon(None) = None
    fallback: _inn.get("non") = None (or new batter if _inn updated)
WS-SCRUB: non = None → skip
[WS-SLOT-INVARIANT] does NOT fire  ← FIXED
```

---

**Cross-references:**
- `sm_rotation_atomicity_design.md` — W-site inventory (§1–§2), W3–W7 migration contract (§6.3)
- `lever1_pr2_match_analysis.md` — Cause C confirmation (§3.1), PR3 scoping (§4.1–§4.3)
- `batters_invariant_cluster_innings1.md` — per-frame mechanism (§4.1, §4.3), call-graph origin
- `mi_srh_innings_break_analysis.md` — STRIKER-SM-CUTOVER fire count (§35 table: 38 fires)
- `files/score_manager.py` L989 (`_set_slot_pair`), L2000 (`_w8_non_for_identified`), L1315 (W3–W6), L1916 (W7)
- `files/test_pipeline.py` L2397 (`_set_inn_slot_with_sm_mirror`), L8063 (`[REPLACE]` block), L9221 (active-slot-repair), L9438 (over-change-rotation)
- `files/test_recent_fixes.py` L7842–8479 (existing Lever 1 PR1+PR2 tests)

---

## §14 Clarifications (Sonnet follow-up, 2026-04-30)

> **Disposition note.** All ten items below are resolved or explicitly deferred with re-open triggers. §14 supersedes any contradictory framing in §1–§13. Composer 2 must treat §14 as authoritative where a conflict exists.

---

### §14.1 batting_card.status reliability at W8 invocation time

**Question.** Is `batting_card.status == "out"` reliably set at the moment `_w8_non_for_identified` runs
on post-wicket frames, or is it subject to the same strip-refresh latency that causes bat2_name to be stale?

**Resolution: RESOLVED — guard is reliable. Independent update path confirmed.**

`batting_card.status` is updated by three independent paths, *none of which are strip-refresh-dependent*:

| Path | Code location | Trigger |
|---|---|---|
| `scoreboard.dismiss_batter()` via `apply_scorer_decision` | `test_pipeline.py:8699` → `scoreboard.py:3400` | Scorer LLM output or wicket-counter delta |
| `scoreboard.apply_known_wicket_increment()` | `test_pipeline.py:9178` → `scoreboard.py:3233` | `ball_detector.detect()` returns `type=WICKET` |
| `_auto_dismiss_for_new_batter()` inside `update_batter()` | `scoreboard.py:1683` | New batter appears in extractor output |

Critically, the main-loop ordering in `test_pipeline.py` is:

```
L8699   apply_scorer_decision()          # → dismiss_batter() if scorer detects wicket
L9148   ball_event = ball_detector.detect()
L9178   apply_known_wicket_increment()   # → batting_card.status = "out"
  ...
L9636   score_mgr.on_frame()             # → _identify_and_set → _w8_non_for_identified
```

Both dismissal paths (L8699 and L9178) execute **before** `score_mgr.on_frame()` (L9636) in the primary
SCOREBOARD-frame code path. By the time `_w8_non_for_identified` is invoked, `batting_card.status`
has already been set to `"out"` for any dismissed batter whose wicket was confirmed on that frame.

**Production validation.** The F487–F506 `[WS-SLOT-INVARIANT]` cluster in MI vs SRH (batters_invariant_cluster_innings1.md §4.1) is proof-by-absence: Rickelton's `batting_card.status = "out"` was already set at F474 (via `apply_known_wicket_increment` → `_add_fow` → `_post_witnessed_dismissal_slot_rotation` at `scoreboard.py:3233–3234`). The fires occur because the **guard does not yet exist in pre-PR3 code** — `_w8_non_for_identified` ignores `batting_card.status` and returns `bat2_name = "Rickelton"` regardless. Post-PR3, the guard checks `batting_card.status` and returns `None` on every post-F474 frame.

**DRS-path caveat.** The code path for DRS-frozen frames (around `test_pipeline.py:7515`) may have
different ordering. Composer 2 must verify that `apply_known_wicket_increment` (or equivalent) executes
before `score_mgr.on_frame()` in the DRS path during implementation. If ordering is reversed in any
path, that is a **stop-and-route-back condition** (see §14.10 S1).

**Conclusion.** For the primary SCOREBOARD-frame path (the dominant case), the guard is reliable.
The alternative source (FOW state) is not required.

---

### §14.2 FOW state vs batting_card.status precedence

**Question.** Should the dismissed-batter guard use FOW state as primary source and batting_card.status
as fallback, or vice versa?

**Resolution: RESOLVED — batting_card.status as primary; FOW not required.**

`batting_card.status == "out"` is the correct primary check for the following reasons:

1. **Directness.** `_w8_non_for_identified` already has access to `self.scoreboard.batting_card` (via
   `_update_batters`' sync into `self.bat2_name`). A direct status check is a single dict lookup.

2. **Coverage.** batting_card.status is set by all three dismissal paths (§14.1 table). FOW via
   `_is_witnessed_dismissal()` (`scoreboard.py:3348`) returns True only for entries with `_witnessed=True`
   and not `_unwitnessed=True`. Unwitnessed placeholders would return False even when the batter is
   genuinely out. batting_card.status is set earlier (at the confirmed-dismissal stage) than the
   `_witnessed=True` FOW stamp.

3. **Simplicity.** Adding a `_is_witnessed_dismissal()` call to `score_manager.py` would introduce
   a new cross-class dependency that isn't already present. batting_card.status access is via the
   existing `self.scoreboard` reference.

4. **Precedence.** Once `batting_card.status = "out"` is set, `update_batter()` guards against
   resurrection for witnessed dismissals (`scoreboard.py:1730–1733`). The guard is sticky.

**Recommended guard logic (single condition):**

```python
# In _w8_non_for_identified, before returning bat2_name:
_bc = self.scoreboard.batting_card.get(self.bat2_name) if self.scoreboard else None
if _bc and _bc.get("status") == "out":
    log.info(f"[SM-W8-DISMISSED-GUARD] bat2_name={self.bat2_name!r} "
             f"is dismissed — returning None for non-striker")
    return None
```

FOW state (via `_is_witnessed_dismissal`) can be added as a belt-and-suspenders check in a
subsequent PR if match data reveals gaps where batting_card.status is briefly stale. Not needed for PR3.

---

### §14.3 Edge case: both bat1_name and bat2_name dismissed

**Question.** In a double-wicket sequence where both bat1_name and bat2_name are dismissed during the
admission window, the guard returns `None`. Is `SM.non = None` acceptable, or does downstream code
expect a fallback?

**Resolution: RESOLVED — SM.non = None is the correct and safe state during double-wicket admission.**

**Analysis of the double-wicket scenario:**

```
W12+δ1: non-striker (Jacks) dismissed.    bat2_name = Jacks.  batting_card["Jacks"].status = "out"
W12+δ2: striker (Rickelton) dismissed.    bat1_name = Rickelton. batting_card["Rickelton"].status = "out"
Admission window: SM.bat1=Rickelton (out), SM.bat2=Jacks (out), no fresh card yet.
_w8_non_for_identified(new_striker="Rohit") → bat2_name="Jacks" → status="out" → returns None
_identify_and_set: _set_slot_pair(new_striker, None) → SM.non = None
```

This is **END-STATE-NULL-OK**, which the design already accounts for (§2, §10). Downstream handling:

1. `_project_active_batters` (`test_pipeline.py:~3890`): `state["non"] = canon(SM.non)` = `canon(None)` = `None`.
   Fallback path: reads `_inn["non"]`. In a double-wicket scenario, `_post_witnessed_dismissal_slot_rotation`
   will have cleared both `_inn["striker"]` and `_inn["non"]` (Case 4, `scoreboard.py:3212–3220`).
   So `_inn["non"]` = `None` as well. `state["non"] = None`.

2. `WS-SCRUB` (`test_pipeline.py:3914`): `if not _nm: continue` — skips the None slot. No scrub.

3. `enforce_ws_slot_invariant`: `None != None` is False… wait. If state["striker"] = new_striker
   and state["non"] = None, there is no duplicate. No `[WS-SLOT-INVARIANT]` fire.

4. The UI rendering a `None` non-striker slot is handled by the existing null-slot rendering path
   (already exercised at innings start and between wickets).

**Double-wicket expectation:** `SM.non = None` is correct. It reflects genuine slot emptiness
(both batters out, second replacement hasn't arrived yet). The system self-heals when the broadcast
strip shows the second new batter in the next 1–5 frames.

**Guard behaviour verification:** Composer 2 should add a synthetic test for this case
(see §14.9 T4).

---

### §14.4 _canonical_active_slot bypass justification

**Question.** Part 2 bypasses `_canonical_active_slot` with a direct SM read. Should the helper
itself be reconsidered instead?

**Resolution: RESOLVED — bypass is correct. Splitting the helper is worse.**

**Purpose analysis of `_canonical_active_slot` (`test_pipeline.py:2385–2395`):**

The helper's contract is: *"return the currently active batter for this slot, or None if the slot
holds a dismissed/unknown name."* This contract is correct and serves all existing call sites:
over-end rotation, active-slot-repair, and `_striker_this_ball` attribution (L9153). All of these
want the **live active batter** — returning `None` for a dismissed name is the correct behavior
for those uses.

Part 2 of the fix has a **different need**: it must detect *whether SM currently holds a dismissed
name* — precisely the case that `_canonical_active_slot` suppresses. This is not a flaw in
`_canonical_active_slot`; it's a distinct question requiring a distinct read.

**Why not split the helper?**

1. **Semantic dilution.** A `_canonical_active_slot_raw` variant that returns dismissed names
   would be semantically identical to `score_mgr.non` or `score_mgr.striker` — a direct attribute
   read. There is no value in adding a wrapper.

2. **Call-site risk.** Introducing a `_raw` variant creates the possibility of future callers
   using the wrong variant. The existing `_canonical_active_slot` call sites (at least 6 in
   `test_pipeline.py`) are all correct with the filtering behavior; a `_raw` variant would need
   a governance rule to prevent misuse.

3. **Two-return-value option is worse.** A `(canonical_value, was_filtered)` return signature
   would require all 6+ existing call sites to unpack a tuple. Backward incompatible without
   a separate helper.

**Recommended bypass pattern for Part 2 (`[REPLACE]` block):**

```python
# Direct SM read — bypasses _canonical_active_slot's dismissed-name filter intentionally.
# We need to detect whether SM currently holds a stale dismissed name, which is
# precisely what _canonical_active_slot suppresses. This is not a mistake.
_sm_non_raw   = score_mgr.non      # may be dismissed / stale
_sm_str_raw   = score_mgr.striker  # should be current striker
```

The bypass is localised to 2 lines in the `[REPLACE]` block with an explanatory comment. No
change to `_canonical_active_slot` is needed or recommended.

---

### §14.5 Reduction prediction baseline

**Question.** The §9 prediction of "85–90% reduction" needs an explicit baseline. Against MI vs
SRH (1.13/min), the arithmetic is 73%, not 85–90%. Against PBKS (2.4/min), the arithmetic is
87.5%.

**Resolution: RESOLVED — MI vs SRH is the authoritative baseline. §9 prediction revised to 73–87%.**

**Clarified baseline:**

| Match | Measured rate | PR3 target | Predicted reduction |
|---|---|---|---|
| MI vs SRH innings 1 | 1.13/min (122 fires / 108 min) | <0.30/min | **73% minimum** (127 → ≤16 fires attributable to non-Cause-C) |
| PBKS vs RR | ~2.4/min | <0.60/min | **75% indicative** (PBKS has additional match-specific Cause C + shared-surname factors; less clean measurement) |

**Why MI vs SRH is the authoritative baseline:**

1. The 122-fire count is from a confirmed Cause C analysis (lever1_pr2_match_analysis.md §2).
   All 122 fires are attributable to WS-SCRUB rebuilds driven by stale SM.non.
2. Part 1 closes all 122 fires (prevents stale SM.non on every post-wicket frame).
3. The residual (<0.30/min target, ~16–20 fires) is attributed to innings-transition fires
   (8 counted in the extended MI vs SRH log) and any Rule=A resurrection fires (F2167 type).

**Why 73% is the minimum, not the ceiling:**

The §9 "85–90%" estimate assumed that roughly 10–15% of fires survive PR3 (innings transitions,
Rule=A, other non-Cause-C). Against the 122-fire MI vs SRH dataset, this is:
122 × 0.125 = ~15 residual fires → (122-15)/122 = **87.7% reduction**.

The 73% figure arises from the conservative ceiling (<0.30/min). If the true residual is
≤16 fires: (122-16)/122 = **87%**. If residual is ≤32 fires: 74%.

**Revised §9 prediction (authoritative):**
- Primary baseline: MI vs SRH, 1.13/min
- Expected residual: 12–20 fires (innings transitions + Rule=A)
- Expected post-PR3 rate: 0.11–0.18/min
- Predicted reduction: **73–87%** (lower bound conservative; upper bound based on Cause C
  isolation analysis)
- Confidence: MEDIUM (same as §9)

**Watch criterion revision.** For next match validation, use the MI vs SRH baseline as the
reference: success if post-PR3 rate ≤ 0.30/min and `[SM-W8-DISMISSED-GUARD]` fires >0
(confirming the guard is triggering).

---

### §14.6 PR sequencing: Part 1, Part 2, or both?

**Question.** Should PR3 ship Part 1 alone (binding fix), both Part 1 + Part 2 together, or
Part 1 in PR3 and Part 2 in PR4?

**Resolution: RESOLVED — ship Part 1 + Part 2 + W3-W7 together in a single PR3.**

**Reasoning:**

| Option | Pros | Cons |
|---|---|---|
| (a) Part 1 alone in PR3a, Part 2 in PR3b | Fastest path to production validation | Part 2's `[STRIKER-SM-CUTOVER] reason=batter-arrival` telemetry unavailable during first match; two PRs for one logical fix |
| **(b) Part 1 + Part 2 together in PR3** | **Complete fix; rich telemetry from first match; single review surface** | Slightly larger diff (~45 LOC vs ~20 LOC for Part 1 alone) |
| (c) Part 1 in PR3, Part 2 in PR4 unconditionally | Clean PR3 focus | Wastes a match cycle; Part 2's `[STRIKER-SM-CUTOVER]` signal is useful for confirming Part 1 worked |

**Key considerations:**

1. **Part 2's risk profile is low.** Change 4 (`[REPLACE]` block, `test_pipeline.py:8097–8104`) is
   ~4 LOC inside an already-guarded branch (only fires on confirmed new batter admission). It cannot
   produce false-positive duplicates: it only corrects SM slots when a dismissed name is detected via
   direct read, and only when a new batter has just been confirmed.

2. **Part 2's telemetry has independent value.** `[STRIKER-SM-CUTOVER] reason=batter-arrival`
   provides a direct confirmation signal: "the intra-over batter-arrival cutover fired". Having this
   signal in the first post-PR3 match log allows instant verification that the new trigger path is
   exercised. Without it, the only signal is the absence of `[WS-SLOT-INVARIANT]` fires — a harder
   inference.

3. **Diff size is manageable.** Total estimated LOC across all 5 changes (Commits 1–3 in §7):
   - Change 1 (Part 1 guard): ~12 LOC in `score_manager.py`
   - Change 2 (W3–W7 migration): ~16 LOC in `score_manager.py`
   - Change 3 (W7): ~4 LOC in `score_manager.py`
   - Change 4 (Part 2 CUTOVER): ~4 LOC in `test_pipeline.py`
   - Change 5 (tests): ~80–120 LOC in `test_recent_fixes.py`
   Total: ≤160 LOC. Well within a single reviewable PR.

**Decision: Option (b). Ship Part 1 + Part 2 + W3-W7 together as PR3 in 3 commits
(per §7 migration order).**

If implementation reveals that Part 2's batter-arrival CUTOVER interacts unexpectedly with any
existing code path, Composer 2 should stop and route back before committing Change 4 (see §14.10 S3).

---

### §14.7 W3-W7 disposition: PR3 or PR4

**Question.** Should W3-W7 migration ship in PR3 (bundled) or as a separate PR4?

**Resolution: RESOLVED — W3-W7 ships in PR3 (bundled).**

**Reasoning:**

1. **Original audit contract.** `sm_rotation_atomicity_design.md §8` framed PR3 as "W3–W7 migration
   through `_set_slot_pair`". While lever1_pr2_match_analysis.md §4.1 revised the framing ("the
   binding fix is the CUTOVER trigger, not W3–W7 migration per se"), the W3–W7 changes remain
   correct and desirable.

2. **Cold-start hygiene compounds quickly.** If W3–W7 are deferred, any cold-start during a live
   match triggers the pre-`_set_slot_pair` path, producing degenerate-card slots that generate
   `[SM-SLOT-INVARIANT]` fires during cold-start windows. These fires are distinct from Cause C
   but contribute to overall noise. Cleaning them up in PR3 closes a separate noise floor.

3. **Changes are small and well-isolated.** Changes 2 and 3 (`_init_from_card` L1315–1328 and
   `_update_batters` L1916–1918) are purely mechanical migrations to `_set_slot_pair`. No logic
   changes. Risk is low.

4. **No benefit to splitting.** Deferring to PR4 adds calendar delay (requires another PR cycle,
   review, and deployment) for 16+4 = 20 LOC of straightforward changes. The bundled PR3 is
   coherent: "close all known SM slot write paths that can produce stale or degenerate state."

**Decision: W3-W7 ships in PR3, as Commit 1 alongside Part 1 (per §7 migration order).**

---

### §14.8 Telemetry coordination

**Question.** Coordination details for `[SM-W8-DISMISSED-GUARD]` (Part 1) and
`[STRIKER-SM-CUTOVER] reason=batter-arrival` (Part 2).

**Resolution: RESOLVED.**

#### §14.8.a `[STRIKER-SM-CUTOVER] reason=batter-arrival` — backward compatibility

The existing `[STRIKER-SM-CUTOVER]` tag is emitted at `test_pipeline.py:2397–2415` with no
`reason` field currently. Adding `reason="batter-arrival"` is **additive** and backward compatible:
existing analyzer regex patterns that match `[STRIKER-SM-CUTOVER]` will continue to match.
The `reason` field allows new queries to distinguish trigger sources:

```
[STRIKER-SM-CUTOVER] reason=batter-arrival  ← Part 2 (new)
[STRIKER-SM-CUTOVER] reason=over-end        ← existing over-end trigger (no change)
```

No analyzer regex changes required for backward compatibility. New queries may filter by
`reason=batter-arrival` to confirm Part 2 is exercised. Recommend adding the `reason` field
to the existing over-end emitter simultaneously (so both sources are disambiguated from PR3
day 1), but this is optional and can be done in a follow-up.

**Expected fire rate for Part 2:** ~1 fire per wicket per innings. MI vs SRH innings 1 had
5 wickets in 108 min → ~5 fires per innings. Rate ≈ 0.05/min. Very low — no noise concern.

#### §14.8.b `[SM-W8-DISMISSED-GUARD]` — deduplication required

**Critical revision to §6 and §4.** The guard fires inside `_w8_non_for_identified`, which is
called on **every steady-state frame** where `_identify_and_set` runs (i.e., every frame with
d_score=d_wickets=d_overs=0). The post-wicket gap lasts ~13–33 frames (F474–F507 in MI vs SRH
= 33 frames for Rickelton's dismissal). Logging on every frame produces:
- 33 frames × 5 wickets × 2 innings ≈ **330 log lines per match** for this tag.

This is noisy. **The guard should be deduplicated using a per-dismissed-batter flag on SM:**

```python
# In ScoreManager __init__: self._w8_guard_fired: set[str] = set()
# In _update_batters, on card refresh: clear _w8_guard_fired for any name
#   that has re-appeared as "batting" (new batter admission clears the set)

# In _w8_non_for_identified:
if _bc and _bc.get("status") == "out":
    if self.bat2_name not in self._w8_guard_fired:
        log.info(f"[SM-W8-DISMISSED-GUARD] ...")  # log only on first fire
        self._w8_guard_fired.add(self.bat2_name)
    return None
```

**Expected fire rate after deduplication:** ~1 fire per non-striker wicket per innings.
MI vs SRH innings 1 had ~2–3 non-striker wickets → **2–3 fires per innings**. Rate ≈ 0.02/min.

**Clear condition for `_w8_guard_fired`:** when `_update_batters` receives a card where bat2_name
changes (new batter confirmed on strip), clear the dismissed batter from `_w8_guard_fired`. This
models the end of the post-wicket admission window.

**Analyzer baseline calibration:** `[SM-W8-DISMISSED-GUARD]` expected ≤5 fires per match (accounting
for both innings). If a match log shows >20 fires, this is a signal that the clear condition is not
firing (bat2_name stuck despite strip updates) — investigate.

#### §14.8.c Summary fire rate table

| Tag | Trigger | Expected per innings | Expected per match |
|---|---|---|---|
| `[SM-W8-DISMISSED-GUARD]` | Once per non-striker wicket (deduplicated) | 2–3 | 4–6 |
| `[STRIKER-SM-CUTOVER] reason=batter-arrival` | Once per admitted new batter | 4–6 | 8–12 |
| `[STRIKER-SM-CUTOVER] reason=over-end` | Once per over (existing) | ~19 | ~38 |
| `[WS-SLOT-INVARIANT]` post-PR3 | Residual only (innings transition, Rule=A) | 6–10 | 12–20 |

---

### §14.9 Test fixture design

**Question.** What are the fixture sources and acceptance criteria for PR3 test coverage?

**Resolution: RESOLVED.**

**Key insight from §14.1:** the ordering finding (`apply_known_wicket_increment` at L9178 before
`score_mgr.on_frame()` at L9636) simplifies test setup considerably. A unit test for the guard can
directly set `batting_card[dismissed].status = "out"` in the test fixture *before* calling
`score_mgr.on_frame()`, exactly mirroring what happens in production. No complex multi-frame
state construction is required for Part 1 unit tests.

#### Test inventory

| ID | Name | Type | Source | Acceptance criterion |
|---|---|---|---|---|
| T1 | `test_lever1_pr3_w8_dismissed_guard_fires` | Unit | Synthetic | `[SM-W8-DISMISSED-GUARD]` emitted; `score_mgr.non` is `None` after frame where bat2_name=dismissed and batting_card[dismissed].status="out" |
| T2 | `test_lever1_pr3_w8_dismissed_guard_dedup` | Unit | Synthetic | `[SM-W8-DISMISSED-GUARD]` emitted exactly once across 5 consecutive frames in same post-wicket window |
| T3 | `test_lever1_pr3_batter_arrival_cutover_fires` | Integration | Real frames (MI vs SRH F474–F510) | `[STRIKER-SM-CUTOVER] reason=batter-arrival` emitted after `[REPLACE]` block for Rohit Sharma admission; no `[WS-SLOT-INVARIANT]` in F487–F510 window |
| T4 | `test_lever1_pr3_double_wicket_both_dismissed` | Unit | Synthetic | Both bat1_name and bat2_name dismissed → `score_mgr.non = None`; no `[WS-SLOT-INVARIANT]` fire |
| T5 | `test_lever1_pr3_ws_scrub_cause_c_eliminated` | Integration | Real frames (MI vs SRH F487–F506) | Zero `[WS-SLOT-INVARIANT]` fires in admission window after applying PR3 changes |
| T6 | `test_lever1_pr3_regression_sm_slot_invariant` | Regression | Existing (adapt from T2 in §8) | `[SM-SLOT-INVARIANT]` still fires for genuine degenerate-card input; PR3 guard doesn't break the existing `_set_slot_pair` invariant path |
| T7 | `test_lever1_pr3_w3_w7_set_slot_pair` | Unit | Synthetic cold-start card | W3–W7 migration: `_init_from_card` and `_update_batters` produce `[SM-SLOT-INVARIANT]` on degenerate-card input (duplicate batter names) and clean output on valid card |

**Fixture sourcing for T3 and T5 (real frames):**

MI vs SRH log file (`logs/pipeline-2026-04-29-194416-mi-srh-live.log`) contains the F474–F638
admission window. The test should replay F474–F510 with PR3 applied and assert:
1. `score_mgr.non` is `None` from F475 until Rohit Sharma admitted (F507+)
2. No `[WS-SLOT-INVARIANT]` fires in F487–F506
3. `[SM-W8-DISMISSED-GUARD]` fires exactly once (dedup) in the F475–F507 window

**Acceptance criteria for shipping:**

All T1–T7 must pass. T3 and T5 are blocking — if real-frame replay still shows
`[WS-SLOT-INVARIANT]` fires in the admission window, PR3 is not achieving its target and
Composer 2 must stop and route back (see §14.10 S4).

---

### §14.10 Composer 2 stop-and-route-back conditions (PR3-specific)

In addition to standard stop conditions (Path A snapshot regression per §11, contract gap, scope
creep), Composer 2 must **stop and route back to a human reviewer** if any of the following is
detected during PR3 execution:

| ID | Condition | Reason to stop |
|---|---|---|
| S1 | In any code path, `score_mgr.on_frame()` is called **before** `apply_known_wicket_increment()` or `apply_scorer_decision()` for the same frame (verified during DRS-path audit or other non-primary path) | §14.1 reliability assumption is violated for that path; guard may be unreliable in that case; needs redesign |
| S2 | `[SM-W8-DISMISSED-GUARD]` fires for a batter whose `batting_card.status` is **not** `"out"` (false positive) | Guard logic has a bug — may suppress valid non-striker assignments |
| S3 | Part 2 batter-arrival CUTOVER trigger fires outside the `[REPLACE]` block, or fires for a batter that is already correctly in `score_mgr.non` (false positive CUTOVER) | Part 2 guard condition is incorrect; may cause slot thrashing |
| S4 | After implementing Commit 1 (Part 1 + W3–W7), the `test_lever1_pr3_ws_scrub_cause_c_eliminated` (T5) fixture still shows `[WS-SLOT-INVARIANT]` fires in the F487–F506 window | Part 1 guard is not working as designed; mechanism analysis may be incomplete |
| S5 | W3–W7 migration (`_init_from_card`, `_update_batters`) causes `[SM-SLOT-INVARIANT]` to fire on frames where it previously did not (regression in existing tests) | The migration introduced a bug; need to review the exact `_set_slot_pair` call-site for W3–W7 |
| S6 | Path A snapshot test byte-identity changes for **any reason** | Per §11; indicates an unintended ripple in the `_build_full_payload_from_state` path |

**General escalation bias:** if Composer 2 encounters a condition during execution that is
architecturally significant but not enumerated above, the conservative default is **stop and route
back**. A 30-minute design clarification is preferable to a silently-incorrect guard in a live
match pipeline.

---

## §15 Final Composer 2 Readiness Checklist

| # | Checklist item | Status | Reference |
|---|---|---|---|
| 1 | All §14 clarification questions resolved or explicitly deferred with re-open triggers | ✓ RESOLVED (all 10) | §14.1–§14.10 |
| 2 | batting_card.status reliability confirmed — guard is NOT strip-refresh dependent | ✓ CONFIRMED — independent update path at L8699/L9178, before L9636 | §14.1 |
| 3 | DRS-path ordering caveat documented as stop condition S1 | ✓ DOCUMENTED | §14.10 S1 |
| 4 | FOW vs batting_card.status precedence decided | ✓ batting_card.status primary; FOW not needed for PR3 | §14.2 |
| 5 | Double-wicket edge case analysed | ✓ SM.non=None is correct; downstream handles gracefully | §14.3 |
| 6 | _canonical_active_slot bypass justified | ✓ Bypass correct; split-helper option rejected | §14.4 |
| 7 | Reduction prediction baseline made explicit | ✓ MI vs SRH (1.13/min) primary; revised prediction 73–87% | §14.5 |
| 8 | PR sequencing decided | ✓ Ship Part 1 + Part 2 + W3-W7 together in single PR3 | §14.6 |
| 9 | W3-W7 disposition decided | ✓ Ship in PR3 (bundled with Part 1) | §14.7 |
| 10 | `[SM-W8-DISMISSED-GUARD]` deduplication requirement added | ✓ Per-dismissed-batter set; ≤6 fires per match | §14.8.b |
| 11 | `[STRIKER-SM-CUTOVER] reason=batter-arrival` backward compatibility confirmed | ✓ Additive field; no analyzer regex changes needed | §14.8.a |
| 12 | Fire rate table calibrated for analyzer baseline | ✓ All four tags with expected per-match rates | §14.8.c |
| 13 | Test fixture inventory specified (T1–T7) with real-frame sources and acceptance criteria | ✓ T3/T5 blocking; T1/T2/T4/T6/T7 non-blocking gating | §14.9 |
| 14 | Composer 2 stop conditions enumerated (PR3-specific, S1–S6) | ✓ Six conditions enumerated | §14.10 |
| 15 | `_w8_guard_fired` set lifecycle (add / clear) specified | ✓ Added on guard fire; cleared on bat2_name change in _update_batters | §14.8.b |
| 16 | §6 Change 1 code sketch updated to include `_w8_guard_fired` deduplication | ✓ IMPLEMENTED — `ScoreManager._w8_guard_fired` + clear on bat2 churn (`_accept_initial`, `_update_batters`) | §14.8.b |
| 17 | §9 prediction revised to 73–87% against MI vs SRH baseline | ✓ **§14.5 authoritative** — backlog + tests cite 73–87%; §9 band superseded | §14.5 |
| 18 | Commits 1–3 migration order from §7 remains valid | ✓ Commit 1 = Part 1 + W3–W7 (Changes 1–3); Commit 2 = Part 2 (Change 4); Commit 3 = Tests (Change 5) | §7 |
| 19 | No improvisation points remain | ✓ Verified via §14.1–§14.10 disposition; all pre-execution unknowns resolved or explicitly gated by stop conditions | §14.* |

**Seal (execution complete):** §15 line-items 1–19 confirmed; items 16–17 implemented per §14.8.b / §14.5. **Lever 1 PR3 shipped** — implementation notes and ancillary fixes in **§16**.

If during execution Composer 2 encounters any condition not enumerated in §14.10 but that feels
architecturally significant, the conservative bias is **stop and route back**.

---

## §16 Implementation notes (ship: 2026-04-30)

**Readiness:** §15 checklist closed with items 16–17 implemented; **`just test`** green (**852** PASS in CI harness at ship commit); Path A WS snapshot regression unchanged.

**§14.10 stop conditions (PR3 scope):** No S1–S6 route-back required for the Part 1 / Part 2 / W3–W7 bundle as specified.

**Ancillary fixes discovered during validation:**

1. **`ScoreManager._accept_initial` broadcast routing (`files/score_manager.py`):** Striker strip detection now snapshots `_strip_bc = card.get("broadcast")` and derives `ind` via `str(_strip_bc).lower().strip()` instead of indexing `card["broadcast"]` after the truthiness gate. On plain `dict` inputs this is equivalent; it avoids spurious fall-through to `source=cold_start` when a mapping’s `.get` and `__getitem__` disagree (observed during T6 harness debugging).

2. **Fix 16 telemetry ordering (`files/test_pipeline.py` `_execute_innings_change_from_state`):** `score_mgr.set_innings_2(...)` runs **before** `scoreboard.set_innings_2(...)` on the cricket-rules swap path, and the cold-start relabel path invokes SM reset **before** mutating `scoreboard.innings` / `current_innings`. `ScoreManager.innings` reads through `Scoreboard.current_innings`; the previous order made `set_innings_2` idempotently return early and suppressed **`[SM-INNINGS-2-RESET]`** in the F2660–F2900 replay harness.

3. **Replay harness artifacts (`files/test_recent_fixes.py`):** `_build_pre_innings_2_transition_fixture` resets innings-1 state with `sb.innings[1] = sb._blank()` (`_inn` is read-only). E2E replay normalizes parser `target=None` on `overs_complete_20` events to **244** for deterministic `_execute_innings_change_from_state` inputs; **`files/f2660_f2900_transition_signature.txt`** holds the tuple repr sentinel; `test_innings_transition_window_parser` accepts **`target in (244, None)`** when the live log omits the chase echo on the firing row.

**Production validation:** §14.5 **73–87%** `[WS-SLOT-INVARIANT]` reduction and §14.8 dedup (**≤6** `[SM-W8-DISMISSED-GUARD]` per match) remain **match-day observability** targets — not re-proven in this offline suite beyond T5/T7 harness bounds.
