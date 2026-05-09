# Issue 2 Task A — Batter alignment validation & fix-ready specification

**Phase:** Investigation + design only. **No production code changes** in this task.

**Purpose:** Confirm [`ScoreManager._update_batters`](../../score_manager.py) (and adjacent SM paths) tolerate **semantic reordering** of `FrameInput.ext_bat1_*` / `ext_bat2_*` so **bat1 tracks striker** when warm, then specify **paste-ready Python** for [`files/test_pipeline.py`](../../test_pipeline.py) **9850–9861** for Task B.

**Anchors:** [`batter_stats_flipping_mechanism.md`](batter_stats_flipping_mechanism.md); [`logs/pipeline-2026-04-30-gt-rcb-live.log`](../../../logs/pipeline-2026-04-30-gt-rcb-live.log) tee **27048** / **`F2689`**.

---

## §1 Executive summary

### §1.1 `_update_batters` verdict

**MIXED — overall SAFE_FOR_REORDER for Task B.**

| Surface | Verdict | Notes |
|---------|---------|-------|
| **`_update_batters`** ([`score_manager.py`](../../score_manager.py) **1997–2093**) | **SAFE_FOR_REORDER** | Substitution (**2058–2073**) selects runs/balls by **`card_b1 == new`** / **`card_b2 == new`** (**name-keyed on incoming card**, not “strip geography”). Fuzzy cross-match (**2074–2093**) maps **`card_name → self.bat1_name/bat2_name`** by **`_same_name`**. Neither assumes **bat1 ≡ left OCR column**. |
| **`_build_scorecard`** (**876–896**) | **SAFE** | Copies **`frame.ext_*`** into **`card`**; scorer-change substring promotion (**884–896**) keys off whichever **`bat*_name`** substring hits — independent of striker policy. |
| **`_accept_initial` / `_init_from_card`** (**1254–1338**) | **MIXED** | **`broadcast` substring detection** tries **`bat1_name` before `bat2_name`** (**1323–1334**). That is **positional only in the weak sense** (“first field wins when both match”). Aligning **`card.bat1_*` with striker** when warm typically **reduces false positives** where the indicator applies to the striker who previously appeared only in **`bat2_*`**. Cold bootstrap (**1336–1338**) keeps **`bat1,bat2` strip order** — preserved by **Case 2 / fallback**. |
| **`_identify_and_set`** (**2171–2270**) | **SAFE_FOR_REORDER** | Explicitly documents **strip row swap** (**2197–2198**); builds **`candidates`** by **matching `card` rows to internal `bat1_name`/`bat2_name` by name**, not by fixed geometry. |

**Stop-condition S1** (**critical path DEPENDS_ON_POSITION requiring `_update_batters` refactor first**) — **NOT triggered**.

**Stop-condition S2** (**multi-site mandatory refactor**) — **NOT triggered**; optional future hardening is **`_accept_initial` indicator branch** only.

### §1.2 Fix shape

Five behavioral cases (**§3**): warm full match, cold strip-order, single-row, dual-row no-match fallback, dual-row partial match.

### §1.3 Implementation site

[`files/test_pipeline.py`](../../test_pipeline.py): introduce **`_align_extractor_batters_for_sm`** (module scope, immediately above **`run_test`** or adjacent to other `FrameInput` helpers), call from **`FrameInput(...)` construction (~9841)** replacing literals **9850–9861**.

### §1.4 Estimated Task B implementation time

**~45–90 minutes** coding + **~30 minutes** targeted pytest (`test_recent_fixes`, `test_score_manager_history_preservation`, new unit tests from **§4**).

### §1.5 Existing test coverage assessment

**Low grep surface:** **`ext_bat1`/`ext_bat2`** literals appear only in **[`files/test_recent_fixes.py`](../../test_recent_fixes.py)** (3 constructions), **[`files/test_score_manager_history_preservation.py`](../../test_score_manager_history_preservation.py)** (1), and **[`files/test_pipeline.py`](../../test_pipeline.py)** FrameInput site — **§4.2**. No tests assert **`ext_bat1 == extractor row zero`** explicitly — **stop-condition S4 unlikely**.

### §1.6 Task B readiness (**YES / NO**)

**YES — Task B can implement directly from §3–§5**, with **§2 residual semantics note** logged during code review.

