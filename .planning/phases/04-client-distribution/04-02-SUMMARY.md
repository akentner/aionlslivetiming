---
phase: 04-client-distribution
plan: 02
subsystem: cli-distribution
tags: [cli, typer-free, argparse, nls-record, nls-replay, jsonl, console-scripts]

# Dependency graph
requires:
  - phase: 04-client-distribution/04-01
    provides: NLSClient composition root + finalized exception hierarchy (LTSNotFoundError, ParseError, UnknownEventError, ReplayError family)
provides:
  - nls-record console script (replaces aionlslivetiming-capture)
  - nls-replay console script with --speed, --limit, --show-time-sync, --strict, --summary
  - 11+18 = 29 new CLI tests covering handshake, replay flags, strict-mode semantics
affects:
  - 04-04 docs/README quickstart will reference both scripts
  - 04-05 build verification needs both [project.scripts] entries present

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "CLI modules live under src/aionlslivetiming/cli/ (no public API re-export — internal subpackage)"
    - "DEFAULT_HOST + DEFAULT_CHANNELS constants duplicated inline rather than extracted to transport/_defaults.py (per agent-discretion note in CONTEXT.md)"
    - "--strict mode (D-25) translates parser/replay WARNINGs into exit 1 via UnknownEventError / ReplayError catches"
    - "--summary (D-05) pre-scans JSONL once for first/last ts_recv_ms to avoid modifying the transport protocol"

key-files:
  created:
    - src/aionlslivetiming/cli/__init__.py — empty marker (CLI subpackage is not part of public API)
    - src/aionlslivetiming/cli/record.py — nls-record CLI; verbatim port of old jsonl_logger.py with renames
    - src/aionlslivetiming/cli/replay.py — nls-replay CLI; full D-03..D-05 + D-25 surface
    - tests/test_cli_record.py — 11 tests for the nls-record CLI (renamed from test_jsonl_logger.py)
    - tests/test_cli_replay.py — 18 tests for the nls-replay CLI
  modified:
    - pyproject.toml — [project.scripts] block now lists nls-record + nls-replay; aionlslivetiming-capture removed
    - src/aionlslivetiming/client.py — _default_channels() lazy import re-pointed from cli.jsonl_logger to cli.record
    - src/aionlslivetiming/transport/websocket.py — _default_host() + _default_channels() lazy imports re-pointed similarly

key-decisions:
  - "Hard cut: cli/jsonl_logger.py deleted outright (no deprecation cycle); library has never been published (D-02)"
  - "DEFAULT_HOST + DEFAULT_CHANNELS duplicated in cli/record.py rather than extracted (per agent-discretion in CONTEXT.md); lazy imports in client.py and transport/websocket.py were re-pointed to the new module"
  - "cli/replay.py catches both ReplayError (transport-level) and UnknownEventError (parser-level) for --strict mode; both routes return exit 1"
  - "cli/replay.py --summary pre-scans the JSONL separately for first/last ts_recv_ms rather than reaching into ReplayTransport internals — keeps the transport protocol clean"

patterns-established:
  - "Each CLI module exposes __all__ = ['main', 'run'] with run() being an async entry that takes structured kwargs (testable directly) and main() being the argparse+asyncio.run() wrapper"
  - "Tests pass an out=StringIO() kwarg to capture stdout without competing with pytest's capsys"
  - "Mock websockets.connect with a sync-callable factory that returns a coroutine for the fake context manager (mirrors Phase 1 D-07 test pattern)"

requirements-completed: [DIST-05]

# Metrics
duration: 22min
completed: 2026-06-21
---

# Phase 4 Plan 02: CLI Distribution (nls-record + nls-replay) Summary

**Shipped two console scripts (`nls-record` + `nls-replay`) per D-01..D-05, hard-cutting the Phase 1 `aionlslivetiming-capture` tool; nls-replay supports --speed/--limit/--show-time-sync/--strict/--summary with strict-mode exit-1 semantics per D-25.**

## Performance

- **Duration:** 22 min
- **Started:** 2026-06-21T18:22:00Z
- **Completed:** 2026-06-21T18:44:34Z
- **Tasks:** 2
- **Files modified:** 8 (4 created, 2 renamed, 3 modified in-place)

## Accomplishments

