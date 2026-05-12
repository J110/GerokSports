import os

SERVER_URL = os.environ.get("EYES_SERVER_URL", "http://localhost:8000")
DEBUG_PORT = int(os.environ.get("EYES_DEBUG_PORT", "8001"))

VISION_MODEL = os.environ.get("EYES_VISION_MODEL", "qwen2.5vl:7b")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

# Groq Scout 17B — sole vision provider: tags + reads in one call
# ~1.0s per frame, $0.09/match
GROQ_API_KEY = os.environ.get(
    "GROQ_API_KEY",
    os.environ["GROQ_API_KEY"],
)
GROQ_PRIMARY_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
GROQ_FALLBACK_MODEL = "llama-3.1-8b-instant"
# Text-only model used by Extractor + Scorer (no image needed for
# either — they just parse SCOUT's text output and reconcile state).
# Defaults to llama-3.1-8b-instant which is ~3× faster than the
# scout-17b multimodal model on Groq for text-only workloads.  Both
# Extractor and Scorer are JSON-output structured-extraction tasks
# that the smaller model handles well; their failure modes are now
# guarded by regex-primary parsing (see eyes/extract_regex.py) and
# score_manager.py's reconciliation logic.
GROQ_TEXT_MODEL = os.environ.get(
    "GROQ_TEXT_MODEL", "llama-3.1-8b-instant")

# ── Backup: DashScope Qwen-VL (Alibaba Cloud intl) ──
# Free quota valid 90 days. Keep as fallback if Groq has outages.
DASHSCOPE_API_KEY = os.environ.get(
    "DASHSCOPE_API_KEY",
    "sk-e43d151417834788a83820e35cf21a7d",
)
DASHSCOPE_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
DASHSCOPE_VISION_MODEL = "qwen-vl-max"

# ── Gemini 3 Flash Preview — delivery-action classifier ──
# Owns delivery details (length / line / shot / handedness / ...) on
# the per-window video clip captured by DeliveryWindowRecorder.  Score-
# board pipeline (Scout) keeps owning names / scores / overs / state.
GEMINI_API_KEY = os.environ.get(
    "GEMINI_API_KEY",
    os.environ["GEMINI_API_KEY"],
)
GEMINI_DELIVERY_MODEL = os.environ.get(
    "GEMINI_DELIVERY_MODEL", "gemini-3-flash-preview")

# ── Retired: Together AI Qwen3-VL ──
# Replaced by Scout doing tag+read in one call. Kept for reference.
# TOGETHER_API_KEY = "tgp_v1_gKtaajInL6RLKCJ5k4Z_YtNU7jcksWOo6885LZWXTrQ"
# TOGETHER_VISION_MODEL = "Qwen/Qwen3-VL-8B-Instruct"

CAPTURE_FPS = 2

# ── Parallel-Scout / OpenScout (per design memo §3-§7) ──
# Master switch: when 0, OpenScout is not constructed, no extra Groq
# calls are made, no shadow telemetry runs.  When 1, OpenScout fires
# at OPEN_SCOUT_*_INTERVAL_S cadence and the SpanAggregator records
# action/replay/ad/umpire/other spans; behaviour fully gated by
# USE_OPEN_SCOUT_SPANS for actual window placement.
USE_OPEN_SCOUT = os.environ.get("USE_OPEN_SCOUT", "1") == "1"
# When 1, the score-event window selector consults OpenScout's
# SpanAggregator first via _find_span_open; legacy _find_span only
# runs as a fallback (or when SpanAggregator returns defer_to_legacy
# / no_match).  Default OFF — production behaviour unchanged.
USE_OPEN_SCOUT_SPANS = os.environ.get("USE_OPEN_SCOUT_SPANS", "0") == "1"
# Per-state cadence (seconds between OpenScout calls).  See §3.3 of
# parallel_scout_delivery_window_design.md for cost arithmetic.
OPEN_SCOUT_ACTIVE_INTERVAL_S = float(
    os.environ.get("OPEN_SCOUT_ACTIVE_INTERVAL_S", "1.0"))
OPEN_SCOUT_AMBIGUOUS_INTERVAL_S = float(
    os.environ.get("OPEN_SCOUT_AMBIGUOUS_INTERVAL_S", "2.0"))
# Open-prompt response budget — shorter than production tag+read
# (600 tokens) per validation memo §12.
OPEN_SCOUT_MAX_TOKENS = int(
    os.environ.get("OPEN_SCOUT_MAX_TOKENS", "220"))
OPEN_SCOUT_TEMPERATURE = float(
    os.environ.get("OPEN_SCOUT_TEMPERATURE", "0.2"))
