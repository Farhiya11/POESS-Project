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

```powershell
docker compose up --build
```

Stop the stack with:

```powershell
docker compose down
```
