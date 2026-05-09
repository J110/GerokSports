# Scout V6c — determinism characterization (Groq metadata + five runs)

**Date:** 2026-04-30  
**Artifacts:** Harness metadata fields on new shadow rows (`groq_*` in `shadow_eval/run_shadow.py`); two back-to-back runs **run4/run5** with full metadata; pooled analysis **`files/docs/scout_v6c_determinism_analysis_autogen.md`**.

**Prior context:** `files/docs/investigations/scout_v6c_replicate_runs_decision.md` established two migration fingerprints among the first three runs (`b0b1…` vs `7dd84…×2`). This memo tests whether **`7dd8483e30258c16`** is a stable attractor when more independent runs arrive.

---

## §1 Executive summary

- **Five** corpus_v1 **`V6c`** shadow envelopes (123 rows each), **errors 0**.
- **Migration hashes** (migration hash definition unchanged — sorted **`(frame_id, vote_cam)`**):

| Run | File (timestamp suffix) | Hash |
|-----|--------------------------|------|
| 1 | `20260430_140220` | `b0b1d9c701d48100` |
| 2 | `141433_run2` | `7dd8483e30258c16` |
| 3 | `141629_run3` | `7dd8483e30258c16` |
| 4 | `143705_run4` | `1c6482a31e208280` |
| 5 | `143910_run5` | `d3044e9a4d9d2f72` |

- **Unique hashes observed:** **four** distinct values across **five** runs. **`7dd8483e30258c16`** recurred **twice** (runs **2–3**). Runs **4–5** (after **`run4`** finished, **≥6** s pause, then **`run5`**) produced **two new fingerprints**, neither equal to **`7dd…`** nor to each other. **Hypothesis (“paired hash dominates / is the evaluation attractor”) is rejected:** **`7dd…`** did **not** repeat on the next paired session.
- **Groq telemetry (runs 4–5 only — legacy rows lack `groq_*`):**

  - **`groq_response_id`:** **123 / 123** non-null rows per run; **no within-run duplicates** (no evidence of response-ID reuse / caching surfaced by this harness).
  - **`groq_finish_reason`:** **100% `stop`** on both runs **4** and **5**.
  - **`groq_model`:** **`meta-llama/llama-4-scout-17b-16e-instruct`** only — no routing churn observed.
  - **`groq_attempt_count`:** many rows **`> 1`** even though **`error`** is empty — consistent with silent **429 / rate-limit retries** succeeding on later attempts (**run4:** `{1: 95, 2: 21, 3: 5, 4: 1, 5: 1}`; **run5:** `{1: 87, 2: 23, 3: 10, 4: 2, 5: 1}`). This is relevant for interpreting **latency spread** vs **determinism** (same logical request can incur different backoff paths).

- **Modal vote consensus across five majority-vote summaries:** **`38 / 41`** frames share the plurality label on **all five runs** — **much** higher agreement than pairwise migration hashing suggests; **three** frames account for dispersion (**`f748`**, **`f941`**, **`f942`** per autogen §watch list and histogram **`{5:38, 4:2, 3:1}`**).
- **Determinism classification:** **Stochastic with a modest vote-level floor but wide migration-hash state space.** **Within five runs we already saw four hash states** ⇒ **cannot** honestly label **`7dd84…`** the single “truth” atlas; **evaluation must tolerate multi-state outputs** despite **`temperature = 0`**. Confidence **medium-high** on *hash* dispersion (evidence-positive), **medium** on *root causes* **(routing + concurrency + retries + nondeterministic sampling layers not exposed in metadata)**.

- **Recommended next action:** (**1**) Treat **`V6c`** scoring as **`K`-run ensembles** (**K≥5** recommendation) summarising **median / modal** metrics and **migration-hash histograms**. (**2**) If shipping decisions require **migration-map stability**, escalate **beyond prompt-only Scout**. Metadata shows **successful retries**, not bitwise determinism. (**3)** **`f941`** / **`f748`** remain **evaluation anchors** (`f941` flipped **`closeup`** only on **run4**; **`f748`** slips back to **`bowlers_end`** on **run5** despite **`closeup`** plurality over four runs). (**4**) Combined corpus stays **sampler M‑2 gated** (`backlog.md`); determinism widenings **raise** variance costs of single-run claims but **do not** alone justify skipping bucket enforcement.

---

## §2 Run inventory (all five)

| Run | Timestamp | Hash | Wall-clock | Errors | Avg latency (Groq harness) |
|-----|-----------|------|------------|--------|----------------------------|
| 1 | `20260430_140220` | `b0b1…` | ~107s (prior memo) | 0 / 123 | n/a *(no metadata rows)* |
| 2 | `141433_run2` | `7dd8…` | 110 s | 0 / 123 | n/a |
| 3 | `141629_run3` | `7dd8…` | 165 s | 0 / 123 | n/a |
| 4 | `143705_run4` | `1c64…` | **119** s | 0 / 123 | ~**3441** ms mean (ok rows)* |
| 5 | `143910_run5` | `d304…` | **140** s | 0 / 123 | ~**4508** ms mean (ok rows)* |

\* From **`scout_v6c_determinism_analysis_autogen.md`** (p50 / p95 / p99 also tabulated there).

**Back-to-back discipline:** **`run5`** starts after **`run4`** completes, **≥6** s idle, then **`run5`** executes — nominally paired (same calendar session, **not hours apart**).

---

## §3 Hash distribution

- **Multiset:** **`7dd84…`** ×**2**, **`b0b1…`**, **`1c64…`**, **`d304…`** ×**1 each** ⇒ **four** unique states.
- **Recurrence:** **`b0b1`** singular; **`7dd84`** reproduced once as a consecutive pair (**runs 2–3**) but absent from **runs 4–5**; **no hash seen more than twice**.
- **New hashes (**runs **4**, **5**): **both distinct** ⇒ **paired-repeatability of runs 2–3 *does not* generalise** to the next paired window on **2026-04-30** afternoon batch.

