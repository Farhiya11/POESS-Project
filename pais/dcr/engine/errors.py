class DCREngineError(Exception):
    """Base class for every error raised by the DCR engine."""


class GraphDoesNotExistError(DCREngineError):
    graph_title: str

    def __init__(self, graph_title: str):
        self.graph_title = graph_title
        super().__init__(f"Graph '{graph_title}' does not exist in the account")
