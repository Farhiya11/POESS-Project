import hashlib
import json
from collections import deque
from typing import Any

import requests

from constants import (
    EVENT_SINK_TIMEOUT_SECONDS,
    EVENT_SINK_URL,
    PREPAREDNESS_WARNING_POLICY_URL,
)


class ForwardError(RuntimeError):
    """The CEP sink did not accept an event."""


class EventForwarder:
    """Posts flat DMI events to the Siddhi HTTP source."""

    def __init__(
        self,
        sink_url: str = EVENT_SINK_URL,
        session: requests.Session | None = None,
        history_size: int = 500,
    ) -> None:
        self.sink_url = sink_url
        self.session = session or requests.Session()
        self.history: deque[dict[str, Any]] = deque(maxlen=history_size)

    def send(self, event: dict[str, Any]) -> None:
        try:
            resp = self.session.post(self.sink_url, json=event, timeout=EVENT_SINK_TIMEOUT_SECONDS)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise ForwardError(f"sink {self.sink_url} rejected {event.get('event_type')}: {exc}") from exc
        self.history.append(event)

    def send_forecast_refresh(
        self, location_id: str, forecasts: list[dict[str, Any]]
    ) -> None:
        identity_fields = (
            "event_type",
            "location_id",
            "collection",
            "forecast_for",
            "sea_level_cm",
            "lead_time_hours",
            "lon",
            "lat",
            "source",
        )
        identity = [
            {key: event.get(key) for key in identity_fields}
            for event in forecasts
        ]
        identity.sort(
            key=lambda event: (
                str(event["forecast_for"]),
                str(event["sea_level_cm"]),
                str(event["lead_time_hours"]),
            )
        )
        refresh_id = hashlib.sha256(
            json.dumps(
                {"location_id": location_id, "forecasts": identity},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

        try:
            response = self.session.post(
                PREPAREDNESS_WARNING_POLICY_URL,
                json={
                    "refresh_id": refresh_id,
                    "location_id": location_id,
                    "forecasts": forecasts,
                },
                timeout=EVENT_SINK_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ForwardError(
                f"forecast refresh sink {PREPAREDNESS_WARNING_POLICY_URL} rejected "
                f"{location_id}: {exc}"
            ) from exc

    def recent(self, limit: int) -> list[dict[str, Any]]:
        return list(self.history)[-limit:]
