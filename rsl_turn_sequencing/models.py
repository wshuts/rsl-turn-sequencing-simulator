from dataclasses import dataclass, field

from rsl_turn_sequencing.effects import Effect


@dataclass
class Actor:
    name: str
    # Speed and turn meter are modeled as floating point values.
    speed: float

    # Optional boss shield model (observer-only until combat is implemented).
    # Convention:
    #   - shield > 0  => "UP"
    #   - shield == 0 => "BROKEN"
    shield: int = 0
    is_boss: bool = False
    # Optional health model (only used when tests require it, e.g., Poison).
    max_hp: float = 0.0
    hp: float = 0.0
    # Multiplicative modifier applied to speed for tick fill (e.g., Decrease SPD).
    # 1.0 means no change; 0.7 means -30% speed.
    speed_multiplier: float = 1.0
    turn_meter: float = 0.0
    # Extra turns are turns granted without advancing turn meter fill.
    extra_turns: int = 0
    effects: list[Effect] = field(default_factory=list)
