# Graphic-vs-strip OCR pollution (MULTI_BALL Cause 4)

**Hypothesis:** Broadcast graphics (info panels, head-to-head, replay chrome) leak OCR digits into extractor `score`/`wickets`/`match_overs`, driving `FRAME POISONED` spikes and **`[POISON-RECAL]`** cold-start trips.

**Evidence source:** Tee logs  
`logs/pipeline-2026-04-30-gt-rcb-live.log`,  
`logs/pipeline-2026-04-29-194416-mi-srh-live.log`,  
`logs/pipeline-2026-04-28-pbks-rr-live.log`.

**Frame-archive note:** Packaged JPGs under `debug_frames_archive/` were not readable in this agent workspace (`cursorignore`). Visual A2 verification was **partially substituted** by correlating **`[SCOUT]`** lines (`frame_type`, `cam=`, `phase=`, `strip=`, `overlay=`), **`[GUARD] GRAPHIC`**, **`[POISONED]`**, and **`DETAIL|F…`** tee lines operator-side.

---

## Phase A — Prevalence

### A1. `[POISON-RECAL]` counts

| Tee | `[POISON-RECAL]` lines |
|-----|-------------------------|
| GT–RCB (2026-04-30) | **24** |
| MI–SRH (2026-04-29) | **4** |
| PBKS–RR (2026-04-28) | **7** |
| **3-match total** | **35** |

Method: `grep -c "POISON-RECAL" logs/<match>.log`.

Representative terminating rows show **`[POISONED] Extracted score … vs tracker … (delta=±N)`** with `abs(N) ≥ 8` (streak semantics same as **`abs(delta) > 7`** in code).

### A2/A3 — Pattern clustering (logged Scout + guards)

Across the sampled POISON-RECAL windows:

