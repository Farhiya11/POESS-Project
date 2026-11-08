from __future__ import annotations

import xml.etree.ElementTree as ET

from dcr_sdk.models.models import Event, Graph, Sim, State


class DCR_Parser:

    # COMMON TRANSFORMATIONS FOR DCR GRAPHS
    # This are just private for the class :)
    
    @staticmethod
    def _to_bool(value: str | None) -> bool:
        return (value or "").lower() == "true"

    # DCR sends the text "None" for empty values
    @staticmethod
    def _to_optional(value: str | None) -> str | None:
        return None if value in (None, "None") else value

    # Missing or empty numbers become 0
    @staticmethod
    def _to_int(value: str | None) -> int:
        return int(value) if value else 0

    @staticmethod
    def _to_float(value: str | None) -> float:
        return float(value) if value else 0.0

    # PARSING FUNCTION
    # This will be called by the core/ classes

    @staticmethod
    def parse_graphs(xml: str) -> list[Graph]:
        return [
            Graph(
                id=DCR_Parser._to_int(graph.get("Id")),
                title=graph.get("Title", ""),
                description=graph.get("Description", ""),
                created=graph.get("Created", ""),
                modified=graph.get("Modified", ""),
            )
            for graph in ET.fromstring(xml).iter("graph")
        ]

    @staticmethod
    def parse_sims(xml: str) -> list[Sim]:
        return [
            Sim(
                id=DCR_Parser._to_int(trace.get("id")),
                title=trace.get("title", ""),
                init=trace.get("init", ""),
                percentage=DCR_Parser._to_float(trace.get("percentage")),
                is_scenario=DCR_Parser._to_bool(trace.get("isScenario")),
                created=trace.get("created", ""),
                created_by=DCR_Parser._to_int(trace.get("createdBy")),
                modified=trace.get("modified", ""),
                modified_by=DCR_Parser._to_int(trace.get("modifiedBy")),
                business_type=trace.get("businessType", ""),
            )
            for trace in ET.fromstring(xml).iter("trace")
        ]

    @staticmethod
    def parse_state(xml: str) -> State:
        root = ET.fromstring(xml)
        return State(
            next_delay=DCR_Parser._to_optional(root.get("nextDelay")),
            next_deadline=DCR_Parser._to_optional(root.get("nextDeadline")),
            is_accepting=DCR_Parser._to_bool(root.get("isAccepting")),
            current_time=root.get("currentTime", ""),
            current_phase=DCR_Parser._to_int(root.get("currentPhase")),
            events={
                event.get("id", ""): Event(
                    id=event.get("id", ""),
                    included=DCR_Parser._to_bool(event.get("included")),
                    enabled=DCR_Parser._to_bool(event.get("enabled")),
                    pending=DCR_Parser._to_bool(event.get("pending")),
                    effectively_pending=DCR_Parser._to_bool(
                        event.get("EffectivelyPending")
                    ),
                    effectively_included=DCR_Parser._to_bool(
                        event.get("EffectivelyIncluded")
                    ),
                    executed=DCR_Parser._to_bool(event.get("executed")),
                    full_path=event.get("fullPath", ""),
                    roles=event.get("roles", ""),
                    groups=event.get("groups", ""),
                    description=event.get("description", ""),
                    label=event.get("label", ""),
                    event_type=event.get("eventType", ""),
                    phases=event.get("phases", ""),
                    deadline=event.get("deadline", ""),
                    sequence=DCR_Parser._to_int(event.get("sequence")),
                    parent=event.get("parent", ""),
                    type=event.get("type", ""),
                    refer_id=event.get("referId", ""),
                    event_type_data=event.findtext("eventTypeData") or "",
                )
                for event in root.iter("event")
            },
        )
