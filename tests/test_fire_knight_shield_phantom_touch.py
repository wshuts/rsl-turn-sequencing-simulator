from __future__ import annotations

import json
from pathlib import Path

from rsl_turn_sequencing.engine import step_tick
from rsl_turn_sequencing.event_sink import InMemoryEventSink
from rsl_turn_sequencing.events import EventType
from rsl_turn_sequencing.models import Actor


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_phantom_touch_adds_one_extra_shield_hit() -> None:
    """Acceptance #2:
    Multi-hit + Phantom Touch produces exactly one extra shield hit.

    Scenario:
      - Boss shield starts at N
      - Coldheart uses A1 (4 hits)
      - Phantom Touch fires once (deterministic)
      - Shield POST = N - 5

    Constraints:
      - Proc chance ignored
      - Cooldown-limited (no double fire)
      - No counters, no ally attacks
    """

    # Arrange
    data_path = _repo_root() / "data" / "champions_fire_knight_team.json"
    payload = json.loads(data_path.read_text(encoding="utf-8"))

    coldheart = next(c for c in payload["champions"] if c["id"] == "coldheart")
    base_hits = int(coldheart["skills"]["A1"]["hits"])
    assert base_hits == 4, "dataset contract: Coldheart A1 must be 4 hits"

    shield_start = 10

    boss = Actor(
        name="Fire Knight",
        speed=1.0,
        is_boss=True,
        shield=shield_start,
        shield_max=shield_start,
    )

    ch = Actor(
        name=coldheart["name"],
        speed=2000.0,
        blessings={"phantom_touch": {"cooldown": 1}},
    )

    actors = [ch, boss]
    sink = InMemoryEventSink()

    # Act
    step_tick(
        actors,
        event_sink=sink,
        hit_counts_by_actor={
            ch.name: base_hits + 1  # +1 from Phantom Touch
        },
    )

    # Assert
    ch_turn_end = next(
        e
        for e in reversed(sink.events)
        if e.type == EventType.TURN_END and e.actor == ch.name
    )

    assert ch_turn_end.data["boss_shield_value"] == shield_start - (base_hits + 1)
    assert ch_turn_end.data["boss_shield_status"] == "UP"
