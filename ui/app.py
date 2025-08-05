"""Streamlit-based UI for browsing trade opportunities.

This application connects to Redis to retrieve pre-calculated trade
opportunities and allows the user to filter them based on available
wallet funds and cargo space.  Results are displayed in a sortable table
for easy comparison.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import redis
import requests
import streamlit as st


# ---------------------------------------------------------------------------
# Static data
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
shared_dir = BASE_DIR / "shared"
if not shared_dir.exists():
    shared_dir = BASE_DIR.parent / "shared"
static_dir = shared_dir / "static_data"

ITEMS_FILE = static_dir / "items.json"
STATIONS_FILE = static_dir / "stations.json"

try:
    with ITEMS_FILE.open() as f:
        _items = json.load(f)
        ITEM_NAMES = {entry["id"]: entry["name"] for entry in _items}
except FileNotFoundError:
    ITEM_NAMES = {}

try:
    with STATIONS_FILE.open() as f:
        STATION_NAMES = json.load(f)
except FileNotFoundError:
    STATION_NAMES = {}


# ---------------------------------------------------------------------------
# Redis helpers
# ---------------------------------------------------------------------------

@st.cache_data(ttl=15 * 60)
def load_opportunities() -> list[dict]:
    """Fetch all stored opportunities from Redis."""

    client = redis.Redis(
        host=os.environ.get("REDIS_HOST", "localhost"),
        port=int(os.environ.get("REDIS_PORT", 6379)),
        decode_responses=True,
    )

    rows: list[dict] = []
    for key in client.keys("opportunities:*"):
        data = client.get(key)
        if not data:
            continue
        try:
            opportunities = json.loads(data)
        except json.JSONDecodeError:
            continue

        rows.extend(opportunities)

    return rows


# ---------------------------------------------------------------------------
# Station name lookup
# ---------------------------------------------------------------------------

ESI_BASE = "https://esi.evetech.net/latest"
USER_AGENT = "EveEasyTradeUI/0.1 (github.com/your/repository)"


def get_station_name(station_id: int | None) -> str:
    """Resolve a station ID to its name using cached static data."""

    if not station_id:
        return "Unknown"

    sid = str(station_id)
    name = STATION_NAMES.get(sid)
    if name:
        return name

    try:  # Fetch once and persist for future lookups
        resp = requests.get(
            f"{ESI_BASE}/universe/stations/{int(station_id)}/",
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        resp.raise_for_status()
        name = resp.json().get("name", sid)
    except Exception:
        name = sid

    STATION_NAMES[sid] = name
    STATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with STATIONS_FILE.open("w") as f:
        json.dump(STATION_NAMES, f, indent=2)
    return name


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------

st.set_page_config(page_title="EVE Easy Trade", layout="wide")
st.title("EVE Easy Trade")

wallet = st.number_input("Wallet (ISK)", min_value=0.0, value=0.0, step=1000.0)
cargo = st.number_input("Cargo capacity (m³)", min_value=0.0, value=0.0, step=1.0)

raw_rows = load_opportunities()

rows: list[dict] = []
for opp in raw_rows:
    if opp.get("full_price", 0) > wallet:
        continue
    if opp.get("full_volume", 0) > cargo:
        continue
    profit = opp.get("profit", 0)
    profit_per_jump = opp.get("profit_per_jump") or 0
    jumps = profit / profit_per_jump if profit_per_jump else 0
    rows.append(
        {
            "Item name": ITEM_NAMES.get(opp.get("item_id"), str(opp.get("item_id"))),
            "From": get_station_name(opp.get("from_location_id")),
            "To": get_station_name(opp.get("to_location_id")),
            "Volume": opp.get("full_volume"),
            "Quantity": opp.get("amount"),
            "Price": opp.get("full_price"),
            "Jumps": jumps,
            "Profit": profit,
            "Profit/jump": profit_per_jump,
        }
    )

if rows:
    df = pd.DataFrame(rows)
    st.dataframe(df.sort_values("Profit", ascending=False), use_container_width=True)
else:
    st.info("No opportunities match the selected constraints.")


if __name__ == "__main__":  # pragma: no cover
    # When executed directly, run via Streamlit for convenience.
    import subprocess
    subprocess.run(
        [
            "streamlit",
            "run",
            __file__,
            "--server.address=0.0.0.0",
            "--server.port=8501",
        ],
        check=True,
    )

