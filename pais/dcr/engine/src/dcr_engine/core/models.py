from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from dcr_sdk import Event

SimulationStatus = Literal["running", "finished"]


@dataclass(frozen=True)
class Overview:
    graphs: dict[str, int]
    simulations: dict[str, dict[str, int]]
    running: dict[str, SimulationStatus]


# A DCR event, containers (subgraphs) hold the events inside them
@dataclass(frozen=True)
class EventNode:
    event: Event
    children: list[EventNode]
