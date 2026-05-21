# Workstream D — rotation-lock-starvation root investigation

**Status.** Open — multi-hypothesis bundle, two independent shapes (H-D1 bowler em-dash; H-D2 striker fallback monoculture) + sharpening sub-findings.
**Branch.** `derive-not-detect` (HEAD `6b613d9`, C25).
**Entry capture.** `files/logs/deliveries/validate_dckkr_20260521_155356/` (DCKKR 2026-05-21, ov 0.0 → 11.5, ~58 min wall).
**Methodology.** C10 temporal-coupling brief + C9 mutation-site catalogue. §7.2 7-gate audit applied to both hypotheses at §6.

---

## §0 Scope + entry data

**Objective.** Localize and close the rotation-lock-starvation root that causes both batter-striker AND bowler-identity pointers to be stale (or em-dash sentinel) at wicket-event boundaries. Promoted at C24 closure to highest-priority unblocked workstream. Blocks C23b (`update_bowler` at wicket-dispatch).

**Entry data inventory.**
- `validate_dckkr_20260521_155356.jsonl` — 406 records, 5 wicket events captured (WICKET-ATTRIB tag), of which 4 carry `ball_event.type == 'WICKET'`.
- `scout_raw.jsonl` — Scout VLM raw output; presence of structured `dismissed` field on wicket frames is a critical H-D2 gate-6 precondition (§3.3).
- `pipeline.log` — DETAIL line preserved per CLAUDE.md trace-and-detect §1.
- `validate_dckkr_replay_observations.md` — Obs 2/3/9 (rotation-lock), Obs 16/18/21 (FOW-name swap), Obs 17/19 (bowler-W increment failure).
- C19A3 `7557d47` — `trace_beta_sm_wicket_dispatch` emission restored at `score_manager.py:5328`. **Capture pre-dates this commit** (capture 15:53:56; commit 17:31:17 same day). `resolution_src` payload not in this trace; P2/P3 attribution distribution deferred to next replay.
- `state_mutation_site_catalogue.md` (C9) — bowler-identity write sites.
- `surface_pair_defect_class_family.md` §2.5 (striker pointer ⊥ FOW-name) + §2.6 (FOW count ⊥ bowler-card W).

---

## §1 Empirical baseline

### §1.1 Five WICKET-ATTRIB events; one striker-path; four non-striker-path

| Frame | WICKET-ATTRIB dismissed | Slot rotation log | Cricket truth | Name match | ball_event.WICKET? |
|---|---|---|---|---|---|
| F400 | KL Rahul | **non**-striker → slot cleared | KL Rahul (Obs 7) | ✓ | yes |
| F679 | Nitish Rana | **non**-striker → slot cleared | Nitish Rana (Obs 11) | ✓ | yes |
| F855 | Pathum Nissanka | **non**-striker → slot cleared | Rizvi (Obs 16) | ✗ | yes |
| F983 | Sameer Rizvi | **striker** → Stubbs rotated in | Nissanka (Obs 18) | ✗ | **no** |
| F1017 | Axar Patel | **non**-striker → slot cleared | not Patel (Obs 21) | ✗ | yes |

### §1.2 Reconciling §0.4 / γ-bundle baseline (`FAIL × 4`) vs 5-wicket capture

`assert_bowler_w_increment_on_dispatch` keys on `ball_event.type == 'WICKET'` (lines 524-529 of `trace_session_assertions.py`). F983's striker-slot dismissal emits WICKET-ATTRIB + POST-WICKET-ROTATION + INCOMING-BATTER-PENDING but **no `ball_event.type == 'WICKET'`** — the assertion silently misses it. `FAIL × 4` is correct under the current detector; the true wicket count in this capture is **5**, with F983 invisible to the γ-bundle.

**Sub-finding S1: striker-path vs non-striker-path dismissal dispatch paths emit different trace artifacts.** The 4 non-striker-path wickets emit `ball_event.type == 'WICKET'`; the 1 striker-path wicket (F983) does not. This is itself a §2.5 / §2.6 surface-pair divergence: dismissal-handler emission is keyed to slot identity in a way that should be uniform.

### §1.3 WICKET-ATTRIB resolution path — P3 monoculture

All 5 WICKET-ATTRIB records carry the identical log signature *"Dismissed batter set from scoreboard striker: <name>"*. **0/5 events resolve via `event.dismissed`** (P2). The dismissal handler always falls back to `scoreboard.striker` — the P3 fallback path per C19A3 schema. Per §3.3 below, this is **forced by upstream**: Scout never emits a structured `dismissed` field.

### §1.4 Em-dash sentinel — over-boundary correlation

`pipeline.current_bowler` snapshot at each wicket frame:

| Frame | `pipeline.current_bowler` | BOWLER-OBSERVE leader | BOWLER-LOCK-RELEASED at frame | Cricket position |
|---|---|---|---|---|
| F400 | `'—'` | Kartik Tyagi LOCKED | **yes** — `over_n=4, prev_bowler=null, reason=over_end_credit_complete` | end of ov 5 (5.0) |
| F679 | `'—'` | Cameron Green LOCKED | **yes** — `over_n=7, prev_bowler=null, reason=over_end_credit_complete` | end of ov 8 (8.0) |
| F855 | `'Sunil Narine'` | Sunil Narine LOCKED | no | mid-ov 10 (9.5) |
| F1017 | `'Anukul Roy'` | Anukul Roy LOCKED | no | mid-ov 11 (10.5) |

**2/2 over-boundary wickets em-dash; 2/2 mid-over wickets name-populated.** Correlation is deterministic in this capture. C23 §0.4 stated "2/3" based on a 3-wicket sub-sample; the 4-wicket frame-anchored count refines this to "**em-dash iff over-end coincides with wicket frame**".

### §1.5 Sub-finding S2 — scout dismissed-field absence

Scout `raw_response` at all wicket-bracket frames (±6 of F400/F679/F855/F983/F1017) emits either `"VISIBLE_TEXT: WICKET"` (a pure event marker) or score-line text (`DC 49-1 (5) ... TYAGI 4 1 1 4 W 1-10 1`) — **never a structured `dismissed` field**. The dismissed batter's identity is never surfaced by the VLM as a typed field on this trace.

