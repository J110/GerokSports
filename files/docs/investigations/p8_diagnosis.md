# P8 anomaly diagnosis — `this_over` score-leak + unbounded growth

**Trace:** `logs/trace/866ce150.jsonl` — WI vs RSA 2026-05-02 YouTube test
**Match report:** `files/docs/match_reports/2026-05-02_youtube_test.md`
**Anomaly:** P8 — `this_over` ball-count drift; first token contains the multi-digit string `"100"` at F157–F178; ribbon grows to 12 `"?"` entries at F181–F198.

---

## §1 Symptom summary

The on-screen "This Over" ribbon broadcasts `["100", ".", ".", ".", ".", "."]` from F157 through F178 with team_overs="1.0" / score=4 (the literal string `"100"` is not a valid ball outcome — the alphabet is `.`, `0..7`, `W`, `Wd`, `Nb`, `{N}b`, `{N}lb`). After a poisoned frame at F181 the ribbon expands to twelve `"?"` placeholders for an over that should hold 0–9 tokens.

## §2 Trace evidence cited

`jq` of frames 155–185 (`logs/trace/866ce150.jsonl`):

| Frame | overs | proposed score | `ui_after.this_over` | Notes |
|-------|-------|----------------|----------------------|-------|
| 155   | 0.5   | 3              | `["?",".","1",".","1"]` | 5 tokens, mid-over |
| 156   | 0.5 (no extractor read) | — | `["?",".","1",".","1"]` | scout strip shows `THIS OVER:  FULL SCORECARD:` (empty between) |
| 157   | 1.0   | 4              | `["?",".","1",".","1","1"]` | over rollover, 6th ball appended |
| **158** | **1.0** | **4**       | **`["100",".",".",".",".","."]`** | wholesale flip — first token is multi-digit |
| 178   | 1.0   | 11 (proposed) | `["100",".",".",".",".","."]` | last frame holding the poisoned ribbon |
| 179   | 2.4   | 11             | `["?","?","?","?"]` | length-floor pad (4 placeholders for X.4) |
| **181** | **4.0** | **11**     | **`["?","?","?","?","?","?","?","?","?","?","?","?"]`** | jumped to 12 placeholders — the P8 12-entry case |
| 182–198 | 4.0 | reset 11→11 (P7) | same 12-`?` ribbon | persists through poisoned/graphic frames |

Raw frame-158 diff (extractor itself never returned anything resembling `"100"`; `extractor.score=4`, `extractor.match_overs=1`):

```json
{"path":"this_over",
 "from":["?",".","1",".","1","1"],
 "to":["100",".",".",".",".","."]}
```

## §3 Root cause location

**Two cooperating bugs.**

### 3a) Token regex accepts unbounded `\d+` — `files/test_pipeline.py:1390-1392`

```1390:1392:files/test_pipeline.py
_THIS_OVER_TOKEN_RE = re.compile(
    r'\b(\d+lb|\d+b|lb|wd|wide|nb|noball|no[_ ]ball|\d+|W|\.)\b',
    re.IGNORECASE)
```

The `\d+` alternative has **no length bound**. Any contiguous digit run in the matched span — score `100`, partnership `100`, target `100`, run-rate `10.0` partial reads — is captured as a single token. Used by:

- `_parse_this_over_from_scout` (`files/test_pipeline.py:1395-1407`): runs `_THIS_OVER_TOKEN_RE.findall(...)` on whatever the outer `_THIS_OVER_RE` captures **and**, in the line-based fallback (L1399-1404), on the **entire line** that contains the substring "this over" — pulling in every digit on the line (score, wickets, overs, batter stats).

### 3b) Cold-start "THIS OVER" backfill — `files/test_pipeline.py:9318-9326`

```9318:9326:files/test_pipeline.py
_to_match = re.search(
    r"THIS\s+OVER[\s:]*([0-9wWnNbBdD\.\,\s]+?)"
    r"(?:\s{2,}|$|FULL\s+SCORECARD|INFO_PANEL|"
    r"SPEED|TO\s+WIN|RECENT)",
    description.upper())
if _to_match:
    _raw = _to_match.group(1).strip()
    _tokens = re.findall(
        r"\d+|W|WD|NB|\.", _raw.replace(",", " "))
```

Same unbounded `\d+` here. This path feeds `over_mgr.on_broadcast_override` whose `_is_legal_run_token` gate **does** reject `"100"` wholesale (`files/eyes/this_over.py:803-817`), so this regex is contained on the over_mgr arm but is the same defect, and **is** the source of the LLM-fed strip when the extractor is the one that produced `this_over_broadcast`.

