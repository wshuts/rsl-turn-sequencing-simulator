from __future__ import annotations

import json
from pathlib import Path

from rsl_turn_sequencing.__main__ import main


def _post_bracket_col(line: str) -> int:
    """Return the column index (0-based) where the POST shield bracket begins.

    Example:
      "  [21 UP] Coldheart {A1} [17 UP]" -> index of the final '['
    """
    return line.rfind("[")


def test_cli_skill_tokens_are_in_a_fixed_column_so_post_shield_does_not_jump(tmp_path: Path, capsys) -> None:
    """Acceptance: token presence must not shift the post-shield column.

    We compare the start column of the POST shield bracket between:
      - an actor row that consumes a skill (has a token)
      - the boss row (no token)
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
    lines = out.splitlines()

    cold_line = next((ln for ln in lines if "Coldheart" in ln and "[" in ln), None)
    boss_line = next((ln for ln in lines if "Fire Knight" in ln and "[" in ln), None)

    assert cold_line is not None, out
    assert boss_line is not None, out

    # Sanity: Coldheart line includes a token marker.
    assert ("{" in cold_line and "}" in cold_line) or ("(" in cold_line and ")" in cold_line), out

    assert _post_bracket_col(cold_line) == _post_bracket_col(boss_line), out
