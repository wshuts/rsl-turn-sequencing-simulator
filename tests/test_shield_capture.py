from rsl_turn_sequencing.engine import step_tick
from rsl_turn_sequencing.event_sink import InMemoryEventSink
from rsl_turn_sequencing.events import EventType
from rsl_turn_sequencing.models import Actor


def test_turn_start_and_end_emit_boss_shield_snapshot_when_boss_present():
    # Use high speeds so we get an action quickly without many ticks.
    boss = Actor("Boss", 900.0, shield=21, is_boss=True)
    a1 = Actor("A1", 1000.0)
    actors = [a1, boss]

    sink = InMemoryEventSink()

    # Tick 1: fill only (no one crosses gate yet at ~1000)
    step_tick(actors, event_sink=sink)
    assert not any(e.type == EventType.TURN_START for e in sink.events)

    # Tick 2: A1 crosses gate and takes a turn.
    step_tick(actors, event_sink=sink)

    turn_start = [e for e in sink.events if e.type == EventType.TURN_START][-1]
    turn_end = [e for e in sink.events if e.type == EventType.TURN_END][-1]

    assert turn_start.data["boss_shield_value"] == 21
    assert turn_start.data["boss_shield_status"] == "UP"
    assert turn_end.data["boss_shield_value"] == 21
    assert turn_end.data["boss_shield_status"] == "UP"


def test_shield_status_reflects_break_between_turns():
    boss = Actor("Boss", 900.0, shield=21, is_boss=True)
    a1 = Actor("A1", 1000.0)
    actors = [a1, boss]
    sink = InMemoryEventSink()

    # Get one action (Tick 2).
    step_tick(actors, event_sink=sink)
    step_tick(actors, event_sink=sink)

    # "Break" the shield externally (combat not implemented yet).
    boss.shield = 0

    # Tick 3: fill only, Tick 4: A1 acts again.
    step_tick(actors, event_sink=sink)
    step_tick(actors, event_sink=sink)

    # The most recent TURN_START/END should report BROKEN.
    turn_start = [e for e in sink.events if e.type == EventType.TURN_START][-1]
    turn_end = [e for e in sink.events if e.type == EventType.TURN_END][-1]

    assert turn_start.data["boss_shield_value"] == 0
    assert turn_start.data["boss_shield_status"] == "BROKEN"
    assert turn_end.data["boss_shield_value"] == 0
    assert turn_end.data["boss_shield_status"] == "BROKEN"
