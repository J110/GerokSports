# Replicate-run cross-analysis (autogen)

* **Corpus:** `docs/scout_corpus_v1.json` (41 frames, sorted by frame_id)
* **Variant (replicates):** `V6c`
* **Baseline comparison:** `V5` from merged shadow baseline

## Run inputs
* **run1:** `docs/shadow_run_v6c_20260430_140220.json` → `migration_hash=b0b1d9c701d48100`
* **run2:** `docs/shadow_run_v6c_20260430_141433_run2.json` → `migration_hash=7dd8483e30258c16`
* **run3:** `docs/shadow_run_v6c_20260430_141629_run3.json` → `migration_hash=7dd8483e30258c16`

## Migration hash stability
* **Distinct hashes:** 2 — ['7dd8483e30258c16', 'b0b1d9c701d48100']
* **Deterministic voting pattern across runs:** `False`

## Internal vs cross-run flip
| Run | Internal flip rate | Strict BE prec | BE emitted | Net acc |
|-----|---------------------|----------------|------------|---------|
| run1 | 14.6% | 33.3% | 15 | 19/41 |
| run2 | 7.3% | 33.3% | 15 | 19/41 |
| run3 | 9.8% | 33.3% | 15 | 19/41 |
| **Avg internal flip** | 10.57% | | | |

* **Cross-run flip rate:** 4.9% (2 / 41 frames)
* **Agreement buckets:**
  * All runs agree: **39**
  * Two-vs-one split: **2**
  * Three distinct votes: **0**

## Baseline row (merged analysis anchors)
* `V5` strict BE precision: **31.2%** (16 emitted)
* `V5` net accuracy: **20/41**
* `V5` internal flip rate: **7.3%**

## Watch frames (votes per run)
* **`f941`:** run1='bowlers_end', run2='bowlers_end', run3='bowlers_end'
* **`f748`:** run1='bowlers_end', run2='closeup', run3='closeup'
* **`f205`:** run1='closeup', run2='closeup', run3='closeup'

## Sample differing frames (run1 vs later runs)
* `f748` run1→run2: 'bowlers_end' → 'closeup'
* `f942` run1→run2: 'closeup' → 'bowlers_end'
* `f748` run1→run3: 'bowlers_end' → 'closeup'
* `f942` run1→run3: 'closeup' → 'bowlers_end'

