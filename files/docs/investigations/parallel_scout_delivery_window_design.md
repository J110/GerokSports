# Parallel-Scout per-frame classification + span aggregation — design memo

**Date:** 2026-05-01
**Status:** **Design only — no production code in this session.** Implementation deferred to a separate session after operator (Anmol) review.
**Inputs read:** `scout_per_frame_classification_validation.md` (§§9–12), `delivery_extraction_audit.md`, `window_content_audit.md`, `files/eyes/vision.py`, `files/eyes/config.py`, `files/test_pipeline.py` (Scout site, AdaptiveSleep, score-event handler), `files/ball_analyzer.py`, `files/delivery_window_recorder.py`, `files/gemini_delivery_classifier.py` (mp4 compile), `files/scripts/scout_validation_research/{run_scout_open.py,classify_descriptions.py}`.
**Cross-cutting context:** §11 wide-camera prose rule (binary v2: P≈0.77, R≈0.99, F1≈0.87 on 247 frames; multiclass `classify_full` accuracy ≈ 87 %) and the §12 verdict that Scout-only is sufficient at 1 fps for delivery-zone narration; replay disambiguation is the open weakness.

---

## §1 Executive summary

**Architecture.** A second `Vision`-style instance (call it `OpenScout`) runs at a **decoupled 1 fps** cadence as a fire-and-forget background coroutine in the existing per-frame loop at ```6052:6056:files/test_pipeline.py```. Each call uses the frozen **`OPEN_PROMPT`** from `run_scout_open.py:32–41`; the response is fed through `classify_full` (`classify_descriptions.py:326`, layered `is_ad_pattern → is_replay_pattern → umpire morphology → classify_v2_final → other`). Per-frame `(ts, class)` tuples flow into a new **`SpanAggregator`** living on `BallAnalyzer` alongside `_tagged_buffer`. The aggregator emits closed contiguous-class spans with hysteresis (1-frame gap merge, 2-frame minimum) and retains spans for **90 s** (matching `TAGGED_BUFFER_RETENTION_S` at ```132:132:files/ball_analyzer.py```). On a score event, `DeliveryWindowRecorder.classify_for_score_event` consults the aggregator first via a new `_find_span_open(event_ts)` selector that filters action-class spans in `[event_ts − LOOKBACK_S, event_ts − POST_EVENT_EXCLUSION_S]` by minimum duration and `MAX_END_TO_EVENT_GAP_S`. **If exactly one span survives, it is committed; if two or more spans survive, v1 defers the selection to the existing legacy `_find_span` (RC-7 anchor walk)** — the multi-span "earliest = live" heuristic is shadow-only in v1 (§5.2). If neither path produces a span, behavior falls through to `fallback_pre_event_window`. The chosen span's `(start_ts, end_ts)` becomes `clip_start, clip_end` via the same `_span_to_clip_bounds` and `_get_frames` raw-buffer slice that the existing path uses.

**Coexistence recommendation.** **Option C3 (feature flag) with telemetry-only shadow side-by-side.** A single env var `USE_OPEN_SCOUT_SPANS=0|1` (default `0`) selects which path's window is sent to Layer 2, but the **alternate path always writes its proposed window into `window_debug.json` as `_alt_window_*` fields** so we get shadow comparison without paying for two L2 calls per delivery. C1 (replace) is too risky given that 205 / 215 deliveries on the production audit (`window_content_audit.md` §3.2) currently fall back; C2 (full shadow) doubles Layer 2 cost (~\$0.05–\$0.10 per delivery on Qwen+Gemini) which is unacceptable across a match.

**Scope estimate.** **MEDIUM** (~**400–600 LOC** prod + ~**200 LOC** tests; **2 implementation sessions** including a shadow-run analysis pass):
- `OpenScout` Vision client + open-prompt narration: ~80 LOC
- `SpanAggregator` (state machine + 90 s span ring): ~150 LOC
- `DeliveryWindowRecorder._find_span_open` + selection algorithm: ~80 LOC
- `window_debug.json` schema extension (`_alt_window_*`, `open_class_stream`): ~40 LOC
- Wiring in `BallAnalyzer.__init__`, `start`, `record_open_classification`, and `test_pipeline` background-task spawn: ~50 LOC
- Unit + replay tests: ~200 LOC

**Open questions for operator decision (see §11 for full list):**
1. **Multi-span policy after shadow validation** — v1 defers the multi-candidate case to legacy `_find_span` (the "earliest action span = live" heuristic is shadow-only) because the 247-frame validation set has only **6** GT replay rows and §11.7 shows v2 binary regressed on `d102` when kinetic language chained into replay. After the §9.4 shadow run, do we promote the heuristic to production default if the §5.2 cutover criterion is met (≥ 15 % multi-span coverage AND ≥ 70 % heuristic-vs-legacy agreement), or permanently defer multi-span cases to legacy regardless? See §11.2.
2. **Cost ceiling** — proposed gated cadence (1 fps active-play, 0.5 fps in-play non-action, paused in ads) adds **≈ +\$0.03 to +\$0.10 per match** (~+0.3× to +1.1× of current ~\$0.09 Scout spend, ```10:10:files/eyes/config.py```; explicit multiplication in §3.3). Day-1 shadow-mode telemetry must measure `usage.total_tokens` per call to validate the reverse-engineered per-call cost. If a hard budget exists, drop to 0.5 fps active (degrades aggregator span continuity per §11.7 sample-rate caveat).
3. **What happens during ads / capture-paused intervals?** Pause `OpenScout` or burn calls anyway? Recommendation in §3.2 is pause; needs sign-off because that pause aligns aggregator behavior with the existing AdaptiveSleep dead-time philosophy but produces gaps.
4. **Should the open-prose path adopt the §11 multiclass `classify_full` end-to-end, or only the binary v2 action gate?** Multiclass gives `replay`/`ad`/`umpire` channels for free but the §11 confusion matrix shows replay recall is 0/6. We propose multiclass routing for telemetry but **only `action` spans** drive window placement.

---

## §2 Current pipeline forensics

### 2.1 Vision class lifecycle (sub-A1)

| Aspect | Finding | Cite |
|---|---|---|
| Process model | **`asyncio` coroutine** owned by the main pipeline loop. `Vision` wraps a single `groq.AsyncGroq` client. | ```267:269:files/eyes/vision.py``` |
| Per-call entry point | `await vision.describe(frame, vision_hint)` returns `(frame_type, description, action_description)` and side-effects `last_camera_view`, `last_frame_phase`, `last_ball_position`, `last_strip_flag`, `last_overlay_flag`, `last_drs_flag`. | ```294:380:files/eyes/vision.py``` |
| Caller | The per-frame loop in `test_pipeline.py` invokes `await vision.describe(...)` once per processed frame, then forwards `last_camera_view` / `last_frame_phase` to `BallAnalyzer.record_tagged_frame`, `BallAnalyzer.on_scout_tag`, `AdaptiveSleep`, and `Scoreboard.on_camera_view`. | ```6052:6126:files/test_pipeline.py``` |
| Rate (effective) | **AdaptiveSleep-driven**, not strict-fps. Phase map: `release/flight/shot=0.4s`, `runup=1.5s`, `between_play=2.0s`, `replay/graphic=3.0s`, `advertisement=8.0s`. With `BURST_DURATION=8.0s` overrides at X.5 overs, and a `5s` `ACTIVE_TAIL_HOLD` after every active-play tag. Capture FPS itself is `CAPTURE_FPS=2` (`config.py:43`) but `AdaptiveSleep.get_sleep_time()` is the actual gate. | ```893:1063:files/test_pipeline.py```, ```43:43:files/eyes/config.py``` |
| Cost (current) | Documented header comment: **"~1.0 s per frame, \$0.09/match"** for the **production tag+read** prompt at 600 max_tokens. | ```10:10:files/eyes/config.py```, ```468:494:files/eyes/vision.py``` |
| Latency observed | Production prompt: ~800 ms median (per `vision.py:54-56` validation note). Validation harness throttle: 0.35 s gives ~240 s wall for 247 frames including model time (≈350 ms median Groq `usage.total_time` per scout_per_frame_classification_validation §1 / §12.1). | as cited |
| API key | Single `GROQ_API_KEY` shared across all Groq calls; one `AsyncGroq` client per `Vision` instance. | ```11:13:files/eyes/config.py``` |

