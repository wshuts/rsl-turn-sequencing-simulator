from __future__ import annotations

from dataclasses import dataclass

from rsl_turn_sequencing.engine import EPS, TM_GATE, step_tick_debug
from rsl_turn_sequencing.models import Actor


@dataclass(frozen=True)
class ActorTrace:
    name: str
    speed: float
    # AFTER fill, BEFORE reset (used for winner selection)
    turn_meter_before: float
    ui_percent_before: float
    eligible_before: bool
    # AFTER reset (post-action state)
    turn_meter_after: float
    ui_percent_after: float


@dataclass(frozen=True)
class TickTrace:
    tick: int
    actors: list[ActorTrace]
    winner: str | None
    winner_before: float | None


def snapshot_tick(
    tick: int,
    actors: list[Actor],
    winner: Actor | None,
    before_reset: list[float],
) -> TickTrace:
    """
    Create a trace snapshot for the current tick.

    Captures both:
      - before_reset: AFTER fill, BEFORE any reset (this is the "winning snapshot")
      - actor.turn_meter: AFTER reset (post-action state)

    This function does not modify simulation behavior.
    """
    traces: list[ActorTrace] = []
    for idx, a in enumerate(actors):
        tm_before = float(before_reset[idx])
        eligible_before = (tm_before + EPS) >= TM_GATE
        ui_before = (tm_before / TM_GATE) * 100.0

        tm_after = float(a.turn_meter)
        ui_after = (tm_after / TM_GATE) * 100.0

        traces.append(
            ActorTrace(
                name=a.name,
                speed=float(a.speed),
                turn_meter_before=tm_before,
                ui_percent_before=float(ui_before),
                eligible_before=bool(eligible_before),
                turn_meter_after=tm_after,
                ui_percent_after=float(ui_after),
            )
        )

    winner_before = None
    if winner is not None:
        for idx, a in enumerate(actors):
            if a is winner:
                winner_before = float(before_reset[idx])
                break

    return TickTrace(
        tick=tick,
        actors=traces,
        winner=(winner.name if winner is not None else None),
        winner_before=winner_before,
    )


def run_ticks_with_trace(actors: list[Actor], num_ticks: int) -> list[TickTrace]:
    """
    Run the simulation for num_ticks global ticks, returning a per-tick trace log.

    Notes:
    - Uses engine.step_tick_debug() for behavior (same rules) + observability.
    - Adds observability only (no rule changes).
    """
    log: list[TickTrace] = []
    for t in range(1, num_ticks + 1):
        winner, before_reset = step_tick_debug(actors)
        log.append(snapshot_tick(t, actors, winner, before_reset))
    return log
