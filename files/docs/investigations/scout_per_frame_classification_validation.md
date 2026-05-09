# Scout per-frame classification validation (delivery span architecture)

Canonical scripts: **`files/scripts/scout_validation_research/`** (see `README.md`).

Artifacts: `output/scout_responses.jsonl`, `output/confusion_metrics.json`, `output/failure_patterns.txt` (production path); **`output/scout_responses_focused.jsonl`**, **`output/confusion_metrics_focused.json`** (focused-prompt A/B, Section 9); **`output/scout_responses_open.jsonl`**, **`output/description_ngrams_by_class.json`**, **`output/keyword_classifier_metrics.json`** (open-description diagnostic, Section 10); **`output/rule_iteration_metrics.json`**, **`rule_v1_errors.jsonl`**, **`rule_v2_errors.jsonl`** (wide-pitch rule iteration, Section 11); **`output/qwen_responses_open.jsonl`**, **`output/qwen_vs_scout_comparison.json`**, **`output/qwen_vs_scout_per_frame.csv`** (Qwen A/B, Section 12).

---

## 1. Executive summary

| Field | Value |
|-------|-------|
| **Status** | **Sections 9–11 complete** on **247** labeled frames / **15** clips; Groq **`llama-4-scout`** via production `Vision.describe` + **frozen** **`scout_responses_open.jsonl`** for §11 prose rules. |
| **Verdict (production JSON path)** | **Weak** — temporal **action** precision/recall nowhere near architecture gates; naive **stop S3** fired. *(Unchanged.)* |
| **Action P/R (temporal mapping)** | **P ≈ 0.74**, **R ≈ 0.19** (`confusion_metrics.json` → `per_class_metrics_temporal.action`) |
| **Action P/R (naive)** | **P ≈ 0.77**, **R ≈ 0.28** |
| **Span-level QC (temporal labels)** | **14 / 15** clips pass clip-overlap heuristic (**9 / 9** positive, **5 / 6** negative) — lone failure **`20260430_195352/d102`** (spurious **4 s** predicted `action` span with **no** human `action` span). |
| **Focused-prompt A/B (Section 9)** | **Regressed** vs production mapping: naive **action R ≈ 0.11** (vs **0.28**), **P ≈ 0.53** (vs **0.77**); **0** invalid parses; span QC **10 / 15** on temporal collapsed labels. Hypothesis *rejected* — stripping auxiliary tasks **did not** recover delivery recall. |
| **Open-description perception (Section 10)** | **Ordinal 2 (“partial”).** Fluent structured captions coexist with prompt-scaffold echo and replay silence; naive keyword skim lifts **`action`** **recall ≈ 0.89** but **precision ≈ 0.35**. |
| **Wide-field prose rule ingress (§11)** | **`classify_descriptions.py`** on open captions — **binary v2**: **P ≈ 0.77**, **R ≈ 0.99**, **F1 ≈ 0.87**; **does not** meet dual **≥ 0.85** (**precision** plateau). Multiclass (`classify_full`) **five-class accuracy ≈ 0.870**. Span QC on **binary** v2 labeled streams: **13 / 15** (**regresses** **`d102`** vs v1 **14 / 15** — kinetic replay text chains across **≥ 3 s**). **Subsystem verdict**: **Mixed** (recall clears bar; precision does not). |
| **Qwen3-VL open A/B (Section 12)** | **247 / 247** frames via **Fireworks** `qwen3-vl-30b-a3b-instruct` (same **`OPEN_PROMPT`** as Scout). **Literal v1** substring fails on Qwen (**paraphrase**); **intent-equivalent** wide rule: **F1 ≈ 0.74** vs Scout **≈ 0.78**. **OR** (Scout literal ∨ Qwen equiv): **R ≈ 0.85**, **F1 ≈ 0.76**; **AND**: **F1 ≈ 0.77**. **Umpire** heuristic: **F1 ≈ 0.67** (Qwen) vs **≈ 0.31** (Scout). **Replay** lexicon: **0** TP both (**n = 6**). **Five-class** (`classify_full`): **≈ 81 %** Scout vs **≈ 77 %** Qwen (equiv binary). **Cost ≈ \$0.04** / **247** frames; **latency** median **≈ 2.0 s** vs **≈ 0.35 s** Scout wall (Groq usage `total_time`). **Verdict**: **Scout-primary**; **Qwen** for **niche** second opinions (umpire / dispute), not wholesale **1 fps** swap. |
| **Final verdict** | **Weak** remains the honest headline for **native Scout structured classification + mapper** — do **not** ship delivery windows on **`camera_view` / `frame_phase`** alone here. **Additive finding (§11)**: hand-tuned prose rules target **broadcast wide-pitch camera** (not instantaneous “delivery happening”); **R** reaches **≥ 0.85** but **P** stalls ~**0.77** on this corpus; span heuristic warns that **lifting recall via alternate positive phrases** can **lengthen** false **`action`** runs on recap clips unless downstream temporal/GFX hygiene tightens. Next: tiny **learned scorer on description text**, **Path 2/3**, or **GFX/replay probes** — not broader rule lists without new labels. |

Production path: Scout **over-tags** `other` on many human-`action` frames once outputs are mapped from `camera_view`/`frame_phase`, which caps **recall**; span overlap on the production-mapped temporal run still hit **14 / 15** clips because **some** bowler-end phases align with labeled delivery windows — that **does not** lift frame-level action fidelity to production targets.

**Architecture decision (2026-05-01 refresh):** **Scout-primary** for **1 fps** open narration + **§11** hand rules on prose. **Qwen3-VL** (Fireworks, Layer2 stack) **does not** beat Scout on **literal** v1 or on **five-class** `classify_full` at equal hand-engineering; it **does** improve **umpire** substring heuristics and marginally **action recall** when **OR**-fused with an **intent-equivalent** wide rule — at **~6×** median latency and measurable token cost. Use **Qwen selectively** (umpire / dispute), **not** as a full-time Scout replacement for delivery-zone narration alone. **JSON** `Vision.describe`+mapper path **remains Weak** for hard **action** gates (**stop S3/S4** unchanged).


## 2. Methodology

### 2.1 Frame extraction

