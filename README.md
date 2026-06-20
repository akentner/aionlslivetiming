# AIO NLS Livetiming API

An async-first Python client library for the official Nürburgring Langstrecken-Serie (NLS) livetiming service at `livetiming.azurewebsites.net`. It wraps the live WebSocket feed and exposes a clean Python API for downstream projects (Discord bots, dashboards, Home Assistant integrations, analytics tools).

## Status

**Phase 1 of 4 complete** — Foundation (package skeleton + parser + 11 fixtures). See `.planning/ROADMAP.md` for the full plan.

## Installation

This project uses [uv](https://docs.astral.sh/uv/) as the single task
runner — no Makefile, no Taskfile, no second wrapper. uv manages the
virtualenv, resolves dependencies, and runs every development command
through it. Anything you can do with `pytest` / `ruff` / `mypy`, you
can do with `uv run pytest` / `uv run ruff` / `uv run mypy` without
activating the venv first.

```bash
# Install runtime + dev dependencies into .venv/
uv sync --extra dev
```

## Development

All commands assume `uv sync --extra dev` has been run once.

```bash
# Run tests
uv run pytest

# Lint
uv run ruff check src tests

# Format
uv run ruff format src tests

# Type-check
uv run mypy --strict src

# Coverage gate (fails build if <80% on parser/+events/)
uv run pytest --cov=aionlslivetiming --cov-report=term-missing
```

### Why no Taskfile / Makefile / Hatch scripts?

For a single-language Python library, uv + `pyproject.toml` is enough:

- `uv sync` reads `[project.optional-dependencies]` — one source of truth
- `uv run` resolves the tool inside the venv — no `activate` step
- `pyproject.toml` already carries `[tool.ruff]`, `[tool.mypy]`,
  `[tool.pytest.ini_options]` — no second config file to drift

A Taskfile would only earn its keep in a multi-language monorepo.

## License

MIT — see [LICENSE](LICENSE) (to be added in Phase 4).
