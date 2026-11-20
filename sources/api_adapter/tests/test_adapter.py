import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app as adapter  # noqa: E402
import dmi_client  # noqa: E402


def test_parse_observations_sorted_and_skips_null():
    obs = dmi_client.fetch_observations("30336", mock=True)
    assert [o.sea_level_cm for o in obs] == [104.0, 112.0]
    assert obs[0].to_event()["event_type"] == "WaterLevelObserved"


def test_parse_forecast_converts_metres_and_lead_time():
    fc = dmi_client.fetch_forecast("cph", 12.6, 55.69, mock=True)
    assert [f.sea_level_cm for f in fc] == [35.0, 90.0, 142.0]
    assert [f.lead_time_hours for f in fc] == [0.0, 12.0, 24.0]
    assert fc[0].to_event()["event_type"] == "SeaLevelForecasted"


def test_ingest_dedups_and_forwards(monkeypatch):
    sent = []
    monkeypatch.setattr(adapter, "MOCK_DMI", True)
    monkeypatch.setattr(adapter, "forward", lambda e: sent.append(e) or True)
    adapter._last_seen.clear()
    assert adapter.ingest_observations() == {"sent": 2, "skipped_duplicates": 0}
    assert adapter.ingest_observations() == {"sent": 0, "skipped_duplicates": 2}
    assert adapter.ingest_forecast() == {"sent": 3}
    assert len(sent) == 5


def test_routes(monkeypatch):
    monkeypatch.setattr(adapter, "MOCK_DMI", True)
    monkeypatch.setattr(adapter.requests, "post", lambda *a, **k: type("R", (), {"raise_for_status": lambda s: None})())
    client = adapter.app.test_client()
    assert client.get("/health").json["status"] == "ok"
    assert client.post("/ingest/forecast").json == {"sent": 3}
    assert client.post("/replay", json={"events": [{"event_type": "X"}]}).json == {"sent": 1, "failed": 0}
    assert client.get("/events?limit=1").json[0]["forwarded"] is True
