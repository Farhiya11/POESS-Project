from unittest.mock import MagicMock, patch

import pytest
import requests

from dcr_sdk.dcr import DCR, INITIALIZE_SIMULATION_URL

from .constants import (
    CALL_TITLE,
    GRAPH_ID,
    INCORRECT_PASSWORD,
    INIT_HEADERS,
    PASSWORD,
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
