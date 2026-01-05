from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable

from rsl_turn_sequencing.engine import step_tick
from rsl_turn_sequencing.event_sink import InMemoryEventSink
from rsl_turn_sequencing.models import Actor
from rsl_turn_sequencing.reporting import derive_turn_rows, group_rows_into_boss_frames
from rsl_turn_sequencing.stream_io import (
    InputFormatError,
    load_battle_spec,
    load_event_stream,
)


def _demo_actors() -> list[Actor]:
    # v0 deterministic demo (kept minimal)
    boss = Actor(name="Boss", speed=1500.0, is_boss=True, shield=21, shield_max=21)
    a1 = Actor(name="A1", speed=2000.0)
    return [a1, boss]


def _actors_from_battle_spec(path: Path) -> list[Actor]:
    spec = load_battle_spec(path)

    actors: list[Actor] = []
    for a in spec.actors:
        speed = float(a.speed)
        # v0: if a form is provided, allow a speed override via speed_by_form.
        if a.form_start and a.speed_by_form and a.form_start in a.speed_by_form:
            speed = float(a.speed_by_form[a.form_start])
        actors.append(Actor(a.name, speed, faction=a.faction))

    boss_speed = float(spec.boss.speed)
    if spec.boss.form_start and spec.boss.speed_by_form and spec.boss.form_start in spec.boss.speed_by_form:
        boss_speed = float(spec.boss.speed_by_form[spec.boss.form_start])

    boss_shield_max = spec.boss.shield_max
    boss_shield_start = int(boss_shield_max) if boss_shield_max is not None else 0

    actors.append(
        Actor(
            spec.boss.name,
            boss_speed,
            is_boss=True,
            shield=boss_shield_start,
            shield_max=boss_shield_max,
            faction=spec.boss.faction,
        )
    )

    return actors


def _fmt_shield(snap: object | None) -> str:
    if snap is None:
        return "--"
    value = getattr(snap, "value", None)
    status = getattr(snap, "status", None)
    if value is None or status is None:
        return "--"
    return f"{int(value)} {str(status)}"


def _render_text_report(*, boss_actor: str, events) -> str:
    rows = derive_turn_rows(events)
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


def _load_hits_by_actor(path: Path) -> dict[str, int]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    hits = raw.get("hits_by_actor", None)
    if hits is None:
        return {}
    if not isinstance(hits, dict):
        raise InputFormatError("hits_by_actor must be an object mapping actor name -> int hits")
    out: dict[str, int] = {}
    for k, v in hits.items():
        if not isinstance(k, str) or not k.strip():
            raise InputFormatError("hits_by_actor keys must be non-empty strings")
        if not isinstance(v, int):
            raise InputFormatError(f"hits_by_actor[{k!r}] must be an int")
        out[k] = int(v)
    return out


def _cmd_run(args: argparse.Namespace) -> int:
    chosen = sum(1 for v in [bool(args.demo), bool(args.battle), bool(args.input)] if v)
    if chosen != 1:
        print("ERROR: choose exactly one of --demo, --battle, or --input.", file=sys.stderr)
        return 2

    if args.input:
        try:
            events = load_event_stream(Path(str(args.input)))
        except InputFormatError as e:
            print(f"ERROR: invalid input stream: {e}", file=sys.stderr)
            return 2
        sys.stdout.write(_render_text_report(boss_actor=str(args.boss_actor), events=events))
        return 0

    hit_provider: Callable[[str], dict[str, int]] | None = None

    if args.battle:
        battle_path = Path(str(args.battle))
        try:
            actors = _actors_from_battle_spec(battle_path)
            hits_by_actor = _load_hits_by_actor(battle_path)
        except InputFormatError as e:
            print(f"ERROR: invalid battle spec: {e}", file=sys.stderr)
            return 2

        # v0: apply hits only for the current winner's turn
        def _provider(winner: str) -> dict[str, int]:
            hits = int(hits_by_actor.get(winner, 0))
            return {winner: hits} if hits > 0 else {}

        hit_provider = _provider
    else:
        actors = _demo_actors()

    sink = InMemoryEventSink()

    for _ in range(int(args.ticks)):
        step_tick(actors, event_sink=sink, hit_provider=hit_provider)

    sys.stdout.write(_render_text_report(boss_actor=str(args.boss_actor), events=sink.events))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog="rsl_turn_sequencing",
        description=(
            "RSL Turn Sequencing Simulator — user harness (Epic D).\n"
            "\n"
            "This CLI is observer-only: it does not change HP or do damage math.\n"
            "It prints Boss Turn Frames with PRE/POST shield snapshots."
        ),
    )

    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run a simulation and print Boss Turn Frames.")
    run.add_argument("--demo", action="store_true", help="Run the built-in deterministic demo roster (v0).")
    run.add_argument("--battle", type=str, help="Run a minimal battle spec JSON.")
    run.add_argument("--input", type=str, help="Render an existing event stream JSON.")
    run.add_argument("--ticks", type=int, default=50, help="Number of ticks to simulate.")
    run.add_argument("--boss-actor", type=str, default="Boss", help="Actor name used to close frames.")
    run.set_defaults(func=_cmd_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
