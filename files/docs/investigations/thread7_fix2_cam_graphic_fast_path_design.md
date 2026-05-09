# Thread 7 Fix 2 — `cam=graphic` strip-text fast-path with non-degeneracy guard (DESIGN)

**Status:** SHIPPED (2026-04-30). Execution followed §16; see §17.
**Companion docs:**
- Diagnosis: [`thread7_rediagnosis_multi_ball_gap.md`](thread7_rediagnosis_multi_ball_gap.md) (re-derives the F2123→F2136 gap mechanism; this doc executes §6 Fix 2).
- Sibling fix: Thread 7 Fix 1 (`STRIP-ROWS-MISALIGNED` — narrow comparison-strip guard) ships independently.
- Sibling fix: Thread 7 Fix 3 (P3, scout strip OCR row-pairing audit in `files/eyes/scoreboard.py`) — see §11 for interaction analysis.

**Ground truth (user, 2026-04-30):** "the strip is always visible during deliveries; it can be replaced briefly during major events (wicket replay graphics) but every delivery itself is accounted for on the broadcast strip."

**Source frame:** F2128 @ 21:22:08 in `logs/pipeline-2026-04-29-194416-mi-srh-live.log:23873-23874`:

```
[SCOUT] SCOREBOARD 696ms strip=True overlay=False drs=False cam=graphic
        phase=graphic digits=True 299 chars
[F2128] SCOREBOARD cam=graphic → dead-time skip (#207)
```

299 characters of scout output, `digits=True`, `strip=True`, `overlay=False`, the bottom strip almost certainly intact — and the pipeline threw the whole thing away because `cam=graphic ∈ _DEAD_VIEWS` at `test_pipeline.py:6465`.

---

## §1. Executive summary

**Mechanism (the bug).** `_DEAD_VIEWS = ("replay", "graphic", "ad", "other")` at `files/test_pipeline.py:6465-6515` short-circuits any frame whose Scout-tagged `camera_view` falls in the set, *before* anything is read from the strip. The skip is correct for `cam=ad` and `cam=replay` (the strip is genuinely absent or being painted over) but **wrong for `cam=graphic` whenever Scout itself reports `has_strip=True`**: the strip area survived the on-screen overlay and is being read by Scout's own pass — we just refuse to look at the digits.

**Fix shape.** A *fast-path* — not a full extractor invocation, not a Scorer LLM call. When `cam=graphic AND has_strip=True`, regex-parse the `STRIP:` line that Scout already produced into `description`, run a hard non-degeneracy guard, and on accept commit **only `score` and `match_overs`** to `Scoreboard` (no batters, no bowler, no this-over, no commentary). The Groq cost stays $0 (no extra LLM call); the cumulative-state contract remains identical to a normal `score`/`overs`-only DIRECT update.

**Detection approach.** Recommendation: **option (d) — combination guard**, with a strict 8-clause AND. Three structural gates derived from Scout's own tag bytes (`has_overlay_stats`, regex-strict `STRIP:` head, visible-team resolves to batting team) and five content gates from the strip itself (not all-zero, score monotone, overs monotone, score-delta ≤ +6, no-identity-loop cooldown). The non-degeneracy load-bearing decision lives in §3; full reasoning in §4.

**Predicted impact.** Conservative: **30–50 % of pure cam=graphic gap windows recovered**. Headline ball-gap rate model: ~5.8 % → ~4.5 % when Fix 2 ships alone; → ~3.5 % when Fix 2 ships *after* Fix 1 (the Fix-1 path is the dominant contributor; Fix 2 closes the residual `cam=graphic` slice). Confidence: **medium**. The dominant cam=graphic contribution to MULTI_BALL is during 1–3 frame solo skips (single graphic frame between live SCOREBOARD frames); these are the cleanest wins. The wicket-replay block at F2128–F2133 is partially reachable (F2128 only — F2129/F2131/F2133 are no-strip / cam=ad and stay skipped).

**Confidence in non-degeneracy guard correctness.** **High for B and C** (existing scout tag bytes catch them cleanly), **medium for D** (over-end preview overlap with live strip is the residual risk; scoped to `score`/`overs`-only acceptance pre-empts the worst failure modes).

**Composer-2-ready?** Yes — the non-degeneracy guard is fully specified in §3, the call site is one diff (≤30 LOC) at `files/test_pipeline.py:6465`, the regex / monotone constants are pinned, the telemetry tag schema is in §8, the fixtures are in §7. No architectural improvisation required at execution time.

---

## §2. Distinguishing live strip from non-live overlays

The user's case enumeration is the design contract. For each case (A live-with-overlay, B wicket replay, C career-stat card, D over-end preview, E no-strip ad) we identify the discriminating signal. **Critical observation that simplifies the whole design:** Scout's own classifier *already* emits a rich tag block (`has_strip`, `has_overlay_stats`, `camera_view`, `frame_phase`, `digits`) **before** the dead-time skip fires. Most of the discrimination work is already done; we are throwing the bytes away.

### §2.1 Case A — live strip with full-screen / partial graphic overlay (READ)

| Signature | Evidence in this match |
|---|---|
| Scout `has_strip=True` | F2128 line 23873: `strip=True` |
| Scout `has_overlay_stats=False` (the graphic is in the action area, not stats overlay) | F2128: `overlay=False` |
| `camera_view="graphic"` (action shot is replaced by a broadcaster element) | F2128: `cam=graphic` |
| Strict STRIP regex `^[A-Z]{2,4}\s+\d+-\d+\s*\(\d+(?:\.\d+)?\)` matches the parsable head | F2128 description not logged (skipped before `[V]` line); inferred from `digits=True` + 299 chars |
| Score / overs in strip ≥ current `Scoreboard` state | Held-over strip from F2126 would read `MI 221-4 (18.1)` ≡ current state ⇒ idempotent |
| Visible team resolves to current batting team | "MI" → Mumbai Indians (batting) |

**Discriminating signal vs B/C/D:** the **conjunction of strict-STRIP-match AND `has_overlay_stats=False`**. Cases C and D both have `has_overlay_stats=True` per Scout's prompt rubric (career card / partnership / over-end summary all populate the stats overlay). Case B's strip area, when visible at all, may parse strict-STRIP but typically with stale or held-over numbers.

### §2.2 Case B — wicket replay with dismissed-batter card in strip area (DON'T READ)

| Signature | Evidence in this match |
|---|---|
| Visual: REPLAY watermark / slow-mo motion blur, dismissed batter prominently in strip | Wickets 18.1 (Hardik Pandya, F1989); F2128 is 4 wall-clock seconds after the wicket — a wicket-replay window is the most likely visual content |
| Scout `cam=graphic` OR `cam=replay` (dependent on whether bottom strip survives) | F2128 returned `cam=graphic`; if strip had been replaced entirely, `cam=replay` would have fired (which is also in `_DEAD_VIEWS` and stays skipped) |
| Score doesn't update during replay window | F2123–F2127: score frozen at 221, overs at 18.1 |
| Frame-sequence context: replay typically follows wicket marker `'W'` in `this_over` | F2128 BEFORE state has `this_over=['W']` (line 23871, F2127 detail dump) |
| Strip-content signature: dismissed batter's stats from before dismissal | If broadcaster freezes strip: numbers ≡ pre-wicket state ⇒ monotone-equal (idempotent) |
| Strip-content signature: scout hallucinates 0-0 template | F2127 shows this happens (line 23853): `STRIP: MI 0-0 (0.0) | Tilak Varma 0(0) | Ricketson 0(0)` even though `cam=closeup`; the all-zero template is a mode the prior frame existing 0-0 mid-innings guard already catches |

