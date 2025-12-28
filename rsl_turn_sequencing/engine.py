from __future__ import annotations

from rsl_turn_sequencing.models import Actor

TM_MAX = 1430


def step_tick(actors: list[Actor]) -> Actor | None:
    """
    Advance the simulation by one global tick.

    Rules (foundation):
    - All actors fill simultaneously: turn_meter += speed
    - If nobody reaches TM_MAX, no one acts this tick
    - If one or more reach TM_MAX, the actor with the highest turn_meter acts
    - Acting resets that actor's turn_meter to 0 (overflow discarded)

    Tie-break (deterministic):
    - Higher turn_meter wins
    - If equal, higher speed wins
    - If still equal, earlier in the list wins
    """
    # 1) simultaneous fill
    for a in actors:
        a.turn_meter += a.speed

    # 2) find all ready actors
    ready = [a for a in actors if a.turn_meter >= TM_MAX]
    if not ready:
        return None

    # 3) choose actor: highest TM, then speed, then list order
    # Use index to make final tie-break stable
    indexed = list(enumerate(actors))
    ready_indexed = [(i, a) for (i, a) in indexed if a.turn_meter >= TM_MAX]
    i_best, best = max(ready_indexed, key=lambda t: (t[1].turn_meter, t[1].speed, -t[0]))

    # 4) act (for now, acting is just returning the actor) and reset TM to 0
    best.turn_meter = 0
    return best
