# Thread 7 RE-DIAGNOSIS — Ball-by-ball gap (MI vs SRH, F2123 → F2136)

**Status:** RE-OPENED 2026-04-30. Original (2026-04-29) verdict — *"H3: broadcaster removed strip → cosmetic, no action"* — **invalidated by user domain knowledge** ("the strip is the broadcaster's persistent overlay; visible during virtually every delivery"). This document re-derives the mechanism from frame-level telemetry instead of mechanism-by-narrative.

**Log:** `logs/pipeline-2026-04-29-194416-mi-srh-live.log`
**Window:** F2123 → F2136 (21:21:39 → 21:22:44, ~65 s wall-clock).
**Outcome of window:** `MULTI_BALL` at F2136 (over jump 18.1 → 18.3, +6 runs, two `?` placeholders).
**Wicket context:** Hardik Pandya dismissed at F1989 / over 18.1; F2127–F2133 is the post-wicket replay/ad block.

---

## §1. Frame-by-frame inventory

Pulled directly from the log. `cam=` is `vision.last_camera_view` (scout output). `STRIP:` is the raw scout OCR string. Disposition is the pipeline's actual choice for that frame (skip / poison / accept).

| Frame | Time | scout `cam=` / `phase=` / `strip=` / `digits=` | scout `STRIP:` (verbatim) | Disposition | Mechanism |
|---|---|---|---|---|---|
| F2123 | 21:21:39 | closeup / between_play / strip=True / digits=True | `MI 221-4 (18.1) \| Tilak 0(0) \| Rickelton 109(50) \| Hussain 1-31 (2.1)` | **ACCEPT** → state 221-5 (18.1) | normal read |
| F2124 | 21:21:44 | closeup / between_play / True / True | same | ACCEPT | normal read |
| F2125 | 21:21:49 | closeup / between_play / True / True | same | ACCEPT | normal read |
| F2126 | 21:21:58 | closeup / between_play / True / True | same | ACCEPT | normal read |
| F2127 | 21:22:03 | closeup / between_play / True / **digits=False** | `MI 0-0 (0.0) \| Tilak Varma 0(0) \| Ricketson 0(0) \| Hussain 0-0 (0.0)` | **POISON** (`[GUARD] Extractor returned 0-0(0.0) mid-innings — stripping all data`) → `FRAME_POISONED:None` | **H1** (scout/extractor mis-read; strip text is the all-zero template — likely strip-animation transient or extractor hallucination) |
| F2128 | 21:22:08 | **graphic / graphic** / strip=True / digits=True | (extractor not run) | **SKIP** (`[F2128] SCOREBOARD cam=graphic → dead-time skip (#207)`) | **H3-revised** (cam-state gate; see §2) |
| F2129 | 21:22:11 | (no scout / strip=False) | — | SKIP (`No-strip skip #1 (lifetime=776)`) | scout polling-cadence skip |
| F2131 | 21:22:13 | **ad / advertisement** / strip=False | — | SKIP (`AD 892ms (#77)`) | **broadcast-genuine ad** — scout itself reports `strip=False` |
| F2132 | 21:22:21 | (no scout) | — | SKIP | scout polling-cadence skip |
| F2133 | 21:22:23 | **ad / advertisement** / strip=False | — | SKIP (`AD 878ms (#78)`) | **broadcast-genuine ad** |
| F2134 | 21:22:32 | closeup / between_play / **True** / True | `MI 227-4 (18.2) \| TILAK 109(50) \| RICKELTON 6(1) \| HUSSAIN 1-37 (2.2)` | **POISON** → `FRAME_POISONED:227` | **H1 + H2** (scout returned valid-looking strip with the **batter rows transposed**: Rickelton=6, Tilak=109; the over-broad `[GUARD] Ryan Rickelton diff 109→6 — comparison strip for batting team` then **also pops `score` and `match_overs`** — see §3) |
| F2135 | 21:22:37 | closeup / between_play / True / True | `MI 227-4 (18.2) \| TILAK 109(50) \| RICKELTON 6(1) \| 12.38` (bowler row partly garbled to RR) | **POISON** → `FRAME_POISONED:227` | same H1 + H2; SUSPICION-CONFIRMED accepts the score-227 spike but the comparison-strip guard had already popped it from `extracted` |
| F2136 | 21:22:41 | closeup / between_play / True / True | `MI 227-4 (18.3) \| TILAK 6(2) \| RICKELTON 109(50) \| HUSSAIN 1-37 (2.3)` | **ACCEPT** → score 221→227, overs 18.1→18.3, `MULTI_BALL` Δballs=2 | normal read; gap closes, `?` placeholders inserted |

