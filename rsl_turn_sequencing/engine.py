from __future__ import annotations

from rsl_turn_sequencing.event_sink import EventSink
from rsl_turn_sequencing.events import EventType
from rsl_turn_sequencing.models import Actor

TM_GATE = 1430.0
EPS = 1e-9


def step_tick(actors: list[Actor], event_sink: EventSink | None = None) -> Actor | None:
    """
    Advance the simulation by one global tick.

    Rules (foundation):
    - All actors fill simultaneously: turn_meter += speed (floats)
    - TM_GATE is an eligibility trigger (a "gate"), not a maximum.
    - If nobody passes the gate, no one acts this tick.
    - If one or more pass the gate, the actor with the highest turn_meter acts.
    - Acting resets that actor's turn_meter to 0.0 (overflow discarded).

    Tie-break (deterministic):
    - Higher turn_meter wins
    - If equal, higher speed wins
    - If still equal, earlier in the list wins
    """
    if event_sink is not None:
        event_sink.start_tick()
        event_sink.emit(EventType.TICK_START)

    # 1) simultaneous fill
    for a in actors:
        eff_speed = float(a.speed) * float(a.speed_multiplier)
        a.turn_meter += eff_speed

    if event_sink is not None:
        event_sink.emit(EventType.FILL_COMPLETE)

    # 2) find all ready actors
    ready = [a for a in actors if a.turn_meter + EPS >= TM_GATE]
    if not ready:
        return None

    # 3) choose actor: highest TM, then speed, then list order
    # Use index to make final tie-break stable
    indexed = list(enumerate(actors))
    ready_indexed = [(i, a) for (i, a) in indexed if a.turn_meter + EPS >= TM_GATE]
    i_best, best = max(
        ready_indexed,
        key=lambda t: (t[1].turn_meter, t[1].speed, -t[0]),
    )

    if event_sink is not None:
        event_sink.emit(
            EventType.WINNER_SELECTED,
            actor=best.name,
            actor_index=i_best,
            pre_reset_tm=float(best.turn_meter),
        )

    # 4) act (for now, acting is just returning the actor) and reset TM to 0
    best.turn_meter = 0.0

    if event_sink is not None:
        event_sink.emit(EventType.RESET_APPLIED, actor=best.name, actor_index=i_best)
    return best


def step_tick_debug(actors: list[Actor]) -> tuple[Actor | None, list[float]]:
    """
    Advance the simulation by one global tick, returning:
      (winner, turn_meters_before_reset)

    This provides observability for traces/logging without changing the
    core step_tick() behavior.
    """
    # 1) simultaneous fill
    for a in actors:
        eff_speed = float(a.speed) * float(a.speed_multiplier)
        a.turn_meter += eff_speed

    # Snapshot AFTER fill, BEFORE any reset (this is the "winning snapshot")
    before_reset = [float(a.turn_meter) for a in actors]

    # 2) find all ready actors
    ready_indexed = [(i, a) for (i, a) in enumerate(actors) if a.turn_meter + EPS >= TM_GATE]
    if not ready_indexed:
        return None, before_reset

    # 3) choose actor: highest TM, then speed, then list order
    _, best = max(
        ready_indexed,
        key=lambda t: (t[1].turn_meter, t[1].speed, -t[0]),
    )

    # 4) reset TM (overflow discarded)
    best.turn_meter = 0.0
    return best, before_reset
