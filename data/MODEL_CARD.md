# Model card: Delhi bus crowding tables

**Version:** `crowding-b2-2026-11-23` (generated 2026-11-23T08:45:15Z, see `eticketing/crowding_model.json`)
**Made by:** the team, with `src/resolve_stops.py` and `src/model/crowding.py --daytype-model b2`
**Data source:** Delhi Transport Stack (Department of Transport, GNCTD), used under the Transport Stack
data License Agreement v1.0, for non-commercial use.

These three tables are the "model weights" the API server loads. They are **derived, aggregated
works**, not the raw datasets. No ticket rows, vehicle numbers or GTFS files are included.

## Files

They are stored gzipped. The API image unpacks them at build time. To run the server without Docker,
first run `gunzip -k data/eticketing/*.csv.gz`.

| File | Rows | One row is | Columns |
|---|---:|---|---|
| `crowding_segments_daytype.csv.gz` | 2,079,660 | one stop-to-stop stretch of a route, in one hour and day type | `route, daytype, hour, pos, stop_id, per_vehicle_load, occupancy, level` |
| `crowding_route_hour_daytype.csv.gz` | 62,217 | one route in one hour and day type (its busiest stretch) | `route, daytype, hour, peak_occupancy, peak_per_vehicle_load, trips_day, pax_month, n_segments, level, confidence` |
| `crowding_stop_hour_daytype.csv.gz` | 257,355 | one stop in one hour and day type (all routes) | `stop_id, daytype, hour, boardings, alightings` |
| `crowding_operator.csv.gz` | 1,129 | one weekday route-hour over capacity on its busiest stretch (high confidence only), ranked by riders above capacity per day. For operators; the API doesn't read it | `route, hour, buses_per_day, peak_occupancy, peak_per_vehicle_load, riders_over_capacity_per_day, occupancy_with_one_more_bus, saturday_occupancy, sunday_holiday_occupancy` |
| `crowding_model.json` | | | day-type model name, days per day type, B2 parameters, confidence thresholds |

The day types are `weekday` (20 days in October), `saturday` (5) and `sunday_holiday` (6).
`route` and `stop_id` are Delhi Buses GTFS Static v1 ids.

## How they are made

1. **Inputs:** Delhi mobile e-ticketing for 1–31 October 2026 (2,559,899 tickets, each with a boarding and
   an alighting stop) and Delhi Buses GTFS Static v1.
2. **Stops:** ticket stop names are matched to GTFS stops served by the ticket's route. This resolves
   97.9% of tickets; see `reports/stop_resolution_report.html`.
3. **Load:** on each route, the load on a stretch is boardings minus alightings along the GTFS stop order
   (89.1% of tickets are usable).
4. **Per bus:** the load is scaled by 1 / coverage and by the buses scheduled in that hour. That gives
   `per_vehicle_load`, and `occupancy` = load / capacity.
5. **Day types:** each route-hour's monthly profile is scaled to weekdays, Saturdays and Sundays/holidays
   by the B2 demand model. B2 is hierarchical Poisson–Gamma smoothing of boardings per route, stop,
   hour and day type (`src/ml/demand.py`). It was chosen over gradient boosting on the held-out week
   of 25–31 October (`reports/ml_model_comparison.json`).
6. **Levels:** occupancy below 0.5 is Low, below 0.8 Medium, below 1.0 High, otherwise Very High.

## Assumptions and limits

- **Coverage:** mobile tickets are assumed to be about 4.5% of all tickets. Absolute rider counts carry
  this assumption, so rely on the order (which stretch, hour or route is busier) more than the counts.
- **Capacity:** 60 riders per bus (about 35 seated and 25 standing).
- **Confidence:** a route-hour is `low` confidence with fewer than 2 scheduled buses a day in that hour,
  or fewer than 30 ticketed passengers in the month. The app shows this.
- **Alighting time:** alightings are counted in the hour the ticket was bought.
- **Schedule:** the GTFS schedule is the same every day, so the day-type differences come only from the
  ticket data.

## Validation

- `reports/crowding_report.html` and `reports/crowding_metrics.json` hold the hourly validation and
  confidence breakdown.
- `reports/ml_model_comparison.json` and `docs/ML_PLAN.md` (§1b) hold the demand-model test on the
  held-out week.

## Changes from the source data (licence: integrity clause)

The raw tickets were aggregated to route, stretch, stop, hour and day type. Ticket stop names were
replaced by GTFS stop ids. Counts were scaled by the coverage and schedule assumptions above, and
smoothed by the B2 model. No individual ticket, timestamp or vehicle number survives aggregation.
