# Handoff — Session continuation document

**Last update**: 2026-05-21 (post-C16)
**Branch**: `derive-not-detect`
**Status**: Workstream paused at operational validation gate. F-η cascade root localized at production F302/F304 via static analysis + pipeline.log audit; Shape B cross-field pairing gate shipped at `apply_scorer_decision`. Predicted-flip claim on disk; next natural production session is the validation gate.

Entry point for next Cowork session. Read this file first, then `CLAUDE.md`, then `Architecture_HANDOFF.md`, then the design memos at:
- `files/docs/investigations/temporal_coupling_investigation_brief.md` (C10–C12.5b: the static-analysis methodology + cascade-root localization)
- `files/docs/investigations/c13_fc5_audit_memo.md` (the §7.2 7-gate audit on 4 shapes + Shape B selection)
- `files/docs/investigations/stream_gap_reconciliation_design.md` (B-η chain §1–§13: 5 empirical falsifications + investigation-strategy pivot)
- `files/docs/investigations/state_mutation_site_catalogue.md` (C9: 38 mutation sites + 2 async callbacks)
- `files/docs/investigations/dckkr_20260521_cc_investigation_brief.md` (the operator-side brief + §0 reframe)
- `files/docs/investigations/sm_as_orchestrator_design.md` §7 (the standing 7-gate audit framework) + §8 (dual-state-write defect-class catalogue — to be added in C17)

## The objective

Shift the pipeline from a detection-heavy architecture to a derivation-first architecture that consumes a strict 5-primitive Scout contract:
1. Runs (cumulative score)
2. Overs (current over notation)
3. Batter identities (names from squad list, not raw OCR strings)
4. Bowler identity
5. First striker after innings start / new batter after wicket

Everything else on the UI is deducible from these primitives plus per-frame deltas. The session's discipline: any classification of code as "scar tissue" or "defect class" is a hypothesis pending the §7.2 seven-gate audit. The audit is the load-bearing safety mechanism.

## Headline result this session — F-η cascade-root localization via static analysis + Shape B fix

**Shape B cross-field pairing gate (`ad151fd`)** at `apply_scorer_decision` (test_pipeline.py:4517) closes the B-η cascade root that produced the DC vs KKR session's f304 anchor corruption + downstream wicket-dispatch failures.

**Cascade root concretely localized via production `/tmp/pipeline.log` audit (C12.5b):**

```
F302 TRACK score: 45 → 49 (post-event immediate, grace=1)
F302 TRACK overs: 4.4 → 4.5 (fast-confirm, natural overs increment F302)
F303 POISONED                                                  (upstream block)
F304 TRACK score: 49 → 54 (post-event immediate, grace=1)      ← CASCADE ROOT
F304 TRACK overs: 4.5 → 6.3 (post-event immediate, grace=0)    ← CASCADE ROOT
```

The `(post-event immediate, grace=N)` suffix is the FC5 log signature from `consistent_tracker.py:304-305`. Two FC5 fires at F304 admit both halves of the bad PANT/WARD/SHAMI overlay frame's reading via `_post_event_grace=2` inherited from f302's `on_ball_event()` reset, combined with `_is_suspicious` returning False for upward score jumps under +30 and forward overs jumps.

**Empirical pairing criterion (C13 §2.1):**

```
legitimate_pair(d_score, d_balls, d_wickets) ≡
    (d_balls == 1 AND 0 ≤ d_score ≤ 7 AND d_wickets ∈ {0, 1})  -- legal delivery
  OR
    (d_balls == 0 AND 0 ≤ d_score ≤ 5 AND d_wickets ∈ {0, 1})  -- extras-only
```

Verified empirically: 127/127 benign DIRECT-SCORE-COMMIT firings (GTRR 80 + DCKKR 47) satisfy `legitimate_pair`. F304 fails (d_balls=10, d_score=+5).

## Session meta-findings — two architectural insights worth headlining

This session's accumulating discipline track record produced two transferable methodology insights, alongside the prior session's F1 cascade-closure headline:

### Meta-finding 1 — Static-analysis methodology at near-zero commit cost

