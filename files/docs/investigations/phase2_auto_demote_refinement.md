# Phase 2 `BATTERS_INVARIANT_AUTOCORRECT` — rule=A `auto_demote` refinement

**Date:** 2026-04-30  
**Scope:** Design only. **No code changes.** Implementation remains **DEFER** until Phase 2 enablement is reconsidered from production data.  
**Status:** Refines the deferred Phase 2 design from `scorer_invariants_categorization.md` §10 after the MI-vs-SRH F2167 finding.

---

## §1 Problem Statement

F2167 in MI vs SRH innings 1 exposed a failure mode in the planned Phase 2 rule=A autocorrect. The analyzer found one rule=A `active_set_max_two` fire at F2167 with active batters `Ryan Rickelton, Tilak Varma, Hardik Pandya`, striker `Ryan Rickelton`, non-striker `Hardik Pandya`, and `upstream_step3_fired=false` (`batters_invariant_cluster_innings1.md` L28-L31, L127-L135). The innings-break synthesis identifies the same frame as a graphic overlay resurrection of Hardik Pandya 62 frames after dismissal, with the current active pair being Rickelton + Tilak (`mi_srh_innings_break_analysis.md` L84-L98).

The current Phase 2 design says rule=A should demote the **most recently activated** batter when more than two cards are `status="batting"` (`scorer_invariants_categorization.md` L611-L617). That criterion is not aligned with the cricket state. In F2167 the incorrect card was the dismissed batter reappearing from a graphic overlay, not necessarily the newest card transition. If the selector chooses Rickelton or Tilak, Phase 2 would remove a legitimate active batter while preserving the resurrected Hardik card.

General pattern: any rule=A fire where the active set contains the two legitimate crease occupants plus one resurrected dismissed batter must select the resurrected dismissed batter, not the latest activation. When authoritative dismissal evidence is unavailable or contradictory, the safe action is no mutation with explicit telemetry.

---

## §2 Current Logic Critique

The current implementation surface is telemetry-only. `test_pipeline.py` imports `BATTERS_INVARIANT_AUTOCORRECT` from `scorer_decision_schema.py` (`test_pipeline.py` L58-L63), and the flag defaults to `False` (`scorer_decision_schema.py` L24-L29). `_batters_invariant_backstop` computes active cards from `scoreboard.batting_card[*].status == "batting"`, detects rule=A when `len(active) > 2`, logs `[BATTERS-INVARIANT]`, and returns if autocorrect is disabled (`test_pipeline.py` L2540-L2605). If the flag is enabled today, action is still only `auto_correct_deferred`; no demotion exists (`test_pipeline.py` L2588-L2605).

The design source, not executable code, carries the problematic selector: rule=A action is "Demote the most recently activated rule-A violator (highest `_fresh_batter_admission[name].frame` value, else lexically last)" (`scorer_invariants_categorization.md` L611-L617). In data-structure terms, "most recently activated" means ordering by a per-batter admission timestamp if available, otherwise a deterministic fallback such as lexical ordering. The current backstop does not read such timestamps, so implementation would need to add or recover them before using that criterion.

Failure modes:

1. **Resurrected batter is most recent:** demotion is correct by accident.
2. **Resurrected batter is older:** a legitimate current batter is wrongly demoted. F2167 is this class per the cluster analysis recommendation (`batters_invariant_cluster_innings1.md` L135-L139).
3. **Activation timestamps are equal or missing:** behavior degrades to arbitrary ordering, which is unsafe for a write-mode Phase 2 correction.

Design-phase stop condition D4 is resolved: §10.1 does specify most-recent activation (`scorer_invariants_categorization.md` L611-L617), but production code has not implemented it yet.

---

## §3 Refined Logic Specification

### Primary Check: Authoritative Dismissal Evidence

For rule=A only, compute `active_batters = [name for name, card in scoreboard.batting_card.items() if card.get("status") == "batting"]`. If `len(active_batters) != 3`, do not use this Phase 2 path; see §4d.

For each active batter, test whether they have a witnessed FOW entry. The preferred predicate is `scoreboard._is_witnessed_dismissal(active_name)` because it already encodes "witnessed, not placeholder" semantics (`eyes/scoreboard.py` L3348-L3373). Before calling it, normalize `active_name` through `scoreboard.resolve_name` / `_find_card_key` when available, following existing name resolution patterns (`eyes/scoreboard.py` L923-L982; `score_manager.py` L964-L991).

Implementation-ready helper contract:

