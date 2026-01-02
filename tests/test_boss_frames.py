from rsl_turn_sequencing.boss_frames import group_events_into_boss_frames
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


def test_group_events_into_boss_frames_closes_on_boss_turn_end():
    actors = make_actors()
    sink = InMemoryEventSink()

    # Run enough ticks to guarantee multiple boss turns.
    for _ in range(50):
        step_tick(actors, event_sink=sink)

    boss_turn_ends = [e for e in sink.events if e.type == EventType.TURN_END and e.actor == "Boss"]
    assert len(boss_turn_ends) >= 2

    frames = group_events_into_boss_frames(sink.events, boss_actor="Boss")

    # One frame per completed boss turn.
    assert len(frames) == len(boss_turn_ends)

    # The boss TURN_END is always the last event in its frame.
    for frame in frames:
        assert frame.events[-1].type == EventType.TURN_END
        assert frame.events[-1].actor == "Boss"

    # Frames partition the event stream up to the last boss TURN_END (no gaps or reordering).
    last_boss_turn_end = boss_turn_ends[-1]
    cutoff = next(i for i, e in enumerate(sink.events) if e == last_boss_turn_end)

    flattened = [e for f in frames for e in f.events]
    assert flattened == sink.events[: cutoff + 1]
