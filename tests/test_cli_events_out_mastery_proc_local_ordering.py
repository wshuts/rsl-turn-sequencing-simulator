from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_module(*args: str) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, "-m", "rsl_turn_sequencing", *args]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        cwd=REPO_ROOT,
        env=env,
    )


def test_mastery_proc_is_between_effect_expired_and_turn_end_in_events_out() -> None:
    """
    GIVEN the sample battle spec and CLI parameters:
      - boss actor: Fire Knight
      - stop after boss turns: 6
      - row index start: 56
    WHEN we run the CLI with --events-out <path>
    THEN for every MASTERY_PROC event:
      - the immediately previous event is EFFECT_EXPIRED
      - the immediately next event is TURN_END
    """
    battle_path = REPO_ROOT / "samples" / "demo_battle_spec_track_shield_state.json"
    assert battle_path.exists(), "Expected sample battle spec to exist in samples/."

    with tempfile.TemporaryDirectory() as td:
        events_out_path = Path(td) / "events_out.json"

        p = _run_module(
            "run",
            "--battle",
            str(battle_path),
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
            "--events-out",
            str(events_out_path),
        )

        assert p.returncode == 0, (
            "Expected CLI run to succeed (returncode 0).\n"
            f"STDOUT:\n{p.stdout}\n"
            f"STDERR:\n{p.stderr}\n"
        )
        assert events_out_path.exists(), "Expected CLI to create the --events-out JSON file."

        events = json.loads(events_out_path.read_text(encoding="utf-8"))
        assert isinstance(events, list), "Expected dumped event stream to be a JSON array."

        mastery_indices = [i for i, e in enumerate(events) if e.get("type") == "MASTERY_PROC"]
        assert mastery_indices, "Expected at least one MASTERY_PROC event in the dumped event stream."

        for i in mastery_indices:
            assert i - 1 >= 0, f"MASTERY_PROC at index {i} has no previous event."
            assert i + 1 < len(events), f"MASTERY_PROC at index {i} has no next event."

            prev_type = events[i - 1].get("type")
            next_type = events[i + 1].get("type")

            assert prev_type == "EFFECT_EXPIRED", (
                "Expected the event immediately before MASTERY_PROC to be EFFECT_EXPIRED.\n"
                f"Index: {i}\n"
                f"Prev type: {prev_type}\n"
                f"Current: {events[i]}\n"
                f"Prev: {events[i - 1]}\n"
            )
            assert next_type == "TURN_END", (
                "Expected the event immediately after MASTERY_PROC to be TURN_END.\n"
                f"Index: {i}\n"
                f"Next type: {next_type}\n"
                f"Current: {events[i]}\n"
                f"Next: {events[i + 1]}\n"
            )
