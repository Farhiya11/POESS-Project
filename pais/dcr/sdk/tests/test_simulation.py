from unittest.mock import MagicMock, patch

import pytest
import requests
from requests.structures import CaseInsensitiveDict

from dcr_sdk.account import Account
from dcr_sdk.constants import (
    INITIALIZE_SIMULATION_URL,
    SIMULATION_EVENTS_URL,
    SIMULATION_URL,
)
from dcr_sdk.simulation import Simulation

from .constants import (
    CALL_TITLE,
    GRAPH_ID,
    INCORRECT_PASSWORD,
    INIT_HEADERS,
    PASSWORD,
    SIMULATION_ID,
    TITLE,
    USERNAME,
)


@patch.object(requests.Session, "request")
def test_init_simulation_success(mock_post: MagicMock):
    mock_post.return_value = MagicMock(
        headers=CaseInsensitiveDict(INIT_HEADERS),
        raise_for_status=lambda: None,
    )

    simulation = Simulation(GRAPH_ID, Account(USERNAME, PASSWORD), title=TITLE)

    assert simulation.sim_id == SIMULATION_ID
    assert simulation.url == SIMULATION_URL.format(GRAPH_ID, SIMULATION_ID)

    mock_post.assert_called_once_with(
        "POST",
        INITIALIZE_SIMULATION_URL.format(GRAPH_ID),
        data=CALL_TITLE,
        json=None,
    )


@patch.object(requests.Session, "request")
def test_load_existing_simulation(mock_request: MagicMock):
    mock_request.return_value = MagicMock(raise_for_status=lambda: None)

    simulation = Simulation(GRAPH_ID, Account(USERNAME, PASSWORD), sim_id=SIMULATION_ID)

    assert simulation.sim_id == SIMULATION_ID
    assert simulation.url == SIMULATION_URL.format(GRAPH_ID, SIMULATION_ID)

    mock_request.assert_called_once_with(
        "GET",
        SIMULATION_EVENTS_URL.format(GRAPH_ID, SIMULATION_ID),
        params={"filter": "all"},
        allow_redirects=True,
    )


@patch.object(requests.Session, "request")
def test_load_missing_simulation(mock_request: MagicMock):
    resp = requests.Response()
    resp.status_code = 404
    resp.reason = "Not Found"
    resp.url = SIMULATION_EVENTS_URL.format(GRAPH_ID, SIMULATION_ID)
    mock_request.return_value = resp

    with pytest.raises(requests.HTTPError) as exc_info:
        _ = Simulation(GRAPH_ID, Account(USERNAME, PASSWORD), sim_id=SIMULATION_ID)

    response = exc_info.value.response
    assert response is not None
    assert response.status_code == 404


@patch.object(requests.Session, "request")
def test_init_simulation_unauthorized(mock_request: MagicMock):
    resp = requests.Response()
    resp.status_code = 401
    resp.reason = "Unauthorized"
    resp.headers["www-authenticate"] = "Basic"
    resp.url = INITIALIZE_SIMULATION_URL.format(GRAPH_ID)
    mock_request.return_value = resp

    with pytest.raises(requests.HTTPError) as exc_info:
        _ = Simulation(GRAPH_ID, Account(USERNAME, INCORRECT_PASSWORD), title=TITLE)

    response = exc_info.value.response
    assert response is not None
    assert response.status_code == 401
