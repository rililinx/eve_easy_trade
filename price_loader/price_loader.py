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

# Load the item and region identifiers we care about along with their names
try:
    with ITEMS_FILE.open() as f:
        _items = json.load(f)
        ITEMS: list[int] = [entry["id"] for entry in _items]
        ITEM_NAMES: dict[int, str] = {entry["id"]: entry["name"] for entry in _items}
except FileNotFoundError:
    ITEMS = []
    ITEM_NAMES = {}

try:
    with REGIONS_FILE.open() as f:
        _regions = json.load(f)
        REGIONS: list[int] = [entry["id"] for entry in _regions]
        REGION_NAMES: dict[int, str] = {entry["id"]: entry["name"] for entry in _regions}
except FileNotFoundError:
    REGIONS = []
    REGION_NAMES = {}


# Redis connection
redis_client = redis.Redis(
    host=os.environ.get("REDIS_HOST", "localhost"),
    port=int(os.environ.get("REDIS_PORT", 6379)),
    decode_responses=True,
)


def get_json(url: str, params: dict | None = None):
    """Fetch JSON data from ``url`` and return it."""

    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req) as resp:  # nosec B310 - trusted source
        return json.loads(resp.read().decode())


def fetch_best_prices(region_id: int, type_id: int) -> dict:
    """Retrieve the best five buy and sell orders for a given item."""

    try:
        data = get_json(
            f"{ESI_BASE}/markets/{region_id}/orders/",
            params={"type_id": type_id},
        )
    except Exception as exc:  # pragma: no cover - network errors
        print(
            f"Error fetching orders for region {region_id} "
            f"item {type_id}: {exc}"
        )
        return {"buy": [], "sell": []}

    buy_orders = [o for o in data if o.get("is_buy_order")]
    sell_orders = [o for o in data if not o.get("is_buy_order")]

    buy_orders.sort(key=lambda o: o["price"], reverse=True)
    sell_orders.sort(key=lambda o: o["price"])

    def simplify(order: dict) -> dict:
        return {
            "price": order["price"],
            "volume_remain": order["volume_remain"],
            "location_id": order["location_id"],
        }

    return {
        "buy": [simplify(o) for o in buy_orders[:5]],
        "sell": [simplify(o) for o in sell_orders[:5]],
    }


def update_prices() -> None:
    """Fetch prices for all items/regions and store them in Redis."""

    for region_id in REGIONS:
        region_name = REGION_NAMES.get(region_id, str(region_id))
        for type_id in ITEMS:
            item_name = ITEM_NAMES.get(type_id, str(type_id))
            prices = fetch_best_prices(region_id, type_id)
            key = f"prices:{region_id}:{type_id}"
            try:
                redis_client.setex(key, TTL_SECONDS, json.dumps(prices))
                print(f"Loaded {item_name} prices for {region_name}")
            except Exception as exc:  # pragma: no cover - redis errors
                print(
                    f"Error storing prices for region {region_name} "
                    f"item {item_name}: {exc}"
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

