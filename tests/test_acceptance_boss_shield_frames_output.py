from __future__ import annotations

import json
from pathlib import Path

from rsl_turn_sequencing.__main__ import main


def test_acceptance_cli_consumes_skill_sequence_and_decrements_shield_from_dataset(tmp_path: Path, capsys) -> None:
    """
    Acceptance test for the user-facing contract (v1):

    - Battle spec provides skill_sequence and sequence_policy=error_if_exhausted
    - CLI consumes skills per actor turn
    - CLI translates skill -> hits using committed FK dataset
    - Boss shield decrements by hit-count before TURN_END snapshot
    - Output prints Boss Turn Frames with PRE/POST shield values
    """

    # Provide enough skills so we don't exhaust during a short run.
    # We only assert on the first boss frame.
    battle = {
        "boss": {"name": "Fire Knight", "speed": 1500, "shield_max": 21},
        "actors": [
            {
                "name": "Coldheart",
                "speed": 2000,
                "skill_sequence": ["A1"] * 20,
            },
        ],
        "options": {"sequence_policy": "error_if_exhausted"},
    }

    battle_path = tmp_path / "battle.json"
    battle_path.write_text(json.dumps(battle), encoding="utf-8")

    rc = main(["run", "--battle", str(battle_path), "--ticks", "10", "--boss-actor", "Fire Knight"])
    assert rc == 0

    out = capsys.readouterr().out

    # Frame exists
    assert "Boss Turn #1" in out

    # Coldheart row shows shield moving from 21 -> 17 (A1 is 4 hits in dataset)
    assert "Coldheart" in out
    assert "Coldheart [17 UP" in out or "Coldheart [17 UP]" in out, out

    # Boss row exists
    assert "Fire Knight" in out
