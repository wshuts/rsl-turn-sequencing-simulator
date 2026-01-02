from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from rsl_turn_sequencing.events import Event, EventType


@dataclass(frozen=True, slots=True)
class ShieldSnapshot:
    value: int
    status: str  # "UP" | "BROKEN"


@dataclass(frozen=True, slots=True)
class TurnRow:
    actor: str
    pre_shield: ShieldSnapshot | None
    post_shield: ShieldSnapshot | None
    events: tuple[Event, ...]


@dataclass(frozen=True, slots=True)
class BossTurnFrame:
    boss_turn_index: int
    rows: tuple[TurnRow, ...]


def _shield_from_event(e: Event) -> ShieldSnapshot | None:
    if "boss_shield_value" not in e.data:
        return None
    return ShieldSnapshot(
        value=e.data["boss_shield_value"],
        status=e.data["boss_shield_status"],
    )


def derive_turn_rows(events: Iterable[Event]) -> list[TurnRow]:
    """
    Derive TURN_START → TURN_END rows from an ordered event stream.
    """
    rows: list[TurnRow] = []
    buffer: list[Event] = []
    actor: str | None = None
    pre: ShieldSnapshot | None = None

    for e in events:
        if e.type == EventType.TURN_START:
            buffer = [e]
            actor = e.actor
            pre = _shield_from_event(e)
            continue

        if actor is None:
            continue

        buffer.append(e)

        if e.type == EventType.TURN_END and e.actor == actor:
            post = _shield_from_event(e)
            rows.append(
                TurnRow(
                    actor=actor,
                    pre_shield=pre,
                    post_shield=post,
                    events=tuple(buffer),
                )
            )
            buffer = []
            actor = None
            pre = None

    return rows


def group_rows_into_boss_frames(
        rows: Iterable[TurnRow],
        *,
        boss_actor: str,
) -> list[BossTurnFrame]:
    frames: list[BossTurnFrame] = []
    current: list[TurnRow] = []
    boss_turn_index = 0

    for row in rows:
        current.append(row)

        if row.actor == boss_actor:
            boss_turn_index += 1
            frames.append(
                BossTurnFrame(
                    boss_turn_index=boss_turn_index,
                    rows=tuple(current),
                )
            )
            current = []

    return frames
