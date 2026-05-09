# Post-Mortem: CSK vs MI, 44th Match IPL 2026 — 2026-05-02

**Session:** `ac752eb5` (capture session `20260502_192820`)
**Pipeline run:** 19:28:23 IST → 20:05:31 IST (37 min, 11469 log lines, 288 trace frames, 421 OpenScout records)
**Operator-observed final UI:** MI 63/3 (7.5 ov), Rickelton 37(24) 4s=1 6s=1
**Real broadcast at session end:** MI 63/3 (~7.0 ov)

Run artifacts:
- `logs/pipeline-2026-05-02-1928-csk-vs-mi-44th-match-ipl-2026.log`
- `logs/trace/ac752eb5.jsonl`
- `files/logs/openscout-ac752eb5.jsonl`
- `files/files/logs/openscout_spans/20260502_192820/{span_0001,span_0002}/`

---

## TL;DR — leverage map

The run had **two independent poison events** (Issue 1 and Issue 2) plus one **previously-unrecognized residue bug** (Issue 3, downstream of Issue 1) that together drove every other observed symptom.

| Event | Frame | Time | Real broadcast | What committed | Survived until |
|---|---|---|---|---|---|
| 47-3 phantom | F55 | 19:31:23 | pre-toss / 0-0 | `score→47(consensus)` | F131 (19:36:35), full F138 |
| `last_dismiss_at=3` residue | (state) | 19:31:24 | n/a | persistent | 20:05:11 (F698, real wkts→3) |
| 7.5 overs phantom | F500 | 19:57:07 | MI 53/1 (5.2) | `overs→7.5` | end of session |

Once you understand those three events, every other symptom falls out:
- Issue 3 (Naman Dhir blackholed) = `last_dismiss_at=3` residue blocks new-batter swap-in for 26 min until real wickets reach 3.
- Issue 5 (bowler tracking breaks at Issue 2) = bowler-spell rotation depends on overs progression, which is frozen at 7.5.
- Issue 7 (partnership stuck) = combination of Issue 3 (wrong batters at the crease) + the partnership counter resetting on each phantom-replayed wicket.
- Issue 4 (this_over `?` placeholders) = mostly normal observation gaps; corrupted by Issue 2 once 7.5 locks the over-decompose math.
- Bonus (boundary count broken) = striker attribution wrong because of Issue 3 + name-collision in extractor (`NAMAN RICKELTON 4(2)`).

Independent of the above:
- Issue 6 (speed_kph hit-and-miss) = depends entirely on whether the strip OCR caught the `SPEED:` chunk in the INFO_PANEL section.

---

## Issue 1 — Phantom 47-3 lock at startup

### A1 — exact consensus commit

**F55 @ 19:31:23, log line 635**:
```
[19:31:23 F55 TEST] INFO:   [S 1337ms] Changes: ['score→47(consensus)']
```
Strip read for that frame (line 643, DETAIL):
```
STRIP: null 47-3 (null) | extras=null | this_over=null | *Ruturaj 20(18) | Sanju 5(7) | Boult 1-15 (3.2)
```
Batters at the crease state at commit: `bat1=Sanju Samson 0(0)`, `bat2=Noor Ahmad 0(0)` (already pre-loaded — see "What was already wrong" below). Score moved `None-None → 47-3` in `AFTER_score`. Wickets advanced to 3 (`AFTER_fow_count=3`).

### A2 — what the broadcast actually showed F2..F55

The broadcast was showing **two distinct CSK previous-match recap overlays** during the cold-start window. The Scout classified them as `phase=between_play digits=True` and tagged them as `SCOREBOARD`, not `GRAPHIC` — so the recap survived all the way through the extract → score path.

