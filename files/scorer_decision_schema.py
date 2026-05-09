"""SCORER decision schema (Item 2 PR 1) — Pydantic v2 + normalize/coerce helpers.

Phase 1 defaults: ``SCORER_SCHEMA_ENFORCE`` and ``BATTERS_INVARIANT_AUTOCORRECT``
are False (shadow telemetry only for schema; telemetry-only for backstop).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Literal,
    Optional,
    Tuple,
    Type,
    Union,
)

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

# ---------------------------------------------------------------------------
# Feature flags (Phase 1 defaults False; Phase 2 enable after match-day a/b)
# ---------------------------------------------------------------------------
SCORER_SCHEMA_ENFORCE = False
BATTERS_INVARIANT_AUTOCORRECT = False

# ---------------------------------------------------------------------------
# Placeholder parity with ``test_pipeline._is_placeholder`` (no import cycle)
# ---------------------------------------------------------------------------
_SCHEMA_PLACEHOLDER_EXACT = {
    "UNNAMED", "UNKNOWN", "NULL", "NONE", "N/A",
    "NOT_VISIBLE", "NOT_SHOWN", "NAME", "PLAYER", "BATTER", "BOWLER",
}


def _schema_is_placeholder(name: str) -> bool:
    if not name:
        return True
    up = name.upper().strip()
    if up in _SCHEMA_PLACEHOLDER_EXACT:
        return True
    if re.match(r"^BATTER\d*", up):
        return True
    if re.match(r"^BOWLER\d*", up):
        return True
    if re.match(r"^PLAYER\d*", up):
        return True
    if "FROM_VISION" in up:
        return True
    if "EXACT_" in up:
        return True
    if "_NAME" in up:
        return True
    return False


def _coerce_int_sr(value: Any) -> Optional[int]:
    """Mirror ``test_pipeline._sr_int`` (split team score ``154-3`` prefix)."""
    try:
        if value is None:
            return None
        return int(str(value).split("-")[0])
    except (TypeError, ValueError):
        return None


def _coerce_float_innings(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        fv = float(value)
    except (TypeError, ValueError):
        return None
    if fv < 0 or fv > 20:
        return None
    return fv


def _raw_meaningful(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and not str(value).strip():
        return False
    return True


# ---------------------------------------------------------------------------
# Pydantic sub-models (design contract §4)
# ---------------------------------------------------------------------------
class ScoreUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)
    from_: Optional[int] = Field(default=None, alias="from", ge=0)
    to: Optional[int] = Field(default=None, ge=0)
    accepted: bool = False

    @field_validator("from_", "to", mode="before")
    @classmethod
    def _coerce_int(cls, v: Any) -> Any:
        return _coerce_int_sr(v)


class OversUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)
    from_: Optional[float] = Field(default=None, alias="from", ge=0, le=20)
    to: Optional[float] = Field(default=None, ge=0, le=20)
    accepted: bool = False

    @field_validator("from_", "to", mode="before")
    @classmethod
    def _coerce_ov(cls, v: Any) -> Any:
        return _coerce_float_innings(v)


class WicketsUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)
    from_: Optional[int] = Field(default=None, alias="from", ge=0, le=10)
    to: Optional[int] = Field(default=None, ge=0, le=10)
    accepted: bool = False

    @field_validator("from_", "to", mode="before")
    @classmethod
    def _coerce_wk(cls, v: Any) -> Any:
        return _coerce_int_sr(v)


class BatterUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    runs: Optional[int] = Field(default=None, ge=0)
    balls: Optional[int] = Field(default=None, ge=0)
    fours: Optional[int] = Field(default=None, ge=0)
    sixes: Optional[int] = Field(default=None, ge=0)
    striker: Optional[bool] = None
    accepted: bool = True

    @model_validator(mode="after")
    def _runs_or_balls_when_accepted(self) -> BatterUpdate:
        if self.accepted and self.runs is None and self.balls is None:
            raise ValueError(
                "BatterUpdate accepted=true requires at least one of runs/balls non-null"
            )
        return self


class BowlerSpell(BaseModel):
    """Single bowler spell row (name required; placeholders rejected)."""

    model_config = ConfigDict(extra="ignore")
    name: str = Field(..., min_length=1)
    overs: Optional[float] = Field(default=None, ge=0, le=20)
    runs: Optional[int] = Field(default=None, ge=0)
    wickets: Optional[int] = Field(default=None, ge=0, le=10)
    accepted: bool = True

    @field_validator("name", mode="after")
    @classmethod
    def _reject_placeholder_name(cls, v: str) -> str:
        if _schema_is_placeholder(v):
            raise ValueError("placeholder bowler name")
        return v

    @field_validator("overs", mode="before")
    @classmethod
    def _ov(cls, v: Any) -> Any:
        return _coerce_float_innings(v)

    @field_validator("runs", "wickets", mode="before")
    @classmethod
    def _ints(cls, v: Any) -> Any:
        return _coerce_int_sr(v)


class DismissalDict(BaseModel):
    model_config = ConfigDict(extra="ignore")
    batter: Optional[str] = None
    name: Optional[str] = None
    how: Optional[str] = None
    bowler: Optional[str] = None
    fielder: Optional[str] = None

    @model_validator(mode="after")
    def _has_subject(self) -> DismissalDict:
        if not (self.batter or self.name):
            raise ValueError("Dismissal dict requires batter or name")
        return self


class ScorerDecision(BaseModel):
    """Root model for SCORER LLM output.

    NOTE: Production schema validation does NOT flow through this root
    model. Use ``process_scorer_decision_schema`` (helper function in this
    module) for actual validation. This class is preserved as a public
    symbol for future extensions that want root-level whole-decision
    validation.

    See ``files/docs/investigations/scorer_invariants_categorization.md``
    §10.7 for context on the helper-vs-root architecture choice.
    """

    model_config = ConfigDict(extra="allow")


@dataclass
class SchemaShadowEvent:
    kind: Literal["would_drop", "would_coerce"]
    top_field: str
    key: Optional[str]
    reason: str
    raw: Any = None
    coerced_fields: tuple[str, ...] = ()
    scalar_subfield: Optional[str] = None


LogFn = Callable[[str], None]


def _log_drop(
    log_warn: LogFn,
    tag: str,
    *,
    top_field: str,
    key: Optional[str],
    reason: str,
    frame: int,
) -> None:
    log_warn(
        f"  [{tag}] field={top_field} key={key or '-'} "
        f"reason={reason} frame=F{frame}"
    )


def _log_coerce(
    log_info: LogFn,
    tag: str,
    *,
    field_path: str,
    raw: Any,
    reason: str,
    frame: int,
) -> None:
    log_info(
        f"  [{tag}] field={field_path} raw={raw!r} coerced=null "
        f"reason={reason} frame=F{frame}"
    )


def _batter_numeric_coerces(row: dict) -> tuple[list[str], Dict[str, Any]]:
    """Per §10.3: count fields that had meaningful raw but coerced to None."""
    coerced_fields: list[str] = []
    out: Dict[str, Any] = {}
    for fname in ("runs", "balls", "fours", "sixes"):
        raw = row.get(fname)
        if not _raw_meaningful(raw):
            out[fname] = row.get(fname)
            continue
        cv = _coerce_int_sr(raw)
        out[fname] = cv
        if cv is None:
            coerced_fields.append(fname)
    return coerced_fields, out


def _validate_batter_row(key: str, row: Dict[str, Any]) -> Tuple[Optional[dict], Optional[str]]:
    if not isinstance(row, dict):
        return None, "not_a_dict"
    num_coerced, numeric_frag = _batter_numeric_coerces(row)
    if len(num_coerced) >= 2:
        return None, f"multi_field_coerce:{','.join(num_coerced)}"
    base = {**row, **numeric_frag}
    try:
        model = BatterUpdate.model_validate(base)
    except ValidationError:
        return None, "batter_update_validation"
    return model.model_dump(exclude_none=False), None


def _normalize_team_assignment(
    decision: dict,
    *,
    frame: int,
    enforce: bool,
    log_info: LogFn,
    events: list[SchemaShadowEvent],
    tag_coerce: str,
) -> None:
    ta = decision.get("team_assignment")
    if not isinstance(ta, dict):
        return
    for fld in ("batting_team", "bowling_team"):
        if ta.get(fld) is not None:
            raw = ta.get(fld)
            if enforce:
                _log_coerce(
                    log_info, tag_coerce,
                    field_path=f"team_assignment.{fld}", raw=raw,
                    reason="must_be_null", frame=frame,
                )
                ta[fld] = None
            else:
                events.append(SchemaShadowEvent(
                    kind="would_coerce",
                    top_field="team_assignment",
                    key=fld,
                    reason="must_be_null",
                    raw=raw,
                    coerced_fields=(fld,),
                    scalar_subfield=fld,
                ))


def _normalize_score_like_block(
    field_name: str,
    model_cls: Union[Type[ScoreUpdate], Type[OversUpdate], Type[WicketsUpdate]],
    decision: dict,
    *,
    frame: int,
    enforce: bool,
    log_warn: LogFn,
    log_info: LogFn,
    events: list[SchemaShadowEvent],
    tag_drop: str,
    tag_coerce: str,
) -> None:
    block = decision.get(field_name)
    if not isinstance(block, dict):
        return
    patch: Dict[str, Any] = dict(block)
    orig_accepted = bool(block.get("accepted"))
    for sub in ("from", "to"):
        raw = block.get(sub)
        if not _raw_meaningful(raw):
            continue
        if model_cls is OversUpdate:
            cv = _coerce_float_innings(raw)
        else:
            cv = _coerce_int_sr(raw)
        in_range = cv is not None
        if model_cls is WicketsUpdate and cv is not None and not (0 <= int(cv) <= 10):
            in_range = False
        if model_cls is ScoreUpdate and cv is not None and int(cv) < 0:
            in_range = False
        if in_range:
            patch[sub] = cv
            continue
        if enforce:
            _log_coerce(
                log_info, tag_coerce,
                field_path=f"{field_name}.{sub}", raw=raw,
                reason="coerce_null_accepted_false", frame=frame,
            )
            patch[sub] = None
            patch["accepted"] = False
        else:
            events.append(SchemaShadowEvent(
                kind="would_coerce",
                top_field=field_name,
                key=None,
                reason="coerce_null",
                raw=raw,
                coerced_fields=(sub,),
                scalar_subfield=sub,
            ))
            patch[sub] = None
            patch["accepted"] = False
    try:
        validated = model_cls.model_validate(patch)
        dumped = validated.model_dump(by_alias=True, exclude_none=False)
    except ValidationError:
        if enforce:
            _log_drop(
                log_warn, tag_drop,
                top_field=field_name, key="-", reason="block_validation",
                frame=frame,
            )
            decision.pop(field_name, None)
        else:
            events.append(SchemaShadowEvent(
                kind="would_drop",
                top_field=field_name,
                key=None,
                reason="block_validation",
            ))
        return
    if enforce:
        decision[field_name] = dumped
    else:
        if orig_accepted and not dumped.get("accepted"):
            events.append(SchemaShadowEvent(
                kind="would_coerce",
                top_field=field_name,
                key=None,
                reason="accepted_forced_false",
                scalar_subfield="accepted",
            ))


def _normalize_batter_updates(
    decision: dict,
    *,
    frame: int,
    enforce: bool,
    log_warn: LogFn,
    events: list[SchemaShadowEvent],
    tag_drop: str,
) -> None:
    bu = decision.get("batter_updates")
    if not isinstance(bu, dict):
        return
    if enforce:
        new_bu: Dict[str, Any] = {}
        for key, row in list(bu.items()):
            norm, drop_reason = _validate_batter_row(str(key), row)
            if drop_reason:
                _log_drop(
                    log_warn, tag_drop,
                    top_field="batter_updates", key=str(key), reason=drop_reason,
                    frame=frame,
                )
                continue
            merged = dict(row)
            merged.update(norm or {})
            new_bu[key] = merged
        decision["batter_updates"] = new_bu
    else:
        for key, row in list(bu.items()):
            _, drop_reason = _validate_batter_row(str(key), row)
            if drop_reason:
                events.append(SchemaShadowEvent(
                    kind="would_drop",
                    top_field="batter_updates",
                    key=str(key),
                    reason=drop_reason,
                ))


def _bowler_aux_coerces(data: dict) -> tuple[list[str], Dict[str, Any]]:
    coerced: list[str] = []
    out = dict(data)
    for fname, coerce_fn in (
        ("overs", _coerce_float_innings),
        ("runs", _coerce_int_sr),
        ("wickets", _coerce_int_sr),
    ):
        raw = data.get(fname)
        if not _raw_meaningful(raw):
            continue
        cv = coerce_fn(raw)
        out[fname] = cv
        if cv is None:
            coerced.append(fname)
    return coerced, out


def _normalize_bowler_update(
    decision: dict,
    *,
    frame: int,
    enforce: bool,
    log_warn: LogFn,
    events: list[SchemaShadowEvent],
    tag_drop: str,
) -> None:
    bu = decision.get("bowler_update")
    if not isinstance(bu, dict) or not bu:
        return
    if "name" in bu:
        name = bu.get("name", "")
        aux_coerced, aux_frag = _bowler_aux_coerces(bu)
        if len(aux_coerced) >= 2:
            if enforce:
                _log_drop(
                    log_warn, tag_drop,
                    top_field="bowler_update", key=str(name),
                    reason=f"multi_field_coerce:{','.join(aux_coerced)}",
                    frame=frame,
                )
                decision["bowler_update"] = {}
            else:
                events.append(SchemaShadowEvent(
                    kind="would_drop",
                    top_field="bowler_update",
                    key=str(name),
                    reason=f"multi_field_coerce:{','.join(aux_coerced)}",
                ))
            return
        row = {**bu, **aux_frag}
        try:
            spell = BowlerSpell.model_validate(row)
        except ValidationError:
            if enforce:
                _log_drop(
                    log_warn, tag_drop,
                    top_field="bowler_update", key=str(name),
                    reason="bowler_validation",
                    frame=frame,
                )
                decision["bowler_update"] = {}
            else:
                events.append(SchemaShadowEvent(
                    kind="would_drop",
                    top_field="bowler_update",
                    key=str(name),
                    reason="bowler_validation",
                ))
            return
        if enforce:
            decision["bowler_update"] = spell.model_dump(exclude_none=False)
    else:
        if enforce:
            new_multi: Dict[str, Any] = {}
            for bname, bdata in list(bu.items()):
                if not isinstance(bdata, dict):
                    continue
                aux_coerced, aux_frag = _bowler_aux_coerces(bdata)
                if len(aux_coerced) >= 2:
                    _log_drop(
                        log_warn, tag_drop,
                        top_field="bowler_update", key=str(bname),
                        reason=f"multi_field_coerce:{','.join(aux_coerced)}",
                        frame=frame,
                    )
                    continue
                row = {"name": bname, **bdata, **aux_frag}
                try:
                    spell = BowlerSpell.model_validate(row)
                    inner = spell.model_dump(exclude_none=False)
                    inner.pop("name", None)
                    new_multi[bname] = inner
                except ValidationError:
                    _log_drop(
                        log_warn, tag_drop,
                        top_field="bowler_update", key=str(bname),
                        reason="bowler_validation",
                        frame=frame,
                    )
            decision["bowler_update"] = new_multi
        else:
            for bname, bdata in list(bu.items()):
                if not isinstance(bdata, dict):
                    continue
                aux_coerced, aux_frag = _bowler_aux_coerces(bdata)
                if len(aux_coerced) >= 2:
                    events.append(SchemaShadowEvent(
                        kind="would_drop",
                        top_field="bowler_update",
                        key=str(bname),
                        reason=f"multi_field_coerce:{','.join(aux_coerced)}",
                    ))
                    continue
                row = {"name": bname, **bdata, **aux_frag}
                try:
                    BowlerSpell.model_validate(row)
                except ValidationError:
                    events.append(SchemaShadowEvent(
                        kind="would_drop",
                        top_field="bowler_update",
                        key=str(bname),
                        reason="bowler_validation",
                    ))


def _normalize_bowlers_array(
    decision: dict,
    *,
    frame: int,
    enforce: bool,
    log_warn: LogFn,
    events: list[SchemaShadowEvent],
    tag_drop: str,
) -> None:
    arr = decision.get("bowlers")
    if not isinstance(arr, list):
        return
    if enforce:
        new_list: list[Any] = []
        for i, item in enumerate(arr):
            if not isinstance(item, dict):
                continue
            name = item.get("name", "")
            aux_coerced, aux_frag = _bowler_aux_coerces(item)
            if len(aux_coerced) >= 2:
                _log_drop(
                    log_warn, tag_drop,
                    top_field="bowlers", key=str(name) or str(i),
                    reason=f"multi_field_coerce:{','.join(aux_coerced)}",
                    frame=frame,
                )
                continue
            row = {**item, **aux_frag}
            try:
                spell = BowlerSpell.model_validate(row)
                new_list.append(spell.model_dump(exclude_none=False))
            except ValidationError:
                _log_drop(
                    log_warn, tag_drop,
                    top_field="bowlers", key=str(name) or str(i),
                    reason="bowler_validation",
                    frame=frame,
                )
        decision["bowlers"] = new_list
    else:
        for i, item in enumerate(arr):
            if not isinstance(item, dict):
                continue
            name = item.get("name", "")
            aux_coerced, aux_frag = _bowler_aux_coerces(item)
            if len(aux_coerced) >= 2:
                events.append(SchemaShadowEvent(
                    kind="would_drop",
                    top_field="bowlers",
                    key=str(name) or str(i),
                    reason=f"multi_field_coerce:{','.join(aux_coerced)}",
                ))
                continue
            row = {**item, **aux_frag}
            try:
                BowlerSpell.model_validate(row)
            except ValidationError:
                events.append(SchemaShadowEvent(
                    kind="would_drop",
                    top_field="bowlers",
                    key=str(name) or str(i),
                    reason="bowler_validation",
                ))


def _normalize_dismissal(decision: dict, *, frame: int, enforce: bool, log_warn: LogFn,
                         events: list[SchemaShadowEvent], tag_drop: str) -> None:
    dmiss = decision.get("dismissal")
    if dmiss is None:
        return
    if isinstance(dmiss, str):
        return
    if isinstance(dmiss, dict):
        try:
            DismissalDict.model_validate(dmiss)
        except ValidationError:
            if enforce:
                _log_drop(
                    log_warn, tag_drop,
                    top_field="dismissal", key="-", reason="dismissal_dict_invalid",
                    frame=frame,
                )
                decision["dismissal"] = None
            else:
                events.append(SchemaShadowEvent(
                    kind="would_drop",
                    top_field="dismissal",
                    key=None,
                    reason="dismissal_dict_invalid",
                ))
        return
    if isinstance(dmiss, list):
        if enforce:
            kept: list[Any] = []
            for idx, item in enumerate(dmiss):
                if isinstance(item, str):
                    kept.append(item)
                    continue
                if isinstance(item, dict):
                    try:
                        DismissalDict.model_validate(item)
                        kept.append(item)
                    except ValidationError:
                        _log_drop(
                            log_warn, tag_drop,
                            top_field="dismissal", key=str(idx),
                            reason="dismissal_item_invalid",
                            frame=frame,
                        )
                    continue
            decision["dismissal"] = kept or None
        else:
            for idx, item in enumerate(dmiss):
                if isinstance(item, dict):
                    try:
                        DismissalDict.model_validate(item)
                    except ValidationError:
                        events.append(SchemaShadowEvent(
                            kind="would_drop",
                            top_field="dismissal",
                            key=str(idx),
                            reason="dismissal_item_invalid",
                        ))


def process_scorer_decision_schema(
    decision: dict,
    *,
    frame: int,
    enforce: bool,
    log,
) -> list[SchemaShadowEvent]:
    """Normalize *decision* in place when ``enforce``; else return shadow events.

    When ``enforce`` is True, emits ``[SCORER-SCHEMA-DROP]`` /
    ``[SCORER-SCHEMA-COERCE]`` and returns an empty list.
    When False, returns shadow events for deferred logging with
    ``filter_caught_in_step3`` (caller fills via ``finalize_schema_shadow_logs``).
    """
    events: list[SchemaShadowEvent] = []
    tag_drop = "SCORER-SCHEMA-DROP"
    tag_coerce = "SCORER-SCHEMA-COERCE"
    log_warn = log.warn
    log_info = log.info

    _normalize_team_assignment(
        decision, frame=frame, enforce=enforce, log_info=log_info,
        events=events, tag_coerce=tag_coerce,
    )
    _normalize_score_like_block(
        "score_update", ScoreUpdate, decision,
        frame=frame, enforce=enforce, log_warn=log_warn, log_info=log_info,
        events=events, tag_drop=tag_drop, tag_coerce=tag_coerce,
    )
    _normalize_score_like_block(
        "overs_update", OversUpdate, decision,
        frame=frame, enforce=enforce, log_warn=log_warn, log_info=log_info,
        events=events, tag_drop=tag_drop, tag_coerce=tag_coerce,
    )
    _normalize_score_like_block(
        "wickets_update", WicketsUpdate, decision,
        frame=frame, enforce=enforce, log_warn=log_warn, log_info=log_info,
        events=events, tag_drop=tag_drop, tag_coerce=tag_coerce,
    )
    _normalize_batter_updates(
        decision, frame=frame, enforce=enforce, log_warn=log_warn,
        events=events, tag_drop=tag_drop,
    )
    _normalize_bowler_update(
        decision, frame=frame, enforce=enforce, log_warn=log_warn,
        events=events, tag_drop=tag_drop,
    )
    _normalize_bowlers_array(
        decision, frame=frame, enforce=enforce, log_warn=log_warn,
        events=events, tag_drop=tag_drop,
    )
    _normalize_dismissal(
        decision, frame=frame, enforce=enforce, log_warn=log_warn,
        events=events, tag_drop=tag_drop,
    )

    if enforce:
        return []
    return events


def finalize_schema_shadow_logs(
    events: list[SchemaShadowEvent],
    *,
    frame: int,
    log,
    step3_notes: list[tuple[str, str]],
    changes: list[str],
) -> None:
    """Emit ``[SCORER-SCHEMA-WOULD-DROP]`` / ``[SCORER-SCHEMA-WOULD-*]`` lines."""
    caught_names = {n.upper() for _t, n in step3_notes}
    score_blocked = any(
        c.startswith("CORRECTION_BLOCKED") or c.startswith("SCORE-INF-GATE")
        for c in changes
    )
    for ev in events:
        if ev.kind == "would_drop":
            fc = "false"
            if ev.top_field == "batter_updates" and ev.key:
                if ev.key.upper() in caught_names:
                    fc = "true"
            log.warn(
                f"  [SCORER-SCHEMA-WOULD-DROP] field={ev.top_field} "
                f"key={ev.key or '-'} reason={ev.reason} "
                f"filter_caught_in_step3={fc} frame=F{frame}"
            )
        elif ev.kind == "would_coerce":
            fc = "false"
            if ev.top_field == "score_update" and ev.scalar_subfield == "to":
                fc = "true" if score_blocked else "false"
            if (ev.top_field == "batter_updates" and ev.key
                    and ev.key.upper() in caught_names):
                fc = "true"
            raw_part = f" raw={ev.raw!r}" if ev.raw is not None else ""
            log.info(
                f"  [SCORER-SCHEMA-WOULD-COERCE] field={ev.top_field}"
                f"{('.' + ev.key) if ev.key and ev.top_field == 'team_assignment' else ''}"
                f"{('.' + ev.scalar_subfield) if ev.scalar_subfield else ''} "
                f"reason={ev.reason}{raw_part} "
                f"filter_caught_in_step3={fc} frame=F{frame}"
            )


def normalize_batter_row_for_test(key: str, row: dict) -> Tuple[Optional[dict], Optional[str]]:
    """Test hook: single-row batter validation."""
    return _validate_batter_row(key, row)
