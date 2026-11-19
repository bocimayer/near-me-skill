"""near_me.py - find places near a starting point, ranked by real route time (not air distance).

Backends:
  osm    (default, free, no key): Nominatim geocoding + Overpass place search +
         FOSSGIS OSRM routing (routing.openstreetmap.de, foot / car / bike).
  google (only if GOOGLE_MAPS_API_KEY is in .env AND --backend google):
         Places API (New) Text Search + Routes API computeRouteMatrix. Billed by Google
         beyond the monthly free allowance.

Config file (optional): .env next to this script (parsed here, not process environment
variables). Copy .env.example to .env.
  HOME_ADDRESS=...            default starting point ("home")
  GOOGLE_MAPS_API_KEY=...     optional

Examples:
  python near_me.py --tags "shop=craft;shop=art" --mode foot
  python near_me.py --name "hobby|craft" --mode car --radius 1000 --from "Alexanderplatz, Berlin"
  python near_me.py --backend google --query "hardware store" --mode foot
  python near_me.py --from "52.5219,13.4132" --mode car --places-json nearby.json
    (nearby.json = saved Composio GOOGLE_MAPS_NEARBY_SEARCH output; routes via free OSRM)

Radius = maximum ROUTE distance in metres (default: foot 2000 m, car 1000 m, bike 3000 m).
Places beyond it by route are dropped even if close in air (river, motorway, no bridge).
"""
import argparse
import json
import math
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ENV_PATH = Path(__file__).with_name(".env")  # optional; never committed (see .gitignore)
UA = "near-me-skill/1.0 (+https://github.com/bocimayer/near-me-skill)"
DEFAULT_RADIUS = {"foot": 2000, "car": 1000, "bike": 3000, "transit": 3000}
OSRM = {"foot": "routed-foot", "car": "routed-car", "bike": "routed-bike"}
GMODE = {"foot": "WALK", "car": "DRIVE", "bike": "BICYCLE", "transit": "TRANSIT"}


def read_env() -> dict:
    env = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def http(url: str, data: bytes | None = None, headers: dict | None = None, timeout: int = 60):
    h = {"User-Agent": UA}
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def air_m(a: tuple, b: tuple) -> float:
    r = 6371000.0
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def geocode(text: str, country: str = "") -> tuple[float, float, str]:
    """'lat,lon' or an address (Nominatim; optional ISO country code such as 'hu', 'de')."""
    try:
        la, lo = (float(x) for x in text.split(","))
        return la, lo, f"{la:.5f},{lo:.5f}"
    except ValueError:
        pass
    params = {"q": text, "format": "json", "limit": 1}
    if country:
        params["countrycodes"] = country
    q = urllib.parse.urlencode(params)
    res = http(f"https://nominatim.openstreetmap.org/search?{q}")
    if not res:
        sys.exit(f"ERROR: address not found: {text}")
    return float(res[0]["lat"]), float(res[0]["lon"]), res[0]["display_name"]


# ---------------- OSM backend ----------------
def osm_places(lat: float, lon: float, radius: int, tags: list[str], name_re: str | None) -> list[dict]:
    parts = []
    for t in tags:
        k, _, v = t.partition("=")
        sel = f'["{k.strip()}"="{v.strip()}"]' if v else f'["{k.strip()}"]'
        parts.append(f"nwr(around:{radius},{lat},{lon}){sel};")
    if name_re:
        for k in ("shop", "amenity", "craft"):
            parts.append(f'nwr(around:{radius},{lat},{lon})["{k}"]["name"~"{name_re}",i];')
    if not parts:
        sys.exit("ERROR: give --tags and/or --name for the osm backend")
    q = f"[out:json][timeout:50];({''.join(parts)});out center tags;"
    res = None
    mirrors = ("https://overpass-api.de/api/interpreter", "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
               "https://overpass.kumi.systems/api/interpreter")
    wait = 5
    for attempt in range(5):   # public Overpass is often "at capacity": back off and retry
        for url in mirrors:
            try:
                res = http(url, urllib.parse.urlencode({"data": q}).encode(), timeout=40)
                break
            except Exception as e:  # noqa: BLE001 - try the next mirror
                print(f"(overpass {url.split('/')[2]} failed: {e})", file=sys.stderr)
        if res is not None:
            break
        print(f"(all Overpass mirrors busy, retry in {wait} s)", file=sys.stderr)
        time.sleep(wait)
        wait *= 2
    if res is None:
        sys.exit("ERROR: Overpass busy or unreachable after 5 tries. Retry later or use --backend google.")
    out, seen = [], set()
    for el in res.get("elements", []):
        tg = el.get("tags", {})
        la = el.get("lat") or el.get("center", {}).get("lat")
        lo = el.get("lon") or el.get("center", {}).get("lon")
        if la is None:
            continue
        name = tg.get("name", "(no name)")
        key = (name, round(la, 4), round(lo, 4))
        if key in seen:
            continue
        seen.add(key)
        addr = " ".join(x for x in (tg.get("addr:postcode"), tg.get("addr:street"),
                                    tg.get("addr:housenumber")) if x)
        kind = next((f"{k}={tg[k]}" for k in ("shop", "amenity", "craft") if k in tg), "")
        out.append({"name": name, "addr": addr, "kind": kind, "lat": la, "lon": lo,
                    "hours": tg.get("opening_hours", ""), "web": tg.get("website") or tg.get("contact:website", ""),
                    "link": f"https://www.openstreetmap.org/{el['type']}/{el['id']}"})
    return out


