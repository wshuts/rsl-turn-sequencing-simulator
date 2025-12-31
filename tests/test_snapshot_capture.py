from rsl_turn_sequencing.engine import step_tick
from rsl_turn_sequencing.event_sink import InMemoryEventSink
from rsl_turn_sequencing.events import EventType
from rsl_turn_sequencing.models import Actor


def make_actors():
    return [
        Actor("Mikage", 340.0),
        Actor("Mithrala", 282.0),
        Actor("Tomblord", 270.0),
        Actor("Coldheart", 265.0),
        Actor("Martyr", 252.0),
        Actor("Boss", 250.0),
    ]


def test_snapshot_captured_at_turn_end_for_requested_turn():
    actors = make_actors()
    sink = InMemoryEventSink()

    # Request snapshot capture at turn 5
    snapshot_turn = 5

    # Advance simulation until at least turn 5 occurs
    for _ in range(snapshot_turn):
        step_tick(
            actors,
            event_sink=sink,
            snapshot_capture={snapshot_turn},
        )

    key = (snapshot_turn, EventType.TURN_END)

    # Snapshot exists
    assert key in sink.snapshots

    snapshot = sink.snapshots[key]

    # Snapshot shape and contents
    assert snapshot["actor"] == "Mikage"
    assert "actors" in snapshot

    names = [a["name"] for a in snapshot["actors"]]
    assert names == [
        "Mikage",
        "Mithrala",
        "Tomblord",
        "Coldheart",
        "Martyr",
        "Boss",
    ]


def test_no_snapshot_captured_when_not_requested():
    actors = make_actors()
    sink = InMemoryEventSink()

    # Advance several turns with no snapshot_capture argument
    for _ in range(5):
        step_tick(
            actors,
            event_sink=sink,
        )
