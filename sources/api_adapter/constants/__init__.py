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

# where events go. this one does change per setup (docker vs local) so it
# can be overridden; the path still has to be agreed with the siddhi side
import os  # noqa: E402

EVENT_SINK_URL = os.getenv("EVENT_SINK_URL", "http://siddhi:8006/dmi")
EVENT_SINK_TIMEOUT_SECONDS = 10
