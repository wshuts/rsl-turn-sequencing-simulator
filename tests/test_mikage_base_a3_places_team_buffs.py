from rsl_turn_sequencing.event_sink import InMemoryEventSink
from rsl_turn_sequencing.events import EventType
from rsl_turn_sequencing.models import Actor

from rsl_turn_sequencing.skill_buffs import apply_skill_buffs


def test_slice2_mikage_base_a3_places_increase_atk_and_cdmg_on_all_allies_for_2_turns() -> None:
    # Arrange: Mikage, one ally, one boss
    mikage = Actor(name="Mikage", speed=200.0)
    ally = Actor(name="Martyr", speed=180.0)
    boss = Actor(name="Fire Knight", speed=100.0, is_boss=True)

    # From the user's perspective, this is the 3rd entry in Mikage's skill sequence.
    # _consume_next_skill increments skill_sequence_cursor after consumption, so a value
    # of 3 indicates the just-consumed skill is the 3rd token.
    mikage.skill_sequence_cursor = 3

    sink = InMemoryEventSink()
    sink.start_tick()

    # Act
    apply_skill_buffs(
        actors=[mikage, ally, boss],
        actor_name="Mikage",
        skill_id="B_A3",
        event_sink=sink,
    )

    # Assert: buffs exist on all non-boss allies
    for target in (mikage, ally):
        effect_ids = [fx.effect_id for fx in target.active_effects]
        assert sorted(effect_ids) == ["increase_atk", "increase_c_dmg"]
        for fx in target.active_effects:
            assert fx.effect_kind == "BUFF"
            assert fx.placed_by == "Mikage"
            assert fx.duration == 2

    assert boss.active_effects == []

    # Assert: EFFECT_APPLIED emitted once per buff instance
    applied = [e for e in sink.events if e.type == EventType.EFFECT_APPLIED]
    assert len(applied) == 4

    for e in applied:
        assert e.actor == "Mikage"
        assert e.data.get("effect_kind") == "BUFF"
        assert e.data.get("placed_by") == "Mikage"
        assert e.data.get("duration") == 2
        assert e.data.get("source_skill_id") == "B_A3"
        assert e.data.get("source_sequence_index") == 3
        assert e.data.get("owner") in {"Mikage", "Martyr"}
        assert e.data.get("effect_id") in {"increase_atk", "increase_c_dmg"}
        instance_id = e.data.get("instance_id")
        assert isinstance(instance_id, str) and instance_id.startswith("fx_Mikage_B_A3_3_")
