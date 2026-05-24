# Workstream R — Step-2 STOP memo: cascade hypothesis empirically falsified

**Date.** 2026-05-24.
**Branch.** `derive-not-detect` @ HEAD = `bc1045e` (WS-R step-1b instrumentation).
**Outcome.** **STOP per spec — diff baseline unchanged at 34; cascade hypothesis falsified; root analysis reveals F-A/F-B residue is a snapshotter/GT semantic mismatch, NOT a canonical-bowler-lifecycle defect. Architectural patches REVERTED.** **S9-strict 4th-instance candidate FALSIFIED for this cohort.**

---

## §1 Patch attempted

Per WS-R step-2 spec, two architectural changes were applied (≤25 LOC total):

1. **`scoreboard.py:_apply_bowler_delta` extension** — at first per-bowler delta event (`name != self._inn.get("current_bowler")`), set `self._inn["current_bowler"] = name` + emit BOWLING-CARD-CREATED (or RESUMED if entry had prior stats).
2. **`score_manager.py:sm.bowler_name` @property + setter** — converted from direct attribute to @property reading `scoreboard._inn.get("current_bowler")`; @setter writing to the same field (with fallback for no-scoreboard). Mirrors WS-Q step-2c canonical-store @property pattern.

Both changes architecturally clean; pass all 17 L1.5 tests + L2 30/30; no regressions.

---

## §2 Empirical verification — cascade did NOT close

**Diff baseline replay on dckkr-264 post-patch: 34 divergences UNCHANGED.** Predicted: 34 → 16-20 (per step-1b prediction). **OBSERVED: 34 → 34 (-0 rows).**

Per-frame snapshot inspection post-patch:

| over.ball | bowler_name pre-patch | bowler_name post-patch |
|---|---|---|
| 0.2-0.5 | Roy | Roy |
| **0.6** | **None** | **None** |
| 1.1-1.5 | Arora | Arora |
| **1.6** | **None** | **None** |
| 2.1-2.5 | Roy | Roy |
| **2.6** | **None** | **None** |
| **3.1** | **None** | **None** |
| 3.2-3.5 | Narine | Narine |
| **3.6** | **None** | **None** |
| **4.1-4.3** | **None** | **None** |
| 4.4-4.5 | Tyagi | Tyagi |

**BOWLING-CARD-CREATED tag fired 4 times post-patch** (was 0); canonical lifecycle reachable. But snapshots at the 10 F-A + 8 F-B residue frames UNCHANGED.

---

## §3 Root mechanism — between-overs state at production layer

The cause: **`current_bowler` is INTENTIONALLY CLEARED at over-end** by `test_pipeline.py:13626`:

```python
scoreboard._inn["last_bowler"] = scoreboard._inn.get("current_bowler")
scoreboard._inn["current_bowler"] = None
scoreboard._inn["bowler_between_overs"] = True
```

This is the production "between overs" state — clears at over-end while awaiting next-over consensus. When the snapshot is constructed at X.6 (after the clear) or 3.1/4.1 (before the next bowler is consensus-confirmed), `current_bowler` is None.

The snapshot reads `current_bowler` (via sm.bowler_name @property) and gets None. GT, however, attributes the X.6 ball to the bowler-who-just-finished (last_bowler) per Cricbuzz commentary convention.

**The "defect" is a SEMANTIC MISMATCH between pipeline's between-overs convention (current_bowler=None) and GT's last-bowler-attribution convention.** Not a canonical-lifecycle gap.

Subordinate: the new-over startup frames (3.1 + 4.1-4.3) show None because the new bowler hasn't reached consensus yet. Tyagi specifically takes 3 frames (4.1/4.2/4.3) before consensus picks up; GT attributes those balls to Tyagi from the first ball.

---

## §4 Why step-1b empirical anchor was correct but step-2 hypothesis was wrong

Step-1b's findings hold:
- 213/213 update_bowler calls hit delta early-return (still true).
- BOWLING-CARD-CREATED was 0 cross-fixture pre-patch (still true).
- Canonical change-detection block at `:3945` is architecturally unreachable (still true).

The step-1b finding **correctly identified** that canonical bowler-card lifecycle (CREATED tag emission) was bypassed. Step-2 patch FIXED that — emission now fires 4 times.

But step-2's hypothesis was **wrong about which surface the cohort closure attributes to**. F-A/F-B residue is downstream of `current_bowler` field state, not BOWLING-CARD-CREATED tag emission. Fixing the tag emission doesn't change `current_bowler` field state at the snapshot construction moments.

The empirical falsification is exactly what step-1b instrumentation was designed to surface BEFORE step-2 patch design — but the instrumentation focused on the tag emission rather than the field state. **S35 methodology lesson: instrumentation should anchor against the snapshot field values, not just the canonical-write trace tags.**

---

## §5 Why the WS-Q parallel doesn't apply here

WS-Q closed the score domain via canonical store (sm._canonical_score) reading authoritative under flag=1. The pattern worked because:
- sb._inn["score"] was the canonical store; the SM property read from it
- The defect class was REGRESSION-REJECTION at sb.set silently masking correct values
- Canonical store accepted the correct values when sb rejected → readers got the right answer

