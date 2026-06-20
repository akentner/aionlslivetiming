# Project Research Summary

**Project:** aionlslivetiming — async-first Python client for the NLS livetiming WebSocket feed
**Domain:** Single-feed async client library (WebSocket consumer + JSONL replay), MIT, HA-friendly
**Researched:** 2026-06-20
**Confidence:** **HIGH** overall — stack and architecture are well-grounded in HA core conventions; server-specific risks (Azure idle timeout, undocumented schema) are MEDIUM because they rest on reverse-engineering.

---

## Executive Summary

**What this is.** An async Python library that wraps the undocumented, multiplexed WebSocket feed at `livetiming.azurewebsites.net` and exposes typed Python objects (`Message` dataclasses) flowing into a queryable `RaceState`. Live mode and replay-from-JSONL mode share one API surface — the transport is replaceable; the parser, events, and state are not. The closest comparator is **FastF1** (5.2k★, MIT) for F1 livetiming; we take FastF1's recording+replay idea but drop pandas, persistent cache, plotting, and multi-series scope, and add a single-client live+replay parity guarantee plus explicit export/import.

**The recommended approach.** Build bottom-up: pure-function `events/` + `parser/` first (zero I/O, fastest tests), then `recorder/jsonl.py`, then `state/` (idempotent reducer), then `transport/replay.py` (proves the protocol), then `client.py` (composition root), then `transport/websocket.py` (live), then `transport/recorder.py` wrapper (composes live + recording), then optional HTTP laps-data fallback. This order makes each phase verifiable against the layers below it without a live server — only the WebSocket phase needs `@pytest.mark.live`.

**Key risks and how to mitigate them.** (1) Azure App Service silently closes idle WebSockets after ~4 minutes — drive heartbeats from the server's `{type:"time",value:ms}` messages rather than relying on TCP keepalive. (2) Server can drop/duplicate messages and the protocol has no sequence numbers — make `RaceState.apply(msg)` idempotent from day one (the API contract, not a bolt-on). (3) Schema changes between seasons — every model carries an `extras: Mapping` field and unknown PIDs become `UnknownMessage`, never a crash. (4) The transport/hot-path must never block the event loop — `orjson` for serialization, dedicated `asyncio` task for JSONL writes, sync-only state queries. (5) HA event-loop blocking — the library must install and run with no `homeassistant.*` imports.

---

## Key Findings

### Recommended Stack

Versions align exactly with Home Assistant core's `package_constraints.txt` so this library drops cleanly into an HA custom component without version-float pain.

