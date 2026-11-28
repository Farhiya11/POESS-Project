import importlib.util
import json
import sys
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest


SERVICE_APP = Path(__file__).resolve().parents[1] / "app.py"


@pytest.fixture
def log_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    log_dir = tmp_path / "logs"
    xes_dir = tmp_path / "xes"
    monkeypatch.setenv("EVENT_LOG_DIR", str(log_dir))
    monkeypatch.setenv("EVENT_XES_DIR", str(xes_dir))
    spec = importlib.util.spec_from_file_location("event_log_service_test_app", SERVICE_APP)
    assert spec is not None and spec.loader is not None
    service_app = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = service_app
    spec.loader.exec_module(service_app)
    return service_app.app.test_client(), service_app


def test_log_endpoint_preserves_preparedness_snapshot_in_json_and_xes(log_client):
    client, service_app = log_client
    decision = {
        "forecasts_json": '[{"sea_level_cm":145.0,"lead_time_hours":5}]',
        "policy_json": '{"forecast_horizon_hours":36}',
        "alert_level": "INFORMATION",
    }
    body = {
        "event": "Internal preparedness",
        "case_id": "episode-1",
        "order_id": "refresh-1",
        "timestamp": "2026-11-28T12:00:00+00:00",
        "role": "camunda",
        "payload": json.dumps(
            {
                "process_name": "Storm Surge Preparedness",
                "lifecycle": "complete",
                "decision": decision,
            }
        ),
    }

    response = client.post("/log", json=body)

    assert response.status_code == 200
    stored = json.loads(service_app.EVENT_STORE.read_text(encoding="utf-8"))
    assert stored[0]["payload"]["decision"] == decision
    assert stored[0]["case_id"] == "episode-1"

    root = ET.parse(service_app.XES_FILE).getroot()
    trace = root.find("trace")
    assert trace is not None
    assert trace.find("string[@key='concept:name']").attrib["value"] == "episode-1"
    event = trace.find("event")
    assert event is not None
    assert event.find("string[@key='concept:name']").attrib["value"] == (
        "Internal preparedness"
    )
    decision_attribute = event.find("string[@key='payload:decision']")
    assert decision_attribute is not None
    assert json.loads(decision_attribute.attrib["value"]) == decision


def test_concurrent_posts_are_not_lost_from_json_or_xes(log_client):
    _, service_app = log_client

    def post_event(index: int) -> int:
        with service_app.app.test_client() as client:
            response = client.post(
                "/log",
                json={
                    "event": "Internal preparedness",
                    "case_id": "episode-concurrent",
                    "timestamp": f"2026-11-28T12:00:{index:02d}+00:00",
                    "role": "camunda",
                    "payload": {"sequence": index},
                },
            )
            return response.status_code

    event_count = 32
    with ThreadPoolExecutor(max_workers=8) as executor:
        statuses = list(executor.map(post_event, range(event_count)))

    stored = json.loads(service_app.EVENT_STORE.read_text(encoding="utf-8"))
    root = ET.parse(service_app.XES_FILE).getroot()
    assert statuses == [200] * event_count
    assert len(stored) == event_count
    assert len(root.findall("trace/event")) == event_count
