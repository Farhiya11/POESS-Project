import json
import math
import os
import tempfile
import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping
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


@dataclass(frozen=True)
class PreparednessWarningDecision:
    location_id: str
    alert_level: AlertLevel
    time_to_critical_hours: float | None
    forecast_value_cm: float | None
    critical_level_cm: float | None
    reason: str


class PreparednessPolicyConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class PreparednessWarningPolicy:
    forecast_horizon_hours: float | None
    information_lead_hours: float
    state_lead_hours: float
    operational_lead_hours: float
    thresholds_by_location: Mapping[str, float]

    @property
    def enabled(self) -> bool:
        return bool(self.thresholds_by_location)

    @classmethod
    def disabled(cls) -> "PreparednessWarningPolicy":
        return cls(None, 6, 4, 2, {})

    @classmethod
    def from_environment(
        cls, environ: Mapping[str, str] | None = None
    ) -> "PreparednessWarningPolicy":
        settings = os.environ if environ is None else environ
        raw_configuration = settings.get(
            "PREPAREDNESS_WARNING_POLICY_JSON", ""
        ).strip()
        if not raw_configuration:
            return cls.disabled()
        try:
            configuration = json.loads(raw_configuration)
        except json.JSONDecodeError as error:
            raise PreparednessPolicyConfigurationError(
                "PREPAREDNESS_WARNING_POLICY_JSON must contain valid JSON"
            ) from error
        if not isinstance(configuration, dict):
            raise PreparednessPolicyConfigurationError(
                "Policy configuration must be a JSON object"
            )

        locations = configuration.get("locations")
        if not isinstance(locations, dict) or not locations:
            raise PreparednessPolicyConfigurationError(
                "Policy configuration requires thresholds for at least one location"
            )
        thresholds: dict[str, float] = {}
        for location_id, location_configuration in locations.items():
            if not isinstance(location_id, str) or not location_id.strip():
                raise PreparednessPolicyConfigurationError(
                    "Location threshold keys must be non-empty strings"
                )
            if not isinstance(location_configuration, dict):
                raise PreparednessPolicyConfigurationError(
                    f"Policy for location {location_id} must be an object"
                )
            threshold = cls._finite_number(
                location_configuration.get("critical_sea_level_cm"),
                f"critical_sea_level_cm for location {location_id}",
                allow_negative=True,
            )
            normalized_location_id = location_id.strip()
            if normalized_location_id in thresholds:
                raise PreparednessPolicyConfigurationError(
                    f"Duplicate location threshold for {normalized_location_id}"
                )
            thresholds[normalized_location_id] = threshold

        horizon = cls._finite_number(
            configuration.get("forecast_horizon_hours", 36),
            "forecast_horizon_hours",
        )
        information = cls._finite_number(
            configuration.get("information_lead_hours", 6),
            "information_lead_hours",
        )
        state = cls._finite_number(
            configuration.get("state_lead_hours", 4),
            "state_lead_hours",
        )
        operational = cls._finite_number(
            configuration.get("operational_lead_hours", 2),
            "operational_lead_hours",
        )
        if not 0 <= operational <= state <= information <= horizon:
            raise PreparednessPolicyConfigurationError(
                "Lead-time cutoffs must satisfy "
                "0 <= operational <= state <= information <= forecast horizon"
            )
        return cls(horizon, information, state, operational, thresholds)

    @staticmethod
    def _finite_number(
        value: Any, name: str, *, allow_negative: bool = False
    ) -> float:
        if isinstance(value, bool):
            raise PreparednessPolicyConfigurationError(f"{name} must be numeric")
        try:
            number = float(value)
        except (TypeError, ValueError) as error:
            raise PreparednessPolicyConfigurationError(
                f"{name} must be numeric"
            ) from error
        if not math.isfinite(number):
            raise PreparednessPolicyConfigurationError(f"{name} must be finite")
        if number < 0 and not allow_negative:
            raise PreparednessPolicyConfigurationError(
                f"{name} must be zero or greater"
            )
        return number

    def evaluate_refresh(
        self, location_id: str, forecasts: Iterable[Mapping[str, Any]]
    ) -> PreparednessWarningDecision:
        if not self.enabled or self.forecast_horizon_hours is None:
            return PreparednessWarningDecision(
                location_id,
                AlertLevel.NONE,
                None,
                None,
                None,
                "policy_disabled",
            )
        threshold = self.thresholds_by_location.get(location_id)
        if threshold is None:
            raise PreparednessPolicyConfigurationError(
                f"No critical sea-level threshold is configured for location {location_id}"
            )

        candidates: list[tuple[AlertLevel, float, float]] = []
        for forecast in forecasts:
            try:
                if isinstance(forecast["sea_level_cm"], bool) or isinstance(
                    forecast["lead_time_hours"], bool
                ):
                    raise ValueError
                sea_level_cm = float(forecast["sea_level_cm"])
                lead_time_hours = float(forecast["lead_time_hours"])
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(
                    "Forecasts require numeric sea_level_cm and lead_time_hours"
                ) from error
            if not math.isfinite(sea_level_cm) or not math.isfinite(lead_time_hours):
                raise ValueError("Forecast values must be finite numbers")
            if not 0 <= lead_time_hours <= self.forecast_horizon_hours:
                continue
            if sea_level_cm < threshold:
                continue

            if lead_time_hours <= self.operational_lead_hours:
                level = AlertLevel.OPERATIONAL
            elif lead_time_hours <= self.state_lead_hours:
                level = AlertLevel.STATE
            elif lead_time_hours <= self.information_lead_hours:
                level = AlertLevel.INFORMATION
            else:
                level = AlertLevel.INTERNAL
            candidates.append((level, lead_time_hours, sea_level_cm))

        if not candidates:
            return PreparednessWarningDecision(
                location_id,
                AlertLevel.NONE,
                None,
                None,
                threshold,
                "no_threshold_exceedance_within_forecast_horizon",
            )

        level, lead_time_hours, sea_level_cm = max(
            candidates,
            key=lambda candidate: (
                PREPAREDNESS_LEVEL_RANK[candidate[0]],
                -candidate[1],
                candidate[2],
            ),
        )
        return PreparednessWarningDecision(
            location_id,
            level,
            lead_time_hours,
            sea_level_cm,
            threshold,
            f"threshold_exceeded_within_{level.value.lower()}_window",
        )


class PreparednessEpisodeStore:
    """Persists one stable case ID, process instance, and level per location."""

    _SCHEMA_VERSION = 3
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
        ) = self._load()

    def _load(self) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
        if not self.path.exists():
            return {}, {}, {}
        try:
            with self.path.open(encoding="utf-8") as state_file:
                document = json.load(state_file)
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError(f"Unable to read alert episode state at {self.path}") from error
        if (
            not isinstance(document, dict)
            or document.get("version") not in (1, 2, self._SCHEMA_VERSION)
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
        return active, process_instances, alert_levels

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
            if case_id is None:
                del updated[location]
                process_instances.pop(current_case_id, None)
                alert_levels.pop(current_case_id, None)
            else:
                updated[location] = case_id
            self._persist(updated, process_instances, alert_levels)
            self._active_episodes = updated
            self._process_instances = process_instances
            self._alert_levels = alert_levels
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
            )
            self._alert_levels = alert_levels

    def _persist(
        self,
        active_episodes: dict[str, str],
        process_instances: dict[str, str],
        alert_levels: dict[str, str],
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
