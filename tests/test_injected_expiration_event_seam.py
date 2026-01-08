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
        e for e in sink.events
        if e.type == EventType.EFFECT_EXPIRED
        and e.actor == "Mikage"
        and e.data.get("effect") == "TEST_EFFECT"
        and e.data.get("injected") is True
        and e.data.get("phase") == str(EventType.TURN_START)
        and e.data.get("injected_turn_counter") == 1
    ]
    assert injected, "Expected an injected EFFECT_EXPIRED event for Mikage before TURN_START on turn 1."
