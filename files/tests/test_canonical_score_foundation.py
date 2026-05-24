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


class _CaptureRecorder:
    def __init__(self):
        self.events: list[tuple] = []

    def record(self, *, tag, **kwargs):
        self.events.append((tag, kwargs))


def _install_capture(monkeypatch):
    import trace_emitter
    rec = _CaptureRecorder()
    monkeypatch.setattr(trace_emitter, "get_recorder", lambda: rec)
    return rec


def test_qb1_parity_no_divergence_when_values_match(monkeypatch):
    rec = _install_capture(monkeypatch)
    sm = _make_sm(monkeypatch, flag=False, sb_seed=11)
    rc = sm.set_score(11, confidence=0.9, source="test_parity")
    assert rc is True
    tags = [t for t, _ in rec.events]
    assert "CANONICAL-SCORE-API-INVOKED" in tags
    assert "SM-SHADOW-PARITY-DIVERGENCE" not in tags


def test_qb2_synthetic_divergence_emits_shadow_parity_tag(monkeypatch):
    rec = _install_capture(monkeypatch)
    sm = _make_sm(monkeypatch, flag=False, sb_seed=7)
    rc = sm.set_score(11, confidence=0.9, source="test_divergence")
    assert rc is True
    div = next((kw for t, kw in rec.events
                if t == "SM-SHADOW-PARITY-DIVERGENCE"), None)
    assert div is not None
    assert div["canonical"] == 11
    assert div["sb_value"] == 7
    assert div["source"] == "test_divergence"


def test_qb3_setter_writer_redirect_does_not_break_legacy(monkeypatch):
    rec = _install_capture(monkeypatch)
    sm = _make_sm(monkeypatch, flag=False, sb_seed=7)
    sm.score = 11
    assert sm.scoreboard._set_calls == [("score", 11, 0)]
    assert sm.scoreboard._inn["score"] == 11
    assert sm._canonical_score == 11
    tags = [t for t, _ in rec.events]
    assert "CANONICAL-SCORE-API-INVOKED" in tags
    assert "SM-SHADOW-PARITY-DIVERGENCE" not in tags


def test_qc1_forward_monotonic_writes_accept(monkeypatch):
    rec = _install_capture(monkeypatch)
    sm = _make_sm(monkeypatch, flag=True, sb_seed=10)
    assert sm.set_score(10, confidence=1.0, source="t") is True
    assert sm.set_score(15, confidence=1.0, source="t") is True
    assert sm.set_score(15, confidence=1.0, source="t") is True
    assert sm._canonical_score == 15
    tags = [t for t, _ in rec.events]
    assert "SCORE-REGRESSION-REJECTED-CANONICAL" not in tags
    assert "SCORE-RETROACTIVE-CORRECTION-APPLIED" not in tags


def test_qc2_backward_high_confidence_accepts_retroactive(monkeypatch):
    rec = _install_capture(monkeypatch)
    sm = _make_sm(monkeypatch, flag=True, sb_seed=63)
    sm.set_score(63, confidence=1.0, source="t_seed")
    rc = sm.set_score(43, confidence=1.0, source="setter")
    assert rc is True
    assert sm._canonical_score == 43
    retro = next((kw for t, kw in rec.events
                  if t == "SCORE-RETROACTIVE-CORRECTION-APPLIED"), None)
    assert retro is not None
    assert retro["canonical"] == 43
    assert retro["prior_canonical"] == 63


def test_qc3_backward_low_confidence_rejects(monkeypatch):
    rec = _install_capture(monkeypatch)
    sm = _make_sm(monkeypatch, flag=True, sb_seed=63)
    sm.set_score(63, confidence=1.0, source="t_seed")
    rc = sm.set_score(43, confidence=0.5, source="low_conf")
    assert rc is False
    assert sm._canonical_score == 63
    rej = next((kw for t, kw in rec.events
                if t == "SCORE-REGRESSION-REJECTED-CANONICAL"), None)
    assert rej is not None
    assert rej["reason"] == "confidence_below_threshold"


def test_qc4_innings_reset_clears_canonical(monkeypatch):
    rec = _install_capture(monkeypatch)
    sm = _make_sm(monkeypatch, flag=True, sb_seed=180)
    sm.set_score(180, confidence=1.0, source="t")
    assert sm._canonical_score == 180
    sm.reset_score(source="innings_change")
    assert sm._canonical_score is None
    sm.set_score(0, confidence=1.0, source="innings_2_start")
    assert sm._canonical_score == 0
    reset_evt = next((kw for t, kw in rec.events
                      if t == "CANONICAL-SCORE-RESET-INVOKED"), None)
    assert reset_evt is not None
    assert reset_evt["source"] == "innings_change"


def test_qc5_flag_flip_read_returns_canonical_not_legacy(monkeypatch):
    sm = _make_sm(monkeypatch, flag=True, sb_seed=63)
    sm.set_score(63, confidence=1.0, source="t_seed")
    sm.set_score(43, confidence=1.0, source="setter")
    assert sm._canonical_score == 43
    assert sm.score == 43


def test_qc6_t20_absolute_bound_rejects_hallucination(monkeypatch):
    rec = _install_capture(monkeypatch)
    sm = _make_sm(monkeypatch, flag=True, sb_seed=50)
    sm.set_score(50, confidence=1.0, source="t_seed")
    rc = sm.set_score(500, confidence=1.0, source="hallucination")
    assert rc is False
    assert sm._canonical_score == 50
    rej = next((kw for t, kw in rec.events
                if t == "SCORE-REGRESSION-REJECTED-CANONICAL"
                and kw.get("reason") == "t20_absolute_bound"), None)
    assert rej is not None
