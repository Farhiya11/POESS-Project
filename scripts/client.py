import argparse
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_API_URL = "http://localhost:5000/events"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Send an order event to the POESS API adapter."
    )
    parser.add_argument("order_id", nargs="?", default="order-001")
    parser.add_argument("action", nargs="?", default="PlaceOrder")
    args = parser.parse_args()

    if not args.order_id.strip() or not args.action.strip():
        parser.error("order_id and action must not be empty")

    api_url = os.getenv("API_URL", DEFAULT_API_URL)
    body = json.dumps(
        {"order_id": args.order_id, "action": args.action}
    ).encode("utf-8")
    request = Request(
        api_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=10) as response:
            response_body = response.read().decode("utf-8")
            print(f"HTTP {response.status}")
            print(response_body)
            return 0
    except HTTPError as error:
        print(f"HTTP {error.code}", file=sys.stderr)
        print(error.read().decode("utf-8"), file=sys.stderr)
    except URLError as error:
        print(f"Could not reach the API adapter: {error.reason}", file=sys.stderr)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
