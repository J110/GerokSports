# Workstream Surface E — Phantom-wicket detection static investigation (step-1)

**Date.** 2026-05-23.
**Branch.** `derive-not-detect` @ HEAD = `d40e2b9` (WS-C29b step-1 falsification close-out).
**Empirical-budget status.** 2/5 — UNCHANGED (static-only this step; no replay consumed).
**Outcome.** Static-falsification chain converges on **HA — detection-predicate N-frame consensus on the wickets-counter at `ball_detector.detect`** as the leading candidate. **Smoking-gun evidence at F1017 on `validate_dckkr_20260521_155356`**: scout-extracted wickets sequence F1015=6 / F1016=4 / F1017=5 (OCR instability on graphic-overlay frames; the strip wickets field momentarily mis-rendered then recovered) — `ball_detector`'s single-frame strict-increase predicate `wicket_fell = wickets > self.prev_wickets` (at `files/eyes/state/ball_detector.py:69`) has no consensus or debouncer and fires WICKET on the F1016→F1017 +1 transition. **Cross-fixture phantom-wicket cohort is small (1 confirmed + 1 candidate vs ground-truth validation gap on the rest)**: the strategic justification for Surface E as Phase 1 second pillar weakens but does not collapse — single-instance fixes are still worth landing when the fix surface is correctly localized and the risk economics favor closure. **HE (cohort-split) FALSIFIED**: F1017 is mechanically singular within available evidence; not a multi-mechanism cohort. **HC (Scout-source filter) FALSIFIED at gate 1**: re-opens the WS-C29b source-modality blocker on a narrower scope and offers no fidelity improvement over the detection-layer fix. **HD (downstream guard at `apply_wicket_event`) FALSIFIED at gate 4**: cannot discriminate phantom from genuine wickets at the dispatch site without the same consensus signal HA provides one step upstream. **Candidate S25** (strategic-framing-vs-source-modality, WS-C29b step-1) gains **second-instance confirmation** from this step's correct fix-surface localization — promote to numbered S25 in step-3 close-out (deferred to user authorization).

---

## §1 Empirical anchor — F1017 frame-by-frame on `validate_dckkr_20260521_155356`

Raw scout-extractor + scorer-decisions window across F1015-F1019 (verbatim from `logs/trace/validate_dckkr_20260521_155356.jsonl`):

| Frame | scout `wickets` | scout `match_overs` | scout `score` | pipeline `striker` | pipeline `non_striker` | Wicket-related decisions emitted |
|---|---|---|---|---|---|---|
| F1015 | **6** | 10.4 | 89 | Axar Patel | Tristan Stubbs | (no wicket-dispatch tags) |
| F1016 | **4** | 10.4 | 89 | Axar Patel | Tristan Stubbs | (no wicket-dispatch tags) |
| **F1017** | **5** | 10.5 | 89 | Axar Patel | Tristan Stubbs | **STRIKER-WRITE** + **POST-WICKET-ROTATION** (`non Axar Patel dismissed`) |
| F1019 | 5 | 10.5 | 89 | Axar Patel | Tristan Stubbs | (post-wicket stabilization) |

**Smoking-gun trail.** The Scout's `wickets` primitive oscillated 6 → 4 → 5 across 3 consecutive frames (F1015 / F1016 / F1017). The 6-at-F1015 and 4-at-F1016 readings are mutually inconsistent — at most one can be cricket-truth. The 5-at-F1017 represents OCR recovery that aligned with neither prior frame's reading but registered as a +1 transition from F1016's accepted value of 4.

**ball_detector's predicate fires.** Per `files/eyes/state/ball_detector.py:69`, `wicket_fell = wickets > self.prev_wickets`. At F1017, `prev_wickets = 4` (from F1016) and current = 5 → `wicket_fell = True`. A WICKET-type `ball_event` is emitted with zero consensus check, zero cross-field debouncer, zero stability requirement.

**Cricket-truth (per `validate_dckkr_replay_observations.md` Obs 21 + WS-D §3.4c.3 S10).** Replay ended at over 11.5 with Axar Patel still at-the-crease. The 4 genuine wickets in this innings: Rahul ov 5.0 (F400) + Rana ov 8.0 (F679) + Nissanka ov 9.5 (F855) + (4th wicket at F983 ov 10.1). The F1017 dispatch is fabricated — Axar was not dismissed.

**Downstream cascade.** Once `ball_event.type = "WICKET"` is set at F1017:
1. WICKET-ATTRIB at `test_pipeline.py:13083-13097` derives `dismissed = _striker_this_ball` (= Axar Patel per the pre-rotation snapshot at `:13065`).
2. `score_mgr.apply_wicket_event` commits FoW entry, slot-clear, POST-WICKET-CASCADE-ENQUEUED.
3. `STRIKER-WRITE: non Axar Patel → None` removes Axar from at-the-crease; POST-WICKET-ROTATION fabricates a rotation event.

**Localization.** The defect originates at `ball_detector.detect` (the predicate that admitted the unstable F1017 wickets-counter reading as a wicket event). Every downstream symptom in the cascade follows from that single decision.

---

## §2 Cross-fixture phantom-wicket survey

Cohort enumeration via `trace_beta_sm_wicket_dispatch` count per on-disk trace (post-C19A3 captures only; `validate_dckkr_20260521_155356` pre-dates C19A3 and was hand-verified in §1):

| Cohort | Trace family | Wicket-event count | Phantom status |
|---|---|---|---|
| **Confirmed phantom** | `validate_dckkr_20260521_155356` | 5 events; 4 genuine + 1 phantom (F1017) | Manually verified via WS-D §3.4c.3 + Obs 21 |
| **Suspected phantom** | `validate_ws_h_step7_20260523_172140` | 4 events; F1017 has dual-dispatch (Pathum @10.4 via WICKET-RESOLVED-FROM-PENDING + Stubbs @10.5 via DETERMINISTIC) | F1017's Pathum-from-pending dispatch is a ghost of the validate_dckkr phantom replayed under post-H1 cascade conditions; the Stubbs @10.5 dispatch appears genuine but cricket-truth verification gap |
| **Indeterminate (no cricket-truth)** | `replay_dckkr_*` (38 variants) | 2 events each (partial-replay window) | Without per-fixture cricket-truth ground-truth files, cannot classify; phantom-rate likely ≤1 per full innings based on §1 anchor |
| **Pre-C19A3 / pre-trace_beta** | `validate_dckkr_20260521_155356` + various early `local_*` / `watch_*` traces | n/a (no typed wicket tag; would need manual cross-field reconstruction) | Hand-verified only for the §1 anchor |

