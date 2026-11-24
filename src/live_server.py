"""Live Delhi bus demo — a tiny server + auto-refreshing map.

Serves a web page that shows every bus in Delhi updating in real time. The
browser polls `/api/positions` once per second (a live ticking clock + redraw
when fresh data lands); the server fetches the upstream GTFS-RT feed only when
its cache is stale (REFRESH secs, default 15) — the feed itself only changes
~every 30s, so this keeps us to a few upstream requests/min instead of 60.

Run:
    python src/live_server.py                 # http://localhost:8766
    python src/live_server.py --port 9000 --refresh 10

Credentials come from `.env` (gitignored): TRANSPORTSTACK_RT_URL, TRANSPORTSTACK_API_KEY.
Data source: Delhi Transport Stack (DoT, GNCTD) — License Agreement v1.0.
Third-party libs: gtfs-realtime-bindings (protobuf), pandas (route names), stdlib http.server.
"""
from __future__ import annotations
import argparse, json, threading, time, urllib.request
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from google.transit import gtfs_realtime_pb2

ROOT = Path(__file__).resolve().parents[1]
GTFS = ROOT / "data" / "delhi_buses_static_gtfs"
IST = timezone(timedelta(hours=5, minutes=30))


def load_env() -> dict:
    env = {}
    f = ROOT / ".env"
    for line in f.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def load_route_names() -> dict:
    f = GTFS / "routes.txt"
    if not f.exists():
        return {}
    names = {}
    import csv
    with open(f, newline="") as fh:
        for row in csv.DictReader(fh):
            names[row["route_id"]] = row.get("route_long_name", "")
    return names


class FeedCache:
    """Fetches upstream at most once per `refresh` seconds; thread-safe."""
    def __init__(self, url, key, refresh, route_names):
        self.url, self.key, self.refresh = url, key, refresh
        self.route_names = route_names
        self.lock = threading.Lock()
        self.payload = None        # cached JSON-able dict
        self.fetched_at = 0.0      # wall-clock of last upstream fetch
        self.upstream_requests = 0
        self.cur = {}              # vehicle_id -> (lat, lon) from the current feed
        self.prev = {}             # vehicle_id -> (lat, lon) from the previous distinct feed
        self.last_feed_time = None

    def _fetch(self):
        req = urllib.request.Request(self.url, headers={"x-api-key": self.key})
        data = urllib.request.urlopen(req, timeout=30).read()
        self.upstream_requests += 1
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(data)
        ft = feed.header.timestamp
        parsed, cur = [], {}
        for e in feed.entity:
            if not e.HasField("vehicle"):
                continue
            v = e.vehicle
            lat, lon = v.position.latitude, v.position.longitude
            if lat == 0 and lon == 0:
                continue
            vid = v.vehicle.id
            lat, lon = round(lat, 5), round(lon, 5)
            cur[vid] = (lat, lon)
            parsed.append((vid, v.trip.route_id, lat, lon, round(v.position.speed * 3.6, 1)))
        # On a genuinely new feed, shift current positions into "previous" so each
        # bus has a prev->cur pair the client can connect with a thin line.
        if ft != self.last_feed_time:
            self.prev, self.cur, self.last_feed_time = self.cur, cur, ft
        # compact rows: [id, route_id, lat, lon, speed_kmh, prev_lat, prev_lon]
        rows = []
        for vid, route, lat, lon, kmh in parsed:
            p = self.prev.get(vid)
            rows.append([vid, route, lat, lon, kmh,
                         (p[0] if p else None), (p[1] if p else None)])
        moving = sum(1 for r in rows if r[4] > 1.8)  # >0.5 m/s
        routes = {r[1] for r in rows}
        self.payload = {
            "feed_time": ft,
            "count": len(rows),
            "moving": moving,
            "stopped": len(rows) - moving,
            "routes": len(routes),
            "vehicles": rows,
        }

    def get(self):
        with self.lock:
            if self.payload is None or (time.time() - self.fetched_at) >= self.refresh:
                self._fetch()
                self.fetched_at = time.time()
            out = dict(self.payload)
            out["fetched_at"] = int(self.fetched_at)
            out["server_time"] = int(time.time())
            out["upstream_requests"] = self.upstream_requests
            return out