---

## §2 `_update_batters` dependency analysis (Phase A)

### §2.1 Inputs consumed (from `FrameInput` → `_build_scorecard` → `card`)

Per [`score_manager.py`](../../score_manager.py) **876–882**, **`_update_batters`** reads **`card`** keys:

- **`bat1_name`, `bat1_runs`, `bat1_balls`**
- **`bat2_name`, `bat2_runs`, `bat2_balls`**

(state mutations summarized below).

### §2.2 State mutated within `_update_batters`

**Does not touch `scoreboard.batting_card` directly** — updates **`self.bat1_name`**, **`self.bat2_name`**, and attempted scalar assigns **`self.batN_runs/balls`** (**2032–2093**). **`batN_runs` live reads remain [`batting_card[self.batN_name]`](../../score_manager.py) properties (**283–357**) — scalars may log via read-only setters; **numerical authority stays scoreboard-fed**.

### §2.3 Matching model

| Branch | Match logic |
|--------|-------------|
| Bootstrap (**2030–2043**) | Adopt **`card_b1/card_b2`** wholesale when SM empty; **`_set_slot_pair(..., update_batters_bootstrap)`** if **`striker` unset**. |
| Wicket substitution (**2058–2073**) | **`arrived`/`departed` sets** via fuzzy membership (**2045–2056**). Replacement chooses **`card.get("bat1_runs")` vs `bat2_runs`** depending on **which card slot carries `new`** (**2063–2072**) — **NAME alignment**, not fixed geography. |
| Steady fuzzy merge (**2074–2093**) | Iterate **`(card_b1,*)`, `(card_b2,*)`** tuples — **`_same_name(card_name, self.batN_name)`**. |

### §2.4 Failure mode if reorder violates assumptions?

If Task B implemented **wrong alignment** (e.g., swapped striker/non):

- Substitution might attach **`new`** batter figures from wrong **`card`** slot — **detectable** as **`MULTI_BALL` / nonsensical deltas** downstream.
- Warm fuzzy merge **still reconciles names**, but **`_identify_and_set`** evidence windows depend on coherent **`prev_*`** ladders (**[`score_manager.py`](../../score_manager.py) ~1577–1584, ~2197–2228**) — misalignment increases transient **`broadcast_first_name`** reliance — **telemetry**, not silent corruption.

### §2.5 `_identify_and_set` coupling

[`score_manager.py`](../../score_manager.py) **2197–2198**:

```2197:2198:files/score_manager.py
        # Map card-side bat1/bat2 to internal batters by name (positions
        # may differ; the broadcast strip can swap the two rows).
```

**Conclusion:** Task B reorder **matches upstream intent**.

### §2.6 Log fidelity note (`F2689` / tee **27048**)

Canonical tee [**27048**](../../../logs/pipeline-2026-04-30-gt-rcb-live.log):

- **`STRIP` order:** **`Sudharsan 1(1) | Gill 0(0)`** (**27016**, **27048**).
- **`DETAIL AFTER_bat*`** stays **`Gill` → `bat1`**, **`Sudharsan` → `bat2`** (**27048**) — **SM crease-slot labels unchanged** while **`AFTER_striker=Sai Sudharsan`** (striker).

So **`F2689` is not the “Gill-left / striker Sudharsan” inversion** — strip already lists Sudharsan first. **Regression fixture §4** therefore uses **synthesized Gill-first strip** (user-visible flip class) **plus** optional **log-faithful** variant — **stop-condition S3** flagged **only for expecting pixel-perfect extractor tuple from DETAIL alone**.

---

## §3 Fix specification (Phase B)

### §3.1 Telemetry tag

**`[BATTER-ALIGN]`** — **`WARN`** on fallback **Case 4**, **`INFO`** optional when **`len(ext_batters)>2`** truncation diagnostic.

### §3.2 Helper placement

**Dedicated module-level helper** (~55 lines including docstring) in **[`files/test_pipeline.py`](../../test_pipeline.py)** — exceeds **30-line inline** threshold (**stop-condition S5**).

### §3.3 Helper signature & contract

```python
def _align_extractor_batters_for_sm(
    ext_batters: list[dict[str, Any]],
    *,
    scoreboard,
    score_mgr,
    log: logging.Logger,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
```

