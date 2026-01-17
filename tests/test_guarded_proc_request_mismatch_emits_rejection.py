from __future__ import annotations

"""Slice B — Guarded deterministic mastery proc resolution on buff expiration.

We validate that a user-declared deterministic proc request matches the number of
qualifying expirations Q observed for the holder at that step.

Failure surface (Option B):
  - emit MASTERY_PROC_REJECTED
  - do NOT emit MASTERY_PROC
"""

import json
import tempfile
from pathlib import Path

from rsl_turn_sequencing.engine import TM_GATE, build_mastery_proc_requester_from_battle_path, step_tick
from rsl_turn_sequencing.event_sink import InMemoryEventSink
from rsl_turn_sequencing.events import EventType
from rsl_turn_sequencing.models import Actor, EffectInstance
from tests._support.battle_spec_helpers import add_mastery_proc_request, find_champion


def _write_battle_spec(tmpdir: Path, battle_spec: dict) -> Path:
    path = tmpdir / "battle_spec_sliceB.json"
    path.write_text(json.dumps(battle_spec, indent=2), encoding="utf-8")
    return path


def test_sliceB_mismatch_requested_count_emits_mastery_proc_rejected() -> None:
    mikage = Actor(name="Mikage", speed=100.0)
    ally = Actor(name="Coldheart", speed=0.0)

    # Force Mikage to act deterministically.
    mikage.turn_meter = float(TM_GATE)
    ally.turn_meter = 0.0

    # ADR-001: expiration-triggered lookup uses Mikage.skill_sequence_cursor as consumed-so-far step (1-based).
    mikage.skill_sequence_cursor = 1

    # Arrange: exactly one qualifying expiration will occur.
    mikage.active_effects = [
        EffectInstance(
            instance_id="fx_mikage_self_mismatch_01",
            effect_id="increase_atk",
            effect_kind="BUFF",
            placed_by="Mikage",
            duration=1,
        )
    ]

    battle_spec = {
        "boss": {"name": "Boss", "speed": 1500},
        "champions": [
            {"slot": 1, "name": "Mikage", "speed": 100.0},
            {"slot": 2, "name": "Coldheart", "speed": 0.0},
        ],
        "options": {"sequence_policy": "error_if_exhausted"},
    }

    mikage_spec = find_champion(battle_spec, name="Mikage")
    add_mastery_proc_request(
        mikage_spec,
        step=1,
        holder="Mikage",
        mastery="rapid_response",
        count=2,  # mismatch: Q will be 1
    )

    with tempfile.TemporaryDirectory() as td:
        battle_path = _write_battle_spec(Path(td), battle_spec)
        mastery_proc_requester = build_mastery_proc_requester_from_battle_path(battle_path)
        assert mastery_proc_requester is not None

        sink = InMemoryEventSink()
        step_tick(
            [mikage, ally],
            event_sink=sink,
            mastery_proc_requester=mastery_proc_requester,
        )

    # Assert: no proc was emitted.
    procs = [e for e in sink.events if e.type == EventType.MASTERY_PROC]
    assert procs == [], "Expected no MASTERY_PROC when request count mismatches Q."

    # Assert: rejection event emitted with deterministic payload.
    rejected = [e for e in sink.events if e.type == EventType.MASTERY_PROC_REJECTED]
    assert rejected, "Expected MASTERY_PROC_REJECTED when request count mismatches Q."

    matching = [
        e
        for e in rejected
        if e.data.get("holder") == "Mikage"
        and e.data.get("mastery") == "rapid_response"
        and e.data.get("requested_count") == 2
        and e.data.get("qualifying_count") == 1
        and e.data.get("skill_sequence_step") == 1
        and e.data.get("turn_counter") == 1
        and e.data.get("reason") == "requested_count_mismatch"
    ]
    assert matching, "Expected rejection payload to include holder/mastery/requested_count/qualifying_count/step."

    # Ordering: the expiration should precede the rejection for this step.
    idx_expired = next(
        i
        for i, e in enumerate(sink.events)
        if e.type == EventType.EFFECT_EXPIRED and e.data.get("instance_id") == "fx_mikage_self_mismatch_01"
    )
    idx_rejected = next(i for i, e in enumerate(sink.events) if e.type == EventType.MASTERY_PROC_REJECTED)
    assert idx_expired < idx_rejected