- **Tool**: `ffmpeg` filter `fps=1`, JPEG `-q:v 2`.
- **Count**: **247** frames across **15** folders (9 positive clips + 6 negative).
- **Positives**: `files/logs/deliveries/20260420_214218/{d001–d008,d010}` excluding `d009`.
- **Negatives**: `files/logs/deliveries/20260430_195352/{d001,d002,d010,d102,d104,d105}`.
- **Naming**: `files/scripts/scout_validation_research/output/frames/<session>_<delivery>_<time_in_clip_s>.jpg`.
- **Source files**: Mixed `delivery_window_p.mp4`, `delivery_window_n.mp4`, and plain `delivery_window.mp4`; extractor picks **`delivery_window*.mp4`** lexicographically.
- **Observed metadata** (representative positives): codec H.264 ~**14.4 fps**, ~13–24 s per window (logged by `extract_frames.py`).

### 2.2 Ground-truth protocol (five-class rubric)

Anmol-authored labels populate `output/labels_to_fill.csv`. Allowed values:

**`action` · `replay` · `ad` · `other` · `umpire` · `unknown`**

Validated distribution (**247** rows, all non-empty): **action 72**, **other 158**, **replay 6**, **umpire 8**, **ad 3**, **unknown 0**.

### 2.3 Scout invocation (production path)

- **Entrypoint**: [`files/eyes/vision.py`](../../eyes/vision.py) — `Vision.describe(frame, vision_hint)`.
- **Model**: `meta-llama/llama-4-scout-17b-16e-instruct`.
- **Run script**: `run_scout.py` — output JSONL fields `ground_truth`, nested `scout_response` (full sidecars + `scout_raw`), `scout_label_naive` from shared mapper.
- **Throttle**: **0.35 s** between requests (~**240 s** wall-clock for **247** frames including model latency).
- **Deviation**: neutral `vision_hint`; no frame history (**S1**).

### 2.4 Scout → naive label mapping (`scout_mapping.py`)

Single function **`scout_to_label_naive`**. Initial policy (Phase B):

| Signal | `scout_label_naive` |
|--------|---------------------|
| `frame_type=ADVERTISEMENT` or `camera_view=ad` | `ad` |
| `camera_view=bowlers_end` + `frame_phase` ∈ {runup, release, flight, shot, post_shot} | `action` |
| `frame_type=GRAPHIC` | `other` |
| `camera_view=closeup` (or defensive `CLOSEUP` ft) | `other` |
| `camera_view=replay` or `frame_phase=replay` | `replay` |
| `camera_view=side_on` | `action` (**provisional** — broadcaster replay geometry without slow-mo cues) |
| Else | `other` |

**Umpire** is **not** a Scout output bucket; empirical behavior summarized in Section 4 (**B4** cohort).

Temporal post-process (**per clip**, chronological): contiguous **runs** where `scout_label_naive=="action"` — **keep first run**, relabel subsequent runs to **`replay`** (`scout_label_temporal`). Rationale mirrors broadcast cadence (live corridor → fillers → reactive replay).

---

## 3. Confusion matrices (naive vs temporal)

Source of truth rows = human labels; columns = Scout-derived labels (**never** `umpire`).

### 3.1 Naive

| GT \\ pred | action | replay | ad | other |
|------------|--------|--------|----|-------|
| action | 20 | 0 | 0 | 52 |
| replay | 5 | 0 | 0 | 1 |
| ad | 0 | 0 | 3 | 0 |
| other | 1 | 0 | 4 | 153 |
| umpire | 0 | 0 | 0 | 8 |

- **Overall** (restricted to GT ∈ {action,replay,ad,other} exact match): **176 / 239 ≈ 0.736**.
- **Action**: P ≈ 0.77, R ≈ 0.28, F1 ≈ 0.41.
- **Stop S3**: **true** — `min(P,R) < 0.5` on **action** (recall collapse).

### 3.2 Temporal (`scout_label_temporal`)

| GT \\ pred | action | replay | ad | other |
|------------|--------|--------|----|-------|
| action | 14 | 6 | 0 | 52 |
| replay | 4 | 1 | 0 | 1 |
| ad | 0 | 0 | 3 | 0 |
| other | 1 | 0 | 4 | 153 |
| umpire | 0 | 0 | 0 | 8 |

- **Overall** exact-match (same restriction): **171 / 239 ≈ 0.716** (**stop S4**: temporal **worse** than naive).
- **Action**: P ≈ 0.74, R ≈ 0.19, F1 ≈ 0.31.
- **Temporal relabel sweep**: **7** frames converted naive `action` → temporal `replay`; **1**/7 human **`replay`** (desired), **6**/7 human **`action`** (regex false positive from “first corridor only” heuristic on this corpus).

### 3.3 Umpire cohort (Phase B4)

All **8** `ground_truth=umpire` frames: Scout emitted **`frame_type=SCOREBOARD`**, **`camera_view=closeup`**, **`frame_phase=between_play`**, naive label **`other`**. Narrative text occasionally references umpires/discussions (**example**: `20260420_214218_d004_*` previews mention umpire)—**no structured umpire signal**. Delivery architecture needs a **separate umpire GFX / pose / dedicated prompt** tier if umpire-aligned windows matter.

---

## 4. Failure modes (temporal predictions)

Structured counts → `failure_patterns.txt` | `failure_pattern_*` JSON.

| Pattern | Count | Interpretation |
|---------|-------|----------------|
| **P1** (`action_as_other`) | **52** | Majority failure — **`action`** GT vs Scout-derived **`other`** (usually **closeup** + **`between_play`** / strip-heavy read paths). |
| **P1b** (`action_as_replay_demotion_or_model`) | **6** | **`action`** GT vs temporal **`replay`** — aligns with naive→temporal corridor demotions (Section 3.2) plus any stray replay-phase tags. |
| **P3** (`umpire_frame`) | **8** | Dedicated slice for umpire cohort (mirrors Section 3.3 telemetry). |
| **P4** (`ad/other cross`) | **4** | Boundary frames **`ad`** vs human **`other`** (notably **`d004` bookends**). |
| **P2** (`replay_as_action_after_temporal`) | **4** | **`replay`** GT still predicted **`action`** post-temporal governor — clustered on **`20260430_195352/d102`** (replay corridor is chronologically **first** naive **`action`** run ⇒ demotion skips it). |
| **P5** (`residual`) | **2** | Leftover multiclass slips after explicit buckets above. |

**Representative frames** (**≤ 5 paths / pattern**) are listed in **`confusion_metrics.json` → `failure_pattern_example_paths_max5`** for Anmol drill-down.

---

## 5. Span-quality simulation (temporal `action`)

**Method**: contiguous **`action`** spans on human labels vs `scout_label_temporal`, same overlap rules as prior memo (positive requires overlap **and** ≥ 1 predicted action frame; negative fails on ≥ 3 s spurious **`action`** when human never labels **`action`**).

