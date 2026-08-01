# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.2] - 2026-08-01

### Fixed
- Parser: PID 0 RESULT rows now accept both modern (`startingNo`,
  `position`, `class`, `driver`) and legacy (`STNR`, `POSITION`,
  `CLASSNAME`, `NAME`) field names. The live NLS feed uses the legacy
  shape — previous code dropped all fields because they didn't match
  the modern names, leaving every car with `starting_no=0`.
- Best lap time (`FASTESTLAP`) is parsed as `MM:SS.sss` display
  string and converted to milliseconds; previously the field was
  unparseable.
- PID 7 (per-car laps) accepts `STNR`/`SESSION` alongside
  `startingNo`/`session`; empty keep-alive frames no longer trigger
  the missing-field warning.

## [0.1.1] - 2026-08-01

### Fixed
- Parser: dispatcher in `parse()` now reads `raw["PID"]` as a fallback when
  `raw["eventPid"]` is absent. The NLS server's outgoing frames use the
  short key `PID` to identify the channel; the dispatcher was only checking
  `eventPid`, causing every real frame to fall through to `UnknownMessage`
  with `event_pid=-1`. Discovered while connected to a live 6h race event
  on 2026-08-01.

### Added
- `examples/live_tail.py` — connect to a live event and stream messages
  with periodic standings snapshots.

## [0.1.0] - 2026-06-21

### Added

- Initial release of `aionlslivetiming`
- Parser: 8 typed Message dataclasses (InitialState, TrackState, Race,
  PerCarLaps, Qualifying, Statistics, TimeSync, UnknownMessage) for PIDs
  0/3/4/7/501/9002
- State: idempotent `RaceState` with `Source` / `Freshness` enums and JSON
  snapshot persistence
- Filter DSL: composable filters across 6 dimensions (class, starting_no,
  driver, position, lap, sector_time_lt)
- Transport: `LiveTransport` (WebSocket + jittered reconnect + app-level
  keepalive), `ReplayTransport` (JSONL + speed_factor),
  `RecordingTransport` (composition wrapper), `JsonlRecorder` (async-isolated
  writer with runtime `set_enabled` toggle)
- HTTP: `fetch_laps_data` for `/event/{id}/laps-data` (HA-compatible httpx
  injection via the consumer's WebSession)
- `NLSClient` composition root with `messages()` / `time_sync()` /
  `lts_not_found()` iterators
- CLI: `nls-record` (live capture) and `nls-replay` (JSONL replay with
  `--speed` / `--limit` / `--strict` / `--summary`)
- Documentation: README, mkdocs-material site, 3 worked examples

### Changed

- None (initial release)

### Deprecated

- None (initial release)

### Removed

- `aionlslivetiming-capture` console script (replaced by `nls-record`)

### Fixed

- None (initial release)

### Security

- None (initial release)

[Unreleased]: https://github.com/akentner/aionlslivetiming/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/akentner/aionlslivetiming/releases/tag/v0.1.0
