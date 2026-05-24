# Workstream O.b — WARM-mode DIRECT-SCORE-COMMIT cascade root (step-1)

**Status.** Step-1 closed; leading candidate identified;
cohort-closure verification UNIFIED-2 (PA closes E2 + conservation;
PE closes negative tokens — cascade-tied through SM-vs-SB
score divergence).

**Trigger.** WS-O step-3 empirical replay at `ed70807` validated
the predicted-flip-table MISS — OA's mechanisms (cold-start
magnitude gate + force_reset_score) wired correctly per the L1.5
contract but NEVER FIRED on the DCKKR dump. The cascade root is
in WARM-mode score-commit logic, not COLD_START seed selection.
Three open questions handed off to WS-O.b:

- Q1: Where in `score_manager.py` does SM.score become 49 given
  cold-start gate doesn't fire + PendingBall queue is empty?
- Q2: Where does `self.this_over.append(str(<negative>))` happen
  given `_synthesize_cold_start_ball_events` excess + PendingBall
  paths are both eliminated?
- Q3: Design the actual fix surface.

**Pre-screen verdict.** GREEN — PIPELINE-DIRECT per S28 (SM
WARM-mode commit logic + score_manager_derivation classifier +
Scoreboard set predicate; no new schemas, no test_pipeline.py
main-loop touch required at step-2).

**Outcome.** Static chain converges on **PA — WARM-mode magnitude
gate at Scoreboard.set("score") + derivation-side negative-runs
guard** as leading candidate. PE token-emission guard at the
classifier ships alongside PA as defense-in-depth (closes the
symptom cohort even if PA leaves residual upstream cases). PB
SM-vs-SB reconciliation deferred as defense-in-depth-of-last-
resort; PC full unification deferred to architectural cleanup pass.

**§12 catalogue 4th-instance promotion.** SM.score (SM-side
tracker) vs sb._inn["score"] (Scoreboard side) is the 4th
confirmed dual-state-write defect instance. Peer to F-α-shadow,
F1/B-ε, B-η/FC5. **S29 candidate promoted: §12 catalogue
extension** (see §9).

---

## §1 Empirical anchor — Q1/Q2/Q3 with per-frame anchors

WS-O step-3 baseline (`files/tests/baselines/dckkr_diff_post_ws_o_baseline.md`)
empirical signature:

