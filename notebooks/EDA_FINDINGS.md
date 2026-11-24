# EDA Findings — Delhi Buses GTFS Static (v1)

> Generated 2026-11-11 by `src/eda_gtfs.py`. Figures in `notebooks/figures/`.
> Data source: Delhi Transport Stack (DoT, GNCTD), License Agreement v1.0.

## Feed contents

| File | Records |
|---|---|
| routes.txt | 2,554 |
| stops.txt | 6,812 |
| trips.txt | 65,322 |
| stop_times.txt | 2,385,381 |
| shapes.txt | 765,633 |
| agency / calendar / feed_info | 2 / 1 / 1 |
| **fare_attributes / fare_rules** | **absent** (documented in metadata, not shipped) |

## Highlights

- **Two agencies:** Delhi Transport Corporation (DTC, 1,619 routes) and Department
  of Transport (DOT, 935 routes). All `route_type = 3` (bus).
- **Referential integrity is perfect:** 0 orphan trips, 0 unknown stop/route refs,
  0 unused stops, 0 routes without trips. Clean feed to build on.
- **Geography:** stops span lat 28.21–29.34, lon 76.60–77.43 — a dense Delhi core
  plus a few radial routes into NCR. 40 stops fall outside a tight Delhi bbox
  (legitimate long-distance routes, not errors). No null coordinates.
- **Trips per route:** median 18, mean 26, max 123 (routes usually have an UP and
  DOWN variant, e.g. `102AUP` / `102ADOWN`).
- **Stops per trip:** median 37, mean 36.5, max 183.

## Service-timing profile (key for Problem 2)

Trip starts by hour show the expected **bimodal commuter pattern**:
- Morning peak ~**06:00–09:00** (peak hour 07:00, 4,209 trip starts).
- Afternoon/evening plateau **13:00–16:00** (peak 15:00, 4,236).
- Service runs effectively 24h; **22,719 stop_time rows use ≥24:00** GTFS
  after-midnight encoding (handle with `hour % 24`).

See `figures/trip_starts_by_hour.png`, `figures/stops_map.png`,
`figures/stops_per_trip.png`.

## Implications for the Problem 2 prototype

1. **Schedule is usable for travel-time estimation** — clean stop_times with
   arrival/departure per stop; good base for the journey-planner leg timing.
2. **`direction_id` is 100% blank** — must infer direction from `route_long_name`
   suffix (UP/DOWN) or shape/headsign when pairing directions.
3. **`calendar.txt` = single all-days service** → the feed encodes **no
   weekday/weekend variation**. Crowding time-of-day analysis must come from the
   **ticketing/ETM data**, not the schedule (the schedule gives structure, tickets
   give load).
4. **No fare data** in this drop → fare-based inference not available here.
5. The hour-of-day trip-start curve is a good **sanity baseline** to validate
   crowding estimates against (crowding peaks should broadly track service peaks).
