import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from functools import cache
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from constants import POLL_INTERVAL_SECONDS
from dmi import DMIClient, DMIParseError, DMIRequestError
from service import EventForwarder, ForwardError, IngestionService

log = logging.getLogger("ingestion_server")


@cache
def ingestion() -> IngestionService:
    return IngestionService(DMIClient(), EventForwarder())


async def poll_forever() -> None:
    while True:
        for job in (ingestion().ingest_observations, ingestion().ingest_forecast):
            try:
                log.info("%s -> %s", job.__name__, await asyncio.to_thread(job))
            except (DMIRequestError, DMIParseError, ForwardError):
                log.exception("%s failed, retrying next round", job.__name__)
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    task = asyncio.create_task(poll_forever())
    yield
    task.cancel()


app = FastAPI(title="DMI Ingestion Service", lifespan=lifespan)


class IngestionResponse(BaseModel):
    sent: int
    skipped_duplicates: int = 0


class ReplayRequest(BaseModel):
    events: list[dict[str, Any]]


@app.exception_handler(DMIRequestError)
@app.exception_handler(DMIParseError)
async def dmi_error(_: Request, error: Exception) -> JSONResponse:
    return JSONResponse(status_code=502, content={"error": "dmi", "detail": str(error)})


@app.exception_handler(ForwardError)
async def forward_error(_: Request, error: ForwardError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"error": "sink", "detail": str(error)})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "sink": ingestion().forwarder.sink_url}


@app.post("/ingest/observations")
def ingest_observations() -> IngestionResponse:
    result = ingestion().ingest_observations()
    return IngestionResponse(sent=result.sent, skipped_duplicates=result.skipped_duplicates)


@app.post("/ingest/forecast")
def ingest_forecast() -> IngestionResponse:
    return IngestionResponse(sent=ingestion().ingest_forecast().sent)


@app.get("/events")
def recent_events(limit: int = Query(50, ge=1, le=500)) -> list[dict[str, Any]]:
    return ingestion().forwarder.recent(limit)


@app.post("/replay")
def replay(body: ReplayRequest) -> IngestionResponse:
    for event in body.events:
        ingestion().forwarder.send(event)
    return IngestionResponse(sent=len(body.events))