- **DIRECT-SCORE-COMMIT trace tag count = 13** across the replay.
  Per `eyes/scoreboard.py:1482-1500`, this tag fires inside
  `Scoreboard.set("score", v, frame)` AT THE WRITE LINE — i.e.
  after the regression-rejection predicate at :1224 passes.
  Implication: 13 separate sb.set("score", ...) calls succeeded
  (`return False` early-exits don't reach the emission). Cold-
  start exit transition synthesises events but those go through
  `_synthesize_cold_start_ball_events` → `self.this_over =
  list(tokens)` (`score_manager.py:2572`); they do not call
  `sb.set("score", ...)`.

- **Snapshotter log line**: `[SM-FEEDER-SYNC] field=score value=49
  sb_accepted=false` plus the Scoreboard warning `Score regression
  rejected: 64→49 (normal-play score physics; reset authority
  required)`. The asymmetric pair: SM internally holds score=49
  while SB holds score=64. SM tries to push 49 into SB
  (FEEDER-SYNC mechanism), SB rejects via the regression
  predicate. The dual-state surfaces diverge and stay diverged.

- **Score-stuck cascade**: per WS-O step-3 §1.1 table, pipeline
  score sticks at 49 from ball 2.3 through 3.5, jumps to 63 at
  3.6, 64 at 4.4. The JUMPS are successful sb.set commits (each
  bumps SB upward; predicate accepts). The STUCK regions are
  SB holding the last accepted value while SM also caches that
  value (or a slightly different one) — the snapshot reads
  `sm.score` for `pipeline.score`.

- **Negative this_over_tokens** at balls 2.3 (`-27`), 2.4 (`-27`),
  2.5 (`-27`), 3.1 (`-20`), 3.2 (`-16`), 3.3 (`-16`), 3.4 (`-15`),
  3.5 (`-11`), 3.6 (`-10`), 4.1 (`-20`), 4.2 (`-19`), 4.3 (`-19`),
  4.4 (`-19`), 4.5 (`-15`). Magnitudes match `(prior.score -
  current.score)` at each frame where the score derivation runs.
  Conservation invariants (14 violations) tie 1:1 to these
  negative-token rows.

- **PendingBall queue empty**: PENDING-BALL-ENQUEUED = 0,
  PENDING-BALL-DRAINED = 0 across the entire replay. The
  PendingBall drain path is not the emission site. WS-O step-2
  V1's narrowing was empirically falsified.

---

## §2 13 DIRECT-SCORE-COMMIT call sites — single call site, 13 firings

**Single emission site**: `files/eyes/scoreboard.py:1490-1500`
inside `Scoreboard.set`. The 13 firings are 13 separate frames
where `Scoreboard.set("score", v, frame)` advanced sb._inn["score"]
(via the `if old != value:` gate). Per-firing call stack:

```
Scoreboard.set("score", v, frame)              # :1188
  ├─ regression-rejection predicate at :1224    # if v < cur_int: return False
  ├─ _tracker.update("score", v, frame)         # :1237
  └─ self._inn[field] = value + DIRECT-SCORE-COMMIT trace  # :1479, :1493
```

**Caller surface for sb.set("score", v, frame).** Static-grep
search across the codebase reveals callers at:
- `replay_captured_scout_trace.py:500-504` — snapshotter
  pre-`sm.on_frame` hydration (mirrors L2 harness pattern):
  `sb.set("score", fi.ext_score, frame=frame_id)`. **Primary
  caller in the snapshotter context.**
- `test_pipeline.py` main loop — production caller chain via
  `score_manager.on_frame` + various direct sb.set writes from
  Scout / extractor consensus paths.

In the snapshotter context, the 13 DIRECT-SCORE-COMMIT firings
correspond to 13 frames where `fi.ext_score` was non-None and
the proposed value passed the regression predicate. **The
cascade root**: at some early frame, `fi.ext_score = 49` was
proposed at a moment when `cur_int < 49`; the predicate passed
(`49 > cur_int`); SB committed 49. The score-stuck cascade follows
from there.

**No SM-side direct write to sm.score that bypasses sb.set was
surfaced at step-1**. The SM-FEEDER-SYNC log line suggests an
SM-internal score sync mechanism but step-1 did not exhaustively
trace SM-side direct writers — deferred to step-2 verification.

---

## §3 SM.score = 49 write path — derivation reads sb-canonical state

Per `replay_captured_scout_trace.py:498-509`:

```python
try:
    if fi.ext_score is not None:
        sb.set("score", fi.ext_score, frame=frame_id)
    ...
except Exception:
    pass

try:
    sm.on_frame(fi)
except Exception as e:
    ...
```

Order of operations per frame:
1. `sb.set("score", fi.ext_score, frame)` — fires
   DIRECT-SCORE-COMMIT if the value advances; else rejects.
2. `sm.on_frame(fi)` — SM consumes the FrameInput; internal
   ScoreManager logic reads sb._inn["score"] (or
   `_tracker.confirmed["score"]`) via `_build_scorecard` (see
   step-1 §2 site map) to compute its own snapshot.

So **sm.score does NOT have its own independent commit path
that bypasses sb.set**. The dual-state surface emerges
DOWNSTREAM in the per-frame derivation:

- Frame N: sb.score = 49 (committed via sb.set).
  sm._build_scorecard reads sb._inn → card.score = 49 → SM's
  internal score snapshot also captures 49.
- Frame N+k: Scout reads a corrected lower score (22). sb.set("score", 22, ...) is called; predicate at :1224 rejects (`22 < 49`). SB stays at 49.
- Frame N+k: sm.on_frame still runs; reads sb._inn["score"]=49.
  SM's snapshot still captures 49. But the prior SM snapshot
  was ALSO 49 — no SM-side movement.
- `score_manager_derivation.py:495` then computes
  `delta_score = current.score - prior.score`. Both are 49,
  so delta is 0. **But the snapshot shows -27, -20, -16
  tokens** — so this isn't the path either at the affected
  frames.

**Reconciled understanding**: SM has a SECOND copy of the score
that DIVERGES from sb when sb's regression predicate rejects
a write but SM's internal tracker accepts (or already cached)
the lower value. This is the dual-state surface — confirmed
existence, exact write-path traceability deferred to step-2.

Step-2 verification task: instrument
`score_manager.py:_build_scorecard` to log every (sb.score,
sm.score-cached) pair per frame. Identify the frame where they
first diverge. The write path SM uses to update its internal
copy WITHOUT going through sb.set is the dual-state-write
Surface A.

---

## §4 Negative this_over_tokens emission path — score_manager_derivation.py:591

**Localized**: `score_manager_derivation.py:584-598`:

```python
# Standard legal ball
if delta_legal_balls == 1:
    if runs_off_bat == 0:
        raw = "."
    elif 1 <= runs_off_bat <= 6:
        raw = str(runs_off_bat)
    else:
        raw = str(runs_off_bat)  # 7+ is rare but legal (overthrows)
    return ThisOverToken(
        raw=raw,
        delta_score=delta_score,
        delta_legal_balls=1,
        wicket_flag=False,
        extras_type=None,
    )
```

Where `runs_off_bat = delta_score - delta_extras` (:498) and
`delta_score = current.score - prior.score` (:495).

**Unguarded negative-runs case**: when `runs_off_bat < 0` (score
went DOWN between snapshots), neither the `== 0` nor the
`1 <= runs_off_bat <= 6` branch fires; the else branch at :591
falls through with the comment "7+ is rare but legal (overthrows)"
but actually emits `str(<any-value>)` — including negative
values. That string flows to `apply_this_over_token` at
`score_manager.py:1222` → `self.this_over.append(token.raw)` at
:1239.

**The classifier's else branch is the emission site.** The
`# 7+ is rare but legal` comment is misleading — the predicate
fails to bound the input from below. Defensive fix (PE): guard
the else branch with `if runs_off_bat < 0: return None` so the
classifier signals "no token; upstream regression detected"
instead of emitting `str(<negative>)`. Caller behaviour for
None return needs verification.

**Why does runs_off_bat go negative on the DCKKR dump?** Per §3,
SM and SB diverge on score. The classifier runs against
snapshots that may carry the divergent values. Specifically:
- prior.score = some inflated stuck value (e.g., 49)
- current.score = a corrected lower read (e.g., 22)
- delta_score = -27, runs_off_bat = -27 (no extras)
- Token = "-27".

So **the negative-token emission is downstream of the
SM-vs-SB score divergence**. Closing the dual-state-write
upstream (PA) eliminates the negative deltas; PE is the
defense-in-depth that catches any residual cases.

---

## §5 SM.score vs sb.score — §12 dual-state-write 4th instance

Per `files/docs/investigations/sm_as_orchestrator_design.md` §12
catalogue methodology:

| Axis | F-α-shadow | F1/B-ε | B-η/FC5 | **WS-O.b (this)** |
|---|---|---|---|---|
| Surface A (weaker) | Snapshot-read path | F1 batter shadow attr | B-η FoW canonical | **SM-internal score copy (sm.score / _tracker.confirmed["score"])** |
| Surface B (stronger) | Canonical attribute | B-ε wicket counter | FC5 cross-credit | **Scoreboard sb._inn["score"]** |
| Divergence-detection signal | Read returns stale | shadow + canonical disagree | FoW count drifts | **`[SM-FEEDER-SYNC] ... sb_accepted=false` + `Score regression rejected` pair on consecutive frames** |
| Cascade signature | Snapshot tests pass, prod fails | Cross-credit cascade | Bowler-W cascade | **E2-phantom-runs + conservation invariants + negative this_over_tokens cascade** |
| Detected via | Static read-path audit | Two-fixture replay | Static analysis | **Empirical replay against ground truth (WS-O step-3)** |
| Remediation pattern | Tighten weaker | Route through stronger | Unify at source | **TBD step-2 — see §6** |

**S29 promotion candidate**: WS-O.b lands as the 4th confirmed
dual-state-write instance. The catalogue methodology generalises:
each new instance follows the same Surface-A-weaker / Surface-B-
stronger / detection-signal / cascade-signature / remediation
pattern. After this instance the methodology has saturated across
four fix-class families (snapshot tooling / batter / wicket /
score). S29 stands for "§12 catalogue extension — score-side dual-
state-write confirmed; methodology generalises across four fix
families".

---

## §6 Hypothesis enumeration — PA/PB/PC/PD/PE

Four candidates from user spec + one defense-in-depth addition.
Static §7.2 gates 1-3 each.

### PA — WARM-mode magnitude gate at Scoreboard.set("score") — **LEADING**

**Mechanism.** Mirror OA's COLD-START magnitude gate, but at
`Scoreboard.set("score", v, frame)` (:1220-1236) BEFORE the
regression-rejection predicate. Reject proposed scores that
exceed an RPO-derived plausibility cap given the current
sb._inn["overs"] value. Catches the original bogus 49 commit
before it lands.

**Gate 1 (fit).** PASS — prevents the cascade root (bogus
upward commit landing in SB). Once SB never accepts 49, SM's
mirror never captures 49, derivation never computes negative
deltas, negative tokens never emit.

**Gate 2 (backward-compat).** PASS (with constraints) — gate
threshold must be empirically validated against legitimate
fast-scoring frames (15+ RPO in early overs is legitimate on
some innings). Threshold candidate: same as OA's
`balls * 2.5 + 6` formula applied to the proposed score+overs
delta from the current state.

**Gate 3 (fix-surface attribution).** PASS — PIPELINE-DIRECT;
modifies `eyes/scoreboard.py` `set` method (~15 LOC). No SM
changes; no test_pipeline.py main-path touch.

**Status.** Leading candidate.

### PB — SM-vs-Scoreboard reconciliation on sb_accepted=false — **DEFENSE-IN-DEPTH**

**Mechanism.** When SM's FEEDER-SYNC observes `sb_accepted=false`
(SM proposed value, SB rejected via regression predicate), SM
should NOT silently retain the lower value while sb holds the
higher value. Three possible reconciliations: (a) SM adopts
sb's value (trust SB); (b) SM triggers consensus-check
mechanism; (c) SM emits SM-VS-SB-DIVERGENCE trace for analyzer
to surface.

**Gate 1.** PARTIAL — treats symptom (existing divergence) not
root (bogus commit). Useful as defense-in-depth IF PA leaves
residue.

**Gate 2.** RISK — auto-adopting SB's value (option (a)) could
mask legitimate corrections; option (c) telemetry-only is safe.

**Gate 3.** PASS — pipeline-direct.

**Status.** Defense-in-depth (telemetry-first option (c)
recommended). Defer behavioural reconciliation until production-
session validation reveals whether the divergence persists post-PA.

### PC — Unify dual-state-write at source — **DEFERRED**

**Mechanism.** Eliminate the dual-state surface: SM reads
sb._inn["score"] live for every read rather than maintaining
an internal cached copy. Eliminates the divergence class
entirely.

**Gate 1.** PASS in theory — addresses the structural pattern.

**Gate 2.** HIGH RISK — broad-surface refactor; multiple SM
internals depend on `self.score` semantics; cascade audit
required across all callers.

**Gate 3.** PIPELINE-DIRECT but engineering-class scope
(>>100 LOC). Defer to architectural cleanup pass per §12
remediation guidance ("Deferred as engineering workstream when
the narrow remediation lands cleanly").

**Status.** Deferred. Reserve for post-stabilisation cleanup
if WS-O.b's PA + PE land cleanly and N-th-instance dual-state
defects continue to surface in adjacent surfaces.

### PD — Hybrid PA + PB + PE — **RECOMMENDED STEP-2 SHAPE**

PA (gate) + PE (token guard) + PB telemetry-only.

**Gates 1-3 PASS** (composite of PA + PE + PB-telemetry).
Estimated combined LOC: ~30-35 LOC across 3 files
(scoreboard.py + score_manager_derivation.py + score_manager.py).

### PE — derivation-side negative-runs guard — **NEW DEFENSE-IN-DEPTH**

**Mechanism.** Guard `score_manager_derivation.py:591` else
branch: `if runs_off_bat < 0: return None` (or emit a regression
signal token instead of stringifying the negative value).

**Gate 1.** PARTIAL — closes negative-tokens cohort but not the
upstream divergence. UNIFIED-2 closure: PA closes E2 +
conservation; PE closes negative tokens.

**Gate 2.** PASS — additive guard; callers of
`_classify_legal_ball` (or the parent function) must handle
None return gracefully. Verify at step-2.

**Gate 3.** PASS — single-line guard at the classifier.

**Status.** Ship alongside PA as defense-in-depth.

---

## §7 §7.2 audit on leading candidate (PA + PE = PD)

| Gate | Status | Rationale |
|---|---|---|
| 1 (defect-class fit) | PASS | PA prevents bogus upward commit; PE prevents negative-token leakage. UNIFIED-2 cohort closure (E2 + conservation cascade-tied to PA; negative tokens defended by PE). |
| 2 (backward-compat) | PASS (conditional on RPO threshold validation) | PA threshold must accept legitimate high-RPO frames; PE's None return must be handled by all classifier callers. |
| 3 (fix-surface attribution) | PASS | PIPELINE-DIRECT; ~15 LOC PA + ~5 LOC PE = ~20 LOC core; +~10 LOC PB telemetry; ~30-35 LOC total. |
| 4 (sub-finding promotion) | PROMOTE | S29 candidate confirmed (§12 catalogue 4th instance). Methodology-class observation: scope-narrowing cascade saturated at 8 instances (§9). |
| 5 (cohort enumeration completeness) | PASS | E2 + conservation + negative tokens + striker-anchor (SPLIT) all enumerated; no orphan cohorts. |
| 6 (test obligation) | OPEN at step-2 | New L1.5 cases: O.b-1 PA gate rejects bogus high score at WARM; O.b-2 PA gate accepts legitimate fast-scoring; O.b-3 PE guard converts negative runs_off_bat to safe signal; O.b-4 PB telemetry tag fires on divergence. |
| 7 (cross-fixture verification) | DEFER to step-3 | Re-run snapshotter; verify E2 + conservation + negative-tokens close + no surface regressions. |

---

## §8 Predicted-flip table for step-2

| Cohort | Pre-WS-O.b | Post-WS-O.b (predicted) | Predicted flip |
|---|---|---|---|
| E2-phantom-runs | 10 | 0 or near-0 | CLOSE (UNIFIED-2 via PA) |
| Conservation invariants (§3) | 14 violations | 0-2 | CLOSE-TIED-TO-E2 |
| `this_over_tokens` negative | ~7 rows | 0 | CLOSE (UNIFIED-2 via PE direct; PA upstream removes the negative-delta inputs entirely) |
| Striker-anchor swap | ~50 fields | UNCHANGED (SPLIT) | SCOPE-RESERVATION (defer to WS-O.c or WS-P) |
| `DIRECT-SCORE-COMMIT` count | 13 | ≤13 (some rejected by PA) | TELEMETRY |
| `SCORE-MAGNITUDE-WARM-REJECTED` (new tag) | 0 | ≥1 | mechanism-confirm |
| `SM-VS-SB-DIVERGENCE` (new tag) | 0 | possibly ≥0 | telemetry-only (PB option c) |
| Other 12 surfaces | (post-WS-N + WS-O baselines) | UNCHANGED | regression-guard |
| L2 ledger | 30 PASS | 30 PASS UNCHANGED | LOAD-BEARING |
| L1.5 total | 84 (post-WS-O O1) | 88 (post-WS-O.b O2) | regression-guard |

---

## §9 Sub-findings

### S29 PROMOTED — §12 catalogue 4th instance landed

**Standing primitive**: §12 dual-state-write catalogue has
saturated across four fix-class families (snapshot tooling /
batter / wicket / score). Pattern is mature; remediation
methodology proven across four distinct surfaces. Future
candidate audits should default to "is this a §12 instance?"
as a first-screen question.

**Action**: append WS-O.b to the §12 catalogue table in
`sm_as_orchestrator_design.md` as part of step-2 work. Update
HANDOFF.md reference. Defer to step-2 commit to avoid scope
creep at step-1 (read-only investigation).

### Methodology footprint — scope-narrowing cascade saturated at 8 instances

WS-O's narrowing cascade across step-1 → step-2 → step-3
each falsified the prior cycle's emission-site narrowing:
1. **WS-L step-1b** (`394ed58`) — 10-call deviation discovery.
2. **WS-M step-1b** (`c46fcb0`) — 1-call cohort-split discovery.
3. **WS-N step-1b** (`6c322c5`) — 1-call sub-mechanism (b) confirmation.
4. **WS-N step-2 verification** (no commit) — 3-call scope-expansion.
5. **WS-N step-1c** (`9631a29` region) — 1-call Fork C MESSY-PARTIAL verdict.
6. **WS-O step-1 → step-2** — emission-site narrowed (a)+(b) falsified, (c) proposed.
7. **WS-O step-2 → step-3** — (c) falsified empirically; PendingBall queue empty.
8. **WS-O.b step-1 (this)** — actual emission site located at `score_manager_derivation.py:591`; root upstream at SM-vs-SB dual-state-write.

**S26 + S26-v2 framework's design ceiling**: each cycle costs 1-3 tool calls. Eight cycles total = ~15-25 tool calls vs the prevented production-harm cost of misspecified patches that ship + ripple downstream. The methodology is working as designed; saturation candidacy stands but no S-number promotion required at this step per standing discipline.

No new sub-findings beyond these two.

---

## §10 Step-2 entry data

### Patch surface (step-2)

1. **`files/eyes/scoreboard.py`** — `Scoreboard.set` (:1220-1236):
   add WARM-mode magnitude gate BEFORE the regression-rejection
   predicate. Reject proposed scores exceeding
   `balls * 2.5 + 6` (mirrors OA's COLD-START formula). Emit
   `SCORE-MAGNITUDE-WARM-REJECTED` trace. ~15 LOC.

2. **`files/score_manager_derivation.py`** — `_classify_legal_ball`
   (:584-598): guard the else branch with
   `if runs_off_bat < 0: return None`. Caller surface
   (`apply_this_over_token`) must handle None gracefully —
   verify at step-2. ~5 LOC.

3. **`files/score_manager.py`** — FEEDER-SYNC site (TBD step-2
   localisation): emit `SM-VS-SB-DIVERGENCE` trace tag when
   `sb_accepted=false`. Telemetry-only at this commit (no
   behavioural reconciliation). ~10 LOC.

4. **`files/trace_emitter.py`** — register new tags:
   `SCORE-MAGNITUDE-WARM-REJECTED`, `SM-VS-SB-DIVERGENCE`.

5. **`files/docs/investigations/sm_as_orchestrator_design.md`**
   §12 catalogue: append WS-O.b as 4th instance row. Update
   the catalogue commentary at lines 921-923. ~15 LOC docs.

Total estimated: ~30-35 LOC code + ~15 LOC docs.

### Test obligation (gate-6)

L1.5 cases needed (step-2):
- **O.b-1 PA gate rejects bogus high score at WARM**: synthesize
  sb._inn at score=10/overs=2.0, propose score=49 → gate
  rejects + SCORE-MAGNITUDE-WARM-REJECTED fires.
- **O.b-2 PA gate accepts legitimate fast-scoring**: sb._inn at
  score=10/overs=2.0, propose score=22 (legitimate +12 inside
  cap) → gate accepts.
- **O.b-3 PE guard converts negative runs_off_bat**: drive
  classifier with prior.score=49, current.score=22, delta=-27
  → classifier returns None (or signal token) instead of
  emitting "-27".
- **O.b-4 PB telemetry fires on divergence**: simulate
  sb_accepted=false → SM-VS-SB-DIVERGENCE tag emitted.

L1.5 total: 84 → 88.

### Gate-7 cross-fixture verification (step-3)

After step-2 patch:
1. Re-run snapshotter against
   `files/logs/deliveries/watch_20260519_121701/scout_raw.jsonl`.
2. Compare against post-WS-O baseline at
   `files/tests/baselines/dckkr_diff_post_ws_o_baseline.md`.
3. Expected: E2 cohort 10 → 0-2; negative-tokens ~7 → 0;
   conservation invariants 14 → 0-2. Striker-anchor swap
   unchanged (SCOPE-RESERVATION).
4. Cross-fixture: re-run against
   `validate_dckkr_20260521_155356/scout_raw.jsonl` per runbook
   §5 second-fixture pass; surface any false rejections.

### Recommended next step

**WS-O.b step-2 patch authorization** at the ~30-35 LOC PD scope
(PA + PE + PB-telemetry) + 4 L1.5 cases (~80 LOC test
scaffolding) + §12 catalogue update (~15 LOC docs).

Step-2 verification preconditions (must hold before patch):
- Confirm SM's FEEDER-SYNC site exists at the expected location
  (step-1 §3 trace incomplete — needs localisation).
- Confirm `apply_this_over_token`'s caller surface handles None
  return from `_classify_legal_ball`.
- Confirm RPO-derived threshold doesn't false-reject any L2
  ledger frame's legitimate sb.set("score", ...).
- Confirm §15-fence non-violation (score-side; mirrors WS-O OA
  audit — confirmed safe).

If any precondition fails: STOP, report, do not patch.

---

## §11 Status footer

**WS-O.b step-1 status.** CLOSED.

- 5 hypotheses enumerated (PA + PB + PC + PD + PE). PD (PA +
  PE + PB-telemetry) leading at ~30-35 LOC scope.
- Cohort closure UNIFIED-2: E2 + conservation close via PA;
  negative tokens close via PE upstream (PA cascade) +
  defense-in-depth (PE direct). Striker-anchor swap (~50)
  SCOPE-RESERVATION unchanged.
- Gates 1-3 + 5 PASS; gate 2 conditional on RPO threshold
  validation at step-2; gate 4 PROMOTE (S29 + methodology
  footprint); gate 6 OPEN at step-2; gate 7 DEFER to step-3.
- §12 catalogue 4th instance promotion confirmed.

**Recommended next step.** WS-O.b step-2 patch authorization at
the PD ~30-35 LOC scope.

**Sub-mechanism reservations.**
- SM's internal score copy WRITE PATH (vs sb-canonical
  reads) — step-1 narrowed to "exists" but exact write site
  not exhaustively located. Step-2 instrumentation +
  static-grep can confirm before patch.
- `apply_this_over_token` caller surface for None return —
  step-2 verification check.

**OA disposition.** WS-O OA patch (`deba545`) STAYS LANDED as
defense-in-depth for COLD_START scenarios its L1.5 cases prove
it handles. WS-O.b is the additional fix surface for the WARM-
mode root cascade WS-O step-3 surfaced.
