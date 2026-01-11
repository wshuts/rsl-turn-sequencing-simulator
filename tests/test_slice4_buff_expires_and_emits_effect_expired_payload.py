from rsl_turn_sequencing.engine import TM_GATE, step_tick
from rsl_turn_sequencing.event_sink import InMemoryEventSink
from rsl_turn_sequencing.events import EventType
from rsl_turn_sequencing.models import Actor, EffectInstance


def test_slice4_buff_owner_turn_end_expires_zero_duration_buff_and_emits_payload() -> None:
    """Slice 4: When a BUFF duration reaches 0 at the BUFF owner's TURN_END,
    the engine removes the instance and emits EFFECT_EXPIRED with structured payload,
    including placed_by.
    """

    mikage = Actor(name="Mikage", speed=100.0)
    ally = Actor(name="Coldheart", speed=0.0)

    # Force Mikage to act deterministically.
    mikage.turn_meter = float(TM_GATE)
    ally.turn_meter = 0.0

    # Mikage has one self-buff with duration=1 (will reach 0 on her TURN_END).
    mikage.active_effects = [
        EffectInstance(
            instance_id="fx_mikage_self_01",
            effect_id="increase_atk",
            effect_kind="BUFF",
            placed_by="Mikage",
            duration=1,
        )
    ]

    sink = InMemoryEventSink()

    # Act: Mikage takes a turn and completes TURN_END.
    winner = step_tick([mikage, ally], event_sink=sink)

    assert winner is mikage

    # Assert: the buff is removed.
    assert mikage.active_effects == []

    # Assert: EFFECT_EXPIRED contains structured payload.
    expired = [e for e in sink.events if e.type == EventType.EFFECT_EXPIRED]
    assert expired, "Expected at least one EFFECT_EXPIRED event."

    matching = [
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

    assert matching, (
        "Expected EFFECT_EXPIRED event with required payload: "
        "instance_id/effect_id/effect_kind/owner/placed_by/duration/reason/phase."
    )
