"""Track one bus over time from the GTFS-RT feed and draw its trajectory.

Two modes:
  collect  — poll the live feed every --interval secs for --duration secs and append
             each snapshot's vehicle positions to data/realtime/vehicle_history.csv
             (deduped by vehicle_id + feed_time).
  render   — pick a vehicle (--vehicle ID, else the best mover) and draw its path on a
             Folium map: time-ordered polyline coloured by speed, numbered points with
             timestamps, green start / red end markers.

Run:
    python src/track_bus.py collect --duration 300 --interval 20
    python src/track_bus.py render                 # auto-pick longest trajectory
    python src/track_bus.py render --vehicle DL1PD4325
    python src/track_bus.py render --list 15       # show top candidates, don't render

The feed only changes ~every 30s, so --interval 20 keeps us to ~3 upstream req/min.
Credentials from .env (gitignored). Source: Delhi Transport Stack (DoT, GNCTD), License v1.0.
Third-party libs: gtfs-realtime-bindings (protobuf), pandas, folium.
"""
from __future__ import annotations
import argparse, csv, math, time, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
import folium
from google.transit import gtfs_realtime_pb2

ROOT = Path(__file__).resolve().parents[1]
GTFS = ROOT / "data" / "delhi_buses_static_gtfs"
RT = ROOT / "data" / "realtime"; RT.mkdir(parents=True, exist_ok=True)
REP = ROOT / "reports"; REP.mkdir(exist_ok=True)
HIST = RT / "vehicle_history.csv"
IST = timezone(timedelta(hours=5, minutes=30))
COLS = ["feed_time", "vehicle_id", "route_id", "trip_id", "lat", "lon", "speed_kmh"]


def load_env() -> dict:
    env = {}
    for line in (ROOT / ".env").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def route_names() -> dict:
    f = GTFS / "routes.txt"
    if not f.exists():
        return {}
    r = pd.read_csv(f, dtype=str)
    return dict(zip(r.route_id, r.route_long_name.fillna("")))


def fetch_rows(url, key):
    req = urllib.request.Request(url, headers={"x-api-key": key})
    data = urllib.request.urlopen(req, timeout=30).read()
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(data)
    ft = feed.header.timestamp
    rows = []
    for e in feed.entity:
        if not e.HasField("vehicle"):
            continue
        v = e.vehicle
        lat, lon = v.position.latitude, v.position.longitude
        if lat == 0 and lon == 0:
            continue
        rows.append([ft, v.vehicle.id, v.trip.route_id, v.trip.trip_id,
                     round(lat, 6), round(lon, 6), round(v.position.speed * 3.6, 1)])
    return ft, rows


def collect(a):
    env = load_env()
    url, key = env["TRANSPORTSTACK_RT_URL"], env["TRANSPORTSTACK_API_KEY"]
    seen = set()  # (vehicle_id, feed_time) already written
    if HIST.exists():
        prev = pd.read_csv(HIST)
        seen = set(zip(prev.vehicle_id.astype(str), prev.feed_time.astype(int)))
    new = not HIST.exists()
    f = open(HIST, "a", newline="")
    w = csv.writer(f)
    if new:
        w.writerow(COLS)

    end = time.time() + a.duration
    polls = feed_times = written = 0
    while time.time() < end:
        try:
            ft, rows = fetch_rows(url, key)
            polls += 1
            added = 0
            for r in rows:
                key_ = (str(r[1]), int(r[0]))
                if key_ not in seen:
                    seen.add(key_); w.writerow(r); added += 1
            if added:
                feed_times += 1; written += added
                f.flush()
                print(f"[{datetime.now(IST):%H:%M:%S}] feed {ft} "
                      f"(+{added} rows, {len(rows)} vehicles in snapshot)")
            else:
                print(f"[{datetime.now(IST):%H:%M:%S}] feed {ft} (no change)")
        except Exception as e:
            print(f"[{datetime.now(IST):%H:%M:%S}] fetch error: {e}")
        if time.time() < end:
            time.sleep(a.interval)
    f.close()
    print(f"done: {polls} polls, {feed_times} distinct feeds, {written} new rows -> {HIST}")


def haversine(a, b):
    R = 6371.0
    la1, lo1, la2, lo2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    h = math.sin((la2-la1)/2)**2 + math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2
    return 2 * R * math.asin(math.sqrt(h))


def trajectories(df):
    """Per vehicle: time-ordered distinct points + summary stats."""
    out = {}
    for vid, g in df.sort_values("feed_time").groupby("vehicle_id"):
        g = g.drop_duplicates("feed_time")
        pts = list(zip(g.lat, g.lon, g.feed_time, g.speed_kmh))
        # drop consecutive identical coords (parked / no GPS move)
        clean = [pts[0]]
        for p in pts[1:]:
            if (p[0], p[1]) != (clean[-1][0], clean[-1][1]):
                clean.append(p)
        if len(clean) < 2:
            continue
        dist = sum(haversine(clean[i][:2], clean[i+1][:2]) for i in range(len(clean)-1))
        span = clean[-1][2] - clean[0][2]
        out[vid] = dict(route=g.route_id.iloc[0], points=clean,
                        n=len(clean), dist_km=round(dist, 2), span_s=int(span))
    return out