For WS-R bowler domain:
- sb._inn["current_bowler"] IS the canonical store already (no parallel SM-side store)
- The defect class is INTENTIONAL CLEAR at over-end (production semantic, not a rejection)
- Canonical store has None at over-end BY DESIGN — not because of a write-side rejection

**The architectural cure pattern doesn't apply** because the F-A/F-B "divergence" isn't from a canonical-bypass — it's from canonical correctly reflecting the between-overs state which GT semantics happen to disagree with.

---

## §6 Three options for the user

### Option A — Accept F-A/F-B residue as known limitation
- **Rationale:** F-A/F-B is a snapshotter/GT semantic mismatch, not production-correctness defect. Real-pipeline UI rendering at over-end can use `last_bowler` for display purposes (per the cleared-but-stored field at `:13624`). The dckkr-264 baseline residue is a test-harness artifact.
- **Action:** No code change. Document F-A/F-B as "snapshotter-GT semantic mismatch; pipeline correctly clears current_bowler at over-end per production between-overs convention."
- **Diff baseline:** stays at 34.

### Option B — Snapshotter fallback to last_bowler at over-end
- **Rationale:** Modify `_build_ui_snapshot` in `replay_captured_scout_trace.py` to add `last_bowler` to the bowler-name fallback chain (after `_last_bowler_at_wicket_commit`). Aligns snapshotter semantics with GT.
- **LOC:** ~3-5 LOC at replay script.
- **Predicted closure:** -4 to -8 rows (closes X.6 boundary frames where last_bowler is correct; new-over startup frames 3.1+4.1-4.3 remain because consensus-not-ready).
- **Risk:** test-harness change; doesn't fix production pipeline; may mask future real defects.

### Option C — GT ingester adjustment (similar to WS-V.B Phase 1 GT-encoding-fix at `c7c853e`)
- **Rationale:** Modify GT ingester to also produce None at over-end + new-over-startup positions, matching pipeline's between-overs convention.
- **LOC:** unknown; need to investigate ingester logic.
- **Predicted closure:** -18 rows potentially (full cohort).
- **Risk:** Changes GT semantics; may invalidate other surfaces' comparisons.

### Recommended: Option A
The F-A/F-B residue is empirically attributable to a test-harness/GT semantic mismatch, not a production defect. Accepting as known limitation matches the precedent at WS-V.B.Z (10-row cohort declared acceptable residue per `999ebbf` arc close-out — also a GT-vs-pipeline semantic mismatch).

---

## §7 S9-strict 4th-instance candidate — FALSIFIED for this cohort

Step-1 + step-1b had flagged WS-R as a potential 4th instance of "architectural cure closes multiple defect classes simultaneously" (F1 + S18 + WS-Q + WS-R). The empirical falsification at step-2 retires this candidacy:

- The cohort (F-A + F-B) isn't a canonical-lifecycle defect class.
- Architectural cure at canonical-write site DOESN'T close the cohort.
- S9-strict pattern requires the defect class to be downstream of a canonical-bypass.

**S9-strict promotion at WS-Q step-3 remains validated (3-instance threshold met).** Future 4th-instance candidates require empirical demonstration that the canonical cure actually closes the targeted defect class — step-2 baseline replay falsified this for WS-R.

---

## §8 Methodology lesson — S35 instrumentation scope refinement

Step-1b instrumentation anchored canonical-write-site (BOWLING-CARD-CREATED tag emission) but NOT snapshot-field-read-site (current_bowler field state at snapshot construction moments). The empirical anchor was technically correct (tag count 0 cross-fixture) but didn't expose the real mechanism.

**Going-forward S35 refinement:** when investigating a cohort attributed to canonical-bypass, instrument BOTH the canonical write-site AND the snapshot/UI-construction read-site. The read-site's actual field-resolution chain is the load-bearing piece for cascade-closure prediction.

Worth documenting as **candidate methodology insight** at step-3 close-out: "Cascade closure verification requires instrumentation of the read-site field-resolution chain, not just the canonical-write trace tags. The bypass-fix only closes the cohort IF the read-site actually consumes the canonical store at the relevant moment."

---

## §9 Quality gates (post-revert)

- L1.5 foundation: 17/17 PASS ✓
- L2 ledger: 30/30 PASS ✓
- Diff baseline replay (dckkr-264 post-revert): matched=28 missing=94 phantom=0 divergences=34 UNCHANGED ✓
- Pre-commit Layer 1.5 + Layer 2: PASS expected
- Step-1b instrumentation (`bc1045e`) preserved (NO-OP log-only; orthogonal to step-2 revert).

---

## §10 Working tree state + commit

- This STOP memo: `files/docs/investigations/workstream_r_step2_stop_memo.md` (10 sections).
- No production code changes at this commit (step-2 patches reverted).
- Step-1b instrumentation at `bc1045e` retained (separate commit; not reverted; provides cross-fixture observability infrastructure).

**Recommended next step:** User decides among Options A/B/C in §6. Option A (accept residue) is the WS-V.B.Z precedent and lowest-risk; recommended unless cohort closure is required.
