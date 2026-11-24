from collections import deque
from typing import Any

import requests

from constants import EVENT_SINK_TIMEOUT_SECONDS, EVENT_SINK_URL


class ForwardError(RuntimeError):
    """The CEP sink did not accept an event."""


class EventForwarder:
    """Posts events to the CEP sink (Siddhi http source) as {"event": {...}}."""

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
            resp = self.session.post(self.sink_url, json={"event": event}, timeout=EVENT_SINK_TIMEOUT_SECONDS)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise ForwardError(f"sink {self.sink_url} rejected {event.get('event_type')}: {exc}") from exc
        self.history.append(event)

    def recent(self, limit: int) -> list[dict[str, Any]]:
        return list(self.history)[-limit:]
