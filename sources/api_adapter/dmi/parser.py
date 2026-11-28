from datetime import datetime, timezone
from typing import Any

from constants import (
    FORECAST_COLLECTION,
    FORECAST_PARAMETER,
    OBSERVATION_PARAMETER,
)
from models import SeaLevelForecast, WaterLevelObservation


class DMIParseError(ValueError):
    """DMI answered but the body does not have the shape we expect."""


class DMIParser:
    """Turns raw DMI responses into normalized water-level data."""

    @staticmethod
    def parse_time(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    def observations(self, payload: dict[str, Any]) -> list[WaterLevelObservation]:
        """oceanObs GeoJSON -> observations, oldest first; drop missing values."""
        if "features" not in payload:
            raise DMIParseError("oceanObs response has no 'features'")
        observations: list[WaterLevelObservation] = []
        for feature in payload["features"]:
            props = feature.get("properties", {})
            if props.get("value") is None:
                continue
            observations.append(
                WaterLevelObservation(
                    station_id=str(props["stationId"]),
                    observed_at=self.parse_time(props["observed"]).isoformat(),
                    sea_level_cm=float(props["value"]),
                    parameter_id=props.get(
                        "parameterId", OBSERVATION_PARAMETER
                    ),
                )
            )
        return sorted(observations, key=lambda observation: observation.observed_at)

    def forecast(
        self,
        payload: dict[str, Any],
        location_id: str,
        issued_at: datetime | None = None,
        collection: str = FORECAST_COLLECTION,
    ) -> list[SeaLevelForecast]:
        """forecastedr CoverageJSON -> future forecast steps. DKSS gives metres, we emit cm."""
        try:
            axes = payload["domain"]["axes"]
            lon, lat = axes["x"]["values"][0], axes["y"]["values"][0]
            times = axes["t"]["values"]
            values = payload["ranges"][FORECAST_PARAMETER]["values"]
        except (KeyError, IndexError, TypeError) as exc:
            raise DMIParseError(f"forecastedr response is missing {exc}") from exc

        issued_at = issued_at or datetime.now(timezone.utc)
        events: list[SeaLevelForecast] = []
        for t, v in zip(times, values):
            if v is None:
                continue
            valid = self.parse_time(t)
            if valid < issued_at:
                continue
            events.append(SeaLevelForecast(
                location_id=location_id,
                lon=float(lon),
                lat=float(lat),
                forecast_for=valid.isoformat(),
                sea_level_cm=round(float(v) * 100, 1),
                lead_time_hours=round((valid - issued_at).total_seconds() / 3600, 2),
                collection=collection,
            ))
        return events
