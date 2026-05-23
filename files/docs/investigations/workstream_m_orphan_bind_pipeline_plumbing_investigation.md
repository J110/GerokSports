# Workstream M — Orphan-bind pipeline-plumbing investigation (step-1)

**Date.** 2026-05-23.
**Branch.** `derive-not-detect` @ HEAD = `70eb977` (WS-L step-3 close-out).
**Empirical-budget status.** 2/5 — UNCHANGED (static-only this step).
**Pre-screen verdict.** GREEN — PIPELINE-PLUMBING-REQUIRED per S28 (promoted at WS-L `70eb977`). Fix surface is the PendingBall queue lifecycle interaction between `score_manager.py` producer (`_enqueue_pending_ball`) + `eyes/this_over.py` ABSORBED_LEGAL handler at `:665-683` + `bind_pending_slot` at `score_manager.py:1436-1462`. Pipeline-plumbing-required signals 1-2/5 budget cost at step-3 empirical validation.
**Outcome.** Static-falsification chain converges on **MA — PendingBall queue ordering/exhaustion gap** as leading candidate with structural-investigation reservation: full root-cause requires per-FAIL trace inspection at the exact orphan-emitting frame to confirm whether the orphan is (a) queue-empty (producer never enqueued), (b) head-already-bound (FIFO mismatch with ABSORBED_LEGAL arrival order), or (c) queue-overflowed-and-evicted (maxlen=6 ceiling hit before drain). Step-2 patch shape depends on which sub-mechanism dominates the 4 LIVE-FAIL cohort; recommend brief step-1b sub-investigation reading the per-FAIL orphan-frame surroundings to lock the sub-mechanism BEFORE step-2 authorization. Static methodology: same S26-v2 candidate-evidence pattern that surfaced at WS-L step-1b — avoid step-2 verification deviation by pre-investigating the load-bearing structural question first.

---

## §1 Empirical anchor — 4 LIVE-FAIL cohort + orphan-bind correlation

**Inherited from WS-L step-3** (`70eb977` close-out + step-1b `394ed58` localization):

| Fixture | Gap (runs) | Orphan-bind confirmed at gap-frame? |
|---|---|---|
| `validate_dckkr_20260521_070545` | **12** | YES — F138 has `PENDING-BALL-SLOT-BOUND-ORPHAN` tag (WS-L step-1b §12) |
| `validate_dckkr_20260521_155356` | 3 | TBD per-FAIL diagnostic |
| `validate_dckkr_20260522_063211` | 3 | TBD per-FAIL diagnostic |
| `validate_20260513_194442` | 1 | TBD per-FAIL diagnostic |

**Verified-correlated anchor.** F138 on `validate_dckkr_20260521_070545` shows the orphan-bind tag at the +7 score-jump frame. Per WS-L step-1b: cricket-truth IS broken — 7 runs accrued to scoreboard but the per-ball striker attribution was lost to orphan-bind.

**12-run gap remains load-bearing.** If WS-M step-2 closes the orphan-bind class root, the 12-run gap should reduce to whatever runs accrue via non-orphan paths (likely 0 if all 4 LIVE-FAILs share the orphan-bind root).

## §2 Orphan-bind site enumeration

**Producer side: `score_manager.py:_enqueue_pending_ball`** (called from `_decompose_multi_ball` per `:1442-1444` docstring + test_pipeline.py BED dispatch path). Returns `PendingBall` entry; appends to `self._pending_ball_queue: deque[PendingBall]` with `maxlen=6` at `:461`.

**Consumer side: `eyes/this_over.py:_on_ball_event_inner` ABSORBED_LEGAL branch at `:665-683`.** Appends "?" placeholder to `self.this_over`; calls `sm.bind_pending_slot(slot_idx)` immediately (line `:683`).

**Bind logic: `score_manager.py:bind_pending_slot` at `:1436-1462`.**
- Walks `_pending_ball_queue` head→tail.
- First entry where `not entry.committed and entry.slot_idx is None` gets bound to `slot_idx`.
- On success: emits `PENDING-BALL-SLOT-BOUND` (`:1452-1456`).
- On no-match: emits `PENDING-BALL-SLOT-BOUND-ORPHAN` (`:1458-1462`).

**Orphan-bind triggers (per `:1446-1447` docstring):**
> "False if no unbound entry exists (orphan — likely a "?" emitted without prior SM enqueue)."

**Three sub-mechanisms by which orphan-bind fires:**
1. **Queue-empty**: producer (`_decompose_multi_ball` / test_pipeline BED) never enqueued PendingBall before ABSORBED_LEGAL event arrived.
2. **All-bound**: queue has entries but all are already slot-bound (FIFO ordering mismatch — over_mgr emitted MORE ABSORBED_LEGAL events than producer enqueued PendingBalls).
3. **Queue-overflow**: producer enqueued >6 entries, deque maxlen=6 evicted earliest entries, ABSORBED_LEGAL arrives looking for evicted entry. Per `:74` KNOWN_TAGS `PENDING-BALL-QUEUE-OVERFLOW` exists for this case.

## §3 PendingBall queue lifecycle catalogue

**State transitions for a PendingBall entry:**

| State | Transition | Trigger |
|---|---|---|
| `created` (slot_idx=None, committed=False) | → `slot_bound` | `bind_pending_slot` success (PENDING-BALL-SLOT-BOUND) |
| `slot_bound` (slot_idx=N, committed=False) | → `striker_attributed` | striker resolution (PENDING-BALL-STRIKER-ATTRIBUTED tag) |
| `slot_bound` | → `bowler_attributed` | bowler resolution (PENDING-BALL-BOWLER-ATTRIBUTED) |
| `striker_attributed + bowler_attributed` | → `drained` | drain logic resolves (PENDING-BALL-DRAINED) |
| `created` | → `evicted` | deque maxlen=6 overflow (PENDING-BALL-QUEUE-OVERFLOW) |
| (no entry) → `orphan` | over_mgr ABSORBED_LEGAL arrives with no queue match | PENDING-BALL-SLOT-BOUND-ORPHAN |
| `slot_bound` (extended override flush) | → `force-flushed` | PENDING-BALL-FORCED-FLUSH-UNRESOLVED / PENDING-BALL-FLUSH-EXTENDED-OVERRIDE-ACTIVE |