**Returns** `(bat1_row, bat2_row)` where each row is either **`None`** or a **`dict`** subset convertible via `.get("name"/"runs"/"balls")` identical to current **`_ext_batters[i]`** usage.

**Requires:**

- **`scoreboard.resolve_name`** ([`eyes/scoreboard.py`](../../eyes/scoreboard.py)) for extractor tokens.
- **`score_mgr.striker` / `score_mgr.non`** plus **`score_mgr._same_name`** for fuzzy equivalence when OCR omits full canonical spelling.

### §3.4 Paste-ready logic (**Cases 1–5**)

```python
from __future__ import annotations

import logging
from typing import Any


def _align_extractor_batters_for_sm(
    ext_batters: list[dict[str, Any]],
    *,
    scoreboard,
    score_mgr,
    log: logging.Logger,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Map extractor rows → (bat1_row, bat2_row) for FrameInput.

    Warm path aligns bat1=striker bat2=non when confident; preserves
    legacy strip ordering on cold striker or unresolved OCR rows.
    """

    def _strip_sentinel_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return row if row.get("name") else None

    def _row_matches_canonical(
            row: dict[str, Any],
            canonical: str | None,
    ) -> bool:
        if not canonical:
            return False
        raw = (row.get("name") or "").strip()
        if not raw:
            return False
        try:
            resolved = scoreboard.resolve_name(raw)
        except Exception:
            resolved = None
        if resolved == canonical:
            return True
        if resolved and score_mgr._same_name(resolved, canonical):
            return True
        return score_mgr._same_name(raw, canonical)

    xs = list(ext_batters or [])
    if len(xs) > 2:
        log.info(
            "  [BATTER-ALIGN] ext_batters "
            f"len={len(xs)} — scanning all rows for striker/non match")

    striker_ref = (score_mgr.striker or "").strip() or None
    non_ref = (score_mgr.non or "").strip() or None

    # CASE 3 — single-row extractor output
    if len(xs) == 1:
        only = xs[0]
        if striker_ref and _row_matches_canonical(only, striker_ref):
            return _strip_sentinel_row(only), None
        if non_ref and _row_matches_canonical(only, non_ref):
            return None, _strip_sentinel_row(only)
        return _strip_sentinel_row(only), None

    if len(xs) == 0:
        return None, None

    # CASE 2 — cold striker unknown → preserve legacy strip order
    if not striker_ref:
        return _strip_sentinel_row(xs[0]), (
            _strip_sentinel_row(xs[1]) if len(xs) >= 2 else None)

    striker_row = None
    striker_idx = None
    for _i, row in enumerate(xs):
        if _row_matches_canonical(row, striker_ref):
            striker_row = row
            striker_idx = _i
            break

    non_row = None
    if non_ref:
        for _j, row in enumerate(xs):
            if striker_idx is not None and _j == striker_idx:
                continue
            if _row_matches_canonical(row, non_ref):
                non_row = row
                break

    # CASE 5 — striker matched, partner unresolved → fill bat2 from remaining row
    if striker_row is not None and non_row is None and len(xs) >= 2:
        for _j, row in enumerate(xs):
            if striker_idx is not None and _j == striker_idx:
                continue
            non_row = row
            break

    # CASE 1 (+ CASE 5 completion) — striker row plus partner row identified
    if striker_row is not None and non_row is not None:
        return (
            _strip_sentinel_row(striker_row),
            _strip_sentinel_row(non_row))

    # CASE 4 — striker known but OCR could not match rows → fallback strip order
    log.warn(
        "  [BATTER-ALIGN] fallback strip order — striker/non could "
        f"not be matched (striker_ref={striker_ref!r}, "
        f"non_ref={non_ref!r})")

    return (
        _strip_sentinel_row(xs[0]),
        _strip_sentinel_row(xs[1]) if len(xs) >= 2 else None)
```

### §3.5 FrameInput call-site replacement (**[`test_pipeline.py`](../../test_pipeline.py) ~9841–9862**)

