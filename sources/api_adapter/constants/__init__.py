"""Fixed values used across the adapter. DMI is a public API so nothing here
depends on the machine it runs on."""

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

# Where events go; override this for local or non-default Docker setups.
import os  # noqa: E402

EVENT_SINK_URL = os.getenv("EVENT_SINK_URL", "http://siddhi:7076/events")
PREPAREDNESS_WARNING_POLICY_URL = os.getenv(
    "PREPAREDNESS_WARNING_POLICY_URL",
    "http://communication:5001/forecast_refresh",
)
EVENT_SINK_TIMEOUT_SECONDS = 10

POLL_INTERVAL_SECONDS = 600  # DMI updates obs every 10 min
