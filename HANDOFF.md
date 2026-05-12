# Handoff — 2026-05-12 (post-PBKS-vs-DC postmortem)

Last night's live match was a disaster — neither Track 1 (state) nor Track 2
(clips/deliveries) produced usable output. Today's plan: **perfect the
real-time system on local Mac first, then port to server**. No terminal
work by the human today; all edits + git + tests + ssh through Cursor /
Claude Code.

## Postmortem — what broke

### Track 1 (main pipeline)

1. **Vision prompt parroting** — `files/eyes/vision.py:218-221` example line
   had literal numbers `null 47-3 (null) | Striker 20(18) | NonStriker 5(7)
   | BowlerName 1-15 (3.2)`. Groq llama-4-scout copied them verbatim when
   it couldn't read the actual scoreboard, substituting ROHIT/JADEJA/BUMRAH
   from training data. Seeded state with phantom 47-3 on first read.
   **Fixed `fed5b5a`** — replaced with `<angle_bracket>` placeholders +
   null-emit fallback.

2. **Foreign-match recaps leaked into state** — extractor (`agent.py:27-29`)
   correctly nulled `batting_team_visible` for non-match teams (MI/RCB),
   but still extracted their score/wickets/overs into the main fields.
   `filter_strip_wrong_team` had `if not visible_team: return False` so
   null-team reads bypassed validation; monotonic-up guards then accepted
   MI 110-4 as PBKS state. **Fixed `b289782`** — reject when visible_team
   is null OR not in our_teams; **`562db58`** — pop ALL state fields on
   team mismatch, not just batters.

3. **No native UDP frame source** — `make_frame_source()` only supports
   `capture_card`, `window`, `file`. UDP was hacked via
   `FRAME_SOURCE_FILE=udp://0.0.0.0:9999` through `FileFrameSource →
   cv2.VideoCapture(url)`. No reconnect logic. cv2 kept losing SPS/PPS and
   overrunning the UDP recv buffer. **Worked around** with
   `?fifo_size=10000000&buffer_size=2097152&overrun_nonfatal=1` + Mac-side
   `-x264opts keyint=30:repeat-headers=1 -force_key_frames` so every
   keyframe carries SPS/PPS. **Permanent fix pending**: dedicated
   `UDPFrameSource` class.

### Track 2 (OpenScout / clip extraction)

1. **Null `frame_idx` crashed sidecar materialization** — `rec.get(
   "frame_idx", line_no)` returned `None` when key present-but-null, then
   `f"{None:06d}"` raised TypeError. Every live-clips cycle logged
   "sidecar materialization failed — skip cycle". **Fixed `3440673`**.

2. **Cluster builder returned n=0 in real time** — OPEN. Algorithm works
   offline against Scout output (verified in past runs), so this is a
   wiring issue — likely time alignment, the sidecar/openscout pair we
   feed it, or content density not crossing thresholds in real time. NOT
   changing the algorithm. Needs design-level diagnosis with the post-
   mortem session bundle.

### Track 2 recorder

* `recorder.service` ExecStart had no `-y` → ffmpeg crash-looped on
  file-overwrite prompt. Fragmented mp4 also produced no moov atom in
  live conditions → ffprobe + clip trim both failed.
  **Fixed `d1e64a7`** — `-y` + container `.ts` mpegts.
  **`96f3182`** — live-clips glob now accepts `.ts`.
  **`eb30eb4`** — `/deliveries` page + API route shipped (was untracked
  in git, hence 404).

## Today's local-first plan

**Phase 1**: Pull the post-mortem bundle from server to
`~/qrackpot-postmortem/` (logs, scout sidecars, deliveries session dir
with `.ts` recording, match_state_cache, live_clips outputs). This is the
ground truth for "what real-time actually saw last night".

**Phase 2**: Reproduce the failure locally — replay the `.ts` recording
through the full pipeline + chunk extractor on Mac, confirm we see the
same n=0 cluster output. This validates the bundle is sufficient.

**Phase 3**: Diagnose cluster builder n=0. Compare:
- Offline `extract_live_clips_chunk.sh` output against the same sidecar
  produced from the live `.ts` (should produce >0 clusters).
- Live sidecar files from last night vs. sidecar regenerated from the
  scout_raw.jsonl now.
Pinpoint where the wiring diverges. Likely candidates:
- `f_{idx:06d}_t={t:06.1f}.txt` filename pattern — uses `rel_t` derived
  from `ts - first_ts`. If `first_ts` was pulled from a frame mid-stream
  (cv2 reconnect, recorder gap), all rel_t values shift and the cluster
  builder's `gap_max=3` time-windowing fires wrong.
- `frame_class != "action"` filter — null vs absent field handling.
- Cluster builder gap thresholds vs. actual live frame cadence (Groq
  inference latency may be > gap_max during heavy load).

**Phase 4**: Implement `UDPFrameSource` class in `files/eyes/` —
proper UDP MPEG-TS ingest with reconnect, SPS/PPS recovery, frame-drop
metrics. Replaces the cv2.VideoCapture(url) hack. Add to
`make_frame_source()` selector.

