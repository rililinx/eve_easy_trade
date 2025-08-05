"""Price Loader microservice.

This service periodically queries the EVE Online ESI API for market
orders and stores the best buy/sell prices in Redis.  Data is cached for
one hour and refreshed every 15 minutes.  A manual refresh can also be
triggered via an HTTP endpoint.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import redis


ESI_BASE = "https://esi.evetech.net/latest"
USER_AGENT = "EveEasyTrade/0.1 (+https://github.com/your/repository)"

# Cache expiry and refresh interval
TTL_SECONDS = 60 * 60  # 1 hour
UPDATE_INTERVAL = 15 * 60  # 15 minutes

# Resolve paths to the shared static data directory.  When running inside
# a Docker container the ``shared`` directory is mounted in the same
# directory as this file.  When running from the repository it is a
# sibling of the ``price_loader`` package.
BASE_DIR = Path(__file__).resolve().parent
shared_dir = BASE_DIR / "shared"
if not shared_dir.exists():
    shared_dir = BASE_DIR.parent / "shared"

ITEMS_FILE = shared_dir / "static_data" / "items.json"
REGIONS_FILE = shared_dir / "static_data" / "regions.json"

# Load the item and region identifiers we care about
try:
    with ITEMS_FILE.open() as f:
        ITEMS: list[int] = [entry["id"] for entry in json.load(f)]
except FileNotFoundError:
    ITEMS = []

try:
    with REGIONS_FILE.open() as f:
        REGIONS: list[int] = [entry["id"] for entry in json.load(f)]
except FileNotFoundError:
    REGIONS = []


# Redis connection
redis_client = redis.Redis(
    host=os.environ.get("REDIS_HOST", "localhost"),
    port=int(os.environ.get("REDIS_PORT", 6379)),
    decode_responses=True,
)


def get_json(
    url: str, params: dict | None = None, *, return_headers: bool = False
):
    """Fetch JSON data from ``url`` with optional query parameters."""

    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req) as resp:  # nosec B310 - trusted source
        data = json.loads(resp.read().decode())
        if return_headers:
            return data, resp.headers
        return data


def fetch_best_prices(region_id: int, type_id: int) -> dict:
    """Retrieve the best five buy and sell orders for a given item."""

    result: dict[str, list[dict]] = {}
    for order_type in ("buy", "sell"):
        page = 1
        orders: list[dict] = []
        while True:
            try:
                data, headers = get_json(
                    f"{ESI_BASE}/markets/{region_id}/orders/",
                    params={
                        "order_type": order_type,
                        "type_id": type_id,
                        "page": page,
                    },
                    return_headers=True,
                )
            except Exception as exc:  # pragma: no cover - network errors
                print(
                    f"Error fetching orders for region {region_id} "
                    f"item {type_id} ({order_type}): {exc}"
                )
                break

            orders.extend(data)
            page_count = int(headers.get("X-Pages", 1))
            if page >= page_count:
                break
            page += 1

        if order_type == "buy":
            orders.sort(key=lambda o: o["price"], reverse=True)
        else:
            orders.sort(key=lambda o: o["price"])

        simplified = [
            {
                "price": o["price"],
                "volume_remain": o["volume_remain"],
                "location_id": o["location_id"],
            }
            for o in orders[:5]
        ]
        result[order_type] = simplified

    return result


def update_prices() -> None:
    """Fetch prices for all items/regions and store them in Redis."""

    for region_id in REGIONS:
        for type_id in ITEMS:
            prices = fetch_best_prices(region_id, type_id)
            key = f"prices:{region_id}:{type_id}"
            try:
                redis_client.setex(key, TTL_SECONDS, json.dumps(prices))
            except Exception as exc:  # pragma: no cover - redis errors
                print(
                    f"Error storing prices for region {region_id} "
                    f"item {type_id}: {exc}"
                )


def schedule_updates() -> None:
    """Start a background thread that refreshes data periodically."""

    def loop():
        while True:
            print("Updating prices...")
            update_prices()
            time.sleep(UPDATE_INTERVAL)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()


class Handler(BaseHTTPRequestHandler):
    """HTTP API exposing the service and a manual refresh endpoint."""

    def do_GET(self):  # noqa: N802 - required method name
        if self.path == "/refresh":
            threading.Thread(target=update_prices, daemon=True).start()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Refresh started")
            return

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Price Loader Service")


def run() -> None:
    schedule_updates()
    server = HTTPServer(("0.0.0.0", 8000), Handler)
    print("Price Loader service running on port 8000")
    server.serve_forever()


if __name__ == "__main__":
    run()

