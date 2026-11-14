class DCREngineError(Exception):
    """Base class for every error raised by the DCR engine."""


class GraphDoesNotExistError(DCREngineError):
    graph_title: str

    def __init__(self, graph_title: str):
        self.graph_title = graph_title
        super().__init__(f"Graph '{graph_title}' does not exist in the account")


# ====== Request Non-Conformance =======


class RequestNonConformanceError(DCREngineError):
    """A request that does not conform to the simulation it targets."""


class EventDoesNotExistError(RequestNonConformanceError):
    event_id: str

    def __init__(self, event_id: str):
        self.event_id = event_id
        super().__init__(f"Event '{event_id}' does not exist in the graph")


class EventNotEnabledError(RequestNonConformanceError):
    event_id: str

    def __init__(self, event_id: str):
        self.event_id = event_id
        super().__init__(f"Event '{event_id}' is not enabled")

