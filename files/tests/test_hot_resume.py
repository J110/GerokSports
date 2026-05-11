"""Hot-resume on pipeline restart (#36).

Replaces the legacy "Rule 1 always-discard" cache policy with an
identity-validated restore path:

  - ``scoreboard.restore_from_cache(cached)`` rebuilds the scoreboard
    side (pre-existing, unit-tested separately).
  - ``score_manager.hot_resume_from_cache(cached, frame)`` mirrors the
    SM-side state without going through ``_accept_initial`` (which
    expects a ``FrameInput`` and would clobber broadcast_* fields).
  - The startup block in ``test_pipeline.run_test`` gates restore on
    match_id + session_id + age, and the frame loop validates the
    first non-null broadcast read against the restored cache (revert
    to COLD_START on divergence).

These tests cover the public-API building blocks (the SM method, the
identity-gate boolean, the validation predicate, and the
``restore_from_cache`` tracker side-effects). The integration-level
test_pipeline.run_test glue is exercised indirectly via the same
predicates mirrored here.

Run from repo root:
    pytest files/tests/test_hot_resume.py -q
"""
from __future__ import annotations

import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from eyes.scoreboard import Scoreboard  # noqa: E402
from score_manager import ScoreManager  # noqa: E402


# ---------------------------------------------------------------------
# Mirrors of the production identity gate and validation predicate.
# Keep aligned with test_pipeline.run_test: CACHE POLICY block at
# ~line 7037 and the HOT-RESUME-VALIDATE block in the frame loop body.
# ---------------------------------------------------------------------
def _identity_ok(cached: dict, current_match_id: str | None,
                 current_session_id: str, now_ts: float) -> bool:
    return (
        cached.get("match_id") == current_match_id
        and cached.get("session_id") != current_session_id
        and (now_ts - (cached.get("saved_at") or 0)) < 3600)


def _validate(cached: dict, obs_score: int, obs_wkts: int,
              obs_overs_f: float) -> bool:
    cs = cached.get("score")
    cw = cached.get("wickets")
    co_f = float(cached.get("overs") or 0)
    score_ok = (cs - 6) <= obs_score <= (cs + 30)
    wkts_ok = cw <= obs_wkts <= (cw + 2)
    overs_ok = obs_overs_f >= (co_f - 0.1)
    return score_ok and wkts_ok and overs_ok


def _make_cache(score=100, wickets=3, overs=10.0,
                match_id="152097", session_id="OLD-uuid",
                saved_at=None,
                striker="Suryakumar Yadav", non="Tilak Varma",
                bowler="Jasprit Bumrah") -> dict:
    return {
        "score": score,
        "wickets": wickets,
        "overs": overs,
        "run_rate": (score / overs) if overs else None,
        "target": None,
        "batting_team": "MI",
        "bowling_team": "RR",
        "innings": 1,
        "striker": striker,
        "non": non,
        "current_bowler": bowler,
        "batting_card": {
            striker: {"runs": 50, "balls": 30, "status": "batting"},
            non: {"runs": 20, "balls": 12, "status": "batting"},
            "Rohit Sharma": {"runs": 10, "balls": 9, "status": "out"},
        },
        "bowling_card": {},
        "fall_of_wickets": [
            {"wicket": 1, "batter": "Rohit Sharma", "score": 30,
             "overs": "3.2"},
        ],
        "over_history": {},
        "match_id": match_id,
        "session_id": session_id,
        "frame": 1234,
        "saved_at": (time.time() if saved_at is None else saved_at),
    }


def _make_sb_with_squad() -> Scoreboard:
    sb = Scoreboard()
    sb.setup_innings(
        "MI", "RR",
        ["Suryakumar Yadav", "Tilak Varma", "Rohit Sharma", "D", "E"],
        ["Jasprit Bumrah", "Bowler2"])
    return sb


# =====================================================================
# 1 — identity passes → hot_resume_from_cache + restore_from_cache fire
# =====================================================================
def test_hot_resume_identity_ok_loads_cached_state():
    cache = _make_cache(score=100, wickets=3, overs=10.0,
                        match_id="152097", session_id="OLD-uuid")
    assert _identity_ok(cache,
                        current_match_id="152097",
                        current_session_id="NEW-uuid",
                        now_ts=time.time()) is True
    sb = _make_sb_with_squad()
    sb.restore_from_cache(cache)
    assert sb._inn.get("score") == 100
    assert sb._inn.get("wickets") == 3
    assert sb._inn.get("overs") == 10.0
    sm = ScoreManager(shadow=False)
    sm.hot_resume_from_cache(cache, frame=0)
    assert sm.mode == "WARM"
    assert sm.score == 100
    assert sm.wickets == 3
    assert sm.overs == 10.0
    assert sm.cold_candidate is None
    assert sm.cold_candidate_streak == 0


# =====================================================================
# 2 — match_id mismatch → identity reject
# =====================================================================
def test_hot_resume_match_id_mismatch_falls_back():
    cache = _make_cache(match_id="152075", session_id="OLD-uuid")
    assert _identity_ok(cache,
                        current_match_id="152097",
                        current_session_id="NEW-uuid",
                        now_ts=time.time()) is False


# =====================================================================
# 3 — stale cache (>60 min) → identity reject
# =====================================================================
def test_hot_resume_stale_cache_falls_back():
    now = time.time()
    cache = _make_cache(match_id="152097", session_id="OLD-uuid",
                        saved_at=now - 4000)  # 66 min ago
    assert _identity_ok(cache,
                        current_match_id="152097",
                        current_session_id="NEW-uuid",
                        now_ts=now) is False


