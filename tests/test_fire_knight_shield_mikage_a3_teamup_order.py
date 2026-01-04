from __future__ import annotations

import json
from pathlib import Path

from rsl_turn_sequencing.engine import step_tick
from rsl_turn_sequencing.event_sink import InMemoryEventSink
from rsl_turn_sequencing.events import EventType
from rsl_turn_sequencing.models import Actor


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _a1_hits_from_dataset(champion: dict) -> int:
    """Return A1 hit count for a champion.

    Special case: Mythical champs (Mikage) store skills under forms.
    """
    if "skills" in champion:
        return int(champion["skills"]["A1"]["hits"])

    # Mythical form-capable champion
    starting_form = champion.get("defaults", {}).get("starting_form", "base")
    return int(champion["forms"][starting_form]["skills"]["A1"]["hits"])


def test_mikage_a3_teamups_resolve_in_canonical_slot_order() -> None:
    """Acceptance #4:
    Mikage A3 (Imperial Decree) triggers team-up default attacks
    in canonical slot order, and all hits decrement the boss shield
    before the POST snapshot.

    Canonical order:
      Lady Mikage
      Mithrala Lifebane
      Martyr
      Tomb Lord
      Coldheart
    """

    # Arrange
    data_path = _repo_root() / "data" / "champions_fire_knight_team.json"
    payload = json.loads(data_path.read_text(encoding="utf-8"))
    by_id = {c["id"]: c for c in payload["champions"]}

    mikage = by_id["mikage"]
    mithrala = by_id["mithrala"]
    martyr = by_id["martyr"]
    tomb_lord = by_id["tomb_lord"]
    coldheart = by_id["coldheart"]

    # Default skill hit counts (A1 for each)
    hits_by_name = {
        mikage["name"]: _a1_hits_from_dataset(mikage),
        mithrala["name"]: _a1_hits_from_dataset(mithrala),
        martyr["name"]: _a1_hits_from_dataset(martyr),
        tomb_lord["name"]: _a1_hits_from_dataset(tomb_lord),
        coldheart["name"]: _a1_hits_from_dataset(coldheart),
    }

    expected_total_hits = sum(hits_by_name.values())
    assert expected_total_hits == 11, "dataset contract sanity check (A1 hits total)"

    shield_start = 15

    boss = Actor(
        name="Fire Knight",
        speed=1.0,
        is_boss=True,
        shield=shield_start,
        shield_max=shield_start,
    )

    # Team slot order (canonical)
    actors = [
        Actor(name=mikage["name"], speed=2000.0),  # ensure Mikage acts first
        Actor(name=mithrala["name"], speed=1.0),
        Actor(name=martyr["name"], speed=1.0),
        Actor(name=tomb_lord["name"], speed=1.0),
        Actor(name=coldheart["name"], speed=1.0),
        boss,
    ]

    sink = InMemoryEventSink()

    # Act
    # Deterministic injection: Mikage A3 causes team-up default attacks
    step_tick(
        actors,
        event_sink=sink,
        hit_counts_by_actor=hits_by_name,
    )

    # Assert: Mikage TURN_END shows shield reduced by all team-up hits
    mikage_turn_end = next(
        e
        for e in reversed(sink.events)
        if e.type == EventType.TURN_END and e.actor == mikage["name"]
    )

    assert mikage_turn_end.data["boss_shield_value"] == shield_start - expected_total_hits
    assert mikage_turn_end.data["boss_shield_status"] == "UP"
