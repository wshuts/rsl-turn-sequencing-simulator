from __future__ import annotations

from rsl_turn_sequencing.engine import step_tick
from rsl_turn_sequencing.event_sink import InMemoryEventSink
from rsl_turn_sequencing.events import EventType
from rsl_turn_sequencing.models import Actor


def test_faultless_defense_reflect_causes_single_shield_hit() -> None:
    """Acceptance #3:
    Faultless Defense reflect produces exactly one shield hit
    during the boss's turn.

    Scenario:
      - Boss shield starts at N
      - Boss takes a turn
      - A reflected hit occurs (deterministic)
      - Shield POST = N - 1

    Notes:
      - Damage amount ignored
      - No ally ordering
      - No real targeting logic
    """

    # Arrange
    shield_start = 10

    boss = Actor(
        name="Fire Knight",
        speed=2000.0,
        is_boss=True,
        shield=shield_start,
        shield_max=shield_start,
    )

    martyr = Actor(
        name="Martyr",
        speed=1.0,
        blessings={
            "faultless_defense": {"rank": 4}
        },
    )

    actors = [boss, martyr]
    sink = InMemoryEventSink()

    # Act
    # Deterministic injection: one reflected hit during boss turn
    step_tick(
        actors,
        event_sink=sink,
        hit_counts_by_actor={
            "REFLECT": 1
        },
    )

    # Assert
    boss_turn_end = next(
        e
        for e in reversed(sink.events)
        if e.type == EventType.TURN_END and e.actor == boss.name
    )

    assert boss_turn_end.data["boss_shield_value"] == shield_start - 1
    assert boss_turn_end.data["boss_shield_status"] == "UP"