| Frame | Time | STRIP raw (truncated) | Identifies as |
|---|---|---|---|
| F2 | 19:28:34 | `null 81-5 (null) \| Ruturaj 33(22) \| Shivam 21(24) \| Bishan 2-37 (4)` | CSK previous match A (Shivam Dube was at the crease — different match) |
| F8 | 19:29:09 | `Chennai Super Kings 47-3 (7.5) \| Ruturaj Gaikwad 1(3) \| Shivam Dube 29(19) \| Mustafizur Rahman 3-13 (2)` | CSK previous match B (Mustafizur bowling — likely an earlier-season MI match) |
| F35 | 19:30:30 | `null 98-3 (7.1) \| Rutu 45(34) \| Sanju 27(21)` | CSK previous match C |
| F53 | 19:31:09 | `null 47-3 (null) \| *Ruturaj 20(18) \| Sams 5(7) \| Boult 1-15 (3.2)` | CSK previous match D (Boult bowling) |
| F55 | 19:31:23 | same as F53 | (committed) |

The 47-3 came from **two different recaps** that happened to share the same score signature: F8's recap had overs=7.5 with Mustafiz, F53/F55's recap had no overs with Boult. The scout's `phase=between_play, digits=True` heuristic does not separate "live strip during a between-overs gap" from "static recap overlay during a between-overs gap" — both look identical structurally (single horizontal strip with score+batters+bowler).

OpenScout text classifications during this window (`files/logs/openscout-ac752eb5.jsonl`) describe walking umpires, advertisements, and Angel One banners — i.e. visual content was at-pitch / pre-match, not live play. The strip OCR was reading a **graphic overlay laid over the pre-match camera feed**.

### A3 — why the gate let 47-3 through

Cold-start GUARD blocked individual proposals:
- F2 line 141: `[GUARD] Score correction in Scorer output: 0→81 — blocking ALL updates`
- F8 line 268: `[GUARD] ... 0→47 — blocking ALL updates`
- F35 line 530: `[GUARD] ... 0→98`
- F53 line 588: `[GUARD] ... 0→47`
- F55 line 629: `[GUARD] ... 0→47` — **BUT**

…the **CONSENSUS path bypasses GUARD**. F8 and F53 both proposed `score=47`. The TRACK consensus accumulator (line 264 at F8: `score: initial proposal flipped 81 → 47 — resetting consensus to 1/3`; F53 line 583: `score: initial proposal flipped 98 → 47 — resetting consensus to 1/3`) reached 2/3 by F53 and 3/3 by F55, at which point line 635 fires `score→47(consensus)`. The consensus commit emits a separate code path that does not re-check the GUARD's "delta from 0" rule.

This is the design defect P7 was supposed to address (cold-start narrowing). The narrowing held for *single-frame* proposals (the GUARD blocked each one), but it does not apply to *consensus-confirmed* proposals — and consensus only requires multiple poison frames to agree, which two recap frames trivially do.

### A4 — why recovery took ~9 minutes

Score 47 committed at F55 (19:31:23). Real broadcast strips appeared starting F56 (19:31:28) but were rejected:

```
F56  19:31:28  STRIP: SUPER KINGS 0-0 (0.0) | GAikwad* null(null)         (CSK pre-toss)
F58  19:31:36  STRIP: MI 0-0 (0.1) | Jacks 0(1) | Rickelton 0(0)          → FRAME_POISONED:0
F77  19:32:47  STRIP: MI 1-0 (0.3) | *Jacks 1(3) | Rickelton 0(0)         → FRAME_POISONED:None
F87  19:33:27  STRIP: MI 1-0 (0.3) | Jacks 1(3) | Rickleton 0(0)          → FRAME_POISONED:1
F90  19:33:41  STRIP: MI 120-0 (0.3) | Ryan Rickelton 120(10)             → FRAME_POISONED:120 (extractor mis-read)
F101 19:34:25  STRIP: CSK 1-0 (0.5) | Jacks 1(3) | Rickelton 0(2)         → FRAME_POISONED:1
...
F128 19:36:20  STRIP: MI 1-0 (1.1) | Jacks Rickelton | KAMBOJ 0-0 (0)     → first batters/bowler commit (no score)
F131 19:36:35  STRIP: MI 1-0 (1.1) | JACKS 1(4) | RICKELTON 0(3)          → score→1, wickets→0  (UI now 1/0)
F138 19:37:07  STRIP: MI 1-1 (1.2) | JACKS 1(5)                            → MULTI_BALL: score→1, overs→1.2, wickets→1
```

