from __future__ import annotations

from rsl_turn_sequencing.models import Actor
from rsl_turn_sequencing.engine import TM_GATE
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
        print(f"\nTick {entry.tick:2d} | winner={entry.winner or '-'}")

        for a in entry.actors:
            eligible = "*" if a.turn_meter >= TM_GATE else " "
            print(
                f"  {a.name:<10s} "
                f"TM={a.turn_meter:7.1f}  "
                f"UI={a.ui_percent:6.1f}% {eligible}"
            )


if __name__ == "__main__":
    main()
