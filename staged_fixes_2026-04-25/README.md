# Inter-match commit bundle — 2026-04-25 RR vs SRH match-2 fixes

**Status**: Diffs prepared during innings 2 (live monitoring concurrent).
Ready to land at the inter-match seam (after match-2 ends).

**No git repo at project root** — diffs were applied directly to source files in
`files/`. The pipeline only re-reads source files at process start, so the
edits do NOT take effect on the currently-running pipeline; they go live at
the next pipeline restart, which IS the "land" step. If anything urgent
forces an unscheduled restart before the seam, the changes will go live with
that restart and tests already cover them.

## Squash-merge commit message (ready to use at land time)

```
Eight production fixes from match-2 monitoring (RR vs SRH 2026-04-25
+ DC vs PBKS 2026-04-25) and the immediately-following backlog audit

All eight discovered or closed during live monitoring + the
2026-04-26 audit pass.  Each has a log-replay, config-shape,
projection-replay, or content-gate regression test against the actual
production sequence that surfaced it.  Independent diffs; minor file
overlap (scoreboard.py touched by Fix 3 and Fix 5 in different
methods, no interaction; test_pipeline.py touched by Fix 1, Fix 7,
and Fix 8 in unrelated sites — innings-1 latch helper, projection
helper, info-panel gate respectively; player_enrichment.py for Fix 6
is untouched by all others).

1. target=640 sanity bound (P0)
   F921 phantom 639-4 (76.5) latched into innings_1_total via
   max-wins logic. Real 228-6 at F1445 rejected because 228 < 639.
   Sanity bound: reject candidates with overs > 20 or score > 350.
   File: test_pipeline.py
   Tests: phantom rejected, normal latched, phantom doesn't poison,
   sanity boundaries (350/351, 20.0/20.1), max-wins preserved within
   bounds, source-callsite wired

2. this_over token-alphabet validation (P0)
   F2461 broadcast strip labeled per-ball-speed track with literal
   "THIS OVER:" field name. Pipeline ingested speed values as ball
   outcomes. Bug active intermittently since 2026-04-16 (earlier
   garbage payloads: ['2161'], ['11', '.', '41']).
   File: this_over.py
   Tests: speed-tokens rejected, 2026-04-16 garbage rejected,
   legal sequence accepted, mixed list rejected, helper boundaries

3. this_over chronological reorder on FOW upgrade (P1)
   Wicket overlay updated ticker before score strip caught up,
   leading to W token appearing before the boundary that came first.
   FOW upgrade pins wicket to ball X.Y; reorder this_over tokens
   accordingly. Wired via new `Scoreboard.on_fow_upgrade` callback
   set in test_pipeline.py main loop.
   Files: this_over.py + scoreboard.py + test_pipeline.py
   Tests: reorder on upgrade (F2068 replay), no-op when correct,
   no-W graceful, extras-skipped legal-count, callback fires on
   upgrade, callback skipped on immutable refuse

4. overs-consensus regression guard (P0)
   F3117-F3120 sequence: (POWERPLAY) text triggered 6.0→0.5 overs
   regression, poisoning state. Mirrors existing bowler-stats
   [CONSENSUS-BLOCKED] guard at consistent_tracker.py:L237-281.
   File: consistent_tracker.py
   Tests: regression rejected, normal progression accepted,
   set_innings_2 path unaffected, cross-field independence preserved

5. striker self-collision guard in update_batter (P1)
   F170-F173 sequence: legitimate swap then transitional review-
   graphic misread drove update_batter onto a name already in the
   opposite slot, ending in striker == non_striker (~8% of frames
   during match-2 innings 2). Conservative collision guard at the
   legacy striker writes inside update_batter; legitimate swap path
   (atomic flip at test_pipeline.py:6228-6237) is independent and
   unaffected. WS payload was already correct via ScoreManager;
   commentary subsystems and DETAIL telemetry that read sb._inn
   directly are now protected.
   File: scoreboard.py
   Tests: refuse non_striker write when same as striker, refuse
   striker write when same as non_striker, idempotent self-writes
   accepted, F170-F173 production replay

6. Pass-2 enrichment client timeout/retry config (P1)
   3/3 sessions on 2026-04-25 timed out at 271 s ±1 s in Pass-2
   (groq/compound web-search verify). Root cause: explicit
   timeout=90.0 in _make_client() composed with Groq SDK 1.1.2's
   default max_retries=2 (3 attempts × 90 s = 271 s). Pass-2 has
   been delivering zero retro-patched styles since deploy.
   Single-shot config: timeout=240.0, max_retries=0. Shorter
   wall-clock than the old broken budget AND can actually succeed.
   Pass-2 is background-async with Pass-1 fallback, so disabling
   SDK auto-retry has no user-visible cost. Verification is
   positive-firing: look for [ENRICH] Pass-2 (verify) complete
   followed by [STYLES-PATCH] Updated N card slots on first restart.
   File: eyes/player_enrichment.py
   Tests: client config-shape assertion (timeout==240.0,
   max_retries==0). Existing wrapper tests (happy + timeout)
   already cover behaviour with mocked clients.

7. WS-PROJECTION-GAP fallback to sb._inn when SM-null + active (P2)
   F145 W2 (Jurel dismissal): WS payload emitted striker=null for
   ~24s while SM caught up to scout's strip read. sb._inn already
   held 'Riyan Parag' as the new striker AND Parag was in
   active_batting, but build_full_payload's SM-cutover wrote the
   None through. UI showed "incoming batter…" / "—" during the
   most attention-grabbing moment of the match. 14 fires across
   ~340 frames in match-2 innings 2, concentrated around wickets.
   Fix: extracted build_full_payload's SM-cutover logic into
   module-level _project_active_batters helper; falls back to
   sb._inn when state[slot] is None AND sb._inn[slot] is in
   active_batting AND it doesn't collide with the already-resolved
   other slot. Active-batting check preserves S18's dismissed-
   batter-leak prevention. Strengthened by Fix 5: sb._inn is now
   collision-protected, so this fallback can never surface a
   self-collided pair. Verification is positive-firing — search
   logs for [WS-PROJECTION-FALLBACK] on next wicket.
   File: test_pipeline.py
   Tests: SM-resolved no-fallback, SM-null+dismissed no-fallback
   (regression-protects S18 leak prevention), SM-null+active uses
   sb._inn, F145 W2 production replay, _other_slot collision-
   avoidance defence.

8. INFO-PANEL bowler-strip gate — content-based graphic gate (P1)
   F619 DC vs PBKS (2026-04-25 16:02:04): "YUZVENDRA CHAHAL IPL
   CAREER MATCHES 181 WICKETS 225 ECONOMY 8.0" stats overlay during
   Marco Jansen's over → Scout extracted bowler="Chahal" → SM
   committed Chahal as bowler before he was actually introduced.
   Existing dead-time skip on camera_view='graphic' missed F619
   because vision.last_camera_view lags scout response by 1-2
   frames; F619 ran with the previous frame's bowlers_end tag.
   Existing frame_type=='GRAPHIC' pop didn't fire because the
   strip was visible (frame_type='SCOREBOARD'). Fix: rewrote
   filter_info_panel_contamination from log-only no-op to active
   gate — when vision_desc contains an _INFO_PANEL_KEYWORDS marker
   (CAREER, IPL CAREER, IN T20, HEAD TO HEAD, PROJECTED SCORE,
   etc.), strip bowler / bowler_name / bowler_figures from
   extracted. Score/wickets stay (tracker bounds them). Content-
   based gate doesn't depend on camera_view tag arrival timing.
   Verification is positive-firing — search logs for [INFO-PANEL-
   GATE] on next match (expect 5-15/match).
   File: test_pipeline.py
   Tests: career-keyword strips bowler, no-keyword no-op (over-
   firing protection), F619 production replay, no-bowler-present
   logs only (graceful no-op), comprehensive bowler/bowler_name/
   bowler_figures strip on PROJECTED SCORE marker.

All eight use log-replay, config-shape, projection-replay, or
content-gate regression tests; fixes 1–5 are log-replay fixtures
from RR vs SRH match 2, fix 6 asserts explicit client config to
insure against silent SDK-default reverts, fix 7 unit-tests the
projection helper directly with `Scoreboard` + stub-SM fixtures, and
fix 8 unit-tests the rewritten content gate against the F619 trace.

Source line counts:
  test_pipeline.py:           +172 (Fix 1 helper + callsite + Fix 3 wiring + Fix 7 helper + callsite rewrite + Fix 8 content-gate rewrite)
  this_over.py:               +144 (Fix 2 alphabet + gate, Fix 3 reorder)
  scoreboard.py:              +45  (Fix 3 callback hook +27, Fix 5 guard +18)
  consistent_tracker.py:      +27  (Fix 4 two guard blocks)
  eyes/player_enrichment.py:  +5   (Fix 6 client config + comment context)
  test_recent_fixes.py:       +989 (36 new tests + helpers + test
                                    hygiene rewrite of two stale-baseline
                                    tests, see addendum below)

Test results: PASS 241 / FAIL 0 (the two long-standing pre-existing
baseline failures — `test_this_over_late_boundary_ball_appends_to_held`
asserting a no-longer-current `_pending_clear` invariant, and the
`>= 18.0` over-broad source-text grep in
`test_twenty_over_invariant_check_in_source` — were rewritten in this
bundle to match current production semantics. Suite is now zero-FAIL
on the 2026-04-26 working tree. See "Test hygiene addendum" below.)
```

