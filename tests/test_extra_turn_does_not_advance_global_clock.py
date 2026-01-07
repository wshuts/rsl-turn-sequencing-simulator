from __future__ import annotations

from rsl_turn_sequencing.engine import step_tick
from rsl_turn_sequencing.event_sink import InMemoryEventSink
from rsl_turn_sequencing.models import Actor


def test_extra_turn_does_not_advance_global_battle_clock() -> None:
    """An extra turn must not advance the global battle clock.

    In this simulator, the EventSink tick counter is the observable proxy for the
    "global battle clock". When an actor is granted an extra turn, that turn is
    taken immediately and must not consume an additional global tick.

    This test is intentionally narrow: it only asserts that the sink tick value
    does not change when resolving an extra turn.
    """

    # Two actors are sufficient; no boss mechanics required.
    actor = Actor(name="Actor", speed=100.0)
    other = Actor(name="Other", speed=200.0)

    sink = InMemoryEventSink()

    # Establish a baseline tick value by running a normal tick.
    step_tick([actor, other], event_sink=sink)
    tick_before_extra_turn = sink.current_tick

    # Now grant an extra turn and resolve it.
    actor.extra_turns = 1
    step_tick([actor, other], event_sink=sink)

    # Contract: the global clock must not advance due to an extra turn.
    assert sink.current_tick == tick_before_extra_turn
