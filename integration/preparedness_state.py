import json
import os
import tempfile
import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from uuid import uuid4


class AlertLevel(str, Enum):
    NONE = "NONE"
    INTERNAL = "INTERNAL"
    INFORMATION = "INFORMATION"
    STATE = "STATE"
    OPERATIONAL = "OPERATIONAL"


PREPAREDNESS_LEVEL_RANK = {
    AlertLevel.NONE: 0,
    AlertLevel.INTERNAL: 1,
    AlertLevel.INFORMATION: 2,
    AlertLevel.STATE: 3,
    AlertLevel.OPERATIONAL: 4,
}

DMI_WARNING_CATEGORIES = {
    "NONE",
    "CATEGORY_1",
    "CATEGORY_2",
    "CATEGORY_3",
}


@dataclass(frozen=True)
class PreparednessWarningDecision:
    location_id: str
    alert_level: AlertLevel
    time_to_critical_hours: float | None
    forecast_value_cm: float | None
    critical_level_cm: float | None
    dmi_warning_category: str
    category_time_to_critical_hours: float | None
    category_forecast_value_cm: float | None
    reason: str


class PreparednessEpisodeStore:
    """Persists one stable case ID, process instance, and decision state per location."""

    _SCHEMA_VERSION = 5
    _VALID_LEVELS = {level.value for level in AlertLevel}

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(
            path
            if path is not None
            else os.getenv(
                "PREPAREDNESS_WARNING_STATE_FILE",
                "/data/preparedness_warning_episodes.json",
            )
        )
        self._lock = threading.Lock()
        (
            self._active_episodes,
            self._process_instances,
            self._alert_levels,
            self._dmi_warning_categories,
            self._processed_refreshes,
        ) = self._load()

    def _load(
        self,
    ) -> tuple[
        dict[str, str],
        dict[str, str],
        dict[str, str],
        dict[str, str],
        dict[str, list[str]],
    ]:
        if not self.path.exists():
            return {}, {}, {}, {}, {}
        try:
            with self.path.open(encoding="utf-8") as state_file:
                document = json.load(state_file)
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError(f"Unable to read alert episode state at {self.path}") from error
        if (
            not isinstance(document, dict)
            or document.get("version") not in (1, 2, 3, 4, self._SCHEMA_VERSION)
            or not isinstance(document.get("active_episodes"), dict)
        ):
            raise RuntimeError(f"Invalid alert episode state at {self.path}")
        active = document["active_episodes"]
        if not all(
            isinstance(location, str)
            and location
            and isinstance(case_id, str)
            and case_id
            for location, case_id in active.items()
        ):
            raise RuntimeError(f"Invalid active episode entry in {self.path}")
        active_case_ids = set(active.values())
        process_instances = document.get("process_instances", {})
        if not isinstance(process_instances, dict) or not all(
            isinstance(case_id, str)
            and case_id in active_case_ids
            and isinstance(process_instance_key, str)
            and process_instance_key
            for case_id, process_instance_key in process_instances.items()
        ):
            raise RuntimeError(f"Invalid process instance entry in {self.path}")
        alert_levels = document.get("alert_levels", {})
        if not isinstance(alert_levels, dict) or not all(
            isinstance(case_id, str)
            and case_id in active_case_ids
            and isinstance(level, str)
            and level in self._VALID_LEVELS
            for case_id, level in alert_levels.items()
        ):
            raise RuntimeError(f"Invalid alert level entry in {self.path}")
        dmi_warning_categories = document.get("dmi_warning_categories", {})
        if not isinstance(dmi_warning_categories, dict) or not all(
            isinstance(case_id, str)
            and case_id in active_case_ids
            and isinstance(category, str)
            and category in DMI_WARNING_CATEGORIES
            for case_id, category in dmi_warning_categories.items()
        ):
            raise RuntimeError(f"Invalid DMI warning category entry in {self.path}")
        processed_refreshes = document.get("processed_refreshes", {})
        if not isinstance(processed_refreshes, dict):
            raise RuntimeError(f"Invalid processed refresh entry in {self.path}")
        normalized_refreshes: dict[str, list[str]] = {}
        for location, refresh_ids in processed_refreshes.items():
            if not isinstance(location, str) or not location:
                raise RuntimeError(
                    f"Invalid processed refresh entry in {self.path}"
                )
            if isinstance(refresh_ids, str):
                refresh_ids = [refresh_ids]
            if (
                not isinstance(refresh_ids, list)
                or not all(
                    isinstance(refresh_id, str) and refresh_id
                    for refresh_id in refresh_ids
                )
            ):
                raise RuntimeError(
                    f"Invalid processed refresh entry in {self.path}"
                )
            normalized_refreshes[location] = refresh_ids[-256:]
        return (
            active,
            process_instances,
            alert_levels,
            dmi_warning_categories,
            normalized_refreshes,
        )

    def case_id_for(self, location_id: str) -> str | None:
        location = location_id.strip()
        if not location:
            raise ValueError("location_id is required")
        with self._lock:
            return self._active_episodes.get(location)

    def alert_level_for(self, case_id: str) -> AlertLevel | None:
        with self._lock:
            level = self._alert_levels.get(case_id)
            return AlertLevel(level) if level is not None else None

    def dmi_warning_category_for(self, case_id: str) -> str | None:
        with self._lock:
            return self._dmi_warning_categories.get(case_id)

    def has_processed_refresh(self, location_id: str, refresh_id: str) -> bool:
        with self._lock:
            return refresh_id in self._processed_refreshes.get(location_id.strip(), [])

    def record_processed_refresh(self, location_id: str, refresh_id: str) -> None:
        location = location_id.strip()
        if not location or not refresh_id:
            raise ValueError("location_id and refresh_id are required")
        with self._lock:
            processed_refreshes = dict(self._processed_refreshes)
            location_refreshes = list(processed_refreshes.get(location, []))
            if refresh_id in location_refreshes:
                return
            location_refreshes.append(refresh_id)
            processed_refreshes[location] = location_refreshes[-256:]
            self._persist(
                self._active_episodes,
                self._process_instances,
                self._alert_levels,
                self._dmi_warning_categories,
                processed_refreshes,
            )
            self._processed_refreshes = processed_refreshes

    def update_episode(self, location_id: str, qualifies: bool) -> str | None:
        """Reuse the active case ID, create an episode, or clear it on a clean refresh."""
        location = location_id.strip()
        if not location:
            raise ValueError("location_id is required")

        with self._lock:
            current_case_id = self._active_episodes.get(location)
            if qualifies and current_case_id:
                return current_case_id
            if not qualifies and current_case_id is None:
                return None

            updated = dict(self._active_episodes)
            case_id = f"preparedness-warning-{uuid4().hex}" if qualifies else None
            process_instances = dict(self._process_instances)
            alert_levels = dict(self._alert_levels)
            dmi_warning_categories = dict(self._dmi_warning_categories)
            if case_id is None:
                del updated[location]
                process_instances.pop(current_case_id, None)
                alert_levels.pop(current_case_id, None)
                dmi_warning_categories.pop(current_case_id, None)
            else:
                updated[location] = case_id
            self._persist(
                updated,
                process_instances,
                alert_levels,
                dmi_warning_categories,
                self._processed_refreshes,
            )
            self._active_episodes = updated
            self._process_instances = process_instances
            self._alert_levels = alert_levels
            self._dmi_warning_categories = dmi_warning_categories
            return case_id

    def process_instance_for(self, case_id: str) -> str | None:
        with self._lock:
            return self._process_instances.get(case_id)

    def record_process_instance(self, case_id: str, process_instance_key: str) -> None:
        if not process_instance_key:
            raise ValueError("process_instance_key is required")
        with self._lock:
            if case_id not in self._active_episodes.values():
                raise ValueError("case_id is not an active alert episode")
            if case_id in self._process_instances:
                return
            process_instances = dict(self._process_instances)
            process_instances[case_id] = process_instance_key
            self._persist(
                self._active_episodes,
                process_instances,
                self._alert_levels,
                self._dmi_warning_categories,
                self._processed_refreshes,
            )
            self._process_instances = process_instances

    def record_alert_level(self, case_id: str, level: AlertLevel) -> None:
        with self._lock:
            if case_id not in self._active_episodes.values():
                raise ValueError("case_id is not an active alert episode")
            alert_levels = dict(self._alert_levels)
            alert_levels[case_id] = level.value
            self._persist(
                self._active_episodes,
                self._process_instances,
                alert_levels,
                self._dmi_warning_categories,
                self._processed_refreshes,
            )
            self._alert_levels = alert_levels

    def record_dmi_warning_category(self, case_id: str, category: str) -> None:
        if category not in DMI_WARNING_CATEGORIES or category == "NONE":
            raise ValueError("an active episode requires a DMI warning category")
        with self._lock:
            if case_id not in self._active_episodes.values():
                raise ValueError("case_id is not an active alert episode")
            dmi_warning_categories = dict(self._dmi_warning_categories)
            dmi_warning_categories[case_id] = category
            self._persist(
                self._active_episodes,
                self._process_instances,
                self._alert_levels,
                dmi_warning_categories,
                self._processed_refreshes,
            )
            self._dmi_warning_categories = dmi_warning_categories

    def _persist(
        self,
        active_episodes: dict[str, str],
        process_instances: dict[str, str],
        alert_levels: dict[str, str],
        dmi_warning_categories: dict[str, str],
        processed_refreshes: dict[str, list[str]],
    ) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as state_file:
                temporary_path = Path(state_file.name)
                json.dump(
                    {
                        "version": self._SCHEMA_VERSION,
                        "active_episodes": active_episodes,
                        "process_instances": process_instances,
                        "alert_levels": alert_levels,
                        "dmi_warning_categories": dmi_warning_categories,
                        "processed_refreshes": processed_refreshes,
                    },
                    state_file,
                    sort_keys=True,
                )
                state_file.flush()
                os.fsync(state_file.fileno())
            os.replace(temporary_path, self.path)
        except OSError as error:
            raise RuntimeError(f"Unable to persist alert episode state at {self.path}") from error
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()
