# Striker write thrashing (S1 cutover gap)

Investigation date: 2026-05-03
Anchor log: `logs/pipeline-2026-05-03-1808-srh-vs-kkr-RESTART2.log`

## Context

During SRH vs KKR (RESTART2 session), `[STRIKER-WRITE]` logging
showed ~12 lines per few-minute window with `non` flapping between
`Ajinkya Rahane` and `Angkrish Raghuvanshi` every frame:

```
F1  non None->Ajinkya Rahane
F1  non Ajinkya Rahane->Angkrish Raghuvanshi
F2  non Angkrish Raghuvanshi->Ajinkya Rahane
F2  non Ajinkya Rahane->Angkrish Raghuvanshi
F3  non Angkrish Raghuvanshi->Ajinkya Rahane
F3  non Ajinkya Rahane->Angkrish Raghuvanshi
…
F22 WARN: [STRIKER-COLLISION] Refusing non=Angkrish Raghuvanshi
        — already striker; would self-collide
```

Counts in this single session:
- `[STRIKER-WRITE]` non flips: 12+ per minute, sustained
- `[STRIKER-COLLISION]`: 40+ refusals from F22 onward
- `[BATTER-CONSENSUS-RESET]`: 94 fires (N4)

Both batters are real (Rahane and Raghuvanshi opened for KKR), so
this is not a misread/poisoned-frame case. The flap is in the
*striker bool* per row, not the names.

## Root cause

The `[STRIKER-WRITE]` log pin to `test_pipeline.py:9053
(run_test)` is misleading. The `_StrikerLoggingDict` wrapper
(`test_pipeline.py:658-686`) deliberately skips frames where
`os.path.basename(frame.filename) == "scoreboard.py"` so it can
surface "external" entry points. The actual writer is **inside**
`scoreboard.update_batter` at `files/eyes/scoreboard.py:2387` /
`:2396` — the Fix 5 backstop branches:

```python
elif striker is True:
    if self._inn.get("non") == name:
        log.warn("[STRIKER-COLLISION] Refusing striker=…")
    else:
        self._inn["striker"] = name
elif striker is False:
    if self._inn.get("striker") == name:
        log.warn("[STRIKER-COLLISION] Refusing non=…")
    else:
        self._inn["non"] = name
```

The "external" caller surfaced is whatever called
`scoreboard.update_batter(…, striker=…)`. In tonight's session the
hot path is the DIRECT batter update at `test_pipeline.py:9053`:

```python
if scoreboard.update_batter(
        _db_name,
        runs=_db.get("runs"),
        balls=_db.get("balls"),
        striker=_db.get("striker"),   # ← per-frame striker bool from extractor
        frame=frame_count):
```

`_db` comes from `extracted["batters"]` — the per-frame strip
parse, where the striker bool is derived from asterisk position.
Asterisk parsing on the SRH-vs-KKR strip is unstable (rows render
in inconsistent order across consecutive frames), so the bool
flaps. Every flap drives a fresh `update_batter` call with
`striker=True/False`, which in turn:

1. Trips the `_batter_slot_last_identity` bookkeeping at
   `scoreboard.py:1922-1927`, calling
   `_reset_batter_consensus_for(name)` whenever the slot's last
   identity changes — this is N4
   (`[BATTER-CONSENSUS-RESET]`, 94 fires).
2. Writes `_inn["striker"]` / `_inn["non"]` via the Fix 5
   branches — surfaced as `[STRIKER-WRITE]`.
3. Once the next frame's flapped bool arrives before the previous
   one is overwritten, both names race the same slot →
   `[STRIKER-COLLISION]`.

### Why this slipped through S27

The S27 comment at `test_pipeline.py:9132-9144` removed two
legacy non-SM striker writers ("STRIKER FROM BALLS-FACED CHANGE"
and "BROADCAST STRIKER WINS"). It explicitly noted that SM
already consumes `broadcast_striker` via the frame card and
handles striker inference from balls-faced via its own ball-event
ingest. But the DIRECT batter update path was left untouched —
it still threads `striker=_db.get("striker")` into
`update_batter`, even though the DIRECT path's purpose is batter
*stats* (runs/balls/fours/sixes), not striker authority.

The same shape exists at:
- `test_pipeline.py:9174-9179` (BATTER REPLACEMENT after wicket)
- `test_pipeline.py:4225-4228` (`apply_scorer_decision`, scorer
  LLM path) — this one is genuinely the "LLM striker= flag"
  case the Fix 5 backstop comment at `scoreboard.py:2398-2402`
  refers to, and SHOULD continue to pass `striker=`.

