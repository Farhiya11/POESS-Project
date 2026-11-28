"""Fixed values used across the adapter. DMI is a public API so nothing here
depends on the machine it runs on."""

import json
import os

DMI_BASE_URL = "https://opendataapi.dmi.dk"
DMI_OBSERVATIONS_PATH = "/v2/oceanObs/collections/observation/items"
DMI_FORECAST_PATH = "/v1/forecastedr/collections/{collection}/position"
DMI_TIMEOUT_SECONDS = 90

# oceanObs: one tide gauge, the one the storm surge declaration looks at
STATION_ID = "30336"  # Copenhagen harbour
OBSERVATION_PARAMETER = "sealev_dvr"
OBSERVATION_HOURS_BACK = 3

# forecastedr: DKSS storm surge model, a point just off Copenhagen
# (the harbour cell itself is masked as land in the model grid)
FORECAST_COLLECTION = "dkss_nsbs"
FORECAST_PARAMETER = "sea-mean-deviation"
FORECAST_LOCATION_ID = "copenhagen"
FORECAST_LON = 12.70
FORECAST_LAT = 55.70

PREPAREDNESS_DECISION_SINK_URL = os.getenv(
    "PREPAREDNESS_DECISION_SINK_URL",
    "http://siddhi:7077/forecast-refreshes",
)
WATER_LEVEL_OBSERVATION_SINK_URL = os.getenv(
    "WATER_LEVEL_OBSERVATION_SINK_URL",
    "http://siddhi:7076/water-level-observations",
)
DEFAULT_PREPAREDNESS_WARNING_POLICY = {
    "forecast_horizon_hours": 36,
    "information_lead_hours": 6,
    "state_lead_hours": 4,
    "operational_lead_hours": 2,
    "regions": {
        "inner_danish_waters": {
            "category_1_min_cm": 125,
            "category_2_min_cm": 140,
            "category_3_above_cm": 160,
        },
        "west_coast_jutland": {
            "category_1_min_cm": 190,
            "category_2_min_cm": 250,
            "category_3_above_cm": 300,
        },
        "wadden_sea": {
            "category_1_min_cm": 240,
            "category_2_min_cm": 300,
            "category_3_above_cm": 400,
        },
    },
    "locations": {
        FORECAST_LOCATION_ID: {"region": "inner_danish_waters"},
    },
}
PREPAREDNESS_WARNING_POLICY_JSON = os.getenv(
    "PREPAREDNESS_WARNING_POLICY_JSON",
    json.dumps(DEFAULT_PREPAREDNESS_WARNING_POLICY),
)
PREPAREDNESS_DECISION_TIMEOUT_SECONDS = 10
OBSERVATION_SINK_TIMEOUT_SECONDS = 10

POLL_INTERVAL_SECONDS = 600  # DMI updates observations every 10 minutes
