from __future__ import annotations

"""Rapid Response — Proc Dynamics Only

Slice contract (see collaboration markdown):
  When a BUFF placed by Mikage expires and a deterministic Rapid Response proc request
  exists for that step, emit a MASTERY_PROC event with payload:
    { holder: "Mikage", mastery: "rapid_response", count: 1 }

This test intentionally does NOT assert any turn meter changes.
"""

from rsl_turn_sequencing.engine import TM_GATE, step_tick
from rsl_turn_sequencing.event_sink import InMemoryEventSink
from rsl_turn_sequencing.events import EventType
from rsl_turn_sequencing.models import Actor, EffectInstance


def test_rapid_response_procs_when_mikage_buff_expires_and_proc_request_exists() -> None:
    mikage = Actor("Mikage", 100.0)
    coldheart = Actor("Coldheart", 100.0)

    # Ensure Mikage acts deterministically on the first tick.
    mikage.turn_meter = TM_GATE
    coldheart.turn_meter = 0.0

    # Arrange: Coldheart has a Mikage-placed BUFF instance.
    coldheart.active_effects = [
        EffectInstance(
            instance_id="fx_mikage_buff_01",
            effect_id="increase_atk",
            effect_kind="BUFF",
            placed_by="Mikage",
        )
    ]

    # Deterministic proc request payload, mirroring future battle spec shape.
    proc_request_data = {
        "turn_overrides": {
            "proc_request": {
                "on_step": {
                    "1": {
                        "mastery_procs": [
                            {"holder": "Mikage", "mastery": "rapid_response", "count": 1}
                        ]
                    }
                }
            }
        }
    }

    def mastery_proc_requester(ctx: dict) -> list[dict]:
        step = str(ctx.get("turn_counter"))
        return (
            proc_request_data.get("turn_overrides", {})
            .get("proc_request", {})
            .get("on_step", {})
            .get(step, {})
            .get("mastery_procs", [])
        )

    sink = InMemoryEventSink()

    def injector(ctx: dict) -> list[dict]:
        # Expire the BUFF at TURN_END of Mikage's first turn boundary.
        if (
            ctx.get("phase") == str(EventType.TURN_END)
            and ctx.get("acting_actor") == "Mikage"
            and ctx.get("turn_counter") == 1
        ):
            return [
                {
                    "type": "expire_effect",
                    "instance_id": "fx_mikage_buff_01",
                    "reason": "injected",
                }
            ]
        return []

    # Act
    step_tick(
        [mikage, coldheart],
        event_sink=sink,
        expiration_injector=injector,
        mastery_proc_requester=mastery_proc_requester,
    )

    # Assert: effect removed
    assert coldheart.active_effects == []

    # Assert: mastery proc emitted with correct payload
    procs = [e for e in sink.events if e.type == EventType.MASTERY_PROC]
    assert procs, "Expected at least one MASTERY_PROC event."

    matching = [
        e
        for e in procs
        if e.data.get("holder") == "Mikage"
        and e.data.get("mastery") == "rapid_response"
        and e.data.get("count") == 1
    ]
    assert matching, "Expected Rapid Response proc payload holder/mastery/count to match."
