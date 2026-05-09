# M-2 combined-corpus stratified sampler

**Last updated:** 2026-04-30

---

## §1 Purpose

Build a **multi-match, phase×innings–stratified** Scout labeling corpus with an auditable **bucket-coverage** report (rubric M-2). This unblocks **distribution validation** for prompt work (e.g. **V6d**) beyond the single-match **41-frame** `scout_corpus_v1.json` slice, without replacing the existing **subset-stratified** candidate selector.

---

## §2 M-2 specification reference

See **`files/docs/scout_labeling_rubric_v1.md`** — **M-2 (Sampler bucket-coverage requirement)**:

- Emit a report with the sample; for each stratification bucket, **`pool > 0`** and **`sampled = 0`** is disallowed unless explicitly **documented**.
- Remedy: re-sample or record **`pool=N, sampled=0 by design`** with a reason.

Implementation matches that contract via **`metadata.bucket_coverage`**, stderr lines prefixed **`[BUCKET-COVERAGE]`**, and optional **`--document-empty BUCKET:REASON`**.

---

## §3 Bucket taxonomy (phase × innings)

**Six primary buckets** (fixed order in reports):

`powerplay_inn1`, `middle_inn1`, `death_inn1`, `powerplay_inn2`, `middle_inn2`, `death_inn2`

**T20 IPL default** (configurable only in code today):

- **Powerplay:** 1st–6th over (1-based over segment from `ball_event_over`).
- **Middle:** 7th–15th over.
- **Death:** 16th–20th over.

**Over parsing:** cricket strings such as `14.5` → 15th-over segment (`int(whole)+1` from the float form built in the script).

**Innings:** not stored in **`corpus_frame_inventory.json`**. The combined sampler **infers** innings by walking each inventory’s **`events`** in **`frame_count`** order: a **large backward jump** in parsed over (default threshold: **> 4** fewer than the previous event) increments the innings counter. This matches typical “15.x → 0.1” resets; see module docstring for limitations.

**Eligible frames:** **`scout_frame_type == "SCOREBOARD"`** only (same spirit as **`select_corpus_candidates.py`**).

**Camera as second dimension:** deferred; only phase×innings buckets in this version.

---

## §4 Implementation summary

**Script:** **`files/scripts/select_combined_scout_corpus.py`**

- **Inputs:** one or more **`--inventory`** JSON files (same top-level shape as **`build_frame_inventory.py`** output: **`events`**, **`frames`**). Optional per-file **`match_id`**; else basename is used.
- **Outputs:** **`--output`** corpus JSON with **`frames[]`**, top-level keys aligned with **`scout_corpus_v1.json`** (version, source_log, labeling_rubric, selection_method, subset_targets, etc.) and additive **`metadata`** (`seed`, `bucket_coverage`, `pool_counts_by_bucket`, inventories list).
- **Per frame:** existing rubric-oriented fields plus additive **`phase_bucket`**, **`match_id`**, **`subset: combined_stratified`**, human fields set to **`pending`** for a follow-up labeling pass.
- **Determinism:** **`--seed`**; JSON written with **`sort_keys=True`** for stable diffs.
- **Strict CI-style gate:** **`--strict`** → exit code **2** if any bucket **`WARN`** or **`UNDOCUMENTED_ZERO`** after sampling.
- **Coverage statuses:**
  - **`OK`**
  - **`UNDOCUMENTED_ZERO`**: `pool > 0`, `sampled == 0`, bucket not in **`--document-empty`**
  - **`WARN`**: `sampled > 0` but **`sampled < min(pool, target)`**

**Tests:** **`files/test_recent_fixes.py`** (`test_combined_sampler_*`).

---

## §5 Backward compatibility

- **`run_shadow.py`** only requires **`frame_id`** and **`path`** on each corpus row; additive keys are ignored.
- Existing **`select_corpus_candidates.py`** path and **`scout_corpus_v1.json`** corpus are **unchanged**; this tool is **additive**.

---

## §6 Usage examples

From repo root:

```bash
python3 files/scripts/select_combined_scout_corpus.py \
  --inventory files/corpus_frame_inventory.json \
  --inventory path/to/second_match_inventory.json \
  --output files/docs/scout_corpus_combined_v1.json \
  --target-per-bucket 8 \
  --seed 42
```

Intentional empty bucket (documented):

```bash
... --document-empty death_inn2:innings_2_not_available_in_source_logs
```

Strict run (fail if any gap):

```bash
... --strict
```

**`run_shadow` prep (multi-match):** overlapping `frame_count` across inventories
produces colliding `frame_id` / jpeg basenames unless you flatten. After the
sampler, run **`files/scripts/materialize_combined_corpus_frames.py`** to copy
referenced JPEGs into e.g. **`docs/corpus_frames_combined_v1/`** and rewrite
**`path`** + **`frame_id`**, then point **`run_shadow`** at
**`--frames-dir docs/corpus_frames_combined_v1`**.

---

## §7 Coordination with `select_corpus_candidates.py`

| Tool | Stratification | Output |
|------|----------------|--------|
| **`select_corpus_candidates.py`** | Labeling **subsets** (closeup / disambiguation / active-play recall) | **`corpus_candidates.json`** |
| **`select_combined_scout_corpus.py`** | **Phase × innings** across matches | Full **corpus-shaped** JSON for shadow / labeling |

They are **complementary**, not replacements.

---

## §8 Validation against rubric M-2

| M-2 ask | Implementation |
|--------|----------------|
| Bucket coverage with sample | **`metadata.bucket_coverage`** |
| Warn when non-empty pool yields zero sample | **`[BUCKET-COVERAGE] UNDOCUMENTED_ZERO`** on stderr unless documented |
| Explicit “by design” | **`--document-empty BUCKET:REASON`** |

---

## §9 Future work

- Optional **second-axis** stratification (e.g. **`scout_cam`**).
- **Format-specific** over boundaries (ODI/Test) as flags.
- **CI** recipe: run sampler on checked-in fixtures with **`--strict`**.
- Optional **`build_frame_inventory.py`** fields **`innings` / `phase_bucket`** to make innings non-heuristic when logs support it.
