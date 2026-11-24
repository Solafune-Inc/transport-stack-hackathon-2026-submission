"""Comprehensive EDA of the full Delhi Buses GTFS static feed.

Runs the whole feed (no sampling). Prints a structured report to stdout, writes
figures to notebooks/figures/, and dumps machine-readable results to
reports/eda_full_metrics.json for the HTML report builder.

Data source: Delhi Transport Stack (DoT, GNCTD) — License Agreement v1.0.
"""
from __future__ import annotations
import json, time
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
GTFS = ROOT / "data" / "delhi_buses_static_gtfs"
FIG = ROOT / "notebooks" / "figures"
REP = ROOT / "reports"
FIG.mkdir(parents=True, exist_ok=True); REP.mkdir(exist_ok=True)

M = {}            # metrics collected for JSON/HTML
t0 = time.time()

def h(t): print("\n" + "=" * 72 + f"\n{t}\n" + "=" * 72)
def rec(k, v): M[k] = v; return v

def hms_to_sec(s):
    """GTFS HH:MM:SS -> seconds (supports hours >= 24). Vectorized on a Series."""
    parts = s.str.split(":", expand=True).astype("float")
    return parts[0] * 3600 + parts[1] * 60 + parts[2]

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0088  # km
    p = np.pi / 180
    a = (np.sin((lat2-lat1)*p/2)**2
         + np.cos(lat1*p)*np.cos(lat2*p)*np.sin((lon2-lon1)*p/2)**2)
    return 2 * R * np.arcsin(np.sqrt(a))

# ======================================================================
h("0. LOAD")
routes = pd.read_csv(GTFS/"routes.txt", dtype=str)
stops  = pd.read_csv(GTFS/"stops.txt", dtype=str)
stops["stop_lat"] = pd.to_numeric(stops.stop_lat); stops["stop_lon"] = pd.to_numeric(stops.stop_lon)
trips  = pd.read_csv(GTFS/"trips.txt", dtype=str)
st = pd.read_csv(GTFS/"stop_times.txt", dtype=str)
shapes = pd.read_csv(GTFS/"shapes.txt",
                     dtype={"shape_id":str,"shape_pt_sequence":int},
                     converters={"shape_pt_lat":float,"shape_pt_lon":float,
                                 "shape_dist_traveled":float})
print(f"loaded: routes={len(routes):,} stops={len(stops):,} trips={len(trips):,} "
      f"stop_times={len(st):,} shapes={len(shapes):,}  ({time.time()-t0:.1f}s)")
rec("counts", {"routes":len(routes),"stops":len(stops),"trips":len(trips),
               "stop_times":len(st),"shape_points":len(shapes)})

# numeric prep for stop_times
st["stop_sequence"] = pd.to_numeric(st.stop_sequence)
st["arr_s"] = hms_to_sec(st.arrival_time)
st["dep_s"] = hms_to_sec(st.departure_time)
st["stop_dist"] = pd.to_numeric(st.stop_dist, errors="coerce")
st["fare_stage"] = pd.to_numeric(st.fare_stage, errors="coerce")

# ======================================================================
h("1. ROUTES — agencies & UP/DOWN pairing")
print("agency split:", routes.agency_id.value_counts().to_dict())
def base_dir(name):
    n = str(name).upper().strip()
    if n.endswith("DOWN"): return n[:-4], "DOWN"
    if n.endswith("UP"):   return n[:-2], "UP"
    return n, "?"
bd = routes.route_long_name.map(base_dir)
routes["corridor"] = bd.map(lambda x: x[0]); routes["dir"] = bd.map(lambda x: x[1])
dir_counts = routes["dir"].value_counts().to_dict()
paired = routes.groupby("corridor")["dir"].nunique()
print("direction suffix parse:", dir_counts)
print(f"corridors (base names): {routes.corridor.nunique():,}; "
      f"with both UP & DOWN: {(paired>=2).sum():,}")
rec("routes", {"agency": routes.agency_id.value_counts().to_dict(),
               "dir_suffix": dir_counts, "corridors": int(routes.corridor.nunique()),
               "paired_corridors": int((paired>=2).sum())})

# ======================================================================
h("2. STOPS — hubs, duplicates, coverage")
# routes per stop via stop_times -> trips -> routes
tr2rt = trips.set_index("trip_id").route_id
st_rt = st[["trip_id","stop_id"]].copy()
st_rt["route_id"] = st_rt.trip_id.map(tr2rt)
routes_per_stop = st_rt.groupby("stop_id").route_id.nunique()
trips_per_stop  = st.groupby("stop_id").trip_id.nunique()
hub = (routes_per_stop.rename("routes").to_frame()
       .join(trips_per_stop.rename("trips"))
       .join(stops.set_index("stop_id")[["stop_name"]]))