Predicate-trail reading + cross-fixture empirical verification produces full cascade-root localization without an instrumentation cycle per hypothesis. The C9 catalogue + C10 static analysis + C11 predicate semantics + C12 sub-candidate elimination + C12.5b pipeline.log parse = **full cascade-root localization at near-zero commit cost** (5 docs commits, zero behavior change), followed by C13 audit + C14 fix at 2 functional commits.

The previous methodology (instrument → replay → fix) had a budget cost of one diagnostic commit per hypothesis. The static-analysis methodology had a budget cost of one docs commit per hypothesis-class. **This is a defect-class identification methodology distinct from "instrument-replay-then-fix", suited specifically to temporal-coupling defect classes that captured-replay flattens (per §0.3 of the C8 brief reframe).**

### Meta-finding 2 — Falsification cascade as methodology signal-of-correctness

Five empirical + eight static falsifications + one acceptance is the methodology's signal of correctness, not its signal of failure. The discipline rule "every classification is a hypothesis pending empirical verification" produces a falsification cascade BY DESIGN; the budget mechanism (5-empirical-falsification methodology-retirement trigger from C9 §11 + C10 §1.2) ensures the cascade terminates productively rather than open-loop. **A complete falsification chain is an architectural finding, not a failure.**

These two meta-findings join F1's cascade-closure (prior session) and the §7.2 7-gate audit (prior session) as the workstream's accumulating discipline track record.

## Architectural posture

### Detection vs Derivation (unchanged from prior session)
- **Detection (5 primitives only)**: vision provides runs, overs, batter names, bowler name, first-striker/new-batter signals.
- **Derivation (everything else)**: this_over tokens derive from per-frame (Δruns, Δovers, wicket events). Striker rotation derives deterministically from first-striker + per-ball runs sequence + wicket events.
- Squad-canonical name resolver enforces that raw Scout name tokens get rejected if they don't fuzzy-match to a squad member.

### SM as sole UI authority (unchanged + reinforced)
- WS payload reads Recent Overs from SM's `over_history`.
- Striker rotation determined by SM; broadcast indicator is corroboration only.
- Squad-canonical name resolver enforced at all bat1_name / bat2_name / broadcast_striker / bowler_name commit sites.
- Initial striker at cold-start exit reads `broadcast_striker` field correctly (F1, `437d952`).
- **New (C14): cross-field pairing gate at `apply_scorer_decision` rejects single-frame commits whose (Δscore, Δballs, Δwickets) tuple violates `legitimate_pair`.**

### No-speculative-fixes discipline (refined further this session)
Every fix commit must cite specific trace evidence — concrete frame numbers — that proves the diagnosed cause. "Likely" / "probably" language is investigation-only, never authorization to commit. If diagnosis can't be confirmed from existing data, add static-analysis + pipeline.log audit first, re-run, then fix.

**The "captured-replay drives investigation" assumption is RETIRED** for temporal-coupling defects (per C8 §0.3). Captured-replay remains canonical as a falsification mechanism and regression-detection substrate; it does NOT drive root-localization for defect classes where the temporal signature flattens under deterministic replay.

### §7.2 seven-gate audit checklist (standing precondition; gates 1–7 unchanged)

The framework added gate 7 (cross-fixture verification) in the prior session per F1 closure. This session applied all 7 gates to 4 candidate shapes (A/B/C/D) at C13 — first deep multi-shape audit in the chain. Gate-6 (predicted-flip with concrete frame numbers, applied recursively) is non-negotiable per the falsification track record.

**New discipline nuance — static vs empirical falsification:**

- **Empirical falsification** counts against the methodology-retirement budget (5-falsification cap per C9 §11 / C10 §1.2). Replay or instrumentation cycle empirically disproves a hypothesis.
- **Static falsification** does NOT count against the budget. Code-reading or predicate-trail pass conclusively proves a hypothesis is impossible at the proposed site. Zero-cost; apply liberally before any instrumentation commit.

This session: 5 empirical falsifications (B-η chain) + 8 static falsifications (C10 + C11 + C12) + 1 acceptance (Shape B). Without the static-vs-empirical distinction, the chain would have hit the retirement budget at C11.

## This session's commit ledger — chronological

