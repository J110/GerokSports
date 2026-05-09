# NEW-BATTER-BALLS-GATE — investigation (2026-04-28)

## Scope

- **Log:** `files/logs/machine-1-2026-04-28.log`
- **Window:** IST **22:19:00–22:35:59** (post-restart monitoring slice referenced in backlog).
- **Method:** `rg "\[NEW-BATTER-BALLS-GATE\]"` filtered by timestamp prefix; surrounding context checked for `[POISON-RECAL]` / `[OVER-RESYNC]` on adjacent frames.

## Fire count

| Metric | Value |
|--------|------:|
| Lines in window | **20** |
| Distinct frames | **10** (each frame appears twice — duplicate `BOARD` lines per timestamp in this build) |
| Distinct (frame, proposed) pairs | **10** |

Full window listing:

```
[22:25:37 F93 BOARD] WARN: [NEW-BATTER-BALLS-GATE] Vaibhav Sooryavanshi: proposed 6(4) exceeds fresh-admission ceiling 3 balls (since_admit=0); dropping row
[22:25:39 F93 BOARD] WARN: [NEW-BATTER-BALLS-GATE] Vaibhav Sooryavanshi: proposed 6(4) exceeds fresh-admission ceiling 3 balls (since_admit=0); dropping row
[22:25:54 F97 BOARD] WARN: [NEW-BATTER-BALLS-GATE] Vaibhav Sooryavanshi: proposed 50(66) exceeds fresh-admission ceiling 3 balls (since_admit=0); dropping row
[22:25:55 F97 BOARD] WARN: [NEW-BATTER-BALLS-GATE] Vaibhav Sooryavanshi: proposed 50(66) exceeds fresh-admission ceiling 3 balls (since_admit=0); dropping row
[22:26:03 F99 BOARD] WARN: [NEW-BATTER-BALLS-GATE] Vaibhav Sooryavanshi: proposed 15(12) exceeds fresh-admission ceiling 3 balls (since_admit=0); dropping row
[22:26:05 F99 BOARD] WARN: [NEW-BATTER-BALLS-GATE] Vaibhav Sooryavanshi: proposed 15(12) exceeds fresh-admission ceiling 3 balls (since_admit=0); dropping row
[22:26:08 F100 BOARD] WARN: [NEW-BATTER-BALLS-GATE] Vaibhav Sooryavanshi: proposed 11(6) exceeds fresh-admission ceiling 3 balls (since_admit=0); dropping row
[22:26:10 F100 BOARD] WARN: [NEW-BATTER-BALLS-GATE] Vaibhav Sooryavanshi: proposed 11(6) exceeds fresh-admission ceiling 3 balls (since_admit=0); dropping row
[22:26:13 F101 BOARD] WARN: [NEW-BATTER-BALLS-GATE] Vaibhav Sooryavanshi: proposed 36(31) exceeds fresh-admission ceiling 3 balls (since_admit=0); dropping row
[22:26:14 F101 BOARD] WARN: [NEW-BATTER-BALLS-GATE] Vaibhav Sooryavanshi: proposed 36(31) exceeds fresh-admission ceiling 3 balls (since_admit=0); dropping row
[22:26:22 F102 BOARD] WARN: [NEW-BATTER-BALLS-GATE] Vaibhav Sooryavanshi: proposed 50(6) exceeds fresh-admission ceiling 3 balls (since_admit=0); dropping row
[22:26:23 F102 BOARD] WARN: [NEW-BATTER-BALLS-GATE] Vaibhav Sooryavanshi: proposed 50(6) exceeds fresh-admission ceiling 3 balls (since_admit=0); dropping row
[22:26:28 F103 BOARD] WARN: [NEW-BATTER-BALLS-GATE] Vaibhav Sooryavanshi: proposed 76(43) exceeds fresh-admission ceiling 3 balls (since_admit=0); dropping row
[22:26:29 F103 BOARD] WARN: [NEW-BATTER-BALLS-GATE] Vaibhav Sooryavanshi: proposed 76(43) exceeds fresh-admission ceiling 3 balls (since_admit=0); dropping row
[22:26:33 F104 BOARD] WARN: [NEW-BATTER-BALLS-GATE] Vaibhav Sooryavanshi: proposed 47(36) exceeds fresh-admission ceiling 3 balls (since_admit=0); dropping row
[22:26:34 F104 BOARD] WARN: [NEW-BATTER-BALLS-GATE] Vaibhav Sooryavanshi: proposed 47(36) exceeds fresh-admission ceiling 3 balls (since_admit=0); dropping row
[22:26:39 F106 BOARD] WARN: [NEW-BATTER-BALLS-GATE] Vaibhav Sooryavanshi: proposed 3(6) exceeds fresh-admission ceiling 3 balls (since_admit=0); dropping row
[22:26:40 F106 BOARD] WARN: [NEW-BATTER-BALLS-GATE] Vaibhav Sooryavanshi: proposed 3(6) exceeds fresh-admission ceiling 3 balls (since_admit=0); dropping row
[22:31:04 F172 BOARD] WARN: [NEW-BATTER-BALLS-GATE] Vaibhav Sooryavanshi: proposed 4(6) exceeds fresh-admission ceiling 3 balls (since_admit=0); dropping row
[22:31:05 F172 BOARD] WARN: [NEW-BATTER-BALLS-GATE] Vaibhav Sooryavanshi: proposed 4(6) exceeds fresh-admission ceiling 4 balls (since_admit=1); dropping row
```

