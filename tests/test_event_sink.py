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


def test_event_order_on_first_action_tick():
    """
    Asserts causality ordering (not formatting/visuals):
      - Each tick emits TICK_START first.
      - On the first action tick (tick 5 baseline), we see:
          TICK_START -> FILL_COMPLETE -> WINNER_SELECTED -> RESET_APPLIED
      - Winner is Mikage on that first action tick.
    """
    actors = make_actors()
    sink = InMemoryEventSink()

    # Run through tick 5 (tick numbering owned by sink.start_tick()).
    for _ in range(5):
        step_tick(actors, event_sink=sink)

    tick5 = [e for e in sink.events if e.tick == 5]
    assert [e.type for e in tick5] == [
        EventType.TICK_START,
        EventType.FILL_COMPLETE,
        EventType.WINNER_SELECTED,
        EventType.RESET_APPLIED,
    ]

    winner_evt = tick5[2]
    assert winner_evt.actor == "Mikage"
    assert float(winner_evt.data["pre_reset_tm"]) > 0.0

    reset_evt = tick5[2]
    assert reset_evt.actor == "Mikage"
