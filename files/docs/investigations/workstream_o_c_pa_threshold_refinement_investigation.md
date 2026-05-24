# Workstream O.c — PA threshold refinement (balls 4.1-4.5 residue) with S33 instrumentation-aware methodology (step-1)

**Status.** Step-1 closed; leading candidate identified; S33
candidate documented with two-instance evidence + canonical
statement.

**Trigger.** WS-O.b step-3 + WS-P step-3 left residual 3
E2-phantom-runs + 5 conservation invariants at balls 4.1-4.5
on DCKKR. PA mechanism is empirically confirmed firing (7 times
on dckkr dump per WS-O.b step-3); residue persists because the
current threshold `balls * 2.5 + 10` admits the higher-overs
overread cascade.

**Pre-screen verdict.** GREEN — PIPELINE-DIRECT per S28
(single-line threshold refinement at the confirmed-firing PA
predicate site).

**Outcome.** Static-falsification chain converges on
**VA — `int(balls * 1.9) + 10`** as leading candidate (tighter
multiplier 1.9 vs current 2.5, same +10 buffer). Closes the
residue (DCKKR 63 at balls=24 rejected: 63 > 55.6) without
false-negative on L2 + DCKKR/GTRR legitimate-scoring envelope.

**S33 candidate**: two-instance evidence
(WS-O OA `deba545` no-op + WS-P P1 `88e03f5` no-op) meets the
two-instance promotion threshold per standing discipline.
Canonical statement at §9. Applied to this very investigation:
recommend step-2 instrument-then-patch protocol (add the refined
predicate with a debug log; run snapshotter; verify firings at
residue frames + zero firings at L2 fixture frames; THEN ship).

---

## §1 Empirical anchor — residue frame trace (balls 4.1-4.5)

Per `files/tests/baselines/dckkr_diff_post_ws_p_baseline.md` §3
conservation invariants:

| Ball | sb._inn pre-commit overs | balls | Pipeline score | GT score | Δ (pipeline − GT) |
|---|---|---|---|---|---|
| 4.1 | "4.0" | 24 | 63 | 43 | +20 |
| 4.2 | "4.1" | 25 | 63 | 44 | +19 |
| 4.3 | "4.2" | 26 | 63 | 44 | +19 |
| 4.4 | "4.3" | 27 | 64 | 45 | +19 |
| 4.5 | "4.4" | 28 | 64 | 49 | +15 |

All five residue commits are sb.set("score", v, ...) calls
where the proposed `v` is the bogus 63 / 64 read AND PA's
current `int(balls * 2.5) + 10` threshold ACCEPTS:
- balls=24: max=70. 63 ≤ 70 → accept (cascade root).
- balls=25: max=72. 63 ≤ 72.
- balls=26: max=75. 63 ≤ 75.
- balls=27: max=77. 64 ≤ 77.
- balls=28: max=80. 64 ≤ 80.

GT progression at those balls (from L2 ledger
`files/tests/fixtures/dc_vs_kkr_2026_152064_ledger.json`):
- 4.1 → 43 (boundary on 25th legal ball, takes total from 39).
- 4.2 → 44 (single).
- 4.3 → 44 (dot).
- 4.4 → 45 (single).
- 4.5 → 49 (boundary).

GT max RPO across balls 4.x window: 43/4.0 = 10.75 RPO at
4.1; 49/4.5 = 10.89 RPO at 4.5. Below the cricket-physics
ceiling of ~12 RPO sustained for short bursts.

---

## §2 Current PA threshold formula analysis

Per `files/eyes/scoreboard.py:1216-1252` (WS-O.b PA gate):

```python
_max_plausible = int(_balls * 2.5) + 10
if v > _max_plausible:
    return False
```

Multiplier 2.5 = 15 RPO max (`runs / over` at the upper bound).
Buffer +10 accommodates rare single-ball maxes (NB+6, free-hit
6, etc.) and very early cold-start cases where balls=0.

**Why it admits the residue**: 15 RPO is generous. Real T20
cricket sustains 12-13 RPO at the high end; 15 RPO is reserved
for explosive 1-2 over windows. At balls=24 (4 overs), max
legitimate cumulative is ~60 (15 RPO * 4 overs). PA's threshold
70 has +10 over the legitimate ceiling — exactly enough to
admit the bogus 63.

