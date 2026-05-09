# MULTI_BALL absorbed-ball Layer 2 recovery — investigation & design memo

**Phase:** Design / architecture forensics — **implementation deferred.**

**Depends on:** [`multi_ball_decomposition_design.md`](multi_ball_decomposition_design.md), shipped decomposition ([`multi_ball_decomposition_fix_implementation.md`](multi_ball_decomposition_fix_implementation.md)), [`score_event_coverage_audit.md`](score_event_coverage_audit.md) posture, [`match_postmortem_data_gt_rcb_20260430.md`](match_postmortem_data_gt_rcb_20260430.md) §4–5.

**Primary tee (GT vs RCB, 2026-04-30):** `logs/pipeline-2026-04-30-gt-rcb-live.log`  

**Code anchors:** [`files/ball_analyzer.py`](../../ball_analyzer.py), [`files/delivery_window_recorder.py`](../../delivery_window_recorder.py), [`files/test_pipeline.py`](../../test_pipeline.py), [`files/score_manager.py`](../../score_manager.py).

---

## §1 Executive summary — verdict and recommendation

**Verdict:** **Defer** a general-purpose “retro Layer 2 for every absorbed ball in a `MULTI_BALL` gap” path **under current buffering**. The dominant blocker is **not** the D2 enqueue skip alone; it is that **live rolling captures do not retain enough wall-clock history** to cover typical scoreboard gaps (`MULTI_BALL` bridges), combined with **`ABSORBED_LEGAL`** traffic never producing persisted `delivery_window.mp4` / `layer2.json` rows for offline gap archaeology.

**POISON-RECAL** resets **score** state (`ScoreManager.full_reset`), but **does not** clear **`BallAnalyzer`’s** rolling frame deques — so “recovery impossible because RECAL wipes the buffer” is **incorrect**. Recovery is still **mostly impossible for long gaps** because **deque eviction by time/size** overtakes wipe semantics.

**Stop-condition synthesis**

| Gate | Applies? |
|------|----------|
| **S1** — raw buffer \(\ll\) typical MULTI bridges | **Yes** — `FRAME_BUFFER_MAXLEN = 1200` with architecture assumption **~20 fps** ⇒ **order ~60 s** of live frames (see §2); **six** examined MULTI spans include **≥81 s wall** gap to last enqueue in **five** cases and **355 s / 1070 s** in the worst chase/post-match spans. Full-gap recovery **without archival extension** fails. |
| **S2** — all six coincide with RECAL wiping buffer | **No** — RECAL **does not** wipe `BallAnalyzer` buffers (**§2.2**). Two MOTs **do** align with **`[POISON-RECAL]`** in forensic memos (**F3296→F3346**, **F5054→F5240**) but that is orthogonal to deque clearing. |
| **S3** — \(\lt 10%\) usable Layer 2 per attempt even if framed | **Indeterminate until frames exist**, but tying recovery to **`retrospective_span`-class** scarcity (~**3.94%** of typed DWR windows, postmortem §4) is the **risk anchor** absent structural relief (explicit gap window + richer archive). Predicting **30–50% hit rate** remains **speculative**. |

**Recommendation tier:** **Defer** — **recover-after-buffer-or-archival-extension** if product later prioritizes absorbed detail. Accept the **honest absorbed-ball ceiling** (Policy U placeholders) near-term; keep this memo as the **narrow recovery** spec thread when extended retention lands. Does **not** reopen D2’s **common-case** correctness (explicitly out of scope per task brief).

---

## §2 Architecture forensics

### §2.1 Raw frame buffer (A1)

| Item | Evidence |
|------|----------|
| **Mechanism** | `BallAnalyzer._frame_buffer`: `deque(maxlen=FRAME_BUFFER_MAXLEN)` — **bounded ring**, continuous append from `_capture_loop`. |
| **Capacity** | `FRAME_BUFFER_MAXLEN = 1200` (`ball_analyzer.py`). |
| **Nominal duration** | `DeliveryWindowRecorder` module doc states **continuous capture “~20 fps frames → rolling raw frame buffer.”** ⇒ **\(1200 / 20 \approx 60\text{ s}\)** of retained **live capture** **if** Quartz capture meets ~20 Hz. Effective seconds scale inversely with real capture FPS. |
| **MULTI bridge coverage** | **No.** GT–RCB gaps from **last `[DELIVERY ENQUEUED]`** to **`MULTI_BALL` commentary line** measured **≥81–1070 s** wall clock (**§3**): **minutes** vs **≤~1 minute** deque. Frames from the **start** of absorbed gaps have **rolled off** before the consolidating event fires (unless ingest halts dramatically). |

```131:146:files/ball_analyzer.py
FRAME_BUFFER_MAXLEN = 1200

TAGGED_BUFFER_RETENTION_S = 90.0
```

