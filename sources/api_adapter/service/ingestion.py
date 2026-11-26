from dataclasses import dataclass

from constants import FORECAST_LAT, FORECAST_LOCATION_ID, FORECAST_LON, STATION_ID
from dmi import DMIClient

from .forwarder import EventForwarder


@dataclass(frozen=True)
class IngestionResult:
    sent: int
    skipped_duplicates: int = 0


class IngestionService:
    """Pulls from DMI and pushes each reading to the CEP sink.

    Errors from DMI (DMIRequestError / DMIParseError) and from the sink
    (ForwardError) are not swallowed, the caller decides what to do.
    """

    def __init__(self, client: DMIClient, forwarder: EventForwarder, station_id: str = STATION_ID) -> None:
        self.client = client
        self.forwarder = forwarder
        self.station_id = station_id
        self._last_observed_at = ""

    def ingest_observations(self) -> IngestionResult:
        sent = skipped = 0
        for obs in self.client.observations(self.station_id):
            if obs.observed_at <= self._last_observed_at:
                skipped += 1
                continue
            self.forwarder.send(obs.to_event())
            self._last_observed_at = obs.observed_at
            sent += 1
        return IngestionResult(sent=sent, skipped_duplicates=skipped)

    def ingest_forecast(self) -> IngestionResult:
        forecasts = [
            forecast.to_event()
            for forecast in self.client.forecast(
                FORECAST_LOCATION_ID, FORECAST_LON, FORECAST_LAT
            )
        ]
        # Send the complete refresh before individual events so the policy can clear
        # an episode only after a successful, complete DMI response.
        self.forwarder.send_forecast_refresh(FORECAST_LOCATION_ID, forecasts)
        sent = 0
        for forecast in forecasts:
            self.forwarder.send(forecast)
            sent += 1
        return IngestionResult(sent=sent)
