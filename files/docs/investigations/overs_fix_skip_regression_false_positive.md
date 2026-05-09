# [OVERS FIX] SKIP regression guard — false-positive analysis

Source log: `logs/pipeline-2026-05-03-2058--stage1ready.log`
Guard site: `files/test_pipeline.py:1382-1387` (`_validate_overs`)
Window investigated: F213 → F244 (21:08:51 → 21:10:49), the 18.0 → 18.2 stall

## TL;DR

The guard is **sound on its inputs**. At F230 it correctly rejected a
(X-1).N correction that would have rolled overs backward from confirmed
18.0 to 17.2 on stale `this_over` tokens. The legitimate 18.1 STRIP
reads at F231/F239/F240 **never reached the guard's regression branch**
— extractor returned 18.1 directly and the early-return at line 1344
bypassed it. The P4 memo's hypothesis ("guard may have rejected
legitimate 18.1 reads") is **not supported** by the trace.

The actual stall blocker lives **downstream of `_validate_overs`** in
the ScoreManager / state-commit path, not in this guard.

## Phase A — Guard logic

`_validate_overs(ext_overs, broadcast_this_over, confirmed_overs)`:

- `ball_from_overs = round((ext_overs % 1) * 10)`
- `ball_from_tokens = len(broadcast_this_over)`
- Early return when the two agree (line 1344) — **legitimate STRIP
  reads with matching tokens never see the regression guard.**
- (X-1).N branch (line 1366) when `ball_from_overs == 0` and
  `ball_from_tokens > 0`: `corrected = (ext_int - 1).tokens`.
- X.N branch (line 1368) otherwise: `corrected = ext_int.tokens`.
- Regression guard (line 1382): if `corrected < confirmed_overs`
  (float compare), return `ext_overs` unchanged.

Comparison is float `<`, not string. No lexical-order pitfall, no
rounding hazard at one-decimal precision.

## Phase A — Frame-by-frame trace, F213-F244

All extractor `(overs)` and tracker `STATE (overs)` columns:

| F   | STRIP overs | this_over   | E overs | STATE overs | OVERS FIX               |
|-----|-------------|-------------|---------|-------------|-------------------------|
| 213 | (18)        | null        | 18      | 18.0        | —                       |
| 214 | (18)        | null        | 18      | 18.0        | —                       |
| 215 | (18)        | null        | —       | 18.0        | —                       |
| 216 | (18)        | 2/2         | —       | 18.0        | —                       |
| 217 | (18)        | null        | —       | 18.0        | —                       |
| 218 | (18)        | null        | —       | 18.0        | —                       |
| 220 | (6.4)       | 1/1.        | —       | 18.0        | —  (different scoreboard)|
| 221 | (null)      | null.       | —       | 18.0        | —                       |
| 226 | (3.2)       | 4.          | —       | 18.0        | —  (different scoreboard)|
| 227 | (null)      | null        | —       | 18.0        | —                       |
| 228 | (18)        | null        | —       | 18.0        | —                       |
| 229 | (18)        | 2/2         | —       | 18.0        | —                       |
| 230 | (18)        | 2/2         | 18.0    | 18.0        | **SKIP regression** 17.2<18.0 |
| 231 | (18.1)      | null        | 18.1    | 18.0        | — (early-return: 1==0 false; 1!=0 → X.0=18.0; not <conf) |
| 236 | (8.1)       | 1.          | —       | 18.0        | —  (different scoreboard)|
| 237 | (8.2)       | 1.2.        | —       | 18.0        | —  (different scoreboard)|
| 239 | (18.1)      | null        | 18.1    | 18.0        | —                       |
| 240 | (18.1)      | null        | 18.1    | 18.0        | —                       |
| 241 | (18.2)      | null        | —       | 18.0        | —                       |
| 242 | (18.2)      | null        | —       | 18.0        | —                       |
| 243 | (18.2)      | null        | —       | 18.0        | —                       |
| 244 | —           | —           | —       | 18.0 → 18.2 | TRACK commit (post-event immediate) |

