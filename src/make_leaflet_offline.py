"""Self-contained INTERACTIVE Leaflet map (works fully offline).

Downloads (once, at build time, needs internet):
  - Leaflet + leaflet.heat library
  - Esri World_Light_Gray_Base tiles for the Delhi bbox, zoom 10-13
...and embeds ALL of them as data-URIs / inline scripts into a single HTML file.
When viewed it makes ZERO external requests, so it pans/zooms on a secured/offline
network.

Run (on a machine with internet):  python src/make_leaflet_offline.py
Output: reports/coverage_map_offline.html

Basemap tiles (C) Esri. Transit data: Delhi Transport Stack (DoT, GNCTD), License v1.0.
"""
import base64, json, math, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import urllib.request
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
GTFS = ROOT / "data" / "delhi_buses_static_gtfs"
REP = ROOT / "reports"; REP.mkdir(exist_ok=True)
CACHE = ROOT / ".tilecache"; CACHE.mkdir(exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (hackathon EDA map builder)"}
ZMIN = 10
TILE_TMPL = ("https://server.arcgisonline.com/ArcGIS/rest/services/"
             "{variant}/MapServer/tile/{z}/{y}/{x}")
# selectable basemaps (base layers). Default (first) goes deeper in zoom; the
# alternates stop at 13 to keep the embedded file size manageable.
BASEMAPS = [
    {"key":"gray",    "name":"Esri Light Gray", "variant":"Canvas/World_Light_Gray_Base", "zmax":14, "mime":"image/png"},
    {"key":"streets", "name":"Esri Streets",    "variant":"World_Street_Map",              "zmax":13, "mime":"image/png"},
    {"key":"imagery", "name":"Esri Satellite",  "variant":"World_Imagery",                 "zmax":13, "mime":"image/jpeg"},
    {"key":"dark",    "name":"Esri Dark Gray",  "variant":"Canvas/World_Dark_Gray_Base",   "zmax":13, "mime":"image/png"},
]
ZMAX = max(b["zmax"] for b in BASEMAPS)
LEAFLET_CSS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
LEAFLET_JS  = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
HEAT_JS     = "https://unpkg.com/leaflet.heat@0.2.0/dist/leaflet-heat.js"

def fetch(url, binary=False, retries=4):
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
            if not data:
                raise ValueError("empty response")
            return data if binary else data.decode("utf-8")
        except Exception as e:
            last = e
            time.sleep(0.5 * (attempt + 1))
    raise last

def deg2num(lat, lon, z):
    n = 2 ** z
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)
    return x, y

# ---- data
stops = pd.read_csv(GTFS/"stops.txt", dtype=str)
stops["stop_lat"] = pd.to_numeric(stops.stop_lat); stops["stop_lon"] = pd.to_numeric(stops.stop_lon)
trips = pd.read_csv(GTFS/"trips.txt", dtype=str)
routes = pd.read_csv(GTFS/"routes.txt", dtype=str)
st = pd.read_csv(GTFS/"stop_times.txt", dtype=str,
                 usecols=["trip_id","stop_id","stop_sequence","arrival_time"])
st["stop_sequence"] = pd.to_numeric(st.stop_sequence)
trip2route = trips.set_index("trip_id").route_id
st["route_id"] = st.trip_id.map(trip2route)
rps = st.groupby("stop_id").route_id.nunique()        # routes per stop
tps = st.groupby("stop_id").trip_id.nunique()          # trips per stop (service intensity)
shapes = pd.read_csv(GTFS/"shapes.txt", dtype={"shape_id":str},
                     converters={"shape_pt_lat":float,"shape_pt_lon":float,"shape_pt_sequence":int})

# agency per shape (via trips -> routes)
route2agency = routes.set_index("route_id").agency_id
shape2agency = (trips.dropna(subset=["shape_id"])
                .assign(agency=lambda d: d.route_id.map(route2agency))
                .groupby("shape_id").agency.first())

# trip terminals: first & last stop of every trip
gseq = st.sort_values(["trip_id","stop_sequence"]).groupby("trip_id")
term_ids = set(gseq.stop_id.first()) | set(gseq.stop_id.last())

# late-night-service stops: any stop event between 00:00 and 04:59
# (GTFS encodes after-midnight trips as 24-28h, so take hour % 24)
hr = st.arrival_time.str.slice(0,2).astype(float) % 24
night_ids = set(st.loc[hr < 5, "stop_id"].unique())

