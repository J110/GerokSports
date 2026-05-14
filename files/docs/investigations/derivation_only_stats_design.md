# Derivation-only stats — bowler + batter (2026-05-14)

Architectural spec for moving `bowling_card` and `batting_card` stat
fields from **strip-driven** to **event-driven derivation**. Vision is
demoted to identity detection (names) and event detection; numerical
stats are computed from events, not parsed from the broadcast strip.

Status: **spec only** — no production edits. Implementation Phase A1+A2
is planned post-match (recommended) or as a separate development cycle.

Motivation: the 2026-05-14 DC-vs-KKR validation session surfaced four
cascading mis-attribution incidents at F438 / F381 / F344-F372 / F232
which all traced to **strip values overriding event-derived state**:

- F438 `VAIBHAV 4-1 (1.2)` column-scrambled wickets crediting Arora.
- F381 wicket committed at score=49/1 with `current_bowler=None`
  (between-overs gap) — no bowler got the event credit, so the next
  strip read of any bowler row backfilled the wicket spuriously.
- F344-F372 striker-tracker oscillation incremented both batters'
  `balls_faced` simultaneously, inflating Pathum 18→32.
- F232 corrupted strip read accepted a `(2.5) → (4)` overs jump as
  multi-ball, then poisoned all downstream comparisons.

Commits `adb587d` and `8c1b33a` added defense-in-depth (bowler-override
consensus, attribution freeze, junk-row reject, sum invariant) but the
underlying competition between strip and event paths remains.

---

## Part 1 — current state survey

### Bowling-card mutation sites

`files/eyes/scoreboard.py`:

| Line | Site | Source | Notes |
|---|---|---|---|
| 1597 | `_mirror_team_delta_to_bowler` runs+= | derived (team-score delta) | BOWLER-AUTO; gated by scout-gap, over-boundary, freeze (`adb587d`) |
| 1723 | `_apply_bowler_delta` runs+= | event (via SM `_accumulate_stats_from_event`) | The intended derivation path |
| 1767 | `_apply_bowler_delta` overs= | event | Same |
| 2807-2808 | `_apply_bowler_delta` runs += / wickets += | event | Same |
| 3308-3312 | `update_bowler` overs/runs/wickets = | strip (extracted.bowler.*) | `_bowler_regress_pending` exit |
| 3373 | `update_bowler` runs = | strip | BOWLER-SPELL-SEED bypass |
| 3383 | `update_bowler` runs = (tracker-confirmed) | strip | normal consensus path |
| 3387 | `update_bowler` wickets = | strip | BOWLER-SPELL-SEED bypass |
| 3397 | `update_bowler` wickets = (tracker-confirmed) | strip | normal consensus, now gated by Changes F+G (`8c1b33a`) |
| 3412, 3424 | `update_bowler` overs = | strip | normal consensus |
| 3428 | `update_bowler` maidens = | strip | direct assignment |
| 3673-3676 | bowler bootstrap seed runs/wickets/overs | strip | first-frame seed |

`files/score_manager.py`:

| Line | Site | Source |
|---|---|---|
| 3438-3520 | `_accumulate_stats_from_event` | event → calls `update_bowler(runs_delta=…, wickets_delta=…)` |

### Batting-card mutation sites

`files/eyes/scoreboard.py`:

| Line | Site | Source |
|---|---|---|
| 2133-2134 | `update_batter` runs=None / balls=None (clobber) | guard reset |
| 2202-2203 | `update_batter` runs=0 / balls=0 | new-batter init |
| 2376-2381 | `update_batter` runs_regression_value / balls | strip (runs-monotonic guard release) |
| 2442 | `update_batter` balls = `int(new_b)` | strip |
| 2455 | `update_batter` runs = `eff_r` (tracker-confirmed) | strip |
| 2529 | `update_batter` balls = `eff_b` (tracker-confirmed) | strip — now gated by Changes H+I (`8c1b33a`) |
| 2562 | `update_batter` balls = old_b (runs-deferred sync) | strip |
| 2587, 2589 | `update_batter` fours / sixes = | strip |
| 2771-2774 | `_apply_batter_delta` runs/balls/fours/sixes += | event |

