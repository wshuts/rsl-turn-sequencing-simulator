from __future__ import annotations

import argparse
import sys

from rsl_turn_sequencing.engine import step_tick
from rsl_turn_sequencing.event_sink import InMemoryEventSink
from rsl_turn_sequencing.models import Actor
from rsl_turn_sequencing.reporting import derive_turn_rows, group_rows_into_boss_frames


def _demo_actors() -> list[Actor]:
    # Baseline, deterministic demo roster.
    return [
        Actor("Mikage", 340.0),
        Actor("Mithrala", 282.0),
        Actor("Tomblord", 270.0),
        Actor("Coldheart", 265.0),
        Actor("Martyr", 252.0),
        Actor("Boss", 250.0),
    ]


def _fmt_shield(snap: object | None) -> str:
    if snap is None:
        return "--"
    # ShieldSnapshot dataclass: value, status
    value = getattr(snap, "value", None)
    status = getattr(snap, "status", None)
    if value is None or status is None:
        return "--"
    return f"{int(value)} {str(status)}"


def _render_text_report(*, boss_actor: str, sink: InMemoryEventSink) -> str:
    rows = derive_turn_rows(sink.events)
    frames = group_rows_into_boss_frames(rows, boss_actor=boss_actor)

    out: list[str] = []
    if not frames:
        out.append("(No complete boss frames were produced. Try increasing --ticks.)")
        return "\n".join(out)

    for frame in frames:
        out.append(f"Boss Turn #{frame.boss_turn_index}")
        for row in frame.rows:
            pre = _fmt_shield(row.pre_shield)
            post = _fmt_shield(row.post_shield)
            out.append(f"  [{pre:<10s}] {row.actor} [{post}]")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def _cmd_run(args: argparse.Namespace) -> int:
    if not args.demo:
        # Epic D2 will introduce a structured input contract.
        print(
            "ERROR: v0 only supports --demo.\n"
            "\n"
            "Next planned step (Epic D2): load an ordered structured event stream from --input.",
            file=sys.stderr,
        )
        return 2

    actors = _demo_actors()
    sink = InMemoryEventSink()

    for _ in range(int(args.ticks)):
        step_tick(actors, event_sink=sink)

    sys.stdout.write(_render_text_report(boss_actor=str(args.boss_actor), sink=sink))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog="rsl_turn_sequencing",
        description=(
            "RSL Turn Sequencing Simulator — user harness (Epic D).\n"
            "\n"
            "This CLI is observer-only: it does not change engine rules.\n"
            "It runs a deterministic simulation and prints Boss Turn Frames."
        )
    )

    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser(
        "run",
        help="Run a simulation and print Boss Turn Frames.",
    )
    run.add_argument(
        "--demo",
        action="store_true",
        help="Run the built-in deterministic demo roster (v0).",
    )
    run.add_argument(
        "--ticks",
        type=int,
        default=200,
        help="Maximum global ticks to simulate (default: 200).",
    )
    run.add_argument(
        "--boss-actor",
        default="Boss",
        help="Actor name used to close Boss Turn Frames (default: 'Boss').",
    )
    run.set_defaults(func=_cmd_run)
