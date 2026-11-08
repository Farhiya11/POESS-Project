from __future__ import annotations

import json
from typing import cast

import requests

from dcr_sdk.core.account import Account
from dcr_sdk.models.models import State
from dcr_sdk.utils.constants import (
    INITIALIZE_SIMULATION_URL,
    SIMULATION_EVENTS_URL,
    SIMULATION_URL,
)
from dcr_sdk.utils.dcr_parser import DCR_Parser


class Simulation:
    graph_id: int
    account: Account
    sim_id: int
    url: str
    parser: DCR_Parser

    def __init__(
        self,
        graph_id: int,
        account: Account,
        sim_id: int | None = None,
        title: str = "Python Simulation",
    ):
        self.graph_id = graph_id
        self.account = account
        self.parser = DCR_Parser()

        if sim_id is None:
            response = self._init_simulation(title)
            sim_id = int(response.headers["X-Dcr-Simulation-Id"])
        else:
            self._verify_sim_id(sim_id)

        self.sim_id = sim_id
        self.url = SIMULATION_URL.format(graph_id, sim_id)

    def _init_simulation(self, title: str) -> requests.Response:
        url = INITIALIZE_SIMULATION_URL.format(self.graph_id)
        payload = json.dumps({"Title": title})
        response = self.account.session.post(url, data=payload)
        response.raise_for_status()
        return response

    # Note: There is no formal GET request to check this
    # Solution: Get events and raise_for_status in case it doens't find it
    def _verify_sim_id(self, sim_id: int) -> None:
        url = SIMULATION_EVENTS_URL.format(self.graph_id, sim_id)
        response = self.account.session.get(url, params={"filter": "all"})
        response.raise_for_status()

    def _load_event_state(self, event_filter: str = "all") -> State:
        url = SIMULATION_EVENTS_URL.format(self.graph_id, self.sim_id)
        response = self.account.session.get(url, params={"filter": event_filter})
        response.raise_for_status()
        # DCR wraps the events XML in a JSON string
        return self.parser.parse_state(cast(str, response.json()))
