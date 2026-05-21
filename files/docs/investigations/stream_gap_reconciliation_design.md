# B-η — Stream-gap reconciliation design memo

**Status.** Investigation. NO CODE. Pause for user review at the end of §6.
**Date.** 2026-05-21
**Author.** Claude Code (investigation session post-DCKKR replay)
**Session under investigation.** `validate_dckkr_20260521_070545`
**Trace.** `logs/trace/validate_dckkr_20260521_070545.jsonl` (341 records)
**Brief.** `files/docs/investigations/dckkr_20260521_cc_investigation_brief.md`
**Observations.** `files/docs/investigations/dckkr_20260521_session_observations.md` Issues 2/3/9
**Standing audit.** `sm_as_orchestrator_design.md` §7.2 (7 gates)

---

## 1. Empirical evidence — what actually happened between f300 and f356

Last known-good committed state: **f300 — SM at DC 45-0, ov=4.4, KL Rahul on strike, Pathum non-striker, Tyagi bowling.** Ground truth per broadcast: same.

The next 56 frames decompose into four phases:

### 1.1 Pre-anchor: f301–f303 — Scout produced three unusable frames

| Frame | Scout text fragment | Extractor outcome | Decision tags |
|---|---|---|---|
| f301 | `DC 45-0 (4.4) \| PATHUM RAHUL > 26 16 \| 19 12 KKR 8` | score=null overs=null (Scout 429 retry; UDP-STREAM-FROZEN; cadence_ms=9345) | `SCOUT-RETRY-IN-CALL-QUEUED`, `UDP-STREAM-FROZEN`, `SCOUT-RETRY-IN-CALL-SUCCESS` |
| f302 | `DC 49-0 4.5 PATHUM 26 16 RAHUL 23 13 RUN-RATE 10.14 FOURS 6 SIXES 2 DC 7 STANDINGS KKR 8` | score=null overs=null (`STANDINGS-ROW-GATE` stripped fields; `FS-REJECT` rejected impossible 6/2 fours-sixes) | `STANDINGS-ROW-GATE`, `FS-REJECT` |
| f303 | `Delhi Capitals 89-4 (10.2)` | extractor proposed s=89 wkts=4 ov=10.2 but poison guard fired | `POISONED`, `POISON-STREAK`, `UDP-STREAM-FROZEN`, `L2` (Qwen unparseable) |

**At end of f303, SM still at `DC 45-0 (4.4)`. Three Scout reads consumed; no commit.** Of note: f302's Scout text contained the *actually correct* live score `49-0 (4.5)`, but the leaderboard/STANDINGS keyword in the same frame triggered the row-gate that stripped score/overs fields.

### 1.2 The bad anchor: f304 — Scout overlay frame accepted

f304 Scout text (truncated to 160 chars):

> `VISIBLE_TEXT: Delhi Capitals 54-0 (6.3) | extras=0 | this_over=●●●●● | PANT 29(21) | WARD 18(20) | SHAMI 2-13 (1) ST...`

Per the DC squad: **PANT** (Rishabh), **WARD** (not in DC's playing XI for this match per the squad-resolver fuzzy keys), **SHAMI** (Mohammed, KKR's bowler in other contexts but not DC). None of these match the post-f300 SM lineup (Pathum/KL Rahul + Tyagi). This is an overlay frame, not a live scoreboard.

Extractor decisions at f304:
- `extractor.score=54, extractor.wickets=0, extractor.match_overs="6.3"` — score/overs survived
- `extractor.batters=[]` — squad resolver rejected PANT/WARD as not-in-squad (correctly)
- `extractor.bowler={}` — SHAMI rejected (correctly)

**The score/overs propagated despite batter/bowler tokens being thrown out by the squad gate.** Frame trust was decided on the score+overs subset; the inconsistency with batter/bowler names did not cause rejection.

Subsequent commit path: SM committed `s=54, wkts=0, ov=6.3` between f304 and f318 (by f318, `GRAPHIC-FILTER-POISON` log line cites `tracker_score=54 tracker_overs=6.3`). The decomposer output 10 ABSORBED_LEGAL events; the per-ball bowler credits drained at **f356** as 10 × `ABSORBED-LEGAL-BOWLER-QUEUED` (bowler_name=None at commit time, so F-α-queue routed them to Queue B).

### 1.3 Rejected reconciliation: f318, f355, f357, f371

The next ~50 frames carry the **correct broadcast strip** (`DC 49-1 (5)` with `KL RAHUL 23(14) c GREEN b TYAGI`). Each correct frame is rejected by one of:

| Tag | Site | Why it fires post-f304 |
|---|---|---|
| `GRAPHIC-FILTER-POISON` (`score_regression`) | f318 — `strip_score=49 tracker_score=54 Δscore=-5 Δballs=-9` | SM at 54/6.3; broadcast read of 49/5 looks like a backwards graphic |
| `OVERS-JUMP-IMPLAUSIBLE-REJECTED` | f318 — `proposed_overs=6.3 current_overs=4.5 d_overs=1.8 delta_balls=10 d_score=5 streak=1/3 source=warm_consensus` | The 3-streak gate counter resets on each correct read attempt |
| `STRIP-HEAD-JOINT-POP` (`overs_regression:6.3→5.0`) | f355, f357 — dropped score=49 wkts=1 overs=5.0 | Atomic strip-head rejection: all-or-nothing |
| `DIRECT-SM-REJECT` (`d_score_-5_negative`) | f355, f356, f357 — `prev=54/1 (6.3) → card=49/1 (5.0)` | cricket_rules monotonicity invariant |

f318 also wrote `[FOW] Placeholder W1: _unwitnessed`, which is why subsequent frames show `tracker_score=54 tracker_wickets=1` — the BED shadow detector inferred a wicket but the FOW entry is a placeholder; no real dismissal landed.

### 1.4 Downstream B-β cascade — frames 371, 521, 636 (the brief's "predicted-flip violation")

| Frame | Scout extractor | What SM did | B-β verdict |
|---|---|---|---|
| 371 | s=null wkts=null (graphic frame; BED emitted WICKET) | `WICKET-ATTRIB: Pathum Nissanka` then `APPLY-KNOWN-WICKET-IDEMPOTENT-NO-OP: FOW W1 already recorded as None — skipping` | **Miss**: BED fired but dispatch was no-op because the f318 placeholder W1 occupied the slot |
| 521 | s=74 wkts=2 ov=8.0 bowler=GREEN | DIRECT path: score 53→74 (+21 jump), wickets 1→2 (+1), overs 7.5→8.0 — accepted in one frame | **Miss**: the trace assertion's definition is a Scout-WICKET ball_event without an SM wicket commit at the same frame; the dispatch happened via DIRECT not ball_event |
| 636 | s=80 wkts=3 ov=9.5 bowler=NARINE | DIRECT path: another +6/+1/+0.5 jump; W3 commit fires | **Miss**: same shape as f521 |

