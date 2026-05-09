# `ScoreManager` rotation atomicity — Lever 1 audit & design contract

**Status (2026-04-29):** AUDIT ONLY — no `score_manager.py` mutations in
this task. Sections §6–§8 are the Composer-2-executable contract for
the follow-up PR(s).

**Predecessors:**

- `striker_path_b_read_audit.md` — established Lever 1 (SM rotation
  atomicity) and Lever 2 (`get_broadcast_state` collapse) as the only
  two `[WS-SLOT-INVARIANT]`-reducing axes. Read audit found zero
  migratable read sites. **Lever 1 deferred.**
- `get_broadcast_state_path_b_audit.md` — Lever 2 audit; predicted ≈0%
  `[WS-SLOT-INVARIANT]` reduction from cleanup alone. **Lever 2
  shipped 2026-04-29** as Option A (alias + shadow projection
  uniformity).
- `build_full_payload_extraction_design.md` — `_build_full_payload_from_state`
  extraction; predicted ≈0% reduction from extraction alone.
  **Extraction shipped 2026-04-29.**

This document audits **Lever 1** and is the single remaining lever
the prior three audits have been pointing at.

---

## 0. Architecture context (locked, do not re-litigate)

### 0.1 Where `[WS-SLOT-INVARIANT]` fires originate

`enforce_ws_slot_invariant` (`test_pipeline.py:2230`) fires only when

```text
state["striker"] == state["non_striker"]   # both non-None, equal
```

after `_project_active_batters` has populated `state` from
`score_mgr.striker` / `score_mgr.non_striker` (with a status-gated,
collision-guarded `_inn` fallback).

The relevant slice of `_project_active_batters` is straightforward:

```2205:2227:files/test_pipeline.py
    state["striker"] = canon_fn(score_mgr.striker)
    state["non_striker"] = canon_fn(score_mgr.non_striker)

    _bc = scoreboard.batting_card or {}
    _sb = scoreboard._inn or {}
    _events = []
    for _slot in ("striker", "non_striker"):
        if state.get(_slot) is not None:
            continue
        _sb_val = _sb.get(_slot)
        if not _sb_val:
            continue
        _card_key = (scoreboard.resolve_name(_sb_val)
                     if hasattr(scoreboard, "resolve_name") else _sb_val)
        _card = _bc.get(_card_key)
        if not _card or _card.get("status") != "batting":
            continue
        _other_slot = "non_striker" if _slot == "striker" else "striker"
        if _card_key == state.get(_other_slot):
            continue
        state[_slot] = canon_fn(_card_key)
        _events.append((_slot, _card_key))
    return _events
```

The `_other_slot` collision guard at L2222–L2224 already prevents the
fallback from manufacturing a duplicate. So the residual duplicates
that reach `enforce_ws_slot_invariant` come from **one of three**
end-states *immediately before* `_project_active_batters` runs:

1. **(A) SM end-state duplicate** — `canon(score_mgr.striker) ==
   canon(score_mgr.non_striker)` after `score_mgr.on_frame()` returns.
2. **(B) Canon collision** — `score_mgr.striker` and `.non_striker`
   are different raw strings that canonicalize to the same squad key
   (e.g. `"R. SINGH"` and `"Rinku"` → `"Rinku Singh"`).
3. **(C) WS-SCRUB rebuild collision** (`test_pipeline.py:4914`) —
   when only one batting-status name remains, the per-slot active-list
   rebuild can lift the same survivor into both slots; `[WS-SCRUB]`
   tags fire first, then `[WS-SLOT-INVARIANT]`.

(A) is exclusively **SM-internal** — Lever 1 territory.
(B) is **SM canonicalization timing** — covered by the same Lever 1
helpers (the design below routes every slot write through
`_canonicalize_name` at the SM boundary, so canon mismatches between
slots cannot arise in the first place).
(C) is downstream of `_project_active_batters` and is mechanically
caused by the active list collapsing to one name before SM has caught
up; it is **not** addressable by SM rotation atomicity. §7.5 sizes
the residual.

### 0.2 What "atomicity" means here (and what it does not mean)

The brief asks about *atomicity contract* and *intermediate states*
visible during rotations. The following scoping is critical:

- The pipeline is **single-threaded** (`asyncio` + sync hot path).
  `main_loop` calls `score_mgr.on_frame(_sm_frame)` (L9472), then
  `build_full_payload(...)` (L9525), then
  `await broadcast_state(ws_payload)` (L9543) — strictly in that
  order. There is **no `await` inside `on_frame`**, no thread
  hand-off, and no callback into `score_mgr` between the SM call
  and `build_full_payload`. Verified by code search: every
  reference to `score_mgr.striker` / `score_mgr.non_striker` in
  `test_pipeline.py` is read **after** `on_frame` returned.
- Therefore, **inter-statement intermediate states inside
  `_apply_event` / `_identify_and_set_striker` / `_init_from_card`
  are not externally observable.** A two-line
  `self.striker = X; self.non_striker = Y` block produces zero
  observable transient state; the GIL serialises bytecodes and
  `build_full_payload` doesn't run until the entire `on_frame`
  call has returned.
- The relevant invariant is therefore the **post-`on_frame` end
  state**, not bytecode-level interleaving. "Rotation atomicity"
  here is shorthand for "every code path that completes a slot
  write must leave a valid end state at the next external read".

This reframing changes the design space from
*hold-the-lock-while-swapping* (irrelevant) to
*single-helper write-with-postcondition-and-telemetry*. §6 designs
the latter.

### 0.3 Out of scope

- `SM.full_reset` (just shipped; clears slots to `(None, None)` —
  trivially distinct).
- State Recovery aggregator (reads `_inn`, not SM; per
  `striker_path_b_read_audit.md` §2.1).
- `_project_active_batters` itself (canonical; only the WS-payload
  collapse direction).
- Path A WS-payload byte-identity snapshot (untouched — none of the
  designs below alter `_build_full_payload_from_state`).
- Item 3 Path B LOW-risk batch (excluded `striker` / `non_striker`
  by design; this audit is the dedicated follow-up).
