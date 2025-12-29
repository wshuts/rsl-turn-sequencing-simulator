from __future__ import annotations

from rsl_turn_sequencing.models import Actor

TM_GATE = 1430.0
EPS = 1e-9


def step_tick(actors: list[Actor]) -> Actor | None:
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
    # 1) simultaneous fill
    for a in actors:
        a.turn_meter += float(a.speed)

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

    # 4) act (for now, acting is just returning the actor) and reset TM to 0
    best.turn_meter = 0.0
    return best
