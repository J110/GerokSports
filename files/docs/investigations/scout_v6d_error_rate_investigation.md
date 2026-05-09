# Scout V6d combined-corpus shadow: error-rate investigation — 2026-04-30

Structured analysis of **V6d** versus **V6c** shadow JSONs on the **combined** 50-frame corpus (`docs/scout_corpus_combined_v1.json`), plus **V6d** **41-frame** runs for operational comparison. Harness: `files/shadow_eval/run_shadow.py` (`TIMEOUT_S = 7.0`, default concurrency **4**, silent **429** retry with backoff up to five attempts).

---

## 1. Executive summary

- **Rates (all rows pooled: 5 runs × 150 rows/run = 750):**
  - **V6d combined:** **47 / 750 = 6.27%** of rows reported a non-empty `error`.
  - **V6c combined:** **3 / 750 = 0.40%**.
  - **V6d 41-frame** corpus (`scout_corpus_v1`): **0 / 615 = 0%** across the five timestamped `shadow_run_v6d_20260430_*_run*.json` artifacts.
- **Per-run “headline” (errors / 150):** V6d ranged from **2.00%** (run 4) to **11.33%** (run 2). The **~11% peak** in `discriminating_frames_v6c_vs_v6d_combined.md` (Section **7**, bullet **S3.1**) matches **run 2** (**17/150**). V6c per-run max was **2/150 = 1.33%** (run 5), consistent with “≤ ~1.3%/run”.
- **Root-cause classification:** Failures are **not** explained by `groq_finish_reason` **`length`** or **`content_filter`**. Every errored row has **`groq_finish_reason: null`** (no completed Groq choice). Error strings are dominated by **`TimeoutError`** at **~7s wall time** (harness `asyncio.wait_for`), plus a small mix of **429**, **502**, and **connection** errors.
- **Hypothesis view (H1–H5):** **H1** (API / rate / provider pressure) and **H5** (pressure amplified by marginal extra work per call) are **primary**. **H2** and **H3** are **not supported** by metadata. **H4** (V6d “can’t handle” specific frames) is **weak**: errors hit **many different** `frame_id`s across runs; the one frame that errored under both variants (`pbks_rr_f615`) did so with **timeout-class** messages, not label logic.
- **Recommendation:** Treat the spike as **operational / harness-timeout–sensitive**, **not** as evidence that **V6d** is unusable on content grounds. **Not blocking** a production decision solely on prompt toxicity; **do** tighten methodology (retry policy, **`TIMEOUT_S`**, concurrency pacing) before trusting combined-corpus K=5 discs. Short-term handling of existing JSON: selective **retry** on error rows or **exclude** those (frame_id, replicate) triples from vote aggregation with explicit coverage notes.

---

## 2. Per-frame error patterns

### 2.1 V6d combined — recurrence

Across **five** combined runs:

| `frame_id` | Error rows (max 15) | Distinct runs with ≥1 error |
|------------|--------------------:|----------------------------:|
| `pbks_rr_f600` | 3 | 2 |
| `pbks_rr_f603` | 3 | 1 |
| `rcb_gt_f791` | 3 | 2 |
| `pbks_rr_f2830` | 2 | 1 |
| `pbks_rr_f315` | 2 | 2 |
| `pbks_rr_f3178` | 2 | 2 |
| `rcb_gt_f1075` | 2 | 1 |
| `rcb_gt_f1267` | 2 | 2 |
| `rcb_gt_f1296` | 2 | 2 |
| `rcb_gt_f446` | 2 | 1 |
| *(24 additional frames with exactly 1 error row each)* | 1 each | *(varies)* |

**Totals:** **34** distinct `frame_id`s had ≥1 error; **47** error rows (**some frames** failed on **more than one** replicate and/or run).

**Concentration:** There is **no** tiny set of “always bad” frames: **run 1** touched **13** distinct erroring frames, **run 2** touched **16**, while **runs 3–5** touched **3–5** each. That **run-to-run spread** is more consistent with **time-varying provider/load** and **harness timeout** than with a fixed prompt–frame interaction.