```339:345:files/ball_analyzer.py
        self._frame_buffer: collections.deque[tuple[float, np.ndarray]] = (
            collections.deque(maxlen=FRAME_BUFFER_MAXLEN))
```

### §2.2 Scout tagged buffer and POISON / RECAL (A2)

| Item | Evidence |
|------|----------|
| **Tagged Scout buffer** | `record_tagged_frame` keeps **`bowlers_end` / `side_on` / `replay`** tuples; rolling retention **`TAGGED_BUFFER_RETENTION_S = 90`** seconds (popleft below cutoff); separate **`deque(maxlen=240)`** (~10 minutes at Scout’s ~0.4 Hz headline cadence — **sparse**, not contiguous video history). |
| **`ScoreManager.full_reset`** | Clears **`ScoreManager`** surface + cold-start machine — **does not** touch **`BallAnalyzer._frame_buffer`**. **`grep` for `buffer.*clear` / `raw.*reset` over `score_manager.py` vs `BallAnalyzer`** — **no shared reset path.** |
| **Implication for A2 hypothesis** | **“RECAL wipes the raw frame buffer” is false.** The practical loss mode is **`maxlen`/time eviction** plus **cold-start ingest gaps** (`FRAME_POISONED`, graphic skips): you often **were not buffering useful wide shots contiguously**, not merely “zeroed by reset.” |

```563:575:files/ball_analyzer.py
    def _frame_source(self,
                      start_ts: float,
                      end_ts: float,
                      ) -> list[tuple[float, np.ndarray]]:
        """Slice the rolling capture buffer by absolute timestamps.
...
        snap = list(self._frame_buffer)
        return [(ts, fr) for ts, fr in snap
                if start_ts <= ts <= end_ts]
```

### §2.3 Existing `retrospective_span` path (A3)

| Question | Answer |
|----------|--------|
| **Where** | **`DeliveryWindowRecorder.classify_for_score_event`** (`delivery_window_recorder.py`). **`_find_span`** walks **`bowlers_end` + action `frame_phase`** inside **`[event_ts - LOOKBACK_S, event_ts - POST_EVENT_EXCLUSION_S]`**. |
| **When it fires** | When a **successful** retrospective span is found ⇒ `source="retrospective_span"`. Else **fallback** ⇒ `fallback_pre_event_window` over raw buffer slice (**~10–12 s** lookback tuning + **`MAX_EVENT_DRIFT_S`**). |
| **Why ~3.94% baseline** | **Structural rarity of valid anchors**, not deque clearing on RECAL: action-phase rejects (`anchor_phase_reject`), **`MAX_END_TO_EVENT_GAP_S`** rejecting “stale” spans pointing at prior ball replay, contiguous-gap breaks (`MAX_CONTIGUOUS_GAP_S`), phantom event guard (`MIN_INTER_DELIVERY_S`), duplicate-span overlaps — enumerated in **`delivery_extraction_audit.md`** / postmortem §4 commentary. Fallback therefore dominates (**~96%**). |

**D2 enqueue skip (caller truth):** **`BallAnalyzer.enqueue_delivery_analysis`** itself **does not** branch on **`absorbed`**. **`test_pipeline._layer2_enqueue_blocked_absorbed`** gates **`enqueue_delivery_analysis`** for **`ball_event["absorbed"]`** (Policy U synthetic legs). Architectural effect matches the brief: **those legs never enqueue Layer 2**.

---

## §3 Six GT–RCB MULTI\_BALL gap analysis (B1)

Telemetry source: **grep** **`[BALL ?] MULTI_BALL |`** **`COMMENTARY`** lines in the GT–RCB tee — **six** events.

### §3.1 Event table

Interpretation helpers:

- **Δwalls** ≈ elapsed **pipeline wall clock** **last `[DELIVERY ENQUEUED]` → MULTI commentary** (`time.time`-anchored ingest; **≠** IPL ball clock unless frame rate steady).
- **Δframes** = frame index delta on same telemetry channel (sparse vs wall).
- **`POISON-RECAL` coincidence** scans forensic memos + tee **line-relative** clustering (narrow window for **live** overlaps).
- **`files/logs/deliveries/20260430_195352/`** existence: **confirmed** (**215 `d*` folders**) via filesystem — **individual absorbed legs do not correspond** to subfolders (**D2 skips** ⇒ no per-absorbed **`window_debug.json`** / **`layer2.json`** emitted for synthetic balls).

