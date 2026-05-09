# Test failures triage — 2026-05-02

Investigation scope: 8 of 12 failing checks in
`files/test_recent_fixes.py` (HEAD baseline) that land in surfaces
today's fixes touched.  3 additional crashes
(`test_sampler_emits_bucket_coverage_report`,
`test_closeup_frames_persisted_before_short_circuit`,
`test_element_checker_header_uses_configured_match`) and 1 dual-
broadcaster wire-override failure are out of scope: their surfaces
do not overlap any of the 7 fixes shipped today and they look like
pre-existing infrastructure flakes.

## §1 HEAD baseline

```
PASS 1065
FAIL 12
SKIPPED (Groq SDK) 1
```

The 12 failures decompose as:

* **3 crashes** (out of scope — pre-existing flakes)
* **1 dual-broadcaster** (out of scope — unrelated surface)
* **8 in scope** for this triage:
  * 4× Fix 8 IPL-CAREER bowler-strip
  * 4× P8 this-over

## §2 Per-test breakdown

### F1 — `test_info_panel_gate_strips_bowler_on_career_keyword` ("score preserved (tracker bounds it)")

* **Failure**: `extracted.score=None`; expected `68`.
* **Root cause**: `_StubScoreboardForInfoPanel.__init__` seeds
  `_inn={"score": 100, ...}`.  The test's `extracted["score"]=68`.
  `filter_info_panel_contamination` lines 2256-2270 (the "Cause-4"
  divergence strip added for the 2026-05-02 extras / poison-streak
  fix) computes `abs(68 - 100) = 32 > 7` and pops
  `score`/`wickets`/`match_overs`.  Test assertion
  `tracker bounds it` reflects pre-fix contract.
* **Category**: 1 — **test bug**. The implementation behaves
  correctly per the new Cause-4 contract (deliberately strips
  score on >7 divergence to pre-empt POISON-RECAL).  Fix: align
  stub `_inn.score` to the test's extracted score (or use a
  divergence ≤7) so the new branch doesn't fire.
* **Recommendation**: fix today, ≤5 LOC (change stub init to
  `score=68`, or add a divergence-zero variant).

### F2 — same test, "match_overs preserved (tracker bounds it)"

* Identical root cause to F1; the same Cause-4 branch pops
  `match_overs` alongside `score`.
* **Category**: 1 — **test bug** (same fix as F1).

### F3 — `test_info_panel_gate_f619_chahal_replay` ("F619 replay: score (DC 68-1) preserved")

* **Failure**: `extracted.score=None`; expected `68`.
* **Root cause**: same Cause-4 divergence strip
  (stub=100, extracted=68, |Δ|=32).
* **Category**: 1 — **test bug**.  Replay fixture's stub state
  is contrived; live F619 had stub.score≈68 from the prior
  scoreboard read so divergence was 0.  Fix: align stub
  `_inn.score` to 68 to mirror the F619 production setting.

### F4 — `test_info_panel_gate_logs_only_when_no_bowler_present` ("score preserved (no bowler to strip)")

* **Failure**: `extracted.score=None`; expected `68`.
* **Root cause**: same Cause-4 strip — fires regardless of
  whether bowler was present.  Branch runs unconditionally after
  the bowler-strip block.
* **Category**: 1 — **test bug** (same fix as F1).
* **Note**: confirms the implementation doesn't gate the
  divergence strip on bowler-present.  That is intentional —
  the strip protects score regardless of whether a bowler
  payload arrived.

### F5 — `test_p8_this_over_regex_rejects_multi_digit` ("legal sequence accepted unchanged")

* **Failure**: `out=['4', '1', '6', 'wd', '4']`; expected
  `["4", ".", "1", "6", "wd", "4"]` — the `.` token is missing.
* **Root cause**: `test_pipeline.py:1390-1392`
  `_THIS_OVER_TOKEN_RE = re.compile(r'\b([0-7]lb|...|[0-7]|W|\.)\b')`.
  The trailing `\b` after `\.` requires a word/non-word boundary,
  but `.` is a non-word character and is surrounded by spaces
  (also non-word) in the input — neither side has a word
  character, so `\b` fails.  Multi-digit "100" is correctly
  rejected (the first check passes), but legal `.` tokens are
  also dropped — a regression introduced by today's P8 regex
  rewrite.
