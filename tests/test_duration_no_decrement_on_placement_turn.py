from rsl_turn_sequencing.engine import TM_GATE, step_tick
from rsl_turn_sequencing.models import Actor
from rsl_turn_sequencing.skill_buffs import apply_skill_buffs


def test_newly_applied_buffs_do_not_decrement_duration_on_the_same_turn_as_placement() -> None:
    """Slice: Duration semantics — no decrement on placement turn.

    Domain rule:
      If a BUFF is applied during an actor's turn, its duration must NOT decrement
      at that same TURN_END. The first eligible decrement is the next matching
      boundary after placement.

    This test forces Mikage to win a turn, applies B_A3 buffs DURING that turn
    (via hit_provider side-effect), and asserts Mikage's newly applied BUFF
    durations remain unchanged through that TURN_END.
    """
    # Arrange: Mikage, one ally, one boss
    mikage = Actor(name="Mikage", speed=200.0)
    ally = Actor(name="Martyr", speed=0.0)
    boss = Actor(name="Fire Knight", speed=0.0, is_boss=True)

    # Force Mikage to take the next turn.
    mikage.turn_meter = float(TM_GATE)
    ally.turn_meter = 0.0
    boss.turn_meter = 0.0

    # Apply buffs DURING Mikage's turn (after TURN_START, before TURN_END)
    def _provider(winner: str) -> dict[str, int]:
        if winner == "Mikage":
            # Mimic CLI behavior: skill has just been consumed, so cursor is 1-based.
            mikage.skill_sequence_cursor = 1
            apply_skill_buffs(actors=[mikage, ally, boss], actor_name="Mikage", skill_id="B_A3")
        return {}

    # Act: advance exactly one step where Mikage wins and completes TURN_END.
    winner = step_tick([mikage, ally, boss], hit_provider=_provider)

    # Assert: buffs were applied and did NOT decrement on the placement turn.
    assert winner is mikage
    assert [fx.duration for fx in mikage.active_effects] == [2, 2]

    # Also prove ally received the team buffs (and remains at full duration).
    assert [fx.duration for fx in ally.active_effects] == [2, 2]
