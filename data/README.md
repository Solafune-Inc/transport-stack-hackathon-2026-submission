# Data directory

> **Raw datasets are gitignored** (see root `.gitignore`). Do not commit them.
> Per the Transport Stack License Agreement v1.0, raw data must not be
> redistributed on its own. See [LICENSE-NOTES.md](./LICENSE-NOTES.md).
> Attribution required: **Data source — Delhi Transport Stack (DoT, GNCTD).**

## Datasets present

### `delhi_buses_static_gtfs/` — Delhi Buses GTFS Static (DTC / DoT)
- Source: https://delhi.transportstack.in/data-services/datadetails/1 ("Open" dataset)
- Obtained: 2026-11-11 via the platform data-request form (Non-Commercial Use).
- Zip archived at `delhi_buses_static_gtfs_v1.zip` (~25 MB).
- Feed version `v1`; feed validity 2025-01-01 → 2040-01-01.
- If it unzips under another name (e.g. `delhi_buses_static_gtfs_v1-2/`), add the expected path
  as a symlink: `cd data && ln -s delhi_buses_static_gtfs_v1-2 delhi_buses_static_gtfs`.

| File | Records | Notes |
|---|---|---|
| `agency.txt` | 1 | DTC (Delhi Transport Corporation), Asia/Kolkata |
| `routes.txt` | 2,554 | agency DOT; `route_type=3` (bus); long/short names |
| `stops.txt` | 6,812 | stop_id, stop_code, name, lat, lon |
| `trips.txt` | 65,322 | route_id, service_id, trip_id, shape_id (direction_id often blank) |
| `stop_times.txt` | 2,385,381 | the big one — arrival/departure per stop per trip |
| `shapes.txt` | 765,633 | route geometry (polylines) |
| `calendar.txt` | 1 | single service, all days active (coarse — note for scheduling) |
| `feed_info.txt` | 1 | publisher = DTC |

**Watch-outs for modeling:**
- `direction_id` appears frequently blank in `trips.txt` → may need to infer
  direction from shape/headsign.
- `calendar.txt` has a single all-days service with a very wide date range, so the
  feed does not encode weekday/weekend service variation — relevant for
  time-of-day / day-type crowding analysis (Problem 2).

**⚠️ Data-quality discrepancies (actual feed vs. metadata PDF):**
The metadata PDF (`docs/Delhi_Buses_GTFS_Static_Metadata.pdf`) and the hackathon
listing describe a larger feed than what v1 actually contains:

| | Metadata PDF says | Actual v1 feed |
|---|---|---|
| Stops | 10,559 | 6,812 |
| Routes | 2,403 | 2,554 |
| Trips | 89,393 | 65,322 |

- The metadata also documents **`fare_attributes.txt`** and **`fare_rules.txt`**, but
  **neither file is present** in the downloaded feed → **no fare data** available
  from this GTFS drop (confirm separately if fare info is needed).
- Treat the metadata PDF as a **field/schema reference**, not an accurate inventory.

### Field reference
Per-file field definitions are in `docs/Delhi_Buses_GTFS_Static_Metadata.pdf`
(agency, calendar, fare_attributes, fare_rules, routes, stop_times, stops, trips).
Canonical GTFS spec: https://gtfs.org/documentation/schedule/reference/

### Delhi Buses GTFS-RT feed (real-time vehicle positions) — dataset `datadetails/7`
- **Open** dataset. It's a **live API**, not a file. Docs in `docs/`:
  `Delhi_Buses_GTFS-RT_Metadata.pdf`, `Delhi_Buses_GTFS-RT_Access_Instructions.pdf`
  (+ shared `LicenceAgreement_v1.0.pdf`).
- **Format:** GTFS-Realtime (Protocol Buffers) `FeedMessage` → `VehiclePositions.pb`.
  Fields per entity: vehicle_id, route_id, latitude, longitude, timestamp (+ speed,
  trip_id, start_time/date in practice).
- **Access:** request the dataset → receive an **API URL + `x-api-key`** by email (team access
  approved 2026-11-19, key valid to 2036-11-10). Current endpoint:
  ```
  curl -L 'https://dts-backend.transportstack.in/api/dataset/otd/get-file?agency=delhi-buses&category=realtime_gtfs&filename=VehiclePositions.pb' \
       --header 'x-api-key: <key-from-email>' -o VehiclePositions.pb
  ```
  Put it in the **repo-root `.env`** (gitignored), which `src/api/main.py`, `src/live_server.py`,
  `src/demo_live_map.py` and `src/track_bus.py` read:
  `TRANSPORTSTACK_API_KEY=<key>` and `TRANSPORTSTACK_RT_URL=<endpoint above>`.
  **Not** in `mobile-implementation/.env`: Expo reads that file when bundling the app.
