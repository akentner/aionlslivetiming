# Phase 4: Client + Distribution - Context

**Gathered:** 2026-06-21
**Status:** Ready for planning

<domain>
## Phase Boundary

A single `NLSClient` composition root that wires Transport → Parser → State with cancellation-safe async iteration, plus CLI entry points, complete documentation, and a publish-ready PyPI package.

**In scope:**

1. **`NLSClient`** in `src/aionlslivetiming/client.py` — the composition root. Direct constructor for live (`NLSClient(event_id=...)`); class method `NLSClient.from_replay(path)` for replay; optional `transport=` kwarg for power-user injection; optional `record_to=Path` for record+consume. Owns a `RaceState` and auto-applies every parsed Message. Exposes `async with` lifecycle, three async iterators (`messages()`, `time_sync()`, `lts_not_found()`), and `state`, `clock_offset`, `source` accessors.
2. **`nls-record` and `nls-replay` console scripts** — `[project.scripts]` entries in `pyproject.toml` pointing into `cli/record.py` and `cli/replay.py`. The old `aionlslivetiming-capture` script and `cli/jsonl_logger.py` are deleted outright (no deprecation cycle — library has never been published, no external users).
3. **Exception hierarchy finalization** — `exceptions.py` stays at the top level. Names finalized. Add `ParseError` (new) so the CLI `--strict` mode has a way to surface parser D-03 violations as a typed exception.
4. **Documentation** — slim README + `docs/` tree. `mkdocs.yml` at the repo root, mkdocs-material theme, mkdocstrings plugin for API ref. CHANGELOG.md (Keep a Changelog 1.1.0). MIT LICENSE file. CONTRIBUTING.md (light). Three worked examples as runnable `.py` files in `examples/`.
5. **PyPI publish prep** — verify `uv build` produces a wheel + sdist with `py.typed` (D-10/D-11 from Phase 1 already lock this). Verify `[project]` metadata is complete (description, license, classifiers, URLs). No actual publishing in Phase 4 — library is `0.1.0` alpha per the classifier.

**Explicitly out of scope** (later phases / v2):

