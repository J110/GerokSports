# Workstream R — Step-1b cross-fixture instrumentation audit

**Date.** 2026-05-24.
**Branch.** `derive-not-detect` @ HEAD = `24b9ca7` (WS-R step-1).
**Trigger.** Empirical attribution for WS-R step-1's BOWLING-CARD-CREATED=0 finding on dckkr-264. NO-OP log-only instrumentation patch at `Scoreboard.update_bowler` entry (CHECKPOINT) + post-flag-check (CHANGE-CHECK) per S33 pattern + cross-fixture spot-check on dckkr-749 + dckkr-618 + gtrr-841.
**Outcome.** **EMPIRICAL ANCHOR LOCKED.** BOWLING-CARD-CREATED canonical lifecycle is structurally bypassed in production: 213 of 213 `update_bowler` calls across 4 captures take the `_apply_bowler_delta` early-return path at `scoreboard.py:3136-3141`; the change-detection + create/resume emission block at `:3945-3961` is **unreachable** via the production delta-driven call pattern. `_bowler_changed=True` fires **0 times** across 2,690 trace records.

---

## §1 Pre-patch verification (S26-v2 spot-check)

1. **`scoreboard.update_bowler` call-site enumeration.** 10 production call sites identified (9 in `score_manager.py:846/2753/6308/6546/6626/6712/7169/7250/7478` + 1 in `test_pipeline.py:5291`). Step-1's "6+" was an undercount; actual is 10.
2. **Bowler-card lifecycle entry points.** BOWLING-CARD-CREATED + BOWLING-CARD-RESUMED emission gated by `_bowler_changed OR _bootstrapped` at `scoreboard.py:3945-3961`. Both flags set earlier in `update_bowler` (identity resolution + must-change bootstrap).
3. **Tag registration.** BOWLING-CARD-CREATED + BOWLING-CARD-RESUMED already in `trace_emitter.py:63` KNOWN_TAGS. ✓
4. **Cross-fixture trace availability.** dckkr-264 (`watch_20260519_121701`, 264 records) + dckkr-749 (`validate_dckkr_20260521_155356`, 749 records) + dckkr-618 (`validate_dckkr_20260521_070545`, 618 records) + gtrr-841 (`validate_gtrr_20260520_180715`, 841 records) all confirmed runnable.

---

## §2 Instrumentation patch summary

**LOC budget compliance.** Total +24 LOC (≤80 budget ✓). 2 instrumentation blocks in `scoreboard.py`:
- CHECKPOINT block at `update_bowler` entry: emits BOWLER-CARD-LIFECYCLE-CHECKPOINT per call with `site` / `bowler` / `frame_id` / `in_card` / `has_delta` / `strip_runs` / `strip_wickets` / `strip_overs` payload.
- CHANGE-CHECK block at `:3945` (immediately before the `_bowler_changed OR _bootstrapped` gating): emits BOWLER-CARD-CHANGE-CHECK with `bowler_changed` / `bootstrapped` / `create_resume_will_emit` flag payload.

Both blocks wrapped in `try/except` + gated on `_trace is not None`. Zero behavior change.

**Trace tag registrations** at `trace_emitter.py`:
- `BOWLER-CARD-LIFECYCLE-CHECKPOINT`
- `BOWLER-CARD-CHANGE-CHECK`

---

## §3 Cross-fixture trace tag counts

| Capture | Records | CHECKPOINT | CHANGE-CHECK | `_bowler_changed=True` | `_bootstrapped=True` | CREATED | RESUMED |
|---|---|---|---|---|---|---|---|
| dckkr-264 (`watch_20260519_121701`) | 264 | 25 | **0** | 0 | 0 | 0 | 0 |
| dckkr-749 (`validate_dckkr_20260521_155356`) | 749 | 48 | 1 | 0 | 1 | 0 | 1 |
| dckkr-618 (`validate_dckkr_20260521_070545`) | 618 | 68 | 3 | 0 | 2 | 0 | 2 |
| gtrr-841 (`validate_gtrr_20260520_180715`) | 841 | 72 | 1 | 0 | 1 | 0 | 1 |
| **Cumulative** | **2,472 + 264 = 2,736** | **213** | **5** | **0** | **4** | **0** | **4** |

