"""Build a self-contained comprehensive HTML report for the GTFS EDA.

Run:  python src/make_eda_report.py   ->  reports/eda_report.html
Reads metrics from reports/eda_full_metrics.json and embeds all figures
from notebooks/figures/ as base64 data URIs (fully portable, no external assets).
"""
import base64, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "notebooks" / "figures"
REP = ROOT / "reports"
M = json.loads((REP / "eda_full_metrics.json").read_text())

def img(name):
    b64 = base64.b64encode((FIG / name).read_bytes()).decode()
    return f"data:image/png;base64,{b64}"

c = M["counts"]; r = M["routes"]; s = M["stops"]; tr = M["trips"]
stt = M["stop_times"]; fq = M["frequency"]; sh = M["shapes"]

def stat(n, l):
    return f'<div class="stat"><div class="n">{n}</div><div class="l">{l}</div></div>'

ORDER = ["count", "mean", "std", "min", "25%", "50%", "75%", "max"]
def fnum(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return str(v)
    if v == int(v) and abs(v) >= 1000:
        return f"{int(v):,}"
    if v == int(v):
        return f"{int(v):,}"
    return f"{v:,.2f}"

def describe_table(cols):
    """cols: list of (label, describe_dict). Renders one table, stats as rows."""
    head = "".join(f"<th class='num'>{lbl}</th>" for lbl, _ in cols)
    rows = ""
    for stat_name in ORDER:
        cells = "".join(f"<td class='num'>{fnum(d.get(stat_name))}</td>" for _, d in cols)
        rows += f"<tr><th>{stat_name}</th>{cells}</tr>"
    return f"<table><tr><th>stat</th>{head}</tr>{rows}</table>"

def hour_table(d, unit, every=1):
    """d: {hour: value} dict. Renders a compact hour->value table."""
    items = sorted(((int(k), v) for k, v in d.items()))
    cells = "".join(
        f"<tr><td class='num'>{hh:02d}:00</td><td class='num'>{fnum(v)}</td></tr>"
        for hh, v in items)
    return f"<table><tr><th>hour</th><th class='num'>{unit}</th></tr>{cells}</table>"

hubs_rows = "".join(
    f"<tr><td>{h['stop']}</td><td class='num'>{h['routes']}</td><td class='num'>{h['trips']:,}</td></tr>"
    for h in s["top_hubs"][:10])

HTML = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Comprehensive EDA — Delhi Buses GTFS (v1)</title>
<style>
  :root {{ --bg:#fff; --fg:#1b1f24; --muted:#5b6670; --card:#f6f8fa; --border:#e2e6ea;
           --accent:#0b7285; --good:#2b8a3e; --warn:#e8590c; --hl:#fff3bf; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg:#0f1317; --fg:#e6edf3; --muted:#9aa4ad; --card:#161b22; --border:#2a3038;
             --accent:#38bdf0; --good:#51cf66; --warn:#ff922b; --hl:#3a3410; }} }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--fg);
    font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }}
  .wrap {{ max-width:980px; margin:0 auto; padding:2.5rem 1.25rem 4rem; }}
  header h1 {{ margin:0 0 .25rem; font-size:1.95rem; letter-spacing:-.01em; }}
  .sub {{ color:var(--muted); font-size:.93rem; }}
  h2 {{ margin:2.4rem 0 .6rem; font-size:1.28rem; border-bottom:2px solid var(--border); padding-bottom:.35rem; }}
  h3 {{ margin:1.4rem 0 .4rem; font-size:1.02rem; color:var(--accent); }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(135px,1fr)); gap:.7rem; margin:1rem 0; }}
  .stat {{ background:var(--card); border:1px solid var(--border); border-radius:10px; padding:.8rem .95rem; }}
  .stat .n {{ font-size:1.45rem; font-weight:700; }}
  .stat .l {{ color:var(--muted); font-size:.72rem; text-transform:uppercase; letter-spacing:.04em; }}
  table {{ border-collapse:collapse; width:100%; margin:.4rem 0 1rem; font-size:.92rem; }}
  th,td {{ text-align:left; padding:.45rem .7rem; border-bottom:1px solid var(--border); }}
  th {{ color:var(--muted); font-weight:600; }}
  td.num, th.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  figure {{ margin:1rem 0; background:var(--card); border:1px solid var(--border); border-radius:10px; padding:1rem; }}
  figure img {{ max-width:100%; height:auto; display:block; margin:0 auto; border-radius:6px; }}
  figcaption {{ color:var(--muted); font-size:.84rem; margin-top:.55rem; text-align:center; }}
  .good {{ color:var(--good); font-weight:600; }} .warn {{ color:var(--warn); font-weight:600; }}
  .key {{ background:var(--card); border-left:4px solid var(--accent); border-radius:8px; padding:.9rem 1.1rem; margin:1rem 0; }}
  .key h3 {{ margin:0 0 .3rem; color:var(--accent); }}
  mark {{ background:var(--hl); color:inherit; padding:0 .2rem; border-radius:3px; }}
  code {{ background:var(--card); padding:.1rem .35rem; border-radius:4px; font-size:.88em; }}
  ul li {{ margin:.28rem 0; }}
  .two {{ display:grid; grid-template-columns:1fr 1fr; gap:1rem; }}
  @media (max-width:640px) {{ .two {{ grid-template-columns:1fr; }} }}
  footer {{ margin-top:3rem; color:var(--muted); font-size:.82rem; border-top:1px solid var(--border); padding-top:1rem; }}
