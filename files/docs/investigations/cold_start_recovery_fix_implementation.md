# Cold-start pipeline watchdog (**Path B**) — implementation memo

Companion investigation: [`cold_start_recovery_analysis.md`](cold_start_recovery_analysis.md).

**Shipped artifacts**

| File | Change |
|------|--------|
| `files/score_manager.py` | **Pipeline-frame counter** incremented for every **`mode == "COLD_START"`** **`on_frame`** call (excluding DRS **IN_PROGRESS**) even when scorer strips the card (**`_build_scorecard → None`**). Tracks **`_cold_last_viable`** (deep copy of last structured triple passing false-zero contextual rejection). **`_cold_start_maybe_pipeline_fallback`** promotes after dual thresholds guarded by **`_cold_start_plausible`**. |
| `files/test_recent_fixes.py` | Fixtures covering starvation watchdog, carousel flip-heavy watchdog, `validate_absolute` rejection path, unchanged fast consensus (`3/3`), and full-reset bookkeeping. |

**Constants (`score_manager` module)**

- **`COLD_START_PIPELINE_FALLBACK_AFTER = 25`** — paired with **`cold_frames ≥ COLD_MAX_FRAMES`** (**10**) for carousel flip deadlock.
- **`COLD_START_PIPELINE_FALLBACK_STARVATION = 45`** — starvation path needing at least **one** stamped viable coarse triple (**does not repair F5054-class scorer starvation** — **carousel/guard lane**).

**Telemetry**

Successful adoption emits:

`WARN: [COLD-START-FORCED-RECOVER] cold_watchdog_frames=… cold_iterations=… path=starvation|heavy_flip snap=… frame=…`

Followed by:

`INFO: [SM] COLD_START → WARM (pipeline watchdog) …`

**Residual risk / follow-ons**

| Risk | Mitigation already in-code | Deferred |
|------|---------------------------|-----------|
| Transient OCR consensus | **`_cold_start_plausible`** + **`validate_absolute`** | Further ML phase guard (**Direction L**) |
| Carousel wrong-but-plausible totals | Thresholds biased late | Consumer-side MULTI attribution (**Direction B**) |
| Zero viable triple ingestion | **`_cold_last_viable`** never stamps | Carousel / ingestion policy |
