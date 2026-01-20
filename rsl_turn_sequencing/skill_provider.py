from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from rsl_turn_sequencing.event_sink import EventSink
from rsl_turn_sequencing.events import EventType
from rsl_turn_sequencing.models import Actor
from rsl_turn_sequencing.skill_buffs import apply_skill_buffs
from rsl_turn_sequencing.stream_io import InputFormatError


class SkillSequenceExhaustedError(RuntimeError):
    """Raised when a skill_sequence is exhausted under a fail-fast policy."""


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


def _apply_skill_side_effects(
    *,
    actors: list[Actor],
    actor_name: str,
    skill_id: str,
    event_sink: EventSink | None,
) -> None:
    """Apply observer-faithful side effects for select skills.

    The simulator is intentionally "observer-only" (no combat math), but some
    skills affect turn sequencing directly. These side effects must be modeled
    so turn order and CLI traces match real-battle expectations.

    Currently implemented:
      - Mikage Metamorph: grants an immediate extra turn.
      - Slice 2: Mikage Base A3: places team buffs (Increase ATK, Increase C.DMG).

    Notes:
      - We keep this narrowly scoped. Unknown skills do nothing.
      - We match Mikage by display name used in the sample specs.
      - We accept both narrated tokens (A_A4 / B_A4) and dataset key "METAMORPH".
    """

    if not skill_id:
        return

    a = (actor_name or "").strip().lower()
    s = (skill_id or "").strip().upper()

    # Mikage Metamorph -> immediate extra turn
    if a in {"mikage", "lady mikage"} and s in {"A_A4", "B_A4", "METAMORPH"}:
        actor = next((x for x in actors if x.name == actor_name), None)
        if actor is None:
            return
        # Metamorph grants an immediate extra turn. The engine will preempt
        # the next tick's fill when extra_turns > 0.
        actor.extra_turns = int(getattr(actor, "extra_turns", 0)) + 1
        return

    # Deterministic BUFF placements (acceptance-driven).
    # We do not model combat math here; only BUFF state materialization.
    apply_skill_buffs(
        actors=actors,
        actor_name=actor_name,
        skill_id=skill_id,
        event_sink=event_sink,
    )


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
                raise InputFormatError(
                    f"invalid skills block for actor {actor_name!r} form {form!r}"
                )
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
            raise InputFormatError(
                f"invalid hits for {actor_name!r} {resolved.key!r}: must be int"
            )
        return int(hits)


def _load_fk_dataset_hit_lookup() -> _ChampionHitLookup:
    """Load data/champions_fire_knight_team.json.

    Locate it reliably regardless of whether the package is installed in-place,
    under src/, or executed from tests.
    """
    here = Path(__file__).resolve()

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


def build_hit_provider_from_battle_path(
    *,
    battle_path: Path,
    actors: list[Actor],
    event_sink: EventSink,
) -> Callable[[str], dict[str, int]]:
    """Engine-owned hit_provider builder.

    This function replaces the __main__ closure `_provider(winner)`.
    It is intentionally observer-only: it consumes skill tokens, emits
    SKILL_CONSUMED, applies narrowly-scoped side effects, and returns
    base hit counts for shield math.
    """

    # Read spec for sequence_policy.
    try:
        raw = json.loads(battle_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise InputFormatError(f"invalid battle spec JSON: {e}")
    if not isinstance(raw, dict):
        raise InputFormatError("battle spec root must be an object")

    options = raw.get("options", {})
    if not isinstance(options, dict):
        options = {}
    sequence_policy = options.get("sequence_policy")
    if isinstance(sequence_policy, str):
        sequence_policy = sequence_policy.strip() or None
    else:
        sequence_policy = None

    hits_by_actor = _load_hits_by_actor(battle_path)
    hits_lookup = _load_fk_dataset_hit_lookup()

    def _provider(winner: str) -> dict[str, int]:
        skill_id = _consume_next_skill(
            actors=actors,
            actor_name=winner,
            sequence_policy=sequence_policy,
        )
        if skill_id:
            event_sink.emit(EventType.SKILL_CONSUMED, actor=winner, skill_id=skill_id)
            _apply_skill_side_effects(
                actors=actors,
                actor_name=winner,
                skill_id=skill_id,
                event_sink=event_sink,
            )
            hits = hits_lookup.hits_for(winner, skill_id)
        else:
            hits = int(hits_by_actor.get(winner, 0))
        return {winner: hits} if hits > 0 else {}

    return _provider
