from flask import Flask, request, jsonify
from datetime import datetime, timezone
from pathlib import Path
import json
import os
from threading import Lock
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

app = Flask(__name__)

LOG_ROOT = Path(os.getenv("EVENT_LOG_ROOT", "/data"))
EVENT_ENGINES = ("bpmn", "dcr")
EVENT_LOG_TIMEZONE_NAME = os.getenv("EVENT_LOG_TIMEZONE", "Europe/Copenhagen")
try:
    EVENT_LOG_TIMEZONE = ZoneInfo(EVENT_LOG_TIMEZONE_NAME)
except ZoneInfoNotFoundError as error:
    raise RuntimeError(
        f"Unknown EVENT_LOG_TIMEZONE: {EVENT_LOG_TIMEZONE_NAME}"
    ) from error


def make_run_id(timestamp: datetime | None = None) -> str:
    """Format a timestamp in the configured timezone, including its UTC offset."""
    timestamp = timestamp or datetime.now(timezone.utc)
    return timestamp.astimezone(EVENT_LOG_TIMEZONE).strftime("%y%m%d_%H%M%S%z")


RUN_ID = make_run_id()
EVENT_STORE_LOCKS = {engine: Lock() for engine in EVENT_ENGINES}


def event_store_path(engine: str) -> Path:
    return LOG_ROOT / engine / "json" / f"{RUN_ID}_events.json"


def xes_file_path(engine: str) -> Path:
    return LOG_ROOT / engine / "xes" / f"{RUN_ID}_process_log.xes"


for engine in EVENT_ENGINES:
    (LOG_ROOT / engine / "json").mkdir(parents=True, exist_ok=True)
    (LOG_ROOT / engine / "xes").mkdir(parents=True, exist_ok=True)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_event_payload(data):
    payload = data.get("event") if isinstance(data, dict) and "event" in data and isinstance(data["event"], dict) else data

    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError):
            payload = {}

    event_name = payload.get("event") or payload.get("activity") or payload.get("name") or "unknown"
    timestamp = payload.get("timestamp") or utc_now_iso()
    case_id = payload.get("case_id") or payload.get("case") or payload.get("trace_id") or "UNKNOWN_CASE"
    order_id = payload.get("order_id")
    role = payload.get("role") or payload.get("user") or payload.get("actor") or "system"
    engine = str(payload.get("process_engine") or "BPMN").strip().lower()
    if engine not in EVENT_ENGINES:
        raise ValueError("process_engine must be BPMN or DCR")
    error = payload.get("error")
    payload_data = payload.get("payload") or {}

    if isinstance(payload_data, str):
        try:
            payload_data = json.loads(payload_data)
        except (TypeError, ValueError):
            payload_data = {"raw": payload_data}

    standard_fields = {
        "case_id",
        "order_id",
        "event",
        "activity",
        "name",
        "timestamp",
        "role",
        "user",
        "actor",
        "error",
        "payload",
        "process_engine",
    }
    source_fields = {
        key: value
        for key, value in payload.items()
        if key not in standard_fields and value is not None
    }
    if isinstance(payload_data, dict):
        payload_data = {**source_fields, **payload_data}

    return {
        "case_id": str(case_id),
        "order_id": str(order_id) if order_id is not None else "",
        "event": str(event_name),
        "timestamp": str(timestamp),
        "role": str(role),
        "process_engine": engine,
        "error": str(error) if error is not None else "",
        "payload": payload_data,
    }


def write_json_store(events, event_store):
    with open(event_store, "w", encoding="utf-8") as f:
        json.dump(events, f, indent=2)


