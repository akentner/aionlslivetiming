# Stack Research

**Domain:** Async-first Python client library (WebSocket + REST consumer, Home Assistant friendly)
**Project:** aionlslivetiming — Python client for `livetiming.azurewebsites.net` NLS livetiming
**Researched:** 2026-06-20
**Confidence:** HIGH (all versions verified against PyPI/HA core on this date)

---

## Executive Summary

The recommended stack is the **same set of dependencies Home Assistant core itself uses** (`aiohttp`, `httpx`, `pydantic`, `websockets`, `orjson`, `typing-extensions`), plus `pytest-asyncio` for tests and `hatchling` + `ruff` + `mypy` for packaging. HA core pins these exact versions in `homeassistant/package_constraints.txt`, which is the strongest possible signal that the stack is production-stable and HA-friendly — adopting HA's pinned versions guarantees no version-float pain when consumers wrap this library into an HA custom component.

Two design decisions deserve emphasis:

1. **`websockets` for the multiplexed WS feed + `httpx` for the one REST endpoint** — NOT `aiohttp.ClientSession` for both. `websockets` is purpose-built (zero deps, Python ≥3.10, explicit handshake control), and `httpx` is the modern sync/async HTTP client with first-class HA integration (`create_async_httpx_client`). Sharing `aiohttp` for both would force one oversized dependency and lose HA's recommended `httpx` injection pattern.
2. **`pydantic` v2 for the typed domain model** — NOT `dataclasses` alone, NOT `msgspec`. The domain model is small but the parser must tolerate unknown fields and unknown PIDs (`UnknownMessage` fallback), which `BaseModel.model_config = ConfigDict(extra="allow")` makes trivial. `msgspec` is faster but its stricter schema-first design is the wrong shape for "tolerate anything, version internally". `dataclasses` alone would force hand-rolled validation.

