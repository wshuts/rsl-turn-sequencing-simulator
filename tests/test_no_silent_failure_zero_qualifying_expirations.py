from __future__ import annotations

"""Slice D — Observability on guarded mastery proc resolution.

D4 — No Silent Failure Modes

If a mastery proc request exists for a (holder, step) in a resolution window,
resolution MUST result in exactly one of:
  - MASTERY_PROC
  - MASTERY_PROC_REJECTED

This test covers the case where a request exists but there are zero qualifying
expirations, which must NOT be silently dropped.
"""

import json
import tempfile
from pathlib import Path

from rsl_turn_sequencing.engine import TM_GATE, build_mastery_proc_requester_from_battle_path, step_tick
from rsl_turn_sequencing.event_sink import InMemoryEventSink
from rsl_turn_sequencing.events import EventType
from rsl_turn_sequencing.models import Actor
from tests._support.battle_spec_helpers import add_mastery_proc_request, find_champion


def _write_battle_spec(tmpdir: Path, battle_spec: dict) -> Path:
    path = tmpdir / "battle_spec_sliceD_D4.json"
    path.write_text(json.dumps(battle_spec, indent=2), encoding="utf-8")
    return path


def test_sliceD_D4_request_exists_zero_qualifying_expirations_emits_rejection() -> None:
    # Arrange: force Mikage to act deterministically, but with no expiring effects.
    mikage = Actor(name="Mikage", speed=100.0)
    ally = Actor(name="Coldheart", speed=0.0)

    mikage.turn_meter = float(TM_GATE)
    ally.turn_meter = 0.0

    # ADR-001: expiration-triggered lookup uses consumed-so-far step (1-based).
    mikage.skill_sequence_cursor = 1

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
        count=1,
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
    assert procs == [], "Expected no MASTERY_PROC when there are zero qualifying expirations."

    # Assert: rejection is emitted (no silent drop).
    rejected = [e for e in sink.events if e.type == EventType.MASTERY_PROC_REJECTED]
    assert rejected, "Expected MASTERY_PROC_REJECTED when a request exists but Q=0."

    matching = [
        e
        for e in rejected
        if e.data.get("holder") == "Mikage"
        and e.data.get("mastery") == "rapid_response"
        and e.data.get("requested_count") == 1
        and e.data.get("qualifying_count") == 0
        and e.data.get("skill_sequence_step") == 1
        and e.data.get("turn_counter") == 1
        and e.data.get("reason") == "no_qualifying_expirations"
    ]
    assert matching, "Expected rejection payload to include holder/mastery/requested_count/qualifying_count/step."