```python
def _rule_a_witnessed_fow_matches(scoreboard, active_batters):
    matches = []
    seen = set()
    for active_name in active_batters:
        card_key = _canonical_batter_key(scoreboard, active_name)
        if (card_key and card_key not in seen
                and scoreboard._is_witnessed_dismissal(card_key)):
            matches.append(card_key)
            seen.add(card_key)
    return matches
```

If exactly one active batter is witnessed-out, demote that batter:

```python
if len(active_batters) == 3:
    fow_matches = _rule_a_witnessed_fow_matches(scoreboard, active_batters)
    if len(fow_matches) == 1:
        demoted = fow_matches[0]
        kept_active = [n for n in active_batters if n != demoted]
        emit("[BATTERS-INVARIANT-AUTOCORRECT-A]",
             reason="fow_match",
             demoted=demoted,
             kept_active=",".join(kept_active),
             confidence="HIGH")
        if BATTERS_INVARIANT_AUTOCORRECT:
            # FOW-match means this is a resurrection; restore the cricket
            # state, not merely a generic "not currently batting" state.
            scoreboard.batting_card[demoted]["status"] = "out"
        return
```

Confidence is **HIGH** because cricket rules say a witnessed-out batter cannot be active.

### Secondary Check: Recent Transition Fallback

If no active batter has witnessed FOW evidence and `fall_of_wickets` data is present and trustworthy enough to conclude "no match", fall back to the original most-recent-transition selector only when exactly one candidate has a strictly greatest transition frame. Emit:

```text
[BATTERS-INVARIANT-AUTOCORRECT-A] reason="recent_transition_fallback" demoted=<name> kept_active=<comma-list> confidence="MEDIUM"
```

This is a best-effort guess without dismissal authority. If execution is later enabled for this fallback, it should retain the original rule=A demotion semantics (`status="yet_to_bat"`, clearing active occupancy) because there is no FOW proof the batter is dismissed. In Phase 1 mode it must only compute and log the candidate; execution stays gated by `BATTERS_INVARIANT_AUTOCORRECT=False` (`scorer_decision_schema.py` L24-L29).

### Tertiary Path: Noop With Telemetry

Do not mutate when the selector is ambiguous or out of scope:

```python
if len(active_batters) > 3:
    unresolvable("beyond_scope")
elif len(fow_matches) > 1:
    unresolvable("double_fow")
elif fow_state_missing_or_stale:
    unresolvable("no_fow_data")
elif recent_transition_missing_or_tied:
    unresolvable("activation_ambiguous")
```

Telemetry:

```text
[BATTERS-INVARIANT-UNRESOLVABLE-A] reason=<specific_reason> active_batters=<comma-list> fow_present=<true|false> confidence="UNRESOLVABLE"
```

Noop is safer than guessing because Phase 1 already tolerates rule=A by logging and allowing downstream UI hygiene to continue.

### FOW Shape Caveat (D1)

The requested design assumed FOW is a list of batter names. Actual state is a list of dicts. The Scoreboard authoritative path writes `{"wicket", "score", "overs", "batter", "_witnessed": True}` (`eyes/scoreboard.py` L3035-L3042), and `_is_witnessed_dismissal` requires `fow["batter"] == name`, `_witnessed`, and not `_unwitnessed` (`eyes/scoreboard.py` L3348-L3373). `ScoreManager._fow_writable()` returns `scoreboard.fall_of_wickets` when attached (`score_manager.py` L215-L218), while one ScoreManager event path writes `{"dismissed": best_dismissed, ...}` into that writable list (`score_manager.py` L2647-L2652, L2686-L2712).

Therefore implementation must not assume `fall_of_wickets: list[str]`. The primary check should call `_is_witnessed_dismissal` first. If implementation needs raw FOW inspection, it must explicitly extract witness names from `batter` and treat `dismissed` as a compatibility fallback only after verifying whether those entries are witnessed. If this shape proves more mixed in tests than this design accounts for, stop under S1.

---

## §4 Edge Cases

**a. Both active batters in FOW.**  
For rule=A with three active batters, `len(fow_matches) > 1` means the frame may be a double-wicket transition, a stale FOW conflict, or a mixed-shape state. Do not demote. Emit `[BATTERS-INVARIANT-UNRESOLVABLE-A] reason="double_fow"`.

**b. No active batter in FOW.**  
If FOW is present and no active batter is witnessed-out, the active-set overflow likely came from a non-dismissal corruption path. Use `recent_transition_fallback` only when transition ordering is strict. Otherwise emit `activation_ambiguous`.

