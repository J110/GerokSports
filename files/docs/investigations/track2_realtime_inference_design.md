# Track 2 Real-Time Inference — Design Memo

**Date**: 2026-05-11
**Status**: Locked. Tonight's match validates delivery windows only.
**Goal**: Per-delivery attribute extraction + commentary generation within
the between-deliveries budget (~30-45s in T20).

## 1. Two-path split

The archive path (mp4 clips) and the inference path (frame attributes +
commentary) have different SLAs. We split them so the inference path
never waits on mp4 work.

```
Mac UDP ──┬──→ pipeline.service (cv2 + OpenScout)
          │       │
          │       └─ on cluster_close → emit event
          │
          └──→ recorder.service (match_*.mp4 archive)

[event] ──→ delivery_attrs_worker.service     [SLA: T+5-15s after delivery]
              ├─ reads cluster frames from scout_raw.jsonl
              ├─ vision API (Gemini / GPT-4V / Llama-3.2-vision)
              ├─ writes attrs JSON
              └─ ws broadcast: "delivery_attrs"

[attrs_ready] ──→ commentary_worker.service   [SLA: T+15-25s]
              ├─ attrs + match context (over, partnership, FOW, recent balls)
              ├─ commentary LLM (Groq llama-3.3-70b or similar)
              └─ ws broadcast: "delivery_commentary"

[archive, parallel]
live-clips.service ──→ trimmed mp4 + detections JSON (60s cadence)
                       For: human review, social clips, post-match.
                       NOT in the inference path.
```

## 2. Cluster-close event mechanism

`pipeline.service` already runs `delivery_classifier` per-frame via the
existing scoreboard processing loop. The chunk script duplicates this
work on a 60s poll. Replace the duplication with an in-process hook:

- When `build_clusters` closes a cluster (last frame's age > gap_max),
  pipeline.service writes a marker file:
  `files/logs/deliveries/${BMF_SESSION_ID}/cluster_events/${anchor_t}.json`
  containing `{anchor_t, cluster_start_t, cluster_end_t, frame_paths[]}`.

- `delivery_attrs_worker.service` watches that dir with inotifywait, picks
  up new event files, dispatches to vision API, writes
  `files/logs/deliveries/${SID}/attrs/${anchor_t}.json`, broadcasts on the
  comm-ws channel.

- `commentary_worker.service` watches `attrs/` dir, dispatches to the
  commentary LLM with context, broadcasts on comm-ws.

Why files-on-disk: simple, language-agnostic, debuggable. We can swap to
NATS/Redis pub-sub later if throughput becomes an issue (T20 is 240 balls
per match = ~1 event every 90s on average — file-watching is plenty).

## 3. Attribute schema (target 13-20 fields)

Vision model output, per delivery:

| Group | Fields |
|---|---|
| Delivery | length, line, angle, bounce, swing, seam, speed_kph |
| Shot | shot_name, shot_intent, contact_point, elevation |
| Outcome | runs, direction_zone, side, hit_region, fielders_involved |
| Misc | free_hit, no_ball_called, drs_call, batter_position |

Frames passed to the vision model: anchor frame ± 1.5s, sampled at
2 fps → 6-8 frames per delivery. Total prompt: ~7 images + match context.

## 4. Context provided to commentary LLM

- Delivery attrs JSON (just written)
- Last 6 balls in this over (from pipeline state)
- Batter career + format context (from cricbuzz scrape)
- Partnership, run rate, required rate, FOW
- Bowler over progression
- Match phase (powerplay, middle, death)
- Recent commentary lines (so we don't repeat ourselves)

## 5. Service placeholders

`deploy/systemd/delivery_attrs_worker.service` and
`deploy/systemd/commentary_worker.service` exist with `Type=oneshot`
+ `Restart=no` for now. They are **not enabled** by deploy.sh. Operator
flips them on once the worker scripts land.

## 6. Tonight's validation scope

Validate **delivery windows only** — does live-clips.service correctly
identify every delivery and trim a clip with the right boundaries?

Tools:
- `files/logs/live_clips/HHMM_detections.json` — anchor + clip start/end per cluster
- `files/logs/live_clips/clip_anchor*.mp4` — trimmed clip files
- Compare against the broadcast: are we catching every legal delivery?
  Are clip boundaries clean (no mid-shot cuts, no missing follow-through)?

If yes → next session builds the attrs worker.
If no → fix the cluster builder before any worker work.

## 7. Out of scope tonight

- Attribute extraction (no vision API calls yet)
- Commentary generation (no LLM dispatch yet)
- Web search for analysis frames
- Accumulating-data analysis frames
- Cluster-close in-process hook (still using 60s poll script for now)

## 8. Real-time-first compliance

This design satisfies design principle #37: every step runs during the
match, in time for between-deliveries presentation. No offline-only
solutions. The mp4 clip archive is parallel, not on the critical path.
