"""Price Loader microservice.

This service queries the EVE Online ESI API for the best buy and sell
orders for each configured item in the major trade hub regions.  The
top five buy and sell orders for every ``(region, item)`` pair are
cached in Redis as JSON with a one hour TTL.  Data is refreshed every
15 minutes and a manual refresh can be triggered via an HTTP endpoint.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
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

REGIONS_FILE = shared_dir / "static_data" / "regions.json"
TRADE_HUBS_FILE = shared_dir / "static_data" / "trade_hubs.json"
ITEMS_FILE = shared_dir / "static_data" / "items.json"

try:
    with REGIONS_FILE.open() as f:
        _regions = json.load(f)
        REGION_NAMES: dict[int, str] = {entry["id"]: entry["name"] for entry in _regions}
except FileNotFoundError:
    REGION_NAMES = {}

try:
    with TRADE_HUBS_FILE.open() as f:
        _hubs = json.load(f)
        REGIONS: list[int] = sorted({entry["region_id"] for entry in _hubs})
except FileNotFoundError:
    REGIONS = []

try:
    with ITEMS_FILE.open() as f:
        _items = json.load(f)
        ITEM_IDS: list[int] = [entry["id"] for entry in _items]
        ITEM_NAMES: dict[int, str] = {entry["id"]: entry["name"] for entry in _items}
except FileNotFoundError:
    ITEM_IDS = []
    ITEM_NAMES = {}


# Redis connection
redis_client = redis.Redis(
    host=os.environ.get("REDIS_HOST", "localhost"),
    port=int(os.environ.get("REDIS_PORT", 6379)),
    decode_responses=True,
)


def get_json(url: str, params: dict | None = None):
    """Fetch JSON data from ``url``."""

    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req) as resp:  # nosec B310 - trusted source
        data = json.loads(resp.read().decode())
    return data


def fetch_best_orders(region_id: int, type_id: int, order_type: str) -> list[dict]:
    """Return top five ``order_type`` orders for ``type_id`` in ``region_id``."""

    region_name = REGION_NAMES.get(region_id, str(region_id))
    item_name = ITEM_NAMES.get(type_id, str(type_id))
    try:
        data = get_json(
            f"{ESI_BASE}/markets/{region_id}/orders/",
            params={"type_id": type_id, "order_type": order_type},
        )
    except Exception as exc:  # pragma: no cover - network errors
        print(f"Error fetching {order_type} {item_name} in {region_name}: {exc}")
        return []

    reverse = order_type == "buy"
    data.sort(key=lambda o: o["price"], reverse=reverse)
    return data[:5]


def update_orders() -> None:
    """Fetch best buy/sell orders for all items and regions and store them."""

    def process_region(region_id: int) -> None:
        region_name = REGION_NAMES.get(region_id, str(region_id))
        for item_id in ITEM_IDS:
            item_name = ITEM_NAMES.get(item_id, str(item_id))
            buy = fetch_best_orders(region_id, item_id, "buy")
            sell = fetch_best_orders(region_id, item_id, "sell")
            key = f"orders:{region_id}:{item_id}"
            value = {"buy": buy, "sell": sell}
            try:
                redis_client.setex(key, TTL_SECONDS, json.dumps(value))
                print(
                    f"Cached {item_name} in {region_name}: {len(buy)} buy / {len(sell)} sell"
                )
            except Exception as exc:  # pragma: no cover - redis errors
                print(f"Error storing {item_name} in {region_name}: {exc}")

    with ThreadPoolExecutor() as executor:
        futures = [executor.submit(process_region, region_id) for region_id in REGIONS]
        for future in futures:
            future.result()


def schedule_updates() -> None:
    """Start a background thread that refreshes data periodically."""

    def loop():
        while True:
            print("Updating orders...")
            update_orders()
            time.sleep(UPDATE_INTERVAL)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()


class Handler(BaseHTTPRequestHandler):
    """HTTP API exposing the service and a manual refresh endpoint."""

    def do_GET(self):  # noqa: N802 - required method name
        if self.path == "/refresh":
            threading.Thread(target=update_orders, daemon=True).start()
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

