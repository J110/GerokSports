# Innings 2 Run — Additional Issues Found in Log Forensics

**Companion to:** `2026_05_02_csk_vs_mi_innings2_post_mortem.md`
**Source:** `pipeline-2026-05-02-2049-csk-vs-mi-44th-match-ipl-2026-innings2.log`
**Purpose:** issues operator did not observe but log analysis reveals. Most are pre-existing weaknesses the operator's 12 issues didn't surface.

---

## A1 — STRIKER-COLLISION refused 125 times (HIGH FREQUENCY)

**The single most common warning in the run.** 125 firings.

**Distribution by victim:**
- 35× `non=Hardik Pandya — already striker`
- 33× `non=Naman Dhir — already striker`
- 32× `non=Krish Bhagat — already striker`
- 16× `non=Robin Minz — already striker`

**Root cause:** the strip was reporting batter slots in different orders across frames (sometimes Naman first, sometimes Hardik first). The pipeline's striker-assignment logic resolves both batters then checks for collision: "if I assign Hardik as non-striker, but he's already the striker, refuse."

The collision check is doing the right thing (refusing to set the same person as both). But the number of refusals (125) suggests the strip-reading is failing to correctly identify which batter has the asterisk (`*`) marker for striker.

**Why operator didn't see it:** state-machine recovers from the collision by keeping the previous striker. UI renders correctly because the eventual state is right.

**Class:** strip-OCR weakness in striker-marker detection. Pre-existing, not regression.

**Fix priority:** P18 (lower priority because no incorrect data leaks through). Long-term, OpenScout-triggered architecture would route around because spans don't depend on striker reading.

---

## A2 — STRIP-ROWS-MISALIGNED: 32 firings with phantom batter swap (NEW MAJOR ISSUE)

**Frequency:** 32 events.

**Pattern:** strip-OCR returned batter rows in WRONG ORDER, swapping Naman Dhir's stats with Hardik Pandya's stats.

**Concrete examples:**
- F11: `row_pair=Hardik Pandya strip_runs=45 card_runs=7` — strip showed Hardik=45 but tracker has Hardik=7
- F45: `row_pair=Naman Dhir strip_runs=21 card_runs=46` — strip showed Naman=21 but tracker has Naman=46
- F52: `row_pair=Hardik Pandya strip_runs=34 card_runs=8` — strip showed Hardik=34 but tracker has Hardik=8

**Root cause:** the broadcast strip occasionally shows the batter rows in unusual order (e.g., Hardik on top despite being non-striker). Pipeline detects misalignment via the row_delta (38 vs 25 vs 26 etc) and pops the misaligned data instead of using it.

**Why operator didn't see it:** the misalignment guard is working — bad data is rejected, not committed. But it means strip-OCR is being thrown out 32 times when it could have been used.

**Connection to A1:** The 32 STRIP-ROWS-MISALIGNED events likely correlate with the 125 STRIKER-COLLISION events. If the strip is mis-ordering batters, the striker assignment is also confused.

**Class:** broadcast-layout-specific issue. The IPL strip occasionally reverses batter order (possibly for "comparison" overlays during analytics).

**Fix priority:** P19. Either use a more robust striker-marker detection OR allow row-ordering to be consensus-resolved across frames (require 3 frames of consistent ordering before trusting it).

---

## A3 — Bowler card stuck for up to 99 frames (LATENCY-STUCK warnings)

**Frequency:** 45 events (`LATENCY-STUCK` + `LATENCY-HIGH` combined).

