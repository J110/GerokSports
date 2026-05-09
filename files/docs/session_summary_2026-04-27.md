# Session Summary - 2026-04-27

## Scope

Today's work focused on stabilizing the DC-vs-RCB live pipeline, shipping
Bundle A fixes, validating recent fixes against live production behavior, and
logging newly observed root causes in `files/docs/backlog.md`.

Bundle A was implemented. Bundle B and Bundle C were not implemented.

## Services Started And Stopped

Live stack used during validation:

- Pipeline watchdog running `files/test_pipeline.py` with WS on port `8765`.
- Parity monitor.
- Element checker.
- Scorecard UI on port `3000`.

End-of-session shutdown:

- Pipeline watchdog and child pipeline process were terminated.
- Parity monitor and element checker were terminated.
- Next UI process was terminated.
- Final verification found no remaining matching live-stack process and no
  listeners on ports `3000` or `8765`.

## Implemented Today

### Bundle A

Implemented in `files/test_pipeline.py` and covered in
`files/test_recent_fixes.py`.

- (8) AUTO-SWAP ScoreManager hook:
  the pipeline AUTO-SWAP path now calls `score_mgr.set_innings_2()` alongside
  `scoreboard.set_innings_2()`, passing the injected target and canonical new
  batting team.
- (9) WS projection fallback hardening:
  `_project_active_batters()` now resolves `scoreboard._inn` names through the
  batting card and requires `status == "batting"` before projecting fallback
  values into the WS payload.
- (12) Standings-row contamination gate:
  `filter_standings_row_contamination()` strips `score`, `wickets`, and
  `match_overs` when the vision text contains standings/table/rank/position
  context labels.

Regression status:

- `files/test_recent_fixes.py` reported `484 PASS / 0 FAIL` after Bundle A.

### Recently Shipped Fixes Validated Today

- (13) `wire.py` fractional-over crash:
  live validation emitted wire commentary at `8.1`, `8.3`, `13.2`, `13.5`,
  `14.2`, `14.3`, `15.4`, and `15.5` with no `ValueError` or traceback.
- State-recovery telemetry:
  the pipeline recovered from a bad mid-match `0-0` cold-start via
  `FORCE_COLD_START_RECALIBRATION`, but the recovery exposed follow-up issues
  with partnership anchoring and this-over cursor state.

## Live Validation Results

Validated live:

- (9) WS projection fallback hardening:
  during multiple SM-null projection gaps, fallback projected only current
  active `status="batting"` card entries. After Kuldeep Yadav's W9 cleanup, it
  did not resurrect the dismissed batter.
- (13) Wire fractional-over parser:
  no crash across multiple fractional-over wire emissions.

Partially validated or still pending:

- (7) Fix 13 Path B:
  still pending live validation by the exact WICKET-handler trigger. The
  Kuldeep wicket was cleaned via the extractor/scorer absence path and
  placeholder upgrade, not the new Path B sibling hook.
- (8) AUTO-SWAP ScoreManager hook:
  source-level regression passed, but live validation was blocked because the
  pipeline missed the upstream final wicket/all-out precondition and did not
  enter a clean innings-2 transition. This is not evidence against `(8)`; the
  hook remains correct but unexercised in production.
- (10) Dual-broadcaster Path A for `over_history`:
  still pending fixture-level validation against the LSG-vs-KKR over-boundary
  stuffing window.
- (12) Standings-row contamination gate:
  local regression passed, but no post-restart standings graphic was observed
  for live validation.

## New Issues Logged Today

These are now in `files/docs/backlog.md`.

- (14) P0 - team-score regression consensus can accept lower score in normal
  play.
- (15) P1 - mid-innings cold-start FOW placeholders dominate UI.
- (16) P0 - new-batter balls corruption becomes self-protecting.
- (17) P1 - bowler identity can be sourced from batting rows or contextual
  strips.
- (18) P1 - same-player active-slot self-collision still reaches WS. This was
  reproduced again after Kuldeep Yadav's W9 cleanup.
- (19) P1 - mid-match cold-start can accept a false `0-0` pre-match/DRS
  graphic before recovering.
- (20) P1 - partnership display anchors from zero after mid-innings recovery.
- (21) P1 - this-over rollover cursor can remain stuck after mid-innings
  recovery, eventually saturating the token buffer and dropping ball events.
- (22) P0 - all-out / final-wicket detection coverage gap can block innings
  transition and leave `(8)` unvalidated.

## Most Important Pending Work

P0 / high priority:

- (7) Validate Fix 13 Path B on a live WICKET event where the dismissed batter
  is known before FOW witness enrichment.
- (14) Block team-score regression unless an explicit correction or innings
  reset authority is present.
- (16) Cap or consensus-gate new-batter balls so a bad initial large balls
  value cannot become sticky.
- (22) Add final-wicket/all-out authority and innings-break lock so the
  pipeline promotes `9 -> 10` when supported by dismissal/all-out evidence and
  rejects contextual wicket regressions during the transition.

P1 / next bounded fixes:

- (6) Bundle B: Rinku Singh extractor split. Not implemented today.
- (8) Live-validate AUTO-SWAP `score_mgr.set_innings_2()` on a clean innings
  transition after (22) is fixed or avoided.
- (12) Live-validate standings-row gate on the next standings/table graphic.
- (17) Harden bowler identity sourcing and post-over bowler-change recovery.
- (18) Add a final active-slot invariant before WS payload build.
- (19) Add mid-match zero-score cold-start gate.
- (20) Re-anchor or hide partnership after mid-innings recovery.
- (21) Resync `ThisOverManager` cursor after mid-innings recovery.

Bundle C remains architectural and should be planned separately:

- Striker self-collision cutover completion.
- Remaining cold-start mid-match join team-assignment cases.
- SCORER active-batter invariants.
- Bowler stats graphic misread.
- State-recovery consensus override Phase 2.

## Backlog Status

`files/docs/backlog.md` was updated with:

- (9) marked `SHIPPED-validated live`.
- (13) live validation extended with additional fractional-over examples.
- (18) fresh reproduction evidence from the Kuldeep wicket window.
- New items (21) and (22) with root-cause notes and proposed fixes.

Tomorrow's recommended first fix is (22), because the missed all-out state
blocked the innings transition and prevented clean live validation of (8).

Follow-up diagnostic on 2026-04-28 found no clean `75/10`, no proposed
`wickets→10`, no `9 -> 10` rejection, and no AUTO-SWAP attempt in the final
wicket window. The evidence points to a coverage / alternate-trigger gap rather
than a guard rejecting a valid `9 -> 10` update.
