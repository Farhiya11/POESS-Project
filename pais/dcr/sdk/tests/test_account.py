from unittest.mock import MagicMock, patch

import requests

from dcr_sdk import Account, Graph, Sim

from .constants import (
    ACCOUNT_GRAPH_BODY,
    GRAPH_ID,
    GRAPH_SIMS_BODY,
    PASSWORD,
    USERNAME,
)


@patch.object(requests.Session, "request")
def test_get_graphs(mock_request: MagicMock):
    mock_request.return_value = MagicMock(
        text=ACCOUNT_GRAPH_BODY,
        raise_for_status=lambda: None,
    )

    assert Account(USERNAME, PASSWORD).get_graphs() == [
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


@patch.object(requests.Session, "request")
def test_get_sims(mock_request: MagicMock):
    mock_request.return_value = MagicMock(
        text=GRAPH_SIMS_BODY,
        raise_for_status=lambda: None,
    )

    assert Account(USERNAME, PASSWORD).get_sims(GRAPH_ID) == [
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