def speed_colour(kmh):
    if kmh <= 1.8: return "#e03131"
    if kmh < 15:   return "#f08c00"
    if kmh < 30:   return "#2f9e44"
    return "#1971c2"


def render(a):
    if not HIST.exists():
        raise SystemExit(f"No history yet. Run: python src/track_bus.py collect")
    df = pd.read_csv(HIST)
    df["vehicle_id"] = df.vehicle_id.astype(str)
    trajs = trajectories(df)
    if not trajs:
        raise SystemExit("No vehicle has moved across >=2 distinct points yet — collect longer.")

    # rank by (points, distance) — a long, well-sampled path makes the best demo
    ranked = sorted(trajs.items(), key=lambda kv: (kv[1]["n"], kv[1]["dist_km"]), reverse=True)

    if a.list:
        print(f"{'vehicle':<14}{'route':<8}{'pts':>4}{'dist_km':>9}{'span_s':>8}")
        for vid, t in ranked[:a.list]:
            print(f"{vid:<14}{t['route']:<8}{t['n']:>4}{t['dist_km']:>9}{t['span_s']:>8}")
        return

    vid = a.vehicle or ranked[0][0]
    if vid not in trajs:
        raise SystemExit(f"Vehicle {vid} not found / not enough points. Try --list.")
    t = trajs[vid]
    rname = route_names().get(t["route"], "")
    pts = t["points"]

    center = [sum(p[0] for p in pts)/len(pts), sum(p[1] for p in pts)/len(pts)]
    m = folium.Map(location=center, zoom_start=14, tiles="OpenStreetMap", control_scale=True)

    # speed-coloured segments
    for i in range(len(pts)-1):
        folium.PolyLine([pts[i][:2], pts[i+1][:2]], color=speed_colour(pts[i+1][3]),
                        weight=5, opacity=0.85).add_to(m)

    # numbered timestamped waypoints
    for i, (lat, lon, ft, kmh) in enumerate(pts):
        tstr = datetime.fromtimestamp(ft, IST).strftime("%H:%M:%S")
        folium.CircleMarker([lat, lon], radius=4, color="#333", weight=1,
                            fill=True, fill_color="#fff", fill_opacity=1,
                            tooltip=f"#{i}  {tstr} IST · {kmh} km/h").add_to(m)

    folium.Marker(pts[0][:2], tooltip="Start",
                  icon=folium.Icon(color="green", icon="play")).add_to(m)
    folium.Marker(pts[-1][:2], tooltip="End (latest)",
                  icon=folium.Icon(color="red", icon="stop")).add_to(m)
    m.fit_bounds([[min(p[0] for p in pts), min(p[1] for p in pts)],
                  [max(p[0] for p in pts), max(p[1] for p in pts)]])

    t0 = datetime.fromtimestamp(pts[0][2], IST)
    t1 = datetime.fromtimestamp(pts[-1][2], IST)
    avg = t["dist_km"] / (t["span_s"]/3600) if t["span_s"] else 0
    title = f"""
    <div style="position:fixed;top:10px;left:50px;z-index:9999;background:rgba(255,255,255,.95);
      padding:10px 14px;border-radius:8px;font:13px/1.5 -apple-system,Arial;color:#222;
      box-shadow:0 1px 6px rgba(0,0,0,.25);max-width:340px">
      <b>Tracked bus {vid}</b> — Route {t['route']} {rname}<br>
      {t['n']} fixes over {t['span_s']//60}m{t['span_s']%60}s &middot;
      <b>{t['dist_km']} km</b> &middot; avg {avg:.0f} km/h<br>
      {t0:%H:%M:%S} → {t1:%H:%M:%S} IST ({t0:%Y-%m-%d})<br>
      <span style="font-size:12px">
        <span style="color:#e03131">●</span> stopped
        <span style="color:#f08c00">●</span> &lt;15
        <span style="color:#2f9e44">●</span> 15–30
        <span style="color:#1971c2">●</span> &gt;30 km/h (segment speed)</span><br>
      <span style="color:#666;font-size:11px">Source: Delhi Transport Stack (DoT, GNCTD), GTFS-RT · License v1.0</span>
    </div>"""
    m.get_root().html.add_child(folium.Element(title))

    out = REP / f"track_{vid}.html"
    m.save(str(out))
    print(f"Tracked {vid} (route {t['route']}): {t['n']} fixes, {t['dist_km']} km over "
          f"{t['span_s']}s. Wrote {out} ({out.stat().st_size/1e6:.1f} MB)")


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="mode", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--duration", type=int, default=300)
    c.add_argument("--interval", type=int, default=20)
    r = sub.add_parser("render")
    r.add_argument("--vehicle")
    r.add_argument("--list", type=int, default=0, help="list top N candidates instead of rendering")
    a = ap.parse_args(argv)
    (collect if a.mode == "collect" else render)(a)


if __name__ == "__main__":
    main()
