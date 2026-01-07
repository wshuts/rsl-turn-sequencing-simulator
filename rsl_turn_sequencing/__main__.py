from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
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


class SkillSequenceExhaustedError(RuntimeError):
    """Raised when a skill_sequence is exhausted under a fail-fast policy."""


def _demo_actors() -> list[Actor]:
    # v0 deterministic demo (kept minimal)
    boss = Actor(name="Boss", speed=1500.0, is_boss=True, shield=21, shield_max=21)
    a1 = Actor(name="A1", speed=2000.0)
    return [a1, boss]


def _actors_from_battle_spec(spec) -> list[Actor]:
    actors: list[Actor] = []
    for a in spec.actors:
        speed = float(a.speed)
        # v0: if a form is provided, allow a speed override via speed_by_form.
        if a.form_start and a.speed_by_form and a.form_start in a.speed_by_form:
            speed = float(a.speed_by_form[a.form_start])
        actors.append(
            Actor(
                a.name,
                speed,
                faction=a.faction,
                skill_sequence=list(a.skill_sequence) if a.skill_sequence is not None else None,
            )
        )

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
            skill_sequence=list(spec.boss.skill_sequence) if spec.boss.skill_sequence is not None else None,
        )
    )

    return actors


def _consume_next_skill(
        *,
        actors: list[Actor],
        actor_name: str,
        sequence_policy: str | None,
) -> str | None:
    """Consume and return the next skill id for the given actor, if any.

    This function does not interpret skill ids; it only advances the cursor.
    """
    if not sequence_policy:
        return None
    if sequence_policy != "error_if_exhausted":
        return None

    actor = next((a for a in actors if a.name == actor_name), None)
    if actor is None:
        return None
    seq = getattr(actor, "skill_sequence", None)
    if not seq:
        return None

    cursor = int(getattr(actor, "skill_sequence_cursor", 0))
    if cursor >= len(seq):
        raise SkillSequenceExhaustedError(
            f"skill_sequence exhausted for {actor.name} (len={len(seq)}, cursor={cursor})"
        )

    skill_id = str(seq[cursor])
    actor.skill_sequence_cursor = cursor + 1
    return skill_id


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

        # Determine padding width for actor labels (actor name + optional token) in this frame.
        labels: list[str] = []
        for row in frame.rows:
            tok = _skill_token_for_row(row)
            labels.append(f"{row.actor} ({tok})" if tok else row.actor)

        max_actor_len = max(len(label) for label in labels) if labels else 0

        for row, label in zip(frame.rows, labels):
            pre = _fmt_shield(row.pre_shield)
            post = _fmt_shield(row.post_shield)

            actor_padded = label.ljust(max_actor_len)

            if row_idx is None:
                out.append(f"  [{pre}] {actor_padded} [{post}]")
            else:
                out.append(f"  {row_idx}: [{pre}] {actor_padded} [{post}]")
                row_idx += 1

        out.append("")

    return "\n".join(out).rstrip() + "\n"


def _load_hits_by_actor(path: Path) -> dict[str, int]:
    """Legacy shim (kept for backwards compatibility)."""
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


# ----------------------------
# Skill → Hits lookup (dataset)
# ----------------------------

@dataclass(frozen=True)
class _ResolvedSkill:
    form: str | None
    key: str


