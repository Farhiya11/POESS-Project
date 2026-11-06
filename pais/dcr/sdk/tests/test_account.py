from unittest.mock import MagicMock, patch

from dcr_sdk.account import Account
from dcr_sdk.models import Graph

from .constants import ACCOUNT_GRAPH_BODY, PASSWORD, USERNAME


@patch("dcr_sdk.account.requests.request")
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
