"""Price Loader microservice.

This service periodically queries the EVE Online ESI API for all market
orders in configured regions.  Orders for each region are cached as a
JSON blob in Redis for one hour and refreshed every 15 minutes.  A
manual refresh can also be triggered via an HTTP endpoint.
"""

from __future__ import annotations

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
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

REGIONS_FILE = shared_dir / "static_data" / "regions.json"
TRADE_HUBS_FILE = shared_dir / "static_data" / "trade_hubs.json"

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


# Redis connection
redis_client = redis.Redis(
    host=os.environ.get("REDIS_HOST", "localhost"),
    port=int(os.environ.get("REDIS_PORT", 6379)),
    decode_responses=True,
)


def get_json(url: str, params: dict | None = None):
    """Fetch JSON data from ``url`` and return it along with headers."""

    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req) as resp:  # nosec B310 - trusted source
        data = json.loads(resp.read().decode())
        headers = resp.headers
    return data, headers


def fetch_region_orders(region_id: int) -> list[dict]:
    """Retrieve all market orders for ``region_id`` handling pagination."""

    orders: list[dict] = []
    page = 1
    region_name = REGION_NAMES.get(region_id, str(region_id))
    while True:
        try:
            data, headers = get_json(
                f"{ESI_BASE}/markets/{region_id}/orders/",
                params={"page": page},
            )
        except Exception as exc:  # pragma: no cover - network errors
            print(f"Error fetching page {page} region {region_name}: {exc}")
            break

        print(f"page {page} region {region_name}")
        orders.extend(data)
        page_count = int(headers.get("X-Pages", 1))
        if page >= page_count:
            break
        page += 1

    return orders


def update_orders() -> None:
    """Fetch market orders for all regions and store them in Redis."""

    def fetch_and_store(region_id: int) -> None:
        region_name = REGION_NAMES.get(region_id, str(region_id))
        orders = fetch_region_orders(region_id)
        key = f"orders:{region_id}"
        try:
            redis_client.setex(key, TTL_SECONDS, json.dumps(orders))
            print(f"Loaded {len(orders)} orders for {region_name}")
        except Exception as exc:  # pragma: no cover - redis errors
            print(f"Error storing orders for region {region_name}: {exc}")

    with ThreadPoolExecutor() as executor:
        futures = [executor.submit(fetch_and_store, region_id) for region_id in REGIONS]
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

