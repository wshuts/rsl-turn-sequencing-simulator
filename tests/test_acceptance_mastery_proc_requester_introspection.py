from __future__ import annotations

import json
import tempfile
from pathlib import Path

from rsl_turn_sequencing.__main__ import _build_mastery_proc_requester_from_battle_json


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_demo_battle_spec() -> dict:
    """Load the canonical CLI battle spec fixture used for acceptance testing."""
    path = REPO_ROOT / "samples" / "demo_battle_spec_track_shield_state.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _inject_proc_request_for_mikage(spec: dict, *, step: int) -> None:
    """Mutate spec in-place: attach an entity-scoped deterministic proc request under Mikage."""
    champions = spec.get("champions")
    assert isinstance(champions, list), "demo battle spec must contain a champions array"

    mikage = next((c for c in champions if isinstance(c, dict) and c.get("name") == "Mikage"), None)
    assert isinstance(mikage, dict), "demo battle spec must include a Mikage champion entry"

    turn_overrides = mikage.setdefault("turn_overrides", {})
    assert isinstance(turn_overrides, dict)

    proc_request = turn_overrides.setdefault("proc_request", {})
    assert isinstance(proc_request, dict)

    on_step = proc_request.setdefault("on_step", {})
    assert isinstance(on_step, dict)

    on_step[str(step)] = {
        "mastery_procs": [
            {"holder": "Mikage", "mastery": "rapid_response", "count": 2},
        ]
    }


def test_mastery_proc_requester_is_inspectable_and_matches_demo_shape() -> None:
    """Acceptance: the requester built from the canonical demo battle spec must be inspectable.

    Motivation:
      The current implementation returns an opaque closure (functional/lazy), which is hard
      for humans to debug. We want an object that is still callable by the engine, but also
      exposes its normalized schedule for TDD/verification.

    Contract (desired):
      - builder returns a callable requester
      - requester exposes:
          * steps() -> list[int]
          * mastery_procs_for_step(step: int) -> list[dict]
      - the callable interface returns the same procs when invoked with ctx={'turn_counter': step}

    This test intentionally uses the real CLI battle spec fixture as a base, then injects a
    deterministic proc request under Mikage (entity-scoped), to avoid relying on whether
    the fixture already contains proc requests.
    """

    spec = _load_demo_battle_spec()
    _inject_proc_request_for_mikage(spec, step=7)

    with tempfile.TemporaryDirectory() as td:
        battle_path = Path(td) / "battle_with_proc_request.json"
        battle_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")

        requester = _build_mastery_proc_requester_from_battle_json(battle_path)

    # Desired: callable requester
    assert requester is not None, "Expected a requester when proc_request content is present."
    assert callable(requester), "Requester must be callable (engine contract)."

    # Desired: inspectable requester
    assert hasattr(requester, "steps"), "Requester must expose steps() for human inspection."
    assert hasattr(requester, "mastery_procs_for_step"), (
        "Requester must expose mastery_procs_for_step(step) for human inspection."
    )

    steps = requester.steps()  # type: ignore[attr-defined]
    assert 7 in steps, f"Expected injected step 7 to be present in requester.steps(); got {steps!r}"

    expected = [{"holder": "Mikage", "mastery": "rapid_response", "count": 2}]
    got = requester.mastery_procs_for_step(7)  # type: ignore[attr-defined]
    assert got == expected, f"Expected procs_for_step(7) == {expected!r}, got {got!r}"

    got_via_call = requester({"turn_counter": 7})
    assert got_via_call == expected, (
        "Callable requester must return the same normalized proc list as mastery_procs_for_step(step)."
    )
