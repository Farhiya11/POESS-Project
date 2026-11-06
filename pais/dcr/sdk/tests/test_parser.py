from dcr_sdk.models import Graph
from dcr_sdk.parser import parse_graphs

from .constants import ACCOUNT_GRAPH_BODY


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