### U3 link (striker tag wrong on UI)

Per the Fix 5 comment block (`scoreboard.py:2360-2402`), the WS
payload is unaffected because it reads via ScoreManager, but
**commentary subsystems (storyteller / analyst / colour) and
persisted DETAIL telemetry both read `sb._inn` directly**. When
`_inn["striker"]` lands on the wrong batter due to flapped
asterisk parses, those consumers emit "X faces X" prose and
zero-length partnerships. U3 (striker tag wrong) is a downstream
read of the same flap, not an independent bug.

## Recommended fix

**Approach (b)-scoped: stop passing `striker=` from
extractor-driven DIRECT paths into `update_batter`.**

Concretely, change two call sites:

1. `test_pipeline.py:9053-9058` (DIRECT batter update):
   drop `striker=_db.get("striker")`. The per-frame asterisk
   bool should not drive `_inn` writes; SM ingests
   `broadcast_striker` via the frame card and is the authority.

2. `test_pipeline.py:9174-9179` (BATTER REPLACEMENT post-wicket):
   drop `striker=_rb.get("striker")` for the same reason. The
   replacement path's job is admitting a new batter to the card,
   not picking who's on strike.

Leave `apply_scorer_decision` at `test_pipeline.py:4225-4228`
unchanged — that is the LLM `striker=` path the Fix 5 backstop
explicitly preserves, and it goes through
`_set_inn_slot_with_sm_mirror` for `_inn` consistency.

This fix:
- Eliminates the per-frame `_inn["non"]` flap (STRIKER-WRITE)
- Eliminates the consequent `[STRIKER-COLLISION]` cascade
- Eliminates the `[BATTER-CONSENSUS-RESET]` storm (N4) caused
  by `_batter_slot_last_identity` churn from this path
- Preserves the Fix 5 backstop for genuine LLM striker decisions

## Risk assessment

**Downstream readers of `sb._inn["striker"]` / `["non"]`**:
storyteller, analyst, colour commentary, and persisted DETAIL
telemetry. After this change, those consumers will get whatever
the *previous* legitimate striker write set (typically
broadcast-indicator path at `test_pipeline.py:9106-9119` or
`apply_scorer_decision`). Those paths already have admission
gates (`[STRIKER-ADMIT]`) and SM mirroring, so the value will be
*more* stable, not less.

**`_batter_slot_last_identity` bookkeeping**: only used to
trigger `_reset_batter_consensus_for`. Removing the DIRECT-path
trigger means consensus tracking won't churn on every asterisk
flap. The legitimate consensus-reset path
(`apply_scorer_decision`'s LLM striker flag) is preserved.

**Extractor's striker bool**: still flows into the broadcast-
indicator computation at `test_pipeline.py:9077-9119` (gated
behind `_pending_bcast_striker_key`, with row-rejection guard
and `[STRIKER-ADMIT]`). That path is the intended consumer.

No production-code changes are part of this memo — the
recommendation is the patch, applied separately.

## Linked issues

- **U3** (striker tag wrong on UI): downstream symptom — commentary
  subsystems read `sb._inn` directly per Fix 5 comment, see
  flapped value. Resolves once the source flap is removed.
- **N4** (BATTER-CONSENSUS-RESET firing 94 times): direct symptom
  of `_batter_slot_last_identity` churn at
  `scoreboard.py:1922-1927`. Resolves once DIRECT path stops
  passing `striker=`.
- **S27** (legacy non-SM striker writer removal): this DIRECT
  path is the third writer that should have been included in
  S27. Same rationale (SM is sole authority post-cutover) applies.

## Files referenced

- `files/test_pipeline.py:658-686` — `_StrikerLoggingDict`
- `files/test_pipeline.py:9033-9070` — DIRECT batter update path
- `files/test_pipeline.py:9132-9144` — S27 removal comment
- `files/test_pipeline.py:9174-9179` — BATTER REPLACEMENT path
- `files/test_pipeline.py:4225-4228` — `apply_scorer_decision`
  (LLM striker, preserve)
- `files/eyes/scoreboard.py:1883-2404` — `update_batter` with
  Fix 5 backstop branches and `_batter_slot_last_identity` reset
- `files/score_manager.py:99,974,2487-2488,2630-2631,2799-2829`
  — SM `broadcast_striker` ingest (the modern authority)
