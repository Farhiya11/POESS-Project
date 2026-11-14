import os
import uuid

from dcr_sdk import Account, Simulation

from .errors import GraphDoesNotExistError


class DCR_Engine:
    account: Account
    graphs: dict[str, int]
    simulations: dict[str, dict[str, int]]
    running_simulations: dict[str, Simulation]

    # Configurations
    zen_mode: bool

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

    def _check_graph_existence(self, graph_title: str) -> None:
        if graph_title not in self.graphs:
            raise GraphDoesNotExistError(graph_title)

    # Attaches the simulation of the graph, creating it if it doesn't exist
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

    # Visualize Running Simulations
