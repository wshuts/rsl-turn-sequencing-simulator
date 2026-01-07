from __future__ import annotations

import json
import re
from pathlib import Path

from rsl_turn_sequencing.__main__ import main


def _norm(s: str) -> str:
    # Collapse all whitespace so formatting tweaks (padding/columns) don't break the test.
    return re.sub(r"\s+", " ", s).strip()


def test_acceptance_cli_consumes_skill_sequence_and_decrements_shield_from_dataset(tmp_path: Path, capsys) -> None:
    """
    Acceptance test for the user-facing contract:

    - Battle spec provides skill_sequence and sequence_policy=error_if_exhausted
    - CLI consumes skills per actor turn
    - CLI translates skill -> hits using committed FK dataset
    - Boss shield decrements by hit-count before TURN_END snapshot
    - Output prints Boss Turn Frames with PRE/POST shield values

    The test is intentionally whitespace-tolerant because output is meant for humans
    and may evolve in alignment/padding.
    """

    battle = {
        "boss": {"name": "Fire Knight", "speed": 1500, "shield_max": 21},
        "actors": [
            {"name": "Coldheart", "speed": 2000, "skill_sequence": ["A1"] * 20},
        ],
        "options": {"sequence_policy": "error_if_exhausted"},
    }

    battle_path = tmp_path / "battle.json"
    battle_path.write_text(json.dumps(battle), encoding="utf-8")

    rc = main(["run", "--battle", str(battle_path), "--ticks", "10", "--boss-actor", "Fire Knight"])
    assert rc == 0

    out = capsys.readouterr().out
    n = _norm(out)

    # Frame exists
    assert "Boss Turn #1" in out

    # Contract: Coldheart A1 is 4 hits in dataset, so 21 -> 17 should appear on her row
    assert "Coldheart" in out
    assert "[21 UP]" in n
    # Token format may evolve: allow none, (A1), or {A1}.
    assert re.search(r"Coldheart( (\{[^}]+\}|\([^)]+\)))? \[17 UP\]", n), out

    # Boss row exists
    assert "Fire Knight" in out
