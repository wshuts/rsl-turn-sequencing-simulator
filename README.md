# RSL Turn Sequencing Simulator (v0)

This repo contains a deterministic **turn-sequencing simulator** plus a **CLI harness**.
The purpose is to make *timing* and *ordering* observable (turn boundaries, trigger boundaries, and boss-relative
groupings)
so we can validate mechanics with tests and reason about Raid: Shadow Legends–style sequencing problems.

## What this tool does

- Runs a deterministic simulation (v0 uses a built-in demo roster).
- Records a structured, ordered event stream (each event has `tick`, `seq`, `type`, optional `actor`, and `data`).
- Derives **Turn Rows** from the event stream: `TURN_START → TURN_END` for each actor.
- Captures the boss shield state at turn boundaries and attaches it to Turn Rows as **PRE** and **POST** snapshots.
- Groups Turn Rows into **Boss Turn Frames**, where a frame ends when the boss completes a turn.
- Prints a human-readable text report from the derived Boss Turn Frames.

## What you can feed it (Epic D2 + JIT input v0)

Option A (recommended for early user evaluation): a **minimal battle spec** JSON
that declares boss + actor speeds.

```bash
python -m rsl_turn_sequencing run --battle samples/demo_battle_spec.json --ticks 400
```

Option B: an authoritative **ordered event stream** (still supported).

The CLI can load an **authoritative ordered event stream** from JSON:

- File format: JSON array of event objects
- Each event must contain:
    - `tick` (int >= 1)
    - `seq` (int >= 1)
    - `type` (string; must match `EventType`)
    - `actor` (string or null)
    - `data` (object)
- Ordering is validated at load time:
    - events must be strictly increasing by `(tick, seq)`

A sample event stream input is included:

```bash
python -m rsl_turn_sequencing run --input samples/demo_event_stream.json
```

## What this tool does NOT do (yet)

- No full scenario/build definition language (JIT input v0 only covers speeds).
- No installable console script (use `python -m ...` for now).
- No UI or visualization.
- No damage modeling, AI, or strategy recommendations.
- Not a full Raid: Shadow Legends combat emulator — this is a sequencing/observability tool.

## Quick start (v0 demo)

From the repo root:

```bash
python -m rsl_turn_sequencing run --demo
```

Optional knobs (still v0 demo):

```bash
python -m rsl_turn_sequencing run --demo --ticks 200
python -m rsl_turn_sequencing run --demo --ticks 200 --boss-actor Boss
```

For help:

```bash
python -m rsl_turn_sequencing -h
python -m rsl_turn_sequencing run -h
```

## How to read the output

The report prints **Boss Turn Frames**. Each frame is labeled:

- `Boss Turn #N` — the Nth boss turn that *ended* a frame.

Inside each frame are one or more **Turn Rows**:

```
  [<PRE>] <ACTOR> [<POST>]
```

Where:

- **PRE** is the boss-shield snapshot captured at that actor's `TURN_START`.
- **POST** is the boss-shield snapshot captured at that actor's `TURN_END`.
- A snapshot renders as: `<value> <status>`
    - `value` is the boss shield integer at that moment.
    - `status` is currently `UP` or `BROKEN`.
- `--` means "no shield snapshot was present on that event".

A small example from the v0 demo:

```
Boss Turn #1
  [0 BROKEN  ] Mikage [0 BROKEN]
  [0 BROKEN  ] Mithrala [0 BROKEN]
  [0 BROKEN  ] Tomblord [0 BROKEN]
  [0 BROKEN  ] Coldheart [0 BROKEN]
  [0 BROKEN  ] Martyr [0 BROKEN]
  [0 BROKEN  ] Boss [0 BROKEN]
```

Interpretation:

- Frame #1 contains the sequence of actor turns that occurred up to (and including) the boss turn.
- Each row shows what the boss shield looked like entering and leaving that actor's turn.

## Running tests

Tests are the arbiter of truth.

```bash
python -m pytest
```

(You will need `pytest` installed in your environment.)

## Baseline discipline (repo workflow note)

When collaborating via patches:

- Fresh ZIP uploads are the canonical baseline.
- Generate patches only against the explicitly provided baseline.
- If formatting/tooling changes (e.g., IDE reformat), refresh the baseline before producing a patch.
