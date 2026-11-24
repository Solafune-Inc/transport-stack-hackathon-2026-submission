"""Build a self-contained HTML report for the crowding model.

Run:  python src/make_crowding_report.py  ->  reports/crowding_report.html
Reads reports/crowding_metrics.json, data/eticketing/crowding_route_hour.csv and
data/eticketing/crowding_operator.csv (all from src/model/crowding.py) and embeds
notebooks/figures/crowd_*.png as base64.
"""
import base64, json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "notebooks" / "figures"
REP = ROOT / "reports"
RH = ROOT / "data" / "eticketing" / "crowding_route_hour.csv"
OPS = ROOT / "data" / "eticketing" / "crowding_operator.csv"
M = json.loads((REP / "crowding_metrics.json").read_text())

def img(name):
    return "data:image/png;base64," + base64.b64encode((FIG / name).read_bytes()).decode()
def stat(n, l):
    return f'<div class="stat"><div class="n">{n}</div><div class="l">{l}</div></div>'

LVL_COLOR = {"Low": "#2b8a3e", "Medium": "#f08c00", "High": "#e8590c", "Very High": "#c92a2a"}
# what riders see in the app for each level (mobile-implementation/src/logic/crowding.ts LEVEL_LABEL)
LVL_LABEL = {"Low": "Seats available", "Medium": "Standing room", "High": "Crowded", "Very High": "Packed"}
rh = pd.read_csv(RH)
hi = rh[rh.confidence == "high"]
top = hi.sort_values("peak_occupancy", ascending=False).drop_duplicates("route").head(15)
top_rows = "".join(
    f"<tr><td class='mono'>{r.route}</td><td class='num'>{int(r.hour):02d}:00</td>"
    f"<td><span class='pill' style='background:{LVL_COLOR.get(r.level,'#888')}'>{r.level}</span></td>"
    f"<td class='num'>{r.peak_occupancy:.2f}</td><td class='num'>{r.peak_per_vehicle_load:.0f}</td></tr>"
    for r in top.itertuples())

ld = M["level_distribution"]; ld_total = sum(ld.values())
lvl_rows = "".join(
    f"<tr><td><span class='dot' style='background:{LVL_COLOR.get(k,'#888')}'></span>{k} "
    f"<span class='sub'>({LVL_LABEL[k].lower()})</span></td>"
    f"<td class='num'>{ld[k]:,}</td><td class='num'>{100*ld[k]/ld_total:.1f}%</td></tr>"
    for k in ["Low", "Medium", "High", "Very High"] if k in ld)

ops = pd.read_csv(OPS) if OPS.exists() else pd.DataFrame()
fmt_occ = lambda x: "–" if pd.isna(x) else f"{x:.1f}&times;"
ops_rows = "".join(
    f"<tr><td class='mono'>{r.route}</td><td class='num'>{int(r.hour):02d}:00</td>"
    f"<td class='num'>{int(r.buses_per_day)}</td><td class='num'>{fmt_occ(r.peak_occupancy)}</td>"
    f"<td class='num'>{fmt_occ(r.saturday_occupancy)}</td><td class='num'>{fmt_occ(r.sunday_holiday_occupancy)}</td>"
    f"<td class='num'>{r.riders_over_capacity_per_day:,.0f}</td><td class='num'>{fmt_occ(r.occupancy_with_one_more_bus)}</td></tr>"
    for r in ops.head(15).itertuples())