Python baseline: **`>=3.12`** (matches PROJECT.md's "Python 3.10+", but documented minimum raised to 3.12 because `pydantic` v2.13 + `httpx` 0.28 + `websockets` 16 all comfortably support 3.12, and 3.12 is the LTS that HA consumers are most likely to have). HA core itself is moving to 3.14 — supporting 3.12 keeps the library importable in older HA installs while leaving headroom.

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | `>=3.12,<3.15` | Runtime | 3.12 is widely deployed in HA/consumer environments, 3.13 is current LTS, 3.14 is what HA core dev requires; cap before 3.15 for forward-compat safety. (`typing.Annotated`, `typing.ParamSpec`, structural pattern matching all available.) |
| `websockets` | `>=15.0.1,<17` | Multiplexed WebSocket client (channel ids 0, 3, 4, 7, 501, 9002) | Purpose-built, zero runtime deps, Python ≥3.10, supports explicit handshake (`send` after `recv` from `time` control message), automatic ping/pong, clean reconnection patterns. HA core pins `websockets>=15.0.1` — version-aligned with the host that will consume us. The `websockets` library is the right choice over `aiohttp.ClientSession.ws_connect` because the NLS server emits a handcrafted `{type:"time",value:ms}` prelude that the dedicated client exposes cleanly via `await ws.recv()`. |
| `httpx` | `>=0.28,<0.29` | One-shot async HTTP for `/event/{id}/laps-data` (laps drilldown) | Modern async-first, HTTP/2-capable, type stubs built in, and — critically — HA core provides `create_async_httpx_client(hass)` in `homeassistant.helpers.httpx_client` (Platinum rule "WebSession Injection" expects this). Adopting `httpx` makes a future HA integration a 5-line wrapper. Also note: HA's policy says "ensure pydantic version does not float", so pinning matters. |
| `pydantic` | `==2.13.4` | Typed domain model + parser validation | Pydantic v2 (Rust core, fast), `extra="allow"` handles unknown server fields gracefully (per PROJECT.md pitfall: "schema can change between seasons. Mitigate by … surfacing unknown PIDs as UnknownMessage"). `model_config = ConfigDict(extra="allow", populate_by_name=True)` is the natural fit. HA core pins the exact same version. |
| `orjson` | `>=3.11,<4` | Fast JSON (de)serialization for log recording | HA core uses it for JSON throughput (over `stdlib json`). Useful for the JSONL recorder/replayer hot path; the server emits high-frequency updates and `orjson` is ~5–10× faster than `stdlib.json`. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `typing-extensions` | `>=4.15,<5` | Backport newer typing features | Required for `typing.Annotated` metadata on 3.10–3.11; harmless on 3.12+. HA pins the same range. |
| `attrs` | `>=26.1,<27` | Lightweight class helpers | Useful for internal state dataclass-style objects that don't need full pydantic validation (e.g., internal mutable cache). Already in HA core deps — no extra cost. |
| `python-dateutil` | `>=2.9` | Parse `TOD` (time-of-day) and `ENDTIME` fields the server emits | The server emits bespoke timestamp formats (`{ type: "time", value: <ms> }`, plus `TOD`/`ENDTIME` race-clock strings); `dateutil.parser.isoparse` and `datetime.fromtimestamp` cover both. |

### Development Tools

| Tool | Version | Purpose | Notes |
|------|---------|---------|-------|
| `hatchling` | `>=1.30,<2` | PEP 621 build backend | Stdlib-backed, no `setup.py`, no Poetry lockfile drama, mature env matrix (`hatch run test.py3.12` etc.). Preferred over `poetry-core` (Poetry 2.x lockfile is fine but heavier) and `setuptools` (legacy). |
| `uv` | `>=0.11` | Local dev / CI / publish | Drop-in `pip`/`pip-tools`/`venv`/`pipx` replacement, 10–100× faster resolution, built-in `uv build`/`uv publish`, handles Python version pinning via `.python-version`. Strong fit because the project will live alongside `ha-*` tooling. |
| `ruff` | `>=0.15` | Lint + format (replaces flake8, isort, black) | Single Rust binary, 100–1000× faster than the trio it replaces. Configure `[tool.ruff.lint]` with `select = ["E","F","W","I","UP","B","SIM","RUF","ASYNC"]` — the `ASYNC` rules are critical for an async-first library. |
| `mypy` | `>=1.1,<2.2` | Static type checking | First-class async support, `strict = true` in `[tool.mypy]`. Pair with `pydantic.mypy` plugin (Pydantic v2 ships one) so `model_validator` signatures don't confuse the checker. |
| `pytest` | `>=9.0` | Test runner | Current major; HA core also moved to 9.x. Use `pytest-asyncio` (below) for async tests. |
| `pytest-asyncio` | `>=1.4,<2` | Run async tests | `asyncio_mode = "auto"` in `pyproject.toml` keeps test files clean. Pair with `pytest-cov` for coverage. |
| `pytest-cov` | `>=7,<8` | Coverage reporting | Drives the coverage gate. |
| `respx` | `>=0.23` | Mock `httpx` calls in tests | First-party `httpx` mock. Use `respx_mock.get(...)` for the REST endpoint. |
| `freezegun` | `>=1.5` | Freeze time for replay tests | For replaying JSONL logs with deterministic timestamps. |

---

## Library Comparison: websockets vs aiohttp (for the WS), pydantic vs dataclasses vs msgspec (for the model)

### WebSocket client

| Library | Verdict | Rationale |
|---------|---------|-----------|
| **`websockets` 16.x** | **RECOMMENDED** | Zero deps, Python ≥3.10, explicit handshake support, automatic ping, mature reconnect patterns in docs (https://websockets.readthedocs.io/en/stable/howto/patterns.html). HA core itself uses it (`websockets>=15.0.1` in constraints). |
| `aiohttp` 3.14 (using `ClientSession.ws_connect`) | OK, secondary | HA core uses aiohttp everywhere, and it's already pulled in transitively if HA is the consumer. But it couples WebSocket handling to the HTTP session lifetime and the API surface for handshake/control messages is less ergonomic. The PROJECT.md reverse-engineering notes specifically describe the JS bundle's `onmessage`/`onreconnect` API — `websockets` maps to that 1:1. |
| `websocket-client` | Avoid | Sync-first, awkward async story, not on HA core's pinned list. |

### Data modeling / parsing

| Library | Verdict | Rationale |
|---------|---------|-----------|
| **`pydantic` 2.13.x** | **RECOMMENDED** | `extra="allow"` handles unknown fields, JSON Schema emission aids debugging, `model_validator(mode="before")` is perfect for the server's short-code JSON (PID 0/4/3/7/501/9002 fan-in to a single parse entrypoint). HA core pins `pydantic==2.13.4` — version-aligned. |
| `dataclasses` + `cattrs` | OK if avoiding pydantic | Lower dependency footprint, but you reimplement `extra="allow"`-style tolerance, JSON serialization, and validation. Not worth the complexity for this domain. |
| `msgspec` 0.21.x | Overkill / wrong fit | msgspec is brilliant for hot-path deserialization against a strict schema, but the NLS schema changes between seasons and the parser must accept "unknown" gracefully. msgspec's strict `Struct` mode fights that requirement. msgspec would shine only if the project became a high-QPS data pipeline. |
| `pydantic` v1 | Avoid | EOL'd by upstream (v2 stable since 2023); HA core is firmly on v2. Mixing v1 and v2 in one ecosystem causes needless friction. |

### HTTP client

| Library | Verdict | Rationale |
|---------|---------|-----------|
| **`httpx` 0.28.x** | **RECOMMENDED** | Async-first, sync-capable, HTTP/2, type stubs, HA core provides `create_async_httpx_client` — perfect for future WebSession injection (Platinum rule). |
| `aiohttp.ClientSession` | Acceptable fallback | Already in HA core; would work. Loses the `httpx`-friendly integration story. Choose this only if HA integration is firmly off the table — but PROJECT.md explicitly names HA as a downstream. |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `asyncio.run_coroutine_threadsafe` / manual event-loop juggling | The library is async-first; mixing sync + async causes the exact problems `websockets`/`httpx` already solved | Stay on `asyncio` end-to-end, expose `async def` API only |
| `requests` / `urllib3` | Sync, blocking — would freeze the event loop on the WS hot path | `httpx` (async mode) |
| `aiohttp` *also* as WS client | Two WS implementations in one library is dead weight; doubles the API surface | `websockets` (single-purpose) |
| `pydantic` v1 | EOL by upstream, conflicts with HA core | `pydantic` v2 |
| `msgspec` | Schema-strict design fights the "tolerate unknown" requirement | `pydantic` v2 with `extra="allow"` |
| `setup.py` + `setuptools` | PEP 517/621 prefers declarative `pyproject.toml`; setuptools is legacy for greenfield libraries | `hatchling` |
| `poetry-core` as build backend | Fine, but heavier and slower than `hatchling`; user already has `uv` for env mgmt | `hatchling` + `uv` |
| `black` + `isort` + `flake8` trio | Three tools, three configs, slow | `ruff` (one binary, replaces all three) |
| `python-dateutil` for hot-path timestamp math | Overkill for simple `datetime` ops | stdlib `datetime` + only import `dateutil.parser` where needed |
| `dataclasses-json` | Adds a layer that pydantic already covers | `pydantic` v2 `model_dump_json()` |
| `websockets` < 15 | Old API surface, before async iteration improvements | `websockets>=15.0.1` |
| `aiohttp` < 3.10 | Older versions, missing current async improvements and HTTP/2 support; HA core uses 3.14.1 | `aiohttp>=3.14,<4` (if you need it; we don't, httpx covers HTTP) |

---

## Stack Patterns by Variant

**If you primarily target Home Assistant consumers (default per PROJECT.md):**
- Use `httpx` (not `aiohttp`) so the HA integration can call `homeassistant.helpers.httpx_client.get_async_client(hass)` and satisfy the Platinum WebSession-Injection rule
- Match HA's pinned versions exactly: `pydantic==2.13.4`, `httpx==0.28.x`, `websockets>=15.0.1`, `orjson==3.11.x`, `typing-extensions>=4.15,<5`
- Document an integration recipe in the README showing the HA wrapping pattern

**If you only care about generic async Python users:**
- The above is still fine; nothing HA-specific is in the core package
- Drop the version pin on `pydantic` to `>=2.13,<3` for more flexibility

**If you ever add a CLI entry point:**
- `typer` (>=0.12) is the modern click-replacement; built-in `rich` integration for progress bars during replay

**If the recorder/replayer becomes I/O-bound at scale:**
- `aiofiles` for non-blocking file I/O when writing JSONL line-by-line (currently stdlib `open()` in thread would also work; profile first)

---

## Installation

The project will ship a `pyproject.toml` (PEP 621) with this dependency layout:

```toml
# Runtime dependencies (in [project].dependencies)
dependencies = [
    "websockets>=15.0.1,<17",
    "httpx>=0.28,<0.29",
    "pydantic==2.13.4",
    "orjson>=3.11,<4",
    "typing-extensions>=4.15,<5",
    "python-dateutil>=2.9",
]

# Dev dependencies (in [project.optional-dependencies].dev)
[project.optional-dependencies]
dev = [
    "pytest>=9.0",
    "pytest-asyncio>=1.4,<2",
    "pytest-cov>=7,<8",
    "respx>=0.23",
    "freezegun>=1.5",
    "ruff>=0.15",
    "mypy>=1.1,<2.2",
    "pydantic[mypy]==2.13.4",
]
```

For local development (user's machine has `uv` 0.11.23 installed):

```bash
# Install + create venv + resolve
uv sync --extra dev

# Run tests
uv run pytest

# Lint + format
uv run ruff check .
uv run ruff format .

# Type-check
uv run mypy src/

# Build wheel + sdist
uv build

# Publish (CI-driven in real life)
uv publish
```

---

## Version Compatibility Matrix

| Package | Pinned To | Compatible With | Notes |
|---------|-----------|-----------------|-------|
| `websockets>=15.0.1,<17` | HA pins `>=15.0.1` | Python `>=3.10` | Current latest 16.0; HA allows it. |
| `httpx>=0.28,<0.29` | HA pins `==0.28.1` | Python `>=3.8` | `0.28.1` is current stable; do not float. |
| `pydantic==2.13.4` | HA pins exactly | Python `>=3.9` | **Critical**: HA comment in `package_constraints.txt` says "ensure pydantic version does not float since it might have breaking changes" — pin exactly. |
| `orjson>=3.11,<4` | HA pins `==3.11.9` | Python `>=3.10` | No breaking changes within 3.11.x in practice; float safe but exact pin matches HA. |
| `typing-extensions>=4.15,<5` | HA pins `>=4.15.0,<5.0` | Python `>=3.8` | HA explicitly caps at 5.0. |
| `hatchling>=1.30,<2` | — | Python `>=3.10` | Build backend, not runtime. |
| `pytest-asyncio>=1.4,<2` | — | Python `>=3.10` | `1.x` API is stable; `2.x` is a major bump worth waiting for. |
| Python `>=3.12,<3.15` | HA core dev branch is `>=3.14.2` | — | Library targets 3.12+ so older HA installs can still vendor it. |

### Known Compatibility Considerations

- **`pydantic` exact pin is non-negotiable.** HA core's `package_constraints.txt` carries the literal comment: *"ensure pydantic version does not float since it might have breaking changes."* If we float pydantic, a future HA update can break us. Pin exactly to `2.13.4`.
- **`httpx` 0.28 dropped Python 3.7/3.8 support** — fine for us since baseline is 3.12.
- **`websockets` 16 removed the deprecated `loop` parameter** — make sure any internal code uses the modern `asyncio.run()` / implicit-loop API.
- **HA Core may pull `aiohttp` 3.14 transitively.** Even if our library only requires `httpx`, an HA integration will have both. No action needed, just don't *also* list `aiohttp` as a runtime dep.
- **Don't add `aiohttp` as a direct dependency.** If a future feature genuinely needs it (e.g., serving a local dashboard), re-evaluate then. Carrying it now is dead weight.

---

## Confidence Assessment

| Area | Confidence | Reason |
|------|------------|--------|
| Library versions | HIGH | All versions verified against PyPI JSON API on 2026-06-20; HA core `package_constraints.txt` cross-checked for the libs HA itself pins. |
| WebSocket library choice (`websockets`) | HIGH | Matches HA core's pinned dep; documented zero-dep API; first-class `await send`/`await recv` model fits the NLS handshake. |
| HTTP client choice (`httpx`) | HIGH | HA core's own `create_async_httpx_client` helper makes future HA integration frictionless. |
| Data model choice (`pydantic` v2) | HIGH | The `extra="allow"` + `model_validator` shape is exactly what tolerant-schema parsing needs; HA pins exact version. |
| Build backend (`hatchling`) | HIGH | Standard 2025/26 choice for greenfield PEP 621 libraries; `uv` ecosystem-aligned. |
| Python baseline (3.12+) | MEDIUM | PROJECT.md says "3.10+"; raising minimum to 3.12 is opinionated. Reversible — if 3.10 support matters to anyone, lower to `>=3.10` and keep `typing-extensions`. |
| `pytest-asyncio` `auto` mode | MEDIUM | Convenience choice; some teams prefer explicit `@pytest.mark.asyncio` on every test. Auto mode keeps test files clean. |
| Dev tool versions (`ruff`, `mypy`) | HIGH | Both are Astral-led projects, current stable, widely adopted in HA-adjacent code. |
| Avoiding `msgspec` | MEDIUM | Performance claims about msgspec are real, but the project domain (tolerant parser, not hot-path deserializer) doesn't benefit. Future pipeline work could revisit. |

---

## Sources

### Context7 / official documentation (HIGH confidence)
- **websockets** — `https://websockets.readthedocs.io/en/stable/intro/index.html` (Python ≥3.10, zero deps, API surface verified)
- **aiohttp** — `https://docs.aiohttp.org/en/stable/` (current version 3.14.1)
- **pydantic** — `https://docs.pydantic.dev/latest/` (version policy: pin to avoid float; v2.13.4 is current)
- **hatch** — `https://hatch.pypa.io/latest/intro/` (hatchling as build backend)
- **uv** — `https://docs.astral.sh/uv/` (project management, lockfile, build/publish)
- **pytest** — `https://docs.pytest.org/en/stable/` (Python 3.10+)

### PyPI JSON API (HIGH confidence, queried 2026-06-20)
- `websockets==16.0` (requires-python >=3.10)
- `httpx==0.28.1` (requires-python >=3.8)
- `aiohttp==3.14.1` (requires-python >=3.10) — not a direct dep, listed for awareness
- `pydantic==2.13.4` (requires-python >=3.9)
- `orjson==3.11.9` (requires-python >=3.10)
- `typing-extensions==4.15.0`
- `pytest==9.1.1` (requires-python >=3.10)
- `pytest-asyncio==1.4.0` (requires-python >=3.10)
- `pytest-cov==7.1.0`
- `hatchling==1.30.1` (requires-python >=3.10)
- `ruff==0.15.18`
- `mypy==2.1.0` (requires-python >=3.10)
- `anyio==4.14.0`
- `attrs==26.1.0`
- `structlog==26.1.0`
- `msgspec==0.21.1` (for comparison; not chosen)
- `uvloop==0.22.1` (not chosen — stdlib asyncio + uvloop not needed for a client lib)
- `exceptiongroup==1.3.1` (not needed — Python 3.12+ baseline has `ExceptionGroup` natively)
- `respx==0.23.1` (requires-python >=3.8)
- `freezegun==1.5.5`

### Home Assistant Core (HIGH confidence, queried 2026-06-20)
- `https://raw.githubusercontent.com/home-assistant/core/dev/pyproject.toml` — `requires-python = ">=3.14.2"`, `aiohttp==3.14.1`, `orjson==3.11.9`, `typing-extensions>=4.15.0,<5.0`, `voluptuous==0.15.2`
- `https://raw.githubusercontent.com/home-assistant/core/dev/homeassistant/package_constraints.txt` — `httpx==0.28.1`, `pydantic==2.13.4` (with explicit "do not float" comment), `websockets>=15.0.1`
- **Implication for our library:** baseline 3.12+ keeps the package importable in HA installs that lag the core branch (3.13 LTS) while the dev branch has already moved to 3.14.

### Python EOL schedule (MEDIUM confidence, from endoflife.date 2026-06-20)
- 3.10: EOL 2026-10-31 (still supported today, but not for long)
- 3.11: EOL 2027-10-31
- 3.12: EOL 2028-10-31 ← **good 3-year support window for our baseline**
- 3.13: EOL 2029-10-31
- 3.14: EOL 2030-10-31

### Project context
- `.planning/PROJECT.md` (line 73: "Python 3.10+, async-first, uses websockets and aiohttp (or httpx async)")
- Reverse-engineering notes (lines 45–59) describing the multiplexed WS and short-code JSON

---

*Stack research for: aionlslivetiming — async-first Python client library*
*Researched: 2026-06-20*