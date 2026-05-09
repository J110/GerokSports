# Wire Commentary "no run" Hallucination — Investigation

**Date:** 2026-05-04
**Source log:** `logs/pipeline-2026-05-04-1924-.log`
**Status:** Diagnosed; fix deferred per scope.

## TL;DR

Wire commentary is *not* the source of the hallucination. `wire.format_wire`
is a string-format function over its input event dict, and the input it
receives is `_sm_evt = _sm_result.get("ball_event")` — ScoreManager's
classification, not BED's. **SM emits `type="DOT"` for every legal
delivery in the warm window** because, in the current dual-broadcaster
wiring, SM's `self.score` is a live read from `scoreboard._inn["score"]`,
which the upstream broadcast tracker has already mutated *before*
`score_mgr.on_frame()` is called. SM computes `d_score = c_score -
self.score == 0` and `_infer_legal(d_score=0)` returns
`{"type": "DOT", "runs": 0}`. Wire receives that and prints "no run".

The score suffix on the wire line (`11/0`, `16/0`, …) is correct because
it reads `snap.get("score")` from the same already-mutated scoreboard;
the `outcome` clause is wrong because it reflects SM's broken delta.

## Phase A — Where wire commentary is generated

Single template, single emit site:

- `files/wire.py:71` `format_wire(event, snap, state)` — pure formatter,
  no LLM. The "no run" string is hardcoded at `wire.py:89-90`:

  ```python
  if etype == "DOT":
      outcome = "no run"
  ```

- Called from `files/test_pipeline.py:11200`, inside the WS broadcast
  block, with `_sm_evt = _sm_result.get("ball_event")`:

  ```python
  _plain = format_wire(_sm_evt, ws_payload.get("scorecard", {}), score_mgr)
  if _plain:
      ws_payload["_wire_override"] = _plain
  ```

  i.e. SM authors the event type the wire renders. BED's parallel
  classification (the `[BALL ✓ FOUR / 1_RUNS / …]` log) is *not*
  consulted by `format_wire`.

## Phase B — Why SM emits DOT with a non-zero score

Trace, F185 (BED says `1_RUNS | 1.0`, wire says `no run. 11/0`):

```
1709  [TRACK]  score: 10 → 11 (post-event immediate, grace=1)
1710  [BOARD]  score: 10 -> 11 [F185]                     ← scoreboard._inn now 11
1713  [TRACK]  overs: 0.5 → 1.0
1714  [BOARD]  overs: 0.5 -> 1.0 [F185]                   ← scoreboard._inn now 1.0
1738  STATE: RCB 11-0 (1.0) ...                           ← state.get("score") == 11
1739  [SCORE_MGR] [SM-FEEDER-SYNC] field=score value=11 sb_accepted=true
1748  [SCORE_MGR] [SM] DOT  11/0 (1.0)  striker=Josh Inglis
1750  [SHADOW] SM=DOT BED=1_RUNS MISMATCH
```

Order of operations: the broadcast tracker mutates `scoreboard._inn` at
F185 line 1710. Then `_sm_frame.ext_score = state.get("score") = 11` is
assembled (`test_pipeline.py:11053`) and `score_mgr.on_frame(_sm_frame)`
runs (`test_pipeline.py:11096`).

Inside `_handle_warm` (`score_manager.py:1583-1590`):

```python
c_score = _val(card.get("score"), self.score)         # 11
...
d_score = c_score - (self.score if self.score is not None else 0)  # 11 - 11 = 0
```

The `self.score` here is the property at `score_manager.py:514-524`:

```python
@property
def score(self) -> int | None:
    if self.scoreboard is not None:
        raw = self._sb_inn_get("score")               # reads scoreboard._inn
        ...
```

There is no SM-owned snapshot of "score as of last on_frame". `prev =
self._snapshot()` at `score_manager.py:1741` re-reads the same property
and so also captures the post-mutation value. `d_score` is therefore
**always 0** when the broadcast tracker has already absorbed the score.

Then `_infer_event` at `score_manager.py:2596-2601`:

```python
if d_overs > 0:
    return self._infer_legal(d_score, striker, ...)
```

and `_infer_legal` at `score_manager.py:2775-2777`:

```python
if d_score == 0:
    return {"type": "DOT", "runs": 0,
            "this_over_token": ".", "striker": striker}
```

Wire receives `{"type": "DOT"}` and prints "no run". The `score` field
on the same wire line reads `snap.get("score")` — also from the
post-mutation scoreboard — so it correctly shows 11.

## Reproducing the pattern across the log

| Frame | Over | BED       | SM (wire)   | Wire text         |
| ----- | ---- | --------- | ----------- | ----------------- |
| F185  | 1.0  | 1_RUNS +1 | DOT 11/0    | `no run. 11/0`    |
| F189  | 1.1  | 1_RUNS +1 | DOT 12/0¹   | `no run. 12/0`    |
| F204  | 1.2  | FOUR +4   | DOT 16/0    | `no run. 16/0`    |
| F208  | 1.3  | 1_RUNS +1 | DOT 17/0    | `no run. 17/0`    |

¹ F189 SM line is `[SM] DOT 12/0 (1.1)` (lines around 1880 in log).
Every entry reproduces the same `c_score == self.score → d_score == 0`
state.

