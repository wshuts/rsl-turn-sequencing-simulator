from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventType(str, Enum):
    """
    Minimal event vocabulary for the simulator "truth engine".
    Keep this small; add types only when tests require them.
    """

    TICK_START = "TICK_START"
    FILL_COMPLETE = "FILL_COMPLETE"
    WINNER_SELECTED = "WINNER_SELECTED"
    RESET_APPLIED = "RESET_APPLIED"


@dataclass(frozen=True, slots=True)
class Event:
    """
    A structured, orderable fact emitted by the engine (optionally).

    tick and seq are owned by the sink (so the engine remains stateless).
    """

    tick: int
    seq: int
    type: EventType
    actor: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