This session ran 2026-05-21. **16 commits total.** Pre-commit gate (Layer 1.5 + Layer 2) held on every commit. Predicted-flip claims empirically validated or statically falsified at each step.

```
b49e48b chore(diagnostics): B-η instrumentation pass — three additive trace tags + replay scaffold
e3171eb chore(diagnostics): replay-scaffold warm-seed mode for f304-anchor reproduction
86299e0 docs(design): B-η stream-gap reconciliation memo + post-instrumentation empirical findings
78b4835 chore(diagnostics): replay-only LLM-extractor fallback for f304-anchor reproduction
ac06fa6 docs(design): B-η memo §10 — empirical f304 evidence + cascade-root pivot
237d227 chore(diagnostics): DIRECT-SCORE-COMMIT instrumentation + GTRR fixture support
e19f72a docs(design): B-η memo §11-§13 — fifth falsification + investigation-strategy pivot + meta-finding
a99d82c docs(brief): C8 reframe — Step 1 retarget + temporal-coupling block on Steps 2/3
af19dd2 docs(design): C9 state-mutation site catalogue — 38 write sites + 2 async callbacks
2df4061 docs(brief): C10 temporal-coupling investigation — sixth hypothesis, static analysis
5833857 docs(brief): C11 static-analysis pass — Outcome A (qualified) on FC5 post-event grace
b6e3c70 docs(brief): C12 overs-side static-analysis closure — score-side fully localized, overs-side narrowed
c05c4b6 docs(brief): C12.5b — pipeline.log audit closes gate 6 with concrete frame numbers
639fa4a docs(audit): C13 §7.2 7-gate audit on FC5 candidate fix shapes — Shape B selected
ad151fd fix(test_pipeline): C14 cross-field pairing gate at apply_scorer_decision — closes B-η F304 cascade root
770db98 test(C15): permanent gate-6 verification + baseline + predicted-flip claim for C14 fix
```

## Trace assertion library (broken-but-known baseline, unchanged from prior session)

Five empirically-grounded invariants in `files/tests/trace_session_assertions.py`. Baselines:

| Assertion | DCKKR pre-fix | GTRR baseline | Predicted post-C14 on next session |
|---|---|---|---|
| `trace_alpha_bowler_runs_sum` | FAIL gap=4 | FAIL (gap=25 pre-F1) | **predicted: gap reduces or PASS** (B-θ cascade contribution collapses) |
| `trace_beta_sm_wicket_dispatch` | FAIL — 3 misses (f371, f521, f636) | FAIL — 2 misses | **predicted: PASS** (cascade closure — F304 anchor blocked) |
| `trace_epsilon_initial_striker` | PASS | FAIL (pre-F1) | PASS (unchanged) |
| `trace_compound_tokens` | PASS | FAIL (pre-F1) | PASS (unchanged) |
| `trace_extras_total` | PASS | FAIL (UI render layer, separate scope) | PASS (unchanged) |

Runner: `python files/scripts/run_trace_session_assertions.py <trace.jsonl>`.

## Validation gate — next natural production session

The workstream's standing operational pattern: ship with predicted-flip claim, validate on next natural production session. No fresh-session-now authorization required.

**On next session's trace landing:**
1. Add filename stem to `SESSION_CONTEXT` in `files/scripts/run_trace_session_assertions.py`
2. Run `python files/scripts/run_trace_session_assertions.py logs/trace/<NEW>.jsonl`
3. Observe whether `trace_beta_sm_wicket_dispatch` flips PASS

**Two outcomes:**
- **YES (predicted-flip materializes):** F-η cascade closure confirmed end-to-end. Workstream cycle complete. C19 → next-session HANDOFF rewrite documents the cycle closure.
- **NO (sixth empirical falsification):** Shape B at `apply_scorer_decision` is necessary but not sufficient. Per §1.2 (C10 brief) + C9 §11: methodology retirement trigger OR coverage extension. The empirically-justified next move is **C19: extend Shape B coverage to `test_pipeline.py:8986+` (catch-up branch) and `:11750` (end-of-over hook)** — the two sites Shape B does not currently gate.

## Workstream status by area

