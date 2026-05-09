# POISON-RECAL → cold-start recovery — duration measurement & exit analysis

**Phase:** Investigation + **focused implementation** (**Issue 3 / Cause 3** — MULTI_BALL accuracy path). Companion: [`cold_start_recovery_fix_implementation.md`](cold_start_recovery_fix_implementation.md) (code changes). Related: [`state_integrity_f5054_f5240.md`](state_integrity_f5054_f5240.md), [`poison_recal_frequency_analysis.md`](poison_recal_frequency_analysis.md), [`multi_ball_decomposition_design.md`](multi_ball_decomposition_design.md).

**Method:** Chronological replay of **`[POISON-RECAL]`** markers in **`logs/pipeline*.log`** (ANSI stripped); frame IDs from prefixes **`[\d\d:\d\d:\d\d F#### ...]`**. Segment **closes** at the **next** `[POISON-RECAL]` in the same tee (exclusive). **Measurements are tee-local** — omitting **`[MULTI-BALL]`** telemetry from unrelated sessions.

---

## §1 Phase A — recovery duration telemetry

### A1. Metrics (per `[POISON-RECAL]`)

| Field | Source |
|------|--------|
| **Trip frame** | WARN line **`F####`** |
| **First cold-start candidate seeded** | `"[SM] cold-start candidate seeded"` |
| **Consensus / warm exit** | `"[SM] COLD_START → WARM (...)"` (any qualifier) |
| **Cold duration (broadcast frames)** | `warm_frame − trip_frame` (non-inclusive span; aligns with investigative “about N frames”) |
| **Seed → warm** | `warm_frame − seed_frame` whenever both exist |
| **First MULTI_BALL commentary** after trip | **`[BALL ?] MULTI_BALL`** with **`Δballs=`** |

**Limitation:** **`SCORE_MGR`** lines only emit when **`on_frame`** receives **`_build_scorecard` → dict** (at least extractor/scorer-derived **`score`**). Repeated **`FRAME_POISONED`/None reads** suppress `_handle_cold_start` entirely; **`cold_frames` did not advance** in legacy code (**§B1**) even while broadcast time marched on.

### A2. Corpus (**May 2026** inventory)

Across **`logs/pipeline*.log`** with at least one poison trip: **49** `[POISON-RECAL]` events (includes April **2026** sealed tees cited in freq analysis).

| Population | Notes |
|-----------|-------|
| **Segments with traced `COLD_START → WARM`** | **13** (**26.5 %**) |
| **`warm_frame` absent before next RECAL / EOF** | **36** (**73.5 %**) — long interviews, ingestion tail, tracker never re-opened SM in-window, etc. |

**Where both `warm` and `trip` exist** (`n = 13`):

| Stat | `seed_to_warm` | `trip_to_warm` |
|-----:|---------------:|---------------:|
| **Median** | **19** | **69** |
| **P75** | ~**38** | ~**120** |
| **P90** | **112** | **195** |
| **Max** | **289** | **1514** |

**Raw sorted `seed_to_warm` (frames):**

`[2, 2, 2, 4, 4, 6, 19, 20, 29, 38, 72, 112, 289]`.

**Correlation `trip_to_warm` vs first `Δballs`** (pairs with both telemetry, illustrative tail):

High wall-clock tails can show **large Δballs without slow SM consensus** (`seed_to_warm ≈ 2`) when seeding stalls for other reasons (**F5054** row below).

### A3. Categories (`trip_to_warm` among **successful** traces, `n = 13`)

| Bucket | Rule | Count | Share |
|--------|------|------:|------:|
| **FAST** | `< 5` | **1** | **7.7 %** |
| **NORMAL** | `5–14` | **2** | **15.4 %** |
| **SLOW** | `15–29` | **1** | **7.7 %** |
| **STALL** | `≥ 30` | **9** | **69 %** |

**Stop-condition `S1` (stall rare &lt; 5 %) — NOT met** on the **`trip_to_warm`-observed** subset. Caveat: denominator **13** excludes the **silent** (**no warm**) cohort; among **all poison trips**, “stall semantics” dominate **presentation / ingestion** artefacts as much as pure SM logic.

---

## §2 Phase B — exit-condition deep dive

### B1. `_handle_cold_start` (**`files/score_manager.py`**)

Mechanised summary (see source for authoritative control flow):

```1101:1181:files/score_manager.py
    def _handle_cold_start(self, card: dict, frame: FrameInput) -> dict | None:
        self.cold_frames += 1
        ...
        if (card.get("score") is None
                or card.get("wickets") is None
                or card.get("overs") is None):
            return None
        ...
        if not consensus:
            ...
            if self.cold_frames >= max_f:
                abs_check = validate_absolute(...)
                if not abs_check.ok:
                    ...
                    return None
                self._accept_initial(card, frame)
                self.mode = "WARM"
                ...
```

