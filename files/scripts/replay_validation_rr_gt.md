# Replay validation — RR vs GT 2026-05-09 (52nd match)

D1+D2+D3+D4+D5+D7 derivation fixes replayed against last night's
cached cluster log via `files/scripts/replay_score_manager.py`
(shadow-mode SM, no Scoreboard, no API calls).

## Inputs

- Source log: `files/logs/pipeline-20260509-rr-vs-gt-52nd-match.log`
  (36,224 lines, 832 DETAIL|F<N>|SCOREBOARD records)
- Replay log: `files/logs/replay-rr-vs-gt-derived.log`
- Frames parsed and fed: 915 (last frame F3088)
- SM mode: `shadow=True`, no Scoreboard attached, `_innings_fallback=1`

## Tonight (production) vs replay marker counts

| Marker substring               | Tonight (prod log) | Replay |
| ------------------------------ | -----------------: | -----: |
| `cold-start reject`            |                 91 |     36 |
| `Overs regression`             |                 14 |      0 |
| `batting_team_changed`         |                  2 |      0 |
| `preserving` (inn2 transition) |                  1 |      0 |

## Per-fix verdict

### D1+D2+D3 — inn1 cold-start plausibility gate
- Replay marker hits: `inn1_impossible_wickets_overs=0`,
  `inn1_severe_collapse_implausible=0`,
  `inn1_score_too_low_for_wickets=0`.
- WARM commits in replay: F350 → 84/4 (7.4), F603 → 74/4 (4.1),
  F2961 → 1/0 (0.1). All three are plausible under D1-D3 by design
  (no false positives — gate is intentionally permissive).
- Production's bad commits 5/4 (0.1) at F869 and 14/4 (8.4) at F920
  did NOT appear in the replay's FrameInput stream because the wickets=4
  side-channel that fed those frames in production (visible as
  `BEFORE_score=None-4(0.1)` in DETAIL) is not reconstructible from
  the DETAIL line alone — wickets=4 entered the SM via a path other
  than `ext_score` parsing. Shadow replay therefore did not exercise
  the D1-D3 gates on the specific tonight's-bad-cases.
- **Authoritative validation: unit tests in
  `files/tests/test_inn1_cold_start_plausibility.py` (9 cases passing).
  Replay confirms zero false-positive rejects on plausible cold-start
  commits.**

### D4 — inn2 preserve gating (`_warm_advancing_observed`)
- Replay marker hits: `NOT preserving=0`. The SM in shadow mode
  reached `set_innings_2` once (F413, reason=`wickets_regressed`),
  but the wrapper that adds the new `_warm_advanced` check lives in
  `test_pipeline.py:_set_innings_2_logged`, which the replayer does
  NOT exercise (replay calls `ScoreManager.on_frame` directly).
- **Authoritative validation: unit tests in
  `files/tests/test_inn2_preserve_gating.py` (7 cases passing) verify
  the SM-side flag and the gate decision logic in isolation.**
- Replay limitation flagged below.

### D5 — stuck-tracker recovery (large-gap + streak)
- Replay marker hits: `Overs LARGE regression=0`, `Regression streak=0`.
- The replay's WARM-mode frames mostly proposed forward-progress that
  exceeded `multi_max_12` (showing as `REJECT cricket_rules d_balts_*`)
  rather than backward overs regressions. The 8.5 → 1.4 class of
  regression that triggered tonight's 67-minute lockup did not appear
  in the replay because the replay never committed an 8.x-overs WARM
  state — the 4.1 / 7.4 baselines drove different reject patterns.
- **Authoritative validation: unit tests in
  `files/tests/test_stuck_tracker_recovery.py` (5 cases passing) prove
  large-gap + streak triggers fire on representative inputs.**

### D7 — batting_team N-frame consensus
- Replay marker hits: `team-change candidate=0`,
  `team-change consensus committed=0`.
- The replay's batting_team stayed `None` throughout (production sets
  it from the scout STRIP first segment via the cluster's team-resolution
  path that the replayer does not reproduce). With `batting_team=None`,
  the consensus branch in `_detect_innings_change` never enters
  (`self.batting_team and frame.broadcast_team` short-circuits).
- **Authoritative validation: unit tests in
  `files/tests/test_team_change_consensus.py` (5 cases passing) cover
  defer/commit/reset behavior.**

## Replay limitations (intentional, per task spec)

1. **BALL EVENT count not validated.** Shadow-mode SM has no
   Scoreboard, so ball-event emission, name canonicalization, and
   striker tracking diverge from production by design.
2. **Production-only side channels not reconstructible.** The DETAIL
   record captures SM AFTER-state fields, not all FrameInput inputs.
   The wickets=4 / batting_team=GT signals that drove tonight's bad
   commits enter SM via paths the replayer cannot rebuild from the
   log alone.
3. **`test_pipeline.py` wrapper not exercised.** The D4 gate lives in
   the cluster's `_set_innings_2_logged` wrapper; the replayer drives
   `ScoreManager.on_frame` directly and so cannot validate the wrapper.
4. **Final-state cricbuzz diff pending.** Cricbuzz scorecard for
   GT 229/4 (20) vs RR 152/10 (16.3) saved at
   `files/scripts/cricbuzz_rr_gt_2026-05-09.json` for the follow-up
   diff once a SB-attached replay path exists.

## Conclusion

Replay surfaces no crashes and no false-positive D1-D7 firings.
None of the new gates *fired* in this shadow-mode run, which is the
expected outcome given the replay reconstructs only a partial
FrameInput stream and shadow SM diverges from production state.

The D1-D7 fixes are validated empirically by their unit tests
(26/26 passing, see `files/tests/test_inn1_cold_start_plausibility.py`,
`files/tests/test_stuck_tracker_recovery.py`,
`files/tests/test_inn2_preserve_gating.py`,
`files/tests/test_team_change_consensus.py`).

A SB-attached replay (or a live re-run) is the next step to observe
the gates firing on the real production signal stream.
