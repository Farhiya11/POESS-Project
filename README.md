# POESS Flood Process Architecture

This repository contains a service-oriented flood-response architecture. External
data enters through an API adapter, Siddhi performs complex event processing, the
integration service routes canonical events to Camunda or DCR, and the logging
service produces process logs for conformance analysis.

## Structure

```text
POESS-project/
├── sources/api_adapter/
├── cep/
├── integration/
├── pais/camunda/
├── pais/dcr/microservice/
├── logging/service/
├── README.md
└── docker-compose.yml
```

## Responsibilities

- `sources/api_adapter` consumes API data from external systems.
- `cep` filters events and emits derived flood events through Siddhi.
- `integration` routes events to Camunda or DCR and normalizes callbacks.
- `pais/camunda/bpmn` deploys and runs the flood-response BPMN process.
- `pais/dcr/microservice` communicates with DCR Graph.
- `logging/service` stores JSON and XES process logs.

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

```powershell
docker compose up --build
```

Stop the stack with:

```powershell
docker compose down
```
