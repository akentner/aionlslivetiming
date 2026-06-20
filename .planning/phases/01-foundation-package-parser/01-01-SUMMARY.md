---
phase: 01-foundation-package-parser
plan: 01
subsystem: packaging, cli
tags: [pyproject, hatchling, src-layout, py.typed, websockets, jsonl, pydantic, pytest-asyncio, ruff, mypy]

# Dependency graph
requires:
  - phase: none
    provides: greenfield repository
provides:
  - Installable src-layout package (hatchling + py.typed, PEP 561)
  - Channel ID constants for the 6 NLS WebSocket PIDs (0/3/4/7/501/9002)
  - D-07 JSONL live-capture CLI (python -m aionlslivetiming.cli.jsonl_logger)
  - Test harness: pytest-asyncio auto-mode + coverage on parser/events
  - Dev tooling: ruff + mypy strict + coverage config
affects:
  - 01-02 (8 frozen dataclass event types in events/__init__.py)
  - 01-03 (parse() dispatcher in parser/__init__.py)
  - All later phases depend on this package skeleton

# Tech tracking
tech-stack:
  added:
    - hatchling 1.30 build backend
    - pydantic==2.13.4 (HA-pinned, used in Phase 2)
    - websockets>=15.0.1,<17 (HA-pinned)
    - httpx>=0.28,<0.29 (HA-pinned)
    - orjson>=3.11,<4 (optional extra, stdlib json fallback)
    - pytest>=9.0 + pytest-asyncio>=1.4,<2 (auto mode)
    - pytest-cov>=7,<8
    - respx>=0.23
    - ruff>=0.15
    - mypy>=1.1,<2.2 + pydantic.mypy plugin
    - freezegun>=1.5
  patterns:
    - src-layout with `src/aionlslivetiming/` package root
    - py.typed marker forced into wheel via hatch force-include (PEP 561)
    - logging.getLogger() wrapper (get_logger) in aionlslivetiming.logging
    - orjson-with-stdlib-fallback pattern for optional fast JSON
    - websockets.connect injection via websockets_factory kwarg for testability
    - dataclass-for-events / pydantic-for-state split (D-01/D-02 — D-02 lands in Phase 2)

key-files:
  created:
    - pyproject.toml
    - .gitignore
    - README.md
    - src/aionlslivetiming/py.typed
    - src/aionlslivetiming/__init__.py
    - src/aionlslivetiming/version.py
    - src/aionlslivetiming/logging.py
    - src/aionlslivetiming/parser/__init__.py
    - src/aionlslivetiming/parser/channels.py
    - src/aionlslivetiming/events/__init__.py
    - src/aionlslivetiming/cli/__init__.py
    - src/aionlslivetiming/cli/jsonl_logger.py
    - tests/__init__.py
    - tests/conftest.py
    - tests/test_smoke.py
    - tests/test_jsonl_logger.py
  modified: []

key-decisions:
  - "Hatchling build backend (PEP 621, no setup.py) — STACK.md recommendation"
  - "orjson as optional extra, not a hard runtime dep — STACK.md D-10"
  - "pydantic listed in runtime deps now even though state/ is Phase 2 — locks the env early"
  - "Logging via thin get_logger() wrapper rather than direct logging.getLogger — keeps the namespace convention discoverable"
  - "WebSocket factory injection via websockets_factory kwarg — testability without network in CI"
  - "ASNYC230 (blocking file open in async) is acceptable here — file IO is sub-ms vs recv() latency; no aiofiles dep needed"
  - "JSONL line shape {ts_recv_ms, raw} is a strict subset of the Phase 2 schema {ts_recv_ms, event_pid, raw, parsed} — no migration needed later"

patterns-established:
  - "Stub subpackages: parser/__init__.py and events/__init__.py re-export channel IDs / declare Message placeholder, with a comment indicating which future plan fills the gap"
  - "CLI subpackage as python -m entry point (not console_scripts yet — those land in Plan 04)"
  - "Async tests use _FakeWebSocket helper class that raises ConnectionResetError when its frame queue is exhausted (instead of blocking forever)"

requirements-completed: [DIST-02, DIST-03, DIST-07]

# Metrics
duration: 25min
completed: 2026-06-20
---
# Phase 1 Plan 01: Package Skeleton + JSONL Live-Capture CLI Summary

