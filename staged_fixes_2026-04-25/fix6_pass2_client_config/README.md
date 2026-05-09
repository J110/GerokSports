# Fix 6 — Pass-2 enrichment client timeout/retry config

**Bug**: P1 — every Pass-2 verify call (`groq/compound`, web-search-grounded)
hit a deterministic 271 s ±1 s timeout in production and delivered zero
retro-patched styles to the live pipeline.
**Backlog ref**: `files/docs/backlog.md` "P1: Pass-2 enrichment retry/timeout
policy".
**Trace**: 3/3 sessions on 2026-04-25 timed out at the same wall:
- `pipeline-2026-04-25-153247-dc-pbks-v5`     → 271 s
- `pipeline-2026-04-25-183644-dc-pbks-v5-restart` → 271 s
- `pipeline-2026-04-25-195304-rr-srh-v5-archival` → 272 s

Every call ended with the same upstream message (`Request timed out.`).
The graceful-degradation path (Pass-1 cached as fallback) worked, but
Pass-2 itself was effectively dead code: it ran, failed at ~271 s, and
the retro-patch callback never fired in any production session.

## Root cause

Composition of two configuration choices, not a single value:

| component               | source                                              | value |
|-------------------------|-----------------------------------------------------|-------|
| per-attempt `timeout=`  | `files/eyes/player_enrichment.py:218` (explicit)    | 90 s  |
| `max_retries`           | Groq SDK 1.1.2 `AsyncGroq.__init__` default — never overridden in `_make_client()` | 2 (= 3 attempts) |
| inter-retry backoff     | SDK exponential w/ jitter, ~0.5 s starting          | ~1 s total |

`3 × 90 s + ~1 s ≈ 271 s`. Deterministic, not network jitter.

The 90 s per-attempt value was set explicitly; the `max_retries=2`
multiplier was inherited silently from the SDK default. The
`groq/compound` model with web-search fan-out has been running slower
than the source comment ("10–30 s") on current Groq prod load, so
every attempt exceeded 90 s and the SDK burned the full 3-attempt
budget before surfacing the timeout.

## Files modified

| file                              | lines added | net  |
|-----------------------------------|-------------|------|
| `files/eyes/player_enrichment.py` | +9 (3 lines new client config + 6 lines comment context, –4 lines old) | +5 |
| `files/test_recent_fixes.py`      | +43 (new test + TESTS wiring + section header) | +43 |

## Source change (`player_enrichment.py:_make_client`)

```python
def _make_client():
    try:
        from groq import AsyncGroq
        # Pass-2 calls groq/compound with web-search fan-out.  Production
        # data (3/3 sessions on 2026-04-25) showed every call exceeding
        # 90 s, and SDK default max_retries=2 turned that into a
        # deterministic 271 s budget burn (3 attempts × 90 s) with zero
        # successes.  Single-shot 240 s is shorter wall-clock than the
        # old 3-attempt budget AND actually fits compound's prod latency.
        # max_retries=0 disables SDK auto-retry: Pass-2 runs background-
        # async with graceful Pass-1 fallback, so a second SDK attempt
        # only triples wall-clock cost without changing failure semantics.
        # See backlog "P1: Pass-2 enrichment retry/timeout policy".
        return AsyncGroq(api_key=GROQ_API_KEY, timeout=240.0, max_retries=0)
    except Exception as e:  # noqa: BLE001
        log.error(f"Groq SDK init failed: {e}")
        return None
```

Two-line semantic change: `timeout=90.0` → `timeout=240.0`, plus an
explicit `max_retries=0` argument that was previously inherited as `2`.

## Why this shape

- **240 s single-attempt > 271 s 3-attempt budget.** Net wall-clock is
  shorter on the failure path AND the call can actually succeed,
  instead of three serial timeouts that all fail.
- **`max_retries=0` removes the silent SDK retry that burned the
  budget.** Pass-2 is background-async with Pass-1 fallback already
  cached, so a second SDK attempt only triples wall-clock cost without
  changing failure semantics — there's no user-visible benefit to
  auto-retry on this path.
- **No new dependency.** No `tenacity`, no new code paths, no outer
  `asyncio.wait_for` wrapper. Just two keyword args on the constructor.

## Rejected alternatives (with reasoning)

| path | proposal | why rejected |
|------|----------|--------------|
| (a-bump) | raise `timeout` only, keep `max_retries=2` | wastes 480 s on retries when the failure mode is timeout, not 5xx — retry of a known-slow path is just three serial timeouts |
| (b-tenacity) | add explicit tenacity retry (60 → 90 → 120 s, budget 270 s) | duplicates the SDK's already-present retry; net effect identical to today's broken state; adds a dependency for no win |
| (c-non-grounded-fallback) | on timeout, fall back to plain Llama (no web search) as `verified_via=heuristic` | useful but separate item — today's fix should restore the grounded path first; non-grounded fallback becomes a defence-in-depth follow-up. Filed as P2. |

