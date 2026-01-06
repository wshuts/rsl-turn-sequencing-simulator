from __future__ import annotations

import json
from pathlib import Path

from tests.test_cli_module import _run_module


def test_sequence_policy_error_if_exhausted_fails_fast(tmp_path: Path) -> None:
    """Acceptance: sequence_policy=error_if_exhausted should fail as soon as a
    skill_sequence runs out (before skill→hit bridging exists).

    We construct a spec where a single fast champion takes every turn.
    """

    battle = {
        "boss": {"name": "Boss", "speed": 1, "shield_max": 21},
        "champions": [
            {
                "slot": 1,
                "name": "Nuker",
                "speed": 2000,
                "skill_sequence": ["A1"],
            }
        ],
        "options": {"sequence_policy": "error_if_exhausted"},
    }

    path = tmp_path / "battle.json"
    path.write_text(json.dumps(battle), encoding="utf-8")

    p = _run_module("run", "--battle", str(path), "--ticks", "5", "--boss-actor", "Boss")
    assert p.returncode == 2
    assert "skill_sequence exhausted" in (p.stderr or "")
