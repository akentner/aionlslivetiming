"""Pytest configuration and shared fixtures for the aionlslivetiming test suite."""

from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture(autouse=True)
def _reset_parser_warned() -> None:
    """Reset the parser's WARNING-dedupe set before each test.

    Per D-03 the parser logs each unique ``(event_pid, field_name)``
    gap exactly once per process. Without this autouse fixture tests
    would be order-dependent: the first test to trigger a warning
    would silence it for the rest of the run.
    """
    from aionlslivetiming.parser import _helpers

    _helpers.reset_warned()
    yield


pytest_plugins: list[str] = []