minlat, maxlat = stops.stop_lat.min()-0.03, stops.stop_lat.max()+0.03
minlon, maxlon = stops.stop_lon.min()-0.03, stops.stop_lon.max()+0.03
center = [float(stops.stop_lat.median()), float(stops.stop_lon.median())]

def get_tile(job):
    bm, z, x, y = job
    cdir = CACHE / bm["key"]; cdir.mkdir(exist_ok=True)
    cf = cdir / f"{z}_{x}_{y}.img"
    try:
        if cf.exists():
            raw = cf.read_bytes()
        else:
            raw = fetch(TILE_TMPL.format(variant=bm["variant"], z=z, x=x, y=y), binary=True)
            cf.write_bytes(raw)
        uri = f"data:{bm['mime']};base64," + base64.b64encode(raw).decode()
        return bm["key"], f"{z}/{x}/{y}", uri
    except Exception:
        return None

# ---- enumerate tiles for every basemap x bbox x zoom level
jobs = []
for bm in BASEMAPS:
    for z in range(ZMIN, bm["zmax"]+1):
        x0, y0 = deg2num(maxlat, minlon, z)
        x1, y1 = deg2num(minlat, maxlon, z)
        for x in range(min(x0,x1), max(x0,x1)+1):
            for y in range(min(y0,y1), max(y0,y1)+1):
                jobs.append((bm, z, x, y))
print(f"downloading {len(jobs)} tiles across {len(BASEMAPS)} basemaps (parallel)...", flush=True)

t0 = time.time()
tilesets = {b["key"]: {} for b in BASEMAPS}
with ThreadPoolExecutor(max_workers=16) as ex:
    for res in ex.map(get_tile, jobs):
        if res:
            key, zxy, uri = res
            tilesets[key][zxy] = uri
for b in BASEMAPS:
    print(f"  {b['name']}: {len(tilesets[b['key']])} tiles")
n_ok = sum(len(v) for v in tilesets.values())
print(f"embedded {n_ok}/{len(jobs)} tiles ({time.time()-t0:.0f}s)", flush=True)

# ---- libraries (inline)
print("downloading leaflet...")
css = fetch(LEAFLET_CSS); ljs = fetch(LEAFLET_JS); hjs = fetch(HEAT_JS)

# ---- data layers as JSON
heat_pts = [[round(r.stop_lat,5), round(r.stop_lon,5)] for r in stops.itertuples()]
stops["routes"] = stops.stop_id.map(rps).fillna(0).astype(int)
stops["trips"] = stops.stop_id.map(tps).fillna(0).astype(int)
# all stops with names + connectivity (for labels + graduated layer)
allstops = [{"lat":round(r.stop_lat,5),"lon":round(r.stop_lon,5),
             "name":str(r.stop_name),"routes":int(r.routes),"trips":int(r.trips)}
            for r in stops.itertuples()]
# service-intensity weighted heat (weight = trips/stop, normalized)
tmax = max(stops.trips.max(), 1)
heat_svc = [[round(r.stop_lat,5), round(r.stop_lon,5), round(r.trips/tmax,3)]
            for r in stops.itertuples() if r.trips > 0]
# terminals & night stops
scoord = stops.set_index("stop_id")
terminals = [{"lat":round(scoord.at[i,"stop_lat"],5),"lon":round(scoord.at[i,"stop_lon"],5),
              "name":str(scoord.at[i,"stop_name"])} for i in term_ids if i in scoord.index]
nightstops = [{"lat":round(scoord.at[i,"stop_lat"],5),"lon":round(scoord.at[i,"stop_lon"],5),
               "name":str(scoord.at[i,"stop_name"])} for i in night_ids if i in scoord.index]
print(f"terminals={len(terminals)} night_stops={len(nightstops)}")
top = stops.sort_values("routes", ascending=False).head(25)
hubs = [{"lat":round(r.stop_lat,5),"lon":round(r.stop_lon,5),
         "name":r.stop_name,"routes":int(r.routes)} for r in top.itertuples()]
# decimated route polylines, split by agency
routes_geo = []; routes_dtc = []; routes_dot = []
for sid, g in shapes.sort_values(["shape_id","shape_pt_sequence"]).groupby("shape_id"):
    pts = g[["shape_pt_lat","shape_pt_lon"]].values[::6]
    if len(pts) < 2:
        continue
    line = [[round(float(a),5), round(float(b),5)] for a,b in pts]
    routes_geo.append(line)
    ag = shape2agency.get(sid, "")
    if ag == "DTC":
        routes_dtc.append(line)
    elif ag == "DOT":
        routes_dot.append(line)
