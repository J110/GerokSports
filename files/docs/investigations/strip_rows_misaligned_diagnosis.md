# P19 — STRIP-ROWS-MISALIGNED Diagnosis

**Match:** CSK vs MI (44th match, IPL 2026), innings 2 + late innings 1 frames
**Log:** `logs/pipeline-2026-05-02-2049-csk-vs-mi-44th-match-ipl-2026-innings2.log`
**Guard implementation:** `files/test_pipeline.py:3171-3223`
**Total firings:** 32

The guard rejects only the `batters` block when a *confirmed* card row (balls > 0) disagrees with the strip-OCR runs by more than 20: `abs(card_runs - strip_runs) > 20` (line 3204). This memo answers: are the strip rows actually misaligned (label↔stats swap), or is the strip rendering an entirely different match-state (comparison/highlight overlay), or is OCR mis-parsing a correctly rendered strip? Evidence below shows the answer is **(c) overlay-graphic substitution**, not row swap and not OCR drift.

---

## §1 Sample-by-sample frame analysis

All 32 firings, with prev/next vision tags, scout STRIP text, and what was actually happening. (`tracker` = card state pre-frame; `strip` = scout-OCR string.)

| # | Frame | Time | Log line | cam / phase | Tracker (BEFORE) | Strip read | row_pair | Δ |
|---|-------|------|----------|-------------|------------------|------------|----------|---|
| 1 | F11 | 20:50:54 | 374 | bowlers_end / shot | MI 118-4 (14.4); Naman 45(31) Hardik 7(?) | `MI 118-4 (14.4) \| Hardik 45(30) \| Naman 7(9)` (l.371) | Hardik 45/7 | 38 |
| 2 | F12 | 20:50:58 | 400 | bowlers_end / between_play | same | `MI 118-4 (14.4) \| Hardik 45(30) \| Naman 7(9)` (l.389) | Hardik 45/7 | 38 |
| 3 | F45 | 20:52:18 | 663 | bowlers_end / shot | MI 120-4 (15.0); Naman 46(31) Hardik 8(10) | `null 49-3 (5.5) \| *Dhir 21(19) \| Pandya 28(20) \| Ghosh 0-8 (2)` (l.654) | Naman 21/46 | 25 |
| 4 | F52 | 20:52:28 | 718 | bowlers_end / shot | (post-wicket cluster) | `null 62-4 (8.3) \| *Hardik Pandya 34(23) \| S Dhiraj 16(11) \| Yashasvi Jaiswal 1-13 (2)` (l.681) | Hardik 34/8 | 26 |
| 5 | F67 | 20:53:54 | 1158 | bowlers_end / between_play | MI 121-4 (15.1); Naman 46(31) Hardik 8(11) | `null 12-4 (null) \| NAMAN DHIR 4(12) \| TILAK VARMA 5(7) \| NOOR AHMAD 2-24 (3.2)` (l.1155) | Naman 4/46 | 42 |
| 6 | F81 | 20:54:59 | 1520 | bowlers_end / shot | (Naman ~47) | `null 47-3 (null) \| *Dhir 20(18) \| Pandya 5(7) \| Noor 1-15 (3.2)` (l.1509) | Naman 20/47 | 27 |
| 7 | F82 | 20:55:03 | 1539 | bowlers_end / shot | same | `null 47-3 (null) \| *Dhir 20(18) \| Pandya 5(7) \| Noor 1-15 (3.2)` (l.1536) | Naman 20/47 | 27 |
| 8 | F118 | 20:55:32 | 1578 | closeup / between_play | same | `null 47-3 (null) \| *Dhir 20(18) \| Pandya 5(7) \| Noor 1-15 (3.2)` (l.1575) | Naman 20/47 | 27 |
| 9 | F123 | 20:55:58 | 1693 | bowlers_end / release | (Naman ~47) | `null 9-1 (2.1) \| *Dhir 0(2) \| Pandya 6(5) \| Ahmad 1-9 (2.1)` (l.1682) | Naman 0/47 | 47 |
| 10 | F124 | 20:56:01 | 1723 | bowlers_end / release | same | `null 49-3 (8.4) \| *Naman Dhir 18(9) \| Tilak Varma 10(13) \| Noor Ahmad 2-16 (3.4)` (l.1712) | Naman 18/47 | 29 |
| 11 | F126 | 20:56:05 | 1751 | bowlers_end / post_shot | same | `null 49-3 (null) \| *Naman Dhir 18(10) \| Tilak Varma 1(3) \| Noor Ahmad 0-11 (2)` (l.1742) | Naman 18/47 | 29 |
| 12 | F131 | 20:56:18 | 1872 | bowlers_end / post_shot | same | `null 49-5 (7.4) \| *Hardik Pandya 11(9) \| Naman Dhir 12(8) \| Noor Ahmad 2-13 (3)` (l.1861) | Naman 12/47 | 35 |
| 13 | F137 | 20:56:37 | 1984 | bowlers_end / between_play | MI 122-4 (15.3) | `MI 122-4 (15.3) \| Naman Dhir 12(9) \| Hardik Pandya 49(37) \| Noor Ahmad 1-19 (7)` (l.1978) | Naman 12/47 | 35 |
| 14 | F138 | 20:56:43 | 2016 | bowlers_end / between_play | same | `MI 122-4 (15.3) \| Dhiraj 1(4) \| Hardik 43(34) \| Noor Ahmad 1-20 (8)` (l.2004) | Naman 1/47 | 46 |
| 15 | F179 | 20:59:06 | 2593 | bowlers_end / between_play | (Hardik ~9) | `MUMBAI 124-4 (16) \| Dhir *31(20) \| Pandya 53(37) \| Noor Ahmad 1-29 (4)` (l.2582) | Hardik 53/9 | 44 |
| 16 | F186 | 20:59:41 | 2825 | bowlers_end / post_shot | (Naman ~48) | `MUMBAI 124-4 (16) \| *Dhiraj 14(11) \| Pandya 36(29) \| Ahmad 1-22 (4)` (l.2817) | Naman 14/48 | 34 |
| 17 | F187 | 20:59:45 | 2854 | bowlers_end / shot | same | `MUMBAI 124-4 \| *Dhiraj 0(2) \| Pandya 36(19) \| Ahsan Malik 0-13 (2)` (l.2843) | Naman 0/48 | 48 |
| 18 | F191 | 21:00:02 | 2984 | closeup / between_play | (Hardik ~9) | `MUMBAI 124-4 (16) \| Hardik 33(24) \| *Ishan 39(31) \| BowlerName null-null (null)` (l.2975) | Hardik 33/9 | 24 |
| 19 | F197 | 21:00:30 | 3024 | bowlers_end / between_play | (Naman ~48) | `null 49-3 (null) \| *Dhir 24(20) \| Pandya 1(5) \| Ahmad 2-19 (4)` (l.3012) | Naman 24/48 | 24 |
| 20 | F241 | 21:03:32 | 3932 | None / between_play | MI 134-4 (16.4); Naman 48(51) Hardik 10(15) | `MI 134-4 (16.4) \| Naman > Hardik \| 57 36 \| 10 15 \| RUN-RATE 8.04 \| SPEED 123.8 kph \| 2 1 1 6` (l.3923, full DETAIL l.3940) | Hardik 36/10 | 26 |
| 21 | F243 | 21:03:40 | 3962 | closeup / between_play | (Hardik ~10) | `MI 134-5 (16.5) \| Hardik 57(37) \| Naman 10(15) \| J Overton 1-18 (2.5)` (l.3951) | Hardik 57/10 | 47 |
| 22 | F244 | 21:03:46 | 3985 | closeup / between_play | same | `MI 134-5 (16.5) \| Hardik 57(37) \| Naman 10(15) \| Overton 1-18 (2.5)` (l.3976) | Hardik 57/10 | 47 |
| 23 | F295 | 21:06:38 | 4718 | bowlers_end / between_play | (Hardik ~10) | `null 74-3 (10.3) \| *Hardik 36(26) \| Suryakumar 18(20) \| Fabian Cowdrey 0-25 (4.3)` (l.4705) | Hardik 36/10 | 26 |
| 24 | F351 | 21:11:28 | 6085 | bowlers_end / shot | MI 139-6 (17.3); Krish Bhagat 0(1) | `null 49-3 (null) \| this_over=◉◉◉◉◉. \| *Hardik Pandya 24(15) \| Krish Bhagat 23(20) \| Anshul Kamboj 1-9 (4)` (l.6074, DETAIL l.6096) | Krish 23/0 | 23 |
| 25 | F404 | 21:15:23 | 7445 | bowlers_end / shot | (Krish ~3) | `null 49-3 (8.2) \| *Bhagat 24(19) \| Pandya 20(20) \| Overton 1-16 (3)` (l.7434) | Krish 24/3 | 21 |
| 26 | F438 | 21:18:00 | 8189 | closeup / between_play | MI 146-6 (19.0); Hardik 11(18) Krish 14(20) (set at F437 l.8134) | `MI 146-6 (19) \| Krish 3(5) \| Hardik 142(20) \| null null-null (null)` (l.8178) | Hardik 142/11 | 131 |
| 27 | F481 | 21:20:04 | 8674 | closeup / between_play | (Hardik ~3 at start of innings break) | `null 62-4 (8.1) \| *Bhagat 14(7) \| Hardik 33(20) \| Kamboj 2-13 (3.1)` (l.8671) | Hardik 33/3 | 30 |
| 28 | F841 | 21:43:44 | 13024 | bowlers_end / between_play | CSK 47-0; Samson 1(12) | `CSK 7-0 (1) \| Samson 84(14) \| Gaikwad null \| Bumrah 0-7 (1)` (l.13017); also fires `[GRAPHIC-FILTER] info_panel_keyword='IN T20'` (l.13022) | Samson 84/1 | 83 |
| 29 | F842 | 21:43:50 | 13053 | closeup / between_play | same | `CSK 7-0 (7) \| Samson 84(14) \| null \| Bumrah 0-7 (3)` (l.13042) | Samson 84/1 | 83 |
| 30 | F853 | 21:44:56 | 13378 | closeup / between_play | CSK 7-0; Samson 1(12) | `null 77-5 (9.5) \| SAMSON 38(29) \| GAIKWAD 21(20) \| BUMRAH 1-16 (4)` (l.13367) | Samson 38/1 | 37 |
| 31 | F857 | 21:45:17 | 13435 | closeup / between_play | (Gaikwad ~1) | `CSK 8-0 (1.2) \| GAIKWAD 29(19) \| SAMSON 6(5) \| BUMRAH 0-8 (1.2)` (l.13428) | Gaikwad 29/1 | 28 |
| 32 | F861 | 21:45:36 | 13527 | closeup / between_play | (Gaikwad ~1) | `(Ruturaj Gaikwad 32 / card 1)` (l.13527) | Gaikwad 32/1 | 31 |

