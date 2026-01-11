from __future__ import annotations

from rsl_turn_sequencing.event_sink import EventSink
from rsl_turn_sequencing.events import EventType
from rsl_turn_sequencing.models import Actor, EffectInstance


def apply_skill_buffs(
    *,
    actors: list[Actor],
    actor_name: str,
    skill_id: str,
    event_sink: EventSink | None = None,
) -> None:
    """Apply deterministic BUFF placements for select skills.

    This is a minimal, acceptance-driven provider. It does not model combat math.
    It only materializes BUFF state needed for downstream expiration/mastery slices.

    Current scope (Slice 2):
      - Mikage Base A3 (B_A3): place Increase ATK and Increase C.DMG on all allies for 2 turns.
    """
    if not skill_id:
        return

    holder = (actor_name or "").strip()
    holder_l = holder.lower()
    s = (skill_id or "").strip().upper()

    # Slice 2: Mikage Base A3 -> team buffs
    if holder_l not in {"mikage", "lady mikage"}:
        return
    if s != "B_A3":
        return

    actor = next((a for a in actors if a.name == holder), None)
    if actor is None:
        return

    # Determine which step in the skill sequence this corresponds to, if available.
    # _consume_next_skill increments the cursor after consumption, so the cursor value
    # is 1-based for the just-consumed skill.
    seq_index = int(getattr(actor, "skill_sequence_cursor", 0))

    # Engine stamps this each time a turn is processed (even without an event sink).
    applied_turn = int(getattr(actor, "_current_turn_counter", 0))

    # Allies: this simulator currently models a single allied team vs a boss.
    allies: list[Actor] = [a for a in actors if not getattr(a, "is_boss", False)]

    for target in allies:
        for effect_id in ("increase_atk", "increase_c_dmg"):
            instance_id = f"fx_{holder}_{s}_{seq_index}_{target.name}_{effect_id}"
            inst = EffectInstance(
                instance_id=instance_id,
                effect_id=effect_id,
                effect_kind="BUFF",
                placed_by=holder,
                duration=2,
                applied_turn=applied_turn,
            )
            target.active_effects.append(inst)

            if event_sink is not None:
                event_sink.emit(
                    EventType.EFFECT_APPLIED,
                    actor=holder,
                    instance_id=inst.instance_id,
                    effect_id=inst.effect_id,
                    effect_kind=inst.effect_kind,
                    owner=target.name,
                    placed_by=inst.placed_by,
                    duration=inst.duration,
                    source_skill_id=s,
                    source_sequence_index=seq_index,
                )