**c. FOW data unavailable/stale.**  
If `scoreboard.fall_of_wickets` is missing, empty despite nonzero wickets, or contains only `_unwitnessed` placeholders, the primary check cannot run. Prefer `UNRESOLVABLE` if activation order is missing; allow fallback only with `reason="recent_transition_fallback"` and include a telemetry caveat field `fow_present=false`.

**d. Active set holds 4+ batters.**  
Multiple resurrections are beyond Phase 2 rule=A scope. Emit `reason="beyond_scope"` and do not mutate. A single demotion may leave the invariant violated.

**e. FOW witness format ambiguity.**  
Name matching must normalize both card names and FOW names. Use Scoreboard lookup forms: full name, surname, first initial + surname, unique 3/4-letter surname prefixes, unique first names, and conservative fuzzy match (`eyes/scoreboard.py` L850-L982). For autocorrect, prefer exact canonical card-key equality after normalization. Surname-only/fuzzy matches should be accepted only if `resolve_name` resolves uniquely.

**f. Activation timestamp missing.**  
Missing or tied transition frames should not demote. Emit `reason="activation_ambiguous"`.

---

## §5 Implementation Locations

**Current backstop and call sites.**  
The relevant production hook is `_apply_scorer_item2_cleanup`, which finalizes schema shadow logs and calls `_batters_invariant_backstop` after scorer mutations (`test_pipeline.py` L2516-L2537). `_batters_invariant_backstop` reads the active set, witnessed-out set, striker/non slots, and emits `[BATTERS-INVARIANT]` (`test_pipeline.py` L2540-L2605). That is the exact insertion point for the refined rule=A decision.

**Feature flags.**  
`SCORER_SCHEMA_ENFORCE=False` and `BATTERS_INVARIANT_AUTOCORRECT=False` live in `scorer_decision_schema.py` (`scorer_decision_schema.py` L24-L29). `test_pipeline.py` imports the autocorrect flag at startup (`test_pipeline.py` L58-L63). No design change flips the flag.

**Inputs needed.**

- `active_batters`: already computed from `scoreboard.batting_card` (`test_pipeline.py` L2548-L2552).
- FOW authority: available through `scoreboard._is_witnessed_dismissal` and `scoreboard.fall_of_wickets` (`eyes/scoreboard.py` L3348-L3373).
- Transition order: not currently present in `_batters_invariant_backstop`; implementation must identify the existing `_fresh_batter_admission` owner or add a small per-batter admission tracker. If that requires more than a simple parameter/helper addition, stop under S2.

**Recommended helper split.**

1. `_canonical_batter_key(scoreboard, raw_name) -> str | None`
2. `_rule_a_witnessed_fow_matches(scoreboard, active_batters) -> list[str]`
3. `_rule_a_recent_transition_candidate(active_batters, admission_frames) -> str | None`
4. `_apply_rule_a_autocorrect_decision(...) -> Decision`

**Telemetry additions.**

- `[BATTERS-INVARIANT-AUTOCORRECT-A] reason=<fow_match|recent_transition_fallback> demoted=<name> kept_active=<comma-list> confidence=<HIGH|MEDIUM> frame=F#`
- `[BATTERS-INVARIANT-UNRESOLVABLE-A] reason=<double_fow|no_fow_data|activation_ambiguous|beyond_scope> active_batters=<comma-list> fow_present=<true|false> frame=F#`

These integrate with existing `[BATTERS-INVARIANT]` telemetry rather than replacing it. The current base log format already includes `rule`, `violation`, `active`, `witnessed_out`, upstream Step 3/4 fields, action, target, and frame (`scorer_invariants_categorization.md` L797-L817; `test_pipeline.py` L2588-L2600).

**Phase 1 compatibility.**  
In Phase 1, compute the decision and emit the new telemetry, but do not mutate. Current behavior remains `action=noop_phase1` when `BATTERS_INVARIANT_AUTOCORRECT=False` (`test_pipeline.py` L2588-L2605). Phase 2 execution is a separate flag flip and remains deferred.

---

## §6 Tests Required

Unit tests:

