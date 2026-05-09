# Batter stats flipping fix — Task B implementation note

Issue 2 Task B: striker-aligned extractor rows at ScoreManager `FrameInput` construction (`test_pipeline.py`). Spec: `batter_stats_flipping_fix_spec.md`.

---

## §1 Implementation summary

| Item | Detail |
|------|--------|
| Files changed | `files/test_pipeline.py` (~115 lines helper + FrameInput wiring + `typing.Any` import); `files/test_recent_fixes.py` (fixtures §4.1 verbatim, helper runner with optional `ultralytics` stub, six tests, `TESTS` registration + `MagicMock` import). |
| New tests | Six: `test_align_extractor_batters_fixture_*` (fixtures A–F). |
| Pytest | `pytest files/test_recent_fixes.py -k align_extractor_batters_fixture`: **6 passed** (364 tests collected in file, +6 vs pre-change inventory). |
| Full-file pytest | **Not clean** on this workspace’s system Python (`ModuleNotFoundError: ultralytics` when importing `test_pipeline`). Failures match missing vision deps, not this change. CI environments with full deps should match project baseline. |
| Cross-match | MI–SRH log spot check (`logs/pipeline-2026-04-29-194416-mi-srh-live.log`): e.g. F53 shows strip text “Jacks … \| Rickelton …” while `AFTER_striker=Will Jacks` and legacy `AFTER_bat1`/`AFTER_bat2` followed extractor strip index (Rickelton bat1). After Task B, warm-path `FrameInput` aligns bat1→striker — **behavior can change** on frames where strip column order ≠ striker/non (expected fix surface). Frames already aligned remain no-op (fixture F pattern). |

---

## §2 Files modified

### `files/test_pipeline.py`

- **`_align_extractor_batters_for_sm`** added immediately after `_safe_float` (starts ~line 1106): Cases 1–5 per spec §3.4; `len(ext_batters) > 2` retains **`[BATTER-ALIGN]`** INFO scan line.
- **ScoreManager `FrameInput` block** (~9948–9978): `_eb1`, `_eb2` from helper; `ext_bat{1,2}_{name,runs,balls}` mirror `_safe_int`/`.get` pattern from §3.5 with **`None`** fallbacks preserved.
- **Imports:** `from typing import Any`.

### `files/test_recent_fixes.py`

- Fixtures **A–F** as dict literals from spec §4.1 (`FIXTURE_*` constants).
- **`_run_align_extractor_fixture`**: stubs `sys.modules["ultralytics"]` before importing `test_pipeline` so unit tests run without YOLO.
- Six **`test_align_extractor_batters_fixture_*`** functions; appended to **`TESTS`** before `main()`.

---

## §3 Test results

| Fixture | Result |
|---------|--------|
| A inverted strip vs striker | PASS — bat1 Sudharsan (1/1), bat2 Gill (0/0) |
| B cold striker | PASS — Alpha Z / Beta Y strip order |
| C single row | PASS — Gill bat1 only |
| D no OCR match | PASS — strip fallback + **`warn`** with **`[STRIKER-ALIGN-FALLBACK]`** |
| E partner unknown | PASS — Gill + New Batter Z |
| F F2689 ordering | PASS — Sudharsan then Gill (no-op vs strip) |

---

## §4 Cross-match validation

- **MI–SRH:** grep `AFTER_bat1|AFTER_striker` on `pipeline-2026-04-29-194416-mi-srh-live.log` shows warm frames where extractor ordering on `ext_bat` and scoreboard slots do not match striker-first semantics; Task B intentionally corrects `FrameInput` feeding ScoreManager when striker/non resolve — **expect deltas vs legacy strip-index mapping**, not silent no-op everywhere.
- **PBKS–RR:** Not re-run here (same dependency caveat).
- **Aligned-strip innings:** When strip order already matches striker/non (fixture F / GT-style Sudharsan-first plus striker Sudharsan), helper returns strip-equivalent rows — **no-op**.

---

## §5 Telemetry

| Tag | Location | When |
|-----|----------|------|
| **`[STRIKER-ALIGN-FALLBACK]`** | `test_pipeline.py`, CASE 4 branch of `_align_extractor_batters_for_sm` | Warm striker known but no extractor row matched striker/non after scans; fallback to legacy strip order `xs[0]`/`xs[1]`. Payload includes `striker_ref`, `non_ref`, **`ext_batter_names`** list. |
| **`[BATTER-ALIGN]`** | Same helper, `len(ext_batters) > 2` | INFO — multi-row scan diagnostic (unchanged from spec paste). |

**Operator note:** Elevated **`[STRIKER-ALIGN-FALLBACK]`** rate ⇒ OCR/name-resolution mismatch vs scrubbed striker/non — correlate with **`[WS-SCRUB]`** if staging shows coupling (spec §3.7).

**Spec delta:** Fixture D’s **`expect_warn_tag`: `[BATTER-ALIGN]`** described the prototype WARN string; shipped WARN uses **`[STRIKER-ALIGN-FALLBACK]`** per Task B telemetry requirement — tests assert the shipped tag.

---

## §6 Rollback

Single commit revert:

```bash
git revert <sha>
```

No migrations. Reverting restores raw `_ext_batters[0]`/`[1]` mapping on the ScoreManager frame path only.

---

## §7 Next-match validation criteria

1. **`[STRIKER-ALIGN-FALLBACK]`** volume — spikes during dirty OCR or innings churn are expected; sustained baseline drift warrants squad/`resolve_name` audit.
2. **Shadow parity:** Fewer striker-vs-strip batter stat inversions on replay vs `batter_stats_flipping_mechanism.md` symptom class.
3. **Regression guard:** Fixture A–F stay green under `pytest -k align_extractor_batters_fixture`.

---

## References

- Mechanism: `batter_stats_flipping_mechanism.md`
- Spec / fixtures: `batter_stats_flipping_fix_spec.md`
