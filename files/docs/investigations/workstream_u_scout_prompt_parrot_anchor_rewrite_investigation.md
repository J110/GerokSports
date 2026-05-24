# Workstream U — Track 1 SCOUT prompt rewrite borrowing Track 2 parrot-anchor pattern (step-1)

**Status.** Step-1 closed; static-falsification chain converges on a **MINIMAL ADAPTIVE** leading candidate (**UD-prime**: anti-priming pattern is ALREADY partially landed at Track 1 SCOUT_PROMPT_SHORT per the 2026-05-12 anti-hallucination fix; the only outstanding parity-gap is the **`[UNREADABLE FRAME]` exit clause** plus narrow surface-specific forbidden-phrase additions). The headline-borrow framing of WS-U ("port Track 2's `cbde6b8` rewrite to Track 1") is **mostly NO-OP** — Track 1 was independently rewritten the SAME day (2026-05-12, see `vision.py:316-387` SCOUT_PROMPT_SHORT header comment block). The genuinely new patch surface is small.

**Pre-screen verdict.** GREEN — PIPELINE-DIRECT per S28 (single-file prompt-text edit at `files/eyes/vision.py:316-387` SCOUT_PROMPT_SHORT). No downstream parser touch required if exit-clause sentinel is emitted as a STRIP all-null line.

**S33 instrumentation-aware methodology applied.** Step-2 will instrument a parallel-prompt variant (UD-prime alongside SCOUT_PROMPT_SHORT), shadow-run on the DCKKR dump, diff structured-field parity, and only flip after parity confirms zero schema-parser breakage. This investigation memo itself is the parallel-prompt-comparison step performed STATICALLY (Track 1 current prompt vs Track 2 `cbde6b8` reference vs UD-prime proposed) before any code touch.

**Hypothesis count.** 5 (UA / UB / UC / UD / UE) with UD-prime as a refinement of UD after gate-1 audit on UA-UC surfaced an unexpected falsification: Track 1's SCOUT_PROMPT_SHORT already contains the load-bearing elements of Track 2's `cbde6b8` rewrite. Two falsifications (UA + UE) at gate 1; UB + UC falsified at gate 4 (schema-parser breakage risk). UD survives gates 1-5; refined to UD-prime.

**Reference commit.** Track 2 OpenScout parrot-anchor fix = `cbde6b8` (2026-05-12, *"openscout: kill V1/V2 parrot anchors; ground on VISIBLE_TEXT, ban canned prose, [UNREADABLE FRAME] exit"*). The user-cited `cbeaeeb` in the WS-U trigger is a different commit (LOCKED state for batting_team in `confidence_tracker.py`) — corrected here for accuracy. Empirical parallel: Track 1's same-day vision.py rewrite (`fed5b5a` per the cbde6b8 commit body reference, plus the SCOUT_PROMPT_SHORT 2026-05-12 anti-hallucination block at vision.py:316-387).

---

## §1 Empirical anchor — Track 1 parrot-anchor evidence + 4 cascade-root anchors

### §1.1 Track 1 SCOUT team-abbreviation thrash (YouTube test WI-vs-RSA, `866ce150.jsonl`)

Per `files/docs/investigations/youtube_test_delivery_detection_analysis.md` §3.1 (174 SCOREBOARD reads):

| Abbrev | Reads | Notes |
|---|---|---|
| `SA` | 375 | correct |
| `LIONS` | 15 | sponsor / promo strip parrot-anchor |
| `LSG` | 9 | IPL-graphic mis-read (mode-collapse onto IPL prior) |
| `RCB` | 10 | IPL-graphic mis-read |
| `KKR` / `MI` / `JAM` / `PR` / `SOU` | 3+3+2+2+3 | spurious mode-collapse onto franchise priors |

**Mechanism**: same as OpenScout's pre-`cbde6b8` failure shape — VLM mode-collapses onto canned example tokens listed in the prompt body when pixel-grounding is weak (graphic overlays, sponsor cards, mid-cuts). The 9-code thrash spans `STRIP: LIONS 8-0 (1.2)` at F204 directly following `STRIP: SA 11-0 (4.0)` at F185 — score string drags with the bogus team token, tripping downstream consistency gates and burning 55 SCORE-INF-GATE rejections in a 3-minute window.

### §1.2 Cold-start overread cascade (WS-O.c residue — DCKKR balls 4.1-4.5)

Per `files/tests/baselines/dckkr_diff_post_ws_o_b_baseline.md` §3 conservation invariants + WS-O.c investigation §1:

| Ball | balls (count) | Pipeline score | GT score | Δ |
|---|---|---|---|---|
| 4.1 | 24 | **63** | 43 | +20 |
| 4.2 | 25 | **63** | 44 | +19 |
| 4.3 | 26 | **63** | 44 | +19 |
| 4.4 | 27 | **64** | 45 | +19 |
| 4.5 | 28 | **64** | 49 | +15 |

The bogus 63 enters the pipeline at the score-read of a specific cold-start frame (post-WS-O.b PA threshold 2.5*balls+10 = 70 admits 63 at balls=24). The 63 originates at the Scout read — not at downstream arithmetic. WS-O.c's PA-threshold-tightening to 1.9*balls+10 = 55.6 catches it AT THE GATE; WS-U targets the SOURCE: why does Scout mis-read 43 as 63 on this specific frame? Hypothesis: parrot-anchor onto a graphic-overlay digit (sponsor side-panel, OTS panel) that the prompt's example numerics seed as priors.

### §1.3 Cold-start striker bat1/bat2 misorder (WS-P cohort — DCKKR balls 0.5+)

Per `files/docs/investigations/workstream_p_cold_start_striker_anchor_investigation.md` §1: every ball 0.5+ on DCKKR shows pipeline striker/non-striker name SWAPPED relative to GT, with per-batter runs/balls/fours/sixes correctly tracking the swapped slot (identity ledger correct post-anchor). Cohort: ~50 fields across ~13 distinct balls (0.5, 0.6, 1.2, 1.5, 1.6, 2.3, 2.4, 2.5, 3.4, 3.5, 3.6, plus 4.x rollover).