- `test_phase2_autocorrect_a_fow_match_demotes_correctly`: F2167-pattern fixture with active `Ryan Rickelton`, `Tilak Varma`, `Hardik Pandya`; FOW marks Hardik witnessed-out. Verify decision demotes Hardik and keeps Rickelton + Tilak.
- `test_phase2_autocorrect_a_recent_transition_fallback`: no active batter in witnessed FOW; strict transition order exists. Verify `reason="recent_transition_fallback"` and medium confidence.
- `test_phase2_autocorrect_a_unresolvable_double_fow`: two active batters match witnessed FOW. Verify no mutation and `[BATTERS-INVARIANT-UNRESOLVABLE-A] reason="double_fow"`.
- `test_phase2_autocorrect_a_unresolvable_no_fow_data`: FOW missing, empty, or only `_unwitnessed` placeholders. Verify graceful noop unless transition fallback has strict evidence; if no strict evidence, `reason="no_fow_data"`.
- `test_phase2_autocorrect_a_name_normalization`: FOW witness `"Pandya"` or raw `"H Pandya"` resolves to card key `"Hardik Pandya"` using existing `resolve_name` semantics.
- `test_phase2_autocorrect_a_phase1_mode_no_action`: with `BATTERS_INVARIANT_AUTOCORRECT=False`, verify telemetry-only behavior and no card status mutation.
- `test_phase2_autocorrect_a_mixed_fow_shape_stop`: fixture with `fall_of_wickets` entries containing `dismissed` but no `_witnessed`. Verify implementation either treats it as non-authoritative or routes to `UNRESOLVABLE`; this guards the D1 shape caveat.

Integration test, if feasible:

- `test_f2167_rule_a_replay_refined_auto_demote`: replay F2167-style state through `_batters_invariant_backstop`; verify Hardik is the selected demotion target, Rickelton + Tilak remain active, and `[BATTERS-INVARIANT-AUTOCORRECT-A] reason="fow_match"` fires.

The primary validation case is F2167, matching the innings-break fixture candidate `test_batters_invariant_rule_a_graphic_resurrection` (`mi_srh_innings_break_analysis.md` L239-L245).

---

## §7 Telemetry Framework

Existing analyzer support recognizes `[BATTERS-INVARIANT]`, `[SCORER-SCHEMA-WOULD-DROP]`, and `[SCORER-SCHEMA-WOULD-COERCE]` (`analyze_match_telemetry.py` L165-L168). It includes `[BATTERS-INVARIANT]` in pending-validation hits (`analyze_match_telemetry.py` L183-L220) and Bundle B/C positive-fire reporting (`analyze_match_telemetry.py` L620-L649, L1239-L1280).

Add:

- `BATTERS_INVARIANT_AUTOCORRECT_A = re.compile(r"\[BATTERS-INVARIANT-AUTOCORRECT-A\]")`
- `BATTERS_INVARIANT_UNRESOLVABLE_A = re.compile(r"\[BATTERS-INVARIANT-UNRESOLVABLE-A\]")`

Add both to:

- `PENDING_VALIDATION_PATTERNS`, next to `[BATTERS-INVARIANT]`.
- `bundle_bc_events`, with keys such as `item2_batters_invariant_autocorrect_a` and `item2_batters_invariant_unresolvable_a`.
- `report_bundle_bc` expected list, so Phase 2 dry-run/prod fires are visible in the standard analyzer surface.

Monitoring charter integration: `[BATTERS-INVARIANT]` is already a PRIMARY surface with rule=A/rule=B escalation thresholds (`MONITORING_CHARTER.md` L48-L62, L81-L101). Add the two new tags to that same PRIMARY row rather than the PENDING-only watch list, because wrong demotion is a user-visible correctness risk.

Design-phase stop condition D3 is resolved: there is no existing `[BATTERS-INVARIANT-AUTOCORRECT-A]` tag in code; only `[BATTERS-INVARIANT]` exists today. The proposed tag is new and does not conflict.

---

## §8 Phase 2 Enablement Gate Update

The innings-break decision explicitly deferred Phase 2 because F2167 showed the planned autocorrect would demote a legitimate active batter, and because innings-transition fires made the match-day unclean (`mi_srh_innings_break_analysis.md` L123-L151). The prior next-match criteria require zero non-admission fires, rule=A count zero, a rule=A autocorrect patch preferring FOW evidence, and clean innings transition (`mi_srh_innings_break_analysis.md` L135-L151).

Updated enablement gate:

1. Refined rule=A implementation shipped behind `BATTERS_INVARIANT_AUTOCORRECT=False`.
2. At least one clean match-day in Phase 1 telemetry with `[BATTERS-INVARIANT] rule=A NON-ADMISSION <= 1 per match`.
3. If an F2167-class scenario appears, `[BATTERS-INVARIANT-AUTOCORRECT-A] reason="fow_match"` selects the witnessed-out batter.
4. `[BATTERS-INVARIANT-UNRESOLVABLE-A]` rate remains bounded, expected `<= 1 per match`.
5. Manual audit finds zero wrong demotion candidates.
6. Only then reconsider `BATTERS_INVARIANT_AUTOCORRECT=True`, before first ball of a future innings or match, never mid-match.

