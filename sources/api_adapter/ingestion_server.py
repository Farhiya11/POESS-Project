import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from functools import cache

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from constants import POLL_INTERVAL_SECONDS
from dmi import DMIClient, DMIParseError, DMIRequestError
from service import (
    DecisionSinkError,
    IngestionService,
    ObservationSinkError,
    PreparednessDecisionForwarder,
    WaterLevelObservationForwarder,
)

log = logging.getLogger("ingestion_server")


@cache
def ingestion() -> IngestionService:
    return IngestionService(
        DMIClient(),
        PreparednessDecisionForwarder(),
        WaterLevelObservationForwarder(),
    )


async def poll_forever() -> None:
    while True:
        for job in (
            ingestion().ingest_observations,
            ingestion().ingest_forecast,
        ):
            try:
                log.info("%s -> %s", job.__name__, await asyncio.to_thread(job))
            except (
                DMIRequestError,
                DMIParseError,
                DecisionSinkError,
                ObservationSinkError,
            ):
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


@app.exception_handler(DMIRequestError)
@app.exception_handler(DMIParseError)
async def dmi_error(_: Request, error: Exception) -> JSONResponse:
    return JSONResponse(status_code=502, content={"error": "dmi", "detail": str(error)})


@app.exception_handler(DecisionSinkError)
async def decision_sink_error(_: Request, error: DecisionSinkError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"error": "sink", "detail": str(error)})


@app.exception_handler(ObservationSinkError)
async def observation_sink_error(
    _: Request, error: ObservationSinkError
) -> JSONResponse:
    return JSONResponse(status_code=502, content={"error": "sink", "detail": str(error)})


@app.get("/health")
def health() -> dict[str, str]:
    service = ingestion()
    return {
        "status": "ok",
        "decision_sink": service.decision_forwarder.decision_sink_url,
        "observation_sink": service.observation_forwarder.observation_sink_url,
    }


@app.post("/ingest/observations")
def ingest_observations() -> IngestionResponse:
    result = ingestion().ingest_observations()
    return IngestionResponse(
        sent=result.sent,
        skipped_duplicates=result.skipped_duplicates,
    )


@app.post("/ingest/forecast")
def ingest_forecast() -> IngestionResponse:
    return IngestionResponse(sent=ingestion().ingest_forecast().sent)
