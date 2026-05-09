# Path 1b window-content audit — GT-RCB `20260430_195352`

**Scope:** `files/logs/deliveries/20260430_195352/` (**215** enqueue folders, GT-RCB).  
**Goal:** Judge whether delivery windows contain what Qwen needs for detail extraction, especially the bounce instant for **length** classification.

---

## 1. Executive summary

**Window quality verdict (from logged artifacts): Adequate for temporal span and frame count; weak for Scout phase alignment in `window_debug.json`.**

- **Temporal windows:** Most deliveries use **12.5 s** clips with **~159–163 frames** (~12.9 fps implied). That is a wide enough span that bounce *could* be in-frame visually, but this audit **does not** prove the bounce instant is sampled or centered.
- **Scout phase tags in logs:** **Sparse and not representative.** Only **101 / 215** folders have any `tags[]` rows; **114** have an empty list. Across **all** tag rows (**116** total), **flight** appears **2** times (**2** deliveries: `d114`, `d131`). **Release / shot** tags are similarly rare. **You cannot answer Q3 (phase placement in the window timeline)** from these artifacts at per-frame resolution; stop-condition **S1** applies for phase auditing unless instrumentation improves.

**Extraction quality verdict (layer2 on **213** deliveries with `layer2.json`): Strong fill for length / bounce / shot geometry; weak for handedness and bowling arm / angle.**

- **Non-null `cricket_values`:** **length**, **bounce**, **shot_type**, **shot_angle**, **elevation**, **bowling_type**, and **contact_quality** are populated for essentially all rows; **line** and **shot_side** use explicit **`unknown`** part of the time (**14.6%** and **12.2%** respectively).
- **Batsman handed / bowling arm / bowling angle:** **100%** **`unknown`** with **0.0** confidence — unchanged from the “low success” bucket in prior bench language.

**Bottleneck classification: Mixed, leaning Path 2 / capability for some fields.**

- **Path 1b (window quality):** Dominant **only** for the two **skipped** phantom events (**d066**, **d213**) — no video. For the rest, span looks healthy; **lack of phase-tagged timelines** blocks a data-driven bounce-frame proof.
- **Path 2 (prompt / parsing):** Plausible for **line** and **shot_side** unknown rates while other fields fill.
- **Path 3 (model):** Consistent with **handedness / bowling arm / angle** remaining at **unknown** across the board.

**Recommendation:** Treat **dense Scout phase alignment inside the clip** (or export of frame indices actually encoded into the Qwen payload) as a **prerequisite** for any rigorous “bounce frame present” claim. Until then, use **human spot-checks** on `delivery_window.mp4` for a stratified sample (fallback vs retrospective).

---

## 2. Artifact inventory

### 2.1 Folder count

- **215** child folders (`d001` … `d215`) under `files/logs/deliveries/20260430_195352/`.

### 2.2 Presence rates (of **215**)

| Artifact | Count | Notes |
|----------|------:|-------|
| `window_debug.json` | **215** | Always present |
| `delivery_window.mp4` | **213** | Missing **`d066`**, **`d213`** (skipped) |
| `layer2.json` | **213** | Same |
| `replay/` (directory) | **213** | Same |
| `predictions.json` | **204** | **11** missing (see below) |

**Missing `predictions.json`:** `d007`, `d025`, `d093`, `d100`, `d124`, `d150`, `d176`, `d177`, `d193`, `d200`, `d210` (11** folders).

**Stop-condition S3:** Artifact completeness is good for **window_debug**; **layer2** / **mp4** miss exactly the **2** skipped deliveries; **predictions** has a larger gap (**204 / 215**) — downstream audits that need commentary alignment should subset or backfill.

### 2.3 Canonical `window_debug.json` schema ( **`d001`** )

Observed fields:

| Field | Example / note |
|-------|----------------|
| `delivery_num`, `window_id` | `1` |
| `event_ts` | Unix timestamp of score event |
| `over_number`, `innings`, `event_type`, `runs` | e.g. `DOT`, `0` |
| `window_source` | `fallback_pre_event_window` (majority) |
| `window_reason` | e.g. `no_bowlers_end_span` |
| `clip_start_ts`, `clip_end_ts` | Unix bounds of clip |
| `frame_count` | Integer (e.g. `163`) |
| `tags` | List of **sparse** Scout samples (often `[]`) |

**Not present in schema (blocking Q1/Q3 as specified):** `start_frame`, `end_frame`, per-frame indices, `pre_padding_s` / `post_padding_s`, per-frame `strip` / `overlay`, or a dense phase timeline. Padding must be **inferred** from timestamps vs event time if at all.

**Canonical `d001` excerpt (trimmed):**

```json
{
  "delivery_num": 1,
  "window_id": 1,
  "event_ts": 1777559119.8162072,
  "over_number": 4.5,
  "innings": 1,
  "event_type": "DOT",
  "runs": 0,
  "window_source": "fallback_pre_event_window",
  "window_reason": "no_bowlers_end_span",
  "clip_start_ts": 1777559109.8162072,
  "clip_end_ts": 1777559122.3162072,
  "frame_count": 163,
  "tags": []
}
```

**Skipped / phantom (`d066`):**

```json
{
  "window_source": "skipped",
  "window_reason": "phantom_event",
  "clip_start_ts": 1777562997.903577,
  "clip_end_ts": 1777562997.903577,
  "frame_count": 0,
  "tags": []
}
```

### 2.4 Sparse `tags[]` shape (when non-empty)

Example **`d005`** — single sample point:

```json
"tags": [
  {
    "ts": 1777559307.7002711,
    "camera_view": "bowlers_end",
    "frame_phase": "between_play"
  }
]
```

Keys: **`ts`**, **`camera_view`**, **`frame_phase`** (not `phase`; no `strip` / `overlay`).

### 2.5 `predictions.json` ( **`d001`** ) — complementary window stats

Mirrors window duration and frame count for consumer-facing reporting:

- `window_dur_s`, `window_frames`, `window_start_ts`, `window_end_ts`, `window_source`, `window_reason`
- **Does not** list frames sent to Qwen (see layer2).

### 2.6 `replay/replay_capture.json` ( **`d001`** )

For **`d001`**: `replay_tag_count: 0`, `saved_frame_count: 0`, empty `tags` — no extra phase data.

### 2.7 `layer2.json` schema ( **`d001`** )

**Stable across all 213 files:** one top-level key set  

`['_note', 'committed', 'conf_floor', 'per_field', 'qwen', 'routed', 'routed_conf', 'suppressed', 'wall_ms']`.

**Qwen block:**

- `qwen.model`, `qwen.ms` (latency), `qwen.err`, `qwen.raw` (JSON string), `qwen.parsed` (structured predictions from raw)
- `qwen.cricket_values` — normalized enums / booleans (e.g. `length`, `line`, `bounce`, `shot_type`, `elevation`, …)
- `qwen.cricket_confidence` — parallel confidence map

**Routed / committed:** `routed`, `routed_conf`, `per_field` (owner, `committed`, `owner_conf`), `committed` count, `suppressed` list, `conf_floor` (**0.7** in sample), `wall_ms`.

**Frames sent to Qwen:** **Not logged** in `layer2.json` (no frame indices or paths in this schema). Latency / cost: **`qwen.ms`**, **`wall_ms`** present.

**Stop-condition S2:** Not triggered — schema is **consistent** across the **213** available `layer2.json` files.

---

## 3. Window content statistics

### 3.1 Aggregate stats (all **215** `window_debug.json`)

| Metric | Median | P25 | P75 | P95 | Min | Max |
|--------|--------|-----|-----|-----|-----|-----|
| `frame_count` | **161** | **159** | **163** | **165** | **0** (`d066`, `d213`) | **167** |
| Duration `(clip_end - clip_start)` s | **12.5** | **12.5** | **12.5** | **12.5** | **0** | **12.5** |