- Cluster 1 helpers (`_set_inn_slot_with_sm_mirror`,
  `_canonical_active_slot`, `_scorer_batter_update_allowed`,
  `_scorer_batter_row_is_dismissed_resurrection`).

---

## 1. SM rotation / slot-write site inventory

The pattern set used to enumerate sites:

```text
rg "(self\.striker|self\.non_striker).*=" files/score_manager.py
```

Every call point that **writes** `self.striker` or
`self.non_striker` is enumerated below. Reads (e.g. the
`_build_payload` canonicalize at L2699/L2701) are not in this table —
they only read the end state and cannot cause duplicates by
themselves.

### 1.1 Master table

| # | File / function | Line(s) | Trigger | Pattern |
|---|---|---|---|---|
| **W1** | `__init__` | 129–130 | object construction | `self.striker = None; self.non_striker = None` |
| **W2** | `_clear_per_innings_sm_surface` | 733–734 | `full_reset()` reason="external" | sequential `= None` writes |
| **W3** | `_init_from_card` (broadcast_striker matches bat1) | 1292–1293 | `_accept_initial` cold-start adoption | `self.striker = self.bat1_name; self.non_striker = self.bat2_name` |
| **W4** | `_init_from_card` (broadcast_striker matches bat2) | 1295–1296 | same | swapped: `striker = bat2; non_striker = bat1` |
| **W5** | `_init_from_card` (no broadcast indicator branch) | 1298–1299 | same | `striker = bat1; non_striker = bat2` (default) |
| **W6** | `_init_from_card` (no broadcast indicator at all) | 1301–1302 | same | `striker = bat1; non_striker = bat2` (default) |
| **W7** | `_update_batters` bootstrap | 1890–1892 | first `_update_batters` after `bat1_name`/`bat2_name` were both None | `if not self.striker: striker = bat1; non_striker = bat2` |
| **W8** | `_identify_and_set_striker` partner write | 2068–2075 | balls-delta / runs-delta / broadcast-first-name evidence flips striker | `self.striker = new_striker; if new == bat1: non_striker = bat2; elif new == bat2: non_striker = bat1` |
| **W9** | `_apply_event` strike-rotation (odd runs) | 2391 | legal ball, runs % 2 == 1 | `self.striker, self.non_striker = self.non_striker, self.striker` (atomic tuple swap) |
| **W10** | `_apply_event` strike-rotation (over rollover) | 2393 | over-end | same atomic tuple swap |
| **W11** | `_apply_event` wicket dismissal — striker out | 2480–2482 | event["type"]=="WICKET" and best_dismissed == self.striker | `self.striker = None; self.non_striker = survivor` |
| **W12** | `_apply_event` wicket dismissal — non_striker out | 2483–2485 | same with best_dismissed == self.non_striker | `self.non_striker = None; self.striker = survivor` |

**Total: 12 slot-write sites across 6 functions.**

### 1.2 Sites that are *not* in the table (but could be confused for them)

- `_build_payload` L2699–L2702: **read** with canonicalize. End-state
  reader; cannot cause duplicates on its own (it could *project* a
  duplicate into the WS payload if SM end state was already a
  duplicate, but that's caught at the source by the post-condition
  in §6.4).
- `set_innings_2` L1736: calls `self.__init__()`, which sets
  `self.striker = None; self.non_striker = None`. Subsumed by W1.
- `stop()` / `start()` L826–L830: calls `__init__`. Subsumed by W1.
- `_post_witnessed_dismissal_slot_rotation`
  (`scoreboard.py:3140+`): writes `_inn["striker"]` / `_inn["non_striker"]`
  on the **scoreboard** side, not SM. Audited as R3–R5 in
  `striker_path_b_read_audit.md`; AUTHORITATIVE writers, not Lever 1.

---

## 2. Per-site categorization

Categories per the brief:

- **ATOMIC** — single statement (tuple swap) or guarded scope; no
  observable intermediate state and no end-state duplicate.
- **INTERMEDIATE-DUPLICATE** — multi-statement write where a
  *bytecode* window holds `striker == non_striker`. **All such
  windows are unobservable** in this codebase per §0.2; the category
  is recorded for completeness and because a future async refactor
  could expose them.
- **END-STATE-DUPLICATE-RISK** — multi-statement write that can
  leave `striker == non_striker` as a **stable** end-state
  depending on input shape. This is the *true* Lever 1 driver
  category.
- **INTERMEDIATE-NULL** — multi-statement write with a transient
  `None`. Same observability caveat as INTERMEDIATE-DUPLICATE.
- **END-STATE-NULL-OK** — leaves one or both slots `None` as a
  *valid* end-state (e.g. post-wicket gap awaiting incoming
  batter). Not a duplicate; not a defect.
- **EXTERNAL-DRIVEN** — atomicity is the caller's responsibility
  (e.g. `__init__` is invoked by callers that own ordering).

### 2.1 Per-site sequence and category