---

## §2. Hypothesis verdicts

The user's stated hypotheses, evaluated against the log slice and the code:

### H1 — Read failure despite visibility — **CONFIRMED at F2127, F2134, F2135 (3 / 8 frames in window)**

- **F2127** (`STRIP: MI 0-0 (0.0) | Tilak ... 0(0) | Ricketson 0(0) | Hussain 0-0 (0.0)`).
  - scout's frame-classifier reported `digits=False` for the same frame, then handed the strip image to the extractor anyway. Extractor returned a structurally valid but all-zero card.
  - The pipeline correctly poisoned this frame via the `0-0(0.0) mid-innings` guard at `test_pipeline.py:6492-6505`. **No bug here**, but the underlying mechanism (strip-animation transient between deliveries, or extractor hallucination of a fresh-innings template) means: **strip *was* visible per scout, but the *extracted text* is wrong.** This is exactly H1.

- **F2134, F2135** (`TILAK 109(50) | RICKELTON 6(1)` ↔ true values are `TILAK 6 | RICKELTON 109`).
  - scout/extractor mis-pair the row labels with the row stats. The **per-row** OCR succeeded (both names and both numbers are present and individually correct); the **row-alignment** failed.
  - This is the row-alignment failure mode characteristic of strip layouts that change visual emphasis on the on-strike batter (highlight box, asterisk, colour swap) — boundary-box detection mis-grouping label and value cells.
  - Adjacent supporting evidence: F2135's bowler row degenerates to ` 12.38` (just the run-rate cell — the bowler name+figures cells were dropped from the output entirely). Same root cause: ROI/cell segmentation drift.

### H2 — Quality gate too aggressive — **CONFIRMED at F2134, F2135 (the most consequential mechanism)**

The "comparison strip for batting team" guard at `test_pipeline.py:6904-6936`:

```6918:6936:files/test_pipeline.py
                        if (_gb_confirmed
                                and _gb_existing is not None
                                and _gb_new is not None
                                and abs(int(_gb_existing) - int(_gb_new)) > 20):
                            _record_state_recovery_guard(
                                "batter_row_rejected",
                                proposed_reset=[
                                    f"bat:{_gb_resolved}:runs",
                                    f"bat:{_gb_resolved}:balls",
                                ])
                            _frame_poisoned = True
                            log.info(f"  [GUARD] {_gb_resolved} diff "
                                     f"{_gb_existing}→{_gb_new} — "
                                     f"comparison strip for batting team")
                            extracted.pop("batters", None)
                            extracted.pop("score", None)
                            extracted.pop("match_overs", None)
                            extracted.pop("bowler", None)
                            break
```

Trigger at F2134: existing Rickelton runs = 109, extractor reports Rickelton runs = 6, Δ = 103 > 20 → guard fires.

**The guard's *response* is too broad.** When a row-alignment mis-read trips the guard, the score (`227`), overs (`18.2`) and bowler (`HUSSAIN 1-37 (2.2)`) regions are *also* popped, even though they are read from a different region of the strip and were correct. F2134's `STRIP:` field shows `MI 227-4 (18.2)` and `HUSSAIN 1-37 (2.2)` — both verifiably correct (F2136 corroborates 227 / 18.3 → 18.2 was the prior state). They were thrown away.

