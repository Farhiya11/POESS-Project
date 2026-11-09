from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Graph:
    id: int
    title: str
    description: str
    created: str
    modified: str


@dataclass(frozen=True)
class Sim:
    id: int
    title: str
    init: str
    percentage: float
    is_scenario: bool
    created: str
    created_by: int
    modified: str
    modified_by: int
    business_type: str


@dataclass(frozen=True)
class Event:
    id: str
    label: str
    event_type: str
    # EVENT STATE
    included: bool
    enabled: bool
    pending: bool
    effectively_pending: bool
    effectively_included: bool
    executed: bool
    # EVENT METADATA
    full_path: str
    roles: str
    groups: str
    description: str
    phases: str
    deadline: str
    sequence: int
    parent: str
    type: str
    refer_id: str
    event_type_data: str

    # Subprocess and nesting boxes only group activities, they can't be
    # executed (DCR answers 400 "... cannot be executed as it is a sub-process")
    @property
    def is_container(self) -> bool:
        return self.type.lower() in ("subprocess", "nesting")


@dataclass(frozen=True)
class State:
    next_delay: str | None
    next_deadline: str | None
    is_accepting: bool
    current_time: str
    current_phase: int
    events: dict[str, Event]

    # ========= Expanded Arsenary of Function ===================

    # Activities that can be executed right now
    def enabled(self) -> list[Event]:
        events = self.events.values()
        return [e for e in events if e.enabled and not e.is_container]

    def pending(self) -> list[Event]:
        events = self.events.values()
        return [e for e in events if e.pending and e.included]
