from __future__ import annotations

import json
from pathlib import Path

from rsl_turn_sequencing.__main__ import main


def test_acceptance_cli_prints_boss_frames_with_pre_post_shield_changes(tmp_path: Path, capsys) -> None:
    """
    Acceptance test for the user-facing contract (v0):

    - CLI can run a minimal battle spec
    - Output prints Boss Turn Frames
    - Each turn row prints PRE and POST shield snapshots
    - Non-boss actor turn can decrement shield (hit-counter semantics)
    - Boss TURN_START resets shield to shield_max (PRE snapshot)
    """

    battle = {
        "boss": {"name": "Boss", "speed": 1500, "shield_max": 21},
        "actors": [
            {"name": "A1", "speed": 2000},
        ],
        # v0 scripting hook: when an actor takes a turn, apply this many shield hits
        "hits_by_actor": {
            "A1": 3
        },
    }

    battle_path = tmp_path / "battle.json"
    battle_path.write_text(json.dumps(battle), encoding="utf-8")

    rc = main(["run", "--battle", str(battle_path), "--ticks", "5", "--boss-actor", "Boss"])
    assert rc == 0

    out = capsys.readouterr().out

    # Frame exists
    assert "Boss Turn #1" in out

    # A1 row shows shield moving from 21 -> 18 within the frame
    assert "A1" in out
    assert "21 UP" in out
    assert "18 UP" in out

    # Boss row shows shield reset to 21 UP at PRE (TURN_START)
    assert "Boss" in out
    assert "Boss [21 UP" in out or "] Boss [21 UP" in out, out
