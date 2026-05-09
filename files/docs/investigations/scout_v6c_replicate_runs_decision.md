# Scout V6c — three replicate shadow runs: decision (corpus_v1)

**Date:** 2026-04-30  
**Scope:** Offline shadow only; production `files/eyes/vision.py` unchanged. Three independent **`V6c`** runs (**`--no-resume`**) on **`files/docs/scout_corpus_v1.json`** (**41** frames, **123** rows each).

**Machine tables:** `files/docs/scout_v6c_replicate_analysis_autogen.md` (from `files/shadow_eval/replicate_analysis.py`).

---

## §1 Executive summary

- **Runs completed:** Three **`V6c`** envelopes, **0** non-empty **`error`** rows on each (**123 / 123**).
- **Migration hashes** (sorted **`(frame_id, vote_cam)`**, SHA-256 first 16 hex chars — see autogen tool):
  - **Run 1:** `b0b1d9c701d48100` — `files/docs/shadow_run_v6c_20260430_140220.json`
  - **Run 2:** `7dd8483e30258c16` — `files/docs/shadow_run_v6c_20260430_141433_run2.json`
  - **Run 3:** `7dd8483e30258c16` — `files/docs/shadow_run_v6c_20260430_141629_run3.json`
- **Hash equality:** **Two** distinct patterns — run **2** and **3** are **identical**; run **1** differs. **Therefore V6c is not fully deterministic across independently launched runs** on this harness, but divergence is **narrow** (cross-run disagreement on **2 / 41** frames, **4.9%**).
- **Internal cam flip rate** (within-run variance across 3 replicates): **14.6%** (run 1), **7.3%** (run 2), **9.8%** (run 3); **avg 10.6%** vs **V5** **7.3%**. Run 1’s **doubled** flip rate versus V5 is **not reproduced** on runs 2–3.
- **Cross-run flip rate** (majority vote differs across at least one pair of runs): **4.9%** (**2** frames) — **much smaller** than run 1’s internal **14.6%**, so cross-run disagreement is **not** the dominant variance mode.
- **Headline vs V5:** **Strict `bowlers_end` precision** stays **33.3%** (**15** emitted) on **all three** runs (**+2.1 pp** vs V5 **31.2%**). **Net frame accuracy** (**vote_cam == human**, N=41) is **19/41** on **all three** runs vs **V5** **20/41** → **regression reproducible**, not a single-run sampling fluke.
- **Decision (classification):** **V6c regresses vs V5 on net accuracy in a stable way across three runs** (**(a)**), while **migration-level behavior is partially unstable: first run is an outlier versus the later pair** — consistent with **mixed (a) + partial first-run atypicality ((c))**. **Not** the “each run is wholly different” profile of runaway API chaos (**(b)** in the strong sense); cross-run flip is low.
- **Recommended next action:** (1) Treat **net 19/41** and **+2.1 pp strict BE** as the **reliable** trade-off signal until more runs; (2) optionally add a **4th** run if we need to know whether run 1 or the run2/3 lineage is closer to long-run Groq behavior; (3) **do not** ship **V6c** to **`SCOUT_PROMPT`** on this evidence alone; favour **V6d** hypotheses or **determinism probes** (timing, rate limits, retries) if migration parity with archived **2026-04-25** narrative matters for promotion rhetoric; (4) keep **combined corpus** work **conditional** on sampler **M-2** and explicit ship bands (`scout_v6c_shadow_run_scoping.md`).

---

## §2 Run inventory

Executed from **`files/`**:

```text
python3 shadow_eval/run_shadow.py --variants V6c --corpus docs/scout_corpus_v1.json \
  --output docs/shadow_run_v6c_<TS>_run{N}.json --no-resume
```

| Run | Timestamp (filename) | Output file | Wall-clock (observer) | Errors |
|-----|----------------------|-------------|------------------------|--------|
| 1 | `20260430_140220` | `files/docs/shadow_run_v6c_20260430_140220.json` | ~107 s (logged in first-run results doc) | 0/123 |
| 2 | `20260430_141433` | `files/docs/shadow_run_v6c_20260430_141433_run2.json` | **110** s | 0/123 |
| 3 | `20260430_141629` | `files/docs/shadow_run_v6c_20260430_141629_run3.json` | **165** s | 0/123 |

Run 3 wall-clock is **~1.5×** run 2 (likely **rate limiting / provider pacing** — still **not** the “5× anomaly” stop condition). All **`total_calls`** fields read **123**.

**Path note:** Invoking from **`files/shadow_eval/`** with **`--corpus ../docs/...`** resolves under the repo’s **`files/`** root incorrectly; use **`--corpus docs/scout_corpus_v1.json`** from **`files/`** (see failed attempt in session log).

---

## §3 Migration hash analysis

- **Per-run hashes:** listed in §1 (two unique values).
- **Equality check:** **Fails** — **not** identical triple.
- **Frames that differ (run 1 vs runs 2–3 majority votes):** **`f748`** and **`f942`** (see §4 and autogen “Sample differing frames”).
- **§3.1 — If V6c were fully deterministic (three equal hashes):** *Not applicable* — we observe **two** hashes. The **stable** portion is: **runs 2 and 3 agree on every frame-level majority vote.**
- **§3.2 — Non-determinism pattern:** **Bounded.** **Cross-run flip 4.9%** vs run 1 **internal** flip **14.6%** ⇒ **within-run variance on run 1** spiked **beyond** cross-run disagreement. **Interpretation:** Run 1 combines **(i)** a **different migration map** on **two** frames versus the later pair **and** **(ii)** **higher replicate churn**; runs 2–3 look like a **paired replicate state** (same hash). Favour **provider/session/timing** sensitivity over “prompt is intrinsically pure noise” — but **N=3** runs is a **minimum**.