## Per-fix breakdown

See subdirectories for detailed READMEs:
- `fix1_target_sanity/` — P0, +43 src / +112 tests, 6 tests
- `fix2_alphabet/` — P0, +69 src / +96 tests, 5 tests
- `fix3_reorder/` — P1, +111 src / +120 tests, 6 tests
- `fix4_overs_consensus/` — P0, +27 src / +99 tests, 4 tests
- `fix5_striker_collision/` — P1, +18 src / +148 tests, 4 tests
- `fix6_pass2_client_config/` — P1, +5 src / +43 tests, 1 test (3 sub-checks)
- `fix7_ws_projection_fallback/` — P2, +71 src / +200 tests, 5 tests (16 sub-checks)
- `fix8_info_panel_gate/` — P1, +49 src / +160 tests, 5 tests (15 sub-checks)

**Total**: 8 production fixes (3 P0, 4 P1, 1 P2), 36 new regression
tests (25 log-replay fixtures from today's match + 1 client
config-shape assertion + 5 projection-helper tests with `Scoreboard`
+ stub-SM fixtures + 5 content-gate tests with stub-scoreboard
fixtures, including F619 DC-vs-PBKS production replay).

## Test hygiene addendum (test-only, no production-source delta)

In addition to the eight production fixes, two long-standing baseline
test failures that had been carried through every recent fix landing
were rewritten to match current production semantics. Both were
stale-test-vs-current-source mismatches, not production bugs.

