from __future__ import annotations


from rsl_turn_sequencing.engine import _emit_injected_expirations
from rsl_turn_sequencing.event_sink import InMemoryEventSink
from rsl_turn_sequencing.events import EventType
from rsl_turn_sequencing.models import Actor, EffectInstance


def test_sliceA_records_qualifying_expirations_by_holder_and_step() -> None:
    """Slice A: the engine records qualifying expirations as (holder, step) -> count.

    Qualifying rule (minimal):
      - BUFF
      - placed_by matches an Actor.name
      - step derived from holder.skill_sequence_cursor (ADR-001 consumed-so-far, 1-based)
    """

    mikage = Actor(name="Mikage", speed=200.0, skill_sequence_cursor=1)
    ally = Actor(name="Ally", speed=180.0)

    # Two qualifying BUFFs placed by Mikage.
    ally.active_effects = [
        EffectInstance(
            instance_id="fx1",
            effect_id="increase_atk",
            effect_kind="BUFF",
            placed_by="Mikage",
            duration=0,
            applied_turn=0,
        ),
        EffectInstance(
            instance_id="fx2",
            effect_id="shield",
            effect_kind="BUFF",
            placed_by="Mikage",
            duration=0,
            applied_turn=0,
        ),
        # Non-qualifying: DEBUFF
        EffectInstance(
            instance_id="fx3",
            effect_id="decrease_def",
            effect_kind="DEBUFF",
            placed_by="Mikage",
            duration=0,
            applied_turn=0,
        ),
        # Non-qualifying: unknown placer
        EffectInstance(
            instance_id="fx4",
            effect_id="increase_spd",
            effect_kind="BUFF",
            placed_by="Ghost",
            duration=0,
            applied_turn=0,
        ),
    ]

    actors = [mikage, ally]
    sink = InMemoryEventSink()
    sink.start_tick()

    def injector(_ctx: dict) -> list[dict]:
        # Expire all four instances deterministically.
        return [
            {"type": "expire_effect", "instance_id": "fx1", "reason": "injected"},
            {"type": "expire_effect", "instance_id": "fx2", "reason": "injected"},
            {"type": "expire_effect", "instance_id": "fx3", "reason": "injected"},
            {"type": "expire_effect", "instance_id": "fx4", "reason": "injected"},
        ]

    _emit_injected_expirations(
        event_sink=sink,
        actors=actors,
        phase=EventType.TURN_END,
        acting_actor=mikage,
        acting_actor_index=0,
        turn_counter=1,
        expiration_injector=injector,
        mastery_proc_requester=None,
    )

    counts = getattr(sink, "_qualifying_expiration_counts", {})
    assert counts.get(("Mikage", 1)) == 2
    # Prove non-qualifiers were ignored.
    assert ("Ghost", 1) not in counts
