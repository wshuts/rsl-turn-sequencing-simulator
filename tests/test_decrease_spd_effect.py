from rsl_turn_sequencing.effects import Effect, EffectKind
from rsl_turn_sequencing.engine import step_tick
from rsl_turn_sequencing.event_sink import InMemoryEventSink
from rsl_turn_sequencing.events import EventType
from rsl_turn_sequencing.models import Actor


def make_actors():
    return [
        Actor("Mikage", 340.0),
        Actor("Mithrala", 282.0),
        Actor("Tomblord", 270.0),
        Actor("Coldheart", 265.0),
        Actor("Martyr", 252.0),
        Actor("Boss", 250.0),
    ]


def test_decrease_spd_duration_1_applies_and_expires_at_turn_end():
    """
    Observer semantics we are locking in (bookmark model):
      - Decrease SPD affects turn-meter fill while present.
      - Duration decrements at TURN_END of the affected actor.
      - duration=1 expires after exactly one of that actor's turns completes.
      - TURN_START / TURN_END are bookmarks; end-of-turn expirations are emitted BEFORE TURN_END.
    """
    actors = make_actors()
    sink = InMemoryEventSink()

    # Apply Decrease SPD (1) to Mikage before any ticks.
    mikage = next(a for a in actors if a.name == "Mikage")
    mikage.effects.append(Effect(kind=EffectKind.DECREASE_SPD, turns_remaining=1, magnitude=0.30))

    # Run until Mikage takes her first turn; at that end-of-turn, effect should expire.
    mikage_tick = None
    while sink.current_tick < 80:
        actor = step_tick(actors, event_sink=sink)
        if actor is not None and actor.name == "Mikage":
            mikage_tick = sink.current_tick
            break

    assert mikage_tick is not None, "Expected Mikage to take a turn within the tick budget."

    # Mikage should have no effects remaining after her TURN_END decrement.
    assert mikage.effects == []

    # Event proof: on Mikage's action tick, we should see EFFECT_EXPIRED then TURN_END (in that order).
    evts = [e for e in sink.events if e.tick == mikage_tick]
    types = [e.type for e in evts]
    assert EventType.TURN_END in types
    assert EventType.EFFECT_EXPIRED in types

    expired_i = types.index(EventType.EFFECT_EXPIRED)
    turn_end_i = types.index(EventType.TURN_END)
    assert expired_i < turn_end_i

    expired_evt = evts[expired_i]
    assert expired_evt.actor == "Mikage"
    assert expired_evt.data["effect"] == str(EffectKind.DECREASE_SPD)