### 2.2 Frame buffer access (sub-A2)

| Aspect | Finding | Cite |
|---|---|---|
| Raw buffer | `BallAnalyzer._frame_buffer: collections.deque[(ts, np.ndarray)]` with `maxlen=FRAME_BUFFER_MAXLEN=1200`. | ```131:131,344:345:files/ball_analyzer.py``` |
| Buffer capacity | 1200 frames; capture loop runs at ~20 fps after `is_wide_shot` decoupling → **~60 s headroom** at 960 px width (≈2 GB peak per the docstring at `ball_analyzer.py:130`). The audit confirms ~12.9 fps **encoded** rate post-mp4 (`window_content_audit.md` §3.1) but raw capture is higher. | ```125:136:files/ball_analyzer.py```, ```1862:1906:files/ball_analyzer.py``` |
| Tagged buffer | `_tagged_buffer: deque[(ts, frame, camera_view, frame_phase)]`, `maxlen=240` and pruned to **`TAGGED_BUFFER_RETENTION_S=90.0`** by ts in `record_tagged_frame`. | ```358:360,608:636:files/ball_analyzer.py``` |
| Reader access | `_frame_source(start_ts, end_ts)` returns a list snapshot via `list(self._frame_buffer)` (atomic on a deque, no lock); `_snapshot_tagged(...)` takes `_tagged_lock` for the snapshot. | ```563:575,638:669:files/ball_analyzer.py``` |
| Timestamp resolution | `time.time()` epoch seconds at frame-grab moment (`now = time.time()` in `_capture_loop`). Sub-millisecond. | ```1890:1905:files/ball_analyzer.py``` |
| Pruning | Raw buffer: implicit FIFO via `deque(maxlen=1200)` → oldest dropped on append. Tagged buffer: explicit `cutoff = ts - TAGGED_BUFFER_RETENTION_S` walk. | ```635:636,1905:1905:files/ball_analyzer.py``` |

### 2.3 Score-event-to-window flow (sub-A3)

| Aspect | Finding | Cite |
|---|---|---|
| Trigger | `ball_event = ball_detector.detect(scoreboard._tracker)` then `_evt_is_real` filter and absorbed-multi-ball gate; calls `ball_analyzer.enqueue_delivery_analysis(...)` which dispatches to a 2-worker `dwr-worker` `ThreadPoolExecutor`. | ```9572,9714:9770:files/test_pipeline.py```, ```753:872:files/ball_analyzer.py``` |
| `event_ts` | **`time.time()` at the moment `enqueue_delivery_analysis` runs** (i.e., post-detect, on the main thread). Then passed verbatim to `DeliveryWindowRecorder.classify_for_score_event`. Precision: ms. | ```805:805:files/ball_analyzer.py```, ```701:712:files/ball_analyzer.py``` |
| Constants (DWR) | `LOOKBACK_S=25.0`, `POST_EVENT_EXCLUSION_S=1.5`, `MAX_END_TO_EVENT_GAP_S=8.0`, `MAX_CONTIGUOUS_GAP_S=2.5`, `PRE_PADDING_S=2.0`, `POST_PADDING_S=1.5`, `MAX_EVENT_DRIFT_S=2.5`, `FALLBACK_LOOKBACK_S=10.0`, `MIN_INTER_DELIVERY_S=8.0`, `MAX_SPAN_OVERLAP_RATIO=0.5`, `_ACTION_PHASES={release,flight,shot,runup}`. | ```54:109:files/delivery_window_recorder.py``` |
| Selection logic | `_find_span` walks NEWEST→OLDEST in `[event_ts − LOOKBACK_S, event_ts − POST_EVENT_EXCLUSION_S]`, anchors only on `view==bowlers_end ∧ phase∈_ACTION_PHASES`, breaks on `MAX_CONTIGUOUS_GAP_S` exceeded, rejects spans whose end is more than 8 s before `event_ts`. Phantom-event guard at `MIN_INTER_DELIVERY_S`; duplicate-span guard at `MAX_SPAN_OVERLAP_RATIO`. Falls through to `fallback_pre_event_window` (12.5 s clip ending at `event_ts + MAX_EVENT_DRIFT_S`) if no span. | ```242:294,328:425:files/delivery_window_recorder.py``` |
| MP4 assembly | `Layer2Classifier.classify_frames` (or `GeminiDeliveryClassifier`) compiles frames via `compile_frames_to_mp4` (cv2 `VideoWriter` with `avc1`/`mp4v` fourcc; FPS = `(len-1)/duration` clamped `[5, 60]`; max-width downscale; even-pixel rounding). Output path: `<delivery_dir>/delivery_window.mp4`. Frames sent are exactly the `_get_frames(clip_start, clip_end)` snapshot. | ```340:383,720:730:files/gemini_delivery_classifier.py```, ```283:293:files/delivery_window_recorder.py``` |

### 2.4 Scout output consumers (sub-A4)

| Consumer | Cite | Class | Tolerance to reroute |
|---|---|---|---|
| `BallAnalyzer.record_tagged_frame` (writes `_tagged_buffer`; gates `bowlers_end`/`side_on`/`replay`) | ```608:636:files/ball_analyzer.py``` | **Required** for current `_find_span` retrospective path | Must be preserved unless `_find_span` itself is retired. |
| `BallAnalyzer.on_scout_tag` → `DWR.on_scout_tag` (histogram counter only) | ```577:594:files/ball_analyzer.py```, ```165:167:files/delivery_window_recorder.py``` | **Telemetry** | No constraint. |
| `AdaptiveSleep.on_camera_view` / `on_frame_phase` (cadence) | ```1023:1044:files/test_pipeline.py``` | **Required** for end-to-end Scout cadence | Must remain wired to **primary** Scout, not `OpenScout`. |
| `Scoreboard.on_camera_view` (XI-reject gate, live-evidence) | ```482:492,2383:2410:files/eyes/scoreboard.py``` | **Required** for batter promotion gating | Must remain wired to **primary** Scout. |
| `extract_broadcast_data` consumes `description` (strip text), drives strip parser | ```6128:6130:files/test_pipeline.py``` | **Required** | OpenScout output is **not** a strip read; this path is untouched. |
| `vision.last_drs_flag` / `last_ball_position` | ```270:288:files/eyes/vision.py``` | Advisory / future | Untouched. |
| Legacy `analyze_last_delivery` (`USE_LEGACY_VLM=1`) phase-priority frame picks | ```1026:1162:files/ball_analyzer.py``` | **Dormant** | Not on default path. |
| `_find_span` `_get_tags` reads | ```360:407:files/delivery_window_recorder.py``` | **Required** today; **alternate** under flag | The new path either runs alongside (default off) or supplants for span discovery only. |

**Conclusion:** the **scoreboard reading path** (description + strip + camera_view + frame_phase consumers in `Scoreboard`/`AdaptiveSleep`/`extract_broadcast_data`) **must continue to be driven by the primary Scout call exactly as today**. The proposed parallel path adds a new, independent narration channel whose consumers are scoped to the new `SpanAggregator` and the recorder.

---

## §3 Proposed architecture

### 3.1 Diagram (text)

