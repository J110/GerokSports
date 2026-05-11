# Tonight's Match — Handoff (2026-05-11, PBKS vs DC, 7:30 PM IST)

## What we're shipping tonight

End-to-end live cricket broadcast analysis pipeline running on a GCP server,
fed by a Mac capture card streaming UDP MPEG-TS over the internet, with:

1. **Track 1**: real-time scoreboard state derivation (score, wickets, overs,
   batters, bowler, partnership, FOW) → UI at https://qrackpot.com
2. **Track 2 (archive)**: per-delivery video clip extraction → UI at
   https://qrackpot.com/deliveries
3. **Track 2 (inference) — design locked, not yet built**: vision-model
   attribute extraction + commentary generation per delivery. See
   `files/docs/investigations/track2_realtime_inference_design.md`.

## Architecture

```
Mac (capture card + ffmpeg)
    ├── udp://server:9999  → pipeline.service (cv2 + OpenScout → ws://8765, 8766)
    └── udp://server:9998  → recorder.service (ffmpeg → fragmented mp4 archive)

Server (qrackpot-prod-1, asia-south1-a, GCP):
    pipeline.service       — Track 1 state derivation
    recorder.service       — ffmpeg UDP listener, writes match_<sid>.mp4
    live-clips.service     — 60s poll of scout_raw + cluster builder + ffmpeg trim
    ui.service             — Next.js 16 (port 3000)
    caddy                  — reverse proxy + static /clips, /server-logs, /scout
```

## Pipeline session id

Pipeline reads `BMF_SESSION_ID` from `/etc/sportscomm/pipeline.env`. CI sets
it to `live_<UTC YYYYMMDD>` so all 3 services share one session dir:
`/mnt/data/sportscomm/files/logs/deliveries/${BMF_SESSION_ID}/`.

Earlier today `test_pipeline.py` was overriding this with a fresh uuid every
restart — patched in last commit so recorder.service mp4 and pipeline's
scout_raw.jsonl + `logs/openscout-<sid>.jsonl` all land under the same id.

## State cache gotcha

`files/match_state_cache.json` is hot-resume cache. Identity gate
(test_pipeline.py ~line 7053) requires `cached_match_id == current_match_id`
AND `cached_session_id != current_session_id`. The cache without a `match_id`
field has been observed to leak stale state. **Always delete the cache file
when switching matches.**

## Pre-match checklist (run each item until green)

```bash
# 1. CI deploy: GitHub Actions → "Deploy to qrackpot-prod-1" →
#    workflow_dispatch → mode=live. Wait for green.

# 2. Server: clear stale cache + restart services + verify sid
gcloud compute ssh qrackpot-prod-1 --zone=asia-south1-a --tunnel-through-iap \
  --command="sudo rm -f /mnt/data/sportscomm/files/match_state_cache.json; \
             sudo rm -f /mnt/data/sportscomm/logs/openscout-*.jsonl; \
             sudo truncate -s 0 /var/log/sportscomm/*.log; \
             sudo systemctl restart pipeline.service recorder.service live-clips.service; \
             sleep 20; \
             for s in pipeline recorder live-clips; do echo \"\$s: \$(sudo systemctl is-active \$s.service)\"; done; \
             sudo grep -E 'session_id=|Teams:|CACHE' /var/log/sportscomm/pipeline.log | head -10"

# Expected: all 3 active, session_id=live_<UTC date>, Teams: ['Punjab Kings', 'Delhi Capitals'],
# [CACHE] No cached state found — starting fresh

# 3. Open UI tabs:
#    https://qrackpot.com/
#    https://qrackpot.com/deliveries
#    https://qrackpot.com/logs
#    https://qrackpot.com/server-logs/   (raw log file browser)

# 4. End-to-end dry run with the 37-min recording (BEFORE the live match)
cd ~/Projects/SportsComm
bash scripts/stream_to_server_test.sh files/logs/deliveries/6ff41b76/match_6ff41b76.mp4
# Run for 5 min, then Ctrl-C.
# Expect: pipeline.log shows F1 F2 F3..., recorder.log shows mp4 growing,
# /deliveries page shows playable clips within ~90s.

# 5. At 7:30 PM, capture card live stream
bash scripts/stream_to_server.sh
# Dual-output: UDP 9999 (pipeline) + UDP 9998 (recorder) + local archive.
```

## What changed today (key commits)

