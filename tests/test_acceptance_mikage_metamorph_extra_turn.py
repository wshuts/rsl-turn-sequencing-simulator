from __future__ import annotations

from pathlib import Path

from rsl_turn_sequencing.__main__ import main


def _extract_frame_actor_rows(*, out: str, boss_turn_index: int) -> list[str]:
    """Return the raw row lines that belong to the requested Boss Turn frame."""
    lines = out.splitlines()
    header = f"Boss Turn #{boss_turn_index}"

    # Find the header line.
    header_idx = None
    for i, line in enumerate(lines):
        if line.strip() == header:
            header_idx = i
            break

    assert header_idx is not None, f"Output did not include {header!r}.\n\n{out}"

    # Rows continue until the next blank line or EOF.
    rows: list[str] = []
    for line in lines[header_idx + 1 :]:
        if not line.strip():
            break
        rows.append(line)

    return rows


def _actor_name_from_row(row: str) -> str:
    """Extract the actor name from a rendered CLI row."""
    # Example row:
    #   7: [21 UP] Mikage      {A_A4} [21 UP]
    # Actor starts after the "]" of the pre-shield snapshot.
    after = row.split("]", 1)[1].strip()
    # Actor name is the next token (names are space-separated in current output).
    # This is intentionally simple; the acceptance assertions below are about order.
    return after.split()[0]


def test_acceptance_mikage_metamorph_grants_an_immediate_extra_turn(capsys) -> None:
    """Using Mikage's Metamorph (A_A4) should grant an immediate extra turn.

    Observable contract (CLI):
    - In the Boss Turn #2 frame of the sample battle spec,
      Mikage consumes {A_A4}.
    - The very next actor row in that same frame should also be Mikage
      (her extra turn), before any other actor can act.

    This is an acceptance test only. Production code changes are expected
    in a subsequent step to satisfy this contract.
    """

    battle_path = Path("samples") / "demo_battle_spec_track_shield_state.json"

    rc = main(
        [
            "run",
            "--battle",
            str(battle_path),
            "--boss-actor",
            "Fire Knight",
            "--stop-after-boss-turns",
            "2",
            "--row-index-start",
            "1",
            "--ticks",
            "500",
        ]
    )
    assert rc == 0

    out = capsys.readouterr().out
    rows = _extract_frame_actor_rows(out=out, boss_turn_index=2)

    # Find Mikage's Metamorph row.
    idx = None
    for i, row in enumerate(rows):
        if " Mikage" in row and "{A_A4}" in row:
            idx = i
            break

    assert idx is not None, (
        "Expected Boss Turn #2 to include Mikage consuming {A_A4}.\n\n" + out
    )
    assert idx + 1 < len(rows), (
        "Expected at least one actor row after Mikage's {A_A4} row.\n\n" + out
    )

    # Extra turn is observable as Mikage acting again immediately.
    next_actor = _actor_name_from_row(rows[idx + 1])
    assert next_actor == "Mikage", (
        "Metamorph should grant an immediate extra turn: Mikage must act twice in a row "
        "(no other actor may intervene).\n\n"
        f"Row with {{A_A4}}: {rows[idx]}\n"
        f"Next row:         {rows[idx + 1]}\n\n"
        + out
    )
