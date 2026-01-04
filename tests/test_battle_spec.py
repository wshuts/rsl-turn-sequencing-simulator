from __future__ import annotations

import json
from pathlib import Path

import pytest

from rsl_turn_sequencing.stream_io import InputFormatError, load_battle_spec


def test_load_battle_spec_happy_path(tmp_path: Path) -> None:
    p = tmp_path / "battle.json"
    p.write_text(
        json.dumps(
            {
                "boss": {"name": "Boss", "speed": 250, "faction": "Demonspawn"},
                "actors": [
                    {"name": "A", "speed": 200, "faction": "Shadowkin"},
                    {
                        "name": "B",
                        "speed": 210,
                        "faction": "Undead Hordes",
                        "form_start": "Alt",
                        "speed_by_form": {"Alt": 333},
                        "metamorph": {"cooldown_turns": 4},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    spec = load_battle_spec(p)
    assert spec.boss.name == "Boss"
    assert spec.boss.speed == 250.0
    assert spec.boss.faction == "Demonspawn"
    assert [a.name for a in spec.actors] == ["A", "B"]
    assert [a.faction for a in spec.actors] == ["Shadowkin", "Undead Hordes"]
    assert spec.actors[1].form_start == "Alt"
    assert spec.actors[1].speed_by_form == {"Alt": 333.0}
    assert spec.actors[1].metamorph == {"cooldown_turns": 4}


@pytest.mark.parametrize(
    "payload, msg",
    [
        ({}, "boss"),
        ({"boss": {"name": "Boss", "speed": 250}}, "actors"),
        ({"boss": "nope", "actors": []}, "boss"),
        ({"boss": {"name": "", "speed": 250}, "actors": [{"name": "A", "speed": 200}]}, "boss.name"),
        ({"boss": {"name": "Boss", "speed": "fast"}, "actors": [{"name": "A", "speed": 200}]}, "boss.speed"),
        ({"boss": {"name": "Boss", "speed": 250}, "actors": []}, "non-empty"),
        ({"boss": {"name": "Boss", "speed": 250}, "actors": ["A"]}, "actors[0]"),
        (
                {
                    "boss": {"name": "Boss", "speed": 250},
                    "actors": [{"name": "A", "speed": 200, "speed_by_form": []}],
                },
                "speed_by_form",
        ),
        ({"boss": {"name": "Boss", "speed": 250, "faction": 123}, "actors": [{"name": "A", "speed": 200}]},
         "boss.faction must be a non-empty string when provided"),
        ({"boss": {"name": "Boss", "speed": 250}, "actors": [{"name": "A", "speed": 200, "faction": ""}]},
         "actors[0].faction must be a non-empty string when provided"),
    ],
)
def test_load_battle_spec_rejects_bad_inputs(tmp_path: Path, payload: dict, msg: str) -> None:
    p = tmp_path / "battle.json"
    p.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(InputFormatError) as e:
        load_battle_spec(p)

    assert msg in str(e.value)
