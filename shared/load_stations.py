import json
import urllib.request
from pathlib import Path

ESI_BASE = "https://esi.evetech.net/latest"
USER_AGENT = (
    "EveEasyTrade/0.1 (+https://github.com/your/repository)"
)

def get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req) as resp:  # nosec B310 - trusted source
        return json.loads(resp.read().decode())

def fetch_all_stations():
    station_ids = get_json(f"{ESI_BASE}/universe/stations/")
    stations = []
    for station_id in station_ids:
        info = get_json(f"{ESI_BASE}/universe/stations/{station_id}/")
        name = info.get("name")
        stations.append({"id": station_id, "name": name})
        print(f"Fetched station {station_id}: {name}")
    return stations

def save_stations(stations, out_file: Path) -> None:
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with out_file.open("w") as f:
        json.dump(stations, f, indent=2)

def main() -> None:
    stations = fetch_all_stations()
    out_file = Path(__file__).parent / "static_data" / "stations.json"
    save_stations(stations, out_file)
    print(f"Saved {len(stations)} stations to {out_file}")

if __name__ == "__main__":  # pragma: no cover - manual execution
    main()
