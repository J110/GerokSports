# Workstream Q — Targeted refactor to unify score state at SM as canonical owner (step-1 investigation)

Branch: `derive-not-detect`. Single docs commit. Architectural investigation memo (step-1 static analysis only — no production code edits this commit).

> Operator framing: WS-O.c step-2 STOP + WS-P step-3 saturation + WS-O.b V3 finding established that the score-domain dual-state-write surface is the architectural root behind two consecutive no-op patches (WS-O OA + WS-P P1) and the surviving balls 4.1-4.5 residue (3 E2 + 5 conservation). User-direction Option 2: targeted refactor to **invert** the current arrangement so SM owns score state canonically and `sb._inn["score"]` becomes the property view. WS-Q is the first attempt to apply the §12.5 **architectural remediation** (Shape C) to a confirmed dual-state-write site rather than landing a §12.5 narrow remediation.

---

## §1 Empirical anchor

1. **WS-O.c step-2 STOP finding** (`files/docs/investigations/workstream_o_c_pa_threshold_refinement_investigation.md`). PA-threshold refinement at `sb.set` cannot close the balls 4.1-4.5 residue without breaking L1.5: regression-rejection semantics at the sb.set bottleneck don't compose with downstream `this_over` derivation. The cascade root lives in `score_manager_derivation.py:210/382/495` (`delta_score = current.score - prior.score`) — a `delta` that silently absorbs sb-side rejections as zero-progress and then poisons `this_over_token` for the affected balls.
2. **WS-P step-3 saturation finding** (commit `b8c3c25` baseline; `52754c7` memo). Two consecutive squad-convention QA + QE patches landed empirical NO-OPs on DCKKR. Cascade root is in a different code path — the snapshotter's score read path also touches `sb._inn["score"]` directly, downstream of any SM-side defensive gate.
3. **WS-O.b step-2 V3 finding** (commit `ae2fe2f`-pred; SM-OA WARM-mode magnitude gate at `scoreboard.py:1216-1252`). Established the existing topology: `sm.score` is currently a `@property` reading `sb._inn["score"]` (score_manager.py:1709-1719). sb is the canonical store; SM is the view. PA gate at sb.set is the only invariant choke point; SM has none of its own.
4. **§12 catalogue 3rd instance** (`files/docs/investigations/sm_as_orchestrator_design.md` §12.2 row "B-η/FC5"). Score / overs / wickets split-commit at sb._tracker.confirmed vs sm.self.{score,overs} — the structural pattern this refactor closes.
5. **S33 instrumentation-aware methodology saturation**: three empirical no-ops in WS-O.c + WS-P + WS-O.b on the same defect class → the methodology has converged on its structural ceiling. Architectural refactor is the indicated next move.

---

## §2 Current architecture diagram — `sb._inn["score"]` as store, `sm.score` as @property view

```
                          ┌─────────────────────────────────────┐
   Scout extractor ───┐   │   SM (score_manager.py)             │
   _accept_initial ───┤   │   ┌───────────────────────────┐    │
   _accept_update ────┼──▶│   │ score = @property         │    │
   _handle_warm       │   │   │   ↳ reads sb._inn["score"]│    │
   commit_decision ───┤   │   │ score.setter              │    │
                      │   │   │   ↳ shadow: write fallback│    │
                      │   │   │   ↳ scoreboard None: write │    │
                      │   │   │     fallback              │    │
                      │   │   │   ↳ scoreboard attached:  │    │
                      │   │   │     delegate sb.set       │    │
                      │   │   └───────────┬───────────────┘    │
                      │   │               │ delegation         │
                      │   └───────────────┼────────────────────┘
                      │                   ▼
                      │   ┌────────────────────────────────────┐
                      └──▶│   SB.set("score", v, frame)        │
                          │   ┌──────────────────────────────┐ │
                          │   │ T20 ceiling (320)            │ │
                          │   │ chase ceiling (target+4)     │ │
                          │   │ WS-O.b PA magnitude gate     │ │
                          │   │   (balls*2.5 + 10)           │ │
                          │   │ regression-rejection (Δ<0)   │ │
                          │   │ jump guard (Δ>100)           │ │
                          │   │ ConsistentReadTracker        │ │
                          │   │   consensus                  │ │
                          │   └─────────────┬────────────────┘ │
                          │                 ▼                  │
                          │   sb._inn["score"] = v             │
                          └─────────────┬──────────────────────┘
                                        │
                                        ▼
                Downstream readers (37 files, ~110 sites):
                ─ snapshotter / UI (`score_manager.py:5208` snapshot field)
                ─ derivation (`score_manager_derivation.py:210/382/495`)
                ─ display state (`score_manager.py:5001`)
                ─ pipeline guards / state-recovery / poison-recal
                  (`test_pipeline.py` × ~80 sites)
                ─ direct dict writes BYPASSING sb.set:
                    S07 (state-recovery Phase-2) @ test_pipeline.py:3620
                    S10 (POISON-RECAL forced reset) @ test_pipeline.py:11099
                    SCORE-FORCE-RESET helper @ scoreboard.py:2137
```

