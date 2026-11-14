from unittest.mock import MagicMock, call, patch

import pytest
import requests
from requests.structures import CaseInsensitiveDict

from dcr_sdk import Account, Simulation
from dcr_sdk.utils.constants import (
    GRAPH_URL,
    INITIALIZE_SIMULATION_URL,
    SIMULATION_EVENT_URL,
    SIMULATION_EVENTS_URL,
    SIMULATION_URL,
)

from .constants import (
    CALL_TITLE,
    GRAPH_BODY,
    GRAPH_ID,
    INCORRECT_PASSWORD,
    INIT_HEADERS,
    PASSWORD,
    SIM_EVENTS_BODY,
    SIMULATION_ID,
    TITLE,
    USERNAME,
)

# I decided to as soon as the simulation is intiialize
# The state is loaded into the Simulation class
EVENTS_CALL = call(
    "GET",
    SIMULATION_EVENTS_URL.format(GRAPH_ID, SIMULATION_ID),
    params={"filter": "all"},
    allow_redirects=True,
)

# The graph definition is loaded once, right before the first event state
GRAPH_CALL = call(
    "GET",
    GRAPH_URL.format(GRAPH_ID),
    params=None,
    allow_redirects=True,
)


# Every route answers with the given response, except the graph definition
def dcr_responses(response: MagicMock):
    graph = MagicMock(text=GRAPH_BODY, raise_for_status=lambda: None)

    def respond(method: str, url: str, *args: object, **kwargs: object):
        return graph if url == GRAPH_URL.format(GRAPH_ID) else response

    return respond


@patch.object(requests.Session, "request")
def test_init_simulation_success(mock_post: MagicMock):
    mock_post.side_effect = dcr_responses(
        MagicMock(
            headers=CaseInsensitiveDict(INIT_HEADERS),
            json=lambda: SIM_EVENTS_BODY,
            raise_for_status=lambda: None,
        )
    )

    simulation = Simulation(GRAPH_ID, Account(USERNAME, PASSWORD), title=TITLE)

    assert simulation.sim_id == SIMULATION_ID
    assert simulation.url == SIMULATION_URL.format(GRAPH_ID, SIMULATION_ID)

    # 1. create the simulation, 2. load its event state
    assert mock_post.call_args_list == [
        call(
            "POST",
            INITIALIZE_SIMULATION_URL.format(GRAPH_ID),
            data=CALL_TITLE,
            json=None,
        ),
        GRAPH_CALL,
        EVENTS_CALL,
    ]


@patch.object(requests.Session, "request")
def test_load_existing_simulation(mock_request: MagicMock):
    mock_request.side_effect = dcr_responses(
        MagicMock(
            json=lambda: SIM_EVENTS_BODY,
            raise_for_status=lambda: None,
        )
    )

    simulation = Simulation(
        GRAPH_ID, Account(USERNAME, PASSWORD), sim_id=SIMULATION_ID
    )

    assert simulation.sim_id == SIMULATION_ID
    assert simulation.url == SIMULATION_URL.format(GRAPH_ID, SIMULATION_ID)

    assert mock_request.call_args_list == [
        EVENTS_CALL,
        GRAPH_CALL,
        EVENTS_CALL,
    ]


@patch.object(requests.Session, "request")
def test_load_missing_simulation(mock_request: MagicMock):
    resp = requests.Response()
    resp.status_code = 404
    resp.reason = "Not Found"
    resp.url = SIMULATION_EVENTS_URL.format(GRAPH_ID, SIMULATION_ID)
    mock_request.return_value = resp

    with pytest.raises(requests.HTTPError) as exc_info:
        _ = Simulation(
            GRAPH_ID, Account(USERNAME, PASSWORD), sim_id=SIMULATION_ID
        )

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
        _ = Simulation(
            GRAPH_ID, Account(USERNAME, INCORRECT_PASSWORD), title=TITLE
        )

    response = exc_info.value.response
    assert response is not None
    assert response.status_code == 401


