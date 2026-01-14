from __future__ import annotations

"""
Rapid Response — Proc Dynamics (User-Declared Intent)

Contract:
  Rapid Response mastery procs ONLY when:
    - a qualifying Mikage BUFF expires via engine-owned duration logic, AND
    - the user explicitly declares a mastery proc request for the relevant step.

This file validates:
  - Proc emission is gated by user intent
  - Proc count matches the declared request
  - Proc timing aligns with BUFF expiration (TURN_END)
  - No proc occurs when no request exists

Non-goals (explicitly excluded):
  - Turn meter changes (Slice 6)
  - Test-only injection seams
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
    path = tmpdir / "battle_spec_rr_dynamics.json"
    path.write_text(json.dumps(battle_spec, indent=2), encoding="utf-8")
    return path


def _base_battle_spec() -> dict:
    return {
        "boss": {"name": "Boss", "speed": 1500},
        "champions": [
            {"slot": 1, "name": "Mikage", "speed": 100.0},
            {"slot": 2, "name": "Coldheart", "speed": 0.0},
        ],
        "options": {"sequence_policy": "error_if_exhausted"},
    }


def _arrange_mikage_with_expiring_buff(step: int) -> tuple[Actor, Actor]:
    mikage = Actor(name="Mikage", speed=100.0)
    ally = Actor(name="Coldheart", speed=0.0)

    mikage.turn_meter = float(TM_GATE)
    ally.turn_meter = 0.0

    # Skill consumption is not driven by the CLI in unit tests;
    # we explicitly set the cursor to align with the requested step.
    mikage.skill_sequence_cursor = step

    mikage.active_effects = [
        EffectInstance(
            instance_id="fx_rr_test",
            effect_id="increase_atk",
            effect_kind="BUFF",
            placed_by="Mikage",
            duration=1,
        )
    ]

    return mikage, ally


def test_rapid_response_proc_fires_with_requested_count_on_buff_expiration() -> None:
    """
    Given:
      - Mikage BUFF expires at TURN_END
      - User declares Rapid Response proc for step 1 with count=2

    Expect:
      - Exactly one MASTERY_PROC event
      - Payload reflects requested count
    """
    mikage, ally = _arrange_mikage_with_expiring_buff(step=1)

    battle_spec = _base_battle_spec()
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
        requester = build_mastery_proc_requester_from_battle_path(battle_path)

        sink = InMemoryEventSink()

        step_tick(
            [mikage, ally],
            event_sink=sink,
            mastery_proc_requester=requester,
        )

    procs = [e for e in sink.events if e.type == EventType.MASTERY_PROC]
    assert len(procs) == 1, "Expected exactly one Rapid Response proc event."

    proc = procs[0]
    assert proc.data.get("holder") == "Mikage"
    assert proc.data.get("mastery") == "rapid_response"
    assert proc.data.get("count") == 2


def test_rapid_response_proc_does_not_fire_without_user_request() -> None:
    """
    Given:
      - Mikage BUFF expires
      - No mastery proc request declared

    Expect:
      - No MASTERY_PROC events
    """
    mikage, ally = _arrange_mikage_with_expiring_buff(step=1)

    battle_spec = _base_battle_spec()

    with tempfile.TemporaryDirectory() as td:
        battle_path = _write_battle_spec(Path(td), battle_spec)
        requester = build_mastery_proc_requester_from_battle_path(battle_path)

        sink = InMemoryEventSink()

        step_tick(
            [mikage, ally],
            event_sink=sink,
            mastery_proc_requester=requester,
        )

    procs = [e for e in sink.events if e.type == EventType.MASTERY_PROC]
    assert procs == [], "No proc should fire without explicit user intent."


def test_rapid_response_proc_is_step_scoped() -> None:
    """
    Given:
      - Mikage expires a BUFF on step 2
      - User declares proc for step 1 only

    Expect:
      - No MASTERY_PROC emitted
    """
    mikage, ally = _arrange_mikage_with_expiring_buff(step=2)

    battle_spec = _base_battle_spec()
    mikage_spec = find_champion(battle_spec, name="Mikage")

    add_mastery_proc_request(
        mikage_spec,
        step=1,  # mismatched step
        holder="Mikage",
        mastery="rapid_response",
        count=1,
    )

    with tempfile.TemporaryDirectory() as td:
        battle_path = _write_battle_spec(Path(td), battle_spec)
        requester = build_mastery_proc_requester_from_battle_path(battle_path)

        sink = InMemoryEventSink()

        step_tick(
            [mikage, ally],
            event_sink=sink,
            mastery_proc_requester=requester,
        )

    procs = [e for e in sink.events if e.type == EventType.MASTERY_PROC]
    assert procs == [], "Proc must not fire when step does not match user request."
