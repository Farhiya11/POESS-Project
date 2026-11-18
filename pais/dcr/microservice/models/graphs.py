from pydantic import BaseModel


class GraphSummary(BaseModel):
    id: int
    simulations: dict[str, int]
