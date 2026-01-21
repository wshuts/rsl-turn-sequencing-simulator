from __future__ import annotations

import re
from dataclasses import dataclass

from rsl_turn_sequencing.__main__ import main


@dataclass(frozen=True)
class ParsedRow:
    row_index: int
    shield_before_value: int
    shield_before_state: str
    actor: str
    skill_token: str
    shield_after_value: int
    shield_after_state: str


_ROW_RE = re.compile(
    r"""
    ^\s*(?P<row>\d+)\s*:\s*
    \[\s*(?P<before_val>\d+)\s+(?P<before_state>[A-Z_]+)\s*\]\s*
    (?P<actor>.+?)\s*
    \{\s*(?P<skill>(?:[A-Z]_[A-Z0-9]+|[A-Z]\d+))\s*\}\s*
    \[\s*(?P<after_val>\d+)\s+(?P<after_state>[A-Z_]+)\s*\]\s*$
    """,
    re.VERBOSE,
)


def _parse_row(line: str) -> ParsedRow:
    m = _ROW_RE.match(line)
    assert m is not None, f"Could not parse row line:\n{line}"

    return ParsedRow(
        row_index=int(m.group("row")),
        shield_before_value=int(m.group("before_val")),
        shield_before_state=m.group("before_state"),
        actor=m.group("actor").strip(),
        skill_token=m.group("skill"),
        shield_after_value=int(m.group("after_val")),
        shield_after_state=m.group("after_state"),
    )


def _extract_parsed_rows_in_range(stdout: str, start: int, end: int) -> list[ParsedRow]:
    parsed: list[ParsedRow] = []
    for line in stdout.splitlines():
        # quick prefilter: must contain "<num>:"
        if ":" not in line:
            continue
        # attempt parse; if it doesn't match, skip (headers, blank lines, etc.)
        m = _ROW_RE.match(line)
        if not m:
            continue
        row_idx = int(m.group("row"))
        if start <= row_idx <= end:
            parsed.append(_parse_row(line))
    return parsed


EXPECTED_56_87: list[ParsedRow] = [
    ParsedRow(56, 21, "UP",     "Mikage (N)",      "A_A1", 20, "UP"),
    ParsedRow(57, 20, "UP",     "Mithrala (N)",    "A1",   18, "UP"),
    ParsedRow(58, 18, "UP",     "Tomb Lord (N)",   "A2",   17, "UP"),
    ParsedRow(59, 17, "UP",     "Coldheart (N)",   "A1",   12, "UP"),
    ParsedRow(60, 12, "UP",     "Martyr",      "A2",   12, "UP"),
    ParsedRow(61, 21, "UP",     "Fire Knight (N)", "A2",    5, "UP"),
    ParsedRow(62,  5, "UP",     "Mikage",      "A_A4",  5, "UP"),
    ParsedRow(63,  5, "UP",     "Mikage",      "B_A3",  0, "BROKEN"),
    ParsedRow(64,  0, "BROKEN", "Mithrala",    "A3",    0, "BROKEN"),
    ParsedRow(65,  0, "BROKEN", "Tomb Lord",   "A3",    0, "BROKEN"),
    ParsedRow(66,  0, "BROKEN", "Coldheart",   "A3",    0, "BROKEN"),
    ParsedRow(67,  0, "BROKEN", "Martyr",      "A1",    0, "BROKEN"),
    ParsedRow(68,  0, "BROKEN", "Mikage",      "B_A2",  0, "BROKEN"),
    ParsedRow(69, 21, "UP",     "Fire Knight (N)", "A1",   11, "UP"),
    ParsedRow(70, 11, "UP",     "Mithrala",    "A2",   10, "UP"),
    ParsedRow(71, 10, "UP",     "Tomb Lord",   "A1",    7, "UP"),
    ParsedRow(72,  7, "UP",     "Coldheart",   "A1",    2, "UP"),
    ParsedRow(73,  2, "UP",     "Mikage",      "B_A1",  1, "UP"),
    ParsedRow(74,  1, "UP",     "Martyr",      "A3",    0, "BROKEN"),
    ParsedRow(75, 21, "UP",     "Fire Knight (N)", "A1",   10, "UP"),
    ParsedRow(76, 10, "UP",     "Mithrala",    "A1",    8, "UP"),
    ParsedRow(77,  8, "UP",     "Tomb Lord (N)",   "A1",    5, "UP"),
    ParsedRow(78,  5, "UP",     "Mikage (N)",      "B_A1",  4, "UP"),
    ParsedRow(79,  4, "UP",     "Coldheart (N)",   "A1",    0, "BROKEN"),
    ParsedRow(80,  0, "BROKEN", "Martyr",      "A2",    0, "BROKEN"),
    ParsedRow(81, 21, "UP",     "Fire Knight (N)", "A1",    5, "UP"),
    ParsedRow(82,  5, "UP",     "Mikage",      "B_A3",  0, "BROKEN"),
    ParsedRow(83,  0, "BROKEN", "Mithrala",    "A3",    0, "BROKEN"),
    ParsedRow(84,  0, "BROKEN", "Tomb Lord",   "A2",    0, "BROKEN"),
    ParsedRow(85,  0, "BROKEN", "Coldheart",   "A1",    0, "BROKEN"),
    ParsedRow(86,  0, "BROKEN", "Martyr",      "A1",    0, "BROKEN"),
    ParsedRow(87,  0, "BROKEN", "Mikage",      "B_A2",  0, "BROKEN"),
]


def test_cli_stdout_rows_56_87_match_expected_fields(capsys) -> None:
    """
    GIVEN the demo shield-state battle spec
      and boss actor Fire Knight
      and stop-after-boss-turns 6
      and row-index-start 56
    WHEN we run the CLI
    THEN the semantic content of rows 56–87 matches expected fields
         (ignoring spacing/formatting differences).
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
    actual = _extract_parsed_rows_in_range(out, start=56, end=87)

    # Fail loudly if we didn't even see the rows.
    assert len(actual) == len(EXPECTED_56_87), (
        f"Expected {len(EXPECTED_56_87)} parsed rows in range 56–87, got {len(actual)}.\n"
        "This usually means row indexing drifted or the stdout format changed enough to not parse.\n"
    )

    assert actual == EXPECTED_56_87