F127 line ~1850: STRIP MI 1-0 (1.1) tagged `FRAME_POISONED:1` because the `+44 → −46` jump (47 → 1) tripped the poison gate. The poison gate was correctly designed to block "score went down by ~50" — but in this case the *previous* commit (47) was the poison, not the new (1) commit, and the gate had no way to know that.

The breakthrough came at F131 (5 min 12 s after the bad commit) when consensus on score=1 finally accumulated against the locked 47. **MULTI_BALL_DECOMPOSED at F138 (19:37:07)** was the operator's observed full-recovery point, 5 min 44 s after the poison commit.

Operator's "9 minutes" measures from session start (19:28:23) → F138 (19:37:07) = 8 min 44 s. That's the user-perceived recovery time and matches the operator's observation precisely.

### What was already wrong before F55

Even before the score commit, F8 line ~256 shows TRACK had been pre-populating *batter* state from the recap:
```
F8 TRACK: bat:Ruturaj Gaikwad:runs: initial proposal flipped 33 → 1
F8 TRACK: bat:Shivam Dube:runs: initial proposal flipped 21 → 29
```
These weren't the actual at-crease batters either, but the consensus mechanism was advancing them. By F55, `bat1/bat2` was Sanju Samson + Noor Ahmad (a different recap had populated this).

---

## Issue 2 — Phantom overs 7.5 mid-run

### A1 — exact frame where overs jumped 5.x → 7.5

**F500 @ 19:57:07** — trace `committed_changes` for that frame:
```json
['overs→7.5', 'bat:Will Jacks=1(5)', 'bat:Ryan Rickelton=22(19)']
```
Strip read at F500:
```
STRIP: null 49-3 (7.5) | extras=5 | this_over=1. | RICKELTON* 22(19) | JACKS 1(5) | CHOUDH
```
Immediately preceding frames (real broadcast):
- F488 (19:56:07): UI=47/1 (5.0), strip `MI 47-1 (5)`
- F495 (19:56:45): strip `MI 47-1 (5.1)`
- F497 (19:56:55): score→53, overs→5.2 committed (real broadcast `MI 53-1 (5.2)`)
- F499 (19:57:03): strip `null 47-3 (null) | *RICKELTON 20(18) | JACKS 5(7)` (recap — earlier than the F500 recap, no overs in this one)
- **F500 (19:57:07)**: strip `null 49-3 (7.5)` (recap — same family of poison overlays as F8/F53)

### A2 — what the 7.5 was

A second recap of the same family that drove Issue 1 (F8 had `47-3 (7.5)` with Mustafiz). F500's recap shows `49-3 (7.5)` with Choudhary's spell stats — a near-identical preview-overlay format. The 7.5 over comes from a **different past CSK match** where CSK collapsed to 47-3 / 49-3 at that point in the powerplay.

### A3 — why didn't the gate catch it

Look at the F500 commit list: `['overs→7.5', 'bat:Will Jacks=1(5)', 'bat:Ryan Rickelton=22(19)']`.

The **score** was rejected (the recap proposed 49 < the live 53; the score-floor logic blocked the regression). The **overs** was accepted. There is no symmetric "overs cannot jump forward by >2 in one frame" guard. Real overs at this point were 5.2; the recap proposed 7.5 (Δ=+2.3); the system accepted.

One frame of poison was sufficient. Unlike Issue 1, no consensus accumulation was required — overs has a fast-path single-frame commit because most ball-by-ball over progressions are +0.1.

### A4 — what happened to this_over and recent_overs after lock

