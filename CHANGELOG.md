# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