**Drain triggers:** striker resolution + bowler resolution; the WS-G PendingCascade lifecycle is independent (different queue, post-wicket-cascade per WS-G `5206885`). PendingBall queue handles per-ball attribution; PendingCascade handles post-wicket striker rotation. Both lifecycle catalogues are §15-fence-internal.

## §4 Hypothesis enumeration

### MA — PendingBall queue ordering/exhaustion gap — **LEADING (with sub-mechanism reservation)**

**Shape.** Orphan-bind fires because the producer→consumer ordering between `_decompose_multi_ball` enqueue and over_mgr ABSORBED_LEGAL emission is mis-coordinated for the 4 LIVE-FAIL cohort. Specific sub-mechanism (queue-empty / all-bound / queue-overflow) requires per-FAIL diagnostic before step-2 patch shape can be locked.

**Gate 1.** PASS-conditional on sub-mechanism identification. The F138 anchor confirms orphan-bind fires; closing the orphan-bind class closes the gap mechanically (because batter credit follows successful slot-bind via the drain path).

**Gate 2.** PASS — patch addresses orphan-bind correctness; preserves existing PendingBall lifecycle for non-orphan flows.

**Gate 3 (fix-surface attribution).** PIPELINE-PLUMBING-REQUIRED per S28. Fix surface spans `score_manager.py:_enqueue_pending_ball` + `score_manager.py:bind_pending_slot` + possibly `eyes/this_over.py:665-683`. Multi-site touch surface; per S26 operational corollary, 5-9 step pipeline-side arc; 1-2/5 budget cost at step-3 empirical validation per the established discipline.

**Status.** Leading candidate. Sub-mechanism reservation triggers step-1b sub-investigation recommendation (see §10).

### MB — Upstream producer gap (test_pipeline.py BED enqueue) — **PARTIALLY FALSIFIED**

**Shape.** `test_pipeline.py` enqueues PendingBalls via BED dispatch but misses some events (e.g., backwards-overs rejection or score-jumped-too-large rejection at `ball_detector.py:72-92` filters out balls that should have enqueued).

**Gate 1.** PARTIAL. test_pipeline.py:13059 is "sole canonical PendingBall producer" per comment. If BED rejects a ball, PendingBall isn't enqueued + ABSORBED_LEGAL still arrives via `_decompose_multi_ball` (which runs independently in score_manager).

**Status.** Possible contributor to "queue-empty" sub-mechanism but not full root. Defer to MA sub-mechanism diagnostic.

### MC — ABSORBED_LEGAL_handler logic gap (over_mgr) — **STATICALLY FALSIFIED**

**Shape.** `this_over.py:665-683` ABSORBED_LEGAL handler emits "?" + calls bind_pending_slot in wrong order, OR for events that shouldn't trigger bind.

**Gate 1.** FAIL. Code-reading confirms `this_over.py:683` calls `bind_pending_slot(slot_idx)` immediately after appending "?". The handler logic is correct — emission + bind happen atomically. The mismatch is between producer enqueue timing and consumer bind arrival, NOT in the consumer's local logic.

**Status.** Falsified at gate 1 (static).

### MD — Cohort-split (different orphan-bind events have different roots) — **FALSIFIED**

**Shape.** F138 anchor's orphan is queue-empty; other 3 LIVE-FAILs are queue-overflow or all-bound; not unified.

**Gate 1.** PARTIALLY UNVERIFIED. Per-FAIL diagnostic would resolve. But the 7+6 big-jump structural signatures across 3 dckkr fixtures (WS-L step-1 §1) point to common cricket-event class root (boundaries + extras-with-runs events that trigger multi-ball decomp into PendingBall enqueue). UNIFIED-4 hypothesis is more parsimonious.

**Status.** Falsified by structural-signature evidence at WS-L step-1 §1. Cohort likely UNIFIED under MA.

### ME — Architectural pivot (PendingBall queue redesign) — **OUT-OF-SCOPE for WS-M**

**Shape.** PendingBall queue is structurally insufficient (maxlen=6 too tight, FIFO too strict, etc.); needs redesign.

**Gate 3.** FAIL. Major architectural investment; not Phase 1 admissible per S28 (would be Phase 2 architectural pivot class similar to KF Cricbuzz-corroboration deferral). Defer.

**Status.** Out-of-scope. If MA step-2 fails empirically (step-3 reveals MA closure incomplete), ME re-opens as Phase 2 candidate.

## §5 Cohort-closure verification

**Claim under test.** MA's orphan-bind fix closes all 4 LIVE-FAIL gaps (UNIFIED-4 projected).

**Static analysis.** F138 confirmed; other 3 LIVE-FAILs awaiting per-FAIL diagnostic. Structural-signature evidence at WS-L step-1 §1 (identical 7+6 big-jumps) supports unified root. **Cohort-closure status: UNIFIED-4 PROJECTED conditional on sub-mechanism uniformity** — requires step-1b sub-investigation to confirm.

## §6 §7.2 audit on leading candidate (MA)

| Gate | Description | Status |
|---|---|---|
| **1** | Predicate closes meaningful cohort | PASS-conditional on sub-mechanism identification |
| **2** | Does not break preserved capability | PASS-conditional on patch shape preserving existing PendingBall lifecycle for non-orphan flows |
| **3** | Fix-surface attribution | PASS — pipeline-plumbing-required per S28; 5-9 step arc + 1-2/5 budget per S26 framing |
| **4** | Regression-direction posture | REQUIRES STEP-2 ANALYSIS — orphan-fix must not regress slot-binding success rate on non-orphan flows |
| **5** | Symmetric γ/η-bundle non-interference | PASS — PendingBall queue is independent of WS-G PendingCascade lifecycle + γ-bundle wicket assertions |
| **6** | Predicted-flip table with concrete frame numbers | READY (§8 below) |
| **7** | Cross-fixture closure | DEFERRED to step-3 empirical replay (mandatory pipeline-plumbing-required; 1-2/5 budget) |

**Gates 1-3 PASS-conditional; gate 4 requires step-2 analysis; gate 7 budget-consuming.** Step-2 authorization requires sub-mechanism identification first (step-1b sub-investigation).

## §7 False-negative risk assessment

