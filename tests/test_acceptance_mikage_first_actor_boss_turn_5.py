# tests/test_acceptance_mikage_first_actor_boss_turn_5.py

from rsl_turn_sequencing.__main__ import main

# Import the same helpers used by the mirror test
from tests.test_acceptance_mikage_metamorph_extra_turn import (
    _extract_frame_actor_rows,
    _actor_name_from_row,
)


def test_acceptance_mikage_is_first_actor_in_boss_turn_5(capsys):
    # -----------------
    # Arrange (IDENTICAL to mirror)
    # -----------------
    argv = [
        "run",
        "--battle",
        "samples/demo_battle_spec_track_shield_state.json",
        "--boss-actor",
        "Fire Knight",
        "--stop-after-boss-turns",
        "5",
        "--row-index-start",
        "1",
        "--ticks",
        "500",
    ]

    # -----------------
    # Act (IDENTICAL to mirror)
    # -----------------
    main(argv)
    out = capsys.readouterr().out

    # -----------------
    # Assert (ONLY difference)
    # -----------------
    rows = _extract_frame_actor_rows(out=out, boss_turn_index=5)

    assert _actor_name_from_row(rows[0]) == "Mikage"
