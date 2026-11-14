from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SimulationStatus = Literal["running", "finished"]


@dataclass(frozen=True)
class Overview:
    graphs: dict[str, int]
    simulations: dict[str, dict[str, int]]
    running: dict[str, SimulationStatus]
