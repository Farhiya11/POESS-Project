from __future__ import annotations

import xml.etree.ElementTree as ET

from dcr_sdk.models import Graph


def parse_graphs(xml: str) -> list[Graph]:
    return [
        Graph(
            id=int(graph.get("Id", "0")),
            title=graph.get("Title", ""),
            description=graph.get("Description", ""),
            created=graph.get("Created", ""),
            modified=graph.get("Modified", ""),
        )
        for graph in ET.fromstring(xml).iter("graph")
    ]