- 469f84c — `_handle_warm` defensive numeric coercion (TypeError fix)
- 0474fb4 — Phase 1B SRT live ingest setup
- (replaced) — SRT switched to UDP MPEG-TS (stock ffmpeg compat)
- 23dd4c2 — `FRAME_SOURCE_FILE` env var name fix
- 786ae32 — `scoreboard.update_bowler` str→int hotfix
- 8adc04f — Caddyfile log blocks removed; `caddy validate` before reload
- Track 2 server-side recording + live-clips service added
- BMF_SESSION_ID honored in test_pipeline.py (latest)

## Files to know

| Path | Purpose |
|---|---|
| `files/test_pipeline.py` | Main pipeline entrypoint (~7000 lines) |
| `files/score_manager.py` | Score state machine, `_handle_warm` etc. |
| `files/scripts/extract_live_clips_chunk.sh` | Track 2 chunk extractor (60s loop) |
| `files/scripts/stream_to_server.sh` | Mac UGREEN capture → dual UDP |
| `files/scripts/stream_to_server_test.sh` | Mac mp4 replay → UDP |
| `scripts/grab_logs.sh` | Mac-side one-shot log bundle to ~/qrackpot-snapshots/ |
| `deploy/Caddyfile` | reverse proxy + /clips /server-logs /scout |
| `deploy/deploy.sh` | Server-side deploy script (idempotent, self-healing) |
| `deploy/systemd/*.service` | pipeline, recorder, live-clips, ui |
| `deploy/pipeline.env.example` | Env template (real one at `/etc/sportscomm/pipeline.env`, 0600) |
| `.github/workflows/deploy.yml` | CI: WIF auth → IAP SSH → git reset --hard origin → deploy.sh |
| `scorecard-ui/app/page.tsx` | Main UI (live, scorecard, field, comm, clips, logs) |
| `scorecard-ui/app/deliveries/page.tsx` | Track 2 clip verification UI |
| `scorecard-ui/app/logs/page.tsx` | Live log tail UI with filter + copy |
| `scorecard-ui/app/api/deliveries/route.ts` | Clips listing endpoint |
| `scorecard-ui/app/api/logs/route.ts` | Log tail endpoint |
| `files/docs/investigations/track2_realtime_inference_design.md` | Locked design for vision-attrs + commentary workers |

## Operations runbook (when something breaks during the match)

1. **UI showing stale data** — delete cache file (`match_state_cache.json`),
   restart pipeline.service. Confirm `[CACHE] No cached state found` in log.

2. **Pipeline crash-loops** — `sudo journalctl -u pipeline.service -n 80`,
   look for traceback. Common past causes: TypeError float-vs-str
   (already patched), missing env var, cricbuzz scrape failure, lxml missing.

3. **No clips on /deliveries** — check live-clips.log for "no session dir"
   or "session=X has no openscout-X.jsonl yet". Means recorder mp4 dir and
   pipeline session id are not the same — verify `BMF_SESSION_ID` matches
   in `/etc/sportscomm/pipeline.env` and shows in `[SESSION-CONFIG]`
   log line. After today's fix this should be stable.

4. **UDP stream from Mac not landing** — check firewall rules
   `qrackpot-udp-9999` and `qrackpot-udp-9998` exist + VM has tag
   `qrackpot-prod`. `gcloud compute instances describe qrackpot-prod-1
   --zone=asia-south1-a --format='value(tags.items)'`.

5. **Caddy stuck reloading** — `sudo systemctl reset-failed caddy &&
   sudo systemctl restart caddy`. Already self-healed in deploy.sh.

6. **Pull logs offline** — `bash scripts/grab_logs.sh` writes tarball to
   `~/qrackpot-snapshots/snapshot_<TS>.tar.gz`.

## Pending after tonight

- Cluster-close in-process event hook in pipeline.service (task #42)
- delivery_attrs_worker — vision API per-delivery attributes (task #43)
- commentary_worker — LLM commentary per delivery (task #44)
- D8 wickets side-channel injection (task #11, latent)
- Frame-level LLM zoom on borderline cases (task #14, future)

## Style

See `CLAUDE.md` for response style rules (no preamble, diff-only code, etc).
Treat me as a senior engineer. No basic explanations. Push back when wrong.

## Sub-page entry points

- /             main scorecard
- /deliveries   Track 2 clip verification (auto-refresh 30s)
- /logs         log tail viewer (auto-refresh 10s, with filter + copy)
- /clips/*      raw clip mp4 files (Caddy file_server)
- /server-logs/ raw server log files (Caddy file_server)
- /scout/*      raw scout_raw.jsonl per session (Caddy file_server)
