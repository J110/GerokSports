# Replay/Recap Inset Detection — Diagnosis (P3)

Investigation memo for the recap-overlay phantom (`47-3`, `49-3 (X.X)`) that
recurs across the CSK vs MI 44th Match (2026-05-02). Source logs:

- Innings 1 — `logs/pipeline-2026-05-02-1928-csk-vs-mi-44th-match-ipl-2026.log`
- Innings 2 — `logs/pipeline-2026-05-02-2049-csk-vs-mi-44th-match-ipl-2026-innings2.log`

Read-only investigation. Line numbers below are absolute (`grep -n`).

## §1 Recurring phantom catalog

Every Scout STRIP read containing `47-3` or `49-3` across both logs. `tag` is
the value emitted by the Scout classifier on the `[SCOUT]` line and echoed
into the per-frame `DETAIL|...|tag=...` summary. `action` is the one-line
"action" / scout-description field from `DETAIL`. `cam` / `phase` from the
`[SCOUT]` line.

### Innings 1 (pipeline-...-1928)

| Frame | Time     | Tag        | cam / phase                | Strip score      | action                                                                 | Log line |
|-------|----------|------------|----------------------------|------------------|------------------------------------------------------------------------|----------|
| F8    | 19:29:07 | SCOREBOARD | bowlers_end / between_play | CSK 47-3 (7.5)   | —                                                                      | 235      |
| F53   | 19:31:07 | SCOREBOARD | closeup / between_play     | null 47-3 (null) | —                                                                      | 564      |
| F55   | 19:31:21 | SCOREBOARD | closeup / between_play     | null 47-3 (null) | A player, likely Ruturaj, is being closely framed.                     | 603      |
| F94   | 19:33:54 | SCOREBOARD | bowlers_end / shot         | null 47-3 (null) | A batsman is playing a shot.                                           | 1243     |
| F96   | 19:34:02 | SCOREBOARD | (cam unread)               | MI 47-3 (9.2)    | —                                                                      | 1315     |
| F208  | 19:40:44 | SCOREBOARD | bowlers_end / release      | null 47-3 (null) | The bowler is releasing the ball.                                      | 3081     |
| F211  | 19:40:49 | SCOREBOARD | closeup / between_play     | null 47-3 (null) | —                                                                      | 3103     |
| F235  | 19:42:29 | SCOREBOARD | closeup / between_play     | null 49-3 (7.5)  | —                                                                      | 3657     |
| F238  | 19:42:40 | SCOREBOARD | closeup / between_play     | null 49-3 (8.4)  | —                                                                      | 3715     |
| F315  | 19:46:27 | SCOREBOARD | bowlers_end / shot         | null 49-3 (5.1)  | —                                                                      | 4884     |
| F359  | 19:48:29 | SCOREBOARD | bowlers_end / shot         | null 49-3 (7.1)  | —                                                                      | 5519     |
| F362  | 19:48:42 | SCOREBOARD | closeup / between_play     | null 49-3 (null) | —                                                                      | 5604     |
| F396  | 19:50:41 | SCOREBOARD | closeup / between_play     | null 47-3 (null) | —                                                                      | 6239     |
| F399  | 19:50:50 | SCOREBOARD | closeup / between_play     | null 49-3 (5.1)  | A player, likely Jacks, appears to be gesturing or reacting on field.  | 6327     |
| F469  | 19:55:13 | SCOREBOARD | closeup / between_play     | null 47-3 (null) | The camera shows a man standing and gesturing, likely a broadcaster…   | 7648     |
| F499  | 19:57:01 | SCOREBOARD | bowlers_end / shot         | null 47-3 (null) | A batsman is playing a shot.                                           | 8112     |
| F500  | 19:57:05 | SCOREBOARD | bowlers_end / shot         | null 49-3 (7.5)  | —                                                                      | 8153     |
| F547  | 19:58:58 | SCOREBOARD | closeup / between_play     | null 49-3 (7.1)  | —                                                                      | 8890     |
| F643  | 20:03:25 | SCOREBOARD | closeup / between_play     | null 49-3 (7.5)  | —                                                                      | 10804    |
| F644  | 20:03:28 | SCOREBOARD | closeup / between_play     | null 49-3 (8.4)  | —                                                                      | 10832    |
| F690  | 20:04:58 | SCOREBOARD | bowlers_end / shot         | null 47-3 (null) | —                                                                      | (DETAIL) |