- **Consensus path:** **`COLD_START_CONSENSUS_FRAMES = 3`** matching **`score/wickets/overs`** (Δovers &lt; **0.05**).
- **Give-up flip path:** **`COLD_MAX_FRAMES = 10`** or **`COLD_MAX_FRAMES_WITH_REF = 25`** depending on **`_last_warm_state`**, guarded by **`validate_absolute`** (`lines ~1161–1180`).
- **Plausible-but-rejected-after-streak-3:** reset candidate; second give-up keyed on **`cold_frames ≥ 25`** with the same **`validate_absolute`** escape hatch (**`1161–1180`** neighbourhood).
- **Cricket legitimacy:** **`_cold_start_plausible`** enforces **`validate_absolute`** unconditionally and **`validate_diff`** when **`_last_warm_state`** exists (**stale recovery**).

Critical gap (pre-watchdog telemetry): **`self.cold_frames` increments only inside `_handle_cold_start`**. Frames where **`_build_scorecard` returns `None`** never reached cold-start — **`COLD_MAX_FRAMES` timers froze**.

### B2. STALL narratives

| Mechanism | Symptom in logs |
|----------|-----------------|
| **Carousel flip deadlock** | Many **`cold-start candidate flipped`** / **`consensus building`** lines |
| **`validate_absolute` / cricket reject churn** | **`cold-start give-up REJECT`** or **`cold-start reject`** bursts |
| **Scorer starvation** | **`[SM]` silence**: no seeded candidate — scorer never delivered a complete triple SM could evaluate |

### B3. **F5054** — stop-condition **`S2` / Direction L**

Anchors (**GT–RCB** live tee):

| Milestone | Frame | Notes |
|-----------|-------|-------|
| **`[POISON-RECAL]`** | **F5054** | Interview strip **`99/6`** vs tracker **`154/6`** — [`state_integrity_f5054_f5240.md`](state_integrity_f5054_f5240.md) |
| **`MULTI_BALL`** (`Δballs=25`) | **F5240** | Ball layer vs SM shadow divergence |
| **First **`cold-start candidate seeded`** telemetry** | **F5247** | **~193** broadcast frames gap |
| **`COLD_START → WARM`** | **F5249** | **`seed_to_warm ≈ 2`** — consensus is **easy once** scorer stabilises |

**Verdict (`S2` TRUE):** the **186-frame** wall-clock pain is dominated by **`post-match / carousel starvation + strip semantics`**, **not** a missing **`cold_frames`** give-up `if`: SM never received adoptable viable triplets to **log** seeded candidates in the carousel window (**§§3–4** of the forensic memo). **`validate_absolute` rejection before warm** did **not** explain the **`F5054→`F5247`** telemetry gap — **nothing reached plausibility checks**.

Primary fix vector remains **Direction L** (**carousel / phase-aware POISON-RECAL veto**).

---

## §3 Phase C — fallback options

| Path | Idea | Upside | Risk |
|------|------|--------|------|
| **A** | Lower **`COLD_START_CONSENSUS_FRAMES`** to **2** | Faster triple agreement | Transient hallucination **`WARM`** lock |
| **B** | **Pipeline-frame watchdog → adopt freshest viable coarse triple** (after gated thresholds), still guarded by **`_cold_start_plausible`** | Breaks carousel **flip-heavy** deadlock; pairs with **`cold_watchdog`** that advances through stripped frames | Anchors “last twitch” carousel row; plausible-but-wrong within chase band |
| **C** | **GRAPHIC**/EOO summary shortcuts | Narrative-strong when correct | Replay / aggregates / stale team strips (**RCB `/` GT head-to-head**) can **re-anchor to wrong inning entirely** |

**Shipped recommendation:** **Path B** with **dual thresholds**:

1. **`heavy_flip`** — **`cold_frames ≥ COLD_MAX_FRAMES`** (**10**) AND **`cold_pipeline_frames ≥ 25`** (**align `COLD_MAX_FRAMES_WITH_REF` scale**).
2. **`starvation`** — **`cold_pipeline_frames ≥ 45`** with at least **one stamped viable triple** (**post false-zero heuristic**).

**Path B deliberately does NOT “fix” F5054-class starvation** until the scorer emits a **`score/wickets/overs`** triple ScoreManager accepts — aligns with **`S2`**.

Constants live beside **`files/score_manager.py:COLD_*`** (**`25`/`45`** documented in companion implementation memo).

---

## §4 Correlation appendix

Representative **`trip_to_warm` / Δballs / seed-delay** triples (**from April trio + extended logs** correlation pass):

```
 F2827  tw=4   Δballs=2  seed_delay≈2
 F22    tw=8   Δballs=2  seed_delay≈4
 F3296  tw=69  Δballs=7  seed_delay≈50   # live chase — freq memo anchor
 F5054  tw=195 Δballs=25 seed_delay≈193  # post-match carousel (**S7**)
```

**Interpretation:** long **`Δballs`** can coexist with **`seed_to_warm ≈ 2`** once ingestion resumes — duration driver is **`trip_to_seed`**, not **`COLD_START_CONSENSUS_FRAMES`**.

---

## §5 Cross-references

| Doc | Tie-in |
|-----|--------|
| [`state_integrity_f5054_f5240.md`](state_integrity_f5054_f5240.md) | Post-match carousel + SM silence (**S7**) |
| [`poison_recal_frequency_analysis.md`](poison_recal_frequency_analysis.md) | Poison trip taxonomy + live-vs-tail filtering |
| [`multi_ball_decomposition_design.md`](multi_ball_decomposition_design.md) | Issue 3 Directions **B vs L** scope split |