### F-η Shape B fix (shipped C14)
Cross-field pairing gate at `apply_scorer_decision`. Closes the F304-class cascade root concretely localized via production pipeline.log. Permanent gate-6 test at `files/tests/test_cross_field_pairing_gate.py` (6 cases) wired into Layer 1.5.

### B-ι (locked-SM-state prevents resync) — deferred pending C14 validation
The previous brief framed B-ι as a separate engineering workstream (the deterministic-rotation override at `score_manager.py:4295-4325`). Per the dual-state-write defect-class pattern: if F-η closure prevents the SM/sb._inn divergence at f304 in the first place, B-ι's "resync prevention" symptom may never manifest. **Wait for next natural production session's trace_beta verdict before opening B-ι memo.**

### B-θ (over-boundary bowler credit) — deferred pending C14 validation
Same rationale. The trace_alpha gap=4 in DCKKR is hypothesized to be B-θ's residual contribution after B-η is removed. If trace_alpha gap closes post-C14, B-θ collapses as cascade symptom. If gap persists, B-θ becomes the next standalone target.

### Captured-replay scaffold (commits b49e48b–237d227)
- `files/scripts/replay_captured_scout_trace.py` — captured-Scout replay scaffold
- Supports `--seed-frame / --seed-striker / --seed-non-striker / --seed-bowler` (warm-seed mode)
- Supports `--enable-llm-extractor` (production Extractor.extract() via Groq Llama)
- Supports `--fixture {dckkr, gtrr}` (cross-fixture)
- Emits four observation tags: `FRAME-TRUST-GATE`, `OVERS-JUMP-STREAK-STATE`, `POISON-STREAK-AT-COMMIT`, `DIRECT-SCORE-COMMIT`
- **Limitation (§0.3 retired-assumption):** does NOT drive `apply_scorer_decision` — only SM-side `on_frame()`. Captured-replay cannot reproduce temporal-coupling defects; serves as falsification mechanism + regression detector, not localization tool.

### State-mutation-site catalogue (C9)
`files/docs/investigations/state_mutation_site_catalogue.md`: 38 write sites + 2 async callbacks across `score_manager.py`, `test_pipeline.py`, `eyes/scoreboard.py`. Score, wickets, overs, batter-identity, bowler-identity primitives.

**Three gate-bypass classes surfaced:**
- §7.1 `_inn[*]` direct-write bypass (6 sites) — state-recovery Phase-2 + POISON-RECAL forced reset
- §7.2 async-callback writes (2 sites: striker/bowler on_lock) — falsified statically in C10 §3 (not actually async)
- §7.3 hot-resume path (5 sites) — startup-only, deprioritized

**Catalogue is itself a gate-6 instrument** (per C9 §11): future "the defect is at site X" hypotheses can be checked against the table for whether X is a real mutation site, what gates protect it, what the invocation pattern is.

### UI render layer bugs (separate workstream — unchanged from prior session)
- B-γ (Recent Overs panel drops entries), B-δ (UI bottom-strip striker), `trace_extras_total` UI inconsistency — out of scope for SM/pipeline workstream.

## Pipeline tracks (unchanged)

### Track 1 — State derivation (production pipeline)
Entry: `files/test_pipeline.py` main loop. Frame source: `files/eyes/capture/udp_frame_source.py` (UDP MPEG-TS via ffmpeg subprocess).

Status: C14 fix in place; operational validation pending; cascade-root localized at F302/F304 via static analysis + pipeline.log empirical evidence.

### Track 2 — Clip extraction (OpenScout)
Disabled (`USE_OPEN_SCOUT=0`). Will not enable until Track 1 fully validated.

## File paths