```
┌──────────────────────── per-frame loop (test_pipeline.py:~6020) ───────────────────────┐
│                                                                                         │
│   capture frame ─►  await vision.describe(frame, hint)   [PRIMARY Scout — UNCHANGED]    │
│        │            └─► strip read, JSON tag (camera_view, frame_phase, …)             │
│        │            └─► AdaptiveSleep / Scoreboard / BallAnalyzer.record_tagged_frame  │
│        │                                                                                │
│        ├─► asyncio.create_task(open_scout.classify(frame, ts))   ── if rate-gate open ──│
│        │            └─► OpenScout.describe_open(frame) → text                          │
│        │            └─► classify_full(text) → {action, replay, ad, umpire, other}      │
│        │            └─► ball_analyzer.record_open_classification(ts, cls, text)        │
│        │                                                                                │
│        ▼                                                                                │
│   ball_event = ball_detector.detect(...)                                               │
│   if real & not absorbed: ball_analyzer.enqueue_delivery_analysis(...)                 │
│                                                                                         │
└─────────────────────────────────────────────────────────────────────────────────────────┘

         ┌─────────────────────────── BallAnalyzer ────────────────────────────┐
         │                                                                      │
         │   _frame_buffer (raw, deque maxlen=1200, ~60s @ ~20fps)             │
         │   _tagged_buffer (Scout cam/phase, 90s)                              │
         │   ┌── NEW: SpanAggregator ───────────────────────────────────────┐  │
         │   │  state: current_class, current_span_start, gap_count          │  │
         │   │  closed_spans: deque[(start_ts, end_ts, cls, n_frames)]       │  │
         │   │  retention: 90 s by ts                                        │  │
         │   │  on_observation(ts, cls)  → maybe close span; maybe open new  │  │
         │   │  spans_in(lo_ts, hi_ts, cls=...) → list                       │  │
         │   └────────────────────────────────────────────────────────────────┘  │
         └──────────────────────────────────────────────────────────────────────┘

                       │
                       ▼
         ┌─────────── DeliveryWindowRecorder.classify_for_score_event ──────────┐
         │                                                                       │
         │   if USE_OPEN_SCOUT_SPANS=1:                                          │
         │       span = _find_span_open(event_ts)                                │
         │   else:                                                                │
         │       span = _find_span(event_ts, "bowlers_end")        # legacy RC-7│
         │                                                                       │
         │   if span is None: fallback_pre_event_window                          │
         │   _alt_span = the path NOT chosen → write to window_debug.json        │
         │                                                                       │
         │   frames = _get_frames(clip_start, clip_end)                          │
         │   layer2/gemini classify_frames(frames) → delivery_window.mp4 + json  │
         └───────────────────────────────────────────────────────────────────────┘
```

### 3.2 Process model (B1) — **proposed answer with reasoning**

**Recommendation: NEW dedicated `OpenScout` instance, async, fire-and-forget background coroutine, same `GROQ_API_KEY` but a separate `AsyncGroq` client; hooked into the existing per-frame loop at ```6052:6056:files/test_pipeline.py``` immediately after `await vision.describe(...)` returns.** The primary `Vision` path is untouched.

**Implementation sketch (no production code in this session):**

```
# in test_pipeline init
open_scout = OpenScout(api_key=GROQ_API_KEY, model=GROQ_PRIMARY_MODEL)
open_rate_gate = OpenScoutRateGate(target_fps=1.0)

# inside the per-frame loop, AFTER `await vision.describe(...)`
if open_rate_gate.allow(t0, adaptive_state=adaptive.last_camera_view):
    asyncio.create_task(open_scout_pipe(frame, t0))   # fire-and-forget

async def open_scout_pipe(frame, ts):
    text = await open_scout.describe_open(frame)
    cls  = classify_full(text, binary_fn=classify_v2_final)
    ball_analyzer.record_open_classification(ts, cls, text)
```

**Tradeoffs documented:**

- *Same `Vision` instance, second prompt?* Rejected. Adding a second-pass call inside `Vision.describe` would double primary-call latency on the main loop (currently ~800 ms median), pushing AdaptiveSleep's 0.4 s active-play cadence out of reach and starving the scoreboard reader. Two clients are also needed because Groq `chat.completions.create(...)` is a single round trip — there is no batching primitive on `AsyncGroq`.
- *Sync vs async?* **Async fire-and-forget**. Sync would block the per-frame loop for the full open-prompt latency (≈1.5–2 s — open prompt is shorter than production but multimodal latency is dominated by image upload). The score-event path does not depend on the most-recent OpenScout result; it queries an **aggregator that only requires the stream to be at most a few seconds behind real time**, which is fine for retrospective span discovery. The only cost is that score events firing within ~2 s of a delivery's first action frame might miss the **last** observation — but `LOOKBACK_S=25 s` gives the aggregator ample history.
- *Same Groq API key?* **Yes**, but a **separate `AsyncGroq` client** (separate connection pool, separate timeout). Groq rate limits are documented per key, and in practice the existing 0.4 s active-play cadence + 1 fps OpenScout cadence = ~3.5 calls/sec peak, well under typical Llama-Scout 17B per-key TPM. **Mitigation:** failure-mode F1 (§8) wraps the async task in a try/except so a 429 simply drops the observation; the aggregator tolerates gaps.
- *Where in the pipeline?* The hook **must** be in the same per-frame loop, immediately after primary Scout, because that loop is where `frame` and `t0` are co-located and `BallAnalyzer` is reachable. A separate consumer of `_frame_buffer` would need its own thread + reuse of the raw buffer; the current per-frame loop already pays the frame-acquisition cost.
- *New ParallelScoutBuffer?* The aggregator owns its own state; raw frames are still pulled from `_frame_buffer` at score-event time via `_get_frames`. We do **not** need to retain frames inside the aggregator — only `(ts, cls, text_preview)`.

### 3.3 Rate selection (B2) — **proposed answer with reasoning**

**Recommendation: 1 fps target, decoupled from primary Scout cadence, gated by an `OpenScoutRateGate` whose `allow(ts, adaptive_state)` returns:**

| Adaptive state | Gate cadence | Reason |
|---|---|---|
| Active play (`bowlers_end`/`side_on`, `release`/`flight`/`shot`/`post_shot`) | **1.0 s** | Validation §11 used 1 fps; below this, span continuity breaks (§11.7 noted single-frame singletons drive false positives). |
| `runup`, `between_play`, `closeup` | **1.0 s** | These are still potential delivery context; 1 fps is the floor for catching the wide-shot cut. |
| `replay`, `graphic`, `other` | **2.0 s** | Reduce spend; aggregator only needs to keep emitting `replay`/`other` to close spans. |
| `advertisement`, AdaptiveSleep `ad_detected=True` | **paused** (skip) | No cricket content; OpenScout adds zero signal. |
| `BallAnalyzer.alive == False` | **paused** | Capture stopped — nothing to classify. |

**Cost calculation (explicit arithmetic).**

*Match call-volume model:*

| Phase | Wall-time fraction | Seconds per match (3 h baseline) | OpenScout cadence | Calls |
|---|---|---|---|---|
| In-play active (`bowlers_end`/`side_on`, action phases) | ~28 % (40 % of in-play, in-play = 70 % of total) | 0.28 × 10,800 = **3,024 s** | **1 fps** (1 s interval) | **3,024** |
| In-play non-action (`runup`/`between_play`/`closeup`, replay/graphic in-play) | ~42 % (60 % of in-play) | 0.42 × 10,800 = **4,536 s** | **0.5 fps** (2 s interval) | **2,268** |
| Ads / capture paused | ~30 % | 0.30 × 10,800 = **3,240 s** | paused | **0** |
| **Total** | | | | **≈ 5,300 calls/match** |

Range across match-length and active-fraction sensitivity (2.5 h short match with 25 % active up to 3.5 h heavy chase with 45 % active): **≈ 3,500 to 7,000 calls/match**.