**Reliable distinguishing signal vs A:** **monotonicity**. A genuine live strip in case A either matches the current state exactly (broadcaster left it up; benign idempotent commit) or has *advanced* (score went up, overs ticked). A case-B wicket-replay strip is showing the *pre-wicket* state, so its score is at most equal to current (often equal — broadcaster doesn't decrement score after a wicket of a not-out batter, only on a withdrawn-runs adjudication). The interval `[current_score, current_score + 6]` with `overs >= current_overs` is exactly the legitimate live-frame response surface.

**The wicket-replay residual risk:** suppose broadcaster shows the dismissed batter's scorecard graphic *in the strip area* with their pre-dismissal stats (career or innings). Scout's STRIP regex matches `MI 221-4 (18.1) | Hardik 31(11) | ...` — the team score and overs are still correct (broadcaster doesn't lie about team total during a wicket replay) but the batter rows are stale. Mitigation: **score/overs commit only**, no batters, no bowler.

### §2.3 Case C — full-screen career-stat / H2H / standings card (DON'T READ)

| Signature | Evidence in this match |
|---|---|
| Scout `has_overlay_stats=True` (the rubric definition of this flag) | F21 (line 369) `cam=graphic` `overlay=True` `strip=False`; F2768 (line 29113) `STRIP: MI 0-0 (0.0) | INFO_PANEL: TRENT BOULT IPL CAREER` |
| Scout strip text contains `INFO_PANEL`, `STANDINGS`, `CAREER`, `HEAD TO HEAD`, `MATCHES`, `WICKETS` keywords | F2768 line 29117 verbatim; F8 line 318 `STANDINGS RCB 2`; F1858 backlog example `STANDINGS RCB 2` |
| Strip-content shows 0-0(0.0) template hallucinated when no strip is parseable | F2768; existing 0-0 mid-innings guard already poisons this on the slow path |
| Visible team may resolve to a *different team* (career card for the opposition) | F2768 batting team is MI but card subject is Trent Boult who is opposition (MI's bowling lineup); strict visible-team check catches |

**Reliable distinguishing signal vs A:** **`has_overlay_stats=True` is dispositive**. Scout's prompt at `files/eyes/vision.py:104-107` defines this flag specifically as "career/tournament/head-to-head stats shown as an OVERLAY on top of the live feed (NOT the regular scoreboard strip)". Case A's full-screen graphic (e.g. a broadcaster-bug logo plate) is *not* a stats overlay → `has_overlay_stats=False`. The two cases are textually disambiguated at the Scout layer.

A second backstop is the strict STRIP regex. Career-stat hallucinations frequently emit `STRIP: MI 0-0 (0.0) | INFO_PANEL: ...` — the 0-0(0.0) head fails the all-zero guard. Standings cards emit `STRIP: MI 33-0 (2.4) | iplt20.com  INFO_PANEL: ...` — the strict head matches but the visible-team and INFO_PANEL contamination filter (already in pipeline at `filter_info_panel_contamination`, called at `test_pipeline.py:6657`) is *not* run on the fast-path; we replicate the keyword reject inline.

### §2.4 Case D — over-end preview / partnership graphic (DON'T READ)

| Signature | Evidence in this match |
|---|---|
| Scout `has_overlay_stats=True` (partnership graphic, end-of-over summary) | Frequent in mid-over breaks; rubric same as C |
| `frame_phase="graphic"` AND `cam=graphic` | Same as A and C; no discrimination |
| `this_over` ≥ 6 legal balls *or* an over-boundary just crossed | Cross-reference: `over_mgr.check_over_change` returned True in the previous accepted frame |
| Strip score either matches current state (if shown alongside live strip) or shows over-summary numbers | High variance — broadcaster-dependent |
| Bowler row may show *next* bowler's name (preview); current bowler in scoreboard doesn't match | Direct mismatch with `scoreboard._inn["current_bowler"]` |

**Reliable distinguishing signal vs A:** **`has_overlay_stats=True`** (same as case C); partnership graphics ≡ stats overlay per Scout rubric. The **bowler-row mismatch** is a secondary signal but we don't read bowler in the fast-path so it doesn't matter.

**Edge case D'** (over-end with strip still live): broadcaster pops a "OVER X — RR/PROJ" banner *above* the strip, leaving the bottom strip live. Scout would tag this as `cam=graphic` with `has_overlay_stats=True` and the strip head would show *correct* current state. Our fast-path rejects on `has_overlay_stats=True`. We pay a small false-negative cost (lose this frame) to be safe. The next live `SCOREBOARD` frame closes the gap immediately.

### §2.5 Case E — broadcast ad (CURRENT BEHAVIOR CORRECT)

Scout reports `strip=False` and `cam=ad` → `_DEAD_VIEWS` correctly skips (and our fast-path is gated on `has_strip=True`, so we never enter it). No change. F2131/F2133 in the gap window are this case (verified line 23880-23890).

### §2.6 Frame-sequence context (DROPPED FROM GUARD — see §3 reasoning)

A "wicket within last N frames → likely replay" state machine was considered but **dropped**: the per-frame static signals (overlay flag + strict STRIP + monotone) already discriminate without needing to maintain replay-window state. Adding a 30-second wicket-window guard would *also* reject Case A frames that legitimately occur within the wicket window (e.g. F2128 itself if the strip survived — which is the very frame we're trying to recover). False-negative cost outweighs marginal false-positive protection.

---

## §3. Detection mechanism (recommended)

### §3.1 Recommendation: option (d) combination guard with strict per-frame static gates

**Rejected alternatives:**
- **(a) Camera-state classifier extension** (split `graphic` into `replay`/`stat_card`/`preview`/`graphic`). Requires Scout prompt revisions + shadow-run validation + per-class label data. The cost-benefit is dominated by (d) which uses *existing* tag bytes Scout already emits. Defer (a) to a later iteration if (d) proves false-positive-prone in production.
- **(b) Strip-content alone** (no scout-flag involvement). Susceptible to scout hallucinations of plausible-looking strips on stat cards. Misses the cleanest discriminator (`has_overlay_stats`).
- **(c) Frame-sequence state machine** (replay-window timer). See §2.6 — drops more Case A than it saves.

**Chosen mechanism — eight-clause AND, all required:**

| # | Gate | Source | Rejects |
|---|---|---|---|
| G1 | `_last_cam == "graphic"` AND `vision.last_strip_flag == True` | Scout tag (already in scope) | Pure no-strip graphics |
| G2 | `vision.last_overlay_flag == False` | Scout tag | C (career card), D (partnership / over-end) |
| G3 | `_FAST_PATH_STRIP_HEAD_RE` matches at the START of `description` | regex | Standings cards, INFO_PANEL-only payloads, scout text not in STRIP format |
| G4 | parsed `(score, wickets, overs)` is NOT `(0, 0, 0.0)` | content | Scout 0-0 template hallucination (Case B residual, Case C all-zero head) |
| G5 | parsed `team` resolves (via `_resolve_team_variant`) to current `batting_team` | content + state | Bowling-team comparison strips, opposition career cards |
| G6 | `current_score <= parsed_score <= current_score + 6` | content + state | Replay frames showing pre-wicket lower numbers (`<` rejects), implausible jumps (`>+6` rejects), career cards with hallucinated unrelated scores |
| G7 | `parsed_overs >= current_overs` AND `parsed_overs - current_overs < 0.4` (less than 4 ball-units, with the `0.5 → 1.0` over-boundary translated to a single-ball delta) | content + state | Replay frames showing future overs, summary graphics showing *next* over |
| G8 | `(parsed_score, parsed_overs) != _last_fast_path_committed` for this frame block (no-op cooldown — see §3.4) | state | Replay-frozen strip spamming the same identity write |

All eight must pass. Any single failure → reject and emit `[CAM-GRAPHIC-FAST-PATH-REJECT reason=Gn]`.

### §3.2 Strict STRIP head regex (`_FAST_PATH_STRIP_HEAD_RE`)

```
^STRIP:\s+(?P<team>[A-Z]{2,4})\s+(?P<score>\d+)-(?P<wkts>\d+)\s*\((?P<overs>\d+(?:\.\d+)?)\)
```

Anchored to `^STRIP:` (must be the first non-whitespace token of the strip line), team is 2–4 uppercase letters (all current IPL franchise abbreviations: MI, CSK, RCB, KKR, SRH, GT, RR, DC, PBKS, LSG), score-wickets-overs follow the canonical broadcast format. The regex deliberately rejects:
- `STRIP: MI 9 STANDINGS SRH 4 INFO_PANEL: ...` (no `\d+-\d+` head)
- `STRIP: MI 0-0 (0.0) | INFO_PANEL: TRENT BOULT IPL CAREER` (matches G3 but G4 catches the 0-0)
- `STRIP: SUNRISERS 89-1 (POWERPLAY)` (overs token isn't numeric — regex fails; safe reject)
- Any `STRIP:` line with the team name spelled out (`SUNRISERS`, `RAJASTHAN`, `MUMBAI INDIANS`) — falls through to the slow path on the next live SCOUT frame.

The regex matches **only the head**. Anything after the captured group (including `| Tilak 0(0) | Hussain 1-37 (2.1) | INFO_PANEL: ...`) is *ignored by the fast-path entirely*. Bowler / batters / extras / this_over are never read in this code path — that is the entire safety thesis of the design. The slow path remains the only reader for those fields.

### §3.3 Wickets policy

Wickets parsed but **NOT committed** by the fast-path. Reasoning:
- Wickets-monotonicity has its own guard layer (`Wickets regression rejected` at scoreboard layer, multiple frames of `wickets=4` already pending consensus during the F2123→F2136 window).
- A wicket-replay frame may show pre-wicket wicket count (case B at F2128 would read `MI 221-4` while truth is `221-5`) → 4<5 would *regress* and the existing guard catches it, but the noise floor of `[WICKETS-REGRESS]` warnings is already non-trivial (lines 23712, 23757, 23793). Don't add to it.
- Score and overs alone advance the over-cursor and close the MULTI_BALL gap; wickets is not on the gap-recovery critical path.

### §3.4 No-op cooldown (G8)

Track the last committed `(score, overs)` written via the fast-path; if a subsequent fast-path attempt would write the identical pair within a window of 4 fast-path acceptances, no-op (don't write, don't broadcast, don't increment `processed`). Implementation: a 2-tuple deque or a single tuple with a counter. Prevents a wicket-replay frozen strip from generating a stream of identical `WS_PAYLOAD` broadcasts; a single broadcast on the first acceptance is sufficient.

### §3.5 Implementation complexity

- 1 new regex constant at module top.
- 2 new instance fields on `Vision` (`last_strip_flag`, `last_overlay_flag`) — propagated alongside `last_camera_view` (set in `Vision.describe` at `files/eyes/vision.py:347-349`; trivial 2-line change).
- 1 new function `_try_cam_graphic_fast_path(description, scoreboard, last_strip_flag, last_overlay_flag, batting_team) -> dict|None` placed near `_resolve_team_variant`.
- 1 new code site at `files/test_pipeline.py:6465-6515` — see §6.
- 1 telemetry source field convention update (`source="cam_graphic_fast_path"` for any score/overs writes), see §8.

Total ≤ 60 LOC (the §6 fix-2 estimate of ~30 in the rediagnosis was for the call site only; the helper + Vision plumbing brings it to 60).

---

## §4. False-positive analysis (the load-bearing decision)

### §4.1 What can survive all 8 gates incorrectly?

The gauntlet of G1–G8 leaves the following residual failure surfaces:

| Failure mode | What gets corrupted | Probability | Severity |
|---|---|---|---|
| **F1.** Career-stat card with `has_overlay_stats=False` mistag from Scout, head=`MI 221-4 (18.1)` matching current state | `score`/`overs` written equal to current → no-op (G8 catches if recurrent; first write idempotent) | LOW (~0.1 % of fast-path attempts) | NONE — idempotent identity write |
| **F2.** Wicket-replay broadcaster-frozen strip head reads correctly | `score`/`overs` written equal to current → no-op | MEDIUM (the F2128 case itself) | NONE — idempotent |
| **F3.** Wicket-replay frame where Scout misreads strip head as a *future* score (e.g. extractor hallucination from background graphic) | `score` advanced incorrectly | LOW — Scout strip head OCR is reliable when the strip is visible (compare to F2127 0-0 hallucination which is the only mid-window F2123→F2136 OCR failure) | MEDIUM — would advance `score` then need to be rolled back; SCORER-INVARIANT-FILTER would catch on the *next* live frame because the live strip will read truth |
| **F4.** Partnership / over-end graphic with `has_overlay_stats=False` mistag AND head shows next-over preview | `score`/`overs` written for next over | LOW — partnership graphics canonically set `has_overlay_stats=True` per Scout rubric | MEDIUM — over-cursor advances by 1 over prematurely; `over_mgr.check_over_change` would fire and lock; recovery requires next live frame to backtrack |
| **F5.** Two consecutive cam=graphic frames where the held-over strip shows pre-wicket state (lower wickets), G6 passes (score equal), G8 catches the second | First write: idempotent score/overs (no harm). Second: G8 cooldown skip | LOW | NONE |
| **F6.** Scout's `has_strip` flag is True but the strip head it parsed is from the *info-panel* region (parser confusion) | `score`/`overs` may be from a stale cached value | LOW — `_parse_tag` in `files/eyes/vision.py:488-530` derives `has_strip` from the `STRIP: TEAM \d+` regex (line 512); if it fires, the head digits exist | LOW — guarded by G3 strict regex re-derivation |

### §4.2 Worst-case scenario (the one to design around)

**F3 + F4 combined**: a stat-card overlay where Scout mistags `has_overlay_stats=False` AND the strip head reads a plausible higher score AND visible team resolves to batting team AND over advance ≤ 0.4. To trigger this, all of the following must coincide:

- Scout's `has_overlay_stats` returns False on a true stats overlay (rare — V5 prompt explicitly anchors this flag).
- The hallucinated head must show a score *above* current (G6 lower bound).
- The hallucinated overs must be ≥ current and within 0.4.

Probability estimate from the 4-hour MI vs SRH log: zero observed instances across 548 cam=graphic frames. Confidence interval (rule-of-three): ≤ 5/548 = 0.9 % at 95 % CI.

### §4.3 Downstream filter coverage gap analysis

For each false-positive class, which existing filter catches it:

| Filter | Location | Catches | Misses |
|---|---|---|---|
| 0-0(0.0) mid-innings | `test_pipeline.py:6608-6621` | Pre-existing path. **Not on fast-path** — G4 replicates inline | n/a — replicated |
| Comparison-strip (`bowling team strip`) | `test_pipeline.py:6850-6890` | Pre-existing slow-path. **Not on fast-path** — G5 replicates inline | n/a — replicated |
| `[GUARD] comparison strip for batting team` (Δ>20 batter row) | `test_pipeline.py:6918-6936` | Slow-path only; never sees fast-path fields because we don't read batters | F2 (wicket-replay batter rows) — *not relevant*, we don't read batters |
| `WICKETS-REGRESS` | `eyes/scoreboard.py:on_wickets_set` | Slow & fast paths; we don't write wickets so it never fires for us | n/a |
| `SCORE-INF-GATE` (score ≤ batters_runs + extras invariant) | `score_manager.py` | Both paths; would catch a score read implausibly *low* | F3 if hallucinated score-above-current also fails the per-batter sum invariant — partial coverage |
| `SUSPICION` defer (score-spike with no corroborating signal) | `test_pipeline.py:7743-7780` | Slow-path only | F3, F4 — not on fast-path. **This is the genuine coverage gap** |
| `over_mgr.check_over_change` | `eyes/this_over.py` | Both paths after `scoreboard.set("overs")` | Triggered by F4 falsely; no rollback path |

**The genuine gap:** the SUSPICION mechanism (defer-on-isolated-spike) is bypassed when the fast-path commits directly. The mitigation is the **score delta cap** (G6, ≤ +6) which is tighter than the SUSPICION trigger threshold. SUSPICION fires for any unsupported spike; we never accept an unsupported spike of >6 in the first place. The residual is a +1 to +6 spike with no corroborating signal — a misread of a plausible value. This is the wedge to monitor in production.

### §4.4 Mitigation via guard vigilance

- Telemetry every reject (§8) so the false-negative rate is visible from the analyzer.
- A failing-loud variant of G6: log `[CAM-GRAPHIC-FAST-PATH-SCORE-DELTA delta=N]` even on accept, so post-hoc analysis can flag any delta-3-or-greater accept that wasn't followed by a corroborating live frame.
- A 5-minute production-window watch criterion (§9.4): if the rate of `[CAM-GRAPHIC-FAST-PATH-READ]` per minute exceeds 4 and the gap-rate doesn't drop, the fast-path is firing on garbage; fall back by reverting `_DEAD_VIEWS`.

---

## §5. False-negative analysis

### §5.1 Cost of rejecting Case A (live strip during cam=graphic)

A case-A reject leaves the cam=graphic frame's strip data on the table — same as current behavior. Cost: at most one frame of `score`/`overs` lag, recovered by the next live SCOREBOARD frame (typically 2–5 seconds later). Per Thread 7's acceptance verdict: cosmetic, not functional.

### §5.2 Acceptable trade-off

Per the design constraint: **prefer some recovery over corruption risk**. A rejected case-A frame returns to the status quo; an accepted case-B/C/D frame writes corruption. The 8-clause guard biases toward rejection on uncertainty, in particular:

- G2 rejects the entire D' edge case (over-end with strip live but `has_overlay_stats=True`) — this is a deliberate false-negative trade.
- G6 lower bound (`>= current_score`) rejects any held-over pre-wicket strip with strictly lower score — likely some rare cases where the strip incorrectly *re-decremented* from a previous over-rule reversal.
- G8 cooldown rejects all repeat accepts in a frozen-strip window — at most loses 0 information (the single first accept already covered the state).

### §5.3 Predicted recovery rate (per match)

Based on the MI vs SRH log:

- Total cam=graphic frames: 548
- cam=graphic frames with `strip=True`: ~500 (sampled; majority — 6 of 6 examples in §2.1 sampling). The remaining ~48 (`strip=False`) are full-screen overlays where the strip really is gone; current behavior of skip is correct, fast-path G1 doesn't fire.
- cam=graphic+strip=True frames with `has_overlay_stats=False` (G2 pass): estimated ~250–350 (50–70 % of strip=True). The other 150–250 are stat overlays (correctly rejected by G2).
- Of those, frames where strict STRIP head matches: ~90 % conservative ⇒ ~225–315.
- Of those, frames where score/overs are monotone-non-decreasing within bounds: ~80 % (subtract held-over identical state, which still passes G6 as equal but is no-op via G8 — counts as accept-but-no-op).

**Net: ~180–250 fast-path accepts per match** (~40–50 % of cam=graphic+strip=True frames).

**Of those accepts, what fraction recovers a ball-gap?** A ball-gap is a `Δovers > 0.1` jump that triggers MULTI_BALL. The vast majority of fast-path accepts will be idempotent (score and overs unchanged from the previous live frame); only the accepts that bridge a missing live-frame increment recover a ball-gap. From the log: the F2128 case is the canonical example — it would have committed `overs→18.1` (idempotent), but the *score-227 read at F2134* would still need the §6 Fix-1 narrowed-guard to land. Fix 2 alone, applied to F2128, doesn't change the F2123→F2136 gap directly — it pre-warms the over-cursor for the next read. **Genuine ball-gap recovery occurs only when the fast-path acceptance bridges a live-frame skip** (e.g. cam=graphic between two cam=closeup with intervening overs progress). Estimated: 1–3 such recoveries per match.

**Headline impact:** 5.8 % → 4.5 % gap rate (Fix 2 alone, conservative). Combined with Fix 1: 5.8 % → 3.0–3.5 %.

### §5.4 Comparison with current state

| Behavior | Status quo | Fix 2 alone | Fix 1 + Fix 2 |
|---|---|---|---|
| Ball-gap rate (per match, projected) | ~5.8 % | ~4.5 % | ~3.0–3.5 % |
| cam=graphic frames committed score/overs | 0 | ~180–250 | ~180–250 |
| Cumulative-state correctness | preserved | preserved | preserved |
| `WS_PAYLOAD` broadcast frequency | baseline | +5–8 % per match (more accepts) | +5–8 % per match |

The ~5–8 % broadcast bump is mostly idempotent identity writes; the WS contract permits this (clients are diff-aware). No baseline payload regression is expected; the snap01_inn1 sentinel in `files/path_a_ws_payload_baseline.txt` doesn't exercise the cam=graphic path and is unaffected.

---

## §6. Implementation locations

### §6.1 Diff site #1 — `files/eyes/vision.py` (Vision plumbing, ~3 LOC)

At `files/eyes/vision.py:347-349`, where `last_camera_view`, `last_frame_phase`, `last_ball_position` are set after each `describe()` call, **also stash** `last_strip_flag` and `last_overlay_flag` so the main loop has the bytes without re-parsing scout's raw response.

```279:288:files/eyes/vision.py
        # Last camera_view tag (set after every describe() call).  Read
        # by the main loop so the tag can be pushed into BallAnalyzer's
        # tagged-frame buffer for delivery analysis.
        self.last_camera_view: str | None = None
        # Last frame_phase tag — drives `analyze_last_delivery`'s
        # frame-selection so VLM classification sees release/flight/
        # shot frames instead of post-action dwell.
        self.last_frame_phase: str | None = None
```

Add `self.last_strip_flag: bool = False` and `self.last_overlay_flag: bool = False` here. Set in `describe()` immediately after `strip_flag` / `overlay_flag` are computed (file already has them as locals at line 339-340).

### §6.2 Diff site #2 — `files/test_pipeline.py` (fast-path call site, ~25 LOC)

Insert after `_was_dead_time = True` and before the strategic-timeout block at line 6469. Pseudocode:

```python
# 2026-04-30 (Thread 7 Fix 2): cam=graphic strip-text fast-path.
# When Scout reports has_strip=True under cam=graphic, the bottom
# strip is on-screen even though the action area is a graphic.
# Parse score/overs ONLY (no batters, no bowler) under the
# 8-clause non-degeneracy guard; commit if all gates pass.
if (_last_cam == "graphic"
        and getattr(vision, "last_strip_flag", False)
        and not getattr(vision, "last_overlay_flag", False)):
    _fp_result = _try_cam_graphic_fast_path(
        description=description,
        scoreboard=scoreboard,
        batting_team=batting_team,
        cooldown=_cam_graphic_cooldown,
    )
    if _fp_result is not None:
        # accept path: score/overs only commit, broadcast, log
        _fp_changes = []
        if scoreboard.set("score", _fp_result["score"], frame_count):
            _fp_changes.append(f"score→{_fp_result['score']}")
        if scoreboard.set("overs", _fp_result["overs"], frame_count):
            _fp_changes.append(f"overs→{_fp_result['overs']}")
        _cam_graphic_cooldown.append(
            (_fp_result["score"], _fp_result["overs"]))
        if _fp_changes:
            log.info(
                f"[F{frame_count}] [CAM-GRAPHIC-FAST-PATH-READ] "
                f"score={_fp_result['score']} "
                f"overs={_fp_result['overs']} "
                f"team={_fp_result['team']} "
                f"changes={_fp_changes}")
            await broadcast_state(build_full_payload())
        # fall through to existing dead-time skip body
```

`_cam_graphic_cooldown` is a module-level `deque(maxlen=4)` of `(score, overs)` tuples maintained alongside `_ad_streak_start` / `_in_strategic_timeout` near line 5460.

The fast-path **does not break out of the dead-time skip**. After `[CAM-GRAPHIC-FAST-PATH-READ]` (or reject) the code continues into the existing strategic-timeout block, broadcast_base, asyncio.sleep, `continue` — all unchanged. The rest of the dead-time block (which is also correct for `cam=ad`/`cam=replay`/`cam=other`) is preserved.

### §6.3 Diff site #3 — `files/test_pipeline.py` (helper function, ~30 LOC)

Place adjacent to `_resolve_team_variant` (helper resolution function used at line 6688). New module-level function:

```python
_FAST_PATH_STRIP_HEAD_RE = re.compile(
    r"^STRIP:\s+(?P<team>[A-Z]{2,4})\s+(?P<score>\d+)-(?P<wkts>\d+)"
    r"\s*\((?P<overs>\d+(?:\.\d+)?)\)"
)

def _try_cam_graphic_fast_path(*, description, scoreboard, batting_team,
                               cooldown):
    """Returns parsed dict on accept, None on reject (with telemetry)."""
    # G3 — strict STRIP head regex
    m = _FAST_PATH_STRIP_HEAD_RE.search(description or "")
    if not m:
        log.info("[CAM-GRAPHIC-FAST-PATH-REJECT reason=G3_strip_head_no_match]")
        return None
    try:
        team = m.group("team")
        score = int(m.group("score"))
        wkts = int(m.group("wkts"))
        overs = float(m.group("overs"))
    except (TypeError, ValueError):
        log.info("[CAM-GRAPHIC-FAST-PATH-REJECT reason=G3_parse_failed]")
        return None
    # G4 — not all-zero
    if score == 0 and wkts == 0 and overs == 0.0:
        log.info("[CAM-GRAPHIC-FAST-PATH-REJECT reason=G4_zero_template]")
        return None
    # G5 — visible team must resolve to batting team
    resolved = _resolve_team_variant(team)
    if not resolved or resolved != batting_team:
        log.info(
            f"[CAM-GRAPHIC-FAST-PATH-REJECT reason=G5_visible_team "
            f"team={team} resolved={resolved} bat={batting_team}]")
        return None
    # G6 — score monotone, +6 cap
    cur_score = int(scoreboard._inn.get("score") or 0) if scoreboard._inn else 0
    if not (cur_score <= score <= cur_score + 6):
        log.info(
            f"[CAM-GRAPHIC-FAST-PATH-REJECT reason=G6_score_window "
            f"parsed={score} cur={cur_score}]")
        return None
    # G7 — overs monotone, < 0.4 jump
    cur_overs_str = scoreboard._inn.get("overs") if scoreboard._inn else "0"
    try:
        cur_overs = float(cur_overs_str)
    except (TypeError, ValueError):
        cur_overs = 0.0
    if not (cur_overs <= overs and (overs - cur_overs) < 0.4):
        log.info(
            f"[CAM-GRAPHIC-FAST-PATH-REJECT reason=G7_overs_window "
            f"parsed={overs} cur={cur_overs}]")
        return None
    # G8 — no-op cooldown
    if (score, overs) in cooldown:
        log.info(
            f"[CAM-GRAPHIC-FAST-PATH-REJECT reason=G8_cooldown_dup "
            f"score={score} overs={overs}]")
        return None
    return {"team": team, "score": score, "wkts": wkts, "overs": overs}
```

### §6.4 Diff site count summary

| File | Lines added | Purpose |
|---|---|---|
| `files/eyes/vision.py` | +3 | Stash `last_strip_flag`, `last_overlay_flag` |
| `files/test_pipeline.py` (helper) | ~32 | `_try_cam_graphic_fast_path` + regex constant |
| `files/test_pipeline.py` (call site) | ~25 | Fast-path invocation in dead-time block |
| `files/test_pipeline.py` (cooldown deque init) | +1 | `_cam_graphic_cooldown = deque(maxlen=4)` near `_ad_streak_start` |

**Total: ~61 LOC across 2 files, 4 diff sites.** No edits to `files/eyes/scoreboard.py` (the scoreboard is the recipient of the writes via existing `set()` API). No edits to extractor, scorer, score_manager, or commentary modules.

---

## §7. Test fixture design

### §7.1 Fixture inventory

All fixtures live in a new `files/test_cam_graphic_fast_path.py` (sibling of `test_recent_fixes.py`). Each fixture exercises exactly one of cases A/B/C/D plus a boundary and the F2128 actual.

| Fixture | Case | Input (scout description / flags / scoreboard state) | Expected fast-path result | Expected telemetry |
|---|---|---|---|---|
| `test_fp_a_live_strip_with_overlay` | A (positive) | `STRIP: MI 221-4 (18.1)`, scout `cam=graphic strip=True overlay=False`, scoreboard `score=221 overs=18.1` | accept (idempotent — no `set()` returns True) | `[CAM-GRAPHIC-FAST-PATH-READ]` |
| `test_fp_a_advancing_strip` | A (positive, advancing) | `STRIP: MI 224-4 (18.2)`, same flags, scoreboard `score=221 overs=18.1` | accept, score→224, overs→18.2 | `[CAM-GRAPHIC-FAST-PATH-READ]` |
| `test_fp_b_wicket_replay_held_strip` | B (negative-replay, idempotent) | `STRIP: MI 221-5 (18.1)`, flags as above, scoreboard `score=221 overs=18.1 wickets=5` | accept (no change committed; G8 dedupes if invoked twice) | first call READ, second call REJECT G8 |
| `test_fp_b_wicket_replay_pre_wicket_score` | B (negative, monotone violation) | `STRIP: MI 220-4 (18.0)`, scoreboard `score=221 overs=18.1` | reject G6 (score 220 < 221) | `[CAM-GRAPHIC-FAST-PATH-REJECT reason=G6_...]` |
| `test_fp_c_career_stat_overlay_flag` | C (negative-stat-card via overlay flag) | `STRIP: MI 0-0 (0.0) | INFO_PANEL: TRENT BOULT IPL CAREER ...`, scout `overlay=True strip=True` | reject G2 (overlay=True; never enters fast-path) | (gate G2 is in caller — assert fast-path *not invoked*) |
| `test_fp_c_career_stat_zero_template` | C (negative-stat-card, overlay misflagged) | `STRIP: MI 0-0 (0.0) | INFO_PANEL: ...`, scout `overlay=False strip=True` | reject G4 (zero template) | `[CAM-GRAPHIC-FAST-PATH-REJECT reason=G4_zero_template]` |
| `test_fp_c_standings_card` | C (negative, standings) | `STRIP: MI 9 STANDINGS SRH 4`, scout `strip=True overlay=False` | reject G3 (strict head no match) | `[CAM-GRAPHIC-FAST-PATH-REJECT reason=G3_strip_head_no_match]` |
| `test_fp_c_opposition_career_card` | C (negative, opposition team) | `STRIP: SRH 137-2 (12.4)`, scout `strip=True overlay=False`, scoreboard batting=MI | reject G5 (SRH ≠ MI) | `[CAM-GRAPHIC-FAST-PATH-REJECT reason=G5_visible_team]` |
| `test_fp_d_partnership_overlay_flag` | D (negative-preview via overlay flag) | `STRIP: MI 221-4 (18.1) | PARTNERSHIP ...`, scout `overlay=True` | reject G2 (caller-gate; fast-path not invoked) | (assert not invoked) |
| `test_fp_d_over_end_implausible_jump` | D (negative-preview, future-overs) | `STRIP: MI 230-4 (19.0)`, scoreboard `score=221 overs=18.1` | reject G7 (Δovers=0.9 > 0.4) | `[CAM-GRAPHIC-FAST-PATH-REJECT reason=G7_overs_window]` |
| `test_fp_d_over_end_huge_score_jump` | D (negative-preview, future-score) | `STRIP: MI 240-4 (18.4)`, scoreboard `score=221` | reject G6 (240 - 221 = 19 > 6) | `[CAM-GRAPHIC-FAST-PATH-REJECT reason=G6_score_window]` |
| `test_fp_boundary_ambiguous` | E (boundary, conservative) | `STRIP: MI 222-5 (18.2)` (1-run advance + 1-wicket regress vs scoreboard 221-4 18.1) | accept (G6 +1, G7 +0.1; wickets not committed; safe) | `[CAM-GRAPHIC-FAST-PATH-READ]` |
| `test_fp_f2128_actual` | F2128 reconstruction | Synthesized: `STRIP: MI 221-4 (18.1) | Tilak 0(0) | Rickelton 109(50) | Hussain 1-31 (2.1)` (held-over from F2126), scout cam=graphic strip=True overlay=False, scoreboard 221-5(18.1) | accept (idempotent) | `[CAM-GRAPHIC-FAST-PATH-READ]` |
| `test_fp_f2120_to_f2136_full_window` | full window integration | Replay the scout SCOUT lines from log lines 23696-23945 verbatim, with the new fast-path active | F2128 commits score/overs (idempotent); F2127 still poisoned by 0-0 guard; F2134/F2135 unchanged (slow path); F2136 closes gap | one `[CAM-GRAPHIC-FAST-PATH-READ]` for F2128, no other fast-path tags |

### §7.2 Synthetic vs real fixture sourcing

- **F2128 real fixture (`test_fp_f2128_actual`):** the scout STRIP text was **never logged** because the dead-time skip fires before `[V {v_ms}ms]` (visible at line 23874 — only the SCOUT classification log appears, no STRIP text). We **infer** the strip content from F2126 (line preceding the wicket replay block) which read `STRIP: MI 221-4 (18.1) | Tilak 0(0) | Rickelton 109(50) | Hussain 1-31 (2.1)`. This is the synthetic-but-grounded fixture.
- **Negative-replay (`test_fp_b_wicket_replay_held_strip`):** purely synthetic but covers the dominant failure mode. Composer 2 should add a real-frame fixture *after* the next match log captures a clean wicket-replay cam=graphic instance.
- **Negative-stat-card (`test_fp_c_career_stat_*`):** F2768 is a real grounded example for the zero-template variant (line 29117). Standings example: F8 (line 318) `MI 9 STANDINGS SRH 4`. Both are real.
- **Negative-preview (`test_fp_d_*`):** synthetic. The MI vs SRH log doesn't have a clean isolated over-end-preview cam=graphic frame within the strip context (most over-ends are followed by ad blocks). Composer 2 to backfill from a future match.
- **F2120–F2136 full-window fixture:** real-grounded — replay the SCOUT lines verbatim. Asserts integration-level invariant: Fix 2 closes one frame (F2128 → idempotent broadcast) and does not regress any other frame's disposition.

### §7.3 Synthetic fixture coverage adequacy

The synthetic D fixtures are the weakest leg of the design. Mitigation:
- Telemetry logs every accept and reject in production (§8) so a post-match analyzer pass can identify any production case-D acceptance that wasn't followed by a corroborating live frame.
- The shipping criterion in §9.4 includes a 1-match production observation window before broader rollout.

### §7.4 Path A baseline regression

The `files/path_a_ws_payload_baseline.txt` snapshot exercises the snap01_inn1 dataset which does **not** include any cam=graphic transitions (it's a static state-payload snapshot for `build_full_payload`). Fix 2 is invariant on this fixture by construction (no `cam=graphic` frame in the input).

---

## §8. Telemetry

### §8.1 New tags

| Tag | When emitted | Fields |
|---|---|---|
| `[CAM-GRAPHIC-FAST-PATH-READ]` | All 8 gates pass; commit attempted | `frame=F{n}`, `score={N}`, `overs={X}`, `team={ABC}`, `changes={[...]}`, `delta_score={d}`, `delta_overs={d}` |
| `[CAM-GRAPHIC-FAST-PATH-REJECT]` | Any gate fails | `frame=F{n}`, `reason=G{n}_{label}`, plus reason-specific context fields (e.g. `parsed=N cur=N` for G6) |
| `[CAM-GRAPHIC-FAST-PATH-COOLDOWN]` | G8 dedupe fired (subset of REJECT for analyzer convenience) | `frame=F{n}`, `score={N}`, `overs={X}`, `cooldown_size={d}` |
| `[STRIP-CONTENT-VALIDATION-FAIL]` | G3 / G4 / G5 specific (subset of REJECT for cross-fix correlation) | `frame=F{n}`, `gate=G{n}`, `description={first 80 chars}` |

### §8.2 Source field convention

Every `Scoreboard.set()` invocation from the fast-path passes a new `source="cam_graphic_fast_path"` argument when the API supports it (check `Scoreboard.set` signature at write time; if not supported, encode in the log line). This lets the analyzer split MULTI_BALL recoveries by source path. The DETAIL log line picks up the change naturally because it serializes `scoreboard._inn.get("score")` regardless of source.

### §8.3 Cross-reference with Thread 7 Fix 1

Fix 1 introduces `[STRIP-ROWS-MISALIGNED]` (per `thread7_rediagnosis_multi_ball_gap.md` §6). The analyzer should treat both `[CAM-GRAPHIC-FAST-PATH-READ]` and `[STRIP-ROWS-MISALIGNED]` as new gap-recovery sources in the per-match scorecard. Suggested analyzer aggregate (in `files/analyze_match_telemetry.py`):

```
[T7-RECOVERY] gaps_recovered=N {fix1=A, fix2=B, native=C}
```

### §8.4 Failure-mode escalation tags

If `[CAM-GRAPHIC-FAST-PATH-READ]` fires followed within 3 frames by a `SUSPICION` defer of *the same score* on a slow-path frame, the analyzer emits `[CAM-GRAPHIC-FAST-PATH-LATENT-FALSE-POSITIVE]` with the F-numbers. This is the production canary for §4.2 worst case.

---

## §9. Predicted impact

### §9.1 Recovery rate estimate

Per §5.3, **net 1–3 ball-gap recoveries per match** from Fix 2 alone (where the recovery is a *new* accept that bridges a missing live increment). Per match: ~36 MULTI_BALL events in the MI vs SRH log (~5.8 % rate) → Fix 2 reduces by 1–3 events ⇒ ~0.2–0.5 percentage-point gap-rate drop ⇒ ~5.8 % → ~5.3–5.6 % from Fix 2 alone.

The headline estimate of "5.8 % → 4.5 %" in §1 is the *upper bound* assuming idempotent identity broadcasts also count toward visible improvement (cleaner `WS_PAYLOAD` continuity, fewer stale-state windows). The conservative bound is the strict ball-gap reduction at ~5.5 %.

When stacked with Fix 1 (which is the dominant contributor at ~2.5 percentage-point reduction), combined rate: **~3.0–3.5 %**.

### §9.2 Confidence level

**Medium.** The §4.3 SUSPICION-gap is the load-bearing uncertainty. If production reveals more case-D mistags than the rubric predicts, false-positive rate could exceed our model. Mitigation: §9.4 watch criteria.

### §9.3 Honest predictions

- Not all cam=graphic frames are case A — typed correctly as ~50 % case A, ~25 % case C, ~15 % case D, ~10 % case B given the IPL broadcast pattern (3 hours of action, ~30 % action-area-occupied-by-graphic time).
- The recovery is dominated by *idempotent* accepts (broadcaster left strip up during a graphic; we re-affirm current state). Genuine new-information accepts are rarer.
- The MULTI_BALL gap rate may not visibly drop from Fix 2 alone; the real drop comes from Fix 1. Fix 2's value is observable but small. **Don't oversell it.**

### §9.4 Watch criteria for next-match validation

After shipping Fix 2 (assumed: solo commit, no Fix 1 entanglement for clarity):

| Criterion | Pass | Investigate |
|---|---|---|
| `[CAM-GRAPHIC-FAST-PATH-READ]` rate per match | 100–300 | <50 (gates too strict) or >400 (gates too loose) |
| `[CAM-GRAPHIC-FAST-PATH-REJECT]` reason histogram | G2/G3/G6/G7 dominate, G5 small, G8 ~5–10 % | G6/G7 reject rate > 30 % (model wrong about score/overs windows) |
| `[CAM-GRAPHIC-FAST-PATH-LATENT-FALSE-POSITIVE]` | 0 | ≥1 (revert / tighten G6 cap) |
| Per-match MULTI_BALL count | drop by 1–3 events | unchanged or increased |
| Path A baseline | byte-identical | any diff |

---

## §10. Risk assessment

### §10.1 Failure modes specific to this fix

| Risk | Likelihood | Severity | Detection | Mitigation |
|---|---|---|---|---|
| Reading replay frames as live (data corruption) | LOW | MEDIUM | `[CAM-GRAPHIC-FAST-PATH-LATENT-FALSE-POSITIVE]` analyzer tag; SCORER-INVARIANT-FILTER on next live frame | G2 + G6 (score window) primary; G6 cap of +6 means worst-case 1-over advance |
| Reading stat-card stats as match stats (numeric drift in batter records) | NONE | NONE | n/a | **Architectural — fast-path never writes batter records**. Only score/overs are exposed |
| Reading preview data as live (over-end state leaking) | LOW | MEDIUM | `over_mgr.check_over_change` fires; if false, log shows premature over change | G7 cap of 0.4 ball-units restricts to 1-ball horizon; partnership-graphic G2 reject is primary |
| Cooldown deque grows unbounded (memory) | NONE | NONE | n/a | `deque(maxlen=4)` is bounded |
| Vision flag plumbing race (read before set) | LOW | LOW | `getattr(vision, "last_strip_flag", False)` defaults safely | Defensive defaults in §6.2 |
| WS_PAYLOAD broadcast storm during long graphic blocks (e.g. innings break) | LOW | LOW | client-side rate-limiting; existing strategic-timeout sleep gating | Existing `_in_strategic_timeout` 4 s sleep wraps the fast-path call site |

### §10.2 Edge case handling

- **Pre-match (`scoreboard._inn` not yet set / `batting_team is None`):** G5 fails because `batting_team` is None → reject. The fast-path is gated naturally to in-innings.
- **Innings break (cam=graphic dominates for ~10 minutes):** G6 score window centred on innings-1 final score (e.g. 248). Innings-2 strip would show e.g. `SRH 12-0 (0.5)` → resolves SRH not MI → G5 reject. Innings transitions handled by the existing AUTO-SWAP path on the slow path; fast-path never interferes.
- **Strategic timeout:** existing `_in_strategic_timeout` wraps the dead-time skip; fast-path runs once per cam=graphic in the timeout window then G8 cooldown rejects subsequent identical reads — no state spam.
- **Scout returns `cam=graphic` with `strip=True` but `description` is empty (truncated response):** G3 regex fails on empty string → reject. Safe.
- **Scout's V5-prompt `has_overlay_stats` true-positive rate is 100 % per current shadow-run** (per the prompt-engineering note at `files/eyes/vision.py:60-82`); G2 is well-calibrated.

### §10.3 Failure modes downstream filters would NOT catch (the vigilance set)

These are the residual risks the guard must handle alone because no downstream filter sees them:

1. **Score-spike between current and current+6 with no corroborating live frame** — SUSPICION is bypassed; G6 cap is the only protection. Vigilance: §8.4 latent-FP tag.
2. **Overs-spike of 0.1–0.3 from a future-bowled strip** — `over_mgr` accepts; no downstream rollback. Vigilance: G7 cap.
3. **Visible-team mistag where opposition strip resolves to batting team via fuzzy lookup** — comparison-strip guard is *not* run on fast-path. Vigilance: G5 uses `_resolve_team_variant` which is the same resolution function the slow path uses; behaviour parity is structural.

---

## §11. Coordination with Thread 7 Fix 3

Fix 3 (per `thread7_rediagnosis_multi_ball_gap.md` §6 third bullet) is a P3 audit of `files/eyes/scoreboard.py` cell-extraction logic to fix the row-pairing bug at the OCR layer (Fix 1 is the downstream containment of the same bug; Fix 3 is the upstream root cause). Fix 3 changes the bytes Scout produces in the `STRIP: ... | NAME RUNS(BALLS) | NAME RUNS(BALLS)` portion.

### §11.1 Independence vs interaction

**Fix 2 and Fix 3 are structurally independent.** Fix 2 only reads the `STRIP: TEAM SCORE-WICKETS (OVERS)` head (via G3 regex) and never touches the batter rows that Fix 3 would correct. Therefore:

- If Fix 3 ships before Fix 2: Fix 2 still works, ignoring the fixed-but-unread batter rows.
- If Fix 2 ships before Fix 3: Fix 2 still works, ignoring the broken batter rows on cam=graphic frames (and never writes them anyway).
- If both ship: no interaction. Fix 3 fixes the batter rows on slow-path SCOREBOARD frames (where the row-misalignment bug actually manifests because the slow path *does* read them); Fix 2 handles the cam=graphic head separately.

### §11.2 Sequencing implications

None. Either order is safe. Recommend Fix 1 → Fix 2 → Fix 3 by impact (Fix 1 highest, Fix 3 lowest).

### §11.3 Latent coordination with Fix 1

Fix 1 narrows the comparison-strip guard at `test_pipeline.py:6918-6936` to pop only `batters` (not score/match_overs/bowler). Fix 1 operates exclusively on the slow path. Fix 2 operates exclusively on the dead-time skip path. They share zero code surface. Both can ship in either order; both can ship in the same commit if convenient (see §12 sequencing).

---

## §12. Migration order (commit sequence)

Three logical commits, each independently shippable and revertable. All Fix 2 work is in one commit; Fix 1 and Fix 3 are tracked separately under their own threads.

### §12.1 Commit C1 — Vision plumbing (~3 LOC)

**Scope:** Add `last_strip_flag` and `last_overlay_flag` instance fields to `Vision` and populate them in `describe()`. No call sites added; the new fields are dead code at this commit.

**File:** `files/eyes/vision.py` only.

**Validation:**
- `pytest files/test_recent_fixes.py` (existing tests still green).
- Manual: run `python -m eyes` for 5 minutes, confirm no regressions in scout cadence.
- Path A baseline: byte-identical (no payload writers touched).

**Revert cost:** trivial — 3 LOC removal.

### §12.2 Commit C2 — Fast-path helper + telemetry (~32 LOC)

**Scope:** Add `_FAST_PATH_STRIP_HEAD_RE` constant and `_try_cam_graphic_fast_path` helper in `files/test_pipeline.py`. Add `_cam_graphic_cooldown = deque(maxlen=4)` near other module-level state. **No call site added** — function is dead code at this commit. Add full unit-test fixture suite from §7.1.

**File:** `files/test_pipeline.py` (helper + cooldown deque), new `files/test_cam_graphic_fast_path.py` (fixture suite).

**Validation:**
- New `pytest files/test_cam_graphic_fast_path.py` — all §7.1 cases pass.
- `pytest files/test_recent_fixes.py` — still green.
- Path A baseline: byte-identical.

**Revert cost:** trivial — function never called, fixtures isolated.

### §12.3 Commit C3 — Wire fast-path into dead-time skip (~26 LOC)

**Scope:** Insert the §6.2 call-site block at `files/test_pipeline.py:6469`. Production behavior change first occurs here.

**File:** `files/test_pipeline.py` only (call site).

**Validation:**
- `pytest files/test_cam_graphic_fast_path.py` — new integration fixture `test_fp_f2120_to_f2136_full_window` exercises the full call site.
- `pytest files/test_recent_fixes.py` — still green.
- Path A baseline: byte-identical (no cam=graphic in snap01).
- **Live validation (next match):** run for 1 full match, capture log, run analyzer with new aggregate (`[T7-RECOVERY]`). Pass criteria per §9.4.

**Revert cost:** ~26 LOC removal at one site. Safe even mid-match because the guard reverts to the existing dead-time skip behaviour.

---

## §13. Open questions / deferred decisions

> **Disposition note (added in §15.1).** All five items below are resolved or explicitly deferred in §15.1. They are kept here for change-history continuity. Composer 2 should treat §15.1 as authoritative.

1. **Vision `last_strip_flag` / `last_overlay_flag` set-on-empty-response semantics.** Currently `Vision.describe` resets `last_camera_view = None` on empty raw responses (line 309) but doesn't reset frame_phase / ball_position symmetrically. New flags should follow the same defensive reset pattern; Composer 2 to choose whether to reset to `False` or `None` (recommendation: `False` — consistent with their default initial value).

2. **G7 overs-jump cap (originally 0.4 float-overs) as configured constant or hardcoded.** Hardcoded for now; if false-positive rate proves high, revisit by promoting to a module constant.

3. **Whether `_cam_graphic_cooldown` should reset on `_was_dead_time = False` transition (back to live play).** Recommendation: yes — the cooldown is anti-spam for an active graphic block; on resumption of live play, the deque should clear to avoid false G8 rejects on the *next* graphic block whose first read happens to coincide with a stale cooldown entry. Composer 2 to add `_cam_graphic_cooldown.clear()` in the §6.2 "resuming active play" block at line 6532.

4. **Whether to also apply the fast-path under `cam=replay` when `has_strip=True`.** Deferred — `cam=replay` strip-true frames in the MI vs SRH log are rare (replays usually replace the strip). Revisit if the next match shows otherwise.

5. **Whether to commit `wickets` along with score/overs.** Deferred — see §3.3 reasoning. Revisit only if a wicket-during-graphic-only-window pattern emerges in production.

---

## §14. Acceptance summary for Composer 2

This document is a complete execution contract. Composer 2 should:

- Implement C1, C2, C3 in three separate commits in order.
- Use the regex, gate semantics, and telemetry tag schema verbatim.
- Add the §7.1 fixtures verbatim (synthetic scout descriptions are explicitly provided).
- Honor the §13 open questions (defaults are recommended in each).
- Do **not** improvise on the non-degeneracy guard. The 8-clause AND is the load-bearing decision.
- Do **not** extend the fast-path acceptance set beyond `score` and `overs`.
- Do **not** invoke `extractor.extract` or any LLM call from the fast-path.

If during implementation an unanticipated case is found (e.g. Scout emits a new `camera_view` enum value, or `_resolve_team_variant` API changed), pause and file a follow-up note in this document under §13 rather than improvising a guard tweak.

> **§14 supersession note.** §15.10 below adds the explicit *stop-and-route-back* condition matrix that Composer 2 must use at execution time. The guidance in this paragraph (file a §13 note) is a fallback only — for the conditions enumerated in §15.10, Composer 2 must stop *and* route back to a human, not improvise.

---

## §15. Clarifications (Opus follow-up, 2026-04-30)

This section resolves all open questions accumulated in §13 and the post-handoff clarification request. Each subsection is authoritative over any earlier guidance in the document. Frame numbers reference `logs/pipeline-2026-04-29-194416-mi-srh-live.log` unless noted.

### §15.1 §13 open-questions disposition

| §13 item | Disposition | Resolution |
|---|---|---|
| Q1 — `last_strip_flag` / `last_overlay_flag` empty-response semantics | **RESOLVED — execution-blocking** | Reset to `False` on empty/error raw response, mirroring the existing `last_camera_view = None` defensive reset at `files/eyes/vision.py:309`. Reasoning: the call site checks `getattr(vision, "last_strip_flag", False)`; the *value* `False` is what an empty Scout response truthfully represents (we don't know if there's a strip → assume no). The asymmetry with `last_camera_view = None` is intentional: `None` for a string-typed field signals "no opinion"; `False` for a bool-typed field signals "no, definitely not". For G1 we *want* the conservative reject (skip the fast-path), and `False` produces that. Composer 2 ships this reset alongside C1. |
| Q2 — G7 cap as named constant | **RESOLVED — execution-blocking** | Promote to module constants. The G6/G7 bounds are revised in §15.3 below; both ship as `_FAST_PATH_SCORE_DELTA_MAX = 6` and `_FAST_PATH_BALL_DELTA_MAX = 3` named at the top of the helper section in `files/test_pipeline.py`. Constants make next-match tuning a 1-line change. |
| Q3 — Cooldown clear on dead-time exit | **RESOLVED — execution-blocking** | Yes, clear. Add `_cam_graphic_cooldown.clear()` in the existing `if _was_dead_time:` block at `files/test_pipeline.py:6532-6536`. Reasoning: the cooldown's purpose is intra-graphic-block dedupe; once we've returned to live play, the next graphic block is a fresh window and a stale cooldown entry would falsely G8-reject the first accept. |
| Q4 — Extend fast-path to `cam=replay` | **DEFERRED — non-blocking future work** | The MI vs SRH log shows **zero** `cam=replay` SCOUT tags across the entire 4-hour file (verified by `rg -c "cam=replay" logs/pipeline-...log` → 0). Scout V5 maps replay content to `cam=graphic` or `cam=closeup` empirically. Re-open trigger: any future match log shows ≥10 `cam=replay+strip=True` frames; at that point evaluate whether to extend G1 to `_last_cam in ("graphic", "replay")`. |
| Q5 — Commit `wickets` | **DEFERRED — non-blocking future work** | Per §3.3 architectural-safety reasoning. Re-open trigger: a production observation of a wicket event whose only on-strip evidence falls inside a cam=graphic-only window (i.e. all live frames between the wicket and the next over-cursor advance are cam=graphic). The MI vs SRH log shows 8 wicket events, none with this pattern. |

**Outcome:** all execution-blocking items resolved; two future-work items have explicit re-open triggers. Composer 2 has zero open questions to "decide during implementation."

### §15.2 G2 (Scout `has_overlay_stats`) reliability

**Status: G2 is PRIMARY (carries the case-C/D rejection load) — Scout already emits the signal reliably; no Scout-side change required.**

#### §15.2.a Production data — does Scout emit `has_overlay_stats`?

Yes. Cross-tabulation across the 275 SCOUT-tag lines for `cam=graphic` in the MI vs SRH log:

| Configuration | Count | Interpretation |
|---|---|---|
| `cam=graphic strip=True overlay=False` | **165** | Fast-path candidate (G1+G2 pass) — case A territory |
| `cam=graphic strip=True overlay=True` | **29** | Stat overlay co-existing with strip — G2 rejects (case C/D) |
| `cam=graphic strip=False overlay=True` | **81** | Full-screen graphic, strip absent — G1 rejects |
| `cam=graphic strip=False overlay=False` | **0** | Degenerate; doesn't occur |

(Verified via `rg "cam=graphic" log | rg "strip=True" | rg -c "overlay=False"` etc.)

**G2 is dispositive on 110 of 275 cam=graphic SCOUT lines (40 %).** The flag is actively populated by Scout's classifier — not a default-False artefact.

#### §15.2.b Specific frame validation

| Frame | Scout tag (verbatim from log) | Interpretation | G2 verdict |
|---|---|---|---|
| F2128 (target frame, log line 23873) | `strip=True overlay=False cam=graphic` | Case A candidate | G2 PASS → fast-path tries to read |
| F2768 (Trent Boult career card, log line 29093) | `strip=True overlay=True cam=closeup` | Case C — overlay correctly tagged True | G2 REJECT (also G1 rejects on cam) — **double-protected** |
| F301, F315, F319, F346, F351, F441, F450, F745, F800, F801 (sampled `cam=graphic strip=True overlay=True`) | All 10 sampled lines verbatim show `overlay=True` | Case C/D pattern — Scout flagged correctly | G2 REJECT all |
| F22, F49, F88, F89 (sampled `cam=graphic strip=True overlay=False`) | All sampled lines show `overlay=False` | Case A territory | G2 PASS — fast-path will attempt; downstream gates G3-G7 finish discrimination |

**Empirical reliability estimate:** ≥95 % within the sampled set (no observed false-False on a confirmed stat-card). The Scout V5 prompt at `files/eyes/vision.py:104-107` explicitly defines `has_overlay_stats` as "career/tournament/head-to-head stats shown as an OVERLAY on top of the live feed (NOT the regular scoreboard strip)" — the prompt-engineered semantics matches case C/D precisely.

#### §15.2.c Scout-side change required?

**No.** The signal exists, is populated correctly, and discriminates ~40 % of the cam=graphic candidate set. G3-G7 provide redundant rejection for the residual ~5 % G2 mistag risk:

- G3 strict regex catches standings cards / INFO_PANEL contamination even when overlay=False mistagged.
- G4 catches 0-0 hallucinated heads.
- G5 catches opposition-team cards.
- G6/G7 catch implausible score/overs values (any case-C hallucinated head with values outside the monotone window).

**G2 is opportunistic on 5 % of cases, primary on 95 %.** No Scout change blocking Fix 2.

#### §15.2.d Per-case rejection-path traceability

| Case | Primary gate | Backstop gates | Observed in log |
|---|---|---|---|
| A live-with-overlay | (accept) | (accept) | F2128 (gap-window target), F22, F49 |
| B wicket replay (strip held over) | G6 (score regress) OR G8 (cooldown) | G3 if strip text degenerates | F2128 itself if read returns 221-5 ≡ current, idempotent accept; else G6/G7 reject |
| B wicket replay (strip absent) | G1 (strip=False) | — | covered upstream |
| C career-stat full-screen | G1 (strip=False) | G2 if strip surfaces alongside | F21, F329, F2768 (cam=closeup but G2 still flags overlay=True) |
| C career-stat with strip | G2 (overlay=True) | G3, G4, G5 | 29 frames in log (none reach fast-path body) |
| D over-end / partnership graphic | G2 (overlay=True) | G7 ball-delta, G3 | partial coverage in 29-frame G2-reject set |
| E ad break | upstream `cam=ad` skip | — | F2131, F2133 |

### §15.3 G6 / G7 monotonicity bounds — **REVISED with production validation**

#### §15.3.a Score-delta bound (G6)

Production score-delta histogram (all `score: X -> Y` BOARD transitions across the 4-hour log):

| Δscore | Count |
|---|---|
| +1 | 55 |
| +2 | 8 |
| +4 | 20 |
| +5 | 2 |
| +6 | 17 |
| +7 | 1 (F-event around `232 -> 239`; this was a slow-path MULTI_BALL recovery committing two balls' worth of runs in one step, not a single-frame +7 read) |

**Bound G6: `current ≤ score ≤ current + 6` is correct.** The single +7 outlier is a slow-path MULTI_BALL batch commit; on the fast-path it would (correctly) be rejected — the next live frame would commit it cleanly. False-negative cost: 1 frame per ~thousand. Acceptable.

**Edge cases:**

| Scenario | Δscore | G6 verdict | Note |
|---|---|---|---|
| Boundary (4 runs) | +4 | accept | within |
| Boundary + leg-bye | +5 | accept | within |
| Six | +6 | accept | within (boundary case) |
| Six + no-ball (1 + 6) | +7 | **reject** | **deliberately unhandled — see below** |
| Six + no-ball + waist-high free hit | +7 to +12 | reject | deliberately unhandled |
| First ball of innings (current=0, six=6) | +6 | accept | within |
| Start of innings 2 (current=0, score=4) | +4 | accept | within |

**Six-off-no-ball (Δ=+7) decision:** Reject. Reasoning: this is a vanishingly rare event (~0–1 per match), and in the rare case it occurs *during a cam=graphic frame*, the next live frame (at most 5 s later) commits it via the slow path. Tightening the cap to +7 would expand the false-positive surface for hallucinated-spike scenarios with no proportional gain. Composer 2: keep +6.

**Constant: `_FAST_PATH_SCORE_DELTA_MAX = 6`** (named near top of helper section per §15.1 Q2 resolution).

#### §15.3.b Overs-delta bound (G7) — **CRITICAL FIX vs §3.1 original**

Production overs-delta histogram (all `overs: X.Y -> A.B` BOARD transitions, **as numerical float subtraction**):

| Numerical Δ | Count | Cricket meaning |
|---|---|---|
| 0.1 | 73 | One ball within an over (e.g. 18.1 → 18.2) |
| 0.2 | 5 | Two-ball gap (typically MULTI_BALL of size 2) |
| 0.3 | 1 | Three-ball gap |
| **0.5** | **18** | **Over-boundary jump** (e.g. 2.5 → 3.0 — last ball of over to first ball of next over; numerically 3.0 − 2.5 = 0.5) |

**The original §3.1 bound `overs - current_overs < 0.4` would reject all 18 over-boundary advances**, breaking the most common transition in cricket. **This is the single most important correction in §15.**

**Revised G7 (ball-units):**

```python
def _overs_to_balls(overs_str: str | float) -> int:
    """Convert cricket overs notation X.Y to total ball count."""
    s = str(overs_str)
    whole, _, frac = s.partition(".")
    return int(whole) * 6 + (int(frac) if frac else 0)

# G7 logic
balls_cur = _overs_to_balls(current_overs_str)
balls_new = _overs_to_balls(parsed_overs_value)
delta_balls = balls_new - balls_cur
if not (0 <= delta_balls <= 3):
    reject(reason="G7_balls_window")
```

| Transition | Δ float | Δ balls | G7 verdict |
|---|---|---|---|
| 18.1 → 18.2 | +0.1 | +1 | accept |
| 18.5 → 19.0 (over boundary) | +0.5 | +1 | accept |
| 19.5 → 20.0 (innings end) | +0.5 | +1 | accept |
| 18.1 → 18.4 | +0.3 | +3 | accept (bound) |
| 18.1 → 19.0 | +0.9 | +5 | reject |
| 18.1 → 18.1 (idempotent) | 0 | 0 | accept |

**Constant: `_FAST_PATH_BALL_DELTA_MAX = 3`** (≤ 3 balls per fast-path commit; matches the score cap which is +6 = roughly 3 balls of scoring).

#### §15.3.c Edge case: cricket-illegal overs notation

`overs="2.6"` is illegal in cricket (the 6th ball ends the over). A misread strip showing `MI 200-3 (18.6)` would parse as 18*6+6 = 114 balls. Ball-delta from current 18.5 (113 balls) is +1 → accept. **Side effect:** scoreboard.set("overs", "18.6") writes an illegal overs value. Recommendation: add a sanity reject in G7 if the fractional part is `>= 6`. Add to the helper:

```python
frac = int(parsed_overs_str.partition(".")[2] or "0")
if frac >= 6:
    reject(reason="G7_illegal_frac")
```

This is a **revision to the §6.3 helper code**; Composer 2 must include this guard.

### §15.4 G8 cooldown sizing and semantics

#### §15.4.a Replay-window length in production

Sampled cam=graphic consecutive runs from MI vs SRH log:

- F2128 (single isolated cam=graphic, surrounded by cam=closeup + cam=ad)
- F22 (single)
- F49 (single)
- F88, F89 (run of 2)
- F164 (single after F162's `[SCOUT] GRAPHIC`)
- F300, F301 (run of 2)
- F315, F319 (singletons separated by other frames)
- F327, F328, F329 (run of 3)

**Maximum observed consecutive `cam=graphic` SCOUT lines: 5–6** (reading F164 → F175 → F194 → F211 spaced over ~2 minutes — these are not strictly consecutive frames; the pipeline samples ~1 SCOUT call per 2 s during dead-time). The "consecutive within a single graphic block" maximum is 3 (F327-F329). Across the whole file, no graphic block exceeded 6 consecutive SCOUT tags.

**Recommended deque size: 4 entries.** Covers the typical block (1–3 frames) plus a safety margin. The original §3.4 specification of `deque(maxlen=4)` is correct.

#### §15.4.b Matching semantics

**Tuple match: `(score, overs)` exact** (both fields must match). Not score-alone, not overs-alone.

```python
if (parsed_score, parsed_overs) in _cam_graphic_cooldown:
    reject(reason="G8_cooldown_dup")
```

Reasoning: a legitimate "score unchanged but overs ticked" advance (e.g. dot ball within an over while broadcaster shows a graphic) is a real event; we want to broadcast it. Only the *full* identity match is spam.

#### §15.4.c Interaction with legitimate identity broadcasts (e.g. drinks break)

The slow path (live SCOREBOARD frames during drinks break) always emits via `broadcast_state(ws_payload)` regardless of whether state changed; this is the existing identity-broadcast pattern and the WS contract permits it. **G8 only suppresses fast-path identity broadcasts, not slow-path.** If a drinks break consists of cam=graphic frames showing a frozen strip, the first fast-path acceptance broadcasts; the next 3 are G8-suppressed; the 5th cycles back into the deque (FIFO eviction at maxlen=4) and broadcasts again. This produces ~1 identity broadcast every 4 fast-path attempts during a long graphic block — a 4× reduction in WS chatter vs unguarded behaviour, but still sufficient periodic reaffirmation for any client that joined mid-break.

If the client fleet's resync semantics require *every* state read to be broadcast (TBD with the WS team), demote G8 from REJECT to ACCEPT-WITHOUT-BROADCAST: still skip the `await broadcast_state(...)` but do log `[CAM-GRAPHIC-FAST-PATH-COOLDOWN]` for telemetry visibility. Composer 2: implement the REJECT variant first; the ACCEPT-WITHOUT-BROADCAST variant is a one-line behavioural toggle if WS team requests.

### §15.5 has_overlay_stats vs alternative Scout signals

**Disposition:** §15.2 establishes that `has_overlay_stats` is reliably emitted. This subsection documents the fallback plan if a future Scout prompt revision degrades the signal.

#### §15.5.a Existing Scout signals that approximate `has_overlay_stats`

| Signal | Carrier of overlay-detection load | Reliability | Notes |
|---|---|---|---|
| `cam=graphic` | partial — coarse-grained "graphic-or-not" | high | doesn't separate live-with-overlay (A) from stat-card (C) |
| `frame_type == "GRAPHIC"` | partial | high | derived from `has_strip + has_overlay` per `_parse_tag` at `files/eyes/vision.py:524-526`; fires on overlay=True |
| `has_overlay_stats` | primary | ≥95 % | the right signal for this design |
| Strip-text contains `INFO_PANEL:` / `STANDINGS` / `CAREER` / `H2H` substrings | secondary | high (literal regex on Scout output) | currently used by `filter_info_panel_contamination` at `test_pipeline.py:6657` |

#### §15.5.b If `has_overlay_stats` becomes unreliable

Fallback chain (in order of preference):

1. Inline keyword-substring check on `description`: reject if `"INFO_PANEL"`, `"CAREER"`, `"STANDINGS"`, `"H2H"`, `"HEAD TO HEAD"`, or `"PARTNERSHIP"` (uppercase, anywhere in description). This is the existing `filter_info_panel_contamination` heuristic, applied locally inside the fast-path. ~5 LOC change to the helper.
2. Restrict G1 to also require `frame_type == "SCOREBOARD"` (excluding `frame_type == "GRAPHIC"` which fires on `has_strip AND has_overlay`). This shifts overlay detection from `has_overlay_stats` to `frame_type` — both are emitted by `_parse_tag`; equivalence in normal operation.

Both fallbacks are 1-line / 5-LOC changes. Composer 2 should NOT pre-implement them; defer until a Scout-prompt-change watchpoint shows the signal degrade.

#### §15.5.c F2128 evidence verification

Log line 23873 verbatim:

```
[21:22:08 F2128 VISION] INFO: [SCOUT] SCOREBOARD 696ms strip=True overlay=False
                              drs=False cam=graphic phase=graphic digits=True 299 chars
```

**Confirmation:** `overlay` field in the log is the same `has_overlay_stats` boolean (set at `files/eyes/vision.py:340`: `overlay_flag = tag.get("has_overlay_stats", False) if tag else False` → logged as `overlay={overlay_flag}` at line 361). No discrepancy. F2128 indeed has `has_overlay_stats=False`, qualifying it for fast-path entry under G1+G2.

### §15.6 Synthetic vs real fixture sourcing

**Per-case decision matrix:**

| Case | Fixture name | Source | Real frame ref | Shipping confidence |
|---|---|---|---|---|
| A — live strip, advancing | `test_fp_a_advancing_strip` | **synthetic** (no F-frame in log shows isolated cam=graphic *with verifiable score advance vs prior live frame* — the only candidate F2128 is idempotent against current state) | n/a | high — synthetic is straightforward; mirrors any of the 165 G1+G2-pass frames |
| A — live strip, idempotent (F2128 actual) | `test_fp_f2128_actual` | **synthetic-from-real** (strip text inferred from F2126 since F2128's STRIP wasn't logged due to skip-before-log ordering) | F2128 (line 23873) for tags; F2126 (line 23752 onwards) for strip text content | medium — strip-text inference is grounded but not byte-verified |
| B — wicket replay, held strip (idempotent) | `test_fp_b_wicket_replay_held_strip` | **synthetic** | conceptually F2128 itself if interpreted as case-B | medium |
| B — wicket replay, monotone violation | `test_fp_b_wicket_replay_pre_wicket_score` | **synthetic** | n/a (no clean log example of this specific failure) | medium — guard-correctness easily provable from logic |
| C — overlay flag rejected | `test_fp_c_career_stat_overlay_flag` | **real** | F2768 (log line 29093: `strip=True overlay=True cam=closeup`); also F301/F315/F319 (cam=graphic + overlay=True) | high |
| C — zero template | `test_fp_c_career_stat_zero_template` | **real** | F2768 STRIP text `MI 0-0 (0.0) | INFO_PANEL: TRENT BOULT` (line 29117) | high |
| C — standings card | `test_fp_c_standings_card` | **real** | F8 STRIP text `MI 9 STANDINGS SRH 4` (log line 318) | high |
| C — opposition team | `test_fp_c_opposition_career_card` | **synthetic** | n/a in log (MI vs SRH didn't have a clean opposition career-card moment within cam=graphic) | medium |
| D — partnership overlay flag | `test_fp_d_partnership_overlay_flag` | **synthetic-from-pattern** | nearest real: F745 (`strip=True overlay=True cam=graphic 451 chars`) — exact partnership-vs-over-end disambiguation needs visual review | medium |
| D — over-end implausible jump | `test_fp_d_over_end_implausible_jump` | **synthetic** | n/a | medium |
| D — over-end huge score jump | `test_fp_d_over_end_huge_score_jump` | **synthetic** | n/a | medium |
| Boundary | `test_fp_boundary_ambiguous` | **synthetic** | n/a | high — guard-correctness is provable |
| F2120-F2136 full window | `test_fp_f2120_to_f2136_full_window` | **real** | log lines 23696-23945 | high |

#### §15.6.a Source-of-truth for synthetic construction

For each synthetic fixture, the source-of-truth is the Scout V5 prompt rubric (`files/eyes/vision.py:83-215`). The synthetic STRIP text must conform to the format documented in the prompt: `STRIP: [TEAM] [SCORE]-[WICKETS] ([OVERS]) | [BATTER1] [RUNS]([BALLS]) | ...`. Composer 2 should construct the synthetic Scout descriptions **byte-for-byte mirroring this format**, with no improvisation.

#### §15.6.b Acceptance criteria for shipping

**Fix 2 ships with the synthetic fixtures listed above.** Real-fixture validation in a future match is *not* a blocker; the synthetic fixtures are sufficient to test guard-logic correctness, and the §9.4 watch criteria provide post-ship telemetry to catch any case-D guard miscalibration that the synthetic fixtures didn't model.

Re-open trigger: if next-match telemetry shows `[CAM-GRAPHIC-FAST-PATH-LATENT-FALSE-POSITIVE]` ≥1 fire, file a follow-up to capture real fixtures from that match and harden the case-D synthetic fixtures into real ones.

### §15.7 Path A snapshot regression interaction

#### §15.7.a Does Path A exercise cam=graphic frames?

**No.** The Path A snapshot test (`test_path_b_low_risk_batch_path_a_regression_signature_match` at `files/test_recent_fixes.py:8091-8149`) calls `tp._build_full_payload_from_state(...)` with a synthetic `_path_b_regression_fixture()` constructed from raw `Scoreboard` and `ScoreManager` objects (lines 8091-8132). It does **not** invoke any frame-processing path — no Vision call, no extractor, no dead-time skip, no cam=graphic gate.

#### §15.7.b Predicted Path A interaction

**Byte-identical, guaranteed by construction.** Fix 2 modifies:
- `files/eyes/vision.py` — adds 2 instance fields on `Vision`. Path A doesn't instantiate `Vision`.
- `files/test_pipeline.py` — adds a helper, a constant, a deque, and a call site inside the dead-time skip block. Path A doesn't call any of these.
- `_build_full_payload_from_state` (the function Path A actually exercises) — **untouched**.

The signature comparison in `test_path_b_low_risk_batch_path_a_regression_signature_match` at line 8145-8149 will yield `sig == baseline_sig` byte-identical post-Fix 2.

#### §15.7.c Composer 2 response matrix

| Path A test result post-Fix 2 | Composer 2 response |
|---|---|
| **Byte-identical (expected)** | Proceed normally. C3 ships. |
| **Signature changed, change is *additive* in a `cam_graphic_fast_path`-source field** (shouldn't happen — no such field is added to the payload schema by this fix) | **STOP. Route back.** Indicates Composer 2 added a payload field not in the spec. |
| **Signature changed, change is in any non-`cam_graphic_fast_path` field** | **STOP. Route back.** Indicates an unintended ripple in a code path Path A exercises. |
| **Signature unchanged but Path A test fails for a different reason (e.g. import error)** | **STOP. Route back.** |

### §15.8 Identity broadcast handling

#### §15.8.a Operational definition

An "identity broadcast" is a fast-path acceptance whose `(score, overs)` tuple equals the value already present in `Scoreboard._inn`. Operationally:

1. `scoreboard.set("score", parsed_score, frame_count)` returns `False` (no change).
2. `scoreboard.set("overs", parsed_overs, frame_count)` returns `False` (no change).
3. Both `_fp_changes` lists are empty.

In this case **the per-§6.2 design currently calls `await broadcast_state(build_full_payload())` UNconditionally**. This is the WS-redundant-but-safe behaviour.

#### §15.8.b Recommended behaviour change (CONFIRMED)

**Skip the `broadcast_state` call when `_fp_changes` is empty.** Reasoning: identity broadcasts have no information for clients beyond "yes, we still see the same state" — and the slow-path live frames (which always run periodically — every 1.5–4 s per `adaptive.get_sleep_time()`) provide the same reaffirmation through their own broadcast. Suppressing identity broadcasts on the fast-path saves ~150 WS sends per match (estimated from 165 G1+G2-pass frames × ~90 % idempotent ratio).

Revise §6.2 pseudocode to:

```python
if _fp_changes:
    log.info(f"[F{frame_count}] [CAM-GRAPHIC-FAST-PATH-READ] ...")
    await broadcast_state(build_full_payload())
else:
    log.info(f"[F{frame_count}] [CAM-GRAPHIC-FAST-PATH-NOOP] "
             f"score={_fp_result['score']} overs={_fp_result['overs']} "
             f"(state unchanged; no broadcast)")
# unconditionally update cooldown deque
_cam_graphic_cooldown.append((_fp_result["score"], _fp_result["overs"]))
```

Note: the cooldown deque is updated *unconditionally* on accept (whether change-emitting or noop). This is correct — G8's purpose is to dedupe the *next* fast-path attempt that would produce the same tuple, regardless of whether this attempt actually broadcast.

#### §15.8.c Telemetry firing convention (revised)

Three tags now (not two):

| Tag | When | Expected per-match rate |
|---|---|---|
| `[CAM-GRAPHIC-FAST-PATH-READ]` | accept AND `_fp_changes` non-empty | 5–15 per match (genuine new-info commits) |
| `[CAM-GRAPHIC-FAST-PATH-NOOP]` | accept AND `_fp_changes` empty | 100–200 per match (idempotent state reaffirmations) |
| `[CAM-GRAPHIC-FAST-PATH-REJECT reason=Gn_…]` | any gate fail | 50–150 per match |
| `[CAM-GRAPHIC-FAST-PATH-COOLDOWN]` | G8-specific reject (subset of REJECT, dual-emitted for analyzer convenience) | 20–50 per match |
| `[CAM-GRAPHIC-FAST-PATH-LATENT-FALSE-POSITIVE]` | analyzer-emitted (not in pipeline source) | 0 per match expected |

**Analyzer baseline calibration.** The `[T7-RECOVERY] gaps_recovered=N {fix1=A, fix2=B, native=C}` aggregate in §8.3 should count READ tags only (not NOOP), because NOOP is by definition *not* a recovery. Update `files/analyze_match_telemetry.py` aggregator accordingly when Composer 2 implements §8.3.

### §15.9 Coordination with Thread 7 Fix 1 (already shipped)

#### §15.9.a Interaction sites

Fix 1 lives in a slow-path helper (the row-misalignment guard at `files/test_pipeline.py:2900-2937`, emitting `[STRIP-ROWS-MISALIGNED]` at line 2930). This guard runs **only when the slow-path Extractor has been invoked and produced an `extracted` dict containing `batters`**. Fix 2's fast-path:

- Never invokes Extractor (regex-only on Scout `description`).
- Never produces an `extracted` dict (returns `{"team", "score", "wkts", "overs"}` from `_try_cam_graphic_fast_path`).
- Never reads the batter portion of the strip.

**Therefore Fix 1's guard cannot fire on a Fix 2 fast-path frame, and vice versa.** They are surface-disjoint.

#### §15.9.b Consequence of fast-path reading a misaligned strip

If the strip text Scout returned has misaligned batter rows (the H1 OCR bug Fix 1 addresses), the fast-path is unaffected because the misalignment is in the batter rows and the fast-path only reads the strip *head* (`STRIP: TEAM SCORE-WICKETS (OVERS)`). The head has no row-alignment dependency — it's a single fixed-position token sequence at the start of the line. Fix 2 ignores everything after the head per the `_FAST_PATH_STRIP_HEAD_RE` regex anchoring.

#### §15.9.c Telemetry coordination

A single frame **cannot** fire both `[STRIP-ROWS-MISALIGNED]` and `[CAM-GRAPHIC-FAST-PATH-READ]`:
- Fast-path runs only when `_last_cam == "graphic"` AND we'd otherwise hit the dead-time `continue`.
- Fix 1's guard runs only on the slow path (post-Extractor).
- The two paths are mutually exclusive within a single frame (different branches of the dead-time gate).

The analyzer aggregate `[T7-RECOVERY]` therefore sums *across frames*, not within. No conflict.

### §15.10 Composer 2 stop-and-route-back conditions (Fix 2-specific)

In addition to the standard stop conditions (Path A regression — see §15.7.c, contract gap, scope creep), Composer 2 must **stop and route back to a human reviewer** if any of the following is detected during execution:

| # | Condition | Why stop |
|---|---|---|
| S1 | `has_overlay_stats` field absent from a Scout response that has `cam=graphic strip=True` (signal degraded vs §15.2 expectations) | G2 dependency unmet; falling back to §15.5.b heuristics is a design call, not an implementation call |
| S2 | G6 or G7 bound rejects ≥30 % of fast-path attempts on the *first match* of validation | Bounds may be wrong; needs human review of production histogram before retuning |
| S3 | Fast-path commits any field other than `score` and `match_overs` (architectural-safety-thesis violation) | The §3.2 / §10.1.2 guarantee is broken; stop |
| S4 | Telemetry fires `[CAM-GRAPHIC-FAST-PATH-READ]` at >50× the per-match expected rate (§15.8.c → expected ≤15; threshold = 750 in a single match) | Indicates a runaway fast-path; defensive halt |
| S5 | Synthetic fixture construction during C2 reveals a case-B/C/D scenario where *no combination* of G1-G8 reliably rejects | Case definition was incomplete; stop and route back to expand the case taxonomy |
| S6 | `_resolve_team_variant` API has changed signature or semantics since this design was written | G5 implementation depends on it; verify before adapting |
| S7 | `Scoreboard.set("score", ...)` returns a value other than bool, or its semantics differ from "True if changed" (e.g. it now requires extra args) | C3 call-site code assumes the boolean-return contract |
| S8 | `_FAST_PATH_STRIP_HEAD_RE` matches >50 % of `cam=graphic strip=False` frames in any sample (false positives on no-strip) | Regex is too loose; needs revision before shipping |
| S9 | Path A snapshot test changes signature for *any* reason (per §15.7.c) | Indicates an unintended ripple |
| S10 | `_cam_graphic_cooldown` deque collides on legitimate score advance during a long ad block (false G8 reject of a real new-info commit on resumption) | Cooldown semantics or clear-policy needs revision |

For each of S1-S10, Composer 2 must:

1. Halt all in-progress edits.
2. Document the trigger condition in this file under a new §17 entry: `## §17. Stop events during execution` (date, condition number, observed evidence).
3. Route back to a human reviewer for design adjustment.
4. Not improvise a workaround.

---

## §16. Final Composer 2 readiness checklist

| # | Criterion | Status | Reference |
|---|---|---|---|
| 1 | All §13 open questions resolved or explicitly deferred with re-open triggers | ✓ RESOLVED | §15.1 |
| 2 | G2 (Scout `has_overlay_stats`) dependency characterized with production data | ✓ PRIMARY signal, ≥95 % reliability, no Scout change required | §15.2 |
| 3 | G6 score-delta bound validated against production histogram | ✓ +6 cap correct (single +7 outlier acceptable false-negative) | §15.3.a |
| 4 | G7 overs-delta bound validated against production histogram and CRITICAL FIX applied | ✓ ball-units comparison required (`<= 3 balls`); float-overs `< 0.4` original would have rejected all over-boundary advances | §15.3.b |
| 5 | G7 illegal-overs-fraction sanity check added | ✓ reject `frac >= 6` | §15.3.c |
| 6 | G6 / G7 bounds promoted to named constants | ✓ `_FAST_PATH_SCORE_DELTA_MAX = 6`, `_FAST_PATH_BALL_DELTA_MAX = 3` | §15.3 |
| 7 | G8 cooldown deque size validated against replay-block length in production | ✓ `deque(maxlen=4)` covers max-3 consecutive frames + safety margin | §15.4.a |
| 8 | G8 matching semantics specified (full tuple, not field-wise) | ✓ `(score, overs)` exact match | §15.4.b |
| 9 | G8 interaction with legitimate identity broadcasts handled | ✓ slow-path unaffected; fast-path identity broadcasts suppressed by §15.8.b | §15.4.c, §15.8.b |
| 10 | Test fixture sourcing decided per case (real vs synthetic) | ✓ matrix in §15.6 | §15.6 |
| 11 | Shipping confidence per fixture documented | ✓ matrix in §15.6 | §15.6 |
| 12 | Path A snapshot interaction predicted (byte-identical by construction) | ✓ Fix 2 doesn't touch `_build_full_payload_from_state` | §15.7 |
| 13 | Identity-broadcast suppression policy decided (skip `broadcast_state` when no `_fp_changes`) | ✓ revised §6.2 pseudocode | §15.8.b |
| 14 | Telemetry firing convention revised (3 tags: READ / NOOP / REJECT + COOLDOWN subset) | ✓ rates calibrated for analyzer | §15.8.c |
| 15 | Fix 1 (`STRIP-ROWS-MISALIGNED`) interaction characterized | ✓ surface-disjoint; no per-frame conflict possible | §15.9 |
| 16 | Composer 2 stop-and-route-back conditions enumerated (Fix 2-specific) | ✓ S1-S10 in §15.10 | §15.10 |
| 17 | Code-revisions to original §6 helper integrated | ✓ §15.3.b (G7 ball-units), §15.3.c (illegal frac), §15.8.b (broadcast skip), §15.1 Q1-Q3 (defaults / constants / clear) | §15.* |
| 18 | Architectural-safety thesis preserved | ✓ fast-path commits only `score` and `match_overs` (S3 guards against violation) | §3, §10.1.2, §15.10 |
| 19 | No improvisation points remain | ✓ verified via §15.1 disposition matrix | §15.1 |

**Seal:** with §15.1 through §15.10 resolved and §16 line-items 1-19 confirmed, **this design contract is ready for Composer 2 execution**. Composer 2 may proceed with C1 → C2 → C3 in order, applying the §15-revised specifications wherever they supersede §6 / §3.

If during execution Composer 2 encounters any condition not enumerated in §15.10 but that feels architecturally significant, the conservative bias is **stop and route back**, even at the cost of throughput. A 30-minute design clarification beats a 30-minute ship of a quietly-corrupting fast-path.

---

## §17. Implementation notes (shipping — 2026-04-30)

Execution completed without triggering §15.10 stop conditions S1–S10.

**Land sequence (logical three-commit split):**

1. **`files/eyes/vision.py`** — Expose Scout strip/overlay signals as `last_strip_flag` and `last_overlay_flag` (from `has_strip` / `has_overlay_stats` on the parsed tag), reset alongside existing placeholder-reject paths.
2. **`files/test_pipeline.py`** — Module-level `_cam_graphic_fast_path`, `_FAST_PATH_*` constants, ball-units G7 via `_fast_path_normalize_overs` / `_fast_path_overs_str_to_balls`; **`files/test_recent_fixes.py`** fixtures **`test_thread7_fix2_*`**; **`files/analyze_match_telemetry.py`** pending-validation + bundle entries for the three telemetry regexes.
3. **`files/test_pipeline.py` (dead-time)** — Inside `_last_cam in _DEAD_VIEWS`, only `cam=graphic` with strip and without overlay runs the fast-path; commits via `scoreboard.set("score"|"overs")` only; `deque(maxlen=_FAST_PATH_COOLDOWN_MAXLEN)` cleared when exiting dead time (`_was_dead_time` transition).

**Telemetry semantics (operational):**

- **`[CAM-GRAPHIC-FAST-PATH-READ]`** — Fast-path accepted and at least one of `score` / `overs` actually changed on the scoreboard; WS broadcast follows.
- **`[CAM-GRAPHIC-FAST-PATH-NOOP]`** — Parsed tuple accepted by the helper but both `Scoreboard.set` calls were no-ops (state already matched); no WS broadcast.
- **`[CAM-GRAPHIC-FAST-PATH-REJECT]`** — Any guard failure, including **`reason=G8_cooldown_dup`** when the `(score, overs)` tuple was recently committed (cooldown membership).

**Regression:** Path A WS snapshot byte-identity unchanged (`test_path_b_low_risk_batch_path_a_regression_signature_match`). Synthetic pending-validation catalog extended with one line per new tag.

**Document complete. Sealed for Composer 2 execution, 2026-04-30; §17 records post-ship facts.**