- Submitting to PyPI (DIST-01 is "publish-ready", not "publish"; first publish happens outside this workflow)
- `homeassistant.*` integration (HAI-01..03 — v2)
- A web UI / dashboard
- Any change to Phase 3 Transport Protocol, Phase 2 RaceState, or Phase 1 parser
- Telemetry, scraping, ML — already out of scope per PROJECT.md
- File rotation for the recorder (Pitfall #12) — never raised by any user yet
- `clock_offset` API expansion beyond a simple `.clock_offset_ms: float | None` property (deferred — see "Deferred")

</domain>

<decisions>
## Implementation Decisions

### CLI surface (DIST-05)

- **D-01:** Ship two console scripts in `[project.scripts]`:
  - `nls-record` → `aionlslivetiming.cli.record:main`
  - `nls-replay` → `aionlslivetiming.cli.replay:main`
  Both short, tab-completable, match DIST-05 verbatim. (No `aionlslivetiming-capture` alias — hard cut, see D-02.)
- **D-02:** **Hard cut** on the Phase 1 D-07 tool. Delete `src/aionlslivetiming/cli/jsonl_logger.py` and remove the `aionlslivetiming-capture` script entry from `pyproject.toml`. The library has never been published, so no external user has the old name. The new `cli/record.py` is the only record CLI. `cli/jsonl_logger.py`'s `run()` body is the seed for `cli/record.py::run()` — same args, same defaults (`DEFAULT_HOST`, `DEFAULT_CHANNELS`), same handshake shape. Channel list and host come from the same constants (`transport/_defaults.py` if Phase 3 already extracted them, otherwise duplicated in `cli/record.py`).
- **D-03:** `nls-replay` is a full D-15 surface CLI, not a stats-only dump:
  - Positional arg: JSONL path
  - `--speed N` (float, default `1.0` — D-15; `0` for burst, `>1` for faster-than-real-time)
  - `--show-time-sync` (flag, default off — D-16 default `suppress_time_sync=True`)
  - `--limit N` (int, default unlimited — stop after N parsed messages; useful for spot-checking a long recording)
  - Default output: one typed Message per line as `repr(msg)` to stdout. Stdout is line-buffered so the user can pipe to `head` / `grep`.
  - Exit code: `0` with WARNING logs on parse failures / UnknownMessage / replay ordering (see D-04).
- **D-04:** Both CLIs exit `0` by default and log parse failures, UnknownMessage, schema drift, and replay ordering errors at WARNING via `logging.getLogger("aionlslivetiming.cli")` — consistent with parser D-03 tolerance. Add `--strict` flag to `nls-replay` only (the record CLI has no "fail on parse error" semantic since recording IS the source of truth). When `--strict`, exit `1` on any WARNING-level event from the parser or replay layer. Pipeline consumers that want strict mode opt in.
- **D-05:** `nls-replay` also gets a `--summary` flag (default off) that prints once at end-of-stream: total messages, breakdown by `eventPid` (dict {pid: count}), first/last `ts_recv_ms`, and any UnknownMessage events observed. Useful for "is this recording healthy?" diagnostics without spamming the message stream.

### NLSClient composition root

- **D-06:** `NLSClient` lives in `src/aionlslivetiming/client.py` (single file — small enough not to need a subpackage). Public class. Direct constructor for the common case:
  ```python
  NLSClient(event_id: str, *, host: str = "wss://livetiming.azurewebsites.net/",
            channels: Sequence[int] = DEFAULT_CHANNELS,
            transport: Transport | None = None,
            record_to: str | Path | None = None,
            reconnect_policy: ReconnectPolicy = ReconnectPolicy(),
            lts_not_found_policy: LTSNotFoundPolicy = LTSNotFoundPolicy(),
            state: RaceState | None = None,
            websockets_factory: Callable[..., Awaitable[Any]] | None = None)
  ```
  - When `transport` is provided: use it directly (power-user escape hatch — RecordingTransport, custom LiveTransport with policy overrides, etc.).
  - When `event_id` is provided and `transport` is not: build `LiveTransport(event_id, host=host, channels=channels, reconnect_policy=..., lts_not_found_policy=..., websockets_factory=...)`.
  - When `record_to` is set (live mode only): wrap as `RecordingTransport(inner_live_transport, JsonlRecorder(record_to))`. The JsonlRecorder honors Phase 3 REC-02 runtime toggle.
- **D-07:** Class method `NLSClient.from_replay(path, *, speed_factor=1.0, suppress_time_sync=True, limit=None) -> NLSClient` — hides the transport choice. Internally builds `ReplayTransport(path, speed_factor=..., suppress_time_sync=...)` and constructs the client with `transport=replay_transport`. Source is `Source.REPLAY`. Construction is lazy: does NOT open the file; `__aenter__` opens it (D-09).
- **D-08:** `NLSClient` owns a `RaceState` (lazily created if `state=None` was passed). Every parsed Message is applied: `self._state.apply(msg)` happens BEFORE the message is yielded. The state cache is exposed as `client.state: RaceState` (read-only by convention — consumers should not call `apply()` themselves while the client is running; documented in the class docstring). Source is set at construction time: `Source.LIVE` for live transport, `Source.REPLAY` for replay, `Source.IMPORTED` if a caller pre-loaded state via `state=RaceState.from_json(...)`.
- **D-09:** `NLSClient` is an async context manager:
  ```python
  async with NLSClient(event_id=20) as client:
      async for msg in client.messages():
          ...
  ```
  `__aenter__` calls `await self._transport.connect()`. `__aexit__` calls `await self._transport.close()` and ensures no reader task is leaked (Pitfall #8 — cancellation safety; the transport protocol's `close()` already cancels its internal task, so the client just propagates).
- **D-10:** Three async iterators (matches Phase 3 D-04 separation):
  - `client.messages() -> AsyncIterator[Message]` — race messages (time-sync excluded by default).
  - `client.time_sync() -> AsyncIterator[TimeSyncMessage]` — only available when the underlying transport exposes time-sync frames (`LiveTransport.time_sync()` and `ReplayTransport` with `suppress_time_sync=False`). For sources that don't, the iterator simply never yields.
  - `client.lts_not_found() -> AsyncIterator[LTSNotFoundEvent]` — only available when the underlying transport exposes it (`LiveTransport.lts_not_found()`). ReplayTransport never yields.
- **D-11:** `client.clock_offset` returns the transport's `ClockOffset` (live and replay both expose one). Replay yields `None` offset until the first time-sync frame (or never, if `suppress_time_sync=True`).
- **D-12:** `client.source: Source` — read-only property reflecting the transport's source. `LIVE` / `REPLAY` / `IMPORTED` per Phase 2 D-PERSIST.

### Documentation (DOC-01..05)

- **D-13:** Slim README.md at the repo root:
  - Title + one-line description
  - Badges: PyPI version, Python versions, license, CI status (placeholder if no CI yet)
  - Installation: `uv add aionlslivetiming` (and `pip install aionlslivetiming` as fallback)
  - 60-second quickstart: live (5 lines) + replay (3 lines) + filter (5 lines)
  - Links out to `docs/` tree: `docs/quickstart.md`, `docs/examples/`, `docs/api/`
  - License: MIT, with link to LICENSE file
  - Acknowledgements / NLS data attribution
- **D-14:** `docs/` tree:
  - `docs/quickstart.md` — full walkthrough (live + replay + filter + recording)
  - `docs/examples/live_quickstart.py`
  - `docs/examples/replay_offline.py`
  - `docs/examples/filter_walkthrough.py`
  - `docs/api/` — auto-generated by `mkdocstrings` (committed to repo via `mkdocs build` step in CI / docs workflow)
  - `docs/index.md` — mkdocs landing page (same content as the top of README but mkdocs-formatted)
- **D-15:** `mkdocs.yml` at the repo root. Theme: `mkdocs-material`. Plugins: `mkdocstrings[python]` (griffe backend). Python handler config: `paths: [src]` so docstrings resolve correctly. `mkdocs serve` for dev; `mkdocs build --strict` for CI. Build output goes to `site/` (gitignored).
- **D-16:** Add dev dependency `mkdocs>=1.6`, `mkdocs-material>=9.5`, `mkdocstrings[python]>=0.27` to `[project.optional-dependencies].dev` in `pyproject.toml`. Optional separate `[project.optional-dependencies].docs` if the install footprint matters (deferred — `dev` is fine for now since contributors install `--extra dev`).
- **D-17:** `CHANGELOG.md` follows [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/) format with SemVer 2.0.0. The v0.1.0 entry sections:
  - `### Added` — full Phase 1/2/3/4 feature list (parser, state, filters, transports, NLSClient, CLIs, docs)
  - `### Changed` — none (initial release)
  - `### Deprecated` — none (initial release)
  - `### Removed` — `aionlslivetiming-capture` console script (replaced by `nls-record`)
  - `### Fixed` — none (initial release)
  - `### Security` — none (initial release)
  Date: `2026-06-21`. The header links section compares to an "unreleased" placeholder for future entries.
- **D-18:** `CONTRIBUTING.md` is a light dev guide:
  - Dev setup: `uv sync --extra dev`
  - Test / lint / typecheck commands (`uv run pytest`, `uv run ruff check src tests`, `uv run mypy --strict src`)
  - The dataclass-for-events / pydantic-for-state rule (Phase 1 D-01/D-02) — events are stdlib `@dataclass(frozen=True, slots=True)`; state/filter models are pydantic
  - How to add a new Message variant (parse first, then event class, then add to the dispatcher in `parser/__init__.py`)
  - How to capture a live JSONL for fixture material (`uv run nls-record <event_id> /tmp/event.jsonl --max-seconds 30`)
  - PR expectations: tests for any new public surface; mypy strict; ≥80% coverage
  No PR/issue templates — out of scope for v0.1.0 alpha.
- **D-19:** `LICENSE` file at the repo root: MIT license text, copyright `Copyright (c) 2026 akentner`. Standard short-form MIT text.

### Worked examples (DOC-05)

- **D-20:** Three runnable examples in `examples/`:
  - `examples/live_quickstart.py` — connect to a live race event, iterate messages, print current standings every 30s. Uses placeholder event_id `"YOUR_EVENT_ID"` with a top-of-file docstring explaining how to find a current event id on the NLS website. Standalone runnable via `uv run python examples/live_quickstart.py` (with a real event id substituted).
  - `examples/replay_offline.py` — load a JSONL via `NLSClient.from_replay(...)`, iterate messages, populate the cached state, query `client.state.cars` at the end. Run the example with a recorded JSONL the user already has (or captured via `nls-record`).
  - `examples/filter_walkthrough.py` — load a JSONL, populate the state, then walk through each of the 6 filter dimensions (class / starting_no / driver / position / lap / sector_time_lt) and print the result for a contrived query. Self-contained — uses a small bundled fixture JSONL (see D-22).
- **D-21:** Each example file has a top-of-file docstring with: one-paragraph description, how to run (`uv run python examples/<name>.py`), expected output shape (e.g. "prints one line per parsed message, then a summary of the cached state"). Examples are tested in CI with a mocked transport — the live example has a `--dry-run` mode that injects a fake `LiveTransport` returning canned messages from `tests/fixtures/example_messages.jsonl` so CI doesn't depend on the NLS server.
- **D-22:** `examples/filter_walkthrough.py` references a small committed sample JSONL at `examples/data/sample_event.jsonl` — a 5-10 message hand-crafted fixture (PID 0 + a couple of PID 4 / PID 3) so the filter walkthrough is runnable end-to-end on a fresh checkout with no live data. This is the only sample JSONL committed to the repo. Larger recordings stay local.

### Exception hierarchy finalization (D-EXC deferred from Phase 3)

- **D-23:** `exceptions.py` stays at the top level (no subpackage — not worth the import-path churn for v1). Names finalized:
  - `NLSError(Exception)` — base
  - `ConnectionError(NLSError)` — Phase 3 name; covers WebSocket transport-level failure (after retry exhaustion)
  - `LTSNotFoundError(NLSError)` — **new**, replaces the per-reason "UnknownEventError" semantic for LTS_NOT_FOUND specifically. Carries `reason: LTSNotFoundReason`. Note: `LTSNotFoundEvent` (the typed event yielded by `client.lts_not_found()`) stays separate — events and errors are different things, even if both carry the same `reason` field.
  - `UnknownEventError(NLSError)` — Phase 3 name; repurposed to mean "UnknownMessage surfaced in --strict mode" (was ambiguous before). CLI `--strict` raises this when an `UnknownMessage` would otherwise be silently logged.
  - `ReplayError(NLSError)` — base; subclasses `ReplayEmptyError`, `ReplaySchemaError`, `ReplayOrderingError` (all from Phase 3, names kept)
  - `ParseError(NLSError)` — **new**. Carries `event_pid: int`, `line_no: int | None`, `message: str`. Raised by the parser ONLY in `--strict` CLI mode (or by consumers who explicitly opt in to strict parsing). The default `parse()` path stays tolerant (Phase 1 D-03).
  - `NLSHttpFallbackUnavailable(NLSError)` — Phase 3 name; kept.
  - `__all__` updated to export all 8. `__init__.py` re-exports the same set.
- **D-24:** `LiveTransport` updates: `LTSNotFoundEvent(reason="unknown_event")` (which Phase 3 D-07 default policy raises as `UnknownEventError`) now raises `LTSNotFoundError(reason="unknown_event")` instead. The other two reasons stay silent (`not_yet_started`) or terminal (`ended`) per Phase 3 D-07. Backward compatibility note: there are no external users yet, so the rename is clean.
- **D-25:** CLI `--strict` mode (`nls-replay --strict`): wraps the message iteration in a small observer that catches `UnknownMessage` events on the parsed stream, logs them at WARNING, then raises `UnknownEventError` with the offending message attached. Also catches `ReplaySchemaError` and `ReplayOrderingError` from the transport and re-raises as-is (they're already typed).

### PyPI publish prep (DIST-01)

- **D-26:** Verify `uv build` produces a valid wheel + sdist. Verification step in Phase 4: run `uv build`, then `python -m twine check dist/*` to validate the metadata. Both must succeed before Phase 4 closes. (`twine` is a dev-only check tool — added to `[project.optional-dependencies].dev`.)
- **D-27:** Verify `py.typed` marker is in the wheel. Already locked by Phase 1 D-11 (`hatch force-include`). Re-verify in Phase 4 with `python -m zipfile -l dist/*.whl | grep py.typed`.
- **D-28:** Verify `[project]` metadata is complete per PyPA guidelines:
  - `name`, `version`, `description`, `readme`, `license`, `requires-python`, `authors`, `keywords`, `classifiers` — all present in current `pyproject.toml`
  - `urls` for `Repository` and `Issues` — already present
  - `dependencies` and `optional-dependencies` — already present
  - No changes needed; verification is a checklist item.
- **D-29:** No actual publish in Phase 4. The first PyPI release happens outside this workflow (manually, or via a future GitHub Actions release workflow). Phase 4 closes when `uv build` produces a publishable artifact. Add a `scripts/build.sh` thin wrapper that runs `uv build && python -m twine check dist/*` for sanity.
- **D-30:** Verify zero HA-specific imports (DIST-04): a single `grep -r "homeassistant" src/` returns zero results. This is the greenfield baseline (Phase 1 already verified). Add a CI step (`scripts/check_no_ha_imports.sh` or `ruff` config) that fails the build if any `homeassistant.*` import appears in `src/`.

### the agent's Discretion

- Internal layout of `cli/` — keep `cli/record.py` and `cli/replay.py` as the two scripts. A future `cli/__main__.py` for `python -m aionlslivetiming` is out of scope (Phase 4 only ships the two console scripts).
- Exact `__repr__` shape of `NLSClient` — sensible default (`NLSClient(event_id=20, source=LIVE, state=<RaceState fresh=True, ...>)`).
- Internal task-management inside `NLSClient.messages()` — single-writer task on the transport, multiplexer fan-in to a per-iterator `asyncio.Queue` (or just delegate to the transport's `__aiter__` if it already exposes one — `LiveTransport` does, per Phase 3 D-04; verify during planning).
- `examples/data/sample_event.jsonl` exact contents — planner hand-crafts 5–10 lines covering PID 0 (with 3 cars), PID 4 (track state update), and PID 3 (one race message).
- README badge URLs — placeholders if no CI exists yet (deferred).
- README "Acknowledgements" wording — single sentence crediting the NLS livetiming service.
- Whether `scripts/build.sh` is added or just documented in README (D-29 is non-prescriptive — pick whichever is lighter).
- `mkdocs.yml` `nav:` section order — sensible defaults (Home / Quickstart / Examples / API reference / Changelog / Contributing / License).

### Folded Todos

None — `gsd-tools todo match-phase 4` returned zero matches.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project intent & requirements

- `.planning/PROJECT.md` — vision, requirements, reverse-engineering notes (server schema, channel IDs, handshake shape, `/laps-data` HTML behavior)
- `.planning/REQUIREMENTS.md` §Distribution & Ergonomics + §Documentation & Community — DIST-01/04/05, DOC-01..05 (Phase 4 scope)
- `.planning/ROADMAP.md` §Phase 4 — success criteria (NLSClient composition, CLI, doc set, publish-ready)
- `.planning/STATE.md` §Accumulated Context — Phase 1/2/3 decisions that lock Phase 4's constraints (D-10 HA-pinned deps, D-23 final exception names, D-08 RaceState ownership boundary)

### Stack & architecture (locked)

- `.planning/research/STACK.md` — exact dependency versions, HA pin rationale, library comparison (mkdocs is NOT in the locked deps — see D-16 for the new dev-dep additions)
- `.planning/research/ARCHITECTURE.md` §Public API Surface, §Testability Gradient — Client composition boundary (Client sits above State, below user code); cancellation safety patterns (lines 477–488)
- `.planning/research/SUMMARY.md` §Architecture Approach — exec summary; the planner can read this instead of the long-form ARCHITECTURE.md
- `.planning/research/PITFALLS.md` — pitfall #8 (cancellation safety — NLSClient must close cleanly within 1s), pitfall #15 (PyPI packaging — DIST-01 checklist items)

### Prior phase context

- `.planning/phases/01-foundation-package-parser/01-CONTEXT.md` — D-05 (time-sync dispatcher order), D-07 (JSONL line shape subset, the existing `cli/jsonl_logger.py`), D-10 (HA-pinned deps), D-11 (py.typed via hatch force-include), D-12 (pytest-asyncio auto mode)
- `.planning/phases/02-state-filtering/` — `Source` enum (`LIVE`/`REPLAY`/`IMPORTED`), `Freshness` enum (`FRESH`/`STALE`/`RESYNCING`), idempotent `RaceState.apply()`, Filter DSL (6 dimensions), `state.from_json`/`state.to_json`. Phase 4 re-exports these at the package root.
- `.planning/phases/03-transport-replay/03-CONTEXT.md` — D-01..D-04 (heartbeat & keepalive), D-05..D-08 (LTS_NOT_FOUND three-state policy), D-09..D-13 (reconnect backoff), D-14..D-17 (replay speed & time semantics), RecordingTransport composition pattern (REC-03), JsonlRecorder REC-02 runtime toggle
- `.planning/phases/03-transport-replay/03-DISCUSSION-LOG.md` — full audit trail of the Phase 3 design decisions including the D-EXC deferral

### Server protocol (reverse-engineering notes)

- `.planning/PROJECT.md` §Context — host `wss://livetiming.azurewebsites.net/`, channel PIDs 0/3/4/7/501/9002, payload keys, handshake shape `{eventId, eventPid, clientLocalTime}`, `{type:"time"}` time-sync prelude
- `src/aionlslivetiming/cli/jsonl_logger.py` — D-07 JSONL tee CLI; the body is the seed for `cli/record.py` (same DEFAULT_HOST, DEFAULT_CHANNELS, handshake shape). The new `cli/record.py` will be a near-verbatim copy with renames.
- `src/aionlslivetiming/parser/channels.py` — `EVENT_PID_*` integer constants; reused in `cli/record.py` if not already extracted to `transport/_defaults.py`
- `src/aionlslivetiming/transport/base.py` — `Transport` Protocol, `ClockOffset`, `LTSNotFoundEvent`, `ReconnectPolicy` (all public types Phase 4 re-exports)
- `src/aionlslivetiming/transport/websocket.py` — `LiveTransport`, `LTSNotFoundPolicy` (D-23 will update which exception is raised for `reason="unknown_event"`)
- `src/aionlslivetiming/transport/replay.py` — `ReplayTransport` with `speed_factor` / `suppress_time_sync` (D-15 surface for `nls-replay`)
- `src/aionlslivetiming/transport/recorder_wrapper.py` — `RecordingTransport` (composition, not subclass — REC-03)
- `src/aionlslivetiming/transport/recorder.py` — `JsonlRecorder` with `set_enabled(bool)` runtime toggle (REC-02)
- `src/aionlslivetiming/exceptions.py` — Phase 3's preliminary hierarchy; D-23 finalizes names
- `src/aionlslivetiming/state/race_state.py` — `RaceState` with `apply()`, idempotency contract, `source`, `freshness` (Phase 4 client wraps this per D-08)

### External references

- `https://keepachangelog.com/en/1.1.0/` — CHANGELOG format (D-17)
- `https://packaging.python.org/en/latest/specifications/declaring-project-metadata/` — PyPI metadata checklist (D-28)
- `https://www.mkdocs.org/` — mkdocs config reference (D-15)
- `https://mkdocstrings.github.io/` — mkdocstrings usage (D-15)
- `https://squidfunk.github.io/mkdocs-material/` — mkdocs-material theme reference (D-15)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- **`src/aionlslivetiming/cli/jsonl_logger.py::run()`** — D-07 JSONL tee CLI body. The new `cli/record.py::run()` is a near-verbatim copy with renames. Constants `DEFAULT_HOST` and `DEFAULT_CHANNELS` already defined here; copy or extract to `transport/_defaults.py` during Phase 4 (planner's call).
- **`src/aionlslivetiming/transport/__init__.py`** — already exports `Transport`, `LiveTransport`, `ReplayTransport`, `RecordingTransport`, `JsonlRecorder`, `ReconnectPolicy`, `LTSNotFoundPolicy`, `LTSNotFoundEvent`, `ClockOffset`. Phase 4 `client.py` imports these directly.
- **`src/aionlslivetiming/state/__init__.py`** — exports `RaceState`, `Filter`, `Freshness`, `Source`, `CarState`, `LapRecord`, `TrackState`. `NLSClient` composes `RaceState` (D-08).
- **`src/aionlslivetiming/exceptions.py`** — preliminary hierarchy (D-23 finalizes names; `LTSNotFoundError` and `ParseError` are new).
- **`src/aionlslivetiming/__init__.py`** — package root already re-exports the major Phase 1/2/3 types. Phase 4 adds `NLSClient` to this re-export.
- **`pyproject.toml` `[project.scripts]`** — currently has `aionlslivetiming-capture`. Replace with `nls-record` and `nls-replay` per D-01.
- **`pyproject.toml` `[project.optional-dependencies].dev`** — already has `pytest`, `pytest-asyncio`, `pytest-cov`, `respx`, `ruff`, `mypy`, `freezegun`. Add `mkdocs`, `mkdocs-material`, `mkdocstrings[python]`, `twine` per D-16, D-26.

### Established Patterns

- **`Source` enum lives on `RaceState`** (Phase 2 decision). `NLSClient.source` returns `client.state.source` — the enum belongs to state, the client surfaces it.
- **Transport Protocol is `runtime_checkable`** (Phase 3 D-09). `NLSClient` uses `isinstance(transport, Transport)` for defensive checks.
- **`Logging.getLogger("aionlslivetiming.<subpackage>")`** convention — Phase 4 CLI uses `aionlslivetiming.cli` and `NLSClient` uses `aionlslivetiming.client`.
- **`@dataclass(frozen=True, slots=True)` for events / pydantic for state** — D-18 CONTRIBUTING.md documents this; Phase 4 adds no new event classes (reuses Phase 1's 8).
- **Frozen dataclasses with `.raw` field** — Phase 1 pattern; the recorder tees `.raw` directly without losing schema-drift fields.

### Integration Points

- `NLSClient.__init__` accepts `transport=` directly — power-user escape hatch. Tests use this to inject mock transports.
- `NLSClient.from_replay()` class method — hides `ReplayTransport` construction. Internally builds the transport and calls the constructor with `transport=replay_t`.
- `RecordingTransport` is composition (Phase 3 D-13) — `NLSClient(record_to=path)` constructs `RecordingTransport(LiveTransport(...), JsonlRecorder(path))` internally. The recorder honors Phase 3 REC-02 runtime toggle (already wired).
- `RaceState.apply()` is idempotent (Phase 2 D-08) — safe for the client to apply every yielded Message without coordination.
- `pyproject.toml` `[project.scripts]` is the canonical console-script declaration point. Adding `nls-record` / `nls-replay` here means `uv sync` installs them to `.venv/bin/` automatically.

</code_context>

<specifics>
## Specific Ideas

- The **`record_to=` kwarg one-liner** (D-06) is a quality-of-life win. A user running `nls-record` to capture AND consume live in the same script is the common workflow for "let me see what just happened and save it." The two CLI paths (record-only via `nls-record`, record+consume via `NLSClient(record_to=...)`) are not duplicates — the CLI writes JSONL and exits; the client iterates forever.
- The **hard cut from `aionlslivetiming-capture` to `nls-record`** (D-02) is the right call because the library has never been published. Any churn would be wasted effort; any user who tried the D-07 tool already knows the project's status is alpha. The CHANGELOG entry (D-17 `### Removed`) is the only paper trail needed.
- The **three-stream iterator surface** (`messages()` / `time_sync()` / `lts_not_found()` — D-10) matches Phase 3's D-04 separation. This is intentional: a consumer that only wants race messages should never see `TimeSyncMessage` events polluting the loop. A consumer that wants time-sync (e.g., for clock-skew debugging) explicitly opts in via `client.time_sync()`.
- The **`LTSNotFoundEvent` (event) vs `LTSNotFoundError` (exception)** distinction (D-23) is a deliberate split: events are part of the normal data flow (the server told us the session ended); errors are raised only when the consumer opted in to strict mode. Consumers iterating `client.lts_not_found()` see events; consumers who don't opt in never see anything.
- The **filter walkthrough example uses a bundled sample JSONL** (D-22) so it's runnable on a fresh `git clone` with no live race and no pre-recorded log. This is the same pattern as the Phase 1 D-08 hand-crafted fixtures — small, committed, public test contract. The sample goes in `examples/data/` rather than `tests/fixtures/` because it's an example asset, not a test asset.
- The **slim README + docs/ tree split** (D-13, D-14) follows the FastAPI / Pydantic convention: README is the elevator pitch and install command (the PyPI landing page), docs are the long-form reference. PyPI's project description is set to the README's first paragraph; GitHub's repo page shows the full README.
- The **single source of truth for the exception list** is `src/aionlslivetiming/exceptions.py` (D-23). `__init__.py` re-exports the same names. Examples reference exceptions via `from aionlslivetiming import NLSError, ConnectionError, ...` — not by module path. This keeps the public API clean.

</specifics>

<deferred>
## Deferred Ideas

### Reviewed Todos (not folded)

None — `gsd-tools todo match-phase 4` returned zero matches.

### From discussion

- **HA integration example** — explicitly out of scope per PROJECT.md ("submitting to home-assistant/core — we ship a library; HA integration is a separate concern") and per v2 requirements HAI-01..03. Do not include an HA sensor example in the 3 worked examples.
- **Web UI / dashboard** — out of scope per PROJECT.md. The library is for downstream consumers; if a dashboard is wanted, that's a separate project.
- **`python -m aionlslivetiming` subcommand entry point** — not in DIST-05. The console scripts are the entry points. If a future phase wants `python -m aionlslivetiming record ...`, that's a new requirement.
- **GitHub Actions CI / release workflow** — no CI exists yet. The first PyPI release happens manually. Phase 4 closes when the artifact is buildable; release automation is a future phase if/when community contribution starts.
- **`clock_offset` API expansion** — D-11 ships a simple `.clock_offset_ms: float | None` property. A future phase could add clock-skew event callbacks, server-vs-local wall-clock formatters, etc. None of this is needed for v1.
- **PyPI trusted publishing setup** — separate concern from "publish-ready". Trusted publishing (via GitHub Actions OIDC) is a release workflow concern, not a packaging concern. Deferred to the first actual release.
- **File rotation for `JsonlRecorder`** — Pitfall #12 in PITFALLS.md. No user has hit the 100 MB / hour threshold yet. Recorder writes a single file; rotation belongs in a future phase if real-world recording demonstrates the need.
- **Telemetry / per-second car data** — out of scope per PROJECT.md ("Not published by the NLS livetiming service").
- **Multi-source clients** (v2 MULT-01..02) — explicitly deferred per REQUIREMENTS.md.

### Out of scope for this phase

- Actual PyPI publishing — Phase 4 ships a publish-ready artifact. First publish is a separate event outside this workflow.
- HA integration package — v2 HAI-01..03.
- Persistence beyond JSON/JSONL (SQLite, Parquet) — v2 PERS-01..02.

</deferred>

---
*Phase: 04-client-distribution*
*Context gathered: 2026-06-21*
