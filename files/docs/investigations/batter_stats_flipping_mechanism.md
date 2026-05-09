# Issue 2 — Batter stat “flipping” mechanism (bounded memo)

**Phase:** Investigation only. **No code changes.**

**Purpose:** Isolate what **still remains** after Direction **M** / **M2** exclusions (Lever 1 PR1–PR4 not root; **`[WS-SLOT-INVARIANT]`** name-only; **`[STRIP-ROWS-MISALIGNED]`** pops extractor batters only). Evaluate **H3 / H4 / H5 / H7** against **`logs/pipeline-2026-04-30-gt-rcb-live.log`** and the **`ScoreManager` ↔ `FrameInput`** contract.

**Anchors:** [`batter_stat_swapping_analysis.md`](batter_stat_swapping_analysis.md); [`strip_row_pairing_analysis.md`](strip_row_pairing_analysis.md).

---

## §1 Executive summary

### §1.1 Confirmed mechanism (primary)

**Dominant explanation — refinement of H5 (“score_manager downstream pairing”), rooted in pipeline wiring:**

- **`FrameInput.ext_bat1_*` / `ext_bat2_*` are assigned strictly from extractor row order**: `_ext_batters[0]` → bat1, `_ext_batters[1]` → bat2 ([`files/test_pipeline.py`](../../test_pipeline.py) **9850–9861**).
- That order is **visual strip column order**, not **striker-first** order.
- **`ScoreManager.bat1_name` / `bat2_name`** are driven from those fields via **`_hydrate_card_from_frame` → `_init_from_card` / `_update_batters`** ([`files/score_manager.py`](../../score_manager.py) **877–896**, **1997–2093**, **1306–1338**).
- **`ScoreManager.striker` / `non`** are maintained separately (**`_set_slot_pair`**, broadcast-indicator admission, balls-faced / `_identify` pipeline — [`files/score_manager.py`](../../score_manager.py) **993–1017**, [`files/test_pipeline.py`](../../test_pipeline.py) **8238–8286**).
- **`bat1_runs` / `bat2_runs` properties** resolve numerics via **`batting_card[self.batN_name]`** ([`files/score_manager.py`](../../score_manager.py) **283–357**) — **correct per canonical player key**.

Therefore **internal numeric truth stays keyed by player name on `batting_card`**. The user-visible **“flipped stats”** symptom matches **any presentation layer that**:

1. Shows **striker / non-striker** order using **`striker` / `non`** (or `scoreboard._inn["striker"]` for markers — [`files/eyes/scoreboard.py`](../../eyes/scoreboard.py) **4236–4241**), **but**
2. Attaches **`bat1_runs` / `bat2_runs` (or bat1/bat2 columns)** by **positional slot** without mapping **batN_name ↔ striker**.

So the pipeline **splits two axes**: **strip slot index (bat1/bat2)** vs **match role (striker/non)**. When those disagree (common whenever the broadcast lists non-striker first or OCR reorder), **positional binding looks like crossed stats**.

**Log-ready illustration:** [`logs/pipeline-2026-04-30-gt-rcb-live.log`](../../../logs/pipeline-2026-04-30-gt-rcb-live.log) **27048–27052** (`F2689`): **`AFTER_striker=Sai Sudharsan`** | **`AFTER_non=Shubman Gill`** (striker/non aligned with commentary wide ball) **while** **`AFTER_bat1=Shubman Gill 0(0)`** | **`AFTER_bat2=Sai Sudharsan 1(1)`** (strip row order unchanged). Runs match names correctly **inside** those fields — but **any UI that renders striker-first yet reads bat1 as “first tile” crosses streams.**

### §1.2 Secondary mechanism (still matches user narrative)

**Strip OCR mis-association / transpose** (M2 **H1**) remains capable of writing **wrong `(runs,balls)` under the wrong surname key** via **`scoreboard.update_batter`** ([`files/test_pipeline.py`](../../test_pipeline.py) **8219–8224**). That is **orthogonal** to H3/H4/H7 and **not disproved** here — excluded from “H5 wins alone” only where **`batting_card` rows remain internally consistent** (many **`DETAIL`** lines show coherent BEFORE/AFTER name↔runs pairs).

