# P4 Diagnosis — Partnership vs At-Crease Batter Sum Divergence

Trace: `logs/trace/866ce150.jsonl` (175 frames).
Anomaly: `P4` (advisory) fires at frame 179 and again ~185.
Operator decision Q4 keeps P4 advisory only — does **not** count
toward Errors/Warnings.

## §1. Symptom + advisory severity context

`rule_p4_advisory` (`files/anomaly_rules.py:407-461`) computes

```
delta = | partnership_current.runs  −  Σ at-crease batters.runs |
fire   if delta > P4_TOLERANCE (=2) and sustains for ≥ 3 records.
```

It fires twice on the same partnership window with two different
deltas (7, then 3). Severity is `"advisory"` per docstring §17 of
`anomaly_rules.py`; report bucketing already separates it from
Errors/Warnings.

## §2. Trace evidence

```
frame  ui partnership   batters at crease            extras_total
175    4 (6)            QdK 2(2) | RH 2(3)           0
178    4 (6)            QdK 2(2) | RH 2(4)           0      committed: SCORE-INF-GATE:advance=7>6
179    11 (16)          QdK 2(3) | RH 2(4)           0      committed: score→11, overs→2.4   ball_event=MULTI_BALL
180    11 (16)          QdK 2(3) | RH 2(4)           7      (info-panel extras arrive)
181    11 (24)          QdK 2(2) | RH 2(4)           7      overs→4.0   (more MULTI_BALL gap fill)
…
185    11 (24)          QdK 2(3) | RH 6(5)           7      committed: SCORE-INF-GATE:proposed=11<bat_sum=8+extras=7
186    11 (24)          QdK 2(3) | RH 6(5)           3      (extras snapped from 7→3)
202-04 11 (24)          QdK 2(3) | RH 6(5)           3      committed: SCORE-INF-GATE:proposed=8<bat_sum=8+extras=3
```

Two divergences in one window:

- **Δ=7 (frames 179-184).** UI batter-sum 4, partnership 11. The
  reported `extras_total` arrives one frame late (180) and equals
  exactly 7. ⇒ `partnership − Σbatters = extras_total`.
- **Δ=3 (frames 185-198).** Hendricks ticks +4 to 6(5) (legitimate
  ball). Partnership stays 11, extras drops 7→3. Again
  `partnership − Σbatters = extras_total` after the snap.

In both segments `delta` exactly equals the contemporaneous
`extras_total`. Cricket: partnership runs ≡ team runs scored while
the pair is at the crease ≡ Σbatter_runs + extras_during_partnership.

## §3. Partnership-update flow (file:line)

State fields: `files/score_manager.py:192-194`
(`partnership_runs`, `partnership_balls`, `partnership_known`).

Update sites:

- `_apply_event` non-WICKET branch — `score_manager.py:2920-2928`:
  ```
  self.partnership_runs  += event.get("runs", 0)
  self.partnership_balls += 1 if event.get("legal", True) else 0
  ```
  Increments unconditionally for every non-WICKET event type,
  including `WIDE`, `NO_BALL`, `B`, `LB` (treated as extras
  elsewhere — see §4).

- `_apply_absorbed_event` (gap-fill) — `score_manager.py:2789-2800`:
  ```
  self.partnership_balls += 1
  if is_last:
      self.partnership_runs += int(gap_meta.get("runs") or 0)
  ```
  Multi-ball gap (`MULTI_BALL` decomposed via
  `_decompose_multi_ball`, `score_manager.py:2422-2462`) attributes
  the **entire gap run-delta** to partnership at the last absorbed
  ball. Individual batter cards are **not** credited inside the gap
  by design (Policy U / Issue 3 — gap is unwitnessed, striker
  attribution unknown).

- Wicket reset — `score_manager.py:2776-2778` and 2794-2797: zero
  on wicket; mark `partnership_known=False` until next ball.

UI emit point — `score_manager.py:1856-1865` and `:3150-3155`:
`partnership.runs / .balls` are surfaced verbatim from the SM
counters; no extras subtraction or accounting on the read side.

## §4. Extras-credit flow (file:line)

- Strip-side detection: `_etype in ("WIDE","NO_BALL")` or token
  `"Wd","Nb","B","LB"` — `score_manager.py:2879-2902`. Updates
  `extras["total"]`, `extras["this_over"]`, append to `extras.log`,
  bumps `this_over_extras`, `innings_extras`. Does **not** touch
  partnership; partnership is bumped in the unconditional branch
  at line 2927 with whatever `event["runs"]` is.

- Info-panel extraction: `test_pipeline.py:1482-1486` reads
  `extras_total` from the broadcast info panel and stamps it on
  the per-frame result.

- Broadcast vs SM reconciliation:
  `test_pipeline.py:6450-6516` — when broadcast extras_total
  exceeds SM total, store as `scoreboard.extras["broadcast_total"]`
  (line 6454). Separately (line 6507-6516) **infer** extras from
  `score − bat_sum` and overwrite `extras["total"]` if positive.

- Layer 1.5 floor gate uses extras: `test_pipeline.py:3101-3133`
  returns `(bat_sum, extras_total, complete)` which feeds the
  SCORE-INF-GATE arithmetic at 3320-3330.

## §5. Where they diverge — does partnership include extras?

**Yes, partnership runs include extras-during-partnership** — and
it must. Cricket scoring: `partnership_runs = Σbatter_runs +
extras_credited_during_pair_at_crease`. The SM accounting in
`_apply_event` line 2927 is faithful to that (extras-style events
add to partnership exactly as runs of any other event).

