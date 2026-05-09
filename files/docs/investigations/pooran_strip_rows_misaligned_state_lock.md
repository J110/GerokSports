# Pooran STRIP-ROWS-MISALIGNED State-Lock Cascade (F493–F562)

**Match:** MI vs LSG, 2026-05-04 (innings 1, LSG batting)
**Log:** `logs/pipeline-2026-05-04-1924-.log`
**Trace:** `logs/trace/b0cdc9f9.jsonl`
**Guard:** `files/test_pipeline.py:3426-3478` (`apply_comparison_strip_batter_row_delta_guard`)
**Call site:** `files/test_pipeline.py:8181-8186`
**Total Pooran firings:** 17 across F493–F562 (~5 min wall clock)
**Status:** Investigation only — no fix shipped.

---

## §1 What the user observed

Pooran came in at F302 (Markram dismissed). The card progressed
`0(0) → 1(1) [F304] → 1(6) [F347] → 1(8) [F393]`, then froze. From
F493 onward, every live strip read shows Pooran at 22+, but the card
stays at 1(8) and the score-manager state freezes at `65-1 (4.4)` for
the entire window — even though the broadcast is at `71-1 (4.5)`,
later `74-?`, `~80-?`, etc. The guard fires 17 times for Pooran (plus
2 Marsh row-rejections at F497, F537).

---

## §2 Phase A — guard mechanics

### §2.1 Guard body

`apply_comparison_strip_batter_row_delta_guard` (test_pipeline.py:3426).
For each `extracted["batters"]` row:

1. Resolve name → look up `scoreboard.batting_card[resolved]`.
2. If `card.balls > 0` (row is *confirmed*) and
   `abs(card.runs - strip.runs) > 20`, call
   `record_state_recovery_guard("batter_row_rejected", …)`,
   emit `[STRIP-ROWS-MISALIGNED]`, `extracted.pop("batters", None)`,
   return `True`.

The log message claims `preserved=score,match_overs,bowler`. **This
claim is false in the current call site** — see §2.2.

### §2.2 Call site — the actual cascade trigger

```python
# test_pipeline.py:8181-8186
elif apply_comparison_strip_batter_row_delta_guard(
        extracted, scoreboard, batting_team,
        frame_count=frame_count,
        record_state_recovery_guard=_record_state_recovery_guard):
    _frame_poisoned = True
    _poison_non_graphic = True
```

The guard pops `batters` from the local extract dict. The caller then
flips `_frame_poisoned = True` for the **entire frame**, which
downstream blocks the score / overs / bowler commit too. The
log-string promise of `preserved=score,match_overs,bowler` is
aspirational, not enforced.

Concrete proof at F502 (logs line 6500): scout sees
`STRIP: LSG 71-1 (4.5) … M Marsh 33(18) | Pooran 22(7)`,
`ext_score=71-1(4.5)`, but `scorer_changes=['FRAME_POISONED:71']` and
`AFTER_score=65-1(4.4)` — the new score is parsed, flagged
poisoned, never committed. Same pattern at F503, F504, F531–F562.

### §2.3 Compare to Batch G (overlay-lockout-breakout)

`_OVERLAY_LOCKOUT_BREAKOUT_K = 3` (line 3294) governs the
*active-batting* prefilter `_detect_overlay_via_active_batting`
(line 3384). Its state `_overlay_lockout_state` keys on
`(strip_pair, active_pair)`; after K=3 identical consecutive
rejections it returns `False` (no pop). **No equivalent breakout
exists for `apply_comparison_strip_batter_row_delta_guard`.** Once
the runs-delta guard latches, nothing in the current code path resets
it.

---

## §3 Phase B — why no recovery

### §3.1 Frame-by-frame ledger of the cascade window