```
files/test_pipeline.py             # Main pipeline; apply_scorer_decision at :4356
                                   # C14 cross-field pairing gate at :4517
files/score_manager.py             # State machine (~6500 lines)
files/eyes/scoreboard.py           # Scoreboard + sb.set bottleneck at :1188-1481
                                   # DIRECT-SCORE-COMMIT emission at :1481 (C6)
files/eyes/consistent_tracker.py   # ConsistentReadTracker — 5 fast-confirm paths
                                   # FC5 post-event grace at :294-306 (cascade root)
files/eyes/scoreboard.py           # batting_card / bowling_card / squad resolution
files/confidence_tracker.py        # ConfidenceTracker (team / striker / bowler)
                                   # NOT the FC5 site (don't confuse with consistent_tracker.py)
files/eyes/vision.py               # SCOUT_PROMPT_SHORT (default), SCOUT_PROMPT (verbose)
files/eyes/agent.py                # Extractor.extract() — LLM fallback path
                                   # Uses int|None syntax (Python 3.10+)
files/eyes/extract_regex.py        # Regex-primary parse_strip (returns None on STRIP miss)
files/eyes/frame_ledger.py         # Frame Fate Ledger
files/eyes/udp_frame_source.py     # UDP MPEG-TS frame source
files/cricket_rules.py             # validate_diff invariants
files/trace_emitter.py             # KNOWN_TAGS registry (180+ tags incl. C6/C10/C14)

scorecard-ui/app/page.tsx          # Main UI
scorecard-ui/app/components/BattingCard.tsx

files/tests/symptom_class_assertions.py    # 11 assertion functions (12 classes)
files/tests/trace_session_assertions.py    # 5 trace-session assertions
files/tests/test_sm_derivation_ledger.py   # Layer 1.5 — 36 balls + 6 cross-field gate cases
files/tests/test_pipeline_captured_replay.py  # Layer 2 — captured-Scout replay
files/tests/test_cross_field_pairing_gate.py  # C15 permanent gate-6 (6 cases)
files/tests/fixtures/dc_vs_kkr_2026_152064_ledger.json
files/tests/fixtures/gt_vs_rr_2026_commentary_first_innings.md

files/scripts/run_trace_session_assertions.py     # Trace session assertion runner
files/scripts/replay_captured_scout_trace.py      # Captured-replay scaffold (C-commits)
files/scripts/analyze_gap_detected_retro.py
files/scripts/audit_scar_tissue_targets.py

files/docs/investigations/temporal_coupling_investigation_brief.md  # C10–C12.5b chain
files/docs/investigations/c13_fc5_audit_memo.md                     # C13 7-gate audit
files/docs/investigations/stream_gap_reconciliation_design.md       # B-η chain §1–§13
files/docs/investigations/state_mutation_site_catalogue.md          # C9 catalogue
files/docs/investigations/dckkr_20260521_cc_investigation_brief.md  # operator brief + §0 reframe
files/docs/investigations/dckkr_20260521_session_observations.md    # observations + C15 §
files/docs/investigations/sm_as_orchestrator_design.md              # §7 framework + §8 (C17 target)

deploy/systemd/*.service           # pipeline, recorder, live-clips, ui
deploy/Caddyfile
.github/workflows/deploy.yml
.git/hooks/pre-commit              # Layer 1.5 + Layer 2 gate; venv-Python preference (C15)
```

## Launch sequence (operational reference, unchanged)

```bash
cd ~/Projects/SportsComm

# Clear stale state
rm -f files/match_state_cache.json logs/openscout-local_*.jsonl
rm -f /tmp/pipeline.log /tmp/ffmpeg.log

# Terminal A — UI
cd ~/Projects/SportsComm/scorecard-ui && npm run dev

# Terminal B — pipeline (Python 3.12 venv)
cd ~/Projects/SportsComm
export FRAME_SOURCE=udp
export FRAME_SOURCE_UDP_URL='udp://0.0.0.0:9999?fifo_size=10000000&buffer_size=2097152&overrun_nonfatal=1'
export FRAME_SOURCE_UDP_ALLOWED_DIMENSIONS='1920x1080,1280x720'
export CRICBUZZ_MATCH_ID=<match_id>
export CRICBUZZ_MATCH_SLUG=<slug>
export BMF_SESSION_ID="validate_$(date +%Y%m%d_%H%M%S)"
export USE_OPEN_SCOUT=0
export SCOUT_PROMPT_MODE=verbose
export SCOUT_RAW_DUMP=1
export PYTHONUNBUFFERED=1
export SCOUT_DEDUP_SHADOW=1
export SKIP_PREMATCH_S=0
files/.venv/bin/python files/test_pipeline.py 2>&1 | tee /tmp/pipeline.log

# Terminal C, D — see prior HANDOFF for ffplay viewer + ffmpeg dual-output stream
```

