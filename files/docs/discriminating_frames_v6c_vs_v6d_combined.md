# V6c vs V6d — discriminating frames (combined corpus)

## §1 Summary

- **Combined corpus frames:** 50
- **Agree (maj V6c = maj V6d):** 47
- **Discriminating:** 3 (6.0% of corpus)
- **Missing majority on ≥1 variant:** 0

## §2 Discriminating frames

| frame_id | phase_bucket | match_id | V6c maj | V6d maj | path |
|----------|--------------|----------|---------|---------|------|
| `rcb_gt_f1455` | `middle_inn2` | `rcb_gt` | `graphic` | `other` | `docs/corpus_frames_combined_v1/rcb_gt_f1455_scoreboard.jpg` |
| `pbks_rr_f600` | `powerplay_inn1` | `pbks_rr` | `side_on` | `bowlers_end` | `docs/corpus_frames_combined_v1/pbks_rr_f600_scoreboard.jpg` |
| `rcb_gt_f937` | `powerplay_inn2` | `rcb_gt` | `closeup` | `other` | `docs/corpus_frames_combined_v1/rcb_gt_f937_scoreboard.jpg` |

## §3 Per-bucket disagreement

- **powerplay_inn1:** 1
- **middle_inn2:** 1
- **powerplay_inn2:** 1

## §4 Pattern notes

- **V6c bowlers_end → V6d other (f941-class):** 0
- **V6c closeup → V6d bowlers_end (f748-class):** 0

> Labels are ensemble majorities — not adjudicated accuracy.

## §5 Labeling recommendations

- **Prioritize:** 3 discriminating frames only.
- **Rough wall time (~45 s/frame):** ~2 min.

## §6 Run inventory

### V6c
- `shadow_run_v6c_combined_20260430_160124_run1.json` — rows 150, errs 0 (**0.0%**)
- `shadow_run_v6c_combined_20260430_160350_run2.json` — rows 150, errs 1 (**0.67%**)
- `shadow_run_v6c_combined_20260430_160704_run3.json` — rows 150, errs 0 (**0.0%**)
- `shadow_run_v6c_combined_20260430_161022_run4.json` — rows 150, errs 0 (**0.0%**)
- `shadow_run_v6c_combined_20260430_161334_run5.json` — rows 150, errs 2 (**1.33%**)

### V6d
- `shadow_run_v6d_combined_20260430_161648_run1.json` — rows 150, errs 15 (**10.0%**)
- `shadow_run_v6d_combined_20260430_161955_run2.json` — rows 150, errs 17 (**11.33%**)
- `shadow_run_v6d_combined_20260430_162259_run3.json` — rows 150, errs 5 (**3.33%**)
- `shadow_run_v6d_combined_20260430_162617_run4.json` — rows 150, errs 3 (**2.0%**)
- `shadow_run_v6d_combined_20260430_162926_run5.json` — rows 150, errs 7 (**4.67%**)

### Majority hashes

- **V6c pooled majority hash:** `94bbfc19a0c59adb`
- **V6d pooled majority hash:** `69006a063bd354a9`
- **V6c ties:** 0
- **V6d ties:** 0

## §7 Cross-run validation notes (workflow flags)

- **S3.1 (Groq errors):** V6d peaked at roughly **11%** failing rows in one ensemble run;
  V6c stayed at or below **~1.3%**. Corpus bytes + JPEG paths validated via planning
  dry-run; treat elevated V6d errors as provider / rate-limit pressure, not schema
  breakage, unless a rerun at lower concurrency still spikes.
- **S3.2 (discrimination rate):** **6%** (**3**/50) is **below** the informal **20–30%**
  band from the smaller 41-frame slice — V6c and V6d **mostly agree** here; the tiny
  discriminating set is still the correct **label-first** queue.
- **S3.3 (bucket concentration):** One disagreeing frame each in **three** buckets — not
  a single-bucket pile-up.
