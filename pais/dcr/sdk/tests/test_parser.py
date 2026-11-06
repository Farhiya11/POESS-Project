from dcr_sdk.models.models import Graph, Sim
from dcr_sdk.utils.parser import parse_graphs, parse_sims

from .constants import ACCOUNT_GRAPH_BODY, GRAPH_SIMS_BODY


def test_parse_graphs():
    assert parse_graphs(ACCOUNT_GRAPH_BODY) == [
        Graph(
            id=2016035,
            title="DCR_Test",
            description="DCR Process",
            created="2026-11-04T18:18:29.430",
            modified="2026-11-04T18:21:06.733",
        ),
        Graph(
            id=2016043,
            title="Payout",
            description="DCR Process",
            created="2026-11-05T08:55:00.140",
            modified="2026-11-05T08:56:49.057",
        ),
    ]


def test_parse_graphs_empty():
    assert parse_graphs("<graphs></graphs>") == []


def test_parse_sims():
    assert parse_sims(GRAPH_SIMS_BODY) == [
        Sim(
            id=2108181,
            title="DCR",
            init="2026-11-06T20:45:44",
            percentage=0.0,
            is_scenario=False,
            created="2026-11-06T20:45:44.127Z",
            created_by=176191,
            modified="2026-11-06T21:45:44.120Z",
            modified_by=176191,
            business_type="none",
        ),
        Sim(
            id=2108182,
            title="DCR",
            init="2026-11-06T20:47:26",
            percentage=0.0,
            is_scenario=False,
            created="2026-11-06T20:47:26.247Z",
            created_by=176191,
            modified="2026-11-06T21:47:26.243Z",
            modified_by=176191,
            business_type="none",
        ),
    ]


def test_parse_sims_empty():
    assert parse_sims("<log></log>") == []
