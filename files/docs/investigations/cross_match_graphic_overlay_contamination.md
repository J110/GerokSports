# Cross-match graphic overlay contamination

**Date:** 2026-05-04
**Match:** GT v PBKS (2026-05-03)
**Linked log:** `logs/pipeline-2026-05-03-2058--stage1ready.log`
**Linked sidecar:** `openscout-2e3a069c.jsonl`

## Context

During GT-PBKS, broadcast inserted a feature graphic captioned
"JASON HOLDER MATCH 42 - GT v RCB 3 CATCHES, 2 WICKETS" — a stat card
sourced from a *different* match (Match 42, GT v RCB). Strip OCR ingested
the graphic verbatim and committed phantom bowler stats to the scoreboard:

- **F70 (21:01:14):** cold-start consensus commits `Jason Holder 2/17 (3)`
  — phantom; Holder was actually mid-spell at a different over count.
- **F79 (21:01:55):** `HOLDER 2-18 (3.1)` — phantom carried forward.
- **F81 (21:02:05):** extractor reads `HOLDER 1-36 (None)` — pulled
  directly from the GT-RCB feature card.
- **F89:** `Holder 2-37 (4)` — 4 overs is from the wrong spell.

The contamination drove issue **U2** (phantom Holder stats / wrong bowler
card): pipeline believed Holder had completed 4 overs when his real spell
was at 8.4 cumulative.

## Why existing filters miss

### GRAPHIC-FILTER (`test_pipeline.py:2285-2325, 6992-7025, 7585-7635, 8058-8153`)
- **Mode A** rejects when `frame_type=="GRAPHIC"` (Vision lexical tag).
- **Mode B** rejects when `scout.cam=="graphic"` AND `scout.phase=="graphic"`
  during a SCOREBOARD lexical frame.
- **Mode C** pops score on info-panel keyword + score divergence > 7.
- **Gap:** Frames 68–79 carried `frame_type==SCOREBOARD` with
  `scout.cam=closeup` — neither Mode A nor Mode B preempt fired. Mode C
  needs a > 7-run score divergence; bowler-only contamination doesn't
  trigger it. Filter fires (28 in tonight's log) cluster around the macro
  overlay window but leak the bowler-card section.

### Strip-overlay sentinels (`test_pipeline.py:2060-2076, 2118-2175`)
- Sentinel list: `" > "`, `"RUN-RATE"`, `"CAREER"`, `"BEST"`, `"AVG"`,
  `"IN T20"`, `"IN IPL"`, `" vs "`, `"this season"`.
- `_detect_overlay_via_active_batting` checks batter resolution against
  current innings status.
- **Gap:** Sentinel list has no entry for `"MATCH NN"` patterns and no
  team-pair mismatch check. Bowler team is never compared against scout
  text. Frame 81's `1-36 (None)` read carried no listed keyword, so
  `apply_strip_overlay_prefilters` returned False.

### FRAME_POISONED (preempt at `test_pipeline.py:8058-8153`)
- Triggered on macro overlay→scoreboard transitions and scout-geometry
  poison signatures. Fired at F85 (post-overlay) — 14 frames after the
  contamination entered the tracker.

### Scout `frame_class` (`open_scout_classify.py:314-335`)
- Returns one of {action, replay, ad, umpire, other}. Used by
  `OpenScoutRateGate.allow()` (line 349-374) to skip ad frames; **not
  used to gate strip write commits**.

### Audit
| Frame | Scout text marker | Filter outcome | Stats committed |
|-------|-------------------|----------------|-----------------|
| F70   | (consensus from F68) | none fired | Holder 2/17 (3) — phantom |
| F79   | carry              | none fired | Holder 2-18 (3.1) |
| F81   | "1-36"             | sentinel miss | extractor read leaked |
| F85   | macro overlay      | GRAPHIC→SCOREBOARD poison | (post-fact) |
| F89   | "Holder 2-37 (4)"  | none fired | wrong-spell over count |
| F101  | row delta=26       | STRIP-ROWS-MISALIGNED backstop | popped, but late |

Cross-match cue coverage:

| Cue | Example | Detected today |
|-----|---------|----------------|
| `MATCH NN` with non-current number | "MATCH 42" during match 46 | No |
| Team-pair mismatch | "GT v RCB" during GT v PBKS | Partial (batter only) |
| Career-stat phrasing | "3 CATCHES, 2 WICKETS" | No |
| Season mentions | "IN T20" / "IN IPL" | Yes |

## Fix options considered

**(a) Cross-match text detector** — extend `_detect_overlay_strip_sentinels`
(`test_pipeline.py:2060`) with a regex for `r"MATCH\s+\d+"` and a team-pair
mismatch check against the current bowling/batting teams. Plugs frame 70
and frame 81 directly. Risk: false positives if commentary text mentions
historical matches; mitigated by requiring the match number to differ from
the current one.

**(b) Monotonic bowler-stat coercion guard** — at `scoreboard.update_bowler`
add a regression check: reject updates where `runs` decreases without a
corresponding wicket increase or explicit spell reset. Catches frame 81's
`2-18 → 1-36` in the wicket dimension (2 → 1). Risk: false negatives when
a cross-match graphic shows higher stats (no regression to detect).

**(c) Stricter frame_class gating** — extend OpenScout classifier to emit
`frame_class="overlay"` for cross-match feature graphics and gate
scoreboard commits in the main loop. Cleaner separation, but OpenScout is
fire-and-forget today; adding a blocking gate adds latency. Larger scope —
classifier needs an overlay-corpus retrain.

**(d) Composite** — (a) immediate, (b) defensive backstop, (c) medium-term.

## Recommended fix

**Implement (a) + (b) together.**

1. Add `r"MATCH\s+\d+"` to the sentinel regex list in
   `_detect_overlay_strip_sentinels` (`test_pipeline.py:2060`). When the
   captured match number ≠ current match number, treat the strip read as
   contaminated and pop bowler/batter writes for that frame.
2. Add a wicket-regression check in `scoreboard.update_bowler`
   (`files/scoreboard.py:~160`): if proposed `wickets < current_wickets`
   without an explicit spell-reset signal, reject the update.

Decisive factor: option (a) closes the exact 11-frame Holder window (F68–F79)
that leaked into consensus, with a single-regex change at the existing
sentinel hook. Option (b) is a cheap last-resort backstop that covers
future variants of the same failure (cross-match graphics with different
phrasing). Together: ~10 LOC, low false-negative risk on legitimate
spell updates, and they preserve the rest of the GRAPHIC-FILTER /
FRAME_POISONED machinery.

## Linked issues

- **U2** — phantom Holder stats / wrong bowler card (GT-PBKS, 2026-05-03)