Implication: H-D2's predicted-flip ("wire `event.dismissed` ahead of P3 striker fallback") **cannot fire** at the dismissal-handler boundary — there is no P2 payload to consume. The actual root sits in **scout extraction / event-construction** — either the Scout prompt schema doesn't request a dismissed-batter slot, or the event-builder downstream of Scout doesn't derive one from the strip text it does receive (e.g., "WICKET" marker + bowler-card W increment from `TYAGI ... W 1-10`).

---

## §2 H-D1 — bowler em-dash root

### §2.1 Mechanism

`BOWLER-LOCK-RELEASED reason=over_end_credit_complete` fires at the same frame as WICKET-ATTRIB when the wicket falls on the final ball of an over. The release clears `self.bowler_name` (or equivalent SM scalar) but **not** the BOWLER tracker LEADER (which holds the correct name). The wicket-dispatch site then reads the cleared scalar — producing the `'—'` sentinel observable in `pipeline.current_bowler` at F400 and F679.

Structural signature matches §12.3 / §2.6 dual-state-write:
- **Surface A** (`self.bowler_name` scalar) — weaker invariant; cleared by `over_end_credit_complete` path.
- **Surface B** (`BOWLER-OBSERVE.leader`) — canonical; preserves Tyagi / Green correctly across the release.
- Dispatch consumer reads A, not B. A is empty → em-dash.

### §2.2 Evidence anchors

- F400 — `pipeline.current_bowler='—'`, BOWLER-OBSERVE leader='Kartik Tyagi' LOCKED at F392/F393/F394/F395/F396/F400/F401, BOWLER-LOCK-RELEASED at F400 with `over_n=4, prev_bowler=null`.
- F679 — `pipeline.current_bowler='—'`, BOWLER-OBSERVE leader='Cameron Green' LOCKED at F676/F679, BOWLER-LOCK-RELEASED at F679 with `over_n=7, prev_bowler=null`.
- F855 — no BOWLER-LOCK-RELEASED in ±8, `pipeline.current_bowler='Sunil Narine'` — control case.
- F1017 — no BOWLER-LOCK-RELEASED in ±8, `pipeline.current_bowler='Anukul Roy'` — second control case; `DISMISSAL` decision records `bowler='Anukul Roy'` correctly.

### §2.3 Predicted-flip claim (§7.2 gate 6)

Routing the wicket-dispatch bowler read to `BOWLER-OBSERVE.leader` (or equivalently: deferring `BOWLER-LOCK-RELEASED reason=over_end_credit_complete` until after the wicket-dispatch emission in over-end-coincident frames) **flips `trace_gamma_bowler_w_increment_on_dispatch` from FAIL×4 toward FAIL×2** on the next DCKKR replay. Specifically:
- F400 — bowler resolves to Kartik Tyagi → BOWL-DELTA `+wkts=1` fires within 30-frame window → assertion passes for this wicket.
- F679 — bowler resolves to Cameron Green → BOWL-DELTA `+wkts=1` fires → assertion passes for this wicket.
- F855, F1017 — already had correct bowler on Surface A; predicted-flip is a no-op for these wickets at H-D1 scope (they fail via H-D2's striker-derived dismissed name corrupting the credit pipeline — see §3).

**Numeric prediction:** `trace_gamma_bowler_w_increment_on_dispatch` FAIL×4 → FAIL×2 (Nissanka + Patel still fail because dismissed-name resolution is corrupted upstream; bowler-name correctness is necessary but not sufficient for the BOWL-DELTA credit to land).

### §2.4 Candidate fix sites

Per C9 mutation-site catalogue, bowler-identity write sites in `score_manager.py`:
- `_finalize_over_credit` / `_release_bowler_lock_on_over_end` — emitter of `BOWLER-LOCK-RELEASED reason=over_end_credit_complete`. Candidate **A**: defer the scalar clear until after `_apply_wicket_fall_only` returns when both fire in the same frame.
- `_apply_wicket_fall_only` (score_manager.py:5328) — current bowler-read site. Candidate **B**: re-source bowler from `BOWLER-OBSERVE.leader` snapshot at dispatch time.
- Candidate **C**: dual-source consensus — prefer Surface A if non-empty, else Surface B. Safest under §12.3 dual-state-write semantics: doesn't change the canonical path, only fixes the cleared-too-early window.

Site selection deferred to the empirical phase. Static-falsification of A vs B vs C can be done first (zero behavior change) using §7.2 gate 1 (predicate trace).

### §2.5b Phase-2.5 — D1-prelim static-falsification verdicts (scratch)

**Call-ordering ground truth** (read of `score_manager.py` HEAD `85b3169`, no behavior change). Within the over-rollover branch of the SM event handler, when a WICKET event coincides with `is_over_change=True`:

1. Lines 5877–5946 — append W token to `this_over`, archive the completed over, reset per-over counters.
2. Lines 5947–5963 — d0df7b4 comment block citing L2-Slim Narine 3.1 regression (the load-bearing rationale for the next two lines).
3. **Line 5965 — BW07: `self.bowler_name = None`** (C9 catalogue site).
4. Line 5968 — `scoreboard._inn["current_bowler"] = None` (second surface clear).
5. Lines 5969–5978 — emit `BOWLER-LOCK-RELEASED reason=over_end_credit_complete prev_bowler=<value>`.
6. Lines 6060–6063 — strike rotation (`is_over_change` flip).
7. **Line 6074 — `_apply_wicket_fall_only(event, frame)`** which at the C19A3 emission point (line 5343) reads `self.bowler_name` — now `None`.

The em-dash sentinel is statically guaranteed under this call ordering whenever a wicket falls on the 6th legal ball of an over. C9 catalogue's BW07 row anticipated this exact site as architecturally significant (*"relevant for B-θ over-boundary if/when that returns to the engineering queue"*); H-D1 reaches it via the γ-bundle FAIL × wicket-frame correlation rather than the retired B-θ static cascade-root path. **Sub-finding S3 — methodology cross-validation: two independent investigation paths converge on the same C9 mutation site.**

**Candidate A — defer the BW07 clear until after `_apply_wicket_fall_only` returns** in WICKET-coincident over-rollover frames. Restructure: gate lines 5965–5978 behind `event["type"] != "WICKET"`; if WICKET, perform the clear + lock-released emission AFTER line 6074 returns. Gate 1: predicate trace differentiates — `BOWLER-LOCK-RELEASED frame_id` would shift to follow WICKET-ATTRIB instead of preceding it (currently both at the same frame_id). Falsifiable. Gate 2: covers F400 (over 5 close) + F679 (over 8 close). Gate 3: cross-fixture regression preservation — BW07's purpose per d0df7b4 comment is to prevent the next frame's `_accumulate_stats_from_event` from miscrediting the new over's first ball; deferring by ~9 lines within the SAME `_apply_event` invocation does NOT cross a frame boundary, so the L2-Slim Narine 3.1 case stays closed. **Survives gates 1/2/3.** Risk profile: highest of the three — touches load-bearing over-end-credit timing, explicit cross-reference to d0df7b4 + L2-Slim regression citation that this code section was added to fix.

**Candidate B — re-source `_apply_wicket_fall_only`'s bowler read from BOWLER-OBSERVE tracker LEADER** instead of `self.bowler_name`. Site: C19A3 emission at line 5343 + any pre-emission bowler read inside the function. Per C9 catalogue, the tracker writes via BW08 (`test_pipeline.py:7220+` async on_lock callback); the ConfidenceTracker instance must be exposed read-side to the SM. Gate 1: predicate trace differentiates — `trace_beta_sm_wicket_dispatch.bowler` field switches from `None` (under em-dash) to `'Kartik Tyagi'` / `'Cameron Green'` at F400 / F679 on next replay. Falsifiable. Gate 2: F400/F679 covered; F855/F1017 already had `self.bowler_name` aligned so changing the read source to LEADER produces identical output for those frames. Gate 3: tracker LEADER authority depends on LOCKED state. Empirical: F401 still shows TYAGI LOCKED with score=0.01 — LOCK survives past the BW07 clear, so the tracker read would return Tyagi at F400 + the dispatch frame. F679 same pattern (Green LOCKED at F676 + F679). **Survives gates 1/2/3.** Risk profile: medium — changes canonical bowler-read source for wicket-dispatch; tracker LEADER staleness in non-LOCKED states is a theoretical regression vector (mitigated by gating the read on `LOCKED` state, which is the tracker's own canonical flag).