### F230 in detail

- `ext_overs = 18.0`, `broadcast_this_over` length = 2 (from `2/2`)
- `ball_from_overs = 0`, `ball_from_tokens = 2` → not equal
- digit-swap branch: `conf_int=18`, `ext_int=18`, `18 > 19` false → skip
- (X-1).N branch fires: `corrected = float("17.2") = 17.2`
- Regression guard: `17.2 < 18.0` → SKIP, return `ext_overs=18.0`

The same frame's `OVER` module logged
`Broadcast ['2', '2'] ignored — score 141 has not advanced past last
mutation (141); this_over is score-gated.` This corroborates that the
`2/2` tokens were stale (an old over's circles, not the live over) —
the guard fired on genuinely poisoned input and made the right call.

### F231/F239/F240 — the legitimate 18.1 reads

- `ext_overs = 18.1`, `broadcast_this_over` is `null`/empty
- `_validate_overs` short-circuits at line 1332 (`len == 0 → return
  ext_overs`). The regression guard is **never reached.**
- `_validate_overs` returns 18.1, but `STATE` stays at 18.0 — the
  rejection is downstream.

## Phase B — Candidate root causes

| # | Hypothesis | Evidence | Verdict |
|---|------------|----------|---------|
| a | String-compare lexical order ("18.1" < "18.0") | Code does float `<` at line 1382 | **Not the bug** |
| b | Float rounding (18.1 stored as 18.0999) | Both sides constructed from `f"{int}.{int}"` formatting; one-decimal precision; comparison is `<` not `<=` | **Not the bug** |
| c | `confirmed_overs` is a stale higher value than what UI shows | At F230, confirmed=18.0 matches STATE display; no evidence of stale-high confirmed | **Not the bug at F230** |
| d | Tokens-based derivation (X-1).N is wrong shape when confirmed_int == ext_int | (X-1).N model assumes "rolled into new over, scout stale on prev"; when confirmed already at X.0, the only sane derivation from tokens is X.tokens | **Real but secondary** — guard correctly rejects, function then returns unchanged 18.0 instead of plausibly-correct 18.2 |
| e | Guard rejected genuine stale input; bug is upstream/downstream | F231/F239/F240 prove extractor produced 18.1 cleanly and the guard was bypassed; STATE still stuck at 18.0 → blocker is in ScoreManager / state-commit | **Confirmed root cause** |

## Recommended fix

**Do not modify `_validate_overs`.** The guard is correct on its
inputs at F230, and is bypassed entirely on the legitimate 18.1 reads
at F231+. Changing its semantics will not unblock the stall.

The stall investigation should redirect to **ScoreManager's
state-commit path**: why did `ext_overs=18.1` (and later 18.2) at
F231/F239/F240/F241/F242/F243 fail to advance `STATE` from 18.0 until
F244's `post-event immediate` commit? Likely candidates:

- ScoreManager `confirm_overs` requires multi-frame agreement that the
  18.1 reads kept resetting (extractor missed F232-F235 and F238)
- Score-gating that requires runs to advance with overs, and
  `score=144` was disagreed-upon vs tracker's 141
- Cold-start / re-warmup hysteresis

Pick this up in a separate investigation focused on ScoreManager.

A minor secondary improvement (low priority, do not bundle with
stall fix): when the regression guard rejects (X-1).N because
`conf_int == ext_int`, consider returning `float(f"{ext_int}.{tokens}")`
instead of unmodified `ext_overs`. This would have produced 18.2 at
F230 — but at F230 the tokens were known-stale (score-gated reject in
OVER module), so even this "improvement" would have been wrong. Defer.

## Linked issues

- Tracker stall investigation (F213-F243 frozen at 18.0)
- U4 visible symptom (stale overs on UI during stall window)
- P4 memo: hypothesis "guard rejected legitimate 18.1" — **disproved**
  by this analysis