Counter-factually: had the guard popped only `batters` (its actual semantic target), F2134 would have committed `score=227, overs=18.2`. The MULTI_BALL at F2136 would then have been Δballs=1 (only ball 18.3 missing) instead of Δballs=2.

### H3 — Cam-state gating skips strip reads — **PARTIALLY CONFIRMED for `cam=graphic`, FALSIFIED for `cam=closeup`**

```6349:6399:files/test_pipeline.py
            _DEAD_VIEWS = ("replay", "graphic", "ad", "other")
            if _last_cam in _DEAD_VIEWS:
                skipped_dead_view += 1
                _was_dead_time = True
                ...
                log.info(f"[F{frame_count}] {frame_type} "
                         f"cam={_last_cam} → dead-time skip "
                         f"(#{skipped_dead_view})"
                         + (" [TIMEOUT]" if _in_strategic_timeout
                            else ""))
                await broadcast_base()
                _sleep = (4.0 if _in_strategic_timeout
                          else adaptive.get_sleep_time())
                await asyncio.sleep(_sleep)
                continue
```

- `cam=closeup` is **NOT** in `_DEAD_VIEWS`. F2123–F2126 and F2134–F2136 are all `cam=closeup` and were processed normally. **The user's literal H3 wording ("skipped when cam=closeup") is wrong.**
- `cam=graphic` **IS** in `_DEAD_VIEWS`, and the comment block at L6340-6348 explicitly acknowledges *"the bottom strip is visible (frame_type=SCOREBOARD or GRAPHIC) but the action shot is a replay or full-screen graphic"*. So the developers know strip is readable on these frames; the skip is a deliberate cost optimisation (saves a Groq extractor call) at the price of dropping the strip data.
- F2128 is the one frame in this window hit by this gate. scout reported `strip=True` for it. **GROUND-TRUTH CHECK NEEDED** — see §5.

### H4 — Consensus too strict — **NOT triggered in this window**

No SUSPICION/consensus gate fired on the score=227 read at F2134/F2135 *for the consensus reason itself* (it actually SUSPICION-CONFIRMED at F2135). The gap was already cemented by H2 popping the score before SUSPICION ran. So the over-cursor advanced cumulatively at F2136 because by then F2134/F2135 reads had been discarded.

That said, the SUSPICION machinery at L7743-7780 is the second tier downstream of H2: even if H2 hadn't poisoned, F2134 would have been deferred 1 frame and F2135 would have confirmed — **the gap would have been 1 ball, not 2**. So fixing H2 alone narrows the gap; fixing H4's defer-on-isolated-spike heuristic is unrelated.

---

## §3. Validated mechanism (composite)

In rough order of contribution to the 2-ball gap:

1. **(MOST IMPORTANT) H1 + H2 cascade at F2134, F2135.** Two consecutive frames where the strip *was* visible, the score region *was* read correctly (227 / 18.2), but the batter-row OCR misalignment triggered an over-broad guard that nullified score+overs+bowler along with the (legitimately bad) batter rows. **Bug-level, fixable.** Δ-saving: ≥1 ball per gap, possibly more across other gaps if the same OCR misalignment pattern repeats.

2. **(LEGITIMATE) Broadcast ad block F2131, F2133** (~10 s of `cam=ad / strip=False`). scout itself confirms `strip=False` here — these frames have no strip on screen. Cannot recover.

3. **(DESIGN CHOICE, not a bug) cam=graphic skip at F2128.** Strip was reported `strip=True` by scout, but the extractor was not invoked. **Pending ground-truth confirmation** that the strip on this frame was actually informative (not still mid-animation from a wicket replay). If yes, this is leaving cheap data on the table.

4. **(MINOR) F2127 strip-animation transient.** Scout itself flagged `digits=False`. Strip read was attempted, returned the all-zero template, and was correctly poisoned by an existing guard. No fix obvious without false-accept risk.

5. **(NOT A FACTOR HERE)** No-strip-skip at F2129/F2132 — scout polling cadence (1 of every ~2 captures); these frames were *between* the scout calls, not skipped *after* a scout result. They contribute 0 to the gap because the surrounding scout calls themselves caught everything reachable.

