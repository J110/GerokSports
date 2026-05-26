# Next Agent Handoff — 2026-05-26

This is a self-contained takeover briefing. Written immediately after the first live broadcast capture (KKR vs DC, IPL 70th match, 2026-05-24). Read this before touching anything.

## 1. State of the world

Branch: `derive-not-detect` (per CLAUDE.md and pre-existing workstream stack).

Two long-running handoffs cover prior sessions:
- `HANDOFF.md` — discipline + workstream history. §18 just added covers the live match.
- `Architecture_HANDOFF.md` — architecture + meta-findings. §13 + §14 just added cover live-pipeline learnings.

CLAUDE.md governs response style, code discipline, and process. Read it; users have explicit no-preamble / no-summary preferences. The empirical-budget framework was retired by user directive 2026-05-24 — do NOT reintroduce 5-call budget language.

Both Cowork and Zed read the same `CLAUDE.md`. Cowork edits files; Zed executes git. Cowork sandbox cannot write to `.git` or run git commands — always hand commit text to Zed.

Working venv: `files/.venv/bin/python` (Python 3.12.13). System `python3` is 3.9 and will fail on `int | None` syntax.

## 2. What happened (live match session, 2026-05-24)

Session `live_20260524_185913` captured the full KKR vs DC IPL match end-to-end:

- 12GB MPEG-TS (`files/logs/deliveries/live_20260524_185913/match_live_20260524_185913.ts`)
- 907MB fragmented MP4 (`files/logs/deliveries/live_20260524_185913/match_live_20260524_185913.mp4`)
- 392 lines of Vision SCOUT raw output (`scout_raw.jsonl` in the session dir)
- 2497 lines of OpenScout sidecar (`logs/openscout-live_20260524_185913.jsonl`)
- 8 lines of ball-by-ball logger TSV (`files/logs/ball_log/ball_log_live_20260524_185913.tsv` — sparse because SM never reached steady-state warm)

Three artifacts shipped before/during the match:

- `files/scripts/ball_by_ball_logger.py` — async WS subscriber writing one row per state-signature change. Auto-reconnects.
- `files/docs/LIVE_MATCH_RUNBOOK.md` — 6-terminal launch playbook. Hardened during the live run: `-f tee` muxer for the UGREEN sender (was silently mis-encoding the mp4 with a 3-output `-c copy` form), drain order with sleep between sender and recorder, T-5 health check tailing `scout_raw.jsonl`, post-match Cricbuzz diff workflow.
- `scripts/shutdown_live_match.sh` — graceful shutdown of all six processes with SIGINT→TERM→KILL escalation. Scheduled via `nohup sleep+exec`; fired at 23:30 IST exactly on schedule.

One code patch shipped during the match: `files/eyes/capture/udp_frame_source.py` — added `+nobuffer`, `-flags low_delay`, `-max_delay 0` to the internal ffmpeg subprocess. Helped but did not fully solve the consumer-buffer-lag class. Initial patch attempt with `-probesize 32 -analyzeduration 0` was reverted (starves the MPEGTS H264 parser, produces blank frames).

## 3. Five defects to attribute (D-LIVE-1 through D-LIVE-5)

The live UI never reached steady-state ball-by-ball tracking. Five interacting defects were observed; full attribution requires offline replay. Each is described in `HANDOFF.md §18` and `Architecture_HANDOFF.md §13`.

**D-LIVE-1** — Stale `match_state_cache.json` from a previous session was hot-resumed; SM rejected live reads as score regressions. Worked around mid-match by deleting cache. Pattern: cross-session state-source defect; cache freshness gating is the architectural cure.

**D-LIVE-2** — UDPFrameSource's internal ffmpeg subprocess accumulates a decoded-frame buffer over ~10-15 min, putting the consumer 60-90s behind the producer. Recorder on UDP 9998 (`-c copy`, no decode) stays live throughout. `[UDP-STREAM-FROZEN]` warning fires but no auto-recovery is wired. Cure: watchdog escalation to `_kill_ffmpeg`+`_spawn_ffmpeg`.

**D-LIVE-3** — Vision SCOUT cadence at 1 call per 7-10s is too thin for T20 ball rate (~20-30s/delivery). AdaptiveSleep + pixel-diff + text-band gates compose to reject most frames. Cure: classifier-aware ceiling drop during `active_play` frames.

