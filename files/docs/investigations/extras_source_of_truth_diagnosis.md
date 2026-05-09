# Extras Source-of-Truth Oscillation Diagnosis

**Date:** 2026-05-02
**Trace:** `logs/trace/866ce150.jsonl`
**Live log:** `logs/pipeline-2026-05-02-1225-wi-vs-rsa-2nd-t20i-south-africa-tour-of-west-indies-2024.log`
**Status:** Investigation only — no code written.

---

## §1 Symptom

Anmol's RR-DC observation (yesterday): "extras was all over the place" — UI extras counter visibly oscillating throughout the match. P4 diagnosis on trace `866ce150` surfaced the same pattern as a side-effect of the F185 score-rejection investigation:

| Frame | UI `extras_total` | Note |
|------:|------------------:|------|
| 178 | 0 | cold-start |
| 179 | 0 | committed `score→11` (cf. live log F158 first inference event) |
| 180 | **7** | first jump |
| 181-184 | 7 | stable (incl. F184 `FRAME_POISONED`) |
| 185 | 7 | `SCORE-INF-GATE:proposed=11<bat_sum=8+extras=7` rejected commit |
| 186 | **3** | snap |
| 198+ | 3 | stable |

Live log shows the same oscillation pattern in dozens of other frames, e.g. `F277 extras=0 → F280 extras=2 → F283 extras=1` (with score pinned at 13).

This is not a one-off F185-only issue. It is a continuous match-long oscillation.

---

## §2 Trace evidence — frame-by-frame inference fires

Cross-checking trace + live log pipeline-2026-05-02-1225 against the `[EXTRAS-INF]` writer log:

```
F158: [EXTRAS-INF] wkts=0: score=4  - bat_sum=3  = extras=1
F160: [EXTRAS-INF] wkts=0: score=4  - bat_sum=4  = extras=0   ← bat_sum caught up
F180: [EXTRAS-INF] wkts=0: score=11 - bat_sum=4  = extras=7   ← bat_sum lagged badly
F186: [EXTRAS-INF] wkts=0: score=11 - bat_sum=8  = extras=3   ← Hendricks 2→6 commit
F214: [EXTRAS-INF] wkts=0: score=12 - bat_sum=11 = extras=1
F277: [EXTRAS-INF] wkts=1: score=13 - bat_sum=13 = extras=0
F280: [EXTRAS-INF] wkts=1: score=13 - bat_sum=11 = extras=2   ← bat_sum REGRESSED
F283: [EXTRAS-INF] wkts=1: score=13 - bat_sum=12 = extras=1
```

Writer-site activity counts in this match:

| Writer site | Fires |
|---|---:|
| `[EXTRA]` (record_extra increments) | 9 |
| `[EXTRAS-INF]` (inference overwrites `extras['total']`) | 11 |
| `[EXTRAS] Broadcast total` (sets `extras['broadcast_total']`) | **0** |

The inference at `test_pipeline.py:6510` fires more often than `record_extra` and is the **last writer** in every frame it runs — it wins.

---

## §3 Extras writer map

### Writer 1 — `record_extra` (per ball_event=EXTRA)

- **Site:** `files/eyes/scoreboard.py:3973-4000`
- **Trigger:** Called from `test_pipeline.py:9787-9793` when `ball_event["type"] == "EXTRA"` and `ball_event["extra_type"]` resolves to wide / no_ball / leg_bye / bye.
- **Mutation:** `self.extras[key] += runs` and `self.extras["total"] += runs`. Monotonic-incremental.
- **Authority:** Designed as the sole authoritative live counter (header comment at `test_pipeline.py:9584-9601` says ball_event path is the *sole* authority).

### Writer 2 — Broadcast info-panel total (rarely fires)

- **Site:** `test_pipeline.py:6450-6456`
- **Source:** `_RE_EXTRAS_PANEL` regex match on scout text (parsed at `test_pipeline.py:1482-1486`).
- **Mutation:** `scoreboard.extras["broadcast_total"] = _be_total` — **separate key**, NOT `total`.
- **Condition:** `_bcast["extras_total"] > sum(scoreboard.extras.values())`.
- **Risk:** Inert in this match (0 fires). The "sum of all values" comparison includes the same key being written, so subsequent fires require strictly higher broadcast values. Does NOT collide with `total`.

### Writer 3 — Inference (post-commit)

- **Site:** `test_pipeline.py:6458-6516`
- **Source:** `extras['total'] = max(0, score - bat_sum)` where `bat_sum` is summed across all `batting`/`out` rows in `scoreboard.batting_card`.
- **Mutation:** `scoreboard.extras["total"] = _ei_inferred`. Hard overwrite.
- **Conditions to fire:**
  1. `score is not None and wickets is not None`,
  2. all batting-card rows in `batting`/`out` status have `runs` known,
  3. dismissed-batter row count equals `wickets`,
  4. at least one active batter has known runs,
  5. `_ei_inferred != _cur_t` (any change),
  6. `_ei_inferred <= 40` (sanity clamp).
