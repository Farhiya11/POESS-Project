import importlib.util
import json
import sys
from pathlib import Path

import pytest

from integration.preparedness_state import PreparednessEpisodeStore

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
    return communication_app.app.test_client()


def send_decision(client, payload: dict):
    return client.post(
        "/preparedness_decision",
        json={"decision_json": json.dumps(payload)},
    )


def test_siddhi_disabled_policy_does_not_change_episode_state(client) -> None:
    response = send_decision(
        client,
        {
            "status": "disabled",
            "refresh_id": "refresh-1",
            "location_id": "copenhagen",
        },
    )

    assert response.status_code == 200
    assert response.json["status"] == "disabled"
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