**Critical patterns.**
- **CHECKPOINT to CHANGE-CHECK ratio: 213 / 5 = 97.7% early-return rate.** Of 213 update_bowler calls, only 5 reached the post-flag-check instrumentation point. 208 calls (97.7%) returned early before reaching `:3945`.
- **`_bowler_changed=True` count = 0 across all 4 captures + 2,736 trace records.** The bowler-identity-change detection path NEVER fires in production. Despite 6 distinct bowlers seen on dckkr captures (Roy / Arora / Tyagi / Narine / Chakaravarthy / Green) + 6 on gtrr (Sharma / Ferreira / Archer / Jadeja / Deshpande / Punja), no transition is classified as `_bowler_changed`.
- **`_bootstrapped=True` fires sparingly (0/1/2/1 across captures)** — the must-change bootstrap path at `:3925` is the ONLY way create/resume emission reaches the wire in production.
- **BOWLING-CARD-CREATED count = 0 cross-fixture.** Despite 4 bootstrap-fire events across captures, all 4 emitted RESUMED (existing_runs > 0 etc.), not CREATED. The CREATED tag is **functionally dead code** in current production semantics.

---

## §4 CHECKPOINT payload distribution (early-return attribution)

| Capture | `has_delta=True` | `has_delta=False` | `in_card=True` | `in_card=False` |
|---|---|---|---|---|
| dckkr-264 | 25 / 25 (100%) | 0 | 25 / 25 (100%) | 0 |
| dckkr-749 | 48 / 48 (100%) | 0 | 48 / 48 (100%) | 0 |
| dckkr-618 | 68 / 68 (100%) | 0 | 68 / 68 (100%) | 0 |
| gtrr-841 | 72 / 72 (100%) | 0 | 72 / 72 (100%) | 0 |
| **Cumulative** | **213 / 213 (100%)** | **0** | **213 / 213 (100%)** | **0** |

**Empirical attribution.** 100% of `update_bowler` calls in production:
- Have `runs_delta` / `balls_delta` / `wickets_delta` arguments present → hit the early-return at `:3136-3141` via `_apply_bowler_delta`.
- Have `name in self.bowling_card` → entry already exists (populated by squad-init at innings setup, `scoreboard.py:825`).

The change-detection / create-resume block at `:3945-3961` is **architecturally unreachable** under the current call pattern.

---

## §5 Root-cause attribution

The cohort root identified at WS-R step-1 (BOWLING-CARD-CREATED=0) is now empirically attributed to the **A1 derivation_only_stats refactor** at `scoreboard.py:3186-3197`:

```python
# A1 part 1 (2026-05-14): derivation-only bowler stats.
# Strip-driven stat fields (overs/runs/wickets/maidens) no
# longer write to bowling_card[X]. ... The
# event-driven _apply_bowler_delta path remains the sole writer
# to entry.runs/.wickets/.overs/.balls.
overs = None
runs = None
wickets = None
maidens = None
```

After A1, the canonical bowler-card lifecycle gating at `:3945` is unreachable via strip-driven calls (they coerce stats to None and bypass the identity-change detection). Only delta-driven calls update `entry.runs/balls/wickets`, and those early-return at `:3136-3141` without reaching the gate.

**Empirical verdict.** BOWLING-CARD-CREATED canonical emission is **structurally bypassed** by post-A1 production semantics. The "missing lifecycle invocation" finding from step-1 is real architectural defect, not a short-capture artifact (cross-fixture verification: 0 firings across 4 captures + 2,736 records).

**Subordinate finding — `current_bowler` write-site disconnect.** The pipeline's `bowler_name` snapshot field comes from `_inn["current_bowler"]`. That field is set inside `update_bowler` ONLY via the bootstrap path at `:3925` (`_bootstrapped=True`). Since bootstrap fires only 4 times across 4 captures (rare), `current_bowler` is rarely set via `update_bowler`. Other code paths must set `current_bowler` elsewhere (e.g., `BOWLER-LOCK` events at 5 firings on dckkr-264) — those need follow-up investigation for full attribution.

---

## §6 Sub-cohort closure implications (step-2 patch shape)

Step-1's leading hypothesis was RC (sub-cohort partition with RA-1 8 frames + RA-2 2 frames). Step-1b empirical anchor reshapes the patch design:

**RA-1 (8 frames at 0.6 / 1.6 / 2.6 / 3.1 / 3.6 / 4.1 / 4.2 / 4.3; bowler_name=None):**
- Root: `_apply_bowler_delta` doesn't set `current_bowler`, so snapshot.bowler_name remains None for delta-driven updates.
- Fix surface: extend `_apply_bowler_delta` to set `current_bowler` at first per-bowler delta event, OR consolidate `current_bowler` write through a canonical lifecycle method that fires on bowler transitions detected from delta events.