**Match mix:** Combined corpus has **`mi_srh_*` 3**, **`pbks_rr_*` 26**, **`rcb_gt_*` 21** frames. **All 47** errors were on **`pbks_rr_*`** or **`rcb_gt_*`** (**0** on the three **`mi_srh_*`** frames). This is **expected under random failure** (only 6% of rows fail) with **non-uniform** per-run clustering; it is **not** sufficient to claim **`mi_srh`** images are “immune”.

### 2.2 Per-run error distribution (V6d combined)

| Run artifact | Error rows | % of 150 | Notes |
|--------------|-----------:|---------:|-------|
| `shadow_run_v6d_combined_20260430_161648_run1.json` | 15 | 10.00% | Errors from row index ~64–148 (scattered; not all “late”) |
| `shadow_run_v6d_combined_20260430_161955_run2.json` | 17 | 11.33% | Peak; many distinct frames |
| `shadow_run_v6d_combined_20260430_162259_run3.json` | 5 | 3.33% | |
| `shadow_run_v6d_combined_20260430_162617_run4.json` | 3 | 2.00% | Includes one **`RateLimitError`** (`pbks_rr_f1454`, `groq_attempt_count` **5**) |
| `shadow_run_v6d_combined_20260430_162926_run5.json` | 7 | 4.67% | Cluster around low row indices for **PBKS** frames; includes **`APIConnectionError`** on **`pbks_rr_f603`** (two replicates) |

### 2.3 V6c combined — errors (comparison)

| Run artifact | Error rows | `frame_id` / message (abridged) |
|--------------|-----------:|----------------------------------|
| `shadow_run_v6c_combined_20260430_160350_run2.json` | 1 | `pbks_rr_f727` — **`RateLimitError` 429** |
| `shadow_run_v6c_combined_20260430_161334_run5.json` | 2 | `pbks_rr_f615` — **`TimeoutError`**; `pbks_rr_f1272` — **`RateLimitError` 429** |

**Overlap with V6d:** **`pbks_rr_f615`** also appears as a **V6d** error in **`shadow_run_v6d_combined_20260430_162926_run5.json`** (**replicate** 1). That shared failure on the **same** `frame_id` under **both** variants is evidence for **operational fragility**, not **V6d-only** misclassification.

---

## 3. Groq metadata analysis

### 3.1 Stop-and-route-back: **S1** (missing `groq_*`)

**Outcome:** **S1 did not trigger.** Every row in **all five** combined V6d and V6c JSONs (**750 / 750** each) carried at least one additive **`groq_*`** field (e.g. `groq_latency_ms`, `groq_attempt_count`). Metadata capture **did not** fail.

### 3.2 `groq_finish_reason`

| Corpus / variant | Errored rows | `finish_reason` on errors | Successful rows (`error` empty) |
|------------------|-------------|---------------------------|--------------------------------|
| V6d combined | 47 | **all `None`** | **703 × `stop`** |
| V6c combined | 3 | **all `None`** | **747 × `stop`** |
| V6d 41-frame | 0 | — | **615 × `stop`** |

**No** observed **`length`** or **`content_filter`** on **any** row in these artifacts. **H2** / **H3** (token cap / content filter as the failure mode) are **not** supported by this dataset.

### 3.3 `groq_attempt_count` (all rows)

| Distribution | V6d combined | V6c combined | V6d 41-frame |
|--------------|-------------|-------------|--------------|
| 1 | 577 | 511 | 410 |
| 2 | 134 | 174 | 152 |
| 3 | 27 | 51 | 36 |
| 4 | 8 | 10 | 11 |
| 5 | 4 | 4 | 6 |

**On V6d errored rows only:** **44** with **`1`**, **1** with **`2`**, **2** with **`5`**. The **`groq_attempt_count` = 5** cases align with **429 backoff** then failure (e.g. **`pbks_rr_f1454`** explicit **429**; **`pbks_rr_f1185`** **TimeoutError** after **`46587`** ms wall time — **total** `_call` duration including retries).

### 3.4 Latency (`groq_latency_ms`)

