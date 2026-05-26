# Replay Triage: KKR vs DC 2026-05-26

## Artifacts

- Replay log: `/tmp/replay_20260526_115105.log`
- Session: `replay_live_kkrdc_20260526_115105`
- Trace: `logs/trace/replay_live_kkrdc_20260526_115105.jsonl`
- Scout raw: `files/logs/deliveries/replay_live_kkrdc_20260526_115105/scout_raw.jsonl`
- Ball log TSV: `files/logs/ball_log/ball_log_live_20260526_115151.tsv`
- Ball log JSONL: `files/logs/ball_log/ball_log_live_20260526_115151.jsonl`

## Replay Result

- Final replay state from log: KKR 130/4 (13.3), target 177.
- Many Scout/OpenScout `429` rate-limit errors occurred, so this is not yet a clean attribution replay.
- D-LIVE-1 and D-LIVE-2 are collapsed in file-source replay by design; remaining signal mainly tests cadence, graphic write-side poisoning, and classifier errors.

## Current Blockers

- GT ingest by `--match-id` is unsupported.
- Supported GT inputs are `--ledger` and `--commentary`.
- `files/scripts/replay_diff_harness.py` accepts only `--pipeline`, `--ground-truth`, and `--report`.
- Ball log JSONL is not directly accepted by `replay_diff_harness.py`.
- This replay now has trace + ball-log signal, a harness-compatible pipeline snapshot stream, and KKR/DC GT snapshot streams.

## GT Source Search

- Search for `152263`, `kkr-vs-dc`, `70th match`, and KKR/DC long-form names found no existing commentary or ledger source under `data`/`files`.
- Matches were limited to `files/match_state_cache.json`, this triage note, and `files/docs/recording_inventory.md`.
- Do not use `files/scripts/scrape_batch_commentary.py` for this match until the ESPN API match id is verified; `152263` is the Cricbuzz id from the handoff.

## Snapshotter Check

- `files/scripts/replay_captured_scout_trace.py --help` supports `--dump`, `--session-id`, `--fixture`, and `--snapshot-output`.
- Snapshotter command:

```bash
files/.venv/bin/python files/scripts/replay_captured_scout_trace.py \
  --dump files/logs/deliveries/replay_live_kkrdc_20260526_115105/scout_raw.jsonl \
  --session-id replay_live_kkrdc_20260526_snapshotter \
  --fixture dckkr \
  --snapshot-output files/logs/deliveries/replay_live_kkrdc_20260526_115105/ui_snapshots.jsonl
```

- Result: succeeded and produced `files/logs/deliveries/replay_live_kkrdc_20260526_115105/ui_snapshots.jsonl` with 85 snapshots.
- Recording/replay remains incomplete and noisy because of many Scout/OpenScout `429`s, but the output is useful for fixture/tooling validation.

## GT Fixtures

- Commentary fixtures:
  - `files/tests/fixtures/kkr_dc_20260524_innings1_cricbuzz_commentary.md`
  - `files/tests/fixtures/kkr_dc_20260524_innings2_cricbuzz_commentary.md`
- GT snapshot fixtures:
  - `files/tests/fixtures/kkr_dc_20260524_innings1_gt_snapshots.jsonl`
  - `files/tests/fixtures/kkr_dc_20260524_innings2_gt_snapshots.jsonl`
- Parser fixes made in `files/scripts/ingest_cricbuzz_ground_truth.py`: textual one-run byes/leg-byes, plural wides, run-out with completed runs, and non-bowler-attributable wicket handling.
- Ingest final states:
  - Innings 1: DC 203/5, 120 legal balls, extras total 12.
  - Innings 2: KKR 163/10, 112 legal balls, extras total 5.

## Diff

- Innings 1 report: `files/docs/replay_live_kkrdc_20260526_diff_innings1.md`
- Summary: matched=72, missing=57, phantom=13, divergences=1019.
- Top surface counts: `Extras-counter-drop` 150, `F-A-commit-lag` 65, `G-pipeline-lag` 57, `E3-wicket-frame-misalign` 55, `D-post-FoW-striker` 43, `F-B-ad-occlusion` 33.
- Innings 2 diff not run; pipeline snapshots were not cleanly isolated by innings.
