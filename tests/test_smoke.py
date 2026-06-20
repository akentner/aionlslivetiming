"""Smoke tests for the aionlslivetiming package skeleton.

These run as plain synchronous ``pytest`` tests; no event loop is required.
They verify the four Phase 1 must-haves related to packaging:

1. The package imports and ``__version__`` is set.
2. All six channel ID constants match the reverse-engineered values.
3. The ``src/`` tree contains no ``homeassistant.*`` imports (D-11).
4. The ``py.typed`` PEP 561 marker is shipped.
"""

from __future__ import annotations

import pathlib

import aionlslivetiming
from aionlslivetiming.parser import (
    EVENT_PID_PER_CAR_LAPS,
    EVENT_PID_QUALIFYING,
    EVENT_PID_RACE_MESSAGE,
    EVENT_PID_RESULT,
    EVENT_PID_STATISTICS,
    EVENT_PID_TRACK_STATE,
)


def test_package_imports() -> None:
    """``import aionlslivetiming`` succeeds and ``__version__`` is set."""
    assert aionlslivetiming.__version__ == "0.1.0"


def test_channel_constants() -> None:
    """The six channel ID constants match the reverse-engineered values."""
    assert EVENT_PID_RESULT == 0
    assert EVENT_PID_RACE_MESSAGE == 3
    assert EVENT_PID_TRACK_STATE == 4
    assert EVENT_PID_PER_CAR_LAPS == 7
    assert EVENT_PID_QUALIFYING == 501
    assert EVENT_PID_STATISTICS == 9002


def test_no_homeassistant_imports() -> None:
    """No source file under ``src/aionlslivetiming/`` may import homeassistant."""
    src_root = pathlib.Path(__file__).resolve().parent.parent / "src" / "aionlslivetiming"
    py_files = list(src_root.rglob("*.py"))
    assert py_files, "no Python files found under src/aionlslivetiming"

    offending: list[tuple[pathlib.Path, int, str]] = []
    for path in py_files:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if "homeassistant" in line:
                offending.append((path, lineno, line))

    assert not offending, (
        "homeassistant.* imports are forbidden in src/ (D-11): "
        + "\n".join(f"{p}:{n}: {line!r}" for p, n, line in offending)
    )


def test_py_typed_present() -> None:
    """``py.typed`` PEP 561 marker must be present in the installed package."""
    pkg_dir = pathlib.Path(aionlslivetiming.__file__).parent
    marker = pkg_dir / "py.typed"
    assert marker.exists(), f"py.typed missing at {marker}"
    # Empty file is the canonical PEP 561 marker; assert it really is empty.
    assert marker.read_text(encoding="utf-8") == "", "py.typed must be empty"
