# aionlslivetiming

Async-first Python client for the [Nürburgring Langstrecken-Serie](https://www.nuerburgring-langstrecken-serie.de/) livetiming service.

## What is this?

`aionlslivetiming` wraps the official NLS livetiming WebSocket feed at
`livetiming.azurewebsites.net` and exposes a clean async Python API. It
works equally well in two modes: **live** (connected to a running race)
and **replay** (driven from a recorded JSONL log).

## Installation

```bash
uv add aionlslivetiming
```

Requires Python 3.12+.

## Quickstart

See the [Quickstart](quickstart.md) for a full walkthrough.

## Examples

- [Live quickstart](examples/live_quickstart.py)
- [Replay offline](examples/replay_offline.py)
- [Filter walkthrough](examples/filter_walkthrough.py)

## License

MIT — see [LICENSE](https://github.com/akentner/aionlslivetiming/blob/main/LICENSE).