- **Lacking guards:**
  - No "score just changed" gate.
  - No "bat_sum stable for N frames" gate.
  - No monotonicity (will write smaller values, *and* larger values, frame-to-frame).

### Writer 4 — Score-manager `_extras_writable` properties

- **Site:** `files/score_manager.py:295-313`
- **Mechanism:** Properties `innings_extras` / `this_over_extras` / `extras_log` setter writes — but `_extras_writable()` returns `self.scoreboard.extras` when the SM is bound (line 256-259). So SM and scoreboard share the same dict. There is no second store; SM is not a competing writer in practice.
- **Reset:** `score_manager.py:793-798` on `full_reset` clears both views.

### Writer 5 — Reader (cited by P4): `_score_inf_floor_components`

- **Site:** `test_pipeline.py:3100-3133`
- **Read-only:** returns `extras['total']` (or 0 if missing) for the SCORE-INF-GATE Layer 1.5 floor at lines 3318-3331.
- **Not a writer**, but a *consumer* whose output cascades into score-rejection decisions.

---

## §4 Identified oscillation mechanism

There is effectively **one writer that matters: the post-commit inference at `test_pipeline.py:6510`**. `record_extra` increments correctly but is overwritten by the inference on the very same frame (and on subsequent frames) since the inference runs unconditionally on every frame where its completeness gate passes.

**The oscillation cause is not "two writers fighting" — it is one writer with unstable inputs.**

`extras['total'] = score - bat_sum` is computed every frame; both `score` and `bat_sum` fluctuate frame-to-frame due to:
- transient OCR misreads of the strip (delayed batter-runs upgrades, regressions, e.g. F277→F280 bat_sum regression 13→11),
- score commits that arrive on different frames than batter-runs commits (F180: score=11 already committed but batter card still showed 2+2=4 → inferred=7; F186: Hendricks ratcheted to 6 → inferred=3),
- score commits made by SCORE-INF-GATE/EXTRAS-INF-GATE rejection vs admission (no symmetric clamp on extras).

The inference's correctness depends on `score` and `bat_sum` being read at the same logical instant. The pipeline does not guarantee that: batter-runs upgrades trail score upgrades by 1+ frame routinely, and OCR can regress batter runs transiently.

---

## §5 Case classification

**Hybrid Case 2 + Case 3**, leaning Case 2.

- **Case 2** (one writer wrong): the inference fires when `bat_sum` is stale, producing wrong values. This is the dominant failure mode.
- **Case 3 angle** (architectural feedback): the inference's output feeds the Layer 1.5 SCORE-INF-GATE floor (3318-3331) which then rejects valid score commits (F185 evidence). This is a feedback loop: extras-inference uses score & bat_sum → writes extras['total'] → next frame's floor uses extras['total'] → may reject score commit that would have stabilized bat_sum. The Layer 1 EXTRAS-INF-GATE (at line 3550) explicitly avoided this loop by using `known_extras = 0` (per its own header comment, line 3586-3592). Layer 1.5 did not adopt the same defense.

Not Case 1 (no last-write-wins ordering bug — the inference always wins because there is no real competing late writer).

Not Case 4 (no shadow-eval architectural rebuild required; the fix is bounded).

---

## §6 Proposed fix

### Recommended: drop inference as authoritative source of truth

Reclassify `[EXTRAS-INF]` as **diagnostic-only** and stop writing `scoreboard.extras['total']` from the inference. Have it write to `scoreboard.extras['inferred_total']` instead (already paired with `extras['inferred'] = True` flag at 6511).

- **LOC:** ~5-10 lines in `test_pipeline.py:6504-6516` (rename target key, keep log).
- **Files touched:** `files/test_pipeline.py` only.
- **`extras['total']` becomes:** monotonically non-decreasing, only mutated by `record_extra` (ball_event=EXTRA path) and `full_reset` (innings boundary).
- **UI behavior:** stable per-innings extras counter, drifts low when broadcast misses an extra event, never oscillates.

### SCORE-INF-GATE behavior change

`_score_inf_floor_components` at 3100-3133 reads `extras['total']`. With the fix:
- The floor uses only `record_extra`-counted extras (potentially under-counted).
- Floor formula becomes: `proposed_score < bat_sum + record_extra_count`.
- Loss of protection: phantoms where `proposed_score < bat_sum + true_extras` but `proposed_score >= bat_sum + record_extra_count` slip through.
- **Mitigating factor:** Layer 1 EXTRAS-INF-GATE (3676-3694) already catches the dominant phantom class (`bat_sum > score`, the cricket-physics floor with `known_extras = 0`); Fix 15 score-side gate (3346-3428) catches advance-side phantoms. The Layer 1.5 floor's marginal contribution is small; the cost of feedback-driven oscillation is large (visible to user).

### Alternative (keep inference as truth, reduce oscillation): stability gate

Require `bat_sum` and `score` to have been the same as the previous N frames before firing the inference. ~20-30 LOC, adds frame-history state. Slower convergence on real extras events; still oscillates if data flips back-and-forth in a slow alternation. Not recommended.

