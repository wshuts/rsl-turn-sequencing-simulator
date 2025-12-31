from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, List, Tuple


class EffectKind(str, Enum):
    """
    Minimal effect vocabulary. Expand only when tests require it.
    """

    DECREASE_SPD = "DECREASE_SPD"


@dataclass(slots=True)
class Effect:
    """
    Observer-faithful duration model:
      - 'turns_remaining' decrements on TURN_END of the affected actor.
      - duration=1 means the effect persists through exactly one of that actor's turns,
        then expires at TURN_END.
    """

    kind: EffectKind
    turns_remaining: int
    magnitude: float = 0.0  # for DECREASE_SPD: 0.30 == -30%


def speed_multiplier_from_effects(effects: Iterable[Effect]) -> float:
    """
    Multiplicative modifier applied during fill.
    Only DECREASE_SPD affects speed for now.
    """
    mult = 1.0
    for e in effects:
        if e.turns_remaining <= 0:
            continue
        if e.kind == EffectKind.DECREASE_SPD:
            # Clamp to [0, 1] to avoid nonsense.
            mag = max(0.0, min(1.0, float(e.magnitude)))
            mult *= (1.0 - mag)
    return mult


def decrement_turn_end(effects: List[Effect]) -> Tuple[List[Effect], List[Effect]]:
    """
    Decrement durations at TURN_END for the affected actor.
    Returns: (remaining_effects, expired_effects)
    """
    remaining: List[Effect] = []
    expired: List[Effect] = []
    for e in effects:
        if e.turns_remaining <= 0:
            expired.append(e)
            continue
        new_n = int(e.turns_remaining) - 1
        if new_n <= 0:
            expired.append(Effect(kind=e.kind, turns_remaining=0, magnitude=e.magnitude))
        else:
            remaining.append(Effect(kind=e.kind, turns_remaining=new_n, magnitude=e.magnitude))
    return remaining, expired
