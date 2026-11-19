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