*Per-call cost reverse-engineered from the documented anchor.* The header at ```10:10:files/eyes/config.py``` states the production tag+read prompt costs **~\$0.09 / match** at the production cadence. We do not have a public Groq image-token rate sheet that we can defend without recourse to an external page, so we **anchor on \$0.09 / match** rather than guessing token rates:

- Production cadence (AdaptiveSleep average ~1.0–1.5 s effective interval over an in-play match) ≈ **5,000–10,000** calls/match → per-call **≈ \$0.09 / 7,500 ≈ \$0.000012**.
- Open prompt is **shorter** than the production prompt (`max_tokens=220` vs `600`; no STRIP/INFO_PANEL/ACTION sections); image input dominates and is identical, so the open call is **~70 %** of production cost: **≈ \$0.0000084 per call**.
- Conservative bracket (per-call cost): **\$0.000008 to \$0.000014**.

*Total cost.*

- Low: **3,500 × \$0.000008 = \$0.028 / match**
- Mid: **5,300 × \$0.000010 = \$0.053 / match**
- High: **7,000 × \$0.000014 = \$0.098 / match**

**Total estimate: +\$0.03 to +\$0.10 per match** on top of the documented ~\$0.09 / match (```10:10:files/eyes/config.py```).

**Delta vs current:** roughly **+0.3× to +1.1× the current Scout dollar spend**. Point estimate: **~+0.6×** (mid). Operator sign-off required (open question §11.1).

**Caveat.** Groq image-token billing for Llama-4-Scout-17B is opaque from the codebase alone; if image input tokens are billed materially higher than reverse-engineered per-call cost suggests, the upper bound could double. The validation memo §12.6 cross-checks against Fireworks Qwen3-VL at **\$0.044 / 247 frames ≈ \$0.000178 / frame**, but Scout on Groq is documented to be cheaper than that at production rate. **Recommendation:** instrument per-call `usage.total_tokens` × per-token cost on day 1 of shadow mode and re-validate.

**What about ad breaks?** Capture itself is unaffected (the `_capture_loop` keeps appending), but `AdaptiveSleep` stretches primary Scout to 8 s. The rate gate **pauses OpenScout entirely** during `ad_detected` and `phase=advertisement`. This produces aggregator gaps of up to ~25 s during over-break ads — acceptable because score events do not fire during ads (no live ball event) and lookback is 25 s anyway.

---

## §4 Span aggregator design (B3)

### 4.1 State machine

```
State variables (per BallAnalyzer instance):
    current_cls: str | None        # class of the open span, or None
    span_start_ts: float            # opened-at ts of current span
    span_last_ts: float             # ts of most recent obs in span
    span_n: int                     # frames accumulated in current span
    gap_obs: int                    # consecutive non-matching obs since
                                    # last matching obs (within tolerance)
    closed_spans: deque[Span]       # bounded by 90 s wall ts pruning

Span = NamedTuple:
    start_ts: float        # ts of FIRST obs in span
    end_ts:   float        # ts of LAST obs in span
    cls:      str          # action / replay / ad / umpire / other
    n:        int          # # observations
    text_samples: list[str]  # up to 3 verbatim previews for telemetry

Tunables (proposed defaults):
    MIN_SPAN_FRAMES        = 2     # filter 1-frame singletons (§11.4 FP_other patterns)
    SAME_CLASS_GAP_TOL     = 1     # allow 1 dissenting frame to merge
    SPAN_RETENTION_S       = 90.0  # match TAGGED_BUFFER_RETENTION_S
    SOFT_GAP_TOLERANCE_S   = 2.5   # mirror DWR.MAX_CONTIGUOUS_GAP_S
```

### 4.2 Pseudocode

```
def on_observation(ts, cls, text):
    # 0. soft gap: if too long since last obs, force-close (e.g., ad break)
    if current_cls is not None and (ts - span_last_ts) > SOFT_GAP_TOLERANCE_S:
        _commit_span()                 # close whatever was open
        current_cls = None
        gap_obs = 0

    # 1. matching: extend
    if cls == current_cls:
        span_last_ts = ts
        span_n += 1
        gap_obs = 0
        _maybe_record_text(text)
        return

    # 2. dissenting under tolerance: count toward gap, don't close yet
    if current_cls is not None and gap_obs < SAME_CLASS_GAP_TOL:
        gap_obs += 1
        return

    # 3. transition: close current (if any), open new
    if current_cls is not None:
        _commit_span()        # uses span_start_ts, span_last_ts, current_cls, span_n

    current_cls   = cls
    span_start_ts = ts
    span_last_ts  = ts
    span_n        = 1
    gap_obs       = 0
    text_samples  = [text]

def _commit_span():
    if span_n >= MIN_SPAN_FRAMES:
        closed_spans.append(Span(span_start_ts, span_last_ts,
                                 current_cls, span_n, list(text_samples)))
    # singletons are dropped — they're noise

def prune(now):
    cutoff = now - SPAN_RETENTION_S
    while closed_spans and closed_spans[0].end_ts < cutoff:
        closed_spans.popleft()

def spans_in(lo_ts, hi_ts, cls_filter=None):
    return [s for s in closed_spans
            if s.start_ts <= hi_ts and s.end_ts >= lo_ts
            and (cls_filter is None or s.cls == cls_filter)]
```

**Notes.**
- **Min span length 2 frames** at 1 fps ≈ 2 s minimum span — long enough to filter §11 FP_other singletons (`description_ngrams_by_class.json` examples), short enough that brief but real deliveries (4–9 s span at 1 fps = 4–9 obs) sail through.
- **Same-class gap tolerance = 1**: a single dissenting `other` obs between two `action` obs is merged. Higher tolerance regresses §11.7 `d102` (4-consecutive-frame replay corridor false positive).
- **Soft 2.5 s gap close** mirrors `MAX_CONTIGUOUS_GAP_S` in DWR (```85:85:files/delivery_window_recorder.py```) — at 1 fps OpenScout, no obs for 2.5 s means we missed a frame (rate-limit) or ad-break; force-closing is honest.
- **Buffer retention 90 s** matches `TAGGED_BUFFER_RETENTION_S=90.0` (```132:132:files/ball_analyzer.py```) — safe upper bound for `LOOKBACK_S=25 s` plus phantom-event jitter. **No frame buffer extension needed (S3 not triggered).**
- **In-flight span** is queried by `spans_in()` only after `prune()` and `_commit_span()` snapshot — race-free with a single `_open_lock` taken on `on_observation`.

### 4.3 Buffer retention vs frame buffer

The aggregator stores **only metadata** `(start_ts, end_ts, cls, n, text_samples)`, not frames. Memory is trivial (≪1 KB per span; ≤200 spans in 90 s). **No extension to `FRAME_BUFFER_MAXLEN=1200` is needed**: when the recorder picks a span and asks for raw frames via `_get_frames(clip_start, clip_end)`, the existing 60 s raw-buffer headroom (`ball_analyzer.py:130` docstring) covers all spans whose `end_ts ≥ now − 60 s`. Score events arrive promptly (event_ts ≈ now), so all viable spans are within 60 s of now → frames are present. **Stop S3 not triggered.**

---

## §5 Score-event matching algorithm (B5 / B4 here in the memo)

### 5.1 Selection algorithm

The selector is **explicit about the two cases that matter operationally**: a single-candidate case (no ambiguity, use the open-prose span) and a multi-candidate case (ambiguous, defer to validated path). The earliest-span heuristic in §5.2 is **gated** — it runs in a logging-only side channel during shadow mode and is **not** the default behavior in v1.

**Sentinel return values.** `_find_span_open` returns one of:
- `("open_scout_span", (start_ts, end_ts))` — committed selection from the open-prose path.
- `("defer_to_legacy", None)` — explicit defer; recorder must call legacy `_find_span` (RC-7 anchor walk) and then `fallback_pre_event_window` if legacy also returns `None`.

