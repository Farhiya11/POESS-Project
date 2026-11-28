from dataclasses import dataclass
from enum import Enum


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
