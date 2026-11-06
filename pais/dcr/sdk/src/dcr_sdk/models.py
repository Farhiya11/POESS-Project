from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Graph:
    id: int
    title: str
    description: str
    created: str
    modified: str