**Core technologies:**
- **Python `>=3.12,<3.15`** — 3.12 is the LTS HA consumers most likely to have; cap before 3.15 for forward-compat safety. `typing.Annotated`, structural pattern matching, `TaskGroup` all available.
- **`websockets>=15.0.1,<17`** — purpose-built zero-dep async WS client; handles the multiplexed NLS feed + explicit handshake (send after recv of the `{type:"time"}` prelude). Pinned to match HA core.
- **`httpx>=0.28,<0.29`** — modern async HTTP for the (optional) `/event/{id}/laps-data` fallback. Critical: HA core provides `create_async_httpx_client(hass)` for downstream injection.
- **`pydantic==2.13.4`** — exact pin (HA's "do not float" rule). `extra="allow"` + `model_validator(mode="before")` is exactly what tolerant reverse-engineered-schema parsing needs; lets `UnknownMessage` swallow unknown PIDs cleanly.
- **`orjson>=3.11,<4`** — 5–10× faster than stdlib `json` for the JSONL hot path. Make optional with stdlib `json` fallback to avoid breaking installs on musl/Alpine.
- **`hatchling>=1.30,<2`** + **`uv>=0.11`** + **`ruff>=0.15`** + **`mypy>=1.1,<2.2`** + **`pytest>=9.0`** + **`pytest-asyncio>=1.4,<2`** (auto mode) + **`respx>=0.23`** + **`freezegun>=1.5`** — modern greenfield toolchain.

**Explicitly NOT used:** `aiohttp` as a runtime dep (HA pulls it transitively; don't double-list), `pydantic` v1 (EOL), `msgspec` (strict-schema design fights "tolerate anything"), `requests`/`urllib3` (sync, blocks the loop), `dataclasses-json` (pydantic covers it), `poetry-core`/`setup.py` (hatchling + PEP 621 is the modern choice).

### Expected Features

**Must-have (table stakes — P1):**
- Async WebSocket connect + handshake by event id (T1)
- Per-channel subscribe for PIDs 0/3/4/7/501/9002 (T2)
- Typed decoder per short-code field, with `UnknownMessage` fallback for unknown PIDs (T3, T4)
- `async for msg in client.messages()` stream API (T5)
- Reconnect with exponential backoff + jitter (T6)
- Exception hierarchy (`NLSError`, `ConnectionError`, `ParseError`, `SchemaError`) (T7)
- In-memory queryable `RaceState` keyed by `starting_no`; idempotent `apply()` (T8)
- Per-car lap drilldown via channel 7 subscription (T9) — NOT the `/laps-data` HTTP endpoint, which returns an HTML SPA
- `async with` lifecycle (T10)
- Type hints throughout (T11)
- Record raw WS to JSONL (D1) + replay JSONL through the same API (D2, D8)
- Cache filter DSL by class/starting_no/position/lap (D3)
- Clear cache on demand (D6)
- Race-control event stream (D7) — typed projection of PID 3
- HA-friendly packaging: no `homeassistant.*` imports (D9)

**Should-have (P2):**
- CLI entry point: `python -m aionlslivetiming record <event_id> <file>` (T12)
- Structured logging via `logging.getLogger("aionlslivetiming")` (T13)
- Export/import state + log to JSON/JSONL (D4, D5)

**Defer (v2+):**
- Pandas `to_pandas()` adapter (only if a user requests it)
- Persistent file cache (NLS has no rate limits; in-memory is enough)
- Sibling libraries for WEC/IMSA (out of scope per PROJECT.md)
- Clock-synchronized replay modes
- Web dashboard / plotting / ML — explicitly anti-features for this library

**Anti-features to refuse outright:** pandas as the primary data type, pickle+sqlite persistent cache, F1TV-style auth flow, telemetry, Ergast-style REST wrapper, plotting, multi-series support, persistent DB backend, push notifications, web UI, ML prediction, sync wrapper class, fancy schema negotiation.

### Architecture Approach

A **5-layer pipeline with strict downward dependencies** — every layer above is replaceable from below; nothing above it cares how it was sourced.

```
Public API  (NLSLivetimingClient)        ← single facade: .messages(), .state, .record(), .replay()
Events      (typed Message hierarchy)     ← frozen dataclasses with raw field for forward-compat
State       (RaceState — idempotent)      ← synchronous reads, single asyncio-task writes
Parser      (pure functions, no I/O)      ← dispatcher + per-PID parsers, UnknownMessage fallback
Transport   (LiveTransport | ReplayTransport | RecordingTransport wrapper)
```

**Major components:**
1. **`Transport` protocol** — `async def connect()`, `__aiter__()`, `async def close()`. Three implementations: `LiveTransport` (real WS), `ReplayTransport` (JSONL), `RecordingTransport` (wraps either, tees to JSONL). Dependency-inversion principle: protocol in `transport/base.py`, implementations compose by composition, not inheritance.
2. **Parser dispatcher** — `parse(raw: dict) -> Message` dispatches on top-level shape first (`{type:"time"}` is the time-sync sentinel, separate branch), then `match raw["PID"]` to per-PID pure-function parsers. Each per-channel parser is one function, one fixture, one test.
3. **`RaceState`** — owns per-car maps, message log, qualifying, stats. `apply(msg)` is **idempotent and synchronous** (the load-bearing contract: live drops + replay both converge to the same state). Reads (`standings()`, `laps(no)`, `best_sectors()`) are pure dict lookups — safe to call from any context, no event loop needed.
4. **`events/` (Message hierarchy)** — `@dataclass(frozen=True, slots=True)` for `InitialStateMessage`, `TrackStateMessage`, `RaceMessage`, `PerCarLapsMessage`, `QualifyingMessage`, `StatisticsMessage`, `TimeSyncMessage`, `UnknownMessage`. Every variant carries `raw: Mapping[str, Any]` as the schema-insurance escape hatch.
5. **`NLSLivetimingClient`** — the only composition root. Owns the lifecycle, exposes `messages()` async iterator + sync `state` accessors + `.record(path)` / `.replay(path)` methods.

**Boundary rules (review-enforced):** `events/` and `parser/` are leaves (import nothing from `transport/`, `state/`, `client/`); `state/` imports only from `events/`; `transport/` imports from `parser/` and `events/` but never `state/`; only `client.py` imports everything.

### Critical Pitfalls

The top 7 pitfalls ranked by blast radius. Each is mapped to the phase that must prevent it.

1. **Azure App Service silently closes idle WebSockets (~4 min)** — drive heartbeats from the server's `{type:"time",value:ms}` messages; configure `websockets` with `ping_interval=None` and `close_timeout<5s`; distinguish 1006 idle close from real disconnect. **Phase: transport/websocket.**
2. **Time-sync messages leak into the race event stream** — dispatcher must branch on `{type:"time"}` *before* `PID` lookup; expose time-sync on a separate `time_sync()` iterator, not `messages()`. **Phase: parser.**
3. **Dropped/duplicate messages corrupt cache** — `RaceState.apply()` MUST be idempotent from day one (the public contract); key by stable tuples like `(session, starting_no, lap_no)`; expose `cache.freshness` (`FRESH`/`STALE`/`RESYNCING`) and call `clear()` on reconnect. **Phase: state + transport.**
4. **`LTS_NOT_FOUND` is three different conditions** — distinguish `not_yet_started` (backoff-retry), `ended` (terminal, allow replay-only), `unknown_event` (hard error). Make the policy configurable per consumer. **Phase: parser + transport.**
5. **Reconnect storms after Azure maintenance** — exponential backoff with full jitter, cap ~60s, per-process random initial offset; honor `Retry-After` if present; make policy a constructor parameter. **Phase: transport/websocket.**
6. **Blocking I/O on the event loop** — `orjson` for serialization; JSONL recorder runs on a dedicated `asyncio` task via `asyncio.Queue` between reader and writer; cache mutators are sync-only (no `await` allowed). **Phase: parser + recorder.**
7. **HA event-loop blocking / package install failures** — no `homeassistant.*` imports in core; `python_requires=">=3.12"`; make `orjson` optional with stdlib `json` fallback; mark package as `py.typed`. **Phase: distribution (last).**

**Other pitfalls worth knowing but lower-priority:** schema drift between seasons (`extras` field + `UnknownMessage`), cancellation safety in `messages()` iterator (proper `try/finally` + `aclose()`), file rotation for 8-hour weekends, memory growth across sessions (cache must be keyed by `session_id`), replay parity (surface `Source` enum `LIVE`/`REPLAY`/`IMPORTED`), stale cache after disconnect (`cache.freshness` signal).

---

## Implications for Roadmap

Based on the build order from ARCHITECTURE.md and the dependency graph in FEATURES.md, this is the recommended phase structure. Each phase is verifiable against the layers below it; only the WebSocket phase needs `@pytest.mark.live`.

### Phase 0: Project Skeleton
**Rationale:** Nothing builds without packaging. Establishes the test scaffolding (pytest-asyncio auto mode, ruff, mypy strict) all later phases reuse.
**Delivers:** `pyproject.toml` (PEP 621, hatchling, exact-version pins matching HA core), `src/` layout, empty modules, CI that runs `pytest` on an empty test suite.
**Addresses:** Stack decisions; nothing from FEATURES yet.
**Avoids:** Pitfall #15 (PyPI packaging) by setting `python_requires=">=3.12"` and `py.typed` from day one.

### Phase 1: `events/` + `parser/` + parser fixtures
**Rationale:** Pure functions, zero I/O, no asyncio. Highest unit-test coverage and fastest feedback loop. Every other phase depends on typed messages.
**Delivers:** 8 `@dataclass(frozen=True, slots=True)` Message variants; 8 per-PID parser modules; `parser/__init__.py` dispatcher (branches on `{type:"time"}` *before* PID); `UnknownMessage` fallback; ~20 fixture JSONs in `tests/fixtures/messages/`.
**Addresses:** T3 (typed decoder), T4 (unknown PID handling), T11 (type hints), D7 (race-message events).
**Avoids:** Pitfalls #2 (time-sync pollution), #9 (schema drift), #4 (session transitions via tolerant parsing).
**Research flag:** None — well-established pattern. Fixture JSONs can be hand-crafted from the reverse-engineering notes in PROJECT.md until a real session is captured.

### Phase 2: `recorder/jsonl.py`
**Rationale:** Pure file I/O + serde of frozen dataclasses; depends only on `events/`. Enables fixture generation and round-trip testing.
**Delivers:** `JsonlRecorder.append(msg)`, `read_messages(path) -> AsyncIterator[Message]`; line schema `{ts_recv_ms, event_pid, raw, parsed}` documented as the public contract.
**Addresses:** D1 (record to JSONL).
**Avoids:** Pitfall #12 (file rotation, partial-trailing-line handling) — design in from the start.
**Research flag:** None.

### Phase 3: `state/` (RaceState, CarState, filters, persistence)
**Rationale:** Depends only on `events/`. Can be tested entirely by constructing Message instances — no transport, no parser, no I/O. **The fastest tests in the suite.**
**Delivers:** `RaceState` with idempotent `apply(msg)`; `CarState` per car; filter DSL (`by_class`, `by_starting_no`, `by_position`, `by_lap_range`); `export_json` / `import_json` round-trip; `cache.freshness` (FRESH/STALE/RESYNCING).
**Addresses:** T8 (in-memory cache), T9 (per-car laps), D3 (filter DSL), D6 (clear cache), D4/D5 (export/import).
**Avoids:** Pitfalls #3 (idempotency is the *contract*), #11 (stale cache after reconnect), #13 (memory growth via session-keyed reset).
**Research flag:** **Yes — discuss filter API shape.** Method-on-cache (`client.cars(class_="AT")`) vs. builder-pattern query object (`cache.query().class_("AT")`) is an open design question.

### Phase 4: `transport/base.py` + `transport/replay.py`
**Rationale:** The first transport proves the protocol interface. Replay tests use committed fixture JSONLs — no live server. Validates that live and replay will share the API surface.
**Delivers:** `Transport` `typing.Protocol`; `ReplayTransport(path, speed_factor=1.0)`; ordering validation; partial-trailing-line handling with WARNING skip.
**Addresses:** D2 (replay), D8 (live+replay parity — proves the shape, doesn't yet add live).
**Avoids:** Pitfall #10 (replay parity — Source enum surfaced here).
**Research flag:** None.

### Phase 5: `client.py` (public API + composition root)
**Rationale:** Everything it composes now exists. Tests use `ReplayTransport` for fully offline verification of the full pipeline. Live tests gated behind `@pytest.mark.live`.
**Delivers:** `NLSLivetimingClient` with `connect(event_id)`, `messages()`, `state`, `record(path)`, `replay(path)`, async context manager. Wires transport → parser → state. The `__init__.py` re-exports the public surface.
**Addresses:** T1 (connect+handshake), T2 (per-channel subscribe — wired through), T5 (stream API), T7 (exception hierarchy), T10 (lifecycle).
**Avoids:** Pitfall #8 (cancellation safety — design `try/finally` into `messages()` from day one).
**Research flag:** None — composition only.

### Phase 6: `transport/websocket.py` (LiveTransport)
**Rationale:** The only phase with real I/O. Tested manually against `livetiming.azurewebsites.net` during a real race; CI smoke test opens the socket and connects (race may not be live, so no race-data assertions).
**Delivers:** `websockets` connection; handshake JSON; reconnect loop with exponential backoff + jitter; time-sync → `TimeSyncMessage`; `ping_interval=None` driven by app-level heartbeat from `{type:"time"}` messages; distinct 1006 vs. 1000/1001/1005 handling; `LTS_NOT_FOUND` three-way semantics.
**Addresses:** T6 (reconnect with backoff).
**Avoids:** Pitfalls #1 (Azure idle timeout), #5 (LTS_NOT_FOUND), #6 (reconnect storms), #14 (HA event-loop blocking).
**Research flag:** **Yes — this is the most research-heavy phase.** Azure App Service WS idle timeout behavior, `websockets` library `ping_interval`/`close_timeout` tuning, and the exact reconnect backoff curve all need a `/gsd-research-phase` spike. Recommend capturing at least one real JSONL during a live test session before this phase is "done".

### Phase 7: `transport/recorder.py` (RecordingTransport wrapper)
**Rationale:** Trivial once `LiveTransport` + `JsonlRecorder` exist. Verifies the whole design: record live, replay later, get same state.
**Delivers:** Composes any `Transport` with `JsonlRecorder`; ~40 lines; async-isolated writer task; rotation by size/time.
**Addresses:** D1 (live recording, completes what Phase 2 started with file I/O alone).
**Avoids:** Pitfall #7 (blocking I/O via async-isolated writer), #12 (file rotation).
**Research flag:** None — composition.

### Phase 8: HTTP laps-data fallback (optional)
**Rationale:** PROJECT.md notes `/laps-data` returns an HTML SPA, so the fallback's real value is **documenting** it and providing a clear "use channel 7 instead" error. Mark as best-effort.
**Delivers:** `http/laps_data.py` using `httpx`; gracefully fails over to a `NLSHttpFallbackUnavailable` exception with a helpful message.
**Addresses:** Active requirement "Fetch per-car lap drilldown via GET /event/{id}/laps-data" (degraded but documented).
**Avoids:** Pitfall #14 (no sync HTTP via `requests`).
**Research flag:** None — likely skipped or folded into Phase 6.

### Phase 9: Distribution & polish
**Rationale:** Final phase before PyPI release.
**Delivers:** `py.typed` marker; `orjson` optional with stdlib `json` fallback; README with HA wrapping example; CLI entry point `python -m aionlslivetiming record <event_id> <file>`; structured logging via `logging.getLogger("aionlslivetiming")`.
**Addresses:** T12 (CLI), T13 (structured logging), D9 (HA-friendly packaging).
**Avoids:** Pitfall #15 (PyPI packaging).
**Research flag:** None.

### Phase Ordering Rationale

- **Dependency-driven.** `parser/` and `events/` are leaves — they depend on nothing in the library and everything else depends on them. They come first because every other phase tests against typed `Message` objects.
- **Testability gradient.** Phases 1–4 are pure-Python unit tests with no asyncio. Phase 5 introduces `pytest-asyncio` for the client composition. Only Phase 6 needs `@pytest.mark.live` (skipped in CI). This keeps CI fast and green.
- **Bottom-up verification.** Each phase is verifiable against the layers below it. Phase 2 tests the recorder by feeding it dataclasses from Phase 1. Phase 3 tests state by feeding it dataclasses from Phase 1. Phase 4 tests replay by feeding it JSONL from Phase 2 + dataclasses from Phase 1. No live server is needed until Phase 6.
- **Risk-front-loading.** The pitfalls that are most expensive to retrofit (idempotency in cache, time-sync dispatch, `UnknownMessage` pattern, idempotent reducer for replay parity) are addressed in Phases 1–3 where the cost of change is lowest.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 3 (state):** filter API shape is an open design decision (method-on-cache vs. builder-pattern). Discuss with `/gsd-discuss-phase` before planning.
- **Phase 6 (websocket):** Most research-heavy phase. Azure App Service WS idle timeout, `websockets` library `ping_interval`/`close_timeout` tuning, exact reconnect backoff curve, and the `LTS_NOT_FOUND` three-way policy all warrant a `/gsd-research-phase` spike. Capture a real JSONL during a live session before declaring this phase done.

Phases with well-documented patterns (skip `/gsd-research-phase`):
- **Phase 0 (skeleton):** standard `pyproject.toml` + `src/` layout.
- **Phase 1 (parser/events):** established pattern (pydantic or dataclasses + dispatcher). Hand-craft fixtures from PROJECT.md reverse-engineering notes.
- **Phase 2 (recorder):** pure file I/O + serde. No research needed.
- **Phase 4 (replay):** composition of Phase 1 + Phase 2.
- **Phase 5 (client):** composition root. No novel design.
- **Phase 7 (recorder wrapper):** trivial composition (~40 lines).
- **Phase 9 (distribution):** standard `py.typed` + optional-dep fallback pattern.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | **HIGH** | All versions verified against PyPI + HA core `package_constraints.txt` on 2026-06-20. Pinned to exact-match HA versions where HA pins exactly. |
| Features | **HIGH** | Validated against FastF1 (5.2k★, MIT) as the primary comparator. Set maps 1:1 to PROJECT.md active requirements. |
| Architecture | **HIGH** | Standard async pipeline patterns; well-supported by `websockets`, `pydantic`, `orjson`. `Transport` protocol is textbook dependency inversion. |
| Pitfalls | **MEDIUM-HIGH** | Server-specific items (idle timeout, undocumented schema, LTS_NOT_FOUND three-way semantics) rest on reverse-engineering and Azure App Service experience. Transport/async/distro items are HIGH (well-documented Python + Azure behavior). |

**Overall confidence: HIGH.** The stack is anchored in HA core's pinned versions (the strongest possible signal), the architecture is a textbook async pipeline, and the features map cleanly to validated FastF1 patterns. The remaining MEDIUM risk lives entirely in the server-specific protocol behavior that will be confirmed (or refined) during Phase 6 with a live capture.

### Gaps to Address

These came up during research and should be resolved at the first `discuss-phase`, not now:

1. **Filter API shape** — method-on-cache (`client.cars(class_="AT")`) vs. builder-pattern query object (`cache.query().class_("AT").top(5)`). FEATURES.md notes both are reasonable. Decide in Phase 3's `discuss-phase`.
2. **Single-object name** — `NLSClient` (matches "client of the WS") vs. `NLSSession` (matches FastF1's `Session`). `NLSClient` is the recommended choice because it's a *client*, not a race session, and the same object drives replay.
3. **Recorder mode** — one client (`.record(path)` is a method that opens a file and tees) vs. separate `NLSRecorder` object. The user's "single API surface for live and replay" goal points to method-on-client. Confirm in Phase 5's `discuss-phase`.
4. **Cache layout** — single flat dict keyed by `(event_id, session)` vs. composed sub-caches (one per data type, FastF1's shape). Composed sub-caches (`RaceState.cars`, `RaceState.messages`, `RaceState.qualifying`, `RaceState.stats`) read more naturally; flat is simpler. Decide in Phase 3's `discuss-phase`.
5. **Public exception class names** — `NLSError` (matches PROJECT.md examples) vs. `AionlsError` (matches package name). Project examples consistently use the `NLS` prefix; lock in `__init__.py` exports.
6. **`Source` enum naming** — `LIVE`/`REPLAY`/`IMPORTED` (per PITFALLS.md #10) vs. simpler `Live`/`Replay`. Pick one and document the differences explicitly.
7. **LTS_NOT_FOUND default policy** — sensible defaults for "retry on not_yet_started, give up on ended" but expose as a constructor parameter so analytics vs. live-display consumers can override.

---

## Sources

### Primary (HIGH confidence)
- **Home Assistant core `package_constraints.txt`** — exact versions of `pydantic==2.13.4`, `httpx==0.28.1`, `websockets>=15.0.1`, `orjson==3.11.9`, `typing-extensions>=4.15,<5`. The strongest signal for stack stability.
- **Home Assistant core `pyproject.toml`** — `requires-python = ">=3.14.2"` on dev branch, `aiohttp==3.14.1`, etc.
- **`websockets` library docs** — `https://websockets.readthedocs.io/en/stable/` — `ping_interval`, `close_timeout`, async iteration, reconnect patterns.
- **Pydantic v2 docs** — `https://docs.pydantic.dev/latest/` — `extra="allow"`, `model_validator(mode="before")`, exact-version policy.
- **PyPI JSON API** — every pinned version verified on 2026-06-20.
- **FastF1 source** — `https://github.com/theOehrly/FastF1` (5.2k★, MIT, v3.8.3) and `https://docs.fastf1.dev/` — primary comparator for features, exception hierarchy, cache/filter patterns.
- **Python `endoflife.date`** — Python 3.10–3.14 EOL dates (3.12 EOL 2028-10-31).
- **PROJECT.md** — own reverse-engineering notes from inspecting `leaderboard.e24a.bundle.js`, `lapsData.0179.bundle.js`, `vendor.aec0.bundle.js` (server schema, channel IDs, handshake shape, `/laps-data` returning HTML).

### Secondary (MEDIUM confidence)
- **Azure App Service WebSocket idle timeout** — well-documented across MS docs and GitHub issues; 4-minute ARR-level timeout. Personal experience corroborates.
- **HA developer docs** — async-first integration patterns, event-loop blocking warnings, Python 3.12+ requirement.

### Tertiary (LOW confidence — needs validation)
- **NLS feed server-specific behavior** — channel counts, message shapes, `LTS_NOT_FOUND` three-way semantics all rest on reverse-engineering. Will be validated during Phase 6 with live captures.
- **`pydantic` exact pin rationale** — HA's "do not float" comment is authoritative; the risk that *we* will need to float is LOW but worth re-checking on each HA core release.

---

*Research completed: 2026-06-20*
*Ready for roadmap: yes*
