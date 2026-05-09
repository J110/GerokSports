# Scout V6d combined corpus — post-harness K=5 rerun (2026-04-30)

**Step 2** of the validate-first sequence: five fresh **`V6d`** shadows on **`docs/scout_corpus_combined_v1.json`** (**50** frames × **3** replicates = **150** rows/run) using the **Step 1** harness (**default `--timeout-s` 15.0**, **`asyncio.TimeoutError` retry**, **`MAX_ATTEMPTS` = 5). Baseline reasoning and pre-harness error taxonomy: **`scout_v6d_error_rate_investigation.md`**.

---

## 1. Executive summary

| Metric | V6d pre-harness | V6d post-harness | V6c combined (reference) |
|--------|----------------|------------------|--------------------------|
| Pooled error rate (**750** rows) | **6.27%** (**47**/750) | **0.53%** (**4**/750) | **0.40%** (**3**/750) |
| Worst single run | **11.33%** (17/150) | **1.33%** (2/150) | **1.33%** (2/150) |
| Runs with **zero** errors | **0**/5 | **3**/5 | **4**/5 |

- **Harness effect:** pooled errors dropped **≈11.8×** (6.27% → 0.53%). Prior dominant failure **`TimeoutError`** at ~**7** s (**43**/47 failures) **does not appear** in the post-harness ensemble; residual failures are **`RateLimitError` (429)** after **five** retry attempts (**2** rows) and Groq **`InternalServerError` (500)** (**2** rows).
- **Outcome classification:** **Outcome A — harness fix successful.** Pooled error **< 1%** (target met). Comparable order of magnitude to **V6c** combined (**~0.4%**); post-harness **V6d** registers **one** additional failing row versus **V6c** (**4** vs **3** on **750** rows), still within the **< 1%** band.
- **Recommendation:** Treat combined-corpus **V6d** completions as **suitable for downstream evaluation**, subject only to excluding or retrying the **four** known error triples. **Proceed toward V6e** design (**`scout_v6d_implementation_audit.md`** Section 5) with **medium-high confidence** — remaining errors look **infra / quota**, not **prompt-shape** regressions (**no** timeouts, **no** `finish_reason = length`).
- **Stop conditions:** **S1** skipped (CLI default **15.0** verified). **S2/D** skipped (not worse than 6.27%). **S3** not triggered (wall-times **≈143–198** s/run, sane **`groq_attempt_count`** spread). **S4** not triggered (**four distinct** erroring **frames**, **single** replicate each — **no** “same frame every run” content pattern).

---

## 2. Run inventory

Artifacts (executor local time **IST 2026-04-30**):

| Run | Output path | Rows | Errors | Observed wall (s)* |
|:---:|-------------|-----:|-------:|------------------:|
| 1 | `files/docs/shadow_run_v6d_combined_postharness_20260430_165832_run1.json` | 150 | 0 | ~143 |
| 2 | `files/docs/shadow_run_v6d_combined_postharness_20260430_170101_run2.json` | 150 | 0 | ~192 |
| 3 | `files/docs/shadow_run_v6d_combined_postharness_20260430_170419_run3.json` | 150 | 0 | ~191 |
| 4 | `files/docs/shadow_run_v6d_combined_postharness_20260430_170736_run4.json` | 150 | 2 | ~194 |
| 5 | `files/docs/shadow_run_v6d_combined_postharness_20260430_171056_run5.json` | 150 | 2 | ~198 |

`*` Shell-measured **`WALL_SECONDS`** from executor logs (sequential **`sleep 6`** between runs omitted from table).

**Validation checks (pooled five files):**

- **Row count:** **150**/`run`; **`total_calls`** field matches.
- **`groq_response_id` uniqueness:** **no** within-run duplicates across all **five** envelopes.
- **Variant:** all **`V6d`** rows; corpus pointer **`docs/scout_corpus_combined_v1.json`**.

---

## 3. Error taxonomy (post-harness)

**Total failing rows:** **4** (**0.53%** of **750**).

| Pattern | Rows | **`groq_finish_reason`** on fail | Typical **`groq_attempt_count`** / **`groq_latency_ms`** |
|---------|-----:|----------------------------------|--------------------------------------------------------|
| **`RateLimitError` 429** (retries exhausted) | **2** | `null` | **`5`** / **~41950**, **~42474** |
| **`InternalServerError` 500** | **2** | `null` | **`1`** and **`3`** / **~12292**, **~23695** |

**Concrete triples:**

