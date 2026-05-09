# Issue 3 — MULTI_BALL decomposition (Direction B): design memo

**Phase:** Depth 2 — forensic cross-check + consumer audit + implementation-facing scope. **No production code changes** in this task.

**Primary references:** [`state_integrity_f3293_f3346.md`](state_integrity_f3293_f3346.md), [`state_integrity_f5054_f5240.md`](state_integrity_f5054_f5240.md), [`poison_recal_frequency_analysis.md`](poison_recal_frequency_analysis.md); code: `files/score_manager.py`, `files/test_pipeline.py`, `files/eyes/this_over.py`, `files/wire.py`; tee `logs/pipeline-2026-04-30-gt-rcb-live.log`.

---

## §1 Executive summary (answers Q1–Q4)

| Question | Verdict (one line) |
|----------|---------------------|
| **Q1** | **`state_integrity_f5054_f5240.md` is listed in [`INDEX.md`](INDEX.md) and exists on disk.** F5054→F5240 is **Pattern X–heavy** (single extended poison / cold-start stall through carousel), **Pattern W LOW** (exactly **one** `[POISON-RECAL]` in **54501–56057**), **Pattern V LOW–MEDIUM** (exit predicates eventually fire; delay dominated by unstable strip/consensus, not a proven “missing exit `if`”). **Direction B remains appropriate for live Issue 3** (F3293-class UI cadence). **It does not supersede** the **post-match / carousel POISON-RECAL guard** lane called out in F5054 §6 — that is **additive P1**, not a reason to cancel decomposition. |
| **Q2** | ScoreManager emits a **single dict** `MULTI_BALL` with **`balls_skipped`**, **`runs`**, **`overs_skipped`**, **`wickets_in_gap`**, **`striker`** (no `legal` / `this_over_token` / `certain`). BED may emit a **different shape** (`balls_missed`, `total_runs`, `certain: False`). **Consumers are split:** WS/`build_full_payload` follows ScoreManager when `not shadow`; **`ThisOverManager`** and **`[DELIVERY ENQUEUED]`** follow **BED `ball_event`** when `ball_detector.detect` fires — **`MULTI_BALL` is not in `_real_delivery_types`**, so **async delivery analysis does not enqueue on SM-only MULTI_BALL today.** |
| **Q3** | **Recommend Policy U (honest absorbed balls)** implemented as **synthetic per-ball events** that stay **`certain=False`**, carry **aggregate gap metadata once** (parent `balls_skipped`, `runs`, `wickets_in_gap`), and use a **dedicated type** (e.g. `ABSORBED_LEGAL` or keep **`MULTI_BALL` micro-events**) **not** in `_COMMENTARY_ELIGIBLE_BALL_TYPES`, so **commentary does not fabricate ball narratives.** **Do not** rely on Layer 2 retrospective to “fill truth”: DWR-style telemetry shows **retrospective spans ~3.94%** vs **fallback ~96%** ([`match_postmortem_data_gt_rcb_20260430.md`](match_postmortem_data_gt_rcb_20260430.md) §4 table). Even splits (E) and last-ball runs (L) stay **out of scope for honest scoring** unless product accepts **explicit fictional ball classification**. |
| **Q4** | **MEDIUM** effort (**~100–250 LOC** across **2–4 files**): **`score_manager.py`** emission + **`_apply_event`** semantics for multi-event or stepped synthetic overs; **`test_pipeline.py`** to **fan out** absorbed balls into **`ThisOverManager`** / logging / optional enqueue policy; **`eyes/this_over.py`** token policy for absorbed balls; tests mirroring **`test_fixture_multi_ball_gap_camera_state_transition`** in **`test_recent_fixes.py`**. **Rollback:** single commit revert **if** decomposition is isolated behind helper + telemetry tags; **risk** rises if BED/SM merge semantics change widely. |

### §1.1 INDEX / F5054 memo status

- **`grep -i f5054 files/docs/investigations/INDEX.md`:** row present for **`state_integrity_f5054_f5240.md`**.
- **Glob:** `files/docs/investigations/state_integrity_f5054_f5240.md` exists.
- **Conclusion:** Q1 is **not** blocked by a missing second-case memo.

---

## §2 Q1 — Fix level: decomposition vs recovery mechanism

### §2.1 F5054 executive facts (from landed memo)