HTML = f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Crowding Model — Delhi Buses (Problem 2)</title>
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
  h1 {{ margin:0 0 .25rem; font-size:1.95rem; }} h2 {{ margin:2.3rem 0 .5rem; font-size:1.28rem;
    border-bottom:2px solid var(--border); padding-bottom:.3rem; }}
  .sub {{ color:var(--muted); font-size:.92rem; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(135px,1fr)); gap:.7rem; margin:1rem 0; }}
  .stat {{ background:var(--card); border:1px solid var(--border); border-radius:10px; padding:.8rem .95rem; }}
  .stat .n {{ font-size:1.5rem; font-weight:700; }}
  .stat .l {{ color:var(--muted); font-size:.72rem; text-transform:uppercase; letter-spacing:.04em; }}
  table {{ border-collapse:collapse; width:100%; margin:.4rem 0 1rem; font-size:.9rem; }}
  th,td {{ text-align:left; padding:.4rem .7rem; border-bottom:1px solid var(--border); }}
  th {{ color:var(--muted); font-weight:600; }}
  td.num, th.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  td.mono {{ font-family:ui-monospace,Menlo,monospace; }}
  .pill {{ color:#fff; padding:.08rem .5rem; border-radius:999px; font-size:.78rem; font-weight:600; }}
  .dot {{ display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:.4rem; vertical-align:middle; }}
  figure {{ margin:1rem 0; background:var(--card); border:1px solid var(--border); border-radius:10px; padding:1rem; }}
  figure img {{ max-width:100%; height:auto; display:block; margin:0 auto; }}
  figcaption {{ color:var(--muted); font-size:.84rem; margin-top:.5rem; text-align:center; }}
  .key {{ background:var(--card); border-left:4px solid var(--accent); border-radius:8px; padding:.9rem 1.1rem; margin:1rem 0; }}
  .key h3 {{ margin:0 0 .3rem; color:var(--accent); }}
  code {{ background:var(--card); padding:.1rem .35rem; border-radius:4px; font-size:.86em; }}
  mark {{ background:var(--hl); color:inherit; padding:0 .2rem; border-radius:3px; }}
  ul li {{ margin:.25rem 0; }}
  footer {{ margin-top:3rem; color:var(--muted); font-size:.8rem; border-top:1px solid var(--border); padding-top:1rem; }}
</style></head><body><div class="wrap">

<h1>Crowding Model — Delhi Buses</h1>
<div class="sub">Transport Stack Hackathon 2026 &middot; <b>Problem 2 — crowdedness-aware journey planner</b>
&middot; built on real Oct e-ticketing &middot; <code>src/model/crowding.py</code></div>

<div class="grid">
  {stat(f"{M['tickets_usable']:,}", "Tickets used")}
  {stat(f"{M['route_hours_total']:,}", "Route-hours")}
  {stat(f"{M['route_hours_high_conf']:,}", "High-confidence")}
  {stat(f"{M['busiest_hour']:02d}:00", "Busiest hour")}
  {stat(f"{M['tickets_forward_pct']}%", "Forward-consistent")}
</div>

<div class="key">
  <h3>⭐ The method (grounded in the ticketing data)</h3>
  <p>For each <b>route + hour</b> we place the month's mobile-ticket boardings and alightings
  on the route's GTFS stop sequence and walk it to get the on-board load:</p>
  <p style="text-align:center"><code>load(after stop i) = &Sigma;<sub>j&le;i</sub> boardings(j) &minus; &Sigma;<sub>j&le;i</sub> alightings(j)</code></p>
  <p>Because this dataset records <b>both</b> boarding and alighting stops, load is computed
  <b>directly</b> — no alighting estimation. We then convert to a <b>per-vehicle</b> figure for an
  average bus in that hour and compare to capacity:</p>
  <p style="text-align:center"><code>per_vehicle_load = load / COVERAGE / trips_month</code> &nbsp;·&nbsp;
  <code>occupancy = per_vehicle_load / CAPACITY</code></p>
  <p class="sub">Assumptions (documented, tunable): COVERAGE = 4.5% (mobile share), CAPACITY = 60
  pax/bus, trips from the GTFS schedule &times; 31 days. Levels: Low &lt;0.5, Medium 0.5–0.8,
  High 0.8–1.0, Very&nbsp;High &gt;1.0 occupancy, shown to riders as <i>seats available, standing
  room, crowded, packed</i>. The estimate is most reliable as a <b>relative</b> ordering of
  crowding — which the planner needs.</p>
  <p class="sub">Day types: each route-hour's monthly profile is scaled to weekdays, Saturdays and
  Sundays/holidays by the B2 demand model ({M.get('daytype_model', 'b2')}), which beat the monthly
  average by 27% on a held-out week (<code>src/ml/compare_models.py</code>). A route-hour is
  low-confidence with &lt;2 scheduled buses/day or &lt;30 ticketed passengers in the month.</p>
</div>

<h2>1 &middot; Validation — does it match reality?</h2>
<p>Checks against known patterns (commute peaks, busy corridors, weekday vs weekend) and the
accounting itself:</p>
<figure><img src="{img('crowd_occ_by_hour.png')}" alt="occupancy by hour">
  <figcaption>① <b>Peak occupancy follows the commute.</b> Mean per-vehicle peak occupancy
  peaks at <b>{M['busiest_hour']:02d}:00</b> and again in the evening, with a midday dip —
  the expected bimodal pattern, now derived from load (not just ticket counts).</figcaption></figure>
<figure><img src="{img('crowd_profile_example.png')}" alt="example load profile">
  <figcaption>② <b>Load profiles have the right shape.</b> Example route
  {M.get('example_route','')} @ {M.get('example_hour','')}:00 — load builds from the origin,
  peaks mid/late route (crossing capacity = crowded), then falls as riders alight.</figcaption></figure>
<figure><img src="{img('crowd_route_hour_heatmap.png')}" alt="route x hour heatmap">
  <figcaption>③ <b>Crowding concentrates where expected</b> — morning/evening peaks per route,
  with directional (UP/DOWN) differences.</figcaption></figure>
<figure><img src="{img('crowd_occ_by_hour_daytype.png')}" alt="occupancy by hour and day type">
  <figcaption>④ <b>Weekday vs weekend.</b> Saturdays run a little below weekdays and Sundays/holidays
  far below (at 09:00 about a third of a weekday), with the same commute peaks.</figcaption></figure>
<p>⑤ <b>Accounting is consistent:</b> alightings / boardings =
<b>{M['mean_alight_to_board_ratio']}</b> (≈1.0 → load returns to zero by the terminus), and
<b>{M['tickets_forward_pct']}%</b> of trips board before they alight along the sequence.</p>

<h2>2 &middot; Crowding level distribution</h2>
<table><tr><th>Level</th><th class="num">Segments</th><th class="num">Share</th></tr>{lvl_rows}</table>
<p class="sub">Most route-segments are uncrowded; a meaningful tail is High / Very&nbsp;High,
concentrated at peak hours and the busy middle of long routes.</p>

<h2>3 &middot; Most-crowded routes (high-confidence)</h2>
<table><tr><th>Route</th><th class="num">Hour</th><th>Level</th>
  <th class="num">Occupancy</th><th class="num">Pax/bus</th></tr>{top_rows}</table>

<h2>4 &middot; For operators — where extra buses would help most</h2>
<p><b>{len(ops):,}</b> weekday route-hours are over capacity on their busiest stretch (high-confidence
only). They're ranked by <b>riders above capacity per day</b> at that stretch: the people an extra bus
in that hour would help. <i>With 1 more bus</i> is how full that stretch would be if the same riders
were spread over one more bus; Sat/Sun show whether the problem is weekday-only.</p>
<table><tr><th>Route</th><th class="num">Hour</th><th class="num">Buses/day</th>
  <th class="num">Weekday</th><th class="num">Sat</th><th class="num">Sun/hol</th>
  <th class="num">Riders over capacity/day</th><th class="num">With 1 more bus</th></tr>{ops_rows}</table>
<p class="sub">Occupancy = peak load &divide; capacity (60). Full list:
<code>data/eticketing/crowding_operator.csv</code> (written by <code>src/model/crowding.py</code>).
Absolute numbers assume one 4.5% mobile-ticket share for every route, which over-scales some
(e.g. 717A): read the <b>order</b>, not the counts. Per-route ticket data (ETM) would fix the scale.</p>

<h2>5 &middot; Using it — the rider's question</h2>
<p>The model answers "<b>will my bus be crowded?</b>" per route, hour, and trip leg:</p>
<pre style="background:var(--card);border:1px solid var(--border);border-radius:8px;padding:.8rem;overflow:auto;font-size:.82rem"><code>python src/query_crowding.py --route 623DOWN --hour 18
python src/query_crowding.py --route 623DOWN --hour 18 --from "Munirka Village" --to "Nehru Place Terminal"</code></pre>
<p class="sub">Outputs the crowding level + the load profile along the route (and the worst
segment on your leg). The app's planner (<code>src/api/</code>) uses the same tables: direct trips
and trips with one change, ranked on <b>time vs crowding</b>.</p>

<h2>6 &middot; Caveats</h2>
<ul>
  <li><b>Coverage ~4.5%:</b> mobile ticketing is a sample; absolute per-vehicle numbers depend
    on the COVERAGE constant. Treat levels as <b>relative</b>; anchor on ETM when it arrives.</li>
  <li><b>Sparse route-hours:</b> per-vehicle scaling divides by scheduled trips/hour, and few tickets
    make a noisy profile; route-hours with &lt;2 scheduled buses/day or &lt;30 ticketed passengers in
    the month ({M['route_hours_total']-M['route_hours_high_conf']:,} of {M['route_hours_total']:,})
    are flagged <b>low-confidence</b> and kept out of headline stats.</li>
  <li><b>Stop resolution:</b> ~2% of ticket stops are unresolved and excluded; {100-M['tickets_usable_pct']:.0f}%
    of tickets drop out overall (unresolved stop or stop not on the GTFS sequence).</li>
  <li><b>Capacity constant (60):</b> not split by bus type / AC yet.</li>
</ul>

<footer>
  Data source: Delhi Transport Stack (DoT, GNCTD), mobile e-ticketing + GTFS, License v1.0.
  Raw/derived data gitignored. Reproduce:
  <code>python src/model/crowding.py &amp;&amp; python src/make_crowding_report.py</code>.
</footer>
</div></body></html>"""

OUT = REP / "crowding_report.html"
OUT.write_text(HTML, encoding="utf-8")
print(f"Wrote {OUT} ({len(HTML)/1024:.0f} KB)")
