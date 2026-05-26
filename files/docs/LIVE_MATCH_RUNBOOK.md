# Live Match Runbook — Local Mac, Track 1 + Track 2

**Setup**: UGREEN HDMI capture card connected to Mac via USB-C. Mac runs entire pipeline locally — no server involvement. UI accessible at http://localhost:3000.

## Hardware wiring

```
Cricket broadcast source       UGREEN HDMI capture           Mac
(set-top box / cable box /  →  (USB-C dongle, appears   →   ffmpeg avfoundation
streaming device with HDMI    as video device 0 in        device index 0
out)                          avfoundation listings)
                              │
                              └─ Optional: HDMI passthrough
                                 to TV for monitoring
```

Source must NOT be HDCP-protected. Fire TV / Apple TV / Chromecast typically refuse to output to capture cards. Use:
- Cable box / DVR HDMI output (works)
- HDMI splitter that strips HDCP (~$15 on Amazon, model varies)
- Browser-based stream playing on a second Mac with HDMI mirror

Verify capture works before match:
```bash
ffmpeg -f avfoundation -list_devices true -i "" 2>&1 | grep -A 20 "AVFoundation video devices"
```
Look for the UGREEN device name. Note the index (usually 0).

Test capture (5-second probe):
```bash
ffmpeg -f avfoundation -framerate 30 -video_size 1920x1080 -pixel_format uyvy422 \
  -i "0:0" -t 5 /tmp/ugreen_test.mp4
```
If the file plays cleanly with a real frame from the broadcast, UGREEN is good.

## Pre-match checklist (T-30 minutes)

### 1. Find tonight's match ID + slug on cricbuzz

Open cricbuzz, navigate to tonight's match, copy the squad-page URL:
`https://www.cricbuzz.com/cricket-match-squads/<MATCH_ID>/<MATCH_SLUG>`

Note both for env vars below.

### 2. Verify clean working state

```bash
cd ~/Projects/SportsComm

# Pull latest changes
git pull origin derive-not-detect

# Sanity check tests
~/Projects/SportsComm/files/.venv/bin/python -m pytest files/tests/test_confidence_tracker.py -q
```

Tests should be all green (31 tests last count).

### 3. Clear stale state from prior runs

```bash
rm -f files/match_state_cache.json
rm -f logs/openscout-local_*.jsonl
rm -f /tmp/pipeline.log /tmp/stage_trace.jsonl /tmp/ffmpeg_sender.log /tmp/recorder.log /tmp/ui.log
rm -rf files/scripts/broadcast_mode_tuning/live_chunk_scout/live_*
rm -f files/logs/live_clips/clip_*.mp4 files/logs/live_clips/clip_*.json files/logs/live_clips/*_detections.json
```

### 4. Kill any leftover processes

```bash
pkill -f 'test_pipeline.py' 2>/dev/null
pkill -f 'ffmpeg.*avfoundation' 2>/dev/null
pkill -f 'ffmpeg.*udp://127.0.0.1' 2>/dev/null
pkill -f 'extract_live_clips_chunk' 2>/dev/null
sleep 1

# Verify ports are clear
lsof -i :3000 -i :8765 -i :8766 -i :9999 -i :9998 2>/dev/null
```

## Process layout (5 terminal tabs)

Use macOS Terminal split panes or iTerm2 windows. Each process runs in its own tab so logs stay separated.

### Terminal A — UI (Next.js)
```bash
cd ~/Projects/SportsComm/scorecard-ui
npm run dev
```
Wait ~5s for "Ready in Xms" message. UI available at http://localhost:3000.

### Terminal B — Local recorder (UDP 9998 → .ts archive)
```bash
mkdir -p ~/Recordings/qrackpot
SESSION_ID="live_$(date +%Y%m%d_%H%M%S)"
mkdir -p ~/Projects/SportsComm/files/logs/deliveries/$SESSION_ID
ffmpeg -y -hide_banner -loglevel warning -fflags +genpts -err_detect ignore_err \
  -i "udp://0.0.0.0:9998?fifo_size=10000000&overrun_nonfatal=1" \
  -c copy -f mpegts \
  ~/Projects/SportsComm/files/logs/deliveries/$SESSION_ID/match_$SESSION_ID.ts
```

