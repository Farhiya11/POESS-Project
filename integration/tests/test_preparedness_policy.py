import json

import pytest

from integration.preparedness_policy import (
    AlertLevel,
    PreparednessEpisodeStore,
    PreparednessPolicyConfigurationError,
    PreparednessWarningPolicy,
)


def configured_policy(**overrides) -> PreparednessWarningPolicy:
    configuration = {
        "locations": {"copenhagen": {"critical_sea_level_cm": 100}},
    }
    configuration.update(overrides)
    return PreparednessWarningPolicy.from_environment(
        {"PREPAREDNESS_WARNING_POLICY_JSON": json.dumps(configuration)}
    )


def test_policy_is_disabled_without_configuration() -> None:
    policy = PreparednessWarningPolicy.from_environment({})

    assert not policy.enabled
    decision = policy.evaluate_refresh("copenhagen", [])
    assert decision.alert_level is AlertLevel.NONE
    assert decision.reason == "policy_disabled"


def test_policy_requires_location_thresholds_and_valid_cutoffs() -> None:
    with pytest.raises(PreparednessPolicyConfigurationError, match="valid JSON"):
        PreparednessWarningPolicy.from_environment(
            {"PREPAREDNESS_WARNING_POLICY_JSON": "not-json"}
        )
    with pytest.raises(
        PreparednessPolicyConfigurationError, match="at least one location"
    ):
        PreparednessWarningPolicy.from_environment(
            {"PREPAREDNESS_WARNING_POLICY_JSON": '{"locations": {}}'}
        )
    with pytest.raises(
        PreparednessPolicyConfigurationError, match="Lead-time cutoffs"
    ):
        configured_policy(information_lead_hours=2, state_lead_hours=4)


def test_policy_selects_highest_level_within_horizon() -> None:
    policy = configured_policy()

    decision = policy.evaluate_refresh(
        "copenhagen",
        [
            {"sea_level_cm": 105, "lead_time_hours": 3},
            {"sea_level_cm": 130, "lead_time_hours": 37},
            {"sea_level_cm": 115, "lead_time_hours": 12},
        ],
    )

    assert decision.alert_level is AlertLevel.STATE
    assert decision.time_to_critical_hours == 3
    assert decision.forecast_value_cm == 105
    assert decision.critical_level_cm == 100


@pytest.mark.parametrize(
    ("lead_time", "expected_level"),
    [
        (36, AlertLevel.INTERNAL),
        (6, AlertLevel.INFORMATION),
        (4, AlertLevel.STATE),
        (2, AlertLevel.OPERATIONAL),
        (0, AlertLevel.OPERATIONAL),
        (36.01, AlertLevel.NONE),
    ],
)
def test_policy_applies_configurable_preparedness_cutoffs(lead_time, expected_level):
    decision = configured_policy().evaluate_refresh(
        "copenhagen",
        [{"sea_level_cm": 100, "lead_time_hours": lead_time}],
    )

    assert decision.alert_level is expected_level


def test_policy_requires_threshold_for_each_forecast_location() -> None:
    with pytest.raises(
        PreparednessPolicyConfigurationError, match="No critical sea-level"
    ):
        configured_policy().evaluate_refresh("aarhus", [])


def test_policy_accepts_negative_sea_level_thresholds() -> None:
    policy = configured_policy(
        locations={"west_coast": {"critical_sea_level_cm": -20}}
    )

    decision = policy.evaluate_refresh(
        "west_coast",
        [{"sea_level_cm": -19, "lead_time_hours": 7}],
    )

    assert decision.alert_level is AlertLevel.INTERNAL
    assert decision.critical_level_cm == -20


def test_invalid_forecast_values_are_rejected() -> None:
    policy = configured_policy()

    with pytest.raises(ValueError, match="numeric sea_level_cm"):
        policy.evaluate_refresh("copenhagen", [{"lead_time_hours": 1}])
    with pytest.raises(ValueError, match="finite"):
        policy.evaluate_refresh(
            "copenhagen",
            [{"sea_level_cm": 100, "lead_time_hours": float("inf")}],
        )


def test_episode_id_is_reused_persisted_and_recreated_after_clear(tmp_path) -> None:
    state_path = tmp_path / "alerts.json"
    store = PreparednessEpisodeStore(state_path)

    first_case_id = store.update_episode("copenhagen", qualifies=True)
    assert first_case_id is not None
    assert store.update_episode("copenhagen", qualifies=True) == first_case_id
    assert PreparednessEpisodeStore(state_path).case_id_for("copenhagen") == first_case_id

    assert store.update_episode("copenhagen", qualifies=False) is None
    assert store.case_id_for("copenhagen") is None
    next_case_id = store.update_episode("copenhagen", qualifies=True)
    assert next_case_id is not None
    assert next_case_id != first_case_id


def test_process_instance_and_level_are_persisted_until_episode_clears(tmp_path) -> None:
    state_path = tmp_path / "alerts.json"
    store = PreparednessEpisodeStore(state_path)
    case_id = store.update_episode("copenhagen", qualifies=True)
    assert case_id is not None

    store.record_process_instance(case_id, "12345")
    store.record_alert_level(case_id, AlertLevel.INFORMATION)
    reloaded = PreparednessEpisodeStore(state_path)
    assert reloaded.process_instance_for(case_id) == "12345"
    assert reloaded.alert_level_for(case_id) is AlertLevel.INFORMATION

    reloaded.update_episode("copenhagen", qualifies=False)
    cleared = PreparednessEpisodeStore(state_path)
    assert cleared.process_instance_for(case_id) is None
    assert cleared.alert_level_for(case_id) is None


def test_episode_state_fails_closed_when_file_or_entries_are_invalid(tmp_path) -> None:
    state_path = tmp_path / "alerts.json"
    state_path.write_text(json.dumps({"active_episodes": {}}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="Invalid alert episode state"):
        PreparednessEpisodeStore(state_path)

    state_path.write_text(
        json.dumps({"version": 3, "active_episodes": {"copenhagen": []}}),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="Invalid active episode entry"):
        PreparednessEpisodeStore(state_path)
