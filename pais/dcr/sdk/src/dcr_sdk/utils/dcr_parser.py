# This is because for defailt any will do a linting error
# I want to ignore that on the IDE(s)
# _get returns Any on purpose: the "kind" argument decides the type
# pyright: reportAny=false, reportExplicitAny=false
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from dcr_sdk.models import Event, Graph, Sim, State


class DCR_Parser:
    # COMMON TRANSFORMATIONS FOR DCR GRAPHS
    # This are just private for the class :)

    @staticmethod
    def _get(element: ET.Element, key: str, kind: str = "str") -> Any:
        value = element.get(key)
        match kind:
            case "bool":
                return (value or "").lower() == "true"
            case "int":
                return int(value) if value else 0
            case "float":
                return float(value) if value else 0.0
            case "optional":
                return None if value in (None, "None") else value
            case _:
                return value or ""

    # PARSING FUNCTION
    # This will be called by the core/ classes

    @staticmethod
    def parse_graphs(xml: str) -> list[Graph]:
        get = DCR_Parser._get
        return [
            Graph(
                id=get(graph, "Id", "int"),
                title=get(graph, "Title"),
                description=get(graph, "Description"),
                created=get(graph, "Created"),
                modified=get(graph, "Modified"),
            )
            for graph in ET.fromstring(xml).iter("graph")
        ]

    @staticmethod
    def parse_sims(xml: str) -> list[Sim]:
        get = DCR_Parser._get
        return [
            Sim(
                id=get(trace, "id", "int"),
                title=get(trace, "title"),
                init=get(trace, "init"),
                percentage=get(trace, "percentage", "float"),
                is_scenario=get(trace, "isScenario", "bool"),
                created=get(trace, "created"),
                created_by=get(trace, "createdBy", "int"),
                modified=get(trace, "modified"),
                modified_by=get(trace, "modifiedBy", "int"),
                business_type=get(trace, "businessType"),
            )
            for trace in ET.fromstring(xml).iter("trace")
        ]

    @staticmethod
    def parse_state(xml: str) -> State:
        get = DCR_Parser._get
        root = ET.fromstring(xml)
        return State(
            next_delay=get(root, "nextDelay", "optional"),
            next_deadline=get(root, "nextDeadline", "optional"),
            is_accepting=get(root, "isAccepting", "bool"),
            current_time=get(root, "currentTime"),
            current_phase=get(root, "currentPhase", "int"),
            events={
                get(event, "id"): Event(
                    id=get(event, "id"),
                    included=get(event, "included", "bool"),
                    enabled=get(event, "enabled", "bool"),
                    pending=get(event, "pending", "bool"),
                    effectively_pending=get(
                        event, "EffectivelyPending", "bool"
                    ),
                    effectively_included=get(
                        event, "EffectivelyIncluded", "bool"
                    ),
                    executed=get(event, "executed", "bool"),
                    full_path=get(event, "fullPath"),
                    roles=get(event, "roles"),
                    groups=get(event, "groups"),
                    description=get(event, "description"),
                    label=get(event, "label"),
                    event_type=get(event, "eventType"),
                    phases=get(event, "phases"),
                    deadline=get(event, "deadline"),
                    sequence=get(event, "sequence", "int"),
                    parent=get(event, "parent"),
                    type=get(event, "type"),
                    refer_id=get(event, "referId"),
                    event_type_data=event.findtext("eventTypeData", ""),
                )
                for event in root.iter("event")
            },
        )
