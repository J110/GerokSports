# Graphic strip pollution fix — implementation note

MULTI_BALL **Cause 4** — companion analysis: **`graphic_strip_pollution_analysis.md`**.

---

## §1 Implementation summary

| Item | Detail |
|------|--------|
| Primary file | `files/test_pipeline.py` — GRAPHIC mismatch score strip (~6996); `filter_info_panel_contamination` score drift (>7) (~2196–2216); FRAME POISON graphic-phase preempt (~8058–8153). |
| Tests | **`files/test_recent_fixes.py`** — `test_graphic_strip_*`, `test_poison_recal_graphic_phase_preempt_wired_in_source`; registered in **`TESTS`**. |
| Pytest slice | **`pytest files/test_recent_fixes.py::test_graphic_strip_info_panel_keyword_large_delta_strips_score …`** — **3 passed** here (narrow selection). |

---

## §2 Mechanism recap

**Mode A.** `frame_type=="GRAPHIC"` mismatch path set `_frame_poisoned` but **retained extractor score**, so FRAME POISON still ran **`abs(delta)>7`** and advanced **`[POISON-STREAK]`** toward **`[POISON-RECAL]`**. **Fix:** pop **`score` / `wickets` / `match_overs`** after logging **`[GRAPHIC-FILTER]`**.

**Mode B.** Scout reports **`cam=graphic`** + **`phase=graphic`** while lexical tag stays **`SCOREBOARD`**. **Fix:** **`_gfx_phase_recal_skip`** — still **`FRAME POISON`** block updates, but **`[POISON-STREAK]`** / **`[POISON-RECAL]`** do **not** advance; emit **`[POISON-RECAL-PRE-EMPTED]`** + **`[GRAPHIC-FILTER]`**.

**Info panels.** Keywords already triggered bowler strip; **`|extracted − tracker| > 7`** now clears the score trio (**`[GRAPHIC-FILTER]`**).

---

## §3 Telemetry

| Tag | When |
|-----|------|
| **`[GRAPHIC-FILTER]`** | GRAPHIC mismatch strip; SCOREBOARD+graphic-phase preempt; info-panel divergence strip. Payload includes **`raw_*`** / **`frame_type`** / **`classification_conf=n/a`**. |
| **`[POISON-RECAL-PRE-EMPTED]`** | Graphic-phase OCR would have incremented poison streak (**`would_be_delta`**, **`raw_score`**). |

---

## §4 Rollback

Revert the single patch touching **`test_pipeline.py`** + test registrations (and remove this doc/analysis pair if rollback is total).

---

## §7 Next-match validation

1. Compare **`grep -c 'POISON-RECAL'`** vs **35**/3 tees baseline in analysis doc.
2. Sample **`[POISON-RECAL-PRE-EMPTED]`** volume — nonzero expected while **`cam=graphic`** interstitials remain.
3. Guard against **false negatives:** real stuck-tracker incidents should still **`[POISON-STREAK]`** when **not** on graphic-phase preempt path.