</style></head><body><div class="wrap">

<header>
  <h1>Comprehensive EDA — Delhi Buses GTFS Static (v1)</h1>
  <div class="sub">Transport Stack Hackathon 2026 &middot; Problem 2 (crowdedness-aware journey planner)</div>
  <div class="sub">Full feed, no sampling &middot; generated 2026-11-11 from <code>src/eda_full.py</code></div>
</header>

<h2>1 &middot; Feed at a glance</h2>
<div class="grid">
  {stat(f"{c['routes']:,}", "Routes")}
  {stat(f"{c['stops']:,}", "Stops")}
  {stat(f"{c['trips']:,}", "Trips")}
  {stat("2.39M", "Stop times")}
  {stat(f"{c['shape_points']:,}", "Shape pts")}
  {stat("2", "Agencies")}
</div>
<p>Operators: <strong>DTC</strong> ({r['agency'].get('DTC',0):,} routes) and
<strong>DoT</strong> ({r['agency'].get('DOT',0):,} routes); all bus.
Routes come as directional variants &mdash; <strong>{r['corridors']:,} corridors</strong>,
of which <strong>{r['paired_corridors']:,}</strong> have both UP &amp; DOWN
({r['dir_suffix'].get('?',0)} names didn't match the UP/DOWN convention).</p>

<div class="key">
  <h3>⭐ Headline insight for modeling</h3>
  <p><mark>The schedule encodes <strong>no time-of-day travel-time variation.</strong></mark>
  Mean scheduled speed is a near-constant <strong>~19.9 km/h</strong> across every hour
  (std just 1.6 km/h), and <strong>dwell time is exactly 0</strong> at every stop
  (arrival = departure). So the GTFS schedule is a <em>structural</em> backbone
  (routes, stops, stop order, geometry) but carries <strong>no congestion or
  crowding signal</strong>. That signal must come from the <strong>GPS traces and
  ticketing / ETM data</strong>. This is the core justification for the Problem 2 approach.</p>
</div>

<h2>2 &middot; Network structure &amp; hubs</h2>
<p>A stop is served by a median of <strong>{s['routes_per_stop']['50%']:.0f} routes</strong>
(mean {s['routes_per_stop']['mean']:.1f}, max {s['routes_per_stop']['max']:.0f}).
The network is strongly hub-oriented:</p>
<div class="two">
  <table>
    <tr><th>Top hub stop</th><th class="num">Routes</th><th class="num">Trips/day</th></tr>
    {hubs_rows}
  </table>
  <figure><img src="{img('routes_per_stop.png')}" alt="Routes per stop">
    <figcaption>Routes per stop (log y) — long tail of mega-hubs.</figcaption></figure>
</div>
<p class="sub">{s['dup_coord_cells']} coordinate cells host &gt;1 stop (≈{s['dup_coord_cells']*2}
stops) — likely paired directional stops or minor duplicates to watch when snapping.</p>

<h2>3 &middot; Spatial coverage</h2>
<p class="sub">Basemap tiles are <strong>baked into the images</strong> (fetched once at
build time) — the report makes <strong>no external requests</strong> when viewed, so it
renders in secured/offline environments. Basemap &copy; Esri.</p>
<figure><img src="{img('network_basemap.png')}" alt="Delhi bus network over basemap">
  <figcaption>All 2,554 route shapes over an Esri street basemap. Red markers = top-20
  hubs (sized by # routes). Dense radial-plus-grid core with long corridors reaching
  into NCR / Haryana.</figcaption></figure>
<figure><img src="{img('stops_heat_basemap.png')}" alt="Stop density over basemap">
  <figcaption>Stop-density hexbin over the basemap — intensity of coverage.</figcaption></figure>
<details><summary class="sub">Tile-free versions (pure GTFS geometry, no basemap)</summary>
<div class="two">
  <figure><img src="{img('network_map.png')}" alt="Network geometry">
    <figcaption>Route geometry only.</figcaption></figure>
  <figure><img src="{img('stop_kde.png')}" alt="Stop density 2D histogram">
    <figcaption>Stop-density 2D histogram.</figcaption></figure>
</div></details>

<h2>4 &middot; Trip profiles</h2>
<div class="grid">
  {stat(f"{tr['dur_min']['50%']:.0f} min", "Median duration")}
  {stat(f"{tr['dist_km']['50%']:.1f} km", "Median distance")}
  {stat(f"{M['speed_by_hour'].get('8',0):.1f} km/h", "Speed @ 08:00")}
  {stat(f"{sh['len_km_median']:.1f} km", "Median shape len")}
</div>
<figure><img src="{img('trip_dur_dist.png')}" alt="Trip duration and distance">
  <figcaption>Trip duration (median {tr['dur_min']['50%']:.0f} min, max {tr['dur_min']['max']:.0f})
  and distance (median {tr['dist_km']['50%']:.1f} km, max {tr['dist_km']['max']:.0f}).</figcaption></figure>
<figure><img src="{img('speed.png')}" alt="Scheduled speed">
  <figcaption>Scheduled speed is tightly clustered (~{tr['speed_kmh']['50%']:.0f} km/h) and
  <strong>flat across the day</strong> — the smoking gun that the schedule ignores congestion.</figcaption></figure>

<h2>5 &middot; Service frequency &amp; timing</h2>
<figure><img src="{img('vehicles_by_hour.png')}" alt="Buses in service by hour">
  <figcaption>Buses in service peaks at ~{max(fq['active_by_hour'].values()):,} (08:00 &amp; 15:00–16:00)
  on a broad 07:00–20:00 plateau; minimal night service.</figcaption></figure>
<figure><img src="{img('spacing_headway.png')}" alt="Spacing and headway">
  <figcaption>Inter-stop spacing median <strong>{stt['spacing_km']['50%']*1000:.0f} m</strong>
  (hop ≈ {stt['median_hop_min']:.1f} min); AM-peak mean headway per route median
  <strong>{fq['am_headway_min']['50%']:.0f} min</strong> — most individual routes are infrequent,
  so coverage relies on overlapping corridors.</figcaption></figure>

<h2>6 &middot; Data-quality notes</h2>
<ul>
  <li><span class="good">✔</span> Perfect referential integrity (0 orphan trips / unknown refs / unused stops / empty routes); 0 null coordinates.</li>
  <li><span class="warn">✦ Non-standard columns:</span> <code>stop_times</code> adds
    <code>fare_stage</code> (100% populated, but only {stt['fare_stages_per_trip_median']:.0f}
    distinct stage/trip median → little OD value here) and an empty <code>stop_dist</code>
    (0% populated). Trip distance therefore comes from <code>shapes.shape_dist_traveled</code>.</li>
  <li><span class="warn">✦ Dwell = 0</span> everywhere; <span class="warn">single all-days
    <code>calendar</code></span> → no weekday/weekend or dwell modeling in the feed.</li>
  <li><span class="warn">✦ No fare files</span> (<code>fare_attributes</code>/<code>fare_rules</code> absent).</li>
  <li><span class="warn">✦ <code>direction_id</code> blank</span> — direction inferred from UP/DOWN route names.</li>
</ul>

<h2>7 &middot; Summary statistics (full distributions)</h2>
<p class="sub">Every distribution below is computed over the <strong>full feed</strong>
(n in the <code>count</code> row). Times in minutes, distances in km, speed in km/h.</p>

<h3>Trip-level &amp; network distributions</h3>
{describe_table([
  ("Trip dur (min)", tr["dur_min"]),
  ("Trip dist (km)", tr["dist_km"]),
  ("Sched speed (km/h)", tr["speed_kmh"]),
  ("Routes / stop", s["routes_per_stop"]),
  ("Stop spacing (km)", stt["spacing_km"]),
  ("AM headway (min)", fq["am_headway_min"]),
])}

<h3>Scalar metrics</h3>
<table>
  <tr><th>Metric</th><th class="num">Value</th></tr>
  <tr><td>Corridors (UP/DOWN base names)</td><td class="num">{r['corridors']:,}</td></tr>
  <tr><td>Corridors with both directions</td><td class="num">{r['paired_corridors']:,}</td></tr>
  <tr><td>Median inter-stop hop time (min)</td><td class="num">{stt['median_hop_min']:.2f}</td></tr>
  <tr><td>Stop events with dwell &gt; 0 (%)</td><td class="num">{stt['dwell_pct_nonzero']:.2f}</td></tr>
  <tr><td>fare_stage populated (%)</td><td class="num">{stt['fare_stage_pct']:.1f}</td></tr>
  <tr><td>Median distinct fare stages / trip</td><td class="num">{stt['fare_stages_per_trip_median']:.0f}</td></tr>
  <tr><td>Shapes</td><td class="num">{sh['n_shapes']:,}</td></tr>
  <tr><td>Median points / shape</td><td class="num">{sh['pts_per_shape_median']:,}</td></tr>
  <tr><td>Median shape length (km)</td><td class="num">{sh['len_km_median']:.1f}</td></tr>
  <tr><td>Duplicate-coordinate cells (stops)</td><td class="num">{s['dup_coord_cells']}</td></tr>
</table>

<h3>Hourly breakdown</h3>
<div class="two">
  <div>
    <p class="sub"><strong>Buses in service</strong> (active trips) by hour</p>
    {hour_table(fq["active_by_hour"], "active trips")}
  </div>
  <div>
    <p class="sub"><strong>Mean scheduled speed</strong> by start hour (note the flatness)</p>
    {hour_table(M["speed_by_hour"], "km/h")}
  </div>
</div>

<h2>8 &middot; So what — implications for the prototype</h2>
<ul>
  <li>Use GTFS for the <strong>journey-planner graph</strong> (stops, stop order, geometry, nominal timing) — it's clean and complete.</li>
  <li>Do <strong>not</strong> trust schedule timings for real travel time; fold in <strong>GPS traces</strong> (Problem 1) for live speeds.</li>
  <li>Derive crowding from <strong>ticketing / ETM boardings</strong>; validate the time-of-day shape against the service-by-hour curve above.</li>
  <li>Exploit the <strong>hub structure</strong> and <strong>UP/DOWN pairing</strong> when building the route graph and estimating load along corridors.</li>
  <li>Median <strong>455 m</strong> stop spacing supports stop-level load modelling without over-sparsity.</li>
</ul>

<footer>
  Data source: Delhi Transport Stack (Department of Transport, GNCTD), used under the Transport Stack
  Data License Agreement v1.0. Derived/aggregated for the hackathon; see <code>data/LICENSE-NOTES.md</code>.
  Reproduce: <code>python src/eda_full.py &amp;&amp; python src/make_eda_report.py</code>.
</footer>
</div></body></html>
"""

(REP / "eda_report.html").write_text(HTML, encoding="utf-8")
print(f"Wrote {REP/'eda_report.html'} ({len(HTML)/1024:.0f} KB incl. embedded figures)")