- **`nls-record` console script** — verbatim port of `cli/jsonl_logger.py::run()` with `prog="nls-record"`, registered in `[project.scripts]`. The old `aionlslivetiming-capture` entry and `cli/jsonl_logger.py` file are gone (D-02 hard cut, library never published).
- **`nls-replay` console script** — drives `NLSClient.from_replay(path)` (the public API surface from Plan 04-01) and prints one `repr(msg)` per line to stdout. Implements the full D-15 surface: `--speed N` (0=burst, 1.0=real-time, >1=faster), `--limit N` (early break), `--show-time-sync` (best-effort, no-op when transport suppresses), `--strict` (D-25 — raises `UnknownEventError` on `UnknownMessage`; catches `ReplayError` family for transport-level schema/ordering errors; both routes return exit 1), `--summary` (D-05 — pre-scans JSONL for first/last `ts_recv_ms`, prints per-pid breakdown block at end-of-stream).
- **29 new tests** — 11 for `nls-record` (port of old `test_jsonl_logger.py` plus module-surface assertions: `prog="nls-record"`, `main`/`run` exports, old-module `ImportError`, default constants) and 18 for `nls-replay` (each D-03..D-05 flag exercised, `--strict` paths, default vs strict mode for `UnknownMessage` / `ReplayEmptyError` / `ReplaySchemaError`, `--help` text, `speed_factor=-1` ValueError, `--show-time-sync` no-op).
- **Zero `jsonl_logger` references in source** — `cli/record.py` is the only live-capture module; `cli/__init__.py` is the empty marker; `pyproject.toml` lists exactly the two D-01 scripts.

## Task Commits

Each task was committed atomically:

1. **Task 1: Build cli/record.py + delete cli/jsonl_logger.py + update pyproject.toml** - `bc9fb59` (feat)
2. **Task 2: Build cli/replay.py with --speed, --limit, --show-time-sync, --strict, --summary** - `5565960` (feat)

_Note: the actual file content for Task 2 was first committed in `f0dde30` by the parallel Plan 03 agent (which absorbed staged changes via `git reset --soft`); a follow-up `5565960` on top of HEAD added a small docstring tweak and proper commit attribution. See "Issues Encountered" below._

## Files Created/Modified

- `src/aionlslivetiming/cli/__init__.py` — empty marker
- `src/aionlslivetiming/cli/record.py` — nls-record CLI (renamed from `cli/jsonl_logger.py`)
- `src/aionlslivetiming/cli/replay.py` — nls-replay CLI with full D-03..D-05 + D-25 surface
- `tests/test_cli_record.py` — 11 tests (renamed from `tests/test_jsonl_logger.py`)
- `tests/test_cli_replay.py` — 18 tests
- `pyproject.toml` — `[project.scripts]` block: nls-record + nls-replay (was aionlslivetiming-capture)
- `src/aionlslivetiming/client.py` — lazy `DEFAULT_CHANNELS` import re-pointed to `cli.record`
- `src/aionlslivetiming/transport/websocket.py` — lazy `DEFAULT_HOST` + `DEFAULT_CHANNELS` imports re-pointed similarly

## Decisions Made

