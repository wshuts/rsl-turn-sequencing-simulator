from __future__ import annotations

"""Slice C — Event ordering contract for expiration-triggered mastery procs.

Contract (within a single tick for a single acting actor):
  1) All qualifying EFFECT_EXPIRED events
  2) MASTERY_PROC (if requested and validated)
  3) TURN_END

This test specifically covers the mixed-source expiration case:
  - One expiration injected via the test seam
  - One expiration produced by engine-owned duration logic

The proc must be emitted only after *all* expirations are processed.
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
    path = tmpdir / "battle_spec_sliceC_ordering.json"
    path.write_text(json.dumps(battle_spec, indent=2), encoding="utf-8")
    return path


def test_sliceC_orders_expiration_then_mastery_proc_then_turn_end() -> None:
    # Arrange actors: force Mikage to act deterministically.
    mikage = Actor(name="Mikage", speed=100.0)
    ally = Actor(name="Coldheart", speed=0.0)
    mikage.turn_meter = float(TM_GATE)
    ally.turn_meter = 0.0

    # ADR-001: consumed-so-far step (1-based) is sourced from skill_sequence_cursor.
    mikage.skill_sequence_cursor = 1

    # Two qualifying BUFFs placed by Mikage. We'll inject-expire fx1 and let
    # engine-owned duration logic expire fx2 at TURN_END.
    mikage.active_effects = [
        EffectInstance(
            instance_id="fx1",
            effect_id="increase_atk",
            effect_kind="BUFF",
            placed_by="Mikage",
            duration=1,
        ),
        EffectInstance(
            instance_id="fx2",
            effect_id="shield",
            effect_kind="BUFF",
            placed_by="Mikage",
            duration=1,
        ),
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
        count=2,  # Q will be 2 (fx1 injected + fx2 duration expiry)
    )

    def injector(ctx: dict) -> list[dict]:
        # The engine calls the injector at both TURN_START and TURN_END.
        # We want to expire fx1 immediately before TURN_END only.
        if str(ctx.get("phase")) != str(EventType.TURN_END):
            return []

        return [{"type": "expire_effect", "instance_id": "fx1", "reason": "injected"}]

    with tempfile.TemporaryDirectory() as td:
        battle_path = _write_battle_spec(Path(td), battle_spec)
        requester = build_mastery_proc_requester_from_battle_path(battle_path)
        assert requester is not None

        sink = InMemoryEventSink()
        step_tick(
            [mikage, ally],
            event_sink=sink,
            expiration_injector=injector,
            mastery_proc_requester=requester,
        )

    # Assert ordering: all EFFECT_EXPIRED happen before MASTERY_PROC, and
    # MASTERY_PROC happens before TURN_END.
    idxs_expired = [i for i, e in enumerate(sink.events) if e.type == EventType.EFFECT_EXPIRED]
    assert idxs_expired, "Expected at least one EFFECT_EXPIRED event in this step."

    idx_proc = next(i for i, e in enumerate(sink.events) if e.type == EventType.MASTERY_PROC)
    idx_turn_end = next(i for i, e in enumerate(sink.events) if e.type == EventType.TURN_END)

    assert max(idxs_expired) < idx_proc, "Expected MASTERY_PROC after all EFFECT_EXPIRED events."
    assert idx_proc < idx_turn_end, "Expected TURN_END to be the final ordering boundary."

    # And confirm the proc count aligns with the two expirations.
    proc = next(e for e in sink.events if e.type == EventType.MASTERY_PROC)
    assert proc.data.get("holder") == "Mikage"
    assert proc.data.get("mastery") == "rapid_response"
    assert proc.data.get("count") == 2