class _ChampionHitLookup:
    """Lookup hits-per-skill using data/champions_fire_knight_team.json.

    IMPORTANT: If an actor is not found in the dataset, we return hits=0 (no error),
    so generic battle specs (e.g., sequence-policy tests with dummy actors) still work.

    For known champions, unknown skill ids are treated as an InputFormatError.
    """

    def __init__(self, payload: dict):
        champs = payload.get("champions", [])
        if not isinstance(champs, list):
            raise InputFormatError("champions_fire_knight_team.json: champions must be an array")

        self._by_id: dict[str, dict] = {}
        self._by_name: dict[str, dict] = {}
        for c in champs:
            if not isinstance(c, dict):
                continue
            cid = str(c.get("id", "")).strip().lower()
            name = str(c.get("name", "")).strip().lower()
            if cid:
                self._by_id[cid] = c
            if name:
                self._by_name[name] = c

    @staticmethod
    def _resolve_skill(actor_name: str, skill_id: str) -> _ResolvedSkill:
        a = (actor_name or "").strip().lower()
        s = (skill_id or "").strip()

        # Mikage narrated spec tokens: A_A1, A_A4, B_A3...
        if a in {"mikage", "lady mikage"} and "_" in s:
            prefix, rest = s.split("_", 1)
            prefix = prefix.strip().upper()
            rest = rest.strip().upper()
            form = "base" if prefix == "A" else "alternate"
            if rest == "A4":
                return _ResolvedSkill(form=form, key="METAMORPH")
            return _ResolvedSkill(form=form, key=rest)

        return _ResolvedSkill(form=None, key=s.strip().upper())

    def _find_champion(self, actor_name: str) -> dict | None:
        key = (actor_name or "").strip().lower()
        if not key:
            return None
        if key in self._by_id:
            return self._by_id[key]
        if key in self._by_name:
            return self._by_name[key]

        # Prefix-name match (must be unique)
        matches = [c for n, c in self._by_name.items() if n.startswith(key)]
        if len(matches) == 1:
            return matches[0]
        return None

    def hits_for(self, actor_name: str, skill_id: str) -> int:
        champ = self._find_champion(actor_name)
        if champ is None:
            # Unknown actor => do not error; treat as no shield hits.
            return 0

        resolved = self._resolve_skill(actor_name, skill_id)

        # Mikage: form-aware
        if "forms" in champ:
            forms = champ.get("forms", {})
            if not isinstance(forms, dict):
                raise InputFormatError(f"invalid forms block for actor {actor_name!r}")
            form = resolved.form or champ.get("defaults", {}).get("starting_form", "base")
            form_block = forms.get(form)
            if not isinstance(form_block, dict):
                raise InputFormatError(f"unknown form {form!r} for actor {actor_name!r}")
            skills = form_block.get("skills", {})
            if not isinstance(skills, dict):
                raise InputFormatError(f"invalid skills block for actor {actor_name!r} form {form!r}")
            skill = skills.get(resolved.key)
        else:
            skills = champ.get("skills", {})
            if not isinstance(skills, dict):
                raise InputFormatError(f"invalid skills block for actor {actor_name!r}")
            skill = skills.get(resolved.key)

        if not isinstance(skill, dict):
            raise InputFormatError(
                f"unknown skill {skill_id!r} (resolved key={resolved.key!r}) for actor {actor_name!r}"
            )

        hits = skill.get("hits", 0)
        if not isinstance(hits, int):
            raise InputFormatError(f"invalid hits for {actor_name!r} {resolved.key!r}: must be int")
        return int(hits)


def _load_fk_dataset_hit_lookup() -> _ChampionHitLookup:
    """
    Locate data/champions_fire_knight_team.json reliably regardless of whether the
    package is installed in-place, under src/, or executed from tests.

    Strategy:
      - Walk upward from this file's directory, looking for /data/champions_fire_knight_team.json
      - First match wins
    """
    here = Path(__file__).resolve()

    # search up to 8 levels just to be safe
    for parent in [here.parent, *here.parents]:
        data_path = parent / "data" / "champions_fire_knight_team.json"
        if data_path.exists():
            payload = json.loads(data_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise InputFormatError("champions_fire_knight_team.json root must be an object")
            return _ChampionHitLookup(payload)

    raise InputFormatError(
        "FK dataset not found. Expected data/champions_fire_knight_team.json somewhere above "
        f"{here} in the directory tree."
    )


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

    hit_provider: Callable[[str], dict[str, int]] | None = None

    if args.battle:
        battle_path = Path(str(args.battle))
        try:
            spec = load_battle_spec(battle_path)
            actors = _actors_from_battle_spec(spec)
            hits_by_actor = _load_hits_by_actor(battle_path)  # legacy fallback
        except InputFormatError as e:
            print(f"ERROR: invalid battle spec: {e}", file=sys.stderr)
            return 2

        sequence_policy = spec.options.sequence_policy

        try:
            hits_lookup = _load_fk_dataset_hit_lookup()
        except InputFormatError as e:
            print(f"ERROR: cannot load FK dataset: {e}", file=sys.stderr)
            return 2

        def _provider(winner: str) -> dict[str, int]:
            skill_id = _consume_next_skill(
                actors=actors,
                actor_name=winner,
                sequence_policy=sequence_policy,
            )
            if skill_id:
                sink.emit(EventType.SKILL_CONSUMED, actor=winner, skill_id=skill_id)
                hits = hits_lookup.hits_for(winner, skill_id)
            else:
                hits = int(hits_by_actor.get(winner, 0))
            return {winner: hits} if hits > 0 else {}

        hit_provider = _provider
    else:
        actors = _demo_actors()

    boss_actor = str(args.boss_actor)
    stop_after = args.stop_after_boss_turns
    boss_turns_seen = 0

    # We still honor --ticks as a safety cap.
    try:
        for _ in range(int(args.ticks)):
            before_len = len(sink.events)
            step_tick(actors, event_sink=sink, hit_provider=hit_provider)

            if stop_after is not None:
                new_events = sink.events[before_len:]
                # Count boss TURN_END events, because a Boss Turn Frame is only "complete"
                # after the boss has ended its turn.
                for evt in new_events:
                    if _is_boss_turn_end_event(evt, boss_actor=boss_actor):
                        boss_turns_seen += 1
                        if boss_turns_seen >= int(stop_after):
                            raise StopIteration

    except StopIteration:
        # Normal stop condition: boss has completed N turns.
        pass
    except SkillSequenceExhaustedError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    except InputFormatError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

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
    run.set_defaults(func=_cmd_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
