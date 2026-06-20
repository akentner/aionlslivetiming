"""PID 0 (initial state) parser specifics.

The InitialState parser is the most complex of the 8: it carries a
nested session info, a result table, a best-sector table, and the
LTS_NOT_FOUND flag. These tests cover the off-happy-path branches
that the dispatcher-level tests do not exercise directly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aionlslivetiming.events import InitialStateMessage
from aionlslivetiming.events.common import BestSector, CarResult, SessionInfo
from aionlslivetiming.parser.initial_state import parse_pid_0

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "messages"


def load(name: str) -> dict[str, Any]:
    """Load and JSON-parse a fixture file by name (no .json suffix)."""
    return json.loads((FIXTURES / f"{name}.json").read_text())


def test_lts_not_found_branch() -> None:
    """``LTS_NOT_FOUND: true`` → ``lts_not_found=True`` on the message."""
    raw = load("pid_0_lts_not_found")
    msg = parse_pid_0(raw)
    assert isinstance(msg, InitialStateMessage)
    assert msg.event_pid == 0
    assert msg.lts_not_found is True
    # No RESULT/BEST → empty tuples, no raise
    assert msg.results == ()
    assert msg.best_sectors == ()
    # raw preserved
    assert msg.raw["LTS_NOT_FOUND"] is True


def test_missing_result_branch() -> None:
    """A PID 0 frame without RESULT or BEST keys parses to empty tuples."""
    raw = {
        "eventPid": 0,
        "PID": 1,
        "VER": "1.0",
        "EXPORTID": "x",
        "TRACKNAME": "NLS",
        "SESSION": "R1",
    }
    msg = parse_pid_0(raw)
    assert msg.results == ()
    assert msg.best_sectors == ()
    assert msg.track_name == "NLS"
    assert msg.session.session == "R1"


def test_unknown_field_preserved_in_raw() -> None:
    """Server fields the parser does not know are preserved in ``raw`` (PARSE-03)."""
    raw = {
        "eventPid": 0,
        "PID": 1,
        "VER": "1.0",
        "EXPORTID": "x",
        "TRACKNAME": "NLS",
        "SESSION": "R1",
        "futureField": "data",
        "anotherNewField": 42,
    }
    msg = parse_pid_0(raw)
    assert msg.raw["futureField"] == "data"
    assert msg.raw["anotherNewField"] == 42


def test_session_info_extraction() -> None:
    """SESSION, CUP, HEAT, HEATTYPE all flow into the SessionInfo subfield."""
    raw = load("pid_0_initial")
    msg = parse_pid_0(raw)
    assert msg.session.session == "R1"
    assert msg.session.cup == "NLS"
    assert msg.session.heat == "1"
    assert msg.session.heat_type == "R"
    assert msg.session.event_id == "abc-123"


def test_best_sectors_extraction() -> None:
    """The ``BEST`` array maps to BestSector entries with sector + value_ms."""
    raw = load("pid_0_initial")
    msg = parse_pid_0(raw)
    assert len(msg.best_sectors) == 2
    assert msg.best_sectors[0].sector == 1
    assert msg.best_sectors[0].value_ms == 32150
    assert msg.best_sectors[0].driver == "M. Müller"


def test_results_extraction_full() -> None:
    """The ``RESULT`` array maps to CarResult entries with all sub-fields."""
    raw = load("pid_0_initial")
    msg = parse_pid_0(raw)
    assert len(msg.results) == 2
    assert msg.results[0].starting_no == 7
    assert msg.results[0].position == 1
    assert msg.results[0].class_name == "SP9"
    assert msg.results[0].driver == "M. Müller"
    assert msg.results[0].laps == 28
    assert msg.results[0].total_time_ms == 7200000
    assert msg.results[0].gap_to_leader_ms == 0
    assert msg.results[0].best_lap_ms == 162340
    assert msg.results[1].position == 2
    assert msg.results[1].gap_to_leader_ms == 5421


def test_empty_dict_does_not_raise() -> None:
    """An empty dict parses to a valid message with safe defaults (D-03)."""
    msg = parse_pid_0({})
    assert isinstance(msg, InitialStateMessage)
    assert msg.event_pid == 0
    assert msg.results == ()
    assert msg.best_sectors == ()
    assert msg.lts_not_found is False


def test_typed_inputs_match_event_class() -> None:
    """Sanity check: constructing the same Message directly round-trips fields."""
    msg = InitialStateMessage(
        pid=12345,
        ver="1.0",
        export_id="abc",
        track_name="NLS",
        session=SessionInfo(
            session="R1",
            cup="NLS",
            heat="1",
            heat_type="R",
            event_id="abc",
        ),
        results=(
            CarResult(
                starting_no=7,
                position=1,
                class_name="SP9",
                driver="M. Müller",
                laps=28,
                total_time_ms=7200000,
                best_lap_ms=162340,
            ),
        ),
        best_sectors=(
            BestSector(starting_no=7, sector=1, value_ms=32150, driver="M. Müller"),
        ),
        raw={},
    )
    assert msg.results[0].driver == "M. Müller"
    assert msg.best_sectors[0].value_ms == 32150
