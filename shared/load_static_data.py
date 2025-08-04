import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path

ESI_BASE = "https://esi.evetech.net/latest"


def get_json(url: str, params: dict | None = None):
    """Fetch JSON data from a URL with optional query parameters."""
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url) as resp:  # nosec B310 - trusted source
        return json.loads(resp.read().decode())


def fetch_items(limit: int | None = None):
    """Retrieve all item type ids then fetch details for each item.

    Args:
        limit: Optional number of items to fetch for quick runs.
    """
    items: list[dict] = []
    page = 1
    while True:
        ids = get_json(f"{ESI_BASE}/universe/types/", {"page": page})
        if not ids:
            break
        for type_id in ids:
            info = get_json(f"{ESI_BASE}/universe/types/{type_id}/")
            name = info.get("name")
            if isinstance(name, dict):
                name = name.get("en-us")
            items.append({
                "id": type_id,
                "name": name,
                "volume": info.get("packaged_volume") or info.get("volume"),
            })
            if limit and len(items) >= limit:
                return items
        page += 1
    return items


def fetch_regions():
    """Retrieve all regions with their names."""
    region_ids = get_json(f"{ESI_BASE}/universe/regions/")
    regions: list[dict] = []
    for region_id in region_ids:
        info = get_json(f"{ESI_BASE}/universe/regions/{region_id}/")
        regions.append({"id": region_id, "name": info.get("name")})
    return regions


def save_data(items, regions, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "items.json").open("w") as f:
        json.dump(items, f)
    with (out_dir / "regions.json").open("w") as f:
        json.dump(regions, f)


def main():
    parser = argparse.ArgumentParser(description="Fetch static EVE Online data")
    parser.add_argument(
        "--item-limit",
        type=int,
        default=0,
        help="Optional limit of items to download (0 = all)",
    )
    args = parser.parse_args()

    limit = args.item_limit or None
    items = fetch_items(limit=limit)
    regions = fetch_regions()
    out_dir = Path(__file__).parent / "static_data"
    save_data(items, regions, out_dir)
    print(f"Saved {len(items)} items and {len(regions)} regions to {out_dir}")


if __name__ == "__main__":
    main()