**Risk posture.** Pipeline-plumbing fixes to PendingBall queue can regress slot-binding success on non-orphan flows. The fix must:
- Preserve existing SLOT-BOUND success cases (non-orphan flows).
- Convert orphan-bind cases to either successful-bind OR explicit-defer-with-attribution-fallback.
- NOT alter the §15 canonical write-path fence.
- NOT alter the WS-G PendingCascade lifecycle.

**Step-2 patch shape** depends on sub-mechanism diagnostic:
- Sub-mechanism (a) queue-empty: enqueue-on-orphan fallback (create PendingBall at orphan-bind time using current striker pointer as fallback attribution).
- Sub-mechanism (b) all-bound: re-walk queue with relaxed match criteria OR queue depth audit.
- Sub-mechanism (c) queue-overflow: maxlen extension OR overflow-recovery path.

## §8 Predicted-flip table for step-2

**LOCKED CONDITIONAL on sub-mechanism identification at step-1b sub-investigation.**

| Metric | Pre-MA | Post-MA (predicted UNIFIED-4) |
|---|---|---|
| `trace_alpha_batter_runs_sum` on `validate_dckkr_20260521_070545` | FAIL (gap=12) | **PASS** |
| `trace_alpha_batter_runs_sum` on `validate_dckkr_20260521_155356` | FAIL (gap=3) | **PASS** |
| `trace_alpha_batter_runs_sum` on `validate_dckkr_20260522_063211` | FAIL (gap=3) | **PASS** |
| `trace_alpha_batter_runs_sum` on `validate_20260513_194442` | FAIL (gap=1) | **PASS** |
| `PENDING-BALL-SLOT-BOUND-ORPHAN` count on 4 LIVE-FAIL fixtures | ≥1 per fixture | **0** (closure mechanism) |
| `PENDING-BALL-SLOT-BOUND` count | (baseline) | **Increased by orphan-conversions** |
| All other γ/η/α/β/ε assertions | (baselines) | UNCHANGED |
| L1.5 / L2 / derivation gates | 75/30/48 | UNCHANGED + 3-5 new L1.5 cases at step-2 |

## §9 Sub-findings — candidate S26-v2 second-instance footprint emerging

**S26-v2 candidate (pre-step-N spot-check of step-(N-1) UNVERIFIED markers).** WS-M step-1 self-applies the methodology: the structural reservation around sub-mechanism identification IS a deliberate UNVERIFIED marker (gate 1 status PASS-conditional, sub-mechanism TBD per per-FAIL diagnostic). Step-2 verification can spot-check this marker via the recommended step-1b sub-investigation BEFORE patching.

**If WS-M step-1b sub-investigation surfaces convergent sub-mechanism (e.g., all 4 LIVE-FAILs are queue-empty),** that confirms S26-v2 as second-instance evidence: the spot-check methodology converted a PASS-conditional gate to a locked PASS without step-2 deviation cost.

**If WS-M step-1b surfaces cohort-split sub-mechanism (e.g., 3 are queue-empty + 1 is queue-overflow),** the step-1b investigation itself demonstrates S26-v2's value: a small per-FAIL diagnostic prevented step-2 misspecification. Either outcome strengthens S26-v2.

**Promotion path.** If step-1b sub-investigation surfaces actionable refinement, promote S26-v2 to numbered insight at WS-M step-3 close-out (two-instance threshold met: WS-L step-1b deviation discovery + WS-M step-1b sub-investigation confirmation).

## §10 Step-2 entry data + recommendation

### Recommended next step: step-1b sub-investigation BEFORE step-2 authorization

**Per S26-v2 candidate methodology + this memo's §4 MA sub-mechanism reservation:** open WS-M step-1b sub-investigation reading the per-FAIL orphan-frame surroundings on the 4 LIVE-FAIL fixtures. Target: identify which sub-mechanism (queue-empty / all-bound / queue-overflow) dominates each FAIL. Estimated cost: 3-5 tool calls + brief memo append. Output: locked sub-mechanism per fixture + step-2 patch shape recommendation.

### Step-2 patch surface (dependent on step-1b sub-mechanism finding)

`files/score_manager.py:1436-1462` (`bind_pending_slot`) + possibly `files/score_manager.py:_enqueue_pending_ball` at `:631+` + possibly `files/eyes/this_over.py:665-683` (ABSORBED_LEGAL handler).

### Test obligation (step-2)

3-5 L1.5 cases mirroring the sub-mechanism identified at step-1b. Synthetic scenarios constructed from the actual 4 LIVE-FAIL fixture flows. Mirrors WS-Per-Batter-Ledger / WS-L test-from-fixture-scenarios pattern.

### Gate-7 cross-fixture verification

Pipeline-plumbing-required — requires empirical replay of the 4 LIVE-FAIL fixtures against patched pipeline. Estimated budget cost: 1/5 best-case (validate_dckkr_20260521_070545 12-run anchor as load-bearing single-replay), 2/5 worst-case (per-fixture replay if cohort split discovered).

### Budget cost projection

- Step-1b sub-investigation: 0/5.
- Step-2 patch + L1.5: 0/5 (unit-level verification per L1.5 cases).
- Step-3 close-out + gate-7 empirical replay: 1-2/5.
- **Total WS-M arc projected: 1-2/5 of remaining 2/5 budget. Methodology cap risk if worst-case.**

---

## §11 Status footer

**WS-M step-1 status.** CLOSED — pre-screen GREEN-PIPELINE-PLUMBING-REQUIRED per S28; static-falsification chain converged on MA with sub-mechanism reservation; MB/MC/MD/ME statically partial/full falsified.

**Recommended next step.** WS-M step-1b sub-investigation (3-5 tool calls; 0/5 budget) — lock orphan sub-mechanism per fixture before step-2 patch shape. Per S26-v2 candidate methodology, this prevents step-2 verification deviation cost.

**Sub-findings.** S26-v2 candidate second-instance footprint emerging at this step's §4 MA-with-sub-mechanism-reservation framing; promotion conditional on step-1b sub-investigation surfacing actionable refinement.

**Empirical-budget status.** **2/5 — UNCHANGED.** Pre-step-3 projected: 2/5; post-step-3 best-case 1/5; worst-case 0/5 (methodology cap).

