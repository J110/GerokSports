"""WS-Q step-2a foundation tests — canonical score API + flag gate.

Validates sm.set_score storage + flag-gated @property branch at
USE_SM_CANONICAL_SCORE foundation layer. Behavior at flag=0 must be
identical to pre-step-2a (zero behavior change at default).

Q-1: flag=0 default - sm.set_score is no-op for production path; sm.score
     still reads from sb._inn["score"] as before.
Q-2: flag=1 + set_score called - _canonical_score updated; @property
     reads from new store; sb._inn["score"] also synced (parallel write).
Q-3: flag=1 + set_score NOT called yet - @property falls back to
     sb._inn["score"]; no spurious nulls.
Q-4: API contract - set_score returns commit success/failure (caller
     observability for step-2c regression-rejection move).
"""
from __future__ import annotations

import pytest

import score_manager as sm_module
from score_manager import ScoreManager


class _FakeScoreboard:
    def __init__(self):
        self._inn: dict = {"score": None, "wickets": 0}
        self._set_calls: list[tuple] = []
        self._set_ok: bool = True

    def set(self, field, value, frame):
        self._set_calls.append((field, value, frame))
        if self._set_ok:
            self._inn[field] = value
        return self._set_ok


def _make_sm(monkeypatch, *, flag: bool, attach_sb: bool = True,
             sb_seed: int | None = 7):
    monkeypatch.setattr(sm_module, "USE_SM_CANONICAL_SCORE", flag)
    sm = ScoreManager(shadow=False)
    if attach_sb:
        sm.scoreboard = _FakeScoreboard()
        sm.scoreboard._inn["score"] = sb_seed
    return sm


def test_q1_flag_off_default_set_score_noop_for_production(monkeypatch):
    sm = _make_sm(monkeypatch, flag=False)
    pre_calls = list(sm.scoreboard._set_calls)
    rc = sm.set_score(11, confidence=0.9, source="test")
    assert rc is True
    assert sm.scoreboard._set_calls == pre_calls
    assert sm.score == 7
    assert sm._canonical_score == 11


def test_q2_flag_on_set_score_updates_canonical_and_syncs_sb(monkeypatch):
    sm = _make_sm(monkeypatch, flag=True)
    rc = sm.set_score(11, confidence=0.9, source="test")
    assert rc is True
    assert sm._canonical_score == 11
    assert sm.score == 11
    assert sm.scoreboard._set_calls == [("score", 11, 0)]
    assert sm.scoreboard._inn["score"] == 11


def test_q3_flag_on_no_set_score_yet_property_falls_back_to_sb(monkeypatch):
    sm = _make_sm(monkeypatch, flag=True)
    assert sm._canonical_score is None
    assert sm.score == 7


def test_q4_set_score_returns_commit_outcome(monkeypatch):
    sm = _make_sm(monkeypatch, flag=True)
    sm.scoreboard._set_ok = False
    rc = sm.set_score(11, confidence=0.9, source="test")
    assert rc is False
    assert sm._canonical_score == 11

    sm2 = _make_sm(monkeypatch, flag=False, attach_sb=False)
    rc2 = sm2.set_score(11, confidence=0.9, source="test")
    assert rc2 is True
    assert sm2._canonical_score == 11


def test_q4b_set_score_rejects_invalid_value(monkeypatch):
    sm = _make_sm(monkeypatch, flag=True)
    rc = sm.set_score("not-an-int", confidence=0.9, source="test")  # type: ignore[arg-type]
    assert rc is False
    assert sm._canonical_score is None