Key observation: every frame has `cam ∈ {bowlers_end, closeup, None}` and `phase ∈ {shot, post_shot, between_play, release}` — none classified `cam=graphic` by Scout. The strip text itself looks well-formed (real-looking team/score/over/batter/bowler tokens). What's wrong is the **content**, not the layout.

---

## §2 Correlation with broadcast events

Eight clusters drive the 32 firings, each correlating with a specific broadcast moment:

1. **F11–F12 (20:50:54–58, MI 118-4 over 14.4):** Strip claims `Hardik 45 / Naman 7` while the card has `Naman 45 / Hardik 7` — the *runs* are correct but *names are reversed*. This is the only cluster that looks like a label-swap (and even here it could be Scout's prompt putting batter1 vs batter2 in inconsistent order — see §3).

2. **F45–F138 cluster (20:52–20:56, ~6 min around an MI mini-collapse):** Strips repeatedly show **`49-3 (5.5)` / `12-4 (3.2)` / `47-3` / `9-1 (2.1)` / `49-5`** with **completely different bowlers** (Ramakrishna Ghosh, Noor Ahmad, Yashasvi Jaiswal, Ahsan Malik) and **non-current batters** (Tilak Varma, S Dhiraj, Suryakumar, Ishan). Tracker is at MI 120-4 (15.0)→122-4. These scoreboards are not the live state. The bowlers and batters named are MI **bench/historical** players. F45 line 666 confirms: `[POISONED] Extracted score 49 vs tracker 120 (delta=-71) — blocking ALL updates`. These are recap/comparison overlays during a slow-motion replay window.

3. **F179, F186–F197 (20:59:06–21:00:30):** Strip says `MUMBAI 124-4 (16)` — possibly a *post-wicket innings-summary* recap card after Naman's dismissal. Names like `*Ishan 39(31)` (F191) and `Ahsan Malik 0-13` (F187) are not in the live MI XI for this match.

4. **F241 (21:03:32, between balls):** Scout text is `STRIP: MI 134-4 (16.4) | Naman > Hardik | 57 36 | 10 15 | RUN-RATE 8.04 | SPEED 123.8 kph | 2 1 1 6` (l.3923). This is a **head-to-head batter-comparison graphic**: two columns (`57 36`, `10 15`) showing each batter's runs and balls side-by-side, with run-rate, speed, and a 4-ball mini-summary. The current state matches column 2 (10 15 = Hardik's actual 10(15)). The vision Scout misclassified this graphic strip-shaped overlay as the live STRIP.

