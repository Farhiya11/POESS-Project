"""Event dataclasses emitted by the API adapter towards the CEP layer (Siddhi).

Every DMI reading is normalised into one flat event so Siddhi stream
definitions stay simple (one attribute per field, no nested JSON).
"""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class WaterLevelObservation:
    """Measured sea level at a station (DMI oceanObs, parameter sealev_dvr).

    Used by the Storm Surge Declaration process (DCR).
    """

    station_id: str
    observed_at: str  # ISO-8601, UTC
    sea_level_cm: float
    parameter_id: str = "sealev_dvr"
    source: str = "dmi.oceanObs"
    ingested_at: str = ""

    event_type = "WaterLevelObserved"

    def to_event(self) -> dict:
        return {"event_type": self.event_type, **asdict(self), "ingested_at": self.ingested_at or now_iso()}


@dataclass(frozen=True)
class SeaLevelForecast:
    """Forecasted sea-level deviation at a point (DMI forecastedr, DKSS model).

    Used by the Forecast Warning process (BPMN / Camunda).
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

    event_type = "SeaLevelForecasted"

    def to_event(self) -> dict:
        return {"event_type": self.event_type, **asdict(self), "ingested_at": self.ingested_at or now_iso()}
