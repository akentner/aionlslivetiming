# Quickstart

## Live mode

Connect to a running race:

```python
import asyncio
from aionlslivetiming import NLSClient

async def main():
    async with NLSClient(event_id="20") as client:
        async for msg in client.messages():
            # msg is a typed Message dataclass (InitialStateMessage,
            # TrackStateMessage, RaceMessage, etc.)
            print(msg)

asyncio.run(main())
```

The `event_id` is the numeric identifier shown on the NLS livetiming website.
Visit `https://livetiming.azurewebsites.net/` to find the current event id.

## Replay mode

Replay a previously recorded JSONL log:

```python
from aionlslivetiming import NLSClient

async with NLSClient.from_replay("recording.jsonl") as client:
    async for msg in client.messages():
        print(msg)
```

`NLSClient.from_replay` hides the transport choice; the same `messages()` API
works for both live and replay.

## Recording

Capture a live race to JSONL via the `nls-record` CLI:

```bash
uv run nls-record 20 /tmp/event.jsonl
```

To stop at a specific time:

```bash
uv run nls-record 20 /tmp/event.jsonl --max-seconds 600
```

## Filtering

The cached state is queryable via the Filter DSL:

```python
async with NLSClient.from_replay("recording.jsonl") as client:
    # Populate the cache by iterating once
    async for _ in client.messages():
        pass

    # Top 3 positions
    top3 = client.state.filter().by_position(lo=1, hi=3).cars()

    # All SP9 class cars
    sp9 = client.state.filter().by_class("SP9").cars()

    # Cars faster than 1:30 in any sector
    fast = client.state.filter().by_sector_time_lt(90000).cars()

    # Compose multiple filters with AND
    sp9_top10 = (
        client.state.filter()
        .by_class("SP9")
        .by_position(lo=1, hi=10)
        .cars()
    )
```

See the [Filter walkthrough example](examples/filter_walkthrough.py) for
all six filter dimensions.

## Next steps

- Browse the [API reference](api/index.md) (auto-generated from docstrings)
- Try the [examples](https://github.com/akentner/aionlslivetiming/tree/main/examples)
- Read [CONTRIBUTING.md](https://github.com/akentner/aionlslivetiming/blob/main/CONTRIBUTING.md) to contribute