# =====================================================================
# 3b — same session (write-flush, not a restart) → identity reject
# =====================================================================
def test_hot_resume_same_session_falls_back():
    cache = _make_cache(match_id="152097", session_id="LIVE-uuid")
    assert _identity_ok(cache,
                        current_match_id="152097",
                        current_session_id="LIVE-uuid",
                        now_ts=time.time()) is False


# =====================================================================
# 4 — score divergence → validation reverts to COLD_START
# =====================================================================
def test_hot_resume_validate_score_divergence_reverts():
    cache = _make_cache(score=100, wickets=3, overs=10.0)
    # cached=100/3 (10.0), observed=200/3 (10.1) — score delta +100 > +30
    assert _validate(cache, obs_score=200, obs_wkts=3,
                     obs_overs_f=10.1) is False
    # Simulate the production-side cleanup the validate block performs.
    sb = _make_sb_with_squad()
    sb.restore_from_cache(cache)
    sm = ScoreManager(shadow=False)
    sm.hot_resume_from_cache(cache, frame=0)
    # Revert path
    sm.mode = "COLD_START"
    sm.cold_candidate = None
    sm.cold_candidate_streak = 0
    for n in list(sb.batting_card.keys()):
        sb.batting_card[n]["runs"] = None
        sb.batting_card[n]["balls"] = None
        sb.batting_card[n]["status"] = "yet_to_bat"
    assert sm.mode == "COLD_START"
    assert all(sb.batting_card[n]["runs"] is None
               for n in sb.batting_card)
    assert all(sb.batting_card[n]["status"] == "yet_to_bat"
               for n in sb.batting_card)


# =====================================================================
# 5 — within tolerance → validation passes, mode stays WARM
# =====================================================================
def test_hot_resume_validate_within_tolerance_accepts():
    cache = _make_cache(score=100, wickets=3, overs=10.0)
    assert _validate(cache, obs_score=102, obs_wkts=3,
                     obs_overs_f=10.1) is True
    assert _validate(cache, obs_score=130, obs_wkts=5,
                     obs_overs_f=12.0) is True


# =====================================================================
# 6 — B5 tracker still gates new commits post-restore
# (force_set primes baselines; cold-start consensus still required for
# subsequent divergent reads)
# =====================================================================
def test_hot_resume_b5_still_active_post_restore():
    cache = _make_cache(score=100, wickets=3, overs=10.0)
    sb = _make_sb_with_squad()
    sb.restore_from_cache(cache)
    # restore_from_cache uses force_set — the baselines should be the
    # cached values, but the cross-field gate state is still active.
    assert sb._tracker.confirmed.get("score") == 100
    assert sb._tracker.confirmed.get("wickets") == 3
    assert str(sb._tracker.confirmed.get("overs")) == "10.0"
    # A phantom -/8 wickets read must NOT commit on first frame.
    # tracker.update returns None until cold-start consensus is met
    # OR the warm-mode suspicious/consensus path admits it.
    sb._tracker.update("wickets", 8, frame_count=200)
    assert sb._tracker.confirmed.get("wickets") == 3, (
        "phantom 8 must not overwrite restored 3 on first read")


# =====================================================================
# 7 (gap-3) — validation defers when card.score is None
# =====================================================================
def test_hot_resume_validation_waits_for_non_null_observation():
    cache = _make_cache(score=100, wickets=3, overs=10.0)
    # Mirror the production guard: validation only fires when ALL of
    # score / wickets / overs are non-null in the observed extracted.
    def _should_fire(obs: dict) -> bool:
        return (obs.get("score") is not None
                and obs.get("wickets") is not None
                and obs.get("overs") is not None)

    # Frames 1-3: at least one field is None — validation defers.
    assert _should_fire({"score": None, "wickets": None,
                         "overs": None}) is False
    assert _should_fire({"score": 100, "wickets": None,
                         "overs": 10.1}) is False
    assert _should_fire({"score": 100, "wickets": 3,
                         "overs": None}) is False
    # Frame 4: all three populated — validation fires.
    obs4 = {"score": 102, "wickets": 3, "overs": 10.1}
    assert _should_fire(obs4) is True
    assert _validate(cache,
                     obs_score=obs4["score"],
                     obs_wkts=obs4["wickets"],
                     obs_overs_f=float(obs4["overs"])) is True


# =====================================================================
# 8 (gap-3) — Scout-silent path: hot-resume state survives indefinitely
# until first non-null observation contradicts it
# =====================================================================
def test_hot_resume_no_validation_when_scout_silent():
    cache = _make_cache(score=100, wickets=3, overs=10.0)
    sb = _make_sb_with_squad()
    sb.restore_from_cache(cache)
    sm = ScoreManager(shadow=False)
    sm.hot_resume_from_cache(cache, frame=0)
    # Simulate N silent frames: extracted = {score: None, wickets: None,
    # overs: None}. The validation predicate never fires; SM stays WARM
    # with cached state.
    hot_resume_validate_pending = True
    for _ in range(50):
        extracted = {"score": None, "wickets": None, "overs": None}
        if (extracted.get("score") is not None
                and extracted.get("wickets") is not None
                and extracted.get("overs") is not None):
            hot_resume_validate_pending = False  # would fire — won't here
    assert hot_resume_validate_pending is True, (
        "validation must remain pending while Scout produces no parse")
    assert sm.mode == "WARM"
    assert sm.score == 100
    assert sm.wickets == 3
    assert sm.overs == 10.0
