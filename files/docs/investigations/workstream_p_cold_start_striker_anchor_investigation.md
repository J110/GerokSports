# Workstream P — Cold-start striker-anchor swap investigation (step-1)

**Status.** Step-1 closed; leading candidate identified;
cohort-closure verification UNIFIED (single initial anchor
decision propagates deterministically through all ~50 swap
fields).

**Trigger.** WS-O.b step-3 empirical replay at `c275807` confirmed
SPLIT verdict — striker-anchor swap did NOT cascade-close
alongside the WARM-mode score cascade. Cohort enumeration: ~50
swap fields across balls 0.5+ on `dckkr_diff_post_ws_o_b_baseline.md`.
Per-batter runs / balls / fours / sixes are CORRECT on the swapped
slot (identity tracking works after initial anchor); only the
SLOT IDENTITY (which name is striker vs non-striker) is wrong.

**Pre-screen verdict.** GREEN — PIPELINE-DIRECT per S28 (SM
cold-start opener-selection logic at `score_manager.py:_accept_initial`
plus snapshotter input-shape coupling at
`tests/test_pipeline_captured_replay.py:extracted_to_frame_input`).

**Outcome.** Static-falsification chain converges on **QA + QE
composite — SM `_accept_initial` defaults to `bat1=striker`
when no explicit `*-marker` asterisk signal is present, AND the
snapshotter's `extracted_to_frame_input` defaults
`broadcast_striker = bat1.name` even when neither bat1 nor bat2
has Scout-detected striker flag**. The composite anchors
whichever opener Scout happens to put in the bat1 row at the
cold-start frame, regardless of cricket-physics truth. F1 fix
(2026-05-20, commit `437d952`) is structurally correct WHEN
broadcast_striker carries an explicit *-marker; the cascade
root is the F1 fix's DEFAULT BRANCH (`cold_start_no_indicator`
at `score_manager.py:3521-3524`) firing on the snapshotter's
asterisk-less default.

---

## §1 Empirical anchor — cohort enumeration with per-frame trace

Per `files/tests/baselines/dckkr_diff_post_ws_o_b_baseline.md`
striker / non_striker name swap fields (sampled from §2 + §4):

| Ball | Pipeline striker | GT striker | Pipeline non | GT non |
|---|---|---|---|---|
| 0.2 | (only non shown) | (only striker) | Rahul | — |
| 0.3 | Rahul | — | (only striker shown) | — |
| 0.5 | **Rahul** | **Nissanka** | Nissanka | Rahul |
| 0.6 | Nissanka | Rahul | Rahul | Nissanka |
| 1.2 | Nissanka | Rahul | Rahul | Nissanka |
| 1.5 | Nissanka | Rahul | Rahul | Nissanka |
| 1.6 | Rahul | Nissanka | Nissanka | Rahul |
| 2.3 | Rahul | Nissanka | Nissanka | Rahul |
| 2.4 | Rahul | Nissanka | Nissanka | Rahul |
| 2.5 | Rahul | Nissanka | Nissanka | Rahul |
| 3.4 | Nissanka | Rahul | Rahul | Nissanka |
| 3.5 | Nissanka | Rahul | Rahul | Nissanka |
| 3.6 | Rahul | Nissanka | Nissanka | Rahul |

Pattern: **every ball with a name divergence has pipeline-name
and GT-name swapped**, with per-batter runs/balls/fours/sixes
matching the GROUND-TRUTH-OPPOSITE slot (e.g. at 0.5 pipeline
non_striker_runs=5 matches GT striker_runs=5; pipeline
striker_runs=1 matches GT non_striker_runs=1). The internal
identity ledgers track CORRECTLY post-anchor; only the
striker/non slot labels are mirrored.

**Total cohort: ~50 swap fields** spanning ~13 distinct balls.

**Locus of root**: ball 0.5 is the first frame with explicit
swap signature (0.2 + 0.3 show only single-batter visibility
in GT, so swap is undetectable). Cold-start exit occurred
between frames 0 and the first commit appearing in the
snapshot at 0.5 (post-WS-O.b: 31 snapshots from 264 frames,
implying cold-start exits early).

---

## §2 Cold-start opener-selection code path

