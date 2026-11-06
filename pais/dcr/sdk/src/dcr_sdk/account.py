from __future__ import annotations

import requests

from dcr_sdk.constants import ACCOUNT_GRAPHS_URL, DEFAULT_HEADERS
from dcr_sdk.models import Graph
from dcr_sdk.parser import parse_graphs


class Account:
    auth: tuple[str, str]
    headers: dict[str, str]

    def __init__(
        self,
        username: str,
        password: str,
        headers: dict[str, str] = DEFAULT_HEADERS,
    ):
        self.auth = (username, password)
        self.headers = headers

    # Private Raw Reponse Method
    def _request_graphs(self) -> requests.Response:
        url = ACCOUNT_GRAPHS_URL
        response = requests.request("GET", url, headers=self.headers, auth=self.auth)
        response.raise_for_status()
        return response

    # SDK object transformed for usage
    def get_graphs(self) -> list[Graph]:
        return parse_graphs(self._request_graphs().text)
