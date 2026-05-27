from __future__ import annotations

import importlib

import pytest

import eyes.player_enrichment as player_enrichment


def _raw_squad() -> dict:
    return {
        "team_a": {
            "name": "A",
            "playing_xi": [{"name": "Alpha Batter", "role": "batter"}],
            "bench": [],
        },
        "team_b": {
            "name": "B",
            "playing_xi": [{"name": "Beta Bowler", "role": "bowler"}],
            "bench": [],
        },
    }


@pytest.mark.asyncio
async def test_disable_player_enrichment_llm_uses_fallback_without_client(
        monkeypatch):
    monkeypatch.setenv("DISABLE_PLAYER_ENRICHMENT_LLM", "1")
    module = importlib.reload(player_enrichment)

    def _unexpected_client():
        raise AssertionError("LLM client should not be constructed")

    monkeypatch.setattr(module, "_make_client", _unexpected_client)

    raw_data = _raw_squad()
    styles = await module.enrich_squad_styles(raw_data, use_cache=False)
    pass2 = await module.enrich_squad_styles_pass2_async(raw_data, styles)

    assert styles["Alpha Batter"]["batting_style"] == "unknown"
    assert styles["Alpha Batter"]["bowling_style"] == "None"
    assert styles["Beta Bowler"]["batting_style"] == "unknown"
    assert styles["Beta Bowler"]["bowling_style"] == "unknown"
    assert raw_data["team_a"]["playing_xi"][0]["batting_style"] == "unknown"
    assert pass2 is None

    monkeypatch.delenv("DISABLE_PLAYER_ENRICHMENT_LLM", raising=False)
    importlib.reload(module)
