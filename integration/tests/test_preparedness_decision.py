import asyncio
import importlib.util
import json
import json as json_module
import sys
from pathlib import Path

import pytest

from integration.preparedness_episode_store import PreparednessEpisodeStore

INTEGRATION_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(INTEGRATION_DIR))
APP_SPEC = importlib.util.spec_from_file_location(
    "preparedness_communication_app", INTEGRATION_DIR / "app.py"
)
assert APP_SPEC is not None and APP_SPEC.loader is not None
communication_app = importlib.util.module_from_spec(APP_SPEC)
sys.modules[APP_SPEC.name] = communication_app
APP_SPEC.loader.exec_module(communication_app)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(
        communication_app,
        "preparedness_episode_store",
        PreparednessEpisodeStore(tmp_path / "episodes.json"),
    )
    emitted_events = []

    class CallbackResponse:
        def raise_for_status(self):
            return None

    def capture_callback(url, *, json, timeout):
        event = dict(json)
        event["url"] = url
        event["timeout"] = timeout
        event["payload"] = json_module.loads(event["payload"])
        emitted_events.append(event)
        return CallbackResponse()

    monkeypatch.setattr(communication_app.requests, "post", capture_callback)
    communication_app.app.config["TEST_PREPAREDNESS_EVENTS"] = emitted_events
    return communication_app.app.test_client()


def send_decision(client, payload: dict, *, event_wrapper: bool = False):
    event = {"decision_json": json.dumps(payload)}
    body = {"event": event} if event_wrapper else event
    return client.post(
        "/preparedness_decision",
        json=body,
    )


def test_siddhi_disabled_policy_does_not_change_episode_state(client) -> None:
    response = send_decision(
        client,
        {
            "status": "disabled",
            "refresh_id": "refresh-1",
            "location_id": "copenhagen",
            "forecasts_json": "[]",
            "policy_json": "",
        },
        event_wrapper=True,
    )

    assert response.status_code == 200
    assert response.json["status"] == "disabled"
    logged = client.application.config["TEST_PREPAREDNESS_EVENTS"]
    assert logged[0]["event"] == "PreparednessRefreshDisabled"
    assert logged[0]["case_id"] == "preparedness-refresh-refresh-1"
    assert logged[0]["payload"]["decision"]["forecasts_json"] == "[]"
    assert logged[0]["url"] == communication_app.SIDDHI_CALLBACK_URL
    assert not communication_app.preparedness_episode_store.has_processed_refresh(
        "copenhagen", "refresh-1"
    )


def test_siddhi_none_decision_clears_and_deduplicates_refresh(client) -> None:
    payload = {
        "status": "decision",
        "refresh_id": "refresh-1",
        "location_id": "copenhagen",
        "alert_level": "NONE",
        "dmi_warning_category": "NONE",
        "time_to_critical_hours": None,
        "forecast_value_cm": None,
        "critical_level_cm": 100.0,
        "category_time_to_critical_hours": None,
        "category_forecast_value_cm": None,
        "reason": "no_threshold_exceedance_within_forecast_horizon",
    }

    response = send_decision(client, payload)
    duplicate = send_decision(client, payload)

    assert response.status_code == 200
    assert response.json["status"] == "clear"
    assert duplicate.status_code == 200
    assert duplicate.json["status"] == "duplicate"
    assert communication_app.preparedness_episode_store.has_processed_refresh(
        "copenhagen", "refresh-1"
    )


def test_invalid_siddhi_decision_is_rejected(client) -> None:
    response = send_decision(
        client,
        {
            "status": "decision",
            "refresh_id": "refresh-1",
            "location_id": "copenhagen",
            "alert_level": "UNRECOGNIZED",
            "dmi_warning_category": "NONE",
            "reason": "invalid",
        },
    )

    assert response.status_code == 400
    assert response.json["error"] == "alert_level is invalid"


def test_invalid_dmi_warning_category_is_rejected(client) -> None:
    response = send_decision(
        client,
        {
            "status": "decision",
            "refresh_id": "refresh-1",
            "location_id": "copenhagen",
            "alert_level": "NONE",
            "dmi_warning_category": "CATEGORY_4",
            "reason": "invalid",
        },
    )

    assert response.status_code == 400
    assert response.json["error"] == "dmi_warning_category is invalid"


