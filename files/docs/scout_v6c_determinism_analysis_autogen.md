# Replicate-run cross-analysis (autogen)

* **Corpus:** `docs/scout_corpus_v1.json` (41 frames, sorted by frame_id)
* **Variant (replicates):** `V6c`
* **Baseline comparison:** `V5` from merged shadow baseline

## Run inputs
* **run1:** `docs/shadow_run_v6c_20260430_140220.json` → `migration_hash=b0b1d9c701d48100`
* **run2:** `docs/shadow_run_v6c_20260430_141433_run2.json` → `migration_hash=7dd8483e30258c16`
* **run3:** `docs/shadow_run_v6c_20260430_141629_run3.json` → `migration_hash=7dd8483e30258c16`
* **run4:** `docs/shadow_run_v6c_20260430_143705_run4.json` → `migration_hash=1c6482a31e208280`
* **run5:** `docs/shadow_run_v6c_20260430_143910_run5.json` → `migration_hash=d3044e9a4d9d2f72`

## Migration hash stability
* **Distinct hashes:** 4 — ['1c6482a31e208280', '7dd8483e30258c16', 'b0b1d9c701d48100', 'd3044e9a4d9d2f72']
* **Deterministic voting pattern across runs:** `False`

## Internal vs cross-run flip
| Run | Internal flip rate | Strict BE prec | BE emitted | Net acc |
|-----|---------------------|----------------|------------|---------|
| run1 | 14.6% | 33.3% | 15 | 19/41 |
| run2 | 7.3% | 33.3% | 15 | 19/41 |
| run3 | 9.8% | 33.3% | 15 | 19/41 |
| run4 | 12.2% | 35.7% | 14 | 19/41 |
| run5 | 4.9% | 31.2% | 16 | 19/41 |
| **Avg internal flip** | 9.76% | | | |

* **Cross-run flip rate:** 7.3% (3 / 41 frames)
* **Modal vote agreement (across 5 runs):**
  * Plurality on **5/5** runs: **38** frames
  * Plurality on **4/5** runs: **2** frames
  * Plurality on **3/5** runs: **1** frames

## Groq API metadata (additive row fields)
| Run | Meta? | non-null response ids | dup ids in-run? | p50 ms | p95 | p99 | mean ms (ok rows) | models | finish_reason (counts) | attempt_count (counts) |
|-----|-------|------------------------|-----------------|--------|-----|-----|------------------|--------|-------------------------|------------------------|
| run1 | no | — | — | — | — | — | — | — | — | — |
| run2 | no | — | — | — | — | — | — | — | — | — |
| run3 | no | — | — | — | — | — | — | — | — | — |
| run4 | yes | 123 | False | 1841.0 | 11243.09999999997 | 20197.88000000001 | 3441.2520325203254 | `meta-llama/llama-4-scout-17b-16e-instruct` | stop=123 | 1=95, 2=21, 3=5, 4=1, 5=1 |
| run5 | yes | 123 | False | 2955.0 | 13396.499999999996 | 23338.56 | 4508.121951219512 | `meta-llama/llama-4-scout-17b-16e-instruct` | stop=123 | 1=87, 2=23, 3=10, 4=2, 5=1 |

## Baseline row (merged analysis anchors)
* `V5` strict BE precision: **31.2%** (16 emitted)
* `V5` net accuracy: **20/41**
* `V5` internal flip rate: **7.3%**

## Watch frames (votes per run)
* **`f941`:** run1='bowlers_end', run2='bowlers_end', run3='bowlers_end', run4='closeup', run5='bowlers_end'
* **`f748`:** run1='bowlers_end', run2='closeup', run3='closeup', run4='closeup', run5='bowlers_end'
* **`f205`:** run1='closeup', run2='closeup', run3='closeup', run4='closeup', run5='closeup'
* **`f942`:** run1='closeup', run2='bowlers_end', run3='bowlers_end', run4='bowlers_end', run5='bowlers_end'

## Sample differing frames (run1 vs later runs)
* `f748` run1→run2: 'bowlers_end' → 'closeup'
* `f942` run1→run2: 'closeup' → 'bowlers_end'
* `f748` run1→run3: 'bowlers_end' → 'closeup'
* `f942` run1→run3: 'closeup' → 'bowlers_end'
* `f748` run1→run4: 'bowlers_end' → 'closeup'
* `f941` run1→run4: 'bowlers_end' → 'closeup'
* `f942` run1→run4: 'closeup' → 'bowlers_end'
* `f942` run1→run5: 'closeup' → 'bowlers_end'