def make_handler(cache: FeedCache):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # quiet
            pass

        def _send(self, body: bytes, ctype: str):
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.startswith("/api/positions"):
                self._send(json.dumps(cache.get()).encode(), "application/json")
            elif self.path.startswith("/api/routes"):
                self._send(json.dumps(cache.route_names).encode(), "application/json")
            elif self.path in ("/", "/index.html"):
                self._send(PAGE.encode(), "text/html; charset=utf-8")
            else:
                self.send_response(404); self.end_headers()
    return H


PAGE = r"""<!doctype html>
<html><head><meta charset="utf-8"><title>Delhi Buses — Live</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>
  html,body,#map{height:100%;margin:0}
  body{font:13px/1.4 -apple-system,Arial}
  #panel{position:fixed;top:10px;left:50px;z-index:1000;background:rgba(255,255,255,.95);
    padding:10px 14px;border-radius:8px;box-shadow:0 1px 6px rgba(0,0,0,.25);max-width:340px}
  #panel b{color:#111}
  .dot{display:inline-block;width:9px;height:9px;border-radius:50%;vertical-align:middle}
  .muted{color:#666;font-size:11px}
  #age{font-variant-numeric:tabular-nums}
</style></head>
<body>
<div id="map"></div>
<div id="panel">
  <b>Delhi Buses — Live</b> <span id="pulse" style="color:#2f9e44">●</span><br>
  <span id="stats">loading…</span><br>
  Feed age: <b id="age">—</b> &middot; updates every 1s<br>
  <span class="muted">
    <span class="dot" style="background:#e03131"></span> stopped
    <span class="dot" style="background:#f08c00"></span> &lt;15
    <span class="dot" style="background:#2f9e44"></span> 15–30
    <span class="dot" style="background:#1971c2"></span> &gt;30 km/h
  </span><br>
  <span class="muted">
    <span class="dot" style="background:#555"></span> current (now) &nbsp;
    <span class="dot" style="background:#fff;border:1.5px solid #555;width:7px;height:7px"></span> previous
    &nbsp;— line = move since last feed
  </span><br>
  <span class="muted" id="upstream"></span><br>
  <span class="muted">Source: Delhi Transport Stack (DoT, GNCTD), GTFS-RT · License v1.0</span>
</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const map = L.map('map', {preferCanvas:true}).setView([28.63,77.15], 11);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
  {maxZoom:19, attribution:'© OpenStreetMap'}).addTo(map);

let routeNames = {};
fetch('/api/routes').then(r=>r.json()).then(j=>routeNames=j);

const lineLayer = L.layerGroup().addTo(map);   // thin lines sit UNDER everything
const ghostLayer = L.layerGroup().addTo(map);  // previous-position markers, under current dots
const layer = L.layerGroup().addTo(map);       // current-position dots on top
let markers = new Map();       // vehicle_id -> circleMarker (current position)
let ghosts = new Map();        // vehicle_id -> circleMarker (previous position, hollow)
let lines = new Map();         // vehicle_id -> polyline (prev -> current)
let lastFeedTime = 0;
let lastFeedWall = Date.now(); // wall clock when current feed_time first seen

function colour(kmh){
  if(kmh<=1.8) return '#e03131';
  if(kmh<15)   return '#f08c00';
  if(kmh<30)   return '#2f9e44';
  return '#1971c2';
}
function popupHtml(d){
  return `<b>Route ${d.route}</b> — ${routeNames[d.route]||'(unknown)'}<br>Vehicle: ${d.id}<br>Speed: ${d.kmh} km/h`;
}

function redraw(data){
  const seen = new Set();
  for(const [id,route,lat,lon,kmh,plat,plon] of data.vehicles){
    seen.add(id);
    const c = colour(kmh);
    let m = markers.get(id);
    if(m){
      m.setLatLng([lat,lon]); m.setStyle({color:c,fillColor:c});
      m._d = {route,id,kmh};                    // keep popup data current (color + speed stay in sync)
      if(m.isPopupOpen()) m.setPopupContent(popupHtml(m._d));
    }else{
      m = L.circleMarker([lat,lon],{radius:4,weight:1,color:c,fillColor:c,fillOpacity:.85});
      m._d = {route,id,kmh};
      m.bindPopup(()=>popupHtml(m._d));         // reads latest data on open, not the first-seen values
      m.addTo(layer); markers.set(id,m);
    }
    // thin line prev -> current, plus a hollow marker at the previous position so the
    // two ends read clearly:  solid dot = current (now),  hollow ring = previous.
    if(plat!=null && plon!=null){
      let ln = lines.get(id);
      if(ln){ ln.setLatLngs([[plat,plon],[lat,lon]]); ln.setStyle({color:c}); }
      else{ ln = L.polyline([[plat,plon],[lat,lon]],{color:c,weight:1.5,opacity:.8});
            ln.addTo(lineLayer); lines.set(id,ln); }
      let g = ghosts.get(id);
      if(g){ g.setLatLng([plat,plon]); g.setStyle({color:c}); }
      else{ g = L.circleMarker([plat,plon],{radius:3,weight:1.5,color:c,fillColor:'#fff',fillOpacity:1});
            g.addTo(ghostLayer); ghosts.set(id,g); }
    }else{
      if(lines.has(id)){ lineLayer.removeLayer(lines.get(id)); lines.delete(id); }
      if(ghosts.has(id)){ ghostLayer.removeLayer(ghosts.get(id)); ghosts.delete(id); }
    }
  }
  for(const [id,m] of markers){ if(!seen.has(id)){ layer.removeLayer(m); markers.delete(id); } }
  for(const [id,g] of ghosts){ if(!seen.has(id)){ ghostLayer.removeLayer(g); ghosts.delete(id); } }
  for(const [id,ln] of lines){ if(!seen.has(id)){ lineLayer.removeLayer(ln); lines.delete(id); } }
}

async function tick(){
  try{
    const data = await (await fetch('/api/positions')).json();
    document.getElementById('stats').innerHTML =
      `<b>${data.count.toLocaleString()}</b> buses on <b>${data.routes.toLocaleString()}</b> routes · `+
      `${data.moving.toLocaleString()} moving, ${data.stopped.toLocaleString()} stopped`;
    document.getElementById('upstream').textContent =
      `upstream fetches: ${data.upstream_requests} · feed updates ~every 30s`;
    if(data.feed_time !== lastFeedTime){
      lastFeedTime = data.feed_time; lastFeedWall = Date.now();
      redraw(data);
      const p=document.getElementById('pulse'); p.style.opacity=.2;
      setTimeout(()=>p.style.opacity=1,200);
    }
  }catch(e){ /* keep ticking */ }
  const age = Math.round((Date.now()-lastFeedWall)/1000);
  document.getElementById('age').textContent = age+'s ago';
}
tick(); setInterval(tick, 1000);
</script>
</body></html>"""


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--refresh", type=int, default=15,
                    help="min seconds between upstream fetches (feed changes ~every 30s)")
    a = ap.parse_args(argv)

    env = load_env()
    url, key = env.get("TRANSPORTSTACK_RT_URL"), env.get("TRANSPORTSTACK_API_KEY")
    if not url or not key:
        raise SystemExit("Missing TRANSPORTSTACK_RT_URL / TRANSPORTSTACK_API_KEY in .env")

    cache = FeedCache(url, key, a.refresh, load_route_names())
    cache.get()  # warm + fail fast if creds are wrong
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(cache))
    print(f"Live demo at http://localhost:{a.port}  "
          f"(upstream refresh every {a.refresh}s, browser polls every 1s)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
