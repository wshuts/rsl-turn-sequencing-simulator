from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from rsl_turn_sequencing.effects import (
    apply_turn_start_effects,
    decrement_turn_end,
    speed_multiplier_from_effects,
)
from rsl_turn_sequencing.event_sink import EventSink
from rsl_turn_sequencing.events import EventType
from rsl_turn_sequencing.models import Actor, EffectInstance

TM_GATE = 1430.0
EPS = 1e-9


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
    the engine builds/owns the mastery proc requester. Callers should not pass
    requester closures into the engine.
    """

    mastery_proc_requester = None
    if battle_path_for_mastery_procs is not None:
        mastery_proc_requester = build_mastery_proc_requester_from_battle_path(battle_path_for_mastery_procs)

    def _is_boss_turn_end_event(evt: object) -> bool:
        actor = getattr(evt, "actor", None)
        etype = getattr(evt, "type", None)
        if actor != boss_actor:
            return False
        if hasattr(etype, "value"):
            return etype.value == "TURN_END"
        return str(etype) == "TURN_END"

    boss_turns_seen = 0

    for _ in range(int(ticks)):
        before_len = len(getattr(event_sink, "events", []) or [])
        step_tick(
            actors,
            event_sink=event_sink,
            hit_provider=hit_provider,
            mastery_proc_requester=mastery_proc_requester,
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

        # Slice 5: mastery proc gating for engine-owned expirations.
        if mastery_proc_requester is not None:
            _maybe_emit_mastery_proc_for_expiration(
                event_sink=event_sink,
                actors=actors,
                turn_counter=int(turn_counter),
                expired_effect=fx,
                mastery_proc_requester=mastery_proc_requester,
            )



def _emit_injected_expirations(
    *,
    event_sink: "EventSink",
    actors: list["Actor"],
    phase: "EventType",
    acting_actor: "Actor",
    acting_actor_index: int,
    turn_counter: int,
    expiration_injector: callable,
    mastery_proc_requester: callable | None = None,
) -> None:
    injected = expiration_injector(
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

            # Slice: Rapid Response (proc dynamics only)
            # If a BUFF placed by Mikage expires and a deterministic proc request exists
            # for this step (turn_counter), emit MASTERY_PROC with the requested payload.
            if mastery_proc_requester is not None:
                _maybe_emit_mastery_proc_for_expiration(
                    event_sink=event_sink,
                    actors=actors,
                    turn_counter=turn_counter,
                    expired_effect=fx,
                    mastery_proc_requester=mastery_proc_requester,
                )

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


def _maybe_emit_mastery_proc_for_expiration(
    *,
    event_sink: "EventSink",
    actors: list[Actor],
    turn_counter: int,
    expired_effect: object,
    mastery_proc_requester: callable,
) -> None:
    """Proc dynamics only (expiration-triggered).

    When a BUFF placed by Mikage expires, consult the deterministic proc request
    provider keyed by ("Mikage", skill_sequence_step).

    ADR-001 alignment:
      - skill_sequence_step is the number of skills Mikage has consumed so far (1-based).
        We read this from Actor.skill_sequence_cursor (0-based), which is advanced by the
        CLI provider when Mikage consumes a skill token.
      - turn_counter is NOT used for scheduling; it remains in the emitted event payload
        for legacy observability only.
    """
    effect_kind = getattr(expired_effect, "effect_kind", None)
    placed_by = getattr(expired_effect, "placed_by", None)
    if effect_kind != "BUFF":
        return
    if placed_by != "Mikage":
        return

    mikage = next((a for a in actors if a.name == "Mikage"), None)
    if mikage is None:
        return

    # ADR-001: consumed-so-far step (1-based), derived from 0-based cursor
    skill_sequence_step = int(getattr(mikage, "skill_sequence_cursor", 0))
    if skill_sequence_step <= 0:
        # Mikage has not consumed any skills yet; there is no valid 1-based step to consult.
        return

    emitted_keys = getattr(event_sink, "_mastery_proc_keys_emitted", None)
    if not isinstance(emitted_keys, set):
        emitted_keys = set()
        setattr(event_sink, "_mastery_proc_keys_emitted", emitted_keys)

    key = ("Mikage", int(skill_sequence_step))
    if key in emitted_keys:
        return

    requested = mastery_proc_requester(
        {
            "champion_name": "Mikage",
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
        if item.get("holder") != "Mikage":
            continue
        if item.get("mastery") != "rapid_response":
            continue
        count = item.get("count")
        if not isinstance(count, int) or count <= 0:
            raise ValueError("mastery proc request requires positive int 'count'")

        emitted_any = True

        event_sink.emit(
            EventType.MASTERY_PROC,
            actor="Mikage",
            holder="Mikage",
            mastery="rapid_response",
            count=int(count),
            turn_counter=int(turn_counter),
        )

        _apply_mastery_proc_effects(
            actors=actors,
            holder="Mikage",
            mastery="rapid_response",
            count=int(count),
        )

    if emitted_any:
        emitted_keys.add(key)


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
        if item.get("holder") != "Mikage":
            continue
        if item.get("mastery") != "rapid_response":
            continue
        count = item.get("count")
        if not isinstance(count, int) or count <= 0:
            raise ValueError("mastery proc request requires positive int 'count'")

        emitted_any = True

        event_sink.emit(
            EventType.MASTERY_PROC,
            actor="Mikage",
            holder="Mikage",
            mastery="rapid_response",
            count=int(count),
            # Keep turn_counter for legacy observability (it is not used for scheduling).
            turn_counter=int(turn_counter),
        )

        _apply_mastery_proc_effects(
            actors=actors,
            holder="Mikage",
            mastery="rapid_response",
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
    if (holder or "").strip() != "Mikage":
        return
    if (mastery or "").strip() != "rapid_response":
        return
    if int(count) <= 0:
        return

    mikage = next((a for a in actors if a.name == "Mikage"), None)
    if mikage is None:
        return

    # Rapid Response: +10% turn meter per proc count.
    mikage.turn_meter += float(TM_GATE) * 0.10 * float(count)


def step_tick(
    actors: list[Actor],
    event_sink: EventSink | None = None,
    *,
    snapshot_capture: set[int] | None = None,
    hit_counts_by_actor: dict[str, int] | None = None,
    hit_provider: callable | None = None,
    expiration_injector: callable | None = None,
    mastery_proc_requester: callable | None = None,
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

        # --- TURN_START bookmark should be emitted BEFORE TURN_START housekeeping/DI seams ---
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

        # Slice 1: allow tests to inject expirations immediately AFTER TURN_START.
        if expiration_injector is not None:
            _emit_injected_expirations(
                event_sink=event_sink,
                actors=actors,
                phase=EventType.TURN_START,
                acting_actor=best,
                acting_actor_index=i_best,
                turn_counter=turn_counter,
                expiration_injector=expiration_injector,
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
    current_hits = None
    if hit_provider is not None:
        current_hits = hit_provider(best.name) or {}
    elif hit_counts_by_actor is not None:
        current_hits = hit_counts_by_actor
    if current_hits is not None:
        boss = next((a for a in actors if bool(getattr(a, "is_boss", False))), None)
        if boss is not None:
            normal_hits = sum(int(v) for k, v in current_hits.items() if k != "REFLECT")
            if normal_hits > 0:
                boss.shield = max(0, int(getattr(boss, "shield", 0)) - normal_hits)

            reflect_hits = int(current_hits.get("REFLECT", 0))
            if reflect_hits > 0:
                boss.shield = max(0, int(getattr(boss, "shield", 0)) - reflect_hits)

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

        # Slice 1: allow tests to inject expirations immediately before TURN_END.
        if expiration_injector is not None:
            _emit_injected_expirations(
                event_sink=event_sink,
                actors=actors,
                phase=EventType.TURN_END,
                acting_actor=best,
                acting_actor_index=i_best,
                turn_counter=int(turn_counter),
                expiration_injector=expiration_injector,
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