| Slice | p50 | p95 | p99 |
|-------|-----|-----|-----|
| V6d combined (all rows) | 3293 | ~12592 | ~26249 |
| V6c combined (all rows) | 3139 | ~13881 | ~23190 |
| V6d 41-frame (all rows) | 3122 | ~13597 | ~25436 |

**Errored vs successful (V6d combined):**

- Errors with **`TimeoutError`:** median **`7002`** ms (**43** rows); **`41`** of **`43`** lie in **`6980–7100`** ms — consistent with the **`7.0`** s **`asyncio.wait_for`** in `_call`.
- Successful rows median **`3167`** ms (still heavy-tailed due to **429** backoff accumulating in **`groq_latency_ms`**, measured from **`t0`** at start of `_call`).

**Interpretation:** The harness **documents long successful calls** (**tens of seconds**) when **429** retries **sleep**, but **`TimeoutError`** failures cluster at **single-attempt ~7** s. **V6d** is **marginally slower** at p50 than **V6c** on the combined corpus (**~3293** vs **`~3140`** ms), which **plausibly** pushes more **marginal** requests over the **7** s **per-attempt** cap under load (**H5**).

### 3.5 `groq_response_id` uniqueness

**Within each file:** **no** duplicate non-null **`groq_response_id`** values detected in **V6d combined**, **V6c combined**, or **V6d 41-frame** subsets. Consistent with **no** unintended response reuse.

---

## 4. Error strings (Phase 2 detail)

**V6d combined** (**47** rows):

| Count | Exception / class (first line) |
|------:|--------------------------------|
| **43** | **`TimeoutError:`** |
| **2** | **`APIConnectionError: Connection error.`** (**`pbks_rr_f603`**, **`run5`**) |
| **1** | **`RateLimitError: Error code: 429`** (**`pbks_rr_f1454`**, **`run4`**) |
| **1** | **`InternalServerError: Error code: 502`** (**`pbks_rr_f1590`**, **`run2`**; Cloudflare **502** body in message) |

**V6c combined** (**3** rows):

- **`429`** ×2, **`TimeoutError`** ×1 (`pbks_rr_f615`, **`groq_attempt_count` 2**, **`groq_latency_ms` 11383** — includes retry/backoff time).

---

## 5. Hypothesis evaluation

| ID | Hypothesis | Evidence | Plausibility | Production implication |
|----|------------|---------|--------------|-------------------------|
| **H1** | API pressure (**429**, provider **5xx**, connection) | **429** (**V6d** & **V6c**), **502**, **`APIConnectionError`**; pervasive **`groq_attempt_count` > 1** on successes and some failures | **High** | **Not** uniquely **V6d** — same org/tier/load model. Mitigate concurrency / backoff / rerun windows. |
| **H2** | **V6d** hits **max_tokens** / **`length`** | **Zero** **`length`** in **`groq_finish_reason`**; errors have **`finish_reason: null`** | **Low / refuted** | No case to trim prompt **for token cap** from this evidence. |
| **H3** | **content_filter** on specific frames | **Zero** **`content_filter`** observations | **Low / refuted** | No Groq filter narrative from these runs. |
| **H4** | **V6d** “struggles” with frames **V6c** handles (model/prompt) | Failures are **transport/timeout** class; **many** frames, **low** cross-run repetition; shared **`pbks_rr_f615`** timeout across variants | **Low** | Do **not** attribute to **label** failure without clean completions. |
| **H5** | **H1** + **V6d** slightly heavier per call → more **7** s timeouts | **V6d** p50 latency **>** **V6c**; **TimeoutError** cluster at **~7000** ms; **V6d** error rate **>>** **V6c** on **same** corpus | **High** | **Hybrid:** fix **harness** (**timeout**, retries for **non-429** failures if desired) **and** optional **pacing** for **V6d** runs. |

**Most likely primary story:** **H5** (with **H1** as the mechanism): **provider variability** + **strict 7** s **per-attempt** timeout **`asyncio.wait_for`** + **`V6d`**’s slightly **higher** typical latency ⇒ **many** more **`TimeoutError`** rows than **V6c** on identical schedule/corpus.

