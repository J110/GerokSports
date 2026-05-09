"""Pytest hooks for `test_recent_fixes.py` (optional dev path).

The primary runner remains `python test_recent_fixes.py`.  When using
`pytest`, tests marked `requires_groq` are skipped unless `--run-groq`.
"""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "requires_groq: needs groq package with client constructible from API key",
    )


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-groq",
        action="store_true",
        default=False,
        help="Run tests that require the Groq SDK (requires_groq marker)",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list) -> None:
    if config.getoption("--run-groq"):
        return
    skip = pytest.mark.skip(
        reason="Groq SDK test (install groq + key, then: pytest --run-groq)",
    )
    for item in items:
        if "requires_groq" in item.keywords:
            item.add_marker(skip)
