from dataclasses import dataclass


@dataclass
class Actor:
    name: str
    speed: int
    turn_meter: int = 0