This blocks. Will start writing .ts as soon as UDP packets arrive in Terminal D.

**Note the SESSION_ID** — Terminal C must use the same one.

### Terminal C — Pipeline (Track 1 + Track 2)
```bash
cd ~/Projects/SportsComm

# Match identity
export CRICBUZZ_MATCH_ID=<tonight_id>
export CRICBUZZ_MATCH_SLUG=<tonight_slug>

# Session — MUST MATCH terminal B's SESSION_ID
export BMF_SESSION_ID="<paste from terminal B>"

# Track 1 (always on)
export FRAME_SOURCE=udp
export FRAME_SOURCE_UDP_URL='udp://0.0.0.0:9999?fifo_size=10000000&buffer_size=2097152&overrun_nonfatal=1'
export FRAME_SOURCE_UDP_ALLOWED_DIMENSIONS='1920x1080,1280x720'
export FRAME_SOURCE_UDP_WATCHDOG_S=5.0
export FRAME_SOURCE_UDP_STARTUP_GRACE_S=20.0
export SCOUT_PROMPT_MODE=verbose
export PYTHONUNBUFFERED=1

# Track 2 (enable + slow cadence for TPM headroom)
export USE_OPEN_SCOUT=1
export OPENSCOUT_DECOUPLED=1
export OPENSCOUT_DECOUPLED_TARGET_INTERVAL_S=2.0
export SCOUT_RAW_DUMP=1

# Cold-start for true live match
export SKIP_PREMATCH_S=0

# Run
~/Projects/SportsComm/files/.venv/bin/python files/test_pipeline.py 2>&1 | tee /tmp/pipeline.log
```

Wait for the log to show:
```
[F0 TEST] INFO: SCRAPING SQUADS...
[F0 SQUAD] INFO: Fetching: https://www.cricbuzz.com/cricket-match-squads/<ID>/<SLUG>
[F0 TEST] INFO: Teams: ['Team A', 'Team B']
```

Pipeline is now ready and waiting for UDP frames on 9999.

### Terminal D — Mac UGREEN capture → dual UDP + local archive

This is the Mac sender. Modify `scripts/stream_to_server.sh` to point at localhost (since pipeline is on the same Mac):

```bash
# Quick override without editing the script:
SERVER_IP=127.0.0.1 DEVICE_INDEX=0 bash scripts/stream_to_server.sh
```

Or run the ffmpeg directly. The encode happens once and is fanned out to all three sinks via the `-f tee` muxer (the previous 3-output form mixed `-c:v libx264` with `-c copy` for the same input which silently mis-encodes the mp4):
```bash
TS=$(date +%Y%m%d_%H%M%S)
LOCAL_MP4=~/Recordings/qrackpot/match_${TS}.mp4
mkdir -p ~/Recordings/qrackpot

ffmpeg \
    -f avfoundation \
    -framerate 30 \
    -video_size 1920x1080 \
    -pixel_format uyvy422 \
    -i "0:0" \
    -c:v libx264 -preset veryfast -tune zerolatency -b:v 6M -maxrate 6M -bufsize 12M \
    -x264opts keyint=30:repeat-headers=1 -force_key_frames "expr:gte(t,n_forced*1)" \
    -c:a aac -b:a 128k -ac 2 \
    -map 0:v -map 0:a \
    -f tee \
    "[f=mpegts]udp://127.0.0.1:9999?pkt_size=1316|[f=mpegts]udp://127.0.0.1:9998?pkt_size=1316|[f=mp4:movflags=+frag_keyframe+empty_moov+default_base_moof:frag_duration=1000000]${LOCAL_MP4}"
```

One libx264 encode, three sinks via tee muxer:
- UDP 9999 → pipeline (Track 1 + OpenScout)
- UDP 9998 → recorder (Track 2 .ts archive)
- Local file → fragmented mp4 archive at `~/Recordings/qrackpot/match_<TS>.mp4` for future replay