```python
            _eb1, _eb2 = _align_extractor_batters_for_sm(
                _ext_batters,
                scoreboard=scoreboard,
                score_mgr=score_mgr,
                log=log,
            )
            _sm_frame = FrameInput(
                frame_id=str(frame_count),
                timestamp=time.time(),
                ext_score=_safe_int(state.get("score")),
                ext_wickets=_safe_int(state.get("wickets")),
                ext_overs=_validate_overs(
                    _safe_float(state.get("overs")),
                    _bcast.get("this_over_broadcast"),
                    confirmed_overs=_safe_float(score_mgr.overs)),
                ext_bat1_name=(
                    _eb1.get("name") if _eb1 else None),
                ext_bat1_runs=(
                    _safe_int(_eb1.get("runs")) if _eb1 else None),
                ext_bat1_balls=(
                    _safe_int(_eb1.get("balls")) if _eb1 else None),
                ext_bat2_name=(
                    _eb2.get("name") if _eb2 else None),
                ext_bat2_runs=(
                    _safe_int(_eb2.get("runs")) if _eb2 else None),
                ext_bat2_balls=(
                    _safe_int(_eb2.get("balls")) if _eb2 else None),
```

*(Remainder of **`FrameInput(...)`** unchanged.)*

### §3.6 Edge behaviors (**§B3**)

| Edge | Behavior |
|------|----------|
| **`resolve_name` raises** | Treat as **`resolved=None`**; rely on **`_same_name`** residual (**inner try/except**). |
| **`score_mgr.striker == ""`** | **`strip()` collapses to **None**** → **Case 2** strip-order path. |
| **Duplicate extractor names** | First scan wins (**deterministic**); partner scan skips consumed index. |
| **`len(ext_batters) > 2`** | Scan entire list for striker/non matches — assign **`bat2`** first unmatched partner row — **`INFO`** diagnostic. |

### §3.7 WS-SCRUB / churn (**stop-condition S6**)

Alignment reads **`score_mgr.striker/non`** already scrubbed earlier in payload projection cycles — **no new scrub loops introduced**. Monitor **`[BATTER-ALIGN]` WARN rate** vs **`[WS-SCRUB]`** if staging shows coupling.

---

## §4 Test fixtures (Phase C)

### §4.1 Executable fixtures (**pytest-ready dict literals**)

**Fixture A — inverted strip vs striker (**canonical regression)**  

```python
FIXTURE_INVERTED_STRIP_VS_STRIKER = {
    "ext_batters": [
        {"name": "Shubman Gill", "runs": 0, "balls": 0},
        {"name": "Sai Sudharsan", "runs": 1, "balls": 1},
    ],
    "score_mgr_striker": "Sai Sudharsan",
    "score_mgr_non": "Shubman Gill",
    "expect_before_fix_bat1_name": "Shubman Gill",  # legacy _ext_batters[0]
    "expect_after_fix_bat1_name": "Sai Sudharsan",
    "expect_after_fix_bat2_name": "Shubman Gill",
}
```

**Fixture B — cold-start striker unset**

```python
FIXTURE_COLD_STRIP_ORDER = {
    "ext_batters": [
        {"name": "Alpha Z", "runs": 10, "balls": 8},
        {"name": "Beta Y", "runs": 4, "balls": 3},
    ],
    "score_mgr_striker": None,
    "score_mgr_non": None,
    "expect_after_fix_bat1_name": "Alpha Z",
    "expect_after_fix_bat2_name": "Beta Y",
}
```

**Fixture C — single-row striker hit**

```python
FIXTURE_SINGLE_ROW_STRIKER = {
    "ext_batters": [
        {"name": "Shubman Gill", "runs": 5, "balls": 3},
    ],
    "score_mgr_striker": "Shubman Gill",
    "score_mgr_non": "Sai Sudharsan",
    "expect_after_fix_bat1_name": "Shubman Gill",
    "expect_after_fix_bat2_name": None,
}
```

**Fixture D — dual-row OCR mismatch fallback (**Case 4**)**

```python
FIXTURE_DUAL_ROW_NO_MATCH = {
    "ext_batters": [
        {"name": "Unknown Batter X", "runs": 1, "balls": 1},
        {"name": "Unknown Batter Y", "runs": 0, "balls": 1},
    ],
    "score_mgr_striker": "Shubman Gill",
    "score_mgr_non": "Sai Sudharsan",
    "expect_after_fix_bat1_name": "Unknown Batter X",
    "expect_after_fix_bat2_name": "Unknown Batter Y",
    "expect_warn_tag": "[BATTER-ALIGN]",
}
```

