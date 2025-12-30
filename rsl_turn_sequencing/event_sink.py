from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from rsl_turn_sequencing.events import Event, EventType


class EventSink(Protocol):
    """
    Consumer of structured events.
    The engine must be able to run with event_sink=None (no events).
    """

    def start_tick(self) -> int: ...

    def emit(self, event_type: EventType, actor: str | None = None, **data: object) -> None: ...


@dataclass(slots=True)
class InMemoryEventSink:
    """
    Simple sink for tests/demos.
    Owns tick/seq numbering so the engine stays free of global state.
    """

    events: list[Event] = field(default_factory=list)
    _tick: int = 0
    _seq: int = 0

    @property
    def current_tick(self) -> int:
        return self._tick

    def start_tick(self) -> int:
        self._tick += 1
        self._seq = 0
        return self._tick

    def emit(self, event_type: EventType, actor: str | None = None, **data: object) -> None:
        if self._tick <= 0:
            raise RuntimeError("EventSink.start_tick() must be called before emitting events.")
        self._seq += 1
        self.events.append(
            Event(
                tick=self._tick,
                seq=self._seq,
                type=event_type,
                actor=actor,
                data=dict(data),
            )
        )
