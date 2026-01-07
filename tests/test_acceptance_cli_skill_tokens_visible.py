from __future__ import annotations

import re
from pathlib import Path

from rsl_turn_sequencing.__main__ import main


def _norm(s: str) -> str:
    # Collapse all whitespace so formatting tweaks (padding/columns) don't break the test.
    return re.sub(r"\s+", " ", s).strip()


def test_acceptance_cli_renders_a_skill_token_on_actor_rows(capsys) -> None:
    """If a battle spec includes skill_sequence, the CLI output should render the consumed token."""

    battle_path = Path("samples") / "demo_battle_spec_track_shield_state.json"

    rc = main(
        [
            "run",
            "--battle",
            str(battle_path),
            "--boss-actor",
            "Fire Knight",
            "--stop-after-boss-turns",
            "1",
            "--row-index-start",
            "56",
            "--ticks",
            "500",
        ]
    )
    assert rc == 0

    out = capsys.readouterr().out
    n = _norm(out)

    # Semantic assertion only: Mikage has a rendered skill token on her row.
    # Format is intentionally flexible to allow future tweaks (e.g., {A1} vs (A1)).
    assert re.search(r"\bMikage\b.*(\{[^}]+\}|\([^)]+\))", n), out
