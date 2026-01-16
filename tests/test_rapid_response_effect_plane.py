from __future__ import annotations

"""
Rapid Response — Effect Plane (Acceptance Path)

Goal:
  Explicitly declare mastery proc requests in the battle spec (entity-scoped turn_overrides),
  then assert turn-meter changes as a consequence of *user intent*.

Key contract:
  When a qualifying Mikage-placed BUFF expires at TURN_END and the user declares:
    champions[i].turn_overrides.proc_request.on_step[step].mastery_procs = [{holder, mastery, count}]
  the engine should:
    (1) emit MASTERY_PROC
    (2) apply Rapid Response effect: +10% Turn Meter per proc count.

Notes:
- No test-only injection seams (no expiration_injector, no inline requester closures).
- Tests match the demo battlespec shape exactly.
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
    path = tmpdir / "battle_spec_rr_effect_plane.json"
    path.write_text(json.dumps(battle_spec, indent=2), encoding="utf-8")
    return path


def test_rapid_response_mastery_proc_increases_mikage_turn_meter_by_10_percent_per_count() -> None:
    mikage = Actor("Mikage", 100.0)
    coldheart = Actor("Coldheart", 100.0)

    # Ensure Mikage acts deterministically on the first tick.
    mikage.turn_meter = float(TM_GATE)
    coldheart.turn_meter = 0.0

    # In unit tests we are not consuming skills via the CLI provider, so we set the step cursor explicitly.
    # Cursor value is used as the step key (per ADR-001 usage in proc requester plumbing).
    mikage.skill_sequence_cursor = 1  # step "1"

    # Arrange: Mikage has a Mikage-placed BUFF that will expire naturally at TURN_END.
    mikage.active_effects = [
        EffectInstance(
            instance_id="fx_rr_effect_plane_01",
            effect_id="increase_atk",
            effect_kind="BUFF",
            placed_by="Mikage",
            duration=1,
        ),
        EffectInstance(
            instance_id="fx_rr_effect_plane_02",
            effect_id="increase_atk",
            effect_kind="BUFF",
            placed_by="Mikage",
            duration=1,
        ),
    ]

    # Battle spec expresses user intent for Rapid Response to proc with count=2 on step 1.
    battle_spec = {
        "boss": {"name": "Boss", "speed": 1500},
        "champions": [
            {"slot": 1, "name": "Mikage", "speed": 100.0},
            {"slot": 2, "name": "Coldheart", "speed": 100.0},
        ],
        "options": {"sequence_policy": "error_if_exhausted"},
    }

    mikage_spec = find_champion(battle_spec, name="Mikage")
    add_mastery_proc_request(
        mikage_spec,
        step=1,
        holder="Mikage",
        mastery="rapid_response",
        count=2,
    )

    with tempfile.TemporaryDirectory() as td:
        battle_path = _write_battle_spec(Path(td), battle_spec)
        mastery_proc_requester = build_mastery_proc_requester_from_battle_path(battle_path)
        assert mastery_proc_requester is not None

        sink = InMemoryEventSink()

        # Act
        step_tick(
            [mikage, coldheart],
            event_sink=sink,
            mastery_proc_requester=mastery_proc_requester,
        )

    # Sanity: MASTERY_PROC was emitted (control plane guardrail).
    procs = [e for e in sink.events if e.type == EventType.MASTERY_PROC]
    assert procs, "Expected at least one MASTERY_PROC event."

    matching = [
        e
        for e in procs
        if e.data.get("holder") == "Mikage"
        and e.data.get("mastery") == "rapid_response"
        and e.data.get("count") == 2
    ]
    assert matching, "Expected Rapid Response proc payload holder/mastery/count to match."

    # Assert (effect plane): +10% TM per count, applied to Mikage.
    expected_increase = float(TM_GATE) * 0.10 * 2

    # Mikage took the turn, so her turn meter was consumed/reset before mastery effects are applied.
    assert abs(mikage.turn_meter - expected_increase) < 1e-6, (
        f"Expected Mikage turn_meter to increase by {expected_increase} after Rapid Response procs, "
        f"but got {mikage.turn_meter}."
    )
