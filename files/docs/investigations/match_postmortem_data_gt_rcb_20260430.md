# Match post-mortem — diagnostic dump (GT vs RCB, IPL 2026, 2026-04-30)

Autonomous overnight capture for offline analysis. **Investigation only** (no production code changes).  

**Companion machine-readable metrics:** [`match_postmortem_data_gt_rcb_20260430.json`](match_postmortem_data_gt_rcb_20260430.json)

---

## 1. File inventory (paths, sizes, line counts, time ranges)

| Artifact | Path | Bytes (approx) | Lines | Wall-clock span (log brackets) | Notes |
|----------|------|----------------:|------:|--------------------------------|-------|
| Pipeline tee (primary) | `logs/pipeline-2026-04-30-gt-rcb-live.log` | ~5.7 MB | 37,775 | **19:50:35 → 22:17:45** | **Does not reach scheduled session end (~22:45 local per IPL sheet) — see stop-condition S1.** |
| Machine service | `files/logs/machine-1-2026-04-30.log` | ~10.4 MB | 85,616 | First bracket **08:55:58** → **22:17:29** | Morning traffic present; **`[DWR]` lines omit leading wall-clock** — evening-only DWR subset not mechanically isolated (S2). |
| Machine symlink/copy (root) | `logs/machine-1-2026-04-30.log` | ~168 KB | (small) | morning-oriented snapshot | **Stale vs `files/logs/` live sink** per earlier ops notes — prefer `files/logs/`. |
| Live observation rollup (replay snapshot) | `files/logs/live_observation_replay_20260430T163252Z.md` | ~15 KB | 249 | Monitor UTC **16:32** | **Stale vs evening match** — captured mid-afternoon replay only; SM/DWR counts therein include **full-day machine noise**. Do **not** treat as final-match rollup. |
| Deliveries folder | `logs/deliveries/<session>/` | — | — | — | **Not enumerated** (workspace `.cursorignore` / automation scope); assume absent unless operator attaches session dir. |
| Analyzer / element-checker / parity / ui (2026-04-30 evening) | — | — | — | — | **No dedicated `*-2026-04-30-gt-rcb*` analyzer / parity / element-checker logs** located beside pipeline tee; nearest artifacts remain older dates (Apr 29 MI–SRH, Apr 28 PBKS–RR, etc.). |

**Live analysis window (this document unless stated otherwise):** pipeline lines whose bracket timestamp satisfies **`HH:MM:SS ≥ 19:50:00`** on **2026-04-30** (**34,751** lines).

---

## 2. Match identification

| Field | Value |
|-------|--------|
| Competition | IPL 2026 |
| Fixture | Match **42**, GT vs RCB |
| Venue (broadcast + public listings) | **Narendra Modi Stadium, Ahmedabad** |
| Pipeline `MATCH_INFO` | `MATCH 42` |
| Toss / batting order | GT elected **field first** (public scorecard listings); pipeline confirms **RCB innings 1** then **GT chase**. |

---

## 3. Pipeline state integrity (user observations A–E vs log evidence)

### A. Phantom deliveries across innings break (118 vs 120 narrative)

**Log-evidence summary**

- Formal innings closure telemetry (not `[DELIVERY ENQUEUED]`):  
  - **`[21:19:38 F2125]`** — `[INNINGS-BREAK]` Innings **1** end detected `(overs=19.2 wickets=10)` — **pipeline line ~23683**.  
  - **`[21:25:06 F2275]`** — `[INNINGS-TRANSITION-TELEMETRY]` `pre_state=155/10 (19.2)` `target=156` — **line ~24563**.  
  - **`[21:25:06 F2275 BOARD]`** — `[INNINGS] Set to 2 … All trackers reset.` — **line ~24564**.
- **`[DELIVERY ENQUEUED]` sequence:**  
  - Last pre-gap enqueue (innings **1** traffic): **`[21:19:38 F2125]` `dnum=84` `evt=WICKET`** — **line 23696**.  
  - Next enqueue after gap: **`[21:28:01 F2347]` `dnum=85` `evt=DOT`** — **line 25341**.  
  - **No `[DELIVERY ENQUEUED]` lines occur between `21:19:38` and `21:28:01`** in this tee log.

