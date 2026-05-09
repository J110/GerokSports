# Fix 8 — INFO-PANEL bowler-strip gate (content-based graphic gate)

**Bug**: P1 — when the broadcast camera was on a stats overlay (player
career stats, head-to-head, projected score, etc.) but the bottom
scoreboard strip was still partially visible, Scout's INFO_PANEL
extraction surfaced the overlaid player's name as `extracted["bowler"]`,
SM ingested it as the current bowler, and the pipeline locked in a
**future bowler ahead of the broadcast**.
**Backlog ref**: `files/docs/backlog.md` "P1: Bowler stats graphic
misread as bowler-change".
**Trace**: `logs/pipeline-2026-04-25-153247-dc-pbks-v5.log` F619, F643.

Concrete F619 (DC vs PBKS, 16:02:04):

```
STRIP: DC 68-1 (6) |   INFO_PANEL: YUZVENDRA CHAHAL IPL CAREER
                       MATCHES 181 WICKETS 225 ECONOMY 8.0
```

Marco Jansen was bowling the over. Chahal hadn't been introduced yet.
But the pipeline picked up `bowler="Yuzvendra Chahal"` from this stats
overlay; later when Chahal *was* introduced, the change had already
been (mis)applied — bowler change-detection sees no change because the
bowler is "already" Chahal.

This is independent of the BOWLER-STALE defense (shipped 2026-04-25),
which guards against *stale* bowler reads (someone who bowled
previously). The F619 pattern is the dual: a *future* bowler getting
locked in too early.

## Why the existing graphic-gate didn't catch it

`test_pipeline.py` already has two gates that should block stats-
overlay bowler reads:

1. **Dead-time skip** at the top of the active-play loop:
   `_DEAD_VIEWS = ("replay", "graphic", "ad", "other"); if _last_cam
   in _DEAD_VIEWS: continue`. When Scout tags the camera_view as
   `graphic`, the entire frame is skipped before any LLM scorer call.
2. **Frame-type GRAPHIC pop** at the SCOREBOARD-frame processing path:
   `if frame_type == "GRAPHIC": extracted.pop("bowler", None) ...`.
   Strips bowler when the top-level frame classifier called the frame
   GRAPHIC.

Both gates rely on Scout's classifier output. The F619 case slipped
through because **`vision.last_camera_view` lags scout response
arrival by 1-2 frames**. F619 ran with the previous frame's
`bowlers_end` tag (active play), so the dead-time skip didn't fire.
And `frame_type` was `SCOREBOARD` (the strip was visible), so the
frame_type==GRAPHIC pop didn't fire either.

A **content-based gate** — looking at the vision description text
directly for stats-overlay markers — doesn't depend on Scout's
camera_view tag arriving in time. That's the Fix 8 surface.

## Files modified

| file                              | lines added | net |
|-----------------------------------|-------------|-----|
| `files/test_pipeline.py`          | +60 (rewrote `filter_info_panel_contamination` from log-only no-op to actively-stripping gate; comment block expanded with bug context, rationale, telemetry intent) | +49 |
| `files/test_recent_fixes.py`      | +160 (helper + 5 tests + section header + TESTS wiring) | +160 |

## Source change (`test_pipeline.py:filter_info_panel_contamination`)

The function already existed. Pre-Fix-8 shape:

```python
def filter_info_panel_contamination(extracted, vision_desc, scoreboard):
    """If vision mentions an info panel, note it but let
    ConsistentReadTracker handle the actual rejection."""
    ...
    if not any(kw in upper for kw in _INFO_PANEL_KEYWORDS):
        return extracted
    log.info("  [INFO PANEL] Detected — tracker will bound values")
    return extracted
```