**Candidate C — dual-source consensus inside `_apply_wicket_fall_only`**: `bowler = self.bowler_name or _bowler_tracker_leader_if_locked()`. Surface A canonical when populated; Surface B (tracker LEADER) fallback only when A is empty. Gate 1: predicate trace differentiates — `trace_beta_sm_wicket_dispatch.bowler` is `'Kartik Tyagi'` at F400 + has a new `bowler_source` field discriminating `sm_scalar` vs `tracker_fallback`. Falsifiable. Gate 2: F400/F679 covered via fallback; F855/F1017 still hit Surface A canonical (`bowler_source=sm_scalar`). Gate 3: lowest regression risk of the three. Canonical path unchanged when Surface A is populated → no behavioral change for any non-em-dash wicket frame. Fallback only activates in the empty-A window. Doesn't restructure over-end-credit timing. **Survives gates 1/2/3.** Risk profile: lowest.

**Verdict — Candidate C selected for D1-fix.** All three survive static gates 1/2/3, but C minimizes the regression-risk surface: it touches one read site inside `_apply_wicket_fall_only`, doesn't restructure the BW07 timing, and reduces to a no-op on mid-over wickets. Architecturally aligned with §12.3 dual-state-write framing (prefer Surface A, fall back to Surface B). Predicted-flip claim from §2.3 remains unchanged: FAIL×4 → FAIL×2 on `trace_gamma_bowler_w_increment_on_dispatch` on next DCKKR replay, with F855/F1017 still failing pending H-D2-Layer-1 resolution of the dismissed-name corruption.

**Sub-finding S4 — falsification budget unconsumed.** Phase-2.5 was zero-cost: read-only inspection of `score_manager.py` lines 5877–6074 + C9 catalogue row BW07. No empirical replay required. Budget cap remains 0/5 consumed for the D defect-class chain.

### §2.5 Static-falsification candidates ruled out

- *"BOWLER-OBSERVE leader is unreliable at over-end."* Falsified by F400 (Tyagi LOCKED with score=0.02 at F396, 0.02 at F400, 0.01 at F401) and F679 (Green LOCKED with score=0.57 at F676, 0.48 at F679). Tracker holds across the release; the empty scalar is the divergence, not tracker noise.
- *"Em-dash is purely a UI render artifact."* Falsified by `pipeline.current_bowler` snapshot at F400 — the em-dash is in the trace `pipeline` payload, not just the WebSocket render. Surface A is genuinely empty at the SM-level read, not just at the build_full_payload bottleneck.
- *"Wicket falls before the over-end-credit path fires, so the order argument doesn't apply."* Falsified by C9 catalogue showing `_finalize_over_credit` and `_apply_wicket_fall_only` both reachable in the same SM tick when the wicket is on the over's final legal ball (Obs 7 confirms wicket fell on 4.6 → over 5.0 boundary → F400 frame).

---

## §3 H-D2 — striker fallback monoculture (now: scout/event-construction root)

### §3.1 Mechanism

WICKET-ATTRIB always reads `scoreboard.striker` as the dismissed-batter identity (log signature *"Dismissed batter set from scoreboard striker"* on 5/5 events). This was originally framed as a dispatch-handler P2/P3 ordering bug. **Refined per §3.3 below**: the actual root is upstream — Scout never emits a structured `dismissed` field, so the dismissal handler has no P2 payload to consult. P3 monoculture is **forced by the input boundary**, not by the dispatch-side ordering.

When the rotation-lock-starvation root has corrupted `scoreboard.striker` (Obs 2/3/9 documented monotonic drift), the dismissal handler reads the corrupted pointer and credits the wrong batter to FOW. F400/F679 happen to attribute correctly only because the rotation pointer happened to be aligned at those wicket frames; F855/F983/F1017 collide with rotation staleness.

### §3.2 Evidence anchors