- **Feed as of 2026-11-19:** about 6,100 vehicles by day (DTC + cluster buses), ~2,400–3,200 at
  night. Measured 19–21 Nov: published every 24–33 s (median ~25 s), downloadable 6–10 s after
  the feed's header timestamp; 280–650 KB per fetch with no ETag, Last-Modified or gzip (keep-alive
  works). Moving buses report every ~22–33 s; a report is ~24 s old (median, p90 ~70 s) when it
  first appears. About 1% of devices keep republishing one old report.
- **`../test.txt`** in the repo root is one such `VehiclePositions.pb` snapshot
  (misnamed `.txt`): GTFS-RT v2.0, 2,483 vehicles, 2026-11-13 00:51 UTC. Decode with
  `python src/decode_gtfsrt.py test.txt --csv ...` (needs `gtfs-realtime-bindings`).
- **`vehicle_positions_2026-11-13.csv`** is that snapshot decoded (2,483 buses, 06:07–06:21 IST).
  `route_id` matches GTFS for 96% of buses, but GTFS-RT `trip_id`s don't match GTFS trips, so the
  link is route-level only. It gave the check "timetable has 2,735 trips running at 06:21, live
  feed 2,483 (90.8%)" (the app now uses the live feed instead of this snapshot).
- Relevance: core to **Problem 1** (travel-time). For **Problem 2** it is not the crowding input;
  it places real buses on the map. `src/api/main.py` (the mobile app's server) snaps each bus
  onto its route and attaches the e-ticketing crowding estimate for the stretch it is on.

### `eticketing/October-Delhi.csv` — Delhi mobile e-ticketing (Oct 2026) — **RECEIVED 2026-11-15**
- Source: Delhi Transport Stack (DoT, GNCTD), mobile ticketing — License v1.0.
  Official organizer link (Oct drop):
  `https://pub-091bd9e794bb4877b10b29e6df80f065.r2.dev/2026-10/October-Delhi.csv.zip`
  (download + unzip into `data/eticketing/`). ~290 MB, **2,559,899 tickets** (one row = one ticket).
- **Organizer-stated fact:** mobile ticketing is **~4–5% of total Delhi bus ticket sales**
  (so the file is a ~1-in-20 sample of ridership).
- This is the **Problem-2 crowding core input** (replaces the removed synthetic data).

| Column | Notes |
|---|---|
| `passenger_count` | int (mean 1.08, max 6); 2.75 M total passengers |
| `amount` | fare INR (mean 13.35, median 13.5); total revenue ₹34.2 M |
| `vehicle_number` | e.g. `DL1PD6826`; **48.5% NULL**; 6,809 distinct; **90% overlap with GTFS-RT vehicle ids** |
| `ticket_type_id` | all `1` in this drop (single type) |
| `start_stop_name` / `end_stop_name` | **boarding AND alighting both observed** — no alighting estimation needed. Only ~48% exact-match GTFS stop_name → resolved to GTFS stops (see below) |
| `route` | e.g. `8UP` / `433DOWN`; **99.9% match GTFS `route_short_name` (100% of tickets)** |
| `created_at` | timestamp `+05:30` IST; full Oct 1–31; peaks **08–09** and **18–19** (bimodal commute) |
| `is_ac` | ~80% AC |

- **EDA:** `python src/eda_eticketing.py` → `notebooks/figures/etk_*.png` +
  `reports/eda_eticketing_metrics.json`.

### `eticketing/stop_resolution.csv` — e-ticketing stop names → GTFS stops (derived)
- Built by `python src/resolve_stops.py` from the two datasets above (gitignored).
- Maps each `(route, stop_name)` → GTFS `stop_id` + `lat`/`lon`, with `method` + `score`.
- **Method:** route-scoped name matching (match only against stops the GTFS route serves),
  with a global fallback. Scoring uses **distinctive tokens only** (ignores generic words
  like *metro/station/road* so two different "X Metro Station" stops don't match), plus
  containment (GTFS supersets like *Mahipal Pur → Mahipal Pur Extension*) and a
  spaceless ratio (split/joined spellings like *Azad Pur ↔ Azadpur*).
- **Coverage: 97.9% of distinct (route,stop) pairs, 97.9% ticket-weighted.**
  Breakdown: exact-route 66%, fuzzy-route 28%, global 4%, unresolved ~2%.
  Generic structural + facility + housing-scheme words (metro/station/road, hospital/
  school/market, DDA/LIG/flats/industrial, ...) are excluded from the match signal so a
  shared type word can't match two different localities ('Jhil Mil DDA Flats' stays
  unresolved rather than mapping to 'Tahir Pur DDA Flats').
  Unresolved are mostly ambiguous abbreviations (e.g. *S.J.* = Safdarjung?) and stops
  possibly absent from GTFS — left unmatched by design (a wrong stop is worse than none).
- Summary metrics: `reports/stop_resolution_metrics.json`.

### `eticketing/crowding_segments.csv` + `crowding_route_hour.csv` — crowding model (derived)
- Built by `python src/model/crowding.py` from e-ticketing + stop_resolution + GTFS (gitignored).
- `crowding_segments.csv`: `(route, hour, pos, stop_id)` → `load_sampled`, `per_vehicle_load`,
  `occupancy`, `level`, `trips_day`, `confidence`. `crowding_route_hour.csv`: per `(route,hour)`
  peak occupancy + level + confidence.
- **Method:** `load = Σboardings − Σalightings` along the GTFS stop sequence (both observed →
  no alighting estimation), then `per_vehicle_load = load / COVERAGE(4.5%) / trips_month`,
  `occupancy = load/CAPACITY(60)`. Levels: Low/Medium/High/Very High.
- **Validation:** peak occupancy bimodal (08–09, 18–19), load returns to ~0 at terminus
  (alight/board = 1.0), 98.7% forward-consistent. Report: `reports/crowding_report.html`.
- Query: `python src/query_crowding.py --route 623DOWN --hour 18`.

- `src/model/crowding.py` also writes **`crowding_stop_hour.csv`** (gitignored): estimated people
  boarding / alighting per day at each stop and hour, all routes (tickets × 1/COVERAGE / 31 days;
  alightings counted in the purchase hour). The app's stop sheet uses it.
- **Day types (2026-11-23):** `crowding_{segments,route_hour,stop_hour}_daytype.csv` hold the same
  tables per `daytype` (weekday / saturday / sunday_holiday), scaled by the B2 demand model
  (`--daytype-model network` for the simpler fallback); `crowding_model.json` records which. These
  are what the API serves. A route-hour is low-confidence with < 2 scheduled buses/day or < 30
  ticketed passengers in the month.
- **`crowding_operator.csv`** (gitignored): weekday route-hours over capacity on their busiest
  stretch (high confidence), ranked by riders above capacity per day, with how full that stretch
  would be with one more bus and the Saturday / Sunday values. Shown in the crowding report's
  "For operators" section.

### Mobile app data — `mobile-implementation/assets/data/meta.json` + the server
- The app bundles only `meta.json` (attribution, sources, crowding assumptions, list of changes),
  written by `python src/export_mobile_data.py`. **Committed**; no data rows.
- Everything else comes from the server (`python src/api/main.py`), which reads the GTFS, the
  crowding outputs above and the live feed, and sends only derived data: simplified shapes,
  crowding estimates, stop busyness, timetable lookups and hashed live positions
  (License v1.0 rule 2, `LICENSE-NOTES.md`). The earlier 2-route `demo_routes.json` bundle is gone.

## Still needed (requested separately)
- **ETM data** (higher-coverage ticketing source) — the mobile e-ticketing above covers
  only ~4–5%; ETM would anchor crowding estimates to fuller ridership. Not yet received.
- **Scope & datasets — confirmed by organizer (2026-11-12):**
  - Minimum scope is **buses**; a **multimodal (bus + metro) view is encouraged** (bonus).
  - **No other immediately relevant datasets** beyond: bus GTFS (have), e-ticketing/ETM
    (awaiting), metro **hourly footfall** `datadetails/4`, metro **yearly OD** `datadetails/9`.
  - Plan: **bus-only crowding MVP**, then metro crowding layer as a stretch.
  - **Metro datasets requested 2026-11-12** (Non-Commercial, License v1.0):
    footfall `datadetails/4` and yearly OD `datadetails/9` — both **Request-in-progress
    (awaiting approval)**. Download once approved and place under `data/`.

## How to re-fetch
Sign in at https://delhi.transportstack.in → Data & Services → open the dataset →
Download → complete the request form (accept License Agreement) → Download Now.