**Installable src-layout Python package (hatchling + py.typed) with D-07 live-capture JSONL CLI and pytest-asyncio test harness — all 10 tests green, ruff + mypy clean.**

## Performance

- **Duration:** 25 min
- **Started:** 2026-06-20T13:42:30Z
- **Completed:** 2026-06-20T14:07:30Z
- **Tasks:** 3
- **Files modified:** 16 (15 created, 1 modified)

## Accomplishments

- `pip install -e ".[dev]"` works on Python 3.12 with HA-pinned dependency versions (pydantic==2.13.4, websockets>=15.0.1,<17, httpx>=0.28,<0.29)
- `py.typed` PEP 561 marker ships in the installed package (verified)
- `python -m aionlslivetiming.cli.jsonl_logger --help` prints full argparse usage
- `import aionlslivetiming` works; `__version__` is `"0.1.0"`; all 6 channel ID constants importable
- 10 tests pass (4 smoke + 6 jsonl-logger) with `pytest-asyncio` auto mode
- `ruff check src tests` and `mypy --strict src` both clean
- Zero `homeassistant.*` imports in `src/` (verified by both grep and a smoke test)
- D-07 deliverable shipped: live-capture JSONL CLI ready to run against a real NLS session before Plan 02 fixture work

## Task Commits

Each task was committed atomically:

1. **Task 1: Create pyproject.toml + .gitignore + README stub** — `978647a` (chore)
2. **Task 2: Create src/ package skeleton + py.typed + version + logging + channels constants** — `0163267` (feat)
3. **Task 3: Implement D-07 JSONL logger CLI + smoke tests + jsonl logger tests** — `7f5ad54` (feat)

## Files Created/Modified

- `pyproject.toml` — hatchling build, src-layout, HA-pinned deps, ruff/mypy/pytest/coverage config, orjson as optional extra
- `.gitignore` — standard Python (`.venv/`, `__pycache__/`, tool caches, build artifacts, IDE)
- `README.md` — Phase 1 stub: install + dev quickstart, MIT license
- `src/aionlslivetiming/py.typed` — empty PEP 561 marker
- `src/aionlslivetiming/__init__.py` — re-exports `__version__` + `get_logger`
- `src/aionlslivetiming/version.py` — `__version__: str = "0.1.0"`
- `src/aionlslivetiming/logging.py` — thin `get_logger(name)` wrapper over `logging.getLogger`
- `src/aionlslivetiming/parser/__init__.py` — re-exports the 6 channel ID constants
- `src/aionlslivetiming/parser/channels.py` — `EVENT_PID_{RESULT,RACE_MESSAGE,TRACK_STATE,PER_CAR_LAPS,QUALIFYING,STATISTICS} = {0,3,4,7,501,9002}` with docstrings
- `src/aionlslivetiming/events/__init__.py` — `Message = object` placeholder (real union in Plan 02)
- `src/aionlslivetiming/cli/__init__.py` — subpackage marker
- `src/aionlslivetiming/cli/jsonl_logger.py` — `run()` coroutine + `main()` argparse entry point, websockets_factory injection for tests
- `tests/__init__.py` — empty (package marker)
- `tests/conftest.py` — adds `src/` to `sys.path` so the test suite runs without an editable install
- `tests/test_smoke.py` — 4 sync tests: imports, version, channel IDs, no-homeassistant, py.typed shipped
- `tests/test_jsonl_logger.py` — 6 async tests: 3 frames written, connection-closed cleanup, KeyboardInterrupt cleanup, argparse happy path, --help exit, websockets module fallback

## Decisions Made