**Confidence:** **High** that failures are **not** **finish-reason–driven** model refusals; **medium-high** that **timeout policy** dominates the **`V6d`–`V6c` gap** on this corpus; **medium** on exact quantification of prompt-length vs pure provider noise without controlled A/B (**same** wall clock, **locked** concurrency, **`TIMEOUT_S` sweep).

### 5.1 Stop-and-route-back checklist

| Code | Trigger | Outcome |
|------|---------|---------|
| **S1** | Missing **`groq_*`** on combined **V6d** | **Not observed** |
| **S2** | Novel mechanism outside **H1–H5** | **No** — **`TimeoutError` + infra codes** suffice |
| **S3** | Reported rate misread | **Partial clarification:** **~11%** is **per-run peak** (**run** **2**); **pooled** is **~6.3%**. Original discriminating summary is **consistent** with raw JSON |
| **S4** | **V6c** combined ≫ **V6c** **41-frame** error rate | Not fully enumerated here (**no** **V6c** **41-frame** artifacts in supplied set); **V6c** combined **≈** **0.4%** pooled, still **far below** **V6d** combined **≈** **6.3%**. **Combined corpus** may add stress vs **smaller** runs, but **does not explain** **V6d**/**V6c** **gap** by itself |

---

## 6. Implications

### 6.1 **V6d** production decision

The combined-corpus JSONs **do not** show **V6d**–specific **schema** or **content_filter** breakage. They **do** show **Shadow** as currently configured is **brittle** for **V6d** on **50×3** batches under **default** **7** s **per-attempt** timeout. Any **go/no-go** on **V6d** should **either** (a) **re-run** with relaxed timeout / lower concurrency and compare error rate, or (b) **explicitly accept** **missing** error triples in offline eval.

### 6.2 Shadow methodology

- Log / standardize **exception class** (already in `error` string).
- Consider **retry** on **`TimeoutError`** (currently **not** retried; only **429** is) or raising **`TIMEOUT_S`** for vision calls.
- When comparing variants, **report pooled** and **per-run max** error rates (both matter for K-of-5 stability).

### 6.3 Combined corpus expansion

Before scaling **N** frames or **K** runs, **calibrate** **timeout** and **concurrency** against **TPM** / observed **`groq_attempt_count`** histograms (see **`scout_v6c_determinism_decision.md`** for prior **429** / retry discussion).

---

## 7. Recommended actions

**Short-term (existing data):**

- For analysis that needs complete **3×** votes: **retry** error triples or **drop** with documented **coverage**; **`pbks_rr_f615`** (and other error triples) should not be interpreted as **V6d** **camera** votes without a clean completion.

**Medium-term (rerun / harness):**

- Increase **`TIMEOUT_S`** and/or lower **`--concurrency`** for **V6d** (and optionally **V6c**) on large corpora; optionally add **retry** for **timeout** with cap.
- **Validate:** **V6d** combined **K=5** rerun; target **pooled** error rate **≪** **6%** (ideally **~** **V6c** order of magnitude) before treating discriminating counts as **final**.

---

## 8. Cross-references

- `files/docs/investigations/combined_corpus_shadow_v6c_v6d_2026-04-30.md` — artifact index
- `files/docs/discriminating_frames_v6c_vs_v6d_combined.md` — Section **7** / **S3.1** error-rate note (**~11%** **V6d** peak vs **~1.3%** **V6c** cap)
- `files/docs/investigations/scout_v6d_first_shadow_run_results.md` — **41-frame** **V6d** ensemble (**zero** errors in cited **K=5** JSONs analyzed here)
- `files/docs/investigations/scout_v6c_determinism_decision.md` — **`groq_*`** fields, **`429`** retry behavior
- `files/shadow_eval/run_shadow.py` — **`TIMEOUT_S = 7.0`**, **`groq_attempt_count`** semantics (**wall time** includes **429** backoff)
- Raw JSON (**read-only** in this investigation):  
  `files/docs/shadow_run_v6d_combined_20260430_*_run*.json`,  
  `files/docs/shadow_run_v6c_combined_20260430_*_run*.json`,  
  `files/docs/shadow_run_v6d_20260430_*_run*.json`