1. **Lexical `GRAPHIC` + mismatch guard (#Mode-A leak)** — PBKS F3355:  
   **`[GUARD] GRAPHIC frame — player stats stripped, score mismatch → poisoned`** immediately followed by **`[POISONED] Extracted …`**.  
   **Mechanism:** `frame_type=="GRAPHIC"` stripped batters/bowler but **left `score`** in `extracted`, so **`test_pipeline.py` FRAME POISON** still consumed the graphic OCR for delta + **`[POISON-STREAK]`**.

2. **`SCOREBOARD` lexical tag + Scout `cam=graphic` + `phase=graphic` (#Mode-B)** — dominant in GT–RCB traces (many streak frames).  
   The strip is often visible (`strip=True`) but Scout still reports **graphic** camera/phase; extractor returns plausible **wrong-innings / overlay** totals (e.g. 99 vs 154, partial scoreboard reads).

3. **Tracker at 0 vs repeated extracted chase totals (#innings-/transition adjacent)** — MI–SRH and PBKS show sequences where **`tracker baseline 0`** and extracted holds small positives (8, 12, 37…) — overlays + cold latch, not purely “graphic” but same **numeric hallucination surface**.

4. **Info-panel semantics** — `filter_info_panel_contamination` (pre-fix) stripped **bowler only** while comments assumed **tracker** would bound **score**; **tracker does not gate the poison watchdog** (`test_pipeline.py` ~8025+) — divergence still increments streak.

### A4 — Hypothesis verdict (Cause‑4 leverage)

**Estimated ≥50–60%** of POISON-RECAL incidents are attributable to graphic / overlay OCR paths when counting:

- All **`GRAPHIC` mismatch** streak contributions (Mode A leak),
- **`SCOREBOARD` + graphic-phase Scout tags** near trip frames (Mode B),
- **Info-overlay keyword** correlations where strip+panel merge.

Uncertainty: some trips are **`cam=closeup`** with no graphic phase (strip misread vs wrong innings) — Causes **2 / 3** remain material.

**Conclusion:** Cause 4 meets the **“>50% → fix first”** bar sufficiently to ship targeted gates before widening Causes **2 / 3** work.

---

## Phase B — Differentiation logic (pre-change)

### B1. Where `frame_type` is assigned

| Layer | Behaviour |
|-------|-----------|
| `files/eyes/vision.py` | **`describe()` → `(frame_type, description, …)`** from Scout JSON; enums include **`GRAPHIC`**, **`SCOREBOARD`**, **`CLOSEUP`**, **`ADVERTISEMENT`**, … |
| `_normalise_camera_view` | If **`has_overlay` and not `has_strip`** → **`graphic`**; lexical `GRAPHIC` can still co-exist with **`strip=True`** overlays. |

### B2–B3 — Failure modes

| Mode | Description | Seen in tees |
|------|-------------|----------------|
| **A** | Classification correct (**`GRAPHIC`**) but **downstream FRAME POISON** still used **`extracted.score`** | PBKS **`[GUARD] GRAPHIC` + `[POISONED]`** pairing |
| **B** | **Scout geometry says graphic phase** (`cam=graphic`, `phase=graphic`) while **lexical `frame_type`** stayed **`SCOREBOARD`** → graphic pollution treated as authoritative strip | GT–RCB dense clusters |

**Deployed “player-stats strip”** on **`GRAPHIC`** (`test_pipeline.py` ~6992+) **did not remove team score**, by design comment (“don't poison … if score matches”) — mismatches **were poisoned twice** (guard + FRAME POISON streak).

**Qwen blocklist (“Path 2”):** **Not implemented.** `grep` shows **`info_panel`** only on **`agent.py`** JSON schema hints — no **`qwen`** tagger blocklist wired in `vision.py` / extractor.

---

## Phase C — Recommended fix summary

| Deliverable | Category |
|-------------|----------|
| **Strip `score`/`wickets`/`match_overs` on GRAPHIC mismatch** before `_pre_guard_score` | Removes Mode **A** double-poison + streak feed (**SMALL**) |
| **Skip POISON-RECAL streak advance** when lexical **`SCOREBOARD`** but **`_last_cam == graphic`** and **`_last_phase == graphic`** | Addresses Mode **B** using Scout geometry (not lexical **`GRAPHIC`** alone) (**SMALL**) |
| **Extend `filter_info_panel_contamination`** to strip trio when **`|extracted − tracker| > 7`** | Targets overlay keywords (**SMALL**) |

**Combined scope:** **MEDIUM-low** (~80–120 LOC touched across `filter_info_panel_*`, GRAPHIC guard, FRAME POISON; tests + docs).

---

## Phase D — Telemetry & tests shipped

See **`graphic_strip_fix_implementation.md`** for tag table, rollback, and **`pytest`** command.

---

## §7 Coordinating Tasks 2 & 3

After this fix lands, **re-run POISON-RECAL frequency analysis** on the next full tee log **with live/post-match decomposition**. Use the **clock-rule** from **`poison_recal_frequency_analysis.md` §11** (post-match window: trips occurring after **match-end clock + 5 min** buffer).

**Baseline** (from threshold memo §A3):

- **Total:** 35 (3 tees)
- **Live-window:** 12
- **Post-match window:** 23

**Per-tee comparison required:**

| Bucket | Pre-fix baseline | Post-fix actual |
|--------|------------------|-----------------|
| Total | 35 | ? |
| Live-window | 12 | ? |
| Post-match window | 23 | ? |

**Attribution rules:**

- **Live count drops significantly (>40%):** Cause 4 is doing the work. A4 verdict (~50%+ leverage) confirmed.

- **Post-match count drops significantly while live stays flat:** Mode B fix is incidentally catching carousel content; Direction L still needed but its scope shrinks proportionally.

- **Both drop similarly:** Mode B fix is broad-spectrum (hits both contexts). Direction L priority drops.

- **Neither drops:** Cause 4 effective leverage was below A4 estimate. Reframe; redirect to Direction L or Cause 3.

**Telemetry-based confirmation:**

- **`[GRAPHIC-FILTER]` count > 0:** Mode A path fired (downstream score-pop on GRAPHIC mismatch).

- **`[POISON-RECAL-PRE-EMPTED]` count > 0:** Mode B path fired (geometric override of lexical SCOREBOARD).

- If **both** telemetry tags fire but **POISON-RECAL count doesn't drop:** gates are triggering on frames that wouldn't have tripped anyway. Reassess A2 pattern classifications.

**Regression watchlist:**

- **`FRAME_POISONED` rate without `[GRAPHIC-FILTER]` or `[POISON-RECAL-PRE-EMPTED]` co-occurrence:** classification drift (Scout giving different cam/phase tags than analyzed).

- **Live-only `[GRAPHIC-FILTER]` firing during legitimate high-scoring sequences** (e.g. 24-run overs): info-panel keyword gate over-triggering. Tighten if rate >5% of live SCOREBOARD frames.
