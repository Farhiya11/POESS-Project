import argparse
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_URL = os.getenv("API_URL", "http://localhost:5000/events")


def post(url: str, body: dict) -> tuple[int, object]:
    req = Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=5) as response:
        return response.status, json.loads(response.read())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Submit or execute a DCR event via the API adapter."
    )
    parser.add_argument("case_id", help="unique ID for this claim")
    parser.add_argument("event_id", nargs="?", help="DCR event to execute, e.g. A2")
    parser.add_argument("--graph", help="exact DCR graph title to start")
    args = parser.parse_args()
    case_id = args.case_id.strip()

    if not case_id:
        parser.error("case_id must not be empty")

    if args.event_id:
        if args.graph:
            parser.error("--graph can only be used when starting a case")
        event_id = args.event_id.strip()
        if not event_id:
            parser.error("event_id must not be empty")
        body = {
            "order_id": case_id,
            "action": "ExecuteDcrEvent",
            "event_id": event_id,
        }
    else:
        body = {"order_id": case_id, "action": "StartDcrCase"}
        if args.graph:
            body["graph_title"] = args.graph.strip()
            if not body["graph_title"]:
                parser.error("graph title must not be empty")

    try:
        status, result = post(API_URL, body)
        print(f"HTTP {status}: {json.dumps(result)}")
        return 0
    except HTTPError as error:
        print(f"HTTP {error.code}: {error.read().decode('utf-8', errors='replace')}", file=sys.stderr)
    except URLError as error:
        print(f"Could not reach the API adapter: {error.reason}", file=sys.stderr)
    except ValueError as error:
        print(f"Invalid JSON in response: {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())