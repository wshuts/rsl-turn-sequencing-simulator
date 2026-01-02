from __future__ import annotations

import subprocess
import sys


def _run_module(*args: str) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, "-m", "rsl_turn_sequencing", *args]
    return subprocess.run(cmd, text=True, capture_output=True)


def test_cli_help_succeeds() -> None:
    p = _run_module("--help")
    assert p.returncode == 0
    assert "RSL Turn Sequencing Simulator" in p.stdout


def test_cli_demo_run_produces_boss_frame() -> None:
    # Use enough ticks to guarantee at least one complete boss frame.
    p = _run_module("run", "--demo", "--ticks", "400")
    assert p.returncode == 0, p.stderr
    assert "Boss Turn #1" in p.stdout
