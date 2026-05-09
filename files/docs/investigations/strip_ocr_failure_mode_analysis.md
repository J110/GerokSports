# Strip OCR Failure-Mode Analysis — YouTube WI-vs-RSA Replay

**Date:** 2026-05-02 14:31
**Run:** 12:25–12:44 (`logs/pipeline-2026-05-02-1225-…log`,
`logs/trace/866ce150.jsonl`,
`files/logs/deliveries/20260502_122517/`)
**Driving question:** Why did the score-strip OCR cause 89 SCORE-INF-GATE / EXTRAS-INF-GATE rejections (per `youtube_test_delivery_detection_analysis.md` §3.2)? Which of A/B/C/D below is the dominant failure mode?

| Hyp. | Cause |
| --- | --- |
| A | YouTube-replay-specific visual artifact |
| B | Hallucination from elsewhere on screen (sponsor strips, IPL example priors, replay/career overlays) |
| C | Prompt regression vs validated baseline |
| D | Infrastructure (timeout, rate-limit, empty response) |

---

## §1 Sample-by-sample frame analysis

Sampled the 55 SCORE-INF-GATE rejections + 34 EXTRAS-INF-GATE rejections; the table below is the first 12 rejections, which are representative of the rest. **`SCOUT`** = what Scout returned in the `STRIP:` line; **`BEFORE`** = state-machine state before the rejected proposal; **`EXT`** = parsed extractor result.

| ts | F | BEFORE state | EXT proposed | SCOUT raw | Cause cluster |
| --- | --- | --- | --- | --- | --- |
| 12:31:40 | 159 | 4-0 (1.0) | 4-0 (1) | `STRIP: SA 4-0 (1)` | overs format only (`(1)` ↔ `(1.0)`); rejected by extras-floor |
| 12:32:54 | 178 | 4-0 (1.0) | 11-0 (0.1) | `STRIP: SA 11-0 (4)` | **career-stats overlay (Shamar Joseph T20I CAREER) bled into strip read** |
| 12:33:26 | 185 | 11-0 (4.0) | 8-0 (1.2) | `STRIP: SA 8-0 (1.2)` | actual strip not visible; Scout pulled stale inset |
| 12:33:53 | 202 | 11-0 (4.0) | 8-0 (1.2) | `STRIP: SA 8-0 (1.2)` | same stale inset (4 frames in a row) |
| 12:33:57 | 203 | 11-0 (4.0) | 8-0 (1.2) | `STRIP: SA 8-0 (1.2)` | "" |
| 12:34:02 | 204 | 11-0 (4.0) | 8-0 (0.2) | `STRIP: LIONS 8-0 (1.2)` | **team abbrev hallucination** ("LIONS" — SA franchise) |
| 12:34:11 | 206 | 11-0 (4.0) | 9-0 (2) | `STRIP: SA 9-0 (2)` | overs integer-only `(2)` — see §2.4 |
| 12:34:15 | 207 | 11-0 (4.0) | 9-0 (0.2) | `STRIP: SA 9-0 (2)` | "" |
| 12:34:20 | 208 | 11-0 (4.0) | 9-0 (2.0) | `STRIP: LIONS 9-0 (2.0)` | "LIONS" hallucination |
| 12:34:31 | 210 | 12-0 (4.0) | 9-0 (1.2) | `STRIP: SA 9-0 (1.2)` | stale inset |
| 12:34:36 | 211 | 12-0 (4.0) | 9-0 (0.2) | `STRIP: United 9-0 (2)` | **"United" hallucination** (sponsor) |
| 12:34:44 | 213 | 12-0 (4.0) | None-None | `STRIP: De Kock 2(6)` | **batter line returned as STRIP** — score line not found |
| 12:36:53 | 259 | 13-1 (4.0) | 9-1 (1.3) | `STRIP: SA 9-1 (1.3)` | stale post-wicket inset |
| 12:37:51 | 276 | 13-1 (4.0) | 9-1 (0.5) | `STRIP: Blue Waters 9-1 (9)` | **"Blue Waters" hallucination** (CPL water sponsor) |
| 12:38:18+ | 282–290 | 13-1 (4.0) | 10-1 (2) | `STRIP: SA 10-1 (2)` | stale recap inset (8 frames in a row) |