**Results**:

- Positives (**9 / 9**) pass.
- Negatives (**5 / 6**) pass.
- **Failure**: **`20260430_195352/d102`** — predicted **`action`** span [**6 s – 9 s**] (4 frames) with **no** human **`action`** span (human clip is **`other`** / **`replay`** heavy early; Scout still fires bowlers-end delivery phases mid-clip).

**Interpretation**: span-level heuristic can still look “okay” while **frame-level action recall is catastrophic** — do **not** use span pass rate alone to certify Scout.

---

## 6. Verdict + reasoning + architectural insights

**Automated verdict**: **Weak** — temporal **action** `min(P,R) ≈ 0.19 < 0.7` gate triggers regardless of clip overlap story.

### 6.1 Insights to carry forward (independent of verdict)

1. **Single-frame Scouts cannot reliably separate `action` vs `replay`** when broadcasters recycle the same angles without GFX/slow-mo fingerprints — validates Anmol’s finding; **mandatory temporal / multi-frame / alternate signals**.
2. **Score-event ordering** remains the strongest *cheap* causal prior for sequencing live vs recap — Phase D heuristic instantiated as “first `action` corridor only`; this corpus proved it **leaks** (late replays anchored as first corridors, false demotions when multiple live bursts exist — see Section 3.2 counters).
3. **GFX overlays / explicit replay bugs** remain more leverageable than raw motion cues on static JPEG cadence — Scout already surfaces `replay` tags rarely here (**6** GT replay frames; model still confused).
4. **Prompt narrowing alone did not recover delivery recall** — the delivery-centric Scout-only prompt (**Section 9**) lowered naive **action** **P/R/F1** vs production-mapped `Vision.describe`; expect **architecture** wins from **signals / models**, not from stripping auxiliary Scout questions alone on **`llama-4-scout`** at **1 fps**.
5. **Open descriptions are rich but not class-pure** (**Section 10**) — Scout narrates broadcast grammar (wide shot, score strip, sponsor bugs) on **both** `action` and `other` frames; naïve keywording on that text can **overshoot action recall** while wrecking precision. Calibrated **binary probes** (separate from the big rubric) are the natural next Scout-side experiment; **Path 2/3** remains mandatory for production-grade accuracy.
6. **Scout’s more reliable prose primitive is camera shot framing, not action level** (**Section 11**) — the same captions that wrongly say “between deliveries” on human **`action`** frames still encode **wide field view**, **full shot**, wicket/pitch geometry, or kinetic verbs. Rules aimed at **“live broadcast wide-pitch camera”** recover **much higher recall** than JSON-mapped **`action`**; **precision** trades off against replay/ceremony/idling stadium shots that reuse wide vocabulary (**§11.8**).
7. **Per-frame VLM “ceiling” is similar once vocabulary is normalized (Section 12)** — **Qwen3-VL** on the **same** open prompt **paraphrases** camera language; **frozen** substring rules trained on Scout’s **prompt-scaffold echo** are **not portable** without **intent-equivalent** relaxation. Neither model delivers **replay** lexicon at usable **P/R** on **n = 6**; **five-class** `classify_full` stays **≈ 77–81 %** — no step-change vs §11’s stronger **v2** route. **Qwen**’s standout is **umpire** morphology under the shared pattern tests.

### 6.2 Branching

- **Weak path (native JSON ingress)**: invest in **replay-specific prompt / second-pass VLM**, **Qwen** / dual-head scoring, or widen heuristics + manual QA.
- **Ingress supplement (§11)**: optionally run **parallel** open-caption + **deterministic classifier** (**`classify_descriptions.py`**) or server-side equivalents; fuse with span aggregation (**first wide-pitch corridor** hypotheses) rather than trusting single-frame **`action`** tokens.
- **If future sweep reaches Strong/Mixed**: scope shifts to **MEDIUM–HIGH** (~**400–700 LOC**) because temporal policies, tests (**~100–200 LOC**), and score-event coupling (**~50–100 LOC**) are now baseline.

---

## 7. Implementation scope vs pivot (**Weak** verdict on JSON path)

Focused-prompt **A/B** (**Section 9**) **did not improve** naive **action** metrics. **Section 11** does **not** revoke the **Weak** verdict on **`Vision.describe`** + mapper — but it **raises confidence** that an **engineering path** exists: treat **open descriptions** as a **cheap wide-camera detector**, aggregate contiguous **`action`**-equivalent spans, then apply **score-event-aligned temporal logic** (first span near wicket event = hypothesized delivery; later spans demoted pending replay cues).

Suggested sketch (orthogonal to tightening Scout JSON):

| Workstream | Indicative LOC |
|------------|----------------|
| Parallel Scout (or replay of stored captions) emitting **`open_description` per frame** **or** server-side **`classify_v2` / `classify_full`** on cached text — **Scout-primary**; optional **Qwen** call on **umpire / dispute** slices only (Section 12) | ~50–120 |
| Rolling buffer + **span aggregator** (contiguous predicted wide-pitch / **`action`** from rule v2) | ~**120–200** |
| **Temporal governor** — first-span vs replay demotion using score/UI events (**§8 limitation d102** still applies if replay leads) | ~**80–140** |
| Frame reconstruction / **FFmpeg** splice from raw ring buffer | ~50 |
| Tests / fixtures | ~**100–200** |
| **Total** | ~**400–700** MEDIUM–HIGH |

Add explicit **replay/GFX detectors** where prose is ambiguous (**Sections 4, 11.7**). **Path 2/3** remains the backstop for **taxonomy-grade** fidelity; §11 validates **ingress** layering, **not** “Scout **`action`** field is fixed.”

---

## 8. Limitations

1. **N = 247**, **replay** GT **6**, **umpire** **8** — statistics are exploratory.  
2. **Single-positive session**.  
3. **1 fps** JPEGs omit micro-motion cues.  
4. **`side_on` → `action`** mapping is brittle (broadcast replay ambiguity).  
5. **Temporal rule** simplistic — failed when replay preceded labeled “live” corridors inside the same stitched window (**d102**).

---

## 9. Focused-prompt A/B test (delivery-centric Scout prompt)

**Goal**: Holding frames, throttle (**0.35 s**), Scout model (**meta-llama/llama-4-scout-17b-16e-instruct** via Groq API), labels, and analysis pipeline fixed, expose whether a **single-task** prompt answering only “five-way frame class” (**action / replay / ad / umpire / other**) improves **naive action recall** relative to **`Vision.describe`** + deterministic mapper (`scout_to_label_naive`).

**Hypothesis**: Rich production prompt steals capacity from delivery detection. **Observation**: Hypothesis **rejected**. Focused naive **action recall collapses**; production mapping remains strictly better here.

Artifacts: **`output/scout_responses_focused.jsonl`**, **`output/confusion_metrics_focused.json`**. Scripts: **`run_scout_focused.py`** (direct Groq, no `Vision.describe` edits), **`analyze_focused_ab.py`** (merge with `scout_responses.jsonl`, parity metrics).

Invalid parse rate: **0** / **247** (no rerun needed for formatting).

### 9.1 Methodology

- JPEGs and GT from **`output/frames/`**, **`labels_to_fill.csv`** (unchanged rubric including **`unknown`** exclusions where applicable — same **239**‑frame denominator for collapsed 4‑class comparisons as Phase C).
- **Focused prompt**: five explicit classes; guidance favoring **`action`** on ambiguous wide-angle live vs **`replay`**; response constrained to **one** token (**action | replay | ad | umpire | other**).
- **Parse**: lowercase, whitespace strip, first substring matching `{action,replay,ad,umpire,other}`; else **`invalid`** (none observed).
- **API**: Matches production stack — **`temperature=0`**, small **`max_tokens`**, **`llama-4-scout`**; image via base64 JPEG (same encoder pattern as `Vision`).

Full prompt text lives in **`files/scripts/scout_validation_research/run_scout_focused.py`** (`FOCUSED_PROMPT`).

### 9.2 Naive confusion and side-by-side metrics

**Focused naive full predictions** (**5‑way**, model may emit **`umpire`**):

| Pred → \ GT | action | replay | ad | other | umpire |
|-------------|-------:|-------:|---:|------:|-------:|
| **action**  | **8**  | **5**  | 0  | **2** | 0 |
| **replay**  | 0      | 0      | 0  | 1      | 0 |
| **ad**      | 0      | 0      | **2** | 1   | 0 |
| **other**   | **62** | 1      | 1  | **152**| **3** |
| **umpire**  | **2**  | 0      | 0  | **2**  | **5** |

**Production naive** (mapped from `Vision.describe`; never predicts **`umpire`** explicitly — see Section 3):

| Pred → \ GT | action | replay | ad | other | umpire |
|-------------|-------:|-------:|---:|------:|-------:|
| **action**  | **20** | **5**  | 0  | **1**  | 0 |
| **other**   | **52** | **1**  | 0  | **153**| **8** |
| **ad**      | 0      | 0      | **3** | **4** | 0 |

**Side‑by‑side** ( **`confusion_metrics_focused.json` → `comparison_table`**):

| Metric | Production (naive) | Focused (naive full) | Δ |
|--------|-------------------|----------------------|---|
| **action Precision** | **0.769** | 0.533 | **−0.236** |
| **action Recall**    | **0.278** | 0.111 | **−0.167** |
| **action F1**        | **0.408** | 0.184 | **−0.224** |
| **replay Precision** | — (never predicted **`replay`**) | 0.000 | — |
| **replay Recall**    | **0.000** | **0.000** | 0 |
| **umpire Precision** | — (never **`umpire`**) | 0.556 | — |
| **umpire Recall**    | **0.000** | **0.625** | +0.625 |
| **Overall acc** (GT **≠ unknown**) | **4‑class 0.736** | collapsed **4‑class 0.686** | **−0.050** |
| **5‑class accuracy** (all labeled rows) | 0.713 | **0.676** | −0.036 |

**Focused stop S3** (action **P** and **R** both > 0.5?): **Fails** (**R** ≪ **0.5**).

**Note on “capability plateau”**: Change is **outside** ±5 pp on **action recall** — focused run is **much worse**, not “same ceiling” stagnation (**`flags.s3_ab_recall_within_5pp`: false** in JSON).

### 9.3 Failure-mode comparison

| Cohort | n | Role |
|--------|---:|------|
| **GT `action`, focused ≠ `action`** (wrong bucket) | **64** | **62** **`other`**, **2** **`umpire`** — dominates “miss” mass (sample: `…/20260420_214218_d001_{0,1,3,4,5}.jpg`). |
| **GT `action`, production `other` → focused `action`** (“rescues”) | **1** | Example: **`…/20260420_214218_d001_2.jpg`** — almost no salvage from collapsing auxiliary tasks alone. |
| **GT `action`, production `other` ∩ focused `≠ action`** (**both prompts miss**) | **51** | Hard **1 fps** / composition cases (samples: **`…_d001_1.jpg`, `…_d001_4.jpg`, `…_d001_5.jpg`, `…_d002_9.jpg`, `…_d002_10.jpg`**). |
| Production-only misses on **`action`** (mapped **`other`**) baseline | **52** | Matches prior memo — focused does not unlock this cohort except the single **`d001_2`** win. |

### 9.4 Temporal logic + span QC on focused labels

Same **`naive_to_temporal_per_clip`** corridor rule as Sections 4–8, applied to **focused naive labels** (**5‑way**), then **`umpire` → `other`** for **collapsed 4‑class** parity with mapped production naive space.

**Action class (GT `support` = 72)**:

| Setting | Precision | Recall | F1 |
|---------|-----------|--------|-----|
| Focused naive (full preds) | 0.533 | **0.111** | **0.184** |
| Focused temporal (**collapsed 4 preds** on GT) | **0.500** | **0.083** | **0.143** |
| Δ recall (temp − naive), collapsed | — | **−0.028** | — |

**Span simulation** (**`span_simulation_focused_temporal_4class`**): **10 / 15** clips pass (**6 / 9** positives, **4 / 6** negatives) vs production temporal mapped run **14 / 15** — **focused temporal governance materially degrades** clip-level heuristic quality here.

Interpretation mirrors Section 8: collapsing predictions to scarce **`action`** spikes makes overlap checks brittle faster when naive recall is poor.

### 9.5 Verdict (focused arm)

Classification per original gates (**Section 6**, **Mixed** 0.7–0.85, **Strong** > 0.85):

- Focused naive **action** **min(P,R)** ≈ **min(0.533, 0.111)** ≈ **0.11** → **Weak**.
- Temporal focused **min(P,R)** on **action** still **≈ 0.083** → **Weak**.

**Conclusion**: **Remain on Weak.** Do **not** ship delivery detection on focused Scout-alone labels; prioritize **Path 2 / Path 3** (stronger VLMs / specialist classifier / richer temporal + GFX cues) rather than iterative Scout prose-only narrowing on **`llama‑4‑scout`** for this corpus.

---

## 10. Open-ended description diagnostic (perception vs elicitation)

**Intent**: Measure what Scout *says* when not forced into `camera_view` / `frame_phase` JSON — i.e., does natural language contain separable cues for **`action` / `replay` / `ad` / `other` / `umpire`**?

**Not a re-validation of architecture gates**; informs whether another Scout prompt pass is worthwhile before heavier model swaps.

**Artifacts**: `output/scout_responses_open.jsonl` (Groq completions + **`raw_response`** JSON snapshots), **`output/description_ngrams_by_class.json`** (per-class bag-of-words + PMI-style log-ratio terms + verbatim pulls), **`output/keyword_classifier_metrics.json`** (`analyze_open_descriptions.py`).

Scripts: **`run_scout_open.py`** (Groq multimodal mirror of focused runner; **`max_tokens`** default **220**, **`temperature`** default **0.2** — override if generations feel templated).

**Stop-condition notes**: (**S1**) **0**/247 replies shorter than **40** characters (model engaged enough for this corpus). (**S3**) Paths resolved from `labels_to_fill.csv`; missing images error out at fetch time identically to other runners.

### 10.1 Methodology

- Same **247** labeled frames (**0.35 s** throttle).
- **`OPEN_PROMPT`** text is embedded in **`run_scout_open.py`** (four bullet asks + forbid explicit label output).
- Per-line **`open_description`** = assistant text; **`raw_response`** = serializable SDK payload (**choices**, **usage**).
- **Stopwords-filtered** 1-/2-/3-grams aggregated per **`ground_truth`** class; discriminative stems are **within-class frequency vs rest-of-corpus log-ratio enrichments**.

### 10.2 Verbatim samples (manual inspection harness)

Eight samples per **`action`** / **`other`**, plus full coverage (**6**/6 replay, **3**/3 ads, **8**/8 umpire cohorts).

**GT `action` — illustrative contradictions**:

- **`20260420_214218_d001_2.jpg`** (GT **action**) — Scout narrates bowler legs + lofted bat yet concludes *“moment between deliveries”* (`open_description`).
- **`20260420_214218_d002_10.jpg`** (GT **action**) — text claims *“the batter standing with their back to the camera, having just thrown a ball into the air”* (**hallucinated role/reasoning** inconsistent with wicket-facing batter).

**GT `replay`**: human **`replay`** rows still read visually like bowler-end live strikes; example **`20260430_195352_d102_8.jpg`** — *“action appears … in real-time, capturing a dynamic moment”* (**no replay / slow-motion / recap language** despite GT).

**GT `umpire`** — discriminative morphology shows up cleanly in prose (**“his arms outstretched”**, *“possibly signaling…”*), e.g. **`20260420_214218_d004_21.jpg`** *“arms outstretched, likely an umpire … signaling … post-action moment”.*

**GT `ad`** — model often **explicitly denies cricket** (**“does not depict a professional cricket match”**) on **`d104_x`** windows — strong separation signal when tuned.

Bulk text for every sample path lives under **`description_ngrams_by_class.json → per_class[*].verbatim_samples`**.

### 10.3 N-gram / discriminator snapshot

Across classes Scout recycles scaffold phrases mirrored from **`OPEN_PROMPT`** (“camera shows …”, “graphical overlays …”, “action level appears …”). That yields **heavy token overlap**.

| Class | Top lemmata (filtered 1‑grams, illustrative) |
|-------|------------------------------------------------|
| **`action`** | `player`, `field`, `score`, `shows`, `overlays`, `deliveries`, `batter` |
| **`other`** | `player`, `action`, `frame`, `shows`, `overlays`, `standing`, `between` |
| **`replay`** | `right`, `corner`, `batter`, `bowler`, `live`, `raised` (**no corpus-wide “replay/slow-motion” spike**) |
| **`umpire`** | `man`, `arms`, `outstretched`, `shirt`, **strong 3‑gram** `his arms outstretched` |
| **`ad`** | `desk`, `woman`, `image` (**non-stadium morphology**) |

**Candidate binary probes** (`description_ngrams_by_class.json → candidate_signal_evaluation`):

| Signal | TP | FN | FP | TPR note |
|--------|---:|---:|---:|-----------|
| `word_replay_upper` | **0** | **6** | **3** | `REPLAY` bug almost never surfaced in narration |
| `phrase_slow_motion` | **0** | **6** | **3** | No slow-mo lexicalization despite GT recap |
| `running_bowler_language` (“bowler” ∧ “running”) | **1** | **71** | **1** | Too sparse for framing-only shots |
| `umpire_signal_language` (“umpire” ∧ {signal \| raised \| finger}) | **2** | **6** | **3** | Coarse but sparse |
| `ad_keyword_branch` (**`AD_PHRASES` ∪ `dream11`/`vivo`/`rupeeplay`**) | **0** | **3** | **3** | Literal brand / “commercial break” strings **rarely appear** even on true ads—model instead says *“not cricket”* |

### 10.4 Keyword classifier vs prompted baselines (sanity check)

**Purpose**: Extremely dumb rule stack on open text — exposes whether *lexical skim* alone can beat structured prompts (**not** a ship candidate).

Classifier order: **replay** (verbatim `REPLAY` / **`SLOW‑MO`** / “slow motion”) → **`AD_PHRASES` ∪ handset brands** (no generic `logo`/`sponsor` substring — IPL scorebugs otherwise trip false ads) → **umpire+signal heuristic** → **token hit on `ACTION_WORDS`** (**includes `run`; see bleed**) → **`other`** (`analyze_open_descriptions.py` lists terms).

**`action`** class exclusively:

| Source | Precision | Recall | F1 |
|--------|-----------|--------|-----|
| Production mapped naive | **0.769** | **0.278** | **0.408** |
| Focused single-task Scout | **0.533** | **0.111** | **0.184** |
| Keyword on open captions | **0.346** | **0.889** | **0.498** |

**Macro read**: brute recall **beats** prompted routes because Scout sprinkles **`bowling`/`delivery`/…** language broadly—including many GT **`other`** frames—so **precision craters**.

**Whole-label exact match** (**247** labeled rows excluding **`unknown`**): naive keyword **≈ 0.417** vs production mapped **five-class ≈ 0.713** — global routing still prefers structured prompt + mapper despite worse action recall headline on this toy lexicon.

### 10.5 Perception verdict (scale 1 / 2 / 3)

**Verdict**: **Ordinal 2 — “Scout perceives partially.”**

**Why not 1?** Reliable class separation is **not** present under cheap lexical probes: prompt-scaffold echoes blanket all GT buckets; replay lexical hooks missing; hallucinated micro motions appear.

**Why not 3?** Narration is **not** generic fluff — GFX/sponsor/channel cues, umpire choreography language, explicit “not cricket” ad detection illustrate **differentiable content** Scout *could* emit if queried with tighter, independent probes.

Formal notes: **`keyword_classifier_metrics.json → perception_verdict_codes`**.

### 10.6 Recommendations

1. **Prompt redesign (budget: one more Groq scrape ≈ same cost as Sections 9–10, ~few minutes wall time)**  
   Draft **orthogonal yes/no probes** distilled from discriminators that *did* fire (umpire choreography, cricket vs non‑cricket, visible scorebug vs fullscreen wipe) — *avoid* chaining them in one multitask mega prompt. Examples to trial:  
   - *“Does the narration mention an umpire with arms extended in a signalling pose (yes/no)?”*  
   - *“Is the bottom strip a live IPL score ticker (yes/no)?”*  
   - *“Do you visually read a recap/slow-motion or REPLAY bug (yes/no)?”*  
   Target metrics: **`action`** **F1 > 0.45** naïvely *and* **five-class exact match > 0.72** vs current production mapping before reconsidering Scout as primary ingress.

2. **Path 2 — Qwen (or comparable) specialty pass** stays the default **engineering** mitigation: open text shows perceptual crumbs but unreliable mapping to taxonomy at **1 fps** JPEGs.

---

## 11. Wide-field-camera rule iteration (open captions, no new Scout calls)

**Purpose**: Iterate hand rules on **frozen** `files/scripts/scout_validation_research/output/scout_responses_open.jsonl` + **`labels_to_fill.csv`** (**247** rows). Goal: **`action`** here means **“live broadcast wide-pitch framing suitable for corridor detection”**, not Scout’s instantaneous play-state narration (which frequently says “between deliveries” on human **`action`** frames — **Sections 10.2, 11.8**).

**Script**: **`files/scripts/scout_validation_research/classify_descriptions.py`**  
**Artifacts**: **`output/rule_iteration_metrics.json`**, **`output/rule_v1_errors.jsonl`**, **`output/rule_v2_errors.jsonl`**.

### 11.1 Methodology

- **No new Groq requests** — re-read existing **`open_description`** strings only.
- **Binary ground truth**: human **`action`** vs all other labeled classes (`replay`, `ad`, `other`, `umpire`) pooled as **`non-action`** for P/R/F1 (same framing as Sections **10.3–10.4** keyword skim comparisons).
- **Multiclass extension**: deterministic routing **`ad` → replay (conservative) → umpire → binary v2 `action` → `other`** — see **§11.6**.
- **Span simulation**: re-use **`analyze.py`** contiguous-span + overlap heuristic on **chronologically sorted** frames per clip (**15** clips), evaluating predicted **`action`** vs human **`action`** spans (failure on negative clips when spurious **`action`** lasts **≥ 3 s**).

### 11.2 Rule v1 baseline (“wide field view” ∧ ¬ closeup cues)

Implement **`classify_v1`** (closeup/framing negatives + substring **`wide field view`**). On this corpus:

| | TP | FP | FN | P | R | F1 |
|---|--:|--:|--:|--:|--:|--:|
| **v1** | 60 | 21 | 12 | **0.741** | **0.833** | **0.784** |

Matches the empirically expected **≈ 0.73 / ≈ 0.83** within rounding (**`rule_iteration_metrics.json → binary_action_vs_rest.v1`**).

### 11.3 Error analysis — FP / FN clusters (v1)

Auto-tagged rows live in **`output/rule_v1_errors.jsonl`** (`cluster` field). Aggregate counts (**`rule_iteration_metrics.json → fp_fn_clusters.v1`**):

**False positives (21)** — predicted **`action`**, GT ≠ **`action`**:

| Cluster tag | Count | Pattern (content) |
|---------------|------:|-------------------|
| **FP_other** | 12 | Residual mixed wide-field stadium / incidental wide shots not captured by finer tags. |
| **FP3_single_batter_tap_prep** | 3 | Wide pitch + solitary batter idle / tapping / “between deliveries” language (GT **`other`**). Examples: **`…/d002_1.jpg`**, **`…/d005_1.jpg`**. |
| **FP2_empty_field_spectators** | 3 | **`stands filled`**, spectators, **no active play** narration. Example: **`…/d005_6.jpg`**. |
| **FP_replay_GT_modeled_as_live_wide** | 2 | Human **`replay`** but prose reads indistinguishable from live (**Section 10.2** — replay silence). Sample: **`…/d001_19.jpg`**. |
| **FP1_cheer_ceremony** | 1 | **`Air Asia`** cheerleaders / pom‑poms. Sample: **`…/d001_17.jpg`**. |

**False negatives (12)** — predicted **`non-action`**, GT **`action`**:

| Cluster tag | Count | Pattern |
|---------------|------:|---------|
| **FN_pitch_player_no_wide_phrase** | 4 | Pitch-level players / prep without literal **“wide field view”**. |
| **FN_misc** | 4 | Fallback (e.g., diving keeper, post-motion framing). Samples: **`…/d004_17.jpg`**, **`…/d004_18.jpg`**. |
| **FN_closeup_or_full_body_language** | 3 | **“Full shot”** / **`full-body`** phrasing triggers v1 **`other`** gate despite corridor context (**FN example `d005_5`** vs rescued **`d001_2`** in v2). |
| **FN_boundary_edge_framing** | 1 | Boundary curve / **`d003_10`** — prose omits playable pitch actors. |

### 11.4 Rule v2 design + iteration table

**v2** adds **hard negatives** (ceremony/brands/non-cricket cues, idle stadium clustering, guarded solitary-batter prep), **narrow positive rescues** (kinetic verbs, wicket/pitch co-mentions, guarded escape from **`CLOSEUP_TERMS`** when **strong kinetic** cues present), and avoids naive **`delivery`** substring matches inside **“between deliveries”** (**stop S3** guard in implementation).

Compact iteration log (**dual ≥ 0.85 stop not met — precision stalled**):

| Step | Notes | Binary P | Binary R | Binary F1 | Δ FP vs v1 | Δ FN vs v1 |
|------|-------|----------|----------|-----------|------------|------------|
| v1 | Baseline wide + closeup | 0.741 | 0.833 | 0.784 | — | — |
| v2 tuned | **`classify_v2_final`** in script | **0.772** | **0.986** | **0.866** | **0** | **−11** |

Interpretation: v2 **rescues 11/12 FNs** at **neutral FP count on this labeled set** — the remaining mass of **precision** loss is structural overlap between **replay / idle wide** narration and corridor vocabulary; fixing it likely needs **probability scores** or **non-text replay cues**, not deeper keyword forests (**`verdict_notes`** in JSON mirrors this).

### 11.5 Final rule definition (`classify_v2_final`)

Authoritative logic is **`classify_v2_final(desc)`** in **`classify_descriptions.py`** ( layered **STRONG negatives → empty-stadium heuristic → solitary wide-batter staging → framing gate with kinetic escape hatch → composite wide / alt positives **`ALT_ACTION_PATTERNS`** ).

Single **irreducible binary FN** documented: **`rule_iteration_metrics.json → irreducible_binary_false_negatives_v2`** (**`…/20260420_214218_d003_10.jpg`** — boundary geometry, no actors in prose).

### 11.6 Multiclass routing (`classify_full`)

Ordered checks: **`is_ad_pattern` → conservative `replay` substring / slow-motion hints → umpire morphology → binary v2 ⇒ `action` → `other`**.

Five-class confusion (**rows GT**, **cols pred**) — excerpt from **`rule_iteration_metrics.json → multiclass_rule_full_v2.confusion_rows_gt_cols_pred`**:

| GT \\ pred | action | replay | ad | other | umpire |
|------------|-------:|-------:|---:|------:|-------:|
| action | **71** | 0 | 0 | **1** | 0 |
| replay | **2** | 0 | 0 | **1** | **3** |
| ad | 0 | 0 | **2** | **1** | 0 |
| other | **16** | 2 | 0 | **140** | 0 |
| umpire | 0 | **1** | 0 | **5** | **2** |

**Per-class highlights** (**`per_class`** in same JSON blob): **`action`** **P ≈ 0.798**, **R ≈ 0.986**; **`replay`** **R ≈ 0** (sparse explicit REPLAY tokens — expected); **`ad`** high precision patchy recall; **`umpire`** weak (small **`n`** + prose variance). **Overall five-class accuracy ≈ 0.870** (**215 / 247**).

Comparable baselines (**Section 10.4**, **memo tables**):

| Source | **`action`** P | **`action`** R |
|--------|----------------|----------------|
| Production mapped naive | **0.769** | **0.278** |
| Focused Scout | ~0.53 | ~0.11 |
| Keyword skim on open text | ~0.35 | ~0.89 |
| **Rule v2 binary** (**§11.4**) | **0.772** | **0.986** |

### 11.7 Span-quality simulation

Contiguous **`action`** runs on predicted labels vs human spans (**`span_simulation_binary_rule_*`** in **`rule_iteration_metrics.json`**):

| Rule stream | Positive pass | Negative pass | **Total** |
|-------------|---------------|---------------|-----------|
| **Binary v1** | **9 / 9** | **5 / 6** | **14 / 15** |
| **Binary v2** | **9 / 9** | **4 / 6** | **13 / 15** |
| **`classify_full` multiclass → collapse `action` vs rest** | **9 / 9** | **5 / 6** | **14 / 15** |

**Regression detail**: **`20260430_195352/d102`** — v1 **`pass`** (singleton false positives **< 3 s**); v2 **`fail`** (**4** consecutive **`action`** frames **[6 s – 9 s]** on a human non-**`action`** clip — **`span_verdict_deltas_v1_to_v2`**). Multiclass routing **suppresses some** kinetic false pulls for this heuristic (**restores** **14 / 15** vs binary v2 **13 / 15**) — **`span_simulation_multiclass_rule_full_v2`**.

Stop condition **S4** from investigation brief: span QC **cannot** unconditionally track frame-level F1 lifts; cite **`d102`** when arguing for **replay-aware** chaining or GFX gates alongside prose.

### 11.8 Updated verdict (§11 subsystem only)

Per acceptance rubric (**both P & R ≥ 0.85**): **not achieved** (**P ≈ 0.77**, **R ≈ 0.99**). Per **≥ one** criterion: **`Mixed`** (**`rule_iteration_metrics.json → verdict_open_rule_architecture`**).

**Residual failure modes** for follow-up:

- **Precision ceiling** ~**0.77** hand-tuned — **replay-as-live prose**, idle wide shots sharing vocabulary with corridors.
- **Single irrecoverable boundary FN** absent pitch actors in text.
- Optional **§11 stop S2**: next bounded step — **bag-of-words logistic regression** on descriptions or **frozen embedding** classify head (~few hundred weighted features), not more regex layers without new labels.

### 11.9 Architecture implications

- **Composable ingress**: Scout JSON **`action`** tag **Poor** surrogate for delivery here; **open prose wide-camera detectors** (**§11**) are a ** plausible parallel feature** fused **before** or **instead of** trusting mapper **`action`**.
- **Mandatory downstream**: contiguous span aggregation **+ temporal / score coupling** (**first wide span near ball event**) — verbatim match to Anmol architecture note; prose alone **cannot** demote recap when kinetic language chains (**§11.7**).
- Native structured Scout path (**Sections 3–8**) verdict **Weak** persists; prose rule path **Mixed** — combined story: **engineering is more viable**, **classification primitive shifted** toward **camera shot**, not naive **`action`** field.

---

## 12. Qwen3-VL vs Scout — open description A/B (same 247 frames, same prompt)

**Intent:** Hold **frames**, **labels**, and **analysis** fixed; swap only the **VLM** that emits **`open_description`**, using the **identical** user prompt as **`run_scout_open.py`** (four bullet asks + “don’t classify”).

**Scripts:**  
- **`files/scripts/scout_validation_research/run_qwen_open.py`** — invokes **Layer2 production Qwen surface**: Fireworks OpenAI-compatible **`accounts/fireworks/models/qwen3-vl-30b-a3b-instruct`** (`layer2_classifier.py:434–438`, `491–493`; image = **base64 JPEG** `data:image/jpeg;base64,...` + text turn, completion JSON).  
- **`files/scripts/scout_validation_research/compare_qwen_scout_open.py`** — metrics, CSV, ngram summary.

**Artifacts (under `files/scripts/scout_validation_research/output/`):**  
`qwen_responses_open.jsonl`, `qwen_vs_scout_comparison.json`, `qwen_vs_scout_per_frame.csv`.

### 12.1 Methodology

- **Qwen call surface**: **Fireworks** HTTP API (same **OpenAI** SDK pattern as Layer2); **not** DashScope/Ollama. **Prompt**: duplicated **`OPEN_PROMPT`** string from **`run_scout_open.py`** for parity with Scout. **Throttling**: **1.0 s** between requests (Scout open run used **0.35 s**). **Stops:** **0** HTTP errors / empty captions on **247 / 247** (**S4** not triggered).
- **Cost (list pricing):** Fireworks publishes **\$0.15 / 1M input** + **\$0.60 / 1M output** tokens for Qwen3-VL-30B Instruct. **Empirical sum** over this JSONL: **≈ \$0.044** for all frames (`qwen_vs_scout_comparison.json → cost_note.qwen_empirical_usd_summed_from_jsonl`).
- **Latency:** Qwen **wall** median **≈ 2021 ms** per frame vs Groq Scout **usage.total_time** median **≈ 353 ms** (same JSONL comparison file).

### 12.2 Per-class description characteristics (Qwen)

Structured summary: **`qwen_vs_scout_comparison.json → qwen_ngrams_summary`** (per-class top bigrams / trigrams + log-ratio terms). Qualitatively vs Section 10’s Scout table:

- **Camera diction**: Qwen favors **“wide view of the … cricket field/match”** instead of echoing **“wide field view”** from the prompt bullet — **less template-locked**, but **breaks literal substring rules** designed on Scout.
- **Replay / slow-motion**: Same **blind spot** as Scout under conservative substring tests — **0** true positives on **6** human **`replay`** rows for both models’ **`is_replay_pattern`** detectors; Qwen **fires more false positives** on replay-like language without recovering GT (**higher FP count** in JSON).
- **Ads**: **Identical** P/R/F1 on the narrow **`is_ad_pattern`** branch (**2**/3 TP both).
- **Umpire**: Qwen improves **precision** (**1.0** vs **0.4**) and **recall** (**0.5** vs **0.25**) on the shared umpire+signal heuristic — small **n = 8**.

### 12.3 Rule v1 applied to Qwen (P/R/F1)

**Literal** **`classify_v1`** (substring **`wide field view`** ∧ ¬ closeup list): on Qwen text this is **degenerate** — **no** frame contains the exact phrase, so **TP = 0**, **R = 0** (`qwen_literal_substring_wide_field_view` in comparison JSON). This is **not** evidence that Qwen “never sees” wide shots; it reflects **prompt paraphrase**.

**Intent-equivalent relaxation** (same closeup gate ∧ (**`wide field view`** ∨ (**`wide view`** ∧ {cricket, field, pitch, match, stadium, ground}) ∨ **wide-angle** variants)): **P ≈ 0.70**, **R ≈ 0.79**, **F1 ≈ 0.74** vs **Scout literal** **F1 ≈ 0.78** (`qwen_equivalent_wide_camera_paraphrase`).

### 12.4 Combined Scout + Qwen strategies

All **binary action-vs-rest** metrics: **`rule_v1_binary_action_vs_rest`** in **`qwen_vs_scout_comparison.json`**.

| Strategy | Role | Binary **F1** (this run) |
|--------|------|--------------------------|
| Scout **literal** v1 only | Baseline wide substring | **≈ 0.78** |
| Qwen **equivalent** wide only | Paraphrase-aligned | **≈ 0.74** |
| **OR** Scout literal ∨ Qwen equiv | Recall-oriented | **≈ 0.76** (**R ≈ 0.85**) |
| **AND** Scout literal ∧ Qwen equiv | Precision-oriented | **≈ 0.77** |
| **Literal–literal OR / AND / agree dual-pass** | Fair A/B on *same* substring | Collapses to Scout-only (Qwen literal never fires) |

**Five-class** `classify_full` accuracies: **≈ 81.4 %** (Scout binary) vs **≈ 77.3 %** (Qwen **equivalent** binary). Combined multiclass rows (**OR / AND / agreement** with Scout literal + Qwen equiv) are listed under **`five_class_accuracy`** — **AND**-style fusion **≈ 77.7 %** vs Scout-only **≈ 81.4 %** on this hand stack.

### 12.5 Comparative verdict (Scout vs Qwen vs combined)

- **Delivery-zone proxy (binary wide rule):** **Scout** wins **literal v1**; **Qwen** is **competitive only after** paraphrase normalization. **Dual-pass OR** trades **~2 pp F1** for **+1 pp recall** vs Scout-only on this narrow test — **not** a decisive architecture upgrade for **corridor detection**.
- **Five-class hand router:** **Scout** ahead by **~4 pp** absolute on **`classify_full`** with the stated binary choices.
- **Replay:** **No** winner — **specialist** cues still required (**GFX**, multi-frame).
- **Umpire:** **Qwen** text heuristics **stronger** on this **tiny** support; consider **targeted** second pass.
- **Cost / ops:** Qwen batch **≈ \$0.04** here but **~6×** slower per frame vs Scout — **multi-hour** at scale vs **minutes** for Scout at 0.35 s spacing.

### 12.6 Cost / latency comparison

| Provider | Model | Median wall / usage-time | Rough batch cost (247 frames) |
|---------|--------|--------------------------|-------------------------------|
| Groq | `llama-4-scout-17b-16e-instruct` | **≈ 0.35 s** | *Order* **\$0.09/match** comment in `eyes/config.py` (not per-frame-tokenized here) |
| Fireworks | `qwen3-vl-30b-a3b-instruct` | **≈ 2.0 s** | **≈ \$0.044** token-sum (this run) |

### 12.7 Architecture recommendation

**Ship Scout-only** for **1 fps** open narration + **§11** deterministic fusion. **Add Qwen** only where product metrics justify **latency + token cost** — **first** candidate: **umpire**-weighted windows or **explicit** “models disagree” arbitration on wide-shot rules. **Do not** replace Scout wholesale with **1 fps Qwen** for this memo’s tasks; **hand rules** must **normalize camera vocabulary** if ever ported across models. **Path 2/3** (trained visual head / richer temporal+GFX) remains the path to beat **§11** precision plateaus.

---

References: **`window_content_audit.md`**, [`files/eyes/vision.py`](../../eyes/vision.py), [`files/layer2_classifier.py`](../../layer2_classifier.py).
