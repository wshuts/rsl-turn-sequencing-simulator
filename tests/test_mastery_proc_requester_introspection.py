from __future__ import annotations

import json
import tempfile
from pathlib import Path

from rsl_turn_sequencing.engine import build_mastery_proc_requester_from_battle_path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_demo_battle_spec() -> dict:
    """Load the canonical CLI battle spec fixture used for acceptance testing."""
    path = REPO_ROOT / "samples" / "demo_battle_spec_track_shield_state.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_expected_demo_mikage_proc_requests(spec: dict) -> tuple[int, list[dict]]:
    """Pull the canonical, entity-scoped Mikage proc_request from the demo battlespec.

    Returns:
      (step, mastery_procs_list)

    Raises AssertionError if the expected structure is not present (by design).
    """
    champions = spec.get("champions")
    assert isinstance(champions, list), "demo battle spec must contain a champions array"

    mikage = next((c for c in champions if isinstance(c, dict) and c.get("name") == "Mikage"), None)
    assert isinstance(mikage, dict), "demo battle spec must include a Mikage champion entry"

    turn_overrides = mikage.get("turn_overrides")
    assert isinstance(turn_overrides, dict), "demo Mikage entry must include turn_overrides"

    proc_request = turn_overrides.get("proc_request")
    assert isinstance(proc_request, dict), "demo Mikage turn_overrides must include proc_request"

    on_step = proc_request.get("on_step")
    assert isinstance(on_step, dict), "demo Mikage proc_request must include on_step"

    # Demo fixture currently uses a single step key like "6".
    step_keys = list(on_step.keys())
    assert step_keys, "demo Mikage on_step must include at least one step key"

    # Use the first step in the fixture (stable enough for acceptance; if demo evolves,
    # this still validates the builder against the fixture rather than hardcoding a number).
    step_key = step_keys[0]
    step_val = on_step[step_key]
    assert isinstance(step_val, dict), "demo Mikage on_step[step] must be an object"

    mastery_procs = step_val.get("mastery_procs")
    assert isinstance(mastery_procs, list), "demo Mikage on_step[step].mastery_procs must be a list"

    cleaned = [p for p in mastery_procs if isinstance(p, dict)]
    assert cleaned, "demo Mikage mastery_procs must include at least one proc dict"

    return int(step_key), cleaned


def test_mastery_proc_requester_is_inspectable_and_matches_demo_shape() -> None:
    """Acceptance: requester built from canonical demo battlespec is inspectable and matches fixture contents.

    Contract (desired):
      - builder returns a callable requester (even if schedule is empty)
      - requester exposes:
          * steps() -> list[int]
          * mastery_procs_for_step(step: int) -> list[dict]
      - callable interface returns the same procs when invoked with ctx={'turn_counter': step}
      - for the demo battlespec, requester must match the fixture’s entity-scoped Mikage proc_request
    """
    spec = _load_demo_battle_spec()
    expected_step, expected_procs = _extract_expected_demo_mikage_proc_requests(spec)

    with tempfile.TemporaryDirectory() as td:
        battle_path = Path(td) / "demo_battle_spec.json"
        battle_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")

        requester = build_mastery_proc_requester_from_battle_path(battle_path)

    assert requester is not None, "Expected a requester for any valid battle spec dict."
    assert callable(requester), "Requester must be callable (engine contract)."

    assert hasattr(requester, "steps"), "Requester must expose steps() for human inspection."
    assert hasattr(requester, "mastery_procs_for_step"), (
        "Requester must expose mastery_procs_for_step(step) for human inspection."
    )

    steps = requester.steps()  # type: ignore[attr-defined]
    assert expected_step in steps, (
        f"Expected demo fixture step {expected_step} to be present in requester.steps(); got {steps!r}"
    )

    got = requester.mastery_procs_for_step(expected_step)  # type: ignore[attr-defined]
    # The requester may merge multiple entity-scoped proc requests that share the same step.
    # This acceptance only requires that the canonical Mikage request is present.
    for item in expected_procs:
        assert item in got, (
            f"Expected demo Mikage proc request {item!r} to be present for step {expected_step}; got {got!r}"
        )

    got_via_call = requester({"turn_counter": expected_step})
    for item in expected_procs:
        assert item in got_via_call


def test_mastery_proc_requester_is_returned_even_when_no_proc_requests_exist() -> None:
    """Acceptance: builder returns an inspectable, callable requester for valid JSON even with no proc_request."""
    empty_spec = {
        "boss": {"name": "Fire Knight"},
        "champions": [{"name": "Mikage"}],
        "options": {"sequence_policy": "by_actor_list"},
    }

    with tempfile.TemporaryDirectory() as td:
        battle_path = Path(td) / "battle_no_proc_request.json"
        battle_path.write_text(json.dumps(empty_spec, indent=2), encoding="utf-8")

        requester = build_mastery_proc_requester_from_battle_path(battle_path)

    assert requester is not None, "Expected a requester even when no proc requests are declared."
    assert callable(requester)

    assert hasattr(requester, "steps")
    assert hasattr(requester, "mastery_procs_for_step")

    assert requester.steps() == []  # type: ignore[attr-defined]
    assert requester.mastery_procs_for_step(1) == []  # type: ignore[attr-defined]
    assert requester({"turn_counter": 1}) == []