After F500, every subsequent commit's `committed_changes` list contains `'overs→7.5'` even when the strip reads correct lower values:

| Frame | Time | Strip overs | UI overs | Commits include |
|---|---|---|---|---|
| F511 | 19:57:26 | 5.2 | 7.5 | `'overs→7.5'` |
| F533 | 19:58:16 | 5.3 | 7.5 | `'overs→7.5'` |
| F558 | 19:59:32 | 6 | 7.5 | (no overs commit) |
| F583 | 20:00:59 | 6.1 | 7.5 | (no overs commit) |
| F596 | 20:01:51 | 6.2 | 7.5 | `'overs→7.5'` |
| F687 | 20:04:47 | 6.5 | 7.5 | (no overs commit) |
| F698 | 20:05:11 | 7.0 | 7.5 | (no overs commit) |

The **score progressed correctly** because score commits use a different code path (Δ-from-current, no overs dependency). But:
- `this_over` array was permanently broken: F533 shows `AFTER_this_over=['?', '?', '?', '?', '?', 'Wd']` (6 entries — the system thought this was over 7.x with 5 prior balls). Every '?' is `(obs)` or `(bcast)` — meaning the system "knew" balls had occurred without classifying them, then padded the array.
- F543 line 8884: `corrections=This-over trimmed 1 '?' placeholder to match 5 legal balls` — the over-trim heuristic is also confused.
- BALLS-CEILING-GATE was firing (line 2029 at F135 during recovery): `[BALLS-CEILING-GATE] overs=0.1 (legal_balls=1, ceiling=3): Will Jacks=balls=4 — rejecting batter proposals.` — once overs is wrong, the per-batter ball-cap is wrong, batter proposals get rejected, the cycle perpetuates.

---

## Issue 3 — Naman Dhir never picked up (root cause: `last_dismiss_at=3` residue)

### Smoking gun

**195 occurrences** of `[DISMISS] Blocked` in the log. Every single one cites `last_dismiss_at=3`. Sample (line 2405, F167 19:38:36):

```
[DISMISS] Blocked — wickets counter has not advanced since last auto-dismiss
(cur=1, last_dismiss_at=3). New batter 'Naman Dhir' is almost certainly an
extractor hallucination (replay/comparison overlay) rather than a real arrival
at the crease.
```

**Root cause chain:**
1. F55 (19:31:23) committed phantom `wickets→3` as part of the `47-3(consensus)` lock.
2. The auto-dismiss code processed three implied wickets, advancing `last_dismiss_at` to 3.
3. Recovery (F131 / F138) corrected `wickets` back down to 0 then 1, but **`last_dismiss_at` is a one-way counter that was never reset**.
4. From that point onwards, the dismiss-batter swap-in path is disabled until real wickets reach 4: `cur > last_dismiss_at` is the gate.
5. Naman Dhir came in at MI 1/1 (real wkts=1, `last_dismiss_at=3`) → blocked.
6. Suryakumar Yadav came in at MI 59/2 (real wkts=2, `last_dismiss_at=3`) → blocked at F165 line 2356.
7. Naman finally appears in commits at F699 (20:05:14) — *after* the third real wicket (F698 `wickets→3`) when `cur=3 == last_dismiss_at=3` → gate finally relaxes.

### Direct evidence Naman was being read but rejected

| Frame | Time | Strip BAT line | What committed |
|---|---|---|---|
| F167 | 19:38:37 | `NAMAN 0(0) \| RICKELTON 0(3)` | `bat:Ryan Rickelton=0(3)` only — DISMISS Blocked |
| F197 | 19:40:03 | `NAMAN RICKELTON 4(2) \| 0(3)` (FOUR event) | `bat:Ryan Rickelton=4(2)` — name collision: extractor read "NAMAN RICKELTON" as one token |
| F213 | 19:41:04 | `NAMAN 4(4) \| RICKELTON 0(3)` | `bat:Ryan Rickelton=0(3)` only |
| F495 | 19:56:45 | `Naman 13(8) \| Rickelton 33(18)` | `bat:Ryan Rickelton=33(18)` only |
| F497 | 19:56:53 | `Naman 19(9) \| Rickelton 33(18)` | `bat:Ryan Rickelton=33(18)` — log lines 8030, 8031, 8043, 8044 explicitly reject Naman |