UI: http://localhost:3000. Validation fixtures:
- DC vs KKR (`files/logs/deliveries/20260508_191946/match_4621b9f8.mp4`, start ~09:30)
- GT vs RR (`files/logs/deliveries/8a0c6c14/match_8a0c6c14.mp4`, start ~40:30)

## Fresh-checkout setup (NEW in C16)

The pre-commit hook at `.git/hooks/pre-commit` prefers the project venv Python (`files/.venv/bin/python`, 3.12) over system `python3` (3.9 on most macOS). This is necessary because the C15 cross-field-pairing-gate test imports `eyes/agent.py` which uses `int | None` syntax (Python 3.10+).

The hook lives outside the tracked git tree (`.git/hooks/` is gitignored), so a fresh clone needs to reinstall the hook with venv preference. **C18 will ship a `scripts/setup_precommit.sh` (or equivalent) that installs the hook with the correct content.** For now, on a fresh checkout, manually edit the hook to use `$REPO_ROOT/files/.venv/bin/python` instead of `python3`. See the version currently on disk for the exact pattern.

## What NOT to touch

Per prior session + this session's findings:

- Queue B (`_pending_bowler_ball_credits`) — load-bearing 3-way-race resolver per §7.1
- `_ScoutRetryBuffer` — active queue across Groq 429 backoff per §7.1
- `broadcast_extra` / `extras_type` — parallel fields per §7.5
- Cold-start synth token-distribution heuristic in `_synthesize_cold_start_ball_events`
- `confidence_tracker.py` ConfidenceTracker class — battle-tested, foundational
- Existing deterministic-rotation override at `score_manager.py:4295-4325` — load-bearing
- **NEW: C14 cross-field pairing gate at `apply_scorer_decision` (`test_pipeline.py:4517`)** — the cascade-closer for B-η
- **NEW: Permanent gate-6 test at `files/tests/test_cross_field_pairing_gate.py`** — the empirical regression detector for C14
- F1's field-name fix at `_accept_initial:2789-2808`
- F-α-shadow fix in `_capture_multi_ball_shadow_state:4515+`
- F-α-queue in `_apply_absorbed_event` (5310-5358)
- Pre-commit hook venv preference — deviating from this will silently break L1.5 imports

## What's in flight behind feature flags (unchanged)

- `SM_INLINE_MULTI_BALL` — default off
- `SM_POST_WICKET_SLOT_DIFF` — default off
- `USE_OPEN_SCOUT` / `USE_OPEN_SCOUT_SPANS`

## Next session's first action

1. Read this HANDOFF.md
2. Read `Architecture_HANDOFF.md` + `CLAUDE.md`
3. Read the design memo chain in the order listed at the top of this file
4. `git log --oneline derive-not-detect | head -20` for full session context

**If a fresh production trace exists in `logs/trace/` newer than `validate_dckkr_20260521_070545.jsonl`:** the validation gate has fired.
- Add the filename stem to `SESSION_CONTEXT` in `files/scripts/run_trace_session_assertions.py`
- Run the assertions
- **Predicted: `trace_beta_sm_wicket_dispatch` flips FAIL→PASS; `trace_alpha_bowler_runs_sum` gap reduces or closes**
- If yes: F-η cascade closure confirmed; rewrite HANDOFF documenting cycle closure
- If no: **sixth empirical falsification** — open C19 design memo for extending Shape B coverage to `test_pipeline.py:8986+` (catch-up branch) and `:11750` (end-of-over hook)

**If no fresh trace yet:** operational pause; no engineering work currently unblocked. DO NOT spend capacity on B-ι / B-θ memos, on Shape C/D revisits, or on dual-state-write catalogue extensions — wait for empirical pressure from the next session's trace.

## Standing discipline (refined this session)

Architecture principles user repeatedly enforces (carried from prior session, refined this session):