**Interpretation**

- The specific **“+2 phantom deliveries before innings reset”** claim is **not reproduced as extra `[DELIVERY ENQUEUED]` rows** straddling the transition — the enqueue stream shows a **quiet gap** followed by **`dnum` continuity** (84→85).  
- Without a dedicated **legal-ball counter** column in grep extracts, **“118 vs 120 legal balls”** remains **user-reported / pending dedicated scorer-state replay** (**stop-condition S3** partial).

### B. Phantom wide at chase **0.1→0.2**

**Evidence**

- **`ball_event_extra=wide`** occurrences in pipeline (**live window**): **6** total (`grep "ball_event_extra=wide"`).
- Early chase example (wide path encoded as **`ball_event=EXTRA`**, **`ball_event_extra=wide`**):  
  - **`[21:37:26 F2683]`** — `AFTER_innings=2`, `ball_event_over=0.2`, partnership progression consistent with extras ladder (`AFTER_this_over` includes `Wd`).  
  - Additional clustered wides at **`[21:38:09 F2694]`** (`Wd+3`, runs=4 on EXTRA).

**Interpretation**

- Wides are **`EXTRA` + `wide`**, not `ball_event=WIDE`. Multiple extras events at **`0.2`** reflect **`Wd` / `Wd+3`** sequencing — requires broadcast reconciliation to classify **fabrication vs legitimate stacked wides/no-ball ladders** (**honest ambiguity**).

### C. Batter stat swapping / WS projection instability

**Evidence**

- **`[WS-SLOT-INVARIANT]`** (**live ≥19:50**): **345** fires (**≈2.34/min** vs **8830 s** wall span). Early cluster samples duplicate **`Rajat Patidar`** (**frames ~F383–F388**, see JSON samples). Around innings transition, **`Josh Hazlewood`** duplicate-slot warnings appear (rollup excerpt in stale `live_observation_replay_*.md`).
- **`[BATTERS-INVARIANT]`** in live window: **79×**, **all parsed `rule=C`** (`striker_non_collision` / admission-window semantics). **No `rule=A` fires counted** in **`≥19:50`** slice — differs from narratives expecting **`rule=A`** swap admits (**possible phase mismatch or telemetry routing change**).

**Interpretation**

- **Scoreboard-vs-slot divergence** is visible via **`WS-SLOT-INVARIANT`** density + **`FRAME_POISONED`**/`scout=STRIP` contradictions (see §10). Full SM-vs-WS matrix exceeds grep-only capture — **needs analyzer replay**.

### D. Over jump (**~3.x → ~5.x**) and “lost deliveries”

**Evidence**

- Monotone **`AFTER_score=(overs)`** sampling detects first major discontinuity:  
  - **Before:** **`[22:00:50 F3293]`** shows **`AFTER_score=49-1(3.5)`** while **`scout=STRIP`** advertises **`GT 57-1 (4.5)`** + **`FRAME_POISONED:57`** — **pipeline line 33709**.  
  - **After:** **`[22:02:41 F3346]`** **`AFTER_score=57-2(5.0)`**, **`ball_event=MULTI_BALL`** — **line 34017**.  
  - **Elapsed wall:** **111 s** between bracket timestamps.

**Interpretation**

- The pipeline **did not silently idle**: frames advanced **F3293→F3346** inside ~**111 s**. The discontinuity aligns with **`MULTI_BALL`** handling + poisoned strip recovery — **lost intermediate `ball_event_over` granularity** should be reconstructed from **`[DELIVERY ENQUEUED]`**, **`[THIS-OVER]`**, and **`MULTI_BALL`** spans (not fully tabulated here).

### E. Processing rate degradation

**Evidence**

- Approximate **`Δframes/Δwall`** (**live window**): **~3725 frames / 8830 s → ~0.422 Hz** average (**JSON `frame_time_span`**).
- Scout latency (**`[SCOUT] <phase> <N>ms`**, live window): **p50 ~830 ms**, **p95 ~1659 ms**, **mean ~943 ms** across **1310** parsed lines — **well below** shadow-eval narrative citing **~3.1–3.3 s** means (**different instrumentation path / subset**).

**Interpretation**