top_hubs = hub.sort_values("routes", ascending=False).head(12)
print("routes per stop — describe:"); print(routes_per_stop.describe().to_string())
print("\nTop hubs by #routes:")
print(top_hubs.to_string())
# duplicate stops by rounded coords (~11m at 4dp)
dup = stops.assign(k=stops.stop_lat.round(4).astype(str)+","+stops.stop_lon.round(4).astype(str))
dup_groups = dup.groupby("k").size()
print(f"\nstops sharing a 4dp coord cell: {(dup_groups>1).sum()} cells, "
      f"{int(dup_groups[dup_groups>1].sum())} stops involved")
rec("stops", {"routes_per_stop": routes_per_stop.describe().round(2).to_dict(),
              "top_hubs": [{"stop":r.stop_name,"routes":int(r.routes),"trips":int(r.trips)}
                           for r in top_hubs.itertuples()],
              "dup_coord_cells": int((dup_groups>1).sum())})

# ======================================================================
h("3. TRIPS — duration, distance, scheduled speed")
g = st.sort_values(["trip_id","stop_sequence"]).groupby("trip_id")
trip = pd.DataFrame({
    "n_stops": g.size(),
    "start_s": g.dep_s.first(),
    "end_s":   g.arr_s.last(),
    "stopdist_end": g.stop_dist.last(),   # cumulative along-trip distance if present
})
trip["dur_min"] = (trip.end_s - trip.start_s) / 60
trip["start_hour"] = ((trip.start_s // 3600) % 24).astype(int)
# distance from shapes (max shape_dist_traveled per shape, meters -> km)
shape_len = shapes.groupby("shape_id").shape_dist_traveled.max() / 1000.0
trip["route_id"] = trip.index.map(tr2rt)
trip["shape_id"] = trip.index.map(trips.set_index("trip_id").shape_id)
trip["dist_km"] = trip.shape_id.map(shape_len)
trip["speed_kmh"] = trip.dist_km / (trip.dur_min / 60)
valid = trip[(trip.dur_min > 0) & (trip.dist_km > 0) & (trip.speed_kmh < 80)]
print("trip duration (min) — describe:"); print(trip.dur_min.describe().round(1).to_string())
print("\ntrip distance (km, from shapes) — describe:"); print(trip.dist_km.describe().round(1).to_string())
print(f"\nscheduled speed (km/h) — describe (n={len(valid):,} valid):")
print(valid.speed_kmh.describe().round(1).to_string())
print(f"stop_dist column populated on trips: {trip.stopdist_end.notna().mean()*100:.1f}%")
rec("trips", {"dur_min": trip.dur_min.describe().round(1).to_dict(),
              "dist_km": trip.dist_km.describe().round(2).to_dict(),
              "speed_kmh": valid.speed_kmh.describe().round(1).to_dict()})

# ======================================================================
h("4. STOP_TIMES — dwell, inter-stop time & spacing, fare_stage")
sdf = st.sort_values(["trip_id","stop_sequence"]).copy()
sdf["dwell_s"] = sdf.dep_s - sdf.arr_s
# inter-stop hop time (within trip)
sdf["prev_dep"] = sdf.groupby("trip_id").dep_s.shift()
sdf["hop_s"] = sdf.arr_s - sdf.prev_dep
# inter-stop spacing via haversine (join coords)
coords = stops.set_index("stop_id")[["stop_lat","stop_lon"]]
sdf = sdf.join(coords, on="stop_id")
sdf["plat"] = sdf.groupby("trip_id").stop_lat.shift()
sdf["plon"] = sdf.groupby("trip_id").stop_lon.shift()
hop = sdf.dropna(subset=["plat","hop_s"])
hop_km = haversine(hop.stop_lat.values, hop.stop_lon.values, hop.plat.values, hop.plon.values)
print(f"dwell time: {(sdf.dwell_s>0).mean()*100:.2f}% of stop events have dwell>0; "
      f"mean dwell {sdf.dwell_s.mean():.1f}s")
print("inter-stop spacing (km) — describe:")
print(pd.Series(hop_km).describe().round(3).to_string())
print(f"median inter-stop hop time: {np.median(hop.hop_s.values)/60:.1f} min")
# fare_stage: how many stages per trip, does it progress?
fs = st.groupby("trip_id").fare_stage
fs_per_trip = fs.nunique()
print(f"\nfare_stage: {st.fare_stage.notna().mean()*100:.1f}% populated; "
      f"distinct stages/trip median={fs_per_trip.median():.0f}, max={fs_per_trip.max():.0f}")
rec("stop_times", {"dwell_pct_nonzero": round((sdf.dwell_s>0).mean()*100,2),
                   "spacing_km": pd.Series(hop_km).describe().round(3).to_dict(),
                   "median_hop_min": round(float(np.median(hop.hop_s.values))/60,2),
                   "fare_stage_pct": round(st.fare_stage.notna().mean()*100,1),
                   "fare_stages_per_trip_median": float(fs_per_trip.median())})

# ======================================================================
h("5. FREQUENCY — vehicles in service by hour, headways")
# vehicles active per hour (trip span covers the hour)
hours = np.arange(0, 24)
active = [int(((trip.start_s < (hh+1)*3600) & (trip.end_s > hh*3600)).sum()) for hh in hours]
for hh, a in zip(hours, active):
    print(f"  {hh:02d}:00  {a:>6,}  {'#'*int(a/max(active)*40)}")
# AM-peak headway per route (07:00-10:00)
amp = trip[(trip.start_hour>=7)&(trip.start_hour<10)]
def route_headway(s):
    v = np.sort(s.values);  return np.mean(np.diff(v))/60 if len(v)>1 else np.nan
hw = amp.groupby("route_id").start_s.apply(route_headway).dropna()
print(f"\nAM-peak (07-10) mean headway per route (min) — describe (n={len(hw):,}):")
print(hw.describe().round(1).to_string())
rec("frequency", {"active_by_hour": {int(hh):a for hh,a in zip(hours,active)},
                  "am_headway_min": hw.describe().round(1).to_dict()})

# ======================================================================
h("6. SCHEDULED SPEED BY HOUR  (does the schedule bake in congestion?)")
spd_hour = valid.groupby("start_hour").speed_kmh.mean()
for hh in range(24):
    if hh in spd_hour.index:
        v = spd_hour[hh]; print(f"  {hh:02d}:00  {v:5.1f} km/h  {'#'*int(v*2)}")
rec("speed_by_hour", {int(k): round(float(v),1) for k,v in spd_hour.items()})

# ======================================================================
h("7. SHAPES")
pts = shapes.groupby("shape_id").size()
print(f"shapes: {shapes.shape_id.nunique():,}; points/shape median={pts.median():.0f} "
      f"max={pts.max():,}; shape length km median={shape_len.median():.1f} max={shape_len.max():.1f}")
rec("shapes", {"n_shapes": int(shapes.shape_id.nunique()),
               "pts_per_shape_median": int(pts.median()),
               "len_km_median": round(float(shape_len.median()),1)})

# ======================================================================
h("8. FIGURES")
def save(fig, name):
    fig.savefig(FIG/name, dpi=110, bbox_inches="tight"); plt.close(fig)

# spatial density hexbin
fig, ax = plt.subplots(figsize=(7,7))
hb = ax.hexbin(stops.stop_lon, stops.stop_lat, gridsize=45, cmap="viridis", mincnt=1)
fig.colorbar(hb, ax=ax, label="stops"); ax.set_title("Stop density (hexbin)")
ax.set_xlabel("lon"); ax.set_ylabel("lat"); save(fig, "stop_density_hexbin.png")

# vehicles in service by hour
fig, ax = plt.subplots(figsize=(9,4))
ax.fill_between(hours, active, step="mid", alpha=.4); ax.plot(hours, active, marker="o")
ax.set_title("Buses in service by hour of day"); ax.set_xlabel("hour"); ax.set_ylabel("active trips")
save(fig, "vehicles_by_hour.png")

# trip duration & distance
fig, axs = plt.subplots(1,2, figsize=(11,4))
axs[0].hist(trip.dur_min.clip(upper=180), bins=60); axs[0].set_title("Trip duration (min)")
axs[1].hist(trip.dist_km.dropna().clip(upper=60), bins=60); axs[1].set_title("Trip distance (km)")
save(fig, "trip_dur_dist.png")

# scheduled speed distribution + by hour
fig, axs = plt.subplots(1,2, figsize=(11,4))
axs[0].hist(valid.speed_kmh, bins=50); axs[0].set_title("Scheduled speed (km/h)")
axs[1].plot(spd_hour.index, spd_hour.values, marker="o")
axs[1].set_title("Mean scheduled speed by start hour"); axs[1].set_xlabel("hour"); axs[1].set_ylabel("km/h")
save(fig, "speed.png")

# inter-stop spacing + AM headway
fig, axs = plt.subplots(1,2, figsize=(11,4))
axs[0].hist(np.clip(hop_km,0,3), bins=60); axs[0].set_title("Inter-stop spacing (km)")
axs[1].hist(hw.clip(upper=120), bins=50); axs[1].set_title("AM-peak mean headway per route (min)")
save(fig, "spacing_headway.png")

# routes per stop
fig, ax = plt.subplots(figsize=(9,4))
ax.hist(routes_per_stop.values, bins=50); ax.set_yscale("log")
ax.set_title("Routes per stop (log y)"); ax.set_xlabel("# routes serving stop")
save(fig, "routes_per_stop.png")

print(f"  saved 6 figures")

(REP/"eda_full_metrics.json").write_text(json.dumps(M, indent=2, default=str))
print(f"\nwrote reports/eda_full_metrics.json   total {time.time()-t0:.1f}s")
print("DONE.")