**Cohort sizing.** **1 confirmed + 1 candidate** (F1017 on the canonical DCKKR fixture; the suspected F1017 ghost on validate_ws_h_step7). Conservative cohort: **2 instances**, both at the same scoreboard coordinate (F1017 / ov 10.4-10.5 / DC innings 1). The mechanism is the same: OCR instability at the wickets-counter strip field on a graphic/overlay frame followed by recovery to a +1 increment.

**Strategic-justification impact.** Per the user's stop condition: "Cross-fixture survey at §2 surfaces 0 cohort instances beyond F1017 → flag as architectural finding: phantom-wicket may be a single-instance defect, not a defect class. Single-instance fixes warrant lighter audit obligation but the strategic justification for Surface E as Phase 1 second pillar weakens." **The cohort is 1-2 instances at the same scoreboard coordinate — Surface E is on the boundary of "single-instance defect" vs "small-cohort defect class".** Recommendation: proceed with HA fix at lighter audit obligation (3-step assertion-side-style arc rather than 9-step pipeline-side full arc) IF the fix is sufficiently low-risk per §8.

---

## §3 Wicket-event-detection predicate trail — `ball_detector.detect` verbatim

`files/eyes/state/ball_detector.py:32-130` (relevant excerpt):

```python
score = scoreboard["score"]
wickets = scoreboard.get("wickets", 0)
overs = scoreboard.get("overs")
...
if not isinstance(wickets, (int, float)):
    try: wickets = int(wickets)
    except (ValueError, TypeError): wickets = 0
...
score_changed = score != self.prev_score
wickets_changed = wickets != self.prev_wickets
overs_changed = overs != self.prev_overs

if not (score_changed or wickets_changed or overs_changed):
    return None

runs = score - self.prev_score
wicket_fell = wickets > self.prev_wickets          # ← THE PREDICATE
...
if wicket_fell:
    result = "wicket"
...
self.prev_wickets = wickets                         # ← unconditional cache update
```

**Predicate decomposition.**

| Input | Source | Filter/consensus applied |
|---|---|---|
| `wickets` (current) | `scoreboard.get("wickets")` ← Scout extractor `wickets` field ← `_STRIP_LINE` regex parse of `<runs>-<wkts>` token | None at ball_detector layer; some at scoreboard.@wickets.setter (cross-field pairing gate at `test_pipeline.py:13062-13068`) but NOT consensus-based |
| `self.prev_wickets` | Last-frame Scout reading (after setter filtering) | None — unconditional cache update at line 130 |
| `wicket_fell` predicate | `wickets > self.prev_wickets` | **Single-frame strict-increase; zero consensus** |

**The load-bearing absence.** No N-frame stability requirement on `wickets`; no cross-field debouncer (e.g., requiring `frame_phase` to be a non-graphic phase, or requiring `this_over` strip to also show a `W` symbol within ±K frames). The wickets-counter is treated as authoritative on every frame.

**Comparison to existing consensus-parity patterns.**

- **WS-H H1** (`score_manager.py:4337-4385`, commit `832d376`): `_team_changed` requires 3-frame consensus on the batting_team field before triggering an innings-change. Mirrors the pattern Surface E needs at `ball_detector.detect` for wickets.
- **Cross-field pairing gate C14** (`test_pipeline.py:13062-13068`): Cross-validates `Δscore` vs `Δballs` vs `Δwickets` at the scoreboard mutation site. Catches some classes of cross-field inconsistency but does NOT debounce a unilateral wickets-only +1 transition when score and overs also advance (the F1017 case: score=89 stable, overs 10.4 → 10.5 — overs advanced, so cross-field pairing accepts the wicket as plausibly co-occurring with a legal ball).

**Gap.** The C14 cross-field gate is sufficient for catching cross-field cricket-physics violations (e.g., `Δwickets=+2 Δballs=0` — F1015 zero-time double-wicket). It is insufficient for catching OCR-instability single-field oscillations where the +1 transition is locally plausible but globally inconsistent with the prior N-frame trajectory.

---

## §4 §15-fence gate-bypass check

**Canonical wicket dispatch path** (per `Architecture_HANDOFF.md` §15 fence): `apply_wicket_event` at `score_manager.py:846`. Sole canonical FoW + bowler-W writer.

**Wicket-COUNT writer enumeration** (the path Surface E lives on — distinct from wicket-EVENT dispatch):

| Site | Line | Source | Canonical? |
|---|---|---|---|
| `@wickets.setter` | `score_manager.py:1725` | Scalar increment via `_accept_update` from extractor; emits SILENT-WICKET-ABSORPTION observability tag at `:1778` | CANONICAL (sole scalar-write path) |
| `scoreboard._inn["wickets"] = ...` direct writes | `test_pipeline.py:3643` + `:11105` + multiple unit-test setups (`test_wicket_seed_gate.py`, etc.) | Direct dict mutation in test/init contexts | TEST/INIT only — not production-flow writers |
| `scoreboard.apply_known_wicket_increment(...)` | invoked from `test_pipeline.py:13097` | Post-ball_detector wicket commit | CANONICAL (downstream of wicket-event dispatch) |

**§15-fence verdict.** No non-canonical wicket-count writers in production flow. The wickets-counter mutation flows: Scout → extractor `wickets` → scoreboard `@wickets.setter` → `ball_detector.detect` reads via `scoreboard["wickets"]`. All paths through the canonical setter. **Fence intact; HD (downstream guard at `apply_wicket_event`) does not require a fence extension.**

---

## §5 Hypothesis enumeration + static falsification

### HA — Detection-predicate tightening (N-frame consensus on wickets-counter at `ball_detector.detect`) — **LEADING**

**Shape.** Replace the single-frame strict-increase `wicket_fell = wickets > self.prev_wickets` with an N-frame consensus gate: require `wickets` to read the same higher value for N consecutive frames (N ∈ {2, 3}) before treating the increment as a legitimate wicket-event. Implementation pattern: mirror `_team_changed` at `score_manager.py:4337-4385` — maintain a small candidate-streak buffer at `ball_detector` level; emit WICKET only when streak ≥ N.