| Frame | Strip score | Strip Marsh | Strip Pooran | Strip bowler | Card BEFORE | Guard hit | row_pair | Δ | Card AFTER | After score |
|-------|-------------|-------------|--------------|--------------|-------------|-----------|----------|---|------------|-------------|
| F493 | LSG 71-1 (4.5) | 33(18) | 22(7) | null | 1(8), 65-1(4.4) | ✓ | Pooran | 21 | 1(8) | 65-1(4.4) |
| F497 | null 49-3 (null) | *11(9) | 33(22) | Coulter-Nile 1-9 | 1(8), 65-1(4.4) | ✓ | Marsh | 22 | 1(8) | 65-1(4.4) |
| F502 | LSG 71-1 (4.5) | 33(18) | 22(7) | null | 1(8), 65-1(4.4) | ✓ | Pooran | 21 | 1(8) | 65-1(4.4) |
| F503 | LSG 71-1 (5) | 33(18) | 22(8) | Jacks 0(1) | 1(8), 65-1(4.4) | ✓ | Pooran | 21 | 1(8) | 65-1(4.4) |
| F504 | LSG 71-1 (5) | 33(18) | 22(8) | null | 1(8), 65-1(4.4) | ✓ | Pooran | 21 | 1(8) | 65-1(4.4) |
| F531 | live | 33(18) | 22(7-8) | — | 1(8), 65-1(4.4) | ✓ | Pooran | 21 | 1(8) | 65-1(4.4) |
| F532–F536 | live | 33(18) | 22 | — | same | ✓ ×5 | Pooran | 21 | unchanged | unchanged |
| F537 | (overlay) | 0 | — | — | same | ✓ | Marsh | 33 | unchanged | unchanged |
| F540 | live | 33(18) | 22 | — | same | ✓ | Pooran | 21 | unchanged | unchanged |
| F543 | live | — | 22 | — | same | ✓ | Pooran | 21 | unchanged | unchanged |
| F544 | overlay (`kph`) | — | — | — | same | sentinel | — | — | unchanged | unchanged |
| F545 | live | — | 22 | — | same | ✓ | Pooran | 21 | unchanged | unchanged |
| F556 | overlay (` > `) | — | — | — | same | sentinel | — | — | unchanged | unchanged |
| F557 | live | — | 32 | — | same | ✓ | Pooran | 31 | unchanged | unchanged |
| F560 | live | — | 48 | — | same | ✓ | Pooran | 47 | unchanged | unchanged |
| F562 | live | — | 32 | — | same | ✓ | Pooran | 31 | unchanged | unchanged |

The cascade is monotone: 17 Pooran firings. Strip runs grow with the
real innings (22 → 32 → 48). Card never moves.

### §3.2 Why no breakout

Three independent properties combine to lock the state:

1. **No K-consecutive breakout per row_pair.** The runs-delta guard
   has zero memory across frames. F503 looks identical to F493 looks
   identical to F540 — same `(row_pair=Pooran, strip_runs=22,
   card_runs=1)` tuple — but the guard does not count repetitions.
2. **Whole-frame poisoning.** Even when only `batters` is popped, the
   call site marks `_frame_poisoned=True`, which blocks the
   independent `score/match_overs/bowler` commits. So the score-
   manager view stays at `65-1 (4.4)`, never advancing past the last
   pre-lock commit. This is the deepest root cause: the rest of the
   pipeline's recovery mechanisms (over-advance heuristics,
   partnership re-anchoring, score-arithmetic gates) all read from a
   frozen score and therefore never get a chance to reconcile.
3. **No use of cross-row coherence.** At F493, Marsh's strip row
   `33(18)` matches the card row `33(18)` *exactly*. Same at F502,
   F503, F504. A strip where one row is identical to the card and the
   other diverges by 21 runs is overwhelmingly more likely a *stale
   card* than a *broadcast comparison overlay*. (Comparison overlays
   render entirely different stats — see existing
   `strip_rows_misaligned_diagnosis.md` §3.) The guard ignores this
   signal and treats each row in isolation.

The user's hypothesis about "Marsh-rejection resetting a Pooran
counter" cannot apply because the counter doesn't exist in the first
place. If a counter existed and were keyed on `(strip_pair,
active_pair)` à la Batch G, then yes — F497 (Marsh row rejected at a
different score) would reset it. The fix has to be per-row_pair, not
per-pair.

