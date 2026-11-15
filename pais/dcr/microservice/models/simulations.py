from pydantic import BaseModel

# ======================================================================
# REQUESTS MODELS
# ======================================================================


class AttachRequest(BaseModel):
    graph_title: str
    simulation_title: str
    reference_name: str = ""


class ExecuteEventRequest(BaseModel):
    event_ids: list[str] = []


# ======================================================================
# RESPONSE MODELS
# ======================================================================


class AttachResponse(BaseModel):
    name: str


class ExecuteEventResponse(BaseModel):
    events: str