The P4 rule's identity, by contrast, is

```
partnership_runs ≟ Σ at-crease batters.runs        (rule, naive)
```

i.e. it omits the `+ extras_during_partnership` term. So whenever
extras > P4_TOLERANCE (default 2) accumulate within an unbroken
partnership, P4 fires by construction — even when SM accounting is
fully correct.

Frame-by-frame proof:

- 179-184: SM partnership=11, batters=4, `extras_total=7` →
  `4 + 7 = 11` ✓ (cricket-correct).
- 185-198: SM partnership=11, batters=8, `extras_total=3` →
  `8 + 3 = 11` ✓ (cricket-correct).
- The MULTI_BALL gap at 179 (decomposed 8 absorbed balls,
  d_score=7) is the mechanism that pushed extras into partnership
  ahead of batter-card credit, but the resulting state remains
  cricket-correct once extras_total catches up one frame later.

A secondary, narrower SM-side asymmetry exists for **gap-fills**:
`_apply_absorbed_event` puts gap runs onto partnership but **never**
onto individual batter cards (`score_manager.py:2789-2800`). For
gaps that genuinely contain bat-credited runs (boundary missed
during ad), this widens `partnership − Σbatters` even when extras
are zero. The 866ce150 trace does **not** exhibit this scenario in
the cited window — extras_total fully accounts for the delta — but
it is a latent contributor.

## §6. Root cause hypothesis

1. **Primary (drives 100% of the firings in this trace).** The P4
   rule is an incomplete physics check. It fails to subtract
   extras_during_partnership from `partnership_runs` before
   comparing to `Σbatter_runs`. Identity should be
   `partnership_runs == Σbatter_runs + extras_partnership` ± tol.
   The rule fires whenever in-window extras exceed tolerance, even
   for legitimate cricket states.

2. **Latent.** SM gap-fill credits partnership but not individual
   batter cards (`_apply_absorbed_event:2789-2800`). When a gap
   actually contains bat runs (not extras), this re-creates the
   same delta — but is intentional under Policy U (unwitnessed
   gaps cannot be safely attributed to a striker). Touching it
   trades one anomaly for striker mis-attribution risk.

3. **Adjacent / unrelated to P4 but flagged in the brief.** Extras
   source-of-truth oscillates (broadcast=7 vs inferred=3 between
   frames 185→186, `test_pipeline.py:6450-6516`). This is the
   "extras was all over the place" observation. It does **not**
   cause P4 (P4 ignores extras entirely) but it does perturb
   `SCORE-INF-GATE` arithmetic and is worth its own ticket.

## §7. Proposed fix scope

**(a) Fix partnership-vs-batter rule identity (P4 only — small).**
Amend `rule_p4_advisory` to compute expected partnership as
`Σbatter_runs + extras_in_partnership` and compare to
`partnership_runs`. Two implementation paths for the
`extras_in_partnership` term:

- **Lean path:** if no wicket has fallen yet in the innings,
  partnership covers the whole innings, so use `extras_total`
  directly. After ≥ 1 wicket, the rule needs an
  `extras_at_partnership_start` snapshot the SM does not currently
  expose — easiest is to skip P4 firing while a fresh snapshot is
  unavailable (return [] until next wicket), preserving the
  no-wicket common-case win. Pure rule-side change; no SM edits.
- **Full path:** add `partnership_extras_runs` to the SM (snapshot
  `innings_extras` at each wicket reset, exposed under
  `partnership_current.extras`). Rule becomes
  `|partnership.runs − (Σbatter + partnership.extras)| > tol`.
  Touches SM emit + UI shape + rule.

**(b) Fix extras attribution wider (cascade).** Stabilise
`scoreboard.extras["total"]` source-of-truth: pin to broadcast
when present, only infer from `score − bat_sum` when broadcast
absent and bat_sum is committed-clean. Touches
`test_pipeline.py:6450-6516` and SCORE-INF-GATE callers (3320-
3330, 3400-3426). Risk: changes SCORE-INF-GATE's floor for many
frames — needs shadow eval, not a same-day fix.

## §8. LOC estimate per option

- **(a) Lean rule patch:** ~25 LOC in `files/anomaly_rules.py` +
  ~10 LOC in `files/tests/test_anomaly_rules.py` (one new case
  asserting non-firing when extras absorbs the delta, one case
  asserting firing when delta exceeds extras). No SM, no
  pipeline, no UI changes.
- **(a) Full rule + SM exposure:** ~25 LOC rule + ~15 LOC in
  `score_manager.py` (snapshot + emit) + ~10 LOC test. ~50 LOC.
- **(b) Extras source-of-truth stabilisation:** ~80-150 LOC across
  `test_pipeline.py:6450-6516`, gate callers, SM extras writer,
  plus shadow harness output diff. Multi-day.

## §9. Recommend: fix today vs defer

**Today: (a) lean rule patch.** The trace confirms every P4 firing
in `866ce150` is a false positive driven by the rule's missing
extras term. The fix is rule-local, ~25 LOC, ships as advisory →
quieter advisory, no commit-path risk. Defer the SM
`partnership_extras` snapshot to a follow-up unless P4 fires
post-wicket within the next 1-2 traces.

**Defer: (b) extras source-of-truth.** Real bug, but P4 is not the
right entry point and the cascade through SCORE-INF-GATE warrants
its own design memo + shadow run. Open a separate ticket
("extras_total oscillates 7↔3 around frame 185") referencing the
trace evidence in §2.