## Tests added (`test_recent_fixes.py`)

1. `test_pass2_client_timeout_config_explicit` — instantiate
   `_make_client()` and assert the returned `AsyncGroq` exposes
   `timeout == 240.0` and `max_retries == 0`. Pure config-shape check;
   uses the public `client.timeout` / `client.max_retries` attrs
   exposed by Groq SDK 1.1.2. Catches accidental revert and silent
   regressions if the SDK is upgraded and `max_retries` defaults
   change. Runs in <1 ms (no network call — only constructor
   inspection).

The two existing Pass-2 wrapper tests cover the behavioural paths and
do not need extension because they mock `_make_client`:

- `test_enrich_squad_styles_pass2_async_invokes_callback` (existing,
  pre-Fix 6) — happy path: callback fires, `raw_data` retro-patched,
  cache written.
- `test_enrich_squad_styles_pass2_async_failure_caches_pass1`
  (existing, pre-Fix 6) — failure path (simulated `RuntimeError`):
  callback NOT fired, Pass-1 cached as fallback, no rollback. The
  `RuntimeError("simulated Pass-2 timeout")` mock at
  `test_recent_fixes.py:1265` already simulates the same surface as
  `groq.APITimeoutError` from the application's perspective.

## Test results

```
PASS 207 / FAIL 2 (both pre-existing, unrelated to Fix 6)
```

Fix-6 test PASS (3 sub-checks). The 207-test baseline is unchanged
from the post-Fix-5 state; the 2 pre-existing failures
(`test_this_over_late_boundary_ball_appends_to_held` and the source-
text check for the old `>= 18.0` over cap) are documented in
`files/docs/backlog.md` "Test hygiene (P3)" and have been carried
through every recent fix landing.

## Bundling note

This is fix #6 in the inter-match commit bundle. **Zero file overlap**
with the other five fixes — `player_enrichment.py` is not touched by
fixes 1–5. Different code path, different telemetry, different
priority class.

## Verification on first restart after deploy

Pass-2 is async / background — its log line lands ~30–120 s after
"Pass-1 (infer) complete in …", not synchronously with cold-start.
Search the post-restart pipeline log for:

```
[ENRICH] Pass-2 (verify) complete in <N>ms
[STYLES-PATCH] Updated <N> card slots from background Pass-2 enrichment
```

Expected `N` for the Pass-2 latency: **30 000–120 000 ms** (30–120 s)
on the happy path. If `N` is consistently >200 000 ms (i.e. close to
240 s ceiling) across three sessions, escalate to a 360 s timeout and
re-evaluate. If `[STYLES-PATCH]` fails to fire at all (i.e.
`[ENRICH] Pass-2 (verify) LLM call failed: ...` instead), the fallback
is still working but the grounded path is broken at the model — file
the c-non-grounded-fallback follow-up immediately.

This is **positive-firing validation** — different from Fixes 1, 4, 5
whose presence is most visibly confirmed by absence of the bad log
class. Fix 6 is confirmed by presence of the success log class.

## Telemetry to capture on first three deploys

- median + p95 of `Pass-2 (verify) complete in Nms` across all
  successful runs (target: median <60 s, p95 <180 s)
- timeout rate (count of `LLM call failed: APITimeoutError` ÷ total
  Pass-2 invocations) — target <20 %
- if timeout rate exceeds 20 % after a full match-day, escalate to
  path (c) (non-grounded fallback as `verified_via=heuristic`)

## Residual / known limits

- **The fix does not change Pass-2's epistemic guarantees.** When
  groq/compound succeeds, the styles are still web-search-grounded.
  When it fails, the fallback (Pass-1 inferred styles) is still cached
  with no `verified_via` label upgrade. We have not added a
  non-grounded LLM second attempt.
- **The 240 s ceiling is empirically chosen, not measured.** No
  production data exists yet for groq/compound's actual p95 under
  current load — only that 90 s isn't enough. If 240 s also isn't
  enough, the failure mode degrades gracefully (Pass-1 cached) and we
  bump to 360 s in a follow-up.
- **`max_retries=0` removes auto-retry on transient 5xx errors** as
  well as on timeouts. The trade is intentional given Pass-2's
  background-async + graceful-fallback shape, but if Groq starts
  returning frequent transient 5xx (rate-limit windows, cluster
  failovers), we may want a tighter outer retry — file a follow-up
  if it surfaces.
- **The test does not exercise a real Groq call.** It asserts
  config shape only. The behavioural happy/failure paths are covered
  by the two pre-existing wrapper tests with mocked clients. Real
  Groq latency is verified on first-restart telemetry, not in CI.