- **Single `[POISON-RECAL]`** at tee line **54501** / **F5054**; **MULTI_BALL** commentary **`Δballs=25`** at **56057** / **F5240**.
- **Wall-clock ~9m15s**, **186** frames — **post-match / carousel** context (**S7**): strip not trustworthy as live chase correction.
- **ScoreManager** telemetry gap until **`cold-start candidate seeded`** at **56255** (**F5247**) — long stall **after** the poison wipe.
- **Pattern ranking (F5054 §1):** **X HIGH**, **W LOW**, **V LOW–MEDIUM**, **Z MEDIUM** (e.g. **`SM=None BED=MULTI_BALL MISSED`**, **`Δballs=0` vs `Δballs=25`** tension).

### §2.2 Abbreviated log window (54501–56057)

Filtered tee lines for **`POISON-RECAL`**, **`MULTI_BALL`**, **`FRAME_POISONED`**:

- **`[POISON-RECAL]`:** **1** occurrence (**54501**) → **not Pattern W** (cascade) inside this window.
- **`MULTI_BALL`:** **56057** (commentary anchor).
- **`FRAME_POISONED` / poison-class DETAIL churn:** many rows — consistent with **extended distrust / carousel**, not a second RECAL trip.

**Phase A4 mapping:**

- **Not Pattern W** in-window (single RECAL).
- **Not Pattern V as primary stop** — F5054 argues exit **does** fire once inputs stabilize; stall is **consensus + chaotic strip**, not proof of a single broken exit predicate.
- **Pattern X (+ Z instrumentation caveats)** fits — decomposition addresses **UI/event cadence**; **carousel guard** addresses **whether RECAL should fire** in post-match segments.

### §2.3 Recovery exit (cold-start → warm) — code anchor

**Exit conditions** (`files/score_manager.py` **`_handle_cold_start`**):

1. **Consensus path:** same **`score`/`wickets`/`overs`** within tolerance for **`COLD_START_CONSENSUS_FRAMES = 3`** consecutive agreeing frames (**1092–1175**).
2. **Give-up path:** **`cold_frames`** vs **`COLD_MAX_FRAMES`** (**10**) or **`COLD_MAX_FRAMES_WITH_REF`** (**25**) when candidate **flips** or **`_cold_start_plausible`** fails (**1110–1164**), with **`validate_absolute`** guard before adopting.

**Interpretation for Q1:** There **is** a frame bound, but **real-world stalls** (F5054) still occur when **cards are incomplete**, **`_false_zero_cold_start`** rejects graphics, or consensus **never stabilizes** — decomposition **does not fix** that class; **lifecycle / ingest gating** does. That is **orthogonal** to Direction B for **Issue 3** (per-ball UI visibility after a **valid** warm recovery jump).

### §2.4 Q1 verdict

- **Decomposition is still the right primary lever for “over jumps / skipped deliveries” in live recovery** (F3293 narrative): one **`MULTI_BALL`** absorbing **`d_balls`** legal advances collapses UI/`this_over` pacing.
- **F5054 does not supersede Direction B**; it **adds** requirement: **gate POISON-RECAL** (or strip trust) **during post-match carousel** so decomposition is not asked to “explain” **presentation-induced** 25-ball gaps.
- **Pattern V stop condition (S1) does not trigger** — no recommendation to **halt** Q2–Q4.

---

## §3 Q2 — Emission shape and downstream consumers

### §3.1 ScoreManager `MULTI_BALL` emission (`_infer_event`)

**Site:** `files/score_manager.py` **2284–2298**.

Emitted dict:

```2284:2298:files/score_manager.py
    def _infer_event(self, d_score: int, d_wickets: int, d_overs: float,
                     prev: dict, card: dict,
                     frame: FrameInput) -> dict | None:

        striker, non, striker_runs = self._identify_striker(
            prev, card, frame)

        # MULTI_BALL: skipped deliveries (use ball count, not decimal overs)
        new_overs = card.get("overs") or self.overs or 0
        old_overs = prev.get("overs") or 0
        d_balls = self._overs_to_balls(new_overs) - self._overs_to_balls(old_overs)
        if d_balls > 1:
            return {"type": "MULTI_BALL", "runs": d_score,
                    "overs_skipped": d_overs, "wickets_in_gap": d_wickets,
                    "balls_skipped": d_balls, "striker": striker}
```

