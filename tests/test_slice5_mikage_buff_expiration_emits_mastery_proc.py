from __future__ import annotations

"""
Slice 5 — Engine-owned BUFF expiration + user-declared proc request ⇒ MASTERY_PROC

Contract:
  When a BUFF placed by Mikage expires via ENGINE-owned duration semantics (TURN_END),
  and the user provides a deterministic proc request for that step (turn_counter),
  the engine emits a MASTERY_PROC event with payload:
    { holder: "Mikage", mastery: "rapid_response", count: <n> }

Notes:
- This test intentionally does NOT assert turn meter changes (that belongs to Slice 6).
- This test MUST NOT use the injected expiration seam. Expiration must occur naturally
  via engine-owned duration decrement + expire at TURN_END.
"""

from rsl_turn_sequencing.engine import TM_GATE, step_tick
from rsl_turn_sequencing.event_sink import InMemoryEventSink
from rsl_turn_sequencing.events import EventType
from rsl_turn_sequencing.models import Actor, EffectInstance


def test_slice5_engine_owned_mikage_buff_expiration_emits_mastery_proc_when_requested() -> None:
    mikage = Actor(name="Mikage", speed=100.0)
    ally = Actor(name="Coldheart", speed=0.0)

    # Force Mikage to act deterministically.
    mikage.turn_meter = float(TM_GATE)
    ally.turn_meter = 0.0

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

    # Deterministic proc request: provide Rapid Response proc on turn_counter=1.
    def mastery_proc_requester(ctx: dict) -> list[dict]:
        turn_counter = int(ctx.get("turn_counter", 0))
        if turn_counter == 1:
            return [{"holder": "Mikage", "mastery": "rapid_response", "count": 1}]
        return []

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
        and e.data.get("turn_counter") == 1
    ]
    assert matching_procs, "Expected Rapid Response proc payload holder/mastery/count/turn_counter to match."

    # Optional ordering contract: expiration should precede proc emission for this turn_counter.
    # (This mirrors the injected expiration path ordering.)
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

    mikage.active_effects = [
        EffectInstance(
            instance_id="fx_mikage_self_02",
            effect_id="increase_atk",
            effect_kind="BUFF",
            placed_by="Mikage",
            duration=1,
        )
    ]

    # No proc request at any step.
    def mastery_proc_requester(ctx: dict) -> list[dict]:
        return []

    sink = InMemoryEventSink()

    step_tick(
        [mikage, ally],
        event_sink=sink,
        mastery_proc_requester=mastery_proc_requester,
    )

    assert mikage.active_effects == []

    procs = [e for e in sink.events if e.type == EventType.MASTERY_PROC]
    assert procs == [], "Expected no MASTERY_PROC events when no proc request exists for the step."