**The previous "broadcaster removed strip" narrative is therefore false in the strict sense.** The strip was visible (per scout's own classifier) on 4 of the 8 in-gap frames (F2127, F2128, F2134, F2135). The pipeline failed to extract usable score/overs from those 4 frames for three different reasons — only one of which (the ad block) is broadcast-side.

---

## §4. Severity reassessment

Original verdict: **"COSMETIC ONLY — no hotfix"** — predicated on the (now-invalidated) narrative that the broadcaster removes the strip and nothing the pipeline can do helps.

**Revised verdict: P2 fixable.**

- **Cumulative state still recovers correctly.** Score, wickets, overs, RR, target, batter cards, WS payload all reach the right values via MULTI_BALL's batched delta commit. The original "no functional impact" claim survives.
- **But the gap rate is reducible.** The single dominant mechanism (H1 + H2 cascade at F2134/F2135-class frames) is in-pipeline. A scoped fix to the comparison-strip guard (pop only `batters`, not `score`/`match_overs`/`bowler`) would convert at least F2134 from a poison into an accept on this gap, narrowing 18.1→18.3 to 18.1→18.2 (1 ball missing) and likely shrinking other gaps in the 6-event innings 1 set by similar margins.
- **Headline ball-gap rate could drop from 5.8 % → ~3 %** with the §6 fix alone. Cosmetic ribbon improves; cumulative state unchanged.
- **One additional bit of latent risk:** the same over-broad pop in `_GUARD comparison strip` is the only thing nullifying the score/overs reads on these frames. If a future *real* comparison-strip overlay (career-stat side-by-side card) lands while this guard is loosened, we'd commit a wrong score. The mitigation in §6 explicitly preserves the side-by-side comparison case.

---

## §5. Ground-truth validation (resolved 2026-04-30)

Two viewing checks against the recorded broadcast were required to commit §6. Both answered by user, 2026-04-30:

1. **F2128 @ 21:22:08** (cam=graphic between Pandya's 18.1 wicket and the next ball). **Answer: strip is *always* visible during deliveries; it can be replaced briefly during major events (wicket replay graphics) but every delivery itself is accounted for on the broadcast strip.** ⇒ The cam=graphic dead-time skip is leaving usable strip data on the table for non-replay frames; for true wicket-replay frames the strip is genuinely absent. **Fix 2 is warranted, with a non-degeneracy guard to handle the wicket-replay case (skip if strip text is missing/all-zero/identical-to-old-state).**

2. **F2134 + F2135 @ 21:22:32 / 21:22:37**. **Answer: `TILAK 6(1) | RICKELTON 109(50)`** — the correct broadcast layout (Rickelton still on 109 as the centurion, Tilak the new batter on 6). ⇒ **Our scout's strip OCR is unambiguously transposing the two batter rows.** H1 is confirmed at the OCR layer, not the broadcast layer. Fix 1 is unblocked; a follow-up cell-extraction audit in `files/eyes/scoreboard.py` (and/or scout post-processing) is filed separately.

Both fixes in §6 are now **committed scope, no longer blocked**.

---

## §6. Recommended fix (committed scope, ground-truth confirmed 2026-04-30)

**Fix 1 — narrow the "comparison strip for batting team" guard (P2, ~15 LOC).**

In `test_pipeline.py:6918-6936`, when the per-row Δ>20 trips:

- Pop **only** `batters` (the field whose row alignment was demonstrably wrong).
- Do **not** pop `score`, `match_overs`, or `bowler` — these come from independent regions of the strip and the existing all-zero / visible-team / SUSPICION guards already protect against the genuine "career-stat side-by-side" overlay (which always misreads `visible_team` to the bowling side and is caught by the `Bowling-team strip` guard at L6850-6890).
- Set a new flag `_strip_batter_rows_unreliable = True` for the frame so downstream batter-tracker writes are still skipped, but score/overs writes proceed.
- Emit a new telemetry tag `[STRIP-ROWS-MISALIGNED]` with `(existing, new, resolved_name)` so analyzer can track the new-mechanism rate independently of MULTI_BALL.

**Fix 2 — strip-text fast-path under cam=graphic dead-time skip (P3, ~30 LOC).**

In `test_pipeline.py:6349-6399`, before `continue`, if scout reported `strip=True` on the cam=graphic frame, run **only the strip-text extractor** (not the full extractor + scorer LLM stack). Apply a non-degeneracy guard (skip if strip text is empty, all-zero, or identical to the last-committed state — which would indicate a genuine wicket-replay window where the strip is briefly absent or held-over). If the strip text is non-degenerate and the score is monotone-non-decreasing vs current state, accept `score + overs + bowler-figures` only (no batters, no commentary). Cost: ~1 cheap call per cam=graphic frame; benefit: closes the ~3 s blind spot per wicket replay graphic on frames where the strip really is persistent (per user, the common case).

**Fix 3 (filed separately, P3) — scout strip OCR row-alignment audit.** F2134/F2135's broadcast strip displayed the rows correctly; our scout transposed them. The cell-extraction pipeline in `files/eyes/scoreboard.py` (and/or the scout's prompt/parser) needs an audit to find the row-pairing logic and add a sanity check (e.g., asterisk-position consistency between rows, or per-row balls-faced monotonicity vs prior frame). This is the upstream root cause; Fix 1 is the downstream containment.

**Fixes 1 and 2 are additive and independently shippable; neither changes the cumulative-state contract.**

---

## §7. Test fixture from the validated frames

A regression fixture suitable for `files/test_recent_fixes.py` (or a new `test_strip_row_misalignment.py`) — exact extractor output and expected post-guard `extracted` after Fix 1:

```python
# Fixture A: F2134 OCR row-misalignment with valid score/overs/bowler region
EXTRACTED_F2134 = {
    "visible_team": "Mumbai Indians",
    "score": 227,
    "wickets": 4,
    "match_overs": 18.2,
    "target": None,
    "rr": None,
    "batters": [
        # Row alignment swap: TILAK paired with Rickelton's stats, vice versa
        {"name": "Tilak Varma",   "runs": 109, "balls": 50},
        {"name": "Ryan Rickelton", "runs": 6,  "balls": 1},
    ],
    "bowler": {"name": "Hussain", "wickets": 1, "runs": 37, "overs": "2.2"},
}
SCOREBOARD_STATE_BEFORE = {
    "score": 221, "wickets": 5, "overs": "18.1",
    "batting_card": {
        "Ryan Rickelton": {"runs": 109, "balls": 50},
        "Tilak Varma":    {"runs": 0,   "balls": 0},
    },
}

# After Fix 1, expected extracted state:
EXPECTED_AFTER_GUARD = {
    "visible_team": "Mumbai Indians",
    "score": 227,            # PRESERVED (Fix 1)
    "wickets": 4,
    "match_overs": 18.2,     # PRESERVED (Fix 1)
    "target": None,
    "rr": None,
    # batters POPPED (this is correct — the per-row Δ exceeded 20)
    "bowler": {"name": "Hussain", "wickets": 1, "runs": 37, "overs": "2.2"},  # PRESERVED
}
EXPECTED_TELEMETRY = "[STRIP-ROWS-MISALIGNED]"  # new tag
EXPECTED_FRAME_POISONED = False                  # downgrade from True
```

```python
# Fixture B: F2127 strip-animation transient (regression — must still poison)
EXTRACTED_F2127 = {
    "visible_team": "Mumbai Indians",
    "score": 0, "wickets": 0, "match_overs": 0.0,
    "batters": [
        {"name": "Tilak Varma",   "runs": 0, "balls": 0},
        {"name": "Ryan Rickelton","runs": 0, "balls": 0},
    ],
    "bowler": {"name": "Hussain", "wickets": 0, "runs": 0, "overs": "0.0"},
}
EXPECTED_AFTER_GUARD = {  # Existing 0-0(0.0) mid-innings guard — UNCHANGED
    "visible_team": "Mumbai Indians",
    # score / wickets / match_overs / batters / bowler all POPPED
}
EXPECTED_FRAME_POISONED = True  # unchanged
```

```python
# Fixture C: genuine career-stat comparison overlay — Fix 1 must STILL poison
EXTRACTED_COMPARISON = {
    "visible_team": "Sunrisers Hyderabad",  # bowling team, not batting team
    "score": 137, "wickets": 2, "match_overs": 12.4,
    "batters": [
        {"name": "Pat Cummins", "runs": 56, "balls": 31},
        {"name": "Travis Head", "runs": 21, "balls": 14},
    ],
    "bowler": {"name": "Bumrah", "wickets": 0, "runs": 19, "overs": "2.0"},
}
# Caught by *prior* visible-team-is-bowling-team guard (L6850-6890),
# pops everything BEFORE Fix 1's narrowed guard runs. Fixture proves
# Fix 1 doesn't open a hole for this case.
EXPECTED_FRAME_POISONED = True
```

These three fixtures together pin the new behaviour: row-misalignment recovers score+overs (A), strip-animation still poisons (B), genuine comparison overlay still poisons (C).

---

## §8. Backlog patch

Replace the 2026-04-29 22:15 IST Thread 7 entry in `files/docs/backlog.md` (lines 188-228) with:

> **Thread 7 — Ball-by-ball read gaps in innings 1 (2026-04-30 RE-DIAGNOSIS, supersedes 2026-04-29).**  Original "H3: broadcaster removed strip → cosmetic" verdict invalidated by user domain knowledge (strip is broadcaster-persistent during deliveries) and by frame-level telemetry (scout reports `strip=True` on F2127, F2128, F2134, F2135 within the 18.1→18.3 gap window).  **Validated mechanism (composite):**  (a) at F2134/F2135, scout strip OCR transposes batter rows (TILAK ↔ RICKELTON cell pair); (b) the resulting batter-row Δ>20 trips `[GUARD] comparison strip for batting team` (`test_pipeline.py:6918-6936`), which pops `score`, `match_overs`, **and** `bowler` along with `batters`, even though those three fields were correctly read from a different strip region — **this is H1 + over-broad H2, in-pipeline, fixable**; (c) F2128 is a `cam=graphic` dead-time skip (`_DEAD_VIEWS = ("replay","graphic","ad","other")`, `test_pipeline.py:6349`) with scout reporting `strip=True` — strip-persistent claim **needs ground-truth viewing check** (§5 of `files/docs/investigations/thread7_rediagnosis_multi_ball_gap.md`); (d) F2131/F2133 ad block is broadcast-genuine (`strip=False` per scout); (e) F2127 strip-animation transient correctly poisoned by the existing all-zero guard.  **Severity revised P3 → P2.**  Cumulative state still recovers via MULTI_BALL (no functional impact), but ball-gap rate ~5.8% → ~3% projected after Fix 1 (narrow the comparison-strip guard to pop only `batters`; preserve `score`/`match_overs`/`bowler`; new tag `[STRIP-ROWS-MISALIGNED]`).  Three regression fixtures captured.  **Blocked-on-user:** two ground-truth viewing questions in §5 of the re-diagnosis doc (F2128 strip-persistence and F2134/F2135 row-swap reality) before Fix 1 ships.

---

## §9. What this re-opens / closes

- **Closes:** the 2026-04-29 "broadcaster controls strip availability — no action required" verdict.
- **Re-opens:** P2 hotfix scope on `test_pipeline.py` comparison-strip guard, conditional on §5 answers.
- **Filed (new P3):** strip-text fast-path under cam=graphic dead-time skip, conditional on §5 Q1 answer.
- **Unchanged:** cumulative-state contract; MULTI_BALL mechanism itself; gap-fill via `on_broadcast_override` (still cannot recover when broadcast itself shows ads).