The detection was correct (`_INFO_PANEL_KEYWORDS` includes "IPL
CAREER", "CAREER", "IN T20", "HEAD TO HEAD", "PROJECTED SCORE", etc.)
— but the action was log-only.  Score / wickets bounding via the
tracker was sufficient for those fields, but **bowler ingest bypasses
the tracker** and goes through SM's `_build_scorecard` directly
(`score_manager.py:305 — card["bowler_name"] = frame.ext_bowler_name`).
So the graphic's bowler name flowed through unchallenged.

Post-Fix-8 shape (key change): strip `bowler`, `bowler_name`, and
`bowler_figures` from `extracted` when an info-panel keyword matches.
Score / wickets are NOT stripped — the tracker handles those.

```python
_matched_keyword = next(
    (kw for kw in _INFO_PANEL_KEYWORDS if kw in upper), None)
if not _matched_keyword:
    return extracted
if extracted.get("bowler") or extracted.get("bowler_name"):
    _bw = extracted.get("bowler") or {}
    _bw_name = (_bw.get("name") if isinstance(_bw, dict)
                else _bw) or extracted.get("bowler_name")
    log.warn(
        f"  [INFO-PANEL-GATE] bowler stripped — "
        f"name={_bw_name!r} panel_keyword={_matched_keyword!r}")
    extracted.pop("bowler", None)
    extracted.pop("bowler_name", None)
    extracted.pop("bowler_figures", None)
else:
    log.info(
        f"  [INFO PANEL] Detected (keyword={_matched_keyword!r}) "
        f"— no bowler in extracted, tracker will bound values")
return extracted
```

## Why bowler-only (and not score / wickets / batters too)

- **Bowler bypasses the tracker.** Score, wickets, and match_overs all
  flow through `ConsistentReadTracker`, which rejects impossible jumps.
  An overlay reading "WICKETS 225" doesn't pass the tracker's bounding
  (current wickets is in [0, 10]). Bowler doesn't have an analogous
  consistency check — any plausible-looking name passes.
- **Bowler is sourced fresh on every active-play frame.** The
  broadcast strip shows the current bowler continuously. Dropping the
  bowler signal from one stats-overlay frame loses no data; the next
  active-play frame re-confirms the actual bowler. Score / wickets
  also re-confirm but they have the tracker as a safety net regardless.
- **Stripping batters would over-fire.** Some legitimate stats
  overlays still have the live batting card visible (split-screen
  during a between-overs comparison). The tracker handles the
  impossible-jump case for batters too. Keep them.
- **The bug pattern is bowler-specific.** F619 and F643 both involve a
  bowler name in the INFO_PANEL. The career-stats and projected-score
  overlay class typically has one prominent player name on it; that
  name corresponds most often to the next-up bowler being introduced
  (broadcasters previewing the bowling change), which is exactly the
  failure mode.

## Tests added (`test_recent_fixes.py`)

Helper: `_StubScoreboardForInfoPanel` — minimal scoreboard-shaped
stub with a populated `_inn` dict so the function proceeds past its
early-return guard. Reused across all five tests.

1. `test_info_panel_gate_strips_bowler_on_career_keyword` — base case:
   "IPL CAREER" in vision_desc, bowler in extracted → bowler stripped,
   score / match_overs preserved.
2. `test_info_panel_gate_no_op_when_no_keyword` — negative case:
   legitimate bowler read with no info-panel keywords → bowler
   preserved (regression-protects against over-firing).
3. `test_info_panel_gate_f619_chahal_replay` — production replay of
   the exact F619 bug — "YUZVENDRA CHAHAL IPL CAREER MATCHES 181
   WICKETS 225 ECONOMY 8.0" overlay during Jansen's over → bowler
   AND bowler_figures stripped, score preserved.
4. `test_info_panel_gate_logs_only_when_no_bowler_present` — edge
   case: info-panel keyword present but no bowler in extracted →
   no-op, no exception, returns extracted dict unchanged.
5. `test_info_panel_gate_strips_all_three_bowler_fields` —
   comprehensive strip across `bowler` (dict), `bowler_name`
   (string, parallel SM-ingest field), and `bowler_figures` (stats
   string) when "PROJECTED SCORE" matches.

## Test results

```
PASS 238 / FAIL 2 (both pre-existing, unrelated to Fix 8)
```

All 5 Fix-8 tests PASS (15 sub-checks). Suite delta from post-Fix-7
state: +15 sub-checks, 0 regressions. The 2 pre-existing failures are
documented in `files/docs/backlog.md` "Test hygiene (P3)".

## Bundling note

This is fix #8 in the inter-match commit bundle. **Zero source-file
overlap with fixes 1-7's specific surfaces** — the modified function
`filter_info_panel_contamination` is at `test_pipeline.py:1677`,
unrelated to any other fix's lines. The fix does not interact with
any other fix in the bundle.

## Verification on first restart after deploy

`[INFO-PANEL-GATE]` log line is positive-firing — it should fire when
a stats overlay with a player name is processed during active play.
Search the post-restart pipeline log for:

```
[INFO-PANEL-GATE] bowler stripped — name='<NAME>' panel_keyword='<KEYWORD>'
```

Expected pattern: ~5-15 fires per match (every batter/bowler intro,
between-overs comparison graphics, head-to-head overlays). The
complementary `[BOWLER-STALE] ... reset` rate (the previously-shipped
defense for stale bowler reads) should remain steady — Fix 8 closes a
DIFFERENT class of bug than BOWLER-STALE.

Telemetry to watch over the first match-day:

- Count of `[INFO-PANEL-GATE]` fires per match. Target: 5-15. If
  zero across multiple matches, Scout isn't surfacing INFO_PANEL
  text or the keyword list needs broadening.
- Count of post-restart `[BOWLER-STALE]` fires. Should NOT change
  from baseline — Fix 8 doesn't touch that path.
- Spot-check: pick a known-bowler-change moment (e.g. opening
  bowler swap, or any over where a new bowler is introduced after
  a graphic). The bowler-change should land within 1-2 active-play
  frames after the graphic clears, NOT before the graphic starts.

## Residual / known limits

- **Keyword list is finite.** `_INFO_PANEL_KEYWORDS` covers
  career-stats / season / head-to-head / projected-score patterns.
  A novel overlay class with a player name and stats but no matching
  keyword (e.g. a Hindi-language broadcast with localized labels)
  would slip through. If post-deploy telemetry shows missed cases,
  add to the keyword list — single-line append, no architectural
  change required.
- **Score / wickets are NOT stripped on info-panel match.** Per the
  rationale above (tracker handles them) this is intentional, but
  it does mean an info-panel frame that ALSO has a corrupted score
  read could still affect the tracker's consistency window. The
  tracker is robust against single-frame corruption (its consensus
  layer needs multiple agreeing frames before committing) so this
  is acceptable in practice; flag for re-evaluation if a score-
  corruption-via-info-panel pattern surfaces in production.
- **Bowler is dropped, not corrected.** Fix 8 strips the misread
  bowler but doesn't try to identify the *correct* bowler. SM
  retains its existing bowler from the previous frame, which is
  what we want — the next active-play frame re-confirms via the
  broadcast strip. The 1-2 second delay this introduces in
  bowler-change pickup is well below the human-perceptible
  threshold.
- **Detection is text-string-match only.** Doesn't attempt to use
  visual cues (overlay layout, font, position). A more robust
  detector could use the layered Scout output (separate INFO_PANEL
  vs STRIP regions) — currently the function looks at the
  concatenated `vision_desc`. If keyword matching false-positives
  on legitimate live-strip text in production, a structured-
  region-aware variant becomes the natural follow-up.
