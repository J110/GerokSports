# Wide / no-ball breaks `this_over` slot count

Date: 2026-05-04
Trace: `logs/pipeline-2026-05-03-2058--stage1ready.log`
Linked: U4 (18.1 slot empty, 18.2 displayed without 18.1)

## TL;DR

The hypothesis ("wide inflates `this_over` slot count, which causes
the UI to skip 18.1") is **not supported** by the trace. The 7-element
`this_over` at F212 is correct cricket: 6 legal + 1 wide. Both
`this_over.py` and `ThisOver.tsx` already filter extras out of the
legal-ball count. The visible 18.0 → 18.2 jump (skipping 18.1) is a
**separate upstream bug**: the tracker's committed `team_overs`
stalled at 18.0 for ~2 minutes while the broadcast strip read
141 → 142 → 144 → 145, then jumped straight to 18.2 in F244. No
intermediate 18.1 state was ever published, so the UI had nothing to
render for that slot.

Recommendation: **no change to `this_over.py` or `ThisOver.tsx`** for
this hypothesis. Open a separate investigation for the tracker
state-commit stall (F213-F243). Suggested name: `tracker_stall_after_
over_rollover.md`.

## Phase A — Trace evidence

### A1. F208-F210: holding state before rollover

```
F208 21:08:31  STRIP: PBKS 141-8 (18) ... this_over=null
              [THIS OVER] ['1', '1', '4', 'Wd', 'W', 'W'] = 6 runs
F209 21:08:35  STRIP: PBKS 141-8 (18) ... this_over=2/2
              [THIS OVER] ['1', '1', '4', 'Wd', 'W', 'W'] = 6 runs
F210 21:08:38  STRIP: PBKS 141-8 (18) ... this_over=null
              [THIS OVER] ['1', '1', '4', 'Wd', 'W', 'W'] = 6 runs
```

Six tokens (5 legal + 1 wide). Legal count of the over so far is
**5** because the closing dot ball had not yet been emitted by
`BallEventDetector`. `team_overs="18"` (ambiguous integer) — a
short-over rollover defer is in effect (line 980-1028 of
`this_over.py`).

### A2. F212: closing-ball event arrives, over 17 archives correctly

```
F212 21:08:48  TRACK: overs 17.5 → 18.0 (post-event immediate, grace=1)
F212 21:08:48  BOARD: overs 17.5 -> 18.0
F212 21:08:49  COMMENTARY: [BALL ✓] DOT | 18.0 +0 runs (Δballs=1)
F212 21:08:49  [THIS-OVER] Ball DOT appended to over 17
F212 21:08:49  OVER: Over 17 complete:
               ['1', '1', '4', 'Wd', 'W', 'W', '.'] = 6 runs, 2 wkts
F212 21:08:49  [OVER CHANGE] → 18.0
F212 21:08:49  STATE: PBKS 141-8 (18.0) ...
```

The DOT event has `over="18.0"`. `on_ball_event` decodes
`ev_over_logical = 17` (line 270-273: `frac == 0` → previous over)
and routes the late ball to the **held** over via
`_append_to_held_and_rearchive` (line 297-320). Result: the over-17
archive correctly holds 7 tokens. Six are legal (1, 1, 4, W, W, .),
one is the wide.

This is correct cricket: an over with 1 wide takes 7 deliveries to
complete (6 legal + 1 extra).

### A3. F213-F243: tracker stalls at 18.0 while strip advances

```
F213 21:08:54  STATE: PBKS 141-8 (18.0)  ← held over flushed (3s timeout)
F214-F217      STATE: PBKS 141-8 (18.0)
F218 21:09:15  STRIP: PBKS 142-8 (18) ... but
               STATE: PBKS 141-8 (18.0)  ← strip score advanced, state didn't
F228 21:09:44  STRIP: PBKS 142-8 (18) ... STATE: PBKS 141-8 (18.0)
F229 21:09:48  STRIP: PBKS 142-8 (18)
F230 21:09:55  [OVERS FIX] SKIP regression: computed=17.2 < confirmed=18.0
                          (tokens=2 likely stale/poisoned) — keeping 18.0
F231 21:09:59  STRIP: PBKS 144-8 (18.1) ... STATE: PBKS 141-8 (18.0)
F239 21:10:22  STRIP: PBKS 144-8 (18.1) ... STATE: PBKS 141-8 (18.0)
F240 21:10:27  STRIP: PBKS 144-8 (18.1)
F241 21:10:34  STRIP: PBKS 145-8 (18.2) ... STATE: PBKS 141-8 (18.0)
F242 21:10:39  STRIP: PBKS 145-8 (18.2)
F243 21:10:44  STRIP: PBKS 145-8 (18.2)
F244 21:10:49  TRACK: overs 18.0 → 18.2 (post-event immediate, grace=0)
F244 21:10:49  [CAM-GRAPHIC-FAST-PATH-READ] score=145 overs=18.2
                                            changes=['score', 'overs']
F244 21:10:49  [FLOOR] Padded 2 '?' placeholders to this_over
                       (team_overs=18.2 expects 2 legal, observed only 0)
F245 21:10:56  [BALL ?] MULTI_BALL | 18.2 +4 runs (Δballs=2)
```

Notes:
- The strip published `(18.1)` cleanly at F231, F239, F240 (12-15s
  apart, three reads) but the committed `STATE.overs` never moved
  off 18.0.
- `[OVERS FIX] SKIP regression` at F230 (and a second time near
  F228) explicitly rejected an inferred 17.2 reading. That guard is
  correct in isolation (regression rejection), but it logged
  `tokens=2 likely stale/poisoned` while the real fault was elsewhere.
- The eventual jump 18.0 → 18.2 (F244) skipped 18.1 entirely. From
  the UI's perspective, the published over_number sequence was
  `... 18.0, 18.0, 18.0, ..., 18.2`. The 18.1 ribbon state never
  existed.
- F244's FLOOR pad correctly inserted 2 '?' placeholders (matching
  the 2 legal balls implied by `18.2`), and F245's MULTI_BALL
  detector noted `Δballs=2` — both confirm the upstream stall, not a
  this_over slot-positioning bug.