F497 line 8031 is particularly clear: `Batter 'Naman Dhir' rejected — 2 batters already active: ['Will Jacks', 'Ryan Rickelton']`. Will Jacks (dismissed at F138!) is **still listed as active** because the dismiss-swap was blocked.

The SCORE_MGR (separate module) did accept Naman as striker (F497 lines 8066-8067: `[SM] ABSORBED_LEGAL 53/1 (5.2) striker=Naman Dhir`), but BOARD's `active_batters` list was never updated, so the UI surface continued reporting Jacks + Rickelton.

### Why was Rickelton tracked but Dhir wasn't?

Rickelton was at the crease *before* the wicket (Jacks dismissed). The pipeline already had Rickelton in `bat2`. Rickelton's stats updated via the normal in-crease batter-update path, which doesn't go through DISMISS. Dhir needed the DISMISS gate to *create his slot* — and that gate was permanently closed.

### Bowler-attribution interaction (A6)

No direct interaction. Bowler attribution and batter attribution are independent paths. The reason both broke at similar times is unrelated for this issue (bowler was fine until Issue 2; Dhir was broken from F167 onwards).

---

## Issue 4 — this_over `?` placeholders

### Are FLOOR-CAP / THIS-OVER-BCAST-REJECT firing?

**Neither tag fires in this run** (0 hits). The named tags are different:
- `BALLS-CEILING-GATE` (the P8-era guard) fires 3× at F135-F137 (lines 2029, 2067, 2101) during the 47-3 recovery — correctly rejecting `Will Jacks=balls=4` against `legal_balls=1`. These are legitimate firings.
- The trimming you see in `corrections=` fields is `corrections=This-over trimmed N '?' placeholders to match M legal balls` (e.g. F138 line 2216: `trimmed 4 '?' placeholders to match 2 legal balls`; F543 line 8884: `trimmed 1 '?' placeholder to match 5 legal balls`).

### Where the `?` comes from

Two distinct sources, marked in `AFTER_this_over_src`:
- `?(obs)` — observation source: Layer-2 ball-event detector saw a delivery happen but couldn't classify the outcome (typical during dead-time / cutaway shots).
- `?(bcast)` — broadcast source: the strip's `this_over=` substring contained a glyph that didn't map to a known outcome (e.g. `⚾️⚾️`, `◉○○`, `1.5.4.`).

Recovery happens because subsequent strip reads with cleaner glyphs replace `?` entries via the trim heuristic (`AFTER_this_over_src=?(obs),?(obs),?(obs),?(obs),Wd(bcast),W(obs)` at F638 line 10764).

### Issue-2 amplification

After the 7.5 lock, the over-trim math is wrong. F533 has `AFTER_this_over=['?', '?', '?', '?', '?', 'Wd']` — five `?` because the system pads to 6 balls per "completed" over even though the broadcast was on real over 5.3.

So Issue 4 is **mostly normal** ball-event observation noise; the *visible severity* was inflated by Issue 2.

---

## Issue 5 — Bowler tracking broke at Issue 2

### Bowlers correctly detected pre-F500

