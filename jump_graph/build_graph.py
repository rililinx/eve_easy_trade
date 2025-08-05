import json
import itertools
import urllib.request
from pathlib import Path

ESI_BASE = "https://esi.evetech.net/latest"
USER_AGENT = (
    "EveEasyTrade/0.1 (Scarlett Clocl; +https://github.com/your/repository; "
    "rililinx@gmail.com)"
)

TRADE_HUBS = [
    "Jita",
    "Rens",
    "Dodixie",
    "Hek",
    "Amarr",
    "Ashab",
    "Botane",
]


def post_json(url: str, data):
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:  # nosec B310 - trusted source
        return json.loads(resp.read().decode())


def get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req) as resp:  # nosec B310 - trusted source
        return json.loads(resp.read().decode())


def resolve_system_ids(names: list[str]) -> dict[str, int]:
    data = post_json(f"{ESI_BASE}/universe/ids/", names)
    systems = data.get("systems", [])
    return {entry["name"]: entry["id"] for entry in systems}


def route_jumps(origin_id: int, dest_id: int) -> int:
    route = get_json(f"{ESI_BASE}/route/{origin_id}/{dest_id}/")
    return max(len(route) - 1, 0)


def build_jump_graph(names: list[str]) -> dict[str, dict[str, int]]:
    ids = resolve_system_ids(names)
    graph: dict[str, dict[str, int]] = {name: {} for name in ids}
    for a, b in itertools.combinations(ids.keys(), 2):
        jumps = route_jumps(ids[a], ids[b])
        graph[a][b] = jumps
        graph[b][a] = jumps
    return graph


def save_graph(graph: dict[str, dict[str, int]], out_file: Path) -> None:
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with out_file.open("w") as f:
        json.dump(graph, f, indent=2, sort_keys=True)


def main() -> None:
    graph = build_jump_graph(TRADE_HUBS)
    out_file = Path(__file__).resolve().parent.parent / "shared" / "static_data" / "jump_graph.json"
    save_graph(graph, out_file)
    print(f"Saved jump graph for {len(graph)} hubs to {out_file}")


if __name__ == "__main__":
    main()