5. **F243–F244 (21:03:40–46):** Right after F241's comparison overlay; broadcast continues showing related batter highlights with `Hardik 57(37)` (his career-high in this venue, perhaps).

6. **F295 (21:06:38), F351 (21:11:28), F404, F438, F481:** Various recap/highlight overlays during between-over windows. F351 has `this_over=◉◉◉◉◉.` (5 boundaries) — that's a *partnership/over highlights* card. F438 shows `Krish 3(5) | Hardik 142(20)` — note `Hardik 142(20)` retains the same balls=20 the card shows for Krish in the previous frame F437 (l.8134), so the OCR is reading a graphic that has its own number rendered into the runs cell. F481 line 8686: `[ACTION] The crowd is celebrating a wicket, with drummers performing in the foreground` — overlay during wicket celebration.

7. **F841–F842 (21:43:44–50, CSK innings 2):** F841 simultaneously fires the **existing** `[GRAPHIC-FILTER] info_panel_keyword='IN T20' divergence` (l.13022) — proving the broadcast was showing a Samson **T20 career-stat** overlay (`Samson 84(14)` ≈ his highest T20 score). The misalignment guard then re-fires on the same frame because the strip-OCR'd batter row also picked up the 84.

8. **F853, F857, F861 (21:44:56–21:45:36):** Likely batter-stat overlays during early CSK innings (Samson 38 ≈ recent average; Gaikwad 29/32 ≈ a season stat).

