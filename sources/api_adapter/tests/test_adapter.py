import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from constants import DEFAULT_PREPAREDNESS_WARNING_POLICY  # noqa: E402
from dmi import DMIClient, DMIParseError, DMIParser, DMIRequestError  # noqa: E402
from service import (  # noqa: E402
    DecisionSinkError,
    IngestionService,
    ObservationSinkError,
    PreparednessDecisionForwarder,
    WaterLevelObservationForwarder,
)

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
    observations = parser.observations(load("ocean_obs.json"))
    assert [observation.sea_level_cm for observation in observations] == [
        104.0,
        112.0,
    ]
    assert observations[0].to_event()["event_type"] == "WaterLevelObserved"


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


def test_observation_forwarder_posts_to_siddhi_monitoring_stream() -> None:
    session = MagicMock()
    session.post.return_value = response()
    observation = {
        "event_type": "WaterLevelObserved",
        "station_id": "30336",
        "observed_at": "2026-11-19T10:10:00+00:00",
        "sea_level_cm": 112.0,
        "parameter_id": "sealev_dvr",
        "source_system": "dmi.oceanObs",
        "ingested_at": "2026-11-19T10:11:00+00:00",
    }
    forwarder = WaterLevelObservationForwarder(
        observation_sink_url="http://siddhi:7076/water-level-observations",
        session=session,
    )

    forwarder.send_observation(observation)

    session.post.assert_called_once_with(
        "http://siddhi:7076/water-level-observations",
        json=observation,
        timeout=10,
    )


def test_observation_forwarder_raises_when_sink_fails() -> None:
    session = MagicMock()
    session.post.return_value = response(status=500)
    forwarder = WaterLevelObservationForwarder(
        observation_sink_url="http://sink", session=session
    )
    with pytest.raises(ObservationSinkError, match="water-level observation sink"):
        forwarder.send_observation({"station_id": "30336"})


def test_decision_forwarder_raises_when_sink_fails() -> None:
    session = MagicMock()
    session.post.return_value = response(status=500)
    forwarder = PreparednessDecisionForwarder(
        decision_sink_url="http://sink", session=session
    )
    with pytest.raises(DecisionSinkError):
        forwarder.send_forecast_refresh("copenhagen", [])


def test_forwarder_sends_complete_forecast_refresh_to_siddhi() -> None:
    session = MagicMock()
    session.post.return_value = response()
    policy_json = json.dumps(
        {
            "regions": {
                "inner_danish_waters": {
                    "category_1_min_cm": 125,
                    "category_2_min_cm": 140,
                    "category_3_above_cm": 160,
                }
            },
            "locations": {
                "copenhagen": {"region": "inner_danish_waters"}
            },
        }
    )
    forwarder = PreparednessDecisionForwarder(
        session=session,
        decision_sink_url="http://siddhi:7077/forecast-refreshes",
        policy_json=policy_json,
    )
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
    assert call.args == ("http://siddhi:7077/forecast-refreshes",)
    assert call.kwargs["json"]["location_id"] == "copenhagen"
    assert json.loads(call.kwargs["json"]["forecasts_json"]) == forecasts
    assert call.kwargs["json"]["policy_json"] == policy_json
    first_refresh_id = call.kwargs["json"]["refresh_id"]
    assert first_refresh_id

    updated_ingestion_time = [dict(forecasts[0], ingested_at="later-poll")]
    forwarder.send_forecast_refresh("copenhagen", updated_ingestion_time)
    assert session.post.call_args.kwargs["json"]["refresh_id"] != first_refresh_id


def test_default_preparedness_policy_contains_dmi_regional_thresholds() -> None:
    regions = DEFAULT_PREPAREDNESS_WARNING_POLICY["regions"]

    assert regions["inner_danish_waters"] == {
        "category_1_min_cm": 125,
        "category_2_min_cm": 140,
        "category_3_above_cm": 160,
    }
    assert regions["west_coast_jutland"] == {
        "category_1_min_cm": 190,
        "category_2_min_cm": 250,
        "category_3_above_cm": 300,
    }
    assert regions["wadden_sea"] == {
        "category_1_min_cm": 240,
        "category_2_min_cm": 300,
        "category_3_above_cm": 400,
    }
    assert DEFAULT_PREPAREDNESS_WARNING_POLICY["locations"]["copenhagen"] == {
        "region": "inner_danish_waters"
    }


def test_ingestion_dedups_observations() -> None:
    session = MagicMock()
    session.get.return_value = response(load("ocean_obs.json"))
    observation_forwarder = MagicMock()
    service = IngestionService(
        DMIClient(session=session),
        MagicMock(),
        observation_forwarder,
    )

    assert service.ingest_observations().sent == 2
    second = service.ingest_observations()

    assert (second.sent, second.skipped_duplicates) == (0, 2)
    assert observation_forwarder.send_observation.call_count == 2


def test_ingestion_forwards_complete_forecast_refresh() -> None:
    events = [
        {"event_type": "SeaLevelForecasted", "sea_level_cm": 100.0},
        {"event_type": "SeaLevelForecasted", "sea_level_cm": 120.0},
    ]
    forecasts = [MagicMock(to_event=MagicMock(return_value=event)) for event in events]
    client = MagicMock()
    client.forecast.return_value = forecasts
    decision_forwarder = MagicMock()
    service = IngestionService(client, decision_forwarder, MagicMock())

    result = service.ingest_forecast()

    assert result.sent == 1
    decision_forwarder.send_forecast_refresh.assert_called_once_with(
        "copenhagen", events
    )


def test_server_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    import ingestion_server

    decision_forwarder = PreparednessDecisionForwarder(
        decision_sink_url="http://sink",
        session=MagicMock(post=MagicMock(return_value=response())),
    )
    observation_forwarder = WaterLevelObservationForwarder(
        observation_sink_url="http://observation-sink",
        session=MagicMock(post=MagicMock(return_value=response())),
    )
    service = IngestionService(
        MagicMock(), decision_forwarder, observation_forwarder
    )
    service.client.forecast.side_effect = DMIRequestError("down")
    service.client.observations.return_value = []
    monkeypatch.setattr(ingestion_server, "ingestion", lambda: service)
    monkeypatch.setattr(ingestion_server, "POLL_INTERVAL_SECONDS", 10**6)

    client = TestClient(ingestion_server.app)
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/events").status_code == 404
    assert client.post("/replay", json={"events": []}).status_code == 404
    assert client.post("/ingest/observations").json() == {
        "sent": 0,
        "skipped_duplicates": 0,
    }
    failed = client.post("/ingest/forecast")
    assert failed.status_code == 502 and failed.json()["error"] == "dmi"