**This is your archive.** Saved automatically. Don't Ctrl-C this terminal until match is complete or you'll lose end of archive.

### Terminal E — Track 2 clip extractor loop
```bash
cd ~/Projects/SportsComm
LIVE_CLIPS_INTERVAL_S=60 bash files/scripts/extract_live_clips_chunk.sh 2>&1 | tee /tmp/live-clips.log
```

This is the 60-second polling loop that builds clusters from scout_raw.jsonl + trims clips from the .ts archive. Will start producing detections JSON within first 60s, clips within ~90-120s of first delivery.

### Terminal F — Ball-by-ball UI logger
```bash
cd ~/Projects/SportsComm
BMF_SESSION_ID="<paste from terminal B>" \
~/Projects/SportsComm/files/.venv/bin/python files/scripts/ball_by_ball_logger.py \
  --ws ws://localhost:8765 \
  --out-dir files/logs/ball_log \
  2>&1 | tee /tmp/ball-log.log
```

Subscribes to the pipeline WS at 8765 and emits one row per state-signature change (innings, overs, score, wickets, striker, non, bowler, this_over). Produces:
- `files/logs/ball_log/ball_log_<SESSION>.tsv` — compare line-by-line vs Cricbuzz commentary post-match
- `files/logs/ball_log/ball_log_<SESSION>.jsonl` — same rows, structured

Auto-reconnects if pipeline restarts. Add `--keep-full` if you also want the raw WS payload snapshots saved (larger).

## Verify all pieces are talking (T-5 min before broadcast)

Quick health check:
```bash
# 1. UI is up
curl -s http://localhost:3000/ | head -5
# Should return HTML

# 2. Pipeline is ready (squad scrape complete)
grep "Teams: " /tmp/pipeline.log | tail -1

# 3. UDP listeners are bound
lsof -i :9999 -i :9998 2>/dev/null
# Should show python (pipeline) on 9999 and ffmpeg (recorder) on 9998

# 4. Mac sender ready (run a 5s probe)
ffmpeg -f avfoundation -framerate 30 -video_size 1920x1080 -pixel_format uyvy422 \
  -i "0:0" -t 5 -f null - 2>&1 | tail -3
# Should show "frame=" lines, not errors

# 5. scout_raw.jsonl is being written (Track 2 extractor reads this, not the .ts)
tail -f ~/Projects/SportsComm/files/logs/deliveries/$BMF_SESSION_ID/scout_raw.jsonl
# Ctrl-C after seeing ≥1 line; absence past T+90s means pipeline isn't dumping
```

## Browser tabs

Open these in your default browser (or pin to a dedicated browser window):
- http://localhost:3000/ — main scoreboard
- http://localhost:3000/deliveries — clip cards (Track 2 output)
- http://localhost:3000/logs — log tail viewer (auto-refresh 10s)