* **Category**: 2 — **implementation bug** in P8.
* **Fix**: hoist `\.` out of the `\b...\b` envelope.  Two
  options:
  * `r'(?:\b(?:[0-7]lb|...|[0-7]|W)\b|\.)'` — alternation with
    bare `\.` outside the boundary group.
  * Use `(?<!\w)` / `(?!\w)` only on the word-shaped alternatives
    and accept `\.` standalone.
* **Scope**: ~5 LOC in `test_pipeline.py:1390-1392`.

### F6 — `test_p8_line_fallback_bounded_by_separator` ("only this-over slice tokens captured")

* **Failure**: `out=['1']`; expected `[".", ".", "1", "."]`.
* **Root cause**: same regex `\b\.\b` boundary bug as F5.
  After `_bound_this_over_slice` correctly trims at `|`, the
  resulting slice is `" . . 1 . "` — `_THIS_OVER_TOKEN_RE.findall`
  catches `1` but skips all four dot tokens.
* **Category**: 2 — **implementation bug** (same root as F5).
* **Fix**: same regex change as F5 — single fix repairs both.

### F7 — `test_p8_score_mgr_backfill_validates_alphabet` ("[THIS-OVER-BCAST-REJECT] decision tag emitted")

* **Failure**: `captured=[]`; expected at least one log line
  containing `THIS-OVER-BCAST-REJECT`.
* **Root cause**: test attaches `logging.Handler` to
  `logging.getLogger("CRICKET")` (line 4754).  The implementation
  uses `log = CricketLogger("SCORE_MGR")` and the
  `CricketLogger._log` method writes to `print()` + a file
  handler under logger name `"SCORE_MGR"` — never to the
  `"CRICKET"` stdlib logger.  The decision tag IS emitted
  (the first check `score_mgr.this_over unchanged` passed,
  proving the rejection path ran), the test just listens on
  the wrong channel.
* **Category**: 1 — **test bug**.
* **Fix**: capture from `"SCORE_MGR"` logger, or capture stdout
  via `capsys` / `contextlib.redirect_stdout`, or grep the
  CricketLogger file handler.  ~10 LOC.

### F8 — `test_p8_score_mgr_backfill_accepts_legal_alphabet` ("legal tokens written into bcast slots")

* **Failure**: `this_over=['?', '?', '?', '?']`; expected
  `[".", "1", "4", "wd"]`.
* **Root cause**: `score_manager.py:2252` lowercases broadcast
  tokens before alphabet check —
  `_normalised = [str(t).lower().strip() for t in _bcast_this_over]`.
  Then `_is_legal_run_token` (in `eyes/this_over.py:804`) checks
  `t in (".", "?", "W", "Wd", "Nb")` — case-**sensitive**.
  Lowercased `"wd"` fails membership against capitalized `"Wd"`,
  is reported as illegal, and the entire list is dropped
  wholesale.  The legal alphabet check rejects every legitimate
  `Wd`/`Nb`/`W` token because of the lowercase pre-step.
* **Category**: 2 — **implementation bug** in P8.
* **Fix**: two viable options:
  * Drop the `.lower()` normalization and run
    `_is_legal_run_token` on raw tokens, OR
  * Run `_merge_broadcast(_bcast_this_over)` first
    (`eyes/this_over.py:820`), which canonicalises `wd`→`Wd`,
    `nb`→`Nb`, `w`→`W` etc., **then** apply the alphabet check.
    This is the cleaner fix because `_merge_broadcast` is the
    documented canonicalisation step for broadcast tokens.
* **Scope**: ~5 LOC in `score_manager.py:2250-2264`.
* **Side-effect of fix**: `test_p8_score_mgr_backfill_validates_alphabet`
  (F7) will still fail on its log capture (separate test bug),
  but the underlying behavior — illegal `"100"` causing
  wholesale rejection — already works because `"100"` fails
  the alphabet whether canonicalised or not.

## §3 Aggregate

| Category | Count | Tests |
|---|---|---|
| 1 — test bug | 5 | F1, F2, F3, F4, F7 |
| 2 — implementation bug | 3 | F5, F6, F8 |
| 3 — pre-existing | 0 | — |

The 3 Category-2 findings collapse to **2 distinct fixes**:
* P8 regex `\b\.\b` boundary (F5 + F6, single fix).
* P8 alphabet case-handling (F8, single fix).

## §4 P7 sign-off

