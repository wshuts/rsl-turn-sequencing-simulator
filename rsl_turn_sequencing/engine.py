from __future__ import annotations

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


def _maybe_emit_mastery_proc_for_expiration(
    *,
    event_sink: "EventSink",
    actors: list[Actor],
    turn_counter: int,
    expired_effect: object,
    mastery_proc_requester: callable,
) -> None:
    """Proc dynamics only.

    When a BUFF placed by Mikage expires, consult the deterministic proc request
    provider for this step (turn_counter). If a Rapid Response proc is requested,
    emit a MASTERY_PROC event with the requested payload.

    The requester is expected to return a list of dicts like:
      [{"holder":"Mikage","mastery":"rapid_response","count":1}, ...]
    """
    effect_kind = getattr(expired_effect, "effect_kind", None)
    placed_by = getattr(expired_effect, "placed_by", None)
    if effect_kind != "BUFF":
        return
    if placed_by != "Mikage":
        return

    requested = mastery_proc_requester({"turn_counter": int(turn_counter)}) or []
    if not isinstance(requested, list):
        raise ValueError("mastery_proc_requester must return a list of proc dicts")

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