- F400 / F679 — P3 read, name correct (rotation happens to be aligned).
- F855 — P3 read returns 'Pathum Nissanka'; cricket truth Rizvi (Obs 16). Scout strip shows `PATHUM > RIZVI 46 28 3 7` (the `>` marks striker as Pathum — also stale per upstream rotation root).
- F983 — P3 read returns 'Sameer Rizvi'; cricket truth Nissanka (Obs 18). Striker-path dismissal (POST-WICKET-ROTATION rotated Stubbs in). Sub-finding S1: this wicket emits no `ball_event.type == 'WICKET'`, so the γ-bundle currently misses it.
- F1017 — P3 read returns 'Axar Patel'; cricket truth ≠ Patel (Obs 21 confirms Axar is still at the crease at 11.5).

### §3.3 Gate-6 precondition — scout dismissed-field absence

Empirical check on `scout_raw.jsonl` (±6 frames of each wicket): **no structured `dismissed` field on any of the 5 wicket-bracket frames**. Wicket signal arrives as:
- F398 / F677 / F678 — `VISIBLE_TEXT: WICKET` (pure marker, no identity)
- F400 — `TYAGI 4 1 1 4 W 1-10 1` (bowler-card with W flag; no dismissed name)
- F855 — `NARINE 1-14 1.5` (bowler-card with W increment; no dismissed name)
- F983 — `AXAR STUBBS 0 0 0 1 LAST 35 BALLS RUNS 41 WICKETS 4` (new pair already on field; previous batter implicit)
- F1017 — `ANUKUL 2-27 2.5 ... 4 W+WD WD 1 2 W` (bowler-card + ball symbols)

The dismissed batter's identity is therefore **derivable but not emitted** from Scout. P3 monoculture at the handler is structural under this Scout schema.

### §3.4 Predicted-flip claim (conditional on §3.3)

H-D2 predicted-flip splits into two layers depending on the fix locus:

**Layer 1 — derive `event.dismissed` upstream of the dismissal handler.** Construct `event.dismissed` in the event-builder from cross-signals already in the Scout payload:
- previous-frame striker name minus current-frame at-the-crease pair (set difference of length 1), OR
- bowler-card W-increment with a `_BOWLER_CREDITED_DISMISSALS` dismissal-mode hint cross-referenced against the most-recently-faced batter from STRIKER-OBSERVE.

Predicted flip: `trace_gamma_fow_name_matches_striker_at_wicket` continues to PASS (internal invariant); cricket-truth FOW attribution flips for F855/F983/F1017 because the derived `event.dismissed` overrides the corrupted striker pointer.

**Layer 2 — fix the upstream rotation-lock-starvation root itself.** Even with H-D2-Layer-1 in place, the rotation pointer remains corrupted for the live-state batter-card and partnership-card surfaces (Obs 2/3/9). A separate fix at `score_manager.py:4295-4325` (deterministic-rotation override, per Obs 2 hypothesis) addresses the broader cascade.

Layer 1 alone closes the FOW-name surface. Layer 2 alone (without Layer 1) does NOT close FOW-name because the WICKET-ATTRIB log still reads from `scoreboard.striker` — fixing the rotation pointer fixes the live-state error but doesn't change the dispatch-time read. **Layer 1 is the load-bearing wicket-correctness fix; Layer 2 is the load-bearing live-state-correctness fix.** They are non-overlapping in surface coverage.

### §3.4b Phase-2.5 — D2-prelim cross-fixture scout-dismissed-field absence (scratch)

**Cross-fixture survey** of `scout_raw.jsonl` across four substantive captured deliveries (read-only, zero behavior change). For each frame, check `raw_response` for any structured `dismissed` / `dismissed_batter` field-style token; tally against wicket-signal frames (broad match: `WICKET` / `wicket` / `DISMISSED` substrings, intentionally over-inclusive to harden the absence-claim against under-counting).

| Fixture | Frames | Wicket-signal frames | `dismissed`-field present |
|---|---|---|---|
| `validate_gtrr_20260520_180715` | 841 | 51 | **0** |
| `validate_dckkr_20260521_155356` | 749 | 64 | **0** |
| `validate_dckkr_20260521_070545` | 618 | 49 | **0** |
| `validate_20260520_114437` | 415 | 18 | **0** |
| `validate_20260513_194442` | 10 | 0 | n/a |

**Universal absence: 0/182 wicket-signal frames** across 4 substantive fixtures. The DCKKR-only baseline at §3.3 (0/5 wicket-anchor frames) is now hardened to a cross-fixture invariant: the Scout VLM, as currently prompted, **never** emits a structured `dismissed` / `dismissed_batter` field on any frame in any captured fixture. The absence is a **property of Scout's prompt/output schema**, not a per-fixture artifact.

**H-D2-Layer-1 predicted-flip claim at §3.4 + §6 — locked.** The gate-6 precondition holds cross-fixture; the dispatch handler can never have a P2 (`event.dismissed`) to consume under the current Scout schema. The fix must therefore land at one of two surfaces:

- **§3.5 Layer 1a — event-builder downstream of Scout** (current §3.4 framing). `_derive_dismissed_name` constructs `event.dismissed` from cross-signals already in the Scout payload (previous-frame STRIKER-OBSERVE minus current-frame at-the-crease pair; bowler-card W increment cross-referenced with most-recently-faced batter).
- **§3.5 Layer 1b — Scout prompt schema extension**. Add a `dismissed_batter` slot to Scout's structured-output JSON. Higher-friction (prompt-eval regression sweep) but cleaner architecturally — closes the contract gap at the source.

These are **non-overlapping fixes**: Layer 1a closes the gap downstream from Scout (works under current Scout schema); Layer 1b closes the gap at Scout's contract boundary (changes the schema). Either one independently flips `trace_gamma_w_symbol_at_wicket` FAIL×2 → PASS + cricket-truth FOW on F855/F983/F1017. Layer 1a is the lower-friction first step; Layer 1b becomes redundant once Layer 1a holds (downstream derivation is canonical) but remains architecturally cleaner if pursued in parallel.

**Sub-finding S5 — Scout-contract gap.** The universal absence is a Scout-side contract gap distinct from the rotation-lock-starvation root the workstream-D scope was promoted on. It surfaces as **two independent workstream surfaces**:

1. **D2-Layer-1a (downstream derivation)** — covered by this memo; closes the immediate γ-bundle FAIL.
2. **Scout-prompt-extension (upstream contract)** — separate workstream candidate; closes the contract gap. Out of D-scope; tracked here as a forward reference for a future C-commit + memo (placeholder: `scout_dismissed_contract_extension.md`).

The §0 framing ("rotation-lock-starvation root that causes both batter-striker AND bowler-identity pointers stale") is now **architecturally precise**: the root is two-layered. The bowler layer (H-D1) was fully on the SM side (closed at C28). The batter layer (H-D2) is two-sourced — SM dispatch reads `scoreboard.striker` because Scout never gave it a `dismissed` field to read. **D-scope retains Layer 1a; Layer 1b is split off as a Scout-contract surface.**

**Sub-finding S6 — methodology cross-validation extends.** S3 documented H-D1's convergence with the retired B-θ investigation on C9 BW07. S6 extends that pattern: the §3.3 single-fixture absence claim (DCKKR 0/5) was sufficient to motivate H-D2-Layer-1's predicted-flip framing, but the cross-fixture survey hardens it from "fixture-anchored hypothesis" to "Scout-schema invariant." **The S3 pattern (predicate-trail static-falsification at zero empirical cost) reproduces at S6, confirming the methodology's transferability across hypothesis types** (H-D1 was an SM-internal mechanism; H-D2 is a Scout-contract gap; same audit pattern produced both verdicts).

**Sub-finding S7 — falsification budget unconsumed (cumulative).** D-chain empirical-falsification budget: 0/5 still. Phase-2.5 D2-prelim was read-only across 5 scout dump files (~2.6k total frames surveyed); zero replay execution. The 5-empirical-falsification cap per C9 §11 + C10 §1.2 remains intact for the D defect-class chain across both hypotheses + sub-findings.

### §3.4c Phase-2.5 — D2-fix predicate-trail; Signal 1 falsified (scratch)

**Static predicate-trail** through `validate_dckkr_20260521_155356.jsonl` at the 3 live-era wicket frames (read-only, zero behavior change). Grep window ±10 around F855 / F983 / F1017 across `STRIKER-OBSERVE`, `NON-STRIKER-OBSERVE`, `STRIKER-WRITE`, `STRIKER-SM-BROADCAST-DISAGREES-DETERMINISTIC`, `STRIKER-IDENTIFY-FALLBACK-INVOKED`, `STRIKER-ALIGN-FALLBACK`, `POST-WICKET-ROTATION`.

**F855 (cricket: Rizvi dismissed; pipeline: Nissanka).**
- F845–F854 — striker_tracker `LOCKED` on `Pathum Nissanka` (wrong); non_striker_tracker `LOCKED` on `Sameer Rizvi`.
- **F854 smoking gun** — `STRIKER-SM-BROADCAST-DISAGREES-DETERMINISTIC method=broadcast_first_name broadcast='Sameer Rizvi' deterministic='Pathum Nissanka' — keeping deterministic`. The broadcast signal correctly identified Rizvi as striker; a deterministic-rotation override kept the tracker on Nissanka.
- F855 POST-WICKET-ROTATION: `non 'Pathum Nissanka' dismissed`.
- **Tracker LEADER is NOT an independent oracle** — corrupted with the same name as the SM pointer, via the same upstream override decision.

**F983 (cricket: Nissanka dismissed; pipeline: Rizvi).**
- F983 STRIKER-OBSERVE: cand=`Axar Patel` leader=`Axar Patel` state=`TENTATIVE` (broadcast updating to new pair post-Stubbs-walked-in).
- F983 NON-STRIKER-OBSERVE: cand=`Tristan Stubbs` leader=`Sameer Rizvi` state=`LOCKED` (LEADER permanently stale on the already-dismissed-per-pipeline Rizvi).
- F983 STRIKER-ALIGN-FALLBACK: `striker_ref='Sameer Rizvi', non_ref='Tristan Stubbs', ext_batter_names=['Axar Patel', 'Tristan Stubbs']` — broadcast at-the-crease pair has already rotated to {Axar, Stubbs} while pipeline's internal pair stayed {Rizvi, Stubbs}.
- Cricket-truth dismissed Nissanka is **not in pipeline's pre-F983 at-the-crease set** (F855 already removed him per the misattribution). F983 is structurally underivable from local pipeline state alone.

**F1017 (cricket: Axar still at crease per Obs 21; pipeline: Patel dismissed).**
- F1010–F1012 — striker_tracker leader=`Tristan Stubbs` state=`LOCKED`, candidate=`Axar Patel` score=2.18→2.01. Tracker LOCKED on Stubbs from F990 onward.
- F1017 STRIKER-WRITE: `non Axar Patel->None`. POST-WICKET-ROTATION: `non 'Axar Patel' dismissed`.
- No actual cricket wicket — **phantom-wicket detection**, qualitatively different defect class.

### §3.4c.1 Sub-finding S8 — Signal 1 falsified; deterministic-rotation override is the true root

Trackers are NOT independent of the rotation-lock-starvation root; they are downstream of the same root via the deterministic-rotation override at the `STRIKER-SM-BROADCAST-DISAGREES-DETERMINISTIC` decision site. The "broadcast disagrees → keep deterministic" gate is the **BW07-analog for the striker side** — it overrides the broadcast signal that would have given the correct dismissed name at F855.

**Reformulated fix surface:** not Signal 1 (tracker LEADER cross-check); the actual surface is the **deterministic-rotation override emission site**. The fix is a **context-aware gate inversion** — broadcast wins when pending-wicket-attribution. Structurally a single-site change, but the "wicket-pending" signal must be in scope at the override site (D2-fix structural-surface check pending).

### §3.4c.2 Sub-finding S9 — F855 → F983 cascade closure

F855 misattribution makes F983 structurally underivable from local pipeline state alone. **Closing F855 auto-closes F983 via cascade closure** — F983 needs no independent fix surface.

