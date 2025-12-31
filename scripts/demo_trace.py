from __future__ import annotations

from rsl_turn_sequencing.engine import TM_GATE
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
        if entry.winner is None:
            print(f"\nTick {entry.tick:2d} | winner=-")
        else:
            # Show the pre-reset TM used to decide the winner
            wb = entry.winner_before if entry.winner_before is not None else float("nan")
            ui_wb = (wb / TM_GATE) * 100.0
            print(f"\nTick {entry.tick:2d} | winner={entry.winner} (pre-reset TM={wb:7.1f}, UI={ui_wb:6.1f}%)")

        for a in entry.actors:
            # Eligibility is determined on the pre-reset ("winning snapshot") TM values
            eligible = "*" if a.eligible_before else " "
            print(
                f"  {a.name:<10s} "
                f"TM(pre)={a.turn_meter_before:7.1f}  UI(pre)={a.ui_percent_before:6.1f}% {eligible}  "
                f"TM(post)={a.turn_meter_after:7.1f}"
            )


if __name__ == "__main__":
    main()