This design satisfies the "auto_demote refinement" prerequisite, but implementation and enablement remain separate steps.

---

## §9 Risk Assessment

**a. FOW data reliability.**  
FOW can be wrong if upstream wicket attribution is wrong. Still, witnessed FOW is the best available authority: Scoreboard treats witnessed entries as immutable and `_is_witnessed_dismissal` as the canonical dismissal check (`eyes/scoreboard.py` L3006-L3033, L3348-L3373). Mitigation: only trust witnessed, non-placeholder entries; otherwise route to `UNRESOLVABLE`.

**b. Name normalization edge cases.**  
Surname-only and fuzzy matching can be ambiguous, especially same-surname squads. Mitigation: require canonical card-key resolution through existing lookup; accept surname/fuzzy only if unique (`eyes/scoreboard.py` L850-L982).

**c. Phase 2 enablement timing.**  
Even with refined logic, initial execution should be cautious. Mitigation: ship telemetry-only first, audit a match-day, then enable execution in a separate decision. The monitoring charter already says Phase 2 remains deferred pending clean data + logic gates (`MONITORING_CHARTER.md` L132-L140).

**d. False `UNRESOLVABLE`.**  
Noop preserves Phase 1 behavior and avoids wrong demotions. The trade-off is a transient active-set violation, already logged today.

**e. Mixed FOW dict shape.**  
Scoreboard and ScoreManager paths expose both `batter` and `dismissed` naming in nearby code. Mitigation: implementation starts with `_is_witnessed_dismissal`; raw dict fallback must be tested before execution. Stop under S1 if production fixture shape differs.

---

## §10 Composer 2 Readiness Checklist

- §3 includes paste-ready helper contracts and decision pseudocode.
- §5 names the insertion point: `_apply_scorer_item2_cleanup` / `_batters_invariant_backstop` in `test_pipeline.py`.
- §5 names required state: `scoreboard.batting_card`, `scoreboard._is_witnessed_dismissal`, `scoreboard.fall_of_wickets`, and admission transition frames.
- §6 includes named tests, with F2167 as primary validation.
- §7 defines exact new telemetry tags and fields.
- §8 updates the enablement gate without flipping any flag.
- §9 documents risks and mitigations, especially FOW shape and normalization.

---

## §11 Stop-And-Route-Back Conditions For Implementation Phase

S1: FOW data shape differs from this design, especially if witnessed entries do not consistently expose `batter` or `_witnessed`.  
S2: Rule=A implementation requires a broad refactor to thread transition timestamps into `_batters_invariant_backstop`.  
S3: A new or existing telemetry tag conflicts with `[BATTERS-INVARIANT-AUTOCORRECT-A]` semantics.  
S4: `scoreboard.resolve_name` / `_find_card_key` cannot uniquely resolve FOW vs card names for common cricket name forms.  
S5: F2167 fixture does not select Hardik Pandya via `reason="fow_match"`.  
S6: Tests show a single demotion can leave rule=A violated; route 4+ active sets to `UNRESOLVABLE` rather than extending Phase 2 scope.

---

## §12 Cross-References

- `files/docs/investigations/scorer_invariants_categorization.md` L591-L655: original Phase 2 rule/action design; L752-L817: Phase 1/2 gating and telemetry format; L939-L970: helpers-vs-root architecture.
- `files/docs/investigations/batters_invariant_cluster_innings1.md` L127-L139: F2167 deep-dive and recommendation to prefer FOW evidence.
- `files/docs/investigations/mi_srh_innings_break_analysis.md` L123-L151: Phase 2 defer decision and next-match enablement criteria.
- `files/docs/MONITORING_CHARTER.md` L48-L62 and L81-L101: PRIMARY monitoring and escalation thresholds.
- `files/docs/backlog.md` L13-L14 and L113-L151: backlog status and MI-SRH Phase 2/F2167 handoff notes.
- `files/test_pipeline.py` L2516-L2605: current telemetry-only backstop and Phase 2 reserved branch.
- `files/scorer_decision_schema.py` L24-L29: Phase 1 default flags.
- `files/score_manager.py` L215-L218 and L2647-L2712: FOW writable source and ScoreManager event FOW shape.
- `files/eyes/scoreboard.py` L3035-L3042 and L3348-L3373: authoritative witnessed FOW shape and witnessed-dismissal predicate.
- `files/analyze_match_telemetry.py` L165-L168, L183-L220, L620-L649, L1239-L1280: analyzer integration points for new tags.