| # | Trigger | Sequence | Intermediate state | End-state duplicate possible? | Category |
|---|---|---|---|---|---|
| **W1** | `__init__` | `striker = None`, `non_striker = None` | `(None, prior=undefined)` | No (both `None`) | EXTERNAL-DRIVEN |
| **W2** | `full_reset` | same as W1 sequentially | `(None, prior_value)` between L733/L734 | No (both end `None`) | END-STATE-NULL-OK |
| **W3** | cold-start, broadcast_striker matches bat1 | `striker = bat1`, `non_striker = bat2` | `(bat1, prior_non_striker)` | **Yes** — if `bat1 == bat2` (degenerate scout card) | END-STATE-DUPLICATE-RISK |
| **W4** | cold-start, broadcast_striker matches bat2 | `striker = bat2`, `non_striker = bat1` | `(bat2, prior_non_striker)` | **Yes** — same as W3 | END-STATE-DUPLICATE-RISK |
| **W5** | cold-start, broadcast_striker present but no bat-name match | `striker = bat1`, `non_striker = bat2` | as W3 | **Yes** — same | END-STATE-DUPLICATE-RISK |
| **W6** | cold-start, no broadcast_striker | as W5 | as W5 | **Yes** — same | END-STATE-DUPLICATE-RISK |
| **W7** | `_update_batters` bootstrap | `striker = bat1`, `non_striker = bat2` | as W3 | **Yes** — same; **and** if SM has already seen one of bat1/bat2 in `non_striker` slot during the bootstrap window | END-STATE-DUPLICATE-RISK |
| **W8** | `_identify_and_set_striker` flips striker on evidence | `striker = new_striker` first, then `non_striker = bat2 (or bat1)` only if new_striker matches a bat slot | `(new_striker, prior_non_striker)` between L2071 and L2073/L2075 | **Yes** — if `new_striker` is canonically equal to either `bat1_name` or `bat2_name` but the literal string mismatches (Issue-1 canon mismatch) — `non_striker` is left at its prior value, which after a partner-update may equal `new_striker`. Also yes if both `bat1_name` and `bat2_name` are `None` and `new_striker` is non-None (`non_striker` not touched) | END-STATE-DUPLICATE-RISK |
| **W9** | odd-run swap | `(s, ns) = (ns, s)` (atomic tuple unpack) | none observable; result distinct iff input distinct | No (assuming pre-state distinct) | ATOMIC |
| **W10** | over rollover swap | as W9 | as W9 | No (assuming pre-state distinct) | ATOMIC |
| **W11** | wicket — striker out | `striker = None`, then `non_striker = survivor` | `(None, prior_non_striker)` | No (None != non-None survivor); but **end-state duplicate possible** if `survivor` was selected by name-iteration loop and equals `prior_non_striker` already (which is the common case → harmless) | END-STATE-NULL-OK |
| **W12** | wicket — non_striker out | `non_striker = None`, then `striker = survivor` | `(prior_striker, None)` | No (same logic as W11) | END-STATE-NULL-OK |

**Summary:** of the 12 sites, **6 are END-STATE-DUPLICATE-RISK
(W3–W8)**; 2 are ATOMIC (W9, W10); 3 are END-STATE-NULL-OK (W2, W11,
W12); 1 is EXTERNAL-DRIVEN (W1).

### 2.2 The "intermediate-duplicate" sites in §0.2 framing

W3, W4, W5, W6, W7, W8 do produce *bytecode-level* intermediate
duplicates depending on prior state. Per §0.2 these are
**unobservable** under the current single-threaded sync hot path.
The design in §6 still treats them as if they were observable — the
helper-based fix is the same fix that closes the end-state-duplicate
risk, so the intermediate window is closed for free.

If a future refactor makes `on_frame` async / re-entrant
(e.g. yielding to an awaitable extractor mid-method), the
`_set_slot_pair` helper in §6.2 is the *right* design for that future
too: the helper performs a single atomic tuple write and emits
`[SM-SLOT-INVARIANT]` post-condition telemetry — both observable
windows and end-state defects collapse to one fix surface.

---

## 3. Cross-reference to `[WS-SLOT-INVARIANT]` production fires

### 3.1 Headline counts

- **387** fires in extended PBKS-vs-RR window (~164 min).
- **26** fires in 15-min post-restart window.

Both numbers are from `analyze_match_telemetry.py` rollup of
`[WS-SLOT-INVARIANT] duplicate slots` log lines (analyzer regex
`WS_SLOT_INVARIANT`, `analyze_match_telemetry.py:140`).

### 3.2 Fire pattern → write-site mapping

The analyzer does not currently tag a *source* per fire. The mapping
below is the audit's hypothesis (medium confidence; live telemetry
in §6.5 will validate).

| Fire pattern | Likely write-site | Confidence |
|---|---|---|
| Burst at over-end + odd-run delivery in same frame | W9+W10 (back-to-back tuple swap; atomic but harmless cancellation that *exposes* a pre-existing duplicate) | LOW — swaps don't *create* duplicates |
| Wicket-frame duplicate (striker becomes survivor; `_inn` still has prior non_striker = survivor) | W11/W12 + `_project_active_batters` `_inn` fallback | MEDIUM — `_other_slot` guard already in place; should not surface, but canon-mismatch (§3.3) can defeat the guard |
| New-batter arrival burst (post-wicket, before extractor confirms incoming name) | W7 (`_update_batters` bootstrap) running with stale `card_b1 == card_b2` after a graphic flash | MEDIUM-HIGH |
| Cold-start re-entry duplicate | W3–W6 (`_init_from_card`) when scout card has degenerate `bat1_name == bat2_name` | MEDIUM |
| Sustained duplicate over multiple frames (no rotation event) | W8 (`_identify_and_set_striker`) flipping striker to a name not matched by either bat-slot, leaving `non_striker` at prior value that canonicalizes to the same person | HIGH |

### 3.3 The canon-collision failure mode (sub-class of (A) and (B) in §0.1)

`_identify_and_set_striker` resolves `new_striker` from card-side
`bat1_name` / `bat2_name` *after* canonicalization at the
`_build_scorecard` boundary (`score_manager.py:914–933`). However, on
frames where:

1. `bat1_name` / `bat2_name` are `None` (cold-start window or
   post-wicket gap), and
2. `_identify_and_set_striker` is called (it returns early at L2004
   if both are None — but only the matching `elif` branches at
   L2072/L2074 require them; L2071 still writes `self.striker = new_striker`
   even when bat1/bat2 are None),

→ `self.striker` is updated; `self.non_striker` stays at its prior
value. If the prior `self.non_striker` canonicalizes to the same name
as `new_striker` (because the prior value was `"R. SINGH"` raw and
`new_striker` is `"Rinku Singh"` canonical), `_project_active_batters`
will canon both to `"Rinku Singh"` and emit `[WS-SLOT-INVARIANT]`.

This is the specific defect path most consistent with the
**387 fire** PBKS-vs-RR pattern (multi-batter clusters with shared
surnames).

### 3.4 Burst correlation hypotheses

The two windows (387 in 164 min ≈ 2.4 fires/min; 26 in 15 min ≈
1.7 fires/min) suggest a **steady background rate** rather than
event-localised bursts. A steady rate is consistent with
canon-collision (§3.3) firing on every WS frame during a
duplicate-window (~24 frames/sec WS rate × N seconds of duplicate
visibility = O(100 fires per minute of duplicate state)). The
post-restart 15-min number (26 / 15 min ≈ 1.7/min) suggests the
duplicate window is short-lived (≤2–5 sec) but recurs frequently.

