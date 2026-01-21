from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Protocol

from rsl_turn_sequencing.effects import (
    apply_turn_start_effects,
    decrement_turn_end,
    speed_multiplier_from_effects,
)
from rsl_turn_sequencing.event_sink import EventSink
from rsl_turn_sequencing.events import EventType
from rsl_turn_sequencing.models import Actor, EffectInstance
from rsl_turn_sequencing.skill_provider import build_hit_provider_from_battle_path

TM_GATE = 1430.0
EPS = 1e-9


class ExpirationResolver(Protocol):
    """Phase-aware expiration resolver.

    This is a dependency-injection seam used by BOTH production and tests.

    The engine will call the resolver at *authoritative expiration phases*:
      - TURN_START phase (begin-of-turn triggers/decrements)
      - TURN_END phase (end-of-turn decrements/expiry)

    The resolver MUST NOT invent state. It may only request expiration of
    effect instances that already exist in the current effect state.

    Return value:
      - Iterable of schema-backed requests, currently supporting:
        {"type":"expire_effect","instance_id":"...","reason":"injected"}
    """

    def __call__(self, ctx: dict[str, Any]) -> list[dict[str, Any]]: ...


class HitContributionResolver(Protocol):
    """Resolve additional shield-hit contributions for the current acting tick.

    The engine owns shield math. This resolver is a DI seam for rule-driven
    hit contributors that are NOT intrinsic to a single actor's skill.

    Examples (modeled by dedicated rule components):
      - Phantom Touch procs
      - Faultless Defense reflect hits
      - Counterattack hits
      - Ally-attack (join attack) contributions

    Contract:
      - MUST return a mapping of contributor -> hit_count.
      - MUST NOT mutate engine state.
      - SHOULD return {} when no additional hits apply.
      - Reserved contributor key: "REFLECT" (reflect-style shield hits).
    """

    def __call__(
        self,
        *,
        acting_actor: "Actor",
        actors: list["Actor"],
        base_hits: dict[str, int],
        turn_counter: int,
        tick: int,
    ) -> dict[str, int]: ...


def _default_hit_contribution_resolver(
    *,
    acting_actor: "Actor",
    actors: list["Actor"],
    base_hits: dict[str, int],
    turn_counter: int,
    tick: int,
) -> dict[str, int]:
    """Engine-owned default resolver for additional shield-hit contributors.

    For now, this resolver implements a deterministic subset of rule behavior.

    Implemented rules:
      - Phantom Touch: if an actor with the Phantom Touch blessing contributes
        one or more base hits during this acting tick, add exactly +1 hit for
        that same actor.
      - Faultless Defense (reflect): when the boss attacks, for each ally that
        is under an Increase DEF buff placed by the blessing holder, emit an
        additional reflect-style shield hit.

    Notes:
      - Proc chance is ignored (deterministic).
      - Cooldowns are ignored for now (stateless behavior).
      - Reserved contributor key: "REFLECT" (reflect-style shield hits).
    """

    # Map for quick lookup.
    by_name: dict[str, Actor] = {a.name: a for a in actors}

    extra: dict[str, int] = {}

    # Boss-turn reactive contributors (shield hits applied during boss turns).
    if bool(getattr(acting_actor, "is_boss", False)):
        allies = [a for a in actors if not bool(getattr(a, "is_boss", False))]

        # Determine which boss skill was just consumed (when driven by a
        # skill_sequence). This enables minimal, deterministic distinctions
        # between AoE boss turns (A2) and single-target boss turns (A1).
        try:
            bseq = getattr(acting_actor, "skill_sequence", None) or []
            bcursor = int(getattr(acting_actor, "skill_sequence_cursor", 0))
            boss_last_skill = str(bseq[bcursor - 1]) if bcursor > 0 and bcursor <= len(bseq) else ""
        except Exception:
            boss_last_skill = ""

        # Faultless Defense: reflect-style hits against the boss shield.
        # We model this as a reserved contributor bucket "REFLECT".
        reflect_hits = 0

        for holder in allies:
            fd_cfg = holder.blessings.get("faultless_defense")
            if not isinstance(fd_cfg, dict):
                continue
            modeling = fd_cfg.get("modeling")
            if not isinstance(modeling, dict):
                continue
            emits = modeling.get("emits_hit_event")
            if not isinstance(emits, dict):
                continue
            try:
                per_target = int(emits.get("count", 1))
            except Exception:
                per_target = 1
            if per_target <= 0:
                continue

            # Determine which allies qualify: Increase DEF buff on target placed by holder.
            for target in allies:
                for fx in getattr(target, "active_effects", []) or []:
                    if getattr(fx, "effect_kind", None) != "BUFF":
                        continue
                    if getattr(fx, "effect_id", None) != "increase_def":
                        continue
                    if getattr(fx, "placed_by", None) != holder.name:
                        continue
                    reflect_hits += per_target
                    break

        if reflect_hits > 0:
            extra["REFLECT"] = int(extra.get("REFLECT", 0)) + int(reflect_hits)

        # Counterattack: when the boss attacks, allies with a Counterattack BUFF
        # respond with an A1. We model this as additional normal hits contributed
        # by each qualifying ally.
        #
        # This is intentionally a shield-math-only approximation (no ordering or
        # per-hit event emission yet).
        # Counterattack targeting scope depends on the boss's attack pattern.
        # Fire Knight's A1 and A2 both "attack all enemies" per data/fire_knight_boss.json,
        # so allies with Counterattack are *independently* eligible to respond.
        #
        # We keep the old "boss A1 is single-target" shortcut only for non-Fire-Knight
        # bosses until we have data-driven targeting for other encounters.
        is_fire_knight = "fire knight" in acting_actor.name.lower()
        if (not is_fire_knight) and boss_last_skill.strip().upper() == "A1" and allies:
            try:
                def _a1(a: Actor) -> int:
                    return int(getattr(a, "_a1_hits", 1))
                counterattack_targets = [max(allies, key=lambda a: (_a1(a), a.speed, a.name))]
            except Exception:
                counterattack_targets = [allies[0]]
        else:
            counterattack_targets = list(allies)

        for target in counterattack_targets:
            has_counterattack = False
            for fx in getattr(target, "active_effects", []) or []:
                if getattr(fx, "effect_kind", None) != "BUFF":
                    continue
                if getattr(fx, "effect_id", None) != "counterattack":
                    continue
                has_counterattack = True
                break
            if not has_counterattack:
                continue

            # Hydrated from champion definitions when available.
            try:
                a1_hits = int(getattr(target, "_a1_hits", 1))
            except Exception:
                a1_hits = 1
            if a1_hits <= 0:
                continue
            extra[target.name] = int(extra.get(target.name, 0)) + int(a1_hits)

            # Phantom Touch can also proc on counterattacks. We treat the
            # counterattack A1 as a normal hit contribution for the purpose of
            # deterministic Phantom Touch (+1) modeling.
            phantom_cfg = target.blessings.get("phantom_touch")
            if isinstance(phantom_cfg, dict):
                extra[target.name] = int(extra.get(target.name, 0)) + 1

    # Mikage Ally Attack (minimal): Mikage's narrated B_A3 is modeled as an
    # ally-attack style contribution that does not appear as direct hits on the
    # Mikage skill itself in the FK dataset.
    #
    # Deterministic selection: choose the ally (excluding Mikage and the boss)
    # with the highest A1 hit count.
    try:
        seq = getattr(acting_actor, "skill_sequence", None) or []
        cursor = int(getattr(acting_actor, "skill_sequence_cursor", 0))
        last_skill = str(seq[cursor - 1]) if cursor > 0 and cursor <= len(seq) else ""
    except Exception:
        last_skill = ""

    if (acting_actor.name or "").strip().lower() in {"mikage", "lady mikage"} and last_skill.strip().upper() == "B_A3":
        candidates = [a for a in actors if (not bool(getattr(a, "is_boss", False))) and a is not acting_actor]
        if candidates:
            def _a1(a: Actor) -> int:
                try:
                    return int(getattr(a, "_a1_hits", 1))
                except Exception:
                    return 1
            joiner = max(candidates, key=lambda a: (_a1(a), a.speed, a.name))
            hits = max(0, _a1(joiner))
            if hits > 0:
                extra[joiner.name] = int(extra.get(joiner.name, 0)) + hits
                phantom_cfg = joiner.blessings.get("phantom_touch")
                if isinstance(phantom_cfg, dict):
                    extra[joiner.name] = int(extra.get(joiner.name, 0)) + 1
    for contributor, hits in base_hits.items():
        if contributor == "REFLECT":
            continue
        try:
            base = int(hits)
        except Exception:
            continue
        if base <= 0:
            continue

        actor = by_name.get(contributor)
        if actor is None:
            continue
        phantom_cfg = actor.blessings.get("phantom_touch")
        if isinstance(phantom_cfg, dict):
            extra[contributor] = int(extra.get(contributor, 0)) + 1

    return extra




