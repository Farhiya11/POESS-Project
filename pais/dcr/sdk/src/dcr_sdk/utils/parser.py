from __future__ import annotations

import xml.etree.ElementTree as ET

from dcr_sdk.models.models import Graph, Sim


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


def parse_sims(xml: str) -> list[Sim]:
    return [
        Sim(
            id=int(trace.get("id", "0")),
            title=trace.get("title", ""),
            init=trace.get("init", ""),
            percentage=float(trace.get("percentage", "0")),
            is_scenario=trace.get("isScenario") == "true",
            created=trace.get("created", ""),
            created_by=int(trace.get("createdBy", "0")),
            modified=trace.get("modified", ""),
            modified_by=int(trace.get("modifiedBy", "0")),
            business_type=trace.get("businessType", ""),
        )
        for trace in ET.fromstring(xml).iter("trace")
    ]