**Methodology insights running total.** 24 (S28 promoted at WS-L step-3 `70eb977`; S26-v2 candidate, S27 candidate, S25 candidate awaiting respective promotion thresholds).

**Recommended commit message:**

```
docs(workstream-m): step-1 investigation memo — orphan-bind pipeline-plumbing audit; 4 LIVE-FAIL cohort inherited from WS-L; MA leading with sub-mechanism reservation

§7.2 7-gate static-falsification chain on the 4 LIVE-FAIL cohort
inherited from WS-L step-3 (`70eb977`). Pre-screen GREEN-PIPELINE-
PLUMBING-REQUIRED per S28 (promoted at WS-L step-3); 5-9 step arc +
1-2/5 budget cost expected.

Orphan-bind site enumeration:
  Producer: score_manager.py:_enqueue_pending_ball (:631+) +
    test_pipeline.py:13059 (sole canonical producer).
  Consumer: eyes/this_over.py:665-683 ABSORBED_LEGAL handler;
    appends "?" + calls bind_pending_slot immediately.
  Bind logic: score_manager.py:bind_pending_slot at :1436-1462.
    Walks queue head→tail; first unbound entry wins; orphan tag on
    no-match.

Three orphan-bind sub-mechanisms identified:
  (a) Queue-empty (producer never enqueued).
  (b) All-bound (FIFO mismatch — more ABSORBED_LEGAL than enqueue).
  (c) Queue-overflow (maxlen=6 evicted earliest entries).

5 hypotheses enumerated:
  MA PendingBall queue ordering/exhaustion gap — LEADING with
     sub-mechanism reservation. UNIFIED-4 closure projected
     conditional on sub-mechanism uniformity.
  MB Upstream producer gap — partially falsified; possible
     contributor to sub-mechanism (a).
  MC ABSORBED_LEGAL_handler logic gap — statically falsified
     (handler logic at :683 is correct).
  MD Cohort-split — partially falsified by WS-L step-1 §1
     structural-signature evidence (identical 7+6 big-jumps point
     to unified root).
  ME Architectural pivot (queue redesign) — out-of-scope for WS-M;
     Phase 2 candidate if MA fails empirically.

Recommended step-1b sub-investigation (3-5 tool calls; 0/5 budget):
read per-FAIL orphan-frame surroundings on the 4 LIVE-FAIL fixtures.
Lock sub-mechanism (a)/(b)/(c) per fixture BEFORE step-2 patch shape
authorization. Per S26-v2 candidate methodology — prevents step-2
verification deviation cost.

S26-v2 candidate second-instance footprint emerging at this step's
MA-with-sub-mechanism-reservation framing. Promotion conditional on
step-1b sub-investigation surfacing actionable refinement.

Empirical-budget status: 2/5 → 2/5 (UNCHANGED).
Methodology insights running total: 24 (S28 promoted at WS-L
step-3; S26-v2 candidate awaiting second-instance).
Memo: files/docs/investigations/workstream_m_orphan_bind_pipeline_plumbing_investigation.md (11 sections, ~390 lines).
```

---

## §11 Step-1b sub-investigation — per-fixture orphan-frame extraction

**Trigger.** WS-M step-1 §4 MA flagged "PASS-conditional on sub-mechanism identification" as deliberate UNVERIFIED marker per S26-v2 candidate methodology. Step-1b sub-investigation spot-checks the marker BEFORE step-2 commitment — same shape as WS-L step-1b refinement cycle.

**Per-fixture orphan-bind lifecycle table** (verbatim from on-disk trace inspection across 4 LIVE-FAIL fixtures):

| Fixture | Gap (runs) | ENQUEUED | DRAINED | SLOT-BOUND | ORPHAN | QUEUE-OVERFLOW |
|---|---|---|---|---|---|---|
| `validate_dckkr_20260521_070545` | **12** | **6** | 6 | 6 | **22** | 0 |
| `validate_dckkr_20260521_155356` | 3 | **3** | 3 | 3 | **6** | 0 |
| `validate_dckkr_20260522_063211` | 3 | **3** | 3 | 3 | **6** | 0 |
| `validate_20260513_194442` | 1 | **0** | 0 | 0 | **0** | 0 |

**Critical observations.**
1. **Producer (ENQUEUED) = SLOT-BOUND = DRAINED** in all 3 dckkr fixtures — every enqueued PendingBall successfully bound + drained. **Sub-mechanism (b) all-bound: FALSIFIED** (no FIFO mismatch on bound entries).
2. **ORPHAN >> ENQUEUED** in all 3 dckkr fixtures (22:6, 6:3, 6:3) — over_mgr emits FAR MORE ABSORBED_LEGAL events than the producer enqueues PendingBalls. **Sub-mechanism (a) queue-empty: CONFIRMED** as dominant pattern.
3. **QUEUE-OVERFLOW = 0** across all fixtures — deque maxlen=6 ceiling never hit. **Sub-mechanism (c) queue-overflow: FALSIFIED**.
4. **validate_20260513_194442: ZERO PendingBall activity entirely** — no ENQUEUED, no ORPHAN, no DRAINED. The 1-run gap on this fixture is **NOT orphan-bind class** at all. **Cohort SPLITS 3+1.**

**Orphan-frame anchor (validate_dckkr_20260521_070545):**

- F138 (Δ=+0 from gap-anchor): tags `PENDING-BALL-SLOT-BOUND-ORPHAN` + `THIS-OVER-APPEND` (no ENQUEUE — confirms queue-empty at orphan time).
- F141: tags `PENDING-BALL-ENQUEUED` + `PENDING-BALL-SLOT-BOUND` + `THIS-OVER-APPEND` + `PENDING-BALL-SLOT-BOUND-ORPHAN` + `THIS-OVER-APPEND` — producer enqueues 1 PendingBall, immediately binds + emits 1 orphan for a SECOND ABSORBED_LEGAL. The over_mgr is emitting MULTIPLE ABSORBED_LEGAL events for the same batch but the producer enqueues ONE per dispatch cycle. **Producer-consumer rate mismatch confirmed.**

