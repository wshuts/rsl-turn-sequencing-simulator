from __future__ import annotations

from rsl_turn_sequencing.engine import TM_GATE, step_tick
from rsl_turn_sequencing.event_sink import InMemoryEventSink
from rsl_turn_sequencing.events import EventType
from rsl_turn_sequencing.models import Actor, EffectInstance


def test_injected_expire_effect_by_instance_id_removes_buff_and_emits_payload() -> None:
    """Slice: injected "expire effect by instance_id" removes a BUFF instance and emits EFFECT_EXPIRED
    containing placed_by so Rapid Response can be tested deterministically.

    This test intentionally uses the existing dev-only `expiration_injector` seam in `step_tick`.
    The seam is being upgraded: the injected payload becomes an `expire_effect` request by instance_id,
    and the engine must translate that into a structured EFFECT_EXPIRED event.

    Acceptance criteria asserted here:
      - The effect instance is removed from owner.active_effects
      - An EFFECT_EXPIRED event is emitted with:
          instance_id, effect_id, effect_kind, owner, placed_by, reason
    """

    mikage = Actor("Mikage", 100.0)
    coldheart = Actor("Coldheart", 100.0)

    # Ensure Mikage acts deterministically.
    mikage.turn_meter = TM_GATE
    coldheart.turn_meter = 0.0

    # Arrange: Coldheart has a Mikage-placed BUFF instance.
    fx = EffectInstance(
        instance_id="fx_mikage_shield_01",
        effect_id="shield",
        effect_kind="BUFF",
        placed_by="Mikage",
        duration=2,
    )

    # Actor currently has no formal `active_effects` field; for this slice we attach it.
    # Production will formalize this on Actor.
    coldheart.active_effects = [fx]

    sink = InMemoryEventSink()

    def injector(ctx: dict) -> list[dict]:
        # Inject at the start of Mikage's first turn boundary.
        if (
            ctx.get("phase") == str(EventType.TURN_START)
            and ctx.get("acting_actor") == "Mikage"
            and ctx.get("turn_counter") == 1
        ):
            return [
                {
                    "type": "expire_effect",
                    "instance_id": "fx_mikage_shield_01",
                    "reason": "injected",
                }
            ]
        return []

    # Act
    step_tick([mikage, coldheart], event_sink=sink, expiration_injector=injector)

    # Assert: effect removed
    assert getattr(coldheart, "active_effects") == []

    # Assert: EFFECT_EXPIRED payload includes placed_by + reason
    expired = [e for e in sink.events if e.type == EventType.EFFECT_EXPIRED]
    assert expired, "Expected at least one EFFECT_EXPIRED event."

    # Find the one corresponding to the instance.
    matching = [
        e
        for e in expired
        if e.data.get("instance_id") == "fx_mikage_shield_01"
        and e.data.get("effect_id") == "shield"
        and e.data.get("effect_kind") == "BUFF"
        and e.data.get("owner") == "Coldheart"
        and e.data.get("placed_by") == "Mikage"
        and e.data.get("duration") == 2
        and e.data.get("reason") == "injected"
    ]

    assert matching, (
        "Expected EFFECT_EXPIRED event with required payload: "
        "instance_id/effect_id/effect_kind/owner/placed_by/reason."
    )
