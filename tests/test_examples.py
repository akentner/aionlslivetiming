"""Tests for the worked examples (DOC-05).

Each test invokes the example's ``main()`` in-process and captures stdout.
No network access — ``live_quickstart.py`` is tested via its ``--dry-run``
mode, and ``replay_offline.py`` / ``filter_walkthrough.py`` are exercised
against the bundled sample JSONL fixture.
"""

from __future__ import annotations

import json
import pathlib
import sys

import pytest

# Add the examples/ directory to sys.path so the test can import them as
# modules. The examples are scripts, not part of the installed package.
ROOT = pathlib.Path(__file__).resolve().parent.parent
EXAMPLES_DIR = ROOT / "examples"
sys.path.insert(0, str(EXAMPLES_DIR))

from filter_walkthrough import main as filter_main  # noqa: E402
from live_quickstart import main as live_main  # noqa: E402
from replay_offline import main as replay_main  # noqa: E402

EXAMPLE_JSONL = ROOT / "tests" / "fixtures" / "example_messages.jsonl"
SAMPLE_JSONL = ROOT / "examples" / "data" / "sample_event.jsonl"


def test_live_quickstart_dry_run(capsys: pytest.CaptureFixture[str]) -> None:
    """``--dry-run`` uses the bundled sample; no network access."""
    rc = live_main(["--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Dry run:" in out
    assert "messages" in out
    assert "cars" in out


def test_live_quickstart_help(capsys: pytest.CaptureFixture[str]) -> None:
    """``--help`` prints the usage with ``--dry-run`` and ``--duration-s`` options."""
    with pytest.raises(SystemExit) as exc:
        live_main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "--dry-run" in out
    assert "--duration-s" in out


def test_replay_offline_with_sample_jsonl(capsys: pytest.CaptureFixture[str]) -> None:
    """Replay against the bundled sample JSONL; source=REPLAY."""
    rc = replay_main([str(EXAMPLE_JSONL)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Replay:" in out
    assert str(EXAMPLE_JSONL) in out
    assert "source=REPLAY" in out


def test_replay_offline_file_not_found(capsys: pytest.CaptureFixture[str]) -> None:
    """Missing file → exit code 2 and a not-found message on stderr."""
    rc = replay_main(["/nonexistent/path.jsonl"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "not found" in err.lower() or "No such file" in err


def test_filter_walkthrough_runs_against_sample(capsys: pytest.CaptureFixture[str]) -> None:
    """Filter walkthrough exercises all 6 filter dimensions against the sample."""
    rc = filter_main([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Filter walkthrough" in out
    assert "by_class" in out
    assert "by_starting_no" in out
    assert "by_driver" in out
    assert "by_position" in out
    assert "by_lap" in out
    assert "by_sector_time_lt" in out


def test_example_jsonl_is_valid_jsonl() -> None:
    """The sample JSONL must parse as one-JSON-object-per-line."""
    with EXAMPLE_JSONL.open() as f:
        lines = f.readlines()
    assert 5 <= len(lines) <= 20, f"expected 5-20 lines, got {len(lines)}"
    for i, line in enumerate(lines, 1):
        obj = json.loads(line)
        assert "ts_recv_ms" in obj, f"line {i} missing ts_recv_ms"
        assert "raw" in obj, f"line {i} missing raw"
    # Verify it contains at least PID 0, PID 4, PID 3
    pids: set[int] = set()
    with EXAMPLE_JSONL.open() as f:
        for line in f:
            obj = json.loads(line)
            pid = obj["raw"].get("eventPid")
            if pid is not None:
                pids.add(pid)
    assert 0 in pids, "sample_event.jsonl must contain a PID 0 (InitialState) message"
    assert 4 in pids, "sample_event.jsonl must contain a PID 4 (TrackState) message"
    assert 3 in pids, "sample_event.jsonl must contain a PID 3 (Race) message"


def test_sample_and_test_fixture_are_identical() -> None:
    """examples/data/sample_event.jsonl and tests/fixtures/example_messages.jsonl must match."""
    sample = SAMPLE_JSONL.read_text(encoding="utf-8")
    fixture = EXAMPLE_JSONL.read_text(encoding="utf-8")
    assert sample == fixture, (
        "examples/data/sample_event.jsonl and tests/fixtures/example_messages.jsonl "
        "diverge — regenerate from the same source per Plan 04-03 Step 3."
    )


def test_examples_not_in_installed_package() -> None:
    """Examples must NOT ship as part of the installed package.

    Phase 4 D-22: examples stay in the repo (for documentation/git clone
    walkthroughs) but are not packaged with the wheel. Verify by checking
    that ``import aionlslivetiming.examples`` fails with ModuleNotFoundError.
    """
    import subprocess

    result = subprocess.run(
        [sys.executable, "-c", "import aionlslivetiming.examples"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0, "examples must not be importable from the installed package"
    assert "ModuleNotFoundError" in result.stderr, (
        f"unexpected error importing aionlslivetiming.examples: {result.stderr!r}"
    )
