from rsl_turn_sequencing.effects import Effect, EffectKind
from rsl_turn_sequencing.engine import step_tick
from rsl_turn_sequencing.event_sink import InMemoryEventSink
from rsl_turn_sequencing.events import EventType
from rsl_turn_sequencing.models import Actor


def advance_until_turn(actors: list[Actor], target_name: str, sink: InMemoryEventSink) -> int:
    """Advance simulation until the named actor takes a turn; return the tick."""
    while sink.current_tick < 200:
        winner = step_tick(actors, event_sink=sink)
        if winner is not None and winner.name == target_name:
            return sink.current_tick
    raise AssertionError(f"{target_name} never took a turn")


def events_at_tick(sink: InMemoryEventSink, tick: int):
    return [e for e in sink.events if e.tick == tick]


def test_poison_triggers_and_decrements_at_turn_start_and_works_on_extra_turns():
    """
    A2: Poison is the canonical TURN_START-triggered effect.

    Locked semantics:
      - Trigger: TURN_START
      - Duration decrement: TURN_START (Poison special case)
      - Extra turns: do NOT perform meter fill, but still fire TURN_START triggers
    """
    a = Actor("A", 340.0, max_hp=1000.0, hp=1000.0)
    b = Actor("B", 100.0, max_hp=1000.0, hp=1000.0)
    actors = [a, b]

    # Poison for 2 turns, flat 50 damage at TURN_START for test clarity.
    a.effects.append(Effect(kind=EffectKind.POISON, turns_remaining=2, magnitude=50.0))

    sink = InMemoryEventSink()

    # --- First A turn ---
    t1 = advance_until_turn(actors, "A", sink)
    assert a.hp == 950.0

    # On this tick, poison should have triggered between TURN_START and TURN_END.
    types = [e.type for e in events_at_tick(sink, t1)]
    assert EventType.TURN_START in types
    assert EventType.EFFECT_TRIGGERED in types
    assert EventType.TURN_END in types
    assert types.index(EventType.EFFECT_TRIGGERED) > types.index(EventType.TURN_START)
    assert types.index(EventType.EFFECT_TRIGGERED) < types.index(EventType.TURN_END)

    # Duration decrements at TURN_START, so after the turn resolves it should still be 1.
    assert a.effects[0].kind == EffectKind.POISON
    assert a.effects[0].turns_remaining == 1

    # --- Extra turn for A (no fill) ---
    b_tm_before = float(b.turn_meter)
    a.extra_turns = 1
    t2_winner = step_tick(actors, event_sink=sink)
    assert t2_winner is not None and t2_winner.name == "A"

    # No fill during extra turn
    assert float(b.turn_meter) == b_tm_before

    # Poison triggers again on extra turn TURN_START
    assert a.hp == 900.0

    # After TURN_END, poison should expire (2 total triggers).
    assert a.effects == []

    # Event proof: on this tick we should see EFFECT_TRIGGERED and EFFECT_EXPIRED
    # BEFORE TURN_END, because Poison expires at TURN_START.
    t2 = sink.current_tick
    types2 = [e.type for e in events_at_tick(sink, t2)]
    assert EventType.TURN_START in types2
    assert EventType.EFFECT_TRIGGERED in types2
    assert EventType.TURN_END in types2
    assert EventType.EFFECT_EXPIRED in types2
    assert types2.index(EventType.EFFECT_EXPIRED) > types2.index(EventType.EFFECT_TRIGGERED)
    assert types2.index(EventType.EFFECT_EXPIRED) < types2.index(EventType.TURN_END)
