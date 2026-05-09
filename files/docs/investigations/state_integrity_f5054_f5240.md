# State integrity — forensic investigation (F5054→F5240, GT vs RCB)

**Phase:** Depth 2 — logs, code paths, hypothesis ranking. **No code changes.** **No fix proposals** beyond **direction selection** (**§6**).

**Companion analyses:** [`state_integrity_f3293_f3346.md`](state_integrity_f3293_f3346.md) (methodology template), [`poison_recal_frequency_analysis.md`](poison_recal_frequency_analysis.md) (**§5** surfaces **`Δballs=25`**), [`match_postmortem_data_gt_rcb_20260430.md`](match_postmortem_data_gt_rcb_20260430.md).

---

## §1 Executive summary

**Anchors (from tee brackets — do not use average-fps extrapolation):**

| Milestone | Wall-clock | Tee line | Frame |
|-----------|------------|---------:|------:|
| **`[POISON-RECAL]`** | **23:14:42** | **54501** | **F5054** |
| **`MULTI_BALL`** commentary **`Δballs=25`** | **23:23:57** | **56057** | **F5240** |

**Wall-clock span:** **23:23:57 − 23:14:42 = 9 min 15 s** (**555 s**) across **186** frames ⇒ effective **~0.335 fps** in this window (consistent with slower post-match ingest — **§2**).

**Pre-fire truth (DETAIL row):** Immediately before wipe, tracker showed **`BEFORE_score=154-6(15.4)`** — plausible **late chase** state (**54518**, DETAIL **`F5054`** excerpt in **§3**). Scout strip during **`FRAME_POISONED`** cycle read **`GT 99-6 (13.5)`** while **`action`** describes **`post-game interview`** (**54518**) — strip context is **not** trustworthy as “live chase correction.”

**`[POISON-RECAL]` count inside NR `54400–56200` slice:** **Exactly one** — line **54501** (**Phase A3**). **No cascading POISON-RECAL** within **`F5054–F5240`** (**Pattern W — LOW**).

**ScoreManager cold-start telemetry gap:** **`grep SCORE_MGR …` between tee lines `54501–56100`** yields **only** **`[SM-FULL-RESET]`** + **`FORCE_COLD_START_RECALIBRATION`** (**54502–54503**). **No** **`cold-start candidate seeded`**, **no** **`cold-start consensus building`**, **no** **`COLD_START → WARM`** until:

| Event | Tee line | Frame |
|-------|---------:|------:|
| **`[SM] cold-start candidate seeded 147/6 (19.5)`** | **56255** | **F5247** |
| **`[SM] COLD_START → WARM (consensus 3/3) 147/6 (19.5)`** | **56339** | **F5249** |

So **`ScoreManager` remained unable to seed consensus for ~193 frames** after RECAL, while the overlay carousel cycled **`GT 0-0`**, highlights (**`43-0`**, **`198-6`**, career graphics **`309-0`**, **`RCB 0-0`**, etc.) — DETAIL summaries in **§3**.

At **`F5240`**, telemetry shows **`[SHADOW] SM=None BED=MULTI_BALL MISSED`** (**56065**) — **ball-event layer emitted `MULTI_BALL`** while **`ScoreManager` shadow compares empty**. **`CORRECTION_BLOCKED:137`** + **`CONSENSUS` frame `1/2`** (**56061–56063**) blocks immediate scorer commit; **`Over-jump rejected: 15 → 19`** (**56061**); wickets jump **`0→6`** with **`168 prior frames`** at **`wickets=0`** (**56048–56049**).

**Stop-condition S7 — CONFIRMED:** This window is dominated by **post-match / presentation / replay** semantics in the **`scout=STRIP` / `action=`** text — **not** a live middle-overs chase segment. **`Δballs=25`** reflects **carousel-driven score/overs divergence** reconciled in one **`MULTI_BALL`**, **not** “4–5 overs of legal live balls” in the sporting sense.

**Pattern ranking (§5):**

| Pattern | Verdict |
|---------|---------|
| **X** (single extended poison / cold-start stall) | **HIGH** |
| **W** (cascading RECAL) | **LOW** (1 fire) |
| **V** (broken exit bug) | **LOW–MEDIUM** — exit predicates **did** eventually fire once inputs stabilized; primary delay is **input chaos + consensus**, not a single missing `if` (**§4**). |
| **Z** (instrumentation) | **MEDIUM** — **`SM=None` vs `BED=MULTI_BALL`** and **`[BALL EVENT ?] … Δballs=0`** vs commentary **`Δballs=25`** (**56057** vs **56069**). |

