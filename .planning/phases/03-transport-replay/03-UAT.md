# Phase 3 UAT — Transport + Replay

## Goals

1. User can record a live NLS race to a JSONL file.
2. User can replay that JSONL through an identical API surface.
3. User can connect live to wss://livetiming.azurewebsites.net/ and receive typed Messages.
4. The `/event/{id}/laps-data` HTTP fallback gracefully handles HTML responses.

## Verification steps (run manually against the live Azure endpoint during a test session)

### Step 1: Live capture

```python
from aionlslivetiming import LiveTransport, RecordingTransport, JsonlRecorder

rec = JsonlRecorder("nls-1.jsonl")
live = LiveTransport("NLS-1")
async with RecordingTransport(inner=live, recorder=rec) as rt:
    async for msg in rt:
        print(msg)  # see InitialStateMessage, TrackStateMessage, RaceMessage, ...
        # Ctrl-C after a few seconds
```

Expected: typed Message instances stream out; `nls-1.jsonl` is fully written on Ctrl-C.

### Step 2: Replay

```python
from aionlslivetiming import ReplayTransport

async for msg in ReplayTransport("nls-1.jsonl", speed_factor=10.0):
    print(msg)
```

Expected: same messages as Step 1, 10x faster than real-time.

### Step 3: HTTP fallback (graceful degradation)

```python
import httpx
from aionlslivetiming.http import fetch_laps_data

async with httpx.AsyncClient() as client:
    try:
        data = await fetch_laps_data("NLS-1", client=client, session="R1", starting_no=7)
        print("got JSON:", data)
    except NLSHttpFallbackUnavailable as e:
        print("expected HTML response:", e)  # the server returns HTML — this is the documented failure mode
```

Expected: NLSHttpFallbackUnavailable raised with "use channel 7 instead" message.

## Smoke results

- [ ] Step 1 — recorded JSONL on disk after Ctrl-C
- [ ] Step 2 — same messages replay at 10x speed
- [ ] Step 3 — NLSHttpFallbackUnavailable with informative message

## Out-of-scope (Phase 4)

- NLSClient composition root
- CLI entry points (`nls-record` / `nls-replay`)
- README + API reference
- PyPI publish