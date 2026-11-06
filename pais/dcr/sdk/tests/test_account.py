from unittest.mock import MagicMock, patch

from dcr_sdk.account import Account
from dcr_sdk.constants import ACCOUNT_GRAPHS_URL

from .constants import GRAPHS_XML, PASSWORD, USERNAME


@patch("dcr_sdk.account.requests.request")
def test_show_graphs(mock_request: MagicMock):
    mock_request.return_value = MagicMock(
        status_code=200,
        text=GRAPHS_XML,
        raise_for_status=lambda: None,
    )

    result = Account(USERNAME, PASSWORD).show_graphs()

    assert result == GRAPHS_XML

    mock_request.assert_called_once_with(
        "GET",
        ACCOUNT_GRAPHS_URL,
        headers={"Content-Type": "application/json"},
        auth=(USERNAME, PASSWORD),
    )