### Alternative (monotonic ratchet)

Change `if (_ei_inferred != _cur_t and _ei_inferred <= 40):` to `if (_ei_inferred > _cur_t and _ei_inferred <= 40):`. Single-line change. **Rejected** because it preserves any spurious upward spike (F180's `extras=7` driven by stale bat_sum=4 would lock in for the rest of the innings).

---

## §7 Risk assessment

### Downstream consumers of `extras['total']`

- `test_pipeline.py:3128` — `_score_inf_floor_components` for SCORE-INF-GATE Layer 1.5 floor (3318). **Affected.** Mitigated by Layer 1 + Fix 15 still firing; floor weakens but does not break.
- `test_pipeline.py:10894` — end-of-match summary log line. Cosmetic, will show real (record_extra-counted) total instead of inference-derived.
- `score_manager.py:291-296` — `innings_extras` property. Reads extras['total']. Used in:
  - `score_manager.py:1899` snapshot creation (cached state) — cosmetic.
  - `score_manager.py:3175-3178` SM `summary()` for logging — cosmetic.
- `files/trace_emitter.py:286` — emits `extras_total` to trace records. **Affected** (trace will reflect real value, not oscillating inferred value — strictly an improvement for `analyze_trace.py` rules).
- `files/anomaly_rules.py:515` — reads `ui_after.extras_total` for an anomaly rule. **Affected** — reduces false-positive rate from the oscillation noise.
- UI scorecard render (frontend): displays `extras['total']`. **Affected** — fixes the visible bug.
- Tests `files/tests/test_anomaly_rules.py:109` and `files/test_recent_fixes.py:8612` — set `extras['total']` directly; unchanged in behavior.

### Regression surface

1. **SCORE-INF-GATE Layer 1.5 floor weakens.** Phantoms admitted that would have been rejected when extras['total'] was inflated. Class size: small (Layer 1 already covers the bat_sum > score case; the floor only catches score-side under-shoots). Acceptable trade-off.
2. **`broadcast_total` orphaned.** The 6450-6456 block writes `extras['broadcast_total']` for diagnostic comparison; nothing reads it currently. Stays harmless.
3. **`extras['inferred']` flag.** Currently set alongside `extras['total']` overwrite. Keep the flag attached to the new `inferred_total` write so consumers can detect inference happened. No known consumer reads it today.

### Test plan (recommended pre-merge)

1. Run trace 866ce150 through `analyze_trace.py` — verify `extras_total` no longer oscillates.
2. Run F232/F239/F257/F262/F263/F278 phantom suite — verify EXTRAS-INF-GATE Layer 1 still fires (these don't depend on Layer 1.5 floor).
3. Confirm F185 SCORE-INF-GATE no longer rejects (the rejection was driven by inflated `extras=7`).

---

## §8 Recommendation: ship today

**Ship the §6-recommended fix (rename inference target to `inferred_total`) today, not deferred.**

Reasoning:
- The bug is user-visible and continuous (RR-DC direct observation).
- Fix is bounded: ~10 LOC in one file.
- Regression surface is small and analyzable: Layer 1.5 floor weakens marginally; Layer 1 (the dominant phantom catcher) is unaffected.
- Trace evidence is clear and reproducible — analyzable without a shadow eval.
- A shadow eval is **not** required because:
  - The change converts `extras['total']` from oscillating to monotonic. Monotonic is strictly easier to reason about.
  - The downstream consumer set is enumerable (§7) and small.
  - The Layer 1 / Fix 15 gates are independent of `extras['total']` and provide the primary phantom-rejection authority.

A shadow eval *would* be required if we were redesigning extras as a multi-source aggregate (broadcast + record_extra + inference + reconciler) — that is a different scope and not what's needed here.

**Specific file:line change site:** `files/test_pipeline.py:6510` — change target key from `"total"` to `"inferred_total"`. Keep the log line. Optionally add a one-line comment pointing to this memo.

---

## Appendix — files read

- `files/test_pipeline.py:1470-1500` (info-panel extras parse)
- `files/test_pipeline.py:3100-3133` (`_score_inf_floor_components`)
- `files/test_pipeline.py:3308-3428` (SCORE-INF-GATE Layer 1.5 floor + advance)
- `files/test_pipeline.py:3550-3696` (Layer 1 EXTRAS-INF-GATE)
- `files/test_pipeline.py:6440-6520` (post-commit broadcast/inference block)
- `files/test_pipeline.py:9580-9620, 9760-9800` (ball_event=EXTRA dispatch)
- `files/test_pipeline.py:10880-10895` (end-of-match summary)
- `files/eyes/scoreboard.py:3970-4030` (`record_extra`)
- `files/score_manager.py:255-313, 793-798` (`_extras_writable`, properties, reset)
- `logs/trace/866ce150.jsonl` (frames 178-200, jq-filtered)
- `logs/pipeline-2026-05-02-1225-wi-vs-rsa-2nd-t20i-south-africa-tour-of-west-indies-2024.log` (grep `EXTRAS\]\|extras\[`)