```
def _find_span_open(event_ts) -> tuple[str, Optional[(float, float)]]:
    lo = event_ts - LOOKBACK_S              # 25.0
    hi = event_ts - POST_EVENT_EXCLUSION_S  # 1.5

    candidates = ball_analyzer.span_aggregator.spans_in(
        lo, hi, cls_filter="action")

    # Filter by minimum span duration (1 obs at 1 fps = 0 s; we want ≥2 s)
    MIN_ACTION_SPAN_S = 2.0
    candidates = [s for s in candidates
                  if (s.end_ts - s.start_ts) >= MIN_ACTION_SPAN_S]

    # Reject stale spans whose end is more than MAX_END_TO_EVENT_GAP_S
    # before event_ts (mirror DWR RC-3 sanity)
    candidates = [s for s in candidates
                  if (event_ts - s.end_ts) <= MAX_END_TO_EVENT_GAP_S]

    n = len(candidates)

    if n == 0:
        # No qualifying open-prose span. Defer to legacy path.
        emit_telemetry("[OPEN-SCOUT-SELECT] no_candidates → defer")
        return ("defer_to_legacy", None)

    if n == 1:
        # Unambiguous. The single span IS the live action — no
        # replay-vs-live disambiguation question even arises because
        # there is only one thing to choose from. Commit it.
        s = candidates[0]
        emit_telemetry(
            f"[OPEN-SCOUT-SELECT] single_candidate "
            f"start={s.start_ts:.2f} end={s.end_ts:.2f} n={s.n}")
        return ("open_scout_span", (s.start_ts, s.end_ts))

    # n >= 2: ambiguous multi-span case. Earliest-span heuristic is
    # NOT validated on this codebase's data (§5.2 + §11.2 + §12.1).
    # Default behavior in v1: defer to legacy `_find_span`.
    # Shadow telemetry below records what the heuristic WOULD have
    # picked, so an offline analyzer can validate or reject the
    # heuristic against live multi-span deliveries before any
    # cutover to "use the heuristic in production" can be made.
    candidates.sort(key=lambda s: s.start_ts)
    heuristic_pick = candidates[0]
    emit_telemetry(
        f"[OPEN-SCOUT-SELECT] multi_candidate n={n} → defer_to_legacy "
        f"(heuristic_would_pick start={heuristic_pick.start_ts:.2f} "
        f"end={heuristic_pick.end_ts:.2f}); all candidates: "
        f"{[(round(s.start_ts,2), round(s.end_ts,2), s.n) for s in candidates]}"
    )
    # Persist the heuristic pick + alternatives in window_debug.json
    # under `_alt_open_scout.multi_span_heuristic` for offline
    # comparison against legacy's choice. THIS IS LOGGING ONLY —
    # the recorder does NOT use heuristic_pick when v1 ships.
    return ("defer_to_legacy", None)
```

**Why option (a) — defer multi-span to legacy — over option (b) — apply earliest-span with a logged warning:**

- The earliest-span heuristic has only the §6.2 / §11.7 validation memo to lean on, and that evidence is **explicitly mixed** (`d102` regression, n=6 GT replay).
- Legacy `_find_span` is the **already-shipped, RC-1-through-RC-7 hardened** path — its multi-span behavior (NEWEST→OLDEST walk that picks the latest contiguous `bowlers_end ∧ action` span) has been operational across the entire 215-delivery production audit and the score-event coverage audit.
- Option (a) produces a **strictly bounded** improvement story for v1: where open-prose adds a single high-confidence span the legacy path missed (the dominant case per `window_content_audit.md` §3.2 — 205 / 215 deliveries currently fall back), we win; where ambiguity exists, we lose nothing relative to today.
- Option (b) (apply heuristic + log warning) commits production windows to an unvalidated heuristic on **every multi-span event** until shadow data proves it correct — risk-asymmetric in the wrong direction.
- **Cutover to option (b)** is gated on the §9.4 acceptance criteria specifically applied to the multi-span subset: see §5.2.

### 5.2 Replay disambiguation — heuristic status, gating, and cutover criterion

**Status of the "earliest action span = live, later = replay" heuristic in v1: SHADOW-ONLY.**

The heuristic is **not** the production selection rule when `USE_OPEN_SCOUT_SPANS=1` ships. It runs in two contexts:

1. **Logging side channel.** Whenever `_find_span_open` returns `("defer_to_legacy", None)` because of multi-span ambiguity (§5.1), the heuristic's pick + the full candidate list are persisted into `window_debug.json` under `_alt_open_scout.multi_span_heuristic`. No production behavior change.
2. **Single-candidate case.** When exactly one span survives the filters, there is no heuristic — it is simply the only choice. This is **not** "the heuristic was applied"; it is "no disambiguation was needed". The validation evidence base for committing a single high-confidence span is §11.4 (binary v2 P≈0.77, R≈0.99) plus the RC-3/RC-5/RC-7 staleness/duplicate guards inherited from the legacy path.

**Empirical basis for marking the multi-span heuristic shadow-only:**

- §6.2 (validation memo) endorsed the chronological-ordering prior as a "cheap causal prior" but **noted leaks** when replay leads inside a stitched window (`d102` in §3.2 / §11.7).
- **§11.7** binary v2 span QC regressed on `d102` precisely because Scout's open prose chained kinetic language across replay frames. The corpus has only **6 GT replay rows** — far too thin to support a production-default policy.
- Across-delivery ordering risk: if the `event_ts` lookback (25 s) catches the **previous** ball's replay tail before catching the current ball's live action, that previous ball's replay would be the "earliest" action span. The `MAX_END_TO_EVENT_GAP_S=8 s` filter mitigates this (mirroring DWR RC-3 sanity, ```411:424:files/delivery_window_recorder.py```) but does not eliminate it.

**Cutover criterion for promoting multi-span heuristic to production default.**

The multi-span heuristic flips from shadow-only to production-default ONLY if both of the following are met after the §9.4 shadow run (3–5 matches, ≥600 deliveries):

- **Multi-span coverage:** at least **15 % of deliveries** in the shadow corpus produce ≥ 2 candidates after the §5.1 filters (otherwise the corpus is too small to evaluate the heuristic).
- **Multi-span heuristic accuracy:** in the multi-span subset, the heuristic's pick agrees with the **legacy `_find_span` choice OR the manually-validated true delivery span** (whichever is available) at **≥ 70 %** rate. This **70 % bar mirrors the §9.4 "span overlap with current path ≥ 70 %"** acceptance criterion already established for the overall path.

If multi-span coverage is below 15 %, the heuristic stays shadow-only by default — there is not enough multi-span data to reason about. If accuracy is below 70 %, the heuristic stays shadow-only and is iterated on (e.g., add a `bowlers_end` corroboration gate per §11.3, or adopt `classify_full` multiclass routing) before re-evaluation.

**No production windows are committed by the multi-span heuristic in v1.** This is a hard guarantee.

**Edge case (still relevant under defer-to-legacy):** quick-fire two-ball over where the legacy `_find_span` picks the wrong span and the open-prose path also has multiple candidates. Both paths fail; this is documented as the known degenerate case for §8 F3 and surfaces in `_alt_open_scout` telemetry for offline analysis.

### 5.3 Edge cases