OPEN_SCOUT_TIMEOUT_S = float(
    os.environ.get("OPEN_SCOUT_TIMEOUT_S", "8.0"))

# ── Decoupled OpenScout loop (parallel async coroutine) ──
# When 1 (default since 2026-05-11), OpenScout runs in a dedicated
# coroutine that polls the capture frame source directly at
# OPENSCOUT_DECOUPLED_TARGET_INTERVAL_S cadence, independent of main
# pipeline iteration timing.  When 0, OpenScout piggybacks on the
# per-frame vision loop (legacy behavior).
#
# Quota verified on Groq Developer plan
# (meta-llama/llama-4-scout-17b-16e-instruct):
#   RPM cap   1,000  → 60 RPM at 1.0s target = 6% utilization
#   RPD cap 500,000  → ~12.6K calls/match    = 2.5% utilization
#   TPM cap 300,000  → ~60% utilization assuming 3K tokens/call
# TPM is the only meaningful ceiling; OPENSCOUT_TPM_BUDGET trips
# auto-derate before the cap is reached.  See
# files/docs/operations/openscout_decoupled_setup.md.
OPENSCOUT_DECOUPLED = os.environ.get("OPENSCOUT_DECOUPLED", "1") != "0"
OPENSCOUT_DECOUPLED_TARGET_INTERVAL_S = float(
    os.environ.get("OPENSCOUT_DECOUPLED_TARGET_INTERVAL_S", "1.0"))
OPENSCOUT_TPM_BUDGET = int(
    os.environ.get("OPENSCOUT_TPM_BUDGET", "240000"))

# ── Chunker v3 (rule-based, time-based broadcast chunker) ──
# When 1, runs ChunkerV3 in parallel as shadow telemetry — every
# delivery window resolution emits a v3_chunker block in
# window_debug.json alongside the legacy and OpenScout proposals.
# Cost: ~$0 — v3 reuses cached Scout outputs from the OpenScout
# result_sink, no new API calls.  See
# files/docs/algorithms/chunker_v3.md and
# files/docs/operations/chunker_v3_setup.md.
USE_V3_CHUNKER = os.environ.get("USE_V3_CHUNKER", "0") == "1"
# When 1 AND USE_V3_CHUNKER=1, v3's window drives the actual delivery
# cut.  When v3 returns None for an event, the pipeline falls back to
# the legacy span as if v3 weren't running.  Default OFF — production
# behavior unchanged until the gates in chunker_v3_setup.md are met.
USE_V3_CHUNKER_SPANS = os.environ.get("USE_V3_CHUNKER_SPANS", "0") == "1"

# ── Chunker v3 None-fallback safety net ──
# When the v3 chunker returns None for a score event AND the legacy
# `_find_span` also fails, ``DeliveryWindowRecorder`` emits a fixed
# window centered on ``event_ts`` instead of the legacy
# ``fallback_pre_event_window`` (which can produce unusable cuts when
# legacy is broken).  Defaults are tuned to the 18-clip corpus average
# delivery duration: 6 s lookback covers bowler run-up; 4 s forward
# covers post-shot fielding.  See
# files/docs/operations/chunker_v3_setup.md "None-event fallback".
V3_FALLBACK_ENABLED = os.environ.get("V3_FALLBACK_ENABLED", "1") == "1"
V3_FALLBACK_LOOKBACK_S = float(
    os.environ.get("V3_FALLBACK_LOOKBACK_S", "6.0"))
V3_FALLBACK_FORWARD_S = float(
    os.environ.get("V3_FALLBACK_FORWARD_S", "4.0"))

# ── Continuous chunker (score-event-decoupled detector) ──
# When 1, ContinuousChunker subscribes to OpenScout results and runs the
# v3 per-frame label state machine continuously, emitting auto/dNNN
# clips to ``files/logs/deliveries/<session>/auto/`` whenever a
# DELIVERY_ACTION cluster closes.  Independent of the score-event path
# under ``d<NNN>/``.  Default OFF — opt-in for controlled rollout.  See
# files/eyes/continuous_chunker.py and files/eyes/auto_delivery_recorder.py.
USE_CONTINUOUS_CHUNKER = os.environ.get(
    "USE_CONTINUOUS_CHUNKER", "0") == "1"
CONTINUOUS_CHUNKER_MIN_DURATION_S = float(
    os.environ.get("CONTINUOUS_CHUNKER_MIN_DURATION_S", "4.0"))
CONTINUOUS_CHUNKER_MAX_DURATION_S = float(
    os.environ.get("CONTINUOUS_CHUNKER_MAX_DURATION_S", "20.0"))