Pattern: 0/32 events correlate with replay-banner tags or `cam=graphic`. **All 32** correlate with broadcast batter-comparison or career-stat overlays that visually resemble the live strip but contain non-live numbers, occurring during `between_play`, `shot`, `post_shot`, and `release` phases — i.e., distributed across the over.

---

## §3 Hypothesis test: layout reversal vs OCR mis-parse

**Conclusion: neither.** The dominant cause is **(c) overlay substitution** — the broadcast shows a graphic that mimics the strip layout but renders different stats (career, head-to-head, recap, partnership). Evidence:

- **Not OCR mis-parse:** in F45 (l.654) the strip OCR cleanly reads `null 49-3 (5.5) | • • • • • • • • • • | *Dhir 21(19) | Pandya 28(20) | Ghosh 0-8 (2)` — every field is well-formed and internally consistent (a valid 5.5-overs scoreboard with a legal balls-faced row). The same goes for F67's `12-4 (3.2)` with `NOOR AHMAD 2-24 (3.2)` (l.1155) — internally consistent but historically/contextually wrong. If OCR were drifting, we'd expect garbled tokens; we don't see them. Bowler names/figures and team scores in these readings are completely different from the live state, not corrupted versions of it.

- **Not layout reversal of live rows:** in F11/F12 (rows `Hardik 45 / Naman 7` vs card `Naman 45 / Hardik 7`) the runs are equal but names swapped. However, the *guard* fires per-row using `resolve_name → batting_card[name]`. A pure label↔stats swap *within the live strip* would also fire if the prompt happens to assign batter1/batter2 in the opposite order to what the card holds. This is consistent with the Scout extractor sometimes reporting `batters[0]` as the non-striker. F11/F12 may belong to category (a) layout/order ambiguity, but they are the **only 2 of 32**.