| Case | Behavior | Reasoning |
|---|---|---|
| No `action` span in lookback | Return `None` → recorder falls through to legacy `_find_span` (RC-7 anchor walk) → ultimately `fallback_pre_event_window` | Preserves current safety net. |
| Multiple `action` spans, all within `MAX_END_TO_EVENT_GAP_S` | Return `("defer_to_legacy", None)` so recorder uses legacy `_find_span`; persist the heuristic's would-be pick + full candidate list to `_alt_open_scout.multi_span_heuristic` for shadow analysis | §5.1 multi-span policy: heuristic is shadow-only in v1 (§5.2). |
| Single `action` span, long (e.g., 12 s) | Return as-is; `_span_to_clip_bounds` clamps to `event_ts + MAX_EVENT_DRIFT_S` | Real ball + replay merged into one span; trim is upstream. |
| Span end is **after** `event_ts` | Span is truncated by the upstream rate gate query bound `hi = event_ts − 1.5 s` so end can extend into [hi, event_ts] only if the obs landed there. We allow that — replay starts immediately. | The `_span_to_clip_bounds` clamp handles the post-event tail. |
| Phantom event (`event_ts − last_accepted_event_ts < MIN_INTER_DELIVERY_S=8 s`) | Recorder skips before reaching `_find_span_open` | Existing guard at ```219:240:files/delivery_window_recorder.py``` is preserved. |
| Span overlaps ≥ `MAX_SPAN_OVERLAP_RATIO=0.5` with last consumed span | Recorder discards and falls through to fallback | Existing duplicate-span guard at ```254:266:files/delivery_window_recorder.py``` is preserved. |

---

## §6 Frame reconstruction (B5)

**Proposed answer: re-use existing `_span_to_clip_bounds` + `_get_frames` exactly.**

```
clip_start = max(0.0, span_start - PRE_PADDING_S)              # 2.0 s pre
clip_end   = min(span_end + POST_PADDING_S,                    # 1.5 s post
                 event_ts + MAX_EVENT_DRIFT_S)                  # ≤ event_ts+2.5
frames     = ball_analyzer._frame_source(clip_start, clip_end)  # list[(ts, ndarray)]
```

| Sub-question | Answer | Reasoning |
|---|---|---|
| Which frames | **All** raw-buffer frames in `[clip_start, clip_end]`. The existing path does this (```563:575:files/ball_analyzer.py```). | Subsampling is the classifier's job (`compile_frames_to_mp4` derives FPS from frame count and duration). |
| Output FPS | **`(len(frames)−1) / duration` clamped to `[5, 60]`** — exactly the existing logic in ```340:349:files/gemini_delivery_classifier.py```. | Already tuned; window_content_audit reports 12.88 fps median which is in range. |
| Buffer access | **Lockless `list(deque)` snapshot then filter** — atomic on a deque per Python doc; current `_frame_source` does this. | No new locking surface. |
| Pruned frames | If `clip_start` is older than the raw buffer's tail (`now − ~60 s`), `_get_frames` returns a partial list; `_classify_frames_for_event` checks `len(frames) < MIN_FRAMES_FOR_CLASSIFICATION=4` and emits the `too_few_frames` untrackable result (```473:488:files/delivery_window_recorder.py```). | **Existing safety path is sufficient.** This is the realistic worst case if a score event fires very late after the live action. |

**The only schema change is informational:** `window_debug.json` gets new optional fields `window_source_path = "open_scout_span" | "retrospective_span" | "fallback_pre_event_window"` (extending the existing `window_source` enum) plus the alternate-path snapshot when running shadow telemetry (§7).

---

## §7 Coexistence strategy (B6)

**Recommendation: Option C3 (feature flag) with telemetry-only shadow side-by-side.**

### 7.1 What "C3 + telemetry shadow" means concretely

- Env var `USE_OPEN_SCOUT_SPANS` (default `0`).
- When `0`: existing `_find_span` is the **primary** selector. The new path **still runs** the aggregator and `_find_span_open(event_ts)` and writes its proposed `(clip_start, clip_end, n_frames)` to `window_debug.json` under a new `_alt_open_scout` block — **but its window is not classified by Layer 2.**
- When `1`: `_find_span_open` is primary. The legacy `_find_span` (and on its absence, `fallback_pre_event_window`) is now the alternate that gets logged to `_alt_legacy`. The chosen window's frames are sent to Layer 2.
- Either way, exactly **one** `delivery_window.mp4` and one `layer2.json` are produced per delivery.

### 7.2 Why not C1 (replace) or C2 (full shadow)

- **C1 — Replace:** Risk: the audit shows 205 / 215 windows currently fall back to `fallback_pre_event_window` (`window_content_audit.md` §3.2). Ripping out the fallback before we have shadow data on whether the new path actually wins on those 205 cases is a regression-by-design. **Rejected.**
- **C2 — Full shadow:** Both paths produce mp4 + L2 calls; both are persisted. Risk: doubles per-delivery Qwen+Gemini cost (≈\$0.05–\$0.10 → ≈\$0.10–\$0.20 per delivery × 215 ≈ \$22–\$43 per match). Unacceptable absent operator sign-off. Even at lower cost, doubled L2 latency could starve the 2-worker `dwr-worker` pool (```468:472:files/ball_analyzer.py```). **Rejected** in favor of C3+telemetry.
- **C3 — Feature flag:** Cheap. The aggregator runs always (cost is OpenScout itself, not L2); flag controls only which `(clip_start, clip_end)` is fed to L2. `_alt_*` block in `window_debug.json` enables offline overlap analysis exactly the way `compare_qwen_scout_open.py` (`files/scripts/scout_validation_research/compare_qwen_scout_open.py`) compared models on frozen corpus. **Recommended.**

### 7.3 Rollout sequencing

1. **Session 1 (impl):** ship OpenScout + aggregator + `_find_span_open` + `_alt_open_scout` telemetry. **Default flag off.** End-state: shadow data accumulates on every match.
2. **Session 2 (analysis):** after **3–5 production matches** (target ≥600 deliveries), run an offline analyzer (analogous to `analyse_window_results.py` already in `files/`) computing per-delivery: did `_alt_open_scout` produce a span? Did its bounds overlap the bounds Layer 2 actually saw? Did the `length` / `bounce` / `shot_type` extraction differ when the chosen path differed? Decision: keep flag off, flip to default on, or roll back.
3. **Cutover:** flip default `USE_OPEN_SCOUT_SPANS=1`. Keep legacy as the alternate for 1–2 matches before final removal.

**This sequencing also satisfies the "validation against 215-delivery production dataset" line in B8.**

---

## §8 Failure modes (B7)

| ID | Failure | Behavior with proposed design | Detection / observability |
|---|---|---|---|
| **F1** | Groq 429 / Scout API down for OpenScout | Async task swallows exception; aggregator simply receives no obs for the duration. After `SOFT_GAP_TOLERANCE_S=2.5 s` of no obs, any open span is force-closed. `_find_span_open` returns `None` for events with no spans → recorder falls through to legacy path. **Primary Scout is unaffected** because OpenScout has its own `AsyncGroq` client. | New counter `open_scout_api_errors` exposed via `BallAnalyzer.stats()`. Log line `[OPEN-SCOUT] error: …` once per error class with rate suppression. Metric: `open_scout_observation_rate` ratio of obs received vs frames at-risk. |
| **F2** | Score event fires but no `action` span in window | `_find_span_open` returns `None` → recorder runs legacy `_find_span` → if that also returns `None`, `fallback_pre_event_window` (existing). | `window_source_path` field in `window_debug.json` records the actual selector (`open_scout_span` / `retrospective_span` / `fallback_pre_event_window`). Aggregate fallback rate per match in dashboards. |
| **F3** | Multiple `action` spans, wrong one chosen (the d102 leak) | The mp4 and L2 result reflect a replay window. Downstream Qwen often returns plausible `length`/`bounce` (window_content_audit §4.3 noted this). | `_alt_open_scout` block records ALL candidate spans + selected index. Telemetry emits `[OPEN-SCOUT-SELECT] candidates=N chosen=k start_ts=… end_ts=…` per delivery. Offline: replay against ground-truth labels (215-delivery production dataset). |
| **F4** | OpenScout classification quality drift (e.g., model drift, prompt scaffold echo loosens, paraphrase) | Aggregator emits implausible class distributions: e.g., `action` span fraction surges to >80 % (real cricket is ~30 %). | Per-match histogram `open_scout_class_dist` vs §11 baseline (`description_ngrams_by_class.json` distribution). Alert thresholds: action fraction outside [10 %, 60 %] over a 100-frame rolling window. |
| **F5** | Raw `_frame_buffer` drops frames before span is materialized into mp4 | `_get_frames(clip_start, clip_end)` returns fewer frames; `MIN_FRAMES_FOR_CLASSIFICATION=4` triggers `too_few_frames` untrackable result (existing). | `[DWR] window #N too few frames` log persists. New: `window_debug.json` records `frame_buffer_oldest_ts` so we can confirm whether buffer truly dropped vs the span was simply outside the buffer. |

