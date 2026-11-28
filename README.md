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

## Preparedness warning decisions

The API adapter polls DMI for measured water levels every 10 minutes and sends
each new observation to Siddhi at
`POST http://siddhi:7076/water-level-observations`. Siddhi logs these readings
to the event-log service for monitoring; they do not affect preparedness
decisions. Forecasts are submitted separately as complete refreshes to
`POST http://siddhi:7077/forecast-refreshes`. Siddhi evaluates each refresh,
including the full forecast and policy snapshots in its result, and sends the
decision to `POST http://communication:5001/preparedness_decision`.
The integration service does not evaluate forecast thresholds; it manages
preparedness episodes and starts or updates the Camunda process. Refresh
outcomes, episode transitions, and Camunda preparedness task outcomes are sent
back to Siddhi at `POST http://siddhi:7072/middleman`, then forwarded to the
event-log service. Logging is fail-open: callback failures are reported in the
communication or Siddhi service logs and do not fail alert handling or a
Camunda task.
The Siddhi container installs the `siddhi-script-js` extension to run the
refresh evaluator in the Siddhi application.
`PREPAREDNESS_DECISION_SINK_URL` can override the adapter's default Siddhi
refresh endpoint when running outside the Compose network.
`WATER_LEVEL_OBSERVATION_SINK_URL` can override the water-level monitoring
endpoint.

The adapter's built-in `PREPAREDNESS_WARNING_POLICY_JSON` uses the supplied
DMI regional thresholds for the configured Copenhagen forecast location.
Override it to change region mappings or policy measures. It configures
regional warning categories independently from the existing 36-hour forecast
horizon and 6/4/2-hour preparedness cutoffs:

```json
{
  "forecast_horizon_hours": 36,
  "information_lead_hours": 6,
  "state_lead_hours": 4,
  "operational_lead_hours": 2,
  "regions": {
    "inner_danish_waters": {
      "category_1_min_cm": 125,
      "category_2_min_cm": 140,
      "category_3_above_cm": 160
    },
    "west_coast_jutland": {
      "category_1_min_cm": 190,
      "category_2_min_cm": 250,
      "category_3_above_cm": 300
    },
    "wadden_sea": {
      "category_1_min_cm": 240,
      "category_2_min_cm": 300,
      "category_3_above_cm": 400
    }
  },
  "locations": {
    "copenhagen": {
      "region": "inner_danish_waters"
    }
  }
}
```

The built-in policy has this shape. Map each additional monitored location to
the appropriate region. The supplied
overlapping endpoints are assigned to the more severe
category: Category 2 starts at 140/250/300 cm and Category 3 is strictly above
160/300/400 cm, respectively. Thresholds use the same units and reference
basis as the adapter's `sea_level_cm` forecasts.
An unset environment variable uses the built-in policy; setting it to an empty
value disables preparedness-warning decisions.

DMI warning category (`NONE`, `CATEGORY_1`, `CATEGORY_2`, or `CATEGORY_3`) is
kept separate from preparedness level (`INTERNAL`, `INFORMATION`, `STATE`, or
`OPERATIONAL`). Siddhi evaluates both for each complete forecast refresh.
Category and its forecast evidence are passed to Camunda as the
`dmiWarningCategory`, `categoryTimeToCriticalHours`, and
`categoryForecastValueCm` process variables; category changes are delivered
even when the preparedness level is unchanged. An unset policy environment
variable uses the built-in measures; an explicitly empty policy disables
preparedness-warning decisions. Malformed configuration or an unconfigured
location is reported as an error. The adapter sends the policy JSON to Siddhi
with each refresh; the adapter does not evaluate it.

The integration deploys both `BPMN_FILE` (food orders) and
`PREPAREDNESS_WARNING_BPMN_FILE` (disaster attention). The disaster process ID
defaults to `Process_0q7dfku` and can be overridden with
`PREPAREDNESS_WARNING_PROCESS_ID`. Active case IDs, process-instance keys, and
preparedness levels persist in the `preparedness_warning_state` Docker volume at
`/data/preparedness_warning_episodes.json`. A case ID and process
instance are reused while an alert episode remains active. Preparedness-level
and DMI-category updates are correlated to that case, and the BPMN waits for
later preparedness levels, category updates, or an alert-clear update,
including after the operational task has completed. Preparedness worker
actions, including operational notice, are currently simulations; no public
warning or evacuation is automatically performed.

## Prerequisites    

- Docker Engine or Docker Desktop
- Docker Compose
- DCR Graph credentials when using the DCR service

## Configuration

The preparedness/Camunda stack does not require DCR credentials:

```powershell
docker compose up --build -d
```

To enable DCR, put its credentials in the repository-root `.env` file and
start the `dcr` Compose profile:

```text
DCR_GRAPH_ID=...
DCR_USERNAME=...
DCR_PASSWORD=...
```

```powershell
docker compose --profile dcr up --build -d
```

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
returns the current DCR status (`running` or `finished`) to Siddhi on
`7075/middleman`. Siddhi logs each callback and emits a separate `DCR Case
Finished` event when the DCR simulation has no remaining pending events.

## Reading the logs

There are two places to look.

### Event log (what happened in each case)

The event-log service stores received events as JSON and XES. Preparedness
refresh and episode events include decision evidence and input snapshots.
Camunda task events use the corresponding BPMN task names, with the case ID,
timestamp, role, and task outcome recorded as event data. Active warning events
share the alert episode case ID; refreshes without an active warning use their
refresh ID. DCR callbacks continue to use the DCR simulation case ID.

New files are separated by process engine under
`event_logs_service/service/logs/`:

```text
bpmn/json/  bpmn/xes/
dcr/json/   dcr/xes/
```

Preparedness and Camunda callback events go under `bpmn`; DCR callbacks and the
DCR water-level monitoring events go under `dcr`. Existing files in the old
top-level `logs/` and `XES/` folders are left in place.

Each file name starts with the log service start time in `EVENT_LOG_TIMEZONE`,
including its UTC offset (for example, `261128_193800+0100`). Compose defaults
to `Europe/Copenhagen`; set `EVENT_LOG_TIMEZONE` in the root `.env` to another
IANA timezone when running from a PC in a different timezone. Event timestamps
inside JSON and XES remain UTC and include `+00:00`.

The XES logs can be imported into ProcessDoctor for conformance checking once a
matching DCR compliance model has been selected. This repository does not yet
document a compliance model for each implemented process or automate the
ProcessDoctor check. The broader course deliverables (six distinct process
models, student ownership, and identification of a knowledge-intensive
process) must be documented separately; event logging alone does not establish
them. The observation and forecast feeds currently both come from DMI, so
confirm whether the course counts these as two event sources or expects two
distinct source systems. Follow the event logger live with:

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
`Request type is not a type of POST`; Siddhi inputs must be called with `POST`.

Stop the stack with:

```sh
docker compose down
```
