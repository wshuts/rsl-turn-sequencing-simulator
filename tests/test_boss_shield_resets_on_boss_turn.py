from __future__ import annotations

from rsl_turn_sequencing.engine import step_tick
from rsl_turn_sequencing.event_sink import InMemoryEventSink
from rsl_turn_sequencing.events import EventType
from rsl_turn_sequencing.models import Actor


def test_boss_shield_resets_to_full_at_boss_turn_start() -> None:
    # Arrange: boss starts broken, but has a defined max shield.
    boss = Actor(name="Boss", speed=2000.0, is_boss=True, shield=0, shield_max=21)
    champ = Actor(name="A", speed=1.0)

    actors = [champ, boss]
    sink = InMemoryEventSink()

    # Act: advance until boss is selected to act and TURN_START is emitted for boss.
    boss_turn_start = None
    for _ in range(5):
        step_tick(actors, event_sink=sink)
        tick = sink.current_tick
        tick_events = [e for e in sink.events if e.tick == tick]
        boss_turn_start = next(
            (
                e
                for e in tick_events
                if e.type == EventType.TURN_START and e.actor == "Boss"
            ),
            None,
        )
        if boss_turn_start is not None:
            break

    assert boss_turn_start is not None, "expected Boss to take a turn within 5 ticks"

    # Assert: reset happens before TURN_START observability emission.
    assert boss_turn_start.data["boss_shield_value"] == 21
    assert boss_turn_start.data["boss_shield_status"] == "UP"