The three B-β misses are **not** independent defects. They are the consequence of SM never resyncing to broadcast after f304. By the time real wicket dispatches do land (f521, f636), they land via the DIRECT score-monotonic path with `OVERS-NATURAL-INCREMENT-FAST-CONFIRM` overriding earlier guards — the assertion's "WICKET event at frame X drove wickets→N at frame X" check fails because the dispatch is happening via score/overs DIRECT path, not via Scout's ball_event=WICKET emission.

---

## 2. Cross-fixture verification (§7.2 gate 7)

Survey of `ABSORBED-LEGAL-BOWLER-*` tags across both captured traces:

| Trace | Frame | Gap size | Routing | ts_match | Outcome |
|---|---|---|---|---|---|
| GTRR | f203 | 10 balls | CREDITED (bowler known: Deshpande) | GT 25-0 (3.1) | **Correct** — broadcast genuinely had a graphics break; Δscore=5 matched ground truth |
| GTRR | f302 | 2 balls | CREDITED | — | — |
| GTRR | f1106 | 11 balls | CREDITED (bowler known: Jadeja) | GT 136-1 (13.3) | **Correct** — broadcast genuinely had a stats graphic; Δscore=2 matched ground truth |
| GTRR | f1325 | 2 balls | CREDITED | — | — |
| DCKKR | f141 | 2 balls | CREDITED | — | — |
| DCKKR | **f356** | **10 balls** | **QUEUED (bowler_name=None)** | DC 54-1 (6.3) | **Wrong** — anchored to bad-overlay reading |
| DCKKR | f418 | 2 balls | QUEUED | — | — |
| DCKKR | f478 | 2 balls | CREDITED | — | — |
| DCKKR | f578 | 4 balls | QUEUED | — | — |
| DCKKR | f594 | 2 balls | QUEUED | — | — |

**GTRR f201/f202/f203 are instructive.** Same shape as DCKKR f304: Scout reads `25-0 (3.1)` after SM is at `1.3`, Δballs=10, Δscore=5. The `OVERS-JUMP-IMPLAUSIBLE-REJECTED` 3-streak gate fired at f201 (streak=1/3), f202 (streak=2/3), then f203 (streak filled → MULTI_BALL_DECOMPOSED). The reading was correct because the broadcast text consistently said `25-0 P 1.5 > SUDHARSAN GILL` for three frames; SM's squad-locked batters (Sudharsan/Gill) matched.

**DCKKR f304 differs structurally.** No 3-streak buildup is visible — f302 was nulled by STANDINGS-ROW-GATE before reaching the streak counter; f303 was POISONED; f304 was the *first* observation that survived. Either (a) f304's accept path bypassed the 3-streak gate (likely because the streak counter increments only on proposal-shape matches, and f302/f303 didn't share a proposal shape with f304), or (b) the streak gate accepted f304 against later frames f305-f308 that re-affirmed `54-0 (6.3)` from Scout. Either way, the gate that worked on GTRR did not catch DCKKR's bad anchor.

**Gate-7 finding.** Large multi-ball absorption is not inherently broken — GTRR has two successful 10/11-ball absorptions on identical decomposition path. **The defect is not in `_decompose_multi_ball`; it is in the frame-trust gate that decided f304 was a legitimate scoreboard read despite its batter/bowler tokens being out-of-squad.**

---

## 3. Mechanism

The B-η chain has three distinct mechanistic links, each independently load-bearing:

**Link A (frame trust).** At f304, the score+overs subset of the Scout proposal was treated as trustworthy in isolation. Batter/bowler tokens (PANT/WARD/SHAMI) were *separately* rejected by the squad resolver. There is no joint validation that asks "does the proposed score+overs come from the same in-the-clear scoreboard reading as the proposed batters?" — the two subsets enter the pipeline through different gates and can disagree without raising an alarm.

**Link B (gap acceptance threshold).** The 3-streak `OVERS-JUMP-IMPLAUSIBLE-REJECTED` gate exists to gate large gaps, and demonstrably worked on GTRR f201–f203. On DCKKR f304 it either was satisfied by a different mechanism or did not fire. Need instrumentation to know which.

**Link C (no resync path).** Once `s=54 wkts=0/1 ov=6.3` was committed, the GRAPHIC-FILTER-POISON `score_regression` filter + `DIRECT-SM-REJECT d_score_-N_negative` cricket_rules invariant + the deterministic-rotation override at score_manager.py:4295-4325 + the STRIP-HEAD-JOINT-POP overs-regression filter form a *combined absolute lock*. Every subsequent correct broadcast read for ~50 frames (f318 through f521) was rejected by one or more of these four filters. There is no escape valve that says "if N consecutive frames disagree with SM by a consistent (Δscore, Δovers, Δwickets) signed offset, roll the SM state back and re-anchor".

This three-link mechanism is what the brief labelled B-η + B-ι. **B-η = Link A + Link B. B-ι = Link C.** The brief asks me to address B-η first; B-ι is Step 2 of the brief and gets its own memo.

---

## 4. Three candidate fix shapes for B-η

All three fix shapes are investigation-stage. The standing principle: **no code yet**.

### 4.1 Shape α — Joint frame-trust gate at score+overs+batters+bowler

**What it does.** Before accepting a Scout proposal that would produce a multi-ball gap (Δballs ≥ 2), require that the proposed batters subset and proposed bowler subset both pass squad-canonical resolution AND name at least one batter that matches SM's current `bat1_name`/`bat2_name` slot OR is a legitimate new-batter slot per FOW history. If neither condition holds, reject the frame as `STREAM-GAP-BATTER-LINEAGE-MISMATCH` and do not commit the score/overs jump.

**Predicted flip.** At f304, the proposed batters list is `[]` (squad resolver already filtered PANT/WARD). The gate fires; score/overs proposal rejected; SM stays at 45/0/4.4. f318's correct broadcast then enters via the normal path: f318's read of `49-1 (5)` produces Δscore=+4, Δballs=+3 from f300's baseline — within MULTI_BALL_MAX_BALLS (12 per `score_manager.py:320` `COLD_START_MULTI_BALL_MAX_BALLS=3` is cold-start specific; warm-state cap is elsewhere). 3-ball gap decomposes cleanly; wicket dispatches; KL Rahul correctly recorded.