| Frame | Time | Bowler commit | Real bowler |
|---|---|---|---|
| F30 | 19:30:11 | `bowl:Trent Boult` | (recap-derived; pre-recovery) |
| F131 | 19:36:35 | `bowl:Anshul Kamboj` | Kamboj over 1 ✓ |
| F227 | 19:41:52 | `bowl:Mukesh Choudhary` | Choudhary over 2 ✓ |
| F320 | 19:46:40 | `bowl:Anshul Kamboj` | Kamboj over 3 ✓ |
| F431 | 19:52:46 | `bowl:Prashant Veer` | Veer over 4 ✓ |
| F486 | 19:55:57 | `bowl:Mukesh Choudhary` | Choudhary over 5 ✓ |
| F595 | 20:01:45 | `bowl:Noor` | Noor (real over ~6) — late by ~1 min |
| F633 | 20:03:10 | `bowl:Noor Ahmad` | Noor Ahmad over 7 ✓ |

### Why it broke after F500

The bowler-spell rotation logic uses `over_completed` events to fire "spell ended → next bowler proposed". With overs frozen at 7.5, the over-completed event fires at the wrong time, and the bowler-update path is gated on overs progression:

- F595 line ~10000: `[SM-FEEDER-DIVERGENCE]` fields show overs disagreement between SM and SB.
- The bowler attribution did eventually catch Noor (at F595, ~3 min late), but only because the strip OCR finally produced a clean `Noor 0-1 (0.1)` reading. The system was working from broadcast strip rather than spell-tracking by then.

**Confirmed: Issue 5 is downstream of Issue 2.** Fixing Issue 2 will restore the over-completion → bowler-rotation chain.

---

## Issue 6 — Speed kph hit-and-miss

### Frequency

`SPEED:` text appears in the strip OCR for **12 distinct frames** in the run (grep `SPEED: \d` → F100, F200, F279, F294, F364, F382, F433, F449, F495, F533, F543, F625, F638). All were captured into `speed_kph=` in the DETAIL line.

Many balls between captures had no speed (e.g. F197 FOUR ev had no `speed_kph` set).

### Why

The speed comes from the strip's `INFO_PANEL` section, which the Scout OCR captures only when:
1. The `INFO_PANEL` substring is present in the OCR'd strip (some frames truncate the strip before INFO_PANEL).
2. The `SPEED:` keyword appears with a numeric value (some frames show `INFO_PANEL: null SPEED: null`).

The `delivery_speed_vlm` field exists separately (from VLM analysis of the delivery clip — F294 has `delivery_speed_vlm=138.7` and F433 has `94.3`). When VLM speed is present, the system also uses it. So speed has **two sources** (strip OCR + VLM analysis), and gaps occur when neither produces a value.

This is **independent of Issues 1-5** and reflects normal strip-OCR gappiness. Fix would require either better OCR coverage of the INFO_PANEL or wider VLM-speed adoption.

---

## Issue 7 — Partnership stuck at +1

### Partnership progression

| Frame | Time | partnership= | striker / non-striker | Notes |
|---|---|---|---|---|
| F135 | 19:36:52 | `1(1)` | Sanju / Rickelton | F135 COMMENTARY line 2040: `[PARTNERSHIP] new pair {'Will Jacks', 'Ryan Rickelton'} anchored at score=0 balls=0` |
| F138 | 19:37:07 | `1(8)` | Rickelton / Jacks | After Jacks dismissed at MI 1/1 |
| F140 | 19:37:17 | `1(8)` | Rickelton / Jacks | Stuck — Naman not yet replaced Jacks |
| F167 | 19:38:37 | `1(8)` | Rickelton / Jacks | DISMISS-Blocked, Naman rejected |
| F197 | 19:40:03 | `5(10)` | Rickelton / Jacks | First boundary credited via score-Δ; partnership advanced from team total |
| F495 | 19:56:45 | `47(30)` | Naman / Rickelton (striker) | SM cutover, partnership tracking correct numerically but pair label is `Jacks/Rickelton` |
| F497 | 19:56:53 | broadcast override `52(24)` | (line 8049: `[PARTNERSHIP] broadcast override: 52(24) — anchor 0/0 → 1/8`) | Strip's "Partnership 52(24)" wired in |

### Link to Issue 3

