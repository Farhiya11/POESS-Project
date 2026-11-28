from dataclasses import dataclass

from constants import (
    FORECAST_LAT,
    FORECAST_LOCATION_ID,
    FORECAST_LON,
    STATION_ID,
)
from dmi import DMIClient

from .forwarder import (
    PreparednessDecisionForwarder,
    WaterLevelObservationForwarder,
)


@dataclass(frozen=True)
class IngestionResult:
    sent: int
    skipped_duplicates: int = 0


class IngestionService:
    """Pulls DMI observations and forecasts and routes them to Siddhi.

    Errors from DMI and either Siddhi sink are not swallowed.
    """

    def __init__(
        self,
        client: DMIClient,
        decision_forwarder: PreparednessDecisionForwarder,
        observation_forwarder: WaterLevelObservationForwarder,
    ) -> None:
        self.client = client
        self.decision_forwarder = decision_forwarder
        self.observation_forwarder = observation_forwarder
        self._last_observed_at = ""

    def ingest_observations(self) -> IngestionResult:
        sent = skipped = 0
        for observation in self.client.observations(STATION_ID):
            if observation.observed_at <= self._last_observed_at:
                skipped += 1
                continue
            self.observation_forwarder.send_observation(observation.to_event())
            self._last_observed_at = observation.observed_at
            sent += 1
        return IngestionResult(sent=sent, skipped_duplicates=skipped)

    def ingest_forecast(self) -> IngestionResult:
        forecasts = [
            forecast.to_event()
            for forecast in self.client.forecast(
                FORECAST_LOCATION_ID, FORECAST_LON, FORECAST_LAT
            )
        ]
        self.decision_forwarder.send_forecast_refresh(
            FORECAST_LOCATION_ID, forecasts
        )
        return IngestionResult(sent=1)