CONTINUOUS_CHUNKER_MIN_EVENT_GAP_S = float(
    os.environ.get("CONTINUOUS_CHUNKER_MIN_EVENT_GAP_S", "4.0"))
# Minimum walk-strength a v3.2 confidence cluster must accumulate
# before ContinuousChunker emits a DeliveryDetectedEvent.  ``walk_chunk``
# starts at the anchor's DELIVERY score (~0.5–1.0) and adds 0.20 per
# supporting frame; 0.65 admits anchor + 1 supporter.
CONTINUOUS_CHUNKER_MIN_CONFIDENCE = float(
    os.environ.get("CONTINUOUS_CHUNKER_MIN_CONFIDENCE", "0.65"))

# ── Full-match raw recorder ──
# When 1, files/eyes/match_recorder.py runs as an async task that
# polls the capture frame slot and writes match_<SESSION_ID>.mp4 to
# files/logs/deliveries/<session>/.  RECORD_FULL_MATCH_FPS sets the
# encoded FPS (default 25 — broadcast-native; pick lower to shrink
# files at the cost of choppier playback).
RECORD_FULL_MATCH = os.environ.get("RECORD_FULL_MATCH", "1") == "1"
RECORD_FULL_MATCH_FPS = float(
    os.environ.get("RECORD_FULL_MATCH_FPS", "25"))

FRAME_SOURCE = os.environ.get("FRAME_SOURCE", "capture_card").lower()
CAPTURE_DEVICE_INDEX = int(os.environ.get("CAPTURE_DEVICE_INDEX", "0"))

# Color-order escape hatch (2026-05-02 audit, V2 verdict):
# The legacy Quartz path applies a `[:, :, ::-1]` flip after stripping
# alpha from BGRA-in-memory data, so the downstream variable named
# `bgr` actually carries RGB pixel bytes. CaptureCardFrameSource
# preserves that quirk for migration parity. Every cv2.imencode /
# cv2.imwrite / cv2.cvtColor on the way to Scout / Qwen / Gemini
# therefore receives R/B-swapped pixels — see
# `files/docs/operations/frame_source_setup.md` for the full audit.
#
# Default: 0 (preserve legacy swap so HSV thresholds in
# pitch_detector, ball_detection_utils, field_detector,
# broadcast_detector etc. keep matching what they were tuned on).
# Set FRAME_COLOR_TRUE_BGR=1 to ship true BGR everywhere — REQUIRES
# coordinated re-tuning of every consumer listed above. Do not flip
# without the consumer audit.
FRAME_COLOR_TRUE_BGR = os.environ.get("FRAME_COLOR_TRUE_BGR", "0") == "1"
PROCESS_EVERY_N = 1  # process every Nth captured frame (1 = all)
DEAD_TIME_PROCESS_EVERY_N = 5  # during ads/timeouts

OCR_WIDTH = 1920    # high-res for text reading
QWEN_WIDTH = 960    # smaller for API calls

MIN_SECONDS_BETWEEN_BALLS = 8
CONTEXT_UPDATE_INTERVAL = 10  # frames between context rebuilds
STATE_BROADCAST_INTERVAL = 20  # frames between full state sends
PREVIEW_INTERVAL = 4  # frames between debug preview updates
MICRO_INSIGHT_INTERVAL = 60  # frames between micro insight generation

OCR_LOOP_INTERVAL = 0.3  # seconds between OCR frames
OCR_FAIL_THRESHOLD = 5   # consecutive failures before triggering Spotter

YOLO_MODEL = "yolov8n.pt"
YOLO_CONFIDENCE = 0.3

# Manual squad fallback — paste from Cricbuzz/ESPNcricinfo before match.
# Leave empty to rely on auto-detection from broadcast graphics.
# GT vs RCB, 42nd Match, IPL 2026 — Narendra Modi Stadium, Ahmedabad
SQUADS: dict[str, list[str]] = {
    "GT": [
        "Shubman Gill",
        "Sai Sudharsan",
        "Jos Buttler",
        "Jason Holder",
        "Shahrukh Khan",
        "Washington Sundar",
        "Arshad Khan",
        "Rashid Khan",
        "Kagiso Rabada",
        "Mohammed Siraj",
        "Manav Suthar",
    ],
    "RCB": [
        "Virat Kohli",
        "Jacob Bethell",
        "Devdutt Padikkal",
        "Rajat Patidar",
        "Jitesh Sharma",
        "Tim David",
        "Romario Shepherd",
        "Krunal Pandya",
        "Bhuvneshwar Kumar",
        "Suyash Sharma",
        "Josh Hazlewood",
    ],
}
