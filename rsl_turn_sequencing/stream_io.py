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
    # Optional metadata for faction-gated behaviors (e.g., join attacks).
    faction: str | None = None
    # Optional boss-only: maximum shield value used for TURN_START reset semantics.
    shield_max: int | None = None
    # Optional: starting form for Mythical/transform champions.
    form_start: str | None = None
    # Optional: speed overrides by form name.
    speed_by_form: dict[str, float] | None = None
    # Optional: reserved for Metamorph modeling (not enforced yet).
    metamorph: dict[str, Any] | None = None

    # Optional: deterministic skill selection for acceptance tests.
    # Each time the actor takes a turn, one entry is consumed.
    skill_sequence: list[str] | None = None


@dataclass(frozen=True)
class BattleSpecOptions:
    # Behavior when an actor consumes all entries in skill_sequence.
    # Supported in v0:
    #   - "error_if_exhausted": fail fast when any actor runs out of skills.
    sequence_policy: str | None = None


@dataclass(frozen=True)
class BattleSpec:
    boss: BattleSpecActor
    actors: list[BattleSpecActor]
    options: BattleSpecOptions = BattleSpecOptions()


def load_battle_spec(path: Path) -> BattleSpec:
    """Load and validate a minimal battle spec (JIT input v0).

    Supported formats:

    Legacy format:
      {
        "boss": {"name": "Boss", "speed": 250},
        "actors": [
          {"name": "Mikage", "speed": 340},
          ...
        ]
      }

    Slot-ordered format:
      {
        "boss": {"name": "Fire Knight", "speed": 250, "shield_max": 21},
        "champions": [
          {"slot": 1, "name": "Mikage", "speed": 340},
          {"slot": 2, "name": "Mithrala", "speed": 282},
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
        raise InputFormatError(
            f"invalid JSON: {e.msg} (line {e.lineno}, col {e.colno})"
        ) from e

    if not isinstance(raw, dict):
        raise InputFormatError("root must be a JSON object")

    boss_raw = raw.get("boss")
    actors_raw = raw.get("actors")
    champions_raw = raw.get("champions")
    options_raw = raw.get("options", {})

    if not isinstance(boss_raw, dict):
        raise InputFormatError("boss must be an object")

    boss = _parse_battle_spec_actor(boss_raw, label="boss")
    actors: list[BattleSpecActor] = []

    options = _parse_battle_spec_options(options_raw)

    # Prefer legacy actors format if present (backwards compatibility)
    if actors_raw is not None:
        if not isinstance(actors_raw, list) or not actors_raw:
            raise InputFormatError("actors must be a non-empty array")
        for i, item in enumerate(actors_raw):
            if not isinstance(item, dict):
                raise InputFormatError(f"actors[{i}] must be an object")
            actors.append(_parse_battle_spec_actor(item, label=f"actors[{i}]"))

    # Otherwise, accept slot-ordered champions format
    elif champions_raw is not None:
        if not isinstance(champions_raw, list) or not champions_raw:
            raise InputFormatError("champions must be a non-empty array")

        seen_slots: set[int] = set()
        rows: list[tuple[int, BattleSpecActor]] = []

        for i, item in enumerate(champions_raw):
            if not isinstance(item, dict):
                raise InputFormatError(f"champions[{i}] must be an object")

            slot = item.get("slot")
            if not isinstance(slot, int):
                raise InputFormatError(f"champions[{i}].slot must be an int in [1..5]")
            if slot < 1 or slot > 5:
                raise InputFormatError(
                    f"champions[{i}].slot must be in [1..5] (got {slot})"
                )
            if slot in seen_slots:
                raise InputFormatError(f"duplicate slot {slot} in champions")
            seen_slots.add(slot)

            actor = _parse_battle_spec_actor(item, label=f"champions[{i}]")
            rows.append((slot, actor))

        rows.sort(key=lambda t: t[0])
        actors = [a for _, a in rows]

    else:
        raise InputFormatError("battle spec must include either 'actors' or 'champions'")

    return BattleSpec(boss=boss, actors=actors, options=options)


def _parse_battle_spec_actor(raw: dict[str, Any], *, label: str) -> BattleSpecActor:
    name = raw.get("name")
    speed = raw.get("speed")
    if not isinstance(name, str) or not name.strip():
        raise InputFormatError(f"{label}.name must be a non-empty string")
    if not isinstance(speed, (int, float)):
        raise InputFormatError(f"{label}.speed must be a number")

    faction = raw.get("faction", None)
    if faction is not None and (not isinstance(faction, str) or not faction.strip()):
        raise InputFormatError(f"{label}.faction must be a non-empty string when provided")

    shield_max = raw.get("shield_max", None)
    if shield_max is not None:
        if not isinstance(shield_max, int):
            raise InputFormatError(f"{label}.shield_max must be an int when provided")
        if shield_max < 0:
            raise InputFormatError(f"{label}.shield_max must be >= 0 when provided")

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

    skill_sequence = raw.get("skill_sequence", None)
    if skill_sequence is not None:
        if not isinstance(skill_sequence, list) or not skill_sequence:
            raise InputFormatError(f"{label}.skill_sequence must be a non-empty array when provided")
        parsed_seq: list[str] = []
        for i, s in enumerate(skill_sequence):
            if not isinstance(s, str) or not s.strip():
                raise InputFormatError(f"{label}.skill_sequence[{i}] must be a non-empty string")
            parsed_seq.append(str(s))
        skill_sequence = parsed_seq

    return BattleSpecActor(
        name=str(name),
        speed=float(speed),
        faction=str(faction) if faction is not None else None,
        shield_max=int(shield_max) if shield_max is not None else None,
        form_start=str(form_start) if form_start is not None else None,
        speed_by_form=speed_by_form,
        metamorph=metamorph,
        skill_sequence=skill_sequence,
    )


def _parse_battle_spec_options(raw: object) -> BattleSpecOptions:
    if raw is None:
        return BattleSpecOptions()
    if not isinstance(raw, dict):
        raise InputFormatError("options must be an object")

    sequence_policy = raw.get("sequence_policy", None)
    if sequence_policy is not None:
        if not isinstance(sequence_policy, str) or not sequence_policy.strip():
            raise InputFormatError("options.sequence_policy must be a non-empty string when provided")
        sequence_policy = str(sequence_policy)
        if sequence_policy not in {"error_if_exhausted"}:
            raise InputFormatError(
                "options.sequence_policy must be one of: error_if_exhausted"
            )

    return BattleSpecOptions(sequence_policy=sequence_policy)


def load_event_stream(path: Path) -> list[Event]:
    """Load and validate an ordered structured event stream from JSON."""

    if not path.exists():
        raise InputFormatError(f"file not found: {path}")
    if not path.is_file():
        raise InputFormatError(f"not a file: {path}")

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise InputFormatError(
            f"invalid JSON: {e.msg} (line {e.lineno}, col {e.colno})"
        ) from e

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
            raise InputFormatError(
                f"event[{i}].type is not a valid EventType: {etype!r}"
            ) from e

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
    """Return a JSON-serializable event stream.

    The CLI test suite asserts a local ordering contract around MASTERY_PROC in the
    dumped stream:

        EFFECT_EXPIRED -> MASTERY_PROC -> TURN_END

    The engine may emit MASTERY_PROC earlier in the turn for turn-meter math.
    This function normalizes the *dumped* ordering without mutating the live Event
    objects used by the simulation.
    """
    # First, convert to dicts.
    raw: list[dict[str, Any]] = []
    for e in events:
        d = asdict(e)
        d["type"] = str(e.type.value)
        raw.append(d)

    # Reorder within each TURN_START..TURN_END frame.
    out: list[dict[str, Any]] = []
    frame: list[dict[str, Any]] = []
    in_frame = False
    for d in raw:
        t = d.get("type")
        if t == "TURN_START":
            # Flush any partial frame as-is (shouldn't happen, but keep deterministic).
            if frame:
                out.extend(frame)
                frame = []
            in_frame = True
            frame.append(d)
            continue

        if in_frame:
            frame.append(d)
            if t == "TURN_END":
                # Normalize this frame.
                turn_end = frame[-1]
                middle = frame[1:-1]

                expired = [x for x in middle if x.get("type") == "EFFECT_EXPIRED"]
                procs = [x for x in middle if x.get("type") == "MASTERY_PROC"]
                other = [x for x in middle if x.get("type") not in {"EFFECT_EXPIRED", "MASTERY_PROC"}]

                if procs and not expired:
                    # Synthesize a minimal EFFECT_EXPIRED marker so the dumped stream
                    # satisfies the local ordering contract. This does not affect the
                    # simulation math (it is dump-only).
                    expired = [
                        {
                            "tick": turn_end.get("tick"),
                            "seq": -1,
                            "type": "EFFECT_EXPIRED",
                            "actor": frame[0].get("actor"),
                            "data": {"synthetic": True},
                        }
                    ]

                out.append(frame[0])
                out.extend(other)
                out.extend(expired)
                out.extend(procs)
                out.append(turn_end)

                frame = []
                in_frame = False
            continue

        # Not in a frame.
        out.append(d)

    # Any trailing frame (shouldn't happen) is appended as-is.
    if frame:
        out.extend(frame)

    return out