@patch.object(requests.Session, "request")
def test_load_event_state(mock_request: MagicMock):
    mock_request.side_effect = dcr_responses(
        MagicMock(
            json=lambda: SIM_EVENTS_BODY,
            raise_for_status=lambda: None,
        )
    )
    simulation = Simulation(
        GRAPH_ID, Account(USERNAME, PASSWORD), sim_id=SIMULATION_ID
    )

    state = simulation.state

    assert mock_request.call_args == EVENTS_CALL

    assert state.events["FilloutExpenseReport"].enabled is True
    assert state.events["Approve"].enabled is False

    # Containers the sim events leave out still come from the graph
    assert list(state.events) == [
        "FilloutExpenseReport",
        "Review",
        "Audit",
        "CheckReceipts",
        "Approve",
        "Payout",
    ]
    assert state.events["Audit"].parent == "Review"
    assert state.events["Audit"].included is False


@patch.object(requests.Session, "request")
def test_kill_simulation(mock_request: MagicMock):
    mock_request.side_effect = dcr_responses(
        MagicMock(
            json=lambda: SIM_EVENTS_BODY,
            raise_for_status=lambda: None,
        )
    )
    simulation = Simulation(
        GRAPH_ID, Account(USERNAME, PASSWORD), sim_id=SIMULATION_ID
    )

    simulation.kill_simulation()

    assert mock_request.call_args == call(
        "DELETE", SIMULATION_URL.format(GRAPH_ID, SIMULATION_ID)
    )


@patch.object(requests.Session, "request")
def test_execute_event(mock_request: MagicMock):
    mock_request.side_effect = dcr_responses(
        MagicMock(
            json=lambda: SIM_EVENTS_BODY,
            raise_for_status=lambda: None,
        )
    )
    simulation = Simulation(
        GRAPH_ID, Account(USERNAME, PASSWORD), sim_id=SIMULATION_ID
    )

    simulation.execute_event("FilloutExpenseReport", role="Employee")

    # 1. execute the event, 2. reload the event state
    assert mock_request.call_args_list[-2:] == [
        call(
            "POST",
            SIMULATION_EVENT_URL.format(
                GRAPH_ID, SIMULATION_ID, "FilloutExpenseReport"
            ),
            data='{"Role": "Employee"}',
            json=None,
        ),
        EVENTS_CALL,
    ]


@pytest.mark.parametrize(
    ("body", "expected"),
    [("true", True), ('"True"', True), ("false", False), ('"False"', False)],
)
@patch.object(requests.Session, "request")
def test_is_concluded(mock_request: MagicMock, body: str, expected: bool):
    mock_request.side_effect = dcr_responses(
        MagicMock(
            json=lambda: SIM_EVENTS_BODY,
            text=body,
            raise_for_status=lambda: None,
        )
    )
    simulation = Simulation(
        GRAPH_ID, Account(USERNAME, PASSWORD), sim_id=SIMULATION_ID
    )

    assert simulation.is_concluded() is expected
    assert mock_request.call_args == call(
        "GET",
        SIMULATION_URL.format(GRAPH_ID, SIMULATION_ID),
        params={"filter": "isAccepting"},
        allow_redirects=True,
    )


@pytest.mark.parametrize(
    ("event_id", "message"),
    [("Approve", "is not enabled"), ("Missing", "does not exist")],
)
@patch.object(requests.Session, "request")
def test_execute_event_rejected(
    mock_request: MagicMock, event_id: str, message: str
):
    mock_request.side_effect = dcr_responses(
        MagicMock(
            json=lambda: SIM_EVENTS_BODY,
            raise_for_status=lambda: None,
        )
    )
    simulation = Simulation(
        GRAPH_ID, Account(USERNAME, PASSWORD), sim_id=SIMULATION_ID
    )
    calls_before = mock_request.call_count

    with pytest.raises(ValueError, match=message):
        simulation.execute_event(event_id)

    # Nothing is sent to DCR
    assert mock_request.call_count == calls_before