### §3.1 “Paired hash dominant (3+ runs match)” — **Not satisfied**

Dominant-hash threshold **failed**: only **two** runs share **`7dd84`**; **later paired runs diversify**.

### §3.2 New hashes widen state space — **Satisfied**

**Implication:** treat **migration hash parity** across sessions as **stochastic**. Shadow evaluation narratives should cite **histograms**, not singleton JSONs.

### §3.3 Runs **4** **≡** **5** voting map — **Not satisfied**

They differ (**`migration_hash`** line in autogen). **Hence** naive “paired identical state” framing does **not** hold for **`run4`**/**`run5`**.

---

## §4 Groq metadata insights (runs **4–5**)

- **`groq_response_id` duplicates within a single run:** **False** (**S3.4 cleared** **for these two executions** — no duplicated IDs surfaced).
- **`groq_finish_reason`:** **`stop`** on **every** succeeded row ⇒ completions not ending on **`length`** in this corpus slice.
- **`groq_attempt_count`:** **non-trivial retries** ⇒ **silent resilience path** correlated with heavier tail latency (**p95** ~**11–13 s** captured in table).
- **Latency:** **`run5`** averages **>** **`run4`** despite similar batching — aligns with varying **provider load** rather than deterministic wall-time per prompt.

*(Legacy runs **1–3** lacking metadata cannot be retrofit-compared — fields absent by design.)*

---

## §5 Watch frame stability (five runs)

Votes = majority **`canon_camera_view`** per envelope.

| Frame | Human | R1 | R2 | R3 | R4 | R5 | Plurality comment |
|-------|-------|-----|-----|-----|-----|-----|-------------------|
| **f941** | other | BE | BE | BE | CU | BE | plurality `bowlers_end` **4**/5 runs |
| **f748** | side_on | BE | CU | CU | CU | BE | plurality `closeup` **3**/5 (split landmark) |
| **f205** | side_on | CU | CU | CU | CU | CU | stable `closeup`, all five |
| **f942** | other | CU | BE | BE | BE | BE | plurality `bowlers_end` **4**/5 |

**Takeaway:** **`f748`** shows elevated dispersion (**`bowlers_end` returns on run5**). **`f941`** hit a singleton **`closeup`** on **run4** only; **`bowlers_end`** still plurality-wins overall.

---

## §6 Five-run consensus histogram

Derived from **`replicate_analysis`** **majority_histogram** (**modal count = number of runs sharing the plurality label**):

- **Modal on 5 / 5 runs:** **38** frames.
- **Modal on 4 / 5 runs:** **2** frames (**`f941`**, **`f942`**).
- **Modal on 3 / 5 runs:** **1** frame (**`f748`**).

Cross-run flip rate (**votes not unanimous across runs**): **7.3%** (**3 / 41** frames) per autogen.

---

## §7 Determinism classification

**Selected label:** **Stochastic inference with observable multi-state migration maps** (**bounded-ish at plurality level**, **not bounded at hash-string level**).

- **Bounded:** **Fails** (**four** hashes / **five** trials).
- **Unbounded** (unique hash every draw): **not proven** — **`7dd…`** repeated once (runs **2–3**); sample size is still thin.
- **Stochastic with weak attractors:** **best fit** — votes often align (**38 / 41** unanimous) while migration hashes proliferate.

**Confidence**

- Hash dispersion: **medium-high** (direct counts).
- Causal attribution to API vs concurrency vs prompt tie-break internals: **low–medium**.

---

## §8 Implications for future Scout work

- **Evaluation:** Prefer **ensemble reports** (**≥5 runs**) or **streaming acceptance bands** (hash histogram + modal metrics) before **`SCOUT_PROMPT`** swap claims.
- **V6d / iterations:** Declare winners only against matching **`K`** and paired timing regimes; store **`groq_*`** fields for regression comparisons.
- **Combined corpus expansion:** Variance tax **increases** value of **M‑2 bucketing / stratification** — not diminished.
- **Production promotion gates:** Recommend explicit **migration-hash multiplicity** thresholds, or require **median net accuracy ≥ V5** across **K** paired runs before a **`SCOUT_PROMPT`** paste.

---

## §9 Recommended next steps

1. **Keep metadata capture shipped** — backfill comparative runs for future variants (**V6d**).
2. Optional **`K`** in **7–10** range for budgeted extra shadows — tighter empirical hash-frequency bands.
3. **Document retry semantics:** operators should expect **`groq_attempt_count` > `1`** under load despite empty **`error`** — do **not** treat **`error`**-empty rows as single-attempt-only evidence.
4. **Backlog:** refresh Scout queue with determinism caveat (this memo and **`scout_v6c_determinism_analysis_autogen.md`**).
5. **Adjacent:** Pass‑2 / side_on canary — unchanged.

---

## §10 Limitations

- **Five** runs ⇒ coarse distribution estimate **only**.
- **`groq_*` keys absent** on runs **1–3**, so latency / retry attribution for those envelopes is retrospective-only.
- **`temperature=0`** does **not** guarantee migration-map uniqueness — observed.
- Provider **KV routing** hypotheses remain **speculative.**

---

## Cross references

| Path | Role |
|------|------|
| `files/docs/investigations/scout_v6c_replicate_runs_decision.md` | Earlier three-run triage |
| `files/docs/scout_v6c_determinism_analysis_autogen.md` | Machine tables (**5-run + metadata**) |
| `files/shadow_eval/run_shadow.py` | Metadata capture patch |
| `files/shadow_eval/replicate_analysis.py` | Majority histogram + Groq aggregates |
