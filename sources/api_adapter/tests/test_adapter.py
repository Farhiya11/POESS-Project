import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dmi import DMIClient, DMIParseError, DMIParser, DMIRequestError  # noqa: E402
from service import EventForwarder, ForwardError, IngestionService  # noqa: E402

MOCK = Path(__file__).parent / "mock_data"


def load(name: str) -> dict:
    return json.loads((MOCK / name).read_text())


def response(payload: dict | None = None, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.side_effect = requests.HTTPError(str(status)) if status >= 400 else None
    return resp


@pytest.fixture
def parser() -> DMIParser:
    return DMIParser()


def test_observations_sorted_and_null_dropped(parser: DMIParser) -> None:
    obs = parser.observations(load("ocean_obs.json"))
    assert [o.sea_level_cm for o in obs] == [104.0, 112.0]
    assert obs[0].to_event()["event_type"] == "WaterLevelObserved"


def test_forecast_metres_to_cm_and_lead_time(parser: DMIParser) -> None:
    raw = load("forecast_edr.json")
    issued = parser.parse_time(raw["domain"]["axes"]["t"]["values"][0])
    fc = parser.forecast(raw, "cph", issued_at=issued)
    assert [f.sea_level_cm for f in fc] == [35.0, 90.0, 142.0]
    assert [f.lead_time_hours for f in fc] == [0.0, 12.0, 24.0]


def test_parser_rejects_bad_shapes(parser: DMIParser) -> None:
    with pytest.raises(DMIParseError):
        parser.observations({})
    with pytest.raises(DMIParseError):
        parser.forecast({"domain": {}}, "cph")


def test_client_wraps_http_errors() -> None:
    session = MagicMock()
    session.get.return_value = response(status=503)
    with pytest.raises(DMIRequestError):
        DMIClient(session=session).observations("30336")


def test_forwarder_raises_when_sink_fails() -> None:
    session = MagicMock()
    session.post.return_value = response(status=500)
    forwarder = EventForwarder("http://sink", session=session)
    with pytest.raises(ForwardError):
        forwarder.send({"event_type": "X"})
    assert forwarder.recent(10) == []


def test_forwarder_sends_flat_dmi_event() -> None:
    session = MagicMock()
    session.post.return_value = response()
    event = {
        "event_type": "SeaLevelForecasted",
        "location_id": "copenhagen",
        "sea_level_cm": 142.0,
    }
    forwarder = EventForwarder("http://siddhi:7076/events", session=session)

    forwarder.send(event)

    session.post.assert_called_once_with(
        "http://siddhi:7076/events",
        json=event,
        timeout=10,
    )
    assert forwarder.recent(1) == [event]


def test_forwarder_sends_complete_forecast_refresh() -> None:
    session = MagicMock()
    session.post.return_value = response()
    forwarder = EventForwarder("http://sink", session=session)
    forecasts = [
        {
            "event_type": "SeaLevelForecasted",
            "location_id": "copenhagen",
            "forecast_for": "2026-11-26T14:00:00+00:00",
            "sea_level_cm": 142.0,
            "lead_time_hours": 1.0,
            "ingested_at": "first-poll",
        }
    ]

    forwarder.send_forecast_refresh("copenhagen", forecasts)

    call = session.post.call_args
    assert call.args == ("http://communication:5001/forecast_refresh",)
    assert call.kwargs["json"]["location_id"] == "copenhagen"
    assert call.kwargs["json"]["forecasts"] == forecasts
    refresh_id = call.kwargs["json"]["refresh_id"]
    assert len(refresh_id) == 64

    updated_ingestion_time = [dict(forecasts[0], ingested_at="later-poll")]
    forwarder.send_forecast_refresh("copenhagen", updated_ingestion_time)
    assert session.post.call_args.kwargs["json"]["refresh_id"] == refresh_id


def test_ingestion_dedups_observations() -> None:
    session = MagicMock()
    session.get.return_value = response(load("ocean_obs.json"))
    forwarder = MagicMock()
    service = IngestionService(DMIClient(session=session), forwarder)
    assert service.ingest_observations().sent == 2
    second = service.ingest_observations()
    assert (second.sent, second.skipped_duplicates) == (0, 2)
    assert forwarder.send.call_count == 2


def test_ingestion_forwards_complete_forecast_refresh() -> None:
    events = [
        {"event_type": "SeaLevelForecasted", "sea_level_cm": 100.0},
        {"event_type": "SeaLevelForecasted", "sea_level_cm": 120.0},
    ]
    forecasts = [MagicMock(to_event=MagicMock(return_value=event)) for event in events]
    client = MagicMock()
    client.forecast.return_value = forecasts
    forwarder = MagicMock()
    service = IngestionService(client, forwarder)

    result = service.ingest_forecast()

    assert result.sent == 2
    forwarder.send_forecast_refresh.assert_called_once_with("copenhagen", events)
    assert forwarder.send.call_args_list[0].args == (events[0],)
    assert forwarder.send.call_args_list[1].args == (events[1],)


def test_server_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    import ingestion_server

    forwarder = EventForwarder("http://sink", session=MagicMock(post=MagicMock(return_value=response())))
    service = IngestionService(MagicMock(), forwarder)
    service.client.forecast.side_effect = DMIRequestError("down")
    monkeypatch.setattr(ingestion_server, "ingestion", lambda: service)
    monkeypatch.setattr(ingestion_server, "POLL_INTERVAL_SECONDS", 10**6)

    client = TestClient(ingestion_server.app)
    assert client.get("/health").json()["status"] == "ok"
    assert client.post("/replay", json={"events": [{"event_type": "X"}]}).json()["sent"] == 1
    assert client.get("/events", params={"limit": 1}).json() == [{"event_type": "X"}]
    failed = client.post("/ingest/forecast")
    assert failed.status_code == 502 and failed.json()["error"] == "dmi"
