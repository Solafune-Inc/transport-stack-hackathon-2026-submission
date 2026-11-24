"""Export the small metadata file the mobile app bundles (mobile-implementation/).

Everything else — stops, routes, crowding, timetable and live buses — comes from the API server
(src/api/main.py), so the app only ships the attribution and the crowding model's assumptions:

  mobile-implementation/assets/data/meta.json   (committed)
    attribution, sources, assumptions (coverage, capacity, days, levels, confidence thresholds,
    day types), changes

Run after src/model/crowding.py (it reads data/eticketing/crowding_model.json for the day types).

Run:
    python src/export_mobile_data.py
Data source: Delhi Transport Stack (DoT, GNCTD) — License Agreement v1.0.
"""
from __future__ import annotations
import datetime as dt
import json
import math
from pathlib import Path

from model.crowding import CAPACITY, COVERAGE, DAYS, LEVELS, MIN_PAX_MONTH, MIN_TRIPS_DAY, OUT_MODEL

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "mobile-implementation" / "assets" / "data" / "meta.json"
ATTRIBUTION = ("Data source: Delhi Transport Stack (Department of Transport, GNCTD). "
               "Used under the Transport Stack data License Agreement v1.0. "
               "Derived and aggregated by the team; see meta.changes.")


DAYTYPE_CHANGE = {
    "b2": "Day types: each route-hour's monthly profile is scaled to weekdays / Saturdays / Sundays+holidays "
          "by the B2 demand model (hierarchical Poisson-Gamma smoothing of boardings per route, stop, hour and "
          "day type; src/ml/demand.py), chosen over gradient boosting on a held-out week (src/ml/compare_models.py).",
    "network": "Day types: each route-hour's monthly profile is scaled by the network's boardings per day in "
               "that hour on weekdays / Saturdays / Sundays+holidays over the monthly average "
               "(src/model/crowding.py --daytype-model network).",
}


def main():
    model = json.loads(OUT_MODEL.read_text())
    meta = {
        "attribution": ATTRIBUTION,
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": {"gtfs": "Delhi Buses GTFS Static v1",
                    "eticketing": "Delhi mobile e-ticketing, October 2026 (1-31)",
                    "live": "Delhi Buses GTFS-RT VehiclePositions feed"},
        "assumptions": {"coverage": COVERAGE, "capacity": CAPACITY, "days": DAYS,
                        "min_trips_day_high_conf": MIN_TRIPS_DAY, "min_pax_month_high_conf": MIN_PAX_MONTH,
                        "day_types": model["days_by_daytype"], "daytype_model": model["daytype_model"],
                        "levels": [[thr if math.isfinite(thr) else None, name] for thr, name in LEVELS]},
        "changes": [
            "Crowding = monthly boardings minus alightings along the GTFS stop order, "
            "scaled by 1/coverage and scheduled trips per hour (src/model/crowding.py).",
            DAYTYPE_CHANGE[model["daytype_model"]],
            f"Low confidence: < {MIN_TRIPS_DAY} scheduled buses/day in the hour or < {MIN_PAX_MONTH} ticketed "
            "passengers in the month for that route-hour.",
            "Stop busyness = tickets boarding/alighting at the stop (all routes) per hour of "
            "ticket purchase, scaled by 1/coverage/days, then by the network day-type factor of that hour. "
            "Alighting hour = purchase hour.",
            "Route shapes simplified (Douglas-Peucker, 4 m, 5 dp) by the API server; vehicle ids "
            "of live buses replaced with hashes.",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(meta, indent=2) + "\n")
    print(f"Wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size} B)")


if __name__ == "__main__":
    main()