For watching the broadcast itself, the Mac display IS the broadcast (UGREEN captures whatever's coming in on HDMI). No video player needed on Mac. The UI tabs show derived state.

## At broadcast start

1. Confirm the broadcast is now on the HDMI source (you can watch on a TV via HDMI passthrough if available, or trust that the source device is on).
2. Verify Terminal D's ffmpeg is showing growing `frame=NNNN` output. If not, UGREEN isn't capturing.
3. Within 10-30s, Terminal C's pipeline should start logging `[F0 TEST]`, `[F1 TEST]`, etc. — these are the per-frame Vision SCOUT processing logs.
4. Within 60-90s, UI at http://localhost:3000/ should show batting_team + score.
5. Within 90-180s of the first delivery, http://localhost:3000/deliveries should show the first clip card.

## During the match

Watch the UI and Terminal C log tail. Tag in real-time any issues you see:
- UI shows wrong score → grab WS-probe + matching strip frame
- Wide tokens appearing in this_over when broadcast doesn't have one → note timestamp, will diagnose post-match
- Cluster builder producing duplicate clips → note anchor_t values

For each issue, save:
- Browser screenshot of the UI moment
- Timestamp from Terminal C log
- That's enough to diagnose next session

If pipeline crashes / hangs: tail `/tmp/pipeline.log`, look for traceback. Common causes:
- TPM 429 cascade → reduce OpenScout cadence (slow `OPENSCOUT_DECOUPLED_TARGET_INTERVAL_S` to 3.0+)
- UDPFrameSource ffprobe timeout → re-check ffmpeg sender in Terminal D
- Cricbuzz scrape failure → restart pipeline (script will re-fetch)

## At innings break

Pipeline should auto-detect innings 2 (target field + chase signature). Verify:
- Terminal C log: `[INNINGS-2-TRANSITION] target=NNN`
- UI updates to "Inn 2", shows "Need X from Y balls"
- batting_team flips to chasing team
- All four trackers reset (`[INNINGS-2-TRACKERS-RESET]`)

If false-trigger fires mid-innings-1 (known bug — `pending_target` from stats graphics), see HANDOFF.md ops cheat sheet for diagnosis.

## At match end

1. **Don't tear down immediately.** Let the recorder + sender drain for 60s after the final delivery so the .ts file closes cleanly.
2. Ctrl-C Terminal D (Mac sender) — this stops the ffmpeg encode and flushes the local mp4 archive.
3. `sleep 5` — let the last keyframe traverse UDP to recorder before EOF.
4. Ctrl-C Terminal B (recorder) — closes the .ts file.
5. Ctrl-C Terminal E (clip extractor) — stops the 60s poll loop.
6. Ctrl-C Terminal F (ball-by-ball logger) — flushes any buffered TSV rows.
7. Ctrl-C Terminal C (pipeline) — graceful shutdown.
8. Terminal A (UI) can stay up for post-match review.

## Archive locations (everything saved by default)

| Artifact | Location | Purpose |
|---|---|---|
| Mac local fragmented mp4 | `~/Recordings/qrackpot/match_<TS>.mp4` | Source recording for re-replay |
| Server-style .ts (local Mac) | `~/Projects/SportsComm/files/logs/deliveries/live_<TS>/match_live_<TS>.ts` | Track 2 archive, used by clip extractor |
| Scout raw sidecar | `~/Projects/SportsComm/files/logs/deliveries/live_<TS>/scout_raw.jsonl` | Per-frame Vision SCOUT output for replay analysis |
| OpenScout sidecar | `~/Projects/SportsComm/logs/openscout-live_<TS>.jsonl` | Per-frame action classification for replay analysis |
| Pipeline log | `/tmp/pipeline.log` | Stage trace + DETAIL lines + all state events |
| Live clips | `~/Projects/SportsComm/files/logs/live_clips/clip_anchor*.mp4` + `*.json` sidecars | Per-delivery video clips |
| Detection JSONs | `~/Projects/SportsComm/files/logs/live_clips/HHMM_detections.json` | Per-cycle cluster detections |
| Match state cache | `~/Projects/SportsComm/files/match_state_cache.json` | Hot-resume state snapshot |
| UI log | `/tmp/ui.log` | Next.js dev server output |
| Recorder log | `/tmp/recorder.log` (or Terminal B output) | ffmpeg recorder errors |
| Live-clips log | `/tmp/live-clips.log` | Cluster extraction cycle output |
| Ball-by-ball TSV | `~/Projects/SportsComm/files/logs/ball_log/ball_log_live_<TS>.tsv` | Per-state-change UI snapshot for Cricbuzz diff |
| Ball-by-ball JSONL | `~/Projects/SportsComm/files/logs/ball_log/ball_log_live_<TS>.jsonl` | Structured form of the TSV |
| Ball-log stdout | `/tmp/ball-log.log` | Logger reconnect + tail |

To preserve the run as a permanent reference (so /tmp logs don't get cleaned):
```bash
ARCHIVE_DIR=~/match-archives/match_$(date +%Y%m%d_%H%M%S)
mkdir -p $ARCHIVE_DIR
cp /tmp/pipeline.log /tmp/ui.log /tmp/live-clips.log /tmp/ball-log.log $ARCHIVE_DIR/ 2>/dev/null
cp -r ~/Projects/SportsComm/files/logs/deliveries/live_* $ARCHIVE_DIR/  # if any
cp -r ~/Projects/SportsComm/files/logs/live_clips $ARCHIVE_DIR/
cp -r ~/Projects/SportsComm/files/logs/ball_log $ARCHIVE_DIR/ 2>/dev/null
cp ~/Projects/SportsComm/files/match_state_cache.json $ARCHIVE_DIR/ 2>/dev/null
echo "Archive: $ARCHIVE_DIR"
```

## Restart procedures

### Pipeline crashed mid-match
1. Terminal C — Ctrl-C the dead python (or it's already exited).
2. Don't clear cache — hot-resume will pick up from `match_state_cache.json`.
3. Same env vars, restart: `python files/test_pipeline.py`.
4. Should re-converge within ~10s by reading the last few frames and matching to cached state.

### Recorder crashed
1. Terminal B — Ctrl-C dead ffmpeg.
2. Restart same command. Will create a NEW .ts file (won't overwrite, `-y` overwrites only the same filename).
3. Edit Terminal B's script to use a fresh `match_<TS>_part2.ts` to preserve part 1.

### Mac sender (UGREEN ffmpeg) crashed
This is the worst case — broadcast goes uncaptured until restarted.
1. Terminal D — Ctrl-C dead ffmpeg.
2. Restart same command. Pipeline will see a brief UDP gap then resume.
3. Local archive will have a small gap (the time between crash and restart).

### UI not loading
1. Terminal A — Ctrl-C, restart `npm run dev`.
2. Refresh browser. State will re-load from pipeline WS.

## Post-match Cricbuzz diff

The TSV from Terminal F is row-aligned to UI-visible state transitions. Diff against Cricbuzz commentary:
```bash
TSV=~/Projects/SportsComm/files/logs/ball_log/ball_log_${BMF_SESSION_ID}.tsv
column -t -s $'\t' "$TSV" | less -S
```

For each row, the columns are: `ts | inn | overs | score | wkts | striker | non | bowler | this_over | last_event`. Pull Cricbuzz commentary for the same match (`files/scripts/ingest_cricbuzz_ground_truth.py` is the GT ingester) and align by `overs`. Issues to flag for next iteration:
- Pipeline `overs` value mismatched against Cricbuzz over.ball
- `striker` swap not reflecting actual on-strike batter
- `current_bowler` lagging at over boundaries (known WS-R limitation: between-overs clear)
- `this_over` token diverging from Cricbuzz (Bug 5 wide fabrication; Bug 4 `?` placeholder)
- Score backward jumps (state corruption)

## Post-match offline review

To replay the recording through pipeline (no live capture needed):
```bash
ffmpeg -re -i ~/Recordings/qrackpot/match_<TS>.mp4 \
  -c:v libx264 -preset veryfast -tune zerolatency -b:v 6M \
  -c:a aac -b:a 128k \
  -map 0 -f mpegts "udp://127.0.0.1:9999?pkt_size=1316" \
  -map 0 -f mpegts "udp://127.0.0.1:9998?pkt_size=1316"
```

This replays the saved mp4 in real-time. Pipeline runs identically. You can iterate on bug fixes against the same broadcast.

Or directly:
```bash
export FRAME_SOURCE=file
export FRAME_SOURCE_FILE=~/Recordings/qrackpot/match_<TS>.mp4
# Skip the UDP terminal setup entirely
python files/test_pipeline.py
```

## Known imperfections to expect tonight

From HANDOFF.md "Pending bugs":
- Bug 6 root cause (bowler tracker doesn't unlock cleanly at strategic timeouts) — bowler stats may drift during 5-min break between overs
- Bug 5 (wide fabrication) — UI may show `Wd` tokens that aren't real
- Bug 4 (this_over `?` placeholder) — cosmetic, self-recovers
- Bug 8 (striker green-dot inversion) — cosmetic, score logic correct
- ConfidenceTracker observation starvation for striker/non_striker — if SCOUT VLM output omits batter rows, trackers may stay TENTATIVE. UI shows names from squad-resolution but no LOCKED transition.

None of these corrupt the core state (score, wickets, overs, team identity). If they happen, capture screenshots + log timestamps, fix post-match.

## Emergency abort

If something is fundamentally broken (UI showing wrong team, score going backwards, false innings change, etc.) and can't be diagnosed mid-match:

1. Stop Terminal C (pipeline). UI will freeze on last good state.
2. Terminals B + D + E continue — your recording is still being saved.
3. You can investigate post-match. The recording is the authoritative source.

The match is being captured. Even if the pipeline misbehaves, the broadcast is preserved.

## Quick reference: command summary

```bash
# Once, before match:
cd ~/Projects/SportsComm
git pull origin derive-not-detect
rm -f files/match_state_cache.json logs/openscout-local_*.jsonl /tmp/pipeline.log

# Terminal A (UI):
cd scorecard-ui && npm run dev

# Terminal B (recorder — pick a SESSION_ID):
SESSION_ID="live_$(date +%Y%m%d_%H%M%S)"
echo "SESSION_ID=$SESSION_ID"  # ← copy this
mkdir -p ~/Projects/SportsComm/files/logs/deliveries/$SESSION_ID
ffmpeg -y -hide_banner -loglevel warning -fflags +genpts -err_detect ignore_err \
  -i "udp://0.0.0.0:9998?fifo_size=10000000&overrun_nonfatal=1" \
  -c copy -f mpegts ~/Projects/SportsComm/files/logs/deliveries/$SESSION_ID/match_$SESSION_ID.ts

# Terminal C (pipeline — paste SESSION_ID from terminal B):
cd ~/Projects/SportsComm
export CRICBUZZ_MATCH_ID=<id>  CRICBUZZ_MATCH_SLUG=<slug>
export BMF_SESSION_ID="<paste>"
export FRAME_SOURCE=udp FRAME_SOURCE_UDP_URL='udp://0.0.0.0:9999?fifo_size=10000000&buffer_size=2097152&overrun_nonfatal=1'
export FRAME_SOURCE_UDP_ALLOWED_DIMENSIONS='1920x1080,1280x720' SCOUT_PROMPT_MODE=verbose
export USE_OPEN_SCOUT=1 OPENSCOUT_DECOUPLED=1 OPENSCOUT_DECOUPLED_TARGET_INTERVAL_S=2.0
export SCOUT_RAW_DUMP=1 PYTHONUNBUFFERED=1 SKIP_PREMATCH_S=0
~/Projects/SportsComm/files/.venv/bin/python files/test_pipeline.py 2>&1 | tee /tmp/pipeline.log

# Terminal D (Mac sender):
TS=$(date +%Y%m%d_%H%M%S)
ffmpeg -f avfoundation -framerate 30 -video_size 1920x1080 -pixel_format uyvy422 -i "0:0" \
  -c:v libx264 -preset veryfast -tune zerolatency -b:v 6M -maxrate 6M -bufsize 12M \
  -x264opts keyint=30:repeat-headers=1 -c:a aac -b:a 128k -ac 2 \
  -map 0 -f mpegts "udp://127.0.0.1:9999?pkt_size=1316" \
  -map 0 -f mpegts "udp://127.0.0.1:9998?pkt_size=1316" \
  -map 0 -c copy -movflags +frag_keyframe+empty_moov+default_base_moof -frag_duration 1000000 \
  ~/Recordings/qrackpot/match_${TS}.mp4

# Terminal E (clip extractor):
cd ~/Projects/SportsComm
LIVE_CLIPS_INTERVAL_S=60 bash files/scripts/extract_live_clips_chunk.sh

# Terminal F (ball-by-ball logger — paste same SESSION_ID):
cd ~/Projects/SportsComm
BMF_SESSION_ID="<paste>" ~/Projects/SportsComm/files/.venv/bin/python \
  files/scripts/ball_by_ball_logger.py --ws ws://localhost:8765 \
  --out-dir files/logs/ball_log 2>&1 | tee /tmp/ball-log.log

# Browser:
open http://localhost:3000/
open http://localhost:3000/deliveries
open http://localhost:3000/logs
```