**Additional codebase-specific failure modes worth flagging.**

- **F6 (capture pause):** `_capture_loop` exits on `CG.CGWindowListCreateImage` returning None or zero size (```1872:1880:files/ball_analyzer.py```). Both buffers stop growing; aggregator sees no obs; spans force-close after 2.5 s. This is consistent and acceptable — when capture resumes, OpenScout starts feeding obs again and spans re-open.
- **F7 (innings change):** `_tagged_buffer` is **not** invalidated on innings change (`on_innings_change` only resets `_roi_cache`, ```671:679:files/ball_analyzer.py```). Mirroring this, the aggregator should **not** clear closed spans on innings change either; the `90 s` retention naturally bounds cross-innings leakage. (Open question: do we want explicit clear at innings change? §11.5.)
- **F8 (DRS freeze):** `_drs_frozen_snapshot` (```548:562:files/ball_analyzer.py```) freezes the raw buffer for review. OpenScout still runs, aggregator still records spans. After DRS resumes, the recorder may pick a pre-freeze span. This is correct behavior — DRS reviews don't fire score events.

---

## §9 Test plan (B8)

### 9.1 Unit tests (~80 LOC)

- `test_span_aggregator_basic.py`
  - Singleton frame is dropped (n=1, MIN_SPAN_FRAMES=2).
  - Two-frame span closes correctly.
  - One dissenting frame between two same-class frames is absorbed via `SAME_CLASS_GAP_TOL=1`.
  - Two dissenting frames force-close the span.
  - 2.5 s gap force-closes regardless of class match.
  - `prune(now)` correctly discards spans older than `SPAN_RETENTION_S`.
  - `spans_in(lo, hi, cls)` correctly filters by overlap and class.
- `test_find_span_open.py`
  - No spans → `None`.
  - One short (<2 s) action span → `None`.
  - One sufficient span fully inside lookback → returned.
  - Two sufficient spans, both within `MAX_END_TO_EVENT_GAP_S` → earliest by `start_ts` returned.
  - One stale span ending 10 s before event → filtered out.

### 9.2 Integration tests (~80 LOC)

- `test_dwr_open_scout_path.py` — feed a synthetic stream of `(ts, cls)` tuples into a `BallAnalyzer` with stubbed `_frame_source` returning ndarray frames; call `classify_for_score_event` with `USE_OPEN_SCOUT_SPANS=1`; assert `window_source` is `open_scout_span`, the `(clip_start, clip_end)` matches expectation, and the alternate-path snapshot is in `window_debug.json` under `_alt_legacy`.
- `test_dwr_open_scout_fallback.py` — same as above with no `action` spans; assert fallback to legacy `_find_span` then to `fallback_pre_event_window`.

### 9.3 Replay validation against frozen corpora

