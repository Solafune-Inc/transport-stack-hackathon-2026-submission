"""Fully offline spatial-coverage maps (no external tiles / network).

Draws the network geometry from the GTFS data itself:
  - figures/network_map.png : all 2,554 route shapes + top hubs
  - figures/stop_kde.png     : stop-density heatmap (2D histogram)
Both are self-contained PNGs safe for secured/offline environments.

Run:  python src/make_static_map.py
Data source: Delhi Transport Stack (DoT, GNCTD) — License Agreement v1.0.
"""
import numpy as np
import pandas as pd
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection

ROOT = Path(__file__).resolve().parents[1]
GTFS = ROOT / "data" / "delhi_buses_static_gtfs"
FIG = ROOT / "notebooks" / "figures"; FIG.mkdir(parents=True, exist_ok=True)

stops = pd.read_csv(GTFS/"stops.txt", dtype=str)
stops["stop_lat"] = pd.to_numeric(stops.stop_lat); stops["stop_lon"] = pd.to_numeric(stops.stop_lon)
trips = pd.read_csv(GTFS/"trips.txt", dtype=str)
st = pd.read_csv(GTFS/"stop_times.txt", dtype=str, usecols=["trip_id","stop_id"])
shapes = pd.read_csv(GTFS/"shapes.txt", dtype={"shape_id":str},
                     converters={"shape_pt_lat":float,"shape_pt_lon":float,"shape_pt_sequence":int})

# routes per stop for hubs
st["route_id"] = st.trip_id.map(trips.set_index("trip_id").route_id)
stops = stops.set_index("stop_id")
stops["routes"] = st.groupby("stop_id").route_id.nunique()

# aspect correction for lat/lon (so the city isn't stretched)
lat0 = stops.stop_lat.median()
aspect = 1.0 / np.cos(np.radians(lat0))

# ---------------------------------------------------------------- network map
segs = []
for _, g in shapes.sort_values(["shape_id","shape_pt_sequence"]).groupby("shape_id"):
    pts = g[["shape_pt_lon","shape_pt_lat"]].values
    segs.append(pts)
lc = LineCollection(segs, colors="#1c7ed6", linewidths=0.3, alpha=0.12)

fig, ax = plt.subplots(figsize=(10, 10))
ax.add_collection(lc)
ax.autoscale()
# top hubs
top = stops.sort_values("routes", ascending=False).head(20)
ax.scatter(top.stop_lon, top.stop_lat, s=40 + top.routes, c="#c92a2a",
           edgecolors="white", linewidths=.6, zorder=5, label="Top 20 hubs")
# label only spatially-separated hubs (greedy de-clutter)
labeled = []
for r in top.itertuples():
    if all(abs(r.stop_lat-la) > 0.03 or abs(r.stop_lon-lo) > 0.03 for la, lo in labeled):
        ax.annotate(f"{r.stop_name} ({int(r.routes)})", (r.stop_lon, r.stop_lat),
                    fontsize=7.5, xytext=(5, 5), textcoords="offset points",
                    color="#862e2e", zorder=6,
                    bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.7))
        labeled.append((r.stop_lat, r.stop_lon))
ax.set_aspect(aspect)
ax.set_title("Delhi bus network — all 2,554 route shapes + top hubs", fontsize=13)
ax.set_xlabel("longitude"); ax.set_ylabel("latitude")
ax.legend(loc="upper right", fontsize=9)
fig.savefig(FIG/"network_map.png", dpi=140, bbox_inches="tight"); plt.close(fig)
print("wrote figures/network_map.png")

# ---------------------------------------------------------------- stop density
fig, ax = plt.subplots(figsize=(9, 9))
hb = ax.hist2d(stops.stop_lon, stops.stop_lat, bins=90, cmap="inferno", cmin=1)
fig.colorbar(hb[3], ax=ax, label="stops per cell", shrink=.8)
ax.set_aspect(aspect)
ax.set_title("Stop-density heatmap (2D histogram, offline)", fontsize=13)
ax.set_xlabel("longitude"); ax.set_ylabel("latitude")
fig.savefig(FIG/"stop_kde.png", dpi=140, bbox_inches="tight"); plt.close(fig)
print("wrote figures/stop_kde.png")
