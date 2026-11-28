from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from constants import (
    DMI_BASE_URL,
    DMI_FORECAST_PATH,
    DMI_OBSERVATIONS_PATH,
    DMI_TIMEOUT_SECONDS,
    FORECAST_COLLECTION,
    FORECAST_PARAMETER,
    OBSERVATION_HOURS_BACK,
    OBSERVATION_PARAMETER,
)
from models import SeaLevelForecast, WaterLevelObservation

from .parser import DMIParser


class DMIRequestError(RuntimeError):
    """DMI could not be reached or answered with an error status."""


class DMIClient:
    """Small SDK over the two DMI open data endpoints we use."""

    def __init__(
        self,
        session: requests.Session | None = None,
        parser: DMIParser | None = None,
        base_url: str = DMI_BASE_URL,
    ) -> None:
        self.session = session or requests.Session()
        self.parser = parser or DMIParser()
        self.base_url = base_url

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            resp = self.session.get(f"{self.base_url}{path}", params=params, timeout=DMI_TIMEOUT_SECONDS)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            raise DMIRequestError(f"DMI request to {path} failed: {exc}") from exc

    def observations(self, station_id: str, hours_back: int = OBSERVATION_HOURS_BACK) -> list[WaterLevelObservation]:
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=hours_back)
        payload = self._get(DMI_OBSERVATIONS_PATH, {
            "stationId": station_id,
            "parameterId": OBSERVATION_PARAMETER,
            "datetime": f"{start:%Y-%m-%dT%H:%M:%SZ}/{end:%Y-%m-%dT%H:%M:%SZ}",
            "sortorder": "observed,DESC",
            "limit": 500,
        })
        return self.parser.observations(payload)

    def forecast(
        self, location_id: str, lon: float, lat: float, collection: str = FORECAST_COLLECTION
    ) -> list[SeaLevelForecast]:
        payload = self._get(DMI_FORECAST_PATH.format(collection=collection), {
            "coords": f"POINT({lon} {lat})",
            "parameter-name": FORECAST_PARAMETER,
            "crs": "crs84",
            "f": "CoverageJSON",
        })
        return self.parser.forecast(payload, location_id, collection=collection)
