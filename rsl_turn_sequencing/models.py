from dataclasses import dataclass


@dataclass
class Actor:
    name: str
    # Speed and turn meter are modeled as floating point values.
    speed: float
    turn_meter: float = 0.0
