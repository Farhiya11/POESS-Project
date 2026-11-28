"""DMI observation and forecast data emitted by the API adapter towards Siddhi.

Forecasts are normalized into flat records inside a complete refresh envelope.
Observed water levels are emitted individually to the monitoring stream.
"""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, ClassVar


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class WaterLevelObservation:
    """Measured sea level at a station (DMI oceanObs, parameter sealev_dvr)."""

    station_id: str
    observed_at: str  # ISO-8601, UTC
    sea_level_cm: float
    parameter_id: str = "sealev_dvr"
    source_system: str = "dmi.oceanObs"
    ingested_at: str = ""

    event_type: ClassVar[str] = "WaterLevelObserved"

    def to_event(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            **asdict(self),
            "ingested_at": self.ingested_at or now_iso(),
        }


@dataclass(frozen=True)
class SeaLevelForecast:
    """Forecasted sea-level deviation at a point (DMI forecastedr, DKSS model).

    Evaluated by Siddhi for the preparedness warning process (BPMN / Camunda).
    """

    location_id: str
    lon: float
    lat: float
    forecast_for: str  # ISO-8601 time the value is valid for
    sea_level_cm: float
    lead_time_hours: float
    collection: str = "dkss_nsbs"
    source: str = "dmi.forecastedr"
    ingested_at: str = ""

    event_type: ClassVar[str] = "SeaLevelForecasted"

    def to_event(self) -> dict[str, Any]:
        return {"event_type": self.event_type, **asdict(self), "ingested_at": self.ingested_at or now_iso()}
