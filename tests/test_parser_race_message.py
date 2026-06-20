"""PID 3 (race message) parser specifics.

The race-message channel carries pit notices, flag declarations, and
penalty decisions. ``startingNo``/``session`` are optional because
sector-level flags apply to no specific car.
"""

from __future__ import annotations

from aionlslivetiming.events import RaceMessage
from aionlslivetiming.parser.race_message import parse_pid_3


def test_pit_message() -> None:
    """A PIT message has text, category, starting_no, and session populated."""
    raw = {"eventPid": 3, "text": "Car #7 in pits", "type": "PIT", "startingNo": 7, "session": "R1"}
    msg = parse_pid_3(raw)
    assert isinstance(msg, RaceMessage)
    assert msg.text == "Car #7 in pits"
    assert msg.category == "PIT"
    assert msg.starting_no == 7
    assert msg.session == "R1"


def test_flag_message() -> None:
    """A FLAG message has category but no startingNo (sector-level)."""
    raw = {"eventPid": 3, "text": "Yellow flag sector 3", "type": "FLAG", "sector": 3}
    msg = parse_pid_3(raw)
    assert msg.category == "FLAG"
    assert msg.starting_no is None
    assert msg.session is None
    # sector preserved in raw
    assert msg.raw["sector"] == 3


def test_minimal_message() -> None:
    """An empty dict parses to category='INFO' and starting_no/session None (D-03)."""
    msg = parse_pid_3({})
    assert msg.category == "INFO"
    assert msg.text == ""
    assert msg.starting_no is None
    assert msg.session is None


def test_starting_no_string_is_cast_to_int() -> None:
    """A string ``startingNo`` is cast to int (the server occasionally sends strings)."""
    raw = {"eventPid": 3, "text": "x", "type": "INFO", "startingNo": "42"}
    msg = parse_pid_3(raw)
    assert msg.starting_no == 42


def test_starting_no_non_numeric_falls_back_to_none() -> None:
    """A non-numeric ``startingNo`` falls back to None (D-03)."""
    raw = {"eventPid": 3, "text": "x", "type": "INFO", "startingNo": "junk"}
    msg = parse_pid_3(raw)
    assert msg.starting_no is None