**Scout-side hypothesis**: the cold-start frame at which `_accept_initial` commits to (bat1=Rahul, bat2=Nissanka) reflects Scout having emitted the rows in (Rahul-first, Nissanka-second) order on a frame where the cricket-truth striker was Nissanka and the broadcast asterisk-marker was either occluded, parrot-anchored away ("> Nissanka" → "Rahul"), or absent due to mid-cut. WS-P's QA+QE fix anchored on squad convention at the SM/snapshotter boundary (88e03f5) and was a NO-OP on DCKKR — the dump's first-committed-frame doesn't carry the squad-convention signal either. WS-U targets the Scout output itself: a stricter VISIBLE_TEXT discipline plus an UNREADABLE FRAME exit would have demoted that cold-start frame instead of committing it.

### §1.4 Phantom-wicket F1017 (WS-Surface-E)

Per `files/docs/investigations/workstream_surface_e_phantom_wicket_investigation.md` §1 (canonical DCKKR `validate_dckkr_20260521_155356`):

| Frame | scout `wickets` | scout `overs` | scout `score` | wicket-decision |
|---|---|---|---|---|
| F1015 | **6** | 10.4 | 89 | (none) |
| F1016 | **4** | 10.4 | 89 | (none) |
| **F1017** | **5** | 10.5 | 89 | **STRIKER-WRITE + POST-WICKET-ROTATION** (phantom) |
| F1019 | 5 | 10.5 | 89 | (post-wicket stabilization) |

Scout's `wickets` primitive oscillated 6 → 4 → 5 across 3 consecutive graphic-overlay frames. The 6 and 4 are mutually inconsistent — at most one is cricket-truth. Both look like parrot-anchor onto an OTS-panel wickets-shaped digit. **WS-U hypothesis**: an UNREADABLE FRAME exit on F1015 + F1016 (both demonstrably noisy graphic frames per the OCR oscillation signature) would have starved the wickets-counter at F1017 → ball_detector's strict-increase predicate sees prev=4-from-F1014 (the stable upstream value of 4, not the unstable F1016 of 4) and rejects the F1017 5-as-fresh-+1.

### §1.5 Per-batter ledger drift residue (post-WS-O.b: 5 fields at ball 4.1)

Per dckkr_diff_post_ws_o_b_baseline.md §1 surface table: 5 Per-batter-ledger-drift incidents starting at 4.1. These are striker_fours/sixes/non_striker_fours/non_striker_sixes mismatches at the residue frames where WS-O.c's bogus-63 cascade roots. Same root: parrot-anchor at the Scout reading of cold-start-rollover frames.

---

## §2 Track 1 SCOUT prompt structural audit

### §2.1 SCOUT_PROMPT_SHORT (live; default per `vision.py:393-397`)

`vision.py:316-387`. ~1.5K input tokens. Used in the per-frame Vision loop (60 fpm cap).

**Structure** (4 LINEs + anti-priming rules + hint footer):

| Line | Content | Schema-load |
|---|---|---|
| LINE 1 | JSON classification tag `{has_strip, has_overlay_stats, drs_review, camera_view, frame_phase, ball_position}` | LOAD-BEARING (parsed by `Vision._parse_tag`, drives BallAnalyzer tagged-frame buffer, AdaptiveSleep, OpenScout rate gate) |
| LINE 2 | VISIBLE_TEXT verbatim transcription with `(none)` exit | LOAD-BEARING (parsed by `extract_regex._VT_LINE` at `extract_regex.py:99`; alternate-format batter rows fall back to VT via `_VT_BATTERS_PREFIX_GT` / `_VT_BATTERS_INFIX_GT` / `_VT_BATTERS_NO_MARKER` / `_VT_BOWLER`) |
| LINE 3 | STRIP structured fields `<team> <runs>-<wkts> (<overs>) \| extras= \| this_over= \| <striker> <r>(<b>) \| <nonstriker> <r>(<b>) \| <bowler> <w>-<r> (<o>)` | LOAD-BEARING (parsed by `extract_regex` STRIP regexes; ~92 downstream consumers per WS-Q step-1 enumeration) |
| LINE 4 | Optional CHASE info `TARGET <n> \| REQUIRED RUN-RATE <f> \| NEED <n> FROM <n> BALLS` | LOAD-BEARING (parsed by `extract_regex._CHASE_RUNS_BALLS / _TARGET / _REQUIRED_RATE`) |

**Parrot-anchor surfaces present** (potential mode-collapse points):

1. **Enum example list for camera_view** (`bowlers_end / side_on / closeup / replay / graphic / ad / other`) — each enum value is a candidate parrot-anchor word, but downstream the `_normalise_camera_view` validator constrains to the allowed set so divergent values are demoted to None. RISK: LOW.
2. **Enum example list for frame_phase** — same as above, with `_normalise_frame_phase` cross-checks. RISK: LOW.
3. **STRIP format placeholder line** (`<team_or_null> <runs>-<wkts> (<overs>) \| ...`) — historical parrot-anchor surface fixed by Fix #4 (vision.py:56-72 `_TEMPLATE_MARKERS` rejection guard). RISK: NEUTRAL (defensive guard already in place).
4. **Anti-priming forbidden names list** (`Rohit Sharma, Suryakumar Yadav, Harshal Patel, Ishan Kishan, Yashasvi Jaiswal, Jasprit Bumrah, Jadeja`) — these are NEGATIVE-anchors (forbidden); they could in principle act as positive primes ("don't think about elephants") but empirically the 2026-05-12 fix shipped this exact pattern and it closed the 2026-05-11/12 hallucination regression. RISK: LOW (validated in production).
5. **Forbidden team-abbreviation list** (`MI, RCB, KKR, LSG, CSK, DC, PBKS, GT, RR, SRH`) — same negative-anchor structure as #4. RISK: LOW.

**Parrot-anchor surfaces NOT yet hardened** (the WS-U gap):

