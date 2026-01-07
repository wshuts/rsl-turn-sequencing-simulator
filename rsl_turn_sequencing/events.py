from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventType(str, Enum):
    """Minimal event vocabulary for the simulator truth engine."""

    TICK_START = "TICK_START"
    FILL_COMPLETE = "FILL_COMPLETE"
    WINNER_SELECTED = "WINNER_SELECTED"
    TURN_START = "TURN_START"
    RESET_APPLIED = "RESET_APPLIED"
    TURN_END = "TURN_END"
    EFFECT_TRIGGERED = "EFFECT_TRIGGERED"
    EFFECT_EXPIRED = "EFFECT_EXPIRED"

    # Emitted when an actor consumes a skill token from its skill_sequence.
    # Must occur within TURN_START → TURN_END so it is preserved by derive_turn_rows().
    SKILL_CONSUMED = "SKILL_CONSUMED"


@dataclass(frozen=True, slots=True)
class Event:
    """A structured, orderable fact emitted by the engine (optionally)."""

    tick: int
    seq: int
    type: EventType
    actor: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
