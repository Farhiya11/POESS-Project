from __future__ import annotations

import requests

from dcr_sdk.constants import ACCOUNT_GRAPHS_URL, DEFAULT_HEADERS
from dcr_sdk.models import Graph
from dcr_sdk.parser import parse_graphs


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

    # Private Raw Reponse Method
    def _request_graphs(self) -> requests.Response:
        response = self.session.get(ACCOUNT_GRAPHS_URL)
        response.raise_for_status()
        return response

    # SDK object transformed for usage
    def get_graphs(self) -> list[Graph]:
        return parse_graphs(self._request_graphs().text)
