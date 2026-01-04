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


def step_tick(
        actors: list[Actor],
        event_sink: EventSink | None = None,
        *,
        snapshot_capture: set[int] | None = None,
        hit_counts_by_actor: dict[str, int] | None = None,
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
    """
    if event_sink is not None:
        event_sink.start_tick()
        event_sink.emit(EventType.TICK_START)

    # 0) extra turn handling (no fill)
    # If any actor has pending extra turns, grant the turn immediately.
    extra_candidates = [(i, a) for i, a in enumerate(actors) if int(a.extra_turns) > 0]
    if extra_candidates:
        i_best, best = extra_candidates[0]
        best.extra_turns = int(best.extra_turns) - 1
    else:
        best = None
        i_best = -1

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
    # Supports:
    #   - actor-driven hits (skills, blessings)
    #   - non-actor hits (e.g., reflect), keyed under "REFLECT"
    if hit_counts_by_actor is not None:
        boss = next((a for a in actors if bool(getattr(a, "is_boss", False))), None)
        if boss is not None:
            # Hits from the acting actor (if not boss)
            if best is not boss:
                hits = int(hit_counts_by_actor.get(best.name, 0))
                if hits > 0:
                    boss.shield = max(0, int(getattr(boss, "shield", 0)) - hits)

            # Hits not attributable to the acting actor (e.g., reflect)
            reflect_hits = int(hit_counts_by_actor.get("REFLECT", 0))
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
