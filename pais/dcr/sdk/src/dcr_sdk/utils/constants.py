# Uniform Resource Locators
HOST: str = "https://repository.dcrgraphs.net"
ACCOUNT_GRAPHS_URL: str = f"{HOST}/api/graphs"
GRAPH_SIMS_URL: str = f"{HOST}/api/graphs/{{}}/sims"
INITIALIZE_SIMULATION_URL: str = GRAPH_SIMS_URL
SIMULATION_URL: str = f"{HOST}/api/graphs/{{}}/sims/{{}}"
SIMULATION_EVENTS_URL: str = f"{SIMULATION_URL}/events"


# Protocol Variables
DEFAULT_HEADERS: dict[str, str] = {"Content-Type": "application/json"}