def test_category_change_is_sent_to_the_existing_camunda_process(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    published_decisions = []
    monkeypatch.setattr(
        communication_app,
        "start_preparedness_warning_process",
        lambda **kwargs: "process-1",
    )
    monkeypatch.setattr(
        communication_app,
        "publish_alert_level",
        lambda case_id, refresh_id, decision: published_decisions.append(decision),
    )

    def active_payload(refresh_id: str, category: str) -> dict:
        return {
            "status": "decision",
            "refresh_id": refresh_id,
            "location_id": "copenhagen",
            "alert_level": "INFORMATION",
            "dmi_warning_category": category,
            "time_to_critical_hours": 5.0,
            "forecast_value_cm": 145.0,
            "critical_level_cm": 125.0,
            "category_time_to_critical_hours": 5.0,
            "category_forecast_value_cm": 145.0,
            "reason": "threshold_exceeded_within_information_window",
        }

    opened = send_decision(client, active_payload("refresh-1", "CATEGORY_1"))
    changed = send_decision(client, active_payload("refresh-2", "CATEGORY_2"))

    assert opened.status_code == 200
    assert changed.status_code == 200
    assert changed.json["alert_level"] == "INFORMATION"
    assert changed.json["dmi_warning_category"] == "CATEGORY_2"
    assert len(published_decisions) == 1
    assert published_decisions[0].dmi_warning_category == "CATEGORY_2"
    variables = communication_app.decision_variables(
        "case-1", "refresh-2", published_decisions[0]
    )
    assert variables["dmiWarningCategory"] == "CATEGORY_2"
    assert variables["categoryForecastValueCm"] == 145.0
    case_id = communication_app.preparedness_episode_store.case_id_for("copenhagen")
    assert case_id is not None
    assert (
        communication_app.preparedness_episode_store.dmi_warning_category_for(case_id)
        == "CATEGORY_2"
    )


def test_preparedness_audit_events_keep_snapshots_and_episode_case_id(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        communication_app,
        "start_preparedness_warning_process",
        lambda **kwargs: "process-1",
    )
    monkeypatch.setattr(
        communication_app,
        "publish_alert_level",
        lambda *args, **kwargs: None,
    )
    payload = {
        "status": "decision",
        "refresh_id": "refresh-active",
        "location_id": "copenhagen",
        "alert_level": "INFORMATION",
        "dmi_warning_category": "CATEGORY_1",
        "time_to_critical_hours": 5.0,
        "forecast_value_cm": 145.0,
        "critical_level_cm": 125.0,
        "category_time_to_critical_hours": 5.0,
        "category_forecast_value_cm": 145.0,
        "reason": "threshold_exceeded_within_information_window",
        "forecasts_json": '[{"sea_level_cm":145.0,"lead_time_hours":5}]',
        "policy_json": '{"forecast_horizon_hours":36}',
    }

    response = send_decision(client, payload)
    clear_response = send_decision(
        client,
        {
            "status": "decision",
            "refresh_id": "refresh-clear",
            "location_id": "copenhagen",
            "alert_level": "NONE",
            "dmi_warning_category": "NONE",
            "time_to_critical_hours": None,
            "forecast_value_cm": None,
            "critical_level_cm": 125.0,
            "category_time_to_critical_hours": None,
            "category_forecast_value_cm": None,
            "reason": "no_threshold_exceedance_within_forecast_horizon",
            "forecasts_json": "[]",
            "policy_json": "{}",
        },
    )

    assert response.status_code == 200
    assert clear_response.json["transition"] == "cleared"
    events = client.application.config["TEST_PREPAREDNESS_EVENTS"]
    evaluated = next(
        event for event in events
        if event["event"] == "PreparednessRefreshEvaluated"
    )
    opened = next(
        event for event in events
        if event["event"] == "PreparednessEpisodeOpened"
    )
    assert evaluated["case_id"] == response.json["case_id"]
    assert evaluated["payload"]["decision"]["forecasts_json"] == payload[
        "forecasts_json"
    ]
    assert evaluated["payload"]["decision"]["policy_json"] == payload[
        "policy_json"
    ]
    assert opened["payload"]["process_instance_key"] == "process-1"
    cleared = next(
        event for event in events
        if event["event"] == "PreparednessEpisodeCleared"
    )
    assert cleared["case_id"] == response.json["case_id"]
    assert cleared["payload"]["previous_alert_level"] == "INFORMATION"


def test_clear_and_duplicate_refreshes_are_logged(client) -> None:
    payload = {
        "status": "decision",
        "refresh_id": "refresh-none",
        "location_id": "copenhagen",
        "alert_level": "NONE",
        "dmi_warning_category": "NONE",
        "time_to_critical_hours": None,
        "forecast_value_cm": None,
        "critical_level_cm": 100.0,
        "category_time_to_critical_hours": None,
        "category_forecast_value_cm": None,
        "reason": "no_threshold_exceedance_within_forecast_horizon",
        "forecasts_json": "[]",
        "policy_json": "{}",
    }

    first = send_decision(client, payload)
    duplicate = send_decision(client, payload)

    assert first.status_code == 200
    assert duplicate.json["status"] == "duplicate"
    events = client.application.config["TEST_PREPAREDNESS_EVENTS"]
    assert events[0]["event"] == "PreparednessRefreshEvaluated"
    assert events[1]["event"] == "PreparednessRefreshDuplicate"
    assert events[0]["case_id"] == "preparedness-refresh-refresh-none"


def test_log_callback_failure_does_not_fail_preparedness_response(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    import requests

    def fail_post(*args, **kwargs):
        raise requests.ConnectionError("Siddhi is unavailable")

    monkeypatch.setattr(communication_app.requests, "post", fail_post)
    response = send_decision(
        client,
        {
            "status": "disabled",
            "refresh_id": "refresh-log-down",
            "location_id": "copenhagen",
            "forecasts_json": "[]",
            "policy_json": "",
        },
    )

    assert response.status_code == 200
    assert response.json["status"] == "disabled"


def test_preparedness_task_logs_bpmn_activity_and_outcome(client) -> None:
    result = asyncio.run(
        communication_app.perform_preparedness_task(
            "internalPreparedness",
            "Internal preparedness",
            "episode-1",
            "INTERNAL",
            "refresh-1",
            "copenhagen",
        )
    )

    assert result == {"internalPreparednessCompleted": True}
    event = client.application.config["TEST_PREPAREDNESS_EVENTS"][-1]
    assert event["event"] == "Internal preparedness"
    assert event["case_id"] == "episode-1"
    assert event["role"] == "camunda"
    assert event["payload"]["lifecycle"] == "complete"
    assert event["payload"]["location_id"] == "copenhagen"


def test_preparedness_task_failure_is_logged_then_reraised(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_print(*args, **kwargs):
        raise RuntimeError("simulated task failure")

    monkeypatch.setattr("builtins.print", fail_print)
    with pytest.raises(RuntimeError, match="simulated task failure"):
        asyncio.run(
            communication_app.perform_preparedness_task(
                "staffPreparedness",
                "Staff preparedness",
                "episode-1",
                "STATE",
                "refresh-1",
                "copenhagen",
            )
        )

    event = client.application.config["TEST_PREPAREDNESS_EVENTS"][-1]
    assert event["event"] == "Staff preparedness"
    assert event["payload"]["lifecycle"] == "failed"
    assert event["error"] == "simulated task failure"


def test_siddhi_routes_communication_callbacks_and_keeps_input_snapshots() -> None:
    siddhi_app = INTEGRATION_DIR.parent / "cep/apps/PreparednessDecisionApp.siddhi"
    source = siddhi_app.read_text(encoding="utf-8")

    assert 'receiver.url="http://0.0.0.0:7072/middleman"' in source
    assert "publisher.url='http://event_logs_service:5010/log'" in source
    assert "forecasts_json: forecastsJson" in source
    assert "policy_json: policyJson" in source
