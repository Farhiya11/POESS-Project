
# Camunda Disaster Protocol – Review Guide

## Requirements
- Docker Desktop
- This GitHub branch: camunda-disaster-emba

## Start
Run from the repository root:

docker compose -f compose.camunda-review.yml up -d --build

## Test critical forecast
In PowerShell:

$body = '{"waterLevel":2.5,"criticalLevel":2.0,"location":"Test"}'
Invoke-RestMethod -Uri "http://localhost:7076/forecast" -Method Post -ContentType "application/json" -Body $body

## Test non-critical forecast

$body = '{"waterLevel":1.5,"criticalLevel":2.0,"location":"Test"}'
Invoke-RestMethod -Uri "http://localhost:7076/forecast" -Method Post -ContentType "application/json" -Body $body

## Verify results

Open Camunda Operate:
http://localhost:8082/operate

Or check the logs:

docker compose -f compose.camunda-review.yml logs --tail=30 communication

## Notes
- Use decimal numbers such as 2.0 in forecast JSON.
- Each request starts a new process instance.
- Preparedness notices are simulated.
- Event-by-event execution is not implemented yet.
- This isolated test stack does not require DCR credentials.

## BPMN files

- `Disaster_Attention_Protocol.bpmn` is the original process model, kept for reference.
- `Disaster_Attention_Protocol_camunda.bpmn` is the executable Camunda version, automatically deployed when the Docker test environment starts.

## Stop

docker compose -f compose.camunda-review.yml down