def xes_attribute_value(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def build_xes(events, xes_file):
    root = ET.Element(
        "log",
        {
            "xes.version": "2.0",
            "xes.features": "nested-attributes",
            "openxes.version": "1.0RC7",
        },
    )

    ET.SubElement(
        root,
        "extension",
        {
            "name": "concept",
            "prefix": "concept",
            "uri": "http://www.xes-standard.org/concept.xesext",
        },
    )
    ET.SubElement(
        root,
        "extension",
        {
            "name": "time",
            "prefix": "time",
            "uri": "http://www.xes-standard.org/time.xesext",
        },
    )
    ET.SubElement(
        root,
        "extension",
        {
            "name": "org",
            "prefix": "org",
            "uri": "http://www.xes-standard.org/org.xesext",
        },
    )

    global_trace = ET.SubElement(root, "global", {"scope": "trace"})
    ET.SubElement(global_trace, "string", {"key": "concept:name", "value": "name"})

    global_event = ET.SubElement(root, "global", {"scope": "event"})
    ET.SubElement(global_event, "string", {"key": "concept:name", "value": "name"})
    ET.SubElement(global_event, "date", {"key": "time:timestamp", "value": "2024-01-01T00:00:00.000+00:00"})
    ET.SubElement(global_event, "string", {"key": "org:resource", "value": "resource"})

    ET.SubElement(root, "classifier", {"name": "Event Name", "keys": "concept:name"})

    grouped = {}
    for event in events:
        case_id = event.get("case_id", "UNKNOWN_CASE")
        grouped.setdefault(case_id, []).append(event)

    for case_id, case_events in grouped.items():
        trace = ET.SubElement(root, "trace")
        ET.SubElement(trace, "string", {"key": "concept:name", "value": str(case_id)})

        for event in case_events:
            event_el = ET.SubElement(trace, "event")
            ET.SubElement(event_el, "string", {"key": "concept:name", "value": str(event.get("event", "unknown"))})
            ET.SubElement(
                event_el,
                "string",
                {
                    "key": "process_engine",
                    "value": str(event.get("process_engine", "bpmn")).upper(),
                },
            )
            ET.SubElement(event_el, "date", {"key": "time:timestamp", "value": str(event.get("timestamp", utc_now_iso()))})
            ET.SubElement(event_el, "string", {"key": "org:resource", "value": str(event.get("role", "system"))})

            if event.get("order_id"):
                ET.SubElement(event_el, "string", {"key": "order_id", "value": str(event["order_id"])})
            if event.get("case_id"):
                ET.SubElement(event_el, "string", {"key": "case_id", "value": str(event["case_id"])})
            if event.get("error"):
                ET.SubElement(event_el, "string", {"key": "error", "value": str(event["error"])})

            payload = event.get("payload") or {}
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except (TypeError, ValueError):
                    payload = {"raw": payload}

            if isinstance(payload, dict):
                for key, value in payload.items():
                    if value is None:
                        continue
                    ET.SubElement(
                        event_el,
                        "string",
                        {
                            "key": f"payload:{key}",
                            "value": xes_attribute_value(value),
                        },
                    )
            elif payload is not None:
                ET.SubElement(event_el, "string", {"key": "payload:raw", "value": str(payload)})

    ET.indent(root)
    tree = ET.ElementTree(root)
    tree.write(xes_file, encoding="utf-8", xml_declaration=True)


@app.route("/log", methods=["POST"])
def log_event():
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({"status": "invalid", "message": "No JSON payload received"}), 400

    try:
        event = normalize_event_payload(data)
    except ValueError as error:
        return jsonify({"status": "invalid", "message": str(error)}), 400

    engine = event["process_engine"]
    event_store = event_store_path(engine)
    xes_file = xes_file_path(engine)

    with EVENT_STORE_LOCKS[engine]:
        try:
            if event_store.exists():
                with open(event_store, "r", encoding="utf-8") as f:
                    events = json.load(f)
            else:
                events = []
        except (json.JSONDecodeError, OSError):
            events = []

        events.append(event)
        write_json_store(events, event_store)
        build_xes(events, xes_file)

    print(
        f"[XES] Logged engine={engine} event={event['event']} "
        f"case_id={event['case_id']} ts={event['timestamp']}",
        flush=True,
    )
    return jsonify(
        {
            "status": "logged",
            "process_engine": engine.upper(),
            "json_file": str(event_store),
            "xes_file": str(xes_file),
        }
    ), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5010)
