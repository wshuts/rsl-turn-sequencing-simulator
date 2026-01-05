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

    # Mythical form-capable champion (e.g., Lady Mikage)
    starting_form = champion.get("defaults", {}).get("starting_form", "base")
    return int(champion["forms"][starting_form]["skills"]["A1"]["hits"])


def test_composite_mikage_a3_teamups_plus_phantom_touch() -> None:
    """Acceptance #5 (Composite):
    Mikage A3 team-ups resolve in canonical slot order and Coldheart's
    Phantom Touch adds exactly +1 hit, all applied before POST snapshot.

    Composite turn model (deterministic injection):
      - Mikage A3 => team-up default attacks (A1) from:
          Lady Mikage, Mithrala Lifebane, Martyr, Tomb Lord, Coldheart
      - Coldheart A1 contributes its normal hits + 1 extra Phantom Touch hit

    Expected:
      shield_post = shield_start - (sum(teamup A1 hits) + 1)
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

    # Base A1 hits from dataset
    mikage_a1 = _a1_hits_from_dataset(mikage)
    mithrala_a1 = _a1_hits_from_dataset(mithrala)
    martyr_a1 = _a1_hits_from_dataset(martyr)
    tomb_lord_a1 = _a1_hits_from_dataset(tomb_lord)
    coldheart_a1 = _a1_hits_from_dataset(coldheart)

    assert coldheart_a1 == 4, "dataset contract: Coldheart A1 must be 4 hits"

    # Composite: team-ups + Phantom Touch (+1 to Coldheart's contribution)
    hits_by_name = {
        mikage["name"]: mikage_a1,
        mithrala["name"]: mithrala_a1,
        martyr["name"]: martyr_a1,
        tomb_lord["name"]: tomb_lord_a1,
        coldheart["name"]: coldheart_a1 + 1,  # +1 Phantom Touch (deterministic)
    }

    expected_total_hits = sum(hits_by_name.values())

    shield_start = 20

    boss = Actor(
        name="Fire Knight",
        speed=1.0,
        is_boss=True,
        shield=shield_start,
        shield_max=shield_start,
    )

    # Canonical team slot order
    actors = [
        Actor(name=mikage["name"], speed=2000.0),  # ensure Mikage acts first
        Actor(name=mithrala["name"], speed=1.0),
        Actor(name=martyr["name"], speed=1.0),
        Actor(name=tomb_lord["name"], speed=1.0),
        Actor(name=coldheart["name"], speed=1.0),
        boss,
    ]

    sink = InMemoryEventSink()

    # Act: deterministic injection of composite hits for Mikage's A3 turn
    step_tick(
        actors,
        event_sink=sink,
        hit_counts_by_actor=hits_by_name,
    )

    # Assert: Mikage TURN_END shows shield reduced by the composite total
    mikage_turn_end = next(
        e
        for e in reversed(sink.events)
        if e.type == EventType.TURN_END and e.actor == mikage["name"]
    )

    assert mikage_turn_end.data["boss_shield_value"] == shield_start - expected_total_hits
    assert mikage_turn_end.data["boss_shield_status"] == "UP"
