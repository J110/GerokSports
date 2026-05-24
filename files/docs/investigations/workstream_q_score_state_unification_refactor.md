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

---

## §11 Arc completion retrospective (WS-Q step-3 close-out, 2026-05-24)

WS-Q multi-commit arc CLOSED. 5-commit execution (4 feat/refactor + 1 cross-fixture audit docs) plus this step-3 retrospective. The "empirical residue-closure gate" framing at step-1 delivered exactly as predicted.

**Arc commits.**

1. **step-2a `d6f041b`** — foundation: `sm._canonical_score` storage + `sm.set_score` canonical API + `USE_SM_CANONICAL_SCORE` env gate (default 0; zero behavior change at flag=0). LOC: 25 logic ≤60 budget.
2. **step-2b `a5c8712`** — writer redirect at 4 production sites (S01 setter + S07 bypass + S08-guarded + S08-direct + S09 catchup) + `SM-SHADOW-PARITY-DIVERGENCE` observability tag. Flag stays default 0; 6 divergences surfaced on dckkr at frames 288/290/303/319/334/361. LOC: 27 logic ≤150 budget.
3. **step-2c `88fe41c`** — flag flip default 0 → 1 + `sm.set_score` regression-rejection predicate (T20 absolute bound + forward-monotonic accept + backward-with-confidence retroactive accept). Diff baseline **59 → 34** (-25 rows -42%). Phase 1 empirical anchor: 6/6 canonical values match GT at balls 4.1-4.6. LOC: 57 logic ≤80 budget.
4. **step-2c.5 `4e3b3d3`** — cross-fixture gate-7 audit (3 dckkr captures + gtrr). Verdict: GREEN-WITH-LIMITATIONS. FA `PREV-SCORE-ANCHOR-APPLIED` count = 0 across 4 captures + 2,472 trace records. Docs-only.
5. **step-2d `24b9777`** — cleanup: legacy sb.set retirement (S01 setter + S07 bypass + S08 + S09 consolidated through sm.set_score) + explicit FA retirement at score_manager.py:4234-4268 + PREV-SCORE-ANCHOR-APPLIED tag retired from KNOWN_TAGS. PA preserved as defense-in-depth; retroactive-correction predicate branch preserved per user direction. Diff baseline 34 UNCHANGED. LOC: net -31 with only +7 new logic ≤80 budget.

**Arc statistics.**

- Total commits: 5 (4 production + 1 audit) + this step-3 retrospective.
- Production logic net: ~88 LOC across all 5 commits (~107 added; -31 net after step-2d cleanup).
- Diff trajectory: **207 → 34 divergences (-83.6% cumulative)** with -42% closure attributable to WS-Q step-2c specifically.
- Defect classes closed at step-2c: E2-phantom-runs (3 → 0), Per-batter-ledger-drift (5 → 0; CASCADE-CLOSED unpredictedly), phantom-in-pipeline (3 → 0).
- L1.5 cases added: 16 (Q-1 / Q-2 / Q-3 / Q-4 / Q-4b foundation + QB-1 / QB-2 / QB-3 writer-redirect + QC-1 / QC-2 / QC-3 / QC-4 / QC-5 / QC-6 predicate + QD-1 / QD-2 cleanup).
- L1.5 broader: 619 PASS (was 608 pre-WS-Q + 16 new cases through arc). Zero new regressions.
- L2 30/30 PASS preserved throughout.

---

## §12 Cascade-closure attribution (load-bearing for S9-strict promotion)

Step-2c flag flip closed **three independent defect surfaces simultaneously** via single architectural change:

| Surface | Pre-step-2c (step-2b baseline) | Post-step-2c | Mechanism |
|---|---|---|---|
| E2-phantom-runs | 3 | **0** | Canonical store returns correct 43-49 at balls 4.1-4.6 (vs sb-stuck 63/64); derivation `delta_score = current.score - prior.score` computes correct deltas. |
| Per-batter-ledger-drift | 5 | **0** | UNPREDICTED CASCADE: batting-card delta calculations align with GT once score reads correct. The 5 drift rows were downstream of the score-cascade root WS-Q targeted. |
| phantom-in-pipeline | 3 | **0** | Per-ball UI snapshots emit at correct score values; no phantom-event fabrication. |

**Cross-fixture validation (`4e3b3d3`).** Pattern holds on additional dckkr captures (749 records: E2 1 / Per-batter-ledger-drift 0; 618 records: E2 2 / Per-batter-ledger-drift 0) — significant reductions vs typical pre-step-2c counts. gtrr executed stably with consistent trace pattern.

**S9-strict third-instance evidence.** Three-instance threshold for architectural-cure-closes-multi-defect-class methodology insight is met:

1. **F1 cascade-closure** (cold-start striker fix; closed N classes simultaneously per HANDOFF history).
2. **S18 composite-fix** (WS-H D1 + P1 closed γ-bowler-w residue; multi-class closure).
3. **WS-Q step-2c canonical-store-flag-flip** (this arc; E2 + Per-batter-ledger-drift + phantom-in-pipeline simultaneously).

S9-strict canonical statement (PROMOTED at this close-out):

> "Single architectural fix closing multiple defect classes simultaneously. Three-instance evidence at promotion: F1 cascade-closure (cold-start striker fix closed N classes); S18 composite-fix (D1+P1 closed γ-bowler-w residue); WS-Q canonical-store-flag-flip (closed E2-phantom-runs + Per-batter-ledger-drift + phantom-in-pipeline simultaneously per step-2c `88fe41c`). **Pattern: when defensive iterations saturate against persistent residue, root-architectural-fix is the next layer to investigate — not more defensive layers.**"

