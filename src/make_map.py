"""Interactive spatial-coverage map of the Delhi Buses GTFS feed.

Run:  python src/make_map.py  ->  reports/coverage_map.html
Layers (toggleable):
  - Stop-density heatmap (all 6,812 stops)
  - Top hubs (labeled circle markers, sized by #routes)
  - Route lines (all shapes, decimated; off by default for speed)

Opens over OpenStreetMap tiles (loaded live when viewed in a browser).
Data source: Delhi Transport Stack (DoT, GNCTD) — License Agreement v1.0.
"""
import json
from pathlib import Path
import pandas as pd
import folium
from folium.plugins import HeatMap

ROOT = Path(__file__).resolve().parents[1]
GTFS = ROOT / "data" / "delhi_buses_static_gtfs"
REP = ROOT / "reports"; REP.mkdir(exist_ok=True)

stops = pd.read_csv(GTFS/"stops.txt", dtype=str)
stops["stop_lat"] = pd.to_numeric(stops.stop_lat)
stops["stop_lon"] = pd.to_numeric(stops.stop_lon)
trips = pd.read_csv(GTFS/"trips.txt", dtype=str)
st = pd.read_csv(GTFS/"stop_times.txt", dtype=str, usecols=["trip_id","stop_id"])
shapes = pd.read_csv(GTFS/"shapes.txt",
                     dtype={"shape_id":str},
                     converters={"shape_pt_lat":float,"shape_pt_lon":float,
                                 "shape_pt_sequence":int})

# routes per stop (for hubs)
st["route_id"] = st.trip_id.map(trips.set_index("trip_id").route_id)
rps = st.groupby("stop_id").route_id.nunique()
stops = stops.set_index("stop_id")
stops["routes"] = rps
center = [stops.stop_lat.median(), stops.stop_lon.median()]

m = folium.Map(location=center, zoom_start=11, tiles="OpenStreetMap",
               control_scale=True)

# --- Layer: stop-density heatmap ---
heat = folium.FeatureGroup(name="Stop-density heatmap", show=True)
HeatMap([[r.stop_lat, r.stop_lon] for r in stops.itertuples()],
        radius=9, blur=12, min_opacity=0.25).add_to(heat)
heat.add_to(m)

# --- Layer: all stops (light dots) ---
dots = folium.FeatureGroup(name="All stops (6,812)", show=False)
for r in stops.itertuples():
    folium.CircleMarker([r.stop_lat, r.stop_lon], radius=1.3, weight=0,
                        fill=True, fill_opacity=0.5, fill_color="#3186cc").add_to(dots)
dots.add_to(m)

# --- Layer: top hubs ---
hubs = folium.FeatureGroup(name="Top 20 hubs", show=True)
top = stops.sort_values("routes", ascending=False).head(20)
for r in top.itertuples():
    folium.CircleMarker(
        [r.stop_lat, r.stop_lon],
        radius=5 + r.routes / 15,
        color="#c92a2a", weight=1, fill=True, fill_color="#ff6b6b", fill_opacity=0.8,
        tooltip=f"{r.stop_name} — {int(r.routes)} routes",
    ).add_to(hubs)
hubs.add_to(m)

# --- Layer: route lines (decimated, off by default) ---
lines = folium.FeatureGroup(name="Route lines (decimated)", show=False)
DECIM = 6  # keep every Nth shape point
for sid, g in shapes.sort_values(["shape_id","shape_pt_sequence"]).groupby("shape_id"):
    pts = g[["shape_pt_lat","shape_pt_lon"]].values[::DECIM]
    if len(pts) >= 2:
        folium.PolyLine([(la, lo) for la, lo in pts],
                        color="#1c7ed6", weight=1, opacity=0.15).add_to(lines)
lines.add_to(m)

folium.LayerControl(collapsed=False).add_to(m)

# title + attribution box
title = """
<div style="position:fixed;top:10px;left:50px;z-index:9999;background:rgba(255,255,255,.9);
  padding:8px 12px;border-radius:8px;font:13px/1.4 -apple-system,Arial;color:#222;box-shadow:0 1px 4px rgba(0,0,0,.2)">
  <b>Delhi Bus Network — Spatial Coverage</b><br>
  6,812 stops &middot; 2,554 routes &middot; toggle layers top-right<br>
  <span style="color:#666">Source: Delhi Transport Stack (DoT, GNCTD), License v1.0</span>
</div>"""
m.get_root().html.add_child(folium.Element(title))

out = REP / "coverage_map.html"
m.save(str(out))
print(f"Wrote {out} ({out.stat().st_size/1e6:.1f} MB)")
