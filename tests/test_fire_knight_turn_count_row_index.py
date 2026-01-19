# tests/test_fire_knight_turn_count_row_index.py

from __future__ import annotations

from rsl_turn_sequencing.__main__ import main

# Reuse the existing parsing helper pattern from the baseline
from tests.test_mikage_metamorph_extra_turn import _extract_frame_actor_rows


def _row_index_from_row(row: str) -> int:
    """
    Extract the printed row index from a rendered CLI row.

    Example:
      98: [19 DOWN] Fire Knight [21 OPEN]
    """
    prefix = row.split(":", 1)[0].strip()
    return int(prefix)


def test_fire_knight_sixth_boss_turn_ends_on_row_index_98(capsys) -> None:
    """
    GIVEN the sample Fire Knight battle spec and a row-index-start of 56
    WHEN we run the CLI stopping immediately after the boss completes 6 turns
    THEN the final printed row index in Boss Turn #6 is 98 (matches observed Turn Count = 98)
    """

    argv = [
        "run",
        "--battle",
        "samples/demo_battle_spec_track_shield_state.json",
        "--champion-defs",
        "data/champions_fire_knight_team.json",
        "--boss-actor",
        "Fire Knight",
        "--stop-after-boss-turns",
        "6",
        "--row-index-start",
        "56",
        "--ticks",
        "500",
    ]

    rc = main(argv)
    assert rc == 0

    out = capsys.readouterr().out
    rows = _extract_frame_actor_rows(out=out, boss_turn_index=6)

    assert rows, "Expected Boss Turn #6 frame to contain at least one row.\n\n" + out

    last_row = rows[-1]

    # Sanity check: Boss Turn #6 should end with the boss completing a turn.
    assert "Fire Knight" in last_row, (
        "Expected the final row of Boss Turn #6 to be the boss.\n\n"
        f"Last row: {last_row}\n\n"
        + out
    )

    assert _row_index_from_row(last_row) == 98, (
        "Observed evidence: at the end of Fire Knight's 6th turn, TURN COUNT = 98.\n\n"
        f"Last row: {last_row}\n\n"
        + out
    )