## Phase B — `this_over.py` slot logic review

Slot positioning is **not** positional. `this_over` is a flat list
of tokens; legal-ball arithmetic is computed by filtering extras
wherever it matters:

- `check_over_change` short-over defer guard (line 999-1007):
  filters `wd`, `nb` (and compound `wd…`/`nb…` prefixes) from the
  legal count, then adds wickets back. Correct.
- `get_display` length-floor (line 1229-1233): identical filter.
  Correct.
- `_append_to_held_and_rearchive` legal-ball count (line 304-307):
  identical filter. Correct.
- `reorder_wicket_to_ball._is_pure_extra` (line 759-762): treats
  `Wd`, `Nb`, `Wd+N`, `Nb+N` as non-ball-consuming. Correct.

Source-tagged sources (`obs` / `bcast`) confirm at F212 that all 7
tokens were `obs`-derived (1=bcast then 6=obs, per the user's
F212 trace: `1(bcast),1(obs),4(obs),Wd(obs),W(obs),W(obs),.(obs)`).
No fabrication, no positional shift.

## Phase C — UI review (`scorecard-ui/app/components/ThisOver.tsx`)

```ts
const EXTRAS = new Set(["wd", "Wd", "nb", "Nb", "NB", "WD", "lb", "Lb"]);
function isExtra(ball: string) { return EXTRAS.has(ball); }
...
const legalCount = (balls || []).filter((b) => !isExtra(b)).length;
const remaining = Math.max(0, 6 - legalCount);
```

For `['1','1','4','Wd','W','W','.']`:
- `legalCount = 6` (Wd filtered, W counted as legal)
- `remaining = 0` (no dashed empty slots)
- Total rendered circles = 7

UI renders correctly. **Caveat**: the EXTRAS set does NOT include
compound forms (`Wd+1`, `Wd+4`, `Nb+2`). If a Wd+N ever lands in the
ribbon, `isExtra` returns false and the token will be (a) miscounted
as a legal ball and (b) styled with the legal-token style instead of
the small-extra style. Upstream `this_over.py` _does_ emit these
compound tokens (line 462-464 of `_append_event_token`). This is a
**latent UI bug** but did not fire for the F212 case (token was
plain `Wd`).

## Root cause of U4 (18.1 skipped, 18.2 displayed without 18.1)

Not in `this_over` slot positioning. The tracker (`overs:` BOARD
events) never committed an 18.1 reading — it stalled at 18.0 from
F213 (21:08:54) through F243 (21:10:44), then jumped to 18.2 at F244
(21:10:49). The strip read 18.1 cleanly at F231, F239, F240 but
those reads did not propagate into committed state.

Likely causes (out of scope here, deferred to a separate
investigation):
- The `overs: 17.5 → 18.0 (post-event immediate, grace=1)` rollover
  set some "just-rolled-over" lockout that suppressed subsequent
  `(18.1)` strip reads as redundant.
- `[STRIP-OVERLAY-DETECTED]` warnings on F210, F213-F217, F228, F230
  may have poisoned multiple consecutive strips, locking the
  committed state.
- The `[OVERS FIX] SKIP regression` at F230 indicates the
  reverse-overs guard fired twice (F228 and F230), at least once on
  a clean 18.1 reading.

## Recommended fix

For this investigation: **no fix to `this_over.py` or
`ThisOver.tsx`**. The hypothesis is wrong; both modules already
handle wides correctly.

Adjacent latent issue (NOT in scope, but worth a one-line ticket):
add compound extra forms to `ThisOver.tsx`'s `isExtra` predicate so
`Wd+N`/`Nb+N` tokens render with the small-extra style and don't
inflate `legalCount` in the UI. Suggested predicate:

```ts
function isExtra(ball: string) {
  if (EXTRAS.has(ball)) return true;
  return /^(Wd|Nb|wd|nb)(\+\d+)?$/.test(ball);
}
```

For U4: open a separate investigation on the tracker stall (F213
through F243 stayed at 18.0 while strip published 18.1, 18.1, 18.1,
18.2, 18.2, 18.2). The state-commit pipeline — `[OVERS FIX] SKIP
regression` guard, the post-rollover grace window, and
`[STRIP-OVERLAY-DETECTED]` poisoning interactions — needs review.

## Linked issues

- **U4** — 18.1 skipped, 18.2 displayed without 18.1.
  Cause: tracker stall, NOT this_over slot positioning.
  Real fix lives in tracker / state-commit guards, not the
  ribbon code paths read here.