### §1.3 Fix scope class

**MEDIUM** — single orchestration site (**`FrameInput` construction**) likely needs **deterministic reorder** or **explicit striker-aligned batters** passed into SM (fix shape §4), plus regression tests for chase starts.

### §1.4 Specific file:line for fix

[`files/test_pipeline.py`](../../test_pipeline.py) **9850–9861** (`FrameInput` batter fields sourced from `_ext_batters[0]`/`[1]`).

### §1.5 Risk (summary)

Reordering batters risks confusing innings where **`striker` is briefly unknown** or extractor returns **single row** — needs guards + replay snippets (**§5**).

### §1.6 Ready to ship today?

**NO.** Mechanism is clear enough to implement next session, but **ordering policy** + **cold-start / bootstrap** interactions ([`files/score_manager.py`](../../score_manager.py) **2030–2043**) require targeted tests — not a safe **≤5 line** emergency patch without validation.

---

## §2 Reproduction in logs (Phase A)

### §2.1 Window scanned

Early chase **`F2308–F2707`** **`DETAIL|…|SCOREBOARD`** lines with Gill / Sudharsan ([`logs/pipeline-2026-04-30-gt-rcb-live.log`](../../../logs/pipeline-2026-04-30-gt-rcb-live.log) tee lines **24915–27329** region).

### §2.2 Per-frame observations (abbreviated table)

| Frame | Tee line | Strip / card snapshot | Notes |
|-------|---------|------------------------|-------|
| **F2314** | **25098** | `Gill* 0(1)`, `Sudharsan* 0(0)` strip asterisk noise; **`AFTER_bat1`/`bat2`** coherent `0(1)` / `0(0)` | **Phase 1 “random digits”** — OCR volatility (`25128` **F2315** regresses Gill balls `1→0`). |
| **F2347** | **25353** | Strip asks `Sudharsan 0(1)` both batters; **`AFTER_bat2`** stays `0` balls despite scorer_changes listing both `0(1)` | Parser/scorer jitter consistent with user “switching”. |
| **F2682–F2694** | **26878–27234** | Strip lists **`Sudharsan` first**, **`Gill` second**; **`AFTER_bat1=Gill`**, **`AFTER_bat2=Sudharsan`**; **`AFTER_striker`/`AFTER_non`** flip to **`Sudharsan`/`Gill`** (`27048`) | **Axis divergence** demonstrable while totals remain name-consistent. |
| **F2825–F2933** | **28630–30177** | `STATE` lines show evolving **`Gill*`/`Sudharsan*` markers with attached `(runs)`** — not a stable inverted-name tuple sustained as **Gill showing Sudharsan-only aggregates** in this grep slice | **Phase 2 “settled wrong”** not reproduced as **pure `(runs,balls)` swap under swapped keys** in these **`STATE`** snapshots — narrative may blend **positional UI mis-binding** + **brief OCR spikes**. |

### §2.3 Broadcast-truth comparison

Postmortem claims (Gill powerplay progression, Hazlewood over, etc.) are **not re-verified against ESPN** in this bounded pass. Log-internal coherence checks above rely on **`STATE`** / **`DETAIL`** only.

### §2.4 Stop-condition **S1** partial assessment

Logs **do** preserve enough structure to prove **bat1/bat2 vs striker/non divergence**. They **do not** prove every pixel-level **user HUD** binding — if production UI reads exclusively from **`batting_card[].is_striker`** on WS payload ([`files/test_pipeline.py`](../../test_pipeline.py) **`batting_card` assembly ~4247–4261**), **flip might be invisible there** — reinforcing that **the bug class is consumer / legacy bat1 coupling**, not universal.

---

## §3 Hypothesis evaluation (Phase B)

### §3.1 H3 — stale slot occupant after **`extracted.pop("batters")`**

