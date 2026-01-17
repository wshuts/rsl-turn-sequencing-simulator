from __future__ import annotations

"""Slice D — D2: Success-path causal attribution (diagnostic only).

Contract:
  When an expiration-triggered mastery proc resolves successfully,
  the emitted MASTERY_PROC event MUST include causal metadata sufficient
  to explain why count == N.

Minimum locked fields (Slice D):
  - qualifying_expiration_count
  - resolution_phase
  - resolution_step

Non-goals:
  - Do not re-assert ordering (Slice C covers ordering).
  - Do not re-assert effect-plane math (other slices cover TM changes).
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
    path = tmpdir / "battle_spec_sliceD_success_metadata.json"
    path.write_text(json.dumps(battle_spec, indent=2), encoding="utf-8")
    return path


def test_sliceD_success_proc_includes_causal_metadata_fields() -> None:
    mikage = Actor(name="Mikage", speed=100.0)
    ally = Actor(name="Coldheart", speed=0.0)

    # Force Mikage to act deterministically.
    mikage.turn_meter = float(TM_GATE)
    ally.turn_meter = 0.0

    # ADR-001 alignment: expiration-triggered lookup uses consumed-so-far step (1-based).
    mikage.skill_sequence_cursor = 1

    # Arrange: Mikage has a Mikage-placed BUFF with duration=1.
    mikage.active_effects = [
        EffectInstance(
            instance_id="fx_mikage_self_sliceD_01",
            effect_id="increase_atk",
            effect_kind="BUFF",
            placed_by="Mikage",
            duration=1,
        )
    ]

    # Build requester from canonical battle spec shape.
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

    procs = [e for e in sink.events if e.type == EventType.MASTERY_PROC]
    assert procs, "Expected a MASTERY_PROC event to be emitted."

    proc = procs[0]

    assert proc.data.get("holder") == "Mikage"
    assert proc.data.get("mastery") == "rapid_response"
    assert proc.data.get("count") == 1

    # Slice D: causal metadata (success path)
    assert proc.data.get("qualifying_expiration_count") == 1
    assert proc.data.get("resolution_phase") == str(EventType.TURN_END)
    assert proc.data.get("resolution_step") == 1

    # Sanity: the diagnostic count explains the emitted count.
    assert proc.data.get("qualifying_expiration_count") == proc.data.get("count")
