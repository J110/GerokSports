#!/usr/bin/env bash
# Path A live clip extractor — runs every 30 min.
#
# Reads the live session's scout_raw.jsonl, materializes per-frame
# sidecar txt files, runs the offline cluster builder + boundary
# extractor, and writes per-cycle DETECTIONS json (anchor_t,
# clip_start, clip_end) plus best-effort ffmpeg trims when the source
# mp4 has settled bytes >=60s past the last cluster end.
#
# DESIGN NOTE: We bypass delivery_clip_pipeline.py because it has a
# hardcoded EXPECTED_ANCHORS verify-gate keyed to the dfb1c947 demo
# session. Instead we drive build_clusters / pick_anchor / extract_window
# directly via an inline python -c block. Detections JSON is the
# always-correct deliverable; ffmpeg trim is best-effort.
#
# Idempotent: skips already-extracted anchors by filename.
# Loop: while true; sleep 1800. PID -> files/logs/live_clips/.pid.

set -uo pipefail

cd "$(dirname "$0")/../.."

LIVE_DIR="files/logs/live_clips"
SIDECAR_BASE="files/scripts/broadcast_mode_tuning/live_chunk_scout"
PRED_BASE="files/scripts/broadcast_mode_tuning/live_chunk_predicted"

mkdir -p "$LIVE_DIR" "$SIDECAR_BASE" "$PRED_BASE"
echo $$ > "$LIVE_DIR/.pid"

cleanup() {
    rm -f "$LIVE_DIR/.pid"
    exit 0
}
trap cleanup INT TERM EXIT

log() { echo "[$(date '+%H:%M:%S')] [live_clips] $*"; }