print(f"routes split: DTC={len(routes_dtc)} DoT={len(routes_dot)} total={len(routes_geo)}")

HTML = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Delhi Bus Network — Interactive Coverage (offline)</title>
<style>{css}
html,body,#map{{height:100%;margin:0}}
.info{{position:absolute;top:10px;left:50px;z-index:1000;background:rgba(255,255,255,.92);
  padding:8px 12px;border-radius:8px;font:13px/1.4 -apple-system,Arial;color:#222;
  box-shadow:0 1px 4px rgba(0,0,0,.25);max-width:320px}}
.leaflet-control-layers{{font:13px -apple-system,Arial}}
.stoplbl{{background:rgba(255,255,255,.82);border:none;box-shadow:none;
  font:10px/1.1 -apple-system,Arial;color:#333;padding:0 2px}}
.stoplbl::before{{display:none}}
</style></head><body>
<div id="map"></div>
<div class="info"><b>Delhi Bus Network — Spatial Coverage</b><br>
6,812 stops &middot; 2,554 routes &middot; interactive, fully offline<br>
<span style="color:#444">Hover any stop for its name; zoom in (&ge;14) for auto labels.</span><br>
<span style="color:#666">Tiles &copy; Esri &middot; Data: Delhi Transport Stack (DoT, GNCTD)</span></div>
<script>{ljs}</script>
<script>{hjs}</script>
<script>
const TILESETS = {json.dumps(tilesets)};
const BASEMAPS = {json.dumps([{k: b[k] for k in ('key','name','zmax')} for b in BASEMAPS])};
const HEAT = {json.dumps(heat_pts)};
const HEAT_SVC = {json.dumps(heat_svc)};
const HUBS = {json.dumps(hubs)};
const ROUTES = {json.dumps(routes_geo)};
const ROUTES_DTC = {json.dumps(routes_dtc)};
const ROUTES_DOT = {json.dumps(routes_dot)};
const ALLSTOPS = {json.dumps(allstops)};
const TERMINALS = {json.dumps(terminals)};
const NIGHTSTOPS = {json.dumps(nightstops)};

const BLANK = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAAMBAQDJ/pLvAAAAAElFTkSuQmCC";
const OfflineTiles = L.TileLayer.extend({{
  initialize: function(setKey, opts) {{ this._set = TILESETS[setKey]; L.setOptions(this, opts); }},
  getTileUrl: function(c) {{ return this._set[c.z + "/" + c.x + "/" + c.y] || BLANK; }}
}});

const map = L.map("map", {{minZoom:{ZMIN}, maxZoom:{ZMAX}, preferCanvas:true}}).setView({json.dumps(center)}, 11);
map.setMaxBounds([[{minlat},{minlon}],[{maxlat},{maxlon}]]);

const baseLayers = {{}};
BASEMAPS.forEach((b, i) => {{
  const layer = new OfflineTiles(b.key, {{minZoom:{ZMIN}, maxZoom:b.zmax,
    maxNativeZoom:b.zmax, attribution:"Tiles &copy; Esri | Data: Delhi Transport Stack"}});
  baseLayers[b.name] = layer;
  if (i === 0) layer.addTo(map);
}});

const heat = L.heatLayer(HEAT, {{radius:10, blur:14, minOpacity:0.25}});
heat.addTo(map);

const hubLayer = L.layerGroup();
HUBS.forEach(h => {{
  L.circleMarker([h.lat,h.lon], {{radius:4+h.routes/15, color:"#c92a2a",
    weight:1, fillColor:"#ff6b6b", fillOpacity:0.85}})
   .bindTooltip(h.name+" — "+h.routes+" routes").addTo(hubLayer);
}});
hubLayer.addTo(map);

const routeLayer = L.layerGroup();
ROUTES.forEach(line => L.polyline(line, {{color:"#1c7ed6", weight:1, opacity:0.18}}).addTo(routeLayer));

// routes split by agency
const dtcLayer = L.layerGroup();
ROUTES_DTC.forEach(line => L.polyline(line, {{color:"#e8590c", weight:1, opacity:0.2}}).addTo(dtcLayer));
const dotLayerRoutes = L.layerGroup();
ROUTES_DOT.forEach(line => L.polyline(line, {{color:"#1971c2", weight:1, opacity:0.2}}).addTo(dotLayerRoutes));

// service-intensity heat (weighted by trips/stop)
const svcHeat = L.heatLayer(HEAT_SVC, {{radius:11, blur:15, minOpacity:0.2,
  gradient:{{0.2:"#2b8a3e",0.5:"#f59f00",0.8:"#e03131"}}}});

// trip terminals (route endpoints)
const termLayer = L.layerGroup();
TERMINALS.forEach(t => L.circleMarker([t.lat,t.lon], {{radius:3, weight:1,
  color:"#7048e8", fillColor:"#b197fc", fillOpacity:0.8}})
  .bindTooltip("Terminal: "+t.name).addTo(termLayer));

// night-service stops
const nightLayer = L.layerGroup();
NIGHTSTOPS.forEach(t => L.circleMarker([t.lat,t.lon], {{radius:3, weight:0,
  fillColor:"#111", fillOpacity:0.7}})
  .bindTooltip("Night service: "+t.name).addTo(nightLayer));

// stop connectivity — graduated circles by #routes
function connColor(n){{ return n>=50?"#800026":n>=25?"#e03131":n>=12?"#f59f00":
  n>=5?"#66a61e":"#4c9be8"; }}
const connLayer = L.layerGroup();
ALLSTOPS.forEach(s => L.circleMarker([s.lat,s.lon], {{radius:1.5+Math.sqrt(s.routes),
  weight:0, fillColor:connColor(s.routes), fillOpacity:0.75}})
  .bindTooltip(s.name+" — "+s.routes+" routes, "+s.trips+" trips/day").addTo(connLayer));

// all stops, each with a hover tooltip (name). Permanent labels appear at high zoom.
const stopLayer = L.layerGroup();
const stopMarkers = [];
ALLSTOPS.forEach(s => {{
  const mk = L.circleMarker([s.lat, s.lon], {{radius:2, weight:0,
    fillColor:"#3186cc", fillOpacity:0.6}});
  mk._nm = s.name;
  mk.bindTooltip(s.name, {{direction:"right", className:"stoplbl", opacity:0.95}});
  mk.addTo(stopLayer); stopMarkers.push(mk);
}});
stopLayer.addTo(map);

// show permanent name labels for in-view stops once zoomed in (>= 14)
const LABEL_ZOOM = 14, LABEL_CAP = 400;
let labelsOn = false;
function updateLabels() {{
  const show = map.hasLayer(stopLayer) && map.getZoom() >= LABEL_ZOOM;
  const b = map.getBounds();
  if (!show) {{
    if (labelsOn) {{ stopMarkers.forEach(m => m.closeTooltip()); labelsOn = false; }}
    return;
  }}
  labelsOn = true;
  let n = 0;
  stopMarkers.forEach(m => {{
    if (n < LABEL_CAP && b.contains(m.getLatLng())) {{
      const t = m.getTooltip();
      if (!t.options.permanent) {{ t.options.permanent = true; m.openTooltip(); }}
      n++;
    }} else {{
      const t = m.getTooltip();
      if (t.options.permanent) {{ t.options.permanent = false; m.closeTooltip(); }}
    }}
  }});
}}
map.on("zoomend moveend", updateLabels);
updateLabels();

L.control.layers(baseLayers, {{
  "Stop-density heatmap": heat,
  "Service intensity (trips/stop) heat": svcHeat,
  "Stop connectivity (by #routes)": connLayer,
  "Top 25 hubs": hubLayer,
  "Trip terminals": termLayer,
  "Late-night stops (00:00–04:59)": nightLayer,
  "Route lines — all": routeLayer,
  "Route lines — DTC": dtcLayer,
  "Route lines — DoT": dotLayerRoutes,
  "All stops + names": stopLayer
}}, {{collapsed:false}}).addTo(map);

// legend for connectivity
const legend = L.control({{position:"bottomright"}});
legend.onAdd = function() {{
  const d = L.DomUtil.create("div", "info");
  d.innerHTML = "<b>Stop connectivity</b><br>" +
    '<span style="color:#800026">&#9679;</span> 50+ routes<br>' +
    '<span style="color:#e03131">&#9679;</span> 25–49<br>' +
    '<span style="color:#f59f00">&#9679;</span> 12–24<br>' +
    '<span style="color:#66a61e">&#9679;</span> 5–11<br>' +
    '<span style="color:#4c9be8">&#9679;</span> 1–4';
  return d;
}};
legend.addTo(map);
</script></body></html>"""

out = REP / "coverage_map_offline.html"
out.write_text(HTML, encoding="utf-8")
print(f"Wrote {out} ({out.stat().st_size/1e6:.1f} MB) — {n_ok} tiles, {len(routes_geo)} routes")