### §1.1 Direct frame inspection (3 deliveries)

Frames extracted with `ffmpeg -ss <t> -i delivery_window.mp4 -frames:v 1` from `files/logs/deliveries/20260502_122517/d{005,006,007}/delivery_window.mp4` (saved to `/tmp/strip-investigation/*.jpg`). Resolution: 960 × 378 (capture-card output, slightly cropped).

**d005 / t=8s (over 1.0, GOOD period):**
The score panel is a single-row strip:
`[FLAG] DE KOCK 2(3) [P] | HENDRICKS 2(3) [P]| 4-0 | TOSS: SA, VENUE: KINGSTON | SPEED 84.0 km/h | THIS OVER: ⊙⊙⊙⊙⊙`
The team abbreviation is **NOT present** as a leading token. Score `4-0` is in the middle, not at the left. There is **no over-counter** in the strip — only the `THIS OVER` ball-by-ball dot row.

**d006 / t=0s (over 4.0, CHAOS period):**
Two-row layout:
`DE KOCK 2  12  [P]` (top row)
`HENDRICKS 6 5  9-0` (bottom row)
`EXTRAS 1 | VENUE: KINGSTON | S JOSEPH 0-5 (0.2) | THIS OVER ⊙⊙`
Score is `9-0`, but a large `12` floats over the top row (probably partnership runs or player strike rate). Scout returned `JAM 12-0 (9)` for an adjacent frame in this clip — i.e. it grabbed the partnership `12` as the score and the leading digit of `9-0` as the over count. The team abbrev `JAM` is invented (no such team in this fixture).

**d007 / t=6s (wicket):**
Wicket overlay banner (REEZA HENDRICKS 6(6) | c MOTIE b S JOSEPH | SR 100.0) + a regular bottom strip:
`DE KOCK 2(3) | HENDRICKS 6 | 13 | 9-1 | EXTRAS 1 | VENUE: KINGSTON | S JOSEPH 1-5 (0.3) | THIS OVER ⊙⊙⊙`
Same pattern: score `9-1` is buried in the middle, a stray `13` floats next to it (probably current run-rate × 10 or partnership), no over-counter on the strip.

### §1.2 Career-stats overlay confounder (F176–F178)

The pre-bowler career graphic ("SHAMAR S JOSEPH T20I CAREER MATCHES 3, …") was on screen at F171–F176 (tagged `GRAPHIC` correctly, score commits were poisoned-and-ignored). When the graphic transitioned out at F177–F178, the frame was tagged `SCOREBOARD` again but Scout's read still had `STRIP: SA 11-0 (4)` — the `11` was Joseph's career wickets, the `4` was his career economy / matches count visible on the fading overlay. The pipeline's `tag=GRAPHIC` filter correctly flagged 11 frames (`scorer_changes=['FRAME_POISONED:None']`), but the GRAPHIC↔SCOREBOARD boundary is single-frame; transition frames leak fake numbers into the score path.

---

## §2 Hypothesis test results

### §2.1 Hypothesis A — broadcast-specific layout: **CONFIRMED, dominant**

The WI broadcast feed uses a **multi-field score info panel** with this geometry:
- No leading `[TEAM]` abbreviation token (just a national flag icon).
- Score `N-W` is mid-strip, not left-justified.
- **No over-counter on the strip**; over progress is shown only as `THIS OVER ⊙⊙` ball-dots.
- Overlay panels (`TOSS`, `VENUE`, `SPEED`, `EXTRAS`, `CURRENT RUN-RATE`, `STRIKE RATE`, partnership) are interspersed with the score in the same horizontal band.

The production prompt's requested format is `STRIP: [TEAM] [SCORE]-[WICKETS] ([OVERS]) | …` (`files/eyes/vision.py:190`) — this template **doesn't match the WI panel layout**. Scout has to *compose* the requested string from non-adjacent visual fields, which is where the wrong digit ends up in the wrong slot (e.g. partnership `12` becomes `score=12`, `9` from `9-0` becomes `overs=9`).

