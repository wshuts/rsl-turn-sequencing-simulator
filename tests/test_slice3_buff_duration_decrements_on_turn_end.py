from rsl_turn_sequencing.engine import TM_GATE, step_tick
from rsl_turn_sequencing.models import Actor
from rsl_turn_sequencing.skill_buffs import apply_skill_buffs


def test_slice3_buff_duration_decrements_on_buff_owner_turn_end_only() -> None:
    # Arrange: Mikage, one ally, one boss
    mikage = Actor(name="Mikage", speed=200.0)
    ally = Actor(name="Martyr", speed=0.0)
    boss = Actor(name="Fire Knight", speed=0.0, is_boss=True)

    # Seed Slice 2 buffs (duration=2) onto all allies (including Mikage).
    mikage.skill_sequence_cursor = 3
    apply_skill_buffs(actors=[mikage, ally, boss], actor_name="Mikage", skill_id="B_A3")

    assert [fx.duration for fx in mikage.active_effects] == [2, 2]
    assert [fx.duration for fx in ally.active_effects] == [2, 2]

    # Force Mikage to take the next turn.
    mikage.turn_meter = float(TM_GATE)
    ally.turn_meter = 0.0
    boss.turn_meter = 0.0

    # Act: advance exactly one step where Mikage wins and completes TURN_END.
    winner = step_tick([mikage, ally, boss])

    # Assert: only the acting actor's BUFF durations decremented.
    assert winner is mikage
    assert [fx.duration for fx in mikage.active_effects] == [1, 1]
    assert [fx.duration for fx in ally.active_effects] == [2, 2]