**Direction selection (§6):** Prefer **new scoped lane: “post-match / carousel POISON-RECAL guard”** + **Direction B (MULTI_BALL / SM–BED telemetry & decomposition)**. **Direction A2 (threshold-only)** **does not** address **S7** — RECAL fired on **`abs(Δ)>7`** during **interview** where **`Δ=-55`** but **truth was likely tracker-side**, not strip-side.

---

## §2 Window anchors and broadcast context

### §2.1 Pipeline slice sanity (**stop-condition S1**)

`awk 'NR>=54400 && NR<=56200' logs/pipeline-2026-04-30-gt-rcb-live.log | wc -l` → **1801** lines — bracket range **covers** **`54501`** and **`56077`** ✅.

### §2.2 **`F5054`** anchor

From **`DETAIL|F5054`** (**54518**, ANSI stripped excerpt):

- **`scout=STRIP:`** **`GT 99-6 (13.5)`** … **`post-game interview`**
- **`BEFORE_score=154-6(15.4)`**, **`AFTER_score=None-None(None)`** after wipe
- **`scorer_changes=['FRAME_POISONED:99']`**
- **`AFTER_innings=2`**, **`AFTER_target=156`**

Immediate WARN chain (**54499–54503**):

- **`[POISONED] … 99 vs tracker 154 (delta=-55)`** (**54499**)
- **`[POISON-STREAK] … streak=5/5`** (**54500**)
- **`[POISON-RECAL] … tracker baseline 154 is stale`** (**54501**)
- **`[SM-FULL-RESET]`**, **`FORCE_COLD_START_RECALIBRATION`** (**54502–54503**)

### §2.3 **`F5240`** anchor

From **`DETAIL|F5240`** (**56077**):

- **`scout=STRIP:`** **`GT 137-6 (19.5)`** (presentation-style **`INFO_PANEL`** filler visible in strip text)
- **`scorer_changes=['CORRECTION_BLOCKED:137']`**
- **`AFTER_score=None-6(19.5)`** — wickets populated before numeric **team score** resolves (`None` runs slice — integrity distortion persists past **`MULTI_BALL`** row)
- **`ball_event=MULTI_BALL`**
- **`AFTER_innings=2`**, **`AFTER_fow_count=6`**

### §2.4 **`MULTI_BALL` anatomy**

| Line | Payload |
|------|---------|
| **56057** | **`[BALL ?] MULTI_BALL \| 19.5 +0 runs (Δballs=25)`** |
| **56058** | **`Missed 25 balls (+0 runs) — added 2 placeholders (capped from 25)`** |
| **56069** | **`[BALL EVENT ?] MULTI_BALL \| None \| +0 runs (Δballs=0)`** — **instrumentation contradicts** **56057** (**Pattern Z** evidence). |

### §2.5 Match phase mapping (user ground truth vs log)

User ground truth: GT **158/6 (15.5)** chase complete ([`match_postmortem_data_gt_rcb_20260430.md`](match_postmortem_data_gt_rcb_20260430.md)). **`BEFORE_score=154-6(15.4)`** at **`F5054`** is **consistent with near completion** (~4 runs short of final, one ball fraction). **`23:14`–`23:24` IST** wall times align with **post-match production** (interviews, trophy, replays), **not** powerplay.

**Conclusion:** Frame index **does not map linearly** to “minutes since 22:00” using global average fps — always use **bracket timestamps** (**user instruction honored**).

---

## §3 Per-frame timeline (Phase B)

### §3.1 Condensed DETAIL milestone table

Full **`DETAIL`** rows for **`F5048–F5250`** were enumerated via pipeline grep (~**40** rows). Below: **milestones only** (tee line · clock · frame · strip headline / notes). *Omitted:* routine duplicate **`GT 0-0 (0.0)`** presentation rows — they **dominate** **`F5134–F5230`**.