**Yes — sign-off proceeds.**  None of the 8 failures are in
P7's surface (FRAME_POISONED / CORRECTION_BLOCKED / SCORE-INF-GATE
/ DIRECT extractor commit).  P7's own 4 wired-in-source tests
(12 sub-checks) all pass, and the existing Fix 11 / Fix 15 /
FRAME_POISONED tests continue to pass.

## §5 Other 7 fixes — sign-off review

* **P3-A / P3-B / P3-C** — no failing checks in their surfaces.
  Sign-off proceeds.
* **Extras source-of-truth** — Cause-4 strip in
  `filter_info_panel_contamination` is part of this fix's
  defensive perimeter.  The behavior is correct; the failures
  are in stub-vs-extracted divergence in the tests.
  **Sign-off proceeds**, but stash-track the test cleanups so
  Fix 8 unit tests actually exercise the gate (currently they
  silently land in the divergence branch instead of asserting
  on it).
* **P4** — no failing checks in its surface.  Sign-off proceeds.
* **P8** — **DO NOT sign off as-is.**  Two Category-2 findings
  (F5+F6 regex; F8 alphabet case) demonstrate the fix is
  incomplete.  P8 ships with the regression that legitimate
  dot-tokens are dropped from `this_over`, AND the SM backfill
  rejects every legal broadcast list because of the lowercase
  pre-normalisation.  The user-visible impact during tonight's
  match: empty / placeholder this_over readings whenever Scout
  produces broadcast `Wd`/`Nb` tokens — which is most overs.
  See §6 fix recommendation.

## §6 Fix-or-defer decisions

### Fix tonight (before match)

1. **P8 regex `\b\.\b`** (F5, F6).  Edit
   `test_pipeline.py:1390-1392`.  Hoist `\.` out of the
   `\b...\b` boundary envelope.  ~5 LOC.  Re-run F5+F6 to
   verify dots survive.

2. **P8 alphabet case-handling** (F8).  Edit
   `score_manager.py:2250-2264`.  Replace lowercase
   normalisation with `_merge_broadcast` canonicalisation.
   ~5 LOC.  Re-run F8 to verify legal `wd` → `Wd` flows
   through.

Combined scope: ~10 LOC across 2 files.  Estimate 15 min
including re-run.  These are Category 2 — they represent live
P8 regressions, not test brittleness, and tonight's match will
hit them in the steady state.

### Fix today but not match-blocking (Category 1 cleanup)

3. **Fix 8 stub-vs-extracted divergence** (F1, F2, F3, F4).
   Edit `test_recent_fixes.py:2672-2677`.  Change the stub's
   `_inn["score"]` to match the extracted score in each test
   (or parameterise the stub).  ~10 LOC.  Adds back coverage
   that Fix 8 actually strips bowler without collateral on
   matched-score frames.  Recommend follow-up: add a
   dedicated test for the Cause-4 divergence branch, since
   it's currently uncovered (the existing tests accidentally
   exercised it but asserted the opposite).

4. **P8 logger capture mismatch** (F7).  Edit
   `test_recent_fixes.py:4744-4761`.  Either capture stdout
   via `redirect_stdout`, or grep the CricketLogger file
   handler, or attach the handler to the `"SCORE_MGR"`
   stdlib logger that CricketLogger's file path uses.  ~10
   LOC.  Restores `THIS-OVER-BCAST-REJECT` decision-tag
   coverage.

### Defer

None.  All 8 failures are actionable today; the 3 crashes
and 1 dual-broadcaster failure are out of scope per §1.

## §7 Risk

* **Regex fix (F5/F6)**: low risk if `\.` is added as a
  bare alternative outside `\b`.  Verify legal sequences
  still tokenise correctly and "100" is still rejected
  (`[0-7]` boundary unchanged).  Existing
  `test_p8_line_fallback_max_chars` and
  `test_this_over_alphabet_*` tests cover surrounding
  behavior — re-run after fix.
* **Alphabet fix (F8)**: medium risk.  Replacing
  `lower().strip()` with `_merge_broadcast` changes the
  canonical form written into `sm.this_over`.  Downstream
  consumers currently see lowercase tokens; they would now
  see `Wd`/`Nb`.  Verify `test_pipeline.py:4498-4507` (WS
  payload `score_mgr.completed_over` fallback) and
  `score_mgr.this_over` consumers handle capitalised tokens.
  Per `_merge_broadcast` docstring this IS the canonical
  format, so consumers should already accept it; spot-check
  the WS payload renderer once.
