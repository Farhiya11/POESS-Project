from __future__ import annotations

import json

import requests

from dcr_sdk.account import Account
from dcr_sdk.constants import DEFAULT_HEADERS, INITIALIZE_SIMULATION_URL


class Simulation:
    graph_id: int
    account: Account
    headers: dict[str, str]

    def __init__(
        self,
        graph_id: int,
        account: Account,
        headers: dict[str, str] = DEFAULT_HEADERS,
    ):
        self.graph_id = graph_id
        self.account = account
        self.headers = headers

    def init_simulation(self, title: str) -> requests.Response:
        url = INITIALIZE_SIMULATION_URL.format(self.graph_id)
        payload = json.dumps({"Title": title})
        response = requests.request(
            "POST", url, headers=self.headers, data=payload, auth=self.account.auth
        )
        response.raise_for_status()
        return response
