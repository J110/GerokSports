# Fix 7 — WS-PROJECTION-GAP fallback (`sb._inn` when SM-null + in active_batting)

**Bug**: P2 — after a wicket, `score_mgr.striker` / `score_mgr.non_striker`
remain `None` for ~24 s while SM catches up to scout's strip read.
During that window the WS payload emits `striker=null, non_striker=null`
even though `scoreboard._inn` and `scoreboard.batting_card` already hold
the correct new pair. UI shows `—` / `incoming batter…` for the most
attention-grabbing moment of the match (the wicket itself).
**Backlog ref**: `files/docs/backlog.md` "P2: WS-PROJECTION-GAP —
striker / non_striker null in payload".
**Trace**: 2026-04-25 RR-vs-SRH match-2 innings 2; 14 fires across
~340 frames, concentrated around wickets and over rollovers.

Concrete F145 W2 (Jurel dismissed):

```
[WS-PROJECTION-GAP] striker=None (payload)
                    sb._inn.striker='Riyan Parag'
                    sm.striker=None
                    active_batting=['Vaibhav Sooryavanshi', 'Riyan Parag']
```

Scoreboard correctly identified Parag as the new striker via scout's
strip read; ScoreManager hadn't received the dismissal-confirmation
flow yet; payload reads from SM only → 24 s of placeholder UI.

## Files modified

| file                              | lines added | net |
|-----------------------------------|-------------|-----|
| `files/test_pipeline.py`          | +71 (new module-level helper `_project_active_batters` + comment + call-site rewrite + fallback-event logging) | +56 |
| `files/test_recent_fixes.py`      | +200 (helper + stub SM + 5 tests + section header + TESTS wiring) | +200 |

## Root cause + fix shape

`build_full_payload` performs the SM cutover at the WS boundary
(`test_pipeline.py:~3434`). Pre-Fix-7 it unconditionally wrote
`state["striker"] = _canon_player_name(score_mgr.striker)` even when
`score_mgr.striker` was `None`. The downstream `WS-SCRUB` block at
`test_pipeline.py:~3500` skipped on `if not _nm: continue` (it only
rejects bad-but-non-None names), so `None` values bypassed scrub
entirely and went to the WS payload as `None`. The `WS-PROJECTION-GAP`
diagnostic block at `test_pipeline.py:~3527` then *observed* the gap
without doing anything about it.

The S18 design rationale for the unconditional `None` write
(documented in the source comment at the call site) was: "after a
WICKET, SM clears striker to None so the incoming batter slot is
'empty until scout reads them'; the original `state['striker']` from
scoreboard still holds the dismissed batter, leaking them onto the UI
for 3-7 s. Pass through None so the UI can render its placeholder."

Fix 7 introduces a **bounded** fallback that respects this rationale:
fall back to `sb._inn` **only when** the value is currently in
`active_batting`. The active-batting check is the safeguard against
the dismissed-batter leak: when scout has detected the wicket and
flipped a player's `batting_card[name].status` to `"out"`, the player
is excluded from `_active` and thus never surfaced via fallback even
if `sb._inn` still holds them for a frame or two before its own
update lands.

## Source change (`test_pipeline.py`)

Two surfaces:

1. **New module-level helper** (`_project_active_batters`, ~50 lines
   including docstring) extracted from the inline block at
   `build_full_payload`. Exposes the projection logic for direct unit
   testing without needing to construct a full `run_test` context.
   Takes `state`, `score_mgr`, `scoreboard`, `canon_fn` as explicit
   args. Returns a list of `(slot, sb_val)` fallback events for the
   caller to log / count.

2. **Call site rewrite** (inside `build_full_payload`'s SM-cutover
   block) — replaces the four lines of inline writes with a single
   call to `_project_active_batters` plus a fallback-event
   `[WS-PROJECTION-FALLBACK]` log loop. The S18 comment block is
   preserved and extended with a Fix-7 reference for future readers.

Helper logic:

```python
state["striker"] = canon_fn(score_mgr.striker)
state["non_striker"] = canon_fn(score_mgr.non_striker)

_bc = scoreboard.batting_card or {}
_active = [_n for _n, _c in _bc.items()
           if _c and _c.get("status") == "batting"]
_sb = scoreboard._inn or {}
_events = []
for _slot in ("striker", "non_striker"):
    if state.get(_slot) is not None:
        continue
    _sb_val = _sb.get(_slot)
    if not _sb_val or _sb_val not in _active:
        continue
    _other_slot = "non_striker" if _slot == "striker" else "striker"
    if _sb_val == state.get(_other_slot):
        continue
    state[_slot] = canon_fn(_sb_val)
    _events.append((_slot, _sb_val))
return _events
```

