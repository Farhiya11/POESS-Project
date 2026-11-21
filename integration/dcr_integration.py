import json
import os
import threading
import uuid
from datetime import datetime, timezone
from urllib.parse import quote

import requests
from flask import Blueprint, current_app, jsonify, request

SIDDHI_CALLBACK_URL = os.getenv("DCR_SIDDHI_CALLBACK_URL", "http://siddhi:7075/middleman")
# SIDDHI_CALLBACK_URL = os.getenv("SIDDHI_CALLBACK_URL", "http://siddhi:7072/middleman")
DCR_SERVICE_URL = os.getenv("DCR_SERVICE_URL", "http://microservice:5001").rstrip("/")
DCR_GRAPH_TITLE = os.getenv("DCR_GRAPH_TITLE", "").strip()

dcr_bp = Blueprint("dcr", __name__)
dcr_simulations = {}
dcr_lock = threading.Lock()


def get_order_id(data):
    event = data.get("event")
    return data.get("order_id") or (event.get("order_id") if isinstance(event, dict) else None)


def get_event_id(data):
    event = data.get("event")
    return data.get("event_id") or (event.get("event_id") if isinstance(event, dict) else None)


def send_callback(order_id, case_id, event, payload):
    body = {
        "order_id": order_id,
        "case_id": str(case_id),
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "role": "dcr",
        "payload": json.dumps(payload),
        "error": "",
    }
    response = requests.post(SIDDHI_CALLBACK_URL, json=body, timeout=30)
    response.raise_for_status()


def events_url(simulation_name, suffix=""):
    encoded = quote(simulation_name, safe="")
    return f"{DCR_SERVICE_URL}/simulations/{encoded}/events{suffix}"


def state_url(simulation_name):
    encoded = quote(simulation_name, safe="")
    return f"{DCR_SERVICE_URL}/simulations/{encoded}/state?only_events=true"


def enabled_events(response):
    return [
        item["event"]
        for item in response.json()
        if isinstance(item, dict)
        and isinstance(item.get("event"), dict)
        and item["event"].get("enabled") is True
    ]


def upstream_status(error):
    return error.response.status_code if error.response is not None else None


@dcr_bp.post("/start_dcr_case")
def start_dcr_case():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "A JSON object is required"}), 400

    order_id = get_order_id(data)
    if not isinstance(order_id, str) or not order_id.strip():
        return jsonify({"error": "order_id must be a non-empty string"}), 400
    graph_title = data.get("graph_title") or DCR_GRAPH_TITLE
    if not isinstance(graph_title, str) or not graph_title.strip():
        current_app.logger.error("DCR_GRAPH_TITLE is not configured")
        return jsonify({"error": "graph_title is required (or configure DCR_GRAPH_TITLE)"}), 400

    with dcr_lock:
        if order_id in dcr_simulations:
            return jsonify({"error": "A DCR simulation already exists for order_id"}), 409
        dcr_simulations[order_id] = None  # reserve while creating

    try:
        response = requests.post(
            f"{DCR_SERVICE_URL}/simulations",
            json={
                "graph_title": graph_title.strip(),
                "simulation_title": f"POESS integration {uuid.uuid4()}",
                "reference_name": order_id,
            },
            timeout=30,
        )
        response.raise_for_status()
        created = response.json()
        simulation_name = created.get("name") if isinstance(created, dict) else None
    except requests.RequestException as error:
        current_app.logger.exception("Failed to create a DCR simulation")
        dcr_simulations.pop(order_id, None)
        return jsonify({
            "error": "Failed to create a DCR simulation",
            "upstream_status": upstream_status(error),
        }), 502

    if not isinstance(simulation_name, str) or not simulation_name:
        dcr_simulations.pop(order_id, None)
        return jsonify({"error": "DCR response did not contain a simulation name"}), 502

    dcr_simulations[order_id] = simulation_name
    try:
        state = requests.get(state_url(simulation_name), timeout=30)
        state.raise_for_status()
        choices = enabled_events(state)
    except requests.RequestException as error:
        current_app.logger.exception("Failed to inspect the new DCR simulation")
        return jsonify({
            "error": "DCR simulation was created but its state could not be read",
            "case_id": simulation_name,
            "upstream_status": upstream_status(error),
        }), 502

    try:
        send_callback(
            order_id,
            simulation_name,
            "DCR Case Started",
            {"enabled_events": choices},
        )
    except requests.RequestException:
        current_app.logger.exception("DCR simulation started, but callback to Siddhi failed")
        return jsonify({
            "error": "DCR simulation started but callback to Siddhi failed",
            "case_id": simulation_name,
        }), 502

    return jsonify({
        "status": "accepted",
        "order_id": order_id,
        "case_id": simulation_name,
        "enabled_events": choices,
    }), 202


@dcr_bp.post("/dcr_event")
def dcr_event():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "A JSON object is required"}), 400

    order_id = get_order_id(data)
    event_id = get_event_id(data)
    if not isinstance(order_id, str) or not order_id.strip():
        return jsonify({"error": "order_id must be a non-empty string"}), 400
    if not isinstance(event_id, str) or not event_id.strip():
        return jsonify({"error": "event_id must be a non-empty string"}), 400

    simulation_name = dcr_simulations.get(order_id)
    if not simulation_name:
        return jsonify({"error": "No DCR simulation known for order_id"}), 404

    try:
        before = requests.get(state_url(simulation_name), timeout=30)
        before.raise_for_status()
        enabled = {
            item.get("id"): item
            for item in enabled_events(before)
            if isinstance(item.get("id"), str)
        }
        if event_id not in enabled:
            current_app.logger.warning(
                "DCR event %s not enabled for order_id=%s; enabled=%s",
                event_id, order_id, list(enabled),
            )
            return jsonify({
                "error": "Event is not currently enabled",
                "enabled_event_ids": list(enabled),
            }), 409

        execute = requests.post(
            events_url(simulation_name),
            json={"event_ids": [event_id]},
            timeout=30,
        )
        execute.raise_for_status()
        after = requests.get(state_url(simulation_name), timeout=30)
        after.raise_for_status()
        choices = enabled_events(after)
    except requests.RequestException as error:
        current_app.logger.exception("DCR event execution failed")
        return jsonify({"error": "DCR event failed", "upstream_status": upstream_status(error)}), 502

    label = enabled[event_id].get("label") or event_id
    try:
        send_callback(
            order_id,
            simulation_name,
            label,
            {"executed_event_id": event_id, "enabled_events": choices},
        )
    except requests.RequestException:
        current_app.logger.exception("DCR event executed, but callback to Siddhi failed")
        return jsonify({"error": "Callback to Siddhi failed", "case_id": simulation_name}), 502

    return jsonify({
        "status": "accepted",
        "case_id": simulation_name,
        "executed_event_id": event_id,
        "enabled_events": choices,
    }), 202