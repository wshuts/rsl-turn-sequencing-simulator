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


def test_cli_events_out_contains_five_mastery_proc_events_for_fire_knight_sample() -> None:
    """
    GIVEN the sample battle spec and CLI parameters:
      - boss actor: Fire Knight
      - stop after boss turns: 6
      - row index start: 56
    WHEN we run the CLI with --events-out <path>
    THEN the event output contains exactly 5 events with type == "MASTERY_PROC"
    """
    battle_path = REPO_ROOT / "samples" / "demo_battle_spec_track_shield_state.json"
    assert battle_path.exists(), "Expected sample battle spec to exist in samples/."

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        events_out_path = td_path / "events_out.json"

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

        raw = json.loads(events_out_path.read_text(encoding="utf-8"))
        assert isinstance(raw, list), "Expected dumped event stream to be a JSON array."

        mastery_proc_events = [e for e in raw if e.get("type") == "MASTERY_PROC"]
        assert len(mastery_proc_events) == 5, (
            "Expected exactly 5 MASTERY_PROC events in the dumped event stream.\n"
            f"Actual: {len(mastery_proc_events)}\n"
        )
