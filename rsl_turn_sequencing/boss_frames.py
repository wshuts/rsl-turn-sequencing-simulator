from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from rsl_turn_sequencing.events import Event, EventType


@dataclass(frozen=True, slots=True)
class BossTurnFrame:
    """
    A boss-relative grouping of events.

    A frame is closed by the boss's TURN_END event. Frame indices start at 1.
    """

    boss_turn_index: int
    events: tuple[Event, ...]


def group_events_into_boss_frames(
        events: Sequence[Event] | Iterable[Event],
        *,
        boss_actor: str,
) -> list[BossTurnFrame]:
    """
    Group an ordered event stream into boss-relative frames.

    Rules:
      - Events are assumed to be in deterministic order already (tick, seq).
      - A frame ends when we observe (TURN_END, actor=boss_actor).
      - The boss TURN_END is the last event in the frame.
      - Any trailing events after the final boss TURN_END are ignored for now
        (they represent a partial frame in-progress).
    """
    frames: list[BossTurnFrame] = []
    current: list[Event] = []
    boss_turn_index = 0

    for e in events:
        current.append(e)

        if e.type == EventType.TURN_END and e.actor == boss_actor:
            boss_turn_index += 1
            frames.append(BossTurnFrame(boss_turn_index=boss_turn_index, events=tuple(current)))
            current = []

    return frames
