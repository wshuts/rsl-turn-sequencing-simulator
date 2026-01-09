from rsl_turn_sequencing.engine import TM_GATE, step_tick
from rsl_turn_sequencing.event_sink import InMemoryEventSink
from rsl_turn_sequencing.events import EventType
from rsl_turn_sequencing.models import Actor, EffectInstance


def test_can_inject_expire_effect_before_turn_start_within_turn_boundary() -> None:
    """
    Slice 1 seam: inject an expire_effect request after winner is chosen,
    immediately before TURN_START is emitted.

    Contract:
      - injector returns schema-shaped expire_effect request
      - engine removes the instance from actor.active_effects
      - engine emits EFFECT_EXPIRED with structured payload
    """
    mikage = Actor("Mikage", 100.0)
    other = Actor("Other", 100.0)

    mikage.turn_meter = TM_GATE
    other.turn_meter = 0.0

    # Arrange: Mikage has an active BUFF instance we will expire
    mikage.active_effects = [
        EffectInstance(
            instance_id="fx_test_01",
            effect_id="test_buff",
            effect_kind="BUFF",
            placed_by="Mikage",
        )
    ]

    sink = InMemoryEventSink()

    def injector(ctx: dict) -> list[dict]:
        if (
            ctx.get("phase") == str(EventType.TURN_START)
            and ctx.get("acting_actor") == "Mikage"
            and ctx.get("turn_counter") == 1
        ):
            return [
                {
                    "type": "expire_effect",
                    "instance_id": "fx_test_01",
                    "reason": "injected",
                }
            ]
        return []

    step_tick([mikage, other], event_sink=sink, expiration_injector=injector)

    # Effect removed
    assert mikage.active_effects == []

    injected = [
        e
        for e in sink.events
        if e.type == EventType.EFFECT_EXPIRED
        and e.actor == "Mikage"
        and e.data.get("instance_id") == "fx_test_01"
        and e.data.get("effect_id") == "test_buff"
        and e.data.get("effect_kind") == "BUFF"
        and e.data.get("owner") == "Mikage"
        and e.data.get("placed_by") == "Mikage"
        and e.data.get("reason") == "injected"
        and e.data.get("phase") == str(EventType.TURN_START)
        and e.data.get("injected_turn_counter") == 1
    ]
    assert injected, "Expected structured EFFECT_EXPIRED before TURN_START on turn 1."


def test_injector_supports_extra_turn_boundaries_without_advancing_tick() -> None:
    """Slice 2: expiration injector supports extra-turn boundaries (TURN_START/TURN_END)
    without advancing the battle clock tick.

    Contract:
      - extra turn produces full TURN_START → TURN_END boundary
      - injector can expire at TURN_START and TURN_END for the extra turn (turn_counter=2)
      - extra turn MUST NOT advance global tick
    """
    mikage = Actor("Mikage", 100.0)
    other = Actor("Other", 100.0)

    mikage.turn_meter = TM_GATE
    other.turn_meter = 0.0

    # Arrange: two instances so we can expire one at TURN_START and one at TURN_END
    mikage.active_effects = [
        EffectInstance("fx_extra_start", "extra_start_buff", "BUFF", placed_by="Mikage"),
        EffectInstance("fx_extra_end", "extra_end_buff", "BUFF", placed_by="Mikage"),
    ]

    sink = InMemoryEventSink()

    def injector(ctx: dict) -> list[dict]:
        if (
            ctx.get("acting_actor") == "Mikage"
            and ctx.get("turn_counter") == 2
            and ctx.get("phase") == str(EventType.TURN_START)
        ):
            return [{"type": "expire_effect", "instance_id": "fx_extra_start", "reason": "injected"}]

        if (
            ctx.get("acting_actor") == "Mikage"
            and ctx.get("turn_counter") == 2
            and ctx.get("phase") == str(EventType.TURN_END)
        ):
            return [{"type": "expire_effect", "instance_id": "fx_extra_end", "reason": "injected"}]

        return []

    # 1) Normal turn (tick advances).
    winner1 = step_tick([mikage, other], event_sink=sink, expiration_injector=injector)
    assert winner1 is mikage
    tick_after_normal = sink.current_tick
    assert tick_after_normal == 1

    # 2) Extra turn (tick must NOT advance).
    mikage.extra_turns = 1
    winner2 = step_tick([mikage, other], event_sink=sink, expiration_injector=injector)
    assert winner2 is mikage
    assert sink.current_tick == tick_after_normal

    # Both instances should now be expired/removed
    assert mikage.active_effects == []

    injected_start = [
        e
        for e in sink.events
        if e.type == EventType.EFFECT_EXPIRED
        and e.actor == "Mikage"
        and e.data.get("instance_id") == "fx_extra_start"
        and e.data.get("phase") == str(EventType.TURN_START)
        and e.data.get("injected_turn_counter") == 2
        and e.tick == tick_after_normal
    ]
    assert injected_start, "Expected EFFECT_EXPIRED at TURN_START on extra turn (turn_counter=2)."

    injected_end = [
        e
        for e in sink.events
        if e.type == EventType.EFFECT_EXPIRED
        and e.actor == "Mikage"
        and e.data.get("instance_id") == "fx_extra_end"
        and e.data.get("phase") == str(EventType.TURN_END)
        and e.data.get("injected_turn_counter") == 2
        and e.tick == tick_after_normal
    ]
    assert injected_end, "Expected EFFECT_EXPIRED at TURN_END on extra turn (turn_counter=2)."