`files/score_manager.py`:

| Line | Site | Source |
|---|---|---|
| 3505-3511 | `_accumulate_stats_from_event` (legal balls) | event → `update_batter(runs_delta=…, balls_delta=…, fours_delta=…, sixes_delta=…)` |
| 3461-3466 | `_accumulate_stats_from_event` (WICKET event) | event |

### Trackers (per HANDOFF + code inspection)

| Tracker | File | LOCK trigger | UNLOCK trigger | Half-life |
|---|---|---|---|---|
| `bowler_tracker` | test_pipeline.py:6234 | accumulated weight reaches FIRM/LOCKED on VLM name reads | `unlock_and_reset()` on `_bowler_change_signal` (over-end) | per ConfidenceTracker default |
| `striker_tracker` | test_pipeline.py | weight on VLM `*`/`>` indicator + balls-delta cross-match | dismissal event for the locked name | per default |
| `non_striker_tracker` | test_pipeline.py | as above | dismissal of locked name | per default |
| `batting_team_tracker` | test_pipeline.py | accumulated team-token reads | innings-2 transition | per default |

`bowling_card` / `batting_card` persist across spells: a bowler returning for a later over re-uses the same entry. ✓

### Event reliability

Ball events fire from `score_manager._infer_event` on each `_handle_warm` call, classifying the diff (score / wickets / overs) into:

- `DOT`, `FOUR`, `SIX`, `RUNS` (1/2/3/5)
- `WICKET` (with type + bowler_attributable flag)
- `WIDE`, `NO_BALL`, `EXTRA` (pending until resolution)
- `MULTI_BALL` (decomposed; events suppressed for batter/bowler stat
  attribution per `_accumulate_stats_from_event`)

Known under-firing modes:

- `MULTI_BALL` gaps skip batter/bowler attribution entirely (intentional — the gap by definition lacks per-ball striker info).
- Wickets in `current_bowler=None` window (between-overs gap) — the wicket event commits to team wickets but `_accumulate_stats_from_event` skips bowler attribution because `bowler_name=None`. **This is the F381 incident's gap**: a backfill mechanism is needed.
- `EXTRA` events that never get resolved leave the batter portion uncredited (acknowledged in `_accumulate_stats_from_event` docstring).

---

## Part 2 — design spec

### Architecture (unified for bowler + batter)

**DETECTION (vision only, ConfidenceTracker-mediated):**

- `bowler_tracker` — name of the bowler delivering this over
- `striker_tracker` — name of the batter facing the ball
- `non_striker_tracker` — name of the non-striker
- `batting_team_tracker` — which team is batting
- Dismissal event (which batter is out, how, by which bowler)
- Run-count event (score-delta interpretation: dot / 1-6 runs / wide+N / nb+N)
- Over-rollover event (team_overs integer crossing)
- Boundary classification (4 vs 6) from broadcast graphic / scout

**DERIVATION (event-driven, no vision for stats):**

Bowler (when `bowler_tracker.state == LOCKED` on name X):

```
on LEGAL_BALL:           bowling_card[X].balls_bowled += 1
on OVER_ROLLOVER(X):     bowling_card[X].overs_completed += 1
                          (computed: balls_bowled // 6)
on RUN_EVENT(runs_total): bowling_card[X].runs += runs_total
on WICKET(bowler-attributable): bowling_card[X].wickets += 1
on MAIDEN_COMPLETE(X):   bowling_card[X].maidens += 1
                          (over closed with 0 runs scored)
```

Batter (when `striker_tracker.state == LOCKED` on name Y):

```
on LEGAL_BALL(faced):     batting_card[Y].balls_faced += 1
on RUN_EVENT(off_bat):    batting_card[Y].runs += runs_off_bat
on FOUR boundary:         batting_card[Y].fours += 1
on SIX boundary:          batting_card[Y].sixes += 1
on WICKET(Y dismissed):   batting_card[Y].status = "out"
                          batting_card[Y].dismissal_overs = current_overs
                          batting_card[Y].dismissal_runs = current_runs
                          batting_card[Y].dismissal_by = bowler_name
                          batting_card[Y].dismissal_type = wicket_type
```

