from __future__ import annotations

from rsl_turn_sequencing.effects import (
    apply_turn_start_effects,
    decrement_turn_end,
    speed_multiplier_from_effects,
)
from rsl_turn_sequencing.event_sink import EventSink
from rsl_turn_sequencing.events import EventType
from rsl_turn_sequencing.models import Actor

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
            continue

        # --- Legacy path (deprecated) ---
        target = item.get("target") or item.get("actor") or acting_actor.name
        effect = item.get("effect")
        if not isinstance(target, str) or not target.strip():
            raise ValueError("Injected expiration requires non-empty 'target' (or 'actor').")
        if not isinstance(effect, str) or not effect.strip():
            raise ValueError("Injected expiration requires non-empty 'effect'.")
        try:
            target_index = next(i for i, a in enumerate(actors) if a.name == target)
        except StopIteration as exc:
            raise ValueError(f"Injected expiration target not found: {target!r}") from exc

        event_sink.emit(
            EventType.EFFECT_EXPIRED,
            actor=target,
            actor_index=target_index,
            effect=str(effect),
            injected=True,
            phase=str(phase),
            injected_turn_counter=int(turn_counter),
            acting_actor=acting_actor.name,
        )


def _validate_expire_effect_request(item: dict) -> None:
    """
    Manual enforcement of the minimal schema:
      {"type":"expire_effect","instance_id":"...","reason":"injected"}
    """
    if item.get("type") != "expire_effect":
        raise ValueError("expire_effect request requires type='expire_effect'.")
    instance_id = item.get("instance_id")
    if not isinstance(instance_id, str) or not instance_id.strip():
        raise ValueError("expire_effect request requires non-empty 'instance_id' (string).")
    if item.get("reason") != "injected":
        raise ValueError("expire_effect request requires reason='injected'.")
    allowed = {"type", "instance_id", "reason"}
    extras = set(item.keys()) - allowed
    if extras:
        raise ValueError(f"expire_effect request has unexpected fields: {sorted(extras)}")


def _expire_effect_instance_by_id(*, actors: list["Actor"], instance_id: str):
    """
    Locate and remove an EffectInstance by instance_id across all actors.

    Returns (owner_actor, effect_instance).
    """
    for owner in actors:
        active = getattr(owner, "active_effects", None)
        if not active:
            continue
        for i, fx in enumerate(list(active)):
            if getattr(fx, "instance_id", None) == instance_id:
                active.pop(i)
                return owner, fx
    raise ValueError(f"Effect instance not found for instance_id={instance_id!r}")



def _apply_mastery_proc_effects(*, actors: list[Actor], holder: str, mastery: str, count: int) -> None:
    """Effect plane (deterministic).

    Slice: Rapid Response
    - If the proc is Mikage's rapid_response, increase Mikage's turn meter by
      TM_GATE * 0.10 per proc count.
    """
    if holder != "Mikage":
        return
    if mastery != "rapid_response":
        return
    if count <= 0:
        return

    try:
        mikage = next(a for a in actors if a.name == "Mikage")
    except StopIteration:
        return

    mikage.turn_meter += float(TM_GATE) * 0.10 * float(count)


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
    emit a single MASTERY_PROC event with the requested payload.

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
    """

    # 0) extra turn handling (no fill)
    # If any actor has pending extra turns, grant the turn immediately.
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
    # Normal ticks advance the global clock. Extra turns do not.
    # If the sink has never started a tick (tick==0), we must start one
    # to satisfy the sink's contract before emitting any events.
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
            # IMPORTANT: contract expects "meters" key (tests depend on this).
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
        # Use index to make final tie-break stable
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

    # 4) act (for now, acting is just returning the actor) and reset TM to 0
    best.turn_meter = 0.0

    if event_sink is not None:
        event_sink.emit(EventType.RESET_APPLIED, actor=best.name, actor_index=i_best)

        # Observability hook (C1): faction-gated join-attack evaluation.
        # For now, we only expose Mikage A1 joiners based on Shadowkin faction.
        # This does not execute attacks or apply damage; it's trace-only semantics.
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
        # The boss shield resets to full at the start of the boss's own turn,
        # before TURN_START is emitted.
        if bool(getattr(best, "is_boss", False)):
            shield_max = getattr(best, "shield_max", None)
            if shield_max is not None:
                best.shield = int(shield_max)

        # Dev-only DI seam: stable turn bookmark counter (increments once per TURN_START).
        # Includes extra turns (TURN_START emitted for each turn boundary).
        turn_counter = int(getattr(event_sink, "turn_counter", 0)) + 1
        setattr(event_sink, "turn_counter", turn_counter)

        # Slice 1: allow tests to inject expirations immediately before TURN_START.
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

    # Boss shield hit-counter semantics (C2):
    # Apply turn-caused hits before TURN_END snapshot.
    #
    # This supports:
    #   - Single-actor hit injection (e.g., Coldheart A1)
    #   - Multi-source hit injection within one turn (e.g., Mikage A3 team-ups)
    #   - Non-actor hits such as reflect, keyed under "REFLECT"
    current_hits = None
    if hit_provider is not None:
        current_hits = hit_provider(best.name) or {}
    elif hit_counts_by_actor is not None:
        current_hits = hit_counts_by_actor
    if current_hits is not None:
        boss = next((a for a in actors if bool(getattr(a, "is_boss", False))), None)
        if boss is not None:
            # Sum all "normal" hits injected for this turn (may involve multiple sources).
            normal_hits = sum(
                int(v)
                for k, v in current_hits.items()
                if k != "REFLECT"
            )
            if normal_hits > 0:
                boss.shield = max(0, int(getattr(boss, "shield", 0)) - normal_hits)

            # Reflect hits are allowed during boss turns (or any turn) and are modeled separately.
            reflect_hits = int(current_hits.get("REFLECT", 0))
            if reflect_hits > 0:
                boss.shield = max(0, int(getattr(boss, "shield", 0)) - reflect_hits)

    if event_sink is not None:
        # Optional snapshot capture at TURN_END (observer-only)
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
            turn_counter = int(getattr(event_sink, "turn_counter", 0))
            _emit_injected_expirations(
                event_sink=event_sink,
                actors=actors,
                phase=EventType.TURN_END,
                acting_actor=best,
                acting_actor_index=i_best,
                turn_counter=turn_counter,
                expiration_injector=expiration_injector,
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

    # Effect semantics (observer-faithful):
    # - Duration decrements at TURN_END of the affected actor (including extra turns later).
    remaining, expired = decrement_turn_end(best.effects)
    best.effects = remaining
    if event_sink is not None:
        for e in expired:
            event_sink.emit(
                EventType.EFFECT_EXPIRED,
                actor=best.name,
                actor_index=i_best,
                effect=str(e.kind),
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
