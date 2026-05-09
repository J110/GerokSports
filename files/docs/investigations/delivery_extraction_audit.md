# Delivery extraction audit — Path 1 (Scout → span assembly → Qwen handoff)

**Date:** 2026-05-01  
**Scope:** Investigation only (no pipeline code changes). Step 1 characterization for Paths 2–3 (prompt + model eval).  

**Driving questions**

- **Q1.** Does pipeline telemetry suffice to measure **delivery extraction accuracy** (frame window vs ground truth)?  
- **Q2.** What is the **clustering / span-selection logic**: which signals feed it, and how do Scout outputs become `[start,end]` for the classifier?

---

## 1. Executive summary

**Outcome classification: 2 — Adequate telemetry + multi-signal clustering**

- **Per-ball triggering** is **`ball_detector.detect` → `ball_event`** (`test_pipeline.py`), not Scout. Scout does **not** decide *whether* delivery analysis runs on a structural legal-ball event (subject to enqueue gates).
- **Frame-range assembly** for the default retrospective path is **Scout-heavy**: timestamps of `camera_view` + `frame_phase` from the tagged buffer drive `DeliveryWindowRecorder._find_span`, with time-based phantom/duplicate/staleness guards that do **not** re-read Scout into `ball_event` for agreement.
- **Telemetry:** Pipeline tees reliably show **`[DELIVERY ENQUEUED]`**, **`[SCOUT]`**, and **`DETAIL|…`** lines. **`[DWR]`**, **`GEMINI OK` / `[L2]`**, and **`[ASYNC-DA]` completions** were **not observed** in a broad grep over `logs/pipeline-*.log` (Apr 2026 sample) — STOP **S3** (tags in code vs absent in common tee sink). Accuracy work should assume **`window_debug.json`** under delivery save dirs and/or aligning alternate log sinks, not tee-only prose.

**Recommendation:** Proceed with Path 2–3 investigations **bounded** by: (a) separating **enumeration errors** (ball detector / scorer vs scorecard) from **window errors** (DWR span/padding/fallback vs broadcast video); (b) treating Scout prompt iteration as targeting **anchor quality & span coherence**, not enqueue count.

---

## 2. Pipeline architecture (file:line)

### 2.1 Scout (1a) — invocation, prompt version, schema

| Item | Location |
|------|-----------|
| Prompt **`SCOUT_PROMPT`** | ```83:215:files/eyes/vision.py``` — comments document **Part B V5** (2026-04-24); extended JSON (**`frame_phase`**, **`ball_position`**) from 2026-04-19. |
| Groq model id | ```15:15:files/eyes/config.py``` — **`meta-llama/llama-4-scout-17b-16e-instruct`**. |
| **Per-frame async call** | ```6052:6056:files/test_pipeline.py``` — `await vision.describe(frame, vision_hint)`. |
| **Normalize + INFO line** | ```355:376:files/eyes/vision.py``` — sets `last_camera_view`, `last_frame_phase`, `last_ball_position`, strip/overlay flags; logs **`[SCOUT] … cam= … phase=`**. |

**Output schema (after normalisation)**

- Booleans / flags from JSON tag: **`has_strip`**, **`has_overlay_stats`**, **`drs_review`**.
- **`camera_view`** (canonical set + aliases): `bowlers_end`, `side_on`, `closeup`, `replay`, `graphic`, `ad`, `other` (subject to `_normalise_camera_view`: `ADVERTISEMENT` → `ad`, overlay-without-strip → `graphic`, no-strip active-view demotion — ```382:418:files/eyes/vision.py```).
- **`frame_phase`**: runup/release/flight/shot/post_shot/fielder_reaction/replay/between_play/graphic/advertisement/other (+ aliases) — ```420:441:files/eyes/vision.py```.
- **Strip / overlays / ACTION** remain in textual tail (STEP 2–4).

### 2.2 Tagged buffer → “clustering” (1b core)

| Item | Location |
|------|-----------|
| **Write tagged frames** | ```6083:6095:files/test_pipeline.py``` → `BallAnalyzer.record_tagged_frame(...)`. Only views `bowlers_end`/`side_on`/`replay`; includes **`frame_phase`**. ```608:636:files/ball_analyzer.py``` |
| **Retrospective contract** | ```1:27:files/delivery_window_recorder.py``` — score event primary; Scout tags supporting; Gemini/Qwen **`is_valid_delivery`** as fallback safety net when no span. |
| **`on_scout_tag` on recorder** | ```165:167:files/delivery_window_recorder.py``` — histogram only (`_stats["tag:…"]`). **Comment drift STOP:** ```6097:6102:files/test_pipeline.py``` still describes “SOLE input” to a window **state machine**; implementation is **`classify_for_score_event` retrospective span**, not open/close FSM driven here. |

