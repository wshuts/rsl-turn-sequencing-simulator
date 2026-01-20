from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable

from rsl_turn_sequencing.engine import build_actors_from_battle_spec, run_ticks
from rsl_turn_sequencing.event_sink import InMemoryEventSink
from rsl_turn_sequencing.models import Actor
from rsl_turn_sequencing.reporting import derive_turn_rows, group_rows_into_boss_frames
from rsl_turn_sequencing.skill_provider import SkillSequenceExhaustedError
from rsl_turn_sequencing.stream_io import (
    InputFormatError,
    dump_event_stream,
    load_battle_spec,
    load_event_stream,
)


def _demo_actors() -> list[Actor]:
    # v0 deterministic demo (kept minimal)
    boss = Actor(name="Boss", speed=1500.0, is_boss=True, shield=21, shield_max=21)
    a1 = Actor(name="A1", speed=2000.0)
    return [a1, boss]


def _actors_from_battle_spec(spec, *, champion_definitions_path: Path | None = None) -> list[Actor]:
    """Build actors from a battle spec.

    This is a compatibility shim. Actor construction is engine-owned
    (including dataset-derived state such as blessings).
    """
    return build_actors_from_battle_spec(spec, champion_definitions_path=champion_definitions_path)


def _fmt_shield(snap: object | None) -> str:
    if snap is None:
        return "--"
    value = getattr(snap, "value", None)
    status = getattr(snap, "status", None)
    if value is None or status is None:
        return "--"
    return f"{int(value)} {str(status)}"


def _render_text_report(*, boss_actor: str, events, row_index_start: int | None = None) -> str:
    from rsl_turn_sequencing.events import EventType

    def _skill_token_for_row(row) -> str | None:
        for e in row.events:
            if e.type == EventType.SKILL_CONSUMED:
                skill_id = e.data.get("skill_id")
                if isinstance(skill_id, str) and skill_id.strip():
                    return skill_id.strip()
        return None

    rows = derive_turn_rows(events)
    frames = group_rows_into_boss_frames(rows, boss_actor=boss_actor)

    out: list[str] = []
    if not frames:
        out.append("(No complete boss frames were produced. Try increasing --ticks.)")
        return "\n".join(out)

    row_idx = row_index_start

    for frame in frames:
        out.append(f"Boss Turn #{frame.boss_turn_index}")

        # Align output into fixed columns so the post-shield column doesn't
        # visually "jump" between rows depending on whether a skill token is present.
        #
        # Columns:
        #   [pre]  actor_name  {skill_token}  [post]
        #
        # The skill token column is padded to the maximum token width within the frame.
        tokens: list[str | None] = []
        for row in frame.rows:
            tokens.append(_skill_token_for_row(row))

        max_actor_len = max((len(row.actor) for row in frame.rows), default=0)
        max_token_len = max((len(f"{{{t}}}") for t in tokens if t), default=0)

        for row, tok in zip(frame.rows, tokens):
            pre = _fmt_shield(row.pre_shield)
            post = _fmt_shield(row.post_shield)

            actor_padded = row.actor.ljust(max_actor_len)
            token_cell = (f"{{{tok}}}" if tok else "")
            token_padded = token_cell.ljust(max_token_len) if max_token_len else ""

            if row_idx is None:
                if token_padded:
                    out.append(f"  [{pre}] {actor_padded} {token_padded} [{post}]")
                else:
                    out.append(f"  [{pre}] {actor_padded} [{post}]")
            else:
                if token_padded:
                    out.append(f"  {row_idx}: [{pre}] {actor_padded} {token_padded} [{post}]")
                else:
                    out.append(f"  {row_idx}: [{pre}] {actor_padded} [{post}]")
                row_idx += 1

        out.append("")

    return "\n".join(out).rstrip() + "\n"


