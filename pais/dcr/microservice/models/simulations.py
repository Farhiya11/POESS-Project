from pydantic import BaseModel


class AttachRequest(BaseModel):
    graph_title: str
    simulation_title: str
    reference_name: str = ""


class AttachResponse(BaseModel):
    name: str