### 2.3 Score event → enqueue → classify

| Item | Location |
|------|-----------|
| **Ball detector output** | `ball_event = ball_detector.detect(...)` ```9572:9572:files/test_pipeline.py``` |
| **`_real_delivery_types` + enqueue** | ```9714:9770:files/test_pipeline.py``` — `_evt_is_real`, absorbed gate, **`ball_analyzer.enqueue_delivery_analysis(...)`**. |
| **`[DELIVERY ENQUEUED]` log** | ```9784:9791:files/test_pipeline.py``` — `dnum`, `evt`, `runs`, `method`, pending flag. |
| **Classifier stack** | Default: `BallAnalyzer._run_gemini_delivery_analysis` ```681:751:files/ball_analyzer.py``` → **`DeliveryWindowRecorder.classify_for_score_event`** ```179:314:files/delivery_window_recorder.py``` → **`_clf.classify_frames`** (production `Layer2Classifier` when **`USE_LAYER2=1`** — ```407:418:files/ball_analyzer.py```). |

### 2.4 Scout output consumers (`camera_view` / `frame_phase` / bowlers_end)

| Consumer | Location | Purpose |
|----------|----------|---------|
| `BallAnalyzer.record_tagged_frame` | ```608:636:files/ball_analyzer.py``` | Buffer `(ts, frame, camera_view, frame_phase)` for legacy VLM slice + recorder tag reads. |
| `BallAnalyzer.on_scout_tag` / `recorder_tick` | ```577:606:files/ball_analyzer.py``` → DWR `on_scout_tag` | **Counters only** on DWR. |
| **AdaptiveSleep** | ```6115:6126:files/test_pipeline.py``` | **`on_camera_view`**, **`on_frame_phase`** — polling cadence, not boundaries. |
| **Scoreboard** | ```6116:6121:files/test_pipeline.py``` `scoreboard.on_camera_view` | XI-reject / live-evidence semantics (documented inline). |
| **`DeliveryWindowRecorder._find_span`** | ```328:425:files/delivery_window_recorder.py``` via `_get_tags` | **Uses `camera_view` + `frame_phase`** for retrospective span selection. |
| **`Vision._normalise_*`** | ```382:441:files/eyes/vision.py``` | Guards bad tags (graphic/ad vs bowlers_end). |
| **Legacy `analyze_last_delivery`** | ```1026:1162:files/ball_analyzer.py``` | Phase-prioritized **discrete frame picks** from tagged buffer (`USE_LEGACY_VLM` / trajectory). |

---

## 3. Clustering logic (pseudocode)

**Naming:** Production “clustering” is **`_find_span` + `_span_to_clip_bounds`** inside **`DeliveryWindowRecorder`**, invoked at **score-event time**, not a streaming Scout-only aggregator.

```
on each score_event with event_ts:
  phantom_guard: if event_ts - last_accepted_event_ts < MIN_INTER_DELIVERY_S → SKIP

  span = FIND_SPAN(event_ts):
    window = [event_ts - LOOKBACK_S, event_ts - POST_EVENT_EXCLUSION_S]
    tags = sorted tagged_buffer entries with ts in window  // includes view + phase

    walk tags NEWEST → OLDEST:
      FOR each tag (tag_ts, frame, view, phase):
        is_bowlers = (view == "bowlers_end")
        is_action_phase = phase in {release, flight, shot, runup}   // RC-7

        IF is_bowlers AND NOT is_action_phase:
           LOG PHASE-REJECT; IF span_already_open THEN close span BREAK
           CONTINUE

        IF is_bowlers AND is_action_phase:
           IF span_open AND (prev_target_ts - tag_ts) > MAX_CONTIGUOUS_GAP_S:
              BREAK   // probable missing cut between deliveries
           open/extend span: span_end youngest such tag; span_end tag_ts oldest added
           prev_target_ts = tag_ts

        ELSE IF span_open:
           BREAK   // broke bowlers_end / action-phase chain

      IF gap(event_ts - span_end) > MAX_END_TO_EVENT_GAP_S: span = ∅  // stale

  duplicate_guard: overlap(span, last_consumed_span) > ratio → span = ∅

  IF span:
     clip_start = span_start - PRE_PADDING_S
     clip_end = min(span_end + POST_PADDING_S, event_ts + MAX_EVENT_DRIFT_S)
     frames = raw_buffer.clip(clip_start, clip_end)
     source = "retrospective_span"
  ELSE:
     clip_start = event_ts - FALLBACK_LOOKBACK_S
     clip_end = event_ts + MAX_EVENT_DRIFT_S
     frames = raw_buffer.clip(...)
     source = "fallback_pre_event_window"

  classify_frames(frames) → Layer2/Qwen path; persist window_debug.json if save_dir set
```