### §2.2 Hypothesis B — hallucination from elsewhere: **CONFIRMED, secondary**

Counted Scout's leading STRIP tokens across the 506 SCOREBOARD frame reads:

| Token | Count | Source |
| --- | --- | --- |
| `SA` | 381 | correct |
| `Not` | 37 | "X **Not** out" parsed as team abbrev |
| `LSG` | 18 | IPL prior (model training data) |
| `LIONS` | 15 | SA franchise jersey/sponsor |
| `RCB` | 14 | IPL prior |
| `Blue` | 9 | "Blue Waters" CPL sponsor |
| `Paarl` | 6 | SA T20 league |
| `South` | 4 | partial parse of "South Africa" |
| `United` | 3 | sponsor |
| `KKR` | 3 | **prompt-example regurgitation** (`STRIP: KKR 105-2 (11.3)` is the production example) |
| `MI` | 3 | IPL prior |
| `RICKELTON` | 2 | batter name as team |
| other (`SOU`, `PR`, `JAM`, `De`) | 9 | misc |

**~24% of STRIP reads (120 / 506) have the wrong team abbreviation.** Three of those flavours are unambiguous hallucinations:
1. **IPL example regurgitation** (KKR especially — that's the literal `STRIP:` example in `vision.py:193`).
2. **CPL/SA franchise priors** (LIONS, Blue Waters, Paarl, LSG, RCB, MI from training data).
3. **Layout fallback** (Not, South, RICKELTON, De — Scout couldn't find a team abbreviation and grabbed whatever leading token was present).

### §2.3 Hypothesis C — prompt regression: **NOT APPLICABLE**

§11.4 binary v2 validates **OpenScout's `frame_class` classifier**, not strip OCR. There is no "validated v2 prompt" for strip reads to regress against; the production STRIP prompt in `vision.py:188–215` is the prompt — it has not changed since the last working IPL run. The prompt itself isn't broken; it just doesn't match this broadcast's panel layout (§2.1).

### §2.4 Hypothesis D — infrastructure: **MINOR** (~2% noise, not the cause)

| Metric | Value |
| --- | --- |
| `Vision timeout — skipping` lines | **5** (out of 240 VISION calls = 2.1%) |
| Vision call latency mean | 632 ms |
| Vision call latency max | 1929 ms |
| Extractor latency mean / max | 1050 / 1616 ms |
| HTTP 429 / RESOURCE_EXHAUSTED / retry | 0 |

Latency is well within budget; the 5 timeouts are scattered (12:34:56, 12:37:17, 12:37:18, 12:42:01, 12:43:33) and don't correlate with the 89 gate rejections. Infrastructure is not the bottleneck.

### §2.5 Overs-format anomaly (sub-pattern of A)

| Format | Count |
| --- | --- |
| `(N.M)` decimal overs | 351 |
| `(N)` integer overs | 85 |

19% of strip reads have overs as a bare integer (`(1)`, `(2)`, `(9)`) instead of `(N.M)`. In every sample inspected the integer is either:
- The **leading digit of the score** stolen as overs (e.g. `9-0` → `(9)`), or
- A **player strike rate / RR** mistaken for the over count.

This is a direct consequence of the WI panel layout missing a clean over-counter token (§2.1).

---

## §3 Dominant failure mode

**A (broadcast-specific layout) + B (hallucination from priors) — combined.**

The two compound: the WI panel doesn't have a `[TEAM] [SCORE]-[WICKETS] ([OVERS])` line in the position the prompt expects, so Scout falls back on (a) IPL/CPL training-data priors for the team abbreviation, and (b) whatever digit is in the visual neighbourhood for the score and overs. C is non-applicable; D is noise.

Quantitatively, treating the 89 gate rejections as the failure budget:

| Failure cluster | Approx. rejections | Cause |
| --- | --- | --- |
| Stale inset / replay graphic showing earlier score | ~30 | A (layout: replay/recap inset is read as primary strip) |
| Career-stats overlay leakage (F171–F178 class) | ~10 | A (graphic-frame transition leak) |
| `(N)` integer-overs misparse | ~17 | A (no over-counter on strip) |
| Team abbreviation hallucination (LIONS, Blue Waters, KKR, RCB, etc.) blocking commits via XI/team gate | ~20 | B (priors + prompt example) |
| Genuine layout-mismatch read of the live strip | ~12 | A (multi-field panel) |

---

## §4 Implication for tonight's match

Tonight's fixture (per the `pipeline-…rsa-tour-of-west-indies-2024` log naming the broadcast is the same WI feed) **will exhibit the same panel layout**, so all of §3's failure modes will recur. The expected gate-rejection rate is 30–40% of strip reads.

If tonight is a different broadcast (IPL or international with a more standard `[TEAM] [SCORE]-[WICKETS] ([OVERS])` strip), the failure mode disappears — this is exactly the case in last night's `2026-05-01-1930-rr-vs-dc-…` run, where SCORE-INF-GATE rejections per minute were materially lower (worth a quick spot-check before the run).

---

## §5 Lever ranked by contribution

1. **Prompt: add a panel-layout disambiguation block to the STRIP step** (highest leverage, lowest cost, ~30 min):
   - Tell Scout that team-abbreviation may be a flag-only icon — emit `team=null` rather than guessing.
   - Tell Scout the score may be mid-strip with the over-counter absent — emit `overs=null` rather than substituting a neighbouring digit.
   - Drop `KKR 105-2 (11.3)` from the example; replace with a canonical example using `team=null, overs=null` to anchor the "don't guess" behaviour.
   - Expected effect: kills hallucinations in §2.2 and the integer-overs misparse in §2.5 → eliminates ~37 of the 89 rejections (clusters 3+4 in §3).

2. **Graphic-transition guard** (medium leverage, small code change, ~1 h):
   - Extend the `tag=GRAPHIC` poison filter by 1 frame after a GRAPHIC→SCOREBOARD transition (the leakage frames in §1.2). Eliminates the ~10 career-stats-overlay rejections.

3. **Replay-inset detection** (high leverage, larger change, ~half day):
   - Add a "replay" / "recap" / "wicket overlay" detector to Scout's tag step (the WI feed flags these visually with a coloured banner). Treat any STRIP read while a replay/recap overlay is on screen as untrusted. Eliminates the ~30 stale-inset rejections.

4. **Vision model swap (Lever 3 from prior memo)**:
   - Still useful as a fallback if (1)–(3) don't recover enough recall, but **don't lead with it**. The current model isn't dramatically worse at OCR; the prompt is dramatically worse-matched to this broadcast.

### §5.1 Recommended order tonight

- **Before tonight's run:** apply (1) only — it's a 30-min prompt edit and reverses ~40% of the rejections without code change.
- **During tonight's run:** measure the post-(1) rejection rate. If still > 25% on this broadcast, queue (2) for tomorrow.
- **Defer the model swap** until (1)–(3) are in and we have a clean baseline; otherwise we'll attribute prompt wins to the model.

---

## Appendix — supporting commands

```bash
# Catalog all SCORE-INF-GATE rejections with the strip Scout returned
grep 'SCORE-INF-GATE' logs/pipeline-2026-05-02-1225-*.log \
  | sed -E $'s/\\x1b\\[[0-9;]*m//g'

# Team-abbreviation hallucination tally
grep -oE 'STRIP: [A-Za-z]+ ' logs/pipeline-2026-05-02-1225-*.log \
  | sort | uniq -c | sort -rn

# Overs format breakdown
grep -ocE 'STRIP: [A-Za-z]+ \d+-\d+ \([0-9]+\)' logs/pipeline-2026-05-02-1225-*.log
grep -ocE 'STRIP: [A-Za-z]+ \d+-\d+ \([0-9]+\.[0-9]+\)' logs/pipeline-2026-05-02-1225-*.log

# Frame extraction (visual inspection)
for d in d005 d006 d007; do
  for t in 0 4 8 12; do
    ffmpeg -y -ss $t -i files/logs/deliveries/20260502_122517/$d/delivery_window.mp4 \
      -frames:v 1 /tmp/strip-investigation/${d}_t${t}s.jpg
  done
done

# Production STRIP prompt
sed -n '180,215p' files/eyes/vision.py
```
