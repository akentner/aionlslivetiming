"""PID 9002 (statistics) parser specifics.

Three independent sub-tables: ``LEADING`` (CarResult rows), ``BEST_LAPS``
(CarResult rows), and ``BEST_SECTORS`` (BestSector rows). Any of the
three may be absent and the parser must still return a valid
StatisticsMessage.
"""

from __future__ import annotations

from aionlslivetiming.events import StatisticsMessage
from aionlslivetiming.parser.statistics import parse_pid_9002


def test_leading_best_laps_best_sectors() -> None:
    """All three sub-tables populated: leading + best_laps + best_sectors."""
    raw = {
        "eventPid": 9002,
        "LEADING": [
            {
                "startingNo": 7,
                "position": 1,
                "class": "SP9",
                "driver": "M. Müller",
                "laps": 28,
                "best": 162340,
            }
        ],
        "BEST_LAPS": [
            {
                "startingNo": 7,
                "position": 1,
                "class": "SP9",
                "driver": "M. Müller",
                "laps": 28,
                "best": 162340,
            }
        ],
        "BEST_SECTORS": [
            {"startingNo": 11, "sector": 1, "value": 31800, "driver": "F. Schmidt"}
        ],
    }
    msg = parse_pid_9002(raw)
    assert isinstance(msg, StatisticsMessage)
    assert len(msg.leading) == 1
    assert msg.leading[0].starting_no == 7
    assert len(msg.best_laps) == 1
    assert len(msg.best_sectors) == 1
    assert msg.best_sectors[0].sector == 1
    assert msg.best_sectors[0].value_ms == 31800


def test_all_three_tables_absent() -> None:
    """A frame with no sub-tables parses to empty tuples (D-03)."""
    msg = parse_pid_9002({})
    assert msg.leading == ()
    assert msg.best_laps == ()
    assert msg.best_sectors == ()


def test_only_leading() -> None:
    """Only ``LEADING`` is present: best_laps and best_sectors are empty."""
    raw = {
        "eventPid": 9002,
        "LEADING": [
            {
                "startingNo": 7,
                "position": 1,
                "class": "SP9",
                "driver": "x",
                "laps": 5,
                "best": 1,
            }
        ],
    }
    msg = parse_pid_9002(raw)
    assert len(msg.leading) == 1
    assert msg.best_laps == ()
    assert msg.best_sectors == ()
