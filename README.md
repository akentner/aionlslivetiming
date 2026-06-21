# aionlslivetiming

Async-first Python client for the Nürburgring Langstrecken-Serie livetiming service.

[![PyPI](https://img.shields.io/pypi/v/aionlslivetiming.svg)](https://pypi.org/project/aionlslivetiming/)
[![Python](https://img.shields.io/pypi/pyversions/aionlslivetiming.svg)](https://pypi.org/project/aionlslivetiming/)
[![License](https://img.shields.io/pypi/l/aionlslivetiming.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-alpha-yellow.svg)](.planning/ROADMAP.md)

`aionlslivetiming` wraps the official NLS livetiming WebSocket feed at
`livetiming.azurewebsites.net` and exposes a clean async Python API. It works
equally well in two modes: **live** (connected to a running race) and
**replay** (driven from a recorded JSONL log). Downstream projects (Discord
bots, dashboards, Home Assistant integrations, analytics tools) consume NLS
race data without reverse-engineering the Azure WebSocket or the cryptic
short-code JSON the server actually emits.

## Installation

```bash
uv add aionlslivetiming
# or:
pip install aionlslivetiming
```

Requires Python 3.12+. No Home Assistant-specific dependencies; safe to
install anywhere.

## 60-Second Quickstart

### Live (5 lines)

```python
import asyncio
from aionlslivetiming import NLSClient

async def main():
    async with NLSClient(event_id="20") as client:
        async for msg in client.messages():
            print(msg)

asyncio.run(main())
```

### Replay (3 lines)

```python
from aionlslivetiming import NLSClient

async with NLSClient.from_replay("recording.jsonl") as client:
    async for msg in client.messages():
        print(msg)
```

### Filter (5 lines)

```python
async with NLSClient.from_replay("recording.jsonl") as client:
    async for _ in client.messages():
        pass  # populate state
    top3 = client.state.filter().by_position(lo=1, hi=3).cars()
    for car in top3:
        print(car.starting_no, car.driver)
```

### Recording

```bash
uv run nls-record 20 /tmp/event.jsonl
```

Captures a live race to JSONL for offline replay.

## Documentation

Full documentation: [docs/quickstart.md](docs/quickstart.md)

- [Quickstart](docs/quickstart.md) — full walkthrough (live + replay + record + filter)
- [Examples](examples/) — three worked examples
- [API Reference](docs/api/) — auto-generated from docstrings
- [Changelog](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md)
- [License](LICENSE) — MIT

## License

MIT — see [LICENSE](LICENSE).

## Acknowledgements

Race data is published by the
[Nürburgring Langstrecken-Serie](https://www.nuerburgring-langstrecken-serie.de/).
This library is a community wrapper; it is not affiliated with or endorsed
by the NLS organization.