**Implied sample rate:** median **`frame_count / duration_s` ≈ 12.88** frames/s for non-degenerate clips.

**Caveat:** P25/P75/P95 durations are **degenerate at 12.5 s** because **205 / 215** share the same `fallback_pre_event_window` span; tail behavior is hidden except for **retrospective** and **skipped** modes.

### 3.2 `window_source` distribution

| `window_source` | Count |
|-----------------|------:|
| `fallback_pre_event_window` | **205** |
| `retrospective_span` | **8** |
| `skipped` | **2** |

`window_reason`: **`no_bowlers_end_span`** (**205**), **`latest_bowlers_end_span`** (**8**), **`phantom_event`** (**2**).

### 3.3 Scout `frame_phase` distribution (tag **rows**, not frames)

**Only 116 tag rows** exist across the corpus:

| `frame_phase` | Tag-row count |
|---------------|-------------:|
| `between_play` | 104 |
| `release` | 5 |
| `post_shot` | 3 |
| `flight` | 2 |
| `shot` | 2 |

**`camera_view`:** `bowlers_end` **113**, `side_on` **3** (on tagged rows only).

**Per-delivery tag counts:** min **0**, max **3**, median **0**; **114** deliveries have **no** tags.

**Phase percentages of “all frames”:** **Not computable** — tags are not a per-frame census.

### 3.4 Outliers

**Shortest clips (by duration):** **8** deliveries at **3.5 s**, **56–59** frames, all **`retrospective_span`** / **`latest_bowlers_end_span`**:  
`d097`, `d100`, `d114`, `d131`, `d137`, `d195`, `d201`, `d205`.

**Longest clips:** Non-skipped clips cap at **12.5 s**; “longest five” are ties at **12.5 s** with varying `frame_count` (**153–165**).

**No flight tag (proxy for bounce framing in logs):** **213 / 215** (**99.07%**) have **no** `frame_phase=flight` row in `window_debug.json`. **2** deliveries **do** (`d114`, `d131`).

**No shot-phase tag:** **210 / 215** have neither `shot` nor `post_shot` in `tags[]` (again, logs are sparse).

---

## 4. Extraction quality (`layer2.json`, **n = 213**)

### 4.1 Field-level success (operational definitions)

- **Non-unknown:** `cricket_values.<field>` exists and is not `unknown` / empty string.
- **conf ≥ 0.7:** `cricket_confidence.<field> >= 0.7` (schema uses **0.0** for unknown-arm fields).

| Field | Non-unknown % | conf ≥ 0.7 % | Explicit unknown % |
|-------|----------------:|-------------:|-------------------:|
| length | **100.0** | **100.0** | **0.0** |
| line | **85.4** | **85.4** | **14.6** |
| bounce | **100.0** | **100.0** | **0.0** |
| shot_type | **100.0** | **99.1** | **0.0** |
| shot_side | **87.8** | **85.0** | **12.2** |
| shot_angle | **100.0** | **99.1** | **0.0** |
| elevation | **100.0** | **99.1** | **0.0** |
| bowling_type | **100.0** | **90.1** | **0.0** |
| contact_quality | **100.0** | **99.5** | **0.0** |
| batsman_handed | **0.0** | **0.0** | **100.0** |
| bowling_arm | **0.0** | **0.0** | **100.0** |
| bowling_angle | **0.0** | **0.0** | **100.0** |

**Line value mix:** `leg_stump` **97**, `outside_off` **85**, `unknown` **31**.  
**Shot side mix:** `leg` **79**, `off` **69**, `straight` **39**, `unknown` **26**.

### 4.2 Comparison to earlier benchmarking language

Prior shorthand (**length 0%, handedness 71%, shot_angle 100%, bounce 100%**) **does not line up** with this slice if “length 0%” meant **non-null extraction**:

