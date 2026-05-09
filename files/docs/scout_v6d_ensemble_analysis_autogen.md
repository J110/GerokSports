# Replicate-run cross-analysis (autogen)

* **Corpus:** `docs/scout_corpus_v1.json` (41 frames, sorted by frame_id)
* **Variant (replicates):** `V6d`
* **Baseline comparison:** `V5` from merged shadow baseline

## Run inputs
* **d1:** `docs/shadow_run_v6d_20260430_145931_run1.json` → `migration_hash=95fee3489ba0410c`
* **d2:** `docs/shadow_run_v6d_20260430_150135_run2.json` → `migration_hash=95fee3489ba0410c`
* **d3:** `docs/shadow_run_v6d_20260430_150414_run3.json` → `migration_hash=b77b83ba73c9c246`
* **d4:** `docs/shadow_run_v6d_20260430_150659_run4.json` → `migration_hash=95fee3489ba0410c`
* **d5:** `docs/shadow_run_v6d_20260430_150944_run5.json` → `migration_hash=95fee3489ba0410c`

## Migration hash stability
* **Distinct hashes:** 2 — ['95fee3489ba0410c', 'b77b83ba73c9c246']
* **Deterministic voting pattern across runs:** `False`

## Internal vs cross-run flip
| Run | Internal flip rate | Strict BE prec | BE emitted | Net acc |
|-----|---------------------|----------------|------------|---------|
| d1 | 2.4% | 35.7% | 14 | 27/41 |
| d2 | 0.0% | 35.7% | 14 | 27/41 |
| d3 | 7.3% | 35.7% | 14 | 26/41 |
| d4 | 2.4% | 35.7% | 14 | 27/41 |
| d5 | 7.3% | 35.7% | 14 | 27/41 |
| **Avg internal flip** | 3.90% | | | |

* **Cross-run flip rate:** 2.4% (1 / 41 frames)
* **Modal vote agreement (across 5 runs):**
  * Plurality on **5/5** runs: **40** frames
  * Plurality on **4/5** runs: **1** frames

## Groq API metadata (additive row fields)
| Run | Meta? | non-null response ids | dup ids in-run? | p50 ms | p95 | p99 | mean ms (ok rows) | models | finish_reason (counts) | attempt_count (counts) |
|-----|-------|------------------------|-----------------|--------|-----|-----|------------------|--------|-------------------------|------------------------|
| d1 | yes | 123 | False | 2107.0 | 13041.099999999991 | 34773.72000000003 | 3495.170731707317 | `meta-llama/llama-4-scout-17b-16e-instruct` | stop=123 | 1=103, 2=12, 3=6, 5=2 |
| d2 | yes | 123 | False | 3090.0 | 12937.5 | 21849.740000000013 | 4712.536585365854 | `meta-llama/llama-4-scout-17b-16e-instruct` | stop=123 | 1=77, 2=35, 3=9, 4=1, 5=1 |
| d3 | yes | 123 | False | 3393.0 | 13853.8 | 25379.34 | 5092.373983739837 | `meta-llama/llama-4-scout-17b-16e-instruct` | stop=123 | 1=79, 2=33, 3=7, 4=3, 5=1 |
| d4 | yes | 123 | False | 3274.0 | 13043.9 | 21772.140000000014 | 5114.90243902439 | `meta-llama/llama-4-scout-17b-16e-instruct` | stop=123 | 1=72, 2=40, 3=9, 4=1, 5=1 |
| d5 | yes | 123 | False | 3384.0 | 21936.799999999934 | 24247.78 | 5388.926829268293 | `meta-llama/llama-4-scout-17b-16e-instruct` | stop=123 | 1=79, 2=32, 3=5, 4=6, 5=1 |

## Baseline row (merged analysis anchors)
* `V5` strict BE precision: **31.2%** (16 emitted)
* `V5` net accuracy: **20/41**
* `V5` internal flip rate: **7.3%**

## Watch frames (votes per run)
* **`f941`:** run1='other', run2='other', run3='other', run4='other', run5='other'
* **`f748`:** run1='bowlers_end', run2='bowlers_end', run3='bowlers_end', run4='bowlers_end', run5='bowlers_end'
* **`f205`:** run1='closeup', run2='closeup', run3='closeup', run4='closeup', run5='closeup'
* **`f942`:** run1='bowlers_end', run2='bowlers_end', run3='bowlers_end', run4='bowlers_end', run5='bowlers_end'

## Sample differing frames (run1 vs later runs)
* `f180` run1→run3: 'other' → 'closeup'