The only deliveries that *don't* hallucinate are the bona-fide dot
balls (F150 0.4, F156 0.5, F212 1.4, F220 1.5) and the SIX/FOUR at the
very start (F132, F138) which fired during cold-start consensus — those
went through `_handle_cold_start`, not `_handle_warm`, so the delta
short-circuit doesn't apply.

## Cross-checks against the brief's three hypotheses

1. *Default fallback template?* — No. `format_wire` has explicit
   branches for FOUR/SIX/RUNS/etc. (`wire.py:91-126`); the default at
   line 126 would render `"4 runs"` not `"no run"`.
2. *Race where ball_event hasn't classified yet but comm fires?* —
   Partial. The wire template doesn't wait for BED's async delivery
   classification — but BED's *event type* (FOUR/1_RUNS) is available
   synchronously on the same frame (see `[BALL ✓]` at log line 1723,
   *before* `[COMM]` at 1752). Wire isn't using it because
   `test_pipeline.py:11200` hands wire `_sm_evt`, not `ball_event`.
3. *Score field uses post-event total but text uses pre-event
   classification?* — **This is the actual mechanism, but with the
   pre-event classification being structurally unreachable, not just
   stale.** SM cannot ever see the pre-event score because its `prev`
   read shares storage with the post-event scoreboard.

## Phase C — Fix recommendations

Three options, ordered by surgical-ness.

### Option C1 — Prefer BED's `ball_event` for `_wire_override`

**Where:** `test_pipeline.py:11199-11204`.

Currently passes `_sm_evt` to `format_wire`. BED's `ball_event` is in
scope on the same line and is the [SHADOW] comparison's authoritative
side. Switch the source (with a fallback to `_sm_evt` when BED is
None — wides/no-balls without an overs tick).

- **Pros:** One-line change. Doesn't touch SM. Eliminates the wire
  hallucination immediately. The shadow log already shows BED is
  correct on these frames.
- **Cons:** Doesn't fix SM's broken event stream — anything else that
  consumes `_sm_evt` (per-ball commentary engines, telemetry,
  `ball_events` list at `test_pipeline.py:11186`) keeps seeing DOT.

### Option C2 — Defer wire emission until BED classifies

**Where:** WS broadcast block in `test_pipeline.py`.

Hold the `_wire_override` until either BED publishes a non-DOT type or
a deadline passes. Cleaner than C1 if there are frames where BED
itself hasn't fired yet, but adds latency and a state machine for a
problem C1 already solves on this dataset.

### Option C3 — Give SM its own pre-mutation snapshot (right fix)

**Where:** `score_manager.py`.

The `score`/`wickets`/`overs` properties (`score_manager.py:514-580`)
read live from `scoreboard._inn`. Add SM-owned plain fields
(`_observed_score`, `_observed_wickets`, `_observed_overs`) that hold
the *last value SM finished a frame on*. Compute `d_score` against
those in `_handle_warm`, then refresh them at the end of `on_frame`.

```python
# at top of _handle_warm
old_score = self._observed_score if self._observed_score is not None else 0
...
d_score = c_score - old_score
...
# at end of on_frame, after _accept_update / _apply_event
self._observed_score = self.score
self._observed_wickets = self.wickets
self._observed_overs = self.overs
```

- **Pros:** Fixes the structural race for *all* SM consumers, not just
  wire. Restores SM's design intent (it's supposed to *infer* events
  from deltas).
- **Cons:** Bigger blast radius — every site that compares
  `prev["score"]` with `card["score"]` is implicitly affected
  (`_infer_extra`, `_infer_wicket`, `_decompose_multi_ball`, the
  cricket-rules `validate_diff` call at `score_manager.py:1673-1680`).
  Needs careful pass over the cold→warm transition (`_handle_cold_start`
  has its own consensus loop, must not get a stale snapshot from a
  prior aborted warm window). Existing tests in
  `test_recent_fixes.py` build SM in isolation without a scoreboard
  attached — the fallback `_sm_scalar_fallback` path
  (`score_manager.py:524`) does *not* exhibit the bug, so the existing
  tests pass even though production is broken; new regression tests
  with a real `Scoreboard` attached would be required.

### Recommendation

Ship **C1 today** (one-line, eliminates the user-visible hallucination,
zero risk to SM internals) and open **C3 as a follow-up** because
`_sm_evt` is consumed elsewhere — most notably the `ball_events` list
that downstream telemetry trusts. The [SHADOW] MISMATCH log is
currently flagging the same bug from the BED side; once C3 lands, that
log should go quiet on warm-mode legal deliveries.

## Pointers

- Wire template: `files/wire.py:71` (`format_wire`), branches at lines
  89-126.
- Wire call site: `files/test_pipeline.py:11200` (`_wire_override`).
- SM live-property bug: `files/score_manager.py:514-524` (score),
  `files/score_manager.py:570-580` (wickets), `files/score_manager.py:1583-1590`
  (delta computation), `files/score_manager.py:2775-2777` (DOT
  fallback).
- Shadow comparison: `files/test_pipeline.py:11141-11149` — the
  `[SHADOW] SM=… BED=… MISMATCH` log is currently the only signal
  surfacing this race.
