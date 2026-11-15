from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from functools import cache

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pais.dcr.microservice.models.simulations import (
    ExecuteEventRequest,
    ExecuteEventResponse,
)

from dcr_engine import (
    DCR_Engine,
    DCREngineError,
    EventDoesNotExistError,
    EventNode,
    GraphDoesNotExistError,
    SimulationNotRunningError,
)
from models import AttachRequest, AttachResponse, GraphSummary

# ======================================================================
# MICRO-SERVICE START SEQUENCE
# ======================================================================


@cache
def engine() -> DCR_Engine:
    return DCR_Engine()


# Loads the graph index on startup instead of
# on the first request :)
@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    _ = engine()
    yield


app = FastAPI(title="DCR Microservice", lifespan=lifespan)

# ======================================================================
# EXCEPTION HANDLERS
# ======================================================================


def status_for(error: DCREngineError) -> int:
    not_found = (
        GraphDoesNotExistError,
        SimulationNotRunningError,
        EventDoesNotExistError,
    )
    return 404 if isinstance(error, not_found) else 409


@app.exception_handler(DCREngineError)
async def engine_error(_: Request, error: DCREngineError) -> JSONResponse:
    return JSONResponse(
        status_code=status_for(error), content={"detail": str(error)}
    )


# ======================================================================
# GRAPH ROUTES
# ======================================================================


@app.get("/graphs")
def list_graphs() -> dict[str, GraphSummary]:
    graphs = engine().graphs
    simulations = engine().simulations
    return {
        title: GraphSummary(id=graph_id, simulations=simulations[title])
        for title, graph_id in graphs.items()
    }


# ======================================================================
# SIMULATION ROUTES
# ======================================================================

# ---- POST ROUTES ----


@app.post("/simulations", status_code=201)
def attach_simulation(body: AttachRequest) -> AttachResponse:
    name = engine().attach_new_simulation(
        body.graph_title, body.simulation_title, body.reference_name
    )
    return AttachResponse(name=name)


# ---- GET ROUTES ----


@app.get("/simulations/{sim_name}/state")
def simulation_state(
    sim_name: str, only_events: bool = False
) -> list[EventNode]:
    return engine().show_state(sim_name, only_events)


# ---- DELETE ROUTES ----


@app.delete("/simulations/{sim_name}", status_code=204)
def kill_simulation(sim_name: str) -> None:
    engine().kill_simulation(sim_name)


# ======================================================================
# EVENT ROUTES
# ======================================================================

# ---- POST ROUTES ----


@app.post("/simulation/{sim_name}/events")
def execute_event(
    sim_name: str, body: ExecuteEventRequest
) -> ExecuteEventResponse:
    # Executed one by one so a failure can report how far the sequence got,
    # since the events that already ran are not rolled back.
    executed: list[str] = []
    for event_id in body.event_ids:
        try:
            engine().execute_single_transition(sim_name, event_id)
        except DCREngineError as error:
            raise HTTPException(
                status_code=status_for(error),
                detail={
                    "message": str(error),
                    "executed": executed,
                    "failed_at": event_id,
                },
            ) from error
        executed.append(event_id)
    return ExecuteEventResponse(
        events=f"Executed successfully: [{', '.join(body.event_ids)}]"
    )


# ---- GET ROUTES ----


@app.get("/simulation/{sim_name}/events")
def events(sim_name: str) -> list[EventNode]:
    return engine().show_state(sim_name, True)