- **247-frame validation set** (`scout_responses_open.jsonl`):
  - Replay the JSONL into the aggregator (using each row's GT `time_in_clip_s` as ts and `classify_full(open_description, classify_v2_final)` as cls).
  - For each of the **15 clips**, compute the action span(s) the aggregator would emit; compare against human action spans (the §5 / §11.7 span-QC harness already does this work via `analyze.py` → reuse).
  - **Acceptance gate:** ≥ **13/15** clip overlap pass (matches §11.7 binary v2 baseline of 13/15). This re-uses the existing `span_simulation_*` harness in `rule_iteration_metrics.json`.
- **215-delivery production dataset** (`files/logs/deliveries/20260430_195352/`):
  - The aggregator cannot replay against this corpus directly because `window_debug.json` does not contain per-frame open-prose narration (`window_content_audit.md` §2.3 — that's the very gap motivating this work).
  - **Compromise:** validate **structural** consistency: feed the sparse `tags[]` (Scout JSON, not open prose) into a **mock aggregator** that maps `bowlers_end ∧ action_phase → action`, and compare the resulting `_find_span_open` choice against the existing `window_source` in each `window_debug.json`. This validates the **selection algorithm**, not the perception layer.
  - **Full perceptual validation requires a re-Scout pass with the open prompt over the 215 saved `delivery_window.mp4` files** — out of scope for this design memo, but called out in the implementation session.

### 9.4 Live shadow run criteria

Running with `USE_OPEN_SCOUT_SPANS=0` in production logs `_alt_open_scout` for every delivery. Cutover gates:

- **3–5 matches**, target ≥ **600 deliveries** total.
- **≥ 50 %** of deliveries have a non-null `_alt_open_scout` span (proves the perception layer is firing on real broadcasts).
- **Span overlap with current path** ≥ **70 %** across the deliveries where both paths produce a span. (Below 70 % means the two paths fundamentally disagree; needs investigation before cutover.)
- **No regression on `MIN_INTER_DELIVERY_S` phantom skips, `MAX_SPAN_OVERLAP_RATIO` duplicate-span skips, or `too_few_frames` untrackable rate.**
- **Layer 2 `length` non-unknown rate** under shadow path ≥ existing 100 % (current baseline per `window_content_audit.md` §4.1). This is the floor; positive lift on `line` or `shot_side` (which currently have 14.6 % / 12.2 % unknowns) would justify cutover.

### 9.5 Rollback

Single env-var flip: `USE_OPEN_SCOUT_SPANS=0`. The aggregator keeps running (cheap, telemetry only). To fully disable: env var `USE_OPEN_SCOUT=0` short-circuits the per-frame `asyncio.create_task` spawn and frees the second `AsyncGroq` client.

---

## §10 Implementation scope

### 10.1 Per-component LOC

| Component | LOC | Files (proposed) |
|---|---|---|
| `OpenScout` class (single Groq round-trip, open prompt frozen from `run_scout_open.py:32–41`, normalization to {action, replay, ad, umpire, other}) | **~80** | `files/eyes/open_scout.py` (NEW) |
| `OpenScoutRateGate` (per-state cadence map, pause logic) | **~40** | same file or `files/eyes/open_scout_rate.py` (NEW) |
| `SpanAggregator` (state machine + closed_spans deque + prune + spans_in) | **~150** | `files/span_aggregator.py` (NEW) — siblings with `delivery_window_recorder.py` |
| `BallAnalyzer.record_open_classification`, `__init__` plumbing, telemetry counters | **~50** | `files/ball_analyzer.py` (edit) |
| `DeliveryWindowRecorder._find_span_open`, env-var gate, `_alt_*` block in `_write_window_debug` | **~80** | `files/delivery_window_recorder.py` (edit) |
| Hook in per-frame loop after `await vision.describe(...)` (background-task spawn + rate gate) | **~30** | `files/test_pipeline.py` (edit) |
| Re-use of `classify_full` / `classify_v2_final` from validation script (verbatim copy or refactor to a real module) | **~0–30** | move `files/scripts/scout_validation_research/classify_descriptions.py:252–326` into `files/eyes/open_scout_classify.py` if production-grade module is desired (recommended) |
| **Tests** | **~200** | `files/test_span_aggregator.py`, `files/test_dwr_open_scout_*.py` |
| **Total** | **~430–650** | |

### 10.2 Phasing

**Recommendation: 2 sessions.**

- **Session 1 (~3–4 h Opus):** ship all production code listed above with `USE_OPEN_SCOUT_SPANS=0` default. Includes telemetry shadow (`_alt_open_scout` writes). Acceptance: unit + integration tests pass; one synthetic 30-min live run shows aggregator firing and `_alt_*` data persisting.
- **Session 2 (~2 h, post-3-matches):** offline analyzer (mirror `analyse_window_results.py`) computing the cutover criteria from §9.4. Produce a follow-up memo with the verdict; flip the flag if criteria pass.

**Do not attempt to implement Session 1 in a Composer-2 session** — the multi-file edit in `ball_analyzer.py` and the careful preservation of consumers in §2.4 require Opus-grade reasoning. Composer-2 is appropriate for the offline analyzer in Session 2.

### 10.3 Dependencies / sequencing

- Hard dependency: `classify_descriptions.py` rules are frozen at `classify_v2_final` v2 (§11.5 of validation memo). If a v3 lands, the production module must follow.
- Soft dependency: graphify index (`files/graphify-out/GRAPH_REPORT.md`) refresh after Session 1 edits — required by repo `.cursor/rules/graphify.mdc`.
- No dependency on the §11 follow-up "tiny learned scorer on description text" (validation memo §6.1.5) — that workstream is orthogonal and can proceed in parallel.

---

## §11 Open questions for operator (Anmol)

1. **Cost ceiling.** §3.3 estimates **+\$0.03 to +\$0.10 per match** (~+0.3× to +1.1× the documented ~\$0.09 baseline at ```10:10:files/eyes/config.py```; mid-point ~+\$0.05, ~+0.6×). The reverse-engineered per-call cost is anchored on the \$0.09/match comment, not on a token-rate sheet — **acceptable, or do we want a hard daily budget cap and drop OpenScout to 0.5 fps active (degrades aggregator span continuity per §11.7) or skip OpenScout outside `BURST_DURATION` windows entirely (requires score-event prediction, not in scope)?** Day-1 shadow telemetry will measure `usage.total_tokens` per call to validate the estimate; flag if real cost exceeds the upper bound.
2. **Multi-span policy after shadow validation.** §5.1 commits to **defer multi-candidate cases to legacy `_find_span`** in v1 (option (a)) and runs the earliest-span heuristic shadow-only with the §5.2 cutover criterion (≥ 15 % multi-span coverage AND ≥ 70 % heuristic accuracy in the multi-span subset). Open question for the operator: **after the §9.4 shadow run completes, do we accept the multi-span earliest-span heuristic as the production default if both criteria are met, or do we permanently defer multi-span cases to legacy regardless of shadow numbers?** The "permanent defer" stance is more conservative and bounds the worst-case regression to "legacy multi-span behavior, which we already ship today"; the "accept on metrics" stance opens an explicit upgrade path. Recommendation: **accept on metrics**, but the operator should commit before the shadow analyzer is written so the analyzer's output is decision-ready, not exploratory.
3. **`bowlers_end` cross-check.** The current `_find_span` requires Scout JSON `camera_view==bowlers_end ∧ phase∈action`. The new path uses **prose wide-camera detection** (§11.4 binary v2) which is a different concept (camera framing, not delivery moment). Should `_find_span_open` additionally require **at least one corroborating `bowlers_end` JSON tag** in the span window from the existing `_tagged_buffer` (a "two-source agreement" gate), or is open-prose alone sufficient? **Recommendation:** start without the gate (purer signal); add it if shadow data shows excess false action spans.
4. **`umpire` / `replay` channels — drive any decisions?** The aggregator emits these classes for free. They are not used by `_find_span_open` today. Should an `umpire` span at `event_ts ± 5 s` veto delivery classification (e.g., DRS-adjacent boundary calls)? Out of scope for v1 unless operator wants it pre-wired.
5. **Innings-change span clearing.** `BallAnalyzer.on_innings_change` does not currently clear `_tagged_buffer`. Should the new `closed_spans` be cleared on innings change? **Recommendation:** no (90 s retention is short enough), but flag.
6. **Module home for `classify_full`.** Currently lives under `files/scripts/scout_validation_research/classify_descriptions.py`. Production code importing from `scripts/` is unprecedented in this repo. **Recommendation:** copy/move the relevant functions (`classify_v1`, `classify_v2_final`, `classify_full`, `is_ad_pattern`, `is_replay_pattern`, plus the keyword constants) into a new `files/eyes/open_scout_classify.py` and have the validation script import from there. **Operator decide** whether to move-and-import or copy-and-diverge.
7. **Telemetry log volume.** `_alt_open_scout` per-delivery JSON adds ~1 KB to each `window_debug.json`. With 215 deliveries / match, that's ~215 KB / match — trivial. But if we also embed full open-prose text per obs (~300 chars × ~200 obs = 60 KB / match), we may want gzip on disk. **Operator decide** verbosity.

---

## §12 Limitations and risks

1. **Replay corpus is too small.** §11.7 / §10.2 of the validation memo reported only 6 GT replay rows; the "earliest action span = live" heuristic has minimal empirical support. **Risk: F3 (§8) materializes silently** — Layer 2 returns plausible `length`/`bounce` from a replay window and we ship a believable but wrong delivery. Mitigation: shadow-mode telemetry + the §9.3 replay validation against the 247-frame corpus + manual spot-checks.
2. **Open-prose precision plateau at ~0.77.** §11.4 reports binary v2 `P=0.772` — meaning ~23 % of spans the aggregator emits as `action` are actually `replay`/`other`/idle wide. We rely on `MIN_ACTION_SPAN_S=2 s` and `MAX_END_TO_EVENT_GAP_S=8 s` to filter, but the FP precision ceiling is an inherent property of `classify_v2_final` until §11.8's "tiny learned scorer" lands or §11.6 multiclass routing is adopted. **Risk: per-match false-positive deliveries.**
3. **No bounce-instant proof.** This design does **not** improve bounce-frame visibility (`window_content_audit.md` §1, §5.2). It improves the **temporal placement** of the window, not the per-frame phase resolution. Bounce work is orthogonal (§7 of the audit's recommendations).
4. **Capture FPS coupling.** `CAPTURE_FPS=2` (`config.py:43`) is the headline rate; effective per-frame loop rate is `AdaptiveSleep.get_sleep_time()`. OpenScout gates on `time.time()` not on capture frame count, so if capture stalls, OpenScout obs density drops naturally — but the aggregator's `SOFT_GAP_TOLERANCE_S=2.5 s` may misclassify a short capture stall as a real class transition. Mitigation: F6 (§8) — accept the force-close behavior, log it.
5. **`AsyncGroq` client failure modes.** Existing `Vision._scout_call` swallows exceptions and returns `None` (```492:494:files/eyes/vision.py```); the OpenScout path will mirror this. We are **not** adding retry logic — Groq's internal retries (per the v6c determinism investigation `scout_v6c_determinism_decision.md`) are sufficient.
6. **Stop-condition status.**
   - **S1 (code path not found):** not triggered. Score-event handler, frame buffer, recorder, and per-frame loop are all located and cited.
   - **S2 (replacement impractical):** **partially triggered** — `fallback_pre_event_window` has many consumers (`window_source`, `window_reason`, `_alt_*` shadow telemetry, downstream `predictions.json`/`layer2.json` joiners). C3 coexistence respects this.
   - **S3 (frame buffer insufficient):** **not triggered** — 60 s raw buffer + 90 s aggregator retention is enough.
   - **S4 (Scout rate over budget):** **conditional** — at 1 fps strict the budget is acceptable per §3.3 estimate. Operator sign-off in §11.1.
7. **Ground-truth quality.** Validation rests on a single labeled session (`20260420_214218`, 9 positive clips) plus 6 negatives from `20260430_195352` (§2.1 of validation memo). We are extrapolating to live broadcasts whose framing conventions may differ. Mitigation: shadow telemetry surfaces drift early (§8 F4).

---

*End of memo. Implementation deferred to a separate Opus session per §10.2; no production code written here.*