- **`shadow_run…_170736_run4.json`**: **`pbks_rr_f316`** `replicate=3`; **`pbks_rr_f1496`** `replicate=2`.
- **`shadow_run…_171056_run5.json`**: **`rcb_gt_f807`** `replicate=3`; **`rcb_gt_f1308`** `replicate=1`.

**Compared to pre-harness V6d** (*from error investigation,* **47** errors): previously **TimeoutError** (**43**), **`APIConnectionError`** (**2**), **429** (**1**), **502** (**1**). Post-harness cohort: **zero** timeouts, **zero** connection errors documented here; residue is **429 exhaustion** (**2**) and **500** (**2**).

---

## 4. Latency analysis (`groq_latency_ms`, all rows)

| Slice | p50 (ms) | p95 (ms) | p99 (ms) |
|-------|---------:|---------:|---------:|
| V6d **post-harness** combined (**750**) | ~**2951** | ~**13998** | ~**33280** |
| V6d **pre-harness** combined (**750**) | ~**3293** | ~**12592** | ~**26249** |
| V6c **combined** (**750**) | ~**3140** | ~**13881** | ~**23190** |

- **Median** latency **drops** modestly versus pre-harness **V6d** (**~2951** vs **~3293** ms) — compatible with eliminating many **would-have-timeout** calls that landed near **7000–8000** ms failures before.
- **p99 rises** modestly (**~33** ks vs **~26** ks pre-harness) — tails still dominated by legitimate slow completions / backoff (same qualitative pattern as **`scout_v6c_determinism_decision.md`** aggregates).
- **V6d** median remains **somewhat below** historical **V6c** pooled median in this measurement window (noise + provider variance caveat).

**`groq_attempt_count` distribution (post-harness V6d, all successes + failures):**  
`1`:**508**, `2`:**173**, `3`:**45**, `4`:**16**, `5`:**8** — consistent with both **429** and **timeout** retry paths succeeding on extra attempts compared to historically **timeout-only** exhaustion at **seven** seconds.

---

## 5. Per-frame error pattern

**Distinct erroring frames:** **4**, each appearing **exactly once** across the ensemble:

- **`pbks_rr_f316`**, **`pbks_rr_f1496`**, **`rcb_gt_f807`**, **`rcb_gt_f1308`**.

Failures are **not** concentrated on a recurring **V6d**‑specific frame set across runs; they are **sparse** and **infra-class** (**429**/500 mix). Pre-harness **V6d** failures hit **many** frames per run (**operational** interpretation in investigation); post-harness data **repeat** that **non-stable** framing.

---

## 6. Decision recommendation

| Code | Interpretation |
|------|----------------|
| **A** | **Selected.** Pooled error **< 1%**, timeout wall eliminated from failure mix, metrics healthy. |

**Next step:** Resume **V6e** drafting / implementation (**`scout_v6d_implementation_audit.md`**) treating combined-corpus **V6d** parity runs as statistically usable.

**Operational follow-ups (optional):** retry the **four** error triples in isolation; optionally lower **`--concurrency`** for future large batches to shave **429** exhaust risk.

---

## 7. Implications

- **V6d production narrative:** Harness reliability was the **binding** blocker for trusting prior **combined** shadows; **this** rerun partially **rebases** offline evidence toward **parity** with **V6c** error rates (**~0.4–0.5%** pooled). Production prompt choice remains gated on **V6e** + **`f748` / **`f600`** audits as before.
- **Discriminating analysis:** Majority votes over **three** successful replicates for **46**/50 frames are unaffected; analyst workflow should exclude or rerun only the failing triples (Section **3** frames/replicates above) when aligning with **`discriminating_frames_v6c_vs_v6d_combined.md`**.
- **Methodology:** Default **`--timeout-s` = 15** + **timeout retries** appears **validated** as the right default for **`llama-4-scout`** vision shadows at **concurrency 4**.

---

## 8. Cross-references

- **`files/docs/investigations/scout_v6d_error_rate_investigation.md`** — pre-harness baseline (**~6.3% pooled**, **`TimeoutError` cluster**).
- **`files/docs/investigations/combined_corpus_shadow_v6c_v6d_2026-04-30.md`** — combined corpus assembly references.
- **`files/docs/discriminating_frames_v6c_vs_v6d_combined.md`** — discriminator list (constructed from **pre-harness** runs; consider refresh if re-voting policy requires).
- **`files/shadow_eval/run_shadow.py`** — **`DEFAULT_TIMEOUT_S`**, **`asyncio.TimeoutError`** handling.
- **`files/shadow_eval/replicate_analysis.py`** — pooled **`groq_*`** aggregation helper for Markdown tables elsewhere.