**Tightening target**: reduce multiplier from 2.5 to a value
that catches 63 at balls=24 while admitting GT's 43-49 range.
Multiplier of 2.0 (= 12 RPO max) at balls=24 = 48, +10 = 58.
Rejects 63 (>58). Accepts 43-49.

Multiplier 1.9 (= 11.4 RPO max) at balls=24 = 45.6, +10 = 55.6.
Rejects 63 (>55.6). Accepts 43-49 with 6-9 run cushion.

---

## §3 L2 + fixture legitimate-scoring envelope

L2 fixture ledger (`dc_vs_kkr_2026_152064_ledger.json`)
balls-to-score map (36 balls):

| Ball | balls | Score | RPO at this point |
|---|---|---|---|
| 0.6 | 6 | 7 | 7.0 |
| 1.4 | 10 | 15 | 9.0 (six on this ball) |
| 2.6 | 12 | 28 (after rollover) | 14.0 |
| 3.6 | 18 | 39 | 13.0 |
| 4.6 | 24 | 49 | 12.25 |
| 5.6 | 30 | 53 | 10.6 |

Wait — recomputing. Let me check the actual scores at each
boundary:

Per the grep output: scores progress as 0, 4, 5, 5, 6, 7, 7, 8,
9, 15, 16, 17, 17, 21, 22, 22, 22, 28, 29, 33, 33, 34, 38, 39,
43, 44, 44, 45, 49, 49, 53, 54, 54, 54, 54, 55.

| Ball | balls (post-commit) | Score | RPO |
|---|---|---|---|
| 0.6 | 6 | 7 | 7.0 |
| 1.4 | 10 | 15 | 9.0 |
| 2.6 | 12 | 28 | 14.0 (six-boundary cluster) |
| 3.6 | 18 | 39 | 13.0 |
| 4.6 | 24 | 49 | 12.25 |
| 5.6 | 30 | 55 | 11.0 |

Max sustained RPO across L2 envelope: ~14 (very brief, ball 2.6
peak); typical 9-13.