- End-to-end frame throughput is modest (~**0.4 fps** average) — operator perception of **severe degradation** is **directionally consistent**, but root causes split across **vision stack**, **`MULTI_BALL`**, **`FRAME_POISONED` storms**, and **Groq/Pass-2 stalls** (§6).

---

## 4. Today’s shipments validation (live ≥19:50)

Quantities mirror **`match_postmortem_data_gt_rcb_20260430.json`** → `telemetry_counts_live_ge_1950`.

| Shipment | Metric | Count | Verdict |
|----------|--------|------:|---------|
| **P0-A** | **`[SM-INNINGS-2-RESET]`** | **0** | **Gap / tag miss** — innings change evidenced instead by **`[INNINGS-TRANSITION-TELEMETRY]`** + **`[INNINGS]` Board**. Expected telemetry hook **absent** on this build/log. |
| **P0-B** | **`overs_tracker.reset`** substring | **0** | **Unknown from tee** — reset may be logged under different tokens only on BOARD/SM channels. |
| **P0-C** | **`[TEAM-ATTRIBUTION-POISON-RATE]`** | **13** | Telemetry **present** — rolling-window rates peak ~**0.53** vs threshold **0.56** near **`inn_break_pending=True`** frames (**e.g.** **F2850**, **F2880** lines in JSON samples). **Cannot validate fixed 8.4% expectation** without denominator definition from code. |
| **Thread 7 Fix 1** | **`[STRIPS-ROW-MISALIGNED]` / `[STRIP-ROWS-MISALIGNED]`** | **119** | Active — recovery **`popped=batters`** pattern dominates samples (**§10**). |
| **Thread 7 Fix 2** | **`CAM-GRAPHIC-FAST-PATH-*`** READ / REJECT / NOOP | **46 / 39 / 2** | Telemetry present — **`G8_cooldown_dup`** dominates rejects (samples JSON). |
| **Lever 1 PR1–PR4 proxy** | **`[WS-SLOT-INVARIANT]`** | **345** (**~2.34/min**) | **Not** a reduction vs MI–SRH **122** hits under **looser `≥19:44:25`** heuristic on Apr 29 log — comparison **biased by duration + phase**. **Cannot substantiate 73–87% reduction claim** from these two scalars alone (**sample bias**, **S5 caution**). |
| **PR3 dedup** | **`[SM-W8-DISMISSED-GUARD]`** | **0** | **≤6 expectation trivially satisfied** — suppression vs non-emission **undistinguished** here. |
| **Harness extraction** | **[DELIVERY ENQUEUED]** vs **[THIS-OVER]** parity | Not recomputed end-to-end | **Deferred** — stale rollup markdown contains exploratory per-over table tied to **replay**, not sealed evening tee. |

**`[STRIKER-SM-CUTOVER]` reasons (live window):**

| Reason | Count |
|--------|------:|
| `over-end` | 40 |
| `broadcast-indicator` | 3 |
| `broadcast-indicator-swap` | 2 |
| `active-slot-dedup` | 3 |

---

## 5. Delivery extraction (#1a ball detector + #1b DWR)

### #1a `[DELIVERY ENQUEUED]` / DETAIL `ball_event`

| Metric | Innings **1** (guess) | Innings **2** | Notes |
|--------|----------------------:|--------------:|-------|
| **`[DELIVERY ENQUEUED]`** rows | **86** | **34** | **1** row lacked backwards-parsed innings (**null**) |
| DETAIL **`ball_event`≠ EM_DASH** (counts) | see JSON `ball_event_on_detail_lines_per_innings` | … | Rough proxies — multiple **`ball_event=` tokens / line possible** |

**`ball_event_extra=wide`:** **6** lines (**§3.B**).

### #1b DWR (`files/logs/machine-1-2026-04-30.log`)

Parsed **`[DWR] window #… source=… frames=…`** rows (**127** typed):

| Source | Windows | Share of typed | Frames median / mean / max |
|--------|--------:|---------------:|----------------------------|
| `retrospective_span` | **5** | **3.94%** | **56 / 57.0 / 61** |
| `fallback_pre_event_window` | **122** | **96.06%** | **161 / 160.6 / 169** |

**Stale-span rejections (`rejecting stale span` substring):** **23** lines.  

