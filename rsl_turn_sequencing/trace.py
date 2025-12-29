from __future__ import annotations

from dataclasses import dataclass

from rsl_turn_sequencing.engine import EPS, TM_GATE, step_tick
from rsl_turn_sequencing.models import Actor


@dataclass(frozen=True)
class ActorTrace:
    name: str
    speed: float
    turn_meter: float
    ui_percent: float
    eligible: bool


@dataclass(frozen=True)
class TickTrace:
    tick: int
    actors: list[ActorTrace]
    winner: str | None


def snapshot_tick(tick: int, actors: list[Actor], winner: Actor | None) -> TickTrace:
    """
    Create a trace snapshot for the current tick after step_tick() has executed.
    This function does not modify simulation behavior.
    """
    traces: list[ActorTrace] = []
    for a in actors:
        eligible = (a.turn_meter + EPS) >= TM_GATE
        ui_percent = (a.turn_meter / TM_GATE) * 100.0
        traces.append(
            ActorTrace(
                name=a.name,
                speed=float(a.speed),
                turn_meter=float(a.turn_meter),
                ui_percent=float(ui_percent),
                eligible=bool(eligible),
            )
        )

    return TickTrace(
        tick=tick,
        actors=traces,
        winner=(winner.name if winner is not None else None),
    )


def run_ticks_with_trace(actors: list[Actor], num_ticks: int) -> list[TickTrace]:
    """
    Run the simulation for num_ticks global ticks, returning a per-tick trace log.

    Notes:
    - Uses engine.step_tick() for behavior.
    - Adds observability only (no rule changes).
    """
    log: list[TickTrace] = []
    for t in range(1, num_ticks + 1):
        winner = step_tick(actors)
        log.append(snapshot_tick(t, actors, winner))
    return log