The cold-start striker anchor commits via the
**`_accept_initial`** path at `score_manager.py:3397+`. Called
from multiple cold-start exit sites (per grep at
`_accept_initial` occurrences `:2944, :3015, :3054, :3066,
:3110`). On entry, `_accept_initial` reads `card.bat1_name`
and `card.bat2_name` from the COLD_START candidate
(populated by Scout's per-batter row reads).

The striker pointer is set inside the **F1 fix block** at
`score_manager.py:3498-3524` (per the comment at :3489-3497
referencing "F1 fix (2026-05-20, B-ε)"):

```python
if self.striker is None:
    _strip_bc = card.get("broadcast_striker")
    if _strip_bc:
        ind = _strip_bc.lower().strip()
        _b1_first = ((self.bat1_name or "").split() or [""])[0].lower()
        _b2_first = ((self.bat2_name or "").split() or [""])[0].lower()
        if _b1_first and _b2_first and _b1_first != _b2_first:
            if _b1_first in ind and _b2_first not in ind:
                self._set_slot_pair(self.bat1_name, self.bat2_name,
                                    source="init_from_card.striker")
            elif _b2_first in ind and _b1_first not in ind:
                self._set_slot_pair(self.bat2_name, self.bat1_name,
                                    source="init_from_card.non")
            else:
                self._set_slot_pair(self.bat1_name, self.bat2_name,
                                    source="init_from_card.combined_ambiguous")
        else:
            self._set_slot_pair(self.bat1_name, self.bat2_name,
                                source="init_from_card.combined_same_first")
    else:
        self._set_slot_pair(self.bat1_name, self.bat2_name,
                            source="cold_start_no_indicator")  # :3522-3524
```

**Default branches (5 in total)** all end with one of two
outcomes:
- `bat1 = striker, bat2 = non` (4 of 5 branches).
- `bat2 = striker, bat1 = non` (1 of 5 branches — only when
  bat2's first name unambiguously matches the indicator).

When `_strip_bc is None` or matches bat1's first name (via the
default), the result is **always `bat1 = striker`**.

`_set_slot_pair` is the §15-fence canonical write path (per
`apply_striker_identity_resolved` family). Confirmed canonical
writer; no non-canonical surface bypasses this.

---

## §3 `BATTING_SQUAD` ordering verification

Per `files/tests/test_pipeline_captured_replay.py` (the
fixture builder consumed by both L2 + the snapshotter):

```python
BATTING_SQUAD = [
    "Pathum Nissanka", "KL Rahul", ...
]
```

(Confirmed from the snapshotter's `build_sm` call at
`tests/test_pipeline_captured_replay.py:61-81` per
WS-N N1.2's L2 reading.)

Per Cricbuzz GT (`files/tests/fixtures/dckkr_innings_1_-
cricbuzz_commentary.md` → ingester output at
`files/tests/fixtures/dckkr_ground_truth_ui_snapshots.jsonl`
row 1):
```
{"over_ball": "0.1", "striker_name": "Nissanka", ...,
 "non_striker_name": null, ...}
```

GT shows Nissanka on strike facing ball 1; non-striker null
(Cricbuzz ingester only records the on-strike batter for the
first delivery). **`BATTING_SQUAD[0] = Nissanka` is correct
per ground-truth opener convention.**

**QD verdict: FALSIFIED.** Squad source is correctly ordered.
The defect is downstream in the opener-selection logic, not
in squad ingestion.

---

## §4 `broadcast_striker` primitive analysis at cold-start

Two divergent sources of `broadcast_striker`:

### Production (test_pipeline.py main loop)
Per `score_manager.py:3491` comment: "consume the canonical
`broadcast_striker` field (populated from Scout's *-marker
detection via test_pipeline.py:1783 + :13823 +
score_manager.py:1616)". In production, `broadcast_striker` is
populated **only when Scout's `*` asterisk marker is detected
on a specific batter row**. When no asterisk is detected (early
pre-match graphics, ad-occluded frames, OCR failure on the
asterisk), `broadcast_striker` is **None / null**.

### Snapshotter (tests/test_pipeline_captured_replay.py:113-117)
```python
bat1_striker = bool(bat1.get("striker"))
broadcast_striker = (
    bat1.get("name") if bat1_striker
    else (bat2.get("name") if bat2.get("striker") else bat1.get("name"))
)
```

The snapshotter's fallback at line 117 **DEFAULTS
`broadcast_striker = bat1.name`** when neither bat1 nor bat2
has Scout-detected striker flag. This is **divergent from
production semantics** — production passes `None`; snapshotter
passes `bat1.name`.

**Cascade chain**:
1. Scout's cold-start frames have neither bat1 nor bat2 with
   asterisk detected (pre-match or asterisk OCR fails).
2. Snapshotter's `extracted_to_frame_input` falls through to
   `broadcast_striker = bat1.name` (line 117 default).
3. `_accept_initial` reads `card.broadcast_striker = bat1.name`
   (NOT None).
4. F1 algorithm at `:3498` enters `if _strip_bc:` branch (truthy).
5. First-name matching: `_b1_first` matches the indicator
   (it IS bat1.name).
6. Slot pair set: `bat1 = striker, bat2 = non`.
7. **Whoever Scout put in the bat1 row at the cold-start
   commit frame becomes the striker for the rest of the
   innings** (until the first wicket).

If Scout's cold-start frame had `bat1 = Rahul` (broadcast row
order at that moment OR OCR row-attribution error), pipeline
anchors Rahul as striker. GT says Nissanka. Cascade root.

**Even with broadcast_striker passthrough None corrected**: the
fallback in `_accept_initial` at `:3522-3524` (`else`
`cold_start_no_indicator`) still sets `bat1 = striker`. So
the SM-side default also anchors to whichever name Scout put
in bat1.

---

## §5 F1 fix context cross-reference

Per HANDOFF: F1 (commit `437d952`, 2026-05-20) was the
**B-ε cascade-closure fix** that addressed the
"broadcast-vs-deterministic striker override at WICKET-ATTRIB"
defect class. F1 added the `_attribute_dismissed_with_broadcast_override`
function (per the WICKET-ATTRIB test gate at
`tests/test_wicket_attrib_broadcast_override.py`). F1's
"cascade-closure" closed multiple WICKET-attribution bug classes
via the single-name canonical-override logic.

The code block at `score_manager.py:3489-3524` references "F1
fix" in its comment but is **adjacent**, not F1 itself:
- F1's canonical site is `_attribute_dismissed_with_broadcast_override`
  at `score_manager.py:3154`.
- The `_accept_initial` block at `:3489-3524` is the **cold-
  start sibling** — same pattern (broadcast first-name matching)
  but applied at cold-start initialization rather than wicket
  attribution.

**F1-adjacent**, not F1-internal. The cold-start anchor uses
the same matching technique but the DEFAULT BRANCH (lines
3521-3524 `else` → `bat1 = striker`) is unique to the
cold-start path and is the root WS-P investigates.

F1's WICKET-ATTRIB context already has the `apply_striker_event`
canonical write path; cold-start init has `_set_slot_pair`
which is structurally similar but distinct. WS-P's fix doesn't
touch F1's WICKET site.

---

## §6 Hypothesis enumeration

| Hypothesis | Verdict | Notes |
|---|---|---|
| QA: Scout's row-attribution at cold-start misorders openers | **LEADING (composite with QE)** | Cascade entry point at the source of `bat1` ordering. SM-side defense possible. |
| QB: Broadcast_striker correctly identifies but SM ignores | FALSIFIED | F1 algorithm uses broadcast_striker correctly WHEN present and unambiguous. The match-by-first-name logic works. |
| QC: F1 fix introduced inverted convention | FALSIFIED | F1's matching logic is structurally correct. The cascade root is in the DEFAULT branch (`cold_start_no_indicator`), not in F1's match logic. |
| QD: BATTING_SQUAD source wrong | FALSIFIED | Squad order [Nissanka, Rahul] matches GT opener convention. |
| QE: Per-batter status seeding produces non-deterministic anchor | **CONFIRMED (composite with QA)** | Both openers seeded `status="batting"` with no striker designation; SM anchor depends on whichever opener Scout puts in bat1 at cold-start. |
| QF: Cohort split | FALSIFIED | All ~50 swap fields trace to the single initial anchor decision at cold-start; subsequent rotations are deterministic and propagate the initial swap. |

**Leading candidate: QA + QE composite.** SM defaults to `bat1
= striker` regardless of whether the broadcast asterisk
unambiguously confirms which name should be striker.

### §7.2 audit on leading candidate

| Gate | Status | Rationale |
|---|---|---|
| 1 (defect-class fit) | PASS | Explains the entire ~50 swap cohort via single initial anchor + deterministic propagation. |
| 2 (backward-compat) | PASS (conditional) | Fix surface must NOT regress legitimate first-asterisk cases (where Scout DOES detect the asterisk and correctly identifies striker). The F1 branch at :3498-3520 handles those; only the default branch at :3521-3524 needs hardening. |
| 3 (fix-surface attribution) | PASS | PIPELINE-DIRECT. Two-site composite:<br>(a) **SM-side**: `score_manager.py:3521-3524` — replace `cold_start_no_indicator` default with deferred-anchor logic (don't commit striker pointer when no explicit asterisk signal).<br>(b) **Snapshotter-side**: `tests/test_pipeline_captured_replay.py:113-117` — pass None when no Scout `striker` flag (mirror production semantics). |
| 4 (sub-finding promotion) | DEFER | No new S-number promoted at step-1. Possible S31 candidate at step-2: "broadcast-asterisk-absence-defer pattern" applicable to other cold-start identity-anchor decisions (bowler-anchor analog at `:3486` may have the same pattern). |
| 5 (cohort enumeration completeness) | PASS | ~50 swap fields cataloged; QF cohort-split ruled out. |
| 6 (test obligation) | OPEN at step-2 | L1.5 cases needed: P-1 SM defers anchor when broadcast_striker is None; P-2 SM defers anchor when broadcast_striker defaults to bat1.name without explicit asterisk metadata; P-3 snapshotter passes None per production semantics; P-4 first asterisk-detected frame correctly anchors striker. |
| 7 (cross-fixture verification) | DEFER to step-3 | Re-run snapshotter; compare per-surface deltas. Expected: ~50 swap fields → 0. |

---

## §8 Predicted-flip table for step-2

| Cohort | Pre-WS-P | Post-WS-P (predicted) | Predicted flip |
|---|---|---|---|
| Striker-anchor swap (~50 fields, ~13 balls) | ~50 | 0 or near-0 | CLOSE (single root + deterministic propagation) |
| Per-batter runs / balls / fours / sixes attribution | swapped slot | correct slot | CLOSE-TIED (label flip propagates to per-batter labels) |
| E2-phantom-runs | 3 (post-WS-O.b) | 3 (independent root; WS-O.c residue) | UNCHANGED |
| Conservation invariants | 5 (post-WS-O.b) | 5 | UNCHANGED |
| this_over_tokens negative tokens | 0 (post-WS-O.b PE closure) | 0 | UNCHANGED (regression-guard) |
| L2 ledger | 30 PASS | 30 PASS | UNCHANGED (load-bearing) |
| L1.5 total | 86 (post-WS-O.b) | 90 (4 new cases) | regression-guard |
| Other 15 surfaces | (post-WS-O.b baselines) | UNCHANGED | regression-guard |

---

## §9 Sub-findings

**No new sub-findings promoted at step-1.** Two candidates
for step-2:

- **S31 candidate (broadcast-asterisk-absence-defer pattern)**.
  When Scout's asterisk-detection signal is absent, the canonical
  identity-anchor write path should DEFER rather than default
  to a positional anchor. Applies symmetrically to bowler-anchor
  at `_accept_initial:3486` (`self.bowler_name = card.get(
  "bowler_name")`), which may have the same pattern (Scout's
  bowler row may not correspond to the current bowler if
  the broadcast shows a stand-in or stale read).

- **S32 candidate (snapshotter-vs-production semantic
  divergence)**. The snapshotter's `extracted_to_frame_input`
  defaults `broadcast_striker` differently from production's
  None-passthrough. This pattern may apply to other FrameInput
  fields and warrants a systematic audit. Promote if step-2
  surfaces additional divergent defaults.

Both deferred to step-2 close-out.

### Methodology footprint

**Ninth-instance footprint** of pre-step-N spot-check catching
scope-narrowing errors: step-1 narrowed the candidate
hypothesis to "SM cold-start opener-selection logic" but the
actual root is a TWO-SITE composite (SM-side default branch +
snapshotter-side passthrough mismatch). Static read at
`score_manager.py:3498-3524` + `tests/test_pipeline_captured_-
replay.py:113-117` was needed to disambiguate the production
path from the snapshotter path. No S-number promotion per
standing discipline.

---

## §10 Step-2 entry data

### Patch surface (step-2)

1. **`files/score_manager.py:3521-3524`** (SM-side
   `_accept_initial` default branch):
   - Replace `cold_start_no_indicator` default `_set_slot_pair`
     call with deferred-anchor logic. When `_strip_bc` is None,
     do NOT commit the striker pointer; leave `self.striker`
     as None. Wait for an asterisk-detected frame to anchor.
   - Conservative alternative: emit
     `STRIKER-ANCHOR-DEFERRED-NO-ASTERISK` trace tag and
     continue with the bat1 default (telemetry first, behavior
     change at step-2b after observing tag firings).
   - ~15 LOC + trace tag.

2. **`files/tests/test_pipeline_captured_replay.py:113-117`**
   (snapshotter-side `extracted_to_frame_input`):
   - Replace `bat1.get("name")` fallback with `None` so the
     snapshotter matches production semantics (production
     passes None when no asterisk; snapshotter currently
     passes bat1.name).
   - ~3 LOC change.

3. **`files/trace_emitter.py`**: register
   `STRIKER-ANCHOR-DEFERRED-NO-ASTERISK` tag (if step-2 uses
   the deferred-anchor route).

Estimated total: ~20 LOC.

### Test obligation (gate-6)

L1.5 cases needed (step-2):
- **P-1**: `_accept_initial` defers striker anchor when
  `broadcast_striker is None` (synthetic card with no
  broadcast_striker; assert `self.striker is None` after the
  call; assert tag emits if telemetry-first route).
- **P-2**: `_accept_initial` defers anchor when
  `broadcast_striker == bat1.name` and Scout's per-batter
  records lack explicit striker flag (synthetic disambiguation
  case).
- **P-3**: snapshotter's `extracted_to_frame_input` passes
  None for broadcast_striker when no bat has `striker=True`
  (synthetic extracted dict; assert FrameInput.broadcast_striker
  is None).
- **P-4**: first asterisk-detected frame correctly anchors
  striker (synthetic card with explicit broadcast_striker =
  bat2.name; assert `_set_slot_pair(bat2, bat1, source="init_from_card.non")`).

L1.5 total: 86 → 90.

### Gate-7 cross-fixture verification (step-3)

After step-2 patch:
1. Re-run snapshotter against
   `files/logs/deliveries/watch_20260519_121701/scout_raw.jsonl`.
2. Compare against post-WS-O.b baseline. Expected: striker-
   anchor swap ~50 → 0; per-batter slot labels correct.
3. Cross-fixture: re-run against
   `validate_dckkr_20260521_155356/scout_raw.jsonl` per
   runbook §5 second-fixture pass; surface any first-
   asterisk-detection regression.

### Recommended next step

**WS-P step-2 patch authorization** at the ~20 LOC scope (SM
deferred-anchor + snapshotter passthrough fix) + 4 L1.5 cases
(~80 LOC).

Step-2 verification preconditions (must hold before patch):
- Confirm `_set_slot_pair` semantics when called with one or
  both arguments None — current callers may assume non-None
  inputs. Deferred-anchor path needs to leave the pair
  uncommitted, not partially committed.
- Confirm the snapshotter's None-passthrough doesn't break
  the L1.5 + L2 fixture cases that currently exercise the
  default fallback.
- Confirm no other `extracted_to_frame_input` field has the
  same "snapshotter defaults differently from production"
  divergence pattern (S32 sub-finding audit).

If any precondition fails: STOP, report, do not patch.

---

## §11 Status footer

**WS-P step-1 status.** CLOSED.

- 6 hypotheses enumerated; QA + QE composite leading; QB +
  QC + QD + QF falsified.
- Cohort closure UNIFIED (~50 swap fields trace to single
  initial anchor decision; deterministic propagation).
- Gates 1, 2 (conditional), 3, 5 PASS; gate 4 deferred (2
  step-2 sub-findings noted); gate 6 OPEN at step-2; gate 7
  deferred to step-3.
- F1 fix context: F1-adjacent (sibling code path), not F1-
  internal. Fix doesn't touch F1's WICKET-ATTRIB site.

**Recommended next step.** WS-P step-2 patch authorization at
the ~20 LOC two-site composite scope.

**WS-O.c residue noted as follow-up**: PA threshold refinement
for balls 4.1-4.5 (3 E2 + 5 conservation residue). Defer until
WS-P closes; methodology cap is no longer the binding
constraint per 2026-05-24 direction.

**Sub-mechanism reservations.**
- `_set_slot_pair` deferred-anchor semantics — step-2
  verification confirms the call site can accept "do nothing"
  inputs OR needs a new public method (e.g.,
  `defer_initial_striker_anchor`).
- S32 audit scope: how many other FrameInput fields have
  snapshotter-vs-production semantic divergences? Step-2
  bounded grep can confirm.