def osm_routes(origin: tuple, places: list[dict], mode: str) -> None:
    if mode not in OSRM:
        sys.exit("ERROR: osm backend has no public transit routing; use --backend google or foot/car/bike")
    for i in range(0, len(places), 90):
        chunk = places[i:i + 90]
        coords = ";".join([f"{origin[1]},{origin[0]}"] + [f"{p['lon']},{p['lat']}" for p in chunk])
        url = (f"https://routing.openstreetmap.de/{OSRM[mode]}/table/v1/driving/{coords}"
               f"?sources=0&annotations=duration,distance")
        res = http(url)
        for j, p in enumerate(chunk, start=1):
            p["route_s"] = res["durations"][0][j]
            p["route_m"] = res["distances"][0][j]
        time.sleep(1)


# ---------------- Places from a saved Google response (Composio) ----------------
def json_places(path: str) -> list[dict]:
    """Places from a saved Google Places response, e.g. Composio GOOGLE_MAPS_NEARBY_SEARCH or
    GOOGLE_MAPS_TEXT_SEARCH output. Accepts {"places": [...]}, Composio's nested
    {"data": {"places": [...]}}, a list of such responses, or a bare list of places.
    Drops places that are not OPERATIONAL and duplicates (same name and location)."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))

    def collect(obj) -> list:
        if isinstance(obj, list):
            if obj and isinstance(obj[0], dict) and "displayName" in obj[0]:
                return obj
            return [p for x in obj for p in collect(x)]
        if isinstance(obj, dict):
            if isinstance(obj.get("places"), list):
                return obj["places"]
            return [p for v in obj.values() if isinstance(v, (dict, list)) for p in collect(v)]
        return []

    out, seen = [], set()
    for p in collect(raw):
        if p.get("businessStatus", "OPERATIONAL") != "OPERATIONAL" or "location" not in p:
            continue
        name = p.get("displayName", {}).get("text", "(no name)")
        la, lo = p["location"]["latitude"], p["location"]["longitude"]
        key = (name, round(la, 5), round(lo, 5))
        if key in seen:
            continue
        seen.add(key)
        out.append({"name": name, "addr": p.get("formattedAddress", ""),
                    "kind": p.get("primaryType", ""), "lat": la, "lon": lo, "hours": "", "web": "",
                    "link": p.get("googleMapsUri", "")})
    return out


# ---------------- Google backend ----------------
def google_places(key: str, query: str, lat: float, lon: float, radius: int, country: str = "") -> list[dict]:
    body = {"textQuery": query, "maxResultCount": 20,
            "locationBias": {"circle": {"center": {"latitude": lat, "longitude": lon},
                                        "radius": float(min(radius * 1.5, 50000))}}}
    if country:
        body["regionCode"] = country.upper()
    hdr = {"Content-Type": "application/json", "X-Goog-Api-Key": key,
           "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location,places.googleMapsUri,places.primaryType"}
    res = http("https://places.googleapis.com/v1/places:searchText", json.dumps(body).encode(), hdr)
    return [{"name": p["displayName"]["text"], "addr": p.get("formattedAddress", ""),
             "kind": p.get("primaryType", ""), "lat": p["location"]["latitude"],
             "lon": p["location"]["longitude"], "hours": "", "web": "",
             "link": p.get("googleMapsUri", "")} for p in res.get("places", [])]


def google_routes(key: str, origin: tuple, places: list[dict], mode: str) -> None:
    if not places:
        return
    def wp(la, lo):
        return {"waypoint": {"location": {"latLng": {"latitude": la, "longitude": lo}}}}
    body = {"origins": [wp(*origin)], "destinations": [wp(p["lat"], p["lon"]) for p in places],
            "travelMode": GMODE[mode]}
    if mode == "car":
        body["routingPreference"] = "TRAFFIC_AWARE"
    hdr = {"Content-Type": "application/json", "X-Goog-Api-Key": key,
           "X-Goog-FieldMask": "originIndex,destinationIndex,duration,distanceMeters,condition"}
    for r in http("https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix",
                  json.dumps(body).encode(), hdr):
        p = places[r["destinationIndex"]]
        if r.get("condition") == "ROUTE_EXISTS":
            p["route_s"] = float(r["duration"].rstrip("s"))
            p["route_m"] = r.get("distanceMeters")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="origin", default="home", help='"home" (HOME_ADDRESS in .env), an address, or "lat,lon"')
    ap.add_argument("--mode", choices=["foot", "car", "bike", "transit"], default="foot")
    ap.add_argument("--radius", type=int, help="max ROUTE distance, m")
    ap.add_argument("--backend", choices=["osm", "google"], default="osm")
    ap.add_argument("--tags", default="", help='osm: "shop=craft;amenity=pharmacy"')
    ap.add_argument("--name", help="osm: name regex, case-insensitive (Hungarian words)")
    ap.add_argument("--query", help="google: free-text query in Hungarian")
    ap.add_argument("--places-json", help="saved Google Places response (Composio Nearby/Text Search); "
                                          "skips place search, routes these places with free OSRM")
    ap.add_argument("--country", help="ISO country code to limit address lookup, e.g. hu, de, us")
    ap.add_argument("--max", type=int, default=10)
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Hungarian accents in the Windows console
    env = read_env()

    src = a.origin
    if src == "home":
        src = env.get("HOME_ADDRESS")
        if not src:
            sys.exit(f"ERROR: no HOME_ADDRESS in {ENV_PATH}. Give --from or fill the file.")
    lat, lon, label = geocode(src, a.country or env.get("COUNTRY", ""))
    radius = a.radius or DEFAULT_RADIUS[a.mode]
    origin = (lat, lon)

    if a.places_json:
        places = json_places(a.places_json)
        osm_routes(origin, places, a.mode)
        a.backend = "google places (saved) + osrm routes"
    elif a.backend == "google":
        key = env.get("GOOGLE_MAPS_API_KEY")
        if not key:
            sys.exit(f"ERROR: no GOOGLE_MAPS_API_KEY in {ENV_PATH}")
        if not a.query:
            sys.exit("ERROR: google backend needs --query")
        places = google_places(key, a.query, lat, lon, radius, a.country or env.get("COUNTRY", ""))
        google_routes(key, origin, places, a.mode)
        print(f"(google calls: 1 Text Search Pro, {len(places)} route-matrix elements)", file=sys.stderr)
    else:
        tags = [t for t in a.tags.split(";") if t.strip()]
        places = osm_places(lat, lon, radius, tags, a.name)
        osm_routes(origin, places, a.mode)

    for p in places:
        p["air_m"] = air_m(origin, (p["lat"], p["lon"]))
    routed = [p for p in places if p.get("route_m") is not None]
    inside = sorted((p for p in routed if p["route_m"] <= radius), key=lambda p: p["route_s"])
    beyond = sorted((p for p in routed if p["route_m"] > radius), key=lambda p: p["route_s"])

    print(f"From: {label}")
    print(f"Mode: {a.mode} | radius: {radius} m by route | backend: {a.backend}")
    print(f"Found {len(places)}, routed {len(routed)}, within radius {len(inside)}, beyond {len(beyond)}")
    print("| # | Name | Address | Type | Route time (min) | Route (m) | Air (m) | Hours | Link |")
    print("|---|---|---|---|---|---|---|---|---|")
    for i, p in enumerate(inside[:a.max], 1):
        print(f"| {i} | {p['name']} | {p['addr'] or '-'} | {p['kind']} | {p['route_s']/60:.0f} min | "
              f"{p['route_m']:.0f} m | {p['air_m']:.0f} m | {p['hours'] or '-'} | {p['link']} |")
    if not inside and beyond:
        n = beyond[0]
        print(f"Nothing within {radius} m. Closest beyond: {n['name']} ({n['addr'] or '-'}), "
              f"{n['route_s']/60:.0f} min, {n['route_m']:.0f} m by route.")


if __name__ == "__main__":
    main()