run_cycle() {
    local cycle_tag
    cycle_tag=$(date '+%H%M')

    # 1. Resolve newest live session dir.
    # Pick the dir that has BOTH a non-empty scout_raw.jsonl AND match_*.mp4.
    # The launcher creates an empty live_<ts>/ dir; test_pipeline.py overrides
    # BMF_SESSION_ID with a uuid and writes scout_raw under THAT dir. The active
    # session is uniquely the one with both files present.
    local session_dir
    session_dir=""
    for d in $(ls -dt files/logs/deliveries/*/ 2>/dev/null \
               | grep -v archive_pre_fix \
               | grep -v archive_run2); do
        [ -s "${d}scout_raw.jsonl" ] || continue
        compgen -G "${d}match_*.mp4" >/dev/null 2>&1 || continue
        session_dir="$d"
        break
    done
    if [ -z "${session_dir:-}" ]; then
        log "no session dir under files/logs/deliveries/ yet — skip"
        return 0
    fi
    session_dir=${session_dir%/}
    local session_id
    session_id=$(basename "$session_dir")

    local scout_raw="$session_dir/scout_raw.jsonl"
    if [ ! -f "$scout_raw" ]; then
        log "session=$session_id has no scout_raw.jsonl yet — skip"
        return 0
    fi

    # 2. Locate live mp4 (match_*.mp4 inside session dir).
    local mp4
    mp4=$(ls -t "$session_dir"/match_*.mp4 2>/dev/null | head -1 || true)
    if [ -z "${mp4:-}" ]; then
        log "session=$session_id has no match_*.mp4 yet — clip extraction will be skipped this cycle"
    fi

    local sidecar_dir="$SIDECAR_BASE/$session_id"
    local pred_json="$PRED_BASE/${session_id}_${cycle_tag}_detections.json"
    local detections_out="$LIVE_DIR/${cycle_tag}_detections.json"

    mkdir -p "$sidecar_dir"

    # 3. Materialize scout_raw.jsonl → sidecar txt files.
    #    Format mirrors the offline first_5min_inspection convention.
    #    Each line in scout_raw.jsonl is expected to carry the rel_t
    #    in either a top-level numeric field or inside the raw_response
    #    body. We are defensive about the schema.
    python3 - "$scout_raw" "$sidecar_dir" <<'PY'
import json, os, re, sys
from pathlib import Path

scout_raw = Path(sys.argv[1])
out_dir = Path(sys.argv[2])
out_dir.mkdir(parents=True, exist_ok=True)

written = 0
skipped = 0
errs = 0

for i, line in enumerate(scout_raw.read_text().splitlines()):
    line = line.strip()
    if not line:
        continue
    try:
        rec = json.loads(line)
    except Exception:
        errs += 1
        continue
    # Try several schema variants for rel_t / frame_no.
    rel_t = None
    for k in ("rel_t", "t", "timestamp_rel", "ts_rel"):
        if k in rec and isinstance(rec[k], (int, float)):
            rel_t = float(rec[k])
            break
    if rel_t is None:
        # Some schemas embed rel_t inside raw_response prose.
        body = rec.get("raw_response") or rec.get("text") or ""
        m = re.search(r"\brel_t[:= ]+([\d.]+)", body)
        if m:
            rel_t = float(m.group(1))
    if rel_t is None:
        # Last resort: derive from frame_id if frames are ~2 fps.
        fid = rec.get("frame_id") or rec.get("frame_no")
        if isinstance(fid, int):
            rel_t = float(fid) * 0.5
    if rel_t is None:
        skipped += 1
        continue

    body = rec.get("raw_response") or rec.get("text") or rec.get("body") or ""
    if not body:
        skipped += 1
        continue

    fname = f"f_{i:06d}_t={rel_t:06.1f}.txt"
    p = out_dir / fname
    if p.exists():
        continue
    # Write with the standard "header --- body" shape so load_sidecars
    # split-on-`---\n` works downstream.
    header = f"ts: 0\nrel_t: {rel_t:.3f}\nframe_no: {i}\n"
    p.write_text(header + "---\n" + body)
    written += 1

print(f"sidecar: written={written} skipped={skipped} errs={errs}")
PY
    if [ $? -ne 0 ]; then
        log "sidecar materialization failed — skip cycle"
        return 0
    fi

    # 4. Run cluster + boundary extraction directly (bypass the
    #    pipeline's hardcoded verify gate).
    python3 - "$sidecar_dir" "$pred_json" <<'PY'
import json, sys, re
from pathlib import Path

sidecar_dir = Path(sys.argv[1])
out_json = Path(sys.argv[2])

REPO = Path.cwd()
sys.path.insert(0, str(REPO / "files/scripts/broadcast_mode_tuning"))

from signal_extraction import extract_signals
from delivery_classifier import (
    FrameInfo, annotate_all, build_clusters, pick_anchor,
)
from boundary_extractor import extract_window

frames = []
seen = set()
for p in sorted(sidecar_dir.glob("f_*.txt")):
    m = re.search(r"_t=(\d+(?:\.\d+)?)\.txt$", p.name)
    if not m:
        continue
    t = float(m.group(1))
    if t in seen:
        continue
    seen.add(t)
    raw = p.read_text()
    text = raw.split("---\n", 1)[1].strip() if "---\n" in raw else raw
    frames.append(FrameInfo(t=t, text=text))
frames.sort(key=lambda f: f.t)

for f in frames:
    f.signals = extract_signals(f.text)
annotate_all(frames)

clusters = build_clusters(frames, gap_max=3, min_run=2)
detections = []
for c in clusters:
    a = pick_anchor(c)
    w = extract_window(c, a.t, frames)
    detections.append({
        "anchor_t": round(a.t, 2),
        "anchor_path": a.path,
        "cluster_start_t": round(c["start_t"], 2),
        "cluster_end_t": round(c["end_t"], 2),
        "clip_start": round(w["clip_start"], 2),
        "clip_end": round(w["clip_end"], 2),
        "clip_duration": round(w["duration"], 2),
        "note": w.get("note", ""),
    })

out_json.parent.mkdir(parents=True, exist_ok=True)
out_json.write_text(json.dumps({
    "n_frames": len(frames),
    "n_clusters": len(detections),
    "detections": detections,
}, indent=2))
print(f"clusters: n={len(detections)} -> {out_json}")
PY
    if [ $? -ne 0 ]; then
        log "cluster extraction failed — skip cycle"
        return 0
    fi

    # Mirror detections JSON into the always-visible live_clips dir.
    if [ -f "$pred_json" ]; then
        cp "$pred_json" "$detections_out"
    fi

    # 5. Best-effort ffmpeg trim — only if mp4 exists and has settled
    #    bytes 60s past the last cluster's end_t.
    if [ -z "${mp4:-}" ] || [ ! -f "$mp4" ]; then
        log "cycle=$cycle_tag detections written, mp4 missing — clip trim skipped"
        return 0
    fi
    if [ ! -f "$pred_json" ]; then
        log "cycle=$cycle_tag no detections json — clip trim skipped"
        return 0
    fi

    local mp4_dur
    mp4_dur=$(ffprobe -v error -show_entries format=duration \
              -of default=noprint_wrappers=1:nokey=1 "$mp4" 2>/dev/null \
              | awk '{printf "%.1f", $1}')
    if [ -z "$mp4_dur" ]; then
        log "ffprobe failed on $mp4 — skip trim"
        return 0
    fi

    local extracted
    extracted=$(python3 - "$pred_json" "$mp4" "$mp4_dur" "$LIVE_DIR" <<'PY'
import json, os, subprocess, sys
from pathlib import Path

pred = Path(sys.argv[1])
mp4 = Path(sys.argv[2])
mp4_dur = float(sys.argv[3])
out_dir = Path(sys.argv[4])

data = json.loads(pred.read_text())
n_new = 0
existing = {p.name for p in out_dir.glob("clip_anchor*.mp4")}

for det in data.get("detections", []):
    end_t = det["clip_end"]
    if end_t + 60.0 > mp4_dur:
        continue  # mp4 hasn't caught up yet
    anchor_int = int(round(det["anchor_t"]))
    name = f"clip_anchor{anchor_int:04d}.mp4"
    if name in existing:
        continue
    out_path = out_dir / name
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", f"{det['clip_start']:.3f}",
        "-to", f"{det['clip_end']:.3f}",
        "-i", str(mp4),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k",
        str(out_path),
    ]
    rc = subprocess.run(cmd).returncode
    if rc == 0:
        # Sidecar metadata for review.
        meta = out_dir / f"clip_anchor{anchor_int:04d}.json"
        meta.write_text(json.dumps(det, indent=2))
        n_new += 1
print(n_new)
PY
) || extracted="0"
    log "cycle=$cycle_tag detections=$pred_json new_clips=$extracted mp4_dur=${mp4_dur}s"
}

while true; do
    run_cycle || log "cycle errored (continuing)"
    sleep 1800
done