Note F8 is a special case — first-frame initialization (`[INIT] First-frame
initialization complete: 47-3(None)` at line 669). The phantom 47-3 was
committed as initial state and persisted F56–F108 even while real strip reads
showed `MI 0-0 (0.1)`/`MI 1-0 (0.4)` (e.g., line 1331 F96 strip
`MUMBAI 47-3 (9.2)` vs F97 strip `MI 1-0 (0.4)`).

### Innings 2 (pipeline-...-2049)

| Frame | Time     | Tag        | cam / phase                | Strip score      | action                                                          | Log line |
|-------|----------|------------|----------------------------|------------------|-----------------------------------------------------------------|----------|
| F45   | 20:52:18 | SCOREBOARD | bowlers_end / shot         | null 49-3 (5.5)  | —                                                               | 654      |
| F81   | 20:54:59 | SCOREBOARD | bowlers_end / shot         | null 47-3 (null) | —                                                               | 1509     |
| F82   | 20:55:03 | SCOREBOARD | bowlers_end / shot         | null 47-3 (null) | A batsman is playing a shot.                                    | 1536     |
| F118  | 20:55:32 | SCOREBOARD | closeup / between_play     | null 47-3 (null) | A player, likely Noor, is walking back after bowling.           | 1575     |
| F120  | 20:55:47 | SCOREBOARD | bowlers_end / shot         | Chennai 47-3 (3.2) | —                                                             | 1598     |
| F124  | 20:56:01 | SCOREBOARD | bowlers_end / release      | null 49-3 (8.4)  | —                                                               | 1712     |
| F126  | 20:56:05 | SCOREBOARD | bowlers_end / post_shot    | null 49-3 (null) | —                                                               | 1742     |
| F127  | 20:56:09 | SCOREBOARD | bowlers_end / release      | null 49-3 (5.4)  | —                                                               | 1767     |
| F128  | 20:56:13 | SCOREBOARD | bowlers_end / release      | null 47-3 (null) | A delivery is being bowled.                                     | 1812     |
| F197  | 21:00:29 | SCOREBOARD | bowlers_end / between_play | null 49-3 (null) | —                                                               | 3012     |
| F247  | 21:03:52 | **GRAPHIC**| bowlers_end / release      | null 47-3 (null) | —                                                               | 4000     |
| F248  | 21:03:56 | **GRAPHIC**| closeup / fielder_reaction | null 47-3 (null) | —                                                               | 4024     |
| F326  | 21:09:13 | SCOREBOARD | bowlers_end / release      | null 47-3 (null) | —                                                               | 5662     |
| F339  | 21:10:37 | SCOREBOARD | bowlers_end / shot         | null 47-3 (null) | —                                                               | 5830     |
| F350  | 21:11:21 | SCOREBOARD | bowlers_end / shot         | null 49-3 (null) | —                                                               | 6042     |
| F351  | 21:11:26 | SCOREBOARD | bowlers_end / shot         | null 49-3 (null) | —                                                               | 6074     |
| F352  | 21:11:30 | SCOREBOARD | bowlers_end / shot         | null 47-3 (null) | —                                                               | 6101     |
| F358  | 21:12:01 | **GRAPHIC**| bowlers_end / release      | null 47-3 (null) | —                                                               | 6345     |
| F360  | 21:12:08 | SCOREBOARD | bowlers_end / release      | null 49-3 (null) | —                                                               | 6393     |
| F404  | 21:15:22 | SCOREBOARD | bowlers_end / shot         | null 49-3 (8.2)  | —                                                               | 7434     |
| F405  | 21:15:26 | SCOREBOARD | (cam unread)               | null 47-3 (null) | A batsman is playing a shot.                                    | 7461     |
| F406  | 21:15:29 | SCOREBOARD | (cam unread)               | null 47-3 (null) | A batsman is playing a shot.                                    | 7486     |
| F519  | 21:22:55 | SCOREBOARD | closeup / between_play     | null 49-3 (8.3)  | A fielder in a teal uniform appears to be celebrating…          | 9669     |
| F520  | 21:22:58 | SCOREBOARD | closeup / between_play     | null 49-3 (null) | A fielder, likely from the bowling team, is celebrating…        | 9695     |
| F521  | 21:23:01 | SCOREBOARD | (cam unread)               | null 47-3 (null) | A player, likely Boult, is shown in a close-up.                 | 9720     |
| F534  | 21:23:32 | SCOREBOARD | bowlers_end / release      | null 49-3 (6.4)  | A delivery is being bowled.                                     | 9990     |
| F647  | 21:31:39 | SCOREBOARD | (cam unread)               | null 49-3 (8.1)  | A player, likely Boult or Bhagat, is running between wickets.   | 10801    |
| F716  | 21:35:17 | SCOREBOARD | (cam unread)               | null 47-3 (null) | —                                                               | 11289    |
| F742  | 21:36:54 | SCOREBOARD | (cam unread)               | null 49-3 (null) | —                                                               | 11386    |
| F745  | 21:37:14 | SCOREBOARD | (cam unread)               | null 49-3 (null) | A player is adjusting their gloves.                             | 11471    |
| F748  | 21:37:37 | SCOREBOARD | (cam unread)               | null 47-3 (null) | A cricketer is walking off the field while another is talking…  | 11511    |
| F766  | 21:38:25 | SCOREBOARD | (cam unread)               | null 49-3 (8.2)  | —                                                               | 11593    |
| F767  | 21:38:30 | SCOREBOARD | (cam unread)               | null 47-3 (null) | A fielder, possibly the captain, is directing or celebrating.   | 11632    |
| F782  | 21:39:24 | SCOREBOARD | (cam unread)               | null 47-3 (null) | —                                                               | 11839    |
| F798  | 21:40:29 | SCOREBOARD | (cam unread)               | null 47-3 (null) | —                                                               | 12268    |
| F799  | 21:40:33 | SCOREBOARD | (cam unread)               | null 47-3 (null) | A cricketer is preparing to bat.                                | 12305    |
| F826  | (later)  | SCOREBOARD | —                          | null 47-3 (null) | —                                                               | (DETAIL) |
| F886  | 21:46:53 | SCOREBOARD | —                          | null 47-3 (null) | —                                                               | (PM §4)  |
| F895  | (later)  | SCOREBOARD | —                          | null 47-3 (null) | —                                                               | (DETAIL) |
| F897  | 21:47:42 | **GRAPHIC**| —                          | null 47-3 (5.4)  | —                                                               | 14142    |