1. `test_this_over_late_boundary_ball_appends_to_held`
   The pre-condition assertion expected `_pending_clear=True` after a
   single `check_over_change` call on a 5-token state. Production
   evolved (2026-04-20 deferred-rollover work,
   `ROLLOVER_MAX_DEFER_FRAMES=2` in `eyes/this_over.py`) to require
   the rollover to be deferred for up to N frames before the held
   state is forced. Test now drives `check_over_change`
   `(ROLLOVER_MAX_DEFER_FRAMES + 1)` times to exhaust the defer
   budget and reach the `_pending_clear=True` branch — then exercises
   the late-event-append behaviour the test was originally about
   (which was previously masked by the failing pre-condition).

2. `test_twenty_over_invariant_check_in_source`
   The negative-grep `assert ">= 18.0" not in content` was over-broad:
   post-Bug-#16 the codebase legitimately uses `< 18.0` (cold-start
   innings-2 detection, twice in `test_pipeline.py`, substring matches
   `18.0`) and `>= 18.0` (innings-1-near-end heuristic on
   `_inn1_overs >= 18.0 or _inn1_wkts >= 8`). Both are intentional
   non-rollover uses. The negative-grep sub-check was dropped; the
   two positive-grep sub-checks (`>= 20.0` present, `>= 10` present)
   are retained as the actual regression protection for the auto-swap
   trigger.

File touched: `files/test_recent_fixes.py` (~15 lines net delta;
included in the +989 total above).

## Land procedure (at inter-match seam)

1. Verify pipeline is at safe stop point (over boundary, between
   innings, or post-match).
2. Stop pipeline (kill Python PID).
3. Confirm full test suite green: `cd files && .venv/bin/python test_recent_fixes.py`
   (expect 241 PASS / 0 FAIL — the two long-standing baseline failures
   were rewritten to current production semantics in this bundle; see
   "Test hygiene addendum").
