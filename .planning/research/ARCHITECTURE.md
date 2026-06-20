# Architecture Research — AIO NLS Livetiming API

**Domain:** Async-first Python client library for a single multiplexed WebSocket feed + one HTTP endpoint
**Researched:** 2026-06-20
**Confidence:** HIGH (design follows established asyncio patterns + reverse-engineered server schema)

---

## Executive Summary

The library's job is to turn an opaque, multiplexed, short-coded WebSocket feed into typed Python objects with a queryable cache, while *also* being drivable from a JSONL log. The architecture below is built around one core insight:

> **The transport is replaceable; the parser and cache are not.**

Live WebSocket and JSONL replay must produce *the same* `Message` objects flowing into *the same* handlers. Everything else (connection management, reconnection, time-sync, recording) lives at the edges and feeds that core pipeline.

The design is a 5-layer pipeline with strict downward dependencies:

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Public API  (NLSLivetimingClient)                                       │
│   - async for msg in client.messages()                                   │
│   - client.state.standings(), client.state.laps(car)                    │
│   - client.record(path), client.replay(path)                            │
├──────────────────────────────────────────────────────────────────────────┤
│  Events  (typed Message hierarchy: ResultState, TrackState, ...)          │
│   - frozen dataclasses, fully serializable to JSON                       │
├──────────────────────────────────────────────────────────────────────────┤
│  State  (RaceState: per-car dicts, message list, qualifying, stats)      │
│   - idempotent .apply(msg) — replays and re-sends converge               │
│   - synchronous queries (no event loop dependency)                       │
├──────────────────────────────────────────────────────────────────────────┤
│  Parser  (parsers/*, dispatcher by eventPid)                              │
│   - pure functions: raw dict → typed Message                             │
│   - no I/O, no state, fully unit-testable                                 │
├──────────────────────────────────────────────────────────────────────────┤
│  Transport  (WebSocketTransport | ReplayTransport)                        │
│   - yields parsed Messages (transport wraps parser)                      │
│   - records to JSONL when configured                                     │
└──────────────────────────────────────────────────────────────────────────┘
```

Every layer below a given layer is replaceable; every layer above it does not care how it was sourced. This is the **inverted dependency direction** that makes replay free.

---

## Recommended Package Structure

`src/` layout (PEP 660 / setuptools auto-discovery; clean separation from tests):

```
src/aionlslivetiming/
├── __init__.py                # Public API surface — re-exports the 3 things users import
├── client.py                  # NLSLivetimingClient — top-level orchestrator
├── exceptions.py              # NLSError, ConnectionError, ParseError, SchemaError
│
├── transport/
│   ├── __init__.py
│   ├── base.py                # Transport protocol (abstract): connect, messages(), close
│   ├── websocket.py           # LiveTransport — websockets client + reconnect + time-sync
│   ├── replay.py              # ReplayTransport — reads JSONL, sleeps to real-time or faster
│   └── recorder.py            # RecordingTransport wrapper — delegates to inner transport, tee-saves
│
├── parser/
│   ├── __init__.py            # parse(payload: dict) -> Message  — dispatcher
│   ├── channels.py            # Channel IDs (EventPid): RESULT=0, TRACK=4, MESSAGE=3, ...
│   ├── initial_state.py       # PID 0 — full results + best sectors + track info
│   ├── track_state.py         # PID 4 — TRACKSTATE / TIMESTATE / ENDTIME / TOD updates
│   ├── messages.py            # PID 3 — race control messages (pit/flags/penalties)
│   ├── per_car_laps.py        # PID 7 — per-car laps drilldown (session+startingNo scoped)
│   ├── qualifying.py          # PID 501 — top qualifying
│   ├── statistics.py          # PID 9002 — leading/best laps, best sectors
│   ├── time_sync.py           # {type:"time", value:ms} protocol message
│   └── unknown.py             # UnknownMessage fallback (forward-compat)
│
├── events/
│   ├── __init__.py            # Message union type + isinstance helpers
│   ├── common.py              # BestSector, TimeOfDay, SessionInfo (shared embedded types)
│   ├── initial_state.py       # InitialStateMessage (frozen dataclass)
│   ├── track_state.py         # TrackStateMessage
│   ├── race_message.py        # RaceMessage (pit/flag/penalty — text + type)
│   ├── per_car_laps.py        # PerCarLapsMessage
│   ├── qualifying.py          # QualifyingMessage
│   ├── statistics.py          # StatisticsMessage
│   └── time_sync.py           # TimeSyncMessage (server clock vs our clock)
│
├── state/
│   ├── __init__.py            # RaceState facade
│   ├── race_state.py          # RaceState — owns per-car maps, message log, idempotent apply()
│   ├── car.py                 # CarState — single car (positions, laps, sectors, bests)
│   ├── filters.py             # Filter DSL: by class, starting_no, position range, lap range
│   └── persistence.py         # export_json / import_json — RaceState ↔ JSON snapshot
│
├── http/
│   ├── __init__.py
│   └── laps_data.py           # Optional HTTP fallback for /event/{id}/laps-data (if WS fails)
│
├── recorder/
│   ├── __init__.py
│   ├── jsonl.py               # write_message() / read_messages() — pure I/O, no transport
│   └── log_format.py          # Line schema: {ts_recv_ms, event_pid, raw, parsed}
│
├── logging.py                 # get_logger(__name__) helper, structured `extra=` keys
└── version.py                 # __version__ = "0.1.0"

tests/
├── fixtures/
│   ├── messages/              # One .json file per (channel, scenario) — sample server payloads
│   │   ├── pid_0_initial_v54.json
│   │   ├── pid_0_initial_lts_not_found.json
│   │   ├── pid_4_track_state_running.json
│   │   ├── pid_4_track_state_finished.json
│   │   ├── pid_3_race_message_pit.json
│   │   ├── pid_3_race_message_flag.json
│   │   ├── pid_7_per_car_laps.json
│   │   ├── pid_501_qualifying.json
│   │   ├── pid_9002_stats.json
│   │   └── time_sync.json
│   └── recordings/            # Captured JSONL sessions from real races (committed samples)
│       └── nls1_2025-04-05_sample.jsonl
│
├── test_parser_*.py           # One per parser module — pure dict-in / dataclass-out
├── test_state_apply.py        # Idempotency: applying same message N times = applying once
├── test_state_filters.py      # Filter DSL coverage
├── test_state_persistence.py  # export → import → equality
├── test_recorder_roundtrip.py # write JSONL → read JSONL → equal to original
├── test_replay_determinism.py # ReplayTransport against fixture JSONL produces expected state
└── test_websocket_smoke.py    # Live WS test, marked @pytest.mark.live, skipped in CI

examples/
├── live_listen.py             # Subscribe + print messages as they arrive
├── dump_to_jsonl.py           # Record a session to disk
├── replay_offline.py          # Replay a JSONL through full client API
└── dashboard_demo.py          # Standings table refreshed on each track-state update
```

### Structure Rationale

- **`src/` layout** — prevents accidental imports from the repo root; well-supported by setuptools, hatchling, uv. Greenfield, no reason to do flat layout.
- **One module per channel in `parser/`** — each reverse-engineered payload has its own quirks; splitting makes each testable in isolation and makes it obvious where to add the next unknown PID.
- **`events/` mirrors `parser/`** — every parsed dataclass lives in a module that namesakes its parser. Imports stay one-to-one.
- **`state/` is independent of `transport/` and `parser/`** — it only depends on `events/`. This is the load-bearing wall for testability and replay.
- **`recorder/` is its own package** — JSONL line format is a public contract (people will want to inspect logs with `jq`), so it deserves a stable home.

---

## Component Boundaries

| Component | Responsibility | Talks To | Notes |
|---|---|---|---|
| `NLSLivetimingClient` | Public facade — owns lifecycle, exposes `messages()`, `state`, `record()` | transport, state, recorder | Single user-facing class. Created via `async with` or factory. |
| `Transport` (protocol) | "Give me a stream of `Message` objects until close." Async-iterable. | parser (wraps it), recorder (teed from it) | **One interface, three implementations.** |
| `LiveTransport` | Open WebSocket, handshake, reconnect loop, time-sync, dispatch raw frames to parser | parser, recorder (optional wrapper), time-sync logic | Holds the `websockets.WebSocketClientProtocol` and reconnect state. |
| `ReplayTransport` | Read JSONL file, decode lines, drive the same parser path | parser, recorder (none — it's already a recording) | Optional `speed_factor` (1.0 = real-time, 0 = burst). |
| `RecordingTransport` | Wraps an inner transport; tees every message to JSONL | inner transport, recorder | Composes — `LiveTransport(RecordingTransport(...))` works the same way round. |
| Parser dispatcher | `parse(raw_dict) -> Message` | `parser/*` modules | Single entry point used by every transport. **Pure** — no I/O. |
| Per-channel parsers | Convert raw dict for one `eventPid` to a typed dataclass | `events/*` dataclasses | Each is a pure function: `def parse_pid_0(raw: dict) -> InitialStateMessage`. |
| `Message` (events) | Frozen dataclasses describing one server update | parser, state, transport | Immutable; safe to share between coroutines without locking. |
| `RaceState` | Queryable snapshot: standings, laps, messages, qualifying, stats. Idempotent `.apply(msg)` | events, filters, persistence | **Synchronous** once messages are in — no `async` on the read path. |
| `CarState` | One car — position, laps, sector bests, total time, last pit | state.race_state | Mutated in-place by `apply()`; safe because writes happen on a single asyncio task. |
| Filter DSL | Composable predicates: `class=`, `starting_no=`, `position <=`, `lap >=` | state.race_state | Returns a list, not a generator — easier to test and serialize. |
| Recorder (JSONL) | Append-only file of `{ts_recv_ms, event_pid, raw, parsed}` per line | transport (tee), user (read) | One JSON object per line; `parsed` field is optional but huge for debugging. |

### Boundary Rules (Enforced by Reviews, Not Types)

1. **`events/` and `parser/` import nothing from `transport/`, `state/`, or `client/`.** They are leaf modules.
2. **`state/` imports only from `events/`.** Not from `parser/`, not from `transport/`. The cache only knows about typed messages, never raw dicts.
3. **`transport/` imports from `parser/`** (to dispatch raw → typed) **and `events/`** (return type), but **never from `state/`**. State lives at the application layer, not the transport layer.
4. **`client.py` is the only module that imports all four** — it is the composition root.

This creates a clear testability gradient: anything in `parser/`, `events/`, or `state/` can be unit-tested without an event loop. Only `transport/` and `client.py` need `pytest-asyncio`.

---

## Data Flow

### Live Path

```
WSS frame (bytes)
    │
    ▼
[LiveTransport._reader_task]
    │  json.loads → raw dict (or time-sync dict)
    ▼
[RecordingTransport._tee]  ─────────►  JSONL file (optional)
    │
    ▼
[Parser dispatcher.parse(raw)]   ────  UnknownMessage on unknown PID (logged, not crashed)
    │
    ▼
[Typed Message dataclass]
    │
    ├──► [client.messages() async iterator]     # user-facing event stream
    │
    └──► [RaceState.apply(msg)]                 # idempotent cache update
              │
              ▼
         [user queries: client.state.standings(), .laps(no), .best_sectors()]
```

### Replay Path

```
JSONL file line
    │
    ▼
[ReplayTransport._reader]
    │  json.loads → line dict → take .raw → same parser
    ▼
[Parser dispatcher.parse(raw)]   ◄── IDENTICAL to live path
    │
    ▼
[Typed Message dataclass]        ◄── IDENTICAL to live path
    │
    ├──► [client.messages()]      ◄── IDENTICAL surface
    │
    └──► [RaceState.apply(msg)]   ◄── IDENTICAL state mutation
```

The convergence is not an accident — it's why the parser dispatcher is *the* chokepoint.

### Cache Convergence Semantics

`RaceState.apply(msg)` MUST be idempotent. Concretely:

- `InitialStateMessage` (PID 0) → reset cars to the new `RESULT` array, replace `BEST`, `TRACKNAME`, etc. Re-sending the same PID 0 produces the same state.
- `TrackStateMessage` (PID 4) → update position/lap of one car, or set `TRACKSTATE`/`TIMESTATE`. Re-sending the same update is a no-op.
- `RaceMessage` (PID 3) → append to message log. Re-sending would duplicate — so each message carries a server-assigned sequence id (or we hash `(text, timestamp)`) and dedup on insert.
- `PerCarLapsMessage` (PID 7) → keyed by `(session, starting_no, lap_no)`; last write wins.
- `StatisticsMessage` (PID 9002) → keyed by `metric_id`; last write wins.

This is the property that makes replay into a JSONL of a *live* session produce exactly the same state as the live session did. It is also the property that lets the WebSocket drop messages during a network blip without corrupting the cache once the next snapshot arrives.

---

## Architectural Patterns

### Pattern 1: Protocol-Driven Transport (Dependency Inversion)

**What:** Define `Transport` as a `typing.Protocol` (or `abc.ABC`) with `async def connect()`, `def __aiter__() -> AsyncIterator[Message]`, `async def close()`. `LiveTransport` and `ReplayTransport` are both implementations.

**When:** Whenever the same logical "source of messages" can come from more than one place, and consumers mustn't care which.

**Trade-offs:**
- ✅ Replay is essentially free (one small class, ~80 lines)
- ✅ Future: `MockTransport` for fuzz tests, `MultiplexTransport` that merges several sessions, `FileTailTransport` that follows a growing log
- ✅ Tests for `RaceState` and the public API can run against `ReplayTransport` with fixture JSONL — no live server needed
- ❌ One indirection — slight reading cost for newcomers

**Example:**
```python
# transport/base.py
from typing import AsyncIterator, Protocol
from aionlslivetiming.events import Message

class Transport(Protocol):
    async def connect(self) -> None: ...
    def __aiter__(self) -> AsyncIterator[Message]: ...
    async def close(self) -> None: ...
```

### Pattern 2: Composition Over Inheritance (Recording = Wrapper, Not Subclass)

**What:** `RecordingTransport(inner: Transport, file: Path)` delegates `connect`, iteration, and `close` to the inner transport. On each `__anext__`, it writes the message to JSONL before yielding. No subclassing of `LiveTransport` or `ReplayTransport`.

**When:** Cross-cutting concerns that apply to multiple implementations (recording, metrics, retry, etc.).

**Trade-offs:**
- ✅ `Live + Recording`, `Replay + Recording`, `Live + Recording + Metrics` all compose without explosion
- ✅ Recording can be added/removed at runtime by swapping the transport wrapper
- ❌ Slight overhead per message (one extra `await file.write()` per message) — but for a human-timescale feed this is invisible

**Example:**
```python
# transport/recorder.py
class RecordingTransport:
    def __init__(self, inner: Transport, recorder: JsonlRecorder) -> None:
        self._inner = inner
        self._rec = recorder

    async def connect(self) -> None:
        await self._inner.connect()

    async def __aenter__(self): await self.connect(); return self
    async def __aexit__(self, *a): await self.close()

    def __aiter__(self) -> AsyncIterator[Message]:
        return self._iter()

    async def _iter(self) -> AsyncIterator[Message]:
        async for msg in self._inner:
            await self._rec.append(msg)  # append-only JSONL write
            yield msg

    async def close(self) -> None:
        await self._inner.close()
        await self._rec.close()
```

### Pattern 3: Tagged Union of Frozen Dataclasses for Events

**What:** `Message` is a `Union[InitialStateMessage, TrackStateMessage, RaceMessage, PerCarLapsMessage, QualifyingMessage, StatisticsMessage, TimeSyncMessage, UnknownMessage]`. Each is a `@dataclass(frozen=True, slots=True)`. An `event_pid: int` field on the base — actually, on each variant as a `ClassVar` — drives isinstance dispatch.

**When:** You have a small, fixed-ish set of message shapes arriving on one channel.

**Trade-offs:**
- ✅ `isinstance(msg, InitialStateMessage)` is fast and refactor-friendly
- ✅ Frozen + slots = cheap to create, safe to share across coroutines, hashable (good for dedup)
- ✅ Each variant can be matched exhaustively with `match`/`case`
- ❌ Adding a new channel means a new dataclass — but this is what we want; it forces an explicit decision

**Example:**
```python
# events/initial_state.py
from dataclasses import dataclass
from typing import ClassVar

@dataclass(frozen=True, slots=True)
class InitialStateMessage:
    event_pid: ClassVar[int] = 0
    ver: str
    export_id: str            # event id
    session: str
    cup: str
    heat: str
    heat_type: str
    track_name: str
    best: tuple[BestSector, ...]
    time_of_day: str
    results: tuple[CarResult, ...]
    raw: Mapping[str, Any]     # forward-compat: keep the original payload
```

The `raw` field on every variant is the **schema insurance policy**. When the server adds a field we don't know about, callers can still reach it without us having shipped a new release.

### Pattern 4: Idempotent Reducer-Style State

**What:** `RaceState.apply(msg: Message) -> None` is a pure mutation of internal maps, indexed by stable keys (`starting_no`, `(session, starting_no, lap_no)`, `metric_id`, message `seq`). Reapplying the same message produces the same state.

**When:** The data source is allowed to drop, duplicate, or reorder messages (network blips, reconnects, replays).

**Trade-offs:**
- ✅ Live drops + reconnect snapshots converge automatically
- ✅ Replay is deterministic — same JSONL → same final state, every time
- ✅ State queries (`state.standings()`) are pure synchronous reads — fast, no event loop contention
- ❌ Some messages (like `RaceMessage`) need a dedup key derived from the payload — small extra work in the parser

### Pattern 5: Pure-Function Parser Dispatcher

**What:** `parse(raw: dict) -> Message` is a single function that does `match raw.get("type"):` for time-sync, then `match raw.get("eventPid"):` and routes to the right per-channel parser. Each per-channel parser is also a pure function.

**When:** The schema is reverse-engineered and may evolve; you want unit tests on every channel shape.

**Trade-offs:**
- ✅ Every channel parser is testable with a JSON fixture — no live server, no mocks
- ✅ Unknown PID = `UnknownMessage(raw=raw, event_pid=X)` — graceful degradation, no crash
- ✅ Adding a new channel is one new file + one match arm
- ❌ Slight overhead vs. inline parsing — negligible at message rate of ~10/sec

---

## Public API Surface

`__init__.py` re-exports only what downstream code needs:

```python
from aionlslivetiming import (
    NLSLivetimingClient,        # the one class
    Message,                    # for type hints
    InitialStateMessage,
    TrackStateMessage,
    RaceMessage,
    PerCarLapsMessage,
    QualifyingMessage,
    StatisticsMessage,
    TimeSyncMessage,
    UnknownMessage,
    RaceState,                  # exposed so users can inspect/filter without going through client
    NLSError,                   # base exception
    ConnectionError,
    ParseError,
    SchemaError,
    Transport,                  # Protocol for type hints on custom transports
    LiveTransport,
    ReplayTransport,
    RecordingTransport,
    JsonlRecorder,
)

__version__ = "0.1.0"
```

The public API follows these rules:

1. **Anything not in `__init__.py` is private.** Modules inside the package can be rearranged freely between minor versions.
2. **Frozen dataclasses with `slots=True`** — instances are part of the contract.
3. **The client is the only thing you `await`.** Everything state-related is synchronous (after `async for msg in client.messages(): ...`, the state is already current).

---

## Suggested Build Order (Phase Dependencies)

This is the single most important question for the roadmap. Build bottom-up so each phase is verifiable against the layers below it.

### Phase 0 — Project Skeleton
- `pyproject.toml`, `src/` layout, empty modules, CI that runs `pytest` on empty test suite
- **Why first:** Nothing builds without packaging. Establishes the test scaffolding all later phases use.

### Phase 1 — `events/` + `parser/` + parser fixtures
- All 8 dataclasses, all 8 parser modules, `parser/__init__.py` dispatcher, ~20 fixture JSONs in `tests/fixtures/messages/`
- **Why first:** Pure functions, zero I/O, no asyncio. Highest unit-test coverage, no flaky tests, fastest feedback loop. **Every other phase depends on having typed messages.**
- **Verifies:** Each `parse(raw_fixture).field == expected_value`. Unknown PID produces `UnknownMessage`.

### Phase 2 — `recorder/jsonl.py`
- `JsonlRecorder.append(msg)`, `read_messages(path) -> AsyncIterator[Message]`
- **Why second:** Pure file I/O + serde of frozen dataclasses. Depends only on `events/`. Enables fixture JSONL generation (Phase 3) and round-trip testing.

### Phase 3 — `state/` (RaceState, CarState, filters, persistence)
- `RaceState`, `CarState`, filter DSL, `export_json` / `import_json`
- **Why third:** Depends on `events/` only. Can be tested entirely by constructing `Message` instances in tests and asserting on state. **No transport, no parser, no I/O** in tests — these are the fastest tests in the suite.
- **Verifies:** Idempotency: `apply(msg); apply(msg) == apply(msg)`. Filter correctness. Persistence round-trip.

### Phase 4 — `transport/base.py` + `transport/replay.py`
- Protocol + `ReplayTransport(path)`. Reads JSONL via the recorder from Phase 2, dispatches via parser from Phase 1, yields typed messages.
- **Why fourth:** The first transport implementation proves the protocol interface works. Tests use committed fixture JSONLs — no live server. **Validates that live and replay will share the API surface.**
- **Verifies:** `ReplayTransport` on a fixture JSONL produces expected messages. `RaceState` after replay equals hand-computed expected state.

### Phase 5 — `client.py` (public API + composition root)
- `NLSLivetimingClient` with `connect(event_id)`, `messages()`, `state`, `record(path)`, `replay(path)`, async context manager. Wires transport → parser → state.
- **Why fifth:** Everything it composes now exists. Tests use `ReplayTransport` for fully offline verification. **Live tests are gated behind `@pytest.mark.live`** and skipped in CI.
- **Verifies:** Full pipeline (JSONL → state) works. `async for msg in client.replay(...).messages()` yields same messages as the JSONL contains. `client.state.standings()` after replay equals expected table.

### Phase 6 — `transport/websocket.py` (LiveTransport)
- `websockets` connection, handshake JSON, reconnect loop with exponential backoff, time-sync (`{type:"time", value:ms}` → `TimeSyncMessage` → offset clock), dispatch raw frames to parser.
- **Why sixth:** The only phase with real I/O. Tested manually against `livetiming.azurewebsites.net` during a real race; in CI it's a `@pytest.mark.live` test that opens the socket and connects but does not assert on race-specific data (race may not be live).
- **Verifies:** Connection succeeds. Handshake ack received. Time-sync messages produce `TimeSyncMessage` events. Unparseable frames logged and skipped, not crashed.

### Phase 7 — `transport/recorder.py` (RecordingTransport wrapper)
- Wrap any transport, tee to JSONL. Composes `LiveTransport` with `JsonlRecorder`.
- **Why seventh:** Trivial code (~40 lines) once both pieces exist. **Verifies the whole design:** record live, replay later, get same state.
- **Verifies:** Live session → JSONL → replay → `RaceState` equality (modulo time-of-day clock differences).

### Phase 8 — HTTP laps-data fallback
- `http/laps_data.py` for the `/event/{id}/laps-data` endpoint. The PROJECT.md notes this returns an HTML SPA, so the fallback's real value is **documenting** it and providing a graceful 404 / "use channel 7" message rather than scraping. Mark as best-effort.
- **Why last:** Optional. The WebSocket already covers per-car laps via channel 7. HTTP is a fallback for when the WS subscription for channel 7 isn't possible (offline, before handshake).

---

### Dependency Diagram

```
                    ┌──────────────────┐
                    │   client.py      │
                    └────────┬─────────┘
                             │ uses
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
        ┌──────────┐  ┌──────────┐  ┌──────────────┐
        │ state/   │  │transport/│  │  recorder/   │
        │          │  │  replay  │  │              │
        └────┬─────┘  └─────┬────┘  └──────┬───────┘
             │              │              │
             ▼              ▼              ▼
                    ┌──────────────────┐
                    │  parser/         │  ← transport/websocket.py adds live I/O here
                    │  events/         │
                    └──────────────────┘
```

Built bottom-up: `events`+`parser` → `recorder` → `state` → `replay` → `client` → `websocket` → `recorder-wrapper`.

---

## Test Strategy (Testability Without a Live Server)

### Three Test Tiers

**Tier 1 — Pure unit tests (no event loop, no I/O, no fixtures bigger than a dict)**
- All parsers: `tests/test_parser_*.py`
- `RaceState.apply`, filters, persistence
- Total: hundreds of tests, run in <1 second, no network

**Tier 2 — Replay tests (no network, but reads JSONL files from disk)**
- `tests/test_recorder_roundtrip.py`: write messages → JSONL → read back → equal
- `tests/test_replay_determinism.py`: drive `ReplayTransport` over fixture JSONL → check state
- `tests/test_client_replay.py`: full client pipeline against fixture JSONL
- Total: dozens of tests, run in <5 seconds

**Tier 3 — Live tests (`@pytest.mark.live`, skipped in CI by default)**
- `tests/test_websocket_smoke.py`: connect, handshake, receive time-sync, receive *some* message
- `tests/test_recorder_live.py`: record 60s of a real race, then replay, then assert on state
- Run manually: `pytest -m live`

### Fixture Strategy

**`tests/fixtures/messages/`** — one JSON file per parser scenario. Captured from real sessions via the recorder, then scrubbed of personal data (driver names, team names) where the test doesn't need them. The minimum set covers:

- PID 0 — initial state, normal race
- PID 0 — initial state, `LTS_NOT_FOUND` (no session)
- PID 4 — track state transitions (GREEN → YELLOW → RED → CHEQUERED → FINISHED)
- PID 4 — `TIMESTATE` variants
- PID 3 — pit in, pit out, flag, penalty, sector best (each as one fixture)
- PID 7 — per-car laps, multi-lap, partial data
- PID 501 — qualifying, pro + pro-am
- PID 9002 — statistics, leading laps + best sectors
- Time-sync — sample time-sync frame
- Unknown PID — random PID, must produce `UnknownMessage`

**`tests/fixtures/recordings/`** — short (10–60s) captured JSONL sessions from real races, committed to the repo. Each is a "ground truth" sequence — replays of these must always produce the same final `RaceState`. A small assertion script can re-verify after any state-machine change.

### How the Parser Is Tested Without a Live Connection

The most important testability property of this design: **the parser dispatcher has no transport dependency**. Tests look like:

```python
# tests/test_parser_initial_state.py
import json
from pathlib import Path
from aionlslivetiming.parser import parse
from aionlslivetiming.events import InitialStateMessage

FIXTURES = Path(__file__).parent / "fixtures" / "messages"

def test_pid_0_initial_state_normal_race():
    raw = json.loads((FIXTURES / "pid_0_initial_v54.json").read_text())
    msg = parse(raw)
    assert isinstance(msg, InitialStateMessage)
    assert msg.event_pid == 0
    assert msg.ver == "54"
    assert msg.session == "R1"
    assert len(msg.results) > 0
    assert msg.track_name  # non-empty
```

No mocks, no monkeypatching, no event loop, no fake sockets. Just a JSON file and a function call. The same test runs on Python 3.10, 3.11, 3.12, 3.13, 3.14. It is fast (microseconds per test), deterministic, and gives 100% coverage of every parser branch simply by adding fixture files.

---

## Home Assistant Compatibility Notes

HA integration is a downstream consumer, but the library must be **drop-in usable** inside an HA `DataUpdateCoordinator`. Constraints:

- **No blocking I/O on the hot path.** All I/O uses `websockets` (asyncio-native) and `aiohttp` (asyncio-native). No `requests`, no `urllib.request`, no `open()` on the read path. JSONL recording is on a hot path too — it uses `aiofiles` or `asyncio.to_thread(open)` so the event loop never blocks on disk.
- **No HA imports in the core package.** `homeassistant.*` is forbidden in `src/aionlslivetiming/`. The HA integration lives in a separate repo (`akentner/aionlslivetiming-ha` or similar) and depends on this package.
- **Lifecycle is async-context-manager compatible.** `NLSLivetimingClient` is usable as `async with NLSLivetimingClient(...) as client:` — HA's `__aenter__` / `__aexit__` patterns work directly.
- **No top-level side effects on import.** Importing `aionlslivetiming` does not open sockets, read files, or create threads.
- **`getLogger("aionlslivetiming")`** is the logger name everywhere. HA picks it up for free and lets users configure verbosity.

The replay path is **especially** valuable for HA development: an HA integration under test can be driven from a recorded JSONL, which means HA test suites don't depend on a real race being live (they never do, in practice).

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Letting `Transport` Subclasses Know About `RaceState`

**What people do:** Make `LiveTransport` call `state.apply(msg)` directly, so it becomes "the thing that drives the cache."

**Why it's wrong:** Now `ReplayTransport` also has to drive the state, and they have to stay in sync. Any other consumer (a metrics exporter, a debug dumper) has to either subclass one of them or duplicate the dispatch logic.

**Do this instead:** Transports yield `Message` objects. The application layer (`NLSLivetimingClient` or any other consumer) decides what to do with them. `LiveTransport` does not import `state/`.

### Anti-Pattern 2: Storing Raw Dicts in `RaceState`

**What people do:** Keep the original `dict` from the server in `RaceState` "for flexibility."

**Why it's wrong:** State queries become `state.results[0]["driver_name"]` instead of `state.results[0].driver_name`. Type checkers can't help. `match`/`case` doesn't work. Serialization is implicit (just `json.dumps` the dict) and brittle (server adds a field, your "typed" state suddenly has a new key).

**Do this instead:** Typed dataclasses in `state/`, plus a `.raw` field on each dataclass for forward-compat. State queries go through typed attributes. The `.raw` field is the escape hatch, not the primary API.

### Anti-Pattern 3: Async-ifying `RaceState` Queries

**What people do:** Make `state.standings()` async "for consistency."

**Why it's wrong:** Queries become coroutines that have to be awaited. In HA `DataUpdateCoordinator._update()`, this means an extra `await` per coordinator cycle. Worse, it makes concurrent reads impossible without locks — and there's no reason for them: state is owned by one task.

**Do this instead:** `RaceState` is a plain Python object with synchronous read methods. Writes happen on the single consumer task. HA can call `client.state.standings()` from any context (sync code in HA's executor, or async code in the event loop) and get a list back.

### Anti-Pattern 4: Treating the Recorder as an Afterthought

**What people do:** "We'll add recording later — for now just print to console."

**Why it's wrong:** Recording is a debugging lifeline for a reverse-engineered protocol. If it's not part of the architecture from day one, you'll wish it was the first time a parsing edge case appears at 2am during a real race. And the *replay* path depends on the *recording* path's file format being stable.

**Do this instead:** Recorder is Phase 2 — before transport, before the client. File format is documented in `recorder/log_format.py` as the public contract. The first JSONL capture happens during the first live test.

### Anti-Pattern 5: Crashing on Unknown PIDs

**What people do:** `raise SchemaError(f"Unknown eventPid {pid}")` when a new PID shows up.

**Why it's wrong:** The site isn't versioned. New PIDs will appear between seasons. A consumer that crashes the day after a server change is useless to a Discord bot that's been running for months.

**Do this instead:** Unknown PID → `UnknownMessage(raw=raw, event_pid=pid)`. Logged at WARNING with the raw payload. Flows through the same pipeline. Users can filter it out or inspect it. The library never crashes on server evolution.

---

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---|---|---|
| `wss://livetiming.azurewebsites.net/` | `websockets.asyncio.client.connect` + async for | Single multiplexed socket, root path. |
| `https://livetiming.azurewebsites.net/event/{id}/laps-data` | `aiohttp.ClientSession.get` (optional, low-value) | Returns HTML SPA; channel 7 is preferred. |

### Internal Boundaries (Recap)

| Boundary | Communication | Considerations |
|---|---|---|
| `transport/websocket.py` → `parser/__init__.py` | Direct function call, sync `parse(raw)` | Hot path; must be O(message_size). |
| `transport/recorder.py` → `recorder/jsonl.py` | `await JsonlRecorder.append(msg)` | Append-only, line-buffered. Crash-safe (fsync on flush). |
| `parser/*` → `events/*` | Direct constructor calls | Pure — no I/O, no logging on the happy path. |
| `client.py` → `state/RaceState` | `state.apply(msg)` from a single asyncio task | State is owned by the reader task; no locking needed. |
| `client.py` → user code | `async for msg in client.messages()` and `client.state.*` | Async iterator + sync queries. |

---

## Scaling Considerations

This library has only one scale axis worth thinking about: **message rate**. The feed publishes roughly 1–20 messages per second during a typical race. There is no horizontal scaling concern; the consumer is a single asyncio process.

| Concern | At 10 msg/sec | At 100 msg/sec | At 1000 msg/sec |
|---|---|---|---|
| Parser CPU | Negligible | Negligible | Negligible (microseconds per message) |
| State memory | ~50 cars × ~50 fields = trivial | Same | Same |
| JSONL recording | Negligible I/O | `aiofiles` handles it | Move to batched flush |
| Replay determinism | Perfect | Perfect | Perfect |

**First bottleneck (if ever):** JSONL write throughput on slow disks (SD cards in some HA hosts). Mitigation: batch writes with a `flush_every_ms` config, or write to `/dev/shm` and copy on shutdown. Not needed for v1.

**No scaling concerns affect the architecture.** This is a single-process, single-consumer library and should stay that way.

---

## Edge Cases the Architecture Must Handle

These are concrete behaviors the design must preserve; each falls out naturally from the patterns above but is worth calling out:

1. **Late-arriving `InitialStateMessage` (PID 0) after track updates have been applied** — the idempotent reducer handles this: PID 0 is treated as a snapshot replacement, not a delta. Already-converged cars with newer data will be reset to the snapshot, then subsequent PID 4 deltas bring them current. Race is brief, gap is tiny, behavior is correct.
2. **Network reconnect mid-race** — the reconnect loop in `LiveTransport` just opens a new socket. The new PID 0 arrives within ~1s and resets the state. Any messages missed during the gap are recovered.
3. **Session change mid-feed (qualifying → race)** — `SESSION`/`CUP` shift is just a field on `InitialStateMessage`. Consumers detect the shift via the new value.
4. **Replay with corrupted JSONL line** — `ReplayTransport` logs WARNING, skips the line, continues. The recorder must also handle this on the read side so a partial write doesn't break replay.
5. **Channel 7 (per-car laps) arrives before any PID 0** — `RaceState.apply` should buffer or create placeholder car entries. The per-car laps message must carry enough info to associate with a car (it does: `(session, startingNo)`).
6. **Concurrent `client.state.standings()` calls** — safe. `RaceState` reads are pure dict lookups + list comprehensions. No locks.
7. **`asyncio.CancelledError` during `async for msg in client.messages()`** — the client's `__aexit__` cleanly closes the transport, which closes the websocket, which cancels the reader task. No resource leaks.

---

## Sources

- [`websockets` asyncio client docs](https://websockets.readthedocs.io/en/stable/) — HIGH (official)
- [`aiohttp` client quickstart](https://docs.aiohttp.org/en/stable/client_quickstart.html) — HIGH (official)
- [Python `asyncio.Queue`](https://docs.python.org/3/library/asyncio-queue.html) — HIGH (official)
- [Python Packaging User Guide — src layout](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/) — HIGH (official)
- [HA Integration Manifest docs](https://developers.home-assistant.io/docs/creating_integration_manifest/) — HIGH (official; informed the HA-compat section)
- Internal reverse-engineering notes from `.planning/PROJECT.md` (server schema, channel IDs, handshake format) — HIGH (project-internal)

---

*Architecture research for: AIO NLS Livetiming API (aionlslivetiming)*
*Researched: 2026-06-20*