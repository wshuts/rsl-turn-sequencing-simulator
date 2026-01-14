# tests/_support/battle_spec_helpers.py
from __future__ import annotations

from typing import Any, MutableMapping


def find_champion(battle_spec: MutableMapping[str, Any], *, name: str) -> MutableMapping[str, Any]:
    """
    Return the first champion dict with matching name.

    Raises AssertionError with a helpful message if not found.
    """
    champs = battle_spec.get("champions")
    assert isinstance(champs, list), "battle_spec['champions'] must be a list"
    for champ in champs:
        if isinstance(champ, dict) and champ.get("name") == name:
            return champ
    raise AssertionError(f"Champion not found in battle_spec: name={name!r}")


def ensure_turn_overrides(entity: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    """Ensure entity has a turn_overrides dict; return it."""
    to = entity.get("turn_overrides")
    if not isinstance(to, dict):
        to = {}
        entity["turn_overrides"] = to
    return to


def add_mastery_proc_request(
    entity: MutableMapping[str, Any],
    *,
    step: int,
    holder: str,
    mastery: str,
    count: int,
) -> None:
    """
    Add an entity-scoped mastery proc request using the canonical demo battlespec shape:

      entity["turn_overrides"]["proc_request"]["on_step"][str(step)]["mastery_procs"] += [{...}]

    Notes:
    - step keys are strings in the JSON fixture, so this helper always stores str(step).
    - appends to existing mastery_procs list if present.
    """
    assert isinstance(step, int) and step >= 0, "step must be a non-negative int"
    assert isinstance(count, int) and count >= 0, "count must be a non-negative int"

    turn_overrides = ensure_turn_overrides(entity)

    proc_request = turn_overrides.get("proc_request")
    if not isinstance(proc_request, dict):
        proc_request = {}
        turn_overrides["proc_request"] = proc_request

    on_step = proc_request.get("on_step")
    if not isinstance(on_step, dict):
        on_step = {}
        proc_request["on_step"] = on_step

    step_key = str(step)
    step_obj = on_step.get(step_key)
    if not isinstance(step_obj, dict):
        step_obj = {}
        on_step[step_key] = step_obj

    mastery_procs = step_obj.get("mastery_procs")
    if not isinstance(mastery_procs, list):
        mastery_procs = []
        step_obj["mastery_procs"] = mastery_procs

    mastery_procs.append({"holder": holder, "mastery": mastery, "count": count})