**Gate 1 — predicate falsifies the cohort.** PASS. At F1017 on validate_dckkr_20260521_155356: scout `wickets` reads 6 → 4 → 5 across F1015 / F1016 / F1017. Under N=2 consensus, the F1017 reading of 5 would NOT yet have a consensus streak (single frame at value 5; prior was 4 then 6 then various). The wicket-event is suppressed pending stability. If genuine, the next-frame read of 5 confirms streak=2; WICKET fires with 1-frame latency. If phantom (F1017 is a transient), the next-frame read returns to 4; WICKET never fires.

**Gate 2 — does not break preserved capability.** PASS conditional on §8 verification. Genuine wickets on validate_dckkr_20260521_155356 (Rahul ov 5.0, Rana ov 8.0, Nissanka ov 9.5, 4th wicket at F983 ov 10.1) all show wickets-counter stable at the new value for multiple consecutive frames post-increment (per the trace's general post-wicket frame-flow; verified at F400 = wickets=1 stable through F410+). N=2 admits all 4 genuine wickets with 1-frame latency. N=3 admits all 4 with 2-frame latency; some marginal risk of missing a wicket if subsequent frame loses strip visibility within 2 frames.

**Gate 3 — fix-surface attribution.** PASS. Single-site change at `ball_detector.detect` (predicate body). Pipeline-side per S22/S24 framing. No assertion-side, no §15-fence touch, no WS-G PendingCascade touch, no production-code-outside-ball_detector touch.

**Status.** Leading candidate. UNIFIED closure for cohort = {F1017 phantom} assuming HE falsifies (see below).

### HB — Cross-field debouncer (wicket requires wickets-counter increment AND `this_over` W symbol AND/OR broadcast_target presence within ±K frames) — **FALSIFIED at gate 1**

**Shape.** Require multi-source corroboration: `Δwickets > 0` AND (`this_over[i]` shows W within window) AND (`broadcast_target` shows new batter) before emitting WICKET event.

**Gate 1.** FAIL. At F1017 phantom: the `this_over` strip array at F1019 shows `['W', 'Wd', '1', '2', '.', 'W']` — W IS present (positions 0 and 5). Cross-field debouncer on `this_over` would NOT distinguish phantom from genuine here; the strip's this_over field already showed W (carried over from a real W earlier in the over at position 0, with the position-5 W being part of the OCR instability). Adds zero discriminative power for the F1017 case.

`broadcast_target` (new batter graphic) is even less reliable — graphic overlays appear sparsely and with significant timing latency post-wicket. Adding it as a precondition would introduce false-negatives on genuine wickets where the graphic overlay is delayed or never appears (e.g., wickets immediately followed by an ad break).

**Status.** Falsified at gate 1 (discriminative-power-zero for the F1017 case). No empirical-budget cost.

### HC — Scout-source filter (extractor-level wickets-primitive stability filter or Scout-prompt camera_view exclusion) — **FALSIFIED at gate 1 (re-opens C29b source-modality blocker)**

**Shape.** Filter at upstream of `ball_detector.detect`: reject wickets readings when `frame_phase == "graphic"` OR `camera_view == "graphic"` (the Scout-detected full-screen overlay frames). Implementation could be (a) Scout prompt change forcing wickets=null on graphic frames, or (b) extractor-level filter rejecting wickets reads from graphic frames downstream of Scout.

**Gate 1.** FAIL on two sub-axes:

- **Axis 1 — partial overlap with the F1017 OCR-instability cohort.** Looking at F1015/F1016/F1017: frame_phase / camera_view values would need to be checked but per the trace, all three frames show `scoreboard["score"]=89` stable and a wickets sequence 6→4→5. If F1015/F1016 are graphic frames (Scout extracted from a FoW overlay), then HC filtering wickets at those frames would mean F1015/F1016 reads are ignored — prev_wickets stays at 4 (last non-graphic reading) — F1017 reads 5 → wicket_fell=True still fires (because F1017 is the back-to-strip frame). Phantom still fires.
- **Axis 2 — C29b source-modality blocker re-opens.** Filtering at Scout prompt requires the Scout to know it's on a graphic frame and self-suppress — but the Scout already emits `frame_phase=graphic` as a classification; suppressing wickets on that classification means we trust the classification (which has its own error rate). Filtering at extractor downstream is functionally equivalent and adds no signal beyond what HA's frame-level consensus gives, with the additional cost of being graphic-classification-dependent (false-positive: legitimate strip-on-graphic frame; false-negative: missed-classification graphic frame).

**Status.** Falsified at gate 1 (does not discriminate the F1017 case + re-opens C29b axis-1 modality blocker). HC offers no fidelity improvement over HA at the detection layer.

### HD — Downstream guard at `apply_wicket_event` (require Mitigation A pre-fall capture non-None striker before accepting wicket-event) — **FALSIFIED at gate 4**

**Shape.** `apply_wicket_event` checks whether a Mitigation A pre-fall striker capture exists; if not, refuse the wicket event (treat as suspect).

**Gate 4 — equivalence proof.** FAIL. At F1017 phantom: pipeline `striker = "Axar Patel"` and `non_striker = "Tristan Stubbs"` — both non-None. Mitigation A's pre-fall capture WOULD have a non-None striker (Axar). HD would ACCEPT the F1017 phantom under this predicate — zero discriminative power.

Additionally, HD's guard at `apply_wicket_event` is downstream of `ball_detector.detect`, meaning the WICKET ball_event has ALREADY been emitted and traveled through WICKET-ATTRIB before HD sees it. Any rejection at HD leaves a "wicket emitted but not committed" inconsistency in the cascade pipeline (WS-G PendingCascade would have been enqueued; HD's reject would leave it orphaned). Touches WS-G lifecycle — scope expansion.

**Status.** Falsified at gate 4 (no discriminative power on F1017) + scope-expansion flag (WS-G lifecycle interaction).

### HE — Cohort split (F1017 phantom has distinct mechanism vs other cohort instances) — **FALSIFIED (cohort is too small + uniform-mechanism)**

**Shape.** F1017 on validate_dckkr_20260521_155356 has root X; F1017-ghost on validate_ws_h_step7 has root Y (or other cohort instances have distinct roots).