**Read at emission time:** `prev` snapshot **before** `_accept_update`; **`d_score` / `d_wickets` / `d_overs`** team-level deltas; **`striker`** from `_identify`. **`_infer_wicket` is skipped** when **`d_balls > 1`** (classification ordering).

**State application (`_apply_event`):** **`MULTI_BALL`** clears **`this_over`** / **`this_over_src`** (and may **`_complete_over`** if integer over rolled) — **does not append per-ball tokens** (**2511–2514**). Partnership branch treats **`MULTI_BALL`** like a non-wicket event: **`partnership_runs += runs`**, **`partnership_balls += 1`** if **`legal` defaults True** (**2716–2722**) — **partnership ball count undercounts** multi-ball gaps today (pre-existing semantic skew).

### §3.2 Single legal-ball shape (comparison target)

**`_infer_legal`** returns **`DOT` / `FOUR` / `SIX` / `RUNS`** with **`this_over_token`**, **`striker`**, **`runs`** (**2479–2498**). Those types drive **`_apply_event`** append path (**2542–2543**) and strike rotation (**2586–2589**).

**Decomposition invariant:** downstream should receive **`N` events** shaped like **legal deliveries** (or a **single dedicated absorbed type**) — **not** **`N` copies of aggregate `MULTI_BALL`**.

### §3.3 BED `MULTI_BALL` (different contract)

**`files/eyes/commentary.py`** builds **`MULTI_BALL`** with **`balls_missed`**, **`total_runs`**, **`certain: False`** when **`balls_delta > 1`** (**464–466**).

**`files/eyes/this_over.py`** placeholder branch reads **`balls_missed`** / **`total_runs`** (**460–472**) — **not** **`balls_skipped`**. ScoreManager’s dict keys **do not match** this branch unless normalized upstream.

### §3.4 Consumer inventory

| Consumer | Location | `MULTI_BALL` / ball handling | Risk if **N** synthetic balls |
|----------|----------|------------------------------|-------------------------------|
| **`ScoreManager._apply_event`** | `score_manager.py` **2504–2723** | Special case clears **`this_over`** | Must run **per ball** or replace with token loop; **strike rotation** must be **correct per absorbed ball** (odd runs) — **hard problem** without per-ball truth |
| **`ScoreManager._build_payload`** | `score_manager.py` **2892–2972** | Embeds **`ball_event`** on payload | Last event wins unless API becomes **list** or **multi-dispatch** frame |
| **`InlineCommentary`** | `test_pipeline.py` **248–303**, **10077–10091** | **`MULTI_BALL` not eligible**; **`certain=False` rejected** | **Policy U + `certain=False`** keeps commentary silent per ball — **safe**. **Policy E/L + `certain=True`** risks **N× LLM** cost |
| **`BallAnalyzer.enqueue_delivery_analysis`** | `test_pipeline.py` **9648–9700** | Gate **`_evt_is_real`** — **`MULTI_BALL` excluded** | Today **SM MULTI_BALL often skips enqueue** (BED `ball_event` empty). **Decomposed `DOT`/`RUNS` with `certain=True`** could trigger **N enqueues** → **cost blowup** unless **gated** (`absorbed` flag → exclude or batch) |
| **`ThisOverManager.on_ball_event`** | `eyes/this_over.py` **392–472** | **`MULTI_BALL`** → capped **`?`** placeholders | Needs **either** **N placeholder/token append** **or** **N absorbed events** with explicit tokens |
| **`format_wire`** | `wire.py` **90–93** | **`MULTI_BALL`** outcome string uses **`overs_skipped`** | Per-ball wire needs template or suppression for absorbed stream |
| **`[SHADOW]` compare** | `test_pipeline.py` **10009–10031** | Logs SM vs BED mismatch | Decomposition should define **whether BED also emits** multi-ball or stays **None** |
| **Partnership / packet fan-out** | `test_pipeline.py` **10101–10230** | Branches on **`ball_event`** (**BED** path) | If only **`ws_payload`** carries SM events, **analytics packet** may **omit** absorbed balls unless **`ball_event`** variable unified |
| **`scorer_decision_schema.py`** | *(grep)* | **No `MULTI_BALL` symbols** | No schema change strictly required for taxonomy |

### §3.5 Layer 2 / delivery classification cost

