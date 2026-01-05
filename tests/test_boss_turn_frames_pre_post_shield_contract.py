from __future__ import annotations

from rsl_turn_sequencing.engine import step_tick
from rsl_turn_sequencing.event_sink import InMemoryEventSink
from rsl_turn_sequencing.models import Actor
from rsl_turn_sequencing.reporting import derive_turn_rows, group_rows_into_boss_frames


def test_boss_turn_frame_has_rows_with_pre_post_shield_and_closes_on_boss_turn_end() -> None:
    """
    Acceptance (Boss Turn Frames):
      - derive TurnRows (TURN_START -> TURN_END) with PRE/POST shield snapshots
      - group TurnRows into Boss Turn Frames (frame ends on boss TURN_END)
      - boss TURN_START resets shield to shield_max and appears in boss row PRE
    """

    # Arrange: predictable 2-tick sequence with TM_GATE=1430:
    #   tick1: A1 TM=2000, Boss TM=1500 => A1 acts
    #   tick2: A1 TM=2000, Boss TM=3000 => Boss acts (frame closes)
    shield_start = 21

    boss = Actor(name="Boss", speed=1500.0, shield=shield_start, shield_max=shield_start, is_boss=True)
    a1 = Actor(name="A1", speed=2000.0)

    actors = [a1, boss]
    sink = InMemoryEventSink()

    # Act: tick1 A1 acts and we inject 3 hits against the boss shield
    step_tick(actors, event_sink=sink, hit_counts_by_actor={"A1": 3})

    # Act: tick2 Boss acts (no hits injected)
    step_tick(actors, event_sink=sink, hit_counts_by_actor={})

    # Derive rows and group into boss frames
    rows = derive_turn_rows(sink.events)
    frames = group_rows_into_boss_frames(rows, boss_actor="Boss")

    # Assert: exactly one complete boss frame captured
    assert len(frames) == 1
    frame = frames[0]

    # Frame must end with boss row
    assert frame.rows[-1].actor == "Boss"

    # Frame should have two rows: A1 then Boss
    assert [r.actor for r in frame.rows] == ["A1", "Boss"]

    a1_row = frame.rows[0]
    boss_row = frame.rows[1]

    # A1 row: PRE shield is starting shield, POST reflects injected hits
    assert a1_row.pre_shield is not None
    assert a1_row.post_shield is not None
    assert a1_row.pre_shield.value == shield_start
    assert a1_row.pre_shield.status == "UP"
    assert a1_row.post_shield.value == shield_start - 3
    assert a1_row.post_shield.status == "UP"

    # Boss row: PRE shield reflects reset to shield_max at boss TURN_START
    assert boss_row.pre_shield is not None
    assert boss_row.post_shield is not None
    assert boss_row.pre_shield.value == shield_start
    assert boss_row.pre_shield.status == "UP"

    # No hits during boss turn in this scenario
    assert boss_row.post_shield.value == shield_start
    assert boss_row.post_shield.status == "UP"