- Here, **`length` is 100% non-unknown** with high confidence — so either the benchmark measured **accuracy against ground truth** (not audited here), or a **different pipeline stage / cohort**.
- **Handedness** in this batch is **0%** non-unknown (**worse** than 71% if that was a hit rate).
- **Shot angle** and **bounce** remain **strong** in fill-rate terms, consistent with older summaries.

**Interpretation:** This audit measures **schema population + confidence floors**, not **cricketing correctness**.

### 4.3 layer2 vs window content (qualitative)

- **Skipped deliveries** have **no** mp4 / layer2 — correctly absent from the **213**.
- **Retrospective** **3.5 s** windows still produced `layer2.json` with full-looking **length** / **bounce** fields — suggests either **sufficient** visual evidence in short clips **or** model extrapolation; **spot-check** video to distinguish.

---

## 5. Window vs extraction correlation

### 5.1 Length vs `flight` tag presence (logged proxy)

| Subset | n | Length non-unknown rate |
|--------|--:|------------------------:|
| With ≥1 `frame_phase=flight` tag | **2** | **100%** |
| Without flight tag | **211** | **100%** |

**Hypothesis test:** **No evidence** in this corpus that **length** fill-rate depends on **flight** rows in `window_debug.json` — the tag signal is too sparse and length is always filled.

### 5.2 Bounce-adjacent signal in Qwen raw

The model emits **`ball_bounce_zone`** in `qwen.parsed` / raw JSON when the prompt requests it; that is indirect evidence the model **believes** it saw bounce-relevant pixels, not that the **true** bounce instant is in the clip.

---

## 6. Bottleneck classification

| Path | Verdict | Evidence |
|------|---------|----------|
| **1b (windows)** | **Partial** | **2** phantom skips lack video; **8** retrospective clips are short (**3.5 s**). Otherwise **12.5 s** / **~161** frames is generous. **Cannot** verify bounce frame from Scout tags. |
| **2 (prompt / routing)** | **Likely for some fields** | **line** / **shot_side** unknowns while peers are filled. |
| **3 (model ceiling)** | **Likely for arm / handedness / angle** | **100%** unknown with **0.0** conf on those keys. |
| **Mixed** | **Overall** | Different fields show different failure modes; no single dominant bottleneck for **length** in this JSON. |

---

## 7. Recommendations

1. **Instrumentation:** Extend `window_debug.json` (or a sidecar) with **dense** Scout alignment: either **per-encoded-frame** `frame_phase` / `camera_view` / time offset, or **N** uniformly sampled frames with indices **into the clip** that match what Qwen receives.
2. **Payload logging:** Log **exact frame indices or file paths** passed to the VLM for each delivery (minimum: count + fps + offset of first/last frame).
3. **Human validation:** Stratified **video** review (**fallback** vs **retrospective** vs **flight-tagged** if expanded) focused on **bounce visibility** and **length** correctness — JSON fill alone is insufficient.
4. **Predictions backfill:** If commentary / SM alignment matters, investigate **11** missing `predictions.json` paths separately from window span.
5. **Handedness / arm / angle:** If product-critical, treat as **Path 3** or **prompt redesign** with **camera** constraints — current outputs are uniformly **unknown**.

**Prerequisites:** Dense phase tagging or frame-level Qwen input trace **before** claiming “≥90% of windows contain bounce-frame evidence.”

---

## 8. Limitations

- **S1 (sparse `window_debug`):** Phase **B3** flight proxy applies to **tag rows**, not video frames — **99%** of deliveries have **no** flight tag in logs despite possibly showing bounce in mp4.
- **Ground truth:** No labels in this folder for **length** / **line** correctness — only model outputs.
- **Two skipped** deliveries distort duration / frame **minima**; exclude them when summarizing “typical playable” windows.
- **Bounce timing:** At **~13 fps**, a **30–50 ms** bounce lasts **&lt;1 frame**; Scout cadence may miss the exact instant even when **flight** is conceptually present.

---

*Session path: `files/logs/deliveries/20260430_195352/` — **215** folders; stats computed **2026-05-01**.*
