# Graph
GRAPH_ID = 4013

# Credentials
USERNAME = "test-user"
PASSWORD = "test-password"
INCORRECT_PASSWORD = "wrong-password"

# SDK Function Payload
TITLE = "Storm Surge Simulation"

# Call Function Payload
CALL_TITLE = '{"Title": "Storm Surge Simulation"}'

# Protocol Variables
INIT_HEADERS = {
    ":status": "201",
    "location": "repository.dcrgraphs.net/api/graphs/4013/sims/2108170",
    "server": "Microsoft-IIS/10.0",
    "www-authenticate": "Basic",
    "simulationid": "2108170",  # For some reason this is the response
    "x-dcr-simulation-id": "2108170",
    "last-modifieddate": "2026-05-21 09:09:47.867",
    "x-dcr-graph-modifiedtime": "2026-05-21 09:09:47.867",
    "x-powered-by": "ASP.NET",
    "date": "Fri, 06 Nov 2026 12:55:53 GMT",
}
