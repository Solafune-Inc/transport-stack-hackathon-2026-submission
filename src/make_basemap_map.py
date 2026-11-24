"""Spatial-coverage map with a REAL street basemap baked into the image.

Fetches OpenStreetMap tiles ONCE (needs internet when generating) and renders
them into a static PNG. The resulting PNG embeds the basemap, so the HTML report
displays real streets with ZERO external requests at view time — safe for
secured / offline environments.

Run (on a machine with internet):  python src/make_basemap_map.py
Output: notebooks/figures/network_basemap.png  (+ stops_heat_basemap.png)

Basemap © OpenStreetMap contributors (ODbL). Data: Delhi Transport Stack (DoT, GNCTD).
"""
import numpy as np
import pandas as pd
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import contextily as ctx

ROOT = Path(__file__).resolve().parents[1]
GTFS = ROOT / "data" / "delhi_buses_static_gtfs"
FIG = ROOT / "notebooks" / "figures"; FIG.mkdir(parents=True, exist_ok=True)

R = 6378137.0
def to_merc(lon, lat):
    x = R * np.radians(lon)
    y = R * np.log(np.tan(np.pi/4 + np.radians(lat)/2))
    return x, y

# ---- load
stops = pd.read_csv(GTFS/"stops.txt", dtype=str)
stops["stop_lat"] = pd.to_numeric(stops.stop_lat); stops["stop_lon"] = pd.to_numeric(stops.stop_lon)
trips = pd.read_csv(GTFS/"trips.txt", dtype=str)
st = pd.read_csv(GTFS/"stop_times.txt", dtype=str, usecols=["trip_id","stop_id"])
shapes = pd.read_csv(GTFS/"shapes.txt", dtype={"shape_id":str},
                     converters={"shape_pt_lat":float,"shape_pt_lon":float,"shape_pt_sequence":int})
st["route_id"] = st.trip_id.map(trips.set_index("trip_id").route_id)
stops = stops.set_index("stop_id")
stops["routes"] = st.groupby("stop_id").route_id.nunique()
sx, sy = to_merc(stops.stop_lon.values, stops.stop_lat.values)
stops["x"], stops["y"] = sx, sy

# ---- route segments in mercator
segs = []
for _, g in shapes.sort_values(["shape_id","shape_pt_sequence"]).groupby("shape_id"):
    x, y = to_merc(g.shape_pt_lon.values, g.shape_pt_lat.values)
    segs.append(np.column_stack([x, y]))

def frame(ax):
    pad = 0.04
    xmin, xmax = stops.x.min(), stops.x.max(); ymin, ymax = stops.y.min(), stops.y.max()
    dx, dy = (xmax-xmin)*pad, (ymax-ymin)*pad
    ax.set_xlim(xmin-dx, xmax+dx); ax.set_ylim(ymin-dy, ymax+dy)
    ax.set_xticks([]); ax.set_yticks([])

# ---- Map 1: routes + hubs over basemap
fig, ax = plt.subplots(figsize=(10, 11))
ax.add_collection(LineCollection(segs, colors="#1565c0", linewidths=0.4, alpha=0.25))
top = stops.sort_values("routes", ascending=False).head(20)
ax.scatter(top.x, top.y, s=40 + top.routes, c="#c92a2a", edgecolors="white",
           linewidths=.6, zorder=5, label="Top 20 hubs")
labeled = []
for r in top.itertuples():
    if all(abs(r.x-lx) > 3000 or abs(r.y-ly) > 3000 for lx, ly in labeled):
        ax.annotate(f"{r.stop_name} ({int(r.routes)})", (r.x, r.y), fontsize=8,
                    xytext=(6, 6), textcoords="offset points", color="#7a1f1f", zorder=6,
                    bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.75))
        labeled.append((r.x, r.y))
frame(ax)
ctx.add_basemap(ax, source=ctx.providers.Esri.WorldGrayCanvas, crs="EPSG:3857",
                attribution_size=6)
ax.set_title("Delhi bus network over Esri basemap", fontsize=13)
ax.legend(loc="upper right", fontsize=9)
fig.savefig(FIG/"network_basemap.png", dpi=150, bbox_inches="tight"); plt.close(fig)
print("wrote figures/network_basemap.png")

# ---- Map 2: stop-density hexbin over basemap
fig, ax = plt.subplots(figsize=(10, 11))
hb = ax.hexbin(stops.x, stops.y, gridsize=55, cmap="YlOrRd", mincnt=1, alpha=0.75)
fig.colorbar(hb, ax=ax, label="stops", shrink=.6)
frame(ax)
ctx.add_basemap(ax, source=ctx.providers.Esri.WorldGrayCanvas, crs="EPSG:3857",
                attribution_size=6)
ax.set_title("Stop density over Esri basemap", fontsize=13)
fig.savefig(FIG/"stops_heat_basemap.png", dpi=150, bbox_inches="tight"); plt.close(fig)
print("wrote figures/stops_heat_basemap.png")