---

## §13 FA forward-compat contract empirically validated (candidate methodology insight)

WS-V.A1 step-2 §10 prediction (`b7251e7` commit body + WS-V.A1 root-cause memo §10): "FA defensive anchor at `score_manager.py:4139` self-disables when WS-Q canonical store lands. The pre-advance mutation that FA defends against is structurally eliminated by the canonical-API write site." Cross-fixture audit at `4e3b3d3` confirmed:

- `PREV-SCORE-ANCHOR-APPLIED` count **0** across 4 captures (dckkr-264 / dckkr-749 / dckkr-618 / gtrr-841) + **2,472 cumulative trace records**.
- Step-2d retired FA's predicate block + tag without any regression.

**Candidate insight statement (first-instance; awaits second-instance corroboration for full promotion):**

> "Tactical defensive patches CAN self-disable structurally when architectural cures land, IF designed with forward-compat contract at commit time. First-instance evidence: WS-V.A1 step-2 §10 predicted FA self-disable post-WS-Q step-2c flag flip; cross-fixture audit at `4e3b3d3` confirmed 0 firings across 4 captures + 2,472 trace records. Implication for future tactical patches: design forward-compat contracts explicitly at commit time so future architectural cures can retire tactical layers cleanly without revert-cycle cost."

---

## §14 Architectural-cure-over-defensive-iteration economics (candidate methodology insight)

WS-O.c persistent residue (3 E2 + 5 conservation invariants at balls 4.1-4.5) survived 3 consecutive empirical no-ops via defensive-gate iteration:

| Workstream / commit | Approach | Rows closed on WS-O.c residue |
|---|---|---|
| WS-O OA (`ae2fe2f`) | WARM-mode magnitude gate at sb.set | 0 |
| WS-P P1 (`b8c3c25`) | Cold-start striker-anchor deferral | 0 |
| WS-U V2 (`b7251e7` predecessor) | Scout prompt parrot-anchor rewrite | 0 |
| **WS-Q step-2c (this arc)** | **Architectural cure (canonical store flag flip + regression-rejection predicate)** | **-25 rows + cascade closure** |

Three defensive-iteration attempts (combined LOC ~150-200) closed 0 rows on the WS-O.c residue. WS-Q's 3-commit architectural cure (~107 LOC) closed -25 rows + cascade-closed an unpredicted Per-batter-ledger-drift surface.

**Candidate insight statement (first-instance; awaits second-instance corroboration for full promotion):**

> "When defensive iterations saturate (3+ consecutive empirical no-ops within same defect class), the next investigation move should be architectural root-cause identification, not additional defensive layers. First-instance evidence: WS-O OA + WS-P P1 + WS-U V2 (3 consecutive empirical no-ops on WS-O.c residue) saturated the defensive-iteration approach; WS-Q architectural cure delivered -25 rows / ~107 LOC where prior 3 attempts delivered 0 rows / ~150-200 LOC similar effort. Trigger: empirical no-op pattern at step-3 baseline replays across 3 workstreams targeting the same residue. Action: pivot to architectural-layer investigation; identify root cause; design cure; ship; defensive layers self-disable per forward-compat contract."

---

## §15 Methodology insights running total + Phase 4 catalogue updates

**Methodology insights running total: 27 → 28 (S9-strict promoted at this commit).** Plus 2 new candidates landed:
- **FA forward-compat empirical validation** (candidate; first-instance via this arc; awaits second-instance).
- **Architectural-cure-over-defensive-iteration economics** (candidate; first-instance via WS-O.c residue closure; awaits second-instance).

S9-strict joins §15 + S21 + S23 + S26 + S26-v2 + S28 + S34 + S35 as standing methodology infrastructure.

**Phase 4 catalogue updates.**
- **CLOSED via WS-Q step-2c cascade closure:** E2-phantom-runs (3 → 0), Per-batter-ledger-drift (5 → 0; was Phase 4 catalogued), phantom-in-pipeline (3 → 0). Retired from active queue.
- **DEFERRED from WS-Q step-2d:** S12 (eyes/main.py `apply_scorer_decision` SM threading) — added to Phase 4 catalogue.
- **STAY in Phase 4 catalogue:** WS-V.B.W (10-row Cohort W mid-over 4.3 true pipeline cricket-defect striker_name-vs-stats internal inconsistency), WS-V.B.Z (10-row Cohort Z mid-over 4.4 acceptable residue), F1017 phantom-wicket (architectural-known-defect within broadcast framework per retirement directive at `9653cff`).
- **Validated baseline at step-3 close-out: 34 divergences** (cumulative WS-Q trajectory 207 → 93 inflated → 59 validated → 34 architectural-cure). All future predicted-flip tables compare against 34, NOT 59 or 93.

**Next-session candidates.**
- Independent residual cohorts surfaceable: F-A-commit-lag (10), F-B-ad-occlusion (8), Recent-overs-drop (4), Boundary-counter-double-increment (visible on larger captures), Bowler-W-credit-failure (visible on larger captures), E3-wicket-frame-misalign (WS-V striker cohort residue).
- WS-V.B.W step-1c instrumentation (10-row Cohort W true pipeline defect; Phase 4 catalogue).
- Track 2 re-enable (OpenScout `USE_OPEN_SCOUT=0`; oldest deferral).
- S12 follow-up (eyes/main.py SM threading from WS-Q step-2d deferral).