**Confirmed.** The partnership *runs* tracked correctly because they derived from team-total Δ. But the partnership *balls* counter was tied to in-crease batters' `balls` — and Jacks (frozen at `1(5)` from F138) was still nominally on the field per BOARD. The result: partnership balls accumulated very slowly because real-Naman runs were going to a phantom-Rickelton-as-striker (the SM thought Naman was striker, the BOARD thought Rickelton, the partnership module split the difference).

Operator's "+1 stuck for a long time" matches the F138-F197 window (~3 min from wicket fall to first boundary) where partnership=`1(8)`. Recovery happened gradually as broadcast strip reads pushed the counter forward, then was overridden directly from the strip at F497.

---

## Bonus — Boundary count broken

### Boundary credit firings

| Frame | Time | Event | BDY-ACC log |
|---|---|---|---|
| F197 | 19:40:03 | FOUR | `Ryan Rickelton FOUR → fours=1 sixes=0 (runs=4)` (line 2932) |
| F241 | 19:42:58 | SIX | `Skip six for 'Ryan Rickelton' — would violate 4f+6s<=runs (new 1/1 vs runs=6)` (line 3847) |
| F253 | 19:43:45 | SIX | `Ryan Rickelton SIX → fours=1 sixes=1 (runs=12)` (line 4068) |
| F353 | 19:48:13 | SIX | `Skip six for 'Will Jacks' — would violate 4f+6s<=runs (new 0/1 vs runs=1)` (line 5450) |
| F443 | 19:53:46 | SIX | `Skip six for 'Will Jacks' — would violate 4f+6s<=runs (new 0/1 vs runs=0)` (line 7196) |

### How boundaries are wired

Two paths:
1. **Δ-inference**: a +4 or +6 score delta with `striker_this_ball` set → BDY-ACC for the striker.
2. **Broadcast field**: strip-derived `Fours N Sixes M` per batter → broadcast-override (rejected by FS-REJECT when impossible).

### Why the count is wrong

- F197's FOUR went to Rickelton (correct on broadcast — Rickelton was on strike for that ball after Naman hit a 4).
- F241's SIX got *skipped* by the 4f+6s≤runs guard because Rickelton's tracker showed `runs=6` (1 four + 1 six = 7 already, vs 6 runs).
- F253's SIX went to Rickelton (`runs=12` → fours=1 sixes=1 fits).
- F353's SIX was credited to **Will Jacks** (the BOARD's stale "active batter" because of Issue 3) and got skipped because Jacks's runs=1.
- F443's SIX got skipped for the same reason — credited to phantom-Jacks instead of Naman/Rickelton.

5 separate FS-REJECT firings during the run rejected impossibly-formatted broadcast 4s/6s values:
```
F439 19:53:28  FS-REJECT  fours=1 sixes=794 vs Rickelton runs=15
F497 19:56:53  FS-REJECT  fours=1 sixes=79  vs Rickelton runs=33
F586 20:01:09  FS-REJECT  fours=1 sixes=7   vs Rickelton runs=37
F688 20:04:48  FS-REJECT  fours=1356 sixes=0 vs Will Jacks runs=5
F699 20:05:12  FS-REJECT  fours=2 sixes=7   vs Rickelton runs=37
```

The OCR was producing junk for the boundary count fields. The FS-REJECT guard correctly rejected them, but the in-pipeline accumulation was already wrong because of Issue 3 misattribution. Final UI showing 4s=1, 6s=1 for Rickelton 37(24) reflects only the F197 four + F253 six that got through the BDY-ACC guard. The two skipped sixes (F241, F353) and any boundaries Naman hit are not credited.

**Confirmed: Bonus is downstream of Issue 3** (striker attribution). FS-REJECT is doing its job; the upstream attribution is the actual bug.

---

## Phase Z — Synthesis

### Z1 — dependency map