**Worst cases:**
- 99 frames stuck (Anshul Kamboj — that's ~8-10 minutes of bowler not visible)
- 96 frames stuck
- 94 frames stuck
- 93 frames stuck

**Distribution by which bowler "was last seen":**
- 15× was `Anshul Kamboj`
- 12× was `None` (cold-start)
- 5× was `Noor Ahmad`
- 3× was `Ramakrishna Ghosh`

**Root cause:** when a bowler ends their over and a new bowler comes in, the broadcast may not show the new bowler's stats clearly for several frames. Pipeline keeps the previous bowler in state until the new one is confirmed.

**Why operator didn't see it:** state recovers eventually. But during the stuck window, comm_bowler shows the WRONG (previous) bowler. Commentary lines and bowler stats during the gap are misattributed.

**Class:** strip-OCR weakness. The `LATENCY-STUCK` is observability — the gap is real and lasted up to ~10 minutes for one bowler.

**Fix priority:** P20. Hard-cap the "stuck" tolerance: after N frames (say 20 = ~2 minutes), force a "bowler unknown" state rather than continuing with stale assignment. Cleaner failure mode than misattributed commentary.

---

## A4 — Comparison strip overlay corrupting batters (COMPARISON STRIP guard fired 36 times)

**Frequency:** 36 firings of `[GUARD] X diff Y→Z — comparison strip for batting team`.

**What's happening:** broadcast occasionally overlays a "comparison strip" showing player career stats or season-best numbers next to current match stats. The strip-OCR reads BOTH and the pipeline detects the conflict via the diff threshold.

**Examples:**
- F11: `Hardik Pandya diff 7→45 — comparison strip` (Hardik has 7 in match, comparison strip shows 45 from his career best)
- F45: `Naman Dhir diff 46→21 — comparison strip` (Naman has 46 in match, comparison strip shows 21 from elsewhere)

**Why operator didn't see it:** the comparison-strip guard correctly rejects the bad reads. But 36 firings means the broadcast shows comparison overlays a LOT, and each time we lose a frame's worth of strip data.

**Class:** broadcast-overlay leak. Same family as recap-overlay (Issues 3, 4 in main post-mortem).

**Fix priority:** rolled into existing P3 (Lever 3 replay-inset detector) — that fix should also detect comparison overlays.

---

## A5 — Squad mismatches 145 times (mostly recap content + analytics)

**Frequency:** 145 "No match for" warnings.

**Top mismatches:**
- 33× `NEHAL BHAGAT` (not in match — fuzzy matched closest to `K BHAGAT` which IS Krish Bhagat in MI)
- 28× `DAVID` (not in either squad — David Warner? But not in this match)
- 11× `KARUN` (not in match — likely Karun Nair from analytics)
- 7× `NONSTRIKER` (not a player name — this is a strip artifact "the non-striker")
- 6× `YASHASVI JAISWAL` (not in match — Jaiswal is RR, this match is CSK vs MI)
- 6× `FABIAN COWDREY` (not in match — historical player)
- 5× `ARSHDEEP S` (not in match — Arshdeep Singh is PBKS)
- 4× `SAMSON GAIKWAD` (concatenation bug — combined two names)

**Root cause:** broadcast shows analytics/comparison overlays referencing OTHER players from other matches/teams. Pipeline correctly rejects them as "not in any squad" — but each rejection is computational waste and may correlate with phantom data leaking through.

`SAMSON GAIKWAD` is interesting — that's a SQL-injection-style row concatenation where the name parser merged two adjacent batter rows into one string. Probably 4 frames where the strip layout was particularly bad.

`NONSTRIKER` (7 firings) is a labeling artifact — the strip presumably showed a literal "Non-Striker:" label that got parsed as a player name.

**Why operator didn't see it:** rejections happen silently. Bad data doesn't reach state.

**Class:** strip-OCR weaknesses + cross-match analytics overlays.

**Fix priority:** P21 (cleanup). Add allowlist filtering: reject obvious non-names (e.g., NONSTRIKER, single-letter strings) before fuzzy match. Lower computation cost.

---

## A6 — BOWLER-STATS-GRAPHIC-GATE rejected 8 implausible bowler reads

**Frequency:** 8 events. Sample:
```
F56: [BOWLER-STATS-GRAPHIC-GATE] rejecting 'Noor Ahmad' - 
  reason=implausible_figures (overs=15.0 runs=None wickets=None)
```

**Pattern:** strip read showed Noor Ahmad bowling 15.0 overs in a T20 (max 4 per bowler). Pipeline rejected this as graphic-leak. Good.

**This is a PRE-EXISTING gate that's working.** Not a new issue, but adding to record because:
- Same gate pattern that's needed for P15 (bowler-overs vs team-overs sanity check)
- Confirms the architectural direction: these sanity gates work; we need more of them

**Class:** existing gate. Working correctly.

---

## A7 — BOWLER-BATTER-GATE stripped 20 events (data integrity)

**Frequency:** 20 events. 

**Pattern:** strip-OCR sometimes returns a bowler name that's actually a batter (or vice versa). Pipeline detects and strips.

**Examples:**
- F13: `bowler stripped — name='Hardik' resolved_batter='Hardik Pandya'` (Hardik is a batter, was being read as bowler)
- F52: `bowler stripped — name='S Dhiraj' resolved_batter='Naman Dhir'` (S Dhiraj isn't even a real player — was misread of Naman Dhir)
- F647: `bowler stripped — name='PATEL' resolved_batter=None complete_figures=True` (Patel — unclear which Patel; rejected for safety)

**Why operator didn't see it:** stripped silently. Means 20 frames where bowler info from strip wasn't trusted.

**Class:** strip-OCR weakness in role identification.

---

## A8 — Innings 2 cold-start window: 12+ minutes of phantom strip reads

**Evidence:** Between F647 (innings 2 transition at 21:31:42) and F864 (first real CSK score commit at 21:45:56), pipeline saw mostly:
```
STRIP: null 49-3 (8.1)    ← recap from old MI innings or projection
STRIP: null null-null (null)    ← graphic frames
STRIP: null 89-3 (6.4)    ← another phantom
STRIP: null null-null (null)    ← more graphic frames
```

**~14 minutes of unusable strip reads** before pipeline locked onto real CSK data.

**Why operator didn't see this duration:** UI was showing stale state (from the held-but-correct innings 1 final + reset target). Operator probably interpreted as "innings break in progress."

**But this is a problem:** broadcast showed CSK's first delivery at ~21:33-21:34 (operator said "innings 2 started"), pipeline didn't lock until 21:45. **~12 minutes of innings 2 data lost.**

**Class:** innings transition unstable window — exactly what P12 in main post-mortem addresses.

**Fix priority:** P12 in main post-mortem. This finding STRENGTHENS the case for that fix.

---

## A9 — 33 DELIVERY ENQUEUED events fired this run (BIG WIN)

**Frequency:** 33 enqueues. Compare to morning's 0 enqueues.

**This is the most important positive finding in the entire run:**
- 33 deliveries actually queued for Layer 2 classification
- Layer 2 method: `gemini_async`
- Real ball events captured: 8 DOT, 5 EXTRA, 2 FOUR, 2 SIX, 3 WICKET, 3 MULTI_BALL = 23 individual + 3 multi
- Plus enqueues that didn't show as ball_events due to other state

**The combined effect of P0+P1+P2 was: from 0 enqueues this morning to 33 enqueues tonight.**

**Class:** positive finding. Document this as success metric.

---

## A10 — OpenScout deliveries directory: only 1 action clip + 3 non_action

**Frequency:** 1 action delivery clip written by OpenScoutDeliveryWriter.

**Disappointing for validation purposes.** 33 actual deliveries enqueued but only 1 OpenScout span closed and was written.

**Likely causes:**
- SpanAggregator's MIN_SPAN_FRAMES=2 means an action span needs 2 contiguous action frames to form
- OpenScout cadence may not be hitting fast enough during action sequences
- The 421-record JSONL file was actually the smoke_test JSONL (operator's earlier check showed "smoke_test_openscout" name). The real session JSONL may not have written properly.

**Action item:** investigation needed before OpenScout-triggered architecture decision.

**Fix priority:** P22 (investigate why span formation is so sparse). Could be SpanAggregator constants or OpenScout per-frame recall regression.

---

## A11 — FIELD WARN powerplay misclassification continues (11 events)

**Frequency:** 11 events this run (down from 22 in morning's run).

Same as A6 from yesterday's addendum. Pre-existing, lower priority.

---

## A12 — Vision timeouts: 1 (acceptable)

Single timeout in 787 frames (~0.13%). Below acceptable threshold.

---

## Summary table — full issue list

| Issue | Class | Severity |
| --- | --- | --- |
| A1 STRIKER-COLLISION (125x) | Strip-OCR weakness | Medium (no data leak, but high warning noise) |
| A2 STRIP-ROWS-MISALIGNED (32x) | Strip-OCR weakness | Medium (32 frames of data rejected) |
| A3 LATENCY-STUCK bowler (45x, up to 99 frames) | Bowler tracking gap | High (commentary misattribution) |
| A4 Comparison strip overlay (36x) | Broadcast overlay leak | Low (gate working) |
| A5 Squad mismatches (145x) | Strip-OCR + analytics overlays | Low (gate working) |
| A6 BOWLER-STATS-GRAPHIC-GATE (8x) | Pre-existing gate working | None (positive) |
| A7 BOWLER-BATTER-GATE strip (20x) | Strip-OCR role confusion | Low |
| A8 Innings 2 cold-start ~14 min phantom window | Architecture | High (P12 addresses) |
| A9 33 deliveries enqueued | Pipeline success | None (positive — major win) |
| A10 OpenScout span sparseness (1 clip) | OpenScout architecture | Medium (investigate) |
| A11 FIELD WARN powerplay (11x) | Field classifier | Low |
| A12 Vision timeouts (1x) | Acceptable noise | None |

---

## Recommended additions to tomorrow's queue

### P19 — STRIP-ROWS-MISALIGNED root cause (1-2 hr)

32 firings means the strip layout is occasionally reversing batter rows. Investigate if the misalignment is detectable BEFORE we try to read the rows (visual signal in strip layout itself), so we can skip the OCR pass entirely on those frames.

### P20 — Bowler latency hard-cap (30 min)

If bowler card has been stuck on same name for >20 frames, set bowler to unknown rather than continuing with stale value. Cleaner failure mode than 99-frame misattribution.

### P22 — OpenScout span formation investigation (~half day)

1 closed span + 3 non-action is way too sparse given 33 enqueued deliveries. Either:
- SpanAggregator constants (MIN_SPAN_FRAMES, SOFT_GAP_TOLERANCE_S) need tuning
- OpenScout per-frame cadence has regressed
- Persistence layer has a bug (JSONL filename was wrong — might be writing to wrong session)

This investigation should also confirm whether the operator's proposed OpenScout-triggered architecture is viable. **Without dense action spans, the redesign won't have signal to work with.**

### P21 (lower priority) — Squad mismatch cleanup

Add allowlist filtering to skip obvious non-names (NONSTRIKER, single chars, concatenated names). Reduces 145 fuzzy-match attempts.

---

## What this run reveals about overall architecture

The run is a structural success: P0/P1/P2 caught their targets, innings transition worked, 33 deliveries enqueued. But the pre-existing weaknesses (A1-A8) point to a deeper pattern:

**Strip-OCR is fragile in many distinct ways:**
- Striker marker detection (A1)
- Row order (A2)
- Bowler name formatting (A3, A7)
- Comparison overlays (A4)
- Cross-match analytics overlays (A5)

Each individual gate works correctly when its specific failure mode hits. But the cumulative effect is **~200 warnings across the 50-minute run** for various strip-OCR confusion modes.

This is exactly the diagnostic environment that justifies the operator's proposed OpenScout-triggered architecture: **detection that doesn't depend on strip-OCR being right** would route around all of A1-A7 simultaneously.

The OpenScout span sparseness (A10) is now the critical blocker for that redesign. If we can't get OpenScout to detect action spans densely, the redesign won't work. **A10 is the next most important investigation.**
