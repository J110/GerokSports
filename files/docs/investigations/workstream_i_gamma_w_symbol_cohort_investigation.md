# Workstream I — γ-w-symbol cohort static investigation (step-1)

**Date.** 2026-05-23.
**Branch.** `derive-not-detect` @ HEAD = `f6cbcbd` (WS-H step-9 close-out).
**Empirical-budget status.** 2/5 — UNCHANGED (static-only this step; no replay consumed).
**Outcome.** Single static-falsification chain converges on **HA — assertion-side Shape B (trace-schema-presence guard)**. Cohort-closure **UNIFIED-4** at the predicate site. HB / HC / HD / HE all statically falsified. C21 UI-layer Phase 3 escalation NOT triggered (HC is irrelevant to this cohort — see §5.HC). γ-w-symbol on validate_ws_h_step7 is a trace-schema heterogeneity false-positive, not a pipeline defect. New sub-finding **S23** (trace-schema-presence as assertion-precondition).

---

## §1 Empirical anchor — 4-frame cohort table (reconstructed from validate_ws_h_step7)

Source trace: `logs/trace/validate_ws_h_step7_20260523_172140.jsonl` (749 frames, 0% `ui_after`-populated).

Wicket-event detection uses `trace_beta_sm_wicket_dispatch` (first occurrence per frame, per the assertion's `break`-after-first loop body at `trace_session_assertions.py:308`). Four wicket events surface in this trace:

| Wicket frame | Dismissed (per beta tag) | Overs | `expected_position` (from `overs.ball−1`, or 5 for `.0`) | F<wicket+1> | `(records[i+1].get("ui_after") or {}).get("this_over") or []` | γ-fow-name co-fail? | Pre/post-H1 |
|---|---|---|---|---|---|---|---|
| **F679** | Pathum Nissanka | `8.0` | 5 | F680 | `[]` (key absent — see §3) | YES (`no_prev_striker`) | Pre-H1 baseline (S17 original anchor) |
| **F855** | Nitish Rana | `9.5` | 4 | F856 | `[]` (key absent) | NO (γ-fow-name PASS at F855) | Pre-H1 baseline |
| **F948** | KL Rahul | `10.1` | 0 | F952 | `[]` (key absent) | YES (`no_prev_striker`) | Post-H1 cohort-exposure (S20) |
| **F1017** | Pathum Nissanka | `10.4` | 3 | F1018 | `[]` (key absent) | YES (`no_prev_striker`) | Post-H1 cohort-exposure (S20) |

**The +1 frame identification.** F1017 is the unspecified 4th cohort frame. Dismissed = Pathum Nissanka at overs 10.4 (NOT Tristan Stubbs at 10.5 — see §2 for the multi-wicket-per-frame undercount caveat).

**Why "empty array" not "W missing from populated array".** Per §3, every record in this trace lacks the `ui_after` key entirely. The assertion's defensive `(records[i + 1].get("ui_after") or {}).get("this_over") or []` collapses to `[]`. The "empty array" semantics observed in WS-H step-5b §6 are not "this_over wiped" — they are "trace-schema does not emit ui_after for this trace path".

**Pre-H1 / post-H1 split.** F679+F855 predate H1 closure; F948+F1017 post-H1 (revealed by H1 unmasking — S20 second-instance). The split is empirically real for the assertion's *visibility surface* but is causally irrelevant to the FAIL reason — see §5.HE.

---

## §2 γ-w-symbol predicate body — verbatim + read-path documentation

`files/tests/trace_session_assertions.py:280-357` (function `assert_w_symbol_at_wicket`):

```python
for i, rec in enumerate(records):
    detected_overs: str | None = None
    for dec in _decisions(rec):
        if dec.get("tag") == "trace_beta_sm_wicket_dispatch":
            detected_overs = str(dec.get("overs") or "") or None
            break                                       # ← ONE WICKET PER FRAME
    if detected_overs is None:
        be = rec.get("ball_event") or {}
        if be.get("type") == "WICKET":
            ov_val = be.get("over")
            if ov_val:
                detected_overs = str(ov_val)
    if not detected_overs or "." not in detected_overs:
        continue
    try:
        ball_within = int(detected_overs.split(".", 1)[1])
    except (ValueError, IndexError):
        continue
    expected_position = 5 if ball_within == 0 else ball_within - 1
    if expected_position < 0:
        continue
    if i + 1 >= len(records):
        failures.append({..., "reason": "no_next_record"}); continue
    next_this_over = (
        (records[i + 1].get("ui_after") or {}).get("this_over") or [])   # ★ READ SURFACE
    window = next_this_over[expected_position:]
    if "W" not in window:
        failures.append({..., "next_this_over": next_this_over, "window": window})
```

**Read path.** `records[i + 1].ui_after.this_over` — a list-of-tokens snapshot of the UI mirror's over-strip published by `UIMirror.snapshot_compact` (`files/trace_emitter.py:651`).

**FAIL terminal predicate.** `"W" not in next_this_over[expected_position:]`.

**Lenient position rule.** Already in place — W must appear at-or-past `expected_position` (extras `Wd`/`Nb` shift the wicket-ball's slot downstream).

**"Empty array" vs "W missing from populated array".** Both fail `"W" not in []` / `"W" not in [".","1","6","1","4","."]`. The assertion is structurally agnostic to *why* the window is empty — it treats schema absence (`ui_after` missing) and state-layer revert (`this_over = [".","..."]`) as the same FAIL class. This is the load-bearing defect: schema-absence false-positives are indistinguishable from real state-layer reverts in the FAIL signal.

**Multi-wicket-per-frame undercount.** At F1017 the trace contains TWO `trace_beta_sm_wicket_dispatch` tags (Pathum Nissanka @10.4 + Tristan Stubbs @10.5 — verbatim from the F1017 scorer.decisions list). The `break`-after-first loop counts only the first. The Stubbs wicket is structurally invisible to γ-w-symbol on this trace. Logged for §10 / S23 follow-up; out-of-scope for the step-1 fix.

---

## §3 `ui_after.this_over` emission ordering — and the trace-schema heterogeneity

**Producer site.** `UIMirror.snapshot_compact` (`files/trace_emitter.py:599-656`) builds `{"this_over": list(s.get("this_over") or []), ...}` from the mirror's internal `_state`. The mirror is updated via `apply(payload)` which `deep_merge_ui` merges into `_state` (`files/trace_emitter.py:590-591`). The `ui_after` snapshot is captured *after* `apply` runs against the current frame's UI payload, so on a normal live-pipeline trace, frame `i+1`'s `ui_after.this_over` reflects the state *after* frame `i+1`'s UI delta (including any wicket symbol that was published between frames `i` and `i+1`).

**Ordering on live pipeline (where `ui_after` is populated).** Per a wicket commit at F<wicket>, the SM `apply_wicket_event` path emits `THIS-OVER-TOKEN-APPENDED raw=W wicket_flag=true` (verified at F679 / F855 / F948 / F1017 — all four cohort frames show the W token append in their own scorer.decisions). The UI mirror's `this_over` list extends with `"W"` synchronously in the same publish cycle. F<wicket+1>'s `ui_after` snapshot SHOULD therefore include the W.

**The trace-schema heterogeneity (load-bearing finding).** Cross-fixture survey of all 150 traces in `logs/trace/`:

| Trace cohort | `ui_after` key present | Wicket-detection method |
|---|---|---|
| `validate_dckkr_*`, `validate_20*`, `validate_gtrr_*`, `watch_*`, `local_*`, `run*`, `anchor*`, `dump_*`, `fix*`, `frameage_*`, `lag_test_*`, `mac_test_*`, `auto_*` | **100%** (51 traces) | `ui_after.fow_count` increase fallback + (post-C19A3) `trace_beta_sm_wicket_dispatch` |
| `replay_*` (all variants — `gtrr_*`, `dckkr_*`) | **0%** (38 traces, 749 frames each for `replay_dckkr_*`) | `trace_beta_sm_wicket_dispatch` only |
| `validate_ws_h_step*`, `validate_shape_a_*`, `validate_surface_b_*` | **0%** (5 traces, 749 frames each) | `trace_beta_sm_wicket_dispatch` only |

**Implication.** Every `replay_*` / `validate_ws_h_*` / `validate_shape_*` / `validate_surface_*` trace's wicket-event surface is invisible to γ-w-symbol via the *intended* read path. The assertion silently degrades to "FAIL on every detected wicket" because `next_this_over = []` and `"W" not in []`. The 4 FAILs on validate_ws_h_step7 are entirely produced by this degradation — they are not pipeline-defect signal.

**Root of the schema heterogeneity.** Replay paths bypass the UIMirror `apply` cycle (they replay raw frames through SM without re-publishing UI deltas), so the trace-emitter's UI snapshot is never populated. This is an emission-path completeness gap, not a UI/state mismatch. It is out-of-scope for WS-I step-2 (separate workstream: replay-path trace-emitter parity) but motivates the Shape B fix in §5.HA.

---

## §4 `this_over` writer enumeration — §15-fence audit

Sites that mutate `self.this_over` or its eyes-side equivalent (`over_mgr.this_over`), per `files/score_manager.py` grep:

| Site | Line | Tag emitted | §15-fence status |
|---|---|---|---|
| Init | `:527`, `:1974` | n/a | Reset path — fenced (cold-start + cascade-drain) |
| `apply_this_over_token` (canonical write — single token append per legal ball) | `:1222-1241` | `THIS-OVER-TOKEN-APPENDED` | CANONICAL (§15 sole-writer per design) |
| `_rewrite_eyes_this_over_from_event` (Fix A — SM-authoritative rewrite of eyes-side stale `?` placeholders) | `:707-738` | n/a (slot-level `rewrite_token` no-op on out-of-range) | CANONICAL (§15-aligned — propagates resolved token to eyes-side post-commit) |
| Synthetic-over reseeding (multi-ball cascade) | `:2520` | (n/a, called from MB event handler) | CANONICAL (§15 multi-ball path) |
| Bootstrap / fresh-init early-join seeding | `:3499-3522` | n/a | CANONICAL (bootstrap-only, guarded by fresh-init predicate) |
| Multi-ball wire-through (§15 step 5) | `:6582-6612` | `THIS-OVER-TOKEN-APPENDED` (downstream via `apply_this_over_token`) | CANONICAL (§15 step 5) |

**§15-fence verdict.** No non-canonical writers found. Every site goes through `apply_this_over_token` OR a §15-aligned reseed path. **HB (producer-side defect)** is statically falsified at the enumeration step — there is no writer that would emit `W` and subsequently overwrite it with `.` between the wicket frame and the next frame.

**Producer-side proof from the cohort frames themselves** (verified by grep of `scorer.decisions` at F679/F855/F948/F1017):
- F679: `THIS-OVER-TOKEN-APPENDED raw=W wicket_flag=True` + `SYNTHETIC-WICKET-DISPATCHED this_over_token=W`
- F855: `THIS-OVER-TOKEN-APPENDED raw=W wicket_flag=True` + `SYNTHETIC-WICKET-DISPATCHED this_over_token=W`
- F948: `THIS-OVER-TOKEN-APPENDED raw=1+W wicket_flag=True` + `SYNTHETIC-WICKET-DISPATCHED this_over_token=W`
- F1017: `SYNTHETIC-WICKET-DISPATCHED this_over_token=W` (×2 — Nissanka @10.4 + Stubbs @10.5) + `THIS-OVER-TOKEN-APPENDED raw=W`

The producer writes `W` correctly at every cohort frame. No reversion event observed downstream within the same trace. HB ruled out.

---

## §5 Hypothesis enumeration + static falsification

§7.2 gates 1-3 applied statically to each. No empirical replay consumed.

### HA — Assertion-side (Shape B: schema-presence guard) — **LEADING / CONFIRMED**

**Shape.** Add a schema-presence precondition to the FAIL terminal: when `records[i+1].get("ui_after") is None`, treat the wicket as INAPPLICABLE-to-this-read-surface (skip), not FAIL. Preserve the existing FAIL capability on ui_after-populated traces (the C21 state-layer revert capability remains load-bearing).

**Gate 1 — predicate falsifies cohort.** PASS. All 4 cohort fires originate from `ui_after = None` (per §3). A presence guard skips all 4. Cohort closes to 0 FAIL on validate_ws_h_step7.

**Gate 2 — does not break preserved capability.** PASS. On `validate_dckkr_20260521_155356` (the canonical C21 baseline with `ui_after` populated 100%), the guard never triggers — the assertion continues to FAIL on real state-layer reverts (Rahul ov 5.0 + Rana ov 8.0 W→·) per the C21 baseline. Nissanka's UI-layer-only revert (per Architecture §0.4 C21 finding) was never visible at the state-layer surface and is correctly NOT-fired by the existing predicate; the guard preserves that distinction.

**Gate 3 — fix-surface attribution.** PASS. Assertion-side only. No production code edits. Mirrors WS-H step-5c Shape A's fix-surface-attribution discipline (the §15-fence enumeration in §4 affirmatively rules out the producer side). **Distinct shape from Shape A**: Shape A was canonical-resolution graceful-degradation on derived state; Shape B is schema-precondition graceful-skip on trace read-surface. Two-shape family confirmed (see §9 / S21 second instance).

**Status.** Leading candidate. Cohort-closure **UNIFIED-4**.

### HB — Producer-side (this_over writer defect) — **FALSIFIED**

**Shape.** A non-canonical writer overwrites `W` with `.` between wicket commit and next frame.

**Gate 1.** FAIL. §4 enumeration shows no non-canonical writers; §15 fence intact. Producer-side proof at the 4 cohort frames shows `THIS-OVER-TOKEN-APPENDED raw=W` fires at every wicket commit and no token-overwrite event follows. The downstream `[]` is not a write — it is the trace-schema absence per §3.

**Gate 2 / 3.** Not reached.

**Status.** Falsified at gate 1 (static). No empirical budget consumed.

### HC — UI-layer revert (C21 precedent reuse) — **STATICALLY FALSIFIED FOR THIS COHORT**

**Shape.** State layer + trace emission write W correctly, but the UI render layer reverts to `·` in the WebSocket → React path (the C21 Nissanka pattern at validate_dckkr_20260521_155356 frame 855).

**Gate 1.** FAIL **as the cohort root**. The C21 finding (Architecture §0.4) requires the trace state to PRESERVE W correctly at F<wicket+1>.this_over while the UI render diverges. This trace's `ui_after` is absent entirely — neither the state-layer signal nor the UI-render signal is observable here. The 4 FAILs cannot be UI-layer reverts because there is no UI-layer state in the trace to revert FROM. The defect class C21 names requires a `ui_after`-populated trace; this trace is not such a trace.

**Critical fork resolution.** The user's decisive-factor framing — "HC is the architecturally-significant fork; if confirmed it retires WS-I and pivots to Phase 3" — resolves to NOT-CONFIRMED here. HC cannot be confirmed on a trace where the UI-render surface is unobservable. **Phase 3 escalation NOT triggered.** The C21 UI-layer findings on validate_dckkr_20260521_155356 / frame 855 / Nissanka remain valid as their own catalogue entry; they are simply not the cause of the validate_ws_h_step7 4-fire cohort.

**Caveat.** A separate latent UI-layer-revert defect could still exist on the replay-path runtime; Shape B does not falsify that possibility. It IS falsified that THIS COHORT'S 4 fires are caused by it. If a future trace fixture populates `ui_after` on the replay path AND γ-w-symbol fires there in a W-present-state-layer + W-absent-UI-layer pattern, that would re-open HC. Until then, no Phase 3 escalation is justified by step-1's evidence.

**Status.** Statically falsified for this cohort. No empirical-budget cost. C21 catalogue entry preserved; UI-layer Phase 3 workstream NOT opened.

### HD — Frame-ordering / snapshot timing — **FALSIFIED**

**Shape.** F<wicket+1>'s `ui_after.this_over` is snapshotted BEFORE the canonical W write commits, so W appears at F<wicket+2> or later. Assertion's `i+1` lookahead is too narrow.

**Gate 1.** FAIL. Per §3, every record in this trace lacks `ui_after` entirely — there is no F<wicket+1> snapshot to be early or late. Even widening the lookahead to `i+2`, `i+3`, ... finds no `ui_after` data anywhere. The defect class HD names requires `ui_after` to exist somewhere in the trace tail; it does not.

**Status.** Falsified at gate 1 (static).

### HE — Cohort split (pre-H1 D-chain residuals vs post-H1 cohort-exposure) — **FALSIFIED**

**Shape.** F679+F855 (pre-H1 baselines) share root X; F948+F1017 (post-H1 cohort-exposure) share root Y; single fix does not close all 4.

**Gate 1.** FAIL. §3 shows all 4 fires share the IDENTICAL root: `records[i+1].ui_after = None` (schema absence). The pre/post-H1 distinction is irrelevant to the FAIL cause — it only affects whether the wicket-event is detectable at all (post-H1 unmasks F948+F1017's wicket-dispatch records), not whether the FAIL fires once detected. Both halves of the supposed split fail for the same Shape B reason.

**Status.** Falsified at gate 1 (static). Cohort is UNIFIED, not split.

---

## §6 Cohort-closure verification

**Claim under test.** A single assertion-side Shape B fix (schema-presence guard) closes all 4 cohort fires on validate_ws_h_step7 simultaneously, with zero pipeline-side change.

**Static analysis.** All 4 fires originate from `records[i+1].get("ui_after") is None`. The fix — `if records[i+1].get("ui_after") is None: continue` (or, equivalently, a typed "INAPPLICABLE" outcome distinct from PASS/FAIL) — eliminates all 4 by short-circuit before the `"W" not in window` predicate runs. No frame-specific carve-out needed.

**Cohort-closure status.** **UNIFIED-4.** Single edit, single read-surface guard.

**Cross-fixture survey** (γ-w-symbol baselines from on-disk traces, recoverable statically by running the assertion at HEAD-derived state without invoking the pipeline):

| Trace | `ui_after` populated? | Wicket events detected | Predicted γ-w-symbol after Shape B |
|---|---|---|---|
| `validate_dckkr_20260521_155356` (C20-anchor, C21 baseline) | YES (100%) | per C21 doc: 3 detectable | FAIL × 2 preserved (Rahul ov 5.0 + Rana ov 8.0 — state-layer reverts; Nissanka NOT-fired) |
| `validate_dckkr_20260521_070545`, `validate_dckkr_20260522_062844`, `validate_dckkr_20260522_063211`, `validate_gtrr_20260520_180715`, `validate_20260513_180911`, `validate_20260520_114437` (6 ui_after-populated validate fixtures) | YES | (varies — read on demand for gate 6) | Baseline preserved (whatever it was — Shape B is a no-op on these) |
| `validate_ws_h_step3_*`, `validate_ws_h_step7_*`, `validate_shape_a_*`, `validate_shape_a_20260523_114053`, `validate_surface_b_*` (5 ui_after-absent validate fixtures, 749 frames each) | NO (0%) | 4 each (via beta tag) | FAIL × 4 → **0** (schema-absence skip) on each |
| `replay_dckkr_*` (38 variants), `replay_gtrr_*` (1 variant) | NO (0%) | varies (749 each for post-rewrite cohort) | All FAIL × N → 0 (Shape B skip) |

**Phase 3 deferral check.** HC is statically falsified for this cohort (§5.HC). No Phase 3 escalation. WS-I closes at step-2 with the Shape B patch landing.

---

## §7 Audit obligation — §7.2 7-gate audit on leading candidate (HA / Shape B)

| Gate | Description | Status |
|---|---|---|
| **1** | Predicate falsifies the cohort (static) | PASS — §5.HA gate 1. |
| **2** | Does not break preserved capability (static) | PASS — §5.HA gate 2. C21 state-layer FAIL preservation on `validate_dckkr_20260521_155356`. |
| **3** | Fix-surface attribution (static, §15-fence-grounded) | PASS — assertion-side only; §4 enumeration falsifies producer-side; pure read-surface schema-precondition. |
| **4** | Regression-direction posture | PASS — Shape B is a strict-narrowing of FAIL conditions (treats a previously-FAIL case as INAPPLICABLE). It cannot introduce NEW false-positives. |
| **5** | Symmetric γ-bundle / η-bundle non-interference (static) | PASS — Shape B touches only `assert_w_symbol_at_wicket`; γ-fow-name + γ-bowler-w + η-cascade share no code with this site. |
| **6** | Concrete frame-list + predicted γ-w-symbol drop (empirical, deferred to step-2) | READY — F679 / F855 / F948 / F1017 enumerated; predicted FAIL × 4 → 0 on validate_ws_h_step7; cross-fixture predicted drops in §8. |
| **7** | Cross-fixture closure (deferred per step-1 stop-condition) | READY for step-2 — same on-disk re-run protocol as WS-H step-5c (assertion-only re-counting on the 13+ on-disk traces, no pipeline execution; zero empirical-budget cost). |

**All gates passable.** Step-2 patch is unblocked.

---

## §8 Predicted-flip table for step-2

| Detector | Trace | Pre-step-2 | Post-step-2 (Shape B) | Type |
|---|---|---|---|---|
| `trace_gamma_w_symbol_at_wicket` | `validate_ws_h_step7_20260523_172140` | FAIL × 4 | **0** | Cohort closure (UNIFIED-4) |
| `trace_gamma_w_symbol_at_wicket` | `validate_dckkr_20260521_155356` (C21 baseline) | FAIL × 2 | FAIL × 2 (preserved) | UNCHANGED — capability preservation |
| `trace_gamma_w_symbol_at_wicket` | all `replay_dckkr_*` (38 variants) | FAIL × N (schema-noise) | **0** | Schema-presence skip (noise → silence) |
| `trace_gamma_w_symbol_at_wicket` | `validate_ws_h_step3`, `validate_shape_a_*` × 2, `validate_surface_b_*` | FAIL × N (schema-noise) | **0** | Schema-presence skip |
| `trace_gamma_w_symbol_at_wicket` | all 51 `ui_after`-populated live traces | baseline (whatever each is — read on demand) | baseline (UNCHANGED) | No-op |
| `trace_gamma_fow_name_matches_striker_at_wicket` | all | per WS-H step-5c baseline | UNCHANGED | Disjoint code path |
| `trace_gamma_bowler_w_increment_on_dispatch` | all | per WS-H step-5c baseline | UNCHANGED | Disjoint code path |
| η-bundle | all | per WS-H step-7 baseline | UNCHANGED | Disjoint code path |

---

## §9 Sub-findings index (S23+)

### S23 — Trace-schema heterogeneity as assertion-precondition

**Statement.** Trace-replay paths can emit a structurally different trace record schema from live-pipeline paths, even when the assertion library is shared. Assertion read surfaces that access fields populated only on one schema variant (here: `ui_after.this_over` populated only on live-pipeline traces, never on `replay_*` / `validate_ws_h_*` / `validate_shape_*` / `validate_surface_*` traces) silently degrade to false-positives when run against the wrong schema. The degradation is asymptotically masked by the assertion's existing defensive `(... or {}).get(...) or []` chain — which converts the schema absence to an empty-list "data" that the predicate then operates on as if it were real signal.

**Why.** Assertion authors guard against missing intermediate keys with `or {}` / `or []` defaults because partial-record robustness is desirable for trace-replay across schema versions. But the same robustness pattern masks complete schema absence as a degenerate-but-actionable signal — exactly the wrong default for FAIL terminal predicates.

**How to apply.** Two complementary disciplines:
1. **Read-surface schema preconditions.** Each assertion's docstring should declare its schema preconditions (e.g., "requires `ui_after.this_over` populated"). When preconditions are not met, assertions should emit INAPPLICABLE, not FAIL.
2. **Inverse-defensive defaults at the assertion site.** Replace `(rec.get("ui_after") or {}).get("this_over") or []` with explicit `if rec.get("ui_after") is None: return INAPPLICABLE` for FAIL-terminal reads. The defensive default should be at the *type-coerce* layer (treat partial dicts as legitimate), not at the *presence* layer (the absence is information).

**Second-instance confirmation discipline.** Combined with S21 (assertion-vs-pipeline disambiguation from WS-H step-5b), S23 graduates assertion-side discipline from a one-instance Shape A (canonical-resolution graceful-degrade) to a two-shape family:
- **Shape A** (γ-fow-name, WS-H step-5c): graceful-degrade FAIL → INAPPLICABLE when a downstream canonical-resolution tag has produced the expected outcome via an alternate path.
- **Shape B** (γ-w-symbol, WS-I step-2): graceful-skip FAIL → INAPPLICABLE when the read-surface schema precondition is not satisfied.

Both shapes are assertion-side; both preserve the FAIL capability when the assertion's intended-signal preconditions hold; both close their respective cohorts UNIFIED. Methodology pattern: **S21 + S23 jointly mature the assertion-vs-pipeline disambiguation discipline into a reusable assertion-correctness audit pattern.**

### S23 cross-assertion audit obligation (load-bearing for future workstreams)

If `ui_after` is 0% on the replay-path cohort and 100% on live-pipeline traces, every other assertion in `files/tests/trace_session_assertions.py` that reads `ui_after.<anything>` (or any other schema-cohort-divergent path) carries the same silent-failure risk surface as γ-w-symbol — but inverted: an assertion that runs `if X in ui_after.<field>: PASS else FAIL` will silently PASS-by-luck on `ui_after = None` (because the defensive `or {}` default makes the membership check trivially false → PASS), masking real-pipeline defects on the schema-populated cohort. The γ-w-symbol cohort surfaced because its predicate-direction was FAIL-by-absence; PASS-by-absence predicates of the same shape would NOT surface in any current cohort scan.

**Audit obligation (must complete before WS-I step-2 commit lands).** Enumerate every assertion in `trace_session_assertions.py` that reads `ui_after.<...>`. For each, classify the predicate-direction (FAIL-by-absence vs PASS-by-absence) and the schema cohort each FAILs or PASSes on. Flag any PASS-by-absence assertions as candidates for a follow-up sub-workstream (S23-extension: silent-PASS variant). DO NOT patch them in WS-I step-2 — step-2's scope is locked to γ-w-symbol. Document the enumeration result inline at step-2 close-out.

### S23-corollary — Multi-wicket-per-frame undercount (logged for follow-up)

The `break`-after-first-`trace_beta_sm_wicket_dispatch` loop at `trace_session_assertions.py:308` undercounts when a single frame contains multiple wicket dispatches (observed at F1017: Nissanka @10.4 + Stubbs @10.5 both in scorer.decisions). Not load-bearing for the cohort fix in step-2 — but worth a separate predicate-design pass (S23-corollary in this memo; promote to standalone S-number only if a second instance surfaces).

### Schema-emission-parity follow-up (separate workstream candidate)

The `replay_*` / `validate_ws_h_*` / `validate_shape_*` / `validate_surface_*` cohort's missing `ui_after` snapshots is a trace-emitter completeness gap on the replay path (UIMirror.apply cycle not invoked during replay). NOT a pipeline correctness defect. Should be opened as its own workstream (call it WS-J or similar) to restore trace-schema parity between live and replay paths. Out-of-scope for WS-I; flagged for next session's first-action consideration.

---

## §10 Step-2 entry data — the patch step

**Patch surface.** Single edit at `files/tests/trace_session_assertions.py:335-336` (the `next_this_over = ...` line):

```diff
- next_this_over = (
-     (records[i + 1].get("ui_after") or {}).get("this_over") or [])
+ next_ui_after = records[i + 1].get("ui_after")
+ if next_ui_after is None:
+     continue                                              # Shape B: schema-precondition skip
+ next_this_over = next_ui_after.get("this_over") or []
```

Optional refinement (preferred per S23 discipline): emit a typed INAPPLICABLE outcome tag rather than `continue`, so the audit log distinguishes "no wickets to check" from "wickets present but schema absent". A `failures.append({"reason": "ui_after_schema_absent", "frame": ..., "_inapplicable": True})`-style record, filtered out of the FAIL count, would preserve the visibility for future fixture-curation work without polluting the regression-detector signal. Decision deferred to step-2 implementer.

**Tests to add (gate-6 permanent regression detector).**
- New unit case in `files/tests/test_anomaly_rules.py` (or a sibling `test_trace_session_assertions.py` if it exists — verify at step-2): a fixture record list with one wicket-dispatch frame followed by a frame that lacks `ui_after`. Pre-patch: FAIL × 1. Post-patch: 0.
- A second unit case: same fixture but with `ui_after.this_over = []` (populated empty list, not missing key). Should STILL FAIL — the schema IS present, the array IS empty, the W IS missing. This locks the discrimination between "schema absent" (skip) and "schema present but W missing" (FAIL).
- A third unit case: full state-layer revert mock (`ui_after.this_over = [".", "1", "6", ".", "4", "."]` at expected position 5). Should FAIL — Shape B does not regress the C21 capability.

**Gate-7 cross-fixture obligations.**
Mirror WS-H step-5c protocol exactly:
- Re-run the assertion against all on-disk traces in `logs/trace/` (assertion-only, no pipeline execution → zero empirical-budget cost).
- Predict (from §8): 5+ schema-absent traces flip FAIL → 0; ui_after-populated baselines UNCHANGED.
- Land step-2 close-out memo with the cross-fixture run result table; if any ui_after-populated baseline drops, that is a regression (must be diagnosed before merge).

**Empirical-budget cost for step-2.** **0/5.** HA is assertion-side, gate-6 is fixture-mocked, gate-7 is on-disk re-counting. Same shape as WS-H step-5c, same zero-cost gate-7. Budget remains at 2/5 through step-2 close.

---

## §11 Status footer + recommended commit-message format

**WS-I step-1 status.** CLOSED — static-falsification chain converged on HA / Shape B; cohort-closure UNIFIED-4; 4 alternative hypotheses (HB / HC / HD / HE) statically falsified; C21 UI-layer Phase 3 escalation NOT triggered.

**WS-I step-2 status.** READY — patch surface enumerated (§10); gate-7 protocol borrowed from WS-H step-5c; zero empirical-budget cost predicted.

**Sub-findings added.** S23 (trace-schema heterogeneity as assertion-precondition) + S23-corollary (multi-wicket-per-frame undercount, logged only).

**Empirical-budget status.** **2/5** — UNCHANGED across step-1.

**Recommended next step.** WS-I step-2 — land Shape B patch (commit), with gate-6 unit tests and gate-7 on-disk re-count close-out memo. Land in a single commit (patch + tests + memo update) per WS-H step-5c precedent (`1dbba14` shape).

**Recommended commit message (DO NOT auto-commit; user authorizes explicitly):**

```
feat(workstream-i): I1 Shape B — γ-w-symbol trace-schema-precondition skip closes UNIFIED-4 cohort

§7.2 gate-6 closure on validate_ws_h_step7 4-frame cohort (F679/F855/F948/F1017).

Predicate change at trace_session_assertions.py:335 — wicket records whose
F<wicket+1> trace record lacks ui_after entirely (replay/validate_ws_h_*/
validate_shape_*/validate_surface_* schema cohort) now SKIP the W-symbol
check, instead of FAIL'ing on the defensive [] degeneracy. C21 state-layer
revert capability preserved on validate_dckkr_20260521_155356 baseline
(FAIL × 2 Rahul ov 5.0 + Rana ov 8.0 UNCHANGED).

S23 sub-finding: trace-schema heterogeneity as assertion-precondition (paired
with S21 from WS-H step-5b to form the assertion-vs-pipeline disambiguation
two-shape family — Shape A canonical-resolution + Shape B schema-precondition).

Gate-7 cross-fixture closure: on-disk re-count protocol per WS-H step-5c
(assertion-only, zero empirical-budget cost). Replay/validate_ws_h cohort
flips FAIL × N → 0; ui_after-populated baselines UNCHANGED.

Empirical-budget status: 2/5 → 2/5 (UNCHANGED).
```
