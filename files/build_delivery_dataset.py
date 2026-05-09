"""Extract all delivery data from pipeline logs into a structured dataset.

Parses DETAIL lines and [DELIVERY] lines, cross-references match context,
and outputs a JSONL file + CSV summary for manual labeling.

Usage:
    python build_delivery_dataset.py
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
from pathlib import Path

LOGS_DIR = Path(__file__).parent / "logs"
OUT_DIR = LOGS_DIR / "deliveries"
OUT_DIR.mkdir(exist_ok=True)

# Deduplicate across log files by (timestamp, frame_num)
_RE_DETAIL = re.compile(
    r'\[(\d{2}:\d{2}:\d{2})\s+F(\d+)\s+\w+\]\s+INFO:\s+DETAIL\|')
_RE_DELIVERY = re.compile(
    r'\[(\d{2}:\d{2}:\d{2})\s+F(\d+)\s+\w+\]\s+INFO:\s+'
    r'\[DELIVERY\]\s+(.*?)(?:\s+\((\d+)ms(?:,\s*(\d+)\s*dets)?\))?$')

_FIELD_RE = re.compile(r'([a-z_]+)=')

ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')


def strip_ansi(s: str) -> str:
    return ANSI_RE.sub('', s)


def parse_detail_fields(line: str) -> dict:
    """Parse pipe-separated key=value fields from a DETAIL line."""
    fields = {}
    parts = line.split('|')
    for part in parts:
        if '=' in part:
            key, _, val = part.partition('=')
            key = key.strip()
            val = val.strip()
            if val == '—' or val == '\u2014':
                val = None
            fields[key] = val
    return fields


def extract_delivery_from_detail(fields: dict) -> dict | None:
    """Return a delivery record if this DETAIL frame has delivery data."""
    length = fields.get('delivery_length')
    if not length or length == '—':
        return None

    return {
        "length": length,
        "line": fields.get('delivery_line'),
        "bowling_angle": fields.get('delivery_angle'),
        "bounce": fields.get('delivery_bounce'),
        "shot_type": fields.get('delivery_shot'),
        "shot_elevation": fields.get('delivery_elevation'),
        "shot_direction_side": fields.get('delivery_direction'),
        "shot_direction_zone": fields.get('delivery_dir_zone'),
        "shot_direction_conf": fields.get('delivery_dir_conf'),
        "detections": fields.get('delivery_dets'),
        "detection_rate": fields.get('delivery_det_rate'),
        "speed_kph": fields.get('speed_kph'),
        "score": fields.get('AFTER_score'),
        "striker": fields.get('AFTER_striker') or fields.get('striker_this_ball'),
        "non": fields.get('AFTER_non'),
        "bowler": (fields.get('comm_bowler')
                   or (fields.get('AFTER_bowl') or '').split()[0]
                   if fields.get('AFTER_bowl') else None),
        "ball_event": fields.get('ball_event'),
        "ball_event_runs": fields.get('ball_event_runs'),
        "ball_event_over": fields.get('ball_event_over'),
        "this_over": fields.get('AFTER_this_over'),
    }


def parse_delivery_log(text: str) -> dict:
    """Parse a [DELIVERY] commentary line into components."""
    parts = [p.strip() for p in text.split(',')]
    result = {
        "bowling_angle": None,
        "length": None,
        "line": None,
        "shot_type": None,
    }

    length_map = {
        "short ball": "bouncer",
        "banged in short": "bouncer",
        "short of a length": "short",
        "good length": "good_length",
        "full": "full",
        "yorker": "yorker",
        "full toss": "full_toss",
    }
    line_map = {
        "wide outside off stump": "wide_outside_off",
        "outside off stump": "outside_off",
        "on off stump": "off_stump",
        "on middle stump": "middle",
        "on leg stump": "leg_stump",
        "on the pads": "leg_side",
        "down the leg side": "down_leg",
    }
    shot_map = {
        "defended": "defended",
        "pushed into the field": "along_ground",
        "hit in the air": "aerial",
    }

    for part in parts:
        low = part.lower()
        if "round the wicket" in low:
            result["bowling_angle"] = "round"
        for key, val in length_map.items():
            if key in low:
                result["length"] = val
        for key, val in line_map.items():
            if key in low:
                result["line"] = val
        for key, val in shot_map.items():
            if key in low:
                result["shot_type"] = val

    if result["bowling_angle"] is None:
        result["bowling_angle"] = "over"

    return result


def scan_logs() -> list[dict]:
    """Scan all log files and extract unique deliveries."""
    seen = set()
    deliveries = []
    log_files = sorted(LOGS_DIR.glob("*.log"))

    for log_file in log_files:
        # Skip duplicate sub-logs (run-specific logs are subsets of machine-1)
        basename = log_file.name
        if basename.startswith("run-") or basename.startswith("detail-"):
            continue

        try:
            text = log_file.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue

        lines = text.splitlines()
        detail_by_frame: dict[str, dict] = {}

        for line in lines:
            line = strip_ansi(line)

            m_detail = _RE_DETAIL.search(line)
            if m_detail:
                ts = m_detail.group(1)
                fnum = m_detail.group(2)
                key = f"{basename}:{ts}:F{fnum}"
                fields = parse_detail_fields(line)
                detail_by_frame[key] = fields

            m_del = _RE_DELIVERY.search(line)
            if m_del:
                ts = m_del.group(1)
                fnum = m_del.group(2)
                commentary = m_del.group(3).strip()
                ms = m_del.group(4)
                dets = m_del.group(5)

                if "No classification" in commentary:
                    continue

                dedup_key = f"{ts}:F{fnum}"
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)

                detail_key = f"{basename}:{ts}:F{fnum}"
                detail_fields = detail_by_frame.get(detail_key, {})

                delivery = parse_delivery_log(commentary)
                detail_delivery = extract_delivery_from_detail(detail_fields)
                if detail_delivery:
                    delivery.update({k: v for k, v in detail_delivery.items()
                                     if v is not None})

                delivery["source_file"] = basename
                delivery["timestamp"] = ts
                delivery["frame"] = int(fnum)
                delivery["commentary_line"] = commentary
                delivery["latency_ms"] = int(ms) if ms else None
                delivery["detections"] = int(dets) if dets else (
                    int(delivery.get("detections", 0)) or None)

                deliveries.append(delivery)

    return deliveries


def add_scout_burst_deliveries(deliveries: list[dict]) -> list[dict]:
    """Add deliveries from scout_burst_results."""
    burst_dir = Path(__file__).parent / "scout_burst_results"
    if not burst_dir.exists():
        return deliveries

    # Per-delivery result files
    for d_dir in sorted(burst_dir.iterdir()):
        if not d_dir.is_dir():
            continue
        result_file = d_dir / "result.json"
        if not result_file.exists():
            continue
        try:
            data = json.loads(result_file.read_text())
        except Exception:
            continue

        cl = data.get("classification") or {}
        ctx = data.get("scout_context") or {}
        ts = ctx.get("timestamp", "")[:19]

        delivery = {
            "source_file": f"scout_burst/{d_dir.name}",
            "timestamp": ts,
            "frame": data.get("delivery_number", 0),
            "bowling_angle": cl.get("bowling_angle"),
            "length": cl.get("length"),
            "line": cl.get("line"),
            "bounce": cl.get("bounce"),
            "shot_type": cl.get("shot_type"),
            "runs": cl.get("runs"),
            "detections": data.get("detections_count"),
            "commentary_line": cl.get("commentary_feed", ""),
            "score": ctx.get("score"),
            "ball_event_over": ctx.get("overs"),
            "speed_kph": None,
        }

        scout_text = ctx.get("strip_after", "")
        speed_m = re.search(r'SPEED:\s*([\d.]+)', scout_text)
        if speed_m:
            delivery["speed_kph"] = speed_m.group(1)

        deliveries.append(delivery)

    # Summary file (has results array without scout_context)
    summary_file = burst_dir / "summary.json"
    if summary_file.exists():
        try:
            summary = json.loads(summary_file.read_text())
            for i, cl in enumerate(summary.get("results", [])):
                delivery = {
                    "source_file": f"scout_burst/summary[{i}]",
                    "timestamp": "",
                    "frame": i + 1,
                    "bowling_angle": cl.get("bowling_angle"),
                    "length": cl.get("length"),
                    "line": cl.get("line"),
                    "bounce": cl.get("bounce"),
                    "shot_type": cl.get("shot_type"),
                    "runs": cl.get("runs"),
                    "detections": None,
                    "commentary_line": cl.get("commentary_feed", ""),
                    "score": None,
                    "ball_event_over": None,
                    "speed_kph": None,
                }
                deliveries.append(delivery)
        except Exception:
            pass

    return deliveries


# Label taxonomy using cricket commentary terminology
LABEL_TAXONOMY = {
    "bowling_angle": {
        "values": ["over", "round"],
        "description": "Over the wicket or round the wicket",
    },
    "length": {
        "values": [
            "bouncer",
            "short",
            "back_of_length",
            "good_length",
            "full",
            "overpitched",
            "yorker",
            "full_toss",
        ],
        "description": "Pitch position of the ball",
    },
    "line": {
        "values": [
            "wide_outside_off",
            "outside_off",
            "off_stump",
            "on_stumps",
            "leg_stump",
            "on_pads",
            "down_leg",
        ],
        "description": "Horizontal position at the batter",
    },
    "bounce": {
        "values": [
            "bouncer",
            "sharp_bounce",
            "good_bounce",
            "normal",
            "stayed_low",
            "skidded_through",
        ],
        "description": "How high the ball bounced",
    },
    "shot_type": {
        "values": [
            "along_ground",
            "in_the_air",
            "defended",
            "missed",
            "left_alone",
        ],
        "description": "Whether ball stayed on the ground or went aerial",
    },
    "shot_direction": {
        "values": [
            "fine_leg",
            "backward_square_leg",
            "square_leg",
            "midwicket",
            "mid_on",
            "straight",
            "mid_off",
            "cover",
            "point",
            "backward_point",
            "third_man",
            "fine_third_man",
            "no_shot",
        ],
        "description": "Where the ball went after the batter played",
    },
}


def write_dataset(deliveries: list[dict]):
    """Write JSONL + CSV for labeling."""
    jsonl_path = OUT_DIR / "dataset.jsonl"
    csv_path = OUT_DIR / "dataset_for_labeling.csv"
    taxonomy_path = OUT_DIR / "label_taxonomy.json"

    with open(jsonl_path, 'w') as f:
        for i, d in enumerate(deliveries):
            d["id"] = i + 1
            f.write(json.dumps(d) + "\n")

    csv_fields = [
        "id", "source_file", "timestamp", "frame",
        "score", "ball_event_over", "striker", "bowler",
        "speed_kph", "runs", "ball_event", "detections",
        "commentary_line",
        # Predicted labels (from classifier)
        "pred_bowling_angle", "pred_length", "pred_line",
        "pred_bounce", "pred_shot_type", "pred_shot_direction_side",
        # Ground truth labels (to fill manually)
        "true_bowling_angle", "true_length", "true_line",
        "true_bounce", "true_shot_type", "true_shot_direction",
    ]
    with open(csv_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields)
        writer.writeheader()
        for d in deliveries:
            row = {
                "id": d.get("id"),
                "source_file": d.get("source_file"),
                "timestamp": d.get("timestamp"),
                "frame": d.get("frame"),
                "score": d.get("score"),
                "ball_event_over": d.get("ball_event_over"),
                "striker": d.get("striker"),
                "bowler": d.get("bowler"),
                "speed_kph": d.get("speed_kph"),
                "runs": d.get("runs") or d.get("ball_event_runs"),
                "ball_event": d.get("ball_event"),
                "detections": d.get("detections"),
                "commentary_line": d.get("commentary_line"),
                "pred_bowling_angle": d.get("bowling_angle"),
                "pred_length": d.get("length"),
                "pred_line": d.get("line"),
                "pred_bounce": d.get("bounce"),
                "pred_shot_type": d.get("shot_type") or d.get(
                    "shot_elevation"),
                "pred_shot_direction_side": d.get("shot_direction_side"),
                "true_bowling_angle": "",
                "true_length": "",
                "true_line": "",
                "true_bounce": "",
                "true_shot_type": "",
                "true_shot_direction": "",
            }
            writer.writerow(row)

    with open(taxonomy_path, 'w') as f:
        json.dump(LABEL_TAXONOMY, f, indent=2)

    print(f"Dataset: {len(deliveries)} deliveries")
    print(f"  JSONL: {jsonl_path}")
    print(f"  CSV:   {csv_path}")
    print(f"  Taxonomy: {taxonomy_path}")

    # Print summary
    print("\n--- Current prediction distribution ---")
    for field in ["bowling_angle", "length", "line", "bounce",
                  "shot_type", "shot_elevation"]:
        counts: dict[str, int] = {}
        for d in deliveries:
            val = d.get(field, "—") or "—"
            counts[val] = counts.get(val, 0) + 1
        print(f"  {field}: {dict(sorted(counts.items()))}")


def main():
    print("Scanning logs for delivery data...")
    deliveries = scan_logs()
    print(f"  Found {len(deliveries)} from pipeline logs")

    deliveries = add_scout_burst_deliveries(deliveries)
    print(f"  Total with scout_burst: {len(deliveries)}")

    write_dataset(deliveries)


if __name__ == "__main__":
    main()