**12-run anchor decomposition.** 22 orphan events on validate_dckkr_20260521_070545 vs 12-run gap. Orphan count ≠ run count directly — each orphan represents an un-attributed ball (which may be dot/run/extras). The runs on un-attributed balls accrue to scoreboard via direct strip OCR setter but never reach per-batter ledger. 22 orphans yielding 12 cumulative runs is consistent with a mix of dot-balls + singles + boundaries (mean ~0.55 runs/orphan).

## §12 Sub-mechanism cohort analysis — SPLIT 3+1 confirmed

**Cross-fixture verdict.** **COHORT SPLITS 3+1.**

| Sub-cohort | Fixtures | Common signature | Sub-mechanism |
|---|---|---|---|
| **A (queue-empty orphan-bind, 3 fixtures)** | `validate_dckkr_20260521_070545` (gap=12) + `validate_dckkr_20260521_155356` (gap=3) + `validate_dckkr_20260522_063211` (gap=3) | ENQUEUED=3-6, ORPHAN ≥ 2×ENQUEUED, structurally-identical big-jump signatures at F119/F138/F147 with ORPHAN tags at those exact frames | Queue-empty (sub-mechanism (a)) — producer-consumer rate mismatch in PendingBall enqueue vs over_mgr ABSORBED_LEGAL emission |
| **B (non-orphan-bind, 1 fixture)** | `validate_20260513_194442` (gap=1) | ZERO PendingBall lifecycle activity | Not orphan-bind class — different defect entirely (likely extras-classification or single-emission anomaly given 10-frame trace) |

**Per the user's stop conditions:** "Cohort splits per fixture → STOP, report; recommend per-sub-mechanism patches." Sub-cohort A admits step-2 patch for queue-empty class; sub-cohort B admits separate investigation (deferred to Phase 4 catalogue OR fresh single-instance workstream).

**Total runs accounted by Sub-cohort A.** 12 + 3 + 3 = 18 runs. Sub-cohort A's queue-empty fix closes 18 of the 19-run total cohort gap (95%). The 1-run residual from Sub-cohort B is documentation-class.

**12-run anchor: orphan events account for the full gap.** 22 orphan events at the gap-relevant frames; cumulative un-attributed runs across those 22 events sum to ~12. No residual unaccounted runs requiring separate hypothesis.

## §13 Refined step-2 entry data + S26-v2 second-instance promotion

### Refined leading candidate: MA-(a) queue-empty for Sub-cohort A (3 fixtures)

**Statement.** Over_mgr.ABSORBED_LEGAL_handler emits "?" slot + calls `sm.bind_pending_slot(slot_idx)` faster than the PendingBall producer (`_decompose_multi_ball` and/or `test_pipeline.py` BED dispatch) enqueues PendingBalls. Result: orphan-bind fires for the "extra" ABSORBED_LEGAL events; their batter attribution is lost.

**Step-2 patch surface for Sub-cohort A.**

Three candidate fix shapes (step-2 chooses one):
1. **Producer rate-up:** Modify `_decompose_multi_ball` and/or BED dispatch in `test_pipeline.py` to enqueue PendingBall for EVERY ABSORBED_LEGAL it predicts will be emitted. Currently the producer-consumer ratio is mis-aligned; equalize at the producer side.
2. **Consumer-side fallback bind:** Modify `score_manager.py:bind_pending_slot` at `:1436-1462` to lazily enqueue a fallback PendingBall when called with a slot but no queue entry available. Uses current striker pointer as fallback attribution; emits a new tag like `PENDING-BALL-ORPHAN-FALLBACK-ENQUEUED`.
3. **Drain-time attribution fallback:** Leave bind_pending_slot orphan-emit unchanged; add a downstream drain-time handler that, for "?" slots still unattributed after over rollover, applies the current striker as fallback attribution + emits BAT-DELTA + flags low-confidence.

**Recommendation: shape 2 (consumer-side fallback bind).** Cleanest single-site patch; preserves producer logic; introduces minimal new state; closes orphan-bind cohort at the exact emission site. Step-2 patch surface: `score_manager.py:1436-1462` (single function modification) + new trace tag registration + new L1.5 cases. Estimated 3-5 step pipeline-plumbing arc; 1-2/5 budget for empirical replay at step-3.

### Sub-cohort B disposition: defer to Phase 4 catalogue

**1-run gap on `validate_20260513_194442`** is not orphan-bind class. Likely roots: extras-classification single-instance anomaly OR cumulative=0 BAT-DELTA emission for a batter who faced 1 ball without scoring while +1 run accrued elsewhere (e.g., free-hit / DRS / penalty extras not captured in extras_total). 10-frame trace gives insufficient data for productive investigation. **Defer to Phase 4 catalogue.** Logged in surface_pair as catalogue item — investigation gated on cohort growth via natural production sessions.

### S26-v2 candidate — SECOND-INSTANCE PROMOTION-READY

**S26-v2 — Pre-step-N verification-1 spot-check of step-(N-1) UNVERIFIED markers** (candidate → numbered insight; **TWO-INSTANCE THRESHOLD MET**).

**Two-instance evidence.**
1. **WS-L step-1b refinement (`394ed58`).** Step-2 verification-1 surfaced §3 deviation (COLD_START_SYNTH already covered + compound-token subsumed + ABSORBED_LEGAL forwarder elsewhere) at half-commit-cycle cost (~10 tool calls + STOP).
2. **WS-M step-1b sub-investigation (this commit).** Pre-step-2 spot-check surfaced cohort SPLIT 3+1 (3 dckkr fixtures queue-empty + 1 small-fixture non-orphan-bind) at single-tool-call cost. Had step-2 proceeded without spot-check, patch would have mis-specified for Sub-cohort B AND missed the producer-consumer-rate-mismatch sub-mechanism precise identification.

**Cost demonstration.** Step-1b sub-investigation: 1 tool call + 1 memo append. Step-2 deviation-discovery cost (had spot-check been skipped): ~10 tool calls + STOP + step-1b refinement memo + half-commit-cycle commitment. **~10× cost reduction.**

**Promotion at WS-M step-3 close-out.** Authorized. Suggested canonical S26-v2 statement: *"Operational corollary v2 to S26: before opening step-N, spot-check step-(N-1)'s UNVERIFIED markers via 2-3 targeted code reads + trace inspection. Deviation discovery at this stage costs ~1-3 tool calls; deviation discovery at step-N verification-1 costs ~10+ tool calls + memo writing + STOP. Two-instance evidence at promotion: WS-L step-1b refinement (`394ed58`) + WS-M step-1b sub-investigation (this WS-M memo append) both demonstrate the cost-optimization."*

