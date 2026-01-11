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


def test_cli_integration_user_proc_request_emits_mastery_proc_on_engine_buff_expiration() -> None:
    """
    CLI Integration Test 1 — Wiring + Causality (no effect math assertions yet)

    Goal:
      Prove that CLI-declared mastery proc requests are consumed by the engine
      AND are consulted when a real engine-owned BUFF expiration occurs,
      producing a MASTERY_PROC event.

    Evidence:
      - At least one EFFECT_EXPIRED event exists where placed_by == "Mikage"
        and reason == "duration_reached_zero"
      - At least one MASTERY_PROC event exists with:
          holder == "Mikage"
          mastery == "rapid_response"
          count == 1

    Notes:
      - This test intentionally assumes new CLI plumbing:
          * --events-out <path> dumps sink.events to JSON (via stream_io.dump_event_stream)
          * battle spec can include turn_overrides.proc_request.on_step[...] which
            is wired into mastery_proc_requester.
      - Today, this is expected to FAIL (RED). We'll implement the CLI bridge next.
    """
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        battle_path = td_path / "battle_cli_integration_1.json"
        events_out_path = td_path / "events_out.json"

        # Provide proc requests for multiple turn_counter values to avoid brittle coupling
        # to the exact expiration step number during early integration.
        on_step: dict[str, dict] = {}
        for k in range(1, 21):
            on_step[str(k)] = {
                "mastery_procs": [
                    {"holder": "Mikage", "mastery": "rapid_response", "count": 1}
                ]
            }

        battle_spec = {
            "boss": {"name": "Boss", "speed": 1500, "shield_max": 21},
            "actors": [
                {
                    "name": "Mikage",
                    "speed": 2000,
                    # Ensure Mikage uses Base A3 (B_A3) early to place the BUFFs.
                    # IMPORTANT: provide a long sequence so we don't fail early due to
                    # ally turn volume before the boss completes 4 turns.
                    "skill_sequence": ["B_A3"] + ["B_A1"] * 60,
                },
                {
                    "name": "A1",
                    "speed": 1900,
                    "skill_sequence": ["A_A1"] * 80,
                },
            ],
            "options": {"sequence_policy": "error_if_exhausted"},
            # Proposed CLI integration surface for proc requests:
            "turn_overrides": {
                "proc_request": {
                    "on_step": on_step
                }
            },
        }

        battle_path.write_text(json.dumps(battle_spec, indent=2), encoding="utf-8")

        # Proposed CLI integration surface for event dump:
        p = _run_module(
            "run",
            "--battle",
            str(battle_path),
            "--ticks",
            "600",
            "--stop-after-boss-turns",
            "4",
            "--events-out",
            str(events_out_path),
        )

        # Once implemented, CLI should succeed and create the event stream file.
        assert p.returncode == 0, (
            "Expected CLI run to succeed (returncode 0).\n"
            f"STDOUT:\n{p.stdout}\n"
            f"STDERR:\n{p.stderr}\n"
        )
        assert events_out_path.exists(), "Expected CLI to create the --events-out JSON file."

        raw = json.loads(events_out_path.read_text(encoding="utf-8"))
        assert isinstance(raw, list), "Expected dumped event stream to be a JSON array."

        expired = [
            e for e in raw
            if e.get("type") == "EFFECT_EXPIRED"
            and isinstance(e.get("data"), dict)
            and e["data"].get("placed_by") == "Mikage"
            and e["data"].get("reason") == "duration_reached_zero"
        ]
        assert expired, "Expected at least one engine-owned Mikage BUFF expiration (EFFECT_EXPIRED)."

        procs = [
            e for e in raw
            if e.get("type") == "MASTERY_PROC"
            and isinstance(e.get("data"), dict)
            and e["data"].get("holder") == "Mikage"
            and e["data"].get("mastery") == "rapid_response"
            and e["data"].get("count") == 1
        ]
        assert procs, "Expected at least one MASTERY_PROC event for Mikage rapid_response count=1."
