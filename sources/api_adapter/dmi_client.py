"""Thin clients for the two DMI Open Data endpoints + parsers into dataclasses.

Endpoints
- Observations: GET {base}/v2/oceanObs/collections/observation/items
    params: stationId, parameterId=sealev_dvr, datetime=<start>/<end>, limit, sortorder
    returns: GeoJSON FeatureCollection; properties.observed, properties.value (cm)
- Forecast:     GET {base}/v1/forecastedr/collections/{collection}/position
    params: coords=POINT(lon lat), parameter-name=sea-mean-deviation, crs=crs84, f=CoverageJSON
    returns: CoverageJSON; domain.axes.t.values + ranges[param].values (metres)

Parsing is kept separate from HTTP so it can be tested on mock_data/ offline.
"""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from models import SeaLevelForecast, WaterLevelObservation

DMI_BASE_URL = os.getenv("DMI_BASE_URL", "https://opendataapi.dmi.dk")
DMI_API_KEY = os.getenv("DMI_API_KEY", "")  # optional; DMI open data no longer requires one
FORECAST_PARAMETER = "sea-mean-deviation"
MOCK_DIR = Path(__file__).parent / "tests" / "mock_data"


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


# ---------- parsers ----------

def parse_observations(payload: dict) -> list[WaterLevelObservation]:
    events = []
    for feature in payload.get("features", []):
        props = feature.get("properties", {})
        if props.get("value") is None:
            continue
        events.append(WaterLevelObservation(
            station_id=str(props["stationId"]),
            observed_at=_parse_time(props["observed"]).isoformat(),
            sea_level_cm=float(props["value"]),
            parameter_id=props.get("parameterId", "sealev_dvr"),
        ))
    return sorted(events, key=lambda e: e.observed_at)


def parse_forecast(payload: dict, location_id: str, issued_at: datetime | None = None,
                   collection: str = "dkss_nsbs") -> list[SeaLevelForecast]:
    axes = payload["domain"]["axes"]
    lon, lat = axes["x"]["values"][0], axes["y"]["values"][0]
    times = axes["t"]["values"]
    values = payload["ranges"][FORECAST_PARAMETER]["values"]
    issued_at = issued_at or datetime.now(timezone.utc)

    events = []
    for t, v in zip(times, values):
        if v is None:
            continue
        valid = _parse_time(t)
        if valid < issued_at:  # skip time steps already in the past
            continue
        events.append(SeaLevelForecast(
            location_id=location_id,
            lon=float(lon),
            lat=float(lat),
            forecast_for=valid.isoformat(),
            sea_level_cm=round(float(v) * 100, 1),  # DKSS gives metres
            lead_time_hours=round((valid - issued_at).total_seconds() / 3600, 2),
            collection=collection,
        ))
    return events


# ---------- HTTP ----------

def _get(path: str, params: dict) -> dict:
    headers = {"X-Gravitee-Api-Key": DMI_API_KEY} if DMI_API_KEY else {}
    resp = requests.get(f"{DMI_BASE_URL}{path}", params=params, headers=headers, timeout=90)
    resp.raise_for_status()
    return resp.json()


def fetch_observations(station_id: str, hours_back: int = 3, mock: bool = False) -> list[WaterLevelObservation]:
    if mock:
        return parse_observations(json.loads((MOCK_DIR / "ocean_obs.json").read_text()))
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours_back)
    payload = _get("/v2/oceanObs/collections/observation/items", {
        "stationId": station_id,
        "parameterId": "sealev_dvr",
        "datetime": f"{start:%Y-%m-%dT%H:%M:%SZ}/{end:%Y-%m-%dT%H:%M:%SZ}",
        "sortorder": "observed,DESC",
        "limit": 500,
    })
    return parse_observations(payload)


def fetch_forecast(location_id: str, lon: float, lat: float, collection: str = "dkss_nsbs",
                   mock: bool = False) -> list[SeaLevelForecast]:
    if mock:
        payload = json.loads((MOCK_DIR / "forecast_edr.json").read_text())
        issued = _parse_time(payload["domain"]["axes"]["t"]["values"][0])
        return parse_forecast(payload, location_id, issued_at=issued, collection=collection)
    payload = _get(f"/v1/forecastedr/collections/{collection}/position", {
        "coords": f"POINT({lon} {lat})",
        "parameter-name": FORECAST_PARAMETER,
        "crs": "crs84",
        "f": "CoverageJSON",
    })
    return parse_forecast(payload, location_id, collection=collection)
