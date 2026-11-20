import os
import uuid

from dcr_sdk import Account, Event, Simulation

from .errors import (
    EventDoesNotExistError,
    EventNotEnabledError,
    GraphDoesNotExistError,
    SimulationNotRunningError,
    raise_,
)
from .models import EventNode, Overview


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
        self.refresh_simulations()

        # If the user knows what they want to initialize
        if graph_title is not None and simulation_title is not None:
            _ = self.attach_new_simulation(graph_title, simulation_title)

    def refresh_simulations(self) -> None:
        """Re-reads the simulation index from DCR, dropping stale entries."""
        self.simulations = {
            graph_title: {
                simulation.title: simulation.id
                for simulation in self.account.get_sims(graph_id)
            }
            for graph_title, graph_id in self.graphs.items()
        }

    # ====== Actions For Standard Users =========

    def attach_new_simulation(
        self, graph_title: str, simulation_title: str, reference_name: str = ""
    ) -> str:
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
        return name

    def kill_simulation(self, sim_name: str) -> None:
        running = self.running_simulations.get(sim_name) or raise_(
            SimulationNotRunningError(sim_name)
        )
        running.kill_simulation()

        self.running_simulations = {
            name: simulation
            for name, simulation in self.running_simulations.items()
            if simulation.sim_id != running.sim_id
        }
        for simulations in self.simulations.values():
            for title, sim_id in list(simulations.items()):
                if sim_id == running.sim_id:
                    del simulations[title]

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

    def show_next_event(self, sim_name: str) -> list[Event]:
        running = self.running_simulations.get(sim_name) or raise_(
            SimulationNotRunningError(sim_name)
        )
        return [
            event
            for event in running.state.events.values()
            if event.enabled
            and event.pending
            and not self._is_subprocess(event)
        ]

    def show_available_events(self, sim_name: str) -> list[Event]:
        running = self.running_simulations.get(sim_name) or raise_(
            SimulationNotRunningError(sim_name)
        )
        return [
            event
            for event in running.state.events.values()
            if event.enabled and not self._is_subprocess(event)
        ]

    def get_overview(self) -> Overview:
        self.refresh_simulations()
        return Overview(
            graphs=self.graphs,
            simulations=self.simulations,
            running={
                name: "finished" if self.is_finished(name) else "running"
                for name in self.running_simulations
            },
        )

    # ====== Helper Functions For validations ==========

    # Subprocess boxes are containers: DCR rejects executing them
    @staticmethod
    def _is_subprocess(event: Event) -> bool:
        return event.type.lower() == "subprocess"

    def _check_graph_existence(self, graph_title: str) -> None:
        if graph_title not in self.graphs:
            raise GraphDoesNotExistError(graph_title)

    def show_state(
        self, sim_name: str, only_events: bool = False
    ) -> list[EventNode]:
        running = self.running_simulations.get(sim_name) or raise_(
            SimulationNotRunningError(sim_name)
        )
        children: dict[str, list[Event]] = {}
        for event in running.state.events.values():
            children.setdefault(event.parent, []).append(event)

        if only_events:
            return [
                EventNode(event, [])
                for event in running.state.events.values()
                if event.id not in children
                and not self._is_subprocess(event)
            ]

        def node(event: Event) -> EventNode:
            return EventNode(
                event, [node(child) for child in children.get(event.id, [])]
            )

        return [node(event) for event in children.get("", [])]

    def is_finished(self, sim_name: str) -> bool:
        running = self.running_simulations.get(sim_name) or raise_(
            SimulationNotRunningError(sim_name)
        )
        return not any(
            event.pending and event.effectively_included
            for event in running.state.events.values()
        )