**Cascade closure prediction.** B-η root removed → B-ι (Link C) has no occasion to fire because SM never enters the bad-locked state → Issues 3/4/5/6/7/8/9/10/11 (the entire post-f304 corruption cascade) all collapse to no-op.

### 4.2 Shape β — Strengthen the OVERS-JUMP-IMPLAUSIBLE-REJECTED streak gate

**What it does.** Today the streak gate requires 3 frames of consistent proposal before accepting a large overs jump (GTRR f201/f202/f203 demonstrated the working path). Instrument to find why f304 bypassed it; the bypass is the real fix target. Candidate refinement: require the 3-frame streak to *also* include batter-name agreement with SM's current lineup, not just (score, overs) agreement.

**Predicted flip.** Depends on which bypass mechanism turns out to apply. If the gate fires but is satisfied by f304+f305+f306 (all reading the same bad overlay), the refinement to require batter-name agreement fails the gate at f304 (batters=[] doesn't agree with SM's locked Pathum/KL Rahul) → rejection → same downstream cascade closure as Shape α.

**Difference from Shape α.** Shape α gates large-gap commits at the source (frame-trust). Shape β gates the specific code path (the streak counter) that was supposed to catch this and didn't. Shape α has broader reach; Shape β is the smaller, more targeted change.

### 4.3 Shape γ — Add an explicit `STREAM-GAP-TOO-LARGE-TO-DECOMPOSE` rejection band

**What the brief proposed.** The brief suggested adding a `STREAM-GAP-TOO-LARGE-TO-DECOMPOSE` trace tag at gap-commit time with `delta_balls=10, delta_runs=5, delta_wickets=1` and rejecting via a hard cap.

**Investigation finding.** This shape **does not match the evidence**. GTRR's f203 (10 balls) and f1106 (11 balls) decomposed cleanly with correct ground-truth deltas — they would be wrongly rejected under a hard cap that triggered on Δballs ≥ 10. The hard-cap threshold cannot distinguish "legitimate broadcast graphic skip with consistent batters" from "bad-overlay frame with wrong-squad batters".

**Verdict.** Shape γ is **rejected on gate-7 cross-fixture verification**. A hard `Δballs ≥ N` reject would regress GTRR's working absorptions.

---

## 5. §7.2 seven-gate audit applied to Shapes α + β

### 5.1 Shape α — Joint frame-trust gate

| Gate | Finding |
|---|---|
| 1. Enumerate callers | Producers of multi-ball gaps: `_decompose_multi_ball` at `score_manager.py:4634`, invoked from `_infer_event` at `:4686-4699` via `d_balls > 1`. Consumers of the proposed batters list during commit: `_accept_update`, `_handle_warm` (need full enumeration before code) |
| 2. Classify each caller | Producer: `_infer_event`. Consumers post-acceptance: bowler card writer, batter card writer, FOW writer. The frame-trust gate would sit *between* extractor and `_infer_event` — a new pre-acceptance site |
| 3. Cross-reference adjacent state | The squad resolver already filters batters at `eyes/scoreboard.py:2853+`. Squad-canonical names are commit-gate enforced per `9856fd6`. The joint gate would consume the *same* squad-resolved names; no new resolver. Adjacent state: `self.bat1_name`, `self.bat2_name`, `self.bowler_name`, FOW list. Race ordering: the gate must run after batter resolution but before score/overs commit — a single ordering, no race |
| 4. Equivalence proof | This is an *additive* gate, not a replacement — preconditions are "score+overs proposal arrives". Postcondition for the rejection branch is "no SM state mutation". No collapsing of N callers into 1; no equivalence claim required |
| 5. State variable lifecycle | No new state variables required. The gate is stateless: reads proposed_batters, current SM lineup, FOW history; emits accept/reject |
| 6. Predicted flip with concrete frame numbers | **At f304:** proposed_batters=[] (already squad-resolved to empty), SM lineup={Pathum, KL Rahul}, FOW=[]. Gate fires; score+overs proposal rejected; no commit. **At f318:** proposed_batters from "KL RAHUL 23(14) c GREEN b TYAGI" → squad resolver yields {KL Rahul}; SM lineup={Pathum, KL Rahul}; KL Rahul ∈ lineup → gate passes; wicket dispatches via standard path. **Predicted assertion flips:** `trace_beta_sm_wicket_dispatch` FAIL→PASS (3 misses→0); `trace_alpha_bowler_runs_sum` gap=4→0 or near-0 (downstream cascade closure removes B-θ over-boundary contribution that was inherited from B-η-corrupted state) |
| 7. Cross-fixture verification | **GTRR f201–f203:** proposed_batters={Sudharsan, Gill} after squad resolution; SM lineup={Sudharsan, Gill}; gate passes. Decomposition runs as today. **GTRR f1105–f1106:** proposed_batters=[] (the f1105 raw text is "STANDINGS GT 5 PROJECTED SCORE 227..." — a stats graphic with no batter names); SM lineup={Buttler, Jadeja or similar}. Gate would fire and reject. **Regression risk: GTRR's f1106 11-ball absorption was correct** — under Shape α it would be rejected. So Shape α has a false-positive cost: legitimate graphic-skip absorptions where Scout text contains no batters get rejected. Mitigation: gate condition is "proposed_batters non-empty AND none of them in SM lineup AND none of them in FOW history" — empty proposed_batters can be allowed through, only out-of-lineup batters trigger reject. Re-evaluating: at f304 proposed_batters=[] so this softened gate **does not fire either**. Need to fall back to the bowler-name check or raw-text squad-membership check |

**Gate 7 result: Shape α as stated has a regression risk. The mitigation softening makes it not fire at f304. Need to think harder.** A pre-commit instrumentation pass is required before this shape can be ruled in or out.

### 5.2 Shape β — Strengthen the streak gate

| Gate | Finding |
|---|---|
| 1. Enumerate callers | `OVERS-JUMP-IMPLAUSIBLE-REJECTED` emission site needs to be located (grep target for next pass) |
| 2. Classify each caller | Single emission site is expected (a guard inside `_handle_warm`); needs verification |
| 3. Cross-reference adjacent state | The streak counter resets on each non-matching frame. Adjacent: `OVERS-NATURAL-INCREMENT-FAST-CONFIRM`, `STRIP-HEAD-JOINT-POP`, `DIRECT-SM-REJECT`. Race: streak counter is single-writer (the guard itself); no race |
| 4. Equivalence proof | Refinement is additive (require additional condition); preconditions+postconditions of the current path are preserved |
| 5. State variable lifecycle | One counter (`streak`), incremented on match, reset on mismatch. Refinement adds a second match condition (batter-name agreement) — no new variable |
| 6. Predicted flip | **Cannot predict without first instrumenting f304 to learn why the streak gate didn't fire there.** The brief explicitly says: "If diagnosis can't be confirmed from existing trace data, **add instrumentation first, re-run, then fix**." This is the case here. |
| 7. Cross-fixture verification | GTRR f201–f203 path is the canonical working case. Shape β preserves it. DCKKR would need re-replay after instrumentation |