```
Issue 1 (47-3 phantom commit, F55)
  ├─ direct: 9 min of locked score 47/3
  └─ residue: last_dismiss_at=3 (never reset)
        └─ Issue 3 (Naman Dhir blackholed, F167-F699)
              ├─ Issue 7 (partnership stuck)
              └─ Bonus (boundary attribution wrong)

Issue 2 (7.5 overs lock, F500)
  ├─ direct: overs frozen at 7.5 for rest of session
  ├─ Issue 5 (bowler rotation breaks — overs-dependent)
  └─ amplifies Issue 4 (this_over array padding wrong)

Issue 4 (this_over '?' base case) — independent observation noise
Issue 6 (speed_kph) — independent strip-OCR coverage gap
```

### Z2 — fix leverage ranking

| Rank | Fix | Unblocks | Scope |
|---|---|---|---|
| 1 | **Reset `last_dismiss_at` when wickets is corrected downward** | Issue 3, Issue 7, Bonus | Small — single counter reset hook on the wickets-correction path |
| 2 | **Add overs-floor / overs-jump-ceiling guard symmetric to the score guard** | Issue 2, Issue 5, partial Issue 4 | Small — mirror the existing score-Δ gate for overs (e.g. reject Δovers > 1.0 in a single frame unless a wicket fell) |
| 3 | **Tighten consensus-bypass-GUARD path with a "delta-from-zero" check** | Issue 1 | Medium — touches the consensus commit code path; needs to distinguish "consensus reached on cold-start poison" from "consensus reached on real opening score" |
| 4 | **Have Scout downgrade `between_play digits=True` strips to GRAPHIC when no `live_camera` evidence in the prior N frames** | Prevents Issues 1 and 2 at source | Medium — Scout heuristic change, needs corpus tuning |
| 5 | **Fix extractor name-collision: split `NAMAN RICKELTON 4(2)` into two batters** | Improves Issue 3 partial mitigation, boundary attribution | Small — extractor regex tightening |

### Z3 — tomorrow's queue

**Ship-worthy fixes (small + high leverage):**
1. `last_dismiss_at` reset on `wickets` downward correction. [~30 min] — fixes Issue 3 and unblocks Issue 7 + Bonus. Ship first.
2. Overs-jump ceiling guard (Δovers > 1.5 unless wicket-fell-this-frame). [~45 min] — fixes Issue 2 cleanly. Validate against any legitimate +6 / multi-ball recovery cases.

**Investigation needed before fixing:**
3. Cold-start consensus tightening (Issue 1) — the right design depends on how often legitimate cold-start strips need consensus to commit (i.e. is it OK to require 5/5 instead of 3/3 at cold start? Or require a `live_camera` co-signal?). Worth a 1-hour design spike + corpus check before coding.
4. Scout `between_play` → GRAPHIC heuristic — needs 5-10 historical recap-overlay corpora to tune against. Investigate whether the OpenScout rich classifier can flag "static graphic over pre-match camera" as a separate phase.
5. Extractor name-collision (`NAMAN RICKELTON 4(2)`) — small in scope but the regex needs corpus validation.

**Non-priority / accept-as-is:**
- Issue 4 base case is normal observation noise; will improve naturally once Issue 2 is fixed.
- Issue 6 speed_kph requires either OCR coverage work or VLM-speed expansion; not urgent.
- Bonus boundary count guard (FS-REJECT) is working correctly; the upstream attribution fix from Issue 3 will resolve.

---

## Appendix — counts

- 162 `FRAME_POISONED` commits across the run.
- 195 `[DISMISS] Blocked` log lines (all `last_dismiss_at=3`).
- 23 `BATTERS-INVARIANT` violations.
- 5 `FS-REJECT` (impossible boundary counts).
- 2 OpenScout span clips written (`span_0001` 19:54:04 ~"frustrated player", `span_0002` 20:03:51 ~"crowd shot") — both `frame_class` was `other`/`action` for off-pitch content; not directly relevant to Issues 1-7 since the poison events came from on-screen recap overlays during *between-play* phases that the Scout did not classify as advertising / off-pitch.