4. Restart pipeline. Watch first 50 frames for clean cold-start.
5. Verify in next live frames (negative-firing — absence is the signal,
   except where noted):
   - `[INNINGS-END] Rejecting bogus latch candidate` if a phantom
     end-zone read fires (Fix 1 active)
   - `[TOKEN-VALIDATE]` log if a speed-track misread fires (Fix 2 active)
   - `[FOW-REORDER]` log on next wicket if positions need adjusting
     (Fix 3 active)
   - `[CONSENSUS-BLOCKED] overs:` if any (POWERPLAY)-class
     misparse fires (Fix 4 active)
   - `[STRIKER-COLLISION] Refusing` if any transitional review-
     graphic misread tries to drive striker == non_striker
     (Fix 5 active)
   - **POSITIVE-firing for Fix 6:** within ~30–120 s after Pass-1
     completes, expect `[ENRICH] Pass-2 (verify) complete in <N>ms`
     followed by `[STYLES-PATCH] Updated N card slots from background
     Pass-2 enrichment`. If those lines fire, Pass-2 is delivering
     retro-patched styles for the first time since its async-split
     deploy. If `[ENRICH] Pass-2 (verify) LLM call failed: ...`
     fires instead, the fallback is still working but the grounded
     path is broken at the model — file the non-grounded fallback
     follow-up immediately.
   - **POSITIVE-firing for Fix 7:** on the first wicket of match 3,
     expect `[WS-PROJECTION-FALLBACK] striker='<name>' surfaced from
     sb._inn (SM-null, in active_batting)` to fire during the SM
     catch-up window. Complementary `[WS-PROJECTION-GAP]` warns
     should drop sharply (only fire now when sb._inn ALSO doesn't
     have the value, i.e. genuine gaps where scout hasn't read the
     new batter yet). If FALLBACK never fires across multiple
     wickets, the helper is dormant — investigate why the active-
     batting check is excluding sb._inn values that should pass.
   - **POSITIVE-firing for Fix 8:** within ~5-15 frames per match,
     expect `[INFO-PANEL-GATE] bowler stripped — name='<X>'
     panel_keyword='<KEYWORD>'` to fire on stats overlays (career
     stats, head-to-head, projected-score graphics). If zero fires
     across multiple matches, Scout isn't surfacing INFO_PANEL text
     or the keyword list needs broadening. Spot-check: at the next
     bowler change, the change should land within 1-2 active-play
     frames AFTER the announce graphic clears, NOT before — Fix 8
     prevents the future-bowler-locked-in-too-early class.
6. Update `files/docs/backlog.md` to mark all eight entries
   `**Status: SHIPPED 2026-04-25 inter-match commit**` (Fixes 6, 7,
   and 8 filed under the 2026-04-26 dated section but ship with the
   same seam commit).

## Rollback safety net

Tagged in `files/` git repo as `pre-restart-bundle-2026-04-25`
(commit `b5471c7`).

**Coverage** — the tag was created after Fixes 1-5 had already been
applied to source on 2026-04-25 evening. So the tag's snapshot is
the **post-Fix-1-5, pre-Fix-6-7-8** state. Reset semantics:

```bash
cd files
git reset --hard pre-restart-bundle-2026-04-25
```

- **Rolls back**: Fix 6 (`eyes/player_enrichment.py` Pass-2 client
  config), Fix 7 (`test_pipeline.py` `_project_active_batters` helper
  + `build_full_payload` callsite rewrite + `test_recent_fixes.py`
  Fix 6/7 tests), Fix 8 (`test_pipeline.py`
  `filter_info_panel_contamination` content-based gate +
  `test_recent_fixes.py` Fix 8 tests), the test-hygiene rewrites
  in `test_recent_fixes.py`, and `docs/backlog.md` updates from
  2026-04-26.
- **Does NOT roll back**: Fixes 1-5 (they're baked into the tag's
  snapshot). All five had passed their log-replay regression tests
  before the tag was cut, so they were considered known-good at
  tag time — the rollback is to that "known-good post-test" state,
  not to the pre-bundle production state.

If the first-restart regression is traceable to one of Fixes 1-5, the
tag-reset alone won't recover. In that case, identify the offending
fix from its log signature, then revert just that fix's source hunk
manually (each fix's subdirectory README documents its source change
in enough detail to reverse-engineer the diff). Fixes 1-5 source
surfaces:
- Fix 1: `test_pipeline.py` (innings-1-final latch helper + callsite)
- Fix 2: `this_over.py` (token alphabet validation + gate)
- Fix 3: `this_over.py` + `scoreboard.py` (FOW reorder + callback)
- Fix 4: `consistent_tracker.py` (overs CONSENSUS-BLOCKED guard)
- Fix 5: `eyes/scoreboard.py` (`update_batter` collision guard)

If the regression is caused by Fix 6, Fix 7, or Fix 8 specifically
(the highest-confidence-but-least-production-tested members of the
bundle), the tag-reset is the full recovery — restart the pipeline
against the reset source.
