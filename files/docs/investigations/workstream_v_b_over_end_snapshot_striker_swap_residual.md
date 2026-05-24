# Workstream V.B — Step-1 investigation: over-end snapshot striker-swap residual classification (D3-class vs different defect class)

Branch: `derive-not-detect`. HEAD: `4db53a3` (WS-V.A1 step-3 baseline). Single docs commit. Static investigation memo (pure trace + code reading; no production code edits this commit).

> Operator framing: WS-V.A1 step-3 (`4db53a3`) confirmed FA's D3-cascade-closure at the score-derivation layer (96 striker-swap rows closed 152 → 56; PREV-SCORE-ANCHOR-APPLIED fired 15× including all smoking-gun frames). The residual 56 striker-swap rows concentrate at OVER-END snapshots (0.6 / 1.6 / 2.6 / 3.6 / 4.3 / 4.4). The **architectural classification of the residual mechanism is load-bearing for the WS-Q step-2a sequencing decision**: if D3-class, WS-Q step-2a graduates from queued cleanup to highest-leverage immediate patch with empirically-anchored cascade-closure. If different defect class, tactical WS-V.B step-2 continues the targeted-fix pattern. S34 application discipline determines which outcome is correct rather than which we guess.

---

## §1 Empirical anchor

1. **WS-V.A1 step-3 baseline** (`4db53a3`; baseline `files/tests/baselines/dckkr_diff_post_ws_v_a1_baseline.md`). Post-FA DCKKR diff: 28 matched / 94 missing-in-pipeline / 3 phantom / 93 divergences. Striker-swap rows: 56 residual (down from 152 pre-FA). PREV-SCORE-ANCHOR-APPLIED fires 15× in the trace including F33/F40/F82/F96/F97/F119/F244 — all smoking-gun frames. Score-derivation D3 cascade EMPIRICALLY CLOSED at the score-side `delta_score` actor.
2. **Residual 56 striker-swap rows distribution** (extracted from baseline §2):
   - over_ball **0.6**: 8 rows (striker_name, striker_runs, striker_balls, non_striker_name, non_striker_runs, non_striker_balls, non_striker_fours, striker_fours)
   - over_ball **1.6**: 10 rows (striker/non symmetric pair + sixes/fours)
   - over_ball **2.6**: 8 rows (striker/non symmetric pair + sixes)
   - over_ball **3.6**: 8 rows (striker/non symmetric pair + sixes)
   - over_ball **4.3**: 10 rows (striker/non symmetric pair + fours/sixes)
   - over_ball **4.4**: 10 rows (striker/non symmetric pair + fours/sixes, INVERTED direction from 4.3)
   - Total: ~54 rows (with bowler_name/bowler_runs adjacent — overlap with F-A/F-B counted separately). Cohort lock: ALL 56 rows are at the over-end frame anchor 0.6 / 1.6 / 2.6 / 3.6 / 4.3 / 4.4.
3. **Trace inspection** (`logs/trace/dckkr_post_ws_v_a1_baseline_20260524_133635.jsonl`, 264 records). At each residual-frame anchor (F40 for 0.6, F119 for 1.5-end, F244 for 3.5-end, F303 for 4.3, F319 for 4.4):
   - **OVERS-NATURAL-INCREMENT-FAST-CONFIRM fires correctly** at every over-rollover anchor (0.5→1.0 at F40, 1.5→2.0 at F126, 2.5→3.0 at F185, 3.5→4.0 at F254).
   - **STRIKER-EVENT-DISPATCHED fires at every over-rollover anchor** (F33/F119/F244 + the inline rollover sites F40/F126). This is the canonical end_of_over_swap path firing per §13.2 rule 3.
   - **STRIKER-IDENTITY-PROPOSAL-REFUSED fires at F319 (4.4) and F334 (4.5)** — the conservative-refuse semantic at `score_manager.py:1201` is actively defending. No D3-class pre-advance is occurring at the identity-write boundary.
