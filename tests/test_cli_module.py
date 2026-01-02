from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_module(*args: str) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, "-m", "rsl_turn_sequencing", *args]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        cmd, text=True, capture_output=True, cwd=REPO_ROOT, env=env
    )


def test_cli_help_succeeds() -> None:
    p = _run_module("--help")
    assert p.returncode == 0, p.stderr
    combined = (p.stdout or "") + (p.stderr or "")
    assert "RSL Turn Sequencing Simulator" in combined


def test_cli_input_run_produces_boss_frame() -> None:
    sample = REPO_ROOT / "samples" / "demo_event_stream.json"
    assert sample.exists()
    p = _run_module("run", "--input", str(sample))
    assert p.returncode == 0, p.stderr
    assert "Boss Turn #1" in (p.stdout or "")


def test_cli_rejects_demo_and_input_together() -> None:
    sample = REPO_ROOT / "samples" / "demo_event_stream.json"
    p = _run_module("run", "--demo", "--input", str(sample))
    assert p.returncode != 0
    assert "choose exactly one" in (p.stderr or "")


def test_cli_demo_run_produces_boss_frame() -> None:
    # Use enough ticks to guarantee at least one complete boss frame.
    p = _run_module("run", "--demo", "--ticks", "400")
    assert p.returncode == 0, p.stderr
    combined = (p.stdout or "") + (p.stderr or "")
    assert "Boss Turn #1" in combined
