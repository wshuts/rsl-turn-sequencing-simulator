from dataclasses import dataclass, field
from typing import Any

from rsl_turn_sequencing.effects import Effect


@dataclass(frozen=True)
class EffectInstance:
    """
    Minimal representation of a buff/debuff instance on an actor.

    This is intentionally small to support deterministic expiration seams.
    """
    instance_id: str
    effect_id: str              # e.g., "shield", "increase_atk"
    effect_kind: str            # e.g., "BUFF"
    placed_by: str              # actor name who applied it


@dataclass
class Actor:
    name: str
    # Speed and turn meter are modeled as floating point values.
    speed: float

    # Optional boss shield model (observer-only until combat is implemented).
    # Convention:
    #   - shield > 0  => "UP"
    #   - shield == 0 => "BROKEN"
    shield: int = 0

    # Optional: maximum shield value used for boss TURN_START reset semantics.
    # If provided on the boss actor, the simulator will reset `shield` to this value
    # at the start of each boss turn (before TURN_START observability emission).
    shield_max: int | None = None

    is_boss: bool = False
    # Optional metadata for faction-gated behaviors (e.g., join attacks).
    faction: str | None = None

    # Optional, deterministic skill selection for acceptance tests.
    #
    # When provided, each time this actor takes a turn, the next entry in
    # `skill_sequence` is consumed and `skill_sequence_cursor` is incremented.
    # The meaning of the skill ids (e.g., "A1", "A3", "B_A2") is not interpreted
    # by the engine yet — this is groundwork for skill→hit bridging.
    skill_sequence: list[str] | None = None
    skill_sequence_cursor: int = 0

    # Blessings live here (data-driven). Tests may use this for deterministic procs.
    # Example:
    #   {"phantom_touch": {"cooldown": 1, "rank": 4}}
    blessings: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Optional health model (only used when tests require it, e.g., Poison).
    max_hp: float = 0.0
    hp: float = 0.0

    # Multiplicative modifier applied to speed for tick fill (e.g., Decrease SPD).
    # 1.0 means no change; 0.7 means -30% speed.
    speed_multiplier: float = 1.0

    turn_meter: float = 0.0
    # Extra turns are turns granted without advancing turn meter fill.
    extra_turns: int = 0

    effects: list[Effect] = field(default_factory=list)

    # NEW: Buff/debuff instances currently active on this actor (for injected expiration seam).
    active_effects: list[EffectInstance] = field(default_factory=list)
