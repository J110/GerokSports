# Target detection off-by-two diagnostic

**Date:** 2026-05-03
**Match:** SRH vs KKR (live, RESTART2 session)
**Frame:** F20 @ 18:10:17
**Symptom:** Pipeline declared `target=164` from `TO WIN 68 OFF 67` regex; actual broadcast target was `166`.

## Context

Live evidence — `logs/pipeline-2026-05-03-1808-srh-vs-kkr-RESTART2.log`:

- F19 (18:10:14) STRIP: `KKR 96-1 (8.4) | RAHANE 32(23) | RAGHUVANSHI 28(16) | SHIVANG 0-15 (1.4)` — score `96` confirmed into `scoreboard._inn`.
- F20 (18:10:15) STRIP: `KKR 98-1 (8.5) | RAHANE 32(23) | RAGHUVANSHI 30(17) | TO WIN 68 OFF 67` — strip is **internally self-consistent** at score=98 (98 + 68 = 166, the true target).
- F20 EXTRACT: `score=98-1 (8.5) target=None` plus `[STRIP-OVERLAY-DETECTED] reason=sentinel sentinel=' kph' popped=batters`.
- F20 SCORER: `Changes: ['FRAME_POISONED:98']` — score update 96→98 was **rejected** as poisoned. `scoreboard._inn.score` stayed at `96`.
- F20 CODE: `HIGH-CONF: score=96 runs_needed=68 balls_remaining=67 → target=164  pattern=TO\s+WIN[\s:]+(\d{1,3})\s+OFF\` and `[INNINGS-CHANGE] source=to_win_N_off_M target=164`.
- F21 (18:10:23) — score `96 → 98 (confirmed F21)`, but innings 2 was already locked at target=164.

## Investigation (Phase A)

### A1. Regex location
`files/test_pipeline.py:10097` — pattern list under the cold-start innings-2 branch:

```10095:10130:files/test_pipeline.py
                    _high_conf_to_win = False
                    _tw_patterns = [
                        r'TO\s+WIN[\s:]+(\d{1,3})\s+OFF\s+(\d+)',
                        ...
                    ]
                    for _pat in _tw_patterns:
                        _tw = re.search(_pat, upper_desc)
                        if _tw:
                            runs_needed = int(_tw.group(1))
                            balls_remaining = int(_tw.group(2))
                            if (runs_needed >= 1
                                    and 1 <= balls_remaining <= 120
                                    and score_now > 0):
                                detected_target = score_now + runs_needed
```

`score_now` is sourced **5 lines above** from the consensus scoreboard, not from `upper_desc`:

```10086:10088:files/test_pipeline.py
                    detected_target = None
                    score_now = int(
                        scoreboard._inn.get("score") or 0)
```

### A2. The strip was not stale — the cached score was

Frame-by-frame N values (regex group 1) and visible strip score:

| Frame | Strip score | Strip overs | TO WIN N | OFF M | scoreboard._inn.score (used) |
|------:|------------:|------------:|---------:|------:|-----------------------------:|
| F19   | 96          | 8.4         | —        | —     | 96                           |
| F20   | **98**      | 8.5         | **68**   | 67    | **96** (poisoned-rejected)   |
| F21   | 98          | 8.5         | —        | —     | 98 (confirmed too late)      |

Self-consistency check on F20 strip alone:
- 8.5 overs ⇒ 53 balls bowled ⇒ 67 balls remaining ✓ (matches `OFF 67`)
- score 98 + needs 68 ⇒ target 166 ✓ (matches broadcast)

**The strip text the regex matched against contained the correct score (98) and the correct chase (68 OFF 67) in the same frame.** The pipeline ignored the in-frame score and mixed `runs_needed=68` from F20 with `score_now=96` from F19's consensus value, off by exactly the score delta (98−96=2).

### A3. Why score 98 was rejected

`[STRIP-OVERLAY-DETECTED]` fired on F20 due to the `' kph'` sentinel (a SPEED graphic was overlaid on the strip), which made the scorer poison the score field but did **not** void the `TO WIN` extraction. The TO_WIN pattern is gated by `_INN2_FALSE_POS` keywords (`PROJECTED`, `RPO`, `PAR SCORE`, …) but `' kph'` / overlay-poisoning is not propagated to that gate.

### A4. Pattern-vs-frame edge case
The exact failure mode is **not** a stale TO_WIN value lingering across frames; it is a **single-frame inconsistency** where the score authority (`scoreboard._inn.score`) lags the strip's own visible score by one frame because the score update was rejected as poisoned in the same frame the TO_WIN was accepted.

## Root cause

`detected_target = score_now + runs_needed` reads `score_now` from `scoreboard._inn` (the lagging, consensus-validated cache) while `runs_needed` comes from `upper_desc` (the live strip text). When a frame is partially trusted — strip text accepted, score update rejected — the two operands originate from different frames and silently desynchronise. The strip itself was self-consistent at target=166; the calculation broke that consistency.

## Recommended fix

**Option (b), strengthened: extract the score from the same `upper_desc` the TO_WIN match came from, prefer strip-local score, fall back to `scoreboard._inn.score` only when the strip score is absent.**

Sketch (do not commit — investigation only):

```python
_strip_score_re = re.compile(r'\b(\d{1,3})\s*[-/]\s*\d{1,2}\s*\(\s*\d{1,2}\.\d\s*\)')
_strip_score_m = _strip_score_re.search(upper_desc)
_strip_score = int(_strip_score_m.group(1)) if _strip_score_m else None

if _strip_score is not None and _strip_score >= score_now:
    _score_basis = _strip_score
else:
    _score_basis = score_now
detected_target = _score_basis + runs_needed
```

**Decisive factor:** the strip we are already trusting for `runs_needed` carries the authoritative score for that exact moment; using it eliminates the cross-frame desync at zero added latency and zero extra consensus rounds. Options (a) and (c) add latency without fixing the underlying mix-and-match bug; option (a) would still emit `164` if the next two frames also rejected the score update.

## Test coverage gap

No fixture exercises the combination `[STRIP-OVERLAY-DETECTED] + FRAME_POISONED:<new_score> + TO WIN N OFF M in same frame`. Needed: a synthetic strip frame where (i) `scoreboard._inn.score` is `S₀`, (ii) the strip text shows `S₁ > S₀` plus `TO WIN N OFF M`, (iii) score is poisoned by an overlay sentinel, (iv) assertion: `target == S₁ + N`, not `S₀ + N`.

Suggested test name: `test_to_win_target_uses_strip_local_score_when_consensus_lags`.