6. **NO `[UNREADABLE FRAME]` exit clause** — when the frame is blank, decoder-corrupted, fully ad-occluded, or otherwise unparseable, the prompt currently directs Scout to "use ? for individual chars/words you cannot resolve" and emit `VISIBLE_TEXT: (none)` + STRIP all-null. This is structurally equivalent to Track 2's `[UNREADABLE FRAME]` but lives in the schema (STRIP-all-null + VT-none) rather than as a distinct sentinel. **PARTIAL HARDENING**. The gap: the prompt does not explicitly authorize an early-stop on a clearly-unreadable frame — Scout still tries to produce all 4 LINEs, opening a parrot-anchor surface for the JSON tag line on graphic/replay frames where camera_view enum becomes a guess.
7. **NO Track 1-specific forbidden-phrase list for non-name surfaces** — the anti-priming rules list player names + team codes but NOT (a) the IPL-graphic-prior franchise inference (covered partially by #5 but not for OTS-panel digit parrot-anchor), (b) score-shape parrot-anchor (e.g. echo of `100-3` or `200-7` round numbers from training data), (c) wickets-counter graphic-overlay parrot-anchor (the F1017 root). GAP.
8. **NO explicit observability for which mode-collapse symptom triggered** — when Scout DOES parrot-anchor, the downstream guards (template-marker rejection, PA threshold, ball_detector strict-increase) reject silently. No trace tag distinguishes "real low-confidence read" from "parrot-anchored read". OBSERVABILITY GAP (not a closure gap but a step-2 instrumentation gap).

### §2.2 SCOUT_PROMPT_VERBOSE (env-flagged; `vision.py:115-304`)

~3.5K input tokens. Used only when `SCOUT_PROMPT_MODE=verbose`. Carries STEP 4 overlays + STEP 5 action narrative beyond what SHORT emits. The 2026-05-02 update (lines 102-114) already includes:
- VISIBLE_TEXT verbatim step (STEP 2)
- Anti-priming forbidden names + forbidden teams (lines 265-279)
- "If VISIBLE_TEXT was (none)" all-null STRIP exit
- Template-placeholder rejection at downstream `_TEMPLATE_MARKERS`

**Same gaps as SHORT** (no explicit `[UNREADABLE FRAME]` sentinel; no graphic-overlay digit forbidden-phrase rule).

### §2.3 Audit summary

Both Track 1 prompts already contain the load-bearing elements of Track 2's `cbde6b8` rewrite: VISIBLE_TEXT verbatim step (LINE 2 / STEP 2), explicit anti-priming forbidden-phrase block, and STRIP all-null as the structural equivalent of `[UNREADABLE FRAME]`. The 2026-05-12 same-day Track 1 fix (vision.py:316-387 header comment) appears to have been authored from the same postmortem evidence as `cbde6b8`. **The genuine gap is narrow**: (i) no distinct `[UNREADABLE FRAME]` sentinel, (ii) no graphic-overlay digit / score-shape forbidden-phrase rule extending the existing anti-priming block.

---

## §3 Track 2 OpenScout post-rewrite pattern reference (`cbde6b8`)

Per `git show cbde6b8 -- files/eyes/open_scout.py` (the actual rewrite commit; user-cited `cbeaeeb` is a different commit on confidence_tracker.py). Pre-rewrite OPEN_PROMPT was 12 lines listing literal example tokens (`fielders walking`, `players talking`, `bowler running`); llama-4-scout mode-collapsed onto "a player walking on the field" for **96.1% of frames** in live_20260511, classifying **2293/2317 (99.0%)** as `other`.

### §3.1 The 4-element pattern

| Element | Verbatim text from `open_scout.py:65-112` |
|---|---|
| **STEP 1 VISIBLE_TEXT verbatim** | "STEP 1 — Read any visible scoreboard or graphic text in the frame verbatim onto the FIRST line, prefixed with \"VISIBLE_TEXT:\". Capture score, batter names, bowler name, run-rate, over count, or whatever overlay text is actually rendered in the pixels. If no scoreboard or graphic text is visible, emit exactly: VISIBLE_TEXT: (none)" |
| **STEP 2 grounded 2-4 sentence description** | "STEP 2 — On the next line(s), write a 2-4 sentence description of what is actually happening in THIS specific frame. Cover: Camera framing; exact pose and motion; persistent on-screen graphics" |
| **CRITICAL anti-priming forbidden phrases** | "CRITICAL — anti-parroting rules: Do not copy phrases from THIS prompt verbatim. The descriptions \"a player walking on the field\", \"a cricket player standing\", \"the camera shows a player walking\" are FORBIDDEN as canned fallbacks. Use them only if they are literally and specifically what is happening in this exact frame. Your description must be grounded in something you can actually point to in the pixels — a number on the scoreboard, a specific body pose, a graphic element, a colour, a framing." |
| **`[UNREADABLE FRAME]` single-line exit** | "If the frame is blank, fully black, corrupted with decoder artifacts, fully obscured, or you cannot identify any cricket-broadcast content, write exactly ONE line and stop: [UNREADABLE FRAME]" |

### §3.2 Removed elements (Track 2 negative space)

- `OPEN_PROMPT_V2` (the `[BROADCAST: REPLAY/SLO-MO/TELESTRATOR/SPLIT-SCREEN/LIVE]` tag layer) was DELETED — V2 had the same parrot vulnerability under different anchor words (`walking between balls`).
- `_active_prompt()` and `OPEN_SCOUT_PROMPT_VERSION` env gate REMOVED — keeping a fallback re-arms the same failure shape.

---

## §4 Delta analysis — Track 1 prompt vs Track 2 pattern

| Track 2 element | Track 1 SCOUT_PROMPT_SHORT equivalent | Delta |
|---|---|---|
| STEP 1 VISIBLE_TEXT verbatim | LINE 2 VISIBLE_TEXT verbatim (vision.py:340-344) | **PARITY** — both demand pixel-grounded transcription with `(none)` exit |
| STEP 2 grounded prose description | LINE 3 STRIP structured + LINE 4 CHASE | **DIVERGENT BY DESIGN** — Track 1 emits structured fields (parsed by ~92 downstream sites); Track 2 emits free prose for `classify_full` rule engine. Track 1 structured-field schema is load-bearing and cannot be replaced with prose without breaking parsers |
| CRITICAL anti-priming forbidden phrases | ANTI-PRIMING RULES block (vision.py:365-382) | **PARITY-MINUS** — Track 1 lists forbidden player names + team codes; Track 2 lists forbidden generic-fallback descriptive phrases. Both target the SAME failure mode (mode-collapse onto canned prior) but at different surface vocabularies. **Track 1 GAP: no forbidden-phrase rule for graphic-overlay digits / score-shape priors / wickets-counter parrots** |
| `[UNREADABLE FRAME]` single-line exit | `VISIBLE_TEXT: (none)` + STRIP all-null (vision.py:353-356) | **PARTIAL** — functionally equivalent (downstream readers treat all-null as no-signal) but Track 1 does NOT explicitly authorize an early-stop. Scout still tries to produce all 4 LINEs, leaving a parrot-anchor surface for the JSON tag line on graphic/replay frames where camera_view becomes a guess. **GAP**: no `[UNREADABLE FRAME]` sentinel; JSON tag line is mandatory and not bypassable |

### §4.1 Candidate additions (the narrow patch surface)

A. **`[UNREADABLE FRAME]` sentinel** as an alternative to the 4-LINE structured output, with downstream parser hardening to treat the sentinel as STRIP-all-null + JSON-tag-as-graphic equivalence.

B. **Anti-priming extension** with forbidden-phrase rules for graphic-overlay parrot-anchor:
   - Forbidden round-score parrots when not in VISIBLE_TEXT: `100-3, 150-4, 200-5` (canonical T20 round numbers).
   - Forbidden wickets-counter parrot when oscillation suspected: this is harder to express in prompt language — likely deferred to consensus N-frame at ball_detector per WS-Surface-E HA (which was reverted) or as observability instrumentation.
   - Forbidden franchise inference rule: extend the existing team-list with explicit "Do NOT infer franchise from sponsor / boundary / kit colours alone" guidance.

C. **Frame-type observability tag**: when Scout chooses the `[UNREADABLE FRAME]` exit, emit a typed trace tag (`SCOUT-UNREADABLE-EXIT`) so trace-replay can correlate with downstream cascade absence (positive signal of preventive demotion).

---

## §5 Known-problem closure prediction (per-cascade-root)

For each of the 5 known cascade roots, predict whether UD-prime (Track 1 prompt rewrite with `[UNREADABLE FRAME]` exit + extended anti-priming) closes the source-frame mode-collapse.

### §5.1 WS-O.c residue — cold-start overread balls 4.1-4.5 (DCKKR)

**Cascade-root anchor frames**: balls 4.1-4.5; the specific Scout reads producing bogus 63 (vs GT 43-49) on a 5-ball sustained window. Per WS-O.b investigation, the underlying frames are cold-start-overlap window where graphic-overlay carries OTS-panel score values that visually parrot-anchor onto the strip score reading.

**Predicted post-WS-U closure**:
- **If the bogus 63 originates as parrot-anchor onto an OTS-panel digit**: UD-prime's extended anti-priming (forbidden-graphic-digit rule) PARTIAL CLOSE (50% probability of closure on these 5 frames; sensitive to exact mode-collapse word).
- **If the bogus 63 originates as decode artifact / motion blur with Scout best-guessing**: `[UNREADABLE FRAME]` exit FULL CLOSE on these 5 frames (Scout demotes, no commit fires).
- **If the bogus 63 originates as legitimate-but-wrong Scout strip read** (no parrot-anchor, no decode artifact, just wrong): UD-prime NO-OP. WS-O.c's PA-threshold-tightening to 1.9*balls+10 catches the residue at the gate regardless.

**Predicted post-WS-U surface counts (vs c275807 baseline)**:
- `E2-phantom-runs`: 3 → 0-2 (partial-to-full close; depends on mode-collapse mechanism).
- Per-batter-ledger-drift: 5 → 3-5 (likely no change; drift is downstream of the overread, not at the same source).
- Conservation invariants: 5 → 0-3.

**Falsifiable prediction**: at step-3 baseline replay, if E2-phantom-runs drops from 3 to ≤1 AND conservation invariants from 5 to ≤2, UD-prime is CONFIRMED on the WS-O.c root. If both unchanged, UD-prime is FALSIFIED on this root (mechanism is not parrot-anchor; suggests legitimate Scout error → WS-O.c PA threshold remains the correct fix).

### §5.2 WS-P cohort — cold-start striker bat1/bat2 misorder (~50 fields)

**Cascade-root anchor frames**: first-committed-frame at DCKKR's cold-start, where SM's `_accept_initial` chose bat1=Rahul / bat2=Nissanka but cricket-truth striker was Nissanka.

**Predicted post-WS-U closure**:
- **If Scout's row-order on the cold-start frame was a parrot-anchor onto first-name-alphabetical or first-name-recency-prior**: UD-prime's extended anti-priming PARTIAL CLOSE (Scout demotes to all-null or emits both rows with `?` markers). SM's `_accept_initial` then exercises the `cold_start_no_indicator` default branch (per WS-P §2) and the squad-convention QA+QE from 88e03f5 fires correctly because Scout's `(none)` triggers the snapshotter's None-passthrough mirror.
- **If Scout's row-order reflects actual broadcast-frame ordering** (the striker was visually at bat2 row in that specific frame): UD-prime NO-OP. WS-P's structural fix is correct; the cascade root sits at the per-frame disagreement between broadcast row-position and cricket-truth striker identity.

**Predicted post-WS-U surface counts**:
- Striker-name swap fields: ~50 → 25-50 (likely partial; depends on how many of the ~13 swap balls trace back to a single cold-start parrot-anchored frame vs how many are independent broadcast-row-ordering events).

**Falsifiable prediction**: at step-3, if striker-name swap field count drops below 40 (i.e., closure of ≥10 fields), UD-prime is CONFIRMED partial. If swap count holds at ~50, UD-prime is FALSIFIED on this root (mechanism is broadcast row-position, not Scout parrot-anchor).

### §5.3 WS-Surface-E phantom-wicket F1017 (validate_dckkr_20260521_155356)

**Cascade-root anchor frames**: F1015 (wickets=6) + F1016 (wickets=4) on graphic-overlay frames; F1017 (wickets=5) is the +1 transition that fires the phantom WICKET event.

**Predicted post-WS-U closure**:
- **If F1015 + F1016 are graphic-overlay frames where the strip wickets-counter is partially occluded / decoder-corrupted / mid-cut**: `[UNREADABLE FRAME]` exit demotes BOTH frames, ball_detector sees prev_wickets=4-from-F1014 and current=5-at-F1017 (still a +1 transition!) → **NO CLOSURE on F1017 phantom**. The phantom fires regardless; UD-prime moves the prev-wickets anchor up by 2 frames but doesn't break the +1 chain.
- **However**, if `[UNREADABLE FRAME]` is paired with a downstream rule that ball_detector REQUIRES a non-graphic, non-unreadable previous-frame baseline (N=2 consensus on stable frames), UD-prime + the cooperating rule FULL CLOSE. But the cooperating rule is the reverted WS-Surface-E E1 HA' (61cd2d7 reverted at b7089a8).

**Predicted post-WS-U surface count**: F1017 phantom wicket → 1 (NO CHANGE). UD-prime alone does not close this cascade root.

**Falsifiable prediction**: at step-3, F1017 phantom wicket events on `validate_dckkr_20260521_155356` re-run → if 0, UD-prime UNEXPECTEDLY FULL CLOSE (would require investigation: what changed?). If still 1, UD-prime FALSIFIED on this root (expected).

### §5.4 YouTube test team-abbreviation thrash (9 codes / 174 reads on `866ce150`)

**Cascade-root anchor frames**: ~28 reads with bogus team codes (LIONS/LSG/RCB/KKR/MI/JAM/PR/SOU) on sponsor / promo / graphic frames.

**Predicted post-WS-U closure**:
- **Sponsor / promo strip frames**: `[UNREADABLE FRAME]` exit demotes when there's no clear scoreboard text → FULL CLOSE on LIONS reads (15/15).
- **IPL-graphic mis-read frames** (LSG / RCB / KKR / MI): the existing anti-priming forbidden-team list at SCOUT_PROMPT_SHORT lines 377-379 already covers these. The Track 1 prompt already lists `MI, RCB, KKR, LSG, CSK, DC, PBKS, GT, RR, SRH` as forbidden. If these 22 reads happened DESPITE the existing forbidden-team list, UD-prime's `[UNREADABLE FRAME]` exit MAY close them (graphic frames demoted entirely) — but this is the same failure mode that motivated the existing forbidden-team rule and that rule already exists. Likely PARTIAL.
- **Spurious 1-3 read franchises** (JAM/PR/SOU — 3+2+3): edge cases; UD-prime PARTIAL CLOSE.

**Predicted post-WS-U surface count**: bogus team-code reads ~28 → 10-15. Sponsor frames (LIONS) FULL CLOSE; IPL franchise mis-reads PARTIAL CLOSE.

**Falsifiable prediction**: at step-3 (if YouTube test fixture re-runnable), if bogus team-code count drops below 15 (≥45% reduction), UD-prime CONFIRMED. Note: this fixture is NOT the DCKKR baseline; verification requires a separate replay on the WI-vs-RSA dump.

### §5.5 Per-batter-ledger-drift residue (post-WS-O.b: 5 fields starting at 4.1)

**Cascade-root anchor frames**: balls 4.1-4.5 (overlaps with §5.1 — same residue window).

**Predicted post-WS-U closure**: tracks §5.1 closure. If WS-O.c root closes via parrot-anchor mechanism, this surface co-closes (downstream of the same source-frame error).

**Predicted post-WS-U surface count**: 5 → 0-3.

### §5.6 Closure prediction summary

| Cascade root | Baseline count | Predicted post-WS-U range | Closure-mechanism dependency |
|---|---|---|---|
| WS-O.c residue (E2-phantom-runs) | 3 | 0-2 | Depends on parrot-anchor mechanism on bogus-63 |
| WS-O.c conservation invariants | 5 | 0-3 | Same as above |
| WS-P striker-name swap fields | ~50 | 25-50 | Depends on broadcast row-ordering vs parrot-anchor |
| WS-Surface-E F1017 phantom wicket | 1 | 1 (NO CHANGE) | Mechanism is +1 ball_detector chain; UD-prime doesn't break it |
| YouTube team thrash (separate fixture) | ~28 | 10-15 | Sponsor frames FULL CLOSE; franchise mis-reads PARTIAL |
| Per-batter-ledger-drift | 5 | 0-3 | Co-closure with §5.1 |

**Aggregate prediction on DCKKR baseline**: total divergences 207 → 175-205 (range 1-15% reduction depending on mechanism). **WS-Surface-E F1017 expected NO CHANGE** — phantom wicket is a separate-mechanism defect. **WS-P expected PARTIAL or NO CHANGE** — sensitive to whether Scout's cold-start row-order is parrot-anchored or pixel-faithful.

**S9-strict-cascade-closure third-instance pattern**: WS-U is the FIRST workstream to explicitly target multiple known cascade roots simultaneously via a single source-level fix. IF the empirical closure surfaces ≥3 of the 6 cascade roots above (i.e., DCKKR drops to <190 divergences AND YouTube franchise reduction ≥45% AND any one of WS-O.c/WS-P closures), the S9-strict-cascade-closure pattern surfaces a third instance (after F1, S9, S18) and promotion at step-3 close-out is justified per user direction.

---

## §6 Regression-guard enumeration

Per `files/tests/baselines/dckkr_diff_post_ws_o_b_baseline.md`:

### §6.1 9 closed surfaces (must remain at 0)

| Surface | Baseline count | Required post-WS-U |
|---|---|---|
| E3-wicket-frame-misalign | 0 | 0 |
| D-post-FoW-striker | 0 | 0 |
| Extras-counter-drop | 0 | 0 |
| Bowler-W-credit-failure | 0 | 0 |
| Multi-ball-compression | 0 | 0 |
| Compound-with-wicket-token | 0 | 0 |
| C21b-symbol-revert | 0 | 0 |
| Silent-wicket-absorption | 0 | 0 |
| Surface J (per WS-Q step-1) | 0 | 0 |

### §6.2 7 active surfaces (must not increase)

| Surface | Baseline count | Required post-WS-U |
|---|---|---|
| G-pipeline-lag | 94 | ≤ 94 |
| F-A-commit-lag | 10 | ≤ 10 |
| Boundary-counter-double-increment | 8 | ≤ 8 |
| F-B-ad-occlusion | 8 | ≤ 8 |
| Per-batter-ledger-drift | 5 | ≤ 5 (target: 0-3) |
| Recent-overs-drop | 4 | ≤ 4 |
| E2-phantom-runs | 3 | ≤ 3 (target: 0-2) |

### §6.3 L2 + L1.5 invariants

| Fixture | Pass count | Required post-WS-U |
|---|---|---|
| L2 ledger (`tests/fixtures/dc_vs_kkr_2026_152064_ledger.json`) | 30 / 30 | 30 / 30 |
| L1.5 (load-bearing backward compat) | 90 | 90 |

### §6.4 Schema-parser regression risk

**~92 production sites + ~60 test sites** (per WS-Q step-1 enumeration) consume Scout output. UD-prime's `[UNREADABLE FRAME]` sentinel is a NEW output shape; parser hardening REQUIRED at:

1. `extract_regex.py:99` `_VT_LINE` — must recognize `[UNREADABLE FRAME]` as `(none)` equivalent.
2. `vision.py:_parse_tag` (line 927) — must accept absence of JSON tag line when `[UNREADABLE FRAME]` present, treating as `(has_strip=False, has_overlay_stats=False, drs_review=False)` → frame_type=ADVERTISEMENT/UNKNOWN equivalent.
3. `vision.py:_split_output` (line 974) — must handle `[UNREADABLE FRAME]` as empty description + None action.

**RISK ASSESSMENT**: parser-changes are LOW-RISK additions (sentinel-recognition only; no existing-shape modification). Can be landed as a single defensive-recognition patch before the prompt change ships.

**Alternative LOW-RISK PATH**: emit the existing STRIP-all-null + VISIBLE_TEXT: (none) + JSON-tag-with-all-false as the `[UNREADABLE FRAME]` equivalent (NO NEW SENTINEL). Parsers handle this shape today. Trade-off: loses the explicit "Scout chose to demote" signal but eliminates all parser-touch risk. **RECOMMEND THIS PATH** for step-2 (call it UD-prime-A); reserve the explicit sentinel (UD-prime-B) for a later workstream if observability signal becomes load-bearing.

---

## §7 §7.2 audit on leading candidate (UD-prime-A)

Gate-by-gate evaluation against the standing §7.2 audit discipline.

### Gate 1 — Pre-screen / fix-surface category

UD-prime-A is a **prompt-text edit at `vision.py:316-387` SCOUT_PROMPT_SHORT** (~30-50 line addition: extended anti-priming forbidden-phrase block + explicit UNREADABLE-frame guidance using the EXISTING all-null STRIP structure as the demotion sentinel, NO new sentinel introduction). PIPELINE-DIRECT per S28. **PASS**.

### Gate 2 — Causal predicate identification

The causal predicate is "VLM mode-collapses onto canned anchor when pixel evidence is weak". Track 2's `cbde6b8` evidence (96.1% mode-collapse on v1 prompt → 0% post-rewrite) is the load-bearing causal proof. Track 1's YouTube-test §3.1 anchor (9-code thrash across 174 reads) is the Track 1-specific causal proof. **PASS** with two-instance causal evidence.

### Gate 3 — Empirical anchor frame numbers

§1.1 cites F185 + F204 (YouTube SA→LIONS thrash); §1.2 cites balls 4.1-4.5 (DCKKR cold-start overread); §1.3 cites balls 0.5-3.6 cohort (DCKKR striker swap); §1.4 cites F1015/F1016/F1017 (DCKKR phantom wicket); §1.5 cites balls 4.1-4.5 (per-batter drift). All anchor frames have specific line numbers in source baselines. **PASS**.

### Gate 4 — Schema-parser breakage assessment

UD-prime-A reuses the existing STRIP-all-null + VT-(none) demotion shape. ZERO new output shapes; ZERO parser-touch required. **PASS**.

(Falsified path: UD-prime-B with explicit `[UNREADABLE FRAME]` sentinel FAILS gate 4 unless paired with defensive parser-recognition patch. UA — verbatim Track 2 port — FAILS gate 4 because Track 2's prose-only output breaks ~92 STRIP-parsing sites.)

### Gate 5 — Regression-guard coverage

§6 enumerates 9 closed + 7 active + L2 + L1.5. UD-prime-A's prompt-text edit affects only Scout output diversity (more `(none)` / all-null reads on unreadable frames; same structured output on readable frames). All-null reads are CURRENTLY HANDLED by downstream consumers (per existing `_VT_LINE` `(none)` handling). **PASS**.

### Gate 6 — Per-surface concrete predictions (deferred to step-3)

§5 enumerates per-cascade-root predictions with concrete frame numbers + predicted post-WS-U counts. Gate 6 verification at step-3 against locked predictions from §5 + §8.

---

## §8 Predicted-flip table for step-2 (locked at this memo)

Per S33 instrumentation-aware methodology: this table is LOCKED at step-1 close. Step-3 empirical replay against `c275807` baseline + WS-O.b baseline measures actual outcomes against predictions. Each row is independently falsifiable.

| Cascade root | Baseline (post-WS-O.b) | UD-prime-A predicted | Mechanism if HIT | Mechanism if MISS |
|---|---|---|---|---|
| E2-phantom-runs | 3 | 0-2 | Bogus-63 was parrot-anchor → demoted | Bogus-63 was legitimate Scout error → PA threshold (WS-O.c) is the correct fix |
| Conservation invariants | 5 | 0-3 | Same source as E2 → co-closure | Same source as E2 → independent close path needed |
| Per-batter-ledger-drift | 5 | 0-3 | Drift was downstream of bogus-63 source-frame | Drift is independent drift mechanism |
| Striker-name swap fields | ~50 | 25-50 | Cold-start frame Scout row-order was parrot-anchor | Cold-start frame Scout row-order is pixel-faithful (broadcast actually rendered Rahul first) |
| F1017 phantom wicket | 1 | 1 (NO CHANGE expected) | UNEXPECTED: investigate downstream cooperating rule | Expected: WS-Surface-E needs ball_detector consensus (reverted HA') |
| G-pipeline-lag | 94 | 94 (no change) | (regression guard — should not move) | (regression guard — should not move) |
| F-A-commit-lag | 10 | 10 (no change) | (regression guard) | (regression guard) |
| F-B-ad-occlusion | 8 | 6-8 (slight DECREASE possible) | `[UNREADABLE FRAME]` demotion on ad-occluded frames cleans up bowler-row noise | No change — bowler-row loss is upstream |
| Boundary-counter-double-increment | 8 | 8 (no change) | (regression guard — distinct mechanism from parrot-anchor) | (regression guard) |
| Recent-overs-drop | 4 | 4 (no change) | (regression guard — distinct mechanism) | (regression guard) |

**Aggregate forecast**: total divergences 207 → 175-205. Best case: 165 (if WS-O.c source-frame parrot-anchor mechanism FULL CLOSES AND WS-P striker swap PARTIAL CLOSES). Worst case: 205 (NO-OP across the board; F1017 unchanged as expected).

---

## §9 Sub-findings + S26-v2 + S33 application notes

### §9.1 Sub-finding 1: corrected reference commit

User-cited `cbeaeeb` is `feat(#64 follow-up #4): LOCKED state for one-way facts (batting_team)` on `files/confidence_tracker.py` — NOT the OpenScout rewrite. The actual OpenScout parrot-anchor fix is `cbde6b8` (2026-05-12). The cbeaeeb reference in the WS-U trigger appears to be a transcription error. Corrected throughout this memo.

### §9.2 Sub-finding 2: Track 1 prompt was independently rewritten same-day

Per `vision.py:316-387` SCOUT_PROMPT_SHORT header comment (2026-05-12), Track 1's primary SCOUT prompt was rewritten the SAME DAY as `cbde6b8` (OpenScout) and `fed5b5a` (vision.py scoreboard prompt referenced in the cbde6b8 commit body). The 2026-05-11/12 hallucination regression appears to have triggered a coordinated dual-track prompt overhaul. **WS-U's headline framing ("borrow Track 2's pattern") is partially obsolete**: the pattern was already borrowed in the same-day fix.

### §9.3 Sub-finding 3: the remaining gap is narrow

The genuine residue is (i) no explicit `[UNREADABLE FRAME]` sentinel (Track 1 uses STRIP-all-null + VT-(none) as functional equivalent), (ii) anti-priming forbidden-phrase list is name+team-focused, not graphic-overlay-digit-focused. Both are LOW-RISK extensions.

### §9.4 S26-v2 spot-check (twelfth+ instance footprint)

S26-v2 = "audit-before-patch surface category against historical footprint". WS-U's patch surface is **prompt-text edit at `vision.py:316-387`**. Historical footprint of vision.py SCOUT_PROMPT_SHORT edits:
- 2026-05-12 (the same-day anti-hallucination rewrite) — closed 2026-05-11/12 regression.
- 2026-05-02 (VISIBLE_TEXT step + team-null + overs-null hardening) — partial close.
- 2026-04-24 (V5 three-balanced-example prompt) — doubled bowlers_end strict precision 15.2% → 31.2%.
- 2026-04-19 (frame_phase + ball_position addition) — schema extension.

Each prior edit converged to a stable shape and remained in production. UD-prime-A's edit is consistent with this pattern (small text-only extension; no structural shape change). **S26-v2 spot-check PASS**.

### §9.5 S33 instrumentation-aware methodology — canonical application

S33 = "parallel-prompt comparison BEFORE flip; parallel-prompt running alongside existing prompt; shadow-diff structured fields; flip only after parity confirms zero schema-parser breakage". Canonical statement per WS-O.c step-1 §9 (two-instance evidence: WS-O OA + WS-P P1 NO-OPs).

**Application to WS-U step-2** (mandatory per WS-U trigger constraints):

1. Add `SCOUT_PROMPT_SHORT_V2` as a new module-level prompt constant (does NOT replace SCOUT_PROMPT_SHORT). Live behind `SCOUT_PROMPT_VARIANT=v2_shadow` env gate. Default is the existing prompt.
2. In dispatch path (`Vision.describe` at vision.py:512), when shadow mode is enabled, dispatch the existing prompt as PRIMARY and the V2 prompt as SHADOW. Log both raw responses to a sidecar JSONL at `files/logs/deliveries/<SID>/scout_prompt_shadow.jsonl`.
3. After running on DCKKR dump + one YouTube-test dump offline, diff structured fields (STRIP tokens, JSON tag fields) frame-by-frame across PRIMARY vs SHADOW.
4. **Parity criterion**: zero divergences on STRIP-parseable frames (= same team / runs / wkts / overs / batter / bowler tokens emitted) OR a divergence pattern that EXCLUSIVELY moves frames from a parseable shape to all-null demotion (i.e., V2 is more conservative, never more aggressive than v1 on positive content).
5. **Falsification criterion**: if V2 emits any STRIP-parseable shape with DIFFERENT structured values from v1 on the same frame (e.g., team=KKR in v1 → team=RCB in V2), V2 has introduced a new failure mode; STOP and refine.
6. If parity holds, proceed to flip (V2 becomes default; v1 retained under env gate for rollback).

**S33 third-instance evidence**: WS-O.c (NO-OP twice: WS-O OA + WS-P P1) is the canonical two-instance pattern. If WS-U step-2 surfaces a third instance (e.g., UD-prime-A shadow-comparison surfaces parity break → would-have-shipped-but-caught), promote S33 to numbered standing-discipline citation at step-3 close-out.

---

## §10 Step-2 entry data

### §10.1 Patch surface

**File**: `files/eyes/vision.py`
**Function-equivalent**: SCOUT_PROMPT_SHORT module-level string (lines 316-387)
**Edit shape**: text-only extension of two existing prose sections:

1. **ANTI-PRIMING RULES block** (vision.py:365-382): append two new bullets after the existing "Overs token" rule:
   - "Forbidden score-shape priors (unless literally in VISIBLE_TEXT this frame): generic round-number scores like 100-3, 150-4, 200-5, 250-6 from training data."
   - "Forbidden graphic-overlay digit parrot: if a side-panel / OTS-panel digit (run-rate denominator, partnership, target, kph) is the only number visible, do NOT use it as the strip score / wickets / overs. Strip values come from the strip alone."

2. **VISIBLE_TEXT step / unreadable-frame guidance** (vision.py:340-356): strengthen the existing `(none)` exit with explicit unreadable-frame authorization:
   - Replace "If the strip is partially visible or text is corrupted by decode artifacts / motion blur / overlay occlusion: transcribe only the parts you can clearly read, use ? for individual characters or words you cannot resolve. Do NOT guess from team context." with: "If the strip is missing OR fully unreadable (blank / decoder-corrupted / fully ad-occluded / mid-cut), emit `VISIBLE_TEXT: (none)` and `STRIP: null null-null (null) | extras=null | this_over=null | null null(null) | null null(null) | null null-null (null)` then stop. If the strip is partially visible, transcribe only clearly readable parts with `?` for unresolved characters."

3. **Optional UNREADABLE FRAME observability** (deferred to UD-prime-B; not part of UD-prime-A): an explicit `[UNREADABLE FRAME]` sentinel would require parser-touch at extract_regex.py:99 + vision.py:_parse_tag + vision.py:_split_output. UD-prime-A reuses existing all-null shape; UD-prime-B is a future-workstream option.

### §10.2 S33 instrumentation-aware verification protocol

**Step 2.0 (instrumentation)**:
- Add `SCOUT_PROMPT_SHORT_V2` constant alongside `SCOUT_PROMPT_SHORT` in vision.py.
- Add `SCOUT_PROMPT_VARIANT` env gate (default empty; values: `v2_shadow` for shadow mode, `v2_primary` for flip).
- In `Vision.describe`, if `SCOUT_PROMPT_VARIANT == "v2_shadow"`, dispatch both prompts in parallel via `asyncio.gather`. Log both raw responses to sidecar JSONL.
- Add trace-emitter typed tag `SCOUT-SHADOW-DIVERGENCE` when STRIP fields differ between PRIMARY and SHADOW.

**Step 2.1 (shadow replay)**:
- Run `test_pipeline.py` against DCKKR dump under `SCOUT_PROMPT_VARIANT=v2_shadow` + `SCOUT_RAW_DUMP=1`.
- Optionally also against `866ce150.jsonl` (YouTube WI-vs-RSA) if fixture re-runnable.

**Step 2.2 (parity diff)**:
- Build a script `files/scripts/scout_prompt_shadow_diff.py` that reads the shadow JSONL and reports per-frame structured-field divergences.
- Parity criterion (§9.5 #4) and falsification criterion (§9.5 #5) applied.

**Step 2.3 (decision)**:
- If parity holds on DCKKR (+ YouTube if available), proceed to flip: set `SCOUT_PROMPT_SHORT = SCOUT_PROMPT_SHORT_V2`, retain v1 as `SCOUT_PROMPT_SHORT_V1` under env gate for rollback.
- If parity breaks, refine V2 prompt to address the divergence shape; re-shadow; iterate.

### §10.3 Step-3 validated baseline replay plan

**Step 3.0**: confirm post-flip prompt is `SCOUT_PROMPT_SHORT_V2` per `SCOUT_PROMPT_VARIANT=v2_primary` or default flip.

**Step 3.1**: run snapshotter against same DCKKR dump with V2 prompt. Produce `/tmp/dckkr_post_ws_u_pipeline_snapshots.jsonl`.

**Step 3.2**: produce diff baseline `files/tests/baselines/dckkr_diff_post_ws_u_baseline.md` against `files/tests/fixtures/dckkr_ground_truth_ui_snapshots.jsonl` using existing diff-baseline-generation tooling.

**Step 3.3**: compare per-surface counts vs post-WS-O.b baseline (immutable comparator `c275807`):
- E2-phantom-runs: target 0-2 (was 3).
- Conservation invariants: target 0-3 (was 5).
- Per-batter-ledger-drift: target 0-3 (was 5).
- Striker-name swap fields: target 25-50 (was ~50).
- F1017 phantom wicket: target 1 (was 1; NO CHANGE expected).
- Other regression-guard surfaces: must not increase (§6).

**Step 3.4 (outcome decision tree)**:
- **FULL CLOSURE** (≥3 cascade roots close significantly + zero regressions): WS-U is FULL HIT; S9-strict-cascade-closure third-instance pattern surfaces; promote at step-3 close-out per user direction.
- **PARTIAL CLOSURE** (1-2 cascade roots close significantly + zero regressions): WS-U is PARTIAL HIT; lock the V2 prompt; remaining cascade roots fall to follow-on workstreams (WS-O.c, WS-P refinements, WS-Surface-E re-investigation).
- **NO-OP** (no cascade roots close significantly + zero regressions): WS-U is BENIGN NO-OP; remove the shadow scaffold; document as falsification of the parrot-anchor hypothesis on Track 1 (the same-day 2026-05-12 fix was sufficient); cascade roots are confirmed separate-mechanism defects.
- **REGRESSION** (any regression-guard surface increases): rollback to v1 immediately; refine V2 prompt; re-shadow.

### §10.4 Hypothesis enumeration ≥4 (§7.2 gates 1-3 static)

| Hypothesis | Description | Gate-1 status | Gate-4 status | Verdict |
|---|---|---|---|---|
| **UA** | Direct port: prepend Track 2's prompt verbatim to existing Track 1 prompt | FAIL (prose-only Track 2 output breaks STRIP-parsing schema) | FAIL | FALSIFIED at gate 1 |
| **UB** | Schema-preserving adaptation: VISIBLE_TEXT step + structured fields after (full rewrite) | PASS | UNCERTAIN (large rewrite risks unmeasured parser interactions) | FALSIFIED at gate 4 (excessive surface area) |
| **UC** | Two-pass within single VLM call: VISIBLE_TEXT then structured, with explicit two-pass framing | PASS | UNCERTAIN (Scout latency budget at 60 fpm with two passes risks TPM exhaustion per `vision.py:307-315` SHORT-prompt motivation) | FALSIFIED at gate 4 (latency risk on hot path) |
| **UD** | Minimal change: anti-priming + UNREADABLE exit only | PASS | PASS (if reusing existing all-null shape; FAIL if introducing new sentinel) | SURVIVES → refined to UD-prime-A |
| **UE** | Cohort split: different prompts for SHORT vs VERBOSE | FAIL (VERBOSE is env-flagged and already has the 2026-05-02 hardening; SHORT cohort-split is structurally identical to UD; cohort framing adds zero value) | n/a | FALSIFIED at gate 1 (no cohort distinction) |
| **UD-prime-A** | UD refined: anti-priming extension (2 new bullets) + unreadable-frame guidance using EXISTING all-null shape (no new sentinel, no parser-touch) | PASS | PASS | LEADING CANDIDATE |
| **UD-prime-B** | UD refined: anti-priming extension + explicit `[UNREADABLE FRAME]` sentinel + parser-touch at extract_regex.py + vision.py | PASS | UNCERTAIN (parser-touch is low-risk but expands surface beyond prompt-text-only) | DEFERRED (post-UD-prime-A; only if observability signal becomes load-bearing) |

**Static-falsification count**: 4 (UA, UB, UC, UE). **Leading candidate**: UD-prime-A.

---

## §11 Stop conditions met

Per WS-U trigger stop-conditions:
- "Static chain converges on single leading candidate with gates 1-5 PASS → STOP, report, recommend step-2." → **MET**. UD-prime-A converged at §10.4; gates 1-5 PASS at §7.
- Schema-parser breakage NOT surfaced for UD-prime-A (no parser-touch required).
- 4 static falsifications < 8 cap.

---

## §12 Working-tree state

This is a docs-only memo. Static investigation. No production-code edits. Single docs commit on `derive-not-detect`.

Untracked files predating this investigation (from `git status`): scripts under `files/scripts/broadcast_mode_tuning/`, `files/scripts/analyze_gap_*.py` — unrelated to WS-U.
