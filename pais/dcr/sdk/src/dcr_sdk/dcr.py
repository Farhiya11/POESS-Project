from __future__ import annotations

import json
import re

import requests

API_BASE: str = "https://repository.dcrgraphs.net/api"
INITIALIZE_SIMULATION_URL: str = API_BASE + "/graphs/{}/sims"
LIST_SIMULATIONS_URL: str = API_BASE + "/graphs/{}/sims?filter=all"
EVENTS_URL: str = API_BASE + "/graphs/{}/sims/{}/events"
EXECUTE_EVENT_URL: str = API_BASE + "/graphs/{}/sims/{}/events/{}"
DEFAULT_HEADERS: dict[str, str] = {"Content-Type": "application/json"}
XML_HEADERS: dict[str, str] = {"Accept": "application/xml"}

SIMULATION_ID_PATTERN = re.compile(r"/sims/(\d+)")
TRACE_ID_PATTERN = re.compile(r'<trace[^>]*id="(\d+)"')
ENABLED_EVENT_PATTERN = re.compile(
    r'<event[^>]*id="([^"]+)"[^>]*enabled="true"[^>]*>', re.IGNORECASE
)


class DCR:
    graph_id: int
    auth: tuple[str, str]
    headers: dict[str, str]

    def __init__(
        self,
        graph_id: int,
        username: str,
        password: str,
        headers: dict[str, str] = DEFAULT_HEADERS,
    ):
        self.graph_id = graph_id
        self.auth = (username, password)
        self.headers = headers

    def init_simulation(self, title: str) -> requests.Response:
        url = INITIALIZE_SIMULATION_URL.format(self.graph_id)
        payload = json.dumps({"Title": title})
        response = requests.request(
            "POST", url, headers=self.headers, data=payload, auth=self.auth
        )
        response.raise_for_status()
        return response

    def create_simulation(self, title: str = "") -> str:
        """Start a simulation and return its id."""
        response = self.init_simulation(title)
        match = SIMULATION_ID_PATTERN.search(response.headers.get("location", ""))
        if match:
            return match.group(1)

        # No location header: fall back to the newest simulation on the graph
        ids = TRACE_ID_PATTERN.findall(self._get_xml(LIST_SIMULATIONS_URL.format(self.graph_id)))
        if not ids:
            raise ValueError(f"No simulations found for graph {self.graph_id}")
        return ids[-1]

    def get_enabled_events(self, simulation_id: str) -> list[str]:
        url = EVENTS_URL.format(self.graph_id, simulation_id)
        # DCR sometimes returns the XML as an escaped JSON string
        xml = self._get_xml(url).replace('\\"', '"')
        return ENABLED_EVENT_PATTERN.findall(xml)

    def execute_event(self, simulation_id: str, event_id: str) -> requests.Response:
        url = EXECUTE_EVENT_URL.format(self.graph_id, simulation_id, event_id)
        response = requests.request(
            "POST", url, headers=self.headers, data="{}", auth=self.auth
        )
        response.raise_for_status()
        return response

    def _get_xml(self, url: str) -> str:
        response = requests.request(
            "GET", url, headers={**self.headers, **XML_HEADERS}, auth=self.auth
        )
        response.raise_for_status()
        return response.text
