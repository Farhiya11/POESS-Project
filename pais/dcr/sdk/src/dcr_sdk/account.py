from __future__ import annotations

import requests

from dcr_sdk.constants import ACCOUNT_GRAPHS_URL, DEFAULT_HEADERS


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

    def _get_graphs(self) -> requests.Response:
        url = ACCOUNT_GRAPHS_URL
        response = requests.request("GET", url, headers=self.headers, auth=self.auth)
        response.raise_for_status()
        return response

    def show_graphs(self) -> str:
        return self._get_graphs().text
