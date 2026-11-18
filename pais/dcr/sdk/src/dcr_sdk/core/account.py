from __future__ import annotations

import requests

from dcr_sdk.models import Graph, Sim
from dcr_sdk.utils.constants import (
    ACCOUNT_GRAPHS_URL,
    DEFAULT_HEADERS,
    GRAPH_SIMS_URL,
)
from dcr_sdk.utils.dcr_parser import DCR_Parser


class Account:
    session: requests.Session

    def __init__(
        self,
        username: str,
        password: str,
        headers: dict[str, str] = DEFAULT_HEADERS,
    ):
        self.session = requests.Session()
        self.session.auth = (username, password)
        self.session.headers.update(headers)

    # ====== Private Raw Reponse Methods =======

    def _request_graphs(self) -> requests.Response:
        response = self.session.get(ACCOUNT_GRAPHS_URL)
        response.raise_for_status()
        return response

    def _request_sims(self, graph_id: int) -> requests.Response:
        response = self.session.get(GRAPH_SIMS_URL.format(graph_id))
        response.raise_for_status()
        return response

    # ====== SDK object transformed for usage =======

    def get_graphs(self) -> list[Graph]:
        return DCR_Parser.parse_graphs(self._request_graphs().text)

    def get_sims(self, graph_id: int) -> list[Sim]:
        return DCR_Parser.parse_sims(self._request_sims(graph_id).text)
