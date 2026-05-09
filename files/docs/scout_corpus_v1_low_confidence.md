# Scout Corpus v1 — Low-Confidence Frames

6 of 41 frames were labeled with `confidence: medium`. All are preserved in `scout_corpus_v1.json`; this file surfaces them for focused review.

All other 35 frames were `high` confidence.

---

## F020 — `active_play_recall`
- **Path**: `debug_frames/f20_scoreboard.jpg`
- **Scout**: `bowlers_end` / `release`
- **Human label**: `other` / `between_play`
- **Why medium**: Very dark frame — looks like a crowd/camera-side dusk shot with the scoreboard strip visible but no pitch. Clearly not `bowlers_end` and clearly not a standard play view, but hard to disambiguate further between `other` and `closeup` because the low light obscures what's actually in front of the camera.
- **Reviewer question**: does the rubric's "other" bucket absorb this, or should I have treated it as `closeup` given the dominant dark foreground figure?

## F174 — `batter_closeup_with_background` (selection: +5 after FOUR @ F169)
- **Path**: `debug_frames/f174_scoreboard.jpg`
- **Scout**: `bowlers_end` / `between_play`
- **Human label**: `graphic` / `graphic`
- **Why medium**: Wide stadium aerial with the broadcaster's projected-score panel replacing the scoreboard strip and occupying the entire lower third. A pitch + tiny players are visible in the distance but the frame's dominant information is the overlay. Per rubric I treated as `graphic`, but a case could be made for `bowlers_end` (elevated wide-shot with pitch faintly visible) since the main cricket content is behind the graphic rather than being replaced by it.
- **Reviewer question**: when a stats strip replaces the scoreboard but the upper portion is still a wide stadium shot, is the rubric's "graphic" threshold met or does the wide-shot still dominate? Result here affects the variant precision bookkeeping for `graphic` vs `bowlers_end`.

## F175 — `batter_closeup_with_background` (selection: +6 after FOUR @ F169)
- **Path**: `debug_frames/f175_scoreboard.jpg`
- **Scout**: `bowlers_end` / `release`
- **Human label**: `bowlers_end` / `runup`
- **Why medium**: Similar overlay as F174 (projected-score strip at bottom) but the upper portion of the frame is a clean bowlers_end view with pitch receding, bowler running in, batter + umpire + keeper visible. I called this `bowlers_end` because the cricket geometry is readable above the overlay. If my call on F174 is wrong (i.e. "overlay dominates → graphic"), then this one should flip too for consistency.
- **Reviewer question**: keep F174/F175 consistent — both graphic or both bowlers_end?

## F311 — `disambiguation / closeup_between_play`
- **Path**: `debug_frames/f311_scoreboard.jpg`
- **Scout**: `closeup` / `between_play`
- **Human label**: `closeup` / `between_play`
- **Why medium**: Post-innings reporter interview with a GT player holding an IPL microphone in front of a full sponsor-logo wall. The sponsor wall dominates the frame's left/right edges, but the subject is a human in closeup. Per rubric "closeup" wins since a person is the primary subject, but the sponsor wall tips this toward "graphic-adjacent". Scout agreed with my call, so this is not a precision failure — flagging for rubric edge-case confirmation.
- **Reviewer question**: is an interview in front of a sponsor board correctly bucketed as `closeup`, or does the rubric want an explicit "interview" subcategory?

## F756 — `batter_closeup_with_background` (selection: +6 after EXTRA @ F750)
- **Path**: `debug_frames/f756_scoreboard.jpg`
- **Scout**: `bowlers_end` / `release`
- **Human label**: `side_on` / `fielder_reaction`
- **Why medium**: Fielder is chasing a ball toward the boundary; the upper third has IPLFantasy boundary ad boards, the middle has some pitch visible, the lower third has a fielder running. Camera angle is elevated and offset to the side, not behind the stumps. I labeled `side_on` because the pitch runs left-to-right rather than receding, but a case for `bowlers_end` exists since you can still see the pitch geometry.
- **Reviewer question**: when the camera is elevated side-of-field and the pitch is visible but not the primary axis, does this count as `side_on` or `bowlers_end`?

## F940 — `batter_closeup_with_background` (selection: +3 after EXTRA @ F937)
- **Path**: `debug_frames/f940_scoreboard.jpg`
- **Scout**: `bowlers_end` / `release`
- **Human label**: `side_on` / `between_play`
- **Why medium**: Wide side-on outfield view with pitch horizontal across the bottom, KOHLI 101* stat strip at the bottom, crowd/boards across the top. Camera is elevated and off-axis from the pitch. Similar framing question to F756 — "wide field view with pitch visible but not receding" is the borderline case. I called `side_on`.
- **Reviewer question**: consistent treatment with F756.

---

## Pattern the low-confidence frames share

Four of the six medium calls (F174, F175, F756, F940) hinge on the same rubric question:

> **When the pitch is visible in a wide/elevated shot but the camera axis is not along the pitch (not receding from camera), does that count as `bowlers_end` or `side_on`/`graphic`?**

My working interpretation was: `bowlers_end` requires the pitch to recede from foreground into distance (classic "along-axis" view); anything side-elevated is `side_on` even if the pitch is visible. If you'd prefer a more permissive `bowlers_end` definition that accepts slightly off-axis wide shots, F175, F756, and F940 would flip.

This is the single rubric ambiguity that will most affect the shadow-run scoring. Your call on this determines roughly 3 frames' worth of bowlers_end precision/recall.

## Turnaround

I estimate you'd want ~10-15 min to confirm these. If you want to adjust labels, reply with the frame_id + new label + (optional) rubric clarification to bake into `scout_labeling_rubric_v1.md`. I'll update `scout_corpus_v1.json` and proceed to the shadow run.