§6.5 adds `[SM-SLOT-INVARIANT]` per-write tagging which will let the
next analyzer pass classify the actual fire source distribution.

---

## 4. Decision points (resolved in this audit)

| Question | Resolution |
|---|---|
| **Property setters vs explicit transaction-style methods?** | **Explicit method** (`_set_slot_pair(self, striker, non_striker, *, source: str)`). Property setters hide caller intent and conflict with the existing `_set_inn_slot_with_sm_mirror` pattern (Cluster 1 chose explicit helpers; that direction stands). Properties also can't take a `source=` tag for telemetry. |
| **Interaction with `[SM-FEEDER-SYNC]` (Item 3 Path B)?** | **None.** Item 3 explicitly excluded `striker` / `non_striker` from the feeder set (`dual_broadcaster_substrate_audit.md`); they remain SM-internal. The new helper does *not* mirror to `Scoreboard._inn` — the legacy slot writers (`_post_witnessed_dismissal_slot_rotation`, `update_batter`) own that. SM-side helper is read-by `_project_active_batters` only. |
| **Should `enforce_ws_slot_invariant` backstop remain after Lever 1 ships?** | **Yes — defense-in-depth.** It is the only WS-payload-side guard against canon collisions originating outside SM (e.g. `_inn` fallback edge cases that the `_other_slot` check might miss). After Lever 1 ships and rates drop, the backstop is documented as redundant in *normal operation* but kept as the post-cluster invariant. |
| **Interaction with State Recovery aggregator?** | **None.** Aggregator reads `_inn["striker"]` / `["non_striker"]` (R15 in `striker_path_b_read_audit.md`); SM helper does not touch `_inn`. |
| **Should the helper canonicalize at write time, or trust callers?** | **Canonicalize at write time** (single source of truth). `_build_scorecard` already canonicalizes `card["bat1_name"]` etc., but W3–W7 read directly from SM scalars (`self.bat1_name`) which are themselves stored canonical (Issue-1 fix at L914–L933). The helper's canonicalize call is a no-op on the hot path; on the rare canon-mismatch frame it closes §3.3. Equivalent of the `_build_payload` defense-in-depth canonicalize at L2699/L2701, but at write time. |
| **Atomicity contract for `(None, X)` end-states?** | **Permitted.** W11/W12 leave `(None, survivor)` / `(survivor, None)` as legitimate post-wicket gaps. Helper accepts `None` in either slot; only same-non-None is the violation. |

---

## 5. Per-site categorization summary

| # | Site | Category | Lever 1 fix needed? |
|---|---|---|---|
| W1 | `__init__` | EXTERNAL-DRIVEN | NO — initialization, not rotation |
| W2 | `_clear_per_innings_sm_surface` | END-STATE-NULL-OK | NO — both end `None` |
| W3 | `_init_from_card` (broadcast_striker matches bat1) | END-STATE-DUPLICATE-RISK | **YES** |
| W4 | `_init_from_card` (broadcast_striker matches bat2) | END-STATE-DUPLICATE-RISK | **YES** |
| W5 | `_init_from_card` (broadcast_striker mismatch) | END-STATE-DUPLICATE-RISK | **YES** |
| W6 | `_init_from_card` (no broadcast indicator) | END-STATE-DUPLICATE-RISK | **YES** |
| W7 | `_update_batters` bootstrap | END-STATE-DUPLICATE-RISK | **YES** |
| W8 | `_identify_and_set_striker` | END-STATE-DUPLICATE-RISK | **YES (highest priority)** |
| W9 | `_apply_event` odd-run swap | ATOMIC | NO — post-condition guard only |
| W10 | `_apply_event` over-rollover swap | ATOMIC | NO — post-condition guard only |
| W11 | `_apply_event` wicket — striker out | END-STATE-NULL-OK | NO (post-condition guard catches degenerate survivor) |
| W12 | `_apply_event` wicket — non_striker out | END-STATE-NULL-OK | NO (same) |

**6 sites need migration** (W3–W8); **6 sites are correct as-is** but
all 12 should pass through the post-condition guard (§6.4) after
mutation.

---

## 6. Lever 1 design contract

### 6.1 Files

| File | Change | Size |
|---|---|---|
| `files/score_manager.py` | add `_set_slot_pair` helper (§6.2); migrate W3–W8 to it; add `_assert_slot_invariant` post-condition in `_build_payload` (§6.4); add `[SM-SLOT-INVARIANT]` telemetry tag (§6.5) | +60 LOC, ~30 LOC modified |
| `files/test_recent_fixes.py` | add 8 tests (§6.6) covering helper contract + per-site post-conditions + canon-collision regression + post-condition repair | +120 LOC |
| `files/analyze_match_telemetry.py` | add `SM_SLOT_INVARIANT` regex and rollup row | +5 LOC |
| `files/docs/backlog.md` | mark Lever 1 design ready; cross-reference this audit | docs only |

No changes to:

- `_project_active_batters` (already SM-first; `_other_slot` guard
  unchanged).
- `enforce_ws_slot_invariant` (defense-in-depth backstop unchanged).
- `_build_full_payload_from_state` (Path A snapshot byte-identity
  preserved).
- `Scoreboard._inn` writers (R1–R7 in `striker_path_b_read_audit.md`).

### 6.2 The `_set_slot_pair` helper