| Line | Clock | Frame | Strip / tag summary |
|-----:|-------|------:|---------------------|
| 54401 | 23:14:27 | F5048 | **`GT 99-6 (13.5)`** — **post-match interview** |
| 54427 | 23:14:31 | F5049 | **`GT -P 9 W 5 L … STANDING`** — **non-live table** |
| 54458 | 23:14:38 | F5053 | **`99-6`** interview |
| **54518** | **23:14:43** | **F5054** | **`99-6`** interview; **`AFTER_score=None`** post-RECAL |
| 54838 | 23:17:11 | F5134 | **`GT 0-0`** — **“GT has won…”** celebration text |
| 54873 | 23:17:16 | F5135 | **`0-0`** celebration / info panel |
| 55017 | 23:17:39 | F5141 | **`0-0`** return-to-pitch filler |
| 55087 | 23:18:09 | F5152 | **`43-0 (4.2)`** — **highlight / flashback** Gill |
| 55118 | 23:18:14 | F5153 | **`16-0 (1.1)`** inconsistent flashback |
| 55164 | 23:18:21 | F5157 | **`0-0`** |
| 55224 | 23:18:28 | F5159 | **`47-0 (4.3)`** hybrid batter line |
| 55273 | 23:18:36 | F5162 | **`GRAPHIC`** **`43-0 (18/3)`** — **stat overlay syntax** |
| 55341 | 23:18:55 | F5169 | **`198-6 (18.1)`** — **aggregate graphic** |
| 55377 | 23:19:09 | F5173 | **`0-0`** |
| 55415 | 23:19:14 | F5174 | **`39-0 (3.5)` Buttler — wrong-phase batting snapshot |
| 55488 | 23:19:26 | F5176 | **`RCB 0-0`** — **wrong team strip** |
| 55560 | 23:20:08 | F5190 | **`GRAPHIC`** **`309-0`** career stat panel |
| 55671 | 23:21:41 | F5219 | **`0-0`** presentation close-up |
| 55799 | 23:22:52 | F5229 | **`20-0 (2.5)`** brief coherent snippet |
| 55831 | 23:22:57 | F5230 | **`0-0`** |
| 55880 | 23:23:28 | F5234 | **`197-6 (20.0)`** interview |
| 55906 | 23:23:33 | F5235 | **`147-6 (19.5)`** |
| 55957 | 23:23:42 | F5237 | **`198-6 (19.3)`** |
| 55993 | 23:23:47 | F5238 | **`147-6 (19.5)`** |
| 56016 | 23:23:52 | F5239 | **`198-6 (19.5)`** |
| **56077** | **23:23:57** | **F5240** | **`137-6 (19.5)`** + **`MULTI_BALL` / `CORRECTION_BLOCKED:137`** |
| 56304 | 23:24:24 | F5248 | Continued presentation oscillation |

### §3.2 **`AFTER_score=None` window (B2)**

| Metric | Finding |
|--------|---------|
| **First `AFTER_score=None-None` on DETAIL after incident** | **`F5054`** DETAIL (**54518**) immediately post-RECAL |
| **First numeric team score restoration on DETAIL** | Still **`None`** runs component at **`F5240`** (**`AFTER_score=None-6(19.5)`**, **56077**) — **partial** recovery |
| **DETAIL density** | Sparse (~**40** rows / ~**200** frames) — many frames lack **`DETAIL`** entirely (ads/skips). |

Comparison to **`F3296→F3346`** memo ([`state_integrity_f3293_f3346.md`](state_integrity_f3293_f3346.md)): earlier window **`~53`** frames / **`111 s`** with **`MULTI_BALL Δballs=7`** during **live chase filler**. **`F5054→F5240`** is **longer wall-clock**, **non-live carousel**, **`ScoreManager` silent until `F5247`**.

### §3.3 Individual **`ball_event`** rows

**`grep '[DELIVERY ENQUEUED]'`** restricted to tee lines **`54501–56150`:** **no matches** — **no enqueued live deliveries** captured in this parser pass — aligns with **post-match** (**§2.5**).

### §3.4 Frame artifacts (**stop-condition S3**)

Shell `find` under `files/debug_frames_archive/` (read-only):

- **`2026-04-30_193643/f505_scoreboard.jpg`**
- **`2026-04-30_193643/f524_scoreboard.jpg`**

Same bucket as **`F3293–F3346`** window — cross-date collision possible for low frame numbers but **date-stamped folder** matches GT–RCB evening session. **No** obligation to open binary assets here.

---

## §4 Recovery mechanism analysis (Phase C)

### §4.1 Cold-start exit logic (code)

**Gate — complete card required** (`files/score_manager.py`):

