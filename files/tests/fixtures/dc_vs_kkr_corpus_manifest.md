# DC vs KKR Scout-Raw Corpus Manifest

Multi-fixture Layer 2 corpus for the
`files/tests/fixtures/dc_vs_kkr_2026_152064_ledger.json` ledger
(DC innings, overs 1-6 = balls 0.1-5.6).

Each fixture is a `scout_raw.jsonl` file produced by a prior pipeline
run with `SCOUT_RAW_DUMP=1` enabled. Each has a different Scout noise
pattern (graphic overlays, sponsor banners, between-overs camera
angles, partial-strip reads) — running the harness against ALL of
them validates that fixes generalize across observable noise
distributions, not just the single fixture they were debugged on.

## Tier 1 — Strong candidates (full-window or significant subset)

Use as primary corpus for multi-fixture Layer 2. Each covers a
substantial portion of the ledger's ball range.

| Fixture | Lines | Range | Overs seen | Teams in STRIP | Notes |
|---|---|---|---|---|---|
| `watch_20260519_121701` | 264 | 0.2 → 4.1 | 31 | DC KKR LSG | **Current baseline** (29/29 PASS) |
| `watch_20260514_161246` | 409 | 0.0 → 6.5 | 40 | DC KKR LSG RCB | Full window + extra |
| `watch_20260515_161437` | 328 | 0.0 → 7.1 | 41 | DC KKR LSG MI RCB RR | Full window + extra |
| `watch_20260514_171851` | 199 | 0.0 → 3.4 | 25 | DC KKR LSG | Ledger first half |
| `watch_20260519_175143` | 198 | 2.2 → 3.5 | 24 | DC KKR RCB | Mid-window; surfaced phantom-5.4 + 6 symptoms |
| `watch_20260519_082523` | 148 | 0.2 → 2.5 | 19 | DC KKR LSG | Early window |
| `watch_20260514_120538` | 119 | 0.1 → 2.2 | 18 | DC KKR LSG RCB | Early window |
| `watch_20260514_105917` |  84 | 0.1 → 1.2 | 10 | DC KKR LSG | Cold-start coverage |

## Tier 2 — Useful for specific symptom triggers

Late-window captures; partial ledger coverage but valuable for
end-of-window edge cases.

| Fixture | Lines | Range | Overs seen | Teams in STRIP | Notes |
|---|---|---|---|---|---|
| `validate_20260513_180911` | 304 | 3.5 → 5.5 | 44 | DC KKR LSG MI RCB RR | Late window |
| `watch_20260514_183124` | 104 | 5.2 → 6.4 | 16 | DC KKR LSG RCB | Late window |
| `watch_20260514_164831` | 131 | 6.2 → 1.5 | 18 | DC KKR LSG RCB RR | First>last reversal — innings replay or restart? Investigate before inclusion |

## Tier 3 — Partial captures (too short for full ledger validation)

May still be useful for cold-start edge cases.

| Fixture | Lines | Range |
|---|---|---|
| `watch_20260516_183623` |  49 | 0.1 → 0.5 |
| `watch_20260516_184957` |  48 | 0.2 → 0.5 |
| `watch_20260514_175856` |  28 | 0.5 → 1.1 |

## DC-only captures (KKR token not extracted from STRIP)

19 files where STRIP shows DC as batting team but never extracts a
KKR token. Could be DC-vs-KKR with KKR-bowling-only frames, or
DC-vs-other-team. Sample-verify before including in corpus.

Notable: `local_20260513_172606` (465 lines, 0.3 → 9.3) is the
longest single-team-token capture — worth verifying.

## Other matches (skip for DC-vs-KKR corpus)

45 files. Primarily MI vs RCB (mid-May 2026 dev session captures)
and a few GT-RR, others. Not applicable to this ledger but reserve
for ledger expansion or other-match harnesses.

## Step 2 corpus selection

Initial multi-fixture Layer 2 corpus = **Tier 1 (8 fixtures)**.
Tier 2 (3 fixtures) added once any first/last-state anomalies in
`watch_20260514_164831` are explained. Tier 3 included if cold-start
coverage gaps surface in the harness.

Each fixture runs against the same `dc_vs_kkr_2026_152064_ledger.json`
via state-tuple matching — coverage shortfalls (fixture window not
reaching all ledger balls) report as INFO not FAIL. Per-fixture
pass criterion: zero divergences, zero ORPHAN commits across
matched balls.