## Why this shape

- **Active-batting check is the safeguard against dismissed-batter
  leaks.** Dismissed players have `batting_card[name].status == "out"`
  by the time scout has detected the wicket, so they're excluded from
  `_active`. A stale `sb._inn["striker"] = "Jurel"` (just dismissed)
  will not be surfaced via fallback even though `sb._inn` still holds
  the name; the placeholder UI behavior from S18 is preserved for
  this case.
- **`_other_slot` collision check is defence-in-depth at the payload
  level.** Fix 5 (same bundle) protects `sb._inn` from
  `striker == non_striker` collisions, but the WS payload could still
  collide if SM resolved one slot to `X`, then SM cleared the other
  slot to `None`, and `sb._inn` for the cleared slot also held `X`
  (e.g. mid-swap, indexing temporarily inverted). The `_other_slot`
  check declines the fallback in that case, keeping the payload's
  `striker != non_striker` invariant.
- **Helper extraction enables direct unit testing.** Pre-Fix-7 the
  projection logic was buried in a closure (`build_full_payload` is
  nested inside `async def run_test()`), making it untestable without
  mocking the entire video-processing pipeline. The module-level
  helper takes the four args it actually needs and is callable from
  any test fixture with a `Scoreboard` + a SM-shaped stub.
- **Strengthened by Fix 5 (same 2026-04-25 inter-match bundle).**
  Pre-Fix-5, falling back to `sb._inn` risked surfacing a self-collided
  pair (`striker == non_striker`) to the WS payload — one bug class
  swapped for another. Post-Fix-5, `sb._inn` is invariant-protected,
  so the fallback can only surface a genuine valid pair. This is what
  reframed WS-PROJECTION-GAP from "consider with caution" to
  "preferred fix shape" in the backlog audit immediately preceding
  this fix.

## Tests added (`test_recent_fixes.py`)

Helper: `_setup_ws_projection_pair_sb()` — `Scoreboard` with two
batters at the crease (Sooryavanshi, Parag) plus a dismissed third
(Jurel, status="out"). Reused across all five tests.

Helper: `_StubSM` — minimal ScoreManager-shaped stub exposing the
attrs `_project_active_batters` reads (`striker`, `non_striker`,
`bowler_name`, `shadow`). Avoids needing a real ScoreManager
construction (which has its own state and would be heavier than this
fix needs).

Helper: `_identity_canon` — `lambda raw, **kw: raw`. Canonicalization
is orthogonal to the projection logic; identity isolates the test to
the projection rules themselves.

1. `test_ws_projection_fallback_sm_resolved_no_fallback` — pre:
   `sm.striker='Sooryavanshi', sm.non_striker='Parag'`, `sb._inn`
   agrees, both in active_batting. Asserts payload uses SM values
   exactly, no fallback events recorded.
2. `test_ws_projection_fallback_sm_null_dismissed_no_fallback` — pre:
   `sm.striker=None, sm.non_striker='Parag'`, `sb._inn.striker='Jurel'`
   (dismissed), Jurel NOT in active_batting. Asserts payload striker
   stays `None` (placeholder UI shown), no fallback fires for the
   dismissed-batter case. **Critical regression-protection test —
   ensures the S18 dismissed-batter-leak prevention is preserved.**
3. `test_ws_projection_fallback_sm_null_active_uses_sb_inn` — pre:
   `sm.striker=None, sm.non_striker='Parag'`, `sb._inn.striker=
   'Sooryavanshi'`, Sooryavanshi IN active_batting. Asserts fallback
   fires for striker slot only, payload now has both slots populated
   correctly.
4. `test_ws_projection_fallback_f145_w2_replay` — pre: F145 ending
   state constructed directly from the production trace
   (`sb._inn.striker='Riyan Parag', sb._inn.non_striker='Vaibhav
   Sooryavanshi'`, both in active_batting; Jurel marked `out`;
   `sm.striker=sm.non_striker=None` — full SM catch-up gap). Asserts
   both slots fallback-populated, `striker != non_striker` invariant
   held in the payload (Fix 5 → Fix 7 inheritance), both fallback
   events recorded.
