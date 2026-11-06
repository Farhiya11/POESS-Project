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
