from __future__ import annotations

import json

import requests

from dcr_sdk.account import Account
from dcr_sdk.constants import INITIALIZE_SIMULATION_URL


class Simulation:
    graph_id: int
    account: Account

    def __init__(self, graph_id: int, account: Account):
        self.graph_id = graph_id
        self.account = account

    def init_simulation(self, title: str) -> requests.Response:
        url = INITIALIZE_SIMULATION_URL.format(self.graph_id)
        payload = json.dumps({"Title": title})
        response = self.account.session.post(url, data=payload)
        response.raise_for_status()
        return response