5. `test_ws_projection_fallback_collision_avoidance_with_other_slot` —
   pre: state with `striker="Parag"` already SM-resolved,
   `non_striker=None`, `sb._inn.non_striker="Parag"` (would collide
   with the resolved striker). Asserts non_striker stays `None`,
   defence-in-depth holds, no fallback event recorded for the
   declined slot.

## Test results

```
PASS 223 / FAIL 2 (both pre-existing, unrelated to Fix 7)
```

All 5 Fix-7 tests PASS (16 sub-checks). Suite delta from post-Fix-6
state: +16 sub-checks, 0 regressions. The 2 pre-existing failures are
documented in `files/docs/backlog.md` "Test hygiene (P3)".

## Bundling note

This is fix #7 in the inter-match commit bundle. **Zero source-file
overlap with fixes 1-6 in the projection helper itself** (new
module-level function in `test_pipeline.py`); minor overlap with
**Fix 1** in `test_pipeline.py` (different sites — Fix 1 added the
innings-1-final latch sanity bound, Fix 7 adds the active-batter
projection helper; the call-site rewrite is in `build_full_payload`
which Fix 1 doesn't touch). The fixes do not interact.

## Verification on first restart after deploy

`[WS-PROJECTION-FALLBACK]` log line is positive-firing — it should
fire exactly when an SM catch-up gap occurs around a wicket or over
rollover and `sb._inn` has the correct value to surface. Search the
post-restart pipeline log for:

```
[WS-PROJECTION-FALLBACK] striker='<name>' surfaced from sb._inn (SM-null, in active_batting)
```

Expected on the first wicket of the next match. The complementary
`[WS-PROJECTION-GAP]` warn line should now fire much less often (and
when it does, it indicates a *genuine* gap where `sb._inn` doesn't
have the value either — i.e. scout hasn't read the new batter yet —
not the SM-catch-up-only class Fix 7 closes).

Telemetry to watch over the first match-day:

- Count of `[WS-PROJECTION-FALLBACK]` fires per match (target: ≥1
  per wicket on average; if zero across multiple wickets, the fix
  is dormant — investigate why `sb._inn` isn't being surfaced)
- Ratio of `[WS-PROJECTION-FALLBACK]` to `[WS-PROJECTION-GAP]` post-
  deploy (target: PROJECTION-GAP rate drops sharply; FALLBACK rate
  ~equals the pre-fix PROJECTION-GAP rate around wickets, since
  the same situations now trigger the fallback rather than the gap)

## Residual / known limits

- **Bowler is out of scope.** The backlog symptom was striker /
  non_striker null in payload; bowler null in payload was logged by
  the diagnostic block but not reproduced in the live re-confirmation
  trace. The `_project_active_batters` helper handles striker /
  non_striker only; the inline `if score_mgr.bowler_name:` guard at
  the call site preserves the existing bowler-write behavior. If a
  bowler-null pattern surfaces in production, file as a follow-up
  with the same shape — `_project_current_bowler` helper next to
  `_project_active_batters`.
- **Fix is silent on the underlying SM catch-up latency.** The
  ~24 s SM-catch-up gap that creates the fallback opportunity is
  itself a separate (higher-effort) item: shortening the SM
  ingest path so `score_mgr.striker` updates within ≤1-2 s of
  scout's strip read. Fix 7 papers over the symptom for the user;
  the root cause stays queued. With Fix 7 in place, that root-cause
  work is **less urgent** because the user no longer sees the
  placeholder UI during the gap.
- **`_canon_player_name` is invoked twice in some scenarios.** When
  the SM cutover writes `None` and the fallback writes `sb._inn`
  value, the canon function is called once for the SM value
  (returning `None`) and again for the `sb._inn` value (returning
  the canonical name). Net: one extra canon call per fallback event.
  Cost is microseconds; not worth optimizing.
- **The `_other_slot` collision check is conservative.** It declines
  the fallback when the candidate matches the already-resolved other
  slot, even when the resolution might be transient (i.e. the SM-
  resolved slot might also be wrong). In the rare case where both
  the SM-resolved slot and the SM-null slot have stale data, Fix 7
  declines to act and leaves the payload as-is. Fixing that requires
  a different shape (full re-projection from `sb._inn` when both
  slots disagree with `_active`), which is out of scope here.
