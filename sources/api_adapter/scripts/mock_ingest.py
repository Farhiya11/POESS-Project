"""Manual check without hitting DMI: parses the mock responses and pushes them
to a sink. Usage (from sources/api_adapter):

    python scripts/mock_ingest.py                      # just print the events
    python scripts/mock_ingest.py http://localhost:8006/dmi   # also send them
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dmi import DMIParser  # noqa: E402
from service import EventForwarder  # noqa: E402

MOCK = ROOT / "tests" / "mock_data"


def main() -> None:
    parser = DMIParser()
    obs = parser.observations(json.loads((MOCK / "ocean_obs.json").read_text()))
    raw = json.loads((MOCK / "forecast_edr.json").read_text())
    issued = parser.parse_time(raw["domain"]["axes"]["t"]["values"][0])
    fc = parser.forecast(raw, "copenhagen", issued_at=issued)
    events = [e.to_event() for e in [*obs, *fc]]

    forwarder = EventForwarder(sys.argv[1]) if len(sys.argv) > 1 else None
    for event in events:
        print(json.dumps(event))
        if forwarder:
            forwarder.send(event)
    print(f"{len(events)} events{' sent' if forwarder else ''}")


if __name__ == "__main__":
    main()
