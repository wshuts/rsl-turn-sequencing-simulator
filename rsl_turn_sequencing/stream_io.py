from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from rsl_turn_sequencing.events import Event, EventType


class InputFormatError(ValueError):
    """Raised when an input event stream fails validation."""

@dataclass(frozen=True)
class BattleSpecActor:
    name: str
    speed: float
    # Optional: starting form for Mythical/transform champions.
    form_start: str | None = None
    # Optional: speed overrides by form name.
    speed_by_form: dict[str, float] | None = None
    # Optional: reserved for Metamorph modeling (not enforced yet).
    metamorph: dict[str, Any] | None = None


@dataclass(frozen=True)
class BattleSpec:
    boss: BattleSpecActor
    actors: list[BattleSpecActor]


def load_battle_spec(path: Path) -> BattleSpec:
    """Load and validate a minimal battle spec (JIT input v0).

    Format:
      {
        "boss": {"name": "Boss", "speed": 250},
        "actors": [
          {"name": "Mikage", "speed": 340},
          ...
        ]
      }

    Optional keys are accepted for future work:
      - form_start: str
      - speed_by_form: {"FormName": number}
      - metamorph: {"cooldown_turns": int}
    """

    if not path.exists():
        raise InputFormatError(f"file not found: {path}")
    if not path.is_file():
        raise InputFormatError(f"not a file: {path}")

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise InputFormatError(f"invalid JSON: {e.msg} (line {e.lineno}, col {e.colno})") from e

    if not isinstance(raw, dict):
        raise InputFormatError("root must be a JSON object")

    boss_raw = raw.get("boss")
    actors_raw = raw.get("actors")
    if not isinstance(boss_raw, dict):
        raise InputFormatError("boss must be an object")
    if not isinstance(actors_raw, list) or not actors_raw:
        raise InputFormatError("actors must be a non-empty array")

    boss = _parse_battle_spec_actor(boss_raw, label="boss")
    actors: list[BattleSpecActor] = []
    for i, item in enumerate(actors_raw):
        if not isinstance(item, dict):
            raise InputFormatError(f"actors[{i}] must be an object")
        actors.append(_parse_battle_spec_actor(item, label=f"actors[{i}]"))

    return BattleSpec(boss=boss, actors=actors)


def _parse_battle_spec_actor(raw: dict[str, Any], *, label: str) -> BattleSpecActor:
    name = raw.get("name")
    speed = raw.get("speed")
    if not isinstance(name, str) or not name.strip():
        raise InputFormatError(f"{label}.name must be a non-empty string")
    if not isinstance(speed, (int, float)):
        raise InputFormatError(f"{label}.speed must be a number")

    form_start = raw.get("form_start", None)
    if form_start is not None and (not isinstance(form_start, str) or not form_start.strip()):
        raise InputFormatError(f"{label}.form_start must be a non-empty string when provided")

    speed_by_form = raw.get("speed_by_form", None)
    if speed_by_form is not None:
        if not isinstance(speed_by_form, dict):
            raise InputFormatError(f"{label}.speed_by_form must be an object when provided")
        parsed: dict[str, float] = {}
        for k, v in speed_by_form.items():
            if not isinstance(k, str) or not k.strip():
                raise InputFormatError(f"{label}.speed_by_form keys must be non-empty strings")
            if not isinstance(v, (int, float)):
                raise InputFormatError(f"{label}.speed_by_form[{k!r}] must be a number")
            parsed[k] = float(v)
        speed_by_form = parsed

    metamorph = raw.get("metamorph", None)
    if metamorph is not None and not isinstance(metamorph, dict):
        raise InputFormatError(f"{label}.metamorph must be an object when provided")

    return BattleSpecActor(
        name=str(name),
        speed=float(speed),
        form_start=str(form_start) if form_start is not None else None,
        speed_by_form=speed_by_form,
        metamorph=metamorph,
    )


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