**Current wiring:** **`enqueue_delivery_analysis`** runs inside **`if ball_event:`** (BED) and only when **`_evt_is_real`** (**9648–9657**). **`MULTI_BALL`** ∉ **`_real_delivery_types`** and does not match **`*_RUNS`** suffix → **no enqueue**.

**Verdict:** Today’s **`MULTI_BALL`** is **not** multiplying Layer 2 cost. **Decomposition that emits `DOT`/`RUNS`-shaped events into the BED path with `certain=True`** would **re-enable N× enqueue** — **S2-class risk**. Mitigations: **`absorbed=True` → skip enqueue**, **single batched enqueue**, or **cap async fan-out**.

### §3.6 WebSocket / UI burst

- **Broadcast:** one **`broadcast_state`** per processed frame today; **multiple logical balls per frame** implies **either** multiple WS ticks (if pipeline loops) **or** one payload with **`ball_events[]`** — **product decision**.
- **Race / animation:** UI assumptions unknown in this memo; ** safest** approach is **explicit absorbed markers** (`?` / muted styling) **consistent** with **`ThisOverManager`** placeholder semantics.

---

## §4 Q3 — Attribution policy

### §4.1 Policy scoring vs consumers

| Policy | Commentary (`_COMMENTARY_ELIGIBLE_BALL_TYPES` + `certain`) | `ThisOverManager` | Layer 2 enqueue | Honesty |
|--------|------------------------------------------------------------|-------------------|-----------------|---------|
| **U — UNKNOWN / absorbed** | **Out of whitelist** + **`certain=False`** → **no fabricated narration** | **`?`** or dedicated token | **Skip or batch** | **High** |
| **E — even split** | If typed as **`RUNS`** + **`certain=True`** → **eligible** → **falsePrecision** | Numeric tokens **lie** | **N× cost** unless gated | **Low** |
| **L — last ball** | Same as **E** for **`DOT`**/`RUNS` | **Misleading** dot narrative | **N× cost** unless gated | **Low** |

### §4.2 Layer 2 retrospective baseline

From **`match_postmortem_data_gt_rcb_20260430.md`** (DWR assembly modes): **`retrospective_span`** **~3.94%** vs **`fallback_pre_event_window`** **~96.06%**. **Policy U cannot assume** retrospective VLM will repair absorbed windows at scale.

### §4.3 Recommendation

**Adopt Policy U** with:

1. **Synthetic per-ball records** carrying **`certain=False`**, **`absorbed_gap=true`**, **`gap_parent={runs, wickets_in_gap, balls_skipped}`** on first event or parallel metadata.
2. **Event type** either **`MULTI_BALL` micro-event** (extended schema) **or** new **`ABSORBED_LEGAL`** — **must remain excluded** from **`_COMMENTARY_ELIGIBLE_BALL_TYPES`** unless product explicitly opts in.
3. **Explicit user-visible behavior:** **`this_over`** shows **N placeholders** (`?`) or equivalent — **honest “we missed structure here”** rather than fake **`.` / `1`**.

**Reject E/L** for default Issue 3 fix unless stakeholders accept **intentionally fictional per-ball reconstruction** documented in UI.

---

## §5 Q4 — Implementation scope

### §5.1 File:line touch list (planned)

| Area | File | Lines / region | Change class |
|------|------|----------------|--------------|
| Emission | `score_manager.py` | **`_infer_event` ~2284–2298** | Replace single **`MULTI_BALL`** return with **helper** emitting **N events** or **single bundle** processed by runner |
| Apply | `score_manager.py` | **`_apply_event` ~2504–2723**, **`on_frame` ~1605–1617** | Loop **`_apply_event`** with **intermediate `prev`** advancement **or** refactor to **consume stepped overs** |
| Cold / warm entry | `score_manager.py` | **`_handle_warm` ~1589–1617** | Ensure **`on_frame` returns** handle **multi-event** (API choice: **last payload** vs **list**) |
| Pipeline merge | `test_pipeline.py` | **`~9506–9782`**, **`~10009–10140`**, **`~10196–10238`** | Fan-out **`ThisOverManager`**, **`[BALL EVENT]`** logs, partnership hooks, **enqueue guard** |
| This-over UX | `eyes/this_over.py` | **`_append_event_token` ~460–472** | Absorbed-per-ball tokens / cap rules across overs |
| Wire | `wire.py` | **`~90–93`** | Absorbed-friendly short wire or **suppress** |
| Telemetry | `score_manager.py` / `test_pipeline.py` | emission sites | **`[MULTI_BALL_DECOMPOSED]`**, per-ball **`[ABSORBED_LEGAL]`** |
| Tests | `test_recent_fixes.py` | new fixtures | **`test_fixture_multi_ball_gap_*`** pattern (**10543+**) |