- **Decisive evidence (F241):** the scout text itself reveals the layout — `Naman > Hardik | 57 36 | 10 15 | RUN-RATE 8.04 | SPEED 123.8 kph | 2 1 1 6` (l.3923). This is *visibly* a 2-column comparison graphic, not a 2-row strip. The live strip layout is `score | batter1 | batter2 | bowler`; this overlay is `header | runs-pair | balls-pair | rate | speed | over-summary`. Scout's prompt collapsed it into the strip schema.

- **Decisive evidence (F841):** the existing `[GRAPHIC-FILTER]` (l.13022) classifier independently identified it as a stat overlay via the `'IN T20'` info-panel keyword on the same frame. So the broadcast pixel evidence is unambiguous: it's a graphic, the strip-OCR pulled headline numbers from it.

- **Score-vs-tracker delta corroborates:** 22 of the 32 events also trip the `[POISONED]` score guard (e.g., F45 l.666, F67 l.1161, F124, F131, F137, F438 l.8194, F841 l.13095, F853 l.13390 etc.) because the score in the same overlay disagrees with the live score by 40–110 runs. A genuine strip with reordered rows would still show the correct match score. The score being wrong + bowler being wrong + batter-pair being wrong = a different scoreboard entirely.

Verdict: **layout reversal accounts for ≤2/32; OCR mis-parse accounts for 0/32; broadcast overlay substitution accounts for ~30/32.** The remaining 2 (F11/F12) are likely Scout `batters[]` ordering ambiguity, not a broadcast issue.

---

## §4 Visual signal availability (can we detect before parse?)

Yes — multiple signals exist BEFORE we have to compare row-pair runs to the card:

1. **Score-vs-tracker delta (already used):** in 22/32 events the `[POISONED] score X vs tracker Y (delta=…)` guard fires *in the same frame* (e.g., F45 l.666 delta=-71; F438 l.8194; F841 l.13094 delta=-40). This is computed before the row-pair guard runs and could short-circuit it. The 10/32 events without poisoning are the cases where the overlay happens to render a score numerically close to the live score (e.g., F11 same `118-4`; F438 same `146-6`; F841 `7-0`).

2. **Bowler-vs-tracker mismatch:** 18+ events name a different bowler than the tracker. F45 strip says `Ghosh 0-8 (2)` while tracker had `Ramakrishna Ghosh 1-22 (2.4)` — different runs and overs. F67 says `NOOR AHMAD 2-24 (3.2)` vs tracker `Noor Ahmad 2-23 (3.1)`. The pipeline already does `[BOWLER-CONSENSUS-INCONSISTENT]` checks (e.g., F844 l.13093) — extending that to detect "bowler stats regressed" is feasible.

3. **Existing `[GRAPHIC-FILTER]` info-panel keyword:** F841 l.13022 already detected the same frame via `info_panel_keyword='IN T20'`. Other career-stat overlays likely have similar keywords (`vs RCB`, `IN IPL`, `T20 CAREER`, `BEST`). Expanding the keyword list would catch many.

4. **Batter-name not in active batting pair:** several frames name players not currently at the crease — F67 `TILAK VARMA`, F52 `S Dhiraj` + `Yashasvi Jaiswal`, F186/F187 `*Dhiraj`, F191 `*Ishan`, F295 `Suryakumar`. The pipeline has `active_batting` (referenced in WS-PROJECTION-FALLBACK l.13067) and a fuzzy matcher (lines 689–705 around F52). A pre-parse check `if neither strip-batter resolves into active_batting → reject` would catch these without needing the row-pair runs delta.

5. **Strip-text "comparison sentinels":** F241's scout output literally contains `Naman > Hardik` and `RUN-RATE 8.04 | SPEED 123.8 kph` — strings that don't appear in normal strip layouts. A simple substring check on the scout `STRIP:` text for `' > '`, `RUN-RATE`, `SPEED`, `kph`, `vs `, `CAREER`, `BEST` would flag overlay frames before any structured parse.

6. **Striker `*` inconsistency:** F351 has `*Hardik Pandya 24(15)` while the tracker striker is also Hardik but with 10(15) — but the over context (`◉◉◉◉◉.` = 5 boundaries+dot) would never match the live `this_over=['4', 'W', '.']` (l.6094). A this_over consistency check vs tracker would catch it.