Non-striker: derivation reduced to:
- No `balls_faced` increment (doesn't face balls)
- Runs only from **byes / leg-byes** which credit the *team* extras, not the batter — non-striker's `runs` field stays unchanged on byes/lbs
- On odd-runs delivery: swap with striker_tracker, both tracker LOCKs preserved

### Lifecycle

**Bowler:**

1. Over-end signal (team_overs crosses integer) → `bowler_tracker.unlock_and_reset()`
2. New over → bowler_tracker accumulates consensus from VLM name reads
3. FIRM/LOCKED on name X → `bowling_card.setdefault(X, blank_bowler_entry())`
4. Events during over → derive into `bowling_card[X]`
5. Over-end → snapshot card, loop to step 1

Consecutive-over constraint: when a new over's bowler_tracker is about to LOCK on name X, reject if X == previous_over_bowler. Bowler rotation is a cricket rule; same bowler bowling two consecutive overs is impossible. Force tracker to wait for a different name.

**Batter:**

1. Wicket on striker → `striker_tracker.unlock_and_reset()`
2. New batter walks out → striker_tracker accumulates consensus
3. FIRM/LOCKED on name Y → `batting_card.setdefault(Y, blank_batter_entry())`
4. Events while LOCKED → derive into `batting_card[Y]`
5. Odd-run delivery → swap_with(non_striker_tracker), both stay LOCKED
6. Dismissal of Y → loop to step 1

### Hard invariants (enforced; trip a trace tag + suppress if violated)

1. Trackers cannot change identity mid-over (bowler) or mid-delivery (batter)
2. `bowling_card[name].{runs,balls,wickets}` are strictly monotonic
3. `batting_card[name].{runs,balls_faced,fours,sixes}` are strictly monotonic
4. No two consecutive overs have the same bowler (cricket rule)
5. `sum(batting_card[*].balls_faced) <= team_legal_balls` (already enforced by `8c1b33a`'s `BATTER-BALLS-INVARIANT-FREEZE`)
6. `sum(bowling_card[*].balls_bowled) == team_legal_balls` (new — to add)
7. `sum(bowling_card[*].runs) == innings_runs - byes - leg_byes` (new — to add)
8. `bowling_card[X].wickets` is derived only from `_add_fow` events crediting bowler=X (already enforced by `8c1b33a`'s `BOWLER-WICKET-DELTA-SUPPRESSED-NO-EVENT`)

### What gets deleted

**Bowler — strip-driven sites that compete with derivation:**

- `scoreboard.py:3308-3312` — `update_bowler` regress-pending exit accepting strip values
- `scoreboard.py:3373, 3383, 3387, 3397, 3412, 3424, 3428` — strip-driven entry assignments inside `update_bowler` (the `runs=`/`wickets=`/`overs=`/`maidens=` kwargs path)
- `scoreboard.py:3673-3676` — bootstrap seed from strip
- `_mirror_team_delta_to_bowler` (BOWLER-AUTO) — line 1597, 1723, 1767. This is *derivation* (team-score delta) but it's a redundant path competing with `_accumulate_stats_from_event`. **Deletion candidate; alternative: keep as fallback when `score_manager` event hasn't fired yet on this frame.**

The `update_bowler(name, frame, vision_desc)` signature is preserved for tracker integration (current_bowler flip, override consensus); only the stat fields (`overs=`, `runs=`, `wickets=`, `maidens=`) cease to write to the card.

**Batter — strip-driven sites:**

- `scoreboard.py:2287-2322` — runs-monotonic guard (commit `f043c5d`) — the entire "strip wins if monotonic >= derived" gate
- `scoreboard.py:2376-2381` — regression value/balls write
- `scoreboard.py:2442` — `entry["balls"] = int(new_b)` direct path
- `scoreboard.py:2455` — `entry["runs"] = eff_r` from tracker
- `scoreboard.py:2529` — `entry["balls"] = eff_b` from tracker
- `scoreboard.py:2562` — runs-deferred balls revert
- `scoreboard.py:2587, 2589` — fours/sixes direct write

### What gets preserved (cross-validation, not source)

- Strip values logged as `observed_strip_bowler` / `observed_strip_batters` in the trace record per frame
- Divergence monitor: when `abs(derived - observed_strip) / max(observed_strip, 1) > N%` (suggest N=20 for runs, N=2 absolute for wickets), emit `DERIVATION-STRIP-DIVERGENCE` trace tag for post-match audit
- Strip never overrides derived; only flags potential event-detection misses

### Defense-in-depth (preserved from current commits)

These guards remain even when strip-driven writes are removed — they catch the event path's own under-firing / misfiring:

- `adb587d` BOWLER-OVERRIDE consensus (2-frame floor) + attribution-freeze
- `8c1b33a` BOWLER-ROW-JUNK-REJECT (physics: Δwickets ≤ 1)
- `8c1b33a` BOWLER-WICKET-DELTA-SUPPRESSED-NO-EVENT (Change G — already a derivation guard)
- `8c1b33a` BATTER-BALLS-INVARIANT-FREEZE (sum cap)
- `8c1b33a` BATTER-BALLS-DOUBLE-INCREMENT-FRAME (one striker per ball)

Once the derivation-only architecture is in place, several of these should fire effectively never — their continued presence is monitoring (count firings; if >0 in a clean session, investigate event-detection misses).

---

## Part 3 — implementation plan

### Phase A1 — Bowler derivation-only (commit 1, ~45 min)

**Scope:** Delete strip-driven `bowling_card` writes; rely on `_accumulate_stats_from_event` + `_apply_bowler_delta`.

**Diff sketch:**

1. `scoreboard.update_bowler` — split into two methods:
   - `update_bowler_identity(name, frame, vision_desc)` — handles tracker, override, must_change, XI-reject, dismissal-resurrection. Returns the resolved name (or None on reject). Does NOT touch stats.
   - `update_bowler_stats(name, runs_delta, balls_delta, wickets_delta, frame)` — existing `_apply_bowler_delta` path. Sole writer to `bowling_card[name].{runs, balls, wickets}`.

2. Callers in `test_pipeline.py` that pass `overs=`/`runs=`/`wickets=` from strip: change to identity-only call. The strip values still flow into `observed_strip_*` for the divergence monitor.

3. `_mirror_team_delta_to_bowler`: delete (or keep as a final-resort no-op when `_accumulate_stats_from_event` hasn't fired in N frames).

4. Add `_add_fow` → emit a synthetic WICKET event that `_accumulate_stats_from_event` will pick up, ensuring bowler credit when the dismissal-event path runs with `current_bowler=None` (F381 gap).

5. Add consecutive-over-bowler rejection in `update_bowler_identity` (refuse to LOCK same name twice in a row).

6. Add bowling-card-balls-sum invariant trace tag at over-rollover.

**Risk areas:**

- Cold-start: first VLM read of a bowler currently uses the strip values to seed `bowling_card[X]` figures. Move seed to identity-only; figures start at 0 and accumulate from events. **Mid-match attach** (pipeline boot mid-innings) becomes a separate case — the strip values are the only source of historical figures. Solution: keep strip-driven seeding ONLY for the very first frame after attach (one-shot), then derivation-only thereafter.

### Phase A2 — Batter derivation-only (commit 2, ~45 min)

**Scope:** Mirror Phase A1 for `batting_card`.

**Diff sketch:**

1. `scoreboard.update_batter` — split identity vs stats:
   - `update_batter_identity` — name resolution, opposition-rejection, dismissed-batter guard
   - `update_batter_stats` — existing `_apply_batter_delta` path

2. Callers that pass strip-derived `runs=`/`balls=`/`fours=`/`sixes=`: change to identity-only.

3. Delete the `f043c5d` runs-monotonic strip-wins gate (`scoreboard.py:2287-2322`).

4. Same one-shot mid-match-attach exception as Phase A1.

5. Wire boundary classification: `_accumulate_stats_from_event` already increments `fours_delta` / `sixes_delta` based on event `type`. Verify the upstream `_infer_event` classifies FOUR/SIX correctly from the broadcast graphic signal (not from strip's 4s/6s columns).

6. Wire wicket → `status="out"` via the event path, removing strip-driven status mutations.

**Risk areas:**

- Strike rotation: `_accumulate_stats_from_event` runs BEFORE strike rotation per the existing comment. Verify the swap_with logic in `striker_tracker` still fires correctly with derivation-only ingestion.
- Non-striker on bye/leg-bye: byes increment team extras and the over progresses, but neither batter scores. Confirm `_accumulate_stats_from_event` for `BYE`/`LEG_BYE` event types (if they exist) — may need a new event type if currently lumped into `EXTRA`.

### Phase B — Validation (commit 3 OR shared with A2)

Replay `match_4621b9f8.mp4` from 10:40 (covers the F232 / F381 / F438 incidents):

| Checkpoint | Expected |
|---|---|
| Overs 1-5 bowlers | `bowling_card[Roy]` overs=1.0/runs=7; `bowling_card[Arora]` overs=1.0/runs=10; `bowling_card[Narine]` overs=1.0; `bowling_card[Roy]` second over (over 3 in cricket terms — but this match Roy doesn't return); `bowling_card[Tyagi]` overs=1.0/wickets=1 |
| F438 column-scramble | `bowling_card[Arora].wickets` stays 0; `BOWLER-ROW-JUNK-REJECT` does NOT fire (strip path deleted) |
| F381 wicket credit | Tyagi credited via `_add_fow` → synthetic WICKET event → `bowling_card[Tyagi].wickets=1` even with `current_bowler=None` at commit moment |
| Pathum balls_faced at over 5 | matches broadcast (18 at 5.4 in the session log); NOT inflated to 32 |
| Sum invariants | `sum(bowling_card[*].balls_bowled) == team_legal_balls`; `sum(batting_card[*].balls_faced) <= team_legal_balls` |
| Divergence monitor | `DERIVATION-STRIP-DIVERGENCE` firings rare and traceable to event-detection gaps |

### Phase C — Post-match audit

Compare derived vs broadcast for every bowler+batter over the full 4621b9f8 innings:

- Identify systematic event-detection gaps (under-fires / mis-classifies)
- If divergence is broad: investigate `_infer_event` heuristics
- If divergence is narrow: tighten that specific path

---

## Recommendation

Spec is internally consistent. Implementation cost ~90 min (A1+A2) plus validation. Recommend deferring to a planned development cycle for these reasons:

1. The session's defense-in-depth commits (`adb587d`, `8c1b33a`) have already neutralised the worst symptoms — the user can run validation tonight with reasonable accuracy.
2. Phase A1/A2 deletes load-bearing code paths (the strip-driven gates have absorbed many edge cases over months). A clean derivation-only architecture must re-validate each gate's intent.
3. Mid-match-attach scenarios (resume from cache, re-enter cold-start) need extra design — the spec mentions the one-shot exception but the detail (which frame, which fields, how to reconcile with the consensus-gate state) is unspecified.

Decision point: ship Phase A1+A2 in a dedicated 2-3-hour session after the next match completes, with the recommendation to land each phase as a separate commit so bisection works if a regression slips through.

---

## Deferred items (post-match audit queue)

- Striker-tracker oscillation root cause (why both batters increment within a single frame — the symptom-level guard `8c1b33a` Change I masks but doesn't fix)
- Wicket-credit backfill at over-rollover: when wicket commits with `bowler=None`, defer attribution until the next over's bowler is identified, then synthesize a credit
- F232-class corrupted strip cold-start poisoning: junk-shape detection at the extractor layer (multi-null fields + low-confidence overs token)
- Striker indicator parsing on `PATHUM > N RANA` collapsed-row shape (deferred per investigation 9 — needs pixel-zoom audit first)