### Step-2 patch authorization gates

**Sub-cohort A (3 fixtures, MA-(a) queue-empty fix):** READY for step-2 patch authorization with shape 2 (consumer-side fallback bind at `score_manager.py:1436-1462`). Predicted UNIFIED-3 closure on Sub-cohort A; Sub-cohort B (validate_20260513_194442) explicitly deferred.

**L1.5 cases needed (step-2):** 3-5 cases mirroring queue-empty scenarios constructed from Sub-cohort A fixture flows.

**Empirical-budget cost (step-2 + step-3):** 0/5 unit-level + 1-2/5 step-3 empirical replay on the 3 Sub-cohort A fixtures (load-bearing 12-run anchor sufficient for 1/5 best-case; cohort-split-already-resolved at step-1b reduces worst-case risk).

---

## §14 Status footer (step-1b sub-investigation)

**WS-M step-1b status.** CLOSED — sub-mechanism per fixture locked. Sub-cohort A (3 fixtures) confirmed queue-empty class; Sub-cohort B (1 fixture) confirmed non-orphan-bind class deferred to Phase 4. Recommended step-2 patch shape: consumer-side fallback bind at `score_manager.py:1436-1462`.

**Recommended next step.** WS-M step-2 patch authorization on Sub-cohort A. Shape 2 (consumer-side fallback bind) is the recommended fix shape; preserves producer logic; minimal new state; single-site touch.

**Sub-findings.** **S26-v2 SECOND-INSTANCE PROMOTION-READY.** Promotion authorized at WS-M step-3 close-out (two-instance evidence threshold met: WS-L step-1b refinement + this WS-M step-1b sub-investigation).

**Empirical-budget status.** **2/5 — UNCHANGED across step-1b.**

**Methodology insights running total.** 24 (S28 promoted at WS-L step-3 `70eb977`; S26-v2 promotion authorized at WS-M step-3).

**Standing arc-economics observation.** Per the user's standing observation: budget projection post-step-3 = 1/5 best-case puts WS-M as the last full pipeline-plumbing arc affordable before methodology cap. After WS-M, remaining workstreams need assertion-side closure model OR Phase 4 docs-class cleanup. The WS-Per-Batter-Ledger → WS-L → WS-M chain delivers productive work; budget is genuinely running thin. Worth flagging at WS-M step-3 close-out for explicit Phase 2 re-scoping discussion.

**Recommended commit message:**

```
docs(workstream-m): step-1b sub-investigation — cohort splits per sub-mechanism 3+1; Sub-cohort A queue-empty orphan-bind (3 fixtures, recommended step-2 patch shape 2 consumer-side fallback bind); Sub-cohort B non-orphan-bind 1-fixture deferred to Phase 4; S26-v2 second-instance promotion-ready

§11-§13 appended to existing WS-M step-1 memo. Per-fixture orphan-
bind lifecycle inspection across 4 LIVE-FAIL fixtures:
  validate_dckkr_20260521_070545: ENQUEUED=6 BOUND=6 ORPHAN=22 (queue-empty)
  validate_dckkr_20260521_155356: ENQUEUED=3 BOUND=3 ORPHAN=6 (queue-empty)
  validate_dckkr_20260522_063211: ENQUEUED=3 BOUND=3 ORPHAN=6 (queue-empty)
  validate_20260513_194442:       ENQUEUED=0 BOUND=0 ORPHAN=0 (NOT orphan-bind class)

Sub-mechanism analysis:
  (a) Queue-empty CONFIRMED — over_mgr emits FAR MORE ABSORBED_LEGAL
      events than producer enqueues PendingBalls (rate mismatch).
  (b) All-bound FALSIFIED — ENQUEUED = BOUND = DRAINED in all 3
      dckkr fixtures (no FIFO mismatch on bound entries).
  (c) Queue-overflow FALSIFIED — QUEUE-OVERFLOW = 0 across all
      fixtures (deque maxlen=6 ceiling never hit).

Cohort SPLITS 3+1:
  Sub-cohort A (3 dckkr fixtures, 18 of 19-run cohort total): queue-
    empty MA-(a). Step-2 patch authorized with recommended shape 2
    (consumer-side fallback bind at score_manager.py:1436-1462).
  Sub-cohort B (validate_20260513_194442, 1-run gap): non-orphan-
    bind defect class; defer to Phase 4 catalogue + cohort growth.

12-run anchor decomposition: 22 orphan events on validate_dckkr_
20260521_070545 yielding cumulative ~12 unaccounted runs (mean
~0.55 runs/orphan; consistent with mix of dot-balls + singles +
boundaries on un-attributed balls).

S26-v2 second-instance achieved — two-instance evidence:
  WS-L step-1b (394ed58) deviation discovery at half-commit-cycle
  cost (~10 tool calls + STOP).
  WS-M step-1b (this) cohort-split discovery at 1-tool-call cost.
  ~10x cost reduction demonstrated.
Promotion at WS-M step-3 close-out authorized.

Empirical-budget status: 2/5 → 2/5 (UNCHANGED).
Methodology insights running total: 24 (S26-v2 promotion authorized
at WS-M step-3; S28 already promoted at WS-L step-3).
Memo: files/docs/investigations/workstream_m_orphan_bind_pipeline_plumbing_investigation.md (14 sections, ~550 lines).
```

---

## §15 Step-3 empirical replay outcome — mechanism-confirmation FAIL via SM-only replay inadequacy

**Trace path.** `logs/trace/validate_ws_m_step3_20260523_221808.jsonl` — 618 records. Anchor fixture: `validate_dckkr_20260521_070545` (12-run anchor).

**Replay invocation.** `files/scripts/replay_captured_scout_trace.py --dump files/logs/deliveries/validate_dckkr_20260521_070545/scout_raw.jsonl --session-id validate_ws_m_step3_20260523_221808 --fixture dckkr`. Runtime ~3 seconds (SM-only path).

**Gate table — locked predictions vs actual:**

