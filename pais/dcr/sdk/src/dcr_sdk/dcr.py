from __future__ import annotations

import json

import requests

INITIALIZE_SIMULATION_URL: str = "https://repository.dcrgraphs.net/api/graphs/{}/sims"
DEFAULT_HEADERS: dict[str, str] = {"Content-Type": "application/json"}


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