- **Hard cut on `aionlslivetiming-capture`:** D-02 explicit; the library has never been published so no external user has the old name. No deprecation cycle.
- **Inlined `DEFAULT_HOST` / `DEFAULT_CHANNELS` in `cli/record.py`:** Per the agent-discretion note in CONTEXT.md ("kept inline rather than extracting a `transport/_defaults.py`"). Existing lazy-import sites in `client.py` and `transport/websocket.py` were re-pointed to the new module rather than extracting shared constants.
- **`--show-time-sync` is a documented no-op for replay:** `ReplayTransport` suppresses time-sync frames by default (Pitfall #10 / D-16); the CLI honors that and silently emits nothing in `--show-time-sync` mode rather than re-implementing parser dispatch.
- **`--summary` pre-scans the JSONL separately:** Reading the file once before constructing the client is acceptable for diagnostics mode; the alternative (reaching into `ReplayTransport` internals) would couple the CLI to transport internals and add complexity for marginal benefit.
- **`--strict` catches both `ReplayError` and `UnknownEventError`:** The transport raises `ReplaySchemaError` / `ReplayOrderingError` / `ReplayEmptyError` (typed `ReplayError` subclasses); the parser yields `UnknownMessage` and the CLI translates that to `UnknownEventError`. Both paths land in the same `return 1` exit-code path under `--strict`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Re-pointed lazy imports of `cli.jsonl_logger` in `client.py` and `transport/websocket.py`**
- **Found during:** Task 1 (after deleting `cli/jsonl_logger.py`)
- **Issue:** The plan listed `src/aionlslivetiming/cli/`, `pyproject.toml`, and `tests/test_cli_*.py` as the only files in `files_modified`, but the existing `_default_channels()` / `_default_host()` helpers in `client.py` and `transport/websocket.py` had lazy imports of `aionlslivetiming.cli.jsonl_logger`. Deleting that module would have broken `_default_channels()` at first call (the lazy imports are triggered by `NLSClient(event_id=...)` and `LiveTransport(...)`).
- **Fix:** Updated the three lazy imports to point at `aionlslivetiming.cli.record` instead, since the `DEFAULT_HOST` / `DEFAULT_CHANNELS` constants live there now.
- **Files modified:** `src/aionlslivetiming/client.py`, `src/aionlslivetiming/transport/websocket.py`
- **Verification:** `uv run pytest tests/` — all 323 tests pass; `uv run python -c "import aionlslivetiming; ..."` succeeds.
- **Committed in:** `bc9fb59` (Task 1 commit)

**2. [Rule 1 - Bug] Removed unused `# type: ignore[import-not-found]` on `import orjson`**
- **Found during:** Task 1 (running `uv run mypy --strict src/aionlslivetiming/cli/record.py`)
- **Issue:** `orjson` is installed in the dev environment (it is a transitive dependency), so `mypy --strict` flagged the `# type: ignore[import-not-found]` comment as unused.
- **Fix:** Removed the type-ignore comments on both `import orjson` lines in `cli/record.py`. The runtime behavior is identical — the `try/except ImportError` fallback still works for environments without `orjson`.
- **Files modified:** `src/aionlslivetiming/cli/record.py`
- **Verification:** `uv run mypy --strict src/aionlslivetiming/cli/` clean.
- **Committed in:** `bc9fb59` (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (2 blocking/correctness — both necessary for build to pass)
**Impact on plan:** Both fixes were strictly necessary; no scope creep.

## Issues Encountered

- **Cross-agent commit entanglement:** The parallel Plan 03 agent ran `git reset --soft HEAD~1` on the shared main branch while I was between Task 1 and Task 2. This absorbed my staged Task 2 files into the Plan 03 commit (`f0dde30` — "test(04-03): add mocked-transport tests for the three worked examples"), which had a misleading message that didn't mention the nls-replay work. I recovered by making a small docstring tweak to `cli/replay.py` to create a real diff and committing it on top as `5565960` with the correct message. The actual file content for `replay.py` and `test_cli_replay.py` was never lost — it was simply attributed to the wrong commit. The `f0dde30` commit still exists in history; this is acceptable since (a) the file content is correct, (b) the working tree is clean, (c) the `5565960` follow-up commit provides the proper attribution. Not a hard rewrite of someone else's history.
- **No external network or auth required** — both CLIs are local tooling; smoke test (`echo '{"ts_recv_ms":1000,"raw":{...}}' | nls-replay --summary`) prints the expected output.

## User Setup Required

None — `uv sync --extra dev` is sufficient to install both console scripts into `.venv/bin/`. No external service configuration, no API keys.

## Next Phase Readiness

- **Ready for Phase 4 Plan 04 (Documentation/Quickstart):** both `nls-record` and `nls-replay` are installed by `uv sync` and have `--help` output. The README quickstart (D-13) can reference them directly.
- **Ready for Phase 4 Plan 05 (Build verification):** `uv build` will produce a wheel containing both `[project.scripts]` entries; the entry-point resolution is mechanical.
- **No blockers** for downstream plans. The CLI surface is the user-facing distribution promise of DIST-05 and is now satisfied.

## Self-Check: PASSED

All created files exist, both task commits (`bc9fb59` and `5565960`) are in `git log --oneline`, `pytest tests/` reports 323 passed (29 new + 294 pre-existing), `ruff check` clean, `mypy --strict src/aionlslivetiming/cli/` clean.

---
*Phase: 04-client-distribution*
*Completed: 2026-06-21*