**Structural signature** (matches §12.3 exactly): Surface A = `sb._inn["score"]` direct dict (permissive — accepts anything written); Surface B = `sb.set("score", …)` invariant-enforcing API (T20/chase/WS-O.b/regression/jump/tracker). The defect-producing path = any read of Surface A downstream of a Surface-A write that bypassed Surface B. Three confirmed bypass writers (S07, S10, SCORE-FORCE-RESET) + the `sm.score` setter cascade-rejection that returns silently from SM's perspective while `delta_score` keeps reading the old Surface-A value.

---

## §3 Reader enumeration (all `sb._inn["score"]` readers)

Total: **~110 reader sites across 37 files** (production + tests). Production-only breakdown:

| Category | Site count | Representative locations | Refactor impact |
|---|---|---|---|
| **R-CORE** SB internal reads (gates / snapshot / display) | 8 | `scoreboard.py:1258,2045,2136,4418,4712,4749,5001,5208` | Behind sb._inn property view — backward-compat via QA's bidirectional property |
| **R-SM** SM internal reads via `@property` | (via property) | `score_manager.py:1709-1719` | The property body changes (becomes a read from `sm._canonical_score`) |
| **R-SMD** SM derivation cascade | ~3 | `score_manager_derivation.py:210,382,495` (`current.score - prior.score`) | **Primary cascade closure target** — these are the WS-O.c residue actors |
| **R-MAIN** main loop bootstrap | 1 | `eyes/main.py:141` | Read-only — property view sufficient |
| **R-PIPE** test_pipeline.py production-loop reads (gates, snapshots, state-recovery, poison-recal, end-of-over, catch-up) | ~80 | enumerated above (`test_pipeline.py:2548…14870`) | Read-only — property view sufficient |
| **R-TEST** test fixtures (`test_recent_fixes.py`, `test_offline.py`, `tests/test_*.py`) | ~60 | various | Backward-compat via property — no test rewrites unless they assert internal invariants we change |

**Production-code reader count: ~92.** All survive the refactor IFF `sb._inn["score"]` remains a readable surface — i.e., QA's bidirectional property model. Direct mutation (`sb._inn["score"] = v`) sites are writers (§4), not readers.

---

## §4 Writer enumeration (all `sb._inn["score"]` writers + `sb.set` call sites)

Per `files/docs/investigations/state_mutation_site_catalogue.md` §C9.2 (score field) + this audit's grep pass:

| ID | Site | Mechanism | Bypasses sb.set? | Source authority | Refactor disposition |
|---|---|---|---|---|---|
| S01 | `score_manager.py:1755` (current line `~1755` — was `:1170` in C9 baseline) | `sb.set("score", iv, frame)` via SM setter delegation | No — uses sb.set | SM `_handle_warm` cadence → score setter | **Redirect**: SM `_handle_warm` writes through new `sm.set_score(value, source, confidence)` canonical API |
| S02 | `score_manager.py:2006` | `self.score = None` (reset path) | n/a — assigns via setter | `_reset` / innings transition | Redirect through `sm.reset_score()` (new) — None-passthrough preserved |
| S03 | `score_manager.py:3334` | `self.score = cached.get("score")` | n/a — assigns via setter | `hot_resume_from_cache` | Redirect — cache-source confidence tag |
| S04 | `score_manager.py:3421` | `self.score = card.get("score")` | n/a — assigns via setter | `_accept_initial` cold-start exit | Redirect — extractor-source confidence tag |
| S05 | `score_manager.py:3681-3682` | `self.score = int(self.score)` / `= 0` | n/a — coercion not advance | type-safety guard | NO-OP — coercion is idempotent |
| S06 | `score_manager.py:4794` | `self.score = card["score"]` | n/a — assigns via setter | `_accept_update` WARM path | Redirect — extractor-source confidence tag |
| S07 | `test_pipeline.py:3643` | `scoreboard._inn["score"] = int(cand["score"])` **DIRECT DICT WRITE — bypasses sb.set** | YES | Phase-2 state-recovery aggregator | **Redirect through `sm.set_score(…, source="state_recovery_phase_2", confidence="high")`** — invariant-aware bypass replacement |
| S08 | `test_pipeline.py:4822` | `sb.set("score", _proposed_score, frame)` | No | `commit_decision` scorer-decisions | Redirect through `sm.set_score(…, source="scorer_commit")` |
| S09 | `test_pipeline.py:9144` | `sb.set("score", _cu_si, frame_count)` | No | catch-up Scout response | Redirect through `sm.set_score(…, source="catchup_scout")` |
| S10 | `test_pipeline.py:11099` | `scoreboard._inn["score"] = None` **DIRECT DICT WRITE — bypasses sb.set** | YES | POISON-RECAL forced reset | Redirect through `sm.reset_score(source="poison_recal")` |
| S11 | `scoreboard.py:2137` (`force_reset_score` helper) | `self._inn["score"] = v` + `_tracker.confirmed["score"] = v` | YES (by design — recovery surface) | cold-start over-read recovery / state-recovery / poison-recal | Redirect through `sm.set_score(…, source="force_reset", confidence="override")` — preserves bypass semantics but goes through canonical API |
| S12 | `eyes/main.py:144` | `scoreboard.set("score", new, frame)` | No | main bootstrap | Redirect through `sm.set_score(…, source="main_bootstrap")` |
| S13 | `test_offline.py:147` | `scoreboard.set("score", int(extracted["score"]), i)` | No (test) | offline replay | Backward-compat via bidirectional property — no test rewrite |

**Production-code writer count: 12 sites.** Three of them currently bypass `sb.set` invariants entirely (S07, S10, S11). The refactor's value-add: all 12 route through a single canonical API where cricket-physics + confidence + cross-field validation lives.

---

## §5 `runs_off_bat` / `this_over` derivation cascade sites

Per `files/score_manager_derivation.py` (grep `current.score - prior.score`):

| Site | Line | Purpose | Cascade-failure mode (status quo) |
|---|---|---|---|
| D1 | `:210` | `delta_score = current.score - prior.score` inside §13.2 striker-derivation | Reads current sb._inn["score"]; if sb.set rejected the proposed value, `current.score` is the stale value and `delta_score = 0`. Striker credit stalls; runs_off_bat under-counts. |
| D2 | `:382` | `delta_score = current.score - prior.score` inside §13.3 wicket-derivation | Same failure mode — wicket-event credit reads stale sb value when sb.set regression-rejected the upstream proposal. |
| D3 | `:495` | `delta_score = current.score - prior.score` inside §14.2 `derive_this_over_token` | Same failure — `this_over_token` shows "0" (or "-") for balls where sb.set rejected the legitimate progression. **This is the WS-O.c residue actor.** |

**Cascade-site count: 3.** All three read `current.score` (resolved via the `sm.score` @property → `sb._inn["score"]`). All three exhibit the same failure mode: silent stale-state poisoning when sb.set's regression/PA gate rejects an upstream Surface-B proposal that Surface-A would otherwise have surfaced.

Refactor closure: if SM owns the canonical store and `sm.set_score` returns explicit accept/reject, the upstream writer (S01/S08/S09) sees the rejection and can re-derive (or defer). The derivation cascade reads the SM-owned canonical value, which is consistent with the gate decision. No more "Surface A accepted, Surface B silently rejected, delta reads stale Surface A" split.

---

## §6 Hypothesis enumeration

### QA — Pure inversion (`sm._canonical_score` is store; `sb._inn["score"]` is property over SM)