```1069:1072:files/score_manager.py
        if (card.get("score") is None
                or card.get("wickets") is None
                or card.get("overs") is None):
            return None
```

**Consensus frames:** **`COLD_START_CONSENSUS_FRAMES = 3`** (**120**, **1134–1141**, **1171–1174**).

**Behavior:** `_handle_cold_start` returns **`None`** until **three** consecutive agreeing **`score/wickets/overs`** tuples land; mismatched carousel frames **flip** candidate & reset streak (**1099–1109**).

### §4.2 Scorer-side large correction consensus (`test_pipeline.py`)

At **`F5240`** (**56056–56063**):

- **`GUARD Score correction … 0→137 (delta=137) — blocking ALL updates`**
- **`CONSENSUS Score 137 frame 1/2, waiting`**

Mirrors **`_CORRECTION_CONFIRM = 2`** machinery (**8978–8993** region documented in [`state_integrity_f3293_f3346.md`](state_integrity_f3293_f3346.md)).

### §4.3 Why recovery waited ~193 frames (**C2 categorization**)

**Primary:** **`Persistent poisoning / unstable strip`** — not chemical OCR “poison,” but **broadcast-phase**: **`post-match`** feeds violate cold-start assumptions (**oscillating narratives**, **`0-0`**, **`GRAPHIC`** Career stats, **`RCB`** strips). **`ScoreManager`** silently **`return None`** (no **`SCORE_MGR`** logs) because **cards fail completeness / plausibility / flip on every frame** — evidenced by **absence** of **`cold-start candidate`** lines until **56255**.

**Secondary:** **`POISON-RECAL` false orientation** — mechanism assumes **strip is “live truth”** after 5 poison reads; here **tracker `154/6 @15.4` was more plausible** than **interview strip `99/6 @13.5`**. RECAL **clears** the better baseline.

**Not primary:** **Cascading RECAL** (single fire). **Pure exit-condition bug** unlikely — **`COLD_START → WARM`** **does** occur at **56339** once **`147/6/19.5`** stabilizes.

### §4.4 Comparative scaling (**C3**)

| Window | Frames | Wall | **`MULTI_BALL` `Δballs`** | SM telemetry |
|--------|-------:|-----:|--------------------------:|--------------|
| **`F3293→F3346`** | ~53 | ~111 s | **7** | Candidate **34004** (`F3346`) per prior memo |
| **`F5054→F5240`** | **186** | **555 s** | **25** | **No** SM cold-start logs **54501–56100** except initial force; **first seed `F5247`** |

**Ratio:** **`Δballs` ~3.6×**, **frames ~3.5×**, **wall-clock ~5×** — **super-linear** wall stretch from **~0.34 fps** vs **~0.48 fps** in earlier window.

**Categorical difference:** **S7** — second window is **production/post-match regime**, not scaled live-chase stall.

---

## §5 Pattern evaluation (Phase D)

### Pattern X — single extended poison / cold-start episode

| FOR | AGAINST |
|-----|---------|
| **One** **`[POISON-RECAL]`** (**54501**) | Label “poison” blurs — much strip data is **valid for its genre** but **wrong for live scoring** |
| Cold-start stuck until **`F5247`** seed (**56255**) | Implies mechanism **works** eventually |
| Carousel noise matches **flip/reset** semantics (**1099–1109**) | **Operational pain** remains extreme |

**Rank:** **HIGH**

### Pattern W — cascading RECAL

Only **one** **`[POISON-RECAL]`** inside documented slice (**54501**).

**Rank:** **LOW**

### Pattern V — broken recovery exit

Gate **requires stable triplets + consensus + plausibility**. Telemetry shows **long silent SM phase** — consistent with **inputs**, not unreachable exit **predicate**.

Partial **V**: **`CORRECTION_BLOCKED`** delays scorer commits (**56061–56063**).

**Rank:** **LOW–MEDIUM**

### Pattern Z — instrumentation

**`SM=None`** shadow (**56065**) vs **`MULTI_BALL`** emission; **`Δballs`** mismatch **56057** vs **56069**.

**Rank:** **MEDIUM**

---

## §6 Direction selection (Phase E)

