# Contributing

Thanks for your interest in contributing to `aionlslivetiming`!

## Development setup

```bash
git clone https://github.com/akentner/aionlslivetiming
cd aionlslivetiming
uv sync --extra dev
```

## Test / lint / typecheck

```bash
uv run pytest            # run the test suite
uv run pytest --cov      # with coverage
uv run ruff check src tests
uv run ruff format src tests
uv run mypy --strict src
```

## Architectural rules

- **Events are stdlib `@dataclass(frozen=True, slots=True)`** — the parser
  layer produces dataclasses with `event_pid: ClassVar[int]` discriminators
  and a `raw: Mapping[str, Any]` field that preserves unknown server keys.
- **State/filter models are pydantic v2** — `RaceState`, `CarState`,
  `LapRecord`, `TrackState`, and the `Filter` DSL all use pydantic.
- **Exceptions live in `src/aionlslivetiming/exceptions.py`** — single
  source of truth; `__init__.py` re-exports the same names.

## Adding a new Message variant

1. Add the typed dataclass in `src/aionlslivetiming/events/<pid>.py` (or
   extend an existing one if the variant is for a known PID).
2. Add a parser in `src/aionlslivetiming/parser/<pid>.py`.
3. Register the parser in the dispatcher in
   `src/aionlslivetiming/parser/__init__.py` (the `parse()` function uses
   `match/case` on the PID).
4. Add a hand-crafted fixture JSON in `tests/fixtures/`.
5. Add per-class tests in `tests/test_events_dataclasses.py` and
   `tests/test_parser_<pid>.py`.

## Capturing live data for fixture material

```bash
uv run nls-record 20 /tmp/event.jsonl --max-seconds 30
```

Use the resulting JSONL as the seed for new fixtures. Filter out any
personally identifying information (driver names, team names) before
committing fixture data.

## PR expectations

- Tests for any new public surface
- `mypy --strict` passes
- `ruff check` passes
- Coverage remains ≥ 80% (the `pyproject.toml` gate)
- One commit per logical change
