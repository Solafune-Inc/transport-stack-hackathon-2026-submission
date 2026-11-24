"""Live Delhi bus map — fetch the GTFS-RT feed and plot every bus in real time.

A small end-to-end demo of the real-time leg: it pulls the live GTFS-Realtime
`VehiclePositions` feed from the Transport Stack API, decodes the protobuf, joins
route names from the GTFS static feed, and renders an interactive Folium map where
each bus is coloured by how fast it's moving.

Run:
    python src/demo_live_map.py                 # fetch live -> reports/live_bus_map.html
    python src/demo_live_map.py --offline PB     # use a saved VehiclePositions.pb instead
    python src/demo_live_map.py --save-pb PB      # also archive the raw feed snapshot

Credentials come from `.env` (gitignored):
    TRANSPORTSTACK_RT_URL=...      # the get-file endpoint
    TRANSPORTSTACK_API_KEY=...     # the x-api-key value emailed on approval

Data source: Delhi Transport Stack (DoT, GNCTD) — License Agreement v1.0.
Third-party libs: requests, gtfs-realtime-bindings (protobuf), pandas, folium.
"""
from __future__ import annotations
import argparse, os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
import requests
import folium
from folium.plugins import MarkerCluster
from google.transit import gtfs_realtime_pb2

ROOT = Path(__file__).resolve().parents[1]
GTFS = ROOT / "data" / "delhi_buses_static_gtfs"
REP = ROOT / "reports"; REP.mkdir(exist_ok=True)
IST = timezone(timedelta(hours=5, minutes=30))  # Asia/Kolkata


def load_env() -> dict:
    """Minimal .env reader (no extra dependency)."""
    env = {}
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return {**env, **os.environ}  # real env vars win


def fetch_live(save_pb: str | None = None) -> bytes:
    env = load_env()
    url, key = env.get("TRANSPORTSTACK_RT_URL"), env.get("TRANSPORTSTACK_API_KEY")
    if not url or not key:
        raise SystemExit("Missing TRANSPORTSTACK_RT_URL / TRANSPORTSTACK_API_KEY in .env")
    r = requests.get(url, headers={"x-api-key": key}, timeout=30)
    r.raise_for_status()
    print(f"Fetched live feed: {len(r.content):,} bytes  (HTTP {r.status_code})")
    if save_pb:
        Path(save_pb).write_bytes(r.content)
        print(f"Archived raw feed -> {save_pb}")
    return r.content


def decode(pb: bytes) -> tuple[pd.DataFrame, datetime]:
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(pb)
    feed_time = datetime.fromtimestamp(feed.header.timestamp, timezone.utc)
    rows = []
    for e in feed.entity:
        if not e.HasField("vehicle"):
            continue
        v = e.vehicle
        rows.append(dict(
            vehicle_id=v.vehicle.id, route_id=v.trip.route_id, trip_id=v.trip.trip_id,
            lat=v.position.latitude, lon=v.position.longitude,
            speed=v.position.speed, ts=v.timestamp,
        ))
    df = pd.DataFrame(rows)
    df = df[(df.lat != 0) & (df.lon != 0)].copy()  # drop null positions
    return df, feed_time


def add_route_names(df: pd.DataFrame) -> pd.DataFrame:
    routes_f = GTFS / "routes.txt"
    if routes_f.exists():
        routes = pd.read_csv(routes_f, dtype=str)
        name = routes.set_index("route_id")["route_long_name"]
        df["route_name"] = df.route_id.map(name).fillna("(unknown route)")
    else:
        df["route_name"] = "(static feed not loaded)"
    return df


def speed_bucket(mps: float) -> tuple[str, str]:
    """(label, colour) — thresholds in m/s. ~14 m/s ≈ 50 km/h."""
    kmh = mps * 3.6
    if mps <= 0.5:
        return "Stopped", "#e03131"       # red
    if kmh < 15:
        return "Slow (<15 km/h)", "#f08c00"   # orange
    if kmh < 30:
        return "Moderate (15–30 km/h)", "#2f9e44"  # green
    return "Fast (>30 km/h)", "#1971c2"   # blue


def build_map(df: pd.DataFrame, feed_time: datetime) -> folium.Map:
    center = [df.lat.median(), df.lon.median()]
    m = folium.Map(location=center, zoom_start=11, tiles="OpenStreetMap",
                   control_scale=True)
    cluster = MarkerCluster(name=f"Live buses ({len(df):,})",
                            disableClusteringAtZoom=14).add_to(m)

    for r in df.itertuples():
        label, colour = speed_bucket(r.speed)
        kmh = r.speed * 3.6
        popup = folium.Popup(
            f"<b>Route {r.route_id}</b> — {r.route_name}<br>"
            f"Vehicle: {r.vehicle_id}<br>"
            f"Speed: {kmh:.1f} km/h &middot; {label}",
            max_width=280)
        folium.CircleMarker(
            [r.lat, r.lon], radius=4, color=colour, weight=1,
            fill=True, fill_color=colour, fill_opacity=0.85,
            popup=popup, tooltip=f"Route {r.route_id} · {kmh:.0f} km/h",
        ).add_to(cluster)

    folium.LayerControl(collapsed=False).add_to(m)

    ist = feed_time.astimezone(IST)
    moving = int((df.speed > 0.5).sum())
    overlay = f"""
    <div style="position:fixed;top:10px;left:50px;z-index:9999;background:rgba(255,255,255,.94);
      padding:10px 14px;border-radius:8px;font:13px/1.5 -apple-system,Arial;color:#222;
      box-shadow:0 1px 6px rgba(0,0,0,.25);max-width:320px">
      <b>Delhi Buses — Live Positions</b><br>
      <b>{len(df):,}</b> buses on <b>{df.route_id.nunique():,}</b> routes &middot;
      {moving:,} moving, {len(df)-moving:,} stopped<br>
      Feed time: <b>{ist:%Y-%m-%d %H:%M}</b> IST<br>
      <span style="font-size:12px">
        <span style="color:#e03131">●</span> stopped &nbsp;
        <span style="color:#f08c00">●</span> &lt;15 &nbsp;
        <span style="color:#2f9e44">●</span> 15–30 &nbsp;
        <span style="color:#1971c2">●</span> &gt;30 km/h
      </span><br>
      <span style="color:#666;font-size:11px">Source: Delhi Transport Stack (DoT, GNCTD), GTFS-RT · License v1.0</span>
    </div>"""
    m.get_root().html.add_child(folium.Element(overlay))
    return m


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", metavar="PB", help="use a saved VehiclePositions.pb instead of fetching")
    ap.add_argument("--save-pb", metavar="PB", help="archive the fetched raw feed to this path")
    ap.add_argument("--out", default=str(REP / "live_bus_map.html"))
    a = ap.parse_args(argv)

    pb = Path(a.offline).read_bytes() if a.offline else fetch_live(a.save_pb)
    df, feed_time = decode(pb)
    df = add_route_names(df)
    print(f"Decoded {len(df):,} vehicles on {df.route_id.nunique():,} routes "
          f"(feed {feed_time.astimezone(IST):%Y-%m-%d %H:%M} IST)")

    m = build_map(df, feed_time)
    m.save(a.out)
    print(f"Wrote {a.out} ({Path(a.out).stat().st_size/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
