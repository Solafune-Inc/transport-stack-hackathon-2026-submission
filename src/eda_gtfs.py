"""EDA of the Delhi Buses GTFS static feed.

Run:  python src/eda_gtfs.py
Outputs text summary to stdout and a few plots to notebooks/figures/.

Data source: Delhi Transport Stack (DoT, GNCTD) — used under License Agreement v1.0.
"""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
GTFS = ROOT / "data" / "delhi_buses_static_gtfs"
FIG = ROOT / "notebooks" / "figures"
FIG.mkdir(parents=True, exist_ok=True)

def h(title):
    print("\n" + "=" * 70 + f"\n{title}\n" + "=" * 70)

def load(name, **kw):
    return pd.read_csv(GTFS / name, dtype=str, **kw)

# ----------------------------------------------------------------------
h("1. FILE INVENTORY")
for f in sorted(GTFS.glob("*.txt")):
    n = sum(1 for _ in open(f, "rb")) - 1
    print(f"  {f.name:20s} {n:>10,} records   {f.stat().st_size/1e6:7.1f} MB")

# ----------------------------------------------------------------------
h("2. AGENCY / ROUTES / STOPS / TRIPS")
agency = load("agency.txt")
print("Agencies:", agency["agency_name"].tolist())

routes = load("routes.txt")
print(f"\nRoutes: {len(routes):,}")
print("  route_type counts:", routes["route_type"].value_counts().to_dict())
print("  agency_id in routes:", routes["agency_id"].value_counts().to_dict())
print("  sample route_long_name:", routes["route_long_name"].dropna().head(3).tolist())

stops = load("stops.txt")
stops["stop_lat"] = pd.to_numeric(stops["stop_lat"], errors="coerce")
stops["stop_lon"] = pd.to_numeric(stops["stop_lon"], errors="coerce")
print(f"\nStops: {len(stops):,}")
print(f"  lat range: {stops.stop_lat.min():.4f} .. {stops.stop_lat.max():.4f}")
print(f"  lon range: {stops.stop_lon.min():.4f} .. {stops.stop_lon.max():.4f}")
print(f"  null coords: {stops.stop_lat.isna().sum()} lat / {stops.stop_lon.isna().sum()} lon")
# out-of-Delhi sanity (Delhi approx lat 28.3-28.9, lon 76.8-77.4)
oob = stops[(stops.stop_lat < 28.2) | (stops.stop_lat > 29.0) |
            (stops.stop_lon < 76.7) | (stops.stop_lon > 77.6)]
print(f"  stops outside Delhi bbox: {len(oob)}")

trips = load("trips.txt")
print(f"\nTrips: {len(trips):,}")
print(f"  distinct routes with trips: {trips.route_id.nunique():,}")
print(f"  service_id values: {trips.service_id.value_counts().to_dict()}")
dirn = trips.direction_id.fillna("(blank)").value_counts().to_dict()
print(f"  direction_id distribution: {dirn}")
print(f"  shape_id null: {trips.shape_id.isna().sum():,}")
print(f"  trips per route — describe:")
print(trips.groupby("route_id").size().describe().to_string())

# ----------------------------------------------------------------------
h("3. CALENDAR")
cal = load("calendar.txt")
print(cal.to_string(index=False))

# ----------------------------------------------------------------------
h("4. STOP_TIMES  (the big table — Problem 2 relevance: trip timing)")
st = pd.read_csv(GTFS / "stop_times.txt", dtype=str,
                 usecols=["trip_id", "arrival_time", "departure_time",
                          "stop_id", "stop_sequence"])
print(f"stop_times rows: {len(st):,}")
print(f"  distinct trips: {st.trip_id.nunique():,}")
print(f"  distinct stops used: {st.stop_id.nunique():,}")

seqn = st.groupby("trip_id").size()
print(f"\nStops per trip — describe:")
print(seqn.describe().to_string())

# parse hour from departure_time (GTFS allows >24h)
def to_hour(t):
    try:
        return int(str(t).split(":")[0])
    except Exception:
        return np.nan
st["dep_hour"] = st["departure_time"].map(to_hour)
print(f"\n  departure hour range: {st.dep_hour.min():.0f} .. {st.dep_hour.max():.0f}")
print(f"  rows with hour >= 24 (after-midnight encoding): {(st.dep_hour >= 24).sum():,}")

# trip start times -> service profile by hour
first = st.sort_values("stop_sequence").groupby("trip_id").first()
first["start_hour"] = first["departure_time"].map(to_hour) % 24
by_hour = first["start_hour"].value_counts().sort_index()
print("\nTrip starts by hour of day:")
for hr, c in by_hour.items():
    bar = "#" * int(c / max(by_hour) * 40)
    print(f"  {int(hr):02d}:00  {c:>5,}  {bar}")

# ----------------------------------------------------------------------
h("5. CROSS-FILE INTEGRITY CHECKS")
trip_ids_tr = set(trips.trip_id)
trip_ids_st = set(st.trip_id.unique())
print(f"  trips in trips.txt but no stop_times: {len(trip_ids_tr - trip_ids_st):,}")
print(f"  trips in stop_times but not trips.txt: {len(trip_ids_st - trip_ids_tr):,}")
stop_ids = set(stops.stop_id)
st_stops = set(st.stop_id.unique())
print(f"  stop_times referencing unknown stop_id: {len(st_stops - stop_ids):,}")
print(f"  stops never used by any trip: {len(stop_ids - st_stops):,}")
route_ids = set(routes.route_id)
print(f"  trips referencing unknown route_id: {len(set(trips.route_id) - route_ids):,}")
print(f"  routes with zero trips: {len(route_ids - set(trips.route_id)):,}")

# ----------------------------------------------------------------------
h("6. PLOTS")
# stop geography
fig, ax = plt.subplots(figsize=(7, 7))
ax.scatter(stops.stop_lon, stops.stop_lat, s=1, alpha=0.3)
ax.set_title("Delhi bus stops"); ax.set_xlabel("lon"); ax.set_ylabel("lat")
fig.savefig(FIG / "stops_map.png", dpi=110, bbox_inches="tight"); plt.close(fig)

# trip starts by hour
fig, ax = plt.subplots(figsize=(9, 4))
ax.bar(by_hour.index, by_hour.values)
ax.set_title("Bus trip starts by hour of day"); ax.set_xlabel("hour"); ax.set_ylabel("trips")
fig.savefig(FIG / "trip_starts_by_hour.png", dpi=110, bbox_inches="tight"); plt.close(fig)

# stops-per-trip distribution
fig, ax = plt.subplots(figsize=(9, 4))
ax.hist(seqn.values, bins=60)
ax.set_title("Distribution of stops per trip"); ax.set_xlabel("stops in trip"); ax.set_ylabel("trips")
fig.savefig(FIG / "stops_per_trip.png", dpi=110, bbox_inches="tight"); plt.close(fig)

print(f"  saved 3 figures to {FIG.relative_to(ROOT)}/")
print("\nEDA complete.")