**D-LIVE-4** — Vision misreads between-overs stats graphics (e.g. "MOST WICKETS BY SPINNERS … KKR 34 RR 30 GT 23 …") as per-batter card rows. SM's batter ledger latches on the fictional state. UI captured `Miller 94(44), Patel 43(43)` partnership 137(87), arithmetically consistent but factually wrong (actual: Axar 22(17), Miller 4(5)). Cure: classifier-aware write-side veto when `frame_phase ∈ {advertisement, graphic, stats_package}`.

**D-LIVE-5** — Vision SCOUT classified F58 as `ADVERTISEMENT` despite broadcast showing live play with visible scoreboard. Edge-case in camera-view classifier. Cure: cross-check `cam=ad` against `STRIP: <non-null>`; downgrade ad classification if strip parses.

## 4. First-move instructions

In this order:

**Step 1 — Verify the recording is intact.** Confirm both files exist and are not zero-byte:
```bash
ls -lah files/logs/deliveries/live_20260524_185913/
# Expect: match_*.ts ≈ 12GB, match_*.mp4 ≈ 907MB
```

**Step 2 — Confirm git state.** Confirm the three new files are committed:
```bash
git log --oneline -10
git status
# Files to confirm: scripts/shutdown_live_match.sh, files/scripts/ball_by_ball_logger.py,
# files/docs/LIVE_MATCH_RUNBOOK.md (recent edits), files/eyes/capture/udp_frame_source.py
# (low-delay flags patch), HANDOFF.md §18, Architecture_HANDOFF.md §13+§14,
# NEXT_AGENT_HANDOFF.md
```

If any are uncommitted, group them as: `docs: live-match handoff updates + runbook + shutdown + ball-by-ball logger`.

**Step 3 — Run the offline replay.** This is the load-bearing diagnostic step. The recording is the source of truth; replaying through the pipeline with `FRAME_SOURCE=file` removes UDP/decoder buffering from the equation. Each D-LIVE defect becomes deterministic.

```bash
cd ~/Projects/SportsComm
rm -f files/match_state_cache.json   # CRITICAL — D-LIVE-1 collapses without this
export BMF_SESSION_ID="replay_live_kkrdc_$(date +%Y%m%d_%H%M%S)"
export CRICBUZZ_MATCH_ID=152263
export CRICBUZZ_MATCH_SLUG=kkr-vs-dc-70th-match-indian-premier-league-2026
export FRAME_SOURCE=file
export FRAME_SOURCE_FILE=files/logs/deliveries/live_20260524_185913/match_live_20260524_185913.ts
export SCOUT_PROMPT_MODE=verbose
export USE_OPEN_SCOUT=1
export OPENSCOUT_DECOUPLED=1
export OPENSCOUT_DECOUPLED_TARGET_INTERVAL_S=2.0
export SCOUT_RAW_DUMP=1
export SKIP_PREMATCH_S=0
export PYTHONUNBUFFERED=1
files/.venv/bin/python files/test_pipeline.py 2>&1 | tee /tmp/replay_$(date +%Y%m%d_%H%M%S).log
```

In parallel, launch the ball-by-ball logger against the replay's WS:
```bash
files/.venv/bin/python files/scripts/ball_by_ball_logger.py \
  --ws ws://localhost:8765 --out-dir files/logs/ball_log
```

**Step 4 — Ingest Cricbuzz ground truth.** Once replay completes:
```bash
files/.venv/bin/python files/scripts/ingest_cricbuzz_ground_truth.py \
  --match-id 152263 --match-slug kkr-vs-dc-70th-match-indian-premier-league-2026 \
  --output files/tests/fixtures/gt_kkr_vs_dc_20260524.json
```

**Step 5 — Diff replay output against GT.** Use the existing diff harness (`files/scripts/replay_diff_harness.py`). Attribute each per-row delta to a specific D-LIVE defect class. Expected output is the per-defect-class cohort that drives subsequent workstreams.

## 5. What's left (workstream candidates, prioritization-pending)

In rough priority order after the replay diff is in hand:

1. **WS-LIVE-A — Cache freshness gating (D-LIVE-1).** Smallest scope; clear cure. Audit `files/test_pipeline.py` cache-load site; refuse `match_state_cache.json` with `saved_at` older than ~30 min OR from a different `match_id`. ~10-20 LOC.