## Recovery context (± few seconds of first fire)

- **`[OVER-RESYNC]`** at **22:19:31 F8** — cursor aligned to over 12 from `score_manager_mid_innings_recovery`, before the F93 burst (~6 minutes earlier in wall clock).
- **`[POISON-RECAL]`** — no line within ±5 frames of **F93** / **F172** in the captured slice; prior POISON events on this file occur earlier (e.g. 21:34–21:57 frames), not in 22:19–22:35.
- **Strip context at F81** (immediately before F93): legitimate RR 151-4 (14.0); pipeline admitted `score→151`; new batter **Vaibhav Sooryavanshi** appears with heavy graphic/strip churn (F82+ `cam=graphic` dead-time skips) — consistent with **unstable reads** while `since_admit=0` stays pinned (admission window not advancing because rows are dropped).

## Per-frame categorization (10 unique frames)

| # | Time | Frame | Proposed | since_admit | Category | Rationale |
|---|------|-------|----------|-------------|----------|-----------|
| 1 | 22:25:37 | F93 | 6(4) | 0 | **AMBIGUOUS** | Plausible early knock; could be tight gate + graphic gap |
| 2 | 22:25:54 | F97 | 50(66) | 0 | **TRUE POSITIVE** | 66 balls vs fresh admit — classic overlay / wrong row |
| 3 | 22:26:03 | F99 | 15(12) | 0 | **AMBIGUOUS** | 12 balls high for admit=0 but not absurd; needs ground truth |
| 4 | 22:26:08 | F100 | 11(6) | 0 | **AMBIGUOUS** | Borderline — 6 balls vs grace 3 |
| 5 | 22:26:13 | F101 | 36(31) | 0 | **TRUE POSITIVE** | 31 balls on fresh row — implausible |
| 6 | 22:26:22 | F102 | 50(6) | 0 | **TRUE POSITIVE** | Runs/balls mismatch pattern (career strip leak) |
| 7 | 22:26:28 | F103 | 76(43) | 0 | **TRUE POSITIVE** | Same class as 50(66) |
| 8 | 22:26:33 | F104 | 47(36) | 0 | **TRUE POSITIVE** | 36 balls vs admit=0 |
| 9 | 22:26:39 | F106 | 3(6) | 0 | **AMBIGUOUS** | Odd runs vs balls; small totals |
| 10 | 22:31:04 | F172 | 4(6) | 0→1 | **FALSE POSITIVE** (soft) | After admit increments to 1, 6 balls vs ceiling 4 may be **legitimate** young innings facing if recovery reset window — **only strong FP candidate** in the slice |

**Totals (conservative):** TP **5**, FP **1**, AMB **4**  
**False-positive rate (FP / (TP+FP)):** 1/6 ≈ **16.7%** — **below 20% threshold**.

## Recommendation

- **No threshold tuning required** on this evidence: the majority of fires are **implausible ball counts** on **`since_admit=0`**, i.e. the gate is doing work against strip/graphic garbage during the post-recovery / close-up ↔ graphic transition (F81→F93).
- **Continue passive monitoring.** If future slices show **predominantly** plausible `(runs, balls)` pairs rejected with **low balls** (e.g. 4(6) with `since_admit` advancing) **and** correlated `[OVER-RESYNC]` / `[POISON-RECAL]`, revisit: **widen grace**, or **reset admission baseline on SM recovery** (separate change — not implemented here).

## Follow-up

None filed: FP rate &lt; 20% per investigation criterion.