def _is_boss_turn_end_event(evt: object, boss_actor: str) -> bool:
    """
    Detect a boss TURN_END event for both dict-like and Event dataclass events.

    In this repo baseline, sink.events contains Event objects with:
      - evt.actor: str | None
      - evt.type: EventType (enum) or str
    """
    # Event dataclass / object case
    actor = getattr(evt, "actor", None)
    etype = getattr(evt, "type", None)
    if actor is not None or etype is not None:
        if actor != boss_actor:
            return False
        # etype may be an Enum (EventType.TURN_END) or a string ("TURN_END")
        if hasattr(etype, "value"):
            return etype.value == "TURN_END"
        return str(etype) == "TURN_END"

    # Dict-like fallback (if you ever switch sinks)
    if isinstance(evt, dict):
        actor = evt.get("actor") or evt.get("winner") or evt.get("name")
        if actor != boss_actor:
            return False
        etype = evt.get("type") or evt.get("event_type") or evt.get("kind")
        if hasattr(etype, "value"):
            return etype.value == "TURN_END"
        return str(etype) == "TURN_END"

    return False



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
        sys.stdout.write(
            _render_text_report(
                boss_actor=str(args.boss_actor),
                events=events,
                row_index_start=args.row_index_start,
            )
        )
        return 0

    from rsl_turn_sequencing.events import EventType

    sink = InMemoryEventSink()

    if args.battle:
        battle_path = Path(str(args.battle))
        try:
            spec = load_battle_spec(battle_path)
            champion_defs_path = Path(str(args.champion_defs)) if getattr(args, "champion_defs", None) else None
            actors = _actors_from_battle_spec(spec, champion_definitions_path=champion_defs_path)
        except InputFormatError as e:
            print(f"ERROR: invalid battle spec: {e}", file=sys.stderr)
            return 2
    else:
        actors = _demo_actors()

    boss_actor = str(args.boss_actor)
    stop_after = args.stop_after_boss_turns

    try:
        run_ticks(
            actors=actors,
            event_sink=sink,
            ticks=int(args.ticks),
            hit_provider=None,
            battle_path_for_mastery_procs=Path(str(args.battle)) if args.battle else None,
            stop_after_boss_turns=int(stop_after) if stop_after is not None else None,
            boss_actor=boss_actor,
        )
    except SkillSequenceExhaustedError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    except InputFormatError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    if getattr(args, "events_out", None):
        out_path = Path(str(args.events_out))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(dump_event_stream(sink.events), indent=2), encoding="utf-8")

    sys.stdout.write(
        _render_text_report(
            boss_actor=boss_actor,
            events=sink.events,
            row_index_start=args.row_index_start,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog="rsl_turn_sequencing",
        description=(
            "RSL Turn Sequencing Simulator — user harness.\n"
            "\n"
            "Observer-only: no HP/damage math.\n"
            "Prints Boss Turn Frames with PRE/POST shield snapshots."
        ),
    )

    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run a simulation and print Boss Turn Frames.")
    run.add_argument("--demo", action="store_true", help="Run the built-in deterministic demo roster.")
    run.add_argument("--battle", type=str, help="Run a battle spec JSON.")
    run.add_argument(
        "--champion-defs",
        dest="champion_defs",
        type=str,
        default=None,
        help=(
            "Optional: path to champion definitions JSON (blessings, etc.). "
            "When provided, the engine hydrates Actor.blessings from this file."
        ),
    )
    run.add_argument("--input", type=str, help="Render an existing event stream JSON.")
    run.add_argument("--ticks", type=int, default=50, help="Safety cap: max ticks to simulate.")
    run.add_argument("--boss-actor", type=str, default="Boss", help="Actor name used to close frames.")
    run.add_argument(
        "--row-index-start",
        type=int,
        default=None,
        help="Optional: prefix each printed actor row with an incrementing index starting at this value.",
    )
    run.add_argument(
        "--stop-after-boss-turns",
        type=int,
        default=None,
        help=(
            "Stop the simulation immediately after the boss completes this many turns "
            "(i.e., after the boss TURN_END of Boss Turn #N). Overrides tick-guessing."
        ),
    )
    run.add_argument(
        "--events-out",
        type=str,
        default=None,
        help=(
            "Optional: write the full event stream to this JSON path "
            "(dumped as an array of {tick, seq, type, actor, data})."
        ),
    )

    run.set_defaults(func=_cmd_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
