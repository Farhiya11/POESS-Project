from unittest.mock import MagicMock, patch

import pytest
import requests

from dcr_sdk.account import Account
from dcr_sdk.constants import INITIALIZE_SIMULATION_URL
from dcr_sdk.simulation import Simulation

from .constants import (
    CALL_TITLE,
    GRAPH_ID,
    INCORRECT_PASSWORD,
    INIT_HEADERS,
    PASSWORD,
    TITLE,
    USERNAME,
)


@patch.object(requests.Session, "request")
def test_init_simulation_success(mock_post: MagicMock):

    mock_post.return_value = MagicMock(
        status_code=200,
        headers=INIT_HEADERS,
        raise_for_status=lambda: None,
    )

    account = Account(USERNAME, PASSWORD)
    result = Simulation(GRAPH_ID, account).init_simulation(TITLE)

    assert result.headers == INIT_HEADERS

    # DCR graphs uses basic auth, set once on the account session
    assert account.session.auth == (USERNAME, PASSWORD)
    assert account.session.headers["Content-Type"] == "application/json"

    mock_post.assert_called_once_with(
        "POST",
        INITIALIZE_SIMULATION_URL.format(GRAPH_ID),
        data=CALL_TITLE,
        json=None,
    )


@patch.object(requests.Session, "request")
def test_init_simulation_unauthorized(mock_request: MagicMock):
    resp = requests.Response()
    resp.status_code = 401
    resp.reason = "Unauthorized"
    resp.headers["www-authenticate"] = "Basic"
    resp.url = INITIALIZE_SIMULATION_URL.format(GRAPH_ID)
    mock_request.return_value = resp

    with pytest.raises(requests.HTTPError) as exc_info:
        _ = Simulation(
            GRAPH_ID, Account(USERNAME, INCORRECT_PASSWORD)
        ).init_simulation(TITLE)

    response = exc_info.value.response
    assert response is not None
    assert response.status_code == 401