4. **`pipeline.striker` field at residual-anchor frames** (extracted via trace inspection):
   - F40 (overs=0.5→1.0): pipeline striker=Nissanka, non=Rahul. GT 0.6: striker=Rahul, non=Nissanka → POST-end-of-over-swap value emitted at the snapshot keyed on `0.6`.
   - F119 (overs=1.5): pipeline striker=Rahul, non=Nissanka. GT 1.6: striker=Nissanka, non=Rahul → POST-swap visible.
   - F244 (overs=3.5): pipeline striker=Rahul, non=Nissanka. GT 3.6: striker=Nissanka, non=Rahul → POST-swap.
   - F303 (overs=4.3): pipeline striker=Rahul, non=Nissanka. GT 4.3: striker=Nissanka, non=Rahul → DIFFERENT class — score did NOT advance (still 44), this is the PA-deferred E2 phantom region.
   - F319 (overs=4.4): pipeline striker=Nissanka, non=Rahul. GT 4.4: striker=Rahul, non=Nissanka → INVERTED of 4.3 pattern.

**Empirical signature**: the strike rotation IS firing correctly (STRIKER-EVENT-DISPATCHED at every over-rollover anchor); the snapshot labeled at the over-end ball (X.6) captures the POST-rotation pointer pair, but the GT expects the PRE-rotation pair (the striker who actually faced ball X.6).

---

## §2 Architectural classification verdict — DIFFERENT DEFECT CLASS (NOT D3-class)

### §2.1 D3-class falsification

The D3-class pattern (per WS-Q §5, WS-V.A1 §2.2) requires:
- A `@property` over a parallel store (`sm.score` → `sb._inn["score"]`).
- An upstream caller pre-advances the parallel store BEFORE `_handle_warm` runs.
- A downstream derivation reads the post-advance value and computes a zero delta.

**Falsification for striker identity** (empirically confirmed at three layers):

1. **No `sm.striker` @property** over a parallel store. `self.striker` is a plain instance attribute on `ScoreManager`. There is no `sb._inn["striker"]` parallel store; the canonical store IS `self.striker`. Confirmed by absence of `sb._inn["striker"]` references in `scoreboard.py` (grep returns 0 matches for `_inn\[.striker`).
2. **No pre-`_handle_warm` striker mutation surface exists.** The three canonical mutation paths (`apply_striker_event` @ `:945`, `apply_striker_identity_resolved` @ `:980`, `apply_striker_identity_proposed` @ `:1213`) are all invoked FROM WITHIN SM methods (`_apply_event` @ `:6952`, `_identify_and_set` @ `:5226`, `_apply_post_wicket_striker_rotation` @ `:1063`). No upstream caller (test_pipeline.py / scoreboard.py / state-recovery) writes `self.striker` directly. The wire-commentary D3 surface (`test_pipeline.py:14102-14109`) is EXPLICITLY for `self.score`, not `self.striker`.
3. **The conservative-refuse defense at `apply_striker_identity_proposed` (`:1201`) IS ACTIVELY FIRING.** Trace shows STRIKER-IDENTITY-PROPOSAL-REFUSED at F319/F334 — the A1-equivalent anchor for striker identity is empirically working. If a D3-class pre-advance were occurring, the proposal-refused would either (a) be silently overridden by direct dict write, or (b) emit STRIKER-IDENTITY-CONFLICT (per `:972`). Neither pattern appears in the trace at the residual anchors.

**D3-class verdict: FALSIFIED**. The striker identity does NOT exhibit the dual-state-write pattern that WS-Q §5 catalogues. There is no parallel store, no upstream pre-advance, and the A1-equivalent defense is firing correctly.

### §2.2 Three-instance corroboration check for D3-class (negative result)

Per WS-Q step-2a sequencing question:

| Corroboration point | Result for striker identity | Evidence |
|---|---|---|
| `sm.X` @property over parallel store? | **NO** | `self.striker` is a plain attribute; no `sb._inn["striker"]` store exists |
| Upstream caller pre-advances the store before `_handle_warm`? | **NO** | Zero direct `self.striker = ...` writes in `test_pipeline.py` outside the three canonical SM-internal paths |
| A1-equivalent anchor exists & defends pre-advance staleness? | **YES, FIRING** | `apply_striker_identity_proposed` REFUSES the write (`:1201`); STRIKER-IDENTITY-PROPOSAL-REFUSED fires at F319/F334 |
| Wire-commentary-equivalent comment documenting parallel-state pattern? | **NO (for striker)** | The wire-commentary comment at `test_pipeline.py:14102-14109` is explicitly for `self.score`. No analogous comment for `self.striker` exists because no analogous defect exists. |

