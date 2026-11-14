from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest
import requests

from dcr_engine import (
    DCR_Engine,
    EventDoesNotExistError,
    EventNotEnabledError,
    GraphDoesNotExistError,
    NextEvent,
    Overview,
    RequestNonConformanceError,
    SimulationNotRunningError,
)
from dcr_sdk.utils.constants import ACCOUNT_GRAPHS_URL, GRAPH_SIMS_URL

MOCK_DATA = Path(__file__).parent / "mock_data"

# Credentials
USERNAME = "test-user"
PASSWORD = "test-password"

# Graphs and simulations described by the mock files
P3_NAIVE = 2016062
PAYOUT = 2016043
ACTIVE_SIM = 2108620
ACTIVE_SIM_TITLE = "Active Simulation"
NEW_SIM = 2108999
P3_NAIVE_TITLE = "P3 Naive"

FIXED_UUID = "12345678-1234-5678-1234-567812345678"

# Every DCR route the engine hits while loading the index
RESPONSES = {
    ACCOUNT_GRAPHS_URL: "account_graphs_body.xml",
    GRAPH_SIMS_URL.format(P3_NAIVE): "p3_naive_sims_body.xml",
    GRAPH_SIMS_URL.format(PAYOUT): "payout_sims_body.xml",
}


def dcr_responses(method: str, url: str, *args: object, **kwargs: object):
    return MagicMock(
        text=(MOCK_DATA / RESPONSES[url]).read_text(),
        raise_for_status=lambda: None,
    )


# The Simulation is mocked so attaching never hits the simulation routes
@pytest.fixture
def simulation_mock():
    with (
        patch.object(requests.Session, "request", side_effect=dcr_responses),
        patch("dcr_engine.core.engine.Simulation") as mock_simulation,
    ):
        yield mock_simulation


def test_loads_simulation_index_from_every_graph(simulation_mock: MagicMock):
    engine = DCR_Engine(USERNAME, PASSWORD)

    assert engine.graphs == {"P3 Naive": P3_NAIVE, "Payout": PAYOUT}
    assert engine.simulations == {
        "P3 Naive": {"Active Simulation": ACTIVE_SIM, "Naive Run": 2108621},
        "Payout": {"Payout Run": 2108700},
    }
    assert engine.running_simulations == {}
    simulation_mock.assert_not_called()


def test_init_raises_when_graph_does_not_exist(simulation_mock: MagicMock):
    with pytest.raises(GraphDoesNotExistError) as exc_info:
        DCR_Engine(
            USERNAME,
            PASSWORD,
            graph_title="Missing Graph",
            simulation_title=ACTIVE_SIM_TITLE,
        )

    assert exc_info.value.graph_title == "Missing Graph"
    simulation_mock.assert_not_called()


def test_attach_raises_when_graph_does_not_exist(simulation_mock: MagicMock):
    engine = DCR_Engine(USERNAME, PASSWORD)

    with pytest.raises(GraphDoesNotExistError):
        engine.attach_new_simulation("Missing Graph", ACTIVE_SIM_TITLE, "alice")

    assert engine.running_simulations == {}
    simulation_mock.assert_not_called()


def test_attach_creates_simulation_when_it_does_not_exist(
    simulation_mock: MagicMock,
):
    simulation_mock.return_value.sim_id = NEW_SIM
    engine = DCR_Engine(USERNAME, PASSWORD)

    engine.attach_new_simulation(P3_NAIVE_TITLE, "New Simulation")

    simulation_mock.assert_called_once_with(
        P3_NAIVE, engine.account, None, "New Simulation"
    )
    assert engine.simulations[P3_NAIVE_TITLE]["New Simulation"] == NEW_SIM
    assert engine.running_simulations == {
        "New Simulation": simulation_mock.return_value
    }


def test_attach_does_not_match_simulation_from_another_graph(
    simulation_mock: MagicMock,
):
    engine = DCR_Engine(USERNAME, PASSWORD)

    engine.attach_new_simulation("Payout", ACTIVE_SIM_TITLE)

    simulation_mock.assert_called_once_with(
        PAYOUT, engine.account, None, ACTIVE_SIM_TITLE
    )


def test_init_attaches_simulation_under_its_title(simulation_mock: MagicMock):
    simulation_mock.return_value.sim_id = ACTIVE_SIM
    engine = DCR_Engine(
        USERNAME,
        PASSWORD,
        graph_title=P3_NAIVE_TITLE,
        simulation_title=ACTIVE_SIM_TITLE,
    )

    simulation_mock.assert_called_once_with(
        P3_NAIVE, engine.account, ACTIVE_SIM, ACTIVE_SIM_TITLE
    )
    assert engine.running_simulations == {
        ACTIVE_SIM_TITLE: simulation_mock.return_value
    }


def test_attach_uses_reference_name(simulation_mock: MagicMock):
    engine = DCR_Engine(USERNAME, PASSWORD)

    engine.attach_new_simulation(P3_NAIVE_TITLE, ACTIVE_SIM_TITLE, "alice")

    assert engine.running_simulations == {"alice": simulation_mock.return_value}
    simulation_mock.assert_called_once_with(
        P3_NAIVE, engine.account, ACTIVE_SIM, ACTIVE_SIM_TITLE
    )


