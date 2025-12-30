from dataclasses import dataclass


@dataclass
class Actor:
    name: str
    # Speed and turn meter are modeled as floating point values.
    speed: float
    # Multiplicative modifier applied to speed for tick fill (e.g., Decrease SPD).
    # 1.0 means no change; 0.7 means -30% speed.
    speed_multiplier: float = 1.0
    turn_meter: float = 0.0