**SKIP telemetry:** not categorized finely — **`phantom/overlap`** splits require structured grep templates beyond overnight capture.

---

## 6. Operational health

| Category | Live-window signal | Notes |
|----------|-------------------|-------|
| JSON parse failures (`JSON parse failed`) | **3** | Examples **F128**, **F912**, **F997** — typical conversational preamble leakage (`telemetry_samples`). |
| Extract connection errors | **1** (**F531**) | Explicit **`Connection error.`** |
| Pass-2 background failures | **`Pass-2` substring lines:** **5** total | **1** shows **`Error code: 524`** Cloudflare/Groq timeout payload (**F24** enrichment window per sample trace). |
| Frame poison churn | **`FRAME_POISONED` substring:** **444** | Correlate with strip trust / scout OCR divergence. |

---

## 7. Scout production behavior (live ≥19:50)

**`cam=` distribution on `[SCOUT]` lines:** see JSON `scout_cam_on_scout_lines` — top buckets **`closeup`**, **`bowlers_end`**, **`graphic`**, **`ad`**.

**Latency (`[SCOUT] … Nms`):** median **~830 ms**, **p95 ~1.66 s**, **mean ~0.94 s** (**subset**, not shadow-eval parity harness).

**Cross-reference DWR:** retrospective windows (**median ~56 frames**) imply shorter bowlers-end spans; fallback windows (**~161 frames**) imply heavier buffering — aligns with **`no_bowlers_end_span`** reasons on sampled `[DWR]` lines.

---

## 8. Final pipeline state vs public ground truth

### Pipeline final STATE (tee truncation)

Last **`DETAIL`** row (**live-filtered**) cites **`AFTER_score=92-3(7.3)`**, **`AFTER_innings=2`**, **`[22:17:30 F3720]`** (**line ~37754**) — yet **`scout=STRIP`** shows unrelated **`GT 20-0 (2.5)`** poison (**honest contradiction**).

Last sampled **`[DELIVERY ENQUEUED]`** rows extend through **`dnum=118` `evt=WICKET`** near **`[22:17:12 F3712]`**.

### Public snapshot (not final-at-cutoff)

Third-party live pages (e.g. ESPNcricinfo live blob ingested via web search) show **`GT 95/3 (8.2 ov), T:156`** with **Buttler dismissed `7.3`** — **directionally consistent** with pipeline **`92/3 @7.3`** ballpark **before** log halt but **not** a sealed official PDF scorecard verification (**S4**).

**Comparison checklist**

| Check | Result |
|-------|--------|
| Score proximity (~92 vs ~95 @ similar wicket/overs) | **Loosely aligned — needs sealed card** |
| Innings progression | Pipeline stopped mid-chase — **cannot validate chase completion** |
| Ball-for-ball legality | **Not asserted** |

Canonical links for human follow-up:

- https://www.espncricinfo.com/series/ipl-2026-1510719/gujarat-titans-vs-royal-challengers-bengaluru-42nd-match-1529285/full-scorecard  
- https://www.ipl.com/matches/indian-premier-league-129908/gujarat-titans-vs-royal-challengers-bengaluru-95999  

---

## 9. Reframing, correlations, priorities

### Severity snapshot

| Theme | Severity | Notes |
|-------|----------|-------|
| **Tee truncation / premature halt** | **High** | Match log ends **~22:17** vs scheduled night session — blocks definitive validation (**S1**). |
| **State integrity (strip poison vs AFTER_*)** | **High** | Repeated **`FRAME_POISONED`** + contradictory **`scout=STRIP`** vs **`AFTER_score`**. |
| **Lever / innings telemetry drift (`SM-INNINGS-2-RESET` absent)** | **Medium–High** | Monitoring hooks expected by charter **missing** — alternate tokens confirm transition. |
| **DWR retrospective under-fire (~4%)** | **Medium** | Structural cost gap (**~56 vs ~161 frames**) confirms fallback-heavy assembly. |
| **Operational JSON / timeouts** | **Low–Medium** | Low absolute counts but clustered risk for enrichment latency. |

### Correlation hypothesis (non-final)

**Strip poisoning + MULTI_BALL + graphic/fast-path rejects** appear **co-active** during chase mid-overs — plausible **single OCR/graphic ambiguity root** with **multiple symptom tags**, but **not proven** overnight.

