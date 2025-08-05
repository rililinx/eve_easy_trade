"""Streamlit-based UI for browsing trade opportunities.

This application connects to Redis to retrieve pre-calculated trade
opportunities and allows the user to filter them based on available
wallet funds and cargo space.  Results are displayed in a sortable table
for easy comparison.
"""

from __future__ import annotations

import json
import os
import requests
import pandas as pd
import redis
import streamlit as st


# ---------------------------------------------------------------------------
# Redis helpers
# ---------------------------------------------------------------------------

@st.cache_data(ttl=60)
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


@st.cache_data(show_spinner=False)
def get_station_name(station_id: int | None) -> str:
    """Resolve a station ID to its name using ESI."""

    if not station_id:
        return "Unknown"
    try:
        resp = requests.get(
            f"{ESI_BASE}/universe/stations/{int(station_id)}/",
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("name", str(station_id))
    except Exception:
        return str(station_id)


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
            "Item name": opp.get("item_name"),
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