| # | Frame | Wall (commentary prefix) | Score context (DETAIL excerpt) | Δballs (−legal gap) | Last enqueue Δwall (s) | Δframes enqueue→MULTI | POISON‑RECAL in window¹ | Persisted gap window on disk² |
|--:|-------|--------------------------|-------------------------------|---------------------|-------------------------|------------------------|-------------------------|-------------------------------|
| 1 | F273 | 20:05:23 | **RCB** `68/2 (6.3)` | **2** | **81** | **38** | **No** (±500 tee lines idle) | **No** archival for absorbed internals |
| 2 | F986 | 20:34:14 | **RCB** `99/6 (11.3)` | **3** | **104** | **46** | No | No |
| 3 | F3021 | 21:50:50 | **GT** chase `42/1 (3.0)` | **2** | **76** | **27** | **Upstream** **21:43:18 `F2827`** (~**7½ min** earlier)³ | No |
| 4 | F3155 | 21:55:49 | **GT** `49/1 (3.4)` | **2** | **93** | **21** | No narrow | No |
| 5 | F3346 | 22:02:41 | **GT** jump `57/2 (5.0)` | **7** | **355** | **170** | **YES** **`F3296`** ([`state_integrity_f3293_f3346.md`](state_integrity_f3293_f3346.md)) | No |
| 6 | F5240 | 23:23:57 | **GT** carousel `MULTI Δballs=25` | **25** cap story | **1070** | **392** | **YES** **`F5054`** ([`state_integrity_f5054_f5240.md`](state_integrity_f5054_f5240.md)) | No |

¹ “In window”: **narrow** `\(\pm\)500** tee-line neighborhood around MULTI; **upstream** flagged separately.  
² **Archived `d*/window_debug.json`** cover **successful** enqueue paths — **skipped absorbed** ⇒ **filesystem cannot answer gap clip presence** retroactively unless session adds **RING buffer export**.  
³ **Interpretation:** **Earlier RECAL ≠ buffer deleted**, but \(\Delta_{\text{wall}}\) exceeds raw ring retention ⇒ **still no contiguous ring coverage** for start-of-gap scouting.

### §3.2 Stop-condition checkpoints

**S1 (short buffer):** All six rows show **Δwall ≥ 76 s** enqueue→MULTI; **five** \(\geq 81\) s **>** **nominal ~60 s** deque horizon. **`FRAME_BUFFER_MAXLEN`** cannot reconstruct **whole** swallowed overs for these observations without **changing retention**.

**S2:** **Not met** — see §2.2.

---

## §4 Recovery feasibility design (implementation sketch) (B2–B3)

Conditional on **having** timestamps + frames spanning **candidate** deliveries:

### §4.1 Proposed retrospective enqueue path

1. **Hook:** **`MULTI_BALL` consolidated score event boundary** (`ScoreManager`-visible; post-decomposition, optionally **parent** **`MULTI_BALL`** + **`ABSORBED_LEGAL`** stream).
2. **Enumerate gap:** wall-clock interval from **last trustworthy score-event time** (or synthesized gap floor from **Δballs** × nominal **inter-delivery**) through **`MULTI` `event_ts`.** Must extend **beyond** **`LOOKBACK_S=25`** for long bridges — **`_find_span` as-is insufficient** unless buffer/archive widens search.
3. **Candidate sub-windows:** Mine **`_snapshot_tagged` / Scout phase** spikes (`release`/`flight`/`shot` contiguous runs at **`bowlers_end`**) analogous to **`_find_span`**, iterating **backward** multiple seeds for **Δballs** hypothesized (**risk:** replays ads, close-ups flagged wrong phase).
4. **Enqueue:** For each surviving candidate ⇒ **`enqueue_delivery_analysis`** (or **`DeliveryWindowRecorder.classify_for_score_event`**) annotated **`absorbed_recovery=True`** (**new contract**) skipping `_layer2_enqueue_blocked_absorbed` **only** for those rows (**risk:** commentary must **`certain=False`**, **`not _COMMENTARY_ELIGIBLE_BALL_TYPES`** parity with Policy U).

### §4.2 Risks (explicit)

- **False positives:** ads, wicket replays, “between deliveries” chatter match phases without legal outcomes.
- **Cost:** **\(\mathcal{O}(N_{\text{cand}})\)** Qwen (+Gemini sibling if Layer2 fused) × MULTI occurrences — plausible **~(6 × 3) ≈ 18** extra multimodal calls / match nominal unless heavily gated.
- **Low confidence payloads:** scorer truth for **runs/wickets/order** absent per absorbed segment ⇒ Layer 2 may extract **motion** divorced from authoritative **runs** (**honest ambiguity** aligns with decomposition design).

### §4.3 If raw frames unavailable (present default for long-gap tails)

Recovery **cannot faithfully span** swallowed overs.

**Direction 1:** **Extend `_frame_buffer` maxlen / add second ring** for **`MULTI` / poison-at-risk`** epochs — **bounded MB** formula: `maxlen × frame_bytes` (BGR buffer width clamp in capture loop applies).

**Direction 2:** **Opportunistic snapshots during `POISON-STREAK` pre‑RECAL** (per F3293/F5054 patterns) preserving **JPEG/MPEG ring** keyed by wall clock — survives SM reset.

