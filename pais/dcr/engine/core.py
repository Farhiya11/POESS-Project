import os
import sys
import uuid

from dcr_sdk import Account, Simulation

from .errors import SimulationDoesNotExistError


class DCR_Engine:
    # Core
    account: Account

    # Metadata
    graphs: dict[str, int]
    simulations: dict[str, tuple[int, int]]
    running_simulations: dict[str, Simulation]

    # Configurations
    zen_mode: bool

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
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
        self.simulations = {}
        for graph_id in self.graphs.values():
            self.simulations.update(
                {
                    simulation.title: (simulation.id, graph_id)
                    for simulation in self.account.get_sims(graph_id)
                }
            )

        # If the user knows what they want to initialize
        if simulation_title is not None:
            self.attach_new_simulation(simulation_title)

    def _check_simulation_existence(self, simulation_title: str) -> None:
        if simulation_title not in self.simulations.keys():
            raise SimulationDoesNotExistError(simulation_title)

    def attach_new_simulation(
        self, simulation_title: str, reference_name: str = ""
    ) -> None:
        self._check_simulation_existence(simulation_title)

        name = reference_name or simulation_title
        if name in self.running_simulations:
            name = f"{name}-{uuid.uuid4()}"

        sim_id, graph_id = self.simulations[simulation_title]
        self.running_simulations[name] = Simulation(
            graph_id, self.account, sim_id, simulation_title
        )


def __main__():
    args = sys.argv[1:]
    zen = "zen" in args
    titles = [arg for arg in args if arg != "zen"]

    engine = DCR_Engine(zen_mode=zen)

    print("\n==== SIMULATIONS =====\n")
    for title, (sim_id, graph_id) in engine.simulations.items():
        print(graph_id, sim_id, title)

    if not titles:
        return

    try:
        engine.attach_new_simulation(titles[0])
    except SimulationDoesNotExistError as error:
        print(f"\n{error}")
        return

    # Same default name again, so the engine attaches a uuid to it
    engine.attach_new_simulation(titles[0])

    print("\n==== RUNNING SIMULATIONS =====\n")
    for reference_name in engine.running_simulations:
        print(reference_name)
    print()

    engine.running_simulations[titles[0]].print_events(engine.zen_mode)


if __name__ == "__main__":
    __main__()
