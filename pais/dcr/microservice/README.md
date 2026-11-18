# Run

From the repository root, with `DCR_USERNAME` and `DCR_PASSWORD` set:

```bash
uv sync
uv run uvicorn app:app --app-dir pais/dcr/microservice --reload --port 5001
docker compose up --build microservice
```

Locally the API docs are at http://localhost:5001/docs (port 5002 with Docker).