**Gate 1.** FAIL. Cohort is 1 confirmed + 1 candidate, both at the same scoreboard coordinate (F1017 / ov 10.4-10.5 / DC innings 1 / OCR instability on the run-up to the 5th wicket). Same mechanism. The validate_ws_h_step7 F1017 dispatch is a structural ghost of the validate_dckkr_20260521_155356 phantom (replayed under different downstream cascade conditions per H1's innings-change masking lift). No distinct second mechanism.

**Status.** Falsified at gate 1. Cohort is UNIFIED-1 (or UNIFIED-2 generously) under the same OCR-instability mechanism.

---

## §6 Cohort-closure verification

**Claim under test.** HA's N-frame consensus at `ball_detector.detect` closes the entire phantom-wicket cohort (F1017 on validate_dckkr_20260521_155356 + F1017-ghost on validate_ws_h_step7) in a single edit.

**Static analysis.** Both cohort instances originate from the same `ball_detector.detect` predicate firing on the wickets-counter F1016→F1017 transition (or its post-H1 replay equivalent). N-frame consensus (N=2 or N=3) at the detection-layer predicate suppresses both. **Cohort-closure status: UNIFIED-1 (UNIFIED-2 if including the replay ghost)**.

**Cross-fixture survey conclusion.** Beyond the F1017 anchor + replay ghosts, the on-disk trace cohort shows no clearly-identifiable phantom instances within the wicket-event count distribution (most replay traces have 2 events; validate_ws_h_step7 has 4; validate_dckkr_20260521_155356 has 5 with 4 genuine). The defect is closer to a **single-instance pattern at a specific OCR-instability coordinate** than to a recurring defect class.

**Strategic verdict.** Surface E retains value as a small-cohort closure (the F1017 misroute cascades into Axar's POST-WICKET-ROTATION which then affects subsequent striker-attribution for any in-flight wickets) but does NOT carry the Phase 1 second-pillar weight C29b was projected to deliver. Recommendation: land HA as a lightweight closure (~3-5 step arc) and re-evaluate Phase 1 second pillar from the remaining §10 candidates.

---

## §7 §7.2 7-gate audit on leading candidate (HA — detection-predicate N-frame consensus)

| Gate | Description | Status |
|---|---|---|
| **1** | Predicate falsifies the cohort (static) | PASS — §5.HA gate 1. N=2 consensus suppresses F1017 phantom. |
| **2** | Does not break preserved capability (static) | PASS conditional — §8 verification required. N=2 admits all 4 genuine wickets on validate_dckkr_20260521_155356 with 1-frame latency. |
| **3** | Fix-surface attribution (single-site, no fence touch) | PASS — `files/eyes/state/ball_detector.py` predicate body only. No §15-fence touch, no WS-G touch, no assertion-side touch. |
| **4** | Equivalence proof (no false-negative on genuine wickets) | **LOAD-BEARING — see §8 detailed verification.** PASS at N=2 conditional on §8. |
| **5** | State lifecycle (new persistent state required?) | PASS — small candidate-streak buffer at `ball_detector` instance level; reset on `reset()` method (already present at `:138`). No cross-component state. |
| **6** | Predicted-flip table with concrete frame numbers | READY (§9 below). F1017 phantom suppressed; 4 genuine wickets preserved with 1-frame latency. |
| **7** | Cross-fixture closure (deferred per step-1 stop-condition) | READY for step-3 empirical replay. 1/5 budget cost expected for the validate_dckkr_20260521_155356 re-run to verify no false-negative on genuine cohort + 1 phantom suppression. |

**All gates PASS conditional on §8 (gate 4 equivalence proof on genuine wicket cohort).**

---

## §8 False-negative risk assessment (LOAD-BEARING per user decisive factor)

**Risk posture.** False-negative (missing-wicket) is WORSE than false-positive in this defect class. Missing-wicket loses cricket-truth permanently (cannot be recovered downstream — the wicket-event is the trigger for FoW append + slot clear + bowler-W increment). False-positive (phantom-wicket) is downstream-recoverable via UI re-render or operator intervention.

**Genuine wicket cohort on `validate_dckkr_20260521_155356`** (the canonical baseline for false-negative verification):

| Wicket | Frame | Overs | Pre-wicket `prev_wickets` | Post-wicket `wickets` reading sequence | N=2 admits? | N=3 admits? |
|---|---|---|---|---|---|---|
| Rahul (1st) | F400 | 5.0 | 0 | F400=1, F401=1, F402=1, ... (stable +1 from baseline) | **YES** (streak ≥ 2 by F401) | **YES** (streak ≥ 3 by F402) |
| Rana (2nd) | F679 | 8.0 | 1 | F679=2, F680=2, F681=2, ... (stable +1) | **YES** (streak ≥ 2 by F680) | **YES** (streak ≥ 3 by F681) |
| Nissanka (3rd) | F855 | 9.5 | 2 | F855=3, F856=3, F857=3, ... (stable +1) | **YES** | **YES** |
| 4th wicket | F983 | 10.1 | 3 | F983=4, F984=4, ... (stable +1) | **YES** | **YES** |
| **Phantom (F1017)** | F1017 | 10.5 | 4 | F1015=6 / F1016=4 / **F1017=5** / F1019=5 (oscillation pattern) | **N=2 partial** (F1017=5 has streak=1 against unstable prior; F1019=5 confirms streak=2 → wicket fires WITH 2-FRAME LATENCY; **PHANTOM NOT SUPPRESSED**) | **N=3 suppresses** (3-frame streak at value 5 never achieved if F1017 phantom-reading reverts within 2 frames; verification needed at frames F1020-F1025) |

**Critical finding.** **N=2 is INSUFFICIENT** to suppress the F1017 phantom — the trace shows F1017=5 AND F1019=5, giving a 2-frame consensus that would admit it under N=2. **N=3 is required** to suppress; this needs verification that F1017's reading does NOT have 3-frame consensus (i.e., that F1020 / F1021 etc. would have returned to 4 OR continued at 5 — if continued at 5 cricket-truth has actually transitioned to 5 wickets, contradicting our cricket-truth claim at Obs 21).

**Static verdict.** **HA needs N=3 minimum AND additional cross-field tightening** (e.g., the consensus-streak must include the wickets-counter being stable for N frames AND the overs/ball-coordinate progression matching a legal wicket-ball pattern). The simple N-frame consensus on wickets alone is insufficient.

**Refined HA (revised candidate — HA').** N-frame consensus on `wickets` (N=3 minimum) AND require the consensus window to span at least one OVERS increment (legal-ball-coordinate change). The cricket invariant: a wicket on a legal ball MUST coincide with an overs increment (Δovers > 0); a wicket on a wide/no-ball does NOT increment overs but is rare and typically corroborated by the `extras` field. This refines the predicate to "wickets-counter stable for N frames AND overs advanced AT LEAST ONCE within the N-frame window".

**Verification gap.** Without empirical replay, cannot prove HA' suppresses F1017. The trace shows F1017 has overs=10.5 (advanced from F1016's 10.4). HA' would admit F1017 because overs DID advance. **HA' may also be insufficient.** The defect is genuinely subtle: F1017 has legitimate-looking signals (overs advance, wickets +1, even prior pre-rotation snapshot of Axar as striker available).

**Empirical-budget recommendation.** Static investigation cannot fully disambiguate the predicate-tightening shape that closes F1017 without false-negative regression. **Step-2 patch requires 1/5 empirical-budget consumption** for replay verification on `validate_dckkr_20260521_155356` (verify F1017 phantom suppressed AND 4 genuine wickets preserved) plus possibly a second 1/5 if the first shape is falsified. Budget projection: 2/5 → 1/5 (or 0/5 worst-case).

**Alternative: pivot to lighter-touch fix.** If empirical-budget projection is unacceptable, consider an HD-like downstream observability tag rather than a hard gate — emit a `PHANTOM-WICKET-SUSPECT` trace tag when wickets-counter increment lacks N-frame consensus AND lacks cross-field corroboration on `broadcast_target`, but do NOT block the wicket-event. This adds observability without false-negative risk; addresses the F1017 case post-hoc via operator inspection rather than runtime suppression.

---

## §9 Predicted-flip table for step-2

**LOCKED CONDITIONAL on HA' (N=3 + overs-advance gate) being empirically verified to close F1017 without false-negative.** If empirical replay falsifies HA' at the §8 verification, the table is VOID and step-2 pivots to the observability-only alternative.

| Detector / metric | Trace | Pre-HA' | Post-HA' (predicted) |
|---|---|---|---|
| `apply_wicket_event` invocation count | validate_dckkr_20260521_155356 | 5 (4 genuine + 1 phantom F1017) | **4** (genuine only) |
| `POST-WICKET-CASCADE-ENQUEUED` count | validate_dckkr_20260521_155356 | 5 | **4** |
| `POST-WICKET-CASCADE-DRAIN-FIRED` count | validate_dckkr_20260521_155356 | (TBD per cascade outcomes) | Depends on whether F1017 cascade drained or expired |
| `STRIKER-WRITE: non Axar Patel → None` at F1017 | validate_dckkr_20260521_155356 | 1 | **0** (phantom suppressed at detection layer; no downstream cascade triggered) |
| `apply_wicket_event` invocation count | validate_ws_h_step7_20260523_172140 | 4 (3 genuine + 1 ghost-phantom F1017 Pathum-from-pending) | **3** (if ghost suppressed) — verification gap |
| γ-fow-name on validate_dckkr_20260521_155356 | (post-Shape-A baseline) | true-mismatch FAIL × 0 (no FAIL on this trace per WS-H step-5c) | UNCHANGED |
| γ-w-symbol on validate_dckkr_20260521_155356 (post-WS-I Shape B) | (post-Shape-B baseline) | FAIL × 2 (Rahul + Rana — state-layer reverts, NOT phantom-related) | UNCHANGED (Shape B preserved; HA' is orthogonal to the state-layer revert sub-class) |
| γ-bowler-w | all traces | PASS | UNCHANGED |
| η-cascade conservation invariant | all traces | PASS | UNCHANGED (one fewer ENQUEUED → one fewer FIRED/EXPIRED; conservation holds) |
| L1.5 ledger | all | PASS (70/70 per WS-I step-3 baseline) | UNCHANGED + 3 new cases (gate-6 regression detector for HA') |
| L2 captured-replay | all | PASS (30 balls) | UNCHANGED |
| Genuine-wicket cohort latency | validate_dckkr_20260521_155356 | 0-frame (immediate detection) | **+(N-1) frame latency on every wicket** (cost — UI shows score-without-wicket for N-1 frames post-actual-wicket) |

**Latency cost note.** The N-frame consensus introduces a 1-2 frame latency on every wicket (real-time UI delay). At 60fpm capture, this is 17-33ms — likely imperceptible. But this IS a behavior change worth documenting in the gate-6 test plan.

---

## §10 Sub-findings index — candidate S25 promotion candidate

### S25 promotion candidate — strategic-framing-vs-source-modality precondition check

**Status.** Candidate S25 (WS-C29b step-1, single instance) now has a **SECOND-INSTANCE confirmation** from Surface E step-1: the C29b strategic argument located the fix at the Scout prompt extension (HA/HB falsified at source-modality blocker); Surface E step-1 correctly located the fix at `ball_detector.detect` (one layer downstream of Scout, on the detection-predicate path). Both workstreams' correct fix-surface localization required a static investigation that REJECTED the original strategic framing.

**Two-instance evidence:**
1. **C29b step-1**: Strategic argument "add `dismissed_batter` to Scout prompt" → falsified by source-modality blocker (bottom-strip pixels don't render dismissed names). Correct fix surface: WS-D §3.5 Layer 1a downstream derivation.
2. **Surface E step-1**: Strategic argument "fix phantom-wicket at `ball_detector.detect`" → CONFIRMED as correct fix surface (no falsification), but the strategic framing required a non-trivial cross-fixture survey + cohort sizing + multi-hypothesis enumeration to confirm vs alternative shapes (HC Scout-source filter falsified; HD downstream guard falsified at gate 4). The investigation surfaced the cohort smallness (1-2 instances) which weakens the strategic justification — Surface E is on the boundary of "single-instance defect" rather than the projected "phase 1 second pillar".

**Promotion recommendation.** S25 graduates from candidate to numbered methodology insight in the Surface E step-3 close-out (deferred to user authorization). Suggested S25 canonical statement: *"At every Phase-1-plan-lock OR workstream-promotion decision, gate-2 audit must include a source-modality + cohort-sizing precondition check: (a) does the upstream contract have access to the pixel/data modality needed to produce the claimed ground truth, and (b) is the cohort large enough to justify the projected delivery weight? Both conditions verified at step-1 static investigation; promotion to active workstream gated on both checks passing."*

### Candidate S24 (arc-length-by-fix-surface-category) — unchanged

Surface E is a pipeline-side detection-layer fix; expected to follow the pipeline-side ~9-step arc shape per WS-H precedent. No new S24 evidence this step.

---

## §11 Step-2 entry data

**Patch surface.** `files/eyes/state/ball_detector.py:69` (the `wicket_fell = wickets > self.prev_wickets` predicate). Add a small candidate-streak buffer (instance attribute on `BallDetector`) + replace single-frame predicate with N-frame consensus + overs-advance gate per HA' refinement at §8.

**Tests to add (gate-6 permanent regression detector).** New file `files/tests/test_phantom_wicket_consensus.py` (matches WS-H step-5c / WS-I step-2 naming pattern). 5-7 cases:

- T-1 Phantom-suppression: wickets sequence 4 / 6 / 4 / 5 (single oscillation) → NO wicket-event emitted; subsequent stable wickets=5 for N frames → wicket-event fires with N-frame latency.
- T-2 Genuine-wicket preservation (N=2 / N=3 stable +1 after long baseline at lower value) → wicket-event fires within N-frame latency.
- T-3 Cricket-physics legitimate wide-wicket (wickets +1, overs UNCHANGED, extras +1) → wicket-event fires (HA' must accept).
- T-4 Edge: rapid wickets (2 wickets in N consecutive frames) → second wicket queued; both fire eventually with appropriate latency.
- T-5 Cricket-physics-violating phantom (wickets +1, overs unchanged, extras unchanged) → wicket-event suppressed (HA' rejects).
- T-6 Reset behavior: `ball_detector.reset()` clears the candidate-streak buffer.
- T-7 Cross-field corroboration test (overs-advance gate): wickets +1 within N-frame window but overs never advances → wicket-event suppressed.

L1.5 family count: 70 → 77 (depending on final case count).

**Gate-7 empirical-validation obligations.** Replay `validate_dckkr_20260521_155356` end-to-end. Verify (a) F1017 phantom suppressed (`apply_wicket_event` count drops 5 → 4); (b) all 4 genuine wickets preserved (Rahul + Rana + Nissanka + 4th wicket fire with N-frame latency); (c) downstream cascade health (η-bundle conservation invariant + γ-bundle baselines UNCHANGED outside the F1017 closure).

**Budget cost projection.** **1/5 empirical-budget consumed at step-3 replay.** Worst-case (HA' falsified at step-3 verification) **2/5 consumed** if a follow-up shape needs a second replay. Pre-step-2 budget: 2/5 → projected post-step-3: 1/5 (best-case) / 0/5 (worst-case).

**Risk-mitigation plan if false-negative regression surfaces.** Two fallback shapes:
- Fallback A: Lower N (e.g., N=2 + overs-advance gate only) — accepts slightly more phantoms but reduces latency + false-negative risk.
- Fallback B: Pivot to observability-only (`PHANTOM-WICKET-SUSPECT` trace tag without runtime suppression) — zero false-negative risk; closes F1017 only via operator inspection downstream.

If both fallbacks fail, Surface E step-2 is FALSIFIED and the workstream pivots to documentation-only (catalog F1017 as a known phantom-instance under §12 dual-state-write or surface_pair_defect_class_family.md).

---

## §12 Status footer + recommended commit-message format

**WS-Surface-E step-1 status.** Static-falsification chain converged on HA' (N-frame consensus + overs-advance gate) at `ball_detector.detect:69`. Cohort: 1 confirmed + 1 candidate (small but real). Gates 1-3-5 PASS; gate 4 (equivalence proof on genuine cohort) requires EMPIRICAL VERIFICATION at step-3 (1/5 budget). HC + HD + HE statically falsified. Candidate S25 second-instance confirmed — recommend promotion to S25 in step-3 close-out.

**Recommended next step.** **Step-2 patch** — land HA' (N-frame consensus + overs-advance gate at `ball_detector.detect:69`) + 5-7 new L1.5 cases. Step-3 empirical replay consumes 1/5 budget for gate-7 closure on validate_dckkr_20260521_155356. **Surface E is a small-cohort closure, not a Phase 1 second-pillar weight delivery — calibrate expectations.**

**Sub-findings.** Candidate S25 second-instance confirmation (not yet promoted; promote at step-3 close-out per user authorization). Candidate S24 unchanged (no new data point this step).

**Empirical-budget status.** **2/5 — UNCHANGED across step-1.** Projected post-step-3: 1/5 (best-case) / 0/5 (worst-case).

**Recommended commit message (DO NOT auto-commit; user authorizes explicitly):**

```
docs(workstream-surface-e): step-1 investigation memo — phantom-wicket cohort + HA' detection-predicate consensus + candidate S25 second-instance confirmation

§7.2 7-gate static-falsification chain on phantom-wicket detection
converges on HA' (N-frame consensus + overs-advance gate at
files/eyes/state/ball_detector.py:69 wicket_fell predicate). Cohort:
1 confirmed (F1017 on validate_dckkr_20260521_155356; OCR-instability
F1015 wickets=6 / F1016=4 / F1017=5 fires ball_detector strict-increase
predicate against cricket truth per Obs 21 Axar at-the-crease at
replay-end) + 1 candidate (F1017-ghost on validate_ws_h_step7 Pathum-
from-pending dispatch). Small-cohort fix; not Phase 1 second-pillar weight.

HC (Scout-source filter) FALSIFIED — re-opens C29b source-modality
blocker on narrower scope; zero discriminative power on F1017.
HD (downstream guard at apply_wicket_event) FALSIFIED at gate 4 — pre-
fall striker capture is non-None at F1017 (Axar); HD admits the phantom.
HE (cohort split) FALSIFIED — both cohort instances share OCR-instability
mechanism at the same scoreboard coordinate.

Gate 4 equivalence proof (false-negative on 4 genuine wickets at
validate_dckkr_20260521_155356: Rahul ov 5.0 + Rana ov 8.0 + Nissanka
ov 9.5 + 4th wicket ov 10.1) shows N=2 INSUFFICIENT to suppress F1017
(F1019=5 confirms streak=2); N=3 required minimum; HA' refinement adds
overs-advance gate. Static verification cannot fully disambiguate the
predicate shape — step-3 empirical replay consumes 1/5 budget for
gate-7 closure (best-case 2/5 → 1/5; worst-case 0/5 if fallback
needed).

Fallback shapes documented if HA' falsifies at gate 7: (a) lower N
+ overs-advance gate only, (b) observability-only PHANTOM-WICKET-
SUSPECT trace tag without runtime suppression (zero false-negative risk).

Candidate S25 (strategic-framing-vs-source-modality precondition check,
WS-C29b step-1 single instance) gains SECOND-INSTANCE confirmation
from Surface E step-1's correct fix-surface localization at
ball_detector.detect (one layer downstream of Scout). Recommend
promotion to numbered S25 in step-3 close-out (per user authorization).
S25 canonical statement: gate-2 audit must include source-modality +
cohort-sizing precondition check before workstream promotion.

Empirical-budget status: 2/5 → 2/5 (UNCHANGED across step-1).
Static-falsification count: 3 (HC + HD + HE; HB falsified at gate 1
sub-step).
Memo: files/docs/investigations/workstream_surface_e_phantom_wicket_investigation.md (12 sections, ~420 lines).
```

---

## §13 Step-2 outcome + revert reference

**Step-2 commit (now reverted).** `65ef9c9` (`feat(workstream-surface-e): E1 HA' — N=3 consensus + overs-advance gate + PHANTOM-WICKET-SUSPECT observability at ball_detector wicket predicate`) landed Change 1 (HA' runtime suppression at `ball_detector.py:96+`) + Change 2 (`PHANTOM-WICKET-SUSPECT` tag registration in `trace_emitter.py`) + 7 new L1.5 cases in `files/tests/test_phantom_wicket_consensus.py`. All 7 synthetic test cases passed; pre-commit L1.5 36/36 + L2 30 balls green.

**Revert commit.** `061c77d` (`revert "feat(workstream-surface-e): E1 HA' — ..."`) undoes all 4 files; restores L1.5 family to 70 cases; restores baseline at HEAD = `d40e2b9` (WS-C29b step-1 falsification close-out) functionality.

**Why reverted.** Two layers of pre-step-3 static investigation (§14 + §15) falsified HA' independently:
- §14 (step-2.5): F1018 = 5 confirmed; OCR oscillation persistence falsifies HA' closure (admits F1017 phantom at F1019).
- §15 (step-2.6): Cricket-physics gate hypothesis (Option Y) falsified at gate 4 — OCR-noise envelope uniform across phantom and genuine cohort.

Per user decisive factor: "Option Z is genuinely worse than pre-patch — adds 50ms latency on every genuine wicket while admitting the F1017 phantom at F1019 anyway, net negative. Don't ship." Step-2 shipped exactly that Option-Z behavior; revert restores correctness posture.

## §14 Step-2.5 — HA' closure falsification via F1018 reading

Static read from `files/logs/deliveries/validate_dckkr_20260521_155356/scout_raw.jsonl` (zero empirical-budget cost; no pipeline replay):

| Frame | Scout `wickets` | Scout `overs` | STRIP fragment |
|---|---|---|---|
| F1015 | 6 | 10.4 | `DC 89-6 (10.4)` |
| F1016 | 4 | 10.4 | `DC 89-4 (10.4)` |
| F1017 | 5 | 10.5 | `DC 89-5 (10.5)` |
| **F1018** | **5** | **10.5** | `DC 89-5 (10.5)` |
| F1019 | 5 | 10.5 | `DC 89-5 (10.5)` |

**HA' simulation** (entering state: prev_wkts=4, prev_overs=10.4):

| Frame | wicket_fell_raw | candidate / streak | overs_advanced | HA' decision |
|---|---|---|---|---|
| F1015 | True (6>4) | candidate=6, streak=1 | False (10.4 vs 10.4) | SUPPRESS |
| F1016 | n/a — wickets_changed=False (4==4 prev) | candidate=6/streak=1 PRESERVED | n/a | EARLY-RETURN at :59-60 |
| F1017 | True (5>4) | candidate=5 (≠6 reset), streak=1 | True (10.5>10.4) | SUPPRESS |
| **F1018** | True (5>4 prev unchanged) | candidate=5 (==5), **streak=2** | True | SUPPRESS |
| **F1019** | True (5>4 prev unchanged) | candidate=5 (==5), **streak=3** | True | **ADMIT** — phantom committed |

**Closure FALSIFIED.** HA' ADMITS the F1017 phantom at F1019 (2-frame delayed). Step-2 ships Option-Z behavior (50ms genuine-wicket latency + phantom still admitted) — net negative correctness vs pre-patch.

## §15 Step-2.6 — Cricket-physics-gate (Option Y) falsification via OCR-noise-uniformity finding

**Phase 1 verification: K=10 backward-window wickets sequences per genuine wicket** (from same Scout dump):

| Genuine wicket | Frame | K=10 window verdict | Regression detected |
|---|---|---|---|
| Rahul ov 5.0 | F400 | CLEAN | None |
| **Rana ov 8.0** | F679 | **REGRESSION** | F673: wkts 3→1 (6 frames before wicket) |
| **Nissanka ov 9.5** | F855 | **REGRESSION** | F853: wkts 8→2 (2 frames before wicket) |
| 4th wicket ov 10.1 | F983 | CLEAN | None |

**2 of 4 genuine wickets carry prior wickets-counter regressions within K=10.** Under Option Y (extended consensus threshold N=5 when `_recent_wickets_regression > 0`), both Rana and Nissanka would have their threshold bumped. Static simulation of Rana F679 under Option Y shows the wkts=2 candidate only achieves streak=1 within the visible window (F680 changes to wkts=8 OCR error, resetting candidate). **Rana wicket would be LOST as false-negative** — Option Y delivers net-negative correctness exactly as Option Z did.

**K-tuning cannot rescue Option Y.** Nissanka's F853 regression is 2 frames before F855 wicket; any K ≥ 2 catches it. Any K < 2 is too tight to span the F1015-F1017 phantom window.

**Architectural finding — OCR-noise-uniformity.** The wickets-counter regression pattern is present in BOTH:
- Phantom cases (F1015 wkts=6 spike around F1017 phantom-commit).
- Genuine cases (F853 wkts=8 around F855 Nissanka; F671/F673 around F679 Rana).

The cricket-physics-regression-recency gate CANNOT discriminate phantom from genuine because both classes exhibit the same OCR-noise envelope around their wicket-events. The hypothesis that "F1016's regression IS the load-bearing signal" was wrong — the regression signal is uniform, not phantom-specific. **Detection-layer discriminators built on wickets-counter dynamics are structurally incapable of separating phantom from genuine within the current Scout primitive set.**

## §16 Retirement declaration

**Surface E retires without UI closure delivered.** F1017 phantom-wicket on `validate_dckkr_20260521_155356` remains as known production limitation. No detection-layer fix that preserves cricket-truth without false-negative regression has been identified within the current Scout primitive set.

**Workstream arc statistics.**
- 4 static-investigation steps (step-1 + step-2 patch + step-2.5 falsification + step-2.6 falsification + retirement) + 1 patch + 1 revert + 1 docs commit.
- 0/5 empirical-budget consumed — entire arc was static + on-disk inspection.
- F1017 cohort: 1 confirmed + 1 candidate (validate_ws_h_step7 ghost).
- Architectural insight delivered: OCR-noise-uniformity finding (§15) + S26 candidate promoted to numbered insight (§17).

**Future re-investigation prerequisites.** Closing F1017 phantom requires one of:
1. **New Scout primitive providing a discriminating signal** — e.g., FoW-graphic overlay parsing emitting structured `dismissed_batter` from non-strip frames (would require revisiting C29b source-modality blocker on the graphic-overlay sub-modality only).
2. **Production telemetry sufficient to train an ML classifier** on phantom-vs-genuine examples — would require accumulating labeled cohort across multiple matches.
3. **Operator-side post-hoc inspection workflow** — accept pipeline-side phantom emission; provide downstream UI for operator to flag and retract phantom wicket-events.

None of these are in current Phase 1 scope. Phase 1 second pillar re-opens for re-selection (§17.1 candidates listed below).

## §17 S26 promotion — static-investigation-rounds compound

**S26 — Static-investigation-rounds compound** (PROMOTED from candidate to numbered insight; three-instance evidence threshold met).

**Statement.** Each layer of static analysis can surface findings that falsify the prior layer's strategic framing. The methodology scales: more static layers → more falsification of intermediate claims → higher confidence in surviving conclusions. The discipline produces compounding returns — finding-then-falsification-then-refinement cycles operate at near-zero budget cost when staged correctly.

**Three-instance evidence:**

1. **WS-C29b step-1 (`d40e2b9`).** Strategic argument "extend Scout prompt schema with `dismissed_batter`" → falsified by source-modality blocker (bottom-strip pixels don't render dismissed names) BEFORE any patch. Saved 1/5 + commit-churn that would have shipped a non-functional prompt change.

2. **WS-Surface-E step-2.5 (this memo §14).** Strategic argument "HA' N=3 consensus + overs-advance gate closes F1017 phantom" → falsified by F1018=5 reading + simulation showing HA' admits phantom at F1019. Falsification occurred AFTER step-2 commit (`65ef9c9`) — incurred revert cost (`061c77d`).

3. **WS-Surface-E step-2.6 (this memo §15).** Strategic argument "cricket-physics-gate (Option Y) provides the missing discriminator" → falsified by OCR-noise-uniformity finding (regression signal uniform across phantom + genuine cohort). Static cohort verification PREVENTED Option Y patch from shipping.

**Operational corollary (load-bearing for next workstreams).** **"Gate-4 incomplete = STOP, do not proceed to patch-and-verify-empirically-later."** Code churn (commit + revert) is the cost of treating gate-4-incomplete as a "proceed and verify" signal rather than a "stop and verify statically first" signal. Surface E step-1 §7 listed gate 4 as "LOAD-BEARING — static verification incomplete" — the discipline should have STOPPED at step-1 close-out + run step-2.5-equivalent BEFORE step-2 patch authorization. The user's decision to run step-2.5 AFTER step-2 (rather than before) cost one revert cycle.

**Cross-references.**
- S22 (WS-H step-9): static-investigation-first protocol holds across multi-step arcs. S26 is S22's per-layer corollary — S22 says "static before empirical at workstream scope"; S26 says "static-round-N+1 before patch at intra-workstream scope."
- S21 (WS-H step-5b) + S23 (WS-I step-3) + S25 (WS-C29b step-1, awaiting promotion at next close-out): all assertion-side / planning-level shape-family insights. S26 is a methodology-level insight peer to S22.

**Methodology insights running total: 22 → 23 (S26 promoted).** S25 (strategic-framing-vs-source-modality) remains a candidate awaiting its third-instance confirmation (currently 2 instances: C29b + Surface E step-1).

### §17.1 Phase 1 second-pillar re-selection candidates

Surface E retirement consumes the Phase 1 second-pillar slot without delivery. Re-selection candidates (ranked by remaining cohort confidence + budget economics):

| Candidate | Fix surface category | Expected arc | Budget cost |
|---|---|---|---|
| **§11.3 item 5 — Recent-Overs partial-render** (RECOMMENDED) | Possibly assertion-side per WS-I pattern reuse | 3-step assertion-side if confirmed | 0/5 if assertion-side; 1/5 if pipeline-side |
| §11.3 item 4 — Per-batter-ledger conservation | Narrow scope, UI-visible | 3-5 step | 0-1/5 |
| WS-D §3.5 Layer 1a — `_derive_dismissed_name` close (HE survivor from C29b) | Pipeline-side; S12 plumbing concern | 9+ step multi-arc | 1-2/5 |
| WS-F bowler-misattribution — γ-bowler-w adjacent surfaces | Narrow pipeline-side | 5-9 step | 1-2/5 |

**Recommended Phase 1 second pillar: §11.3 item 5 (Recent-Overs partial-render).** If static investigation confirms an assertion-side shape, delivers budget-neutral UI closure mirroring WS-I economics. Step-1 investigation memo authorized at next session.

## §18 Surface_pair catalogue entry — phantom-wicket as architectural-known-defect

Cross-reference: `files/docs/investigations/surface_pair_defect_class_family.md` §2.10 (new entry) — phantom-wicket-detection-class with F1017 anchor + retirement reference to this memo §13-§18. Defect persists in production; documented as architectural-known-limitation pending future Scout-primitive extension or ML-classifier-trained telemetry.

**Arc retired.**

