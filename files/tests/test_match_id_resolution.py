"""D9 squad-URL parametrization tests.

Target: test_pipeline.py:_resolve_match_id (CRICBUZZ_MATCH_ID env >
--match-id CLI arg > hardcoded default with WARN log).

Run from repo root:
    pytest files/tests/test_match_id_resolution.py -q
"""
from __future__ import annotations

import importlib
import logging
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _reload_pipeline():
    if "test_pipeline" in sys.modules:
        del sys.modules["test_pipeline"]
    return importlib.import_module("test_pipeline")


def _clear_env():
    os.environ.pop("CRICBUZZ_MATCH_ID", None)


def _patch_argv(argv):
    sys.argv = ["test_pipeline.py"] + list(argv)


def test_env_set_resolves_to_env_value(monkeypatch):
    _clear_env()
    _patch_argv([])
    monkeypatch.setenv("CRICBUZZ_MATCH_ID", "999999")
    tp = _reload_pipeline()
    mid, source = tp._resolve_match_id()
    assert mid == "999999"
    assert source == "env:CRICBUZZ_MATCH_ID"


def test_arg_only_resolves_to_arg_value(monkeypatch):
    _clear_env()
    _patch_argv(["--match-id", "888888"])
    tp = _reload_pipeline()
    mid, source = tp._resolve_match_id()
    assert mid == "888888"
    assert source == "arg:--match-id"


def test_arg_equals_form_resolves(monkeypatch):
    _clear_env()
    _patch_argv(["--match-id=777777"])
    tp = _reload_pipeline()
    mid, source = tp._resolve_match_id()
    assert mid == "777777"
    assert source == "arg:--match-id"


def test_env_overrides_arg(monkeypatch):
    _clear_env()
    _patch_argv(["--match-id", "888888"])
    monkeypatch.setenv("CRICBUZZ_MATCH_ID", "999999")
    tp = _reload_pipeline()
    mid, source = tp._resolve_match_id()
    assert mid == "999999"
    assert source == "env:CRICBUZZ_MATCH_ID"


def test_neither_set_falls_back_to_default(monkeypatch):
    _clear_env()
    _patch_argv([])
    tp = _reload_pipeline()
    mid, source = tp._resolve_match_id()
    assert mid == tp.DEFAULT_MATCH_ID
    assert source == "default"


def test_squad_url_uses_resolved_id(monkeypatch):
    _clear_env()
    _patch_argv([])
    monkeypatch.setenv("CRICBUZZ_MATCH_ID", "152075")
    tp = _reload_pipeline()
    assert "/152075/" in tp.SQUAD_URL


def test_default_emits_warn_log(monkeypatch, capsys):
    _clear_env()
    _patch_argv([])
    _reload_pipeline()
    captured = capsys.readouterr()
    assert "[CONFIG] CRICBUZZ_MATCH_ID not set" in (
        captured.out + captured.err)
