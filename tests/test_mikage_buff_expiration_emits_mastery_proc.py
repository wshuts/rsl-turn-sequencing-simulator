from __future__ import annotations

"""
Slice 5 — Engine-owned BUFF expiration + user-declared proc request ⇒ MASTERY_PROC

Contract:
  When a BUFF placed by Mikage expires via ENGINE-owned duration semantics (TURN_END),
  and the user declares a deterministic mastery proc request for Mikage's
  *skill sequence step* (ADR-001, champion-scoped),
  the engine emits a MASTERY_PROC event with payload:
    { holder: "Mikage", mastery: "rapid_response", count: <n> }

Notes:
- This test intentionally does NOT assert turn meter changes (that belongs to Slice 6).
- This test MUST NOT use the injected expiration seam. Expiration must occur naturally
  via engine-owned duration decrement + expire at TURN_END.
- We remove the test-defined requester closure; the requester is built from battle spec JSON
  via build_mastery_proc_requester_from_battle_path, matching the demo battlespec shape.
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
    path = tmpdir / "battle_spec_slice5.json"
    path.write_text(json.dumps(battle_spec, indent=2), encoding="utf-8")
    return path


def test_slice5_engine_owned_mikage_buff_expiration_emits_mastery_proc_when_requested() -> None:
    mikage = Actor(name="Mikage", speed=100.0)
    ally = Actor(name="Coldheart", speed=0.0)

    # Force Mikage to act deterministically.
    mikage.turn_meter = float(TM_GATE)
    ally.turn_meter = 0.0

    # ADR-001 alignment:
    # Expiration-triggered proc lookup uses Mikage.skill_sequence_cursor (0-based),
    # interpreted as "skills consumed so far" (1-based step = cursor).
    # In unit tests we are not running the CLI skill-token provider, so we set this explicitly.
    mikage.skill_sequence_cursor = 1  # means Mikage has consumed 1 skill (step 1)

    # Arrange: Mikage has a Mikage-placed BUFF with duration=1.
    # Engine-owned decrement occurs at acting actor TURN_END (Slice 3),
    # and engine-owned expiration emits EFFECT_EXPIRED when duration reaches 0 (Slice 4).
    mikage.active_effects = [
        EffectInstance(
            instance_id="fx_mikage_self_01",
            effect_id="increase_atk",
            effect_kind="BUFF",
            placed_by="Mikage",
            duration=1,
        )
    ]

    # Build the mastery proc requester from a battle spec that uses the canonical
    # entity-scoped demo shape: champions[i].turn_overrides.proc_request.on_step[step].mastery_procs
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
        assert mastery_proc_requester is not None, "Expected requester to be constructed from battle spec."

        sink = InMemoryEventSink()

        # Act
        winner = step_tick(
            [mikage, ally],
            event_sink=sink,
            mastery_proc_requester=mastery_proc_requester,
        )

    assert winner is mikage

    # Assert: effect removed by engine-owned expiration.
    assert mikage.active_effects == []

    # Assert: EFFECT_EXPIRED emitted for the instance (Slice 4 payload shape).
    expired = [e for e in sink.events if e.type == EventType.EFFECT_EXPIRED]
    assert expired, "Expected at least one EFFECT_EXPIRED event (engine-owned expiration)."

    matching_expired = [
        e
        for e in expired
        if e.data.get("instance_id") == "fx_mikage_self_01"
        and e.data.get("effect_id") == "increase_atk"
        and e.data.get("effect_kind") == "BUFF"
        and e.data.get("owner") == "Mikage"
        and e.data.get("placed_by") == "Mikage"
        and e.data.get("duration") == 1
        and e.data.get("reason") == "duration_reached_zero"
        and e.data.get("phase") == str(EventType.TURN_END)
    ]
    assert matching_expired, (
        "Expected EFFECT_EXPIRED payload to include instance_id/effect_id/effect_kind/"
        "owner/placed_by/duration/reason/phase for engine-owned expiration."
    )

    # Assert: MASTERY_PROC emitted with requested payload.
    procs = [e for e in sink.events if e.type == EventType.MASTERY_PROC]
    assert procs, "Expected at least one MASTERY_PROC event."

    matching_procs = [
        e
        for e in procs
        if e.data.get("holder") == "Mikage"
        and e.data.get("mastery") == "rapid_response"
        and e.data.get("count") == 1
        and e.data.get("turn_counter") == 1  # legacy observability only
    ]
    assert matching_procs, "Expected Rapid Response proc payload holder/mastery/count/turn_counter to match."

    # Ordering contract: expiration should precede proc emission for this step.
    idx_expired = next(
        i
        for i, e in enumerate(sink.events)
        if e.type == EventType.EFFECT_EXPIRED and e.data.get("instance_id") == "fx_mikage_self_01"
    )
    idx_proc = next(
        i
        for i, e in enumerate(sink.events)
        if e.type == EventType.MASTERY_PROC and e.data.get("turn_counter") == 1
    )
    assert idx_expired < idx_proc, "Expected EFFECT_EXPIRED to be emitted before MASTERY_PROC for the same step."


def test_slice5_engine_owned_mikage_buff_expiration_does_not_emit_mastery_proc_without_request() -> None:
    mikage = Actor(name="Mikage", speed=100.0)
    ally = Actor(name="Coldheart", speed=0.0)

    mikage.turn_meter = float(TM_GATE)
    ally.turn_meter = 0.0
    mikage.skill_sequence_cursor = 1  # consumed 1 skill; still no request declared

    mikage.active_effects = [
        EffectInstance(
            instance_id="fx_mikage_self_02",
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

    assert mikage.active_effects == []

    procs = [e for e in sink.events if e.type == EventType.MASTERY_PROC]
    assert procs == [], "Expected no MASTERY_PROC events when no proc request exists for the step."
