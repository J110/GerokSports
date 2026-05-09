# Scout per-frame classification validation (research)

Feasibility work for parallel-Scout + span aggregation delivery-window detection.

## Prerequisites

- `ffmpeg` / `ffprobe` on PATH (Phase A extraction)
- `opencv-python` / Groq client + `GROQ_API_KEY` for `run_scout.py`

## Layout

| File | Purpose |
|------|---------|
| `extract_frames.py` | 1 fps JPG export + `output/labels_to_fill.csv` |
| `scout_mapping.py` | **`scout_to_label_naive`** — single mapping function |
| `run_scout.py` | `Vision.describe` → `output/scout_responses.jsonl` |
| `run_scout_focused.py` | **A/B-only** — direct Groq **`llama-4-scout`** + delivery-focused **`FOCUSED_PROMPT`** → `output/scout_responses_focused.jsonl` (does **not** touch `Vision`) |
| `analyze.py` | Naive + temporal confusion matrices, span sim, verdict |
| `analyze_focused_ab.py` | Merges production + focused JSONLs → `output/confusion_metrics_focused.json` (+ span sim on temporal focused) |
| `run_scout_open.py` | Diagnostic — open-ended captions → `output/scout_responses_open.jsonl` (direct Groq, long `max_tokens`) |
| `analyze_open_descriptions.py` | N-grams + PMI-ish terms + naive keyword sanity check → `output/description_ngrams_by_class.json`, `output/keyword_classifier_metrics.json` |
| `classify_descriptions.py` | **§11** — wide-pitch / closeup rules on frozen open JSONL → `output/rule_iteration_metrics.json`, `rule_v1_errors.jsonl`, `rule_v2_errors.jsonl` (no API) |

## Label ontology (CSV column `label`)

Exactly one of:

- **`action`** — live delivery corridor (bowler run-up through post-shot as seen in live coverage)
- **`replay`** — rebroadcast/slow-motion/angles repeating the delivery
- **`ad`** — commercial / full break
- **`other`** — everything else (graphics, tight shots without live corridor, fillers)
- **`umpire`** — signal / umpire-centric decision framing
- **`unknown`** — cannot determine

(`run_scout.py` validates the CSV before issuing Groq traffic.)

## Phase B+C — classify + analyze

```bash
cd files/scripts/scout_validation_research
PYTHONPATH="$(cd ../.. && pwd)" python3 run_scout.py --throttle-s 0.35
python3 analyze.py
```

**JSONL record shape**:

```json
{
  "frame_path": "...",
  "source_clip": "...",
  "time_in_clip_s": "0.0",
  "ground_truth": "action",
  "scout_response": { "frame_type": "...", "last_camera_view": "...", "...": "..." },
  "scout_label_naive": "other"
}
```

`analyze.py` derives **`scout_label_temporal`** in-memory (later action corridors → **`replay`**).

Artifacts: `output/scout_responses.jsonl`, `output/confusion_metrics.json`, `output/failure_patterns.txt`.

### Focused-prompt A/B (memo Section 9)

```bash
cd files/scripts/scout_validation_research
PYTHONPATH="$(cd ../.. && pwd)" python3 run_scout_focused.py --throttle-s 0.35
python3 analyze_focused_ab.py
```

Artifacts: **`output/scout_responses_focused.jsonl`**, **`output/confusion_metrics_focused.json`**.

JSONL minimal shape:

```json
{
  "frame_path": "...",
  "ground_truth": "action",
  "focused_response_raw": "...",
  "focused_label": "other"
}
```

### Open-ended descriptions (memo Section 10 — perception diagnostic)

```bash
cd files/scripts/scout_validation_research
PYTHONPATH="$(cd ../.. && pwd)" python3 run_scout_open.py --throttle-s 0.35
python3 analyze_open_descriptions.py
```

Artifacts: **`output/scout_responses_open.jsonl`**, **`description_ngrams_by_class.json`**, **`keyword_classifier_metrics.json`**.

### §11 — Rule iteration on open descriptions (no API)

```bash
cd files/scripts/scout_validation_research
python3 classify_descriptions.py
```

Artifacts: **`output/rule_iteration_metrics.json`**, **`output/rule_v1_errors.jsonl`**, **`output/rule_v2_errors.jsonl`**. See memo **Section 11** in `scout_per_frame_classification_validation.md`.

Minimal JSONL row:

```json
{
  "frame_path": "output/frames/....jpg",
  "ground_truth": "action",
  "open_description": "The camera shows ...",
  "raw_response": { "choices": [...], "usage": {...} }
}
```

## Production Scout references

- [`files/eyes/vision.py`](../../eyes/vision.py) — `Vision.describe`, `SCOUT_PROMPT`
- [`files/eyes/config.py`](../../eyes/config.py) — Groq model id

Memo: [`files/docs/investigations/scout_per_frame_classification_validation.md`](../../docs/investigations/scout_per_frame_classification_validation.md).
