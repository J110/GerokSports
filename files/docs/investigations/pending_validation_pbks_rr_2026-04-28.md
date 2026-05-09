# Pending-validation analyzer — PBKS-vs-RR log (2026-04-28)

## Repository note

The path referenced in runbooks — `logs/pipeline-2026-04-28-pbks-rr-live.log` — is **not shipped in this repo** (ops artifacts stay local). CI and agents therefore **cannot** run:

```bash
python files/analyze_match_telemetry.py --log logs/pipeline-2026-04-28-pbks-rr-live.log --report-pending-validation
```

against a guaranteed-on-disk file without the operator copying the log into the workspace.

## Substitution shipped in-repo

**Synthetic coverage:** `test_pbks_rr_replay_pending_validation_catalog_all_patterns_synthetic` in `files/test_recent_fixes.py` builds a temp log containing **one canonical line per entry in** `PENDING_VALIDATION_PATTERNS` (`analyze_match_telemetry.py`), runs `analyze()`, and asserts **every** label has `hits >= 1`, and `report_pending_validation()` reports **zero** still-pending tags.

That proves regexes match the documented tag shapes; it does not replace a full production replay.

## When the real log is available

1. Copy the log under the repo (e.g. `files/fixtures/logs/pipeline-2026-04-28-pbks-rr-live.log` — optional; do not commit large binaries without policy).
2. Run:
   ```bash
   python files/analyze_match_telemetry.py --log <path> --report-pending-validation
   ```
3. For each `(pending) <label>` in the report, grep the log for substring variants (whitespace, `WARN` vs `INFO`, emoji). If the tag truly never appears, leave it **genuinely pending** awaiting natural triggers.
4. If the tag should appear but pattern misses, adjust the regex in `analyze_match_telemetry.py` and extend `test_pbks_rr_replay_pending_validation_catalog_all_patterns_synthetic` with a matching line.

## 2026-04-29 agent run (no log on disk)

- **Log file:** not found in workspace (`Glob **/*pbks*rr*.log` → empty).
- **Pattern verification:** all `PENDING_VALIDATION_PATTERNS` exercised via synthetic test above (`python` probe: `miss: []`).
- **Regex changes:** none required.
- **Genuinely pending in production:** requires operator log — not classified here.
- **Should have fired but didn’t (investigation):** not classified here without log.