**Gate 6 result: Shape β requires an instrumentation pass before it can be audited.** This is the standing principle the brief calls out.

---

## 6. Recommendation — instrumentation pass first, no fix code yet

Both Shape α and Shape β fail gate 6 / gate 7 in different ways:
- Shape α has a gate-7 regression-risk path (GTRR f1106) that the softening mitigation does not cleanly resolve at the DCKKR f304 anchor.
- Shape β fails gate 6 because we cannot confirm from existing trace data **why the streak gate did not fire at f304**. The trace shows no `OVERS-JUMP-IMPLAUSIBLE-REJECTED` tag at f304 itself; it appears at f318+ after SM is already poisoned.

**The next action is an instrumentation commit, not a fix commit.** Three trace tags to add:

1. **`FRAME-TRUST-GATE`** at the score+overs accept site — emit `proposed_score`, `proposed_overs`, `proposed_batters_squad_resolved`, `proposed_bowler_squad_resolved`, `sm_bat1`, `sm_bat2`, `sm_bowler`, `decision={accept|reject_lineage|reject_squad|reject_streak}`, `delta_balls`, `delta_runs`, `delta_wickets`. Required for both Shape α and Shape β analysis.
2. **`OVERS-JUMP-STREAK-STATE`** at the streak gate emission site — emit `streak_count`, `streak_baseline_overs`, `streak_baseline_score`, `proposed_overs`, `proposed_score`, `match_mode={score+overs|score+overs+batters}`. Required to answer "why did f304 bypass the gate".
3. **`POISON-STREAK-AT-COMMIT`** at the commit site that takes the gap proposal — emit recent `POISONED` count, recent `STANDINGS-ROW-GATE` count, the (frame_id, raw_text_120) tuples of the last 3 frames preceding the commit. Required to answer "what filtered out f301/f302/f303 and how that interacted with the streak gate".

After re-replay against the DCKKR scout dump (which is captured at `files/logs/deliveries/validate_dckkr_20260521_070545/scout_raw.jsonl` — already on disk; no fresh recording required), the instrumented trace can be used to:
- Confirm which one of {Link A, Link B} is the operative defect (or both)
- Choose between Shape α and Shape β with empirical evidence
- Predict flips with concrete frame numbers (gate 6 satisfied)
- Cross-validate against GTRR re-replay with the same instrumentation (gate 7 satisfied)

### 6.1 What I will NOT do without explicit authorization

- Write any code that mutates SM state, the streak gate, the squad resolver, the score-regression filter, or the deterministic-rotation override
- Open a fix commit before the instrumentation re-replay produces concrete frame-by-frame evidence
- Touch Step 2 (B-ι resync-unlock) or Step 3 (B-θ over-boundary) until Step 1's instrumentation lands and re-replay produces the evidence the brief requires
- Touch the symptom-tier issues (Issues 4, 8, 10, 11) per the brief's §5 ordering

---

## 7. Open questions for user review

1. **Authorize the instrumentation commit?** Three new trace tags as described in §6, additive only, no behavior change. The DCKKR scout_raw.jsonl on disk supports replay without a fresh production session.
2. **Confirm cascade-closure hypothesis priority.** If f304 frame-trust is the cascade root (Shape α / Shape β collapsing both B-η and B-ι), the brief's Step 2 (separate B-ι memo) and Step 3 (B-θ over-boundary) may be cascade-closed by the same fix — saving two design memos. The brief explicitly says this is the cascade-closure pattern §7.2 gate 7 exists to catch. **Should I treat Step 2/Step 3 as gated on the post-instrumentation B-η fix, rather than as parallel investigations?**
3. **Frame-trust gate scope.** Shape α's natural scope reaches beyond multi-ball gaps — every score+overs commit could benefit from joint batter/bowler lineage validation. Is broader scope a future-work line, or in scope for the same fix?

---

## 8. Order-of-operations the brief sets (sanity check) — updated post-instrumentation

Per the brief §"Order of operations (strict)":
- ✅ Step 0: brief read in full
- ✅ Step 0: HANDOFF.md, Architecture_HANDOFF.md, sm_as_orchestrator_design.md §7.2 read
- ✅ Step 0: dckkr_20260521_session_observations.md read
- ✅ Step 0: `git log --oneline derive-not-detect | head -30` executed
- ✅ Step 1: this design memo opened at the prescribed path
- ✅ Step 1 instrumentation authorized and shipped: commit `b49e48b` (tags + scaffold + XI fix) and `e3171eb` (warm-seed mode). Gates held green.
- ⏸ Step 1 Shape α/β commit: paused for user review per §9.5 path decision.
- ⏸ Step 2/3/4/5: blocked on Step 1 user decision per §7.2 cascade-closure pattern.

---

## 9. Empirical findings — post-instrumentation warm-seeded replay (2026-05-21)

Two commits landed: `b49e48b` (instrumentation tags + replay scaffold) and `e3171eb` (warm-seed mode). Layer 1.5 + Layer 2 gates held green on both. Replay run:

```
files/.venv/bin/python files/scripts/replay_captured_scout_trace.py \
    --dump files/logs/deliveries/validate_dckkr_20260521_070545/scout_raw.jsonl \
    --session-id replay_dckkr_20260521_WARMSEEDED \
    --seed-frame 37 --seed-striker "Pathum Nissanka" \
    --seed-non-striker "KL Rahul" --seed-bowler "Anukul Roy"
```

SM advanced from the warm seed through to f300 at `score=45, wickets=0, overs=4.4, striker=KL Rahul, non=Pathum Nissanka` — **identical to the production trace's f300 state**. The seed mechanism works.

### 9.1 What the new tags revealed

Three FRAME-TRUST-GATE / POISON-STREAK-AT-COMMIT firings observed; five OVERS-JUMP-STREAK-STATE rejections, zero acceptances.

**Replay f138** — multi-ball gap commit at over-boundary:

```
delta_balls=2, delta_score=7, delta_wickets=0,
proposed_overs=1.4, current_overs=1.2,
proposed_score=15, current_score=15,
proposed_batters=['PATHUM RAHUL'],            # OCR-concat junk
proposed_bowler='Vaibhav Arora',              # squad-canonical resolved
sm_bat1='Pathum Nissanka', sm_bat2='KL Rahul',
proposed_batter_in_sm_lineup=False,
proposed_batter_in_batting_xi=False,
proposed_bowler_in_bowling_xi=True,           # bowler-axis trust ok
batting_xi_size=11, bowling_xi_size=11
```

**Mixed-signal commit.** Bowler tokens correctly squad-resolved into the locked XI; batter tokens are OCR garbage. Shape α's "reject when proposed_batters not in SM lineup" would reject this commit — but the underlying gap is benign (real over-boundary, real +7 runs). Shape α as stated produces a false positive here.

**Replay f475** — multi-ball gap commit with no batter/bowler signal:

```
delta_balls=2, delta_score=3, delta_wickets=0,
proposed_overs=7.0, current_overs=6.4,
proposed_batters=[], proposed_bowler=null,
sm_bat1='Pathum Nissanka', sm_bat2=null,
sm_bowler='Varun Chakaravarthy',
proposed_batter_in_batting_xi=False,
proposed_bowler_in_bowling_xi=False
```

**Empty-signal commit** — Scout frame at this point had no extractable batter or bowler tokens (graphic frame). Shape α with the §5.1 "non-empty batters" softening does NOT fire; Shape α without softening DOES fire.

**OVERS-JUMP-STREAK-STATE × 5** — all `decision=reject, streak=1/3`:

```
f47:  proposed_overs=10.3, current_overs=0.2, delta_balls=61, delta_score=118
f119: proposed_overs=6.2,  current_overs=1.0, delta_balls=32, delta_score=42
f220: proposed_overs=3.1,  current_overs=3.1, delta_balls=0,  delta_score=125
f262: proposed_overs=4.1,  current_overs=4.0, delta_balls=1,  delta_score=24
f608: proposed_overs=10.5, current_overs=9.0, delta_balls=11, delta_score=18
```

The streak gate **held on every single attempt** (all 5 rejections, no acceptance). The trace-tag pairing means the analyzer can see the per-frame proposal that triggered each rejection.

**POISON-STREAK-AT-COMMIT × 2** at f138, f475 — both showed `overs_jump_streak=0, overs_jump_candidate=null, last_cold_start_verdict_implausible=false`. The gap commits at f138/f475 **bypassed the streak gate entirely** (`delta_balls=2` below the `_BALLS_JUMP_TOLERANCE=3` threshold at `score_manager.py:3035`). This is structural, not random: anything with Δballs ≤ 3 goes directly through `_decompose_multi_ball`.

### 9.2 Critical limitation — f304 anchor not reproduced

The warm-seeded replay processes f303 and f304 from the captured scout_raw, but both are rejected by parse_strip as no-scorecard-data:

```
scout_raw f303: "Delhi Capitals 89-4 (10.2) | "                        # rejected
scout_raw f304: "Delhi Capitals 54-0 (6.3) | extras=0 | this_over=●●●●●
                | PANT 29(21) | WARD 18(20) | SHAMI 2-13 (1) ..."      # rejected
```

The production session at f304 used the LLM-fallback extractor (`EXTRACT-PATH: path=llm t_ms=1085` in the original trace) which the captured-replay's regex-only parse_strip does not invoke. The result: **SM's score stays at 45/4.4 across replay f300–f308, no absorption fires, and `_decompose_multi_ball` is not entered at f304**.

This is the parse_strip-rejection limitation noted in commit `e3171eb`. Without LLM-extractor wiring (or manual synthetic-FrameInput injection at f304), the f304 cascade cannot be observed in re-replay.

### 9.3 What we can and cannot say about Shape α / Shape β

**Cannot say from current evidence:**
- Whether the production session's f304 commit went through the streak gate (likely — Δballs=11 is above the 3-ball threshold) and bypassed it via the 3-frame consensus, OR bypassed the streak gate via a different code path.
- Whether Shape α's joint frame-trust gate would correctly reject f304 in production. (The replay didn't reach the commit; we have no direct trace tag firing there.)
- Whether Shape β's streak gate tightening would catch f304.

