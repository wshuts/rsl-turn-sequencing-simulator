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
    Observer semantics we are locking in:
      - Decrease SPD is "baggage": it affects turn-meter fill while present.
      - Duration decrements at TURN_END of the affected actor.
      - duration=1 expires after exactly one of that actor's turns completes.
    """
    actors = make_actors()
    sink = InMemoryEventSink()

    # Apply Decrease SPD (1) to Mikage before any ticks.
    for a in actors:
        if a.name == "Mikage":
            a.effects.append(Effect(kind=EffectKind.DECREASE_SPD, turns_remaining=1, magnitude=0.30))
            break

    # With -30% SPD, Mikage should NOT be the first actor to act.
    # First action should occur on tick 6 (Mithrala), matching the earlier multiplier test behavior.
    first_actor = None
    for _ in range(6):
        first_actor = step_tick(actors, event_sink=sink)
    assert first_actor is not None
    assert first_actor.name == "Mithrala"

    # Continue until Mikage takes her first turn; at that TURN_END, effect should expire.
    mikage_tick = None
    while sink.current_tick < 50:
        actor = step_tick(actors, event_sink=sink)
        if actor is not None and actor.name == "Mikage":
            mikage_tick = sink.current_tick
            break

    assert mikage_tick is not None

    # Mikage should have no effects remaining after her TURN_END decrement.
    mikage = next(a for a in actors if a.name == "Mikage")
    assert mikage.effects == []

    # Event proof: on Mikage's action tick, we should see TURN_END then EFFECT_EXPIRED (in that order).
    evts = [e for e in sink.events if e.tick == mikage_tick]
    types = [e.type for e in evts]
    assert EventType.TURN_END in types
    assert EventType.EFFECT_EXPIRED in types

    turn_end_i = types.index(EventType.TURN_END)
    expired_i = types.index(EventType.EFFECT_EXPIRED)
    assert expired_i > turn_end_i

    expired_evt = evts[expired_i]
    assert expired_evt.actor == "Mikage"
    assert expired_evt.data["effect"] == str(EffectKind.DECREASE_SPD)
