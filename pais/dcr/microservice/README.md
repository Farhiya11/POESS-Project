# Run

From the repository root, with `DCR_USERNAME` and `DCR_PASSWORD` set in the
environment or root `.env` file:

```bash
uv sync
uv run uvicorn app:app --app-dir pais/dcr/microservice --reload --port 5001
docker compose --profile dcr up --build -d microservice
```

Locally the API docs are at http://localhost:5001/docs (port 5002 with Docker).
