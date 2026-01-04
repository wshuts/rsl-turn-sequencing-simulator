from __future__ import annotations

import json
from pathlib import Path

from rsl_turn_sequencing.engine import step_tick
from rsl_turn_sequencing.event_sink import InMemoryEventSink
from rsl_turn_sequencing.events import EventType
from rsl_turn_sequencing.models import Actor


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_shield_decrements_by_multihit_count_from_committed_dataset() -> None:
    """Acceptance slice: consume the committed FK team JSON and prove multi-hit decrements shield.

    Scenario:
      - Boss shield starts at N
      - Coldheart uses A1 (4 hits, per dataset)
      - TURN_END snapshot reports N-4

    Notes:
      - No damage model
      - No ally attacks / counters / blessings in this slice
    """

    # Arrange
    data_path = _repo_root() / "data" / "champions_fire_knight_team.json"
    payload = json.loads(data_path.read_text(encoding="utf-8"))
    coldheart = next(c for c in payload["champions"] if c["id"] == "coldheart")
    hits = int(coldheart["skills"]["A1"]["hits"])
    assert hits == 4, "dataset contract: Coldheart A1 must be 4 hits"

    shield_start = 10
    boss = Actor(name="Fire Knight", speed=1.0, is_boss=True, shield=shield_start, shield_max=shield_start)
    ch = Actor(name=coldheart["name"], speed=2000.0)
    actors = [ch, boss]
    sink = InMemoryEventSink()

    # Act: advance until Coldheart takes a turn.
    # With speed=2000 and TM_GATE=1430, Coldheart should act on the first tick.
    step_tick(actors, event_sink=sink, hit_counts_by_actor={ch.name: hits})

    # Assert: the most recent Coldheart TURN_END reports shield reduced by 4.
    ch_turn_end = next(
        e
        for e in reversed(sink.events)
        if e.type == EventType.TURN_END and e.actor == ch.name
    )
    assert ch_turn_end.data["boss_shield_value"] == shield_start - hits
    assert ch_turn_end.data["boss_shield_status"] == "UP"
