---
name: near-me
description: Use for ANY "near me / nearest / closest / where can I buy / find a shop near X / within walking distance / within N km by car" request for a physical shop, store, pharmacy, service or place. Ranks places by REAL walking, driving or cycling route time and route distance from the user's position (never straight-line air distance or guesswork), then online shops in the user's country, foreign shops only on request.
---

# near-me: find the nearest shop by real route, not by air distance

Never call a place "near" or "nearest" unless `near_me.py` measured its route.
A shop 100 m away across a river, motorway or railway can be 2 km on foot.

## 1. Read the request

- **Start point**: "I am at X" -> `--from "X"` (address or `lat,lon`). Otherwise `--from home`
  (`HOME_ADDRESS` in `.env` next to the script; never print or repeat the address).
- **Mode**: "on foot / walking" -> `foot`, "by car / driving" -> `car`, "bike" -> `bike`,
  "public transport" -> `transit` (Google backend only). Not stated: `foot`.
- **Radius**: a number the user gives = maximum ROUTE distance in metres. Not stated:
  foot 2000 m, car 1000 m, bike 3000 m.
- **Country**: `--country hu` (ISO code) or `COUNTRY=` in `.env` keeps address lookup local.
- Search terms in the local language (Hungarian shop names for Hungary, German for Germany...).

## 2. Physical shops: run the tool

```
python near_me.py --from home --mode foot --tags "shop=craft;shop=art" --name "hobby|craft"
```

- Default backend `osm` is free and needs no key: Nominatim geocoding, Overpass place search,
  OSRM routing (routing.openstreetmap.de). Map the product to OpenStreetMap tags and add a
  name regex for badly tagged shops. Useful tags: `shop=craft`, `shop=art`, `shop=hardware`,
  `shop=doityourself`, `shop=garden_centre`, `shop=chemist`, `amenity=pharmacy`,
  `shop=stationery`, `shop=model`, `shop=electronics`, `shop=mall`.
- For a shopping mall, also check the mall's own store list on its website.
- **If Overpass is down** (502/504/timeouts; the script retries 3 mirrors with backoff) or
  coverage is thin, use Google Places for the search and keep OSRM for the routes:
  1. Get places from Google Places **Nearby Search** (preferred) or Text Search: through the
     Composio `google_maps` toolkit (`GOOGLE_MAPS_NEARBY_SEARCH`) or any Places API client.
     Nearby Search: `latitude`, `longitude`, `radius` (car: at least 2000 so routes can be
     compared), `maxResultCount` 20, `fieldMask`
     `displayName,formattedAddress,location,googleMapsUri,businessStatus,primaryType`,
     `includedTypes` from Google's Table A only: e.g. `hardware_store`,
     `home_improvement_store`, `home_goods_store`, `department_store`, `shopping_mall`,
     `gift_shop`, `book_store`, `pharmacy`, `electronics_store`, `garden_center`.
     `arts_and_crafts_store` and `food` are NOT valid filters (the whole call fails).
  2. Save the raw JSON response (one response, or several in a list) to a file.
  3. Route with free OSRM, one run per mode:
     `python near_me.py --from "LAT,LON" --mode foot --places-json nearby.json`
     It keeps OPERATIONAL places, drops duplicates, routes, cuts at the radius, prints the table.
- `--backend google --query "..."` does search and routing in one go with your own
  `GOOGLE_MAPS_API_KEY` in `.env` (Places Text Search + Routes API; needed for transit).
- Google Places and Routes calls can cost money beyond Google's free monthly allowance.
  Ask the user before running them.
- Report the tool's table as it is. Every number carries its unit. If nothing is inside the
  radius, say so and ask before widening it.
- Car caveat: OSRM snaps a shop inside a mall to the nearest road, so mall shops can show long
  car routes; use the mall entrance row for them.
- Stock: a shop type is not proof that the item is in stock. Say "call to check" unless the
  shop's own website shows the item.

## 3. Online shops (after local)

- Search in the local language and restrict to the country's domain (e.g. `site:.hu`).
  Keep shops that ship domestically with local-currency prices.
- Table: shop, product, pack size, price with currency, URL.
- Show foreign shops only if the user asks, or the local and domestic searches came back empty.
  Label them "FOREIGN" and say why they are shown.

## 4. Never

- Never use straight-line (air) distance or district guesses to rank places.
- Never present the first search hit as "nearest".
- Never use a foreign shop when a domestic search was asked for.
