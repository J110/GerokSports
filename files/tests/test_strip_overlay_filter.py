"""P19 strip-overlay sentinel + active-batting pre-filters.

See files/docs/investigations/strip_rows_misaligned_diagnosis.md.
Fixtures derived from the 32 firings logged in
logs/pipeline-2026-05-02-2049-csk-vs-mi-44th-match-ipl-2026-innings2.log.

Run: pytest files/tests/test_strip_overlay_filter.py -q
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from test_pipeline import (  # noqa: E402
    _detect_overlay_strip_sentinels,
    _detect_overlay_via_active_batting,
    apply_strip_overlay_prefilters,
    reset_overlay_lockout_state,
)


def _mk_scoreboard(active: dict[str, dict],
                   resolve_map: dict[str, str] | None = None):
    sb = MagicMock()
    sb.batting_card = active
    rm = {k.upper(): v for k, v in (resolve_map or {}).items()}
    rm.update({k.upper(): k for k in active})

    def _resolve(name: str | None):
        if not name:
            return None
        return rm.get(name.upper().strip())

    sb.resolve_name.side_effect = _resolve
    return sb


def _record(family, proposed_reset=None):
    _record.calls.append((family, list(proposed_reset or [])))


def _reset_recorder():
    _record.calls = []


_reset_recorder()


# ─── Sentinel detector unit tests ───────────────────────────────────


def test_sentinel_run_rate_speed_kph() -> None:
    text = ("MI 134-4 (16.4) | Naman > Hardik | 57 36 | 10 15 | "
            "RUN-RATE 8.04 | SPEED 123.8 kph | 2 1 1 6")
    assert _detect_overlay_strip_sentinels(text) is not None


def test_sentinel_career_qualifier_in_t20() -> None:
    assert _detect_overlay_strip_sentinels(
        "Samson 84 IN T20 vs MI") is not None


def test_sentinel_returns_none_on_clean_strip() -> None:
    text = "MI 122-4 (15.3) | Naman Dhir 12(9) | Hardik Pandya 49(37)"
    assert _detect_overlay_strip_sentinels(text) is None


def test_sentinel_env_override(monkeypatch) -> None:
    monkeypatch.setenv("STRIP_OVERLAY_SENTINELS", "ZZZONLY")
    assert _detect_overlay_strip_sentinels(
        "MI 134-4 RUN-RATE 8.04") is None
    assert _detect_overlay_strip_sentinels("ZZZONLY appears") == "ZZZONLY"


# ─── Active-batting membership tests ────────────────────────────────


def test_active_batting_neither_resolves_returns_true() -> None:
    sb = _mk_scoreboard(
        {"Naman Dhir": {"status": "batting"},
         "Hardik Pandya": {"status": "batting"}})
    assert _detect_overlay_via_active_batting(
        [{"name": "Tilak Varma"}, {"name": "Suryakumar"}], sb,
        cam="graphic")


def test_active_batting_one_resolves_returns_false() -> None:
    sb = _mk_scoreboard(
        {"Naman Dhir": {"status": "batting"},
         "Hardik Pandya": {"status": "batting"}},
        resolve_map={"DHIR": "Naman Dhir"})
    assert not _detect_overlay_via_active_batting(
        [{"name": "Dhir"}, {"name": "Suryakumar"}], sb,
        cam="graphic")


def test_active_batting_skips_when_no_active() -> None:
    sb = _mk_scoreboard({})
    assert not _detect_overlay_via_active_batting(
        [{"name": "Tilak Varma"}], sb, cam="graphic")


# ─── End-to-end pre-filter wiring (8 representative fixtures) ───────


def _mk_csk_mi_scoreboard():
    return _mk_scoreboard(
        {"Naman Dhir": {"status": "batting"},
         "Hardik Pandya": {"status": "batting"}},
        resolve_map={
            "NAMAN": "Naman Dhir",
            "DHIR": "Naman Dhir",
            "HARDIK": "Hardik Pandya",
            "PANDYA": "Hardik Pandya",
        })


def _run(extracted, sb, text, *, frame=0, cam="graphic", frame_class=None,
         reset_lockout=True):
    _reset_recorder()
    if reset_lockout:
        reset_overlay_lockout_state()
    return apply_strip_overlay_prefilters(
        extracted, sb, text,
        frame_count=frame,
        record_state_recovery_guard=_record,
        cam=cam,
        frame_class=frame_class)


def test_f11_label_swap_falls_through_to_row_pair_guard() -> None:
    """F11: 'MI 118-4 (14.4) | Hardik 45(30) | Naman 7(9)' — names
    swapped but both resolve into active_batting; sentinel filter has
    no signal either. Pre-filter should NOT pop; row-pair guard handles."""
    extracted = {"batters": [
        {"name": "Hardik", "runs": 45, "balls": 30},
        {"name": "Naman", "runs": 7, "balls": 9},
    ]}
    sb = _mk_csk_mi_scoreboard()
    text = "MI 118-4 (14.4) | Hardik 45(30) | Naman 7(9)"
    assert not _run(extracted, sb, text, frame=11)
    assert "batters" in extracted


def test_f45_phantom_score_caught_by_active_batting() -> None:
    """F45: 'null 49-3 (5.5) | *Dhir 21(19) | Pandya 28(20) | Ghosh ...'
    Dhir resolves, so this falls through pre-filters (one batter
    matches). Confirm pre-filter does NOT pop."""
    extracted = {"batters": [
        {"name": "Dhir", "runs": 21, "balls": 19},
        {"name": "Pandya", "runs": 28, "balls": 20},
    ]}
    sb = _mk_csk_mi_scoreboard()
    text = "null 49-3 (5.5) | *Dhir 21(19) | Pandya 28(20) | Ghosh 0-8 (2)"
    assert not _run(extracted, sb, text)


def test_f67_tilak_varma_caught_by_active_batting() -> None:
    """F67: 'NOOR AHMAD ... NAMAN DHIR 4(12) | TILAK VARMA 5(7)'.
    Naman resolves; one match means pre-filter does not pop. The row-
    pair guard then catches the runs delta."""
    extracted = {"batters": [
        {"name": "NAMAN DHIR", "runs": 4, "balls": 12},
        {"name": "TILAK VARMA", "runs": 5, "balls": 7},
    ]}
    sb = _mk_csk_mi_scoreboard()
    text = ("null 12-4 (null) | NAMAN DHIR 4(12) | TILAK VARMA 5(7) | "
            "NOOR AHMAD 2-24 (3.2)")
    assert not _run(extracted, sb, text)


def test_f67_neither_resolves_caught_by_active_batting() -> None:
    """F67-variant: neither strip batter resolves to active set."""
    extracted = {"batters": [
        {"name": "TILAK VARMA", "runs": 5, "balls": 7},
        {"name": "SURYAKUMAR", "runs": 0, "balls": 0},
    ]}
    sb = _mk_csk_mi_scoreboard()
    text = "null 12-4 (null) | TILAK VARMA 5(7) | SURYAKUMAR 0(0)"
    assert _run(extracted, sb, text)
    assert "batters" not in extracted
    assert _record.calls == [
        ("batter_row_rejected", ["bat:not_in_active_batting"])]


def test_f241_run_rate_speed_caught_by_sentinel() -> None:
    """F241: head-to-head comparison overlay with RUN-RATE / SPEED /
    kph. Sentinel filter must catch this regardless of name match."""
    extracted = {"batters": [
        {"name": "Naman", "runs": 57, "balls": 36},
        {"name": "Hardik", "runs": 10, "balls": 15},
    ]}
    sb = _mk_csk_mi_scoreboard()
    text = ("MI 134-4 (16.4) | Naman > Hardik | 57 36 | 10 15 | "
            "RUN-RATE 8.04 | SPEED 123.8 kph | 2 1 1 6")
    assert _run(extracted, sb, text, frame=241)
    assert "batters" not in extracted
    assert _record.calls and _record.calls[0][0] == "batter_row_rejected"


def test_f351_krish_caught_by_active_batting() -> None:
    """F351: live state is Krish Bhagat 0(1); strip names Krish (not
    in active set) and Hardik. Hardik IS active → falls through."""
    sb = _mk_scoreboard(
        {"Krish Bhagat": {"status": "batting"},
         "Hardik Pandya": {"status": "batting"}},
        resolve_map={"HARDIK PANDYA": "Hardik Pandya",
                     "KRISH BHAGAT": "Krish Bhagat"})
    extracted = {"batters": [
        {"name": "Hardik Pandya", "runs": 24, "balls": 15},
        {"name": "Krish Bhagat", "runs": 23, "balls": 20},
    ]}
    text = ("null 49-3 | this_over=◉◉◉◉◉. | *Hardik Pandya 24(15) | "
            "Krish Bhagat 23(20)")
    assert not _run(extracted, sb, text, frame=351)


def test_f438_hardik_142_no_sentinel_falls_through() -> None:
    """F438: 'MI 146-6 (19) | Krish 3(5) | Hardik 142(20)' — names
    resolve, no sentinel; pre-filter does not pop. Row-pair guard
    catches Δ=131."""
    sb = _mk_scoreboard(
        {"Hardik Pandya": {"status": "batting"},
         "Krish Bhagat": {"status": "batting"}},
        resolve_map={"HARDIK": "Hardik Pandya", "KRISH": "Krish Bhagat"})
    extracted = {"batters": [
        {"name": "Krish", "runs": 3, "balls": 5},
        {"name": "Hardik", "runs": 142, "balls": 20},
    ]}
    text = "MI 146-6 (19) | Krish 3(5) | Hardik 142(20) | null null-null"
    assert not _run(extracted, sb, text, frame=438)


def test_f841_in_t20_caught_by_sentinel() -> None:
    """F841: career-stat overlay with 'IN T20' qualifier — sentinel
    keyword catches it."""
    sb = _mk_scoreboard(
        {"Sanju Samson": {"status": "batting"},
         "Ruturaj Gaikwad": {"status": "batting"}},
        resolve_map={"SAMSON": "Sanju Samson",
                     "GAIKWAD": "Ruturaj Gaikwad"})
    extracted = {"batters": [
        {"name": "Samson", "runs": 84, "balls": 14},
        {"name": "Gaikwad", "runs": 0, "balls": 0},
    ]}
    text = ("CSK 7-0 (1) | Samson 84(14) | Gaikwad null | "
            "Bumrah 0-7 (1) IN T20")
    assert _run(extracted, sb, text, frame=841)
    assert "batters" not in extracted
    assert _record.calls and _record.calls[0][0] == "batter_row_rejected"


def test_f853_phantom_score_caught_by_active_batting() -> None:
    """F853: 'null 77-5 (9.5) | SAMSON 38(29) | GAIKWAD 21(20)'.
    Both names resolve, no sentinel. Pre-filter does NOT pop; row-pair
    guard handles via runs delta."""
    sb = _mk_scoreboard(
        {"Sanju Samson": {"status": "batting"},
         "Ruturaj Gaikwad": {"status": "batting"}},
        resolve_map={"SAMSON": "Sanju Samson",
                     "GAIKWAD": "Ruturaj Gaikwad"})
    extracted = {"batters": [
        {"name": "SAMSON", "runs": 38, "balls": 29},
        {"name": "GAIKWAD", "runs": 21, "balls": 20},
    ]}
    text = ("null 77-5 (9.5) | SAMSON 38(29) | GAIKWAD 21(20) | "
            "BUMRAH 1-16 (4)")
    assert not _run(extracted, sb, text, frame=853)


def test_empty_batters_returns_false() -> None:
    sb = _mk_csk_mi_scoreboard()
    assert not _run({}, sb, "anything")
    assert not _run({"batters": []}, sb, "anything")


def test_record_called_with_correct_reason_for_sentinel() -> None:
    sb = _mk_csk_mi_scoreboard()
    extracted = {"batters": [{"name": "X", "runs": 1, "balls": 1}]}
    _run(extracted, sb, "RUN-RATE 8.04")
    assert _record.calls == [
        ("batter_row_rejected", ["bat:overlay_sentinel"])]


# ─── Batch G: secondary-cue gating + K=3 lockout breakout ───────────


def _mk_pbks_lockout_scoreboard():
    """Mirror tonight's GT-PBKS F132+ state: active = {Stoinis} (stale
    after bug A's UN-DISMISS), strip names Vyshak + Jansen.  Resolve
    map covers all three names so the detector reaches the active-set
    membership comparison."""
    return _mk_scoreboard(
        {"Marcus Stoinis": {"status": "batting"}},
        resolve_map={
            "MARCUS STOINIS": "Marcus Stoinis",
            "STOINIS": "Marcus Stoinis",
            "VIJAYKUMAR VYSHAK": "Vijaykumar Vyshak",
            "VYSHAK": "Vijaykumar Vyshak",
            "MARCO JANSEN": "Marco Jansen",
            "JANSEN": "Marco Jansen",
        })


def test_overlay_detector_requires_secondary_cue() -> None:
    """GT-PBKS F132 reproduction: stale active = {Stoinis}, real strip
    [Vyshak, Jansen], frame_class=SCOREBOARD, cam=closeup.  Without a
    secondary cue, active-batting mismatch alone must NOT classify as
    overlay (otherwise the post-wicket lockout fires)."""
    sb = _mk_pbks_lockout_scoreboard()
    assert not _detect_overlay_via_active_batting(
        [{"name": "Vijaykumar Vyshak"}, {"name": "Marco Jansen"}],
        sb,
        frame_class="SCOREBOARD",
        cam="closeup")


def test_overlay_detector_fires_with_secondary_cue() -> None:
    """Same active/strip pair, but cam=graphic + frame_class=GRAPHIC
    supplies the secondary cue, so the detector fires normally."""
    sb = _mk_pbks_lockout_scoreboard()
    assert _detect_overlay_via_active_batting(
        [{"name": "Vijaykumar Vyshak"}, {"name": "Marco Jansen"}],
        sb,
        frame_class="GRAPHIC",
        cam="graphic")


def test_overlay_lockout_breakout_K3() -> None:
    """Active = {Stoinis} (stale), strip = [Vyshak, Jansen], cam=graphic
    so the active-batting branch fires.  Frames 1-2 pop; frame 3
    triggers OVERLAY-LOCKOUT-BREAKOUT and lets the strip through."""
    sb = _mk_pbks_lockout_scoreboard()
    reset_overlay_lockout_state()
    for _ in range(2):
        extracted = {"batters": [
            {"name": "Vijaykumar Vyshak", "runs": 0, "balls": 1},
            {"name": "Marco Jansen", "runs": 2, "balls": 2},
        ]}
        assert _run(extracted, sb, "any text",
                    cam="graphic", reset_lockout=False)
        assert "batters" not in extracted
    extracted = {"batters": [
        {"name": "Vijaykumar Vyshak", "runs": 0, "balls": 1},
        {"name": "Marco Jansen", "runs": 2, "balls": 2},
    ]}
    assert not _run(extracted, sb, "any text",
                    cam="graphic", reset_lockout=False)
    assert "batters" in extracted


def test_overlay_lockout_counter_resets_on_change() -> None:
    """Two consecutive identical rejections (counter=2), then an
    intervening rejection with a DIFFERENT strip pair must restart the
    counter at 1.  When the original pair re-appears, it must again
    start at 1 — i.e. the original streak is forgotten."""
    sb = _mk_scoreboard(
        {"Marcus Stoinis": {"status": "batting"}},
        resolve_map={
            "STOINIS": "Marcus Stoinis",
            "MARCUS STOINIS": "Marcus Stoinis",
            "VYSHAK": "Vijaykumar Vyshak",
            "VIJAYKUMAR VYSHAK": "Vijaykumar Vyshak",
            "JANSEN": "Marco Jansen",
            "MARCO JANSEN": "Marco Jansen",
            "BARTLETT": "Xavier Bartlett",
            "XAVIER BARTLETT": "Xavier Bartlett",
            "ARSHAD": "Arshad Khan",
        })
    reset_overlay_lockout_state()

    pair_a = [{"name": "Vijaykumar Vyshak"}, {"name": "Marco Jansen"}]
    pair_b = [{"name": "Xavier Bartlett"}, {"name": "Arshad Khan"}]

    # Two pair_A rejections — counter advances to 2, both pop.
    for _ in range(2):
        ext = {"batters": list(pair_a)}
        assert _run(ext, sb, "any text",
                    cam="graphic", reset_lockout=False)
        assert "batters" not in ext

    # Different pair — pop, counter restarts at 1 (tracking pair_B).
    ext = {"batters": list(pair_b)}
    assert _run(ext, sb, "any text",
                cam="graphic", reset_lockout=False)
    assert "batters" not in ext

    # Original pair_A returns — counter restarts at 1 (NOT 3); must pop
    # rather than triggering breakout.
    ext = {"batters": list(pair_a)}
    assert _run(ext, sb, "any text",
                cam="graphic", reset_lockout=False)
    assert "batters" not in ext

    from test_pipeline import _overlay_lockout_state
    assert _overlay_lockout_state["consecutive"] == 1