```python
def _set_slot_pair(self,
                   striker: str | None,
                   non_striker: str | None,
                   *,
                   source: str) -> None:
    """Atomic slot-pair write with canonicalize + invariant guard.

    Writes ``self.striker`` and ``self.non_striker`` together via
    a single tuple unpack. Both arguments are canonicalized at the
    SM boundary so that a canon-mismatch in caller-supplied raw
    names cannot manufacture a duplicate-slot end state (Issue-1
    defense-in-depth at write time; mirrors the read-time
    canonicalize in ``_build_payload`` L2699-L2702).

    Post-condition: ``striker is None`` or ``non_striker is None``
    or ``canon(striker) != canon(non_striker)``. If the
    post-condition is violated (degenerate scout card, canon
    collision the caller didn't anticipate), the helper logs
    ``[SM-SLOT-INVARIANT]`` with ``source=`` and clears
    ``non_striker`` to ``None`` (matching the WS-side
    ``enforce_ws_slot_invariant`` repair direction so downstream
    ``_project_active_batters`` sees ``(name, None)`` and emits a
    ``_active`` re-seed via fallback, telemetering normally).

    Args:
        striker: new striker name (raw or canonical; canon'd here).
        non_striker: new non-striker name (raw or canonical).
        source: short tag identifying the write site
            (e.g. ``"_init_from_card.broadcast_match_bat1"``,
            ``"_identify_and_set_striker.balls_delta"``,
            ``"_apply_event.wicket.survivor"``). Used for
            telemetry classification per §3.4.
    """
    _s = self._canonicalize_name(striker) or striker
    _ns = self._canonicalize_name(non_striker) or non_striker
    if _s is not None and _ns is not None and _s == _ns:
        log.warn(
            f"[SM-SLOT-INVARIANT] duplicate slots {_s!r} "
            f"(source={source}); clearing non_striker")
        _ns = None
    self.striker, self.non_striker = _s, _ns
```

Tuple-pack on the last line means there is no observable
intermediate state even under future async reentrancy.

### 6.3 Per-site migration

#### W3–W6 (`_init_from_card`, L1289–L1302)

Replace the four-branch if/elif/else with a single block that
chooses (s, ns) and calls the helper once:

```python
# Before
if card.get("broadcast_striker"):
    ind = card["broadcast_striker"].lower()
    if self.bat1_name and ind in self.bat1_name.lower():
        self.striker = self.bat1_name
        self.non_striker = self.bat2_name
    elif self.bat2_name and ind in self.bat2_name.lower():
        self.striker = self.bat2_name
        self.non_striker = self.bat1_name
    else:
        self.striker = self.bat1_name
        self.non_striker = self.bat2_name
else:
    self.striker = self.bat1_name
    self.non_striker = self.bat2_name

# After
_s, _ns = self.bat1_name, self.bat2_name
if card.get("broadcast_striker"):
    ind = card["broadcast_striker"].lower()
    if self.bat2_name and ind in self.bat2_name.lower() \
            and not (self.bat1_name and ind in self.bat1_name.lower()):
        _s, _ns = self.bat2_name, self.bat1_name
self._set_slot_pair(_s, _ns, source="_init_from_card")
```

Behavior preserved for non-degenerate cards; degenerate
`bat1_name == bat2_name` cards are now caught and `non_striker`
cleared with `[SM-SLOT-INVARIANT] source=_init_from_card`.

#### W7 (`_update_batters` bootstrap, L1890–L1892)

```python
# Before
if not self.striker:
    self.striker = self.bat1_name
    self.non_striker = self.bat2_name

# After
if not self.striker:
    self._set_slot_pair(self.bat1_name, self.bat2_name,
                        source="_update_batters.bootstrap")
```

#### W8 (`_identify_and_set_striker`, L2068–L2075)

```python
# Before
if new_striker and new_striker != self.striker:
    log.info(f"[STRIKER] method={method} striker={new_striker} "
             f"(was={self.striker})")
    self.striker = new_striker
    if new_striker == self.bat1_name:
        self.non_striker = self.bat2_name
    elif new_striker == self.bat2_name:
        self.non_striker = self.bat1_name

# After
if new_striker and new_striker != self.striker:
    log.info(f"[STRIKER] method={method} striker={new_striker} "
             f"(was={self.striker})")
    if new_striker == self.bat1_name:
        _ns = self.bat2_name
    elif new_striker == self.bat2_name:
        _ns = self.bat1_name
    else:
        # neither bat-slot matches: explicitly compute partner
        # rather than leaving non_striker at its prior value.
        # Prior value was likely the previous striker; if that
        # canonicalizes to new_striker we'd produce a duplicate
        # (the §3.3 path). Choose the other bat-slot if
        # available; else clear.
        _ns = (self.bat2_name
               if (self.bat1_name and new_striker == self.bat1_name)
               else self.bat1_name
               if self.bat2_name
               else None)
    self._set_slot_pair(new_striker, _ns,
                        source=f"_identify_and_set_striker.{method}")
```

The explicit fallback in the `else` branch is the **single most
impactful change** in this design — it closes the canon-collision
mode hypothesised in §3.3.

#### W9, W10 (atomic swaps, L2391/L2393)

**No code change required** for atomicity. They already use tuple
swap. The post-condition in §6.4 catches the rare case of pre-existing
duplicate carrying through the swap.

Optional cosmetic upgrade (NOT required for Lever 1):

```python
# Optional, for telemetry uniformity:
self._set_slot_pair(self.non_striker, self.striker,
                    source="_apply_event.odd_runs_swap")
```

This makes every slot mutation traceable in
`[SM-SLOT-INVARIANT]` rollups by source. Defer to a follow-up
documentation PR — not required for rate reduction.

#### W11, W12 (wicket dismissal, L2480–L2485)

```python
# Before
if best_dismissed == self.striker:
    self.striker = None  # incoming will be slotted later
    self.non_striker = survivor
elif best_dismissed == self.non_striker:
    self.non_striker = None
    self.striker = survivor

# After
if best_dismissed == self.striker:
    self._set_slot_pair(None, survivor,
                        source="_apply_event.wicket.striker_out")
elif best_dismissed == self.non_striker:
    self._set_slot_pair(survivor, None,
                        source="_apply_event.wicket.non_striker_out")
```

Per §2.1 these are END-STATE-NULL-OK; the migration is for
telemetry uniformity and to catch the degenerate survivor case
(survivor == dismissed-and-still-in-card after a stale strip read).

#### W2 (`_clear_per_innings_sm_surface`)

**No change.** Both writes are to `None`; helper would short-circuit
trivially. Keep the explicit clears for grep-ability in the reset
path.

### 6.4 Post-condition guard at `_build_payload`