| Recommended primary | Rationale |
|---------------------|-----------|
| **New direction — “carousel / post-match POISON-RECAL & cold-start policy”** | **`S7`** dominates — threshold **`N=5`** / **`absΔ>7`** **mis-fired** against **valid tracker** vs **interview strip**. Needs **phase detection** or **RECAL veto** when **`action`/scout semantics imply post-match** — **scoped design**, likely **`test_pipeline`** guardrails adjacent **7874–7975**. |

| Recommended parallel | Rationale |
|------------------------|-----------|
| **Direction B — `MULTI_BALL` / SM–BED decomposition** | **`[SHADOW] SM=None BED=MULTI_BALL MISSED`**, placeholder capping (**56058**), **`Δballs` inconsistency** (**56057** vs **56069**) — **telemetry & ownership clarity** without changing thresholds. |

| Deprioritized here | Rationale |
|--------------------|-----------|
| **Direction A2 — numeric threshold only** | Does not separate **live vs post-match**; risks replaying **PBKS/MI template rescue** regressions ([`poison_recal_frequency_analysis.md`](poison_recal_frequency_analysis.md) **§6.3**). |

**Confidence:** **Medium–high** on **S7 + cold-start starvation**; **medium** on engineering fix shape (needs product policy on **post-match** scoring).

**What would change recommendation:** Demonstrate, via replay, **≥3** analogous windows during **live middle overs** with **same SM silence** pattern — would upgrade **Pattern V** investigation.

---

## §7 Implications for prior findings

| Prior doc | Revision |
|-----------|----------|
| [`poison_recal_frequency_analysis.md`](poison_recal_frequency_analysis.md) | **`F5054→F5240`** must be annotated as **post-match / presentation-heavy** — **`Δballs=25` is not comparable** to **`F3296`** chase bridge without **phase tag**. Worst-case **`MULTI_BALL` list** splits into **(a) live chase** vs **(b) post-match reconciliation**. |
| [`state_integrity_f3293_f3346.md`](state_integrity_f3293_f3346.md) | **No retraction** — first window remains **live-phase Pattern Y**. Second window **does not** disprove prior code-path analysis; it adds **regime dependence**. |
| [`match_postmortem_data_gt_rcb_20260430.md`](match_postmortem_data_gt_rcb_20260430.md) | Supports using **final score** to interpret **`154/6 @15.4`** as **near terminal chase** — aligns with **`BEFORE_score`** at **`F5054`**, contradicting “mid chase” heuristic. |

---

## §8 Limitations

1. **Single** second-case deep dive — no third **`Δballs≥20`** peer on MI–SRH / PBKS ([`poison_recal_frequency_analysis.md`](poison_recal_frequency_analysis.md)).
2. **`machine-1`** correlation **not attempted** (**stop-condition S2** assumed — prior session grep empty for frame IDs).
3. **No pipeline replay** — cannot assert pixel-level strip truth.
4. **Public ball-by-ball** at **minute** resolution **absent** — broadcast claims remain **tee-anchored**.

---

## §9 Cross-references

| Resource | Lines / sections |
|----------|------------------|
| **`logs/pipeline-2026-04-30-gt-rcb-live.log`** | **54499–54503**, **54518**, **54838+**, **56048–56077**, **56255**, **56339** |
| **`files/test_pipeline.py`** | **7874–7975** poison/recal; **8978–8993** correction consensus |
| **`files/score_manager.py`** | **`full_reset` 780–798**; **`_handle_cold_start` 1057–1175**; **`COLD_START_CONSENSUS_FRAMES` 120** |
| [`state_integrity_f3293_f3346.md`](state_integrity_f3293_f3346.md) | Methodology reference |
| [`poison_recal_frequency_analysis.md`](poison_recal_frequency_analysis.md) | **`§5` worst-case inventory** |

---

### Stop-condition ledger

| ID | Resolution |
|----|------------|
| **S1** | **`54400–56200`** spans anchors ✅ |
| **S2** | **Skipped** (expected absent). |
| **S3** | **Partial** artifact coverage **`f505_*`, `f524_*`** under **`2026-04-30_193643/`**. |
| **S4** | Cold-start mechanics match hypotheses — enriched with **`SM` silence** observation. |
| **S5** | **false** — **`POISON-RECAL`** present (**54501**). |
| **S6** | **Carousel / shadow mismatch** flagged (**§1**, **§5 Pattern Z**). |
| **S7** | **TRUE** — reframes severity (**§1**, **§2.5**). |

---

*Investigation-only memo — production code untouched.*
