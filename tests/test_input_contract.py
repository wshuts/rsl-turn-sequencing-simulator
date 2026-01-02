from __future__ import annotations

import json
from pathlib import Path

import pytest

from rsl_turn_sequencing.stream_io import InputFormatError, load_event_stream


def test_load_event_stream_happy_path_sample_file() -> None:
    sample = Path(__file__).resolve().parents[1] / "samples" / "demo_event_stream.json"
    events = load_event_stream(sample)
    assert len(events) > 0
    # Strictly increasing by (tick, seq)
    keys = [(e.tick, e.seq) for e in events]
    assert keys == sorted(keys)
    assert len(set(keys)) == len(keys)


def test_load_event_stream_rejects_out_of_order_events(tmp_path: Path) -> None:
    bad = [
        {"tick": 1, "seq": 2, "type": "TICK_START", "actor": None, "data": {}},
        {"tick": 1, "seq": 1, "type": "FILL_COMPLETE", "actor": None, "data": {}},
    ]
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad), encoding="utf-8")

    with pytest.raises(InputFormatError):
        load_event_stream(path)
