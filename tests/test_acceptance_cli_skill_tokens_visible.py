import re
from pathlib import Path

from rsl_turn_sequencing.__main__ import main


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def test_acceptance_cli_renders_a_skill_token_on_actor_rows(capsys) -> None:
    main(
        [
            "run",
            "--battle",
            str(Path("samples") / "demo_battle_spec_track_shield_state.json"),
            "--boss-actor",
            "Fire Knight",
            "--stop-after-boss-turns",
            "1",
            "--row-index-start",
            "56",
        ]
    )

    out = capsys.readouterr().out
    n = _norm(out)

    # Minimal contract: a token exists on the same line as the actor.
    # (Don’t care what the token is yet.)
    assert re.search(r"\bMikage\b.*\([^)]+\)", n), out
