"""Manual check without hitting DMI: parses the mock forecast and submits one
complete refresh to Siddhi. Usage (from sources/api_adapter):

    python scripts/mock_ingest.py                      # just print the forecasts
    python scripts/mock_ingest.py http://localhost:7077/forecast-refreshes
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dmi import DMIParser  # noqa: E402
from service import PreparednessDecisionForwarder  # noqa: E402

MOCK = ROOT / "tests" / "mock_data"


def main() -> None:
    parser = DMIParser()
    raw = json.loads((MOCK / "forecast_edr.json").read_text())
    issued = parser.parse_time(raw["domain"]["axes"]["t"]["values"][0])
    forecasts = [
        forecast.to_event()
        for forecast in parser.forecast(raw, "copenhagen", issued_at=issued)
    ]

    for forecast in forecasts:
        print(json.dumps(forecast))
    if len(sys.argv) > 1:
        forwarder = PreparednessDecisionForwarder(decision_sink_url=sys.argv[1])
        forwarder.send_forecast_refresh("copenhagen", forecasts)
        print(f"Submitted {len(forecasts)} forecasts to {sys.argv[1]}")
    else:
        print(f"{len(forecasts)} forecasts parsed")


if __name__ == "__main__":
    main()
