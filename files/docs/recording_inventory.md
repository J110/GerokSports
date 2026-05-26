# Recording Inventory

Tier 1 live-match recordings for the 2026-05-24 KKR vs DC session:

| File | Status |
|---|---|
| `files/logs/deliveries/live_20260524_185913/match_live_20260524_185913.ts` | Canonical full-match source. Approx. 4:24:19, 11-12GB, H.264/AAC. Use this for WS-LIVE replay attribution. |
| `files/logs/deliveries/live_20260524_185913/match_live_20260524_185913.mp4` | Partial/backup MP4 sink unless re-probed. Do not treat as canonical. |
| `files/logs/deliveries/match_20260524_190636.mp4` | Broken/unusable original MP4. `ffprobe` and VLC fail on invalid H.264 payload. |
| `files/logs/deliveries/match_20260524_190636.recovered.mp4` | Usable convenience remux from the canonical `.ts`; not an independent source. |

Recommended replay order:

1. Replay `files/logs/deliveries/live_20260524_185913/match_live_20260524_185913.ts` first.
2. Generate a replay trace and ball log.
3. Ingest Cricbuzz ground truth for match `152263`.
4. Diff replay output against ground truth.
5. Re-run the DCKKR baseline before code changes.
