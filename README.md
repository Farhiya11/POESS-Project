# POESS Flood Process Architecture

This repository contains a service-oriented flood-response architecture. External
data enters through an API adapter, Siddhi performs complex event processing, the
integration service routes canonical events to Camunda or DCR, and the logging
service produces process logs for conformance analysis.

## Structure

```text
POESS-project
C:.
│   .gitignore
│   docker-compose.yml
│   README.md
│           
├───cep 
│   └───apps
│           
├───event_logs_service
│   └───service
│           
├───integration
├───pais
│   ├───bpmn
│   │   └───microservice
│   │           
│   └───dcr
│       └───microservice
│               
├───scripts
└───sources
    └───api_adapter
```

## Responsibilities

- `cep` runs the Siddhi event-processing application.
- `sources/api_adapter` provides a template HTTP adapter for submitting orders.
- `integration` routes events to Camunda or DCR and normalizes callbacks.
- `pais/bpmn/microservice` contains the Camunda BPMN process.
  - bpmn files should follow the naming convention `P<number>-<name-of-process>.bpmn`.
- `pais/dcr/microservice` communicates with DCR Graph.
- `event_logs_service/service` stores JSON and XES process logs.

## Preparedness warning policy

`FloodDecisionApp.siddhi` accepts the API adapter's flat DMI events at
`POST http://siddhi:7076/events`. Set the adapter's `EVENT_SINK_URL` to that
URL (or `http://localhost:7076/events` when posting from the host). The input
contract is `WaterLevelObserved` or `SeaLevelForecasted`, with the fields
defined by the adapter event dataclasses.

The app logs source events with their flat DMI fields. Its Siddhi storm-surge
and forecast gates remain deliberately closed (`1 == 0`); the API adapter
separately sends each complete forecast refresh to
`POST http://communication:5001/forecast_refresh`.

Set `PREPAREDNESS_WARNING_POLICY_JSON` to enable the policy. Each monitored
location requires a `critical_sea_level_cm` value; the 36-hour horizon and
6/4/2-hour preparedness cutoffs default to the supplied domain values and can
also be overridden:

```json
{
  "forecast_horizon_hours": 36,
  "information_lead_hours": 6,
  "state_lead_hours": 4,
  "operational_lead_hours": 2,
  "locations": {
    "DMI_LOCATION_ID": {
      "critical_sea_level_cm": "<approved threshold in cm>"
    }
  }
}
```

Replace the example threshold with an approved value for each DMI location;
the service does not provide a guessed threshold. Configure the threshold in
the same units and reference basis as the adapter's `sea_level_cm` forecasts.
An unset policy disables preparedness-warning process starts, while malformed
configuration or an unconfigured location is reported as an error. Each complete refresh
selects the highest preparedness level indicated by any forecast in the
configured horizon.

The integration deploys both `BPMN_FILE` (food orders) and
`PREPAREDNESS_WARNING_BPMN_FILE` (disaster attention). The disaster process ID
defaults to `Process_0q7dfku` and can be overridden with
`PREPAREDNESS_WARNING_PROCESS_ID`. Active case IDs, process-instance keys, and
preparedness levels persist in the `preparedness_warning_state` Docker volume at
`/data/preparedness_warning_episodes.json`. A case ID and process
instance are reused while an alert episode remains active. Level updates are
correlated to that case, and the BPMN waits for later preparedness levels or
for an alert-clear update. Preparedness worker actions, including operational
notice, are currently simulations; no public warning or evacuation is
automatically performed.

## Prerequisites    

- Docker Engine or Docker Desktop
- Docker Compose
- DCR Graph credentials when using the DCR service

## Configuration

Set these variables before starting the stack if DCR is enabled:

```text
DCR_GRAPH_ID=...
DCR_USERNAME=...
DCR_PASSWORD=...
### DCR

DCR is event-driven. Starting a case creates a simulation and executes nothing.
You then choose which enabled event to run next.

1. Start a case: with the default graph, or pick one for this case:

   ```powershell
   python3 scripts/client_dcr.py flood-case-001
   python3 scripts/client_dcr.py flood-case-002 --graph "Exact Graph Title"
   ```

   `HTTP 202` means the adapter accepted the event. Processing is asynchronous,
   so wait briefly before checking the case.

2. Find the enabled events: Choose one whose `enabled` value is `true`:

   ```powershell
   curl.exe "http://localhost:5002/simulations/flood-case-001/state?only_events=true"
   ```

   Don't assume a first event ID. Each graph defines its own events and rules.

3. Execute an event: through the same client and adapter route:

   ```powershell
   python3 scripts/client_dcr.py flood-case-001 EVENT_ID
   ```

4. Repeat steps 2 and 3 until the case finishes. Check with:

   ```powershell
   curl.exe http://localhost:5002/simulations/flood-case-001
   ```

   The status becomes `finished` when the graph is done.

The state request is read-only and goes directly to the DCR microservice. Starting
a case and executing events always go through the adapter, Siddhi and the
integration service. After each start or event execution, the integration service
returns the current DCR status (`running` or `finished`) to Siddhi with the
callback. Siddhi logs each callback and emits a separate `DCR Case Finished`
event when the DCR simulation has no remaining pending events.

## Reading the logs

There are two places to look.

### Event log (what happened in each case)

Every executed step is sent to the event log service, which stores it as JSON and
XES. Follow it live with:

```powershell
docker compose logs -f event_logs_service
```
```

There are two ways to select the DCR graph; you can use both modes in the same
run:

1. Put a default graph title in a repository-root `.env` file. Starts without
   `--graph` use this graph:

```text
DCR_GRAPH_TITLE= Put the title of your own DCR graph
```

2. Pass `--graph "Exact Graph Title"` when starting a case. This selects that
   graph for that case and overrides the `.env` default only for that case. It
   does not change the default for other cases, and the default does not limit
   which other graphs you can select.

The root `.env` is ignored by Git, so create it locally if needed. After
changing the default, apply it by starting or recreating the integration
service with `docker compose up -d --build communication`. You can list exact
graph titles available from the DCR service with:

```sh
curl http://localhost:5002/graphs
```

## Running

Start the services in the background:

```sh
docker compose up --build -d
```

Check that the containers are running:

```sh
docker compose ps
```

On the first start, wait until `zeebe`, `siddhi`, and `communication` show
`healthy` before submitting events; the full stack can take a few minutes to
initialize.

Submit an event through the API adapter (the expected JSON fields are
`order_id` and `action`):


By default it sends `order-001` with the `PlaceOrder` action. Supply different
values as arguments:

```sh
python3 scripts/client.py order-002 CancelOrder
```

The adapter forwards the event to Siddhi at `/customer`. In Camunda mode,
Siddhi routes it to the communication service, which deploys and runs the BPMN
process. Open [Camunda Operate](http://localhost:8081/operate) to inspect
process instances. View service logs with:

```sh
docker compose logs -f communication siddhi event_logs_service
```

The Siddhi ports are HTTP event inputs, not browser pages. In particular,
`http://localhost:7071/` sends a `GET` to a `POST`-only input and returns
`Request type is not a type of POST`; use the adapter's `POST /events` endpoint
instead.

Stop the stack with:

```sh
docker compose down
```
