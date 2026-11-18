from dcr_engine import SimulationStatus
from pydantic import BaseModel, Field

# ======================================================================
# REQUESTS MODELS
# ======================================================================


class AttachRequest(BaseModel):
    graph_title: str
    simulation_title: str
    reference_name: str = ""


class ExecuteEventRequest(BaseModel):
    event_ids: list[str] = Field(min_length=1)


# ======================================================================
# RESPONSE MODELS
# ======================================================================


class AttachResponse(BaseModel):
    name: str


class ExecuteEventResponse(BaseModel):
    events: str


class SimulationStatusResponse(BaseModel):
    name: str
    status: SimulationStatus
