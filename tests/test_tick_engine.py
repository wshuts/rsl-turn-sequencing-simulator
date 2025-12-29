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
