import os

import requests
from flask import Flask, jsonify, request


SIDDHI_URL = os.getenv("SIDDHI_URL", "http://siddhi:7071/customer")
SIDDHI_DCR_URL = os.getenv("SIDDHI_DCR_URL", "http://siddhi:7074/customer")
DCR_ACTIONS = {"StartDcrCase", "ExecuteDcrEvent"}

app = Flask(__name__)


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/events")
def submit_event():
    event = request.get_json(silent=True)
    if not isinstance(event, dict):
        return jsonify({"error": "A JSON object is required"}), 400

    order_id = event.get("order_id")
    action = event.get("action")
    if not isinstance(order_id, str) or not order_id.strip():
        return jsonify({"error": "order_id must be a non-empty string"}), 400
    if not isinstance(action, str) or not action.strip():
        return jsonify({"error": "action must be a non-empty string"}), 400

    event_id = event.get("event_id", "")
    if event_id is None:
        event_id = ""
    if not isinstance(event_id, str):
        return jsonify({"error": "event_id must be a string"}), 400
    if action == "ExecuteDcrEvent" and not event_id.strip():
        return jsonify({"error": "event_id is required for ExecuteDcrEvent"}), 400
    graph_title = event.get("graph_title", "")
    if graph_title is None:
        graph_title = ""
    if not isinstance(graph_title, str):
        return jsonify({"error": "graph_title must be a string"}), 400


    if action in DCR_ACTIONS:
        target = SIDDHI_DCR_URL
        body = {
            "order_id": order_id,
            "action": action,
            "event_id": event_id,
            "graph_title": graph_title,
        }
    else:
        target = SIDDHI_URL
        body = {"order_id": order_id, "action": action}

    try:
        response = requests.post(target, json=body, timeout=10)
        response.raise_for_status()
    except requests.RequestException as error:
        app.logger.exception("Failed to forward event to Siddhi")
        upstream_status = error.response.status_code if error.response is not None else None
        return jsonify({
            "error": "Failed to submit event to Siddhi",
            "upstream_status": upstream_status,
        }), 502

    return jsonify({
        "status": "accepted",
        "order_id": order_id,
        "action": action,
    }), 202


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