## §2 Tag analysis

Counting only the recap-overlay phantoms (excluding F8/F56–F108 init-phantom
which is a different bug class):

| Tag        | Innings 1 | Innings 2 | Total |
|------------|-----------|-----------|-------|
| SCOREBOARD | 21        | 33        | 54    |
| GRAPHIC    | 0         | 4         | 4     |

Ratio: **54 / 58 ≈ 93 % of phantom frames are tagged SCOREBOARD**, not
GRAPHIC. The Scout classifier is **not** flagging recap-overlay frames as
GRAPHIC. Every `[SCOUT] SCOREBOARD ... overlay=False` line in §1 confirms
Scout believes the frame is a clean live scoreboard. The four GRAPHIC-tagged
phantoms (F247, F248, F358, F897) all rode in alongside an actual on-screen
graphic (full-screen overlay co-incident with the inset), and were caught by
the existing `[GRAPHIC-FILTER] GRAPHIC frame — rejecting extractor score
path …` rule (lines 4010, 4034, 6355, 14142).

The GRAPHIC poison filter (P2's "rejecting extractor score path upstream")
catches Scout-classified GRAPHICs only. The 54 SCOREBOARD-tagged phantoms
slip past it entirely; they survive only because the downstream poison-streak
gate sees `delta=−71…−109` vs the live tracker and emits
`[POISONED] Extracted score 47/49 vs tracker NNN — blocking ALL updates this
frame`. That's a downstream defence; the upstream classifier is blind.

## §3 Visual signature analysis

Scout's `action` field on phantom frames is mostly generic gameplay text —
"A batsman is playing a shot.", "A delivery is being bowled.", "A fielder is
celebrating", "A player is adjusting their gloves." 23 of the 58 phantom
frames have `action=—` (empty). Zero phantom frames contain any of the
keywords "replay", "recap", "highlight", "career", "comparison", "PIP",
"split-screen", "inset", or "banner". Scout's vision summary does not
notice the inset banner — its description focuses on the live action
visible in the rest of the frame.

The Scout STRIP itself is the strongest signal. Two consistent fingerprints:

1. **Score is always one of `47-3` or `49-3`** with overs either `null` or
   one of a tiny vocabulary `(3.2)`, `(5.1)`, `(5.4)`, `(5.5)`, `(6.4)`,
   `(7.1)`, `(7.5)`, `(8.1)`, `(8.2)`, `(8.3)`, `(8.4)`, `(9.2)`. The score
   is the same in both innings and across two distinct broadcast feeds
   (CSK-strip and MI-strip), strongly suggesting it is a **fixed
   pre-rendered banner** (likely the morning's score from a different
   match/segment baked into the broadcaster's recap template).
2. **Player rows are filler text** — `*Dhir 20(18) | Pandya 5(7) | Noor 1-15
   (3.2)` recurs literally across F81/F82/F118/F128 even though the live
   match has moved on. The runs/balls pair `20(18) … 5(7) … 1-15 (3.2)`
   appears 14× in the innings 2 log and is the single most reliable phantom
   signature.

Three other observable signals:

3. **Strip team prefix is `null`** on 51 of 58 phantom frames. A real live
   strip almost always has a team initialism (`MI`/`CSK`/`Mumbai Indians`/
   `Chennai`). When `team=null` and `score in {47-3, 49-3}`, the read is the
   recap inset.
4. **`INFO_PANEL` token is `null`** on every phantom frame (e.g., F81 line
   1509 DETAIL: `INFO_PANEL: null`). The existing
   `info_panel_keyword='IN T20'` filter at lines 13022/13051 (F841/F842)
   only fires when Scout actually populates an INFO_PANEL ("Sam…", "Samson…")
   from the recap's career-stats banner. Recap **inset** frames don't
   trigger the player-stats panel — Scout only writes INFO_PANEL when the
   panel is full-width.
5. **Camera is `bowlers_end` or `closeup` with `phase` ∈
   {between_play, release, shot, post_shot}** — i.e. the underlying
   live frame looks like a normal scoreboard moment, which is exactly
   why `tag=SCOREBOARD`. The inset banner is a small overlay over a live
   shot; Scout's classifier fires on the dominant content (live play) and
   reads the inset's strip as the canonical strip.

## §4 Why P2 didn't catch all overlays

P2 has two firing modes (visible in the `[GRAPHIC-FILTER]` lines):

- **Mode A — "GRAPHIC frame — rejecting extractor score path upstream of
  poison delta"**: triggered when Scout tags the frame `GRAPHIC`. Strips
  the score path entirely. Caught **all 4** GRAPHIC-tagged phantoms above
  (F247/F248/F358/F897).
- **Mode B — "GRAPHIC→SCOREBOARD transition — poisoning strip read
  (lever-2 partial fade guard)"**: triggered when the **previous** frame
  was tagged GRAPHIC and the current frame is SCOREBOARD. Single-frame
  edge guard.

The gap is structural:

1. **Mode B only fires on a GRAPHIC→SCOREBOARD edge.** Innings 2 example:
   - F326 fired Mode B (line 5672) — previous frame was GRAPHIC.
   - F339 (line 5830, 1m24s later) — `null 47-3 (null)`, **no
     GRAPHIC-FILTER firing**. Reason: Scout never tagged any preceding
     frame as GRAPHIC; the inset just appeared inside an otherwise
     SCOREBOARD-classified clip. Same pattern at F350/F351/F352, F404,
     F519/F520/F521, F647, F716, F742…
2. **Mode A requires Scout to tag GRAPHIC.** As shown in §2, Scout
   tags 93 % of these as SCOREBOARD because the inset is small relative
   to the live frame.
3. **There is no debounce window after a confirmed Mode-A or Mode-B
   firing.** F197 fires Mode B at line 3022 (GRAPHIC→SCOREBOARD edge); the
   very next frame inside the same recap segment, if Scout still classifies
   it SCOREBOARD, gets no protection. The post-mortem's 30 P2 firings (each
   a single edge) match the 4 GRAPHIC-tagged frames + ~26 visible single-edge
   transitions — the problem is the **multi-frame interior** of each recap
   block.

So: P2 is doing exactly what its design says (single-frame partial-fade
guard). It can't cover multi-frame inset segments because (a) Scout never
re-classifies them GRAPHIC and (b) there's no "stay suspicious for N frames
after a transition" follow-on.

The downstream poison-streak gate (`[POISONED] Extracted score 47/49 vs
tracker NNN`) is the actual safety net — every phantom in §1 was blocked
there. But that is post-hoc (it relies on the tracker already having a
sane score) and breaks at every cold-start (innings 2 F647 phantom
49-3 (8.1) was rejected only because the gate compared to tracker=159
from innings 1). At true cold-start (e.g., F8 of innings 1 — line 235:
`Chennai Super Kings 47-3 (7.5)` was committed as the initial state via
`[INIT] First-frame initialization complete: 47-3(None)` line 669) the
phantom **becomes** the tracker.

## §5 Detection mechanism proposals

Five candidates, ordered by signal strength.

1. **Phantom-fingerprint allowlist of recap rows.** The runs/balls pair
   `20(18) … 5(7) … 1-15 (3.2)` and the bowler `1-15 (3.2)` are literal
   fingerprints of the recap banner. A frame whose extracted strip carries
   these AND `team=null` AND `score in {47-3, 49-3}` is the inset banner
   with overwhelming probability. Cheap regex on the existing Scout STRIP
   string. Brittle to broadcast template changes, but immediate.
2. **Scout strip "team=null + score not adjacent to tracker" gate.** If
   Scout's strip starts with `null` (no team initial) AND the parsed
   score differs from the tracker by `>10 runs` AND camera is `closeup`/
   `bowlers_end`, treat as inset. Generalises beyond `47-3/49-3`. Already
   most of these signals are computed; combining them into a new
   `[GRAPHIC-FILTER] inset-strip suspected` rule would add Mode-C alongside
   the existing Mode A/B.
3. **N-frame debounce after every Mode A or Mode B firing.** When P2 fires,
   keep an "overlay-window" flag for the next K frames (K≈3–5) or until
   Scout returns two consecutive SCOREBOARD reads whose score matches the
   tracker within ±2. Within the window, every SCOREBOARD strip is
   poison-suspected. Cheap; covers the multi-frame interior; doesn't need
   any new visual signal.
4. **Inset-region YOLO/zone detector.** Add a small YOLO class or a fixed
   rectangular region scan looking for the recap-banner shape (the inset is
   visually distinct: smaller, top-right or bottom-left, rounded corners).
   Highest accuracy, biggest engineering cost. Belongs to "Lever 3" in the
   roadmap — outside the half-day estimate.
5. **Scout prompt addendum to surface "is this a recap overlay?".** Have
   Scout return an explicit `inset_present: bool` field in addition to
   `tag`. Requires a Scout-prompt change and a re-eval. Highest-quality
   signal, but couples to Scout iteration cadence.

Existing telemetry already has the raw materials for proposals 1–3 (see
the `INFO_PANEL` / `STRIP` fields in every DETAIL line). Proposals 4–5
require model work.

## §6 Fix proposal with effort estimate

**Preferred — combined Mode-C + N-frame debounce (proposals 2 + 3).**

Why: keeps the fix inside the existing P2 / GRAPHIC-FILTER substrate, no
new model work, addresses both the multi-frame gap (debounce) and the
"Scout never tagged GRAPHIC" gap (team=null + delta>K rule). Proposal 1's
literal allowlist is added as a third Mode-C trigger for high-precision
guaranteed catches.

Files to touch (greppable):

- `files/test_pipeline.py` — find the `[GRAPHIC-FILTER]` log emission
  sites (search `GRAPHIC→SCOREBOARD transition` and
  `GRAPHIC frame — rejecting extractor score path`). Add:
  - Mode-C trigger conditions (team=null + |score−tracker|>10 OR strip
    matches recap-fingerprint regex).
  - Window-flag bookkeeping: after any Mode A/B/C firing, set
    `overlay_window_remaining = 5`; decrement each frame; while > 0, treat
    SCOREBOARD strips with `team=null` as poison-suspected.
- `files/trace_emitter.py` — add `inset_suspected` and
  `overlay_window_active` fields to the trace record (per the trace v1
  schema in CLAUDE.md). No anomaly-rule changes required for v1.
- `files/tests/` — add a unit test fixture replaying the F81/F82/F118/F124/
  F127/F128 sequence, asserting all are poison-suspected (none commits a
  score change).

Effort: **~half day** (roughly 4 hours coding + 2 hours fixture/tests),
matching the post-mortem's P3 estimate. Proposal 4 (region detector) is a
second-pass enhancement and stays out of scope.

Out of scope for this fix (separate work items already noted in the
post-mortem):

- True cold-start hardening (P12) — F8 init phantom is a different bug
  (init code commits the strip without any tracker comparison).
- Bowler-overs sanity check (P15) for Bumrah-class hallucinations.
- OpenScout-driven strip-OCR rewrite — would supersede most of the above
  but is a longer programme.
