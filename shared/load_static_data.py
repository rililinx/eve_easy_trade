import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path

ESI_BASE = "https://esi.evetech.net/latest"
USER_AGENT = (
    "EveEasyTrade/0.1 (Scarlett Clocl; +https://github.com/your/repository; "
    "rililinx@gmail.com)"
)


def get_json(url: str, params: dict | None = None):
    """Fetch JSON data from a URL with optional query parameters."""
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req) as resp:  # nosec B310 - trusted source
        return json.loads(resp.read().decode())


def fetch_items(limit: int | None = None):
    """Retrieve marketable items from ESI market groups and fetch their details.

    Args:
        limit: Optional number of items to fetch for quick runs.
    """
    group_ids = get_json(f"{ESI_BASE}/markets/groups/")
    print(f"Fetched {len(group_ids)} market groups")

    type_ids: set[int] = set()
    for group_id in group_ids:
        group = get_json(f"{ESI_BASE}/markets/groups/{group_id}/")
        name = group.get("name")
        if isinstance(name, dict):
            name = name.get("en-us")
        types = group.get("types") or []
        print(f"Fetched market group {group_id}: {name} ({len(types)} types)")
        type_ids.update(types)
        if limit and len(type_ids) >= limit:
            break

    sorted_ids = sorted(type_ids)
    if limit:
        sorted_ids = sorted_ids[:limit]

    items: list[dict] = []
    for type_id in sorted_ids:
        info = get_json(f"{ESI_BASE}/universe/types/{type_id}/")
        name = info.get("name")
        if isinstance(name, dict):
            name = name.get("en-us")
        print(f"Fetched item {type_id}: {name}")
        items.append({
            "id": type_id,
            "name": name,
            "volume": info.get("packaged_volume") or info.get("volume"),
        })
    return items


def fetch_regions():
    """Retrieve all regions with their names."""
    region_ids = get_json(f"{ESI_BASE}/universe/regions/")
    regions: list[dict] = []
    for region_id in region_ids:
        info = get_json(f"{ESI_BASE}/universe/regions/{region_id}/")
        name = info.get("name")
        print(f"Fetched region {region_id}: {name}")
        regions.append({"id": region_id, "name": name})
    return regions


def save_data(items, regions, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "items.json").open("w") as f:
        json.dump(items, f, indent=2)
    with (out_dir / "regions.json").open("w") as f:
        json.dump(regions, f, indent=2)


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
