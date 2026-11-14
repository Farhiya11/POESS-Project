import os
import uuid

from dcr_sdk import Account, Simulation

from .errors import (
    EventDoesNotExistError,
    EventNotEnabledError,
    GraphDoesNotExistError,
    SimulationNotRunningError,
    raise_,
)
from .models import Overview


class DCR_Engine:
    account: Account
    graphs: dict[str, int]
    simulations: dict[str, dict[str, int]]
    running_simulations: dict[str, Simulation]
    zen_mode: bool

    # ====== Complex Initialization =======

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        graph_title: str | None = None,
        simulation_title: str | None = None,
        zen_mode: bool = False,
    ):
        # Core
        self.account = Account(
            username or os.environ["DCR_USERNAME"],
            password or os.environ["DCR_PASSWORD"],
        )
        self.running_simulations = {}

        # Configs
        self.zen_mode = zen_mode

        # Auto-magically loads the graph index without loading the simulations
        self.graphs = {
            graph.title: graph.id for graph in self.account.get_graphs()
        }
        self.simulations = {
            graph_title: {
                simulation.title: simulation.id
                for simulation in self.account.get_sims(graph_id)
            }
            for graph_title, graph_id in self.graphs.items()
        }

        # If the user knows what they want to initialize
        if graph_title is not None and simulation_title is not None:
            self.attach_new_simulation(graph_title, simulation_title)

    # ====== Actions For Standard Users =========

    def attach_new_simulation(
        self, graph_title: str, simulation_title: str, reference_name: str = ""
    ) -> None:
        self._check_graph_existence(graph_title)

        name = reference_name or simulation_title
        if name in self.running_simulations:
            name = f"{name}-{uuid.uuid4()}"

        graph_id = self.graphs[graph_title]
        # A None sim_id makes the Simulation create a new one in DCR
        sim_id = self.simulations[graph_title].get(simulation_title)
        simulation = Simulation(
            graph_id, self.account, sim_id, simulation_title
        )
        self.simulations[graph_title][simulation_title] = simulation.sim_id
        self.running_simulations[name] = simulation

    # ======= Execute Instructions and Traces =========

    def execute_single_transition(self, sim_name: str, event_id: str) -> None:
        simulation = self.running_simulations.get(sim_name) or raise_(
            SimulationNotRunningError(sim_name)
        )
        event = simulation.state.events.get(event_id)
        if event is None:
            raise EventDoesNotExistError(event_id)
        if not event.enabled:
            raise EventNotEnabledError(event_id)

        simulation.execute_event(event_id)

    # Runs the events in order, stopping at the first non-conforming one
    def execute_sequence(self, sim_name: str, sequence: list[str]) -> None:
        for event_id in sequence:
            self.execute_single_transition(sim_name, event_id)

    # ======= Get State and Structure ============

    def show_next_event(self, sim_name: str) -> list[tuple[str, str]]:
        running = self.running_simulations.get(sim_name) or raise_(
            SimulationNotRunningError(sim_name)
        )
        next_events = [
            (e_id, e.label.strip())
            for e_id, e in running.state.events.items()
            if (e.enabled and e.pending)
        ]
        return next_events

    def get_overview(self) -> Overview:
        return Overview(
            graphs=self.graphs,
            simulations=self.simulations,
            running={
                name: "finished" if self.is_finished(name) else "running"
                for name in self.running_simulations
            },
        )

    # ====== Helper Functions For validations ==========

    def _check_graph_existence(self, graph_title: str) -> None:
        if graph_title not in self.graphs:
            raise GraphDoesNotExistError(graph_title)

    def is_finished(self, sim_name: str) -> bool:
        running = self.running_simulations.get(sim_name) or raise_(
            SimulationNotRunningError(sim_name)
        )
        return not any(
            event.pending and event.effectively_included
            for event in running.state.events.values()
        )