### 3c) ScoreManager backfill bypasses alphabet validation — `files/score_manager.py:2236-2241`

```2236:2241:files/score_manager.py
if card.get("broadcast_this_over"):
    for i, token in enumerate(card["broadcast_this_over"]):
        if (i < len(self.this_over)
                and i < len(self.this_over_src)
                and self.this_over_src[i] == "bcast"):
            self.this_over[i] = token
```

Unlike `ThisOverManager.on_broadcast_override`, this writer **does not** call `_is_legal_run_token` (or any token sanitisation). Whatever string the regex produced is written verbatim into `score_mgr.this_over[i]` (and then promoted to `score_mgr.completed_over` at over rollover via `files/score_manager.py:2847`).

### 3d) WS payload falls back to poisoned `score_mgr.completed_over` — `files/test_pipeline.py:4498-4507`

```4498:4507:files/test_pipeline.py
"this_over": (
    list(over_mgr.get_display(
        scoreboard._inn.get("overs")
        if scoreboard._inn else None))
    if (over_mgr.get_display(
        scoreboard._inn.get("overs")
        if scoreboard._inn else None))
    else (list(score_mgr.completed_over)
          if score_mgr and score_mgr.completed_over
          else [])),
```

When `over_mgr.get_display()` returns `[]` (the moment after `_consume_pending_clear`), the WS payload falls through to `score_mgr.completed_over`. If SM's mirror was poisoned in step 3c, the `"100"` token reaches the UI/trace from this fallback even though `over_mgr.this_over` was never mutated.

### 3e) Twelve-`"?"` growth — get_display length-floor + multi-over jump rejection

`ThisOverManager.check_over_change` correctly **rejects** the F179→F181 over jump (2.4 → 4.0 is implausible for one frame, files/eyes/this_over.py:937-943, returns `False`), so `_last_over_int` stays at 1 while team_overs reads "4.0". On a subsequent frame where overs reads e.g. "4.6" (or any X.6 inside the rejected window), `get_display` runs the length-floor pad:

```1199:1212:files/eyes/this_over.py
if legal_n < sub:
    missing = sub - legal_n
    for _ in range(missing):
        self.this_over.append("?")
        self.this_over_sources.append("bcast")
```