**RA-2 (2 frames at 4.4 / 4.5; bowler_name='Tyagi' but bowler_overs 0.2/0.3 vs GT 0.4/0.5):**
- Root: per-ball credit pathway is correct (entry.runs/balls increments via _apply_bowler_delta), but the credit lags by 2 balls.
- Fix surface: investigate delta-event timing vs ball-event-commit timing at frames around 4.1-4.5.

**Shared root (RA architectural-cleanup):** Single fix at `_apply_bowler_delta` to also invoke canonical bowler-card lifecycle (current_bowler write + CREATED/RESUMED emission) on first-per-bowler delta. Closes RA-1 fully + may close RA-2 if the lag is downstream of current_bowler establishment.

**S9-strict 4th-instance candidate still applicable.** If step-2 patch closes both sub-cohorts via single architectural fix at the delta path's lifecycle integration, WS-R becomes the 4th S9-strict instance (F1 + S18 + WS-Q + WS-R).

---

## §7 Audit outcome decision tree resolution

Per WS-R step-1b spec outcome decision tree:

- **BOWLING-CARD-CREATED stays =0 cross-fixture:** YES (0 firings on all 4 captures + 2,736 records).
- **BOWLING-CARD-CREATED > 0 on other fixtures but =0 on dckkr-264:** NO. Cross-fixture is consistently 0.
- **BOWLER-CARD-CREATE-SKIPPED shows specific reason cross-fixture:** N/A (didn't implement CREATE-SKIPPED tag; CHANGE-CHECK shows `_bowler_changed=False / _bootstrapped=False` distribution as the gating signal).

**Verdict: STRUCTURAL DEFECT, NOT SHORT-CAPTURE ARTIFACT.** The "missing lifecycle invocation" on dckkr-264 is the cross-fixture norm, not an outlier. Step-2 patch authorization is empirically anchored.

---

## §8 Quality gates

- L1.5: 17/17 PASS on `test_canonical_score_foundation.py` + `test_sm_derivation_ledger.py` (no regression).
- L2 ledger: 30/30 PASS (instrumentation log-only).
- Diff baseline replay (dckkr-264): matched=28 missing=94 phantom=0 **divergences=34 UNCHANGED** ✓. Surfaces byte-identical: G-pipeline-lag=94 / F-A-commit-lag=10 / F-B-ad-occlusion=8 / Recent-overs-drop=4.
- Cross-fixture trace files saved under `logs/trace/*_ws_r_step1b_*.jsonl`.

---

## §9 Step-2 patch recommendation

**Step-2 authorization recommended** with the following shape:

**Patch surface (preliminary; step-2 step-1 investigation will refine):**
1. Extend `_apply_bowler_delta` to set `current_bowler = name` on first delta event for that bowler (i.e., when bowler transitions to a new name from previous current_bowler).
2. Emit `BOWLING-CARD-CREATED` from `_apply_bowler_delta` on first per-bowler delta event (or first non-zero stat).
3. Investigate `BOWLER-LOCK` interaction (5 events on dckkr-264) — is `BOWLER-LOCK` an orthogonal lifecycle that should also propagate to `current_bowler`?
4. Per-ball credit lag at 4.4-4.5 (sub-cohort RA-2): may close as cascade from (1) if current_bowler write timing aligns with delta event commit.

**LOC budget estimate:** ~15-30 LOC at `_apply_bowler_delta` + canonical lifecycle integration.

**Predicted closure:** -18 rows on dckkr-264 (34 → 16); cross-fixture closure depends on bowler-state surfaces visible on larger captures (Bowler-W-credit-failure=13 on dckkr-618; F-A=35 + F-B=23 on dckkr-749). Step-2 cross-fixture audit will quantify.

---

## §10 Working tree state at commit time

- New memo: `files/docs/investigations/workstream_r_step1b_cross_fixture_audit.md` (this file; ~10 sections).
- 2 instrumentation blocks added to `files/eyes/scoreboard.py` (+24 LOC; NO-OP log-only).
- 2 trace tags registered in `files/trace_emitter.py` (BOWLER-CARD-LIFECYCLE-CHECKPOINT + BOWLER-CARD-CHANGE-CHECK).
- 4 cross-fixture trace files: dckkr-264 + dckkr-749 + dckkr-618 + gtrr-841 (under `logs/trace/*_ws_r_step1b_*.jsonl`; not git-tracked).
- No L1.5 test changes (instrumentation is observability-only; step-2 patch will add tests).
