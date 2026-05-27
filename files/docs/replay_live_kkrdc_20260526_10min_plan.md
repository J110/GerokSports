# KKR/DC 10-Minute Replay Plan

Goal: run one bounded replay from the canonical live recording to validate both tracks without replaying the full match.

## Source Clip

- Canonical source: `files/logs/deliveries/live_20260524_185913/match_live_20260524_185913.ts`
- Mini source: `files/logs/deliveries/kkrdc_20260524_10min_source/kkrdc_20260524_first10.ts`
- Offset: `1710s`, derived from the full replay log's first KKR/DC live-play reads around DC 0-0.
- Duration: `600s`

## Preflight

- `TEST_DURATION` is env-configurable via `TEST_DURATION_S`.
- Decoupled OpenScout receives `OPENSCOUT_TPM_BUDGET` through `TPMBudget`.
- `openscout_loop` checks `tpm_budget.reset_in_s()` before classify calls and logs `[OPEN-SCOUT-LOOP] tpm budget exhausted`.
- Existing focused test `test_tpm_budget_blocks_calls_when_exhausted` verifies an exhausted budget makes zero OpenScout calls.

## Replay Profile

- Track 1 quality stays high: `SCOUT_PROMPT_MODE=verbose`, `SCOUT_RAW_DUMP=1`.
- Track 2 remains enabled but throttled: `OPENSCOUT_TPM_BUDGET=30000`, `OPENSCOUT_DECOUPLED_TARGET_INTERVAL_S=5.0`, `OPEN_SCOUT_MAX_TOKENS=120`.
- Track 2 does not drive production delivery selection: `USE_OPEN_SCOUT_SPANS=0`.

## Acceptance Checks

- Track 1: legal Cricbuzz deliveries inside the clip appear once in pipeline order with matching score, wicket, extras, striker, and over progression.
- Track 2: delivery-window clips and debug files exist for the mini session and are manually inspectable.

## Run Result

- Session: `replay_kkrdc_10min_20260526_193747`
- Source clip: created from offset `1710s`; size `463867440` bytes.
- Replay log: `/tmp/replay_kkrdc_10min_20260526_193747.log`
- Pipeline duration: `900s`
- OpenScout profile observed: target `5.00s`, TPM cap `30000`, `USE_OPEN_SCOUT_SPANS=0`.
- TPM gate proved active in-run: `[OPEN-SCOUT-LOOP] tpm budget exhausted` appeared; match summary reported `loop_e429_total=0`.
- Track 1 slice: `files/logs/deliveries/replay_kkrdc_10min_20260526_193747/gt_trimmed_1p1_to_2p5.jsonl`
- Track 1 diff report: `files/docs/replay_live_kkrdc_20260526_10min_diff.md`
- Track 1 diff summary: `matched=12`, `missing=0`, `phantom=2`, `divergences=148`.
- Track 2 artifact check failed: no `delivery_window.mp4`, no `window_debug.json`, no `files/logs/openscout_deliveries/replay_kkrdc_10min_20260526_193747`, and no `files/logs/openscout_spans/replay_kkrdc_10min_20260526_193747`.