| | |
|--|--|
| **FOR** | User-visible staleness during **`FRAME_POISONED`** streaks ([`logs/pipeline-2026-04-30-gt-rcb-live.log`](../../../logs/pipeline-2026-04-30-gt-rcb-live.log) early chase shows prolonged **0–0** holds — e.g. **25573–25853** `F2381–F2458`). |
| **AGAINST** | Pop removes **`extracted["batters"]`**, **not** `scoreboard.batting_card` entries ([`files/test_pipeline.py`](../../test_pipeline.py) **3026–3027**, **2984–2989**). **`DETAIL`** AFTER bat lines frequently **preserve** prior coherent tuples (`25599` **`F2382`** poisoned headline yet **`AFTER_bat*` unchanged). |
| **Rank** | **LOW** |

### §3.2 H4 — broadcast indicator swap without stats migration

| | |
|--|--|
| **FOR** | Deferred **`broadcast-indicator`** writes **`_set_legacy_active_slot`** swapping striker/non ([`files/test_pipeline.py`](../../test_pipeline.py) **8272–8282**). |
| **AGAINST** | Runs remain stored on **`batting_card[name]`** keys updated independently via **`update_batter`** — swaps intentionally move **roles**, not numeric blobs. **`get_current_batters`** annotates `*` via **`name == striker`** ([`files/eyes/scoreboard.py`](../../eyes/scoreboard.py) **4236–4241**). |
| **Rank** | **LOW–MEDIUM** (symptom amplifier **only if** UI binds stats by tile index tied to stale bat1/bat2 ordering). |

### §3.3 H5 — SM / downstream pairing failure

| | |
|--|--|
| **FOR** | **`FrameInput` bat1/bat2 positional coupling** to extractor ordering (**9850–9861**). **`_snapshot`** exposes **`bat1_*` alongside implicit striker logic** ([`files/score_manager.py`](../../score_manager.py) **1897–1907**, comments **94–96**). Concrete **`DETAIL`** divergence **`AFTER_striker` vs `AFTER_bat1`** (**§2.2**, tee **27048**). |
| **AGAINST** | **`batN_runs` getters** intentionally **read through `batting_card`** — internally consistent when consumers use getters **with matching `batN_name`**. |
| **Rank** | **HIGH** (for **positional / legacy bat1 coupling** path); **LOW** if all surfaces consume **`batting_card` + `is_striker`**. |

### §3.4 H7 — WS-SCRUB-driven flipping

| | |
|--|--|
| **FOR** | Dense **`[WS-SCRUB]`** during chase bootstrap (**26501–26539**, **`F2619–F2636`**) replaces **`state["striker"]`/`state["non"]`** fallbacks ([`files/test_pipeline.py`](../../test_pipeline.py) **4024–4033**). |
| **AGAINST** | Telemetry shows scrub adjusting **projection slots**, **not deleting `batting_card` numeric rows**. Active roster remains **`['Shubman Gill','Sai Sudharsan']`**. |
| **Rank** | **LOW** as **direct stats transplant** mechanism; **MEDIUM** as **forcing striker/non churn** while **`bat1_name` stays strip-ordered**, widening **§1.1** mismatch window. |

### §3.5 Ranking summary

| Hypothesis | Plausibility | Confidence |
|------------|--------------|------------|
| **H5** (strip-order **`bat1/bat2`** vs **`striker/non`**) | **HIGH** | **Strong** |
| **H7** (scrub exacerbates axis divergence) | **MEDIUM** | **Moderate** |
| **H4** | **LOW–MEDIUM** | **Moderate** |
| **H3** | **LOW** | **Moderate** |

**Stop-condition S2:** **H5 + H7** interaction plausible — recommend phased validation (**§5**), not simultaneous multi-file gamble.

---

## §4 Confirmed mechanism (Phase C)

### §4.1 Bug location (contract defect)

[`files/test_pipeline.py`](../../test_pipeline.py) **9850–9861**:

