import json

import pytest

from integration.preparedness_episode_store import PreparednessEpisodeStore
from integration.preparedness_state import AlertLevel


def test_episode_id_is_reused_persisted_and_recreated_after_clear(tmp_path) -> None:
    state_path = tmp_path / "episodes.json"
    store = PreparednessEpisodeStore(state_path)

    first_case_id = store.update_episode("copenhagen", qualifies=True)
    assert first_case_id is not None
    assert store.update_episode("copenhagen", qualifies=True) == first_case_id
    assert (
        PreparednessEpisodeStore(state_path).case_id_for("copenhagen")
        == first_case_id
    )

    assert store.update_episode("copenhagen", qualifies=False) is None
    assert store.case_id_for("copenhagen") is None
    next_case_id = store.update_episode("copenhagen", qualifies=True)
    assert next_case_id is not None
    assert next_case_id != first_case_id


def test_process_instance_and_level_are_persisted_until_episode_clears(tmp_path) -> None:
    state_path = tmp_path / "episodes.json"
    store = PreparednessEpisodeStore(state_path)
    case_id = store.update_episode("copenhagen", qualifies=True)
    assert case_id is not None

    store.record_process_instance(case_id, "12345")
    store.record_alert_level(case_id, AlertLevel.INFORMATION)
    store.record_dmi_warning_category(case_id, "CATEGORY_2")
    store.record_processed_refresh("copenhagen", "refresh-1")

    reloaded = PreparednessEpisodeStore(state_path)
    assert reloaded.process_instance_for(case_id) == "12345"
    assert reloaded.alert_level_for(case_id) is AlertLevel.INFORMATION
    assert reloaded.dmi_warning_category_for(case_id) == "CATEGORY_2"
    assert reloaded.has_processed_refresh("copenhagen", "refresh-1")

    reloaded.update_episode("copenhagen", qualifies=False)
    cleared = PreparednessEpisodeStore(state_path)
    assert cleared.process_instance_for(case_id) is None
    assert cleared.alert_level_for(case_id) is None
    assert cleared.dmi_warning_category_for(case_id) is None
    assert cleared.has_processed_refresh("copenhagen", "refresh-1")


def test_legacy_episode_state_loads_without_processed_refreshes(tmp_path) -> None:
    state_path = tmp_path / "episodes.json"
    state_path.write_text(
        json.dumps(
            {
                "version": 3,
                "active_episodes": {"copenhagen": "case-1"},
                "process_instances": {"case-1": "12345"},
                "alert_levels": {"case-1": "INFORMATION"},
            }
        ),
        encoding="utf-8",
    )

    store = PreparednessEpisodeStore(state_path)

    assert store.case_id_for("copenhagen") == "case-1"
    assert not store.has_processed_refresh("copenhagen", "refresh-1")


def test_episode_state_fails_closed_when_file_or_entries_are_invalid(tmp_path) -> None:
    state_path = tmp_path / "episodes.json"
    state_path.write_text(json.dumps({"active_episodes": {}}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="Invalid alert episode state"):
        PreparednessEpisodeStore(state_path)

    state_path.write_text(
        json.dumps({"version": 4, "active_episodes": {}, "processed_refreshes": []}),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="Invalid processed refresh"):
        PreparednessEpisodeStore(state_path)