This is the **second instance of the F1-session cascade-closure-via-one-edit pattern** (meta-finding #1 in the Architecture_HANDOFF §0.7 methodology track record). The F1 pattern: one upstream fix closes N downstream symptoms when the downstream surfaces are structural consequences of the upstream defect. Here: closing the F855 striker-attribution misroute prevents pipeline from "removing" Nissanka from the at-the-crease set, leaving him available for F983's dismissed-name derivation. Same mechanical pattern, different defect surface.

### §3.4c.3 Sub-finding S10 — F1017 phantom-wicket; workstream surface E candidate

F1017 emits POST-WICKET-ROTATION against cricket truth (Obs 21 broadcast strip confirms Axar Patel at-the-crease at replay-end). This is **phantom-wicket detection**, not misattribution. The defect class is qualitatively distinct from F855/F983:
- F855/F983 — real cricket wicket, wrong name attributed.
- F1017 — no cricket wicket, fabricated dismissal event.

Out of H-D2-Layer-1a scope. Tracked in `Architecture_HANDOFF.md` §0.6 deferred-work index as **workstream surface E candidate (phantom-wicket detection)** — parallel to S5's Scout-contract-gap split into a separate workstream surface. Needs its own audit chain: root-localization on the wicket-event-detection path (`ball_detector.detect`, or upstream wicket-signal aggregation), not the dismissed-name derivation path that H-D2 lives on.

### §3.4c.4 Architectural note — §12 catalogue extension candidate

`STRIKER-SM-BROADCAST-DISAGREES-DETERMINISTIC` override is structurally the **fourth instance of the dual-state-write defect class** catalogued in `sm_as_orchestrator_design.md` §12 (after F-α-shadow / F1-B-ε / B-η-FC5 / D1-BW07-bowler-em-dash). Two surfaces, weaker invariant (deterministic-rotation override) decision-flips a stronger invariant (broadcast-derived consensus). Same §12.3 signature.

Candidate for §12 catalogue extension in a follow-up commit (parallels C20's surface_pair_defect_class_family.md skeleton extension pattern). Out of C30 scope; tracked here as a forward reference.

### §3.4c.5 Predicted-flip claim reformulation (locked)

Original §3.4 / §6 H-D2-Layer-1a: *"Layer 1 flips `trace_gamma_w_symbol_at_wicket` FAIL×2 → PASS + cricket-truth FOW on F855/F983/F1017"*.

**Reformulated:** H-D2-Layer-1a flips `trace_gamma_w_symbol_at_wicket` FAIL×2 → PASS + cricket-truth FOW on:
- **F855** — direct fix at the deterministic-rotation override site (context-aware gate inversion: broadcast wins when pending-wicket-attribution).
- **F983** — closes automatically via S9 cascade closure (no independent fix surface required).
- **F1017** — split off per S10 (workstream surface E phantom-wicket detection; out of D-scope).

### §3.4c.6 Falsification-budget impact

0/5 empirical cap unchanged. Signal 1 falsification + sub-findings S8/S9/S10 were all derived via static predicate-trail through the existing trace file (zero empirical cost per the C10 §1.2 static-vs-empirical distinction). The D-chain remains at 0/5 consumed across both hypotheses + 4 sub-findings (S1, S3, S4, S5, S6, S7, S8, S9, S10).

### §3.4d Phase-2.5 — D2-fix structural-surface check; override gate ruled out (scratch)

**Predicate-trail** at `score_manager.py:4411–4441` (the `STRIKER-SM-BROADCAST-DISAGREES-DETERMINISTIC` emission site inside the private `_identify_and_set` method). Single call site at `score_manager.py:3408`, inside the steady-state branch (`d_score == d_wickets == d_overs == 0`). The gate fires on the preceding steady-state frame, never on the wicket frame itself.

**Gate structure** (lines 4411–4441):

```
if new and new != self.striker:
    if self.striker is not None:          # gate: locked-deterministic wins
        log.info(... "keeping deterministic")
        _trace.record(tag=STRIKER-SM-BROADCAST-DISAGREES-DETERMINISTIC, ...)
    else:                                  # else: cold-start, accept broadcast
        self._set_slot_pair(new, ...)
```

**Gate rationale** (lines 4413–4426): designed to prevent broadcast-leading-by-one-frame from flipping `self.striker` to the post-wicket striker before the wicket-attribution logic runs. Citation: `test_sm_derivation_ledger.py` ball 4.6 DC vs KKR fixture — the broadcast indicator advanced to the post-wicket-and-EOO-swap striker (Nissanka) mid-frame, which would have flipped `self.striker` to Nissanka before wicket-attribution could identify Rahul as dismissed.

### §3.4d.1 Discriminator analysis — non-discriminable predicate signature

Both the DC-vs-KKR ball-4.6 regression case AND the DCKKR F855 case arrive at the same emission site with the **same predicate signature**:

| | DC-vs-KKR ball 4.6 (regression case) | DCKKR F855 (this investigation) |
|---|---|---|
| `new` source | `broadcast_first_name` | `broadcast_first_name` |
| `new ≠ self.striker` | yes | yes |
| `self.striker is not None` | yes | yes |
| Frame-type | steady-state (`d_*==0`) | steady-state (`d_*==0`) |
| Next-frame d_wickets | ticks (wicket frame follows) | ticks (wicket frame follows) |

The two cases differ in the **truth-value of the broadcast signal**, not in any locally-observable predicate:

- **Regression case** — broadcast is LEADING by 1 frame (showing post-wicket striker before pipeline detects the d_wickets tick). Deterministic is correct. **Gate must keep deterministic.**
- **DCKKR F855 case** — broadcast is CURRENT (correctly showing pre-wicket striker). Deterministic is corrupted by rotation-lock-starvation drift accumulated over many earlier frames (Obs 2/3/9 documented monotonic batter-ball drift). **Gate must accept broadcast.**

**Discriminating requires one of:**
- **Lookahead** (next-frame d_wickets value) — not in scope; requires deferral state machine.
- **Persistence count** (broadcast has shown this name for N consecutive frames) — not in scope; requires broadcast-name history plumbing.
- **Drift detection** (deterministic provably out-of-sync with cumulative balls-faced delta) — partial signals in scope; requires multi-frame accumulated state.

All three are structural plumbing equivalent to D1's β. **Override gate is plumbing-required, NOT single-site.**

### §3.4d.2 Gate is load-bearing protection — not scar tissue

Per §3.4d, the override gate prevents a known regression (DC-vs-KKR ball 4.6 → Rahul-dismissed-attribution). The gate is NOT scar tissue. Removing it without a discriminator regresses the original case. **Ruling out as a D2 fix surface; the next move at this site is plumbing (D2-Layer-2 candidate), not single-site retries.**

### §3.4d.3 Alternative fix surface confirmed — WICKET-ATTRIB at test_pipeline.py:13062–13068

The H-D2 surface originally identified in the §3.5 structural-surface check (pre-C30) remains correct under the C30 reformulation:

- Wicket-pending context is **IMPLICIT** (we're inside the `ball_event.type in ("WICKET", "WICKET_LATE")` block at `test_pipeline.py:13062`).
- `card["broadcast_striker"]` is in scope at the site (`card` is the current frame's extracted card data, passed into the event-handling block).
- Regression-case rationale (don't flip `self.striker` prematurely) is **independent of this site** — at WICKET-ATTRIB the wicket is already confirmed; reading broadcast for the dismissed-name attribution does not flip the striker pointer.
- Override gate's discriminator problem is **bypassed entirely** — different code path, different invariant.

Fix shape: before the `ball_event["dismissed"] = _striker_this_ball` write at `test_pipeline.py:13063`, check whether `card.get("broadcast_striker")` disagrees with `_striker_this_ball`; if so, prefer broadcast for the dismissed-name attribution. Emit `WICKET-ATTRIB-BROADCAST-OVERRIDE-APPLIED` trace tag on the override branch (gate-6 instrument).

### §3.4d.4 Sub-finding S11 — signal/site decoupling (methodology meta-finding)

The C30 predicate-trail moved the predictive signal from "tracker LEADER cross-check" (§3.4 / §3.4c S8 falsified Signal 1) to "broadcast-striker field". The fix site, however, did NOT move — it stayed at `test_pipeline.py:13062–13068` from the original §3.5 structural-surface check. **Signal/site decoupling: predicate-trail reformulation can move the predictive signal without moving the implementation surface.**

Promoted to methodology track record (`Architecture_HANDOFF.md` §0.7 candidate). Transferable across future audits where the predicate-trail produces a "wrong signal, right site" finding. Pattern: when the original structural-surface check identifies a fix site by code-context (not by signal source), a later signal reformulation does not invalidate the site — only the consumed signal at that site needs updating.

### §3.4d.5 Sub-finding S12 — non-discriminable-predicate-signature defect-class

When two cases (one regression-protected, one investigation-target) arrive at the same site with the same observable predicate signature, **single-site fix is structurally impossible without plumbing**. The discriminator must come from outside the local predicate scope (lookahead, history, accumulated drift).

This is a transferable audit-pattern entry, parallel to the dual-state-write defect class catalogued in `sm_as_orchestrator_design.md` §12. Candidate for §12 catalogue extension as a peer entry (the dual-state-write pattern is "two surfaces, one weaker invariant decision-flips a stronger one"; the non-discriminable-signature pattern is "two cases, one predicate signature, plumbing-required to distinguish"). Out of C30b scope; tracked here as a forward reference.

### §3.4d.6 Deferred-work index update

`score_manager.py:4411` override gate is explicitly ruled out as a D2 fix candidate. Re-investigation authorized only if WICKET-ATTRIB fix at `test_pipeline.py:13063` proves insufficient on next replay (equivalent to consuming the first empirical-falsification slot in the D chain's 5-cap budget; see §3.4d.7).

### §3.4d.7 Falsification-budget impact

0/5 empirical cap unchanged. Structural-surface check was zero-cost static (predicate-trail through existing code + comment-block read). The D-chain remains at 0/5 consumed across both hypotheses + 6 sub-findings (S1, S3, S4, S5, S6, S7, S8, S9, S10, S11, S12 — count expanded; all static).

### §3.5 Candidate fix sites

- **Layer 1 (event-builder).** Per C9 catalogue, event construction sits at `apply_scorer_decision` (`test_pipeline.py:4517`) upstream of `_apply_wicket_fall_only`. Insert a `_derive_dismissed_name` step that consumes Scout's WICKET marker + adjacent STRIKER-OBSERVE / BATTING_TEAM-OBSERVE records and emits `event.dismissed`.
- **Layer 1 (Scout prompt schema).** Alternatively, extend the Scout VLM schema to request a dismissed-batter field. Higher-friction — needs prompt-eval regression — but cleaner architecturally.
- **Layer 2 (rotation root).** Deferred to a separate sub-investigation. Out of D-scope per §0; tracked here as a co-located reference only.

---

## §4 Hypothesis independence proof (why bundle, not collapse)

H-D1 fires at `BOWLER-LOCK-RELEASED reason=over_end_credit_complete` (over-boundary timing condition) and operates on the bowler-name surface.

H-D2 fires at WICKET-ATTRIB dismissal-name resolution (every-wicket condition) and operates on the dismissed-batter-name surface.

Collapsing them would require either:
- A shared mechanism (refuted by §1.4 empirical: F855/F1017 have H-D2 surface failures with no H-D1 em-dash; F400/F679 have H-D1 em-dash but H-D2 surface accidentally passes because rotation was aligned).
- A shared fix site (refuted by §2.4 vs §3.5: bowler-lock release path vs event-builder are architecturally non-adjacent).

**Hypothesis bundle is the correct container.** Each shape closes a disjoint subset of γ-bundle failure modes:
- H-D1 closes `trace_gamma_bowler_w_increment_on_dispatch` for the 2 over-boundary wickets.
- H-D2-Layer-1 closes `trace_gamma_w_symbol_at_wicket` (indirectly, via correct dismissed name → correct W-symbol commit) and the FOW-name cricket-truth surface (which is currently untested by the γ-bundle — `trace_gamma_fow_name_matches_striker_at_wicket` is the internal-consistency invariant, PASSes by construction even when cricket-wrong).

---

## §5 Sequencing — H-D1 vs H-D2 commit order; C23b unblock condition

### §5.1 Recommended order

1. **D1-prelim.** Static-falsify Candidates A/B/C of §2.4 at zero behavior change. Pick the survivor.
2. **D1-fix.** Land the bowler-name re-source. Pre-commit Layer 1.5 + γ-bundle on captured trace must hold. Expected: `trace_gamma_bowler_w_increment_on_dispatch` FAIL×4 → FAIL×2 on next replay.
3. **D2-prelim.** Confirm §3.3 empirical (Scout dismissed-field absence) on a second replay (any fixture). If a fixture exists where Scout DOES emit `dismissed`, H-D2 Layer 1 candidate becomes "wire dispatch-handler to prefer Scout-emitted P2 when present" — narrower scope.
4. **D2-fix (Layer 1).** Land the `_derive_dismissed_name` event-builder step. Expected: `trace_gamma_w_symbol_at_wicket` FAIL×2 → PASS, cricket-truth FOW attribution flips for F855/F983/F1017.
5. **C23b.** Unblocked once D1+D2 land. Re-test `trace_gamma_bowler_w_increment_on_dispatch` end-to-end with correctly-resolved dismissed name + correctly-resolved bowler name. Expected: FAIL×2 → PASS.
6. **S1 (assertion gap).** Independently of D1/D2, extend `assert_bowler_w_increment_on_dispatch` to detect striker-path dismissals (key on WICKET-ATTRIB or POST-WICKET-ROTATION as a fallback signal when `ball_event.type == 'WICKET'` is absent). Surfaces F983-class wickets to the γ-bundle.

### §5.2 C23b unblock condition

C23b lands cleanly once D1 (bowler resolves to non-em-dash) AND D2-Layer-1 (dismissed name resolves to cricket-truth, not stale-striker) both hold. C23b cannot land standalone because the wicket-dispatch path it tightens reads both pointers and would inherit em-dash failures.

---

## §6 §7.2 7-gate audit application

| Gate | H-D1 application | H-D2 application |
|---|---|---|
| 1 — predicate trace | `BOWLER-LOCK-RELEASED reason=over_end_credit_complete && WICKET-ATTRIB at same frame_id` → 2/2 over-boundary wickets in capture; 0/2 mid-over wickets. | `WICKET-ATTRIB.raw_message LIKE "%scoreboard striker%"` → 5/5 wickets. `scout_raw.jsonl.dismissed` field → 0/5 wickets. |
| 2 — predicate completeness | All 4 ball_event.WICKET frames covered; F983 striker-path not covered (sub-finding S1). | All 5 WICKET-ATTRIB frames covered including F983. |
| 3 — cross-fixture preservation | Need replay on second fixture (GTRR or other) to confirm `over_end_credit_complete` timing reproducibility. Deferred to D1-prelim. | Need second fixture to confirm Scout schema (dismissed-field absent everywhere, or fixture-specific). Deferred to D2-prelim. |
| 4 — falsification budget | 0/5 empirical falsifications consumed so far (this memo authored from existing capture). | 0/5 empirical falsifications consumed. |
| 5 — static-falsification check | §2.5 — 3 candidates ruled out via static analysis. | §3.3 — falsified the original "ordering bug in handler" framing; refined to "scout/event-builder root". |
| 6 — predicted-flip claim | §2.3 — FAIL×4 → FAIL×2 on `trace_gamma_bowler_w_increment_on_dispatch`. | §3.4c.5 (reformulated post-Signal-1-falsification) — Layer 1a flips `trace_gamma_w_symbol_at_wicket` FAIL×2 → PASS + FOW cricket-truth on F855 (direct fix at deterministic-rotation override site) + F983 (S9 cascade closure). F1017 split off (S10 — workstream surface E candidate). |
| 7 — cross-fixture preservation post-fix | Re-run γ-bundle on archived GTRR + DCKKR captures + fresh replay. Both must hold. | Same. |

---

## §7 Open sub-questions tracked

- **Layer 2 rotation-root site.** §3.4 Layer 2 references `score_manager.py:4295-4325` per Obs 2 hypothesis. Static-analysis confirmation needed; tracked as `workstream_d2_rotation_root_layer2.md` placeholder (TBD next session if Layer 1 lands cleanly and live-state surfaces don't auto-flip).
- **S1 striker-path assertion gap.** §1.2 — extending `assert_bowler_w_increment_on_dispatch` to detect F983-class wickets needs a careful trigger predicate that doesn't double-count when both `ball_event.type == 'WICKET'` and POST-WICKET-ROTATION fire on the same frame.
- **F855 vs Obs 16 cricket-truth verification.** §1.1 cricket-truth column is per Obs 16/18/21; broadcast-strip frame screenshots would harden the verification. Operator action.
- **C19A3 trace_beta replay validation.** Memo's predicted-flip claims at §2.3 and §3.4 assume next replay captures `trace_beta_sm_wicket_dispatch` payloads with `resolution_src`. Preflight tag-existence check (`scripts/preflight_validation_tags.sh`) confirms emission lives in code; only replay execution remains.
- **Layer 1b — Scout prompt schema extension (C29b candidate).** Tracked in `Architecture_HANDOFF.md` §0.6 deferred-work index. Closes the Scout-contract gap at the source by adding a `dismissed_batter` field to Scout's structured output. Non-overlapping with H-D2-Layer-1a; either independently flips `trace_gamma_w_symbol_at_wicket` + cricket-truth FOW. OUT of workstream D scope; candidate for a new workstream surface (E or similar). Empirical basis at §3.4b (0/182 wicket-signal frames across 4 fixtures).

---

## §8 Cross-reference index

- `Architecture_HANDOFF.md` §0 — C19–C24 session context, γ-bundle baseline.
- `surface_pair_defect_class_family.md` §2.5 — striker-pointer ⊥ FOW-name (H-D2 surface).
- `surface_pair_defect_class_family.md` §2.6 — FOW count ⊥ bowler-card W (H-D1 surface).
- `sm_as_orchestrator_design.md` §12.3 — dual-state-write structural family.
- `state_mutation_site_catalogue.md` (C9) — bowler-identity + striker-identity write sites.
- `temporal_coupling_investigation_brief.md` (C10) — methodology, §12.4 detection.
- `trace_and_detect_system_design.md` §3 — trace schema reference for C19A3 payload fields.
- `validate_dckkr_replay_observations.md` Obs 2/3/9/16/17/18/19/21 — empirical observation anchors cited per-hypothesis above.
- `files/tests/trace_session_assertions.py:460` — `assert_bowler_w_increment_on_dispatch` (γ-B3).
- `files/score_manager.py:5328` — C19A3 emission site for `trace_beta_sm_wicket_dispatch`.