`_build_payload` at L2692–L2702 already canonicalizes
`self.striker` / `self.non_striker` at output. Add an
invariant-and-repair pass in the same block:

```python
def _build_payload(self, event: dict | None = None) -> dict:
    _striker_out = (self._canonicalize_name(self.striker)
                    or self.striker)
    _non_striker_out = (self._canonicalize_name(self.non_striker)
                        or self.non_striker)
    # Lever 1 post-condition: SM payload must never carry duplicate
    # active slots. Mirrors enforce_ws_slot_invariant on the
    # WS-payload side (test_pipeline.py:2230). If a write site
    # bypassed _set_slot_pair (e.g. external monkey-patch in tests
    # or a future code path that forgets to use the helper), repair
    # at output and emit [SM-SLOT-INVARIANT-PAYLOAD].
    if (_striker_out is not None
            and _non_striker_out is not None
            and _striker_out == _non_striker_out):
        log.warn(
            f"[SM-SLOT-INVARIANT-PAYLOAD] duplicate slots "
            f"{_striker_out!r} at payload boundary; clearing "
            f"non_striker (event={event.get('type') if event else None})")
        _non_striker_out = None
    # ... rest of _build_payload unchanged ...
```

This is **defense-in-depth** for any future write site that bypasses
the helper. Test count contribution: 1 (post-condition fires when SM
slots are externally set to a duplicate).

### 6.5 Telemetry

Two new tags:

- **`[SM-SLOT-INVARIANT]`** (per-write) — emitted by `_set_slot_pair`
  when the helper had to repair a same-non-None pair before writing.
  Includes `source=` for §3 classification.
- **`[SM-SLOT-INVARIANT-PAYLOAD]`** (per-payload) — emitted by
  `_build_payload` post-condition when a duplicate reached the
  payload boundary despite the helper. **Should be zero** in normal
  operation; non-zero indicates a bypass site to find and migrate.

Analyzer changes (`analyze_match_telemetry.py`):

```python
SM_SLOT_INVARIANT = re.compile(r"\[SM-SLOT-INVARIANT\]\s+duplicate slots")
SM_SLOT_INVARIANT_PAYLOAD = re.compile(
    r"\[SM-SLOT-INVARIANT-PAYLOAD\]\s+duplicate slots")
```

Add to `PENDING_VALIDATION_PATTERNS`:

```python
("[SM-SLOT-INVARIANT] (Lever 1 helper repair)", SM_SLOT_INVARIANT),
("[SM-SLOT-INVARIANT-PAYLOAD] (Lever 1 backstop)",
 SM_SLOT_INVARIANT_PAYLOAD),
```

The combined ratio of `[SM-SLOT-INVARIANT]` to `[WS-SLOT-INVARIANT]`
fires after Lever 1 ships is the **direct measurement** of Lever 1's
upstream coverage — see §7.4.

### 6.6 Tests

Add 8 tests to `test_recent_fixes.py`:

1. **`test_sm_set_slot_pair_basic_distinct_pair`** —
   helper writes `(A, B)` cleanly; both fields updated.
2. **`test_sm_set_slot_pair_canonicalizes_inputs`** —
   helper writes raw `"R. SINGH"` / `"Rinku"` and SM scalars come
   out as `"Rinku Singh"` / `"Rinku Singh"` BEFORE the duplicate
   guard fires; guard repairs to `("Rinku Singh", None)` and emits
   `[SM-SLOT-INVARIANT]`.
3. **`test_sm_set_slot_pair_allows_none_pairs`** —
   `(None, None)`, `(A, None)`, `(None, B)` all allowed; no
   `[SM-SLOT-INVARIANT]` emission.
4. **`test_sm_init_from_card_degenerate_card_no_duplicate`** —
   cold-start with `bat1_name == bat2_name` (degenerate scout card);
   SM end state is `(name, None)` not `(name, name)`; tag emitted
   with `source=_init_from_card`.
5. **`test_sm_identify_and_set_striker_canon_collision_no_duplicate`** —
   reproduces §3.3: `_identify_and_set_striker` flips striker via
   broadcast indicator while `non_striker` raw value canonicalizes
   to the same name; SM end state is `(name, None)` (or
   `(name, partner_from_explicit_else)`); tag emitted with
   `source=_identify_and_set_striker.broadcast_first_name`.
6. **`test_sm_apply_event_wicket_helper_telemetry`** —
   wicket on striker; `_set_slot_pair(None, survivor,
   source="_apply_event.wicket.striker_out")` invoked; SM end state
   `(None, survivor)`; no `[SM-SLOT-INVARIANT]`.
7. **`test_sm_build_payload_postcondition_repairs_external_duplicate`** —
   directly set `sm.striker = "X"; sm.non_striker = "X"` (bypassing
   helper); call `sm._build_payload()`; payload `striker == "X"`,
   `non_striker is None`; `[SM-SLOT-INVARIANT-PAYLOAD]` emitted.
8. **`test_sm_apply_event_atomic_swap_preserves_distinctness`** —
   pre-state `(A, B)`, run odd-run swap; end state `(B, A)`; no
   `[SM-SLOT-INVARIANT]` (atomic; helper not invoked).

Tests must:

- Pass under both `shadow=True` and `shadow=False` (helper is
  shadow-agnostic).
- Not modify Path A WS-payload byte-identity sentinel
  (`test_path_b_low_risk_batch_path_a_regression_signature_match`).
- Not depend on `[WS-SLOT-INVARIANT]` rate (those are integration
  validation, not unit tests).

Expected test count delta: **+8** (current ≈685 → 693 PASS).

---

## 7. Predicted `[WS-SLOT-INVARIANT]` rate reduction

### 7.1 Per-fix estimate

