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
- This replay currently has trace + ball-log signal, but not a harness-compatible GT stream.

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
- Diff is not yet possible because no KKR/DC GT commentary or ledger fixture exists in a harness-compatible form.

## Next GT Work

- Create separate DC innings and KKR innings Cricbuzz commentary fixture files before ingesting; the current ingester is single-innings only.
- Normalize only parser-hostile one-run extras in the fixture text (`byes` -> `1 bye`; `leg byes, 1 run` -> `1 leg bye`).
- Expected GT sanity once commentary is available: DC innings near 203/5 from 120 legal balls; KKR innings near 163/10 from 112 legal balls.
- Likely parser gaps to expose next: `2 wides` and `W1` run-out-with-run.