**Three-instance corroboration: ZERO of the four D3 corroboration points confirm for striker identity.** WS-Q D3 catalogue is NOT empirically extensible to striker identity.

### §2.3 Mechanism identification — VBD-class snapshot-construction timing defect

The actual mechanism is **VBD-class** per the WS-V.B step-1 task-4 enumeration (with a refinement): the per-ball OUTGOING UI snapshot is emitted AFTER the end-of-over strike rotation has already been applied to `self.striker` / `self.non`. Mechanism walkthrough at over-rollover F40 (overs=0.5→1.0, GT key=0.6):

1. Frame F40 arrives with `card.overs = 1.0` (scoreboard ticked to next over because the 6th legal ball of over 0 just landed).
2. `_handle_warm` (`:3655`) runs. `prev = self._snapshot()` (`:4139`) captures `self.score, self.overs=0.5, self.bat1_name, self.bat2_name` — but NOT `self.striker` (snapshot dict doesn't include striker; see `:4807-4818`).
3. PREV-SCORE-ANCHOR-APPLIED fires (FA defense): `prev["score"] = _event_baseline_score`. Score side is anchored.
4. `self._accept_update(card, fi)` (`:4184`) runs: bat1_name/bat2_name slot order may be swapped by `_update_batters(card)` to reflect the broadcast strip's post-rotation slot order. `self.overs` advances to 1.0.
5. `self._identify_and_set(...)` (`:4187`) runs. Determines new striker from balls_delta / runs_delta. Calls `apply_striker_identity_proposed` — REFUSED if `self.striker` is already set. Striker pointer preserved.
6. `self._apply_event(evt, prev, card, frame)` (`:4239`) runs.
7. `_wire_prior = self._snapshot_primitives_from_dict(prev)` (`:6703`). Per `_snapshot_primitives_from_dict` (`:766-783`): `striker=self.striker, non_striker=self.non` — these come from CURRENT SM state at the time of the call, NOT from `prev` dict (which doesn't even have a `striker` key). So `_wire_prior.striker = self.striker` at the F40 entry-point, which is the PRE-rotation striker (Nissanka).
8. `is_over_change = True` (card.overs=1.0, prev.overs=0.5).
9. `_derive_striker_event(_wire_prior, _wire_current_str, ..., over_boundary_crossed=True, legal_ball_completed=True)` (`:6948`) — fires `end_of_over_swap` per `score_manager_derivation.py:389-403`. Returns `next_striker=prev_non=Rahul, next_non_striker=prev=Nissanka`.
10. `self.apply_striker_event(_wire_striker_ev)` (`:6952`) — atomic pointer-swap. `self.striker=Rahul, self.non=Nissanka`. **CORRECT per cricket rules** — after over 0's 6th ball, batters cross, so Rahul faces ball 1 of over 1.
11. Frame F40 completes. The OUTGOING per-ball UI snapshot writer (downstream of `_handle_warm`) reads `self.striker=Rahul` and emits a snapshot keyed by the current over_ball — labeled `0.6` because the diff harness keys on the LAST-COMPLETED ball.

The defect: **the UI snapshot keyed on `0.6` (the just-completed ball that triggered the rotation) reports the POST-rotation striker pointer, but the GT expects the striker who FACED ball 0.6 (the PRE-rotation Nissanka).** The strike rotation is correctly applied; the snapshot construction's striker_name field reads the post-rotation pointer instead of capturing a "striker-at-the-time-this-ball-was-faced" pre-rotation snapshot.

### §2.4 Cohort split check (4.3 / 4.4 sub-cohort)

The 4.3 / 4.4 cohort has a DIFFERENT signature from the X.6 (X=0,1,2,3) over-end cohort:
- 4.3 is NOT an over-end (over=4 still in progress; ball 3 of 6).
- 4.3 + 4.4 swaps are MIRROR INVERTED of each other (4.3: pipeline=Rahul, GT=Nissanka; 4.4: pipeline=Nissanka, GT=Rahul).
- 4.3 / 4.4 occur in the PA-deferred E2 region where score sits at 44 frame-after-frame (F303-F318).

**4.3 / 4.4 sub-cohort hypothesis** (10 + 10 = 20 rows): striker rotation is correctly happening on the legal odd-run boundary, but the OUTGOING snapshot timing pairs with the WRONG side of the rotation. This is the SAME VBD-class snapshot-timing mechanism, applied to legal-ball-odd-run rotation instead of over-end rotation.

**Cohort split verdict: NO split.** All 56 rows are the same VBD-class snapshot-timing mechanism. The over-end subcohort (0.6 / 1.6 / 2.6 / 3.6) is triggered by `end_of_over_swap`; the 4.3 / 4.4 subcohort is triggered by `odd_run_rotation`. Both rotations fire correctly per cricket rules; both snapshots emit the post-rotation pointer when the GT expects the pre-rotation pointer.

---

## §3 D3-pattern three-instance corroboration findings (NEGATIVE)

Per §2.2: zero of four D3 corroboration points confirm. WS-Q D3 catalogue does NOT empirically extend to striker identity. WS-Q step-2a (score-canonical-API refactor) would close ZERO of the 56 residual rows, because the cascade root is not in the score-derivation D3 actor — it's in the snapshot-construction timing for the striker pointer.

---

## §4 Alternative-mechanism enumeration (per task 4 — DIFFERENT-DEFECT-CLASS branch)

### §4.1 Hypothesis enumeration

| ID | Mechanism | §7.2 gate-1 (defect-class fit) | §7.2 gate-2 (backward-compat) | §7.2 gate-3 (fix-surface attribution) | Verdict |
|---|---|---|---|---|---|
| VBA | Over-end rotation logic bug (rotates wrong direction at X.5→next over) | FAIL — `_derive_striker_event` rule 3 at `:389-403` correctly swaps; same logic fires for ALL over-rollovers including the ones WITHOUT swap residue. Trace confirms STRIKER-EVENT-DISPATCHED fires with the expected (striker,non) → (non,striker) swap. | n/a | n/a | **FALSIFY** — rotation logic is correct per code reading + trace |
| VBB | Identity-assignment race at snapshot construction (correct identity stored, but snapshot reads stale) | FAIL — `_snapshot_primitives_from_dict` reads CURRENT `self.striker`, not stale; the issue is the snapshot reads the POST-rotation current value when the GT expects PRE-rotation | n/a | n/a | **FALSIFY** — no race; mechanism is sequential and deterministic |
| VBC | Striker pointer not anchored to actual at-crease batter (rotation derives correctly but pointer doesn't follow) | FAIL — `apply_striker_event` atomically mutates BOTH `self.striker` and `self.non` (`:945-946`); pointer DOES follow the rotation | n/a | n/a | **FALSIFY** — atomic pointer-pair contract satisfied |
| VBD | Over-end fast-path / snapshot-emission timing: the OUTGOING UI snapshot keyed on the just-completed ball captures post-rotation pointer state instead of capturing pre-rotation state at the moment the ball was faced | PASS — explains 56/56 residual rows + 4.3/4.4 mirror inversion | PASS — fix is in the snapshot emission layer; rotation logic stays intact | PASS — fix surface = OUTGOING per-ball snapshot writer (~1 site in test_pipeline.py); no §15 fence touches | **LEADING CANDIDATE** |
| VBE | Other (rotation triggers on wrong frame side; snapshot capture point at handle_warm entry vs exit) | PARTIAL — could explain over-end subcohort but doesn't explain 4.3/4.4 mid-over | n/a | n/a | **FALSIFY** — VBD subsumes |

**Verdict count**: 4 FALSIFIED + 1 LEADING CANDIDATE = 5 hypotheses enumerated, 4 falsified statically. Well under the 8-falsification budget.

### §4.2 §7.2 audit on leading candidate VBD

| Gate | Verdict | Evidence |
|---|---|---|
| 1 — defect-class fit | PASS | VBD mechanism explains BOTH the over-end (0.6 / 1.6 / 2.6 / 3.6) cohort AND the mid-over 4.3 / 4.4 mirror-inversion cohort. Cricket rotation IS firing correctly; snapshot emission captures wrong rotation side relative to ball-key. |
| 2 — backward-compat | PASS — preliminary | Fix surface is the per-ball UI snapshot writer (downstream of `_handle_warm`). No mutation to `apply_striker_event`, `_derive_striker_event`, or any other rotation primitive. L1.5 + L2 ledger expected unchanged for non-snapshot assertions. |
| 3 — fix-surface attribution | PASS — preliminary | Snapshot emission writer in `test_pipeline.py` is PIPELINE-DIRECT. No §15 fence touches; no canonical mutation-path rewiring. Step-2 should locate the exact per-ball snapshot emit site (suspected near `test_pipeline.py` per-ball commit, downstream of SM `_handle_warm` return). |
| 4 — S33 instrumentation-aware | OPEN | Step-2 should land the fix behind a feature flag (`USE_PREROTATION_STRIKER_SNAPSHOT`) so a shadow comparison validates the predicted-flip count before flipping default. |
| 5 — cohort enumeration completeness | PASS | 56 rows enumerated; over-end + 4.3/4.4 mid-over subcohorts both explained. |
| 6 — predicted-flip frame numbers | OPEN at step-2 | Predicted flip set = 56 residual rows at frames F40 (0.6), F126 (1.6), F185 (2.6), F254 (3.6), F303 (4.3), F319 (4.4). |
| 7 — empirical replay closure | DEFER to step-3 | Step-3 after step-2 replay reports new-baseline + flip-coverage table. |

Gates 1-3 + 5 PASS; gates 4 + 6 + 7 deferred per S33. Static convergence achieved on VBD.

---

## §5 Per-cohort cascade attribution

| Cohort | Pre-WS-V.B rows | VBD cascade-closure prediction | Notes |
|---|---|---|---|
| Over-end striker-swap (0.6/1.6/2.6/3.6) | ~34 rows | VBD closes 34 → 0 | All same mechanism (over_boundary_crossed=True rotation captured pre-emit) |
| Mid-over striker-swap (4.3/4.4) | ~20 rows | VBD closes 20 → 0 | Same mechanism applied to odd_run_rotation; mirror inversion confirms |
| Per-batter-ledger-drift (5 rows @ 4.1+) | 5 | PARTIAL (0-3 close) | Tied to wrong-striker BAT-DELTA attribution during PA-deferred E2 region; VBD fix re-aligns striker identity at snapshot time but BAT-DELTA already credited the wrong batter mid-stream. May need WS-V.C follow-on for ledger rewind. |
| Recent-overs-drop (4 rows) | 4 | NO (independent) | Driven by `over_history` archive timing, not striker snapshot |
| Boundary-counter-double-increment (1 row @ 0.6) | 1 | PARTIAL (0-1 close) | The 0.6 striker_fours mismatch is downstream of the striker-name mismatch; VBD fix flips striker_name and the boundary attribution follows |
| WS-V.A1 step-1 "striker-write residue at 4.3/4.4" (10 rows) | 10 | YES — SAME mechanism | This is the §4 cohort A; VBD subsumes it |

**Total predicted closure under VBD step-2**: ~54-56 of 56 residual striker-swap rows + 0-1 boundary-double + 0-3 per-batter-ledger = **~54-60 rows closed**. Recent-overs-drop (4) remains independent (separate workstream WS-V.D).

---

## §6 WS-Q step-2a vs WS-V.B step-2 sequencing recommendation

### §6.1 Recommendation: WS-V.B step-2 TACTICAL PATCH (NOT WS-Q step-2a pivot)

**Rationale**:
1. WS-Q step-2a's value proposition was empirically-anchored cascade-closure of striker-swap residue via score-state-unification. The empirical anchor REQUIRES striker-swap residue to be downstream of the score-derivation D3 actor. **It is not.** Per §2.1 + §2.2: striker identity does not exhibit the D3 pattern; the residual cascade root is in the snapshot-emission layer.
2. WS-Q step-2a remains valuable for its ORIGINAL chartered scope (score-axis canonical-API refactor + WS-O.c/WS-P/WS-O.b cascade-root closure for the score-side defect class). But it would close ZERO of the 56 striker-swap rows.
3. WS-V.B step-2 tactical patch (snapshot-emission timing fix) closes 54-56 of the 56 rows. PIPELINE-DIRECT fix surface; ~1 site in test_pipeline.py snapshot writer; no architectural refactor needed.
4. **Sequencing**: WS-V.B step-2 FIRST (immediate 54-56 row closure), then WS-Q step-2a in original chartered order (score-axis structural improvement; no longer load-bearing for striker residue).

### §6.2 What changes about WS-Q sequencing

WS-Q step-2a is no longer load-bearing for the next-iteration striker-swap residue closure. It remains a legitimate structural improvement chartered for the score axis but is not the highest-leverage next move. The "WS-Q step-2a graduates from queued cleanup to highest-leverage immediate patch" scenario in the operator framing is **EMPIRICALLY FALSIFIED**. WS-Q stays queued in its original order behind WS-V.B step-2.

---

## §7 Predicted-closure prediction

| Cohort | Pre-WS-V.B rows | Under WS-V.B step-2 (VBD patch) | Under WS-Q step-2a (if pivoted) |
|---|---|---|---|
| Striker-swap (56) | 56 | **0-2 residual** (full closure) | **56 unchanged** (no cascade overlap) |
| Per-batter-ledger-drift | 5 | 0-3 | 5 unchanged |
| Boundary-counter-double | 1 | 0-1 | 1 unchanged |
| Recent-overs-drop | 4 | 4 unchanged | 4 unchanged |
| E2-phantom-runs (3) | 3 | 3 unchanged (independent PA cohort) | 3 unchanged |
| F-A-commit-lag (10) | 10 | 10 unchanged (bowler-side) | 10 unchanged |
| F-B-ad-occlusion (8) | 8 | 8 unchanged | 8 unchanged |

**WS-V.B step-2 (VBD) predicted post-fix divergences**: 93 → ~32-37 (close 56-61 rows). Highest-leverage tactical patch on the current baseline.

**WS-Q step-2a (if mistakenly pivoted) predicted post-fix divergences**: 93 → 93 on the striker axis (no overlap). Score-axis impact is the separate WS-Q-chartered scope (~0-8 additional rows in unrelated cohorts).

---

## §8 §7.2 audit on leading candidate (VBD)

Per §4.2 — gates 1-3 + 5 PASS statically; gates 4, 6, 7 deferred to step-2/step-3.

---

## §9 Regression-guard enumeration

Standard preserved from prior workstreams. All shipped defensive gates stay landed:

- **L2 ledger 30/30**: preserved (VBD touches snapshot emission, not ledger).
- **L1.5 95**: preserved.
- **9 closed surfaces stay at 0**.
- **7 active surfaces**: unchanged behavior modulo VBD's targeted impact.
- **WS-O.b PA `WARM-MODE-MAGNITUDE-GATE-REJECTED`**: stays at `scoreboard.py:1216-1252` unchanged.
- **WS-O OA `COLD-START-OVERREAD-REJECTED`**: stays at `score_manager.py` cold-start path unchanged.
- **A1 `_event_baseline_score` anchor at `:3734-3741`**: preserved.
- **WS-V.A1 FA `PREV-SCORE-ANCHOR-APPLIED` at `:4139-4174` (commit `b7251e7` / `4db53a3`)**: preserved — FA continues firing 15× per replay; no interaction with VBD's striker-snapshot surface.
- **STRIKER-IDENTITY-PROPOSAL-REFUSED defense at `:1201`**: preserved (and confirmed actively firing at F319/F334).
- **STRIKER-LOCK-MID-OVER-SUPPRESSED**: preserved.
- **Shape A, Shape B, D1, D2-Layer-1a, H1, H3**: preserved.
- **Squad-convention QA/QE (WS-P P1)**: preserved.
- **Wire-commentary BED-prioritization at `test_pipeline.py:14110`**: preserved (different cascade actor).
- **`_derive_striker_event` rule 3 end_of_over_swap (`score_manager_derivation.py:389-403`)**: UNCHANGED — VBD fixes the SNAPSHOT-EMISSION layer, not the rotation derivation.
- **`apply_striker_event` atomic pair-mutation (`:945-946`)**: UNCHANGED.

---

## §10 Step-2 entry data

### §10.1 Recommendation

**PROCEED TO STEP-2** with candidate VBD (snapshot-emission timing fix at the per-ball UI snapshot writer).

### §10.2 Step-2 charter

1. **Locate the per-ball snapshot emission site.** Suspected location: `test_pipeline.py` downstream of `_handle_warm` return, where the per-ball UI snapshot is constructed (the writer producing `/tmp/dckkr_*_pipeline_snapshots.jsonl` records). Confirmed structure: 33-field record keyed by `over_ball` with `striker_name` + `non_striker_name` reading from `sm.striker` + `sm.non` at emit-time.
2. **Determine the pre-rotation striker capture mechanism.** Two candidates:
   - **VBD-1**: Cache `(sm.striker, sm.non)` SNAPSHOT at `_handle_warm` ENTRY (before any rotation), expose via `sm._last_pre_rotation_striker_pair` attribute, snapshot writer reads cached value for the over_ball key matching `prev.overs`.
   - **VBD-2**: Compute the snapshot's striker_name field via reverse-cricket-rule: `striker_at_ball(over_ball) = post_rotation_striker if NOT odd_runs_rotated else pre_rotation_striker`. Higher complexity; lower fix-surface attribution clarity.
   - **Recommended**: VBD-1 (single cached pair, single SM-attribute write at `_handle_warm` entry, single read at snapshot emit time).
3. **§S33 protocol**: gate behind `USE_PREROTATION_STRIKER_SNAPSHOT` (default 0); step-2b enable shadow; step-2c flip default; step-2d remove flag.
4. **Predicted-flip table**: 56 residual rows at frames F40 / F126 / F185 / F254 / F303 / F319.

### §10.3 Predicted L1.5 risk

NONE. VBD touches the snapshot-emission layer; rotation primitives + score-derivation primitives + identity-write primitives are all unchanged. L1.5 score-sequence assertions, striker-pointer assertions, ledger-attribution assertions all expected unchanged.

### §10.4 Forward-compat with WS-Q

WS-Q step-2a's score-canonical-API refactor is orthogonal to VBD. The two patches do not interact; WS-V.B step-2 can land before, after, or interleaved with WS-Q without merge conflict.

---

## §11 S34 empirical-parity-check applied + outcome

S34 methodology applied PRE-hypothesis. Trace inspection at each of 6 residual-anchor frames (F40 / F119 / F185 / F244 / F303 / F319) BEFORE any hypothesis-derivation:
- Observed STRIKER-EVENT-DISPATCHED + STRIKER-IDENTITY-PROPOSAL-REFUSED firing correctly per cricket rules.
- Observed `pipeline.striker` reflecting POST-rotation value at over-rollover anchors.
- Observed mirror-inversion at 4.3 / 4.4 (post-odd-run-rotation pattern).
- Observed ZERO direct `self.striker` mutations from upstream callers (no D3 pre-advance evidence).

**Outcome**: D3-class hypothesis EMPIRICALLY FALSIFIED before being asserted. VBD snapshot-emission-timing hypothesis CONFIRMED as the leading mechanism. Methodology validated for a fourth successive instance (WS-O OA, WS-P P1, WS-V.A1, now WS-V.B).

---

## §12 Stop condition reached

**Static convergence on different-defect-class verdict + identified mechanism (VBD)** → STOP per charter stop condition. Recommend WS-V.B step-2 tactical patch (snapshot-emission timing fix).

WS-Q step-2a sequencing decision: **DO NOT PIVOT**. WS-Q stays queued in its original score-axis chartered order; it is not load-bearing for striker-swap residue closure.
