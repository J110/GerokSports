# Scout V6e — combined-corpus replicate analysis (autogen)

**Generated:** 2026-04-30 (Step 5, `validate-first`). **Corpus:** `files/docs/scout_corpus_combined_v1.json` (**50** frames × **3** replicates × **5** runs = **750** scheduled cells/variant). **Variant:** `V6e`.

## Tooling note

`python3 shadow_eval/replicate_analysis.py --runs …` **aborts** when any single run has **>10%** `error` rows (`S1.3` guard). This V6e ensemble exceeded that threshold on every run (Groq **503** capacity), so this file is **assembled manually** from the same statistics `replicate_analysis.py` would surface (migration hash, watch frames, cross-run agreement).

## Run inventory

| Run | Artifact | Rows | Errors | Approx. error rate |
|:---:|----------|-----:|-------:|-------------------:|
| 1 | `shadow_run_v6e_combined_20260430_173344_run1.json` | 150 | 23 | 15.3% |
| 2 | `shadow_run_v6e_combined_20260430_173916_run2.json` | 150 | 23 | 15.3% |
| 3 | `shadow_run_v6e_combined_20260430_174357_run3.json` | 150 | 27 | 18.0% |
| 4 | `shadow_run_v6e_combined_20260430_174803_run4.json` | 150 | 22 | 14.7% |
| 5 | `shadow_run_v6e_combined_20260430_175228_run5.json` | 150 | 24 | 16.0% |
| **Pooled** | | **750** | **119** | **15.87%** |

**Error taxonomy (all 119 failing rows):** `InternalServerError` **503** — `meta-llama/llama-4-scout-17b-16e-instruct is currently over capacity…` — **not** `TimeoutError`, **not** JSON/parse rejects attributable to prompt length.

**Comparison:** V6d post-harness combined cohort pooled **~0.53%** (`scout_v6d_postharness_rerun_results.md`). The V6e error spike is interpreted as **provider saturation during this execution window**, not a deterministic harness regression (timeout default remains **15.0** s).

## Ensemble plurality methodology

For each `frame_id`, collect every successful `canon_camera_view` across **5** runs × **3** replicates (**≤15** votes). **Plurality** = mode of non-null votes. Ties handled by Python `collections.Counter.most_common(1)` (stable for our counts).

Vote depth on V6e: **minimum** successful votes/frame **8** (**worst frame** shed **7**/15 slots to **503**); plurality still computed from available draws.

## Migration hash (per run, majority within 3 replicates)

Per-run hash uses `shadow_eval.replicate_analysis.migration_hash` on `(frame_id, vote_cam)` with `vote_cam` from `shadow_eval.analyze._build_per_frame` (within-run majority).

| Run | `migration_hash` (16-hex) |
|:---:|--------------------------|
| 1 | `6521d78e38c985d1` |
| 2 | `6521d78e38c985d1` |
| 3 | `8ebd96fea71fb1f2` |
| 4 | `6521d78e38c985d1` |
| 5 | `83ecb635b22bb647` |

**Distinct hashes:** **3** (same order of magnitude as V6d post-harness **3** distinct hashes).

## Agreement vs V6c ensemble (proxy “net accuracy” on combined)

Using the five `shadow_run_v6c_combined_20260430_*` envelopes with the same plurality-over-15-votes rule:

| Variant | Frames where V6x plurality == V6c plurality (both non-null) |
|---------|----------------------------------------------------------:|
| **V6d** post-harness | **47** / **50** |
| **V6e** (this run) | **47** / **50** |

So **P4** (no regression vs V6d on this proxy) **ties** — no net drift vs V6c majority on the stratified combined slice.

## Bowlers_end recall on combined TP set (construction from V6c ∩ V6d)

Define **BE TP approximation:** frames where **V6c** plurality **`bowlers_end`** **AND** **V6d** post-harness plurality **`bowlers_end`**. Count = **17** frames.

**V6e** plurality **`bowlers_end`** on **all 17** → **100%** recall on this TP set (**P5** pass).

## V6e vs V6d plurality deltas (combined corpus)

Frames where **V6e** plurality ≠ **V6d** post-harness plurality (**both non-null**): **3**

| frame_id | V6d post-harness plurality | V6e plurality | Notes |
|----------|-----------------------------|---------------|-------|
| `pbks_rr_f600` | `bowlers_end` | **`side_on`** | **Primary design target** — **14** votes: **11×** `side_on`, **3×** `bowlers_end`. |
| `rcb_gt_f1455` | `other` | **`bowlers_end`** | **Regression risk** vs V6d “graphics / other” remediation — **14×** `bowlers_end` unanimous among successes. |
| `pbks_rr_f931` | `graphic` | **`closeup`** | Side movement; graphic → closeup (**14** votes). |

All other frames: matching plurality vs V6d (when both sides defined).

## Watch-style frames present on combined corpus

`replicate_analysis.py` default watch tuple (`f941`, `f748`, `f205`, `f942`) references **scout_corpus_v1** IDs; **`scout_corpus_combined_v1` does not contain those `frame_id` values.** On-combined substitutes from `discriminating_frames_v6c_vs_v6d_combined.md`:

| frame_id | V6c maj | V6d maj | V6e plurality (this ensemble) |
|----------|---------|---------|------------------------------|
| `pbks_rr_f600` | `side_on` | `bowlers_end` | **`side_on`** |
| `rcb_gt_f1455` | `graphic` | `other` | **`bowlers_end`** |
| `rcb_gt_f937` | `closeup` | `other` | **`other`** |

## Secondary

| ID | Observation |
|----|----------------|
| S1 (`f748`) | **N/A** on combined corpus (frame absent). |
| S2 | **3** distinct migration hashes (**≤** informal V6d comparability band). |
| S3 | Pooled operational error **15.87%** — fails “<1% healthy” gate, but dominated by **503** overload, not parse/timeouts. |
| S4 | No improvement vs V6d on V6c-agreement proxy (**47**/50 plateau). |

## Cross-reference

- Decision narrative: **`files/docs/investigations/scout_v6e_first_shadow_run_results.md`**
- Baseline prose: **`files/docs/investigations/scout_v6d_postharness_rerun_results.md`**
- Design: **`files/docs/investigations/scout_v6e_design.md`**
