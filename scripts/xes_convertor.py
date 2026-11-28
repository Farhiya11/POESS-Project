#!/usr/bin/env python3
"""Convert an XES event log into an importable Process DoCtoR DCR graph.

The XES log provides observed activities, their event attributes, and their
ordering. It does not describe all the rules in a DCR model. By default this
script creates one DCR event per activity and a condition relation for each
directly-following pair observed in a trace. Use ``--relations none`` to make
an unconstrained activity graph instead.

This intentionally does not invent response, include, exclude, milestone,
subprocess, or nesting semantics. Add those rules in Process DoCtoR after
importing the generated graph. XES ``int`` and ``boolean`` values become DCR
``Int`` and ``Bool``; string-like values become ``String``.
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


NS_DCR = "http://tk/schema/dcr"
NS_DI = "http://tk/schema/dcrDi"
NS_DC = "http://www.omg.org/spec/DD/20100524/DC"
ET.register_namespace("dcr", NS_DCR)
ET.register_namespace("dcrDi", NS_DI)
ET.register_namespace("dc", NS_DC)

XES_TYPE_MAP = {
    "string": "String",
    "date": "String",
    "int": "Int",
    "boolean": "Bool",
    # Process DoCtoR Graph (3) shows Int, Bool, and String. XES floats
    # therefore use String until the target format documents a decimal type.
    "float": "String",
    "id": "String",
    "uri": "String",
}
STANDARD_EVENT_KEYS = {"concept:name", "time:timestamp", "org:resource"}


@dataclass(frozen=True)
class XESAttribute:
    value: str
    dcr_type: str


def tag(namespace: str, local_name: str) -> str:
    return f"{{{namespace}}}{local_name}"


def children_named(element: ET.Element, local_name: str) -> list[ET.Element]:
    return [child for child in element if child.tag.rsplit("}", 1)[-1] == local_name]


def attributes(element: ET.Element) -> dict[str, XESAttribute]:
    """Read XES attributes with their types; flatten nested values by key."""
    result: dict[str, XESAttribute] = {}

    def visit(parent: ET.Element, prefix: str = "") -> None:
        for child in parent:
            key = child.get("key")
            if child.tag.rsplit("}", 1)[-1] in {"list", "container"}:
                visit(child, f"{prefix}{key or ''}:")
            else:
                xes_type = child.tag.rsplit("}", 1)[-1]
                value = child.get("value")
                if key is not None and value is not None and xes_type in XES_TYPE_MAP:
                    result[f"{prefix}{key}"] = XESAttribute(
                        value, XES_TYPE_MAP[xes_type]
                    )

    visit(element)
    return result


def event_data_spec(values: list[XESAttribute]) -> dict[str, str]:
    """Choose the common observed type and first value as the DCR default."""
    types = {value.dcr_type for value in values}
    dcr_type = next(iter(types)) if len(types) == 1 else "String"
    default = values[0].value if values else ""
    return {"type": dcr_type, "default": default}


def read_log(path: Path) -> list[tuple[str, list[dict[str, XESAttribute]]]]:
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        raise ValueError(f"Cannot read XES file {path}: {exc}") from exc

    if root.tag.rsplit("}", 1)[-1] != "log":
        raise ValueError("Input XML root must be an XES <log> element")

    traces: list[tuple[str, list[dict[str, XESAttribute]]]] = []
    activities: set[str] = set()
    for index, trace in enumerate(children_named(root, "trace"), start=1):
        trace_attrs = attributes(trace)
        case_name = trace_attrs.get(
            "concept:name", XESAttribute(f"case_{index}", "String")
        ).value
        events: list[dict[str, XESAttribute]] = []
        for event in children_named(trace, "event"):
            event_attrs = attributes(event)
            activity = event_attrs.get(
                "concept:name", XESAttribute("", "String")
            ).value.strip()
            if not activity:
                raise ValueError(f"Trace {case_name!r} contains an event without concept:name")
            activities.add(activity)
            events.append(event_attrs)
        traces.append((case_name, events))

    if not activities:
        raise ValueError("XES log contains no events with concept:name")
    return traces


def build_dcr_graph(
    traces: Iterable[tuple[str, list[dict[str, XESAttribute]]]],
    relation_mode: str,
) -> ET.Element:
    traces = list(traces)
    activity_names = sorted({
        event["concept:name"].value
        for _, events in traces
        for event in events
    })
    event_ids = {
        name: f"Event_{index:04d}"
        for index, name in enumerate(activity_names, 1)
    }

    # Collect non-standard event attributes per activity as DCR event data.
    data_values: dict[str, dict[str, list[XESAttribute]]] = defaultdict(
        lambda: defaultdict(list)
    )
    roles: dict[str, set[str]] = defaultdict(set)
    observed_pairs: set[tuple[str, str]] = set()
    for _, events in traces:
        names = [event["concept:name"].value for event in events]
        if relation_mode == "directly-follows":
            observed_pairs.update(
                (left, right)
                for left, right in zip(names, names[1:])
                if left != right
            )
        for event in events:
            activity = event["concept:name"].value
            role = event.get("org:resource")
            if role:
                roles[activity].add(role.value)
            for key, attribute in event.items():
                if key not in STANDARD_EVENT_KEYS:
                    data_name = key.removeprefix("payload:")
                    data_values[activity][data_name].append(attribute)

    graph = ET.Element(tag(NS_DCR, "dcrGraph"), {"id": "dcrGraph"})
    positions: dict[str, tuple[int, int]] = {}
    columns = 4
    for index, activity in enumerate(activity_names):
        event_id = event_ids[activity]
        x = (index % columns) * 240
        y = (index // columns) * 170
        positions[event_id] = (x, y)
        event_attrs = {
            "id": event_id,
            "description": activity,
            "included": "true",
            "executed": "false",
            "pending": "false",
            "enabled": "true",
        }
        if roles[activity]:
            event_attrs["role"] = ", ".join(sorted(roles[activity]))
        event_node = ET.SubElement(graph, tag(NS_DCR, "event"), event_attrs)
        for data_name in sorted(data_values[activity]):
            ET.SubElement(
                event_node,
                tag(NS_DCR, "eventData"),
                {
                    "name": data_name,
                    **event_data_spec(data_values[activity][data_name]),
                },
            )

    relation_ids: list[tuple[str, str]] = []
    if relation_mode == "directly-follows":
        for index, (source, target) in enumerate(sorted(observed_pairs), 1):
            relation_id = f"Relation_{index:04d}"
            source_id, target_id = event_ids[source], event_ids[target]
            ET.SubElement(
                graph,
                tag(NS_DCR, "relation"),
                {
                    "id": relation_id,
                    "type": "condition",
                    "sourceRef": source_id,
                    "targetRef": target_id,
                },
            )
            relation_ids.append((relation_id, source_id + "\0" + target_id))

    definitions = ET.Element(tag(NS_DCR, "definitions"))
    definitions.append(graph)
    root_board = ET.SubElement(
        definitions, tag(NS_DI, "dcrRootBoard"), {"id": "RootBoard"}
    )
    plane = ET.SubElement(
        root_board,
        tag(NS_DI, "dcrPlane"),
        {"id": "Plane", "boardElement": "dcrGraph"},
    )

    for activity in activity_names:
        event_id = event_ids[activity]
        x, y = positions[event_id]
        shape = ET.SubElement(
            plane,
            tag(NS_DI, "dcrShape"),
            {"id": f"{event_id}_di", "boardElement": event_id},
        )
        ET.SubElement(
            shape,
            tag(NS_DC, "Bounds"),
            {"x": str(x), "y": str(y), "width": "180", "height": "100"},
        )

    for relation_id, refs in relation_ids:
        source_id, target_id = refs.split("\0")
        sx, sy = positions[source_id]
        tx, ty = positions[target_id]
        relation = ET.SubElement(
            plane,
            tag(NS_DI, "relation"),
            {"id": f"{relation_id}_di", "boardElement": relation_id},
        )
        ET.SubElement(relation, tag(NS_DI, "waypoint"), {"x": str(sx + 90), "y": str(sy + 50)})
        ET.SubElement(relation, tag(NS_DI, "waypoint"), {"x": str(tx + 90), "y": str(ty + 50)})

    return definitions


def convert(input_path: Path, output_path: Path, relation_mode: str) -> None:
    traces = read_log(input_path)
    root = build_dcr_graph(traces, relation_mode)
    ET.indent(root, space="  ")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(output_path, encoding="UTF-8", xml_declaration=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="XES input file")
    parser.add_argument("output", type=Path, help="Process DoCtoR XML output file")
    parser.add_argument(
        "--relations",
        choices=("directly-follows", "none"),
        default="directly-follows",
        help="Generate condition links for observed adjacent activities, or no links (default: directly-follows)",
    )
    args = parser.parse_args()
    try:
        convert(args.input, args.output, args.relations)
    except ValueError as exc:
        print(f"xes_convertor: {exc}", file=sys.stderr)
        return 2
    print(f"Wrote Process DoCtoR XML to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
