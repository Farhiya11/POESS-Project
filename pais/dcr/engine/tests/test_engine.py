from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests
from pais.dcr.engine.core import DCR_Engine
from pais.dcr.engine.errors import SimulationDoesNotExistError

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
        patch("pais.dcr.engine.core.Simulation") as mock_simulation,
    ):
        yield mock_simulation


def test_loads_simulation_index_from_every_graph(simulation_mock: MagicMock):
    engine = DCR_Engine(USERNAME, PASSWORD)

    assert engine.graphs == {"P3 Naive": P3_NAIVE, "Payout": PAYOUT}
    assert engine.simulations == {
        "Active Simulation": (ACTIVE_SIM, P3_NAIVE),
        "Naive Run": (2108621, P3_NAIVE),
        "Payout Run": (2108700, PAYOUT),
    }
    assert engine.running_simulations == {}
    simulation_mock.assert_not_called()


def test_init_raises_when_simulation_does_not_exist(simulation_mock: MagicMock):
    with pytest.raises(SimulationDoesNotExistError) as exc_info:
        DCR_Engine(USERNAME, PASSWORD, simulation_title="Missing Simulation")

    assert exc_info.value.simulation_title == "Missing Simulation"
    simulation_mock.assert_not_called()


def test_attach_raises_when_simulation_does_not_exist(
    simulation_mock: MagicMock,
):
    engine = DCR_Engine(USERNAME, PASSWORD)

    with pytest.raises(SimulationDoesNotExistError):
        engine.attach_new_simulation("Missing Simulation", "alice")

    assert engine.running_simulations == {}
    simulation_mock.assert_not_called()


def test_init_attaches_simulation_under_its_title(simulation_mock: MagicMock):
    engine = DCR_Engine(USERNAME, PASSWORD, simulation_title=ACTIVE_SIM_TITLE)

    simulation_mock.assert_called_once_with(
        P3_NAIVE, engine.account, ACTIVE_SIM, ACTIVE_SIM_TITLE
    )
    assert engine.running_simulations == {
        ACTIVE_SIM_TITLE: simulation_mock.return_value
    }


def test_attach_uses_reference_name(simulation_mock: MagicMock):
    engine = DCR_Engine(USERNAME, PASSWORD)

    engine.attach_new_simulation(ACTIVE_SIM_TITLE, "alice")

    assert engine.running_simulations == {
        "alice": simulation_mock.return_value
    }
    simulation_mock.assert_called_once_with(
        P3_NAIVE, engine.account, ACTIVE_SIM, ACTIVE_SIM_TITLE
    )


@patch("pais.dcr.engine.core.uuid.uuid4", return_value=FIXED_UUID)
def test_attach_taken_reference_name_gets_uuid(
    _: MagicMock, simulation_mock: MagicMock
):
    engine = DCR_Engine(USERNAME, PASSWORD)

    engine.attach_new_simulation(ACTIVE_SIM_TITLE, "alice")
    engine.attach_new_simulation(ACTIVE_SIM_TITLE, "alice")

    assert list(engine.running_simulations) == ["alice", f"alice-{FIXED_UUID}"]


@patch("pais.dcr.engine.core.uuid.uuid4", return_value=FIXED_UUID)
def test_attach_without_reference_name_gets_uuid_when_title_taken(
    _: MagicMock, simulation_mock: MagicMock
):
    engine = DCR_Engine(USERNAME, PASSWORD, simulation_title=ACTIVE_SIM_TITLE)

    engine.attach_new_simulation(ACTIVE_SIM_TITLE)

    assert list(engine.running_simulations) == [
        ACTIVE_SIM_TITLE,
        f"{ACTIVE_SIM_TITLE}-{FIXED_UUID}",
    ]