### Priority ranking (next session)

1. **Seal full-session tee + correlate analyzer pass** on **`logs/pipeline-*-gt-rcb-live.log`** continuation — unblock Phases **7–8**.  
2. **State integrity replay** focusing **`AFTER_*` vs `scout`** divergence matrix & **`MULTI_BALL` bridges** (**§3.D** window **F3293–F3346** first).  
3. **Instrumentation audit:** **`[SM-INNINGS-2-RESET]` emission vs `[INNINGS-TRANSITION-TELEMETRY]`** parity (**P0-A gap**).  
4. **Lever 1 rate diagnosis** — rebuild comparable innings-phase windows vs MI–SRH before declaring regression (**bias caution**).  
5. **Scout `V6d/V6e` disposition** — remain **deferred** behind items **1–4** per backlog posture.

---

## 10. Specific extracts (verbatim snippets)

### Innings transition triple

```
[21:19:38 F2125 TEST] INFO:   [INNINGS-BREAK] Innings 1 end detected (all_out_10: overs=19.2 wickets=10) ...
[21:25:06 F2275 TEST] INFO: [INNINGS-TRANSITION-TELEMETRY] source=set_innings_2 ... pre_state=155/10 (19.2) ... target=156
[21:25:06 F2275 BOARD] INFO: [INNINGS] Set to 2. Target: 156. All trackers reset.
```

### `[DELIVERY ENQUEUED]` boundary

```
22660:[21:15:18 F1963 TEST] INFO:   [DELIVERY ENQUEUED] dnum=83 evt=WICKET ...
23696:[21:19:38 F2125 TEST] INFO:   [DELIVERY ENQUEUED] dnum=84 evt=WICKET ...
25341:[21:28:01 F2347 TEST] INFO:   [DELIVERY ENQUEUED] dnum=85 evt=DOT ...
25452:[21:28:19 F2352 TEST] INFO:   [DELIVERY ENQUEUED] dnum=86 evt=DOT ...
```

### Over discontinuity anchor (**lines 33709 → 34017**)

Abbreviated — full rows on disk at cited **line numbers**:

```
33709:[22:00:50 F3293 ... ] scout=STRIP: GT 57-1 (4.5) ... FRAME_POISONED:57 ... AFTER_score=49-1(3.5)
34017:[22:02:41 F3346 ... ] AFTER_score=57-2(5.0) ... ball_event=MULTI_BALL ...
```

### Early chase wide (**EXTRA + wide**)

```
[21:37:26 F2683 ... ] AFTER_innings=2 ... ball_event=EXTRA ... ball_event_extra=wide ... ball_event_over=0.2
```

---

## 11. Open questions (human / tool follow-up)

1. **Recover continuation past line ~37775** — confirm pipeline crash vs intentional shutdown (**S6** if silent crash).  
2. **`SM-INNINGS-2-RESET` routing:** verify feature flag / logging tier explaining **zero hits**.  
3. **`rule=A` BATTERS expectation mismatch:** reconcile Phase **2 enablement vs telemetry**.  
4. **Legal-ball ledger extraction:** settle **`118 vs 120`** claim via scorer internals / analyzer dump.  
5. **Machine-1 timestamp alignment:** unify `[DWR]` wall-clock vs pipeline tee for night-only aggregates.

---

### Stop-condition ledger

| ID | Trigger | Resolution |
|----|---------|------------|
| **S1** | Tee truncated before nominal match end | Documented — analysis conditional on **`≤22:17:45`**. |
| **S2** | Machine `[DWR]` lacks timestamps | Used **full-day** typed-window stats — caveat embedded. |
| **S3** | User phantom-ball narrative vs enqueue trace | Partial — **no stray `[DELIVERY ENQUEUED]`**, ledger still **unknown**. |
| **S4** | Ground truth paywall / live-only | Partial — cite links + ESPN approximate snapshot only. |
| **S5** | Extra anomalies | **`MULTI_BALL`**, **`FRAME_POISONED`**, **`AFTER`/scout divergence**, **`Pass-2 524`** documented. |

---

*Generated in-repo from sealed artifacts on disk — reproducible counts in JSON companion.*