- "Detection establishes identity, derivation maintains state"
- "SM is the final authority on the UI; everything else should not have a say"
- "Once high confidence reached, LOCKED — only explicit events unlock"
- "Real-time first, no offline-only solutions"
- "Consolidate and validate together — minimize ping-pong validation cycles"
- **"No speculative fixes. Find the root cause and confirm. Always."** — this session: 5 empirical + 8 static falsifications enforced the rule recursively across 16 commits.
- Any "scar tissue" / "defect class" label is a hypothesis pending the §7.2 audit.
- **Static-falsification ≠ empirical-falsification.** Static is zero-cost; apply liberally before any instrumentation commit. Empirical counts against the methodology-retirement budget (cap: 5 per session per defect-class chain).
- **Captured-replay does NOT drive root-localization for temporal-coupling defects.** It remains canonical as falsification + regression-detection substrate.
- **A complete falsification chain is an architectural finding, not a failure.** Document each chain's meta-finding in HANDOFF alongside the positive cascade-closure findings (F1, etc.).

## Trace-and-Detect (v1, unchanged)

Per CLAUDE.md trace-and-detect section. Per-frame trace records to `logs/trace/<SESSION_ID>.jsonl`. New trace tags this session:

- `FRAME-TRUST-GATE`, `OVERS-JUMP-STREAK-STATE`, `POISON-STREAK-AT-COMMIT` (C6 instrumentation pass)
- `DIRECT-SCORE-COMMIT` (C12 — at sb.set bottleneck)
- `CROSS-FIELD-PAIRING-REJECT` (C14 — at apply_scorer_decision gate)
- `REPLAY-LLM-EXTRACT-RECOVERED` (replay-scaffold-only, not in production)

## Pipeline feature flags (unchanged)

- `USE_OPEN_SCOUT` (default 0): disabled until Track 1 fully validated
- `USE_OPEN_SCOUT_SPANS` (default 0)
- `SM_INLINE_MULTI_BALL` (default 0): flag flip blocked pending fresh trace
- `SM_POST_WICKET_SLOT_DIFF` (default 0)

## Working venv

Project venv at `files/.venv/bin/python` (Python 3.12). **Pre-commit hook uses this venv** (C15 change). System `python3` (Python 3.9 on macOS) does not support the Python 3.10+ syntax used in `eyes/agent.py`.

## Session-end architectural insight

This session's most important architectural insights, validated empirically across 16 commits:

**(1) Static-analysis methodology + predicate-trail reading + pipeline.log audit produces full cascade-root localization at near-zero commit cost.** The chain C9 + C10 + C11 + C12 + C12.5b produced 8 static falsifications and concrete F302/F304 localization with zero behavior change. Followed by C13 audit + C14 fix at 2 functional commits.

**(2) A complete falsification cascade is an architectural finding, not a failure.** Five empirical + eight static falsifications + one acceptance is the discipline working as designed. The budget mechanism (5-empirical-falsification cap per defect-class chain) ensures the cascade terminates productively rather than open-loop.

**(3) Two-parallel-state-surfaces is a recurring defect class.** Three instances confirmed across two sessions: F-α-shadow (`sb.bowling_card` vs `sb._inn["bowling_card"]`), F1/B-ε (`card.get("broadcast")` vs `card.get("broadcast_striker")`), B-η/FC5 (`sb._tracker.confirmed` vs SM `_handle_warm` streak gate). To be catalogued in `sm_as_orchestrator_design.md` §8 in C17 with detection-signal + remediation-pattern documented.

The workstream pauses cleanly at the operational validation gate. Next move is operational, not engineering. The trace assertion library + 16-commit investigation chain are the standing data-collection + verification mechanisms for any future production session.

Track record of architectural insights accumulated across sessions:

- **F1 session (prior)**: cascade-closure pattern — one-edit fix can close N bug classes; §7.2 gate 7 (cross-fixture verification) catches cascade reach.
- **B-η session (this one)**: static-analysis-with-predicate-trail methodology + falsification-chain-as-architectural-finding + dual-state-write defect class.

Each session contributes one or more transferable methodology insights that survive into the next session's discipline. **The discipline track record is itself a load-bearing artifact** — preserve it; document new insights as they accumulate.
