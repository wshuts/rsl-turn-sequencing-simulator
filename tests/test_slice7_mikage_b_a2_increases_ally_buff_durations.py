from rsl_turn_sequencing.event_sink import InMemoryEventSink
from rsl_turn_sequencing.events import EventType
from rsl_turn_sequencing.models import Actor
from rsl_turn_sequencing.skill_buffs import apply_skill_buffs


def test_slice7_mikage_b_a2_increases_ally_buff_durations_by_1() -> None:
    """Slice 7 (new): Mikage Base A2 increases ally BUFF durations by 1.

    Battle truth reference (champions_fire_knight_team.json):
      - "Decreases duration of enemy buffs by 1; ally debuffs by 1."
      - "Then increases duration of enemy debuffs by 1; ally buffs by 1."

    This slice locks only the ally-buff increment behavior, because it is
    required for CLI integration observability (duration changes).
    """

    # Arrange
    sink = InMemoryEventSink()
    sink.start_tick()

    mikage = Actor(name="Mikage", speed=200.0)
    ally = Actor(name="Martyr", speed=0.0)
    boss = Actor(name="Fire Knight", speed=0.0, is_boss=True)

    # Provide a stable turn counter for provider helpers.
    for a in (mikage, ally, boss):
        setattr(a, "_current_turn_counter", 1)

    # Seed Slice 2 buffs (duration=2) onto all allies (including Mikage).
    mikage.skill_sequence_cursor = 3
    apply_skill_buffs(
        actors=[mikage, ally, boss],
        actor_name="Mikage",
        skill_id="B_A3",
        event_sink=sink,
    )

    assert [fx.duration for fx in mikage.active_effects] == [2, 2]
    assert [fx.duration for fx in ally.active_effects] == [2, 2]

    # Act: Mikage uses Base A2 (B_A2), which should increase ally BUFF durations by 1.
    mikage.skill_sequence_cursor = 2
    apply_skill_buffs(
        actors=[mikage, ally, boss],
        actor_name="Mikage",
        skill_id="B_A2",
        event_sink=sink,
    )

    # Assert: all ally BUFFs gained +1 duration.
    assert [fx.duration for fx in mikage.active_effects] == [3, 3]
    assert [fx.duration for fx in ally.active_effects] == [3, 3]

    # And: at least one EFFECT_DURATION_CHANGED event was emitted.
    changed = [e for e in sink.events if e.type == EventType.EFFECT_DURATION_CHANGED]
    assert changed, "Expected at least one EFFECT_DURATION_CHANGED event from B_A2."