### §5.2 Diff size estimate

- **SMALL (<100):** unrealistic if pipeline fan-out is included.
- **MEDIUM (100–300):** likely — helper + `_apply_event` loop + `test_pipeline` guarded enqueue + tests.
- **LARGE (>300):** if strike rotation / FOW / partnership semantics require full cricket simulator for absorbed gaps.

### §5.3 Test fixture shape (minimum **5** cases)

Mirror **`test_fixture_multi_ball_gap_camera_state_transition`** style (**Mock/patch logging**, assert **`ThisOverManager`** tokens + telemetry):

1. **`d_balls=2`**, `runs=0`, `wickets=0` — minimal loop.
2. **`d_balls=7`** — F3293-scale gap (overs fraction alignment).
3. **`d_balls=25`** — F5054-scale gap **sanity** (overs progression / caps).
4. **`d_balls>1` + `wickets_in_gap>0`** — placeholder **FOW** interaction (**score_manager** gap padding **2706–2712**).
5. **Over boundary spanning gap** — ensures **`is_over_change`** archival ordering matches **`_apply_event`** **2516–2543** semantics.

**Inputs:** `prev` overs/score/wickets + incoming **`card`** after **`_accept_update`** validation passes.

**Outputs:** **`N` events** with Policy **U** fields; **`this_over`** length **+= N** (subject to per-over cap policy); **no `DELIVERY ENQUEUED` multiplication** unless test asserts intentional batching.

### §5.4 Rollback

- **Single-commit revert** feasible if changes are **localized** (helper + conditional fan-out + tests).
- **Higher coupling risk:** altering **`on_frame` return type** or **`build_full_payload`** contract — prefer **internal loop** with **single external payload** initially.

---

## §6 Ready-to-ship gate

**`ready_to_ship`:** **NO** (against the memo’s strict definition **SMALL + clear single-hop diff**).

**Reason:** Consumer graph has **BED vs SM split**, **`balls_skipped` vs `balls_missed`** mismatch, and **Layer 2 enqueue coupling** — decomposition requires **targeted pipeline merging** and **`absorbed` gating**, not **`score_manager.py` ~2291-only**.

**Readiness for implementation task block:** **YES** — Q2–Q4 are sufficiently constrained to start coding **next session**, beginning with **API choice** (single frame multi-apply vs multi-broadcast) and **`absorbed` enqueue guard**.

---

## §7 Risks and open questions

1. **Strike rotation across absorbed balls** without per-ball runs — Policy **U** may still need **parity heuristics** (or accept **rotation drift** until next trusted broadcast).
2. **Scorer `CORRECTION_BLOCKED` / consensus** (F5240) — decomposition does not fix **blocked commits**; may **amplify** visible churn if scoreboard and SM disagree mid-gap.
3. **Carousel / post-match** — implement **Direction L** guard per **[`state_integrity_f5054_f5240.md`](state_integrity_f5054_f5240.md) §6** in parallel or before relying on decomposition in **S7** contexts.
4. **Telemetry contradictions (`Δballs=0` vs commentary)** — [`state_integrity_f5054_f5240.md`](state_integrity_f5054_f5240.md) §2.4; decomposition should **normalize logging** so **`[BALL EVENT]`** reflects **`balls_skipped`** consistently.
5. **Product:** Does UI want **one frame / N balls** or **N websocket messages**? drives animation and load.

---

## §8 Stop-condition crosswalk

| Condition | Triggered? |
|-----------|------------|
| **S1** Pattern V dominates → truncate Q2–Q4 | **No** |
| **S2** Layer 2 per-ball blowup unacceptable | **Mitigate with absorbed enqueue skip** — flag resolved |
| **S3** No consumer tolerates policies | **No** — Policy **U** + placeholders aligns with existing **`ThisOverManager`** **`?`** path |
| **S4** F5054 memo concludes **W/V** and supersedes B | **No** — memo recommends **B + carousel guard** |
