# AIO NLS Livetiming API

An async-first Python client library for the official Nürburgring Langstrecken-Serie (NLS) livetiming service at `livetiming.azurewebsites.net`. It wraps the live WebSocket feed and exposes a clean Python API for downstream projects (Discord bots, dashboards, Home Assistant integrations, analytics tools).

## Status

**Phase 1 of 4 in progress** — Foundation (package skeleton + parser). See `.planning/ROADMAP.md` for the full plan.

## Installation

```bash
# From a fresh Python 3.12 venv
uv venv --python 3.12
source .venv/bin/activate
pip install -e ".[dev]"
```

Or with `uv`:

```bash
uv sync --extra dev
```

## Development

```bash
# Run tests
pytest

# Lint
ruff check src tests

# Format
ruff format src tests

# Type-check
mypy src
```

## License

MIT — see [LICENSE](LICENSE) (to be added in Phase 4).
