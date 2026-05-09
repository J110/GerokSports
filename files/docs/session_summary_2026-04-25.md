# Session summary — 2026-04-25

V5 validation run during DC vs PBKS (35th match, IPL 2026).
Production monitoring as planned — zero new code shipped — but
the run surfaced **two P0 root-cause regressions** that justify a
focused fix-session before the next live run.

---

## 1. The plan vs what happened

**Plan (per yesterday's checklist):**
- Validate V5 `camera_view` distribution against expected ranges.
- Confirm/refute the predicted phase regression on `bowlers_end`.
- Verify the V1 alias re-point (`wide_shot`/`wide` → `side_on`).
- Opportunistically capture data for the phase-regression mini
  shadow run.

**What happened:**
- All four plan items completed with clear verdicts (section 2).
- The pipeline entered a corrupted SM state at frame F339 (15:50:05,
  ~17 min into capture) and **never recovered** for the rest of
  innings 1.  Three downstream guards combined to make recovery
  impossible.  See section 3.
- Commentary stack remained robust to SM corruption — the
  storyteller continued producing high-quality output by reading
  broadcast strips directly.  This is a useful positive signal.

---

## 2. V5 verdicts

### 2a. `camera_view` distribution — incomplete verdict, precision eval required

After **1250 SCOUT calls** spanning the full first innings:

| Bucket       | V5 expected | Live    |
|--------------|-------------|---------|
| `bowlers_end`| 40–55%      | 20.4%   |
| `closeup`    | 25–35%      | 43.9%   |
| `graphic`    | 3–7%        | 18.1%   |
| `side_on`    | nonzero     | 0.24%   |
| `ad`         | stable      | 5.8%    |
| `other`      | stable      | 3.6%    |

**The shift is dramatic but distribution is not a quality measure.**
V5 was designed to suppress `bowlers_end`'s collapse-mode behavior
(was ~83% pre-change).  It did so.  Whether that's an over-correction
("V5 is now wrong in the opposite direction") or a *correctly tighter*
classifier ("V5 emits `bowlers_end` less often but more accurately")
cannot be determined from distribution alone.

**Required next step before V5 → V6:** label 20–30 production frames
where V5 emitted `bowlers_end` and compute production precision.

- If precision > 40–50% on those frames, V5 is a real improvement
  (V0's ~15% precision is the comparison baseline) and "overcorrection"
  framing is wrong.
- If precision is around V0's ~15%, V5 only shifted the failure
  mode and a V6 iteration is justified.

Same eval should be done on `closeup` and `graphic` — if V5 is
emitting these *correctly* on frames that V0 misclassified as
`bowlers_end`, the distribution shift is a feature, not a bug.

**On the apparent monotonic decline within session.**  My initial
observation `28.6 → 25.8 → 23.1 → 20.4` across cumulative sweeps was
**an averaging artifact** of cumulative means, not a real trend.
Per-10-min wallclock bins on the same data show `bowlers_end` share
bouncing around 22–27% for the first 80 minutes (15:30–16:50)
with no consistent direction:

```
24.1  26.7  30.8  22.9  26.3  25.5  21.9  21.4  19.6  14.3  19.1  6.6  16.0
```

The dip from 19.6 → 14.3 → 19.1 → 6.6 → 16.0 from 16:50–17:30
coincides with the innings-break window (17:20 bin shows ad share
jumping from typical ~5% to 17.0%, a clean signal for pre-break
sponsor segment).  Hypothesis A (in-session bias accumulation) is
ruled out.  Match-phase variance (B) and small-bin noise (C) jointly
explain what we see.

### 2b. Phase regression on `bowlers_end` — confirmed

Final phase distribution on `bowlers_end` frames (n=238):
- `between_play`: 181 (76.0%)
- `release`: 19 (8.0%)
- `shot`: 23 (9.7%)
- `flight`: 10 (4.2%)
- `runup`: 2 (0.8%)
- `post_shot`: 3 (1.3%)

**Delivery-context phase rate: 24.0%** (vs V0 baseline ~40%).

The shadow-run prediction held: V5's STEP-1 closeup example (which
emits `between_play`) bleeds into the `bowlers_end` decision and
biases toward `between_play`.  Severity is consistent with the
shadow run's prediction.  This is a **prompt-level regression with
no behavioral mitigation today**; see backlog P1 "Phase regression
from V5 multi-example prompt".

### 2c. V1 alias re-point — confirmed inert (Scout never produces source tokens)

`_CAMERA_VIEW_ALIASES` correctly maps `wide_shot`/`wide` → `side_on`.
The implementation is fine.  However, in 1250 SCOUT calls the raw
unaliased Scout output produced `wide_shot` zero times and `wide`
zero times.  Total `side_on` emissions across the run: **3** (0.24%).

The mechanism for V5 emissions appears to be: a category emerges
reliably **only if it has a STEP-1 example**.  V5 added `graphic` as
the third example; `side_on` is named in the rubric but has no
example.  Result: `graphic` emits frequently, `side_on` doesn't.

**Two paths forward, both contingent on the precision eval (2a):**
1. **Add `side_on` as a fourth STEP-1 example.**  Risks further
   destabilizing the closeup/bowlers_end balance V5 reached.  Worth
   trying via shadow run if precision eval shows V5 is misclassifying
   wide-elevated shots (boundary chases / third-man fielder chases)
   as `bowlers_end`.
2. **Keep `side_on` in the schema but accept the low rate.**  If the
   precision eval shows V5 absorbs wide-elevated shots into
   `bowlers_end` *correctly* from a downstream-consequence standpoint
   (DWR windows still capture the action), the distinction matters
   less than the overall bowlers_end precision.

**Path 0 (drop side_on entirely) is rejected.**  `side_on` has real
downstream consumers: `test_pipeline.py:683`
(`_ACTIVE_PLAY_VIEWS = ("bowlers_end", "side_on")` — gates DWR
active-play interval and dead-time skipping), `ball_analyzer.py:627`
(delivery-detection gate).  Removing `side_on` would collapse it
into `other`, which is dead-time-skipped — wide elevated shots
during boundary chases would close DWR windows mid-action.

### 2d. Data capture for phase-regression mini shadow run

The full-innings DETAIL log captures every Scout output with
camera_view + frame_phase + STRIP + scorer changes — sufficient to
build a 100+ frame "post-V5 phase ground truth" set offline.  Will
extract once the run terminates.

---

## 3. Two P0 regressions surfaced

These are downstream defects that V5 didn't cause but exposes.

### P0-A: SCORER doesn't enforce active-batter invariants

At **F339 (15:50:05)** the broadcast cut to a phase-economy stats
graphic.  Scout emitted a malformed strip:
`STRIP: DC 45-1 (3.5) | NEW DELHI PUNJAB KINGS ECONOMY, TATA IPL
2026 OVERS 1-6 10.6  OVERS 7-15 9.1  OVERS 16-20 10.0  T...`

The scorer extracted **three** batter names from this and earlier
context (Rahul, Pathum, Rana) and inserted all three into the active
batter list — including Pathum, who had been dismissed 7 minutes
earlier.  Pathum's stats then re-froze at her dismissal figures
`11(7)` and the ScoreManager carried her forward as an active
batter for the next 92 minutes.

The scorer doesn't enforce two cricket-physics invariants:
1. `len(active_batters) <= 2`
2. `active_batters ∩ dismissed_batters == ∅`

Both checks would have caught this regression at frame F339.
See backlog P0 (filed today).

### P0-B: Recovery deadlock from compounded guards

Even after F339, scout/extractor continued to emit correct strips
(Rana 11, 22, 43, 73 at successive overs; Marco Jansen / Bartlett /
Arshdeep as the actual bowlers).  None of these correct reads
made it into SM because of three independent guards:

1. **`FRAME_POISONED`** — score-jump guard rejects updates when the
   broadcast score is too far from SM's stale value.
2. **`[GUARD] runs diff comparison strip for batting team`** —
   runs-delta guard rejects updates when an existing batter's runs
   jump too much, treating the strip as a comparison/graphic.
3. **`[WS-SCRUB] non_striker rejected reason=status_yet_to_bat`** —
   WS payload scrubber rejects players whose squad-status is
   `yet_to_bat`.  The auto-dismiss-replacement path doesn't update
   the squad's static `status` field when a new batter comes in,
   so Rana stays `yet_to_bat` forever and gets scrubbed every
   single frame she's mentioned.

Lifetime WS-SCRUB count at innings 1 end: **1330**.  STATE
indicator never moved off `inn=1` despite the innings ending at
20 overs.

Each guard is individually reasonable.  Composed they form a
deadlock with no exit:

- FRAME_POISONED rejects updates that would correct SM (because
  they look like jumps from SM's stale value).
- Runs-delta guard rejects strips that show the new batter's
  progressive runs (because the existing record has wrong runs to
  compare against).
- WS-SCRUB rejects the new batter's name because squad-status
  hasn't been updated.

**The architectural pattern is the issue, not the individual guards.**
Tightening any single guard wouldn't fix the deadlock; loosening
any single guard would re-open the failure modes those guards exist
to prevent.

The right fix is a **multi-guard consensus override**: when N
consecutive frames produce internally-consistent proposed states
(batter exists in squad, runs progress monotonically, score
monotonic, bowler valid) that get rejected by all three guards
*simultaneously and in agreement*, that's structural evidence the
**state itself is wrong, not the reads**.  The override accepts the
proposed state and resets SM to match.

This is parallel to the rotation-guard override pattern from
earlier sessions: each guard rejects in isolation, but cross-guard
agreement on the rejection target is a positive signal that the
guards' reference state is the wrong thing.

Implementation: guards report rejection reasons + proposed-state
to a central tracker; tracker detects "all guards rejecting in
agreement on a coherent alternative state" as the trigger; reset
SM with telemetry and an explicit `[STATE-RECOVERY-OVERRIDE]` log
line.  Substantive work — 2–3 hours including telemetry,
consensus thresholds, and validation tests.

The alternative is shipping a pipeline where one bad frame can
break SM permanently.  Not viable for production.

### Two more secondary findings (P1)

- **Bowler stats-graphic misread as bowler-change.**  At F619 a
  Yuzvendra Chahal IPL career graphic appeared (Chahal hadn't been
  introduced as a bowler yet).  The pipeline absorbed
  "bowl:Yuzvendra Chahal" from the graphic.  When Chahal *was*
  introduced ~1 over later, the change had already been (mis)applied
  and obscured.
- **Pass-2 enrichment blocks frame capture for ~4–5 min on startup.**
  Today's Pass-2 enrichment hit a real timeout (~4:30) and blocked
  the entire startup.  We missed the toss → opening over.  Captured
  as P1 with a clear non-blocking-async fix.

---

## 4. What we know now that we didn't yesterday

1. **V5's STEP-1 example slot is the dominant control surface, but
   slot-quantity matters too.**  Yesterday: "the closeup example
   creates the phase bias."  Today: "with three examples, Scout's
   default falls toward whichever STEP-1 examples it finds easiest
   to match — `closeup` and `graphic` — and `bowlers_end` rate
   declines monotonically through a session."  This is a stronger
   claim than yesterday: examples don't just fix specific failures,
   they **reshape the global distribution**.

2. **`side_on` is unreachable as a STEP-1 non-example.**  Yesterday's
   V5 added `graphic` as the third example; we predicted side_on
   would emerge once the wide-elevated alias chain was active.
   It didn't.  The prompt mechanism today appears to require
   "must be an example" for a category to be reliably emitted.
   `side_on` will need to become a fourth example or be removed
   from the taxonomy.

3. **Pipeline downstream has a recovery deadlock that survives an
   innings boundary.**  This is a structural fragility, not a
   per-frame bug.  Three independent guards, each reasonable, with
   no consensus-recovery override.  This needs to be the next
   workstream (or fold it into V6 prep).

4. **Commentary is robust to SM corruption.**  The wire/storyteller
   stack reads broadcast strips directly and produced high-quality
   output even while SM was 100+ runs / 7 wickets behind reality.
   This is a credit to the broadcast-grounded design choice — and
   means commentary quality is *not* a blocker for shipping the
   live pipeline even before state-recovery is fixed.

---

## 5. Backlog deltas (today)

New P0:
- `P0: SCORER doesn't enforce active-batter invariants
   (resurrects dismissed batters)`
- `P0: State-recovery deadlock — three guards compound to prevent
   recovery from corrupted SM state`

New P1:
- `P1: Bowler stats graphic misread as bowler-change`
- `P1: Scout never emits side_on (V5 third-example canary failing)`
- `P1: Pass-2 enrichment blocks frame capture on startup (~4–5 min)`

New P2:
- `P2: Pass-2 enrichment retry/timeout policy`
- `P2: WS-PROJECTION-GAP — striker / non_striker null in payload`

Updated:
- `P1: Phase regression from V5 multi-example prompt` — live
  confirmation appended (24.0% delivery-context vs V0 ~40%).
- `P1: Bowler-change pickup latency` — extended live evidence.

---

## 6. Recommended next session order

Re-ordered so structural fragility is fixed *before* iterating on
prompt quality (prompt iteration on a fragile pipeline produces
variable results — fix fragility first).

1. **P0-A active-batter invariants** (30–60 min).  Highest-leverage
   single fix.  Two assertions on every SM merge:
   `len(active_batters) <= 2` and `active_batters ∩ dismissed_batters == ∅`.
   Catches resurrection-class regressions structurally.

2. **P0-B squad-status patch** (~20 min, smallest piece of P0-B).
   Auto-dismiss-replacement path must set the replacing player's
   `squad[player].status = 'batting'`.  Unblocks WS-SCRUB
   specifically and breaks one leg of the deadlock independently.

3. **V5 production precision evaluation** (30–45 min).  Sample
   20–30 frames from today's run where V5 emitted `bowlers_end`,
   apply the rubric, compute precision.  Determines whether V6
   work is needed at all.

4. **P0-B consensus-recovery override** (2–3 h).  The
   architectural fix for the deadlock.  Bigger piece but highest
   leverage on structural fragility — turns "one bad frame
   breaks SM permanently" into "N consistent good frames force
   recovery".  See section 3 P0-B for detailed mechanism.

5. **P1 Pass-2 enrichment async** (30–45 min).  Recovers the lost
   first-4-overs window every fresh-team-pairing session.

6. **V5 → V6 iteration** — *contingent on step 3*.  Skip if V5
   production precision is acceptable.  If V5 has misclassification
   patterns, candidate variants:
   - `side_on` as fourth STEP-1 example (if precision eval shows
     wide-elevated shots are being misabsorbed by `bowlers_end`)
   - phase-regression mitigation (if the 24% delivery-context rate
     translates to bad downstream consequences — DWR window quality
     evaluation needed first)

Steps 1–3 are quick wins (~2 h total).  Step 4 is the big one.
Step 5 is bounded.  Step 6 is contingent and may not be needed.

This sequence gets the pipeline to "structurally robust to bad
frames" before iterating on prompt quality.
