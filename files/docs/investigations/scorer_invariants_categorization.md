# SCORER invariants categorization (Item 2 design doc)

**Date:** 2026-04-29
**Scope:** Design document only. **No code changes.** Categorizes every
invariant currently enforced inside `apply_scorer_decision`
(`files/test_pipeline.py` ~L2679+) plus the upstream
SCORER-side filters `_scorer_batter_update_allowed` (~L2321) and
`_scorer_batter_row_is_dismissed_resurrection` (~L2335). Output
specifies which invariants belong in a Pydantic schema, which must
remain runtime filters, which should be added to the SCORER LLM
prompt, and which are already enforced elsewhere.

The Item 2 backlog entry is **P0: SCORER doesn't enforce active-batter
invariants** (`files/docs/backlog.md` L5745-5793). The structural
refactor goal is **defense-in-depth**: introduce a Pydantic-typed
SCORER decision contract on top of the existing filters, *not*
replacement.

---

## 0. Constraints (locked by user prompt)

- **Existing filters MUST remain.** Schema layer is additive.
- **SCORER LLM prompt is a separate workstream.** Recommend
  language; do not modify `SCORER_PROMPT` in `files/eyes/match_state.py`
  in this task.
- **No deployed code changes** in this task.
- **Pydantic is not currently a dependency** (`files/eyes/requirements.txt`
  lists `ollama`, `ultralytics`, `aiohttp`, `opencv-python-headless`,
  `numpy`, `pyobjc-framework-Quartz`). Adding Pydantic v2 is part of
  Item 2 implementation cost (one new dep; ~3-5 MB; pure Python +
  Rust extension already pulled by FastAPI ecosystem; decision lives
  in implementation PR).

---

## 1. Inventory: every invariant inside `apply_scorer_decision`

The following table enumerates every guard / gate / filter executed
when SCORER output enters the pipeline. Line numbers are from
`files/test_pipeline.py` as of 2026-04-29 (Item 3 shipped). Tags in
brackets are the existing telemetry strings emitted on fire. The
**Class** column is the categorization decided in §2.

| # | Guard / invariant | Lines | Tag emitted on reject | Class |
|---|------|------:|------|---|
| 1 | GRAPHIC frame strip (drop `batter_updates`, `bowler_update`, `bowlers`, `score_update`, `extras_update` when `frame_type == "GRAPHIC"`) | 2693-2696 | (silent strip) | **STATE-DEPENDENT** |
| 2 | Innings-change requires score *not* to increase (else flip `innings_change=False`) | 2698-2710 | `[GUARD] Innings change rejected — score increased` | **STATE-DEPENDENT** |
| 3 | Empty `batting_team` short-circuit | 2712-2714 | "No batting team set — skipping" | **STATE-DEPENDENT** |
| 4 | "No players from our match recognized" gate (require accepted batter / bowler / bowlers / ground_truth) | 2716-2734 | "No players from our match recognized" | **STATE-DEPENDENT** |
| 5 | Empty-extractor block: any `accepted=true` field with extractor flat (no `score`/`overs`/`wickets`/`batters`) | 2736-2740, 2763-2766, 2911-2913, 2920-2922 | `[GUARD] … — extractor empty, blocking` | **STATE-DEPENDENT** |
| 6 | Score correction guard: `\|proposed-current\| > 7` blocks all updates | 2742-2761 | `[GUARD] Score correction in Scorer output: …` | **PROMPT-EXPRESSIBLE** + STATE-DEPENDENT |
| 7 | **SCORE-INF-FLOOR** (Layer 1.5 floor — Fix 11 sibling): proposed_score ≥ bat_sum + extras_total | 2776-2799 | `[SCORE-INF-GATE] … min_score_from_batters_and_extras` | **STATE-DEPENDENT** |
| 8 | **SCORE-INF-GATE phantom advance** (Fix 15 / F52-F53 class): score advance ≤ bat_delta + extras_max(6 / 12 if wkt) | 2801-2896 | `[SCORE-INF-GATE] score X→Y (advance=...) > explained` | **STATE-DEPENDENT** |
| 9 | Wickets-update applies via `scoreboard.set("wickets", …)` (no separate physics check here; SB owns it) | 2918-2926 | none in scope | **ALREADY-ENFORCED** (`Scoreboard.set`) |
| 10 | **WICKET-AUTO** auto-dismiss the canonical striker on wickets +1 with no explicit `dismissal` | 2940-2969 | `[WICKET-AUTO] Dismissed striker …` | **STATE-DEPENDENT** |
| 11 | Dismissal proposed without wickets-increment ⇒ block | 2971-2980 | `[GUARD] Scorer proposed dismissal but wickets unchanged` | **STATE-DEPENDENT** |
| 12 | **EXTRAS-INF-GATE** (Fix 11 / cricket-physics): proposed bat_sum ≤ score (when wkts/dismissed counts coherent) | 3018-3164 | `[EXTRAS-INF-GATE] wkts=N: proposed bat_sum=… > score=…` | **STATE-DEPENDENT** |
| 13 | **BALLS-CEILING-GATE** (Fix 14): per-batter `balls` ≤ `overs * 6 + ball_of_over + 2` | 3179-3244 | `[BALLS-CEILING-GATE] overs=… (legal_balls=…)` | **STATE-DEPENDENT** + PROMPT-EXPRESSIBLE |
| 14 | INIT path skip activation when extractor row has both `runs=None` AND `balls=None` | 3261-3272 | `[INIT] Skipping activation … extractor returned null` | **SCHEMA-ENFORCEABLE** (row-level) |
| 15 | INIT path: `_scorer_batter_row_is_dismissed_resurrection` filter | 3273-3275 | `[SCORER-INVARIANT-FILTER]` / `[SCORER-DISMISSED-RESURRECT]` | **STATE-DEPENDENT** ★ Item 2 cluster |
| 16 | INIT path: `_scorer_batter_update_allowed` (witnessed-out gate) | 3276-3277 | `[SCORER-ACTIVE-GATE]` | **STATE-DEPENDENT** ★ Item 2 cluster |
| 17 | Short-name expansion (`len(name.strip()) <= 2` ⇒ match `extractor_batter_names` prefix) | 3287-3292 | (silent rewrite) | **PROMPT-EXPRESSIBLE** |
| 18 | Batter not in extractor output ⇒ reject (only when extractor names exist) | 3293-3300 | `[GUARD] Batter '…' not in extractor output — scorer inferred, rejecting` | **STATE-DEPENDENT** |
| 19 | Loop path: `_scorer_batter_row_is_dismissed_resurrection` | 3301-3303 | `[SCORER-INVARIANT-FILTER]` / `[SCORER-DISMISSED-RESURRECT]` | **STATE-DEPENDENT** ★ Item 2 cluster |
| 20 | Loop path: `_scorer_batter_update_allowed` | 3304-3305 | `[SCORER-ACTIVE-GATE]` | **STATE-DEPENDENT** ★ Item 2 cluster |
| 21 | TRUST HIERARCHY: prefer extractor numbers over scorer numbers | 3310-3336 | `[FLOW] X: extractor … vs scorer … — USING EXTRACTOR` | **STATE-DEPENDENT** (composition rule) |
| 22 | `bowler_update` placeholder name reject (`_is_placeholder`) | 3346-3357 | (silent skip) | **SCHEMA-ENFORCEABLE** (placeholder regex) |
| 23 | Bowlers-array placeholder reject | 3384-3394 | (silent skip) | **SCHEMA-ENFORCEABLE** |
| 24 | Score-changed-without-batter warning | 3396-3400 | `[WARN] Score changed but no batter update` | n/a (advisory log only) |

In addition, the following invariants are enforced by **callers /
downstream** rather than `apply_scorer_decision` itself, but are
recorded here because they belong to the same "what does the SCORER
contract promise" question:

| Caller-side check | Where | Class |
|------------------|-------|-------|
| `update_batter` un-dismiss prevention via `_is_witnessed_dismissal` | `eyes/scoreboard.py` ~L1730-1734 | **STATE-DEPENDENT** (defense-in-depth duplicate of #16/20) |
| `update_batter` max-2-active enforcement (yet_to_bat path) | `eyes/scoreboard.py` ~L1770-1812 | **STATE-DEPENDENT** (last line of defense for resurrection class) |
| `validate_state_consistency` post-hoc resurrection demote | `eyes/scoreboard.py` (called from FOW upgrade) | **STATE-DEPENDENT** |
| WS-payload active-batter filter (P0-3 / P1-4 audit, 2026-04-22) | `test_pipeline.py` build_full_payload SM-authority override | **STATE-DEPENDENT** |
| `[BATTERS-INVARIANT]` (proposed in backlog P0; not yet implemented) | not yet present | **STATE-DEPENDENT** (would replace none of above; adds post-merge sanity) |

---

## 2. Categorization legend

| Class | Definition | Enforcement layer |
|---|---|---|
| **SCHEMA-ENFORCEABLE** | Expressible as a Pydantic v2 model field constraint or JSON-schema rule using only the data inside the SCORER decision payload (no scoreboard state required). Violations are raised at parse time. | Pydantic model in `files/eyes/match_state.py` |
| **STATE-DEPENDENT** | Requires runtime state (current `batting_card`, `fall_of_wickets`, witnessed-dismissal set, current `striker`/`non_striker`, current `score`/`wickets`/`overs`, extractor names, etc.). Cannot be schema-enforced because a syntactically valid decision can still violate cricket physics relative to current state. | Existing runtime filters in `apply_scorer_decision` (kept verbatim). |
| **PROMPT-EXPRESSIBLE** | Behavior the SCORER LLM should be guided to *not produce* via prompt language. Filter must remain (LLM compliance is probabilistic) but prompt guidance reduces fire rate. | Recommend language for `SCORER_PROMPT` in `files/eyes/match_state.py`; do **not** modify in this task. |
| **ALREADY-ENFORCED** | A separate structural check downstream covers the invariant; no additional layer required. | Downstream, e.g. `Scoreboard.set` consensus / `Scoreboard.update_batter`. |

A single invariant may carry **multiple labels** (e.g. score-correction
guard #6 is both PROMPT-EXPRESSIBLE and STATE-DEPENDENT — the prompt
can be told "never propose a score change > 7", but the filter must
still verify against current SB state because LLM compliance is not
guaranteed).

---

## 3. Per-invariant categorization table

Re-grouped from §1, primary class first, with rationale.

### 3.1 SCHEMA-ENFORCEABLE (parse-time rejections)

| # | Invariant | Pydantic constraint | Reject scope |
|---|-----------|--------------------|--------------|
| 14 | Activation row with both `runs=None` and `balls=None` | `BatterUpdate.runs: int | None` + `BatterUpdate.balls: int | None`; **model_validator** asserts `runs is not None or balls is not None` when `accepted=True` and the row carries no other supporting field | **Per-row reject** (drop the offending entry from `batter_updates`; keep siblings) |
| 22 | `bowler_update.name` is a placeholder (`?`, `—`, empty, `tbd`, etc.) | `BowlerUpdate.name: constr(strip_whitespace=True, min_length=1, pattern=r"^(?!(\?|—|tbd|TBD)$).+$")` (full pattern derived from `_is_placeholder`) | **Per-row reject** |
| 23 | `bowlers[*].name` placeholder | Same constraint applied to `Bowler.name` element | **Per-row reject** within array |
| Aux | Numeric ranges (`runs ≥ 0`, `balls ≥ 0`, `wickets in 0..10`, `overs in 0..20`, `extras.* ≥ 0`) | `Field(ge=0)`, `Field(ge=0, le=10)`, `Field(ge=0, le=20.0)` | **Per-field reject** |
| Aux | `score_update.to`, `overs_update.to`, `wickets_update.to` typed coercion (`"154-3"` style strings handled by validator) | Custom `field_validator` mirrors `_sr_int(...split("-")[0])` from L2368 | **Per-field reject** |
| Aux | `dismissal` shape: `str | dict | list[str|dict] | None`; if dict, keys must be subset of `{batter, name, how, bowler, fielder}` | Discriminated union | **Per-row reject** |
| Aux | `team_assignment.batting_team` and `bowling_team` MUST be `null` (prompt requirement L195-197) | `Literal[None]` | **Whole field reject** (set to None; do not fail decision) |
| Aux | `innings_change: bool` (currently used as bool, but model accepts truthy) | `bool` strict mode | **Per-field reject** |
| Aux | `team_assignment.innings: Literal[1, 2, None]` | `Literal[1, 2] | None` | **Per-field reject** |

**No SCHEMA-ENFORCEABLE rule operates on cricket physics or
witnessed-dismissal state.** All physics gates are STATE-DEPENDENT
(§3.2) by construction.

### 3.2 STATE-DEPENDENT (runtime filters — keep verbatim)

These are the invariants that the schema layer **cannot replace**.
They require live read of `scoreboard._inn`, `scoreboard.batting_card`,
`scoreboard.fall_of_wickets`, `scoreboard._is_witnessed_dismissal`,
extractor batter set, or canonical striker (via `_canonical_active_slot`).

| # | Invariant | Filter that handles it | Why it cannot be schema-enforced |
|---|-----------|-----------------------|-----------------------------------|
| 1 | GRAPHIC frame strip | `frame_type == "GRAPHIC"` branch (L2693-2696) | `frame_type` is a frame attribute, not a SCORER decision field |
| 2 | Innings-change forbids score increase | L2702-2705 | Compares `score_update.to` vs current `scoreboard._inn["score"]` |
| 3 | Empty batting_team | L2712-2714 | `batting_team` is caller state |
| 4 | "No players recognized" | L2731-2734 | Requires resolved-name set on the caller side |
| 5 | Empty-extractor block | L2736-2740 + per-field | Compares against `extracted.get(...)` |
| 6 | Score-correction \|Δ\| ≤ 7 | L2746-2761 | Compares against current `scoreboard._inn["score"]` |
| 7 | SCORE-INF-FLOOR | L2776-2799 | Reads `bat_sum + extras_total` from current `batting_card` + `extras["total"]` |
| 8 | SCORE-INF-GATE phantom advance | L2814-2896 | Reads current bat-card runs + wickets + extras headroom |
| 10 | WICKET-AUTO striker auto-dismiss | L2940-2969 | Reads canonical striker + striker card status |
| 11 | Dismissal needs wkts++ | L2971-2980 | Compares `extracted.wickets` vs `scoreboard._inn.wickets` |
| 12 | EXTRAS-INF-GATE | L3018-3164 | Reads dismissed-batter runs + active-batter runs vs proposed |
| 13 | BALLS-CEILING-GATE | L3179-3244 | Computes innings-balls ceiling from current `overs` |
| 15 / 19 | DISMISSED-RESURRECT (witnessed FOW vs scorer row) | `_scorer_batter_row_is_dismissed_resurrection` | Reads `fall_of_wickets` + `_is_witnessed_dismissal` |
| 16 / 20 | ACTIVE-GATE (witnessed-out batter receives update) | `_scorer_batter_update_allowed` | Reads `_is_witnessed_dismissal` |
| 17 | Short-name expansion | L3287-3292 | Reads `extractor_batter_names` |
| 18 | Batter not in extractor output | L3293-3300 | Reads `extractor_batter_names` |
| 21 | TRUST HIERARCHY (extractor wins on numbers) | L3310-3336 | Reads `_ext_batter_stats` |

**Coverage gap (Item 2 deliverable in implementation phase):** the
backlog P0 explicitly calls out two unwitnessed invariants:

1. `len(active_batters) <= 2` (max-2-active across the SM merge).
2. `active_batters ∩ dismissed_batters == ∅` (no resurrection across
   the SM merge).

(2) is partially covered by #15/19 + #16/20 *at SCORER decision
boundary*, plus `update_batter` un-dismiss guard at SB boundary. (1)
is partially covered by `update_batter`'s yet-to-bat max-2 path
(L1770-1812). Neither is enforced as a **post-merge invariant** on
SM/SB joint state. Adding `[BATTERS-INVARIANT]` as a post-merge
assertion is part of the implementation phase, not this design doc.
The new assertion is **STATE-DEPENDENT** (reads SM + SB merged
state) and lives in `apply_scorer_decision` *after* the per-row
loops (or in a wrapping helper).

### 3.3 PROMPT-EXPRESSIBLE (recommend prompt language only)

| # | Behavior | Recommended prompt addition (English; do **not** add in this task) | Filter that still fires on non-compliance |
|---|-----------|--------------------------------------------------------------------|------|
| 6 | Don't propose score deltas > 7 in a single frame | `SCORE CORRECTION DISCIPLINE: A single broadcast strip frame may shift the team score by at most +6 (one ball, all extras combined). Never propose a new score that differs from the current score by more than +7 (one ball headroom). If the strip looks like it shows score 200 but our records show 130, that is a stale strip / OCR misread — leave score_update.accepted=false and report the discrepancy in vision_hint.` | #6 (`[GUARD] Score correction`) |
| 13 | Per-batter `balls` ≤ legal balls in innings | `BALLS CEILING: A batter's balls value cannot exceed the legal balls bowled in this innings (overs × 6 + balls-this-over). If you see Powell 14(56) at 6.1 overs, that is a season-aggregate / career stat overlay — reject it (do not include in batter_updates).` | #13 (`[BALLS-CEILING-GATE]`) |
| 17 | Always emit full names, never single letters | `BATTER NAMES: Always emit the resolved squad name, never a single-letter or two-letter abbreviation. If the extractor sent "M", resolve to "Maxwell" (or the matching squad member) before emitting in batter_updates.` | #17 (silent rewrite) |
| 22 / 23 | Never emit placeholder bowler names | `BOWLER NAMES: If you cannot identify the bowler from the extractor output and the squad, emit bowler_update={} (empty) — never emit "?", "—", "TBD", "(unknown)", or any other placeholder.` | #22 / #23 (silent skip) |
| 14 | Don't activate a batter row with both runs=null and balls=null | `BATTER ACTIVATION (numbers required): Only include a batter in batter_updates if at least one of runs/balls is a number you actually read from the strip. A row with runs=null AND balls=null is a guess — leave the batter out and put the name in vision_hint instead.` | #14 (`[INIT] Skipping activation`) |
| (cluster) | NEVER include a known witnessed-out batter in batter_updates or dismissal | The existing prompt already says this (L171-173 `NEVER dismiss a batter who is already marked "out"`), but doesn't cover **batter_updates** — recommend extending: `BATTER UPDATES (witnessed-out): If a batter's status in BATTING CARD is "out", do NOT include them in batter_updates either. The pipeline filters such rows via [SCORER-INVARIANT-FILTER] / [SCORER-DISMISSED-RESURRECT]; reducing fire rate cuts noise and frame-budget.` | #15-16 / #19-20 |

**Important boundary:** all PROMPT-EXPRESSIBLE rules are **also**
STATE-DEPENDENT in their *enforcement*. Prompt guidance reduces
filter fire **rate** (LLM doesn't propose violation as often) but
doesn't move the enforcement layer (filter must still fire when LLM
is non-compliant). Prompt iteration is a **noise-reduction** lever,
never an enforcement lever.

### 3.4 ALREADY-ENFORCED (no new layer)

| # | Behavior | Where covered |
|---|-----------|---------------|
| 9 | Wickets monotonic / consensus | `Scoreboard.set("wickets", …)` consensus tracker (3 frames) plus `[WICKETS-LOW]` / `[WICKETS-HIGH]` consensus paths |
| (Aux) | Score monotonic same-innings | `Scoreboard.set("score", …)` rejects regressions; backlog `(14)` score-regression hard-block landed |
| (Aux) | Bowler over-boundary changes only | `Scoreboard.update_bowler` (`BOWLER-STALE` + bowler-rotation guards); SCORER prompt says "Mid-over name change → reject name" (L175-176) |

---

## 4. Pydantic model spec (proposed)

This section specifies the **shape** of the new `ScorerDecision`
contract. **Not for implementation in this task.** The model lives
in `files/eyes/match_state.py` next to `MatchStateAgent.validate`.
Validation order is documented in §5.

**NOTE:** See §10.7 for architectural deviation — production uses helper
dispatch instead of root model validation.

```python
# files/eyes/match_state.py (proposed; not for this task)
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic import ConfigDict


_PLACEHOLDER_PATTERN = (
    r"^(?!(\?|—|-|tbd|TBD|n/a|N/A|none|None|unknown|UNKNOWN)$).+$"
)


def _coerce_int_strip(value):
    if value is None:
        return None
    s = str(value)
    if "-" in s:
        s = s.split("-", 1)[0]
    try:
        return int(s)
    except (ValueError, TypeError):
        return None


class TeamAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    batting_team: Literal[None] = None
    bowling_team: Literal[None] = None
    innings: Literal[1, 2] | None = None
    target: int | None = Field(default=None, ge=0)


class ScoreUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_: int | None = Field(default=None, alias="from", ge=0)
    to: int | None = Field(default=None, ge=0)
    accepted: bool = False

    @field_validator("from_", "to", mode="before")
    @classmethod
    def _coerce(cls, v):
        return _coerce_int_strip(v)


class OversUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_: float | None = Field(default=None, alias="from", ge=0, le=20)
    to: float | None = Field(default=None, ge=0, le=20)
    accepted: bool = False


class WicketsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_: int | None = Field(default=None, alias="from", ge=0, le=10)
    to: int | None = Field(default=None, ge=0, le=10)
    accepted: bool = False


class BatterUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    runs: int | None = Field(default=None, ge=0)
    balls: int | None = Field(default=None, ge=0)
    fours: int | None = Field(default=None, ge=0)
    sixes: int | None = Field(default=None, ge=0)
    striker: bool | None = None
    accepted: bool = True

    @model_validator(mode="after")
    def _runs_or_balls_when_accepted(self):
        # Per-row reject (filter at parse): an accepted batter update
        # with both runs and balls null is a guess; drop the row.
        # The caller MUST treat this as "skip this entry", not
        # "reject the whole decision".
        if self.accepted and self.runs is None and self.balls is None:
            raise ValueError(
                "BatterUpdate accepted=true requires at least one of "
                "runs/balls to be non-null"
            )
        return self


class BowlerUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = Field(..., min_length=1, pattern=_PLACEHOLDER_PATTERN)
    overs: float | None = Field(default=None, ge=0, le=20)
    runs: int | None = Field(default=None, ge=0)
    wickets: int | None = Field(default=None, ge=0, le=10)
    accepted: bool = True


class Bowler(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = Field(..., min_length=1, pattern=_PLACEHOLDER_PATTERN)
    overs: float | None = Field(default=None, ge=0, le=20)
    runs: int | None = Field(default=None, ge=0)
    wickets: int | None = Field(default=None, ge=0, le=10)


class DismissalDict(BaseModel):
    model_config = ConfigDict(extra="ignore")
    batter: str | None = None
    name: str | None = None
    how: str | None = None
    bowler: str | None = None
    fielder: str | None = None

    @model_validator(mode="after")
    def _has_subject(self):
        if not (self.batter or self.name):
            raise ValueError(
                "Dismissal dict requires batter or name"
            )
        return self


class ScorerDecision(BaseModel):
    """Pydantic-typed SCORER decision contract.

    Schema-level invariants are SCHEMA-ENFORCEABLE rules from §3.1.
    State-dependent invariants (§3.2) and prompt-expressible
    invariants (§3.3) remain enforced by ``apply_scorer_decision``.
    """

    model_config = ConfigDict(extra="ignore")

    team_assignment: TeamAssignment = Field(default_factory=TeamAssignment)
    score_update: ScoreUpdate = Field(default_factory=ScoreUpdate)
    overs_update: OversUpdate = Field(default_factory=OversUpdate)
    wickets_update: WicketsUpdate = Field(default_factory=WicketsUpdate)
    batter_updates: dict[str, BatterUpdate] = Field(default_factory=dict)
    bowler_update: BowlerUpdate | dict[str, BowlerUpdate] = Field(
        default_factory=dict
    )
    bowlers: list[Bowler] = Field(default_factory=list)
    dismissal: str | DismissalDict | list[str | DismissalDict] | None = None
    ball_event: dict | None = None
    ground_truth_applied: dict | None = None
    rejected: dict[str, str] = Field(default_factory=dict)
    deferred: dict[str, str] = Field(default_factory=dict)
    innings_change: bool = False
    vision_hint: str | None = None
    innings_transition_reset: bool | None = None
```

### 4.1 Which fields stay flexible

The following fields **stay loosely typed** (`dict | None`,
`extra="ignore"`) because their internal shape is consumed by code
paths outside `apply_scorer_decision`:

- `ball_event` — consumed by `OverManager` token aggregator; its
  schema isn't fully discovered yet.
- `ground_truth_applied` — used by ground-truth scorecard graphics;
  schema not stable.
- `rejected`, `deferred` — informational dicts; LLM may use any keys.

### 4.2 Per-row vs whole-decision reject

The model layer follows a strict rule:

- **Whole-decision reject:** *never*. A `ScorerDecision` either
  parses (with row-level drops) or returns an empty decision. The
  current pipeline already returns `{}` from `MatchStateAgent.validate`
  on JSON parse failure (`match_state.py` L295-317); the new
  Pydantic layer extends that fallback path.
- **Per-row reject:** dictionary entries (`batter_updates`,
  `bowler_update` when dict-shaped, `bowlers[*]`, `dismissal[*]`)
  that fail their nested validator are **dropped from the parsed
  output** with telemetry `[SCORER-SCHEMA-DROP] field=batter_updates
  key='X' reason='runs_or_balls_required'`. The remaining decision
  is passed through unchanged.
- **Per-field reject:** scalar fields (`score_update.to`,
  `overs_update.to`, `wickets_update.to`) that fail coercion are
  **set to None** with telemetry `[SCORER-SCHEMA-COERCE] field=...
  raw='200-3' coerced=null reason='...'`. Downstream `accepted` flag
  on the same field is **forced to False** so the empty-extractor
  block (#5) and the [GUARD] paths fire correctly.

This keeps the existing post-Pydantic flow ("for `score_update`,
check `accepted` and `to` is not None, then verify against state")
working unchanged.

---

## 5. Validation order (proposed)

```
SCORER LLM → JSON
    │
    ▼
[Step 1: Parse]            json.loads     → MatchStateAgent._parse_json (existing)
    │
    ▼
[Step 2: Schema check]     ScorerDecision.model_validate
    │                         ├─ per-row drops with [SCORER-SCHEMA-DROP]
    │                         └─ per-field coerce/null with [SCORER-SCHEMA-COERCE]
    ▼
[Step 3: State-dependent filters]   apply_scorer_decision (unchanged)
    │                         ├─ frame_type GRAPHIC strip
    │                         ├─ batting_team / no-players short-circuits
    │                         ├─ extractor-empty [GUARD]s
    │                         ├─ Score correction [GUARD]
    │                         ├─ SCORE-INF-FLOOR / SCORE-INF-GATE
    │                         ├─ EXTRAS-INF-GATE / BALLS-CEILING-GATE
    │                         ├─ SCORER-ACTIVE-GATE / DISMISSED-RESURRECT / INVARIANT-FILTER
    │                         ├─ Trust hierarchy
    │                         └─ WICKET-AUTO
    ▼
[Step 4: Apply]              scoreboard.set(...) / update_batter / update_bowler / dismiss_batter
    │                         (downstream consensus, witnessed-out un-dismiss guard, etc.)
    ▼
[Step 5: Post-merge invariants]  NEW for Item 2 implementation phase
                              [BATTERS-INVARIANT]
                                ├─ assert len(active) <= 2
                                └─ assert active ∩ witnessed_out == ∅
                              On violation: rollback the offending change,
                                             log the rejected delta + SM/SB state,
                                             let next frame's strip re-confirm
```

**Rejection layer matrix:**

| Violation type | Rejected at | What the caller sees |
|----------------|-------------|----------------------|
| Type error (string in `runs`) | Step 2 (per-field coerce) | `runs=None`, telemetry log |
| Range violation (`wickets=11`) | Step 2 (per-field coerce + force `accepted=false`) | wickets_update inert |
| Placeholder bowler name | Step 2 (per-row drop) | bowler_update missing this row |
| Missing batter numbers when accepted | Step 2 (per-row drop) | batter_updates missing this entry |
| Whole-decision JSON broken | Step 1 (existing) | Empty `{}` decision, frame skipped |
| Innings-change with score increase | Step 3 (`[GUARD]`) | `innings_change=False`, decision continues |
| Score delta > 7 vs SB | Step 3 (`[GUARD]`) | `CORRECTION_BLOCKED:N`, all updates blocked |
| bat_sum > score (extras-inf) | Step 3 (`[EXTRAS-INF-GATE]`) | `batter_ups` cleared for frame |
| Batter balls > innings ceiling | Step 3 (`[BALLS-CEILING-GATE]`) | `batter_ups` cleared for frame |
| Witnessed-out batter receives update | Step 3 (`[SCORER-ACTIVE-GATE]` / `[SCORER-INVARIANT-FILTER]`) | per-row skip |
| Non-witnessed-out batter receives update | Step 3 (`[SCORER-DISMISSED-RESURRECT]`) | per-row skip |
| Score regression | Step 4 (Scoreboard) | `set()` returns False |
| Wickets regression / cap | Step 4 (Scoreboard `_pending_wickets_*`) | `set()` returns False |
| Active set > 2 / witnessed-out crept in | Step 5 (NEW `[BATTERS-INVARIANT]`) | rollback; await re-confirm |

---

## 6. Filter responsibility matrix

For every `[SCORER-*]` / `[GUARD]` / `[EXTRAS-*]` / `[SCORE-*]` /
`[BALLS-*]` / `[BATTERS-*]` filter, the matrix below records which
of the four enforcement layers (Schema, Step-3 runtime, Step-4
Scoreboard, Step-5 post-merge) is the **owner** vs **defense-in-depth
mirror**. Owner = first layer that detects the violation; mirror =
later layer that catches the same class as a backstop.

| Filter / tag | Owner | Mirror(s) | Rationale |
|--------------|-------|-----------|-----------|
| `[SCORER-SCHEMA-DROP]` (NEW) | Step 2 | — | New parse-time drop |
| `[SCORER-SCHEMA-COERCE]` (NEW) | Step 2 | Step 3 [GUARD] empty-extractor | Coercion to null + accepted=false routes to existing [GUARD] block |
| `[GUARD] Innings change rejected` | Step 3 | — | Compares `score_update.to` vs SB score |
| `[GUARD] Scorer proposed X — extractor empty, blocking` | Step 3 | — | |
| `[GUARD] Score correction in Scorer output` | Step 3 | Step 4 (`Scoreboard.set` regression) | Filter rejects the magnitude; SB still rejects regression on commit |
| `[SCORE-INF-GATE]` (Layer 1.5 floor + Fix 15) | Step 3 | — | Pre-commit; SB has no equivalent |
| `[EXTRAS-INF-GATE]` (Fix 11) | Step 3 | — | Pre-commit physics |
| `[BALLS-CEILING-GATE]` (Fix 14) | Step 3 | `[NEW-BATTER-BALLS-GATE]` (SB) | SB also enforces fresh-batter ceiling; Step 3 is broader (any batter, not just fresh) |
| `[GUARD] Batter not in extractor output` | Step 3 | — | Caller-state check |
| `[INIT] Skipping activation` | Step 3 | Step 2 (per-row drop on accepted=true with both null) | Step 2 catches strict accepted-true case; Step 3 covers the INIT path which doesn't go through `accepted` |
| `[SCORER-ACTIVE-GATE]` | Step 3 | Step 4 (`update_batter` un-dismiss guard) + Step 5 | Triple defense for resurrection class |
| `[SCORER-INVARIANT-FILTER]` (witnessed-out resurrect attempt) | Step 3 | Step 4 + Step 5 | Same |
| `[SCORER-DISMISSED-RESURRECT]` (non-witnessed-out resurrect attempt) | Step 3 | Step 4 + Step 5 | Same |
| `[FLOW] X: extractor … vs scorer …` | Step 3 (informational) | — | Composition rule, not a reject |
| `[GUARD] Scorer proposed dismissal but wickets unchanged` | Step 3 | — | Cross-field consistency |
| `[WICKET-AUTO] Dismissed striker` | Step 3 (action) | — | Constructive; not a reject |
| `Scoreboard.set` regression | Step 4 | Step 3 [GUARD] for score | SB owns monotonicity post-commit |
| `Scoreboard.update_batter` un-dismiss | Step 4 | Step 3 ACTIVE-GATE / INVARIANT-FILTER | SB owns final un-dismiss veto |
| `[NEW-BATTER-BALLS-GATE]` (SB) | Step 4 | Step 3 [BALLS-CEILING-GATE] | SB scope is narrower (fresh admission); Step 3 is broader |
| `[BATTERS-INVARIANT]` (NEW Step 5) | Step 5 | Step 3 ACTIVE-GATE etc. | Post-merge backstop covers paths that Step 3 missed (e.g. card delta bypassing `_scorer_batter_*` helpers) |

---

## 7. Integration plan: schema + filters working together

### 7.1 Defense-in-depth, not replacement

The core decision: **Pydantic is additive.** No existing filter is
removed. Rationale:

1. The schema layer rejects only what is provably wrong **regardless
   of state**. It cannot know about cricket physics, witnessed
   dismissals, or current bat_sum.
2. LLM compliance with the schema (post prompt iteration) is
   probabilistic. An LLM may emit `wickets=10` legitimately at
   all-out **and** illegitimately on a misread. The schema only
   knows the type; the filter knows the cricket context.
3. The existing filters are battle-tested against ~6 weeks of live
   match data. Removing any of them in the same PR as introducing
   the schema would couple two large risks. Item 2 ships the
   schema as **pure additive surface**; future PRs can deprecate
   filters one-by-one with explicit per-filter telemetry showing
   the schema layer is catching the class.

### 7.2 Graceful degradation

If `pydantic.ValidationError` is raised with no recoverable rows,
the new code path returns the **same `{}` empty decision** that
`MatchStateAgent._parse_json` already returns on JSON parse failure.
That keeps the existing "frame skipped, retry on next strip"
contract intact. No new failure mode is introduced.

### 7.3 Observability

Three new telemetry tags ship with the schema layer (proposed):

- `[SCORER-SCHEMA-DROP] field=<top-level> key=<row key> reason=<short>`
- `[SCORER-SCHEMA-COERCE] field=<scalar> raw=<repr> coerced=null reason=<short>`
- `[SCORER-SCHEMA-PARSE-FAIL] reason=<short>` (catastrophic; whole
  decision discarded; pairs with existing JSON-parse path)

Analyzer regression: `analyze_match_telemetry.py` adds these to
`bundle_bc_events` next to the existing `[SCORER-*]` tags so the
bundle B/C report shows schema-layer fire rate alongside filter
fire rate. A drop in filter rate without a rise in schema rate is
the green-light signal that prompt iteration (§3.3) is working;
a rise in schema rate without a drop in filter rate would indicate
LLM has started emitting newly-malformed output and the schema is
the new line of defense.

### 7.4 Prompt iteration as a separate workstream

Per the user's constraint, the prompt-language recommendations in
§3.3 are not applied in this task. The recommended sequence is:

1. **PR 1 (Item 2 schema):** introduce `ScorerDecision` model;
   ship telemetry-only with no filter removal. Validate one
   match-day on the schema-drop / coerce rates.
2. **PR 2 (prompt iteration):** apply §3.3 prompt language; verify
   filter fire rate drops without schema-drop rate rising.
3. **PR 3+ (filter deprecation, opt-in):** for each filter where
   schema + prompt cover the class, add an opt-in flag to skip the
   filter; compare with-flag vs without-flag on a match-day; flip
   the default once schema-only catches the class on N matches.

Item 2 deliverable scope = PR 1 (schema introduction +
`[BATTERS-INVARIANT]` post-merge backstop). PRs 2 and 3 are
follow-ups with their own backlog entries.

---

## 8. Decision points (resolved)

1. **If SCORER output schema becomes Pydantic, which fields become
   typed/constrained vs which stay flexible?**
   See §4.1. Constrained: `team_assignment`, `score_update`,
   `overs_update`, `wickets_update`, `batter_updates[*]`,
   `bowler_update`, `bowlers[*]`, `dismissal`, `innings_change`,
   `vision_hint`. Flexible (`dict | None` with `extra="ignore"`):
   `ball_event`, `ground_truth_applied`, `rejected`, `deferred`,
   plus any new top-level fields the LLM may invent.
2. **Should schema validation reject the entire decision or filter
   individual fields?**
   Per-row drops + per-field coerce. Whole-decision reject only on
   JSON parse failure (existing behavior). See §4.2.
3. **How does schema validation interact with existing Cluster 1
   filters (defense-in-depth or replacement)?**
   **Defense-in-depth.** Schema is additive; no existing filter is
   removed in PR 1. See §7.1.

---

## 9. Estimates

| Phase | Scope | LOC est. | Risk |
|-------|-------|---------:|------|
| **PR 1** schema introduction + `[BATTERS-INVARIANT]` | New file or ~250 LOC in `match_state.py`; ~30 LOC integration in `apply_scorer_decision` (parse + coerce telemetry); ~40 LOC `[BATTERS-INVARIANT]` post-merge; ~80 LOC tests | ~400 | LOW (additive; degrades to current behavior on schema failure) |
| **PR 2** prompt iteration | ~80 LOC in `SCORER_PROMPT`; analyzer fixture extension | ~100 | MEDIUM (LLM behavior change; must re-validate on a clean match-day) |
| **PR 3+** opt-in filter deprecation | Per-filter; flag + a/b telemetry; ~50-100 LOC each | varies | LOW per filter (opt-in) |

**Item 2 design-doc deliverable (this task): complete.**

---

## 10. Clarifications (2026-04-29 addendum)

Sections 1–9 are unchanged. Where a clarification reveals a design
bug, this section uses **back-reference notation** `(§X.Y → 10.Z
back-ref)` to point at the affected paragraph; subsequent sections
SHOULD read 10.Z as the authoritative override.

### 10.1 Step 5 `[BATTERS-INVARIANT]` backstop scope

**Invariants verified (locked).** The Step 5 backstop fires after
all batter / wickets mutations from this frame have committed and
checks three rules in order:

| Rule ID | Predicate | Reads |
|---------|-----------|-------|
| **A** `active_set_max_two` | `len({k for k,v in scoreboard.batting_card.items() if v.get("status") == "batting"}) <= 2` | `scoreboard.batting_card` |
| **B** `no_witnessed_in_active` | `{active} ∩ {k for k in batting_card if scoreboard._is_witnessed_dismissal(k)} == ∅` | `scoreboard.batting_card`, `scoreboard.fall_of_wickets`, `_is_witnessed_dismissal` |
| **C** `striker_card_consistency` | For each of `striker` / `non_striker` (canonical via `_canonical_active_slot`): the resolved name's card MUST be `status=="batting"`; `striker != non_striker` when both non-None | SM properties (which read SB after Item 3) + `scoreboard.batting_card` |

Rule **A** matches backlog P0 invariant (1) verbatim. Rule **B**
matches invariant (2). Rule **C** is new in this clarification —
it covers the `[WS-SLOT-INVARIANT]` class (387 fires in extended
PBKS-vs-RR window per `files/docs/backlog.md` L84) at SCORER decision
boundary instead of WS-payload boundary, complementing the existing
`[STRIKER-STATUS-GATE]` defense in `update_batter` and the
`get_broadcast_state` active-batter filter.

**Action on violation (locked).** Per-rule, in order:

| Rule | Action | Mutates |
|------|--------|---------|
| **A** | Demote the **most recently activated** rule-A violator (highest `_fresh_batter_admission[name].frame` value, else lexically last) back to `status="yet_to_bat"` with `runs=None`, `balls=None`. Log `[BATTERS-INVARIANT] rule=A action=auto_demote demoted=<name>`. | `scoreboard.batting_card[demoted].status` only |
| **B** | Force `status="out"` on the resurrected card (do NOT touch FOW; the witnessed entry is already canonical). Log `[BATTERS-INVARIANT] rule=B action=force_out target=<name>`. | `scoreboard.batting_card[name].status` only |
| **C** | Clear the offending slot in SM (`score_mgr.striker = None` or `score_mgr.non_striker = None` via Item 3 setter, which propagates to `sb._inn` via `_set_inn_slot_with_sm_mirror`). Log `[BATTERS-INVARIANT] rule=C action=clear_slot slot=<striker|non_striker> reason=<card_not_batting|self_collision>`. | SM property setter |

Rationale for "log + auto-correct, never raise": matches the same
rationale that grounded the P0-B "consensus override" pattern in
`files/docs/session_summary_2026-04-25.md` §3 — a single bad frame
must never break SM permanently. Raising would replicate the same
production failure mode the SCORER filters were introduced to
prevent.

**Pipeline position (locked).** The backstop runs at the **end of
`apply_scorer_decision`**, after all `update_batter` / `dismiss_batter`
/ `update_bowler` calls have returned, and **before** the surrounding
frame loop calls `build_full_payload`. Concretely: at
`files/test_pipeline.py` ~L3415 (just before the final `return changes`
at the end of `apply_scorer_decision`). This guarantees:

- Path A WS payload assembly observes corrected state (rule **B**
  `force_out` propagates through `get_broadcast_state` immediately).
- Step 5 telemetry appears in the same DETAIL block as the SCORER
  decision that triggered it, so post-hoc log analysis can correlate
  Step 3 SCORER-* fires (or non-fires) with Step 5 outcomes on the
  same frame.

**Independence from Item 3 `[SM-FEEDER-SYNC]`.** Item 3 SM-FEEDER-SYNC
is a **write-direction** lockstep telemetry (SM property setter →
`SB.set` / direct attribute → log). Step 5 backstop is a **read-
verify-correct** loop on already-committed state. The two never
conflict because:

- Backstop reads SM properties (which, post-Item 3, read through to
  SB), so it sees post-write state.
- Backstop's own writes go through SM property setters (rule **C**)
  or directly through SB methods (rules **A**/**B**), both of which
  re-emit `[SM-FEEDER-SYNC]` if applicable. The only new behavior is
  the corrective write itself.

No new flag-gate is required; the backstop is part of the same
`apply_scorer_decision` code path as the existing SCORER-* filters.

### 10.2 Pydantic version pinning

**Choice (locked):** Pydantic **v2** (specifically `>=2.5,<3`).
Rationale:

- Pydantic v1 reached EOL on **2024-06-30**; no security maintenance.
- §4 model already uses v2-only syntax (`model_config = ConfigDict(...)`,
  `@model_validator(mode="after")`, `field_validator(..., mode="before")`,
  `Field(..., pattern=...)`) — there is no v1-compatible form of
  this spec.
- Groq Python SDK already depends on Pydantic v2 (`>=1.9.0,<3` in
  groq's manifest, with v2 selected by transitive solvers in
  practice). A second pydantic v2 consumer is free.

**Pin proposal:** add to `files/eyes/requirements.txt`:

```
pydantic>=2.5,<3
```

The `>=2.5` floor guarantees `model_validator` and `ConfigDict`
APIs as specified in §4. `<3` keeps the next major-bump opt-in.

**Import path:** all imports come from the top-level `pydantic`
namespace (`from pydantic import BaseModel, Field, field_validator,
model_validator, ConfigDict`). No `pydantic.v1` shim is required
because nothing in the codebase currently uses v1 APIs.

**Test harness interactions:** none. `files/test_recent_fixes.py`
uses plain `pytest` + `unittest`; Pydantic models are pure Python
and instantiable in tests without async fixtures. The existing
`MatchStateAgent.validate` test path (offline JSON capture, e.g.
`files/test_groq_offline.py` L118) becomes a perfect fixture source
for `ScorerDecision.model_validate` tests — feed historical decisions
through the new model and assert the expected per-row drop /
per-field coerce telemetry.

**Transitive dependency conflicts (audited):**

| Existing dep (`files/eyes/requirements.txt`) | Pydantic compatibility |
|---|---|
| `ollama` | Newer versions use Pydantic v2; older versions unconstrained — no conflict |
| `ultralytics` | Uses pydantic optionally; v2-compatible since 8.x |
| `aiohttp` | No pydantic dependency |
| `opencv-python-headless`, `numpy` | No pydantic dependency |
| `pyobjc-framework-Quartz` | No pydantic dependency |
| `groq` (used in `match_state.py`) | Pydantic v2 already required |

Conclusion: **no transitive conflict**. Adding pydantic v2 is a
clean dependency add. Resident memory cost: pydantic-core (Rust
extension) is ~3-5 MB; negligible vs OpenCV / ultralytics footprint.

### 10.3 Per-field coerce semantics edge cases

**Multiple-coerced-fields-in-one-row escalation rule (locked).**
The schema layer applies a **per-row tally**: if **two or more**
fields inside the same row coerce to `None` (with non-null raw
input), the row escalates to a per-row drop with telemetry
`[SCORER-SCHEMA-DROP] field=<top> key=<key> reason=multi_field_coerce
coerced=<comma-separated-fields>`. Single-field coerce stays as a
non-fatal coerce (existing semantics from §4.2).

Rationale: a single coerce on `runs` while `balls` is clean is a
typical OCR misread on one digit; the row is salvageable. Two or
more coerces on the same row indicate the LLM emitted structurally
broken output for that row (e.g. `runs="—", balls="?"`), and any
remaining valid field is too unreliable to commit.

**Cross-field invariant interaction (locked).** When a coerced
field participates in a multi-field invariant, the coerce
**propagates**:

| Multi-field invariant | Coerced field | Propagation rule |
|----------------------|---------------|-------------------|
| `score_update.from + delta = score_update.to` | Either `from` or `to` | Force `accepted=False` on `score_update`; downstream Step 3 `[GUARD] empty-extractor` will fire |
| `wickets_update.to ≥ wickets_update.from` | Either field | Force `accepted=False` on `wickets_update` |
| `BatterUpdate` accepted requires `runs is not None or balls is not None` | Either `runs` or `balls` | If both end up None after coerce → row drop (single-field coerce path; the `model_validator` catches it and the failure converts to a per-row drop) |
| `bowler_update.{overs, runs, wickets}` cumulative spell | Any of the three | Coerce that field to None; do NOT force `accepted=False` (downstream `update_bowler` accepts None for missing fields) |

Per-field rule: a coerce on field `X` MUST also clear any
"accepted" flag on the parent object **only when `X` is the value
field that the accepted flag refers to** (`to`, `runs`, `balls`).
Accepted flags on objects whose value fields are all clean stay
intact.

**Boundary cases (locked).**

| Case | Behavior |
|------|----------|
| `runs` coerced to None, `balls=10` (clean), `accepted=true` | Row passes model validation (model_validator allows runs OR balls). `update_batter(name, runs=None, balls=10, ...)` is supported by the SB API and lets `balls` advance while `runs` waits for a clean strip. Telemetry: `[SCORER-SCHEMA-COERCE]` on `runs` only. |
| `balls` coerced to None, `runs=42` (clean), `accepted=true` | Symmetric to above. Common case for stale strip readers. |
| `runs=None`, `balls=None`, `accepted=true` (raw) | Per-row drop at Step 2 (model_validator). NOT the same code path as Step 3 INIT path #14 (which handles `runs=None` AND `balls=None` from extractor, not from SCORER decision). The two paths are independent and both must remain. |
| `striker: bool` field coerce (raw `"yes"` / `null`) | Coerce to `None`; `update_batter` treats `striker=None` as "no slot change" — existing behavior preserved. |
| `dismissal` raw `[]` (empty list) | Validates as empty list; Step 3 dismissal loop runs zero iterations (existing behavior). |
| `bowler_update` raw `{"name": ""}` | Fails `min_length=1` on `name`; per-row drop. Telemetry: `[SCORER-SCHEMA-DROP] field=bowler_update key=name reason=empty_string`. |

### 10.4 `[BATTERS-INVARIANT]` failure mode

**Escalation behavior (locked):** **WARN-level telemetry +
auto-correction**, NEVER raise. This is non-negotiable for production
because:

- A raised exception inside `apply_scorer_decision` would propagate
  to the frame loop and break the next 3-frame consensus window;
  one bad frame would translate to ~3 frames of UI freeze.
- The auto-correction in §10.1 is bounded (touches at most one
  card per rule per fire), so the worst case is a transient UI
  flicker on the affected card while strip re-reads converge.

Action map (locked):

| Phase | Behavior of `[BATTERS-INVARIANT]` |
|-------|-----------------------------------|
| **Phase 1 (PR 1, ~first match-day)** | Telemetry-only WARN; auto-correction **disabled** behind `BATTERS_INVARIANT_AUTOCORRECT=False` env flag (default off). Validates rate-of-fire on a real match before flipping write semantics. |
| **Phase 2 (after 1 clean match-day on Phase 1)** | Auto-correction **enabled** (`BATTERS_INVARIANT_AUTOCORRECT=True`). Telemetry stays WARN. |
| **Phase 3 (deferred, see below)** | If three-layers-leaking (Step 3 + Step 4 + Step 5 all bypassed and a violation reaches build_full_payload anyway), file a separate backlog item; do NOT escalate to ERROR or raise inside the backstop. |

**Why three-layers-leaking is a Phase 2+ concern, not a Phase 1
hard-fail.** Three layers leaking is structural evidence that:

1. The SCORER-* filters in Step 3 didn't recognize the violation
   class (LLM emitted a row that bypasses `_is_witnessed_dismissal`
   check — likely a witnessed-out card whose name resolved
   differently this frame; or a non-batting card flipping to
   batting via an unknown code path).
2. The Step 4 SB defenses (`update_batter` un-dismiss guard,
   `dismiss_batter` status check) also bypassed — likely because
   the violating mutation came through a route that doesn't pass
   those checkpoints (e.g. direct `batting_card[name].status =
   "batting"` assignment outside `update_batter`).
3. The class is now visible at Step 5 only.

Hard-failing in Phase 1 would gate every match-day on us never
hitting case (1)/(2)/(3). The architecture P0-B explicitly fixed
in 2026-04-25 was "one bad frame breaks SM permanently"; raising
in Step 5 reintroduces that exact failure mode. Instead, Phase 3
work item: enumerate the leak path, file a backlog item, fix at
the upstream layer (Step 3 or Step 4), then optionally tighten Step
5 to ERROR-level **only** when leaks have been eliminated for N
matches.

**Telemetry format (locked).** Every fire emits a single line:

```
[BATTERS-INVARIANT] rule=<A|B|C> violation=<short> \
    active=<comma-list> witnessed_out=<comma-list> \
    striker=<canonical|None> non_striker=<canonical|None> \
    upstream_step3_fired=<true|false> \
    upstream_step3_tags=<comma-list of [SCORER-*] tags this frame> \
    upstream_step4_returned_false=<true|false> \
    action=<auto_demote|force_out|clear_slot|noop_phase1> \
    target=<name|slot> frame=<F#>
```

The `upstream_step3_*` and `upstream_step4_*` fields are CRITICAL
for Phase 3 leak diagnosis — they let the analyzer answer "did Step
3 see this and let it through, or did the row bypass Step 3
entirely?" without cross-log correlation. Implementation note: the
tracker for these flags lives in a per-frame dict that
`apply_scorer_decision` populates as filters fire / Scoreboard methods
return False. The `[BATTERS-INVARIANT]` tag at function-end reads
that dict.

### 10.5 PR 1 internal migration order

**Sub-step sequence (locked):**

| Sub-step | Scope | Independently testable? | Recommended commit unit |
|---|---|---|---|
| **1.0** | Add `pydantic>=2.5,<3` to `files/eyes/requirements.txt`; verify `python -c 'import pydantic; print(pydantic.VERSION)'` | Yes (just an import smoke test) | **Commit 1** with 1.1 |
| **1.1** | Define `ScorerDecision` model + nested types in `files/eyes/match_state.py` (no integration; module-level definition only) | Yes (`pytest` round-trip from captured fixtures, asserting parse correctness on ~5 saved decisions) | **Commit 1** with 1.0 |
| **2.0** | Wire `ScorerDecision.model_validate` into `MatchStateAgent.validate` after `_parse_json`; on `ValidationError` fall back to current dict path; expose parsed model as a dict (via `.model_dump(by_alias=True, exclude_none=False)`) so `apply_scorer_decision` consumes the same shape | Yes (offline `MatchStateAgent.validate` smoke test with mocked Groq) | **Commit 2** with 2.1 + 2.2 |
| **2.1** | Add `[SCORER-SCHEMA-DROP]` telemetry on per-row drops | Yes (synthetic decision with bad row → assert log line) | **Commit 2** |
| **2.2** | Add `[SCORER-SCHEMA-COERCE]` telemetry on per-field coerce | Yes (synthetic decision with bad scalar → assert log line) | **Commit 2** |
| **3.0** | Add Step 5 `[BATTERS-INVARIANT]` backstop function (rules A/B/C from §10.1) at `apply_scorer_decision` end; gated `BATTERS_INVARIANT_AUTOCORRECT=False` per §10.4 | Yes (replay F339-class fixture; assert backstop fires WARN-only by default) | **Commit 3** with 3.1 |
| **3.1** | Update `files/analyze_match_telemetry.py` with regex for `[SCORER-SCHEMA-DROP]`, `[SCORER-SCHEMA-COERCE]`, `[SCORER-SCHEMA-PARSE-FAIL]`, `[BATTERS-INVARIANT]` + bundle B/C rows; extend analyzer self-test fixture | Yes (existing analyzer self-test pattern) | **Commit 3** |
| **3.2** | Backlog update; analyzer doc update | Yes (text only) | **Commit 3** |

**Three commits inside PR 1, in order:** (1) dep + model + parse
tests; (2) integration + telemetry; (3) backstop + analyzer +
backlog. Each commit leaves the repo in a green-test state and
each can be reverted independently. The reviewer can squash to a
single PR commit if preferred (per Item 3 contract §12.4 precedent).

**Why this order.** Sub-step 1.x has no dependency on the rest of
the codebase. Sub-step 2.x can ship telemetry-only (drops are
real but downstream Step 3 filters still run on what's left;
existing Path A/Path B unchanged). Sub-step 3.x is the only one
that mutates SB state (rule **B** `force_out`; rule **C** clears
slot), so it ships last and behind the autocorrect flag for the
first match-day per §10.4.

### 10.6 Existing filter telemetry preservation

**Do filters fire on schema-caught violations?** Per §4.2 / §5,
schema **drops** the row before Step 3 sees it, so Step 3 filters
**do not fire** on schema-caught violations in normal operation.
This is correct for production but **breaks the a/b telemetry
strategy in §7.3 that assumed concurrent rate measurement**
(§7.3 → 10.6 back-ref; see "Design bug" below).

**A/b measurement strategy (locked).** Two-phase, per §10.4:

| Phase | Schema action | Filter visibility | Analyzer signal |
|-------|--------------|-------------------|-----------------|
| **Phase 1 (PR 1, ~first match-day)** | Schema runs in **shadow mode** (see "Shadow mode" below); rows are NOT dropped; filters see all rows as today | Filters fire as today; full pre-PR1 baseline preserved | Compare `[SCORER-SCHEMA-WOULD-DROP]` count vs `[SCORER-INVARIANT-FILTER]` / `[SCORER-DISMISSED-RESURRECT]` / `[SCORER-ACTIVE-GATE]` overlap. Redundancy = both fire on same row; schema-only = new catches; filter-only = schema gap (refine model) |
| **Phase 2 (PR 1 + flip after Phase-1 a/b clean)** | Schema **enforces** drops; filter rate naturally collapses for the schema-covered class | Filter fire rate becomes the leak indicator (filter-fire = schema didn't catch a class it should have) | Watch for filter-fire rate above zero on schema-covered classes — that is the signal to refine the schema |

**Shadow mode (locked).** A `SCORER_SCHEMA_ENFORCE` env flag
(default `False` in PR 1, flipped to `True` after Phase-1 validation):

- `False` (Phase 1): `model_validate` runs; on per-row failure the
  pipeline emits `[SCORER-SCHEMA-WOULD-DROP] field=<top> key=<key>
  reason=<short> filter_caught_in_step3=<true|false>` and **passes
  the original raw row through unchanged** to Step 3. The
  `filter_caught_in_step3` flag is computed at Step 3 by checking
  whether any `[SCORER-*]` filter fired on the same row (rate
  determined per-row via the per-frame tracker dict from §10.4).
- `True` (Phase 2): per §4.2 — actual drop, telemetry switches to
  `[SCORER-SCHEMA-DROP]` (no `WOULD-`), filter rate organically
  collapses on covered classes.

The two telemetry tags (`-WOULD-DROP` vs `-DROP`) are intentionally
distinct so analyzer can compare across the cutover boundary
without ambiguity about which mode produced which line.

**Per-field coerce shadow:** symmetric. Phase 1 emits
`[SCORER-SCHEMA-WOULD-COERCE]` and **does not coerce** the value
(raw passes through); Phase 2 emits `[SCORER-SCHEMA-COERCE]` and
coerces. This guarantees that the existing Step 3 `[GUARD] …
extractor empty, blocking` rate stays comparable across the
cutover.

**"Would-have-fired" markers required (locked).** Yes: the
`-WOULD-` variants are exactly the would-have-fired markers needed
for accurate measurement. Without them, the moment schema enforces
on day 1, every filter rate that the schema covers drops to zero,
and the analyzer cannot distinguish "schema correctly absorbed the
class" from "the class no longer occurs in production." The
shadow-mode + WOULD-marker pattern gives one match-day of
overlapping signal that resolves both questions simultaneously.

#### Design bug surfaced and back-referenced

**Bug:** §7.3 (paragraph "A drop in filter rate without a rise in
schema rate is the green-light signal …") implicitly assumes both
schema rate and filter rate can be measured concurrently across
the same set of rows. As written in §4.2 / §5 (per-row drop in
PR 1), schema enforces from day 1, so filter rate trivially drops
to zero on covered classes regardless of LLM behavior, and the
"drop without rise" comparison degenerates.

**Affects:** §7.3 ("Observability" paragraph). §4.2 (which says
PR 1 enforces) is also affected indirectly because it encodes the
PR 1 default that triggers the §7.3 degeneracy.

**Proposed correction (per Item 3 contract §12.6 back-ref pattern):**
Sections 4.2, 5, and 7.3 SHOULD be read with the §10.6 phase split
as the authoritative override. Concretely:

- **§4.2 → §10.6 back-ref:** "Per-row drop" and "Per-field coerce"
  are the **Phase 2** semantics. Phase 1 default is shadow mode
  (`SCORER_SCHEMA_ENFORCE=False`); rows pass through unchanged with
  `-WOULD-` telemetry.
- **§5 → §10.6 back-ref:** Step 2 of the validation flow is
  flag-gated. With `SCORER_SCHEMA_ENFORCE=False` (Phase 1), Step 2
  emits telemetry only and the original row continues to Step 3.
  With `SCORER_SCHEMA_ENFORCE=True` (Phase 2), Step 2 enforces as
  diagrammed.
- **§7.3 → §10.6 back-ref:** The concurrent-rate comparison is the
  Phase-1 a/b signal (one match-day), not the steady-state
  observability. Steady state (Phase 2) is "filter fire = schema
  gap (refine model)" per the table in §10.6.

Reasoning for non-removal of §7.3: the underlying intuition (drop
in filter rate is a positive signal; rise in schema rate is a
defensive signal) remains correct as a steady-state heuristic
**after** the Phase-1 → Phase-2 flip. The §10.6 phase split is the
only refinement needed.

**No further sections require correction.** §1, §2, §3, §6, §8, §9
are unaffected.

### 10.7 Architectural deviation from §4: helpers, not root

§4 of this contract specified `ScorerDecision` as the parent Pydantic
model carrying whole-decision validation logic via `model_validator`.
Implementation chose a different architecture:

- Whole-decision logic (per-row drops, JSON parse fallback, schema
  enforcement) lives in `process_scorer_decision_schema` helper function
  (`files/scorer_decision_schema.py`).
- Row-level invariants live on sub-models via `@model_validator`
  (`BatterUpdate`, `BowlerUpdate`).
- `ScorerDecision` root model exists but is unused in production paths.

**Reasoning for the choice (post-hoc):**

- Helper-function dispatch is easier to test (no model construction
  overhead).
- Easier to integrate with §10.6 shadow-mode (helpers can branch on flag
  without triggering root validation).
- Per-row drop logic is cleaner as imperative code than as
  `model_validator` with conditional logic.
- JSON parse fallback to `{}` stays in `MatchStateAgent` unchanged.

§4 sub-model specs remain accurate (`BatterUpdate`,
`BowlerUpdate`, `ScoreUpdate` field validators are correct
as specified). Only the root-level validators in §4.2
moved to `process_scorer_decision_schema`.

Future PRs that want root-level whole-decision
validation can populate `ScorerDecision` with `model_validator` and
migrate `process_scorer_decision_schema` to wrap it. Not currently
needed.

---

## Files

- **New:** `files/docs/investigations/scorer_invariants_categorization.md`
  (this document)
- **No code changes** in this task. Output feeds Item 2 PR 1.