`missing = sub - legal_n` is **not capped** by `MAX_OBSERVED_THIS_OVER_LEN`. With `sub` reading 6 (e.g. team_overs="X.6") and an existing 4–6 `"?"` from previous frames, the pad pushes `len(this_over)` past 12. Subsequent frames at "4.0" return the bloated list as-is (the `sub == 0` short-circuit at L1192-1193 returns whatever's there). `MAX_OBSERVED_THIS_OVER_LEN = 12` (L59) is enforced **only** in `on_ball_event`/`_append_to_held_and_rearchive`, **not** in `get_display`.

## §4 Root cause mechanism

1. The broadcast strip's `THIS OVER:` slot is misread (or the LLM hallucinates a value) such that the captured substring contains a multi-digit number — the prompt at `files/eyes/agent.py:220-224` tells the LLM to emit tokens like `["4", ".", "1", ...]` but provides no length validation, and the regex sister-path at `_THIS_OVER_TOKEN_RE` greedily takes any `\d+` run.
2. `extract_broadcast_data` stores the contaminated list in `_bcast["this_over_broadcast"]` (`files/test_pipeline.py:1514-1516`).
3. The list is plumbed into the `FrameInput` SM feeder as `broadcast_this_over` (`files/test_pipeline.py:10145`).
4. `ScoreManager._update_supplements` writes the contaminated tokens into its own `self.this_over` mirror **without** alphabet validation.
5. At the next over boundary inside `_apply_event`, `self.completed_over = list(self.this_over)` snapshots the poisoned ribbon (`files/score_manager.py:2847`).
6. The WS payload-builder at `files/test_pipeline.py:4498` falls back to `score_mgr.completed_over` whenever `over_mgr.get_display(...)` is empty (which happens for one frame after `_consume_pending_clear`). The `"100"` token reaches the UI mirror and the trace's `ui_after.this_over`.
7. Independently, the multi-over jump 2.4 → 4.0 is rejected by `check_over_change`; the rejection leaves `_last_over_int` stuck while team_overs continues climbing, so subsequent `get_display(...)` calls invoke the unbounded length-floor pad and grow the ribbon to 12 `"?"`.

`over_mgr.on_broadcast_override` itself is **not** the leak channel — its `_is_legal_run_token` gate (`files/eyes/this_over.py:573-582`) correctly rejects the multi-digit list wholesale. The `"100"` reaches the UI through SM's parallel, unvalidated mirror.

## §5 Proposed fix scope (no code in this memo)

Three small, surgical changes — total ~25 LOC plus tests:

1. **Tighten `_THIS_OVER_TOKEN_RE`** (`files/test_pipeline.py:1390-1392`) — restrict the digit alternative to `[0-7]` (cricket scorecard alphabet, single digit per ball-token). Mirror the same restriction in the cold-start regex at `files/test_pipeline.py:9325-9326`. ~4 LOC.
2. **Reject the line-based fallback when no `THIS OVER:` substring is followed by token-shaped content** (`files/test_pipeline.py:1399-1404`) — instead of running `findall` on the whole line, restrict the search to the trailing slice after the keyword and bound the slice to ≤30 characters or a hard separator (`|`, `EXTRA:`, `FULL`, `SPEED:`). ~8 LOC.
3. **Reuse `ThisOverManager._is_legal_run_token` inside SM's backfill** (`files/score_manager.py:2236-2241`) — guard each token with the existing alphabet predicate before assignment; on any illegal token, drop the entire `broadcast_this_over` for the frame and emit a `[THIS-OVER-BCAST-REJECT]` decision tag for the trace. ~10 LOC.
4. **Bound the length-floor pad** (`files/eyes/this_over.py:1199-1208`) — clamp `missing` so `len(self.this_over) + missing ≤ MAX_OBSERVED_THIS_OVER_LEN`. ~3 LOC. Prevents the 12-`"?"` runaway.

## §6 Test plan for the fix

- **Unit (`files/test_recent_fixes.py`):**
  - `test_this_over_regex_rejects_multi_digit` — feed `"THIS OVER: 100 . . . . ."` and `"THIS OVER: 4 . 1 6 wd 4"`; assert the multi-digit case is rejected (returns `None` or empty), the cricket-alphabet case is accepted unchanged.
  - `test_score_mgr_backfill_validates_alphabet` — call `_update_supplements` with `broadcast_this_over=["100", ".", ".", ".", ".", "."]`; assert `score_mgr.this_over` is unchanged and the rejection decision is recorded.
  - `test_get_display_floor_pad_bounded_by_max_obs_len` — seed `over_mgr.this_over` with 6 `"?"`, call `get_display("X.9")`; assert resulting length ≤ 12.
- **Replay regression:** rerun `python files/analyze_trace.py logs/trace/866ce150.jsonl --report files/docs/match_reports/2026-05-02_youtube_test_post_fix.md` after the fix; expected delta — zero P8 anomalies for F157-F198, P3/P7/P9 unaffected.
- **Anomaly rule coverage:** add a new fixture in `files/tests/test_anomaly_rules.py` that injects `this_over=["100", ".", ".", ".", ".", "."]` directly and confirms the analyzer still flags P8 (the rule itself is correct — the bug is upstream of it).

## §7 Risk: other consumers of `this_over`

The poisoned token reaches several downstream surfaces. Flag for re-validation post-fix:

- **`Scoreboard.update_this_over`** (`files/eyes/scoreboard.py:4002-4027`) — currently dead on the live path (only `test_offline.py:197` calls it per `files/docs/investigations/dual_broadcaster_path_c_audit.md` §2.A); no live risk but the same multi-digit weakness exists, would surface if the dead path is revived.
- **`ScoreManager.completed_over_runs`** — `sum(int(t) for t in self.this_over if t.isdigit())` (`files/score_manager.py:2849`) silently treats `"100"` as a 100-run ball, polluting the per-over runs total used by the UI's "Recent Overs" panel.
- **`commentary/context_builder.py`** consumes `this_over` for line generation (per top-of-file grep). A `"100"` token would propagate into a Wire/commentary line as a literal "100 run" delivery — cosmetic but visible.
- **`build_delivery_dataset.py`** ingests `this_over` for offline ML training data (per grep). One contaminated session could pollute the dataset; verify the loader rejects out-of-alphabet tokens.
- **`anomaly_rules.py` P8** itself is correct — it computed `delta=12` and `delta=6` correctly from the corrupted state. No rule change needed.

## Stop-condition status

- **S1 — multiple sites:** yes; fixes 1, 2, 3, 4 above.
- **S2 — shared upstream code:** the regex and the SM backfill are both upstream of two consumers each (over_mgr ribbon and SM mirror). Documented in §3-§5.
- **S3 — UI payload corruption:** ruled out — the trace records `over_mgr.get_display()` and the SM fallback as the only writers of `this_over` in the WS payload (`files/test_pipeline.py:4498-4507`); no UI/client code mutates this list.