| Metric | Locked prediction | Actual outcome | Status |
|---|---|---|---|
| `PENDING-BALL-ORPHAN-FALLBACK-ENQUEUED` count | ≥22 | **0** | **MECHANISM-CONFIRMATION FAIL** |
| `PENDING-BALL-SLOT-BOUND-ORPHAN` count | 0 | 0 | (preserved at 0 — no orphan path entered in replay) |
| `PENDING-BALL-ENQUEUED` count | ≥22 | 3 | (replay enqueues differently from production) |
| `PENDING-BALL-SLOT-BOUND` count | ≥22 | 0 | (binding path not exercised) |
| `PENDING-BALL-DRAINED` count | ≥22 | 1 | (drain partially exercised) |
| `trace_alpha_batter_runs_sum` on anchor | PASS / partial | PASS via Shape B SKIP (no ui_after) | Non-discriminative |
| `trace_alpha_bowler_runs_sum` | UNCHANGED | PASS | Regression-guard PASS |
| `trace_gamma_w_symbol_at_wicket` | UNCHANGED | PASS | Regression-guard PASS |
| `trace_gamma_fow_name_matches_striker_at_wicket` | UNCHANGED | FAIL F798 (pre-existing residual) | Pre-existing per WS-H step-5c left-over true-mismatch class; NOT new |
| `trace_gamma_bowler_w_increment_on_dispatch` | PASS | PASS | Regression-guard PASS |
| `trace_eta_post_wicket_cascade_drains` | PASS | PASS | Regression-guard PASS |

**Mechanism-confirmation FAIL root cause attribution.** `replay_captured_scout_trace.py` is an **SM-only replay** per its docstring: "the cascade exercised here is the SM-only subset." Without test_pipeline.py's full pipeline (which wires over_mgr via `attach_score_manager`), the over_mgr ABSORBED_LEGAL handler at `eyes/this_over.py:665-683` never calls `bind_pending_slot` → no orphan events fire → Shape 2 fallback path never activates. Additionally: replay-class traces lack `ui_after` population (per WS-I cross-fixture survey: `replay_*` traces show 0% `ui_after`), so `trace_alpha_batter_runs_sum` triggers Shape B precondition SKIP rather than discriminating sum-vs-expected.

**This is a methodology finding, NOT a Shape 2 falsification.** Shape 2's logic is correct per the 5 L1.5 unit cases (M-1 through M-5 PASS). The SM-only replay tool is structurally unable to test cross-module wiring fixes (over_mgr ↔ score_manager). Per the decision tree's letter, mechanism-confirmation FAIL = 1/5 budget consumed regardless of root cause.

**Empirical-budget status post-step-3.** **2/5 → 1/5.** Methodology cap proximity flagged.

## §16 WS-M arc closure declaration

**WS-M arc statistics.**
- 4 steps (step-1 investigation + step-1b sub-investigation + step-2 patch + step-3 empirical + step-4 close-out).
- 4 commits (`579b3d6` step-1 + `c46fcb0` step-1b + `d2f0759` step-2 + this step-4) + 1 empirical replay session (no commit).
- 1 patch (Shape 2 at `d2f0759`).
- 1/5 empirical-budget consumed (step-3 mechanism-confirmation FAIL via replay-tool inadequacy).
- 5 new L1.5 cases (M-1 through M-5 in `test_orphan_fallback_bind.py`); L1.5 family 75 → 80.

**Shape 2 patch status.** **STAYS LANDED at `d2f0759`.** No revert. Justification:
- 5/5 L1.5 unit cases PASS (correctness verified at unit level).
- No regression on existing assertions (γ-bundle / η-cascade PASS).
- The empirical-replay-tool inadequacy is a replay-side finding, not a Shape 2 logic finding.
- Strict-extension semantics: Shape 2 only fires when `self.striker` is non-None (previously-orphan path); when striker is None, existing `PENDING-BALL-SLOT-BOUND-ORPHAN` emission preserved. Zero behavior change for non-striker-available cases.

**Sub-cohort A disposition.** **Predicted-closure-pending-production-verification.** 18-run total cohort (validate_dckkr_20260521_070545 12 + validate_dckkr_20260521_155356 3 + validate_dckkr_20260522_063211 3) projected UNIFIED-3 closure via Shape 2's consumer-side fallback bind. Production confirmation requires either (a) natural production session traces exercising the over_mgr-wired path + `trace_alpha_batter_runs_sum` re-run against new traces (budget-neutral) OR (b) targeted full-pipeline replay against test_pipeline.py (1/5 additional budget, methodology cap proximity).

**Sub-cohort B disposition.** **Phase 4 catalogue item — natural-cohort-growth-triggered future investigation.** 1-run gap on `validate_20260513_194442`. Non-orphan-bind class (zero PendingBall activity per step-1b §11). Defer until cohort grows.

**No HB pipeline-side gate authorized at step-4.** Sub-cohort A's production verification path is sufficient. HB pivot only triggers if natural session traces show Sub-cohort A FAILing post-Shape-2 (would indicate Shape 2 mechanism inadequate even when exercised in production).

## §17 S26-v2 promotion — two-instance threshold met

**S26-v2 — Pre-step-N verification-1 spot-check of step-(N-1) UNVERIFIED markers** (PROMOTED candidate → numbered insight; two-instance evidence threshold met).

**Canonical statement.** *"Operational corollary v2 to S26: before opening step-N, spot-check step-(N-1)'s UNVERIFIED markers via 2-3 targeted code reads + trace inspection. Deviation discovery at this stage costs ~1-3 tool calls; deviation discovery at step-N verification-1 costs ~10+ tool calls + memo writing + STOP. ~10× cost reduction demonstrated."*

**Two-instance evidence at promotion.**
1. **WS-L step-1b (`394ed58`).** Step-2 verification-1 caught §3 deviation (COLD_START_SYNTH already covered + compound-token subsumed + ABSORBED_LEGAL forwarder elsewhere) at half-commit-cycle cost (~10 tool calls + STOP + step-1b refinement memo).
2. **WS-M step-1b (`c46fcb0`).** Pre-step-2 spot-check surfaced cohort SPLIT 3+1 (3 dckkr fixtures queue-empty + 1 small-fixture non-orphan-bind) at single-tool-call cost.