def build_actors_from_battle_spec(
    spec: object,
    *,
    champion_definitions_path: Path | None = None,
) -> list[Actor]:
    """Build Actor instances from a loaded battle spec.

    This is an engine-owned construction step.

    Blessings:
      - When champion_definitions_path is provided, blessings are hydrated from
        that JSON file (matched by champion name, case-insensitive).
      - When champion_definitions_path is None, no blessings are applied.

    The battle spec is produced by rsl_turn_sequencing.stream_io.load_battle_spec.
    """

    champion_defs: dict[str, dict[str, Any]] = {}
    if champion_definitions_path is not None:
        try:
            raw = json.loads(Path(champion_definitions_path).read_text(encoding='utf-8'))
            if isinstance(raw, dict) and isinstance(raw.get('champions'), list):
                for c in raw['champions']:
                    if not isinstance(c, dict):
                        continue
                    name = c.get('name')
                    if isinstance(name, str) and name.strip():
                        champion_defs[name.strip().lower()] = c
        except Exception:
            champion_defs = {}

    def _champion_def_for(name: str) -> dict[str, Any] | None:
        if not champion_defs:
            return None
        c = champion_defs.get((name or "").strip().lower())
        return c if isinstance(c, dict) else None

    def _blessings_for(name: str) -> dict[str, Any]:
        if not champion_defs:
            return {}
        c = _champion_def_for(name)
        if not isinstance(c, dict):
            return {}
        b = c.get('blessings')
        return dict(b) if isinstance(b, dict) else {}

    def _a1_hits_for(name: str) -> int:
        """Best-effort A1 hit count from champion definitions.

        Used for counterattack shield-hit contributions during boss turns.
        If champion definitions are not present or malformed, default to 1.
        """
        c = _champion_def_for(name)
        if not isinstance(c, dict):
            return 1

        # Mikage / multi-form champions: attempt to use the declared starting form.
        forms = c.get("forms")
        if isinstance(forms, dict):
            defaults = c.get("defaults")
            starting_form = None
            if isinstance(defaults, dict):
                starting_form = defaults.get("starting_form")
            if not isinstance(starting_form, str) or not starting_form:
                starting_form = "base"

            form_block = forms.get(starting_form)
            if isinstance(form_block, dict):
                skills = form_block.get("skills")
                if isinstance(skills, dict):
                    a1 = skills.get("A1")
                    if isinstance(a1, dict) and isinstance(a1.get("hits"), int):
                        return int(a1.get("hits"))

        # Single-form champions.
        skills = c.get("skills")
        if isinstance(skills, dict):
            a1 = skills.get("A1")
            if isinstance(a1, dict) and isinstance(a1.get("hits"), int):
                return int(a1.get("hits"))

        return 1

    actors: list[Actor] = []

    for a in getattr(spec, 'actors', []):
        speed = float(getattr(a, 'speed'))
        form_start = getattr(a, 'form_start', None)
        speed_by_form = getattr(a, 'speed_by_form', None)
        if form_start and isinstance(speed_by_form, dict) and form_start in speed_by_form:
            speed = float(speed_by_form[form_start])

        actor = Actor(
            getattr(a, 'name'),
            speed,
            faction=getattr(a, 'faction', None),
            skill_sequence=list(getattr(a, 'skill_sequence')) if getattr(a, 'skill_sequence', None) is not None else None,
        )
        actor.blessings = _blessings_for(actor.name)
        # Hydrate A1 hits for counterattack modeling.
        actor._a1_hits = _a1_hits_for(actor.name)  # type: ignore[attr-defined]
        actors.append(actor)

    boss = getattr(spec, 'boss')
    boss_speed = float(getattr(boss, 'speed'))
    boss_form_start = getattr(boss, 'form_start', None)
    boss_speed_by_form = getattr(boss, 'speed_by_form', None)
    if boss_form_start and isinstance(boss_speed_by_form, dict) and boss_form_start in boss_speed_by_form:
        boss_speed = float(boss_speed_by_form[boss_form_start])

    boss_shield_max = getattr(boss, 'shield_max', None)
    boss_shield_start = int(boss_shield_max) if boss_shield_max is not None else 0

    boss_actor = Actor(
        getattr(boss, 'name'),
        boss_speed,
        is_boss=True,
        shield=boss_shield_start,
        shield_max=boss_shield_max,
        faction=getattr(boss, 'faction', None),
        skill_sequence=list(getattr(boss, 'skill_sequence')) if getattr(boss, 'skill_sequence', None) is not None else None,
    )
    boss_actor.blessings = _blessings_for(boss_actor.name)
    boss_actor._a1_hits = _a1_hits_for(boss_actor.name)  # type: ignore[attr-defined]
    actors.append(boss_actor)

    return actors


class MasteryProcRequester:
    """Inspectable, callable mastery proc requester.

    - Callable contract (engine): requester({"turn_counter": int}) -> list[dict]
    - Introspection: steps(), mastery_procs_for_step(step)
    """

    def __init__(self, schedule: dict[int, list[dict[str, Any]]]):
        self._schedule: dict[int, list[dict[str, Any]]] = schedule
        # Marker used by step_tick: when present/true, the engine is allowed to
        # emit requested procs at TURN_START as a user-driven CLI seam.
        # Plain callables (unit tests) will not have this attribute, keeping
        # emission gated on modeled triggers (e.g., buff expiration).
        self.emit_on_turn_start = True

    def __call__(self, ctx: dict[str, Any]) -> list[dict[str, Any]]:
        turn_counter = ctx.get("turn_counter")
        try:
            step = int(turn_counter)
        except Exception:
            return []
        return list(self._schedule.get(step, []))

    def steps(self) -> list[int]:
        return sorted(self._schedule.keys())

    def mastery_procs_for_step(self, step: int) -> list[dict[str, Any]]:
        try:
            s = int(step)
        except Exception:
            return []
        return list(self._schedule.get(s, []))