- **Hatchling over setuptools/poetry-core** — STACK.md recommendation, no lockfile drama, mature env matrix
- **orjson as optional extra, not a hard runtime dep** — STACK.md D-10; stdlib `json` works fine for the CLI's modest throughput
- **pydantic==2.13.4 listed in runtime deps now** even though `state/` is Phase 2 — locks the HA-pinned env early so Phase 2 won't have to touch `pyproject.toml`
- **websockets_factory injection kwarg** for testability — lets the test suite run without ever hitting `wss://livetiming.azurewebsites.net/`
- **ASNYC230 (blocking file open in async) accepted with explicit comment** — the file write is sub-ms vs the `recv()` blocking call; adding aiofiles would be dead weight
- **JSONL line shape `{ts_recv_ms, raw}` is a strict subset of Phase 2's `{ts_recv_ms, event_pid, raw, parsed}`** — no migration needed when Plan 02/03 add the parser
- **No `console_scripts` entry in pyproject.toml yet** — `python -m` is the only entry point until Plan 04 (Client + Distribution)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed `_FakeWebSocket.recv()` blocking forever when frame queue exhausted**
- **Found during:** Task 3 (jsonl logger tests)
- **Issue:** The test helper blocked on `asyncio.Event().wait()` when its frames list was empty, causing pytest-asyncio tests to hang past the timeout. This is a test-quality bug, not a production bug — but it would block CI for any future contributor who adds a test that drains all frames.
- **Fix:** Changed `_FakeWebSocket.recv()` to raise `ConnectionResetError("fake websocket closed (no more frames)")` when the queue is empty. The `run()` loop's outer `except Exception` catches this and returns 0 cleanly. Also changed the `recv_exc` semantics to fire only *after* queued frames are drained, which matches the real `websockets` library's behavior.
- **Files modified:** tests/test_jsonl_logger.py
- **Verification:** All 6 jsonl-logger tests pass in 0.05s (previously hung indefinitely)
- **Committed in:** 7f5ad54 (Task 3 commit)

**2. [Rule 1 - Bug] Fixed double-await of `websockets.connect` in lazy-import branch**
- **Found during:** Task 3 (mypy strict + test_run_uses_websockets_module_when_no_factory)
- **Issue:** The original `run()` wrapped `websockets.connect` in `async def _factory(...)`, so `await factory(...)` returned a coroutine that needed a second `await`. The test that exercised the no-factory path triggered a `RuntimeWarning: coroutine was never awaited` because the test mock matched the real signature (one await gives the context manager).
- **Fix:** Bind `websockets.connect` directly as `connect` in the no-factory path so the call site `await connect(url, ...)` matches what test mocks provide.
- **Files modified:** src/aionlslivetiming/cli/jsonl_logger.py
- **Verification:** `mypy --strict src` passes; `test_run_uses_websockets_module_when_no_factory` passes; the no-factory path is now exercised in CI.
- **Committed in:** 7f5ad54 (Task 3 commit)

---

**Total deviations:** 2 auto-fixed (2 bugs)
**Impact on plan:** Both fixes are correctness improvements in the test infrastructure. The first would have caused indefinite CI hangs for any future contributor adding jsonl-logger tests; the second makes the optional-websockets-factory path actually work end-to-end. No scope creep — both keep to D-07's "ship a working CLI + tests" mandate.

## Issues Encountered

- **pytest-asyncio 1.4 + asyncio_mode=auto + nested `await ws.recv()`** required `await ws.send(...)` (no `# type: ignore`) — the strict mypy run flagged the `# type: ignore[attr-defined]` comments as unused because `websockets.connect` returns a typed object whose `recv`/`send` are well-known. Cleaned up the comments.
- **`orjson` not installed by default** — fell back to stdlib `json` in tests (works correctly). mypy needs `# type: ignore[import-not-found]` for the optional import; documented the optional-extras pattern.
- **`uv` venv creation worked cleanly** on Python 3.12.13 (cached locally) without internet downloads. `uv pip install -e ".[dev]"` resolved all 14 transitive dependencies in ~6s.

## User Setup Required

None — no external service configuration required for this plan. The JSONL live-capture CLI (D-07) is ready to run against the real `wss://livetiming.azurewebsites.net/` endpoint; running it is a Phase 1 acceptance step the user can take before Plan 02 fixture work.

## Next Phase Readiness

- **Plan 02 (events dataclasses) can start immediately:** the `events/__init__.py` `Message = object` placeholder is in place and the `parser/__init__.py` re-export shape is established.
- **Plan 03 (parse() dispatcher) can start immediately:** `parser/channels.py` exposes the 6 PIDs and `parser/__init__.py` is the natural home for the dispatcher.
- **No blockers for either.** The captured JSONL (D-07) is now a runnable user step: `python -m aionlslivetiming.cli.jsonl_logger E-123 out.jsonl` will dump a real session to JSONL, which the user can commit as the seed for Plan 02/03 fixtures (D-08).

---
*Phase: 01-foundation-package-parser*
*Completed: 2026-06-20*

## Self-Check: PASSED
