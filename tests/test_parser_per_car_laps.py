"""PID 7 (per-car laps) parser specifics.

Per Phase 1 the per-car-laps parser preserves the raw lap dicts
verbatim. Typed lap parsing (per-lap dataclass) is Phase 2.
"""

from __future__ import annotations

from aionlslivetiming.events import PerCarLapsMessage
from aionlslivetiming.parser.per_car_laps import parse_pid_7


def test_two_laps() -> None:
    """Two-lap payload: session, starting_no, and raw lap dicts preserved."""
    raw = {
        "eventPid": 7,
        "session": "R1",
        "startingNo": 7,
        "laps": [
            {"lap": 1, "time": 168200, "s1": 32150, "s2": 58720, "s3": 77330},
            {"lap": 2, "time": 162340, "s1": 31000, "s2": 55000, "s3": 76340},
        ],
    }
    msg = parse_pid_7(raw)
    assert isinstance(msg, PerCarLapsMessage)
    assert msg.session == "R1"
    assert msg.starting_no == 7
    assert len(msg.laps) == 2
    assert msg.laps[0]["lap"] == 1
    assert msg.laps[0]["time"] == 168200


def test_no_laps() -> None:
    """A frame with no ``laps`` key (e.g. car retired notice) parses to ``laps=()``."""
    raw = {"eventPid": 7, "session": "R1", "startingNo": 7}
    msg = parse_pid_7(raw)
    assert msg.laps == ()


def test_session_starting_no_required() -> None:
    """Verify session + starting_no are extracted (both are required)."""
    raw = {"eventPid": 7, "session": "R2", "startingNo": 11, "laps": []}
    msg = parse_pid_7(raw)
    assert msg.session == "R2"
    assert msg.starting_no == 11


def test_starting_no_fallback_to_zero() -> None:
    """A missing or non-numeric ``startingNo`` falls back to 0 (D-03)."""
    raw = {"eventPid": 7, "session": "R1", "startingNo": "junk"}
    msg = parse_pid_7(raw)
    assert msg.starting_no == 0


def test_empty_dict() -> None:
    """An empty dict parses with no raise (D-03)."""
    msg = parse_pid_7({})
    assert msg.starting_no == 0
    assert msg.laps == ()
