# Combined-corpus shadow ensemble (V6c vs V6d) — 2026-04-30

Operational record for **three-match** stratified inventory → combined corpus → K=5 shadows.

## Artifacts

| Kind | Path |
|------|------|
| Per-match inventories | `docs/corpus_frame_inventory_{rcb_gt,mi_srh,pbks_rr}.json` |
| M-2 stage corpus (pre-flatten) | `docs/scout_corpus_combined_v1.stage.json` |
| Combined corpus (flat `frame_id` / paths) | `docs/scout_corpus_combined_v1.json` |
| Copied JPEG pool for `run_shadow` | `docs/corpus_frames_combined_v1/` (**50** files) |
| Bucket coverage | `docs/scout_corpus_combined_v1_bucket_coverage.txt` |
| V6c K=5 runs | `docs/shadow_run_v6c_combined_20260430_*_run*.json` |
| V6d K=5 runs | `docs/shadow_run_v6d_combined_20260430_*_run*.json` |
| Discriminating-frame report | `docs/discriminating_frames_v6c_vs_v6d_combined.md` |

## Method

1. **`build_frame_inventory.py`** parameterized (`--log`, `--output`, `--frames-dir`, `--match-id`).
2. **Logs / frames:** `files/logs/runs/rcb_gt_rc9_commentary_203904.log` + `debug_frames/`; repo `logs/pipeline-*.log` + matched `debug_frames_archive/` snapshots (**mi_srh**, **pbks_rr**).
3. **`materialize_combined_corpus_frames.py`** — unique `frame_id` + flat snapshot dir (avoids `run_shadow` collisions on overlapping `frame_count` across matches).
4. **`identify_discriminating_frames.py`** — majority over **5×3** votes per variant.

## Stop conditions hit

- **death_inn2** pool **0** (no second-innings death SCOREBOARD strata in merged pool) — not a sampler bug.

See discriminating report **§7** for S3 rate / disagreement flags.
