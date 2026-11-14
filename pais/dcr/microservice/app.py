from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from functools import cache

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from dcr_engine import (
    DCR_Engine,
    DCREngineError,
    EventNode,
    GraphDoesNotExistError,
    SimulationNotRunningError,
)
from models import AttachRequest, AttachResponse, GraphSummary


# One engine per process, shared by every request
@cache
def engine() -> DCR_Engine:
    return DCR_Engine()


# Loads the graph index on startup instead of on the first request
@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    _ = engine()
    yield


app = FastAPI(title="DCR Microservice", lifespan=lifespan)


@app.exception_handler(DCREngineError)
def engine_error(_: Request, error: DCREngineError) -> JSONResponse:
    not_found = (GraphDoesNotExistError, SimulationNotRunningError)
    status = 404 if isinstance(error, not_found) else 409
    return JSONResponse(status_code=status, content={"detail": str(error)})


@app.get("/graphs")
def list_graphs() -> dict[str, GraphSummary]:
    graphs = engine().graphs
    simulations = engine().simulations
    return {
        title: GraphSummary(id=graph_id, simulations=simulations[title])
        for title, graph_id in graphs.items()
    }


# Resumes the simulation with that title, or creates it if it doesn't exist
@app.post("/simulations", status_code=201)
def attach_simulation(body: AttachRequest) -> AttachResponse:
    name = engine().attach_new_simulation(
        body.graph_title, body.simulation_title, body.reference_name
    )
    return AttachResponse(name=name)


@app.get("/simulations/{sim_name}/state")
def simulation_state(
    sim_name: str, only_events: bool = False
) -> list[EventNode]:
    return engine().show_state(sim_name, only_events)


@app.delete("/simulations/{sim_name}", status_code=204)
def kill_simulation(sim_name: str) -> None:
    engine().kill_simulation(sim_name)
