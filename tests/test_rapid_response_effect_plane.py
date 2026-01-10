from __future__ import annotations

"""Rapid Response — Effect Plane Only (RED)

Slice contract:
  When a MASTERY_PROC event for Mikage's Rapid Response is emitted, apply the
  turn meter increase to Mikage according to the mastery effect.

This test intentionally reuses the already-green proc dynamics path to produce
a deterministic MASTERY_PROC event, then asserts the *effect* is applied.

Expected mastery effect (Rapid Response):
  +10% Turn Meter per proc count when triggered.
  In this simulator, TM_GATE represents 100% turn meter.
"""

from rsl_turn_sequencing.engine import TM_GATE, step_tick
from rsl_turn_sequencing.event_sink import InMemoryEventSink
from rsl_turn_sequencing.events import EventType
from rsl_turn_sequencing.models import Actor, EffectInstance


def test_rapid_response_mastery_proc_increases_mikage_turn_meter_by_10_percent_per_count() -> None:
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
                            {"holder": "Mikage", "mastery": "rapid_response", "count": 2}
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

    # Sanity: mastery proc was emitted (control plane already verified elsewhere, but keep the guardrail).
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
    expected_increase = TM_GATE * 0.10 * 2
    # Note: Mikage took the turn, so the engine consumed/reset her turn meter before applying mastery effects.
    assert abs(mikage.turn_meter - expected_increase) < 1e-6, (
        f"Expected Mikage turn_meter to increase by {expected_increase} after Rapid Response procs, "
        f"but got {mikage.turn_meter}."
    )