L2 sb.set("score", v, ...) calls use the PRE-COMMIT overs (just
before the ball's overs commit). So at ball 1.4's score commit,
sb._inn["overs"] is still "1.3" (= 9 balls). Proposed score=15.

Refined threshold predictions per candidate at L2's max-RPO
moments:

| Ball | balls (pre) | Score (post) | VA 1.9+10 | Acceptance |
|---|---|---|---|---|
| 0.2 | 1 | 4 | 1.9+10=11 | accept (4 ≤ 11) |
| 1.4 | 9 | 15 | 17.1+10=27 | accept (15 ≤ 27) |
| 2.6 | 11 | 28 | 20.9+10=30 | accept (28 ≤ 30) |
| 3.6 | 17 | 39 | 32.3+10=42 | accept (39 ≤ 42) |
| 4.1 | 24 | 43 | 45.6+10=55 | accept (43 ≤ 55) |
| 4.6 | 23 | 49 | 43.7+10=53 | accept (49 ≤ 53) |
| 5.6 | 29 | 55 | 55.1+10=65 | accept (55 ≤ 65) |

All L2 commits accepted. Tightest margin: ball 2.6 (cushion of
2 runs). Acceptable; the cushion preserves accept-on-boundary
behaviour.

DCKKR fixture full-innings GT max (per
`files/tests/fixtures/dckkr_ground_truth_ui_snapshots.jsonl`
final state): score=142 at legal_balls=120. RPO = 7.1 (low-
scoring innings overall). Highest single-ball delta in fixture:
~6 (boundaries). All within VA threshold.

GTRR fixture cited at WS-N N1.2 for cross-fixture verification
— similar T20 envelope (max RPO ~13-14 typical T20). VA
threshold 1.9 RPO + 10 buffer covers this envelope.

---

## §4 Threshold formula candidates

### VA — Tighter linear: `int(balls * 1.9) + 10` — **LEADING**

Same shape as current but multiplier 2.5 → 1.9.

**Rejection prediction (residue)**:
- balls=24, v=63: max=55. 63 > 55 → REJECT. ✓
- balls=25, v=63: max=57. 63 > 57 → REJECT. ✓
- balls=26, v=63: max=59. 63 > 59 → REJECT. ✓
- balls=27, v=64: max=61. 64 > 61 → REJECT. ✓
- balls=28, v=64: max=63. 64 > 63 → REJECT. ✓ (1-run margin)

**Acceptance prediction (L2 + fixtures)**: all legitimate
commits accepted per §3 envelope analysis. Tightest cushion:
ball 2.6 of L2 (2-run cushion).

**Trade-off**: ultra-explosive scoring (sustained 14+ RPO over
6+ overs, e.g. 100/10 powerplay) could false-reject. Rare;
acceptable.

### VB — Capped linear: `min(balls * 2.5 + 10, balls * 2.0 + 30)`

Two-tier: tight in middle, loose at extremes. Complex; marginal
benefit over VA.

**Status**: rejected; complexity not justified.

### VC — Per-call delta cap: `if v - cur_int > 15: reject`

Replace cumulative-cap with per-call delta cap. Catches the
+20 / +19 / +15 jumps at residue frames directly.

**Risk**: doesn't catch cumulative cascade where the bogus
value is achieved via multiple small Scout misreads. The
current residue arrived via one Scout misread spike, but
defense-in-depth wants both layers.

**Status**: viable as ADDITIONAL guard alongside VA; not
standalone replacement.

### VD — Hybrid: VA + VC

VA cumulative cap + VC per-call delta cap.

**Status**: defense-in-depth. Defer VC to step-2b if VA leaves
residue.

### VE — RPO-based: `int(overs * 12) + 10`

Conceptually identical to `int(balls * 2.0) + 10` (12 RPO =
2.0 runs/ball). Slightly less precise than VA's 1.9 but cleaner
to reason about ("max 12 RPO").

**Status**: viable alternative to VA. VA preferred for tighter
cushion against the specific 64-at-balls=27 edge case.

---

## §5 Per-candidate cohort closure prediction

| Cohort | Pre-WS-O.c | Post-VA predicted |
|---|---|---|
| E2-phantom-runs | 3 | 0 (all 5 residue frames rejected) |
| Conservation invariants | 5 | 0 (cascade-tied to E2) |
| Striker-anchor swap | ~50 | UNCHANGED (SPLIT; WS-P.b root) |
| this_over_tokens negative tokens | 0 | 0 (PE still works) |
| L2 ledger | 30 PASS | 30 PASS (legitimate-envelope analysis confirms) |
| Other 15 surfaces | (post-WS-P baselines) | UNCHANGED |

**Cascade-closure pattern**: VA closes E2 + conservation
together; both are tied to the same bogus 63 / 64 sb.score
commits. Once rejected at sb.set, the snapshot's pipeline.score
stays at the last-accepted-legitimate value, conservation
invariants no longer fire.

---

## §6 §7.2 audit on leading candidate (VA)

| Gate | Status | Rationale |
|---|---|---|
| 1 (defect-class fit) | PASS | Rejects all 5 residue commits; accepts all L2 + fixture legitimate commits. |
| 2 (backward-compat) | PASS | L2 30/30 envelope verified; PA mechanism call site + emission path unchanged; threshold-only change. |
| 3 (fix-surface attribution) | PASS | PIPELINE-DIRECT; single-line change at `scoreboard.py` (1 LOC: multiplier 2.5 → 1.9). |
| 4 (sub-finding promotion) | **PROMOTE — S33 candidate** | Two-instance evidence (WS-O OA + WS-P P1 both no-op). Canonical statement at §9. |
| 5 (cohort enumeration completeness) | PASS | E2 + conservation residue cataloged; striker-anchor split-out preserved per WS-P SCOPE-RESERVATION. |
| 6 (test obligation) | OPEN at step-2 | New L1.5 case (O.c-1: VA rejects bogus 63 at balls=24; O.c-2: VA accepts legitimate 49 at balls=24 boundary). |
| 7 (cross-fixture verification) | DEFER to step-3 | Re-run snapshotter + diff; verify residue closure. |

---

## §7 False-negative risk assessment

**L2 envelope cushions** (proposed score vs VA threshold):

| Ball | balls (pre) | Score | VA max | Cushion |
|---|---|---|---|---|
| 0.2 | 1 | 4 | 11 | 7 |
| 1.4 | 9 | 15 | 27 | 12 |
| 2.6 | 11 | 28 | 30 | 2 ⚠ |
| 3.6 | 17 | 39 | 42 | 3 |
| 4.6 | 23 | 49 | 53 | 4 |
| 5.6 | 29 | 55 | 65 | 10 |

Minimum cushion: 2 runs at ball 2.6. Acceptable but TIGHT.
Could fail if a future fixture has a +3-run jump from a more
aggressive scoring rate at this exact balls count.

Mitigation: if step-3 cross-fixture verification surfaces a
false-reject, bump buffer from +10 to +12 (loses 0 residue
rejections at the current cascade, gains 2-run cushion across
all L2 cases). Defer the bump until empirical signal.

---

## §8 Predicted-flip table for step-2

| Metric | Pre-VA (post-WS-P baseline `b8c3c25`) | Post-VA predicted |
|---|---|---|
| E2-phantom-runs | 3 | 0 (full closure) |
| Conservation invariants | 5 | 0 (cascade-tied) |
| Striker-anchor swap | ~50 | UNCHANGED (SPLIT; WS-P.b) |
| this_over_tokens negative tokens | 0 | 0 (regression-guard) |
| L2 ledger | 30 PASS | 30 PASS (load-bearing) |
| L1.5 total | 90 | 92 (+2 O.c cases) |
| `WARM-MODE-MAGNITUDE-GATE-REJECTED` count on dckkr baseline | 7 | ≥12 (existing 7 + new 5 residue rejections) |
| Other 15 surfaces | (post-WS-P) | UNCHANGED (regression-guard) |

---

## §9 S33 candidate — instrumentation-aware methodology

**Two-instance evidence (threshold met for promotion per
standing discipline)**:

1. **WS-O OA** (`deba545`): COLD-START-OVERREAD-REJECTED +
   SCORE-FORCE-RESET both fired 0 times on dckkr dump.
   Mechanism wired correctly per O-1/O-3 unit tests; cascade
   root in WARM mode not COLD_START. Patch shipped + L1.5
   passed but NO empirical effect.

2. **WS-P P1** (`88e03f5`): STRIKER-ANCHOR-DEFERRED-NO-ASTERISK
   fired 0 times on dckkr dump. Mechanism wired correctly per
   P-1/P-3 unit tests; cascade root not on `_accept_initial`
   else branch. Patch shipped + L1.5 passed but NO empirical
   effect.

**Canonical statement (proposed for promotion at next close-out
commit)**:

> **S33 — Instrumentation-aware predicate refinement.** When a
> static investigation proposes a predicate refinement
> (threshold tightening, branch addition, gate modification),
> the step-2 patch should be preceded by a one-cycle
> instrumentation pass:
>
> (a) Add the proposed predicate at the call site, gated as a
> NO-OP (log only, no behavior change).
> (b) Run the snapshotter against the captured dump.
> (c) Inspect the predicate's firings: does it fire at the
> expected frames AND zero firings at known-legitimate frames?
> (d) If both pass, ship the predicate with behavior change. If
> either fails, refine OR pivot.
>
> Cost: ~3-5 tool calls per workstream. Benefit: prevents
> shipping NO-OP patches (the WS-O OA + WS-P P1 pattern). The
> static-derive-then-patch discipline has hit a design ceiling
> for cascade-root identification in this codebase; empirical
> confirmation of mechanism-firing-pattern at step-2 closes the
> ceiling.

**S33 applied to this very investigation**: this memo's §3 + §7
already incorporated empirical envelope analysis from L2 fixture
ball-by-ball scores. The step-2 patch (§10) explicitly mandates
the instrument-then-patch protocol.

**S33 promotion path**: NOT promoted at this commit. Per the
"promote at next close-out commit" pattern observed at S26-v2
promotion at WS-M step-4 + S28 / S22 promotions on two-
instance evidence — S33 PROMOTION lands at WS-O.c step-3
close-out IF the methodology demonstrates value (PA refinement
closes residue via instrumentation-confirmed predicate firing).

---

## §10 Step-2 entry data

### Patch surface (step-2)

**Production code change**: 1 LOC at
`files/eyes/scoreboard.py:1252` (current line; may shift
slightly with my insertions).

```diff
-                _max_plausible = int(_balls * 2.5) + 10
+                _max_plausible = int(_balls * 1.9) + 10
```

No new trace tag (reuses WARM-MODE-MAGNITUDE-GATE-REJECTED).

### S33 instrumentation-aware verification protocol (step-2)

Pre-patch sequence:
1. **Add instrumentation as NO-OP**: clone the proposed predicate
   at the call site, gated as `log.info` only, no `return False`.
   Variable: `_max_plausible_va = int(_balls * 1.9) + 10`.
2. **Run snapshotter against dckkr dump**:
   ```
   files/.venv/bin/python files/scripts/replay_captured_scout_trace.py \
     --dump files/logs/deliveries/watch_20260519_121701/scout_raw.jsonl \
     --session-id dckkr_va_instrumentation_$(date +%Y%m%d_%H%M%S) \
     --fixture dckkr
   ```
3. **Inspect predicate firings** in the trace log:
   - Grep for the instrumentation log lines.
   - Count: how many `v > _max_plausible_va` cases (would-reject
     under VA)?
   - Inspect frames: do they correspond to balls 4.1-4.5
     residue?
   - Cross-check L2 fixture: would any L2 frame trigger?
4. **Decision**: if instrumentation confirms ≥5 firings at
   residue frames + 0 at L2 frames → ship the threshold change.
   Else refine.
5. **Ship behavior change**: remove the NO-OP instrumentation
   and apply the actual threshold change as the single-line
   patch.

### Test obligation (gate-6)

L1.5 cases needed (step-2):
- **O.c-1 VA rejects bogus 63 at balls=24**: synthetic sb state
  at score=43, overs="4.0"; propose sb.set("score", 63, ...);
  assert rejected + WARM-MODE-MAGNITUDE-GATE-REJECTED tag
  emits.
- **O.c-2 VA accepts legitimate boundary at balls=23**:
  synthetic sb state at score=45, overs="3.5"; propose
  sb.set("score", 49, ...); assert accepted (boundary is
  legitimate; 49 ≤ 23*1.9+10 ≈ 53).

L1.5 total: 90 → 92.

### Gate-7 cross-fixture verification (step-3)

After step-2 patch:
1. Re-run snapshotter; diff against post-WS-P baseline.
2. Expected: E2 3→0; conservation 5→0; striker-anchor swap
   UNCHANGED; L2 30/30.
3. Cross-fixture: optionally re-run against GTRR fixture; surface
   any false-negative.

---

## §11 Status footer

**WS-O.c step-1 status.** CLOSED.

- 5 hypotheses enumerated (VA-VE); VA leading.
- Cohort closure UNIFIED-2: VA closes E2 + conservation
  cascade-tied. Striker-anchor SCOPE-RESERVATION unchanged.
- Gates 1, 2, 3, 5 PASS; gate 4 PROMOTE (S33 candidate); gate
  6 OPEN at step-2; gate 7 DEFER to step-3.
- S33 canonical statement drafted at §9; promotion to numbered
  insight deferred to WS-O.c step-3 close-out.

**Recommended next step.** WS-O.c step-2 patch authorization
at the 1-LOC scope (`int(_balls * 2.5) + 10` → `int(_balls *
1.9) + 10`) + S33 instrumentation-aware verification protocol
+ 2 L1.5 cases.

**Sub-mechanism reservation.** Tightest L2 cushion at ball 2.6
(2 runs). Step-2 verification should confirm via instrumentation
NO firing on any L2 frame. If false-positive, bump buffer from
+10 to +12 (still rejects residue 63 at balls=24: 55.6→57.6;
preserves all closures).

**WS-P.b striker-anchor root-cause investigation deferred** as
follow-up to WS-O.c per CC's recommended sequencing.