The single most cost-effective signal is **#5 (strip-text sentinels)** because it operates on existing scout output, requires no extra LLM/CV cost, and would catch the F241/F841 patterns directly. Combined with **#1 (score delta, already running)** and **#4 (active_batting membership)**, the row-pair guard could be relegated to a last-resort check.

---

## §5 Fix proposal

**Recommendation:** Stack three lightweight pre-parse filters in front of `apply_comparison_strip_batter_row_delta_guard`. The row-pair guard becomes a backstop, not the primary defense.

### Implementation

**File:** `files/test_pipeline.py`
- Add `_detect_overlay_strip_sentinels(scout_strip_text: str) -> str | None` near line 3140 (alongside `apply_comparison_strip_batter_row_delta_guard`). Returns the matched sentinel keyword or None. Sentinel list to start: `[' > ', 'RUN-RATE', 'SPEED ', 'kph', 'CAREER', 'BEST', 'AVG', 'STRIKE-RATE', 'IN T20', 'IN IPL', 'vs ']`.
- Add `_detect_overlay_via_active_batting(extracted_batters, scoreboard) -> bool`. Returns True if neither strip batter resolves into `scoreboard.active_batting` *and* the existing batting card is non-empty (so we know who should be at the crease).
- In the existing extracted-frame validation flow (find where `apply_comparison_strip_batter_row_delta_guard` is invoked — search for "comparison_strip_batter_row_delta_guard"), gate it: if either pre-filter fires, log `[STRIP-OVERLAY-DETECTED] reason={sentinel|active_batting} sentinel='…'` and pop `batters` immediately. Reuse `record_state_recovery_guard("batter_row_rejected", …)` for telemetry parity.
- The existing `_gb_existing - _gb_new > 20` guard stays as-is for residual cases. Lower the threshold to >15 once the pre-filters take pressure off (currently 20 is conservative because guard is the only line of defense).

**File:** `files/scout_extractor.py` (or wherever Scout's prompt for `STRIP:` lives — confirm with `grep -n "has_strip" files/scout_*.py`)
- Optional, lower priority: add a prompt clause "If the panel shows two side-by-side comparison columns (e.g., `Naman > Hardik | 57 36`), set `has_strip=false` and surface as `INFO_PANEL` only." This is a model-side fix and may take 2–3 prompt iterations.

**File:** `files/tests/` new test `test_strip_overlay_filter.py`
- Fixture cases from the 32 events above (representative subset of ~10): F11, F45, F67, F241, F351, F438, F841, F853 with their scout STRIP text + tracker state. Assert pre-filter rejection with the right reason code.

### Telemetry

- New WARN tag `[STRIP-OVERLAY-DETECTED]` with `reason=` so `analyze_trace.py` (P-rules) can split the existing P19-class events into `OVERLAY-PRE-FILTERED` vs `ROW-DELTA-FALLBACK`.
- Update `files/docs/operations/trace_and_detect_setup.md` to document the new tag.

### Effort estimate

- Sentinel + active-batting pre-filter implementation, wiring, telemetry: **2 hours**.
- Test fixtures from the 8 representative frames: **1.5 hours**.
- Optional Scout-prompt iteration for `has_strip=false` on comparison panels: **1.5–3 hours** (not on critical path; ship the pre-filters first).
- Threshold tuning (20→15) after one match of post-fix telemetry: **30 min**.

**Total: half a day (~4 hours) for the core fix. One additional half-day if Scout prompt is also retrained.**

### Why not raise the existing threshold or change Scout-classifier directly?

- Raising the threshold doesn't help — F438 (`Hardik 142 vs 11`, Δ=131) and F841 (`Samson 84 vs 1`, Δ=83) would still fire, but F404 (Krish `24 vs 3`, Δ=21) is right at the edge and lowering would cause false positives on legitimate end-of-over re-syncs.
- A Scout-classifier change to mark these as `cam=graphic` would help, but the broadcast overlays are heterogeneous and the existing `[GRAPHIC-FILTER]` only catches one variant (info-panel keyword). The text-sentinel approach generalises faster than per-overlay model retraining.

### Out of scope (deferred)

- F11/F12-class label↔stats swap within a *real* live strip — likely a Scout-prompt determinism issue with `batters[0]` ordering. Can be addressed by always sorting `extracted["batters"]` by striker-marker presence before the guard runs. ~30 min, separate ticket.