---

## §4 Per-frame vote stability (across three runs)

From **`replicate_analysis`** agreement buckets (corpus order, N=41):

- **All three runs agree:** **39** frames.
- **Two-of-three split:** **2** frames (**`f748`**, **`f942`**).
- **All three differ:** **0** frames.

**Watch frames** (majority **`canon_camera_view`** per run):

| Frame | Human | Run 1 | Run 2 | Run 3 | Note |
|-------|-------|-------|-------|-------|------|
| **f941** | `other` | `bowlers_end` | `bowlers_end` | `bowlers_end` | **Escalation is stable** across all three — not a run-1-only artifact. |
| **f748** | `side_on` | `bowlers_end` | `closeup` | `closeup` | Run 1 matches the “stuck **`bowlers_end`**” failure in the first-run memo; **runs 2–3** match the **2026-04-25**-*style* remediation (**→ `closeup`**). |
| **f205** | `side_on` | `closeup` | `closeup` | `closeup` | **Stable** boundary-closeup pattern across all three (aligns with narrative intent). |

---

## §5 Comparison to 2026-04-25 narrative

Source: **`files/docs/scout_v6c_shadow_run_corpus_v1_2026-04-25.md`** (and first-run results cross-ref).

- **`f748` “improvement” claim:** **Only runs 2–3** show **`closeup`** majority; **run 1** does **not**. **Aggregated** conclusion: **narrative partially matches** the **later** replicate state, **not** the **earliest** timestamped JSON.
- **`f205` remediation:** **Consistent `closeup`** — **matches** the remediation story **across all runs**.
- **`f941` watch item:** **Stable `bowlers_end`** on all three runs — **worse** than the corpus doc’s **`closeup`-FP** framing; **operational severity remains**.
- **Strict `bowlers_end` precision:** **33.3%** each run — **matches** the **+2.1 pp** headline vs V5 **throughout**.

**Honest read:** The **2026-04-25** story is **not** refuted on **strict BE** or **`f205`**, but **`f748`** and migration **hash** parity are **time/run sensitive**, and **`f941`** **contradicts** a benign single-run interpretation.

---

## §6 Aggregate metrics

| Metric | V5 | V6c run 1 | V6c run 2 | V6c run 3 | V6c aggregate |
|--------|----|-----------|-----------|-----------|---------------|
| Strict `bowlers_end` precision | 31.2% (16) | 33.3% (15) | 33.3% (15) | 33.3% (15) | **33.3%** (identical) |
| Net frame accuracy (N=41) | 20/41 | 19/41 | 19/41 | 19/41 | **19/41** (stable) |
| Internal flip rate | 7.3% | 14.6% | 7.3% | 9.8% | **mean 10.6%** |
| Cross-run flip rate (V6c) | n/a | — | — | — | **4.9%** (2/41) |

---

## §7 Decision

- **Primary label:** **V6c regresses vs V5 on net accuracy** — **replicated** on **three** runs (**confidence: high** on that scalar).
- **Secondary label:** **Partial run-to-run migration instability** (**two** hashes; **2** frames discordant) **with** a **strong pair agreement** (runs **2 ≡ 3**) — **confidence: medium** on mechanistic cause (Groq pacing, retries, latent sampling despite **`temperature=0`** in harness — see `run_shadow.py`).
- **`f941` stability** pushes **overall ship posture** toward **“do not paste V6c”** absent **`V6d`** or **`f941`-targeted** prompt discipline.

---

## §8 Recommended next steps

1. **Prompt iteration (`V6d`):** Explicitly target **`f941`** (**`other`** → forbid **`bowlers_end`** escalation) **without** sacrificing **`f205`/`f748`** gains observable in runs **2–3**.
2. **Determinism / harness hygiene:** Log **Groq response ids** / **attempt counts** per row if feasible; rerun **two** disjoint shadows back-to-back to see if **paired hash recurrence** persists.
3. **If treating run 2–3 as “preferred” lineage:** Document that **migration hash `7dd8483e30258c16`** is the **paired-replicate fingerprint** vs **`b0b1d9c701d48100`** (**run 1**).
4. **Combined corpus expansion:** Still **sampler M‑2 prerequisite** (`files/docs/backlog.md`); outcome here **does not** green-light spend — it clarifies variance bands.
5. **Adjacent backlog:** **Pass‑2**, **`side_on` canary** — **status unchanged** (defer).

---

## §9 Limitations

- **N=41**, single lineage (**RCB–GT–derived** corpus).
- **Three** runs is a **minimal** variance sample; ambiguous **paired** equality (**run 2 = run 3**) could be **lucky** concurrency — §8 recommends optional **4th / 5th** run before **hard** migration claims.
- **Cross-run analysis** cannot observe **Groq-internal** KV cache — only **exported** **`canon_*`** votes.
- **Wall-clock drift** (**165 s** on run 3) warns **against** naive “identical infra” assumptions even with **`temperature=0`**.

---

## Cross references

| Path | Purpose |
|------|---------|
| `files/docs/investigations/scout_v6c_first_shadow_run_results.md` | First-run mixed metrics memo |
| `files/docs/investigations/scout_v6c_shadow_run_scoping.md` | Metrics framework + backlog adjacency |
| `files/docs/scout_v6c_replicate_analysis_autogen.md` | Automated cross-run aggregates |
| `files/shadow_eval/replicate_analysis.py` | Replication CLI (`--runs`, `--baseline`, `--out-md`) |