def build_mastery_proc_requester_from_battle_path(battle_path: Path) -> MasteryProcRequester | None:
    """Build a mastery proc requester from a battle spec JSON file.

    ADR-001 semantics (authoritative):
      - User-facing `step` is a 1-based index of a specific ENTITY'S skill activation sequence.
      - Scheduling is entity-scoped (champion-scoped), not global.
      - Requests are consulted by (entity_name, skill_sequence_step).

    Canonical (demo) location:
      entity["turn_overrides"]["proc_request"]["on_step"][step]["mastery_procs"]

    Where `entity` may be the boss or any champion.

    Return contract:
      - If the JSON is readable and is an object, ALWAYS return an inspectable requester.
      - If no proc requests are declared, the requester returns [] for every ctx.
      - If the JSON cannot be read/parsed or is not an object, return None.
    """
    try:
        raw = json.loads(battle_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    if not isinstance(raw, dict):
        return None

    # schedule_by_entity[entity_name][skill_sequence_step] -> list[proc_dict]
    schedule_by_entity: dict[str, dict[int, list[dict[str, Any]]]] = {}

    def _extract_on_step(container: object) -> tuple[str, dict[str, Any]] | None:
        """Return (entity_name, on_step) if present, else None."""
        if not isinstance(container, dict):
            return None
        name = container.get("name")
        if not isinstance(name, str) or not name.strip():
            return None
        turn_overrides = container.get("turn_overrides")
        if not isinstance(turn_overrides, dict):
            return None
        proc_request = turn_overrides.get("proc_request")
        if not isinstance(proc_request, dict):
            return None
        on_step = proc_request.get("on_step")
        if not isinstance(on_step, dict):
            return None
        return (name, on_step)

    def _merge_on_step(entity_name: str, on_step: dict[str, Any]) -> None:
        for k, v in on_step.items():
            if not isinstance(v, dict):
                continue
            procs = v.get("mastery_procs", [])
            if not isinstance(procs, list):
                continue
            try:
                step_i = int(k)
            except Exception:
                continue
            if step_i <= 0:
                continue

            cleaned: list[dict[str, Any]] = [p for p in procs if isinstance(p, dict)]
            if not cleaned:
                continue
            schedule_by_entity.setdefault(entity_name, {}).setdefault(step_i, []).extend(cleaned)

    # NOTE: ADR-001 removes the meaning of root-level scheduling.
    # We intentionally do NOT merge root-level `turn_overrides` into the schedule.

    boss = raw.get("boss")
    boss_pair = _extract_on_step(boss)
    if boss_pair is not None:
        entity_name, on_step = boss_pair
        _merge_on_step(entity_name, on_step)

    champions = raw.get("champions")
    if isinstance(champions, list):
        for ch in champions:
            pair = _extract_on_step(ch)
            if pair is None:
                continue
            entity_name, on_step = pair
            _merge_on_step(entity_name, on_step)

    class _ChampionScopedRequester(MasteryProcRequester):
        """Requester that supports champion-scoped calls and legacy introspection.

        Call contract (preferred):
          requester({"champion_name": str, "skill_sequence_step": int}) -> list[dict]

        Back-compat call contract (discouraged):
          requester({"turn_counter": int}) -> list[dict]
          This returns the UNION of all entities' requests for that numeric step.
        """

        def __init__(self, schedule: dict[str, dict[int, list[dict[str, Any]]]]):
            # Keep base type/duck compatibility; we don't use the base schedule.
            super().__init__({})
            self._schedule_by_entity = schedule
            self.emit_on_turn_start = True

        def __call__(self, ctx: dict[str, Any]) -> list[dict[str, Any]]:
            if not isinstance(ctx, dict):
                return []

            champ = ctx.get("champion_name")
            step = ctx.get("skill_sequence_step")
            if isinstance(champ, str):
                try:
                    step_i = int(step)
                except Exception:
                    step_i = None
                if step_i is not None and step_i > 0:
                    return list(self._schedule_by_entity.get(champ, {}).get(step_i, []))

            # Legacy union-by-step support (kept for older tests/tools)
            turn_counter = ctx.get("turn_counter")
            try:
                step_i = int(turn_counter)
            except Exception:
                return []
            if step_i <= 0:
                return []
            out: list[dict[str, Any]] = []
            for _entity, per_step in self._schedule_by_entity.items():
                out.extend(list(per_step.get(step_i, [])))
            return out

        def steps(self) -> list[int]:
            # Union of steps across all entities (legacy introspection)
            s: set[int] = set()
            for per_step in self._schedule_by_entity.values():
                s.update(int(k) for k in per_step.keys())
            return sorted(s)

        def mastery_procs_for_step(self, step: int) -> list[dict[str, Any]]:
            # Union across all entities (legacy introspection)
            try:
                step_i = int(step)
            except Exception:
                return []
            if step_i <= 0:
                return []
            out: list[dict[str, Any]] = []
            for per_step in self._schedule_by_entity.values():
                out.extend(list(per_step.get(step_i, [])))
            return out

        def mastery_procs_for_champion_step(self, champion_name: str, step: int) -> list[dict[str, Any]]:
            # Optional richer introspection (not required by engine).
            try:
                step_i = int(step)
            except Exception:
                return []
            if not isinstance(champion_name, str) or not champion_name.strip() or step_i <= 0:
                return []
            return list(self._schedule_by_entity.get(champion_name, {}).get(step_i, []))

    return _ChampionScopedRequester(schedule_by_entity)


class DamageReceivedProvider:
    """Inspectable, callable damage-received provider.

    Call contract (engine):
      provider({"champion_name": str, "skill_sequence_step": int}) -> list[str] | None

    Semantics:
      - Returns None when no override is declared for the requested (entity, step).
      - Returns a list (possibly empty) when an override is declared.

    Data source (battle spec):
      entity["turn_overrides"]["damage_received"]["on_step"]

    Supported shapes for `on_step`:
      - dict: {"3": {"damaged": ["A", "B"]}, ...}
      - list: [{"3": {"damaged": [...] }}, ...]
    """

    def __init__(self, schedule_by_entity: dict[str, dict[int, list[str]]]):
        self._schedule_by_entity = schedule_by_entity

    def __call__(self, ctx: dict[str, Any]) -> list[str] | None:
        if not isinstance(ctx, dict):
            return None
        champ = ctx.get("champion_name")
        step = ctx.get("skill_sequence_step")
        if not isinstance(champ, str) or not champ.strip():
            return None
        try:
            step_i = int(step)
        except Exception:
            return None
        if step_i <= 0:
            return None
        per_step = self._schedule_by_entity.get(champ, {})
        if step_i not in per_step:
            return None
        return list(per_step.get(step_i, []))

    def steps(self, *, champion_name: str | None = None) -> list[int]:
        if isinstance(champion_name, str) and champion_name.strip():
            return sorted(self._schedule_by_entity.get(champion_name, {}).keys())
        s: set[int] = set()
        for per_step in self._schedule_by_entity.values():
            s.update(int(k) for k in per_step.keys())
        return sorted(s)


def build_damage_received_provider_from_battle_path(battle_path: Path) -> DamageReceivedProvider | None:
    """Build a damage-received override provider from a battle spec JSON file.

    Canonical (boss-turn) use-case:
      - On a specific boss skill-sequence step, the user may declare which champions
        actually received damage.
      - This enables deterministic gating for reactive mechanics that require
        damage to be received (e.g., Faultless Defense reflect).

    Return contract:
      - If the JSON cannot be read/parsed or is not an object, return None.
      - If the JSON is valid but declares no overrides, return a provider that
        always returns None.
    """
    try:
        raw = json.loads(battle_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    if not isinstance(raw, dict):
        return None

    schedule_by_entity: dict[str, dict[int, list[str]]] = {}

    def _extract_on_step(container: object) -> tuple[str, object] | None:
        if not isinstance(container, dict):
            return None
        name = container.get("name")
        if not isinstance(name, str) or not name.strip():
            return None
        turn_overrides = container.get("turn_overrides")
        if not isinstance(turn_overrides, dict):
            return None
        dr = turn_overrides.get("damage_received")
        if not isinstance(dr, dict):
            return None
        on_step = dr.get("on_step")
        if on_step is None:
            return None
        return (name, on_step)

    def _merge_step_obj(entity_name: str, step_key: object, payload: object) -> None:
        try:
            step_i = int(step_key)
        except Exception:
            return
        if step_i <= 0 or not isinstance(payload, dict):
            return
        damaged = payload.get("damaged")
        if not isinstance(damaged, list):
            return
        cleaned = [str(x) for x in damaged if isinstance(x, str) and x.strip()]
        schedule_by_entity.setdefault(entity_name, {})[step_i] = cleaned

    def _merge_on_step(entity_name: str, on_step: object) -> None:
        if isinstance(on_step, dict):
            for k, v in on_step.items():
                _merge_step_obj(entity_name, k, v)
            return
        if isinstance(on_step, list):
            for item in on_step:
                if not isinstance(item, dict):
                    continue
                for k, v in item.items():
                    _merge_step_obj(entity_name, k, v)
            return

    boss = raw.get("boss")
    boss_pair = _extract_on_step(boss)
    if boss_pair is not None:
        entity_name, on_step = boss_pair
        _merge_on_step(entity_name, on_step)

    champions = raw.get("champions")
    if isinstance(champions, list):
        for ch in champions:
            pair = _extract_on_step(ch)
            if pair is None:
                continue
            entity_name, on_step = pair
            _merge_on_step(entity_name, on_step)

    return DamageReceivedProvider(schedule_by_entity)


class BossTurnOverrideProvider:
    """Inspectable, callable boss turn-override provider.

    Current supported override(s):
      - damage_received: which champions actually received damage from the boss
        on a given boss skill-sequence step (used to gate reflect-style effects
        such as Faultless Defense).

    Call contract:
      provider({"boss_name": str, "skill_sequence_step": int}) -> dict | None

    Return value:
      - None when no override exists for the requested boss+step.
      - Otherwise a dict payload, currently: {"damaged": [<names>]}
    """

    def __init__(self, schedule: dict[str, dict[int, dict[str, Any]]]):
        self._schedule_by_boss = schedule

    def __call__(self, ctx: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(ctx, dict):
            return None
        boss = ctx.get("boss_name")
        step = ctx.get("skill_sequence_step")
        if not isinstance(boss, str) or not boss.strip():
            return None
        try:
            step_i = int(step)
        except Exception:
            return None
        if step_i <= 0:
            return None
        payload = self._schedule_by_boss.get(boss, {}).get(step_i)
        if not isinstance(payload, dict):
            return None
        return dict(payload)

    def steps_for_boss(self, boss_name: str) -> list[int]:
        if not isinstance(boss_name, str) or not boss_name.strip():
            return []
        return sorted(int(k) for k in (self._schedule_by_boss.get(boss_name, {}) or {}).keys())


def build_boss_turn_override_provider_from_battle_path(battle_path: Path) -> BossTurnOverrideProvider | None:
    """Build boss turn overrides from a battle spec JSON file.

    Canonical (demo) location:
      raw["boss"]["turn_overrides"]["damage_received"]["on_step"]

    Where on_step may be either:
      - a dict: {"3": {"damaged": [..]}}
      - or a list of dict items: [{"3": {"damaged": [..]}}, ...]

    Return contract mirrors mastery proc builder:
      - If the JSON is readable and is an object, ALWAYS return an inspectable provider.
      - If no overrides are declared, the provider returns None for every ctx.
      - If the JSON cannot be read/parsed or is not an object, return None.
    """
    try:
        raw = json.loads(battle_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    if not isinstance(raw, dict):
        return None

    schedule_by_boss: dict[str, dict[int, dict[str, Any]]] = {}

    boss = raw.get("boss")
    if not isinstance(boss, dict):
        return BossTurnOverrideProvider(schedule_by_boss)

    boss_name = boss.get("name")
    if not isinstance(boss_name, str) or not boss_name.strip():
        return BossTurnOverrideProvider(schedule_by_boss)

    turn_overrides = boss.get("turn_overrides")
    if not isinstance(turn_overrides, dict):
        return BossTurnOverrideProvider(schedule_by_boss)

    damage_received = turn_overrides.get("damage_received")
    if not isinstance(damage_received, dict):
        return BossTurnOverrideProvider(schedule_by_boss)

    on_step = damage_received.get("on_step")
    merged: dict[str, Any] = {}
    if isinstance(on_step, dict):
        merged = dict(on_step)
    elif isinstance(on_step, list):
        for item in on_step:
            if not isinstance(item, dict):
                continue
            for k, v in item.items():
                merged[str(k)] = v

    for k, v in merged.items():
        if not isinstance(v, dict):
            continue
        damaged = v.get("damaged")
        if not isinstance(damaged, list):
            continue
        cleaned = [n for n in damaged if isinstance(n, str) and n.strip()]
        try:
            step_i = int(k)
        except Exception:
            continue
        if step_i <= 0:
            continue
        schedule_by_boss.setdefault(boss_name, {})[step_i] = {"damaged": cleaned}

    return BossTurnOverrideProvider(schedule_by_boss)


class EffectPlacementProvider:
    """Inspectable, callable provider for effect placements driven by battle spec turn_overrides.

    Current supported schema:
      entity["turn_overrides"]["skill_sequence_steps"][step]["allied_attack_outcomes"]["effects_placed"]

    Call contract:
      provider({"actor_name": str, "skill_sequence_step": int}) -> list[dict]

    Returns an empty list when no placements are scheduled for the requested key.
    """

    def __init__(self, schedule: dict[str, dict[int, list[dict[str, object]]]]):
        self._schedule_by_entity = schedule

    def __call__(self, ctx: dict[str, object]) -> list[dict[str, object]]:
        if not isinstance(ctx, dict):
            return []
        actor = ctx.get('actor_name')
        step = ctx.get('skill_sequence_step')
        if not isinstance(actor, str) or not actor.strip():
            return []
        try:
            step_i = int(step)
        except Exception:
            return []
        if step_i <= 0:
            return []
        payload = self._schedule_by_entity.get(actor, {}).get(step_i, [])
        if not isinstance(payload, list):
            return []
        return [p for p in payload if isinstance(p, dict)]

    def steps_for_actor(self, actor_name: str) -> list[int]:
        if not isinstance(actor_name, str) or not actor_name.strip():
            return []
        return sorted(int(k) for k in (self._schedule_by_entity.get(actor_name, {}) or {}).keys())


def build_effect_placement_provider_from_battle_path(battle_path: Path) -> EffectPlacementProvider | None:
    """Build an effect placement provider from a battle spec JSON file.

    Canonical (demo) location:
      raw["champions"][*]["turn_overrides"]["skill_sequence_steps"][step]["allied_attack_outcomes"]["effects_placed"]

    Return contract mirrors other builders:
      - If the JSON is readable and is an object, ALWAYS return an inspectable provider.
      - If no placements are declared, the provider returns [] for every ctx.
      - If the JSON cannot be read/parsed or is not an object, return None.
    """
    try:
        raw = json.loads(battle_path.read_text(encoding='utf-8'))
    except Exception:
        return None

    if not isinstance(raw, dict):
        return None

    schedule_by_entity: dict[str, dict[int, list[dict[str, object]]]] = {}

    def _merge_entity(container: object) -> None:
        if not isinstance(container, dict):
            return
        name = container.get('name')
        if not isinstance(name, str) or not name.strip():
            return
        turn_overrides = container.get('turn_overrides')
        if not isinstance(turn_overrides, dict):
            return
        steps = turn_overrides.get('skill_sequence_steps')
        if not isinstance(steps, dict):
            return
        for step_k, step_v in steps.items():
            try:
                step_i = int(step_k)
            except Exception:
                continue
            if step_i <= 0 or not isinstance(step_v, dict):
                continue
            outcomes = step_v.get('allied_attack_outcomes')
            if not isinstance(outcomes, dict):
                continue
            placed = outcomes.get('effects_placed')
            if not isinstance(placed, list) or not placed:
                continue
            cleaned = [p for p in placed if isinstance(p, dict)]
            if not cleaned:
                continue
            schedule_by_entity.setdefault(name, {}).setdefault(step_i, []).extend(cleaned)

    boss = raw.get('boss')
    _merge_entity(boss)

    champs = raw.get('champions')
    if isinstance(champs, list):
        for ch in champs:
            _merge_entity(ch)

    return EffectPlacementProvider(schedule_by_entity)


def run_ticks(
        *,
        actors: list[Actor],
        event_sink: EventSink,
        ticks: int,
        hit_provider: Callable[[str], dict[str, int]] | None = None,
        battle_path_for_mastery_procs: Path | None = None,
        stop_after_boss_turns: int | None = None,
        boss_actor: str = "Boss",
) -> None:
    """Engine-owned ticking loop.

    This is an architectural seam: callers provide data (battle spec path), and
    the engine builds/owns the mastery proc requester and any boss turn overrides.
    Callers should not pass requester/override closures into the engine.
    """

    mastery_proc_requester = None
    boss_turn_override_provider = None
    effect_placement_provider = None
    if battle_path_for_mastery_procs is not None:
        mastery_proc_requester = build_mastery_proc_requester_from_battle_path(battle_path_for_mastery_procs)
        boss_turn_override_provider = build_boss_turn_override_provider_from_battle_path(battle_path_for_mastery_procs)
        effect_placement_provider = build_effect_placement_provider_from_battle_path(battle_path_for_mastery_procs)

        # Engine-owned skill consumption + base hit provider.
        # When callers do not inject a hit_provider, we derive one from the
        # battle spec and the engine-owned actor list.
        if hit_provider is None:
            hit_provider = build_hit_provider_from_battle_path(
                battle_path=battle_path_for_mastery_procs,
                actors=actors,
                event_sink=event_sink,
            )

    def _is_boss_turn_end_event(evt: object) -> bool:
        actor = getattr(evt, "actor", None)
        etype = getattr(evt, "type", None)
        if actor != boss_actor:
            return False
        if hasattr(etype, "value"):
            return etype.value == "TURN_END"
        return str(etype) == "TURN_END"

    boss_turns_seen = 0

    def _resolver_with_boss_overrides(
            *,
            acting_actor: Actor,
            actors: list[Actor],
            base_hits: dict[str, int],
            turn_counter: int,
            tick: int,
    ) -> dict[str, int]:
        """Wrapper around the default hit contribution resolver.

        When a boss `damage_received` override exists for the current boss skill-sequence step,
        Faultless Defense reflect hits are gated to only those targets listed as damaged.
        """
        extra = _default_hit_contribution_resolver(
            acting_actor=acting_actor,
            actors=actors,
            base_hits=base_hits,
            turn_counter=turn_counter,
            tick=tick,
        )

        if boss_turn_override_provider is None:
            return extra
        if not bool(getattr(acting_actor, "is_boss", False)):
            return extra

        try:
            boss_step = int(getattr(acting_actor, "skill_sequence_cursor", 0))
        except Exception:
            boss_step = 0
        if boss_step <= 0:
            return extra

        payload = boss_turn_override_provider(
            {
                "boss_name": str(getattr(acting_actor, "name", "")),
                "skill_sequence_step": boss_step,
            }
        )
        if not isinstance(payload, dict):
            return extra
        damaged = payload.get("damaged")
        if not isinstance(damaged, list):
            return extra
        damaged_set = {n for n in damaged if isinstance(n, str) and n.strip()}

        # Recompute reflect hits with damage gating, then replace REFLECT bucket.
        allies = [a for a in actors if not bool(getattr(a, "is_boss", False))]
        reflect_hits = 0
        for holder in allies:
            fd_cfg = holder.blessings.get("faultless_defense")
            if not isinstance(fd_cfg, dict):
                continue
            modeling = fd_cfg.get("modeling")
            if not isinstance(modeling, dict):
                continue
            emits = modeling.get("emits_hit_event")
            if not isinstance(emits, dict):
                continue
            try:
                per_target = int(emits.get("count", 1))
            except Exception:
                per_target = 1
            if per_target <= 0:
                continue

            for target in allies:
                if target.name not in damaged_set:
                    continue
                for fx in getattr(target, "active_effects", []) or []:
                    if getattr(fx, "effect_kind", None) != "BUFF":
                        continue
                    if getattr(fx, "effect_id", None) != "increase_def":
                        continue
                    if getattr(fx, "placed_by", None) != holder.name:
                        continue
                    reflect_hits += per_target
                    break

        extra = dict(extra)
        if reflect_hits > 0:
            extra["REFLECT"] = int(reflect_hits)
        else:
            extra.pop("REFLECT", None)
        return extra

    hit_contribution_resolver = _resolver_with_boss_overrides if boss_turn_override_provider is not None else None

    for _ in range(int(ticks)):
        before_len = len(getattr(event_sink, "events", []) or [])
        step_tick(
            actors,
            event_sink=event_sink,
            hit_provider=hit_provider,
            hit_contribution_resolver=hit_contribution_resolver,
            mastery_proc_requester=mastery_proc_requester,
            effect_placement_provider=effect_placement_provider,
        )

        if stop_after_boss_turns is not None:
            new_events = (getattr(event_sink, "events", []) or [])[before_len:]
            for evt in new_events:
                if _is_boss_turn_end_event(evt):
                    boss_turns_seen += 1
                    if boss_turns_seen >= int(stop_after_boss_turns):
                        return


def _boss_shield_snapshot(actors: list[Actor]) -> dict[str, object] | None:
    """Observer-only: derive current boss shield state from the actor list."""
    boss = next((a for a in actors if bool(getattr(a, "is_boss", False))), None)
    if boss is None:
        boss = next((a for a in actors if a.name == "Boss"), None)
    if boss is None:
        return None

    value = int(getattr(boss, "shield", 0))
    status = "UP" if value > 0 else "BROKEN"
    return {"value": value, "status": status}


def _decrement_active_effect_durations_turn_end(actor: Actor, *, turn_counter: int) -> dict[str, int]:
    """Slice 3: Decrement BUFF durations at the affected actor's TURN_END.

    Duration semantics (updated):
      - BUFF duration must NOT decrement on the same turn it was applied.
      - First eligible decrement is the next matching boundary after placement.

    Returns a mapping of instance_id -> duration BEFORE decrement so callers can
    emit useful expiration payloads in Slice 4.

    This updates `actor.active_effects` in-place by replacing frozen EffectInstances.
    Expiration/removal is intentionally NOT performed here.
    """
    current = list(getattr(actor, "active_effects", []) or [])
    if not current:
        return {}

    duration_before: dict[str, int] = {}
    updated: list[EffectInstance] = []

    for fx in current:
        iid = str(getattr(fx, "instance_id"))
        d0 = int(getattr(fx, "duration", 0))
        duration_before[iid] = d0

        if getattr(fx, "effect_kind", None) == "BUFF":
            applied_turn = int(getattr(fx, "applied_turn", 0))

            # Skip decrement on placement turn.
            if applied_turn == int(turn_counter):
                new_d = d0
            else:
                new_d = max(0, d0 - 1) if d0 > 0 else 0

            updated.append(
                EffectInstance(
                    instance_id=iid,
                    effect_id=str(getattr(fx, "effect_id")),
                    effect_kind=str(getattr(fx, "effect_kind")),
                    placed_by=str(getattr(fx, "placed_by")),
                    duration=int(new_d),
                    applied_turn=applied_turn,
                )
            )
        else:
            updated.append(fx)

    actor.active_effects = updated
    return duration_before


def _emit_effect_duration_changed_events(
        *,
        event_sink: EventSink,
        owner: Actor,
        duration_before: dict[str, int],
        turn_counter: int,
        boundary: str,
        reason: str,
) -> None:
    """Emit EFFECT_DURATION_CHANGED for any EffectInstance on `owner` whose duration changed.

    Designed to keep duration logic observable in CLI/event logs without tests needing
    to infer duration from indirect behavior.
    """
    current = list(getattr(owner, "active_effects", []) or [])
    if not current:
        return

    for fx in current:
        if getattr(fx, "effect_kind", None) != "BUFF":
            continue
        iid = str(getattr(fx, "instance_id"))
        d0 = int(duration_before.get(iid, int(getattr(fx, "duration", 0))))
        d1 = int(getattr(fx, "duration", 0))
        if d0 == d1:
            continue

        event_sink.emit(
            EventType.EFFECT_DURATION_CHANGED,
            actor=owner.name,
            instance_id=iid,
            effect_id=str(getattr(fx, "effect_id", "")),
            effect_kind=str(getattr(fx, "effect_kind", "")),
            owner=owner.name,
            placed_by=str(getattr(fx, "placed_by", "")),
            duration_before=d0,
            duration_after=d1,
            delta=d1 - d0,
            reason=reason,
            boundary=boundary,
            turn_counter=int(turn_counter),
        )


def _expire_active_effects_turn_end(
        *,
        owner: Actor,
        owner_index: int,
        actors: list[Actor],
        event_sink: EventSink,
        duration_before: dict[str, int],
        turn_counter: int,
        mastery_proc_requester: callable | None = None,
) -> None:
    """Slice 4/5: Expire BUFF instances whose duration reached 0 at TURN_END.

    Engine-owned expiration occurs BEFORE emitting the TURN_END bookmark.

    Slice 5 bridge:
      If a BUFF placed by Mikage expires AND a deterministic proc request exists
      for this step (turn_counter), emit MASTERY_PROC with the requested payload.
    """
    current = list(getattr(owner, "active_effects", []) or [])
    if not current:
        return

    remaining: list[EffectInstance] = []
    expired: list[EffectInstance] = []

    for fx in current:
        iid = str(getattr(fx, "instance_id"))
        d0 = int(duration_before.get(iid, int(getattr(fx, "duration", 0))))
        d1 = int(getattr(fx, "duration", 0))

        # Expire only if this instance is using engine-owned duration tracking.
        if getattr(fx, "effect_kind", None) == "BUFF" and d0 > 0 and d1 <= 0:
            expired.append(fx)
        else:
            remaining.append(fx)

    if not expired:
        return

    owner.active_effects = remaining

    for fx in expired:
        iid = str(getattr(fx, "instance_id"))
        event_sink.emit(
            EventType.EFFECT_EXPIRED,
            actor=owner.name,
            actor_index=int(owner_index),
            instance_id=iid,
            effect_id=getattr(fx, "effect_id", None),
            effect_kind=getattr(fx, "effect_kind", None),
            owner=owner.name,
            placed_by=getattr(fx, "placed_by", None),
            # Use duration BEFORE decrement for observability and consistency with injected expiration.
            duration=int(duration_before.get(iid, int(getattr(fx, "duration", 0)))),
            reason="duration_reached_zero",
            phase=str(EventType.TURN_END),
        )

        # Slice A: record qualifying expirations for deterministic validation.
        _record_qualifying_expiration(event_sink=event_sink, actors=actors, expired_effect=fx)


def _resolve_external_expirations_for_phase(
        *,
        event_sink: "EventSink",
        actors: list["Actor"],
        phase: "EventType",
        acting_actor: "Actor",
        acting_actor_index: int,
        turn_counter: int,
        expiration_resolver: ExpirationResolver,
        mastery_proc_requester: callable | None = None,
) -> None:
    injected = expiration_resolver(
        {
            "phase": str(phase),
            "acting_actor": acting_actor.name,
            "acting_actor_index": int(acting_actor_index),
            "turn_counter": int(turn_counter),
            "tick": int(event_sink.current_tick),
        }
    ) or []

    for item in injected:
        if not isinstance(item, dict):
            raise ValueError("Injected expiration must be a dict payload.")

        # --- New schema-backed path ---
        if item.get("type") == "expire_effect" or "instance_id" in item or "reason" in item:
            _validate_expire_effect_request(item)
            instance_id = item["instance_id"]

            owner, fx = _expire_effect_instance_by_id(actors=actors, instance_id=instance_id)
            owner_index = next(i for i, a in enumerate(actors) if a is owner)

            # Emit EFFECT_EXPIRED in a way that won't break existing consumers:
            # keep existing fields you already emit, and ADD the new ones.
            event_sink.emit(
                EventType.EFFECT_EXPIRED,
                actor=owner.name,
                actor_index=owner_index,
                # new structured fields:
                instance_id=instance_id,
                effect_id=getattr(fx, "effect_id", None),
                effect_kind=getattr(fx, "effect_kind", None),
                owner=owner.name,
                placed_by=getattr(fx, "placed_by", None),
                duration=getattr(fx, "duration", None),
                reason=item["reason"],
                # preserve debug fields you already use:
                phase=str(phase),
                injected_turn_counter=int(turn_counter),
                acting_actor=acting_actor.name,
            )

            # Slice A: record qualifying expirations for deterministic validation.
            _record_qualifying_expiration(event_sink=event_sink, actors=actors, expired_effect=fx)

        else:
            raise ValueError(
                "Injected expiration item must use schema: "
                "{'type':'expire_effect','instance_id':'...','reason':'injected'}"
            )


def _validate_expire_effect_request(item: dict) -> None:
    """
    Schema:
      {"type":"expire_effect","instance_id":"...","reason":"injected"}
    """
    if item.get("type") != "expire_effect":
        raise ValueError("expire_effect request requires type='expire_effect'.")

    instance_id = item.get("instance_id")
    if not isinstance(instance_id, str) or not instance_id.strip():
        raise ValueError("expire_effect request requires non-empty 'instance_id' (string).")

    reason = item.get("reason")
    if reason != "injected":
        raise ValueError("expire_effect request requires reason='injected'.")

    extras = set(item.keys()) - {"type", "instance_id", "reason"}
    if extras:
        raise ValueError(f"expire_effect request has unexpected fields: {sorted(extras)}")


def _expire_effect_instance_by_id(*, actors: list["Actor"], instance_id: str):
    """
    Remove a buff/debuff instance from whichever actor currently owns it.

    Returns: (owner_actor, expired_effect_instance)
    """
    for a in actors:
        current = getattr(a, "active_effects", None)
        if not current:
            continue
        for i, fx in enumerate(list(current)):
            if getattr(fx, "instance_id", None) == instance_id:
                removed = current.pop(i)
                return a, removed
    raise ValueError(f"Effect instance_id not found: {instance_id}")


def _record_qualifying_expiration(
        *,
        event_sink: "EventSink",
        actors: list[Actor],
        expired_effect: object,
) -> None:
    """Slice A: Record qualifying expirations for later guarded resolution.

    We do NOT emit any events here; we only record counts on the event sink.

    Qualifying rule (minimal / initial):
      - expired_effect.effect_kind == "BUFF"
      - expired_effect.placed_by matches an existing Actor.name
      - step is holder's ADR-001 skill_sequence_step (1-based), derived from
        Actor.skill_sequence_cursor (0-based consumed count).

    Stored at:
      event_sink._qualifying_expiration_counts[(holder_name, skill_sequence_step)] = int
    """
    effect_kind = getattr(expired_effect, "effect_kind", None)
    if effect_kind != "BUFF":
        return

    placed_by = getattr(expired_effect, "placed_by", None)
    if not isinstance(placed_by, str) or not placed_by.strip():
        return

    holder = next((a for a in actors if a.name == placed_by), None)
    if holder is None:
        # Unknown placer; ignore for determinism.
        return

    # ADR-001: skill_sequence_step is 1-based consumed-so-far.
    step = int(getattr(holder, "skill_sequence_cursor", 0))
    if step <= 0:
        return

    counts = getattr(event_sink, "_qualifying_expiration_counts", None)
    if not isinstance(counts, dict):
        counts = {}
        setattr(event_sink, "_qualifying_expiration_counts", counts)

    key = (holder.name, int(step))
    counts[key] = int(counts.get(key, 0)) + 1


def _resolve_guarded_mastery_procs_for_qualifying_expirations(
        *,
        event_sink: "EventSink",
        actors: list[Actor],
        turn_counter: int,
        mastery_proc_requester: callable,
) -> None:
    """Slice B: Guarded deterministic resolution for expiration-triggered mastery procs.

    Slice A records qualifying expiration counts on the event sink:
      event_sink._qualifying_expiration_counts[(holder_name, skill_sequence_step)] = Q

    Slice B enforces that a user-declared deterministic proc request for (holder, step)
    MUST NOT exceed Q.

    Guard behavior (Option B):
      - If a request exists for (holder, step) and requested_count > Q, emit
        MASTERY_PROC_REJECTED and do NOT apply proc effects.
      - If requested_count <= Q, emit MASTERY_PROC and apply proc effects.
      - If no request exists for (holder, step), do nothing (no rejection).

    Current scope (minimal): Mikage rapid_response only.
    """
    counts = getattr(event_sink, "_qualifying_expiration_counts", None)
    if not isinstance(counts, dict):
        counts = {}

    resolved = getattr(event_sink, "_mastery_proc_keys_resolved", None)
    if not isinstance(resolved, set):
        resolved = set()
        setattr(event_sink, "_mastery_proc_keys_resolved", resolved)

    # Iterate deterministically for stable testing.
    for (holder_name, skill_sequence_step), q in sorted(counts.items(), key=lambda kv: (str(kv[0][0]), int(kv[0][1]))):
        if holder_name != "Mikage":
            continue
        try:
            step_i = int(skill_sequence_step)
            q_i = int(q)
        except Exception:
            continue
        if step_i <= 0 or q_i <= 0:
            continue

        key = (holder_name, step_i)
        if key in resolved:
            continue

        requested = mastery_proc_requester(
            {
                "champion_name": holder_name,
                "skill_sequence_step": int(step_i),
                "turn_counter": int(turn_counter),  # legacy observability only
            }
        ) or []
        if not isinstance(requested, list):
            raise ValueError("mastery_proc_requester must return a list of proc dicts")

        requested_total = 0
        has_request = False
        for item in requested:
            if not isinstance(item, dict):
                raise ValueError("mastery proc request items must be dicts")
            if item.get("holder") != holder_name:
                continue
            if item.get("mastery") != "rapid_response":
                continue
            count = item.get("count")
            if not isinstance(count, int) or count <= 0:
                raise ValueError("mastery proc request requires positive int 'count'")
            has_request = True
            requested_total += int(count)

        if not has_request:
            # No declared request for this (holder, step): remain silent.
            continue

        if int(requested_total) > int(q_i):
            event_sink.emit(
                EventType.MASTERY_PROC_REJECTED,
                actor=holder_name,
                holder=holder_name,
                mastery="rapid_response",
                requested_count=int(requested_total),
                qualifying_count=int(q_i),
                # Slice D / D5: prefer explicit naming while retaining legacy field.
                qualifying_expiration_count=int(q_i),
                resolution_phase=str(EventType.TURN_END),
                resolution_step=int(step_i),
                skill_sequence_step=int(step_i),
                turn_counter=int(turn_counter),
                reason="requested_count_exceeds_qualifying",
            )
            resolved.add(key)
            continue

        # Match: emit proc and apply effects.
        event_sink.emit(
            EventType.MASTERY_PROC,
            actor=holder_name,
            holder=holder_name,
            mastery="rapid_response",
            count=int(requested_total),
            # Slice D / D2: success-path causal attribution (observability only).
            qualifying_expiration_count=int(q_i),
            resolution_phase=str(EventType.TURN_END),
            resolution_step=int(step_i),
            skill_sequence_step=int(step_i),
            turn_counter=int(turn_counter),  # legacy observability only
        )

        _apply_mastery_proc_effects(
            actors=actors,
            holder=holder_name,
            mastery="rapid_response",
            count=int(requested_total),
        )

        resolved.add(key)

    # Slice D / D4: If a request exists for a (holder, step) but Q==0, emit an explicit rejection.
    # This prevents silent drops when the user requests an expiration-triggered proc but the
    # qualifying expirations never occur.
    for holder_name in ("Mikage",):
        holder_obj = next((a for a in actors if a.name == holder_name), None)
        if holder_obj is None:
            continue

        # ADR-001: expiration-triggered lookup uses consumed-so-far step (1-based).
        step_i = int(getattr(holder_obj, "skill_sequence_cursor", 0))
        if step_i <= 0:
            continue

        key = (holder_name, step_i)
        if key in resolved:
            continue

        q_i = int(counts.get(key, 0))
        if q_i != 0:
            continue

        requested = mastery_proc_requester(
            {
                "champion_name": holder_name,
                "skill_sequence_step": int(step_i),
                "turn_counter": int(turn_counter),  # legacy observability only
            }
        ) or []
        if not isinstance(requested, list):
            raise ValueError("mastery_proc_requester must return a list of proc dicts")

        requested_total = 0
        has_request = False
        for item in requested:
            if not isinstance(item, dict):
                raise ValueError("mastery proc request items must be dicts")
            if item.get("holder") != holder_name:
                continue
            if item.get("mastery") != "rapid_response":
                continue
            count = item.get("count")
            if not isinstance(count, int) or count <= 0:
                raise ValueError("mastery proc request requires positive int 'count'")
            has_request = True
            requested_total += int(count)

        if not has_request:
            continue

        event_sink.emit(
            EventType.MASTERY_PROC_REJECTED,
            actor=holder_name,
            holder=holder_name,
            mastery="rapid_response",
            requested_count=int(requested_total),
            qualifying_count=0,
            # Slice D / D5: prefer explicit naming while retaining legacy field.
            qualifying_expiration_count=0,
            resolution_phase=str(EventType.TURN_END),
            resolution_step=int(step_i),
            skill_sequence_step=int(step_i),
            turn_counter=int(turn_counter),
            reason="no_qualifying_expirations",
        )
        resolved.add(key)


def _emit_requested_mastery_procs_once(
        *,
        event_sink: EventSink,
        actors: list[Actor],
        turn_counter: int,
        mastery_proc_requester: callable,
) -> None:
    """Emit user-requested mastery procs for this turn at most once.

    ADR-001 alignment:
      - Requests are keyed by (acting_actor_name, skill_sequence_step).
      - The caller provides `turn_counter` only as a stable per-turn bookmark;
        it is NOT used for request lookup.

    TURN_START seam behavior:
      - Determine the acting actor from the most recent TURN_START event.
      - Interpret `skill_sequence_step` as the NEXT skill token to be consumed:
          skill_sequence_step = actor.skill_sequence_cursor + 1
        (skill_sequence_cursor is 0-based and is advanced by the CLI provider when a skill is consumed.)
    """
    emitted_keys = getattr(event_sink, "_mastery_proc_keys_emitted", None)
    if not isinstance(emitted_keys, set):
        emitted_keys = set()
        setattr(event_sink, "_mastery_proc_keys_emitted", emitted_keys)

    # Determine the acting actor by inspecting the event stream.
    acting_actor: str | None = None
    try:
        for ev in reversed(getattr(event_sink, "events", []) or []):
            if getattr(ev, "type", None) == EventType.TURN_START:
                acting_actor = getattr(ev, "actor", None)
                break
    except Exception:
        acting_actor = None

    if not acting_actor:
        return

    actor_obj = next((a for a in actors if a.name == acting_actor), None)
    if actor_obj is None:
        return

    # ADR-001: next skill activation step (1-based)
    cursor = int(getattr(actor_obj, "skill_sequence_cursor", 0))
    skill_sequence_step = cursor + 1
    key = (acting_actor, int(skill_sequence_step))
    if key in emitted_keys:
        return

    requested = mastery_proc_requester(
        {
            "champion_name": acting_actor,
            "skill_sequence_step": int(skill_sequence_step),
            "turn_counter": int(turn_counter),  # legacy observability only
        }
    ) or []
    if not isinstance(requested, list):
        raise ValueError("mastery_proc_requester must return a list of proc dicts")

    emitted_any = False
    for item in requested:
        if not isinstance(item, dict):
            raise ValueError("mastery proc request items must be dicts")
        holder = item.get("holder")
        mastery = item.get("mastery")
        if not isinstance(holder, str) or not holder.strip():
            continue
        if not isinstance(mastery, str) or not mastery.strip():
            continue
        count = item.get("count")
        if not isinstance(count, int) or count <= 0:
            raise ValueError("mastery proc request requires positive int 'count'")

        emitted_any = True

        event_sink.emit(
            EventType.MASTERY_PROC,
            actor=str(holder),
            holder=str(holder),
            mastery=str(mastery),
            count=int(count),
            # Keep turn_counter for legacy observability (it is not used for scheduling).
            turn_counter=int(turn_counter),
        )

        _apply_mastery_proc_effects(
            actors=actors,
            holder=str(holder),
            mastery=str(mastery),
            count=int(count),
        )

    if emitted_any:
        emitted_keys.add(key)


def _apply_mastery_proc_effects(
        *,
        actors: list["Actor"],
        holder: str,
        mastery: str,
        count: int,
) -> None:
    """
    Effect-plane handler (minimal): apply deterministic effects for proc events.
    """
    holder = (holder or "").strip()
    mastery = (mastery or "").strip()
    if int(count) <= 0:
        return

    # Minimal deterministic mastery effects used by the simulator tests.
    if holder == "Mikage" and mastery == "rapid_response":
        a = next((x for x in actors if x.name == "Mikage"), None)
        if a is None:
            return
        a.turn_meter += float(TM_GATE) * 0.10 * float(count)
        return

    if holder == "Mithrala" and mastery == "arcane_celerity":
        a = next((x for x in actors if x.name == "Mithrala"), None)
        if a is None:
            return
        a.turn_meter += float(TM_GATE) * 0.10 * float(count)
        return


def step_tick(
        actors: list[Actor],
        event_sink: EventSink | None = None,
        *,
        snapshot_capture: set[int] | None = None,
        hit_counts_by_actor: dict[str, int] | None = None,
        hit_provider: callable | None = None,
        hit_contribution_resolver: HitContributionResolver | None = None,
        # Dependency-injection seam: phase-aware expiration resolver.
        #
        # Back-compat: `expiration_injector` is kept as an alias, but the semantic
        # contract is now explicit: it is called once per expiration phase.
        expiration_resolver: ExpirationResolver | None = None,
        expiration_injector: callable | None = None,
        mastery_proc_requester: callable | None = None,
        effect_placement_provider: callable | None = None,
) -> Actor | None:
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

    Extra turn contract:
    - Resolving an extra turn MUST NOT advance the global battle clock.
      (The EventSink tick counter is the observable proxy for that clock.)

    Domain bookmark contract:
    - TURN_START and TURN_END are bookmarks.
    - All turn semantics (effects, housekeeping, expirations, procs) happen BETWEEN them.
    - Therefore, end-of-turn duration decrement and any EFFECT_EXPIRED events must occur
      BEFORE emitting TURN_END.
    """

    # Normalize DI seam: prefer phase-aware expiration_resolver.
    #
    # Back-compat: callers/tests may still pass `expiration_injector`.
    if expiration_resolver is None and expiration_injector is not None:
        expiration_resolver = expiration_injector  # type: ignore[assignment]

    # 0) extra turn handling (no fill)
    extra_candidates = [(i, a) for i, a in enumerate(actors) if int(a.extra_turns) > 0]
    if extra_candidates:
        i_best, best = extra_candidates[0]
        best.extra_turns = int(best.extra_turns) - 1
        is_extra_turn = True
    else:
        best = None
        i_best = -1
        is_extra_turn = False

    # 0.5) tick start
    if event_sink is not None:
        if (not is_extra_turn) or (event_sink.current_tick <= 0):
            event_sink.start_tick()
            event_sink.emit(EventType.TICK_START)

    # 1) simultaneous fill (only if no extra turn was granted)
    if best is None:
        for a in actors:
            eff_speed = (
                    float(a.speed)
                    * float(a.speed_multiplier)
                    * float(speed_multiplier_from_effects(a.effects))
            )
            a.turn_meter += eff_speed

        if event_sink is not None:
            event_sink.emit(
                EventType.FILL_COMPLETE,
                meters=[
                    {
                        "name": a.name,
                        "turn_meter": float(a.turn_meter),
                    }
                    for a in actors
                ],
            )

        # 2) find all ready actors
        ready = [a for a in actors if a.turn_meter + EPS >= TM_GATE]
        if not ready:
            return None

        # 3) choose actor: highest TM, then speed, then list order
        indexed = list(enumerate(actors))
        ready_indexed = [(i, a) for (i, a) in indexed if a.turn_meter + EPS >= TM_GATE]
        i_best, best = max(
            ready_indexed,
            key=lambda t: (t[1].turn_meter, t[1].speed, -t[0]),
        )

    if event_sink is not None:
        event_sink.emit(
            EventType.WINNER_SELECTED,
            actor=best.name,
            actor_index=i_best,
            pre_reset_tm=float(best.turn_meter),
        )

    # 4) reset TM to 0
    best.turn_meter = 0.0

    if event_sink is not None:
        event_sink.emit(EventType.RESET_APPLIED, actor=best.name, actor_index=i_best)

        # Observability hook (C1): faction-gated join-attack evaluation.
        join_attack_joiners: list[str] | None = None
        if best.name == "Mikage":
            join_attack_joiners = [
                a.name
                for a in actors
                if (not a.is_boss)
                   and (a is not best)
                   and (getattr(a, "faction", None) == "Shadowkin")
            ]

        # Boss shield semantics (C1 deliverable):
        if bool(getattr(best, "is_boss", False)):
            shield_max = getattr(best, "shield_max", None)
            if shield_max is not None:
                best.shield = int(shield_max)

        boss_shield = _boss_shield_snapshot(actors)
        if boss_shield is None:
            if join_attack_joiners is None:
                event_sink.emit(EventType.TURN_START, actor=best.name, actor_index=i_best)
            else:
                event_sink.emit(
                    EventType.TURN_START,
                    actor=best.name,
                    actor_index=i_best,
                    join_attack_joiners=join_attack_joiners,
                )
        else:
            if join_attack_joiners is None:
                event_sink.emit(
                    EventType.TURN_START,
                    actor=best.name,
                    actor_index=i_best,
                    boss_shield_value=boss_shield["value"],
                    boss_shield_status=boss_shield["status"],
                )
            else:
                event_sink.emit(
                    EventType.TURN_START,
                    actor=best.name,
                    actor_index=i_best,
                    boss_shield_value=boss_shield["value"],
                    boss_shield_status=boss_shield["status"],
                    join_attack_joiners=join_attack_joiners,
                )

        # TURN_START housekeeping (happens after TURN_START bookmark)
        # Dev-only DI seam: stable turn bookmark counter (increments once per TURN_START).
        turn_counter = int(getattr(event_sink, "turn_counter", 0)) + 1
        setattr(event_sink, "turn_counter", turn_counter)

        # CLI seam: if the user requested a mastery proc on this step, emit it now.
        # (At most once per step; expiration-triggered emission uses the same guard.)
        if mastery_proc_requester is not None and bool(getattr(mastery_proc_requester, "emit_on_turn_start", False)):
            _emit_requested_mastery_procs_once(
                event_sink=event_sink,
                actors=actors,
                turn_counter=int(turn_counter),
                mastery_proc_requester=mastery_proc_requester,
            )

        # Phase-aware expirations (DI): resolve expirations at TURN_START phase.
        if expiration_resolver is not None:
            _resolve_external_expirations_for_phase(
                event_sink=event_sink,
                actors=actors,
                phase=EventType.TURN_START,
                acting_actor=best,
                acting_actor_index=i_best,
                turn_counter=turn_counter,
                expiration_resolver=expiration_resolver,
                mastery_proc_requester=mastery_proc_requester,
            )
    else:
        # No event sink: we still need a stable per-battle turn counter for duration semantics.
        # Store it on the first actor instance so it naturally resets per battle/test.
        seed = actors[0] if actors else best
        turn_counter = int(getattr(seed, "_turn_counter", 0)) + 1
        setattr(seed, "_turn_counter", turn_counter)

    # Stamp the current turn counter onto actors so provider helpers can read it
    # when placing effect instances (e.g., apply_skill_buffs).
    for a in actors:
        setattr(a, "_current_turn_counter", int(turn_counter))

    # TURN_START-triggered effects (A2): Poison triggers and decrements at TURN_START.
    remaining_start, expired_start, poison_dmg = apply_turn_start_effects(best.effects)
    best.effects = remaining_start
    if poison_dmg > 0 and float(best.max_hp) > 0:
        best.hp = max(0.0, float(best.hp) - float(poison_dmg))
        if event_sink is not None:
            event_sink.emit(
                EventType.EFFECT_TRIGGERED,
                actor=best.name,
                actor_index=i_best,
                effect="POISON",
                amount=float(poison_dmg),
                phase=EventType.TURN_START,
            )

    # If any TURN_START effects expired (e.g., Poison), emit expiration now.
    if event_sink is not None:
        for e in expired_start:
            event_sink.emit(
                EventType.EFFECT_EXPIRED,
                actor=best.name,
                actor_index=i_best,
                effect=str(e.kind),
                phase=EventType.TURN_START,
            )

    # Boss shield hit-counter semantics (C2): Apply turn-caused hits before TURN_END snapshot.
    current_hits: dict[str, int] | None = None
    if hit_provider is not None:
        current_hits = hit_provider(best.name) or {}
    elif hit_counts_by_actor is not None:
        current_hits = hit_counts_by_actor

    # Boss skill hit counts represent attacks *from* the boss and must not be
    # treated as shield-hit contributions against the boss. Any shield hits
    # that occur during a boss turn are modeled via engine-owned contributors
    # (e.g., Counterattack, Faultless Defense reflect).
    if (
        current_hits is not None
        and bool(getattr(best, "is_boss", False))
        and hit_provider is not None
    ):
        current_hits = {}

    if current_hits is not None:
        resolver = hit_contribution_resolver or _default_hit_contribution_resolver

        # Engine-owned seam: allow rule components to contribute additional hits
        # (e.g., Phantom Touch, Counterattack, Ally Attack, Faultless Defense).
        extra = resolver(
            acting_actor=best,
            actors=actors,
            base_hits=dict(current_hits),
            turn_counter=int(turn_counter),
            tick=int(getattr(event_sink, "current_tick", 0)) if event_sink is not None else 0,
        )
        if isinstance(extra, dict) and extra:
            merged: dict[str, int] = dict(current_hits)
            for k, v in extra.items():
                try:
                    inc = int(v)
                except Exception:
                    continue
                if inc == 0:
                    continue
                merged[k] = int(merged.get(k, 0)) + inc
            current_hits = merged
    if current_hits is not None:
        boss = next((a for a in actors if bool(getattr(a, "is_boss", False))), None)
        if boss is not None:
            normal_hits = sum(int(v) for k, v in current_hits.items() if k != "REFLECT")
            if normal_hits > 0:
                boss.shield = max(0, int(getattr(boss, "shield", 0)) - normal_hits)

            reflect_hits = int(current_hits.get("REFLECT", 0))
            if reflect_hits > 0:
                boss.shield = max(0, int(getattr(boss, "shield", 0)) - reflect_hits)

    # Data-driven effect placements (turn_overrides.skill_sequence_steps).
    # These are applied after shield-hit math so requirements like "AFTER_SHIELD_OPEN"
    # can gate on the updated boss shield state.
    if effect_placement_provider is not None:
        try:
            step_i = int(getattr(best, "skill_sequence_cursor", 0))
        except Exception:
            step_i = 0
        if step_i > 0:
            placements = effect_placement_provider({
                "actor_name": str(getattr(best, "name", "")),
                "skill_sequence_step": int(step_i),
            }) or []
        else:
            placements = []

        if isinstance(placements, list) and placements:
            boss = next((a for a in actors if bool(getattr(a, "is_boss", False))), None)
            boss_shield_open = bool(boss is not None and int(getattr(boss, "shield", 0)) == 0)

            for item in placements:
                if not isinstance(item, dict):
                    continue

                # Optional requires gate: currently only supports boss_shield_open.
                requires = item.get("requires")
                if isinstance(requires, dict):
                    if requires.get("boss_shield_open") is True and not boss_shield_open:
                        continue

                timing = item.get("timing")
                if isinstance(timing, str) and timing.strip().upper() == "AFTER_SHIELD_OPEN":
                    if not boss_shield_open:
                        continue

                target_name = item.get("target")
                if not isinstance(target_name, str) or not target_name.strip():
                    continue
                target = next((a for a in actors if a.name == target_name), None)
                if target is None:
                    continue

                effect_kind = item.get("effect_kind")
                if not isinstance(effect_kind, str) or not effect_kind.strip():
                    continue
                effect_kind_u = effect_kind.strip().upper()

                # Minimal effect vocabulary: expand only when tests/fixtures require it.
                if effect_kind_u not in {"DECREASE_SPD", "HEX"}:
                    continue

                magnitude = item.get("magnitude", 0.0)
                duration_turns = item.get("duration_turns", 0)
                try:
                    mag_f = float(magnitude)
                    dur_i = int(duration_turns)
                except Exception:
                    continue
                if dur_i <= 0:
                    continue

                from rsl_turn_sequencing.effects import Effect, EffectKind

                if effect_kind_u == "DECREASE_SPD":
                    target.effects.append(Effect(EffectKind.DECREASE_SPD, dur_i, magnitude=mag_f))
                else:
                    # HEX has no magnitude.
                    target.effects.append(Effect(EffectKind.HEX, dur_i, magnitude=0.0))

                if event_sink is not None:
                    event_sink.emit(
                        EventType.EFFECT_APPLIED,
                        actor=str(getattr(best, "name", "")),
                        actor_index=int(i_best),
                        effect=effect_kind_u,
                        target=target.name,
                        magnitude=float(mag_f),
                        duration=int(dur_i),
                        timing=str(timing) if isinstance(timing, str) else None,
                    )

    # Engine-owned minimal skill effect modeling: Mithrala A2 places HEX.
    #
    # We only model this when the boss shield is already open (broken) to match
    # the dataset intent for the Fire Knight shield-state baseline.
    try:
        seq = getattr(best, "skill_sequence", None) or []
        cursor = int(getattr(best, "skill_sequence_cursor", 0))
        last_skill = str(seq[cursor - 1]) if cursor > 0 and cursor <= len(seq) else ""
    except Exception:
        last_skill = ""

    if (best.name or "").strip().lower() == "mithrala" and last_skill.strip().upper() == "A2":
        boss = next((a for a in actors if bool(getattr(a, "is_boss", False))), None)
        boss_shield_open = bool(boss is not None and int(getattr(boss, "shield", 0)) == 0)
        if boss is not None and boss_shield_open:
            from rsl_turn_sequencing.effects import Effect, EffectKind

            # Mithrala's A2 Hex is typically 2 turns; we model the duration only.
            boss.effects.append(Effect(EffectKind.HEX, 2, magnitude=0.0))

            if event_sink is not None:
                event_sink.emit(
                    EventType.EFFECT_APPLIED,
                    actor=str(getattr(best, "name", "")),
                    actor_index=int(i_best),
                    effect="HEX",
                    target=boss.name,
                    magnitude=0.0,
                    duration=2,
                    timing="AFTER_SHIELD_OPEN",
                )

    # Optional snapshot capture at TURN_END (observer-only)
    if event_sink is not None:
        if (
                snapshot_capture is not None
                and event_sink.current_tick in snapshot_capture
                and hasattr(event_sink, "capture_snapshot")
        ):
            event_sink.capture_snapshot(
                turn=event_sink.current_tick,
                phase=EventType.TURN_END,
                snapshot={
                    "actor": best.name,
                    "actors": [
                        {
                            "name": a.name,
                            "turn_meter": float(a.turn_meter),
                            "speed": float(a.speed),
                            "speed_multiplier": float(a.speed_multiplier),
                        }
                        for a in actors
                    ],
                },
            )

        # Phase-aware expirations (DI): resolve expirations at TURN_END phase.
        if expiration_resolver is not None:
            _resolve_external_expirations_for_phase(
                event_sink=event_sink,
                actors=actors,
                phase=EventType.TURN_END,
                acting_actor=best,
                acting_actor_index=i_best,
                turn_counter=int(turn_counter),
                expiration_resolver=expiration_resolver,
                mastery_proc_requester=mastery_proc_requester,
            )

    # END-OF-TURN semantics must happen BEFORE TURN_END bookmark.
    duration_before = _decrement_active_effect_durations_turn_end(best, turn_counter=int(turn_counter))
    if event_sink is not None:
        _emit_effect_duration_changed_events(
            event_sink=event_sink,
            owner=best,
            duration_before=duration_before,
            turn_counter=int(turn_counter),
            boundary="turn_end",
            reason="tick_decrement",
        )

    # Slice 4: Expire BUFF instances whose duration reached 0 (engine-owned).
    if event_sink is not None and duration_before:
        _expire_active_effects_turn_end(
            owner=best,
            owner_index=i_best,
            actors=actors,
            event_sink=event_sink,
            duration_before=duration_before,
            turn_counter=int(turn_counter),
            mastery_proc_requester=mastery_proc_requester,
        )

    remaining_end, expired_end = decrement_turn_end(best.effects)
    best.effects = remaining_end
    if event_sink is not None:
        for e in expired_end:
            event_sink.emit(
                EventType.EFFECT_EXPIRED,
                actor=best.name,
                actor_index=i_best,
                effect=str(e.kind),
            )

        # Slice B: resolve guarded proc requests after all expirations for this turn, before TURN_END.
        if mastery_proc_requester is not None:
            _resolve_guarded_mastery_procs_for_qualifying_expirations(
                event_sink=event_sink,
                actors=actors,
                turn_counter=int(turn_counter),
                mastery_proc_requester=mastery_proc_requester,
            )

        boss_shield = _boss_shield_snapshot(actors)
        if boss_shield is None:
            event_sink.emit(EventType.TURN_END, actor=best.name, actor_index=i_best)
        else:
            event_sink.emit(
                EventType.TURN_END,
                actor=best.name,
                actor_index=i_best,
                boss_shield_value=boss_shield["value"],
                boss_shield_status=boss_shield["status"],
            )

    return best


def step_tick_debug(actors: list[Actor]) -> tuple[Actor | None, list[float]]:
    """
    Advance the simulation by one global tick, returning:
      (winner, turn_meters_before_reset)

    This provides observability for traces/logging without changing the
    core step_tick() behavior.
    """
    # 1) simultaneous fill
    for a in actors:
        eff_speed = float(a.speed) * float(a.speed_multiplier)
        a.turn_meter += eff_speed

    # Snapshot AFTER fill, BEFORE any reset (this is the "winning snapshot")
    before_reset = [float(a.turn_meter) for a in actors]

    # 2) find all ready actors
    ready_indexed = [(i, a) for (i, a) in enumerate(actors) if a.turn_meter + EPS >= TM_GATE]
    if not ready_indexed:
        return None, before_reset

    # 3) choose actor: highest TM, then speed, then list order
    _, best = max(
        ready_indexed,
        key=lambda t: (t[1].turn_meter, t[1].speed, -t[0]),
    )

    # 4) reset TM (overflow discarded)
    best.turn_meter = 0.0
    return best, before_reset