**Phase 5**: Local end-to-end validation — Mac-side stream
`scripts/stream_to_server_test.sh` modified to point at `localhost:9999`,
run pipeline locally with the new UDPFrameSource, watch /deliveries
populate within 90s.

**Phase 6**: Port to server. CI deploy. Validate one more time before
next match.

## What's deployed on server (as of 2026-05-12 morning)

Last night's commits are live. Services running:

| Service | Purpose |
|---|---|
| pipeline.service | Track 1 (cv2 UDP hack on port 9999) |
| recorder.service | ffmpeg UDP→.ts mpegts on port 9998 (no -y bug fixed `d1e64a7`) |
| live-clips.service | 60s poll, sidecar materialization (frame_idx null bug fixed `3440673`) |
| ui.service | Next.js 16, /deliveries route now committed (`eb30eb4`) |
| caddy | reverse proxy + static /clips /server-logs /scout |

## Post-mortem bundle layout (after Phase 1)

```
~/qrackpot-postmortem/
├── logs/                                  # /var/log/sportscomm/*
│   ├── pipeline.log
│   ├── pipeline-err.log
│   ├── recorder.log
│   ├── recorder-err.log
│   ├── live-clips.log
│   ├── live-clips-err.log
│   ├── ui.log
│   └── ui-err.log
├── deliveries/<sid>/
│   ├── scout_raw.jsonl
│   ├── match_<sid>.ts                     # ← the recording (multi-GB)
│   └── scout_chunk_*.jsonl (if any)
├── clips/                                 # /mnt/data/sportscomm/files/logs/live_clips/
│   ├── HHMM_detections.json
│   └── clip_anchor*.mp4 + .json sidecars
├── openscout-*.jsonl                      # /mnt/data/sportscomm/logs/openscout-*.jsonl
├── match_state_cache.json
└── pipeline.env.masked
```

## Acceptance criteria — when "today's plan" is done

1. Replay `match_<sid>.ts` locally → pipeline derives PBKS vs DC state
   that matches the actual broadcast timeline (spot-check at 3 random
   over boundaries).
2. Same replay → live-clips emits ≥1 clip per actual delivery in the
   replay window.
3. `UDPFrameSource` lands in `files/eyes/` and `make_frame_source()`,
   replacing the cv2 hack. Pipeline boots with `FRAME_SOURCE=udp` and
   reconnects across stream interruptions.
4. End-to-end local: Mac ffmpeg → localhost UDP → pipeline → UI shows
   state, /deliveries shows playable clips.
5. Same code path running on server, validated with a short ffmpeg
   replay test from Mac before next match.

## Pending after today (carried forward)

- Cluster-close in-process event hook in pipeline.service (task #42)
- delivery_attrs_worker (task #43)
- commentary_worker (task #44)
- D8 wickets side-channel injection (task #11)
- Frame-level LLM zoom on borderline cases (task #14)

## Operations cheat sheet

All `gcloud compute ssh qrackpot-prod-1 --zone=asia-south1-a
--tunnel-through-iap --command="..."` — Cursor runs these directly.

Pre-match reset:

```bash
sudo rm -f /mnt/data/sportscomm/files/match_state_cache.json
sudo rm -f /mnt/data/sportscomm/logs/openscout-*.jsonl
sudo truncate -s 0 /var/log/sportscomm/*.log
sudo systemctl restart pipeline.service recorder.service live-clips.service
```

State check:

```bash
for s in pipeline recorder live-clips; do
  echo "$s: $(sudo systemctl is-active $s.service)"
done
sudo grep -E 'session_id=|Teams:|CACHE' /var/log/sportscomm/pipeline.log | head
```

Pull bundle to local (used today, Phase 1):

```bash
mkdir -p ~/qrackpot-postmortem/{logs,deliveries,clips}
gcloud compute scp --zone=asia-south1-a --tunnel-through-iap --recurse \
  qrackpot-prod-1:/var/log/sportscomm/ ~/qrackpot-postmortem/logs/
# session id from `ls /mnt/data/sportscomm/files/logs/deliveries/`
SID=live_20260511
gcloud compute scp --zone=asia-south1-a --tunnel-through-iap --recurse \
  "qrackpot-prod-1:/mnt/data/sportscomm/files/logs/deliveries/${SID}" \
  ~/qrackpot-postmortem/deliveries/
gcloud compute scp --zone=asia-south1-a --tunnel-through-iap \
  "qrackpot-prod-1:/mnt/data/sportscomm/logs/openscout-*.jsonl" \
  ~/qrackpot-postmortem/
gcloud compute scp --zone=asia-south1-a --tunnel-through-iap --recurse \
  qrackpot-prod-1:/mnt/data/sportscomm/files/logs/live_clips/ \
  ~/qrackpot-postmortem/clips/
```

## Style

See `CLAUDE.md`. No preamble, diff-only code, treat as senior engineer.
