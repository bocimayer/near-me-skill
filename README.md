# near-me: "nearest shop near me" by real walking & driving route — Claude Code skill + Python CLI

**Find the nearest shop, store, pharmacy or place to any address, ranked by real route time and
route distance on foot, by car or by bike — not by straight-line distance.**
Free by default (OpenStreetMap + OSRM, no API key). Optional Google Places / Google Maps.

Works as a **Claude Code skill** (Agent Skill, `SKILL.md`), as a tool for any AI agent
(Claude, ChatGPT, Codex, Cursor, MCP / Composio agents), or as a plain command-line tool.

> "Where is the nearest hardware store I can walk to?"
> "Find a pharmacy within 1 km by car from Alexanderplatz."
> "Craft shop near me, on foot."

## Why

AI assistants and map searches answer "near me" with the first hit or with air distance.
A shop 150 m away across a river, motorway or railway can be a 2 km walk. `near-me`:

- searches places around a start point (address, landmark or `lat,lon`),
- computes the **real route** to every candidate (OSRM walking / driving / cycling profiles,
  or Google Routes incl. public transit),
- drops everything beyond your radius **by route**, sorts by route time,
- prints a Markdown table: route minutes, route metres, air metres, map link.

## Example output

From a shopping mall entrance, on foot, radius 2000 m:

| # | Name | Type | Route time | Route | Air |
|---|---|---|---|---|---|
| 1 | Pepco | clothing_store | 1 min | 57 m | 71 m |
| 2 | Euronics | home_goods_store | 6 min | 439 m | 116 m |
| 3 | Hardware store | building_materials_store | 11 min | 836 m | 722 m |

Note row 2: 116 m in a straight line, 439 m to actually walk there.

## Install

Python 3.10+, no dependencies (standard library only).

```bash
git clone https://github.com/bocimayer/near-me-skill.git
```

**As a Claude Code skill** (Claude picks it up for any "near me / nearest / where to buy" question):

```bash
# macOS / Linux
git clone https://github.com/bocimayer/near-me-skill.git ~/.claude/skills/near-me
# Windows (PowerShell)
git clone https://github.com/bocimayer/near-me-skill.git "$HOME\.claude\skills\near-me"
```

Optional: copy `.env.example` to `.env` (same folder) and set `HOME_ADDRESS`, `COUNTRY`,
`GOOGLE_MAPS_API_KEY`. `.env` is git-ignored.

## Usage

```bash
# free: OpenStreetMap tags + name regex, walking, default radius 2000 m
python near_me.py --from "Alexanderplatz, Berlin" --mode foot --tags "shop=hardware;shop=doityourself"

# by car, 1000 m route radius, pharmacies
python near_me.py --from "52.5219,13.4132" --mode car --radius 1000 --tags "amenity=pharmacy"

# Google Places results you already fetched (e.g. Composio GOOGLE_MAPS_NEARBY_SEARCH), routed free by OSRM
python near_me.py --from "52.5219,13.4132" --mode foot --places-json nearby.json

# all-Google (needs GOOGLE_MAPS_API_KEY in .env; supports --mode transit)
python near_me.py --backend google --query "craft store" --mode transit
```

| Option | Meaning |
|---|---|
| `--from` | `home` (`HOME_ADDRESS` in `.env`), an address, or `lat,lon` |
| `--mode` | `foot`, `car`, `bike`, `transit` (Google only) |
| `--radius` | max **route** distance in metres (default foot 2000 m, car 1000 m, bike 3000 m) |
| `--tags` | OpenStreetMap tags, `;`-separated, e.g. `shop=craft;amenity=pharmacy` |
| `--name` | case-insensitive name regex, e.g. `hobby\|craft` |
| `--places-json` | saved Google Places response; skips search, routes with OSRM |
| `--backend` | `osm` (free, default) or `google` |
| `--country` | ISO code to keep address lookup local, e.g. `hu`, `de`, `us` |
| `--max` | rows to print (default 10) |

## Data sources & cost

- **OpenStreetMap** Nominatim (geocoding) + Overpass (place search, 3 mirrors with retry) +
  FOSSGIS **OSRM** routing — free, please keep usage light and respect their usage policies.
- **Google Maps Platform** Places API (New) + Routes API — optional, billed by Google beyond
  the free monthly allowance.

## Keywords

nearest store near me, closest shop, walking distance, driving distance, route distance vs
straight line, isochrone alternative, local search, store locator, OpenStreetMap, Overpass API,
OSRM, Nominatim, Google Places API, Google Maps, Routes API, distance matrix, Claude Code skill,
Agent Skills, SKILL.md, AI agent tool, LLM tool, MCP, Composio, Python CLI.

## License

MIT
