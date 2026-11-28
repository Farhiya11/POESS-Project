import json
from typing import Any
from uuid import uuid4

import requests

from constants import (
    OBSERVATION_SINK_TIMEOUT_SECONDS,
    PREPAREDNESS_DECISION_SINK_URL,
    PREPAREDNESS_DECISION_TIMEOUT_SECONDS,
    PREPAREDNESS_WARNING_POLICY_JSON,
    WATER_LEVEL_OBSERVATION_SINK_URL,
)


class DecisionSinkError(RuntimeError):
    """Siddhi did not accept a forecast refresh."""


class PreparednessDecisionForwarder:
    """Posts complete DMI forecast refreshes to Siddhi for evaluation."""

    def __init__(
        self,
        decision_sink_url: str = PREPAREDNESS_DECISION_SINK_URL,
        session: requests.Session | None = None,
        policy_json: str = PREPAREDNESS_WARNING_POLICY_JSON,
    ) -> None:
        self.session = session or requests.Session()
        self.decision_sink_url = decision_sink_url
        self.policy_json = policy_json

    def send_forecast_refresh(
        self, location_id: str, forecasts: list[dict[str, Any]]
    ) -> None:
        refresh_id = uuid4().hex

        refresh = {
            "refresh_id": refresh_id,
            "location_id": location_id,
            "forecasts_json": json.dumps(
                forecasts, sort_keys=True, separators=(",", ":")
            ),
            "policy_json": self.policy_json,
        }
        try:
            response = self.session.post(
                self.decision_sink_url,
                json=refresh,
                timeout=PREPAREDNESS_DECISION_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise DecisionSinkError(
                f"forecast refresh sink {self.decision_sink_url} rejected "
                f"{location_id}: {exc}"
            ) from exc


class ObservationSinkError(RuntimeError):
    """Siddhi did not accept a measured water-level observation."""


class WaterLevelObservationForwarder:
    """Posts measured water levels to the Siddhi monitoring stream."""

    def __init__(
        self,
        observation_sink_url: str = WATER_LEVEL_OBSERVATION_SINK_URL,
        session: requests.Session | None = None,
    ) -> None:
        self.session = session or requests.Session()
        self.observation_sink_url = observation_sink_url

    def send_observation(self, observation: dict[str, Any]) -> None:
        try:
            response = self.session.post(
                self.observation_sink_url,
                json=observation,
                timeout=OBSERVATION_SINK_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ObservationSinkError(
                f"water-level observation sink {self.observation_sink_url} "
                f"rejected {observation.get('station_id')}: {exc}"
            ) from exc
