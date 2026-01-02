from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from rsl_turn_sequencing.events import Event, EventType


class InputFormatError(ValueError):
    """Raised when an input event stream fails validation."""


def load_event_stream(path: Path) -> list[Event]:
    """Load and validate an ordered structured event stream from JSON.

    The input format is a JSON array of objects. Each object must have:
      - tick: int (>= 1)
      - seq: int (>= 1)
      - type: str (must match EventType)
      - actor: str | null
      - data: object (must be a JSON object / dict)

    Ordering contract:
      - Events must be strictly increasing by (tick, seq).
      - seq must be strictly increasing within a tick.
    """

    if not path.exists():
        raise InputFormatError(f"file not found: {path}")
    if not path.is_file():
        raise InputFormatError(f"not a file: {path}")

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise InputFormatError(f"invalid JSON: {e.msg} (line {e.lineno}, col {e.colno})") from e

    if not isinstance(raw, list):
        raise InputFormatError("root must be a JSON array of events")

    events: list[Event] = []
    last_key: tuple[int, int] | None = None

    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise InputFormatError(f"event[{i}] must be an object")

        tick = item.get("tick")
        seq = item.get("seq")
        etype = item.get("type")
        actor = item.get("actor", None)
        data = item.get("data", {})

        if not isinstance(tick, int) or tick < 1:
            raise InputFormatError(f"event[{i}].tick must be an int >= 1")
        if not isinstance(seq, int) or seq < 1:
            raise InputFormatError(f"event[{i}].seq must be an int >= 1")
        if not isinstance(etype, str):
            raise InputFormatError(f"event[{i}].type must be a string")
        if actor is not None and not isinstance(actor, str):
            raise InputFormatError(f"event[{i}].actor must be a string or null")
        if not isinstance(data, dict):
            raise InputFormatError(f"event[{i}].data must be an object")

        try:
            event_type = EventType(etype)
        except Exception as e:
            raise InputFormatError(f"event[{i}].type is not a valid EventType: {etype!r}") from e

        key = (tick, seq)
        if last_key is not None and key <= last_key:
            raise InputFormatError(
                "events must be strictly increasing by (tick, seq); "
                f"event[{i}] has (tick, seq)={key} after {last_key}"
            )
        last_key = key

        events.append(Event(tick=tick, seq=seq, type=event_type, actor=actor, data=data))

    return events


def dump_event_stream(events: list[Event]) -> list[dict[str, Any]]:
    """Helper for generating sample streams (not used by the CLI)."""
    out: list[dict[str, Any]] = []
    for e in events:
        d = asdict(e)
        d["type"] = str(e.type.value)
        out.append(d)
    return out
