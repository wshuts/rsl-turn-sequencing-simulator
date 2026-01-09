from rsl_turn_sequencing.engine import TM_GATE, step_tick
from rsl_turn_sequencing.event_sink import InMemoryEventSink
from rsl_turn_sequencing.events import EventType
from rsl_turn_sequencing.models import Actor


def test_can_inject_expiration_event_before_turn_start_within_turn_boundary() -> None:
    """
    Slice 1 seam: inject an expiration event after winner is chosen,
    immediately before TURN_START is emitted.
    """

    mikage = Actor("Mikage", 100.0)
    other = Actor("Other", 100.0)

    # Ensure Mikage will win deterministically on the first call.
    mikage.turn_meter = TM_GATE
    other.turn_meter = 0.0

    sink = InMemoryEventSink()

    def injector(ctx: dict) -> list[dict]:
        if (
            ctx.get("phase") == str(EventType.TURN_START)
            and ctx.get("acting_actor") == "Mikage"
            and ctx.get("turn_counter") == 1
        ):
            return [{"target": "Mikage", "effect": "TEST_EFFECT"}]
        return []

    step_tick([mikage, other], event_sink=sink, expiration_injector=injector)

    injected = [
        e
        for e in sink.events
        if e.type == EventType.EFFECT_EXPIRED
        and e.actor == "Mikage"
        and e.data.get("effect") == "TEST_EFFECT"
        and e.data.get("injected") is True
        and e.data.get("phase") == str(EventType.TURN_START)
        and e.data.get("injected_turn_counter") == 1
    ]
    assert injected, "Expected an injected EFFECT_EXPIRED event for Mikage before TURN_START on turn 1."


def test_injector_supports_extra_turn_boundaries_without_advancing_tick() -> None:
    """Slice 2: expiration injector supports extra-turn boundaries (TURN_START/TURN_END)
    without advancing the battle clock tick.

    Scenario:
      - Run one normal tick where Mikage wins (tick advances to 1).
      - Grant Mikage an extra turn and call step_tick again.

    Contract:
      - The extra turn produces a full TURN_START → TURN_END boundary.
      - The expiration injector can inject at TURN_START and TURN_END for that extra turn.
      - The extra turn MUST NOT advance the global tick (Event.tick remains the same).
    """

    mikage = Actor("Mikage", 100.0)
    other = Actor("Other", 100.0)

    # Ensure Mikage wins deterministically on the first normal tick.
    mikage.turn_meter = TM_GATE
    other.turn_meter = 0.0

    sink = InMemoryEventSink()

    def injector(ctx: dict) -> list[dict]:
        # Inject on the extra turn only (turn_counter==2), at both TURN_START and TURN_END.
        if (
            ctx.get("acting_actor") == "Mikage"
            and ctx.get("turn_counter") == 2
            and ctx.get("phase") == str(EventType.TURN_START)
        ):
            return [{"target": "Mikage", "effect": "EXTRA_TURN_START"}]

        if (
            ctx.get("acting_actor") == "Mikage"
            and ctx.get("turn_counter") == 2
            and ctx.get("phase") == str(EventType.TURN_END)
        ):
            return [{"target": "Mikage", "effect": "EXTRA_TURN_END"}]

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

    injected_start = [
        e
        for e in sink.events
        if e.type == EventType.EFFECT_EXPIRED
        and e.actor == "Mikage"
        and e.data.get("effect") == "EXTRA_TURN_START"
        and e.data.get("injected") is True
        and e.data.get("phase") == str(EventType.TURN_START)
        and e.data.get("injected_turn_counter") == 2
        and e.tick == tick_after_normal
    ]
    assert injected_start, (
        "Expected an injected EFFECT_EXPIRED event before TURN_START on the extra turn (turn_counter=2)."
    )

    injected_end = [
        e
        for e in sink.events
        if e.type == EventType.EFFECT_EXPIRED
        and e.actor == "Mikage"
        and e.data.get("effect") == "EXTRA_TURN_END"
        and e.data.get("injected") is True
        and e.data.get("phase") == str(EventType.TURN_END)
        and e.data.get("injected_turn_counter") == 2
        and e.tick == tick_after_normal
    ]
    assert injected_end, (
        "Expected an injected EFFECT_EXPIRED event before TURN_END on the extra turn (turn_counter=2)."
    )