**Signals consumed**

| Signal | Role |
|--------|------|
| **Scout `camera_view`** | Must equal **`bowlers_end`** to contribute to span. |
| **Scout `frame_phase`** | RC-7: anchor/extension only if phase ∈ **`{release, flight, shot, runup}`**. |
| **Inter-tag Δt** | `MAX_CONTIGUOUS_GAP_S` (default 2.5s): breaks continuity. |
| **`event_ts` geometry** | `POST_EVENT_EXCLUSION_S`, `MAX_END_TO_EVENT_GAP_S`, phantom + overlap guards — **timing from score-event path**, not Scout. |
| **`ball_event` type/runs** | Passed into classification context; **not** used inside `_find_span` to veto Scout tags. |

**Deprecated / dormant path:** `DeliveryBurstTracker` + per-frame **`is_delivery_frame`** on capture is **explicitly deprecated** (“remain deprecated”) — ```1908:1912:files/ball_analyzer.py```. Do not describe it as current Path 1b.

**Legacy path (fallback flags):** `analyze_last_delivery` temporal slice **`[T−15s,T−2s]`** (etc.) + **phase-priority** sampling from `_tagged_buffer` — ```991:1162:files/ball_analyzer.py``` — separate from DWR retrospective.

---

## 4. Telemetry inventory and sufficiency

### 4.1 Tags (code), when they fire, payload

| Tag / pattern | When | Typical payload |
|---------------|------|-------------------|
| **`[SCOUT]`** | Every successful `Vision.describe` | `frame_type`, `strip`, `overlay`, `drs`, **`cam=`**, **`phase=`**, timings |
| **`[DELIVERY ENQUEUED]`** | Non-skipped enqueue with pending async result | **`dnum`**, **`evt`**, **`runs`**, **`method`**, `submit_ms` ```9784:9791:files/test_pipeline.py``` |
| **`[DELIVERY SKIPPED]` / `[DELIVERY]`** | Skip reason or synchronous result | Commentary + timing ```9792:9801:files/test_pipeline.py``` |
| **`[DELIVERY-AB]`** | Comparison harness present | Snapshot vs three-layer timing ```9840:9850:files/test_pipeline.py``` |
| **`[QUALITY]` / `[QUALITY-LOW]`** | Sync delivery result path | Unknown-field counts ```9802:9839:files/test_pipeline.py``` |
| **`[DWR] window #…`** | `DeliveryWindowRecorder._classify_frames_for_event` | `source`, `frames`, **`span=clip_start->clip_end`**, reason ```452:454:files/delivery_window_recorder.py``` |
| **`PHASE-REJECT`** | RC-7 anchor rejects | ts, view, phase ```383:388:files/delivery_window_recorder.py``` |
| **`[D#] GEMINI OK` / `GEMINI REJECT`** | `BallAnalyzer._log_gemini_result` | Fields + **`window=…`** ```1329:1354:files/ball_analyzer.py``` |
| **`[L2]` / `[L2-DENSIFY]`** | `Layer2Classifier` success / densify strip | timings, routed fields ```545:577:files/layer2_classifier.py``` |
| **`[ASYNC-DA] submitted/completed`** | Async worker bookkeeping | **`dnum`**, pending counts ```827:865:files/ball_analyzer.py``` |
| **`DETAIL|`** | Frame summary | **`ball_event_*`**, delivery_* snapshot, scout strip preview (not normalized cam/phase fields) ```10551:10608:files/test_pipeline.py``` |
| **`[TAGS]`** (30s cadence) | Capture thread buffer stats | tagged_buffer phase histograms ```1937:1943:files/ball_analyzer.py``` |

### 4.2 Sample tee lines

- **`[SCOUT]`** (non-ANSI excerpt): From `pipeline-2026-04-26-153016-csk-gt-v5-eight-fix-bundle.log`: `cam=bowlers_end phase=between_play` alongside `Fx VISION`.
- **`[DELIVERY ENQUEUED]`**: From **`pipeline-2026-04-30-gt-rcb-live.log`**, e.g. `dnum=1 evt=DOT runs=0 … method=gemini_async`.

### 4.3 Sufficiency (per delivered ball, tee vs artifacts)