**Architectural caveat:** **`F5240`-class carousel MULTI\_BALL** (post-mortem **`S7`**) lacks **sporting deliveries** altogether — recovery would **amplify nonsense** unless **gates** classify **presentation phase**.

---

## §5 Cost / value / hit-rate analysis (C1–C3)

### §5.1 Cost model (C1)

Assume **six** **`MULTI_BALL`** anchors / session (GT–RCB observed), **`k=3`** candidates each ⇒ **≤18** extra Layer 2 classifications / match (**upper envelope**).

**Per-call token bill (order of magnitude):** Fireworks’ **published** multimodal tiers include **“Qwen3 VL 30B”**‑class SKUs cited around **\$0.15 input / \$0.60 output** **per million tokens** (`https://fireworks.ai/pricing`, aggregated mirrors). Typical delivery clip ⇒ **few thousand image tokens + short JSON**. **Rough envelope:** **\$0.003–\$0.02 / call USD** excluding egress, Gemini sidecars, retries — verify against **instantiated** SKU in **`layer2_classifier.py`**.

### §5.2 Value model (C2)

| Aspect | Upside |
|--------|-------|
| **UI** | Richer placeholders for absorbed legs (instead of terse **?**) if model returns **validated** kinematics (**line/shot**) **without pretending score truth**. |
| **Commentary / wire** | Only if guarded — Policy U forbids fabricated ball narratives (**decomposition_design.md Q3). |
| **Downstream** | Marginal vs fixing **BED/SM enqueue parity** first (Path 1) — absorbs remain **thin tail** (**~6**/215 balls class narrative). |

### §5.3 Hit-rate prediction vs `retrospective_span` (C3)

| Perspective | Inference |
|-------------|-----------|
| **Naïve extrapolation (~3.94%)** | If each recovery attempted window behaved like **`classify_for_score_event`** on jittery tags ⇒ **<(1 usable detail)** / session — **violates usefulness bar** once engineering + hallucination safeguards counted. |
| **Structural deltas that could elevate** | **Known interval** \(\Delta t\) anchored on **Δballs**, multi-seed **`_find_span`**, permissive LOOKBACK ⇒ **might** outperform single-event hindsight **IF** uncompressed frames existed. GT–RCB **contradicts** frame availability ⇒ **elevated hypothesis untested.** |
| **Working range estimate** | **10–35% plausible** conditioned on (**a**) **Δballs ≤ 2–3**, **(b)** **Δwalls ≤ deque horizon**, **(c)** **`bowlers_end` action-phase density** survives cold-start ⇒ **narrow lane** consistent with **`S3` skepticism globally**. |

---

## §6 Recommendation with reasoning

1. **Do not ship** unconditional absorbed recovery atop today’s deque — **`S1` dominates** (**§3** quantitative gaps vs **§2** `FRAME_BUFFER_MAXLEN`).
2. **Do not postpone** carousel / POISON safeguards waiting for Layer 2 salvage — decomposition memos (**F3293**, **F5054**) demonstrate **truth collapse** regimes where VLM salvage **adds narration debt**.
3. **If product revives salvage:** (**a**) **`Direction 1`** ring extension + telemetry on **RING coverage vs MULTI \(\Delta\)wall**; (**b**) **then** revive **§4 sketch** gated by **`Δballs`**, ingest health, **`absorbed_recovery` flag**.
4. **Verdict bucket:** Matches brief **Defer** + **`recover-after-buffer-extension`** prelude — **not** **Recover-now** (frames / coverage missing), **not** **Architectural-redesign-indicator-as-truth** (orthogonal thread).

---

## §7 Limitations

- **`logs/deliveries/20260430_*`** enumerated via shell only; **`window_debug.json`** sample proves **successful** enqueue artifacts — **cannot** disprove hidden parallel captures absent spec.
- **Wall-clock deltas** inferred from tee brackets — correlate with **`event_ts`** monotonic logs for machine precision next pass.
- **Layer 2 routing** SKU + tokenization must be read from **`layer2_classifier`** before budget sign-off (**§5.1 uses public rate card placeholders**).

---

### Cross-reference checklist

| Doc | Relation |
|-----|----------|
| [`multi_ball_decomposition_design.md`](multi_ball_decomposition_design.md) | Policy **U**, D2 rationale, retrospective baseline warning. |
| [`state_integrity_f3293_f3346.md`](state_integrity_f3293_f3346.md), [`state_integrity_f5054_f5240.md`](state_integrity_f5054_f5240.md) | **POISON-RECAL ∩ MULTI** exemplars (`Δballs=7`, `Δballs=25`). |
| [`match_postmortem_data_gt_rcb_20260430.md`](match_postmortem_data_gt_rcb_20260430.md) | **3.94%** `retrospective_span`; tee truncation caveat. |
