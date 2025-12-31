from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BattleSnapshot:
    turn: int
    phase: str
    actor: str
    state: dict[str, Any]


@dataclass(frozen=True)
class SnapshotCaptureSpec:
    turns: set[int]
    phases: set[str]

    def wants(self, turn: int, phase: str) -> bool:
        return turn in self.turns and phase in self.phases
