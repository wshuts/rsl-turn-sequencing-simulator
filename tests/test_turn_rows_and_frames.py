from rsl_turn_sequencing.engine import step_tick
from rsl_turn_sequencing.event_sink import InMemoryEventSink
from rsl_turn_sequencing.models import Actor
from rsl_turn_sequencing.reporting import (
    derive_turn_rows,
    group_rows_into_boss_frames,
)


def test_turn_rows_capture_pre_and_post_shield():
    boss = Actor("Boss", 900.0, shield=21, is_boss=True)
    a1 = Actor("A1", 1000.0)
    actors = [a1, boss]

    sink = InMemoryEventSink()

    # Produce one full A1 turn
    step_tick(actors, event_sink=sink)
    step_tick(actors, event_sink=sink)

    rows = derive_turn_rows(sink.events)
    row = rows[-1]

    assert row.pre_shield.value == 21
    assert row.pre_shield.status == "UP"
    assert row.post_shield.value == 21
    assert row.post_shield.status == "UP"


def test_rows_grouped_into_boss_frames_with_boss_last():
    boss = Actor("Boss", 300.0, shield=10, is_boss=True)
    a1 = Actor("A1", 500.0)
    a2 = Actor("A2", 450.0)
    actors = [a1, a2, boss]

    sink = InMemoryEventSink()

    # Run enough ticks to complete at least one boss turn
    for _ in range(20):
        step_tick(actors, event_sink=sink)

    rows = derive_turn_rows(sink.events)
    frames = group_rows_into_boss_frames(rows, boss_actor="Boss")

    assert len(frames) >= 1

    frame = frames[0]
    assert frame.rows[-1].actor == "Boss"
