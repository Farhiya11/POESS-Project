class DCREngineError(Exception):
    """Base class for every error raised by the DCR engine."""


class SimulationDoesNotExistError(DCREngineError):
    simulation_title: str

    def __init__(self, simulation_title: str):
        self.simulation_title = simulation_title
        super().__init__(
            f"Simulation '{simulation_title}' does not exist in any of the account's graphs"
        )