- **Mechanism**: New SM-owned scalar `sm._canonical_score`. `sb._inn["score"]` becomes a `property` on the `_inn` dict-like view (or `Scoreboard.__getitem__` shim on the `_inn` attribute) that reads from the bound SM. All current `sb._inn["score"] = v` direct writes become illegal (must route through SM); `sb._inn.get("score")` reads continue working transparently.
- **§7.2 gate-1 (defect-class fit)**: PASS — Surface A becomes a derived view of Surface B, closing the dual-state-write class for the score field.
- **§7.2 gate-2 (backward-compat)**: PARTIAL FAIL — `sb._inn` is currently a `dict`. Making one key a property requires either subclassing `dict` (fragile under copy/serialize) or replacing `_inn` with a custom Mapping (touches ~15 other fields' read paths). High blast radius. L2 ledger backward-compat at risk.
- **§7.2 gate-3 (fix-surface attribution)**: PARTIAL — fix surface is structurally correct but the Mapping replacement adds scope-creep risk to other primitive fields (overs, wickets, target, run_rate) not in this workstream's charter.
- **Status**: **FALSIFY** — gate-2 backward-compat risk too high for a single-workstream refactor; Mapping replacement is a larger architectural project.

### QB — Hybrid (sb._inn["score"] stays canonical store; all writes route through `sm.set_score` which validates then calls sb.set)

- **Mechanism**: Storage stays at `sb._inn["score"]`. New `sm.set_score(value, source, confidence) -> bool` API is the **only** legal write path. Internally calls cricket-physics + cross-field + confidence validation; if accepted, calls `sb.set("score", v, frame)` (preserving sb.set's existing T20/chase/tracker guards); if rejected, returns False without touching sb. Sb.set's PA/regression gates remain as defense-in-depth.
- **§7.2 gate-1**: PASS — eliminates the bypass writers (S07/S10/S11) by routing them through the validated API.
- **§7.2 gate-2**: PASS — `sb._inn["score"]` storage unchanged; all 92 readers + 13 tests survive byte-identical.
- **§7.2 gate-3**: PASS — fix surface = the canonical API + 13 writer-redirect lines + delete-cascade for now-orphan setter delegation. PIPELINE-DIRECT classification. L1.5 cases additive.
- **Cascade-closure prediction**: `sm.set_score` can apply cricket-physics regression rejection BEFORE sb.set (eliminating the silent-rejection cascade at D1/D2/D3). On rejection, the caller sees False and can fall through to consensus/retry. On acceptance, the value lands in sb._inn["score"] AND any SM-side mirror via the same call. WS-O.c residue closes (delta_score reads consistent state). WS-O.b PA stays as inherited defense-in-depth (mechanism unchanged; may simplify in step-2c cleanup).
- **Status**: **LEADING CANDIDATE.**

### QC — Single-canonical-API (keep storage at sb._inn; force all writes through `sm.set_score_canonical` API; deprecate direct sb.set("score", ...) call sites)

- **Mechanism**: Like QB but does NOT add a new SM scalar; the API is purely a write-gate that calls sb.set internally. SM @property reads continue via sb._inn.
- **§7.2 gate-1**: PASS — same gating semantics as QB.
- **§7.2 gate-2**: PASS — even less change than QB (no new SM scalar storage).
- **§7.2 gate-3**: PASS — but **structurally identical to QB minus the SM-side mirror scalar**. The mirror scalar is the load-bearing piece of QB's WS-P.b SCOPE-RESERVATION cascade-close potential — without it, striker-anchor cold-start logic still reads sb.
- **Status**: **FALSIFY (sub-optimal)** — QC is a strict subset of QB's mechanism without the cascade-close upside. If QB is implementable, QC is dominated.

### QD — SM-as-pure-derivation (SM has no own state; reads always from sb._inn; sb.set becomes the single sophisticated regression-rejection site; remove SM-side fallback scaffolding)

- **Mechanism**: Delete `_sm_scalar_fallback` entirely. Delete shadow-mode + scoreboard-None paths in setter. All sophistication lives at sb.set.
- **§7.2 gate-1**: PARTIAL FAIL — does not address the bypass writers (S07/S10/S11 still write directly to `sb._inn["score"]`). Defect class survives.
- **§7.2 gate-2**: FAIL — removes shadow-mode parity instrumentation that L1.5 + L2 baseline depends on.
- **§7.2 gate-3**: FAIL — fix surface deletes load-bearing code paths; not pipeline-direct.
- **Status**: **FALSIFY** — gate-1 + gate-2 + gate-3 all fail.

### QE — Cohort-split (score-first refactor; wickets + overs follow separately)

- **Mechanism**: Independent meta-decision. Apply QB to score-only this workstream; queue follow-on workstreams (WS-R wickets, WS-S overs) for the other two primitives in §C9 catalogue.
- **§7.2 gate-1/2/3**: INHERIT QB's gate verdicts for the score axis.
- **Status**: **COMPLEMENTARY to QB** — adopted as the execution scoping discipline. WS-Q delivers score-axis only; wickets + overs deferred. Striker-anchor cascade-close is a SCOPE-RESERVATION; WS-Q does NOT touch the striker/non identity surfaces, only the score primitive.

### Hypothesis verdicts

- **Leading candidate: QB** (with QE scoping discipline).
- **Falsifications: 3** (QA on gate-2, QC dominated by QB, QD on gates 1+2+3).
- Static-falsification budget: 3 of 8 used; well under threshold.

---

## §7 §7.2 audit on leading candidate QB

| Gate | Verdict | Evidence |
|---|---|---|
| 1 — defect-class fit | PASS | QB closes all 12 score writers under a single validated API. The 3 bypass writers (S07/S10/S11) get cricket-physics + confidence validation they currently lack. WS-O.c residue (3 E2 + 5 conservation) targeted directly: `sm.set_score` rejects upstream of `delta_score` derivation, so the cascade no longer reads stale state. |
| 2 — backward-compat | PASS | sb._inn["score"] storage unchanged; 92 production readers + 60+ test readers byte-identical. Sb.set retains all guards as defense-in-depth. SM @property continues returning the same value. L2 30/30 ledger expected UNCHANGED. |
| 3 — fix-surface attribution | PASS | PIPELINE-DIRECT. Fix surface = `sm.set_score` new API (~80 LOC) + 12 writer-redirect edits + (optional) deprecation logging at sb.set("score", ...) direct call sites. No §15 fence touches; no canonical write-path rewiring. |
| 4 — S33 instrumentation-aware | PASS-WITH-PROTOCOL | Step-2a lands the API + redirects under a feature flag `USE_SM_CANONICAL_SCORE` (default 0); step-2b enables flag in shadow mode (parity logging); step-2c flips default; step-2d removes flag + deprecates direct sb.set("score") access. Each step independently empirically replayed. |
| 5 — cohort enumeration completeness | PASS | QE scoping: score axis only. Wickets + overs explicit SCOPE-RESERVATION (WS-R/WS-S). Striker-anchor (WS-P.b) SCOPE-RESERVATION pending WS-Q cascade-close empirical observation. WS-O.c residue: full-closure target. WS-O.b PA: inherited defense-in-depth; may simplify in step-2d cleanup. |
| 6 — predicted-flip frame numbers | OPEN at step-2d | Predicted flip set = balls 4.1-4.5 residue per WS-O.c step-1 §1 (DCKKR fixture frame range TBD at step-2d replay). |
| 7 — empirical replay closure | DEFER to step-3 | Step-3 after step-2d replay reports new-baseline + flip-coverage table. |

Gates 1-5 PASS; gate 4 has explicit protocol; gates 6+7 deferred per S33. Static convergence achieved on QB.

---

## §8 Predicted-flip table for step-2

| Surface | Pre-WS-Q (post-WS-P baseline `b8c3c25`) | Post-WS-Q (predicted) | Confidence |
|---|---|---|---|
| WS-O.c residue (E2) | 3 firings on DCKKR balls 4.1-4.5 | **0** (full closure) | HIGH — direct cascade-root removal |
| WS-O.c residue (conservation) | 5 firings on DCKKR balls 4.1-4.5 | **0** (full closure) | HIGH — same cascade root |
| WS-O.b PA gate | inherited mechanism active | UNCHANGED firing-count (mechanism preserved as defense-in-depth) | HIGH — mechanism not touched |
| WS-P.b striker-anchor (cold-start swap ~50 fields) | unresolved at `b8c3c25` | **TBD — SCOPE-RESERVATION**; may cascade-close if SM-owned state model simplifies cold-start striker derivation; or may require WS-P.c follow-on | MEDIUM-LOW — separate code path; cascade-close is speculative |
| L2 ledger | 30 PASS | **30 PASS UNCHANGED** (load-bearing backward-compat) | HIGH — readers byte-identical |
| L1.5 total | 90 PASS | **~100+ PASS** (additive cases for `sm.set_score` API + cricket-physics gates + confidence semantics; existing 90 unchanged) | HIGH — additive only |
| Other 15 surfaces (§7.2 gate-5 cohort enumeration) | UNCHANGED | **UNCHANGED** | HIGH — not in scope |
| §12 catalogue 4th instance | (would have been score-domain) | **NOT NEEDED** — WS-Q preemptively closes the would-be 4th-instance defect by architectural remediation (Shape C) rather than logging it for narrow remediation later | HIGH — closing in-class |

---

## §9 Sub-findings

- **S33 promotion ready at step-3 close-out**: WS-O OA + WS-P P1 + WS-O.c step-2 STOP all empirically demonstrated the same saturation pattern (defensive-gate refinement on a dual-state surface hits a structural ceiling). Promote to S33 line item.
- **New candidate sub-finding: "architecture-vs-defensive-gate trade-off"** — when a defect class admits both a narrow remediation (defensive gate tightening) and an architectural remediation (surface unification), the narrow remediation's local cost is dominated by the architectural remediation's cascade-closure value IF and only if more than 2 narrow remediations have failed empirically on the same defect class. WS-Q is the first instance where this trade-off is acted on. Mark as S34-candidate pending step-3 empirical confirmation.
- **Methodology lesson**: the §12 catalogue's "deferred as engineering workstream" disposition on the Shape-C remediation (sm_as_orchestrator §12.5) has now been triggered for the first time by user-direction Option 2. The triggering condition was 3 consecutive empirical NO-OPs on the same defect class with the same fix surface — a falsifiable, observable criterion that future operators can apply.

---

## §10 Step-2 entry data — multi-commit execution plan

Per CLAUDE.md `Agent behavior` discipline (max 5 tool calls per task; minimum changes; no auto-explore) AND §7.2 gate-4's S33 instrumentation-aware methodology, WS-Q step-2 is decomposed into 4 independent commits each with its own L1.5 + L2 + derivation green gate.

### Step-2a — Foundation (highest-risk; storage location move)

- **Scope**: Introduce `sm._canonical_score: int | None` attribute (initialized to None). Introduce `sm.set_score(value, source: str, confidence: str = "normal") -> bool` canonical write API. Body: (i) coerce + None-passthrough; (ii) cricket-physics validation (T20 ceiling, chase ceiling, regression-direction, jump-magnitude — duplicated from sb.set for explicit ownership); (iii) confidence-aware override (`confidence="override"` bypasses regression rejection for legitimate force-reset paths); (iv) cross-field validation (overs-balls × RPO plausibility); (v) on accept: write to `sm._canonical_score` AND call `sb.set("score", v, frame)` to preserve sb-side mirror + tracker consensus; (vi) return bool.
- **Behavior under feature flag `USE_SM_CANONICAL_SCORE=0` (default)**: API exists but is NOT called by any production writer. SM @property reads still go to `sb._inn["score"]`. Zero behavior change.
- **L1.5 obligations**: new test cases covering each validation branch (T20 / chase / regression / jump / cross-field / confidence-override).
- **Empirical gate**: derivation green; L2 30/30 UNCHANGED; L1.5 90 + new cases all PASS.
- **Risk**: API surface is new; no production caller — exposure limited to test-fixture surface. Highest design-correctness risk; lowest production-blast-radius risk.

### Step-2b — Writer redirection (transition)

- **Scope**: 12 writer-redirect edits. Each current write site (`self.score = X`, `sb.set("score", X, frame)`, `sb._inn["score"] = X`) becomes `sm.set_score(X, source="<site_tag>", confidence="<tag>")`. The 3 bypass writers (S07/S10/S11) gain proper invariant routing via the canonical API. Confidence tag "override" on S11 (force-reset) preserves bypass semantics where genuinely needed.
- **Behavior under flag**: when `USE_SM_CANONICAL_SCORE=1`, `sm.set_score` writes `sm._canonical_score` AND `sb._inn["score"]` (via the internal sb.set call); SM @property reads `sm._canonical_score` first, falls back to `sb._inn["score"]` if None. When flag=0, set_score short-circuits to legacy sb.set delegation; @property reads sb._inn unchanged.
- **Shadow-mode parity logging**: under flag=0, ALSO write to `sm._canonical_score` and emit `[SM-CANONICAL-PARITY]` divergence logs (mirrors WS-O.b shadow methodology).
- **L1.5 obligations**: per-site test asserting `sm.set_score` is the call path; legacy fixtures using direct sb.set or `_inn[...]=` continue PASS via backward-compat.
- **Empirical gate**: shadow-parity replay on DCKKR + GTRR captured Scout dumps. Zero parity divergences expected (flag=0 means no behavior change).

### Step-2c — Flag flip (canonical activation)

- **Scope**: Flip `USE_SM_CANONICAL_SCORE` default to 1. `sm._canonical_score` is now the canonical store; `sb._inn["score"]` is the mirror (still writable as fallback for legacy paths).
- **Empirical gate**: full DCKKR + GTRR replay. **WS-O.c residue 3 E2 + 5 conservation predicted to flip to 0.** L2 30/30 UNCHANGED. L1.5 PASS.
- **Step-2 STOP condition**: if any of WS-O.c residue does NOT flip OR L2 ledger regresses, revert flag default to 0 and re-investigate at step-2c.1 (residue characterization).

### Step-2d — Cleanup (deprecation + optional sb.set simplification)

- **Scope**: Add `DeprecationWarning` at the 3 surviving direct dict-write sites (S07/S10/S11 if any still exist after step-2b; ideally none). Optional: simplify or remove WS-O.b PA magnitude gate at `sb.set` IF empirical replay shows `sm.set_score`'s cross-field validation fully subsumes it (otherwise PA remains as inherited defense-in-depth per §8). Remove `_sm_scalar_fallback` IF empirical replay shows it is no longer reachable.
- **Empirical gate**: derivation green; L2 30/30 UNCHANGED; L1.5 PASS; no DeprecationWarning emissions in DCKKR + GTRR replay.

### Stop conditions for step-2 sequence

- Step-2a derivation red → STOP; revisit `sm.set_score` body design.
- Step-2b shadow-parity divergence → STOP; reconcile the divergent path before flag flip.
- Step-2c residue does not flip → STOP; cascade root is in a different code path than predicted; escalate to step-2c.1 investigation memo.
- Any commit increases L2 regression-count → STOP; immediate revert + investigation.

---

## Stop-condition status (per operator brief)

- **Static convergence on single leading candidate (QA-QE) with gates 1-5 PASS**: ACHIEVED → QB + QE scoping.
- All candidates statically falsify: NO (QB stands).
- Leading candidate requires §15-fence canonical-write-path touches: NO (sb.set retained as inner-call; SM canonical API is additive).
- Reader/writer enumeration surfaces unknown call sites that expand scope: NO (92 readers + 12 writers all accounted for via §C9 + this audit's grep pass).
- 8 static falsifications without convergence: NO (3 used).

---

## Report-back summary

- Memo path: `files/docs/investigations/workstream_q_score_state_unification_refactor.md`
- Section count: 10 (§1-§10) per standard structure.
- Hypothesis count: 5 (QA, QB, QC, QD, QE).
- Leading candidate: **QB** (with QE scoping discipline).
- Static-falsification count: 3 (QA gate-2, QC dominated, QD gates 1+2+3).
- Reader enumeration count: **~92 production reader sites** (across `scoreboard.py` × 8, `score_manager.py` via @property, `score_manager_derivation.py` × 3, `eyes/main.py` × 1, `test_pipeline.py` × ~80) + ~60 test-fixture readers.
- Writer enumeration count: **12 production writer sites** (S01-S12 per §4 table) + 1 test-only writer (S13); 3 of the 12 currently bypass `sb.set` invariants.
- runs_off_bat / this_over derivation cascade-site count: **3** (D1/D2/D3 at `score_manager_derivation.py:210,382,495`).
- Cohort-closure prediction: WS-O.c residue (3 E2 + 5 conservation) → **0** (full closure); WS-O.b PA mechanism UNCHANGED (inherited defense-in-depth); WS-P.b striker-anchor TBD SCOPE-RESERVATION; L2 30/30 UNCHANGED; L1.5 additive ~90 → ~100+; §12 catalogue 4th instance NOT NEEDED (preemptive in-class closure).
- Multi-commit execution plan: step-2a (foundation: `sm._canonical_score` + `sm.set_score` API under flag=0; ~80 LOC + L1.5 cases) → step-2b (writer redirect + shadow-parity; ~12 LOC edits + parity logging) → step-2c (flag flip default 1; empirical residue closure gate) → step-2d (cleanup: DeprecationWarning + optional PA simplification).
- Recommended next step: **step-2a authorization** (foundation commit). Step-2a has zero production-behavior change (flag=0); the cascade-closure risk is isolated to step-2c flag flip. WS-O.c residue stays as known limitation pending step-2c; WS-P.b striker-anchor deferred pending WS-Q cascade observation.
- Working tree state: docs-only edit at this memo; no production code touched.