### §3.3 How Pooran got stuck at 1(8) in the first place

Read the F302–F390 prelude. Pooran admitted at F302 with `0(0)`
(strip OCR had him at `POORAN 0(0)` while Markram was simultaneously
dismissed). Confirmed runs reached 1 by F304. Between F304 and F390,
the strip kept showing low values (e.g. F390 has strip `Pooran 2(2)`,
log line 3851 — "balls regression 6→2 rejected (>2 balls backward)
— dropping runs=2 too"). So the `_balls_regression_guard` was busy
rejecting upstream OCR drift, holding Pooran at 1(6)→1(8) for ~50
frames during a flurry of overlay/replay activity. By F493, the
broadcast strip caught up to the live state (Pooran ~22) but the card
was now too far behind, so the runs-delta guard latched. Two
independent guards combined: the regression guard prevented healthy
small updates from arriving, and the runs-delta guard then refused
the eventual large catch-up.

### §3.4 Score-manager team-name confusion (orthogonal)

The `STATE:` line says `RCB 65-1 (4.4)` while `batting_team=Lucknow
Super Giants`. The `RCB` token is wrong but consistent across all
frozen frames — appears to be a stale value carried in
`scoreboard.team_short` or similar from match init. **Out of scope
for this memo.** Note for follow-up: investigate why
`STATE:` renders the wrong team-short while `batting_team` is
correct.

---

## §4 Phase C — fix recommendations

Three independent changes; each addresses a distinct property of
§3.2. They stack cleanly. Listed in order of impact.

### §4.1 Stop poisoning score/overs/bowler when only batters were popped

**File:** `files/test_pipeline.py:8181-8186`.

```python
elif apply_comparison_strip_batter_row_delta_guard(
        extracted, scoreboard, batting_team,
        frame_count=frame_count,
        record_state_recovery_guard=_record_state_recovery_guard):
    _frame_poisoned = True          # ← remove
    _poison_non_graphic = True      # ← remove
```

Make the call site honour the guard's stated contract: pop only
`batters`, let `score`, `match_overs`, `bowler` commit. (Verify no
downstream reader assumes `batters` and the other fields commit
atomically; spot-checks suggest they don't, since the prior
`apply_strip_overlay_prefilters` branch *does* preserve the same
fields when its pop-batters path runs — but it also sets
`_frame_poisoned=True`, so consistency would prefer this fix
**also extend** to the prefilter path. Likely needs a small tri-state
distinction: `frame_poisoned_full` vs `frame_poisoned_batters_only`.)

**Why this matters most:** even without any breakout logic, allowing
score/overs to advance lets the partnership-anchor and score-delta
heuristics independently sense the gap. The current implementation
freezes *every* commit channel on a single-row pop, which is far more
than the guard claims to do.

**Risk:** if the guard mis-fires on a real comparison overlay where
the score in the strip is *also* wrong, the wrong score will commit.
Mitigation: the existing `[POISONED] score X vs tracker Y delta=…`
guard (a different gate) still runs and will block large score
deltas; that guard is what catches the genuine overlays from the
prior CSK-MI memo (e.g. F45 there had delta=-71).

### §4.2 Add per-row_pair K-consecutive breakout

**File:** `files/test_pipeline.py` — alongside `_overlay_lockout_state`.

```python
_ROW_DELTA_LOCKOUT_BREAKOUT_K = 3
_row_delta_lockout_state: dict = {}   # {resolved_name: {"key": (s_runs, c_runs), "consecutive": int}}

def reset_row_delta_lockout_state(name: str | None = None) -> None:
    if name is None:
        _row_delta_lockout_state.clear()
    else:
        _row_delta_lockout_state.pop(name, None)
```

Inside `apply_comparison_strip_batter_row_delta_guard` after computing
`row_delta`, before the pop: track `(strip_runs, card_runs)` keyed by
`_gb_resolved`. Increment on identical key, reset on change (same
batter, different numbers) or different batter row appearing instead.
At `consecutive >= K`, log `[ROW-DELTA-LOCKOUT-BREAKOUT]`, do NOT pop,
return `False` so the strip row passes through and the card updates.
On any successful (non-rejected) row update for that name, clear that
batter's entry.

Critical: state is per-resolved-name, so a Marsh rejection does **not**
reset Pooran's counter. The user's worry from Phase B is real for any
shared-counter design and must be avoided here.

**Risk:** a real comparison overlay that happens to render the same
wrong runs three frames in a row (rare — overlays usually rotate
through career stats / matchups / venue history that vary frame to
frame). To bound this, gate the breakout on a sanity check: only
breakout if the OTHER batter's strip row matches the card within ≤2
runs (i.e. cross-row coherence). This narrows the breakout to "one row
stale, the rest live" and disqualifies the overlay-substitution case
where every row is wrong.

### §4.3 Tier the threshold by delta magnitude

The user proposed `large-delta poison (60+) vs incremental delta
(20-50)`. The data supports the split:

- **Δ ≤ ~50:** consistent with stale-card lockout, especially when
  the other row matches. Examples: F493 Δ=21, F557 Δ=31, F560 Δ=47.
- **Δ ≥ ~60:** consistent with overlay substitution. Examples from
  the existing CSK-MI memo: F438 Δ=131 (Hardik 142 vs 11), F841 Δ=83
  (Samson 84 vs 1). For Pooran here, no firing exceeds Δ=47.

Suggestion: keep the existing >20 threshold for the `pop batters`
path, but **route Δ>60 through a stricter `_frame_poisoned=True` path
and Δ∈(20,60] through a `pop batters only` path** (which §4.1 makes
distinct). This formalises §4.1 with a magnitude gate so genuine
high-Δ overlays still poison the whole frame and we lose nothing on
that side.

### §4.4 Why not address the upstream regression guard

The reason Pooran got behind in the first place (§3.3) is the balls-
regression rejections during F305–F390. Loosening that guard is
strictly worse than what we have — it would let in the genuine OCR
drift we caught (e.g. Pooran 2(2) when he was actually at 1(6)). The
right place to break the lockout is the runs-delta guard at
catch-up time, not the regression guard at slow-update time.

---

## §5 Open questions / follow-ups (not in scope)

- Why does `STATE:` render team_short=`RCB` while `batting_team=LSG`?
  Likely a stale read on `scoreboard.team_short` carried from match
  init. Separate ticket.
- The `_apply_overlay_prefilters` path also sets
  `_frame_poisoned=True` — should that also be downgraded for the
  pop-batters-only case? Likely yes, but verify against the prefilter
  fixture corpus before changing.
- Validate the §4.2 cross-row coherence check against the 32-frame
  corpus in `strip_rows_misaligned_diagnosis.md` to confirm it
  doesn't allow any of those genuine-overlay frames through.
- Trace-rule update: add a P-rule that flags a `[STRIP-ROWS-
  MISALIGNED]` count exceeding K for the same row_pair across a
  rolling window — this would have surfaced the Pooran cascade in
  near real-time at K=4.

---

## §6 Telemetry pointers

- 17 `[STRIP-ROWS-MISALIGNED]` events against `row_pair=Nicholas Pooran`
  in `logs/pipeline-2026-05-04-1924-.log`.
- 2 events against `Mitchell Marsh` (F497, F537) — these correspond
  to genuine overlay frames (different score, different bowler) and
  are **correct rejections**.
- 2 sentinel-prefilter hits (F544 `' kph'`, F556 `' > '`) prove the
  pre-filter additions from `strip_rows_misaligned_diagnosis.md` §5
  are landing — but they only fire on the overlay frames in this
  cascade, not on the live frames where the lock is happening.
- Frame-poisoning evidence: `scorer_changes=['FRAME_POISONED:71']`
  on F502 (and analogues on F503/F504/F531+) where the strip-OCR
  score is parsed, flagged, and discarded.
