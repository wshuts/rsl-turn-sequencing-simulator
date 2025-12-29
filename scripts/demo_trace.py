from __future__ import annotations

from rsl_turn_sequencing.models import Actor
from rsl_turn_sequencing.trace import run_ticks_with_trace


def main() -> None:
    actors = [
        Actor("Mikage", 340.0),
        Actor("Mithrala", 282.0),
        Actor("Tomblord", 270.0),
        Actor("Coldheart", 265.0),
        Actor("Martyr", 252.0),
        Actor("Boss", 250.0),
    ]

    log = run_ticks_with_trace(actors, 12)

    for entry in log:
        ui = ", ".join(f"{a.name}:{a.ui_percent:6.1f}%" for a in entry.actors)
        print(f"Tick {entry.tick:2d} | winner={entry.winner or '-':8s} | {ui}")


if __name__ == "__main__":
    main()
