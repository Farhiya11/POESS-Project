from unittest.mock import MagicMock, patch

import pytest
import requests

from dcr_sdk.dcr import (
    DCR,
    EVENTS_URL,
    EXECUTE_EVENT_URL,
    INITIALIZE_SIMULATION_URL,
    LIST_SIMULATIONS_URL,
)

from .constants import (
    CALL_TITLE,
    EVENT_ID,
    EVENTS_XML,
    GRAPH_ID,
    INCORRECT_PASSWORD,
    INIT_HEADERS,
    PASSWORD,
    SIMS_XML,
    SIMULATION_ID,
    TITLE,
    USERNAME,
)


@patch("dcr_sdk.dcr.requests.request")
def test_init_simulation_success(mock_post: MagicMock):

    mock_post.return_value = MagicMock(
        status_code=200,
        headers=INIT_HEADERS,
        raise_for_status=lambda: None,
    )

    result = DCR(GRAPH_ID, USERNAME, PASSWORD).init_simulation(TITLE)

    assert result.headers == INIT_HEADERS

    mock_post.assert_called_once_with(
        "POST",
        INITIALIZE_SIMULATION_URL.format(GRAPH_ID),
        headers={"Content-Type": "application/json"},
        data=CALL_TITLE,
        # DCR graphs uses basic auth
        auth=(USERNAME, PASSWORD),
    )


@patch("dcr_sdk.dcr.requests.request")
def test_init_simulation_unauthorized(mock_request: MagicMock):
    resp = requests.Response()
    resp.status_code = 401
    resp.reason = "Unauthorized"
    resp.headers["www-authenticate"] = "Basic"
    resp.url = INITIALIZE_SIMULATION_URL.format(GRAPH_ID)
    mock_request.return_value = resp

    with pytest.raises(requests.HTTPError) as exc_info:
        _ = DCR(GRAPH_ID, USERNAME, INCORRECT_PASSWORD).init_simulation(
            "Python Simulation"
        )

    response = exc_info.value.response
    assert response is not None
    assert response.status_code == 401


@patch("dcr_sdk.dcr.requests.request")
def test_create_simulation_reads_location_header(mock_request: MagicMock):
    mock_request.return_value = MagicMock(
        headers=INIT_HEADERS, raise_for_status=lambda: None
    )

    assert DCR(GRAPH_ID, USERNAME, PASSWORD).create_simulation(TITLE) == SIMULATION_ID
    mock_request.assert_called_once()


@patch("dcr_sdk.dcr.requests.request")
def test_create_simulation_falls_back_to_latest_trace(mock_request: MagicMock):
    mock_request.side_effect = [
        MagicMock(headers={}, raise_for_status=lambda: None),
        MagicMock(text=SIMS_XML, raise_for_status=lambda: None),
    ]

    assert DCR(GRAPH_ID, USERNAME, PASSWORD).create_simulation() == SIMULATION_ID
    mock_request.assert_called_with(
        "GET",
        LIST_SIMULATIONS_URL.format(GRAPH_ID),
        headers={"Content-Type": "application/json", "Accept": "application/xml"},
        auth=(USERNAME, PASSWORD),
    )


@patch("dcr_sdk.dcr.requests.request")
def test_get_enabled_events_returns_only_enabled(mock_request: MagicMock):
    mock_request.return_value = MagicMock(
        text=EVENTS_XML.replace('"', '\\"'), raise_for_status=lambda: None
    )

    events = DCR(GRAPH_ID, USERNAME, PASSWORD).get_enabled_events(SIMULATION_ID)

    assert events == ["PlaceOrder", "CancelOrder"]
    assert mock_request.call_args.args[1] == EVENTS_URL.format(GRAPH_ID, SIMULATION_ID)


@patch("dcr_sdk.dcr.requests.request")
def test_execute_event_posts_to_event_url(mock_request: MagicMock):
    mock_request.return_value = MagicMock(raise_for_status=lambda: None)

    DCR(GRAPH_ID, USERNAME, PASSWORD).execute_event(SIMULATION_ID, EVENT_ID)

    mock_request.assert_called_once_with(
        "POST",
        EXECUTE_EVENT_URL.format(GRAPH_ID, SIMULATION_ID, EVENT_ID),
        headers={"Content-Type": "application/json"},
        data="{}",
        auth=(USERNAME, PASSWORD),
    )
