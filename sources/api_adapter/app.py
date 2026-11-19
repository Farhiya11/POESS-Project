"""API adapter: polls DMI open data and forwards normalised events to the CEP layer.

Routes
  GET  /health
  POST /ingest/observations   pull latest water levels for all stations -> forward
  POST /ingest/forecast       pull forecasts for all locations -> forward
  GET  /events?limit=50       last events sent (debugging)
  POST /replay                body: {"events": [...]} forward custom events (demo / tests)

Env
  EVENT_SINK_URL     where events are POSTed, one JSON per request (Siddhi HTTP source)
  STATIONS           comma-separated DMI station ids       (default 30336 = Copenhagen/Kbh Havn)
  FORECAST_POINTS    "id:lon:lat,..."                      (default Copenhagen)
  POLL_SECONDS       background polling interval, 0 = off  (default 0)
  MOCK_DMI           "true" = read mock_data/ instead of DMI
"""
import logging
import os
import threading
import time
from collections import deque

import requests
from flask import Flask, jsonify, request

import dmi_client

EVENT_SINK_URL = os.getenv("EVENT_SINK_URL", os.getenv("INTEGRATION_URL", "http://siddhi:8006/dmi"))
STATIONS = [s for s in os.getenv("STATIONS", "30336").split(",") if s]
FORECAST_POINTS = os.getenv("FORECAST_POINTS", "copenhagen:12.70:55.70")
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "0"))
MOCK_DMI = os.getenv("MOCK_DMI", "false").lower() == "true"

log = logging.getLogger("api_adapter")
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
sent_events: deque = deque(maxlen=500)
_last_seen: dict[str, str] = {}  # station_id -> last observed_at forwarded (dedup)


def parse_points(spec: str) -> list[tuple[str, float, float]]:
    points = []
    for item in filter(None, spec.split(",")):
        loc, lon, lat = item.split(":")
        points.append((loc, float(lon), float(lat)))
    return points


def forward(event: dict) -> bool:
    try:
        requests.post(EVENT_SINK_URL, json={"event": event}, timeout=10).raise_for_status()
        ok = True
    except requests.RequestException as exc:
        log.warning("forward failed: %s", exc)
        ok = False
    sent_events.append({**event, "forwarded": ok})
    return ok


def ingest_observations() -> dict:
    sent = skipped = 0
    for station in STATIONS:
        for obs in dmi_client.fetch_observations(station, mock=MOCK_DMI):
            if obs.observed_at <= _last_seen.get(station, ""):
                skipped += 1
                continue
            forward(obs.to_event())
            _last_seen[station] = obs.observed_at
            sent += 1
    return {"sent": sent, "skipped_duplicates": skipped}


def ingest_forecast() -> dict:
    sent = 0
    for loc, lon, lat in parse_points(FORECAST_POINTS):
        for fc in dmi_client.fetch_forecast(loc, lon, lat, mock=MOCK_DMI):
            forward(fc.to_event())
            sent += 1
    return {"sent": sent}


@app.get("/health")
def health():
    return jsonify({"status": "ok", "mock": MOCK_DMI, "sink": EVENT_SINK_URL})


@app.post("/ingest/observations")
def route_observations():
    try:
        return jsonify(ingest_observations())
    except requests.RequestException as exc:
        return jsonify({"error": f"DMI request failed: {exc}"}), 502


@app.post("/ingest/forecast")
def route_forecast():
    try:
        return jsonify(ingest_forecast())
    except requests.RequestException as exc:
        return jsonify({"error": f"DMI request failed: {exc}"}), 502


@app.get("/events")
def route_events():
    limit = int(request.args.get("limit", 50))
    return jsonify(list(sent_events)[-limit:])


@app.post("/replay")
def route_replay():
    events = (request.get_json(force=True) or {}).get("events", [])
    results = [forward(e) for e in events]
    return jsonify({"sent": sum(results), "failed": len(results) - sum(results)})


def poll_loop():
    while True:
        for job in (ingest_observations, ingest_forecast):
            try:
                log.info("%s: %s", job.__name__, job())
            except Exception as exc:  # keep polling on transient errors
                log.warning("%s failed: %s", job.__name__, exc)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    if POLL_SECONDS > 0:
        threading.Thread(target=poll_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=5000)
