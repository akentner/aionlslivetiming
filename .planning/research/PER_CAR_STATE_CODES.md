---
topic: per-car "State" column codes observed in NLS livetiming SPA
status: unverified-hypothesis
captured: 2026-06-20
source: user observation of https://livetiming.azurewebsites.net/events/20/results/ SPA
---

# Per-Car "State" Column Codes

The NLS livetiming SPA (`/events/{id}/results/`) renders a leaderboard with
a column labeled **"State"** whose values are short 1–2 character codes.
Observed set: `PI`, `F`, `I1`, `I2`, `I3`, `I4`.

## Hypothesised mapping

| Code | Meaning (unverified) | Confidence | Rationale |
|------|----------------------|------------|-----------|
| `PI` | Pit In (car entered pit lane) | medium | Standard pit-in code; pairs with the racing-style "Box, Box" race message; matches common motorsport short codes |
| `F` | Finished (car crossed finish line for the last lap) | medium-high | Single-letter, terminal state; consistent with NLS chequered-flag semantics |
| `I1` | Installation / In-lap 1 | medium | First of the pre-race installation laps |
| `I2` | Installation / In-lap 2 | medium | Second installation lap |
| `I3` | Installation / In-lap 3 | low-medium | Third installation lap (only some NLS rounds allow ≥3) |
| `I4` | Installation / In-lap 4 | low | Fourth installation lap (rare) |

## Why we believe these but haven't proven them

- **NLS/VLN tradition**: NLS events typically allow 2 installation laps
  before the rolling-start formation; 3–4 are occasionally permitted for
  longer races (e.g. 6h or 24h).
- **Code structure**: 1–2 character terminal/sequential codes match the
  rest of the NLS short-code protocol (`TRACKSTATE: "0"`–`"5"`,
  `TIMESTATE: "0"`–`"3"`, `LTS_TIMESYNC`).
- **No public spec**: NLS does not publish a protocol reference. The
  reverse-engineered JS bundle uses opaque constants; the upstream
  Zeitnahme software is suspected to be a RaceLogic / Tag Heuer decoder
  family whose original spec is not publicly available.

## Where these codes live in the WS payload — narrowing down

User confirmed (2026-06-20): the codes are attached to **individual cars**
on the leaderboard row, not to the track-level state. The ``TRACKSTATE``
field on PID 4 (which we already model) carries separate values like
``"0"`` (idle), ``"1"`` (green), ``"2"`` (yellow), etc. — those are
flag/phase indicators, **not** the per-car codes in question.

The codes must therefore arrive on one of:

1. **PID 7 (PerCarLaps)** — strongest candidate. The leaderboard
   updates the State column as cars complete laps, so a per-lap delta
   stream fits the data shape. PID 7 was **not** in our 20-second
   capture because Event 20 was in pre-race setup (``TRACKSTATE: "0"``);
   we expect per-car state transitions to fire only during a live
   session.
2. **PID 0 (InitialState)** — weaker candidate. The static car list
   may carry a baseline ``state`` per car, but ongoing I1→I2→...→F
   transitions would need a separate stream. Worth checking the
   InitialState fixture once we capture an active event.
3. **An as-yet-unmodelled PID** — possible. We currently subscribe to
   ``eventPid: [0, 3, 4, 7, 501, 9002]`` by default; if the State column
   is fed by another PID we would have silently missed it.

Our 20-second live capture of Event 20 (saved at
`/tmp/nls_event20_v2.jsonl`) yielded PID 0/3/4/9002 frames but **none**
contained these codes — consistent with Event 20 being in pre-race setup
(``TRACKSTATE: "0"``). **PID 7 was absent from the handshake-ack burst**;
we need an active race to test the I1→I2→...→F sequence.

## How to verify

In rough order of cost / reliability:

1. **Longer live capture during an active session** (30+ min) so we
   observe state transitions. Run with all default channels including
   PID 7. Especially useful: capture during formation laps
   (I1->I2->I3->I4 sequence) and at chequered flag (->F transition).
2. **Browser DevTools WS sniff** during a state change: open
   `/events/{id}/results/`, switch to Network → WS, trigger a manual
   pit-in (or wait for one), and capture the exact payload that updates
   the per-car "State" cell.
3. **Cross-reference with PID 3 race messages**: when a car enters the
   pit, the SPA often also shows a "Box" race message. Match the timing
   of `PI` against PID 3 messages to confirm the pairing.
4. **JS bundle reverse-engineering**: the leaderboard bundle
   (`/leaderboard.*.bundle.js`) renders the State column. Search for the
   exact set `["PI","F","I1","I2","I3","I4"]` (or short-codes patterns)
   to find where the SPA maps wire values to display labels — this
   often reveals the wire field name. Specifically: grep for the
   literal string `I1` and `carState` / `STATUS` / `STATE` in the
   bundle.
5. **NLS Zeitnahme / RaceLogic docs** (if accessible via insider): the
   underlying decoder publishes a spec sheet that maps these codes to
   their full names.

## Action items

- [ ] During the next active NLS round, capture with PID 7 enabled
      (default) and grep the JSONL for any field whose value matches
      `^(PI|F|I[1-4])$`.
- [ ] Once the wire field is identified, extend `events/per_car_laps.py`
      with a `state: str | None` field — keeping it as plain `str`
      rather than an enum, consistent with `track_state` / `time_state`
      policy (PROJECT.md pitfall: schema changes between seasons).
- [ ] Update `parser/per_car_laps.py` to extract the state field with
      `warn_missing` on first occurrence.
- [ ] Add fixtures covering all 6 observed codes once we have real
      frames.