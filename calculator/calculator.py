"""Trade opportunity calculator.

This module reads market order data from Redis along with static
information about trade hubs, jump distances and item volumes.  It
calculates potential buy/sell opportunities for **all** item and trade
hub pairs and stores the results back into Redis.  Opportunities are
persisted immediately after each item is processed so that other
services can start consuming data before the full calculation completes.

Each stored opportunity contains:

* ``from`` – source trade hub name
* ``to`` – destination trade hub name
* ``item_id`` – type identifier
* ``amount`` – number of units that can be traded
* ``full_volume`` – total volume in m³
* ``full_price`` – total sale price at the destination
* ``profit`` – potential profit in ISK
* ``profit_per_jump`` – profit divided by jump distance between hubs
"""

from __future__ import annotations

import itertools
import json
import logging
import os
from pathlib import Path

import redis


# ---------------------------------------------------------------------------
# Static data setup
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
shared_dir = BASE_DIR / "shared"
if not shared_dir.exists():
    shared_dir = BASE_DIR.parent / "shared"

ITEMS_FILE = shared_dir / "static_data" / "items.json"
HUBS_FILE = shared_dir / "static_data" / "trade_hubs.json"
JUMPS_FILE = shared_dir / "static_data" / "jump_graph.json"


try:  # pragma: no cover - files may be missing during development
    with ITEMS_FILE.open() as f:
        _items = json.load(f)
        ITEMS: dict[int, dict] = {entry["id"]: entry for entry in _items}
except FileNotFoundError:  # pragma: no cover - missing static data
    ITEMS = {}

try:  # pragma: no cover - files may be missing during development
    with HUBS_FILE.open() as f:
        TRADE_HUBS = json.load(f)
except FileNotFoundError:  # pragma: no cover - missing static data
    TRADE_HUBS = []

try:  # pragma: no cover - files may be missing during development
    with JUMPS_FILE.open() as f:
        JUMP_GRAPH = json.load(f)
except FileNotFoundError:  # pragma: no cover - missing static data
    JUMP_GRAPH = {}


# ---------------------------------------------------------------------------
# Redis and logging configuration
# ---------------------------------------------------------------------------

redis_client = redis.Redis(
    host=os.environ.get("REDIS_HOST", "localhost"),
    port=int(os.environ.get("REDIS_PORT", 6379)),
    decode_responses=True,
)

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Order fetching
# ---------------------------------------------------------------------------

def fetch_best_orders(region_id: int, item_id: int) -> tuple[dict | None, dict | None]:
    """Return the best sell and buy orders for ``item_id`` in ``region_id``."""

    key = f"orders:{region_id}:{item_id}"
    logger.debug("Fetching %s", key)
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


# ---------------------------------------------------------------------------
# Opportunity calculation
# ---------------------------------------------------------------------------

def calculate_item_opportunities(item_id: int, item: dict) -> list[dict]:
    """Calculate trade opportunities for a single item across hub pairs."""

    opportunities: list[dict] = []
    volume_per_unit = item.get("volume") or 0

    for hub_a, hub_b in itertools.permutations(TRADE_HUBS, 2):
        region_a = hub_a["region_id"]
        region_b = hub_b["region_id"]
        if region_a == region_b:
            continue

        name_a = hub_a["name"]
        name_b = hub_b["name"]
        jumps = JUMP_GRAPH.get(name_a, {}).get(name_b)
        if jumps is None:
            continue

        sell, _ = fetch_best_orders(region_a, item_id)
        _, buy = fetch_best_orders(region_b, item_id)
        if not sell or not buy:
            continue

        buy_price = sell["price"]
        sell_price = buy["price"]
        if sell_price <= buy_price:
            continue

        amount = min(sell.get("volume_remain", 0), buy.get("volume_remain", 0))
        if amount <= 0:
            continue

        full_volume = volume_per_unit * amount
        full_price = sell_price * amount
        profit = (sell_price - buy_price) * amount
        profit_per_jump = profit / jumps if jumps else profit

        opportunity = {
            "from": name_a,
            "to": name_b,
            "item_id": item_id,
            "amount": amount,
            "full_volume": full_volume,
            "full_price": full_price,
            "profit": profit,
            "profit_per_jump": profit_per_jump,
        }
        opportunities.append(opportunity)
        logger.debug("Opportunity found: %s", opportunity)

    return opportunities


def calculate_and_store_opportunities() -> dict[int, list[dict]]:
    """Calculate opportunities for all items and store each item immediately."""

    logger.info("Calculating trade opportunities...")
    results: dict[int, list[dict]] = {}

    for item_id, item in ITEMS.items():
        opportunities = calculate_item_opportunities(item_id, item)
        if not opportunities:
            continue

        key = f"opportunities:{item_id}"
        redis_client.set(key, json.dumps(opportunities))
        logger.debug("Stored %d opportunities in %s", len(opportunities), key)
        results[item_id] = opportunities

    logger.info("Stored opportunities for %d items", len(results))
    return results


if __name__ == "__main__":  # pragma: no cover - manual execution
    calculate_and_store_opportunities()

