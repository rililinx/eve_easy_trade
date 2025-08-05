import json
import sys
import urllib.request

ESI_BASE = "https://esi.evetech.net/latest"


def fetch_item_names(ids: list[int]) -> dict[int, str]:
    url = f"{ESI_BASE}/universe/names/"
    data = json.dumps(ids).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:  # nosec B310 - trusted source
        results = json.loads(resp.read().decode())
    return {r["id"]: r["name"] for r in results if r.get("category") == "inventory_type"}


def main() -> None:
    ids = [int(arg) for arg in sys.argv[1:]]
    if not ids:
        print("Usage: get_item_names.py <id> [<id> ...]")
        return
    mapping = fetch_item_names(ids)
    print(json.dumps(mapping, indent=2))


if __name__ == "__main__":
    main()