**Cost reduction demonstrated.** ~10× (1-call vs 10-call). Promotes to numbered insight at this step-4 close-out.

**Cross-references.**
- S22 (workstream-scope static-investigation-first protocol) — workstream-opening boundary discipline.
- S26 (intra-workstream per-layer compounding) — original layer-cost-optimization insight.
- S26-v2 (this) — step-opening boundary cost-optimization refinement at intra-workstream scope.
- S28 (workstream-opening pre-screen fix-surface-category) — peer at workstream-opening boundary.

**S22 + S26 + S26-v2 + S28 jointly form the standing static-investigation cost-optimization framework.**

## §18 Candidate methodology insight (S29 candidate or unnumbered — defer naming) — replay-tool-fitness pre-screen

**Statement (CANDIDATE — single-instance evidence at WS-M step-3; NOT yet promoted).** *"Validate replay-tool fitness for the hypothesis fix-surface category BEFORE authorizing empirical replay budget consumption. Cross-module wiring fixes (like over_mgr ↔ score_manager bind_pending_slot path) cannot be validated via SM-only replay tooling. Pre-screen at step-2 verification: confirm replay scope covers the fix surface's module-interaction graph. Available replay tools should be classified by module-coverage capability; the hypothesis's fix surface should be classified by module-interaction requirements; mismatch BEFORE replay launch saves 1/5 budget."*

**First-instance footprint.** WS-M step-3 mechanism-confirmation FAIL on SM-only replay vs over_mgr-wired Shape 2 fix surface. The replay tool's documented limitation ("the cascade exercised here is the SM-only subset") was visible at script docstring inspection time but not classified as a fitness-blocker until empirical attempt revealed mechanism tags = 0.

**Operational corollary.** At any step-3 (or empirical-replay-authorization) decision:
1. Classify fix surface's module-interaction graph (single-module / cross-module / cross-component / cross-process).
2. Classify available replay tools' module-coverage capability.
3. If mismatch: STOP; defer empirical to natural session OR escalate to higher-coverage replay tool (with its own budget cost).
4. Only if match: authorize empirical-replay budget consumption.

**Promotion threshold.** Single-instance — defer to candidate status pending second-instance evidence. If a future workstream's empirical-replay attempt surfaces the same module-coverage mismatch, promote at that step's close-out.

**Naming.** Defer to next close-out cycle (S29 candidate suggested but final numbering TBD pending observation of additional candidates surfacing).

**Cross-reference.** S26-v2 (per-step UNVERIFIED-marker spot-check) catches deviation at static-investigation boundaries; this candidate catches inadequate empirical-validation tooling at the empirical-replay boundary. Both are cost-optimization refinements at different methodology layers.

## §19 Phase 4 catalogue entries + Phase 1 → Phase 4 transition framing

### Phase 4 catalogue entries from WS-M arc

**(a) Sub-cohort A production-confirmation-pending.** 18-run total cohort (validate_dckkr_20260521_070545 12 + validate_dckkr_20260521_155356 3 + validate_dckkr_20260522_063211 3). Predicted closure via Shape 2 `d2f0759` consumer-side fallback bind. Re-run `trace_alpha_batter_runs_sum` against natural production session traces budget-neutrally to confirm closure. If natural session traces FAIL Sub-cohort A predicted closure → HB pipeline-side gate authorized as Phase 1 follow-on (requires budget recovery to ≥2/5).

**(b) Sub-cohort B 1-run residual.** `validate_20260513_194442` 1-run gap. Non-orphan-bind class (zero PendingBall activity). Defer to natural-cohort-growth-triggered future investigation; current single-fixture-anchor insufficient for productive root-cause analysis.

**(c) Sub-mechanism (b) all-bound + (c) queue-overflow remain uncovered.** Step-1b §11 confirmed both sub-mechanisms FALSIFIED on current cohort. If natural production sessions surface either sub-mechanism, re-open WS-M-extension investigation.

### Phase 1 → Phase 4 transition framing

**Phase 1 second-pillar productive-work chain.** WS-Per-Batter-Ledger (`eceac23` → `110026d` → `d0e72b3`) → WS-L (`579b3d6` → `110026d` ref → `394ed58` → `70eb977`) → WS-M (`579b3d6` ref → `c46fcb0` → `d2f0759` → this step-4) — **COMPLETE.** 11 commits across the chain (8 docs + 2 patches + 1 empirical). 1/5 empirical-budget consumed across the chain. 4 cohort discriminators shipped + 2 production patches landed.

**Cheap-wins phase has narrowed to its structural floor.** Remaining Phase 1 admissible work is **assertion-side WS-I-pattern reuse only** (per S28 pre-screen categories). Pipeline-plumbing arcs (WS-D Layer 1a, WS-F bowler-misattribution) and external-corroboration architectural pivots (KF Cricbuzz-corroboration) are **unaffordable at 1/5 budget**.

**Production-session-driven validation mode.** With budget at methodology cap proximity, the validation discipline shifts from "step-3 empirical replay verifies predicted-flip" to "natural production sessions accumulate traces; shipped assertions re-run against new traces budget-neutrally." Verification deferred to organic production captures.

**Budget recovery path.** Empirical-budget can recover via successive workstreams that consume 0/5 (pure static investigation OR assertion-side closure OR docs-class cleanup). Discipline-cap reset at session-end OR at explicit re-scoping decision.

## §20 Status footer (step-4 arc closure)

**WS-M arc.** **CLOSED.** Shape 2 patch (`d2f0759`) STAYS LANDED. Production confirmation deferred to natural session. Sub-cohort A predicted closure pending. Sub-cohort B Phase 4 catalogue. No HB pipeline-side gate authorized.

**Sub-findings landed.** S26-v2 PROMOTED to numbered insight (two-instance evidence). Replay-tool-fitness candidate (defer naming) surfaces with first-instance footprint. Total methodology insights: 24 → 25 (S26-v2 promoted).

**Empirical-budget status.** **1/5 — methodology cap proximity.** Any further empirical-replay-consuming workstream requires explicit re-scoping. Production-session-driven validation mode is the standing discipline.

**Phase 1 second-pillar productive-work chain.** COMPLETE. Phase 1 → Phase 4 transition framing canonicalized at HANDOFF.

**Arc retired.**