```9850:9861:files/test_pipeline.py
                ext_bat1_name=(_ext_batters[0].get("name")
                               if len(_ext_batters) >= 1 else None),
                ext_bat1_runs=(_safe_int(_ext_batters[0].get("runs"))
                               if len(_ext_batters) >= 1 else None),
                ext_bat1_balls=(_safe_int(_ext_batters[0].get("balls"))
                                if len(_ext_batters) >= 1 else None),
                ext_bat2_name=(_ext_batters[1].get("name")
                               if len(_ext_batters) >= 2 else None),
                ext_bat2_runs=(_safe_int(_ext_batters[1].get("runs"))
                               if len(_ext_batters) >= 2 else None),
                ext_bat2_balls=(_safe_int(_ext_batters[1].get("balls"))
                                if len(_ext_batters) >= 2 else None),
```

**Current behavior:** **`bat1` ≡ left strip batter**, **`bat2` ≡ right strip batter**.

**Expected behavior (fix shape):** When **`score_mgr.striker`** / **`non`** are known warm-path, **reorder or annotate** extractor rows so **`bat1` aligns with striker** (or abandon positional bat1/bat2 for SM ingest entirely in favor of keyed updates only — larger refactor).

Secondary coordination surface if reordering **`FrameInput`**: [**`files/score_manager.py`](../../score_manager.py) **`_update_batters`** **2030–2093** (bootstrap assumes bat1/bat2 naming stability)** — reorder must preserve fuzzy wicket substitution logic.

### §4.2 Why this matches “settled flipped”

Once OCR stabilizes on a **consistent strip column ordering** while **`striker` settles separately**, **positional dashboards** freeze the wrong pairing — reads as **stable inversion** between two batters.

---

## §5 Fix readiness (Phase D)

### §5.1 Ship today?

**NO** — scope **MEDIUM**, coupling to **`ScoreManager` bootstrap** + **`WS-SCRUB`** churn (**§3.4**) demands replay harness frames (**`F2682–F2695`**, **`F2637`** scrub cluster).

### §5.2 Recommendation text

Implement **striker-aligned batter ordering** (or equivalent keyed ingest) at **[`files/test_pipeline.py`](../../test_pipeline.py):9850–9861**. Validate by replaying **`F2689`** ensuring **`bat1_name == striker`** when strip order inverted; regression-check **`_update_batters` wicket substitution** ([`files/score_manager.py`](../../score_manager.py) **2058–2073**). Rollback = revert ordering patch only.

### §5.3 Tests / telemetry

| Approach | Purpose |
|---------|---------|
| Unit | Synthetic `_ext_batters` permutations × frozen **`score_mgr.striker`**. |
| Log replay | **`DETAIL`** parity on **`AFTER_bat1`** vs **`AFTER_striker`** divergence clusters (**tee ~27048**). |
| Ops watch | **`[SM-FEEDER-SYNC]`** + **`STATE`** divergence rates ([`dual_broadcaster_path_b_migration_contract.md`](dual_broadcaster_path_b_migration_contract.md)). |

### §5.4 Cross-match regression anxiety

MI / PBKS lacked **`STRIP-ROWS`** spikes but share **`FrameInput`** construction — **behavior change affects all tees** unless gated behind innings-phase detection.

---

## §6 Cross-references

| Doc | Role |
|-----|------|
| [`batter_stat_swapping_analysis.md`](batter_stat_swapping_analysis.md) | Pattern **R** Orthogonality vs Lever 1 |
| [`strip_row_pairing_analysis.md`](strip_row_pairing_analysis.md) | M2 pairing / transpose class |

**Code lines cited:** [`files/test_pipeline.py`](../../test_pipeline.py) **9850–9861**, **8238–8286**, **4024–4033**; [`files/score_manager.py`](../../score_manager.py) **283–357**, **993–1017**, **1997–2093**; [`files/eyes/scoreboard.py`](../../eyes/scoreboard.py) **4236–4241**.

**Log lines cited:** [`logs/pipeline-2026-04-30-gt-rcb-live.log`](../../../logs/pipeline-2026-04-30-gt-rcb-live.log) tee **24915**, **25128**, **25353**, **26501**, **27048**, **28630**.
