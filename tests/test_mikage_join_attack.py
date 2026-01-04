from __future__ import annotations

from rsl_turn_sequencing.engine import step_tick
from rsl_turn_sequencing.event_sink import InMemoryEventSink
from rsl_turn_sequencing.events import EventType
from rsl_turn_sequencing.models import Actor


def test_mikage_a1_has_no_join_attack_when_no_shadowkin_allies_present() -> None:
    """RED test for faction-gated join attacks (Mikage A1).

    Intent:
    - When Mikage uses her A1, allies may join the attack depending on faction.
    - In a composition with *no Shadowkin allies*, no one should join.

    This test is purely about *event semantics* (observability), not damage/shield math.

    NOTE: The current baseline does not yet model skills/join attacks, so this test
    intentionally fails until that feature is implemented.
    """

    # Team slot order (strategic): Mikage, Mithrala, Martyr, Tomblord, Coldheart
    mikage = Actor(name="Mikage", speed=400)
    mithrala = Actor(name="Mithrala", speed=260)
    martyr = Actor(name="Martyr", speed=250)
    tomblord = Actor(name="Tomblord", speed=240)
    coldheart = Actor(name="Coldheart", speed=230)

    # Boss included so future shield/join-attack interactions have an anchor.
    boss = Actor(name="Boss", speed=100, is_boss=True)

    actors = [mikage, mithrala, martyr, tomblord, coldheart, boss]

    # Factions are currently modeled as optional metadata. We attach them dynamically.
    # Crucially: *no Shadowkin allies* besides Mikage herself.
    mikage.faction = "Shadowkin"
    mithrala.faction = "Lizardmen"
    martyr.faction = "Sacred Order"
    tomblord.faction = "Undead Hordes"
    coldheart.faction = "Dark Elves"
    boss.faction = "Demonspawn"

    sink = InMemoryEventSink()

    mikage_turn_start = None
    for _ in range(10):
        step_tick(actors, event_sink=sink)
        tick = sink.current_tick
        tick_events = [e for e in sink.events if e.tick == tick]
        mikage_turn_start = next(
            (e for e in tick_events if e.type == EventType.TURN_START and e.actor == "Mikage"),
            None,
        )
        if mikage_turn_start is not None:
            break

    assert mikage_turn_start is not None, "expected Mikage to take a turn within 10 ticks"

    # New observability contract (to be implemented): TURN_START for Mikage should include
    # a join-attack evaluation result for her A1.
    assert "join_attack_joiners" in mikage_turn_start.data
    assert mikage_turn_start.data["join_attack_joiners"] == []