| Question | Tee alone | Tee + `[SCOUT]` + `DETAIL` + disk **`window_debug.json`** |
|----------|-----------|------------------|
| Did Scout classify frames “correctly”? | Partially — `[SCOUT]` gives **normalised tags** vs time/F; no automatic GT without video | Stronger — align JSON tag preview + timestamps to video |
| Did clustering emit a logical boundary? | **Often weak** — `[DWR]` not seen in **`logs/pipeline-*.log`** sample | Strong — **`window_debug.json`** lists **`clip_*_ts`, `tags[]` with `camera_view`, `frame_phase`** ```532:554:files/delivery_window_recorder.py``` |
| What frame **time range** reached Qwen/L2? | Same gap as above unless `window_debug`/`[DWR]` appears | **`_window_start_ts` / `_window_end_ts`** on result ```512:517:files/delivery_window_recorder.py``` |
| What did Qwen/L2 **return**? | **Often weak for async tee** — `DETAIL` may still show placeholders while pending; **`[L2]`** lines not found in sampled pipeline tees | **`layer2.json`** sidecar; completion logs if routed to cricket file handler |

**Bucket:** Operational classification **between Adequate and Weak for tee-only** Path 1 end-to-end; **Adequate → Strong when delivery save dirs** are retained.

---

## 5. Bounce-window cross-check (Scout phases)

There is **no dedicated Scout `bounce` phase**. Bounce proximity is inferred indirectly:

- **DWR anchors** allow **`runup` | `release` | `flight` | `shot`** ```107:109:files/delivery_window_recorder.py``` — the clip is padded before/after the span ```54:62:files/delivery_window_recorder.py``` ```427:437:files/delivery_window_recorder.py```.
- **Optional `ball_position`** is only validated for **`release`/`flight`/`shot`** ```443:453:files/eyes/vision.py``` — currently **stored**, not plugged into `_find_span` for geometry.

**Reliability:** Bounded by Scout phase accuracy — same RC-7 note as code comments: **`between_play` / `post_shot` mis-tagged as action phases** blows anchor quality (“Part B” prompt/model territory). **`_normalise_frame_phase`** cross-checks ad/graphic/replay ```420:436:files/eyes/vision.py```.

---

## 6. Outcome classification (evidence mapping)

| Criterion | Evidence |
|-----------|----------|
| **≠ Outcome 4** | `_find_span` **requires** Scout `bowlers_end` **+ action phases** — Scout is structural for span discovery, not “informational only.” ```368:407:files/delivery_window_recorder.py``` |
| **≠ pure Outcome 1** | **Ball event + timing guards** are co-primary with Scout for **which moment** fires analysis and rejects phantoms; fallback window can bypass Scout absence ```276:282:files/delivery_window_recorder.py``` |
| **⇒ Outcome 2** | Multi-signal: **BED/score-event path + Scout tags + time heuristics + optional classifier `is_valid_delivery`** |

---

## 7. Recommendations

**If Outcome 2 (this audit):**

- **Path 2 (Qwen prompt):** Scope to clips already chosen by **`retrospective_span` vs fallback** — characterise **`is_valid_delivery`** / abstention interplay on fallback-heavy innings.
- **Path 3 (model eval):** Join **`dnum`** from **`[DELIVERY ENQUEUED]`** to **`layer2.json`** / `window_debug.json` paths; define metrics for span vs ESPN ball timecodes separately from field accuracy.

**If treating tee as authoritative (anti-pattern today):**

- Add **explicit tee-forwarding or TEST-channel mirroring** for **`delivery_window_recorder`** + **`[ASYNC-DA]`** + **`[L2]`** STOP **S3** (~1–2h instrumentation) — then re-tee capture.

---

## 8. Limitations and uncertainties

1. **`on_scout_tag` comment drift** — maintenance risk for future refactors STOP **documentation-only** ambiguity.  
2. **Alternate code paths STOP S2:** `USE_LEGACY_VLM`, `USE_TRAJECTORY_ANALYSIS`, sync vs async enqueue, executor shutdown fallback ```788:886:files/ball_analyzer.py``` — this audit emphasizes **default DWR + Layer2**.  
3. **STOP S3:** DWR/GEMINI/`[L2]` INFO lines absent from sampled **`pipeline-*.log`** tees; **`window_debug.json`** / sidecars assumed for span forensics unless logging topology changes.  
4. **`logs/` readability** varies by Cursor sandbox vs shell; investigation used shell-visible copies under **`/Users/anmolmohan/Projects/SportsComm/logs/`**.  
5. **No `ball_event` ↔ Scout disagreement hook** inside `_find_span` — disagreements manifest only indirectly (fallback window, `is_valid_delivery`, downstream unknowns).

