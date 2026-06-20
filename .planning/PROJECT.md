# AIO NLS Livetiming API

## What This Is

An async-first Python client library for the official Nürburgring Langstrecken-Serie (NLS) livetiming service at `livetiming.azurewebsites.net`. It wraps the live WebSocket feed (multiplexed across result/track/messages/qualifying/statistics/per-car-lap channels) and the `/event/{id}/laps-data` HTTP endpoint, exposing a clean Python API that lets downstream projects (Discord bots, dashboards, Home Assistant integrations, analytics tools) consume NLS race data without reverse-engineering the site. The library works equally well in two modes: **live** (connected to a running race) and **replay** (driven from a recorded JSONL message log), so consumers can develop and test against historical races that are no longer reachable.

## Core Value

Downstream Python projects can subscribe to a running NLS race and get typed, filtered, cached race data (positions, lap times, sector times, pit messages, statistics) — live or replayed from a log — without ever touching the Azure WebSocket or the cryptic short-code JSON the server actually emits.

## Requirements

### Validated

- [x] Maintain a queryable cached state (current standings, per-car lap history, sector times, race messages, qualifying, statistics) — *Phase 02 (STATE-01..05)*
- [x] Filter the cached state by car class, starting number, driver, position range, lap range, and sector time — *Phase 02 (FILT-01..07)*
- [x] Clear and reset the in-memory cache on demand — *Phase 02 (STATE-05)*
- [x] Export the cached state and the recorded log to JSON / JSONL — *Phase 02 (STATE-06)*
- [x] Import state and logs from JSON / JSONL — *Phase 02 (STATE-07)*

### Active

- [ ] Connect to the NLS livetiming WebSocket and authenticate a session by event id
- [ ] Subscribe to all message channels (results, track state, race messages, qualifying, statistics, per-car laps)
- [ ] Decode the server's short-code JSON (`PID`, `EXPORTID`, `SESSION`, `CUP`, `HEAT`, `HEATTYPE`, `TRACKNAME`, `STQ`, `BEST`, `TOD`, `RESULT`, `LTS_NOT_FOUND`, etc.) into typed Python objects
- [ ] Expose a live event stream API (`async for msg in client.messages(): ...`)
- [ ] Maintain a queryable cached state (current standings, per-car lap history, sector times, race messages, qualifying, statistics)
- [ ] Filter the cached state by car class, starting number, driver, position range, lap range, and sector time
- [ ] Clear and reset the in-memory cache on demand
- [ ] Fetch per-car lap drilldown via `GET /event/{id}/laps-data?session=...&startingNo=...`
- [ ] Record the raw WebSocket message stream to a JSONL file (one parsed message per line) for later replay
- [ ] Replay a previously recorded JSONL log through the same API surface as a live connection
- [ ] Export the cached state and the recorded log to JSON / JSONL
- [ ] Import state and logs from JSON / JSONL
- [ ] Work as a drop-in async library for Home Assistant custom components (no HA-specific imports in the core package)
- [ ] Be community-friendly: clean public API, examples, type hints, MIT-licensed

### Out of Scope

- Submitting to home-assistant/core — we ship a library; HA integration is a separate concern
- Scraping the public NLS website (only the WebSocket + the public REST endpoint)
- Building a UI / web frontend
- Persistent storage beyond files (no DB requirement in v1)
- Predicting / forecasting race outcomes (only consume what the server publishes)
- Authentication against any logged-in NLS endpoints (the livetiming service is currently public)

## Context

**Reverse-engineering notes (from inspecting `leaderboard.e24a.bundle.js`, `lapsData.0179.bundle.js`, `vendor.aec0.bundle.js`, July 2026):**

- Host: `livetiming.azurewebsites.net` (Azure App Service, Express + IIS, no public config/strings API)
- WebSocket: `wss://livetiming.azurewebsites.net/` — a single multiplexed socket at the root, no path
- On `onopen`, client sends JSON handshake: `{ eventId, eventPid: <channel>, clientLocalTime, ...channelSpecificPayload }`
- Channels (called `eventPid` in the bundle):
  - `0, 4` — initial results + ongoing track state updates (results, positions, lap counts, sector times, gaps)
  - `3` — race control messages (pit, flags, penalties, sector bests)
  - `7` — per-car lap drilldown (subscribed with `{ session, startingNo }`)
  - `501` — top qualifying (pro / pro-am tables)
  - `9002` — statistics (leading laps, best laps, best sectors)
- Server messages are JSON with short keys. Initial state payload (PID `0`) carries `VER`, `EXPORTID` (event id), `SESSION`, `CUP`, `HEAT`, `HEATTYPE`, `TRACKNAME`, `STQ`, `BEST` (array of 4-tuples for best sector time + speed), `TOD` (time-of-day), `RESULT` (array of cars). PID `4` carries `TRACKSTATE`, `TIMESTATE`, `ENDTIME`, `TOD`. `LTS_NOT_FOUND` indicates the session is over or never started.
- `onmessage` first receives a `{ type: "time", value: <ms> }` time-sync message, then JSON payloads.
- A thin reconnection wrapper lives in the vendor bundle: 1s backoff, retries on codes 1000/1001/1005, exposes `onmessage`/`onopen`/`onclose`/`onerror`/`onreconnect`/`onmaximum`/`json`/`send`/`close`/`reconnect`/`open`.
- HTTP endpoint `/event/{id}/laps-data?session={n}&startingNo={n}` returns an HTML page (another SPA), not raw JSON — so per-car lap detail is best obtained by subscribing to channel `7` on the WebSocket.

**User research themes (from initial discovery):**
- The NLS livetiming is the only public race data feed for the series — no official public API
- The site is JS-rendered and not crawlable; community tooling wraps the WS
- The feed is only live during a race event — replay/log support is essential
- A Home Assistant integration is the primary motivation for picking async-first Python

**Known issues to address:**
- The server can drop messages during high-frequency updates; the cached state must converge idempotently
- Race sessions can change (qualifying → heat → race) — `SESSION` and `CUP` may shift, the client must handle that without crashing
- The site is not versioned — schema can change between seasons. Mitigate by versioning the parser internally and surfacing unknown PIDs as `UnknownMessage` rather than crashing.

## Constraints

- **Tech stack**: Python 3.10+, async-first, uses `websockets` and `aiohttp` (or `httpx` async) — no blocking I/O on the hot path
- **License**: MIT — community-friendly, consistent with the user's other open-source work
- **Home Assistant compatibility**: no HA-specific imports in the core package; pure stdlib + the listed third-party deps
- **Schema**: parsed from the JS bundle — must be tolerant of unknown fields and unknown PIDs
- **No data fabrication**: only expose data the server actually publishes

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Async-first Python | HA integration is the primary downstream; async is the natural fit for the WS | — Pending |
| Replay and live share one API surface | Live data is only available during the race; consumers want to develop/test against historical data without code branching | — Pending |
| JSONL for the recorder, JSON for state snapshots | JSONL matches the natural message-stream shape; JSON for state matches the server's payload shape | — Pending |
| All channels in v1 | User chose full coverage — every channel the server publishes should be reachable through the library | — Pending |
| Library only, not a HA integration | Keeps scope focused; HA integration is a thin wrapper that can be added later without changing this package | — Pending |
| Don't submit to home-assistant/core | Lower-friction release; community can adopt via HACS instead | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-20 after initialization*
