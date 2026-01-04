from __future__ import annotations

import json
from pathlib import Path

from rsl_turn_sequencing.__main__ import main


def test_acceptance_cli_prints_boss_frames_with_shield_reset(tmp_path: Path, capsys) -> None:
    """
    Acceptance test for the user-facing contract:

    - CLI can run a minimal battle spec
    - Output prints Boss Turn Frames
    - Boss TURN_START shows shield reset to shield_max (PRE snapshot)
    """

    battle = {
        "boss": {"name": "Boss", "speed": 1490, "shield_max": 21},
        "actors": [
            # Slightly faster so we get at least one non-boss row before boss closes the frame.
            {"name": "A", "speed": 1500},
        ],
    }
    battle_path = tmp_path / "battle.json"
    battle_path.write_text(json.dumps(battle), encoding="utf-8")

    rc = main(["run", "--battle", str(battle_path), "--ticks", "5", "--boss-actor", "Boss"])
    assert rc == 0

    out = capsys.readouterr().out

    # Frame exists
    assert "Boss Turn #1" in out

    # Boss row shows shield reset at PRE (TURN_START). Rendering uses "[<PRE>] Boss [<POST>]".
    # We assert a robust substring that should survive spacing tweaks.
    assert "Boss [21 UP" in out or "] Boss [21 UP" in out, out
