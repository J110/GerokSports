# Live match runbook

## Pre-flight (run 5 min before pre-match)

1. Verify env vars present:
   - `GROQ_API_KEY` (Scout/Scorer/20b)
   - `GEMINI_API_KEY` (Extract)
   - `CRICBUZZ_MATCH_ID=<TODO_MATCH_ID>` (set per match)

2. Free old recorders/pipelines:

   ```
   pkill -INT -f "test_pipeline.py" 2>/dev/null
   pkill -INT -f "record_live_match.py" 2>/dev/null
   sleep 5
   ```

3. Disk space check: `df -h | head -3` (need >20 GB free for a 5h recording).

## Launch

Terminal 1 — pipeline + recorder:

```
cd /Users/anmolmohan/Projects/SportsComm
./files/scripts/start_live_match.sh
```

The launcher prints a banner with stable paths:
- `files/logs/pipeline-live.log`
- `files/logs/trace/live.jsonl`
- `files/logs/deliveries/<BMF_SESSION_ID>/scout_raw.jsonl`

Terminal 2 — audit dumper (writes a chunk every 30 min):

```
cd /Users/anmolmohan/Projects/SportsComm
chmod +x files/scripts/audit_chunk_dumper.sh
./files/scripts/audit_chunk_dumper.sh > files/logs/audit_chunks/.dumper.log 2>&1 &
echo $! > files/logs/audit_chunks/.pid
```

(The script also writes its own PID to `.pid` on startup; both forms agree.)

Terminal 3 — delivery watcher (only if Item 4 landed):

```
cd /Users/anmolmohan/Projects/SportsComm
mkdir -p files/logs/live_clips
python files/scripts/realtime_delivery_watcher.py &
echo $! > files/logs/live_clips/.pid
```

## During match — every 30 min

1. Audit chunk lands at `files/logs/audit_chunks/<HHMM>_audit.txt`.
2. Hand the chunk to Zed: "audit chunk `<HHMM>`".
3. Zed surfaces issues. For each: confirm root cause via reading the cited file:line.
4. If ROOT CAUSE CONFIRMED:
   - Make the edit
   - Run any unit test that covers the fix
   - Restart pipeline only (recorder keeps writing the same mp4):

     ```
     pkill -INT -f "test_pipeline.py"
     sleep 10   # let trace flush
     ./files/scripts/start_live_match.sh   # state re-bootstraps from scoreboard
     ```

## Track 2 — delivery review

- Live clips appear at `files/logs/live_clips/o<over>_b<ball>_<HHMMSS>.mp4`.
- Open in QuickTime to review release/phantom.
- If a clip is missing release or has a phantom: note timestamp, fix
  `files/scripts/broadcast_mode_tuning/delivery_classifier.py` or
  `signal_extraction.py`, then restart watcher only (do NOT restart pipeline):

  ```
  kill -INT $(cat files/logs/live_clips/.pid)
  python files/scripts/realtime_delivery_watcher.py &
  echo $! > files/logs/live_clips/.pid
  ```

## Track 2 (Path A) — chunk extractor (every 30 min)

If `realtime_delivery_watcher.py` is not running, the chunk extractor
provides equivalent output on a 30-min cadence. It re-uses the offline
cluster/boundary code against accumulated `scout_raw.jsonl`.

Start (Terminal 4):

```
cd /Users/anmolmohan/Projects/SportsComm
chmod +x files/scripts/extract_live_clips_chunk.sh
# SKIP_PREMATCH_S (default 400s): drop clusters whose anchor_t lands
# in the pre-match window. Lower for short pre-match broadcasts.
SKIP_PREMATCH_S=400 ./files/scripts/extract_live_clips_chunk.sh > files/logs/live_clips/.extractor.log 2>&1 &
echo $! > files/logs/live_clips/.pid
```

Outputs each cycle:
- `files/logs/live_clips/<HHMM>_detections.json` — anchor_t,
  clip_start, clip_end per detected delivery (always written).
- `files/logs/live_clips/clip_anchor<NNNN>.mp4` — best-effort ffmpeg
  trim, only when the recorded mp4 has settled bytes >=60s past the
  cluster end. Re-runs are idempotent (filenames keyed on rounded
  anchor_t).
- `files/logs/live_clips/clip_anchor<NNNN>.json` — per-clip metadata.

Sidecar staging (auto-managed): `files/scripts/broadcast_mode_tuning/live_chunk_scout/<SESSION_ID>/`
and detections per cycle: `files/scripts/broadcast_mode_tuning/live_chunk_predicted/`.

Stop:

```
kill -INT $(cat files/logs/live_clips/.pid)
```

## Kill procedure

```
kill -INT $(cat files/logs/audit_chunks/.pid) 2>/dev/null
kill -INT $(cat files/logs/live_clips/.pid) 2>/dev/null
pkill -INT -f "test_pipeline.py"
pkill -INT -f "record_live_match.py"
# wait 15s for moov flush before pkill -KILL
sleep 15
```

## Useful greps mid-match

```
tail -f files/logs/pipeline-live.log
grep -c WS-PROMOTE files/logs/pipeline-live.log
grep "STATE: " files/logs/pipeline-live.log | tail -5
tail -f files/logs/trace/live.jsonl
```