**Can say from current evidence:**
- Shape α as originally stated in §4.1 **has false-positive risk** confirmed by replay f138: proposed_batters=['PATHUM RAHUL'] (junk OCR) would trigger Shape α's reject even though the underlying delta=2 commit was legitimate. The softening "only fire when proposed_batters non-empty AND none in SM lineup AND none in FOW history" still fires at f138 (the junk batter is non-empty, in_sm_lineup=False, FOW empty), so the softening does not resolve the false positive.
- The streak gate at score_manager.py:3035 (`_BALLS_JUMP_TOLERANCE=3`) has a **clear structural blind spot** at Δballs=2 — observed empirically at f138 and f475. This is independent of the f304 question; any Δballs=2 gap commit bypasses the consensus check entirely.
- The lineage telemetry is **correctly wired** post-`is_playing_xi` fix: f138 shows `bowling_xi_size=11, proposed_bowler_in_bowling_xi=True` (bowler correctly resolved against KKR's XI), while `batting_xi_size=11, proposed_batter_in_batting_xi=False` (batter token correctly flagged as not-in-DC-XI).

### 9.4 Revised candidate shapes after empirical evidence

**Shape α' (refined).** Reject only when **both** axes mismatch: `proposed_batter_in_sm_lineup=False AND proposed_bowler_in_bowling_xi=False` (or `proposed_bowler is None`). Tested against replay:

| Frame | bat_mismatch | bowl_mismatch | Shape α' decision | Correct? |
|---|---|---|---|---|
| f138 | True | False (Vaibhav ∈ XI) | accept | ✅ benign gap |
| f475 | True (empty) | True (null) | reject | needs ground truth check |
| production f304 (hypothetical) | True (PANT∉DC XI) | True (SHAMI∉KKR XI) | reject | ✅ cascade root |

This dual-axis softening is more robust than §4.1's single-axis check. Worth proceeding to gate-7 cross-fixture replay (GTRR f203, f1106) once we have a way to reproduce f304-style commits.

**Shape β re-stated.** The streak gate's `_BALLS_JUMP_TOLERANCE=3` threshold blinds it to Δballs=2 commits. Lowering to 2 would catch f138-class commits — but the replay showed those are mostly benign. The streak gate is not the right tool for f138/f475 — those are below the noise floor where consensus tracking adds value.

For the f304-class commit (Δballs=11), the streak gate SHOULD have fired in production. Why it didn't is the live question Shape β must answer. **Resolution still requires either LLM-extractor scaffolding or manual FrameInput injection at f304**. Without that, Shape β cannot be empirically discriminated.

### 9.5 Next-step recommendation (operator decision required)

Three paths forward:

1. **Wire LLM-extractor fallback into the replay scaffold** so f304 reproduces end-to-end. Substantial work (~1–2 commits scaffolding the LLM call against captured raw_response). Buys full f304 reproduction.

2. **Inject a synthetic FrameInput at f304** with the production-extracted values (`score=54, wickets=0, overs=6.3, batters=[], bowler={}`). One-commit scaffold extension; bypasses the parse_strip limitation but loses fidelity (the synthetic input may not match the exact production extractor state).

3. **Accept the current evidence as sufficient to ship Shape α'** (the dual-axis frame-trust gate) without f304 reproduction. The §9.3 logic argues that Shape α' would correctly reject f304-class commits while accepting f138-class commits; the dual-axis decision rule is structurally sound.

Path 3 has the lowest engineering cost but the highest gate-6 risk (predicted-flip claim against f304 is by structural argument, not direct trace evidence). Path 1 is the most rigorous but the slowest. Path 2 is the pragmatic middle.

**Operator decision required before any code-level Shape α' commit.**

---

---

## 10. Empirical f304 evidence — LLM-extractor replay (commit `78b4835`) and the cascade-root pivot

Operator selected Path 1. LLM-extractor scaffolding shipped at `78b4835` (replay-only). Re-replay command:

```
files/.venv/bin/python files/scripts/replay_captured_scout_trace.py \
    --dump files/logs/deliveries/validate_dckkr_20260521_070545/scout_raw.jsonl \
    --session-id replay_dckkr_20260521_WARMSEEDED_LLM \
    --seed-frame 37 --seed-striker "Pathum Nissanka" \
    --seed-non-striker "KL Rahul" --seed-bowler "Anukul Roy" \
    --enable-llm-extractor
```

Result: 193 LLM extractor calls, 28 recoveries including the previously-unreachable f303 and f304 frames. OVERS-JUMP-STREAK-STATE tag count rose from 5 to 11, FRAME-TRUST-GATE stayed at 2.

### 10.1 The f304 anchor in replay — the streak gate fires and rejects

```
f303 (LLM-extracted: score=89, overs=10.2, wickets=4):
  OVERS-JUMP-STREAK-STATE decision=reject
  proposed=(10.2, 89) current=(4.5, 49) streak=1/3

f304 (LLM-extracted: score=54, overs=6.3, wickets=0):
  OVERS-JUMP-STREAK-STATE decision=reject
  proposed=(6.3, 54) current=(4.5, 49) streak=1/3
```

Each proposal is a fresh candidate (different (overs, score) tuple), so the streak counter resets to 1 each time. Neither reaches the 3-frame consensus threshold. **In replay, SM's `_handle_warm` correctly rejects f304's bad overlay anchor.** SM stays at 49/4.5 through f303-f318.

### 10.2 The f304 anchor in production — the gate ALSO fires and rejects

Production trace `logs/trace/validate_dckkr_20260521_070545.jsonl` shows the same gate decisions at the same frames:

```
f304: OVERS-JUMP-IMPLAUSIBLE-REJECTED × 2 + GAP-AT-REJECTION
      proposed=(6.3, 54) current=(4.5, 49) streak=1/3
f308: OVERS-JUMP-IMPLAUSIBLE-REJECTED × 2 + DIRECT-SM-REJECT
      + STRIP-HEAD-JOINT-POP × 2
f318: OVERS-JUMP-IMPLAUSIBLE-REJECTED × 2 (current_overs=4.5 in payload)
      + GRAPHIC-FILTER-POISON (tracker_score=54 tracker_overs=6.3)
```

**The streak gate fires at f304 in production identically to replay.** Same decision, same rejection.

But by f318 the GRAPHIC-FILTER-POISON message reports `tracker_score=54 tracker_overs=6.3` — meaning the Scoreboard's internal `_inn.score` IS at 54 and `_inn.overs` IS at 6.3 by f318. Meanwhile the OVERS-JUMP-IMPLAUSIBLE-REJECTED payload at f318 still cites `current_overs=4.5 current_score=54` — i.e., `self.overs` (the SM) is at 4.5 but `self.score` (the SM) is at 54.

**SM.score and SM.overs diverged.** Score advanced from 45 to 54 via a path that did NOT go through `_handle_warm`'s streak gate. Overs stayed at 4.5 (the gate caught the overs jump). The Scoreboard tracker (`sb._inn.score`, `sb._inn.overs`) advanced to 54 / 6.3 separately.

### 10.3 The cascade root pivot

This empirical evidence falsifies both the original B-η hypothesis ("multi-ball-gap decomposer accepted a bad anchor") and Shape β as stated ("strengthen the streak gate"). The streak gate at `score_manager.py:3035` does its job. The cascade root is upstream of `_handle_warm`:

- **`self.score = 54` got committed via a non-`_handle_warm` SM mutation site.** Probably the DIRECT-path score-commit at `score_manager.py:1376` (which we saw mutates `self.scoreboard.batting_team`) or a similar split score/overs commit.
- **The `[DIRECT]` log tag at f304** (`DIRECT × 3` in production) implies test_pipeline.py's score/overs/wickets DIRECT-path emitted score commits independently of SM's `_handle_warm` gating logic.
- **Scoreboard's `_inn` mutation** (separate from SM state) advanced to 54/6.3 via the `sb.set("score", ...)` / `sb.set("overs", ...)` calls in test_pipeline.py before SM's `on_frame` was even invoked.

Confirmed by inspecting `test_pipeline.py` for the DIRECT-path: there is a score-only DIRECT commit that bypasses SM's gap-rejection logic. The `[DIRECT-SM-REJECT]` tag at f308 is the SM rejecting a DIRECT score/overs proposal that the DIRECT path already executed at the tracker level.

This is **Link D**, a fourth mechanism not enumerated in §3:

- **Link A** (frame trust): no joint batter/bowler/score validation at the score-accept site.
- **Link B** (streak gate bypass): hypothesized; **falsified by §10.2 evidence** — the gate fires correctly.
- **Link C** (no resync path): once `self.score` diverges from broadcast, the override + filter chain prevents resync.
- **Link D** (split score/overs commit): score and overs commit through different code paths, allowing `self.score` to advance while `self.overs` is held by the streak gate. **This is the active defect mechanism.**

### 10.4 Implications for Shape α / Shape β / Shape α'

- **Shape α' (dual-axis frame-trust at `_decompose_multi_ball`)** is **not the right site**. `_decompose_multi_ball` is never reached at f304 in production OR replay; the streak gate guards it correctly. Shape α' would not have prevented the production cascade.
- **Shape β (streak-gate tightening)** is **also not the right site**. The streak gate is doing its job; Δballs≤3 blind spot is a separate concern.
- **A new candidate shape is required**: a frame-trust check at the DIRECT-path score commit site in test_pipeline.py — gating individual score mutations on the same joint-lineage condition Shape α' proposed for `_decompose_multi_ball`.

### 10.5 Next-step recommendation (operator decision required)

The investigation has shifted target. The active defect is in test_pipeline.py's DIRECT-path score-commit logic, not in `score_manager.py`. Three paths:

1. **Locate the exact DIRECT-path score-commit site in test_pipeline.py and add a fourth trace tag** (`DIRECT-SCORE-COMMIT`) that fires at every score-mutation, exposing whether f304's score=54 went through this path. One additive commit (C6-prep, observability-only). Then re-run replay; compare frame-by-frame; localize the defect.

2. **Skip directly to Shape γ (DIRECT-path frame-trust gate)**: add the joint batter/bowler/score lineage check at the test_pipeline.py site where DIRECT-path commits score. This requires identifying the site first (Path 1 above) — so Path 1 is the prerequisite, not an alternative.

3. **Pause the engineering work and update the brief**: B-η as the brief framed it is partially falsified. The cascade root is upstream of `_decompose_multi_ball`. The brief's Step 2 (B-ι) and Step 3 (B-θ) memos remain on hold per §7.2 cascade-closure pattern. The new design memo target is the DIRECT-path commit site — possibly a new bug class (B-κ?) replacing the brief's B-η framing.

**Operator decision required before Path 1 (additional instrumentation) or Path 3 (brief update).**

---

---

## 11. Fifth falsification — B-κ not reproducible from captured `scout_raw.jsonl`

C6 (`237d227`) shipped the `DIRECT-SCORE-COMMIT` instrumentation at the single `sb.set()` bottleneck in `eyes/scoreboard.py:1481`, paired with GTRR fixture support for gate-7 cross-fixture verification.

### 11.1 Empirical replay results

| Replay | DIRECT-SCORE-COMMIT firings | Anomalous (B-κ signature) | Tracker reached `score=54`? |
|---|---|---|---|
| DCKKR warm-seeded + LLM (`replay_dckkr_20260521_BKAPPA`) | 48 | 0 — all benign boundary advances (f138 8→15 at ov=1.2, f302 45→49 at ov=4.5, f361 49→53 at ov=5.1, etc.) | **No** — tracker holds at 49 across f303-f308 |
| GTRR warm-seeded + LLM (`replay_gtrr_20260520_BKAPPA`, fixture=gtrr) | 81 | 0 — large-Δ commits at f72/f296/f406/f466/f1075/f1123/f1379 all track normal six/boundary events with overs advancing in parallel | N/A |

### 11.2 Why the replay doesn't reach the production cascade

In the replay:
- Streak gate at `score_manager.py:3080` rejects f304 (`OVERS-JUMP-IMPLAUSIBLE-REJECTED, streak=1/3`).
- Consensus tracker at `sb.set` line 1237 receives one LLM-extracted f304 read of `score=54`, holds it as unconfirmed.
- Subsequent frames f305-f308 report `score=49` (parse_strip extracts the *real* broadcast strip), causing the tracker to drop the 54 candidate.
- SM's score never advances past 49 in replay. No cascade.

In production, the same f303/f304 frames produced the same `OVERS-JUMP-IMPLAUSIBLE-REJECTED` decisions (verified at §10.2). Yet by f318, `tracker_score=54`. This means the production session's tracker confirmed `54` via a path the captured-replay does not exercise.

### 11.3 Falsification of the §10.3 Link D hypothesis

§10.3 proposed Link D — "split score/overs commit via the DIRECT-path score-mutation site". The hypothesis was: `self.score = 54` got committed via a non-`_handle_warm` SM mutation while `self.overs` was held at 4.5.

C6 instrumentation now shows that **every score commit in replay went through `sb.set()` AND was accompanied by an overs commit**. The replay never shows score-only advancement. The hypothesis is falsified by the absence-of-signal across 48+81 instrumented frames.

This is the **fifth empirical falsification** of the B-η investigation chain:

1. `STREAM-GAP-TOO-LARGE-TO-DECOMPOSE` (§4.3, gate 7) — falsified
2. Shape α single-axis frame-trust (§9.4) — falsified at replay f138
3. Shape α' dual-axis frame-trust at `_decompose_multi_ball` (§10.4) — falsified at §10.2
4. Shape β streak-gate tightening (§10.4) — falsified at §10.2
5. **B-κ split-commit via sb.set (§10.3)** — falsified at §11.2 / §11.3

---

## 12. Investigation-strategy pivot — the captured-replay path is at end-of-yield

### 12.1 Diagnosis

Five empirical falsifications across one investigation chain, all on the same fixture pair, all via the same instrumentation-first methodology. The chain produced four diagnostic commits (`b49e48b`, `e3171eb`, `78b4835`, `237d227`) and three design-doc revisions (`86299e0`, `ac06fa6`, this C7). Total cost: 6 commits and roughly a week of investigation. The chain's output is empirical, not speculative — that is the discipline working — but the chain has stopped converging on a localized defect.

**The production cascade at f304-f318 is non-reproducible from captured `scout_raw.jsonl` alone via the SM-driven replay scaffold**, regardless of how comprehensively the scaffold is instrumented. The captured-replay path:

- Faithfully reproduces parse_strip's regex extraction (verified by f300/f302 SM-state match against production)
- Faithfully invokes the LLM-fallback extractor at the same frames production used (78b4835)
- Faithfully exercises the `sb.set` tracker / `_handle_warm` streak gate / `_decompose_multi_ball` decomposer
- **And yet** does not reach the `tracker_score=54` state production reached at the same frame indices

The defect is in **temporal / async coupling** that the deterministic-replay scaffold flattens: consensus-tracker confirmation behavior across UDP-stream-frozen windows, frame-arrival ordering with Scout 429-retry windows, the interaction of `THIS-OVER-APPEND` writes (seen in production f304 trace but absent in replay) with the streak gate's state, etc. None of these are at a single code site that more `sb.set` / `_decompose_multi_ball` / `_handle_warm` instrumentation can localize.

### 12.2 The "more instrumentation" trap

The natural next-instrumentation suggestion would be: instrument `test_pipeline.py:3620` (the state-recovery direct `_inn["score"] = ...` write), or instrument `confidence_tracker.py`'s consensus-confirmation state machine, or instrument every `_inn[*]` assignment across the codebase. Each is a plausible candidate; each would be additive; each would pre-commit-pass.

**But there is no empirical evidence the next instrumentation commit breaks the falsification pattern.** Four diagnostic commits in a row have produced findings that ruled out the previous hypothesis without converging on the actual defect site. Continuing the instrumentation treadmill assumes the defect is at a code site captured-replay can exercise — an assumption all five falsifications have now empirically challenged.

### 12.3 The pivot

The next investigation move is **static analysis of state-mutation sites + invariant classification**, NOT another instrumentation commit. Concrete shape (deliverable C9, deferred until C7+C8 land):

- **Enumerate every write site** for the five primitive fields (`score`, `wickets`, `overs`, batter identities, bowler identity) across `test_pipeline.py`, `score_manager.py`, `eyes/scoreboard.py`, and any other files that mutate them.
- **For each site, classify on four dimensions:**
  1. **Mutation target**: which underlying state (`sm.score`, `sm.scoreboard._inn["score"]`, `sm.scoreboard.batting_card[name]["runs"]`, etc.)
  2. **Gate protection**: which validation gates fire before the write (`_handle_warm` streak gate, `sb.set` tracker consensus, `cricket_rules.validate_diff`, etc.) and which sites bypass which gates
  3. **Invocation pattern**: sync inline, async via callback (e.g., `on_lock`), driven by external event (Scout retry, UDP freeze), etc.
  4. **Source of authority**: extractor reading, SM derivation, broadcast indicator, scout retry-buffer drain, etc.
- **Identify gate-bypass / invariant-violation classes.** A site that mutates `sm.score` but bypasses `_handle_warm`'s streak gate; a site that mutates `sb._inn["score"]` but bypasses `sb.set()`'s tracker consensus; a site that writes to one slot but not its sibling. These are the temporal-coupling defect candidates.

Output is a catalogue table; no fixes proposed at C9. Pure observability of the system surface.

### 12.4 What replay remains useful for

The captured-replay scaffold is not retired. It remains the canonical:
- **Falsification mechanism.** Any proposed fix can be replayed against DCKKR+GTRR `scout_raw.jsonl` to confirm whether the predicted-flip holds. Five falsifications above are proof the mechanism works.
- **Regression detector** for the existing trace-session assertions library.
- **Pre-commit gate substrate** (Layer 1.5 / Layer 2 / `run_trace_session_assertions`).

What it CANNOT do, per §11/§12 evidence: drive root-localization for temporal-coupling defects. That requires static analysis (this pivot) or end-to-end production-pipeline reproduction against the captured video (out of scope per the brief's "no fresh session needed" constraint, but a legitimate fallback if the static catalogue doesn't yield a localized defect either).

---

## 13. Meta-finding — the five-falsification discipline track record

This investigation's most important architectural finding is **the discipline itself, demonstrated at scale across one chain**.

### 13.1 The five falsifications

| # | Hypothesis | Site | Falsification mechanism | Speculative fix it prevented |
|---|---|---|---|---|
| 1 | `STREAM-GAP-TOO-LARGE-TO-DECOMPOSE` | `_decompose_multi_ball` cap | Gate 7 cross-fixture: GTRR has working 10/11-ball absorptions | A hard Δballs cap that would have regressed GTRR's legitimate gaps |
| 2 | Shape α single-axis frame-trust | `_decompose_multi_ball` entry | Replay f138: junk OCR batters + correct bowler → would false-reject | A frame-trust gate at the wrong site rejecting legitimate gaps |
| 3 | Shape α' dual-axis frame-trust | `_decompose_multi_ball` entry | Replay + production agree: gate never reached at f304 | A targeted fix at a site the defect never reaches |
| 4 | Shape β streak-gate tightening | `score_manager.py:3080` | Replay + production agree: streak gate fires correctly | A redundant tightening of a gate that wasn't broken |
| 5 | B-κ split-commit via `sb.set` | `eyes/scoreboard.py:1481` | DCKKR+GTRR replay: 48+81 firings, no anomalous Δscore | A `sb.set` guard against a phantom signature that doesn't exist |

### 13.2 The cost ratio

Six diagnostic/docs commits. Roughly a week of investigation time. Five speculative fixes that would have landed without the discipline. Each speculative fix would have:

- Passed Layer 1.5 / Layer 2 gates (additive enough to not regress the captured ledger)
- Looked architecturally reasonable in code review
- **Hidden the real defect under more cascade symptoms.** Subsequent sessions would have reported new bugs, traced them, found that the hidden defect surfaces under different overlay patterns or different async timings. Iteration cost would have compounded.

The discipline's cost: six commits, one week, zero production behavior change. The alternative: one speculative-fix commit, no upfront delay, multi-session iteration cost as cascade symptoms refactor through the codebase.

### 13.3 Architectural insight for next-session HANDOFF

**A complete falsification chain is an architectural finding, not a failure.** Previous session's headline result was F1's cascade-closure of four bug classes (`437d952`). This session's headline result is the inverse architecture: a five-link falsification chain that **prevented** four speculative fixes from landing and surfaced a class of defect (temporal coupling) that requires a different investigation methodology (static cataloguing) than the one that built F1.

The discipline pattern, validated empirically across both sessions:

- F1 session: predicted-flip discipline + gate-7 cross-fixture verification → one-edit fix closed four bug classes by collapsing cascade root.
- This session: same discipline applied recursively → five hypothesis falsifications → identified that the defect class doesn't admit instrumentation-driven localization → pivot to static cataloguing.

Both outcomes are the discipline working. Track-record-wise, the F1 closure validated the methodology's positive case (a one-edit fix can collapse multiple bug classes); this session validates its negative case (a five-falsification chain can surface a defect-class mismatch with the methodology, signaling a strategic pivot). The discipline produces **both** outcomes by design — neither is more legitimate than the other.

Bake into next-session HANDOFF §10 / §12 discipline-lesson catalogue.

---

**Replay paused at §12.3 pivot decision. Six commits landed: `b49e48b`, `e3171eb`, `86299e0`, `78b4835`, `ac06fa6`, `237d227`. Captured-replay path is at end-of-yield for B-η root-localization. Next move: C8 brief reframe → C9 state-mutation-site catalogue. No further instrumentation commits until the catalogue surfaces empirically-grounded candidates.**