| Fix | Targets fire pattern (§3.2) | Estimated reduction | Confidence |
|---|---|---|---|
| W8 explicit `else` partner fallback | "Sustained duplicate over multiple frames" + canon-collision (§3.3) | **40–60%** of fires | MEDIUM-HIGH |
| W3–W6 degenerate-card guard | "Cold-start re-entry duplicate" | **5–15%** of fires | LOW (rare event-class) |
| W7 bootstrap guard | "New-batter arrival burst" | **10–20%** of fires | MEDIUM |
| W11/W12 explicit `_set_slot_pair` | "Wicket-frame duplicate" (already mostly caught by `_other_slot` guard in `_project_active_batters`) | **0–5%** of fires | LOW (helper change is mostly telemetry, not behaviour) |
| `_build_payload` post-condition | Defense-in-depth catch of bypasses | **0%** *expected* (zero bypasses) | n/a |

### 7.2 Combined estimate

Fixes overlap (the same canon-collision frame can be caught by W8's
`else` branch and by `_build_payload`'s post-condition). Conservative
combined estimate accounting for overlap and double-counting:

**Predicted reduction: 50–75% of `[WS-SLOT-INVARIANT]` fires.**

Mid-point: **~60%**. PBKS-vs-RR window 387 fires → projected
**~150 fires** post-Lever-1. Post-restart 26 → projected **~10 fires**.

Confidence: **MEDIUM**. The W8 fix in particular addresses the
hypothesised dominant driver (§3.3) but the hypothesis is unverified
without per-source telemetry. The new `[SM-SLOT-INVARIANT]` tag
(§6.5) provides exactly that telemetry; first live run after Lever 1
will calibrate the prediction.

### 7.3 Lower-bound (pessimistic) estimate

If §3.3 turns out NOT to be the dominant driver and the fires are
mostly cause (C) (WS-SCRUB rebuild collision when only one batting
name is active — outside SM's reach), Lever 1 reduces fires by only
**~10–15%**. Lower bound: **~330 fires** in the PBKS-vs-RR window.

The Lever 1 design is still worth shipping in this scenario for the
architectural-correctness reasons (single source of truth for slot
writes, telemetry per source) — but the headline rate-reduction win
moves to a future Lever 3 (WS-SCRUB rebuild logic).

### 7.4 Direct measurement after ship

Post-Lever-1 telemetry will produce three numbers:

- `N_helper_repair`: `[SM-SLOT-INVARIANT]` fires at the helper
  boundary (caught upstream of `_project_active_batters`).
- `N_payload_repair`: `[SM-SLOT-INVARIANT-PAYLOAD]` fires at the
  SM payload boundary (would have leaked without §6.4).
- `N_ws_invariant`: `[WS-SLOT-INVARIANT]` fires post-Lever-1
  (residual at the WS-payload boundary).

The three sum, in expectation, to roughly the pre-Lever-1
`[WS-SLOT-INVARIANT]` count: every fire becomes one of three caught
events. Lever 1 effectiveness =
`(N_helper_repair + N_payload_repair) / pre_fire_count`.
A live calibration window of ~1 hour suffices.

### 7.5 Residual fire sources Lever 1 will NOT address

- **Cause (C) WS-SCRUB rebuild collision** (§0.1). When the
  `batting_card` collapses to a single `status="batting"` entry
  (e.g. between a wicket and the next batter's first ball), the
  WS-side `[WS-SCRUB]` loop in `test_pipeline.py:4914` lifts the
  same surviving name into both slots, and
  `enforce_ws_slot_invariant` then repairs. SM cannot prevent this
  because the trigger is downstream of every SM mutation. **Estimated
  residual: 5–10% of total fires.**
- **Cause (B) canon collision originating in `_inn`** (rare; Fix 5
  prevents `_inn` collisions on the writer side, but a frame where
  `_inn["striker"]` and `_inn["non_striker"]` were each accepted in
  separate frames before canonicalisation alignment can briefly
  hold two raw names that canon to one). **Estimated: <1%.**
- **Future WS-PROJECTION-GAP edge cases** if `_project_active_batters`
  ever loses the `_other_slot` guard (regression risk; not a
  current driver).
- **External writer bypass** of `_set_slot_pair` (e.g. tests, future
  code paths, monkey-patches). Caught by `_build_payload`
  post-condition (§6.4) but not silenced.

---

## 8. Migration order recommendation

### 8.1 Recommended PR sequence

1. **PR 1 — helper + post-condition + telemetry (no callsite migration).**
   - Add `_set_slot_pair` (§6.2).
   - Add `_build_payload` post-condition (§6.4).
   - Add analyzer regexes (§6.5).
   - Add tests 1, 3, 7, 8 (helper contract + post-condition).
   - **Expected `[WS-SLOT-INVARIANT]` change:** none (no callsite
     uses the helper yet). PR validates the helper's contract in
     isolation.
   - Risk: **VERY LOW**. Pure addition.
   - Estimated diff: +50 LOC source, +60 LOC tests.

2. **PR 2 — migrate W8 (highest-yield).**
   - Replace `_identify_and_set_striker` slot writes with
     `_set_slot_pair` per §6.3 W8 (including explicit `else`
     branch).
   - Add tests 2, 5 (canonicalize + canon-collision).
   - **Expected reduction:** 40–60% of fires (per §7.1).
   - Risk: **LOW** — the explicit `else` branch is the only
     behavior-changing line; rest is mechanical.

3. **PR 3 — migrate W3–W7 (init paths).**
   - Replace `_init_from_card` and `_update_batters` bootstrap with
     `_set_slot_pair` per §6.3 W3–W7.
   - Add test 4 (degenerate-card guard).
   - **Expected incremental reduction:** 15–35% of remaining fires.
   - Risk: **LOW** — cold-start path is well-tested already
     (`test_pipeline.py:_make_sb_for_*` + recent fixes coverage).

4. **PR 4 — migrate W11/W12 (wicket telemetry uniformity).**
   - Replace `_apply_event` wicket dismissal with `_set_slot_pair`.
   - Add test 6.
   - **Expected reduction:** 0–5% (mostly telemetry, not behavior).
   - Risk: **VERY LOW**.

5. **(Optional) PR 5 — W9/W10 telemetry uniformity (cosmetic).**
   - Replace odd-run / over-rollover swaps with `_set_slot_pair`
     for source-tag traceability.
   - Risk: **VERY LOW**. No reduction expected (atomic swap
     unchanged); test count change: 0.

### 8.2 Rationale for not bundling

The audit explicitly recommends a 4-PR sequence (not a single PR)
because:

- **Per-PR rate measurement.** Each PR's `[WS-SLOT-INVARIANT]`
  delta is independently measurable (one live match window per PR)
  — confirms the per-fix estimates in §7.1 and either validates or
  refutes the canon-collision dominance hypothesis (§3.3) before
  the harder PRs land.
- **Rollback granularity.** If PR 2 over-corrects (e.g. the
  explicit `else` branch breaks a test fixture that depended on
  `non_striker` staying at prior value), rollback is one commit
  rather than a wholesale revert.
- **Test-count predictability.** Each PR adds 1–3 tests; reviewer
  can audit the expected count change against actual.

### 8.3 Stop-and-route-back conditions

The execution agent should stop and route back if:

- **(a) `_project_active_batters` would need a change.** It is
  canonical; any required change is out of Lever 1 scope.
- **(b) A new SM write site is discovered** that this audit didn't
  enumerate. Likely buried inside `_post_witnessed_dismissal_slot_rotation`
  or a Cluster 1 hot path; route to the audit author.
- **(c) Path A snapshot byte-identity check fails** after PR 2
  ships. The W8 explicit `else` is the only behavior-changing line
  that could affect WS payload bytes; if it does, the canon-collision
  hypothesis (§3.3) is wrong and the design needs revisiting.
- **(d) `[SM-SLOT-INVARIANT-PAYLOAD]` fires non-zero** after all
  callsites are migrated. There's a bypass site Lever 1 missed.

---

## 9. Risk assessment

| Risk | Severity | Likelihood | Mitigation |
|---|---|---|---|
| Helper inadvertently changes WS-payload byte-identity | HIGH | LOW | Path A snapshot test runs in CI; PR 1 (helper-only) cannot change bytes by construction |
| W8 explicit `else` clears `non_striker` on a frame where prior value was correct | MEDIUM | MEDIUM | Test 5 reproduces the failure mode; review commit shows only the canon-collision branch is changed |
| Degenerate-card guard (W3–W6) suppresses a card we should have warned about | LOW | LOW | `[SM-SLOT-INVARIANT] source=_init_from_card` IS the warning |
| `[SM-SLOT-INVARIANT-PAYLOAD]` indicates a bypass site we missed | MEDIUM | LOW | Stop-and-route-back §8.3(d); enumerate bypass site in next audit |
| `enforce_ws_slot_invariant` deprecation pressure after Lever 1 | LOW | LOW | Decision in §4 keeps it as defense-in-depth permanently |
| Test count regression | LOW | LOW | +8 tests; expected ≈685 → 693 PASS / 0 FAIL |
| Migration order order-dependence | LOW | LOW | PRs are decoupled; PR 1 is a strict superset of "do nothing" |

**Overall risk:** **LOW** with the 4-PR sequence in §8.

### 9.1 Rollback

Each PR is one commit; revert restores prior behaviour exactly. Tests
under `test_recent_fixes.py` are the safety net. The helper itself
is purely additive in PR 1; reverting any later PR removes the
caller migration but leaves the helper available.

---

## 10. Cross-references

- **`files/docs/investigations/striker_path_b_read_audit.md`** — Lever
  1 source; §3 (`[WS-SLOT-INVARIANT]` correlation), §8 (predicted rate
  reduction attributed here).
- **`files/docs/investigations/get_broadcast_state_path_b_audit.md`**
  — Lever 2 audit; shipped 2026-04-29; §7.2 enumerates the three
  duplicate-source causes that this audit's §0.1 inherits.
- **`files/docs/investigations/build_full_payload_extraction_design.md`**
  — extraction prerequisite; §5.4 explicitly attributes the
  remaining `[WS-SLOT-INVARIANT]` rate to "SM rotation atomicity
  (Lever 1, follow-up)".
- **`files/docs/investigations/dual_broadcaster_substrate_audit.md`**
  — Item 3 scoping rationale; striker / non_striker excluded from
  Path B LOW-risk batch (bcs of the dedicated audit captured here).
- **`files/docs/investigations/scorer_invariants_categorization.md`**
  §10.1 — Item 2 PR 1 backstop reads via `_canonical_active_slot`
  (already SM-first); unaffected by this audit.

---

## 11. Files

- **New:** `files/docs/investigations/sm_rotation_atomicity_design.md`
  (this document).
- **No code changes in this task.** The 4-PR sequence in §8 is the
  executable outcome; this audit is its design contract.

---

## 12. Appendix: full read inventory of `self.striker` / `self.non_striker`

For completeness — these are *reads* (not Lever 1 sites) but are
documented here so the next audit doesn't have to rediscover them.

| # | Function | Line | Read pattern | Notes |
|---|---|---|---|---|
| RR1 | `_identify_striker` (state fallback) | 2162 | `return self.striker, self.non_striker, ...` | event-inference path; consumed by `_apply_event` only |
| RR2 | `_apply_event` wicket P3 fallback | 2441/2449 | `event.get("striker") or self.striker` | dismissed-batter resolution last resort |
| RR3 | `_build_payload` canonicalize | 2699/2701 | `self._canonicalize_name(self.striker)` etc. | output canonicalize; §6.4 adds the post-condition here |
| RR4 | `_update_batters` bootstrap guard | 1890 | `if not self.striker:` | gate condition only; not a duplicate driver |
| RR5 | `_apply_event` wicket dispatch | 2480/2483 | `if best_dismissed == self.striker:` | branch selection; not a write |
| RR6 | `_apply_event` strike rotation tuple | 2391/2393 | RHS of swap | atomic with the LHS write (W9/W10) |
| RR7 | `_identify_and_set_striker` flip guard | 2068 | `if new_striker and new_striker != self.striker:` | gate condition |
| RR8 | `_identify_and_set_striker` log line | 2069/2070 | f-string `was={self.striker}` | logging only |
| RR9 | `_init_from_card` adoption | 1292/1295/1298/1301 | RHS of writes (uses `self.bat1_name`/`bat2_name`, not `self.striker`) | source for W3–W6 writes |

No additional read sites need migration — they all read end state and
are consistent with the post-helper invariant.
