"""Trade opportunity calculator microservice.

This service reads market order data from Redis along with static
information about trade hubs, jump distances and item volumes.  It
calculates potential buy/sell opportunities between all trade hub
pairs and exposes the top results via a simple HTTP API.

Query parameters:

``wallet``:        maximum ISK to spend (default: 50_000_000)
``cargo``:         available cargo volume in m^3 (default: 230)
``min_profit``:    minimum profit in ISK to include (default: 1_000_000)
``limit``:         maximum number of results to return (default: 10)
"""

from __future__ import annotations

import json
import itertools
import logging
import math
import os
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import redis


# Default filters
DEFAULT_WALLET = 50_000_000
DEFAULT_CARGO = 230.0
DEFAULT_PROFIT = 1_000_000
DEFAULT_LIMIT = 10


# Resolve paths to shared static data directory
BASE_DIR = Path(__file__).resolve().parent
shared_dir = BASE_DIR / "shared"
if not shared_dir.exists():
    shared_dir = BASE_DIR.parent / "shared"

ITEMS_FILE = shared_dir / "static_data" / "items.json"
HUBS_FILE = shared_dir / "static_data" / "trade_hubs.json"
JUMPS_FILE = shared_dir / "static_data" / "jump_graph.json"


# Load static data
try:
    with ITEMS_FILE.open() as f:
        _items = json.load(f)
        ITEMS: dict[int, dict] = {entry["id"]: entry for entry in _items}
except FileNotFoundError:  # pragma: no cover - file missing only during dev
    ITEMS = {}

try:
    with HUBS_FILE.open() as f:
        TRADE_HUBS = json.load(f)
except FileNotFoundError:  # pragma: no cover - file missing only during dev
    TRADE_HUBS = []

try:
    with JUMPS_FILE.open() as f:
        JUMP_GRAPH = json.load(f)
except FileNotFoundError:  # pragma: no cover - file missing only during dev
    JUMP_GRAPH = {}


# Redis connection
redis_client = redis.Redis(
    host=os.environ.get("REDIS_HOST", "localhost"),
    port=int(os.environ.get("REDIS_PORT", 6379)),
    decode_responses=True,
)


# Logging configuration
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger(__name__)


def fetch_best_orders(region_id: int, item_id: int) -> tuple[dict | None, dict | None]:
    """Return best sell and buy orders for ``item_id`` in ``region_id``."""

    logger.debug("Fetching orders for region %s item %s", region_id, item_id)

    key = f"orders:{region_id}:{item_id}"
    data = redis_client.get(key)
    if not data:
        logger.debug("No order data for %s", key)
        return None, None
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:  # pragma: no cover - corrupt data
        logger.debug("Invalid JSON in %s", key)
        return None, None

    sell_orders = payload.get("sell", [])
    buy_orders = payload.get("buy", [])
    logger.debug(
        "Fetched %d sell and %d buy orders for %s",
        len(sell_orders),
        len(buy_orders),
        key,
    )
    sell = sell_orders[0] if sell_orders else None
    buy = buy_orders[0] if buy_orders else None
    return sell, buy


def calculate_trades(
    wallet: int = DEFAULT_WALLET,
    cargo: float = DEFAULT_CARGO,
    min_profit: int = DEFAULT_PROFIT,
    limit: int = DEFAULT_LIMIT,
) -> list[dict]:
    """Compute potential trade opportunities.

    Iterates over all ordered pairs of trade hubs and items.  For each
    pair it determines the maximum quantity that can be purchased given
    wallet, cargo space and order volumes, then calculates the expected
    profit.  Results are filtered by ``min_profit`` and sorted
    descending by profit.
    """

    logger.debug(
        "calculate_trades wallet=%s cargo=%s min_profit=%s limit=%s",
        wallet,
        cargo,
        min_profit,
        limit,
    )

    results: list[dict] = []

    for hub_a, hub_b in itertools.permutations(TRADE_HUBS, 2):
        region_a = hub_a["region_id"]
        region_b = hub_b["region_id"]
        # Skip trading within the same region as prices are identical
        if region_a == region_b:
            continue

        name_a = hub_a["name"]
        name_b = hub_b["name"]
        jumps = JUMP_GRAPH.get(name_a, {}).get(name_b)
        if jumps is None:
            continue

        logger.debug("Evaluating %s -> %s (%s jumps)", name_a, name_b, jumps)

        for item_id, item in ITEMS.items():
            sell, _ = fetch_best_orders(region_a, item_id)
            _, buy = fetch_best_orders(region_b, item_id)
            if not sell or not buy:
                continue

            buy_price = sell["price"]
            sell_price = buy["price"]
            if sell_price <= buy_price:
                continue

            volume_per_unit = item.get("volume") or 0
            available = min(
                sell.get("volume_remain", 0),
                buy.get("volume_remain", 0),
                math.floor(wallet / buy_price),
                math.floor(cargo / volume_per_unit) if volume_per_unit else 0,
            )
            if available <= 0:
                continue

            total_cost = buy_price * available
            total_volume = volume_per_unit * available
            revenue = sell_price * available
            profit = revenue - total_cost
            if profit < min_profit:
                continue

            profit_per_jump = profit / jumps if jumps else profit

            result = {
                "item": item.get("name", str(item_id)),
                "buy_region": name_a,
                "sell_region": name_b,
                "quantity": available,
                "total_cost": total_cost,
                "total_volume": total_volume,
                "expected_revenue": revenue,
                "profit": profit,
                "jumps": jumps,
                "profit_per_jump": profit_per_jump,
            }
            results.append(result)
            logger.debug("Found trade opportunity: %s", result)

    results.sort(key=lambda r: r["profit"], reverse=True)
    return results[:limit]


class Handler(BaseHTTPRequestHandler):
    """HTTP API returning trade opportunities as JSON."""

    def do_GET(self):  # noqa: N802 - required method name
        logger.debug("HTTP GET %s", self.path)

        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        def get_int(name: str, default: int) -> int:
            try:
                return int(params.get(name, [default])[0])
            except ValueError:
                return default

        wallet = get_int("wallet", DEFAULT_WALLET)
        cargo = float(params.get("cargo", [DEFAULT_CARGO])[0])
        min_profit = get_int("min_profit", DEFAULT_PROFIT)
        limit = get_int("limit", DEFAULT_LIMIT)

        data = calculate_trades(wallet, cargo, min_profit, limit)
        logger.debug("Returning %d opportunities", len(data))

        body = json.dumps(data, indent=2).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run() -> None:
    server = HTTPServer(("0.0.0.0", 8001), Handler)
    logger.info("Calculator service running on port 8001")
    server.serve_forever()


if __name__ == "__main__":
    run()

