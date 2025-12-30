from rsl_turn_sequencing.engine import step_tick
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


def test_no_actor_before_threshold():
    actors = make_actors()

    # Advance 4 ticks — nobody should act yet
    for _ in range(4):
        actor = step_tick(actors)
        assert actor is None


def test_mikage_acts_on_tick_5():
    actors = make_actors()

    actor = None
    for _ in range(5):
        actor = step_tick(actors)

    assert actor is not None
    assert actor.name == "Mikage"


def test_sequence_through_tick_10_matches_tick_sheet():
    """
    Validates the known acting order derived from the Tick sheet inputs
    (TM gate = 1430.0; speeds: 340/282/270/265/252/250) under the
    "one action per tick" foundation rule.

    Expected:
      Tick 5  -> Mikage
      Tick 6  -> Mithrala
      Tick 7  -> Tomblord
      Tick 8  -> Coldheart
      Tick 9  -> Martyr
      Tick 10 -> Boss
    """
    actors = make_actors()

    actions = []
    for tick in range(1, 11):
        actor = step_tick(actors)
        if actor is not None:
            actions.append((tick, actor.name))

    assert actions == [
        (5, "Mikage"),
        (6, "Mithrala"),
        (7, "Tomblord"),
        (8, "Coldheart"),
        (9, "Martyr"),
        (10, "Boss"),
    ]


def test_decrease_speed_multiplier_delays_turn_gate_crossing():
    """
    If Mikage is under a -30% SPD effect (multiplier 0.7), she should NOT
    reach the TM gate on tick 5 anymore (340 * 0.7 * 5 = 1190 < 1430).
    The first action should occur on tick 6 (Mithrala), matching the
    gate-then-tie-break model.
    """
    actors = make_actors()

    # Apply Decrease SPD to Mikage only
    for a in actors:
        if a.name == "Mikage":
            a.speed_multiplier = 0.7
            break

    # Tick 1-5: nobody acts
    actor = None
    for _ in range(5):
        actor = step_tick(actors)
    assert actor is None

    # Tick 6: Mithrala is now the first to act
    actor = step_tick(actors)
    assert actor is not None
    assert actor.name == "Mithrala"