**Fixture E — wicket substitution sanity (**partner unresolved Case 5**)**

```python
FIXTURE_PARTIAL_MATCH_NON_UNKNOWN = {
    "ext_batters": [
        {"name": "Shubman Gill", "runs": 12, "balls": 9},
        {"name": "New Batter Z", "runs": 0, "balls": 0},
    ],
    "score_mgr_striker": "Shubman Gill",
    "score_mgr_non": None,
    "expect_after_fix_bat1_name": "Shubman Gill",
    "expect_after_fix_bat2_name": "New Batter Z",
}
```

**Fixture F — log-faithful `F2689` extractor ordering (**documentation only**)**

```python
FIXTURE_LOG_F2689_STRIP_ORDER = {
    "ext_batters": [
        {"name": "Sai Sudharsan", "runs": 1, "balls": 1},
        {"name": "Shubman Gill", "runs": 0, "balls": 0},
    ],
    "score_mgr_striker": "Sai Sudharsan",
    "score_mgr_non": "Shubman Gill",
    "note": (
        "Matches tee 27048 STRIP column order; alignment output equals "
        "strip order — regression signal weaker than Fixture A."
    ),
}
```

### §4.2 Existing inventory (**`rg ext_bat1|ext_bat2`**)

| File | Hits |
|------|-----:|
| [`files/test_pipeline.py`](../../test_pipeline.py) | 6 assignments (**9850–9860**) |
| [`files/test_recent_fixes.py`](../../test_recent_fixes.py) | 6 literals (**1018–1019**, **1368–1369**, **2707–2708**) |
| [`files/test_score_manager_history_preservation.py`](../../test_score_manager_history_preservation.py) | 2 kwargs (**32**) |

**Likely unaffected:** abstract **`A`/`B`** batter constructions — **no ordering coupling**.

---

## §5 Implementation guidance for Task B

1. **Add** `_align_extractor_batters_for_sm` (**§3.4**) near top-level helpers in **[`files/test_pipeline.py`](../../test_pipeline.py)** (after imports resolve **`Any`** availability — reuse existing **`typing`** imports if present).
2. **Swap** **`FrameInput`** batter kwargs (**§3.5**).
3. **Unit-test** helper with **`unittest.mock.Mock`** stubs supplying **`resolve_name`**, **`_same_name`**, minimal **`score_mgr`** (**fixtures §4.1**).
4. **Replay sanity:** grep **`[BATTER-ALIGN]`** on **`pipeline-2026-04-30-gt-rcb-live.log`** expectation (**WARN sparse**).
5. **Pytest batch:**  
   `pytest files/test_recent_fixes.py files/test_score_manager_history_preservation.py -q`

---

## §6 Risks & rollback

| Risk | Mitigation |
|------|------------|
| Mis-parameterized **`score_mgr.striker`** during innings transitions | **`Case 4`** fallback restores legacy ordering + WARN. |
| **`resolve_name`** divergence vs **`_same_name`** | Dual-path (`resolved` + raw) matching (**§3.4**). |
| Indicator churn amplification (**S6**) | Telemetry-only watch — **no automatic scrub coupling**. |

**Rollback:** revert helper + **`FrameInput`** hunks (**two localized regions**) — **no schema migrations**.

---

## §7 Cross-references

| Doc / artifact | Role |
|----------------|------|
| [`batter_stats_flipping_mechanism.md`](batter_stats_flipping_mechanism.md) | Mechanism + **`9850–9861`** locus |
| [`strip_row_pairing_analysis.md`](strip_row_pairing_analysis.md) | Adjacent OCR pairing context |
| [`files/score_manager.py`](../../score_manager.py) **1997–2093**, **2171–2270**, **876–896**, **1323–1338** | Dependency proofs |
| [`files/test_pipeline.py`](../../test_pipeline.py) **8219–8224**, **8238–8286**, **4024–4033** | Adjacent orchestration surfaces |
| [`logs/pipeline-2026-04-30-gt-rcb-live.log`](../../../logs/pipeline-2026-04-30-gt-rcb-live.log) **27016**, **27048** | **`F2689`** anchors |