2. **WS-LIVE-B — UDPFrameSource watchdog auto-restart (D-LIVE-2).** Wire `_consumer_md5_streak ≥ K` (K = 15-20, well above the warn threshold of 5) to call `_kill_ffmpeg()` + `_spawn_ffmpeg()` with backoff. Verify against the live recording by replaying via UDP rather than file source. ~20-30 LOC + 1 trace tag + 1 unit test.

3. **WS-LIVE-C — Write-side graphic-context veto (D-LIVE-4).** Add a guard in the per-batter card writer that consults `frame_phase` / `camera_view` and refuses writes when the classifier reports a graphic/stats/ad context. Cross-fixture verification on the replay run. Scope likely 30-50 LOC across `score_manager.py` per-batter write sites.

4. **WS-LIVE-D — Vision cadence ceiling drop under `active_play` (D-LIVE-3).** Investigate AdaptiveSleep + pixel-diff + text-band interaction. Likely investigation memo before code; the three gates each have legitimate reasons for their current thresholds.

5. **WS-LIVE-E — Ad-misclassify cross-check (D-LIVE-5).** Lower priority; one-bit prompt or post-classifier check. Scope ~10 LOC if it can be done at the classifier-output layer.

6. **Pre-existing workstreams from `Architecture_HANDOFF.md §11`** — D1+D2 empirical validation on next replay, §12 catalogue extension, C20b populate, Surface E skeleton — all still open but lower priority than the D-LIVE cohort.

## 6. Standing discipline reminders

- §15 fence on `self.striker` writes is canonical (3 paths: `apply_striker_event`, `apply_striker_identity_resolved`, `apply_striker_identity_proposed`). Do not add a 4th.
- Layer 1.5 (36 ledger + 6 cross-field) + Layer 2 (30-ball ledger) must pass pre-commit. Pre-commit hook uses `files/.venv/bin/python`.
- Static-investigation-first protocol (S22). Predicate-trail static-falsification before instrument-replay-then-fix. S33/S34/S35 empirical-anchoring stack remains canonical for any replay-based work.
- "Broadcast IS the corroboration" — no runtime dependency on external data sources (Cricbuzz commentary real-time, audio, third-party APIs). Cricbuzz GT is acceptable as offline-only training/validation substrate, not live state-source.
- Track 1 and Track 2 are independent. Borrow patterns, not dependencies.

## 7. File map (pointers, not contents)

| Path | Purpose |
|---|---|
| `HANDOFF.md §18` | Live match session narrative + defect descriptions |
| `Architecture_HANDOFF.md §13, §14` | Live-pipeline architecture + updated first-move |
| `files/docs/LIVE_MATCH_RUNBOOK.md` | Operational playbook for the next live capture |
| `files/docs/TRACK2_STATUS.md` | Track 2 (OpenScout + clips) status |
| `files/docs/TRACK2_ARCHITECTURE.md` | Track 2 architecture reference |
| `files/scripts/ball_by_ball_logger.py` | Live WS subscriber + TSV/JSONL emitter |
| `files/eyes/capture/udp_frame_source.py` | Pipeline UDP consumer (subject of D-LIVE-2) |
| `files/match_state_cache.json` | Hot-resume cache (subject of D-LIVE-1) |
| `scripts/shutdown_live_match.sh` | Auto-shutdown script |
| `files/scripts/ingest_cricbuzz_ground_truth.py` | GT ingester for diff |
| `files/scripts/replay_diff_harness.py` | 16-surface diff classifier |
| `files/scripts/replay_captured_scout_trace.py` | Snapshotter (SM-only per WS-N) |
| `files/logs/deliveries/live_20260524_185913/` | Live match archive (12GB .ts + 907MB mp4 + scout_raw) |
| `logs/openscout-live_20260524_185913.jsonl` | OpenScout sidecar (2497 lines) |
| `files/logs/ball_log/ball_log_live_20260524_185913.tsv` | Live ball-log (8 sparse rows) |

## 8. Honest assessment of the live session

The live capture met its primary objective: full broadcast preserved end-to-end across two independent media (MPEG-TS + fragmented MP4). The pipeline did not meet its secondary objective of producing a clean live UI track. Five distinct defect classes interacted; mid-match firefighting cleared one (D-LIVE-1) and a code patch reduced but didn't eliminate another (D-LIVE-2). The remaining three were observed but not addressed live.

The recording is the load-bearing artifact going forward. The pipeline's defects are now reproducible on demand against a real broadcast substrate, which is a stronger evidence base than any synthetic fixture. The next session's work surface is well-defined.

Welcome.