@patch("dcr_engine.core.engine.uuid.uuid4", return_value=FIXED_UUID)
def test_attach_taken_reference_name_gets_uuid(
    _: MagicMock, simulation_mock: MagicMock
):
    engine = DCR_Engine(USERNAME, PASSWORD)

    engine.attach_new_simulation(P3_NAIVE_TITLE, ACTIVE_SIM_TITLE, "alice")
    engine.attach_new_simulation(P3_NAIVE_TITLE, ACTIVE_SIM_TITLE, "alice")

    assert list(engine.running_simulations) == ["alice", f"alice-{FIXED_UUID}"]


@patch("dcr_engine.core.engine.uuid.uuid4", return_value=FIXED_UUID)
def test_attach_without_reference_name_gets_uuid_when_title_taken(
    _: MagicMock, simulation_mock: MagicMock
):
    engine = DCR_Engine(
        USERNAME,
        PASSWORD,
        graph_title=P3_NAIVE_TITLE,
        simulation_title=ACTIVE_SIM_TITLE,
    )

    engine.attach_new_simulation(P3_NAIVE_TITLE, ACTIVE_SIM_TITLE)

    assert list(engine.running_simulations) == [
        ACTIVE_SIM_TITLE,
        f"{ACTIVE_SIM_TITLE}-{FIXED_UUID}",
    ]



# ====== Executing transitions =======

SIM_NAME = "alice"


# A3 is enabled, A4 only becomes enabled once A3 has run
@pytest.fixture
def running(simulation_mock: MagicMock):
    simulation_mock.return_value.sim_id = ACTIVE_SIM
    engine = DCR_Engine(USERNAME, PASSWORD)
    engine.attach_new_simulation(P3_NAIVE_TITLE, ACTIVE_SIM_TITLE, SIM_NAME)

    events = {
        "A3": SimpleNamespace(enabled=True),
        "A4": SimpleNamespace(enabled=False),
    }
    simulation = simulation_mock.return_value
    simulation.state.events = events
    simulation.execute_event.side_effect = lambda event_id: events.update(
        {"A4": SimpleNamespace(enabled=True)} if event_id == "A3" else {}
    )
    return engine, simulation


def test_execute_single_transition(running: tuple[DCR_Engine, MagicMock]):
    engine, simulation = running

    engine.execute_single_transition(SIM_NAME, "A3")

    simulation.execute_event.assert_called_once_with("A3")


@pytest.mark.parametrize(
    ("event_id", "error"),
    [
        ("A99", EventDoesNotExistError),
        ("A4", EventNotEnabledError),
    ],
)
def test_execute_single_transition_non_conformance(
    running: tuple[DCR_Engine, MagicMock],
    event_id: str,
    error: type[RequestNonConformanceError],
):
    engine, simulation = running

    with pytest.raises(error):
        engine.execute_single_transition(SIM_NAME, event_id)

    simulation.execute_event.assert_not_called()


def test_execute_sequence_runs_in_order(running: tuple[DCR_Engine, MagicMock]):
    engine, simulation = running

    engine.execute_sequence(SIM_NAME, ["A3", "A4"])

    assert simulation.execute_event.call_args_list == [call("A3"), call("A4")]



def test_execute_sequence_stops_at_non_conforming_event(
    running: tuple[DCR_Engine, MagicMock],
):
    engine, simulation = running

    with pytest.raises(EventDoesNotExistError):
        engine.execute_sequence(SIM_NAME, ["A3", "A99", "A4"])

    simulation.execute_event.assert_called_once_with("A3")


def test_execute_on_simulation_that_is_not_running(
    running: tuple[DCR_Engine, MagicMock],
):
    engine, simulation = running

    with pytest.raises(SimulationNotRunningError) as exc_info:
        engine.execute_single_transition("bob", "A3")

    assert exc_info.value.sim_name == "bob"
    simulation.execute_event.assert_not_called()


# ====== Finished and overview =======


def pending(included: bool) -> SimpleNamespace:
    return SimpleNamespace(pending=True, effectively_included=included)


@pytest.mark.parametrize(
    ("events", "finished"),
    [
        ({}, True),
        ({"A3": pending(included=True)}, False),
        # Pending but inside an excluded box, nothing left to do
        ({"A9": pending(included=False)}, True),
    ],
)
def test_is_finished(
    running: tuple[DCR_Engine, MagicMock],
    events: dict[str, SimpleNamespace],
    finished: bool,
):
    engine, simulation = running
    simulation.state.events = events

    assert engine.is_finished(SIM_NAME) is finished


@pytest.mark.parametrize(
    ("events", "status"),
    [({"A3": pending(included=True)}, "running"), ({}, "finished")],
)
def test_overview(
    running: tuple[DCR_Engine, MagicMock],
    events: dict[str, SimpleNamespace],
    status: str,
):
    engine, simulation = running
    simulation.state.events = events

    assert engine.get_overview() == Overview(
        graphs=engine.graphs,
        simulations=engine.simulations,
        running={SIM_NAME: status},
    )


def test_show_next_event_only_returns_enabled_and_pending(
    running: tuple[DCR_Engine, MagicMock],
):
    engine, simulation = running
    simulation.state.events = {
        "A3": SimpleNamespace(enabled=True, pending=True, label=" Hits "),
        "A4": SimpleNamespace(enabled=False, pending=True, label="Peak"),
        "A5": SimpleNamespace(enabled=True, pending=False, label="Council"),
    }

    assert engine.show_next_event(SIM_NAME) == [NextEvent("A3", "Hits")]

