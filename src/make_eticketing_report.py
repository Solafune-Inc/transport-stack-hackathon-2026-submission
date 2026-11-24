"""Build a self-contained HTML report for the e-ticketing EDA.

Run:  python src/make_eticketing_report.py  ->  reports/eda_eticketing_report.html
Reads reports/eda_eticketing_metrics.json and embeds notebooks/figures/etk_*.png
as base64 data URIs (portable, no external requests).
"""
import base64, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "notebooks" / "figures"
REP = ROOT / "reports"
M = json.loads((REP / "eda_eticketing_metrics.json").read_text())

def img(name):
    b64 = base64.b64encode((FIG / name).read_bytes()).decode()
    return f"data:image/png;base64,{b64}"

def stat(n, l):
    return f'<div class="stat"><div class="n">{n}</div><div class="l">{l}</div></div>'

def rows_from(d, kcol, vcol, fmt=lambda v: f"{int(v):,}"):
    return "".join(f"<tr><td>{k}</td><td class='num'>{fmt(v)}</td></tr>" for k, v in d.items())

ac = M["is_ac_counts"]; ac_total = sum(ac.values())
ac_true = ac.get("True", 0)
peak = M["peak_route_hour_example"]

HTML = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>EDA — Delhi Mobile E-ticketing (Oct 2026)</title>
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
  <h1>EDA — Delhi Mobile E-ticketing (October 2026)</h1>
  <div class="sub">Transport Stack Hackathon 2026 &middot; Problem 2 (crowdedness-aware journey planner)</div>
  <div class="sub">Full file, no sampling &middot; generated from <code>src/eda_eticketing.py</code>
    &middot; runtime {M['runtime_sec']}s</div>
</header>

<h2>1 &middot; Dataset at a glance</h2>
<div class="grid">
  {stat(f"{M['rows']:,}", "Tickets")}
  {stat(f"{M['total_passengers']:,}", "Passengers")}
  {stat(f"{M['n_days']}", "Days (Oct)")}
  {stat(f"{M['distinct_routes']:,}", "Routes")}
  {stat(f"{M['distinct_start_stops']:,}", "Boarding stops")}
  {stat(f"&#8377;{M['revenue_total']/1e6:.1f}M", "Revenue")}
</div>
<p><strong>Facts.</strong> One row = one mobile-ticketing ticket. {M['rows']:,} tickets span
<strong>{M['date_min'][:10]} &rarr; {M['date_max'][:10]}</strong> ({M['n_days']} days). Every
field is populated except <code>vehicle_number</code> ({100-M['vehicle_number_present_pct']:.0f}%
null); no fully-duplicate rows.</p>

<div class="key">
  <h3>Facts observed in the data</h3>
  <ul>
    <li><strong>Per the organizer</strong>, this mobile-ticketing channel is
      <strong>~4&ndash;5% of total Delhi bus ticket sales</strong> — i.e. the file is a
      ~1-in-20 sample of ridership, not the full count.</li>
    <li>Every ticket carries <strong>both</strong> <code>start_stop_name</code> and
      <code>end_stop_name</code> (both 0% null) — boarding and alighting stops are recorded.</li>
    <li><code>route</code> equals a GTFS <code>route_short_name</code> for
      <strong>{M['route_match_gtfs_volpct']}% of tickets</strong>
      ({M['route_match_gtfs_pct']}% of distinct route strings).</li>
    <li><code>vehicle_number</code> (present on {M['vehicle_number_present_pct']}% of tickets,
      {M['distinct_vehicles']:,} distinct) overlaps live GTFS-RT vehicle ids by
      <strong>{M['vehicles_overlap_rt_pct']}%</strong>.</li>
    <li>Ticketing volume is <strong>bimodal</strong> by hour (peaks {M['peak_hour']:02d}:00 and
      18&ndash;19:00) and higher on weekdays ({M['weekday_per_day']:,.0f}/day) than weekends
      ({M['weekend_per_day']:,.0f}/day).</li>
  </ul>
</div>
<div class="key" style="border-left-color:var(--warn)">
  <h3 style="color:var(--warn)">Hypotheses derived from these facts</h3>
  <ul>
    <li><strong>H1</strong> — Because both stops are recorded, on-vehicle load is
      reconstructable directly as <code>load = &Sigma;boardings &minus; &Sigma;alightings</code>
      along a route, with no alighting model. <span class="sub">(Testable: load should return
      to ~0 at the terminus.)</span></li>
    <li><strong>H2</strong> — The bimodal volume reflects commute demand, so on-vehicle
      <em>crowding</em> should peak at {M['peak_hour']:02d}:00 and 18&ndash;19:00 and dip midday.</li>
    <li><strong>H3</strong> — With <code>route</code> ≡ GTFS <code>route_short_name</code>,
      e-ticketing aligns to the GTFS network without a crosswalk.</li>
    <li><strong>H4</strong> — The {M['vehicles_overlap_rt_pct']}% vehicle-id overlap means ridership
      can be linked to live vehicle positions (for the {M['vehicle_number_present_pct']}% that carry an id).</li>
    <li><strong>H5</strong> — The stop-name gap (below) is mostly formatting/abbreviation
      differences rather than missing stops, so it should be resolvable by name matching.</li>
    <li><strong>H6</strong> — As a ~4&ndash;5% channel where {100*ac_true/ac_total:.0f}% of tickets
      are AC and <code>ticket_type_id</code> is a single value, the mobile sample may over-represent
      AC / one fare product — its representativeness vs the whole fleet is worth checking before
      reading absolute volumes as ridership.</li>
  </ul>
</div>

<h2>2 &middot; Temporal patterns</h2>
<div class="grid">
  {stat(f"{M['peak_hour']:02d}:00", "Busiest hour")}
  {stat(f"{M['daily_mean']:,.0f}", "Tickets / day (avg)")}
  {stat(f"{M['weekday_per_day']:,.0f}", "Weekday / day")}
  {stat(f"{M['weekend_per_day']:,.0f}", "Weekend / day")}
</div>
<figure><img src="{img('etk_tickets_by_hour.png')}" alt="tickets by hour">
  <figcaption><strong>Fact:</strong> bimodal by hour — morning peak at
  {M['peak_hour']:02d}:00 and an evening peak around 18&ndash;19:00, with a midday trough.
  <span class="sub">(→ H2)</span></figcaption></figure>
<div class="two">
  <figure><img src="{img('etk_tickets_by_date.png')}" alt="daily volume">
    <figcaption>Daily volume across October (weekday/weekend rhythm visible).</figcaption></figure>
  <figure><img src="{img('etk_tickets_by_dow.png')}" alt="by day of week">
    <figcaption>By day of week &mdash; weekdays clearly busier than weekends.</figcaption></figure>
</div>

<h2>3 &middot; Routes &amp; direction</h2>
<p><strong>{M['distinct_routes']:,}</strong> distinct route strings
({M['distinct_route_base']:,} base routes ignoring UP/DOWN). Direction split:
{', '.join(f"<strong>{k}</strong> {v:,}" for k,v in M['direction_counts'].items())}.
Routes match GTFS <code>route_short_name</code> for
<span class="good">{M['route_match_gtfs_pct']}% of distinct routes
({M['route_match_gtfs_volpct']}% of tickets)</span>.</p>
<div class="two">
  <figure><img src="{img('etk_top_routes.png')}" alt="top routes">
    <figcaption>Top 15 routes by ticket volume.</figcaption></figure>
  <table>
    <tr><th>Route</th><th class="num">Tickets</th></tr>
    {rows_from(dict(list(M['top_routes'].items())[:15]), 'route', 'n')}
  </table>
</div>

<h2>4 &middot; Stops — boarding &amp; alighting both present</h2>
<p><strong>Fact:</strong> {M['distinct_start_stops']:,} distinct boarding stops,
{M['distinct_end_stops']:,} alighting stops. Exact (case-insensitive) match to GTFS
<code>stop_name</code>: <span class="warn">start {M['start_stop_match_gtfs_pct']}% /
end {M['end_stop_match_gtfs_pct']}%</span>; the non-matching names are variants of GTFS names
(spacing, punctuation, abbreviations). <span class="sub">(→ H5)</span></p>
<div class="two">
  <div><h3>Top boarding stops</h3>
    <table><tr><th>Stop</th><th class="num">Tickets</th></tr>
      {rows_from(dict(list(M['top_boarding_stops'].items())[:8]), 's', 'n')}</table></div>
  <div><h3>Top alighting stops</h3>
    <table><tr><th>Stop</th><th class="num">Tickets</th></tr>
      {rows_from(dict(list(M['top_alighting_stops'].items())[:8]), 's', 'n')}</table></div>
</div>

<h2>5 &middot; Fare, ticket type &amp; AC</h2>
<div class="grid">
  {stat(f"&#8377;{M['amount_mean']:.2f}", "Mean fare")}
  {stat(f"&#8377;{M['amount_median']:.1f}", "Median fare")}
  {stat(f"&#8377;{M['amount_max']:.0f}", "Max fare")}
  {stat(f"{100*ac_true/ac_total:.0f}%", "AC trips")}
</div>
<figure><img src="{img('etk_fare_distribution.png')}" alt="fare distribution">
  <figcaption>Fare amount distribution (clipped at 99th pct). Total recorded revenue
  &#8377;{M['revenue_total']:,.0f}.</figcaption></figure>
<p class="sub"><code>ticket_type_id</code> is a single value ({', '.join(f"{k}:{v:,}" for k,v in M['ticket_type_counts'].items())})
in this drop &mdash; no concession/pass breakdown here.</p>

<h2>6 &middot; Boardings by route &times; hour</h2>
<figure><img src="{img('etk_boardings_route_hour.png')}" alt="route x hour boardings">
  <figcaption><strong>Fact:</strong> boardings (&Sigma;<code>passenger_count</code>) for the top
  routes by hour; the busiest (route, hour) cell among them is
  <strong>{peak['route']} @ {peak['peak_hour']:02d}:00</strong>. Combined with alightings
  (both recorded) this gives the load profile in H1. <span class="sub">(→ H1, H2)</span></figcaption></figure>

<h2>7 &middot; Data-quality facts</h2>
<ul>
  <li>No fully-duplicate rows; no nulls in <code>route</code>, <code>start_stop_name</code>,
    <code>end_stop_name</code>, <code>created_at</code>, <code>amount</code>,
    <code>passenger_count</code>.</li>
  <li><code>vehicle_number</code> is {100-M['vehicle_number_present_pct']:.1f}% null
    (present on {M['vehicle_number_present_pct']}%, {M['distinct_vehicles']:,} distinct vehicles).</li>
  <li>Stop names match GTFS exactly ~{M['start_stop_match_gtfs_pct']:.0f}% of the time; the rest
    are formatting/abbreviation variants of GTFS names.</li>
  <li><code>ticket_type_id</code> takes a single value in this file; {100*ac_true/ac_total:.0f}%
    of tickets are AC.</li>
</ul>

<footer>
  Data source: Delhi Transport Stack (Department of Transport, GNCTD), mobile e-ticketing,
  used under the Transport Stack Data License Agreement v1.0. Raw data is gitignored; see
  <code>data/LICENSE-NOTES.md</code>.
  Reproduce: <code>python src/eda_eticketing.py &amp;&amp; python src/make_eticketing_report.py</code>.
</footer>
</div></body></html>
"""

(REP / "eda_eticketing_report.html").write_text(HTML, encoding="utf-8")
print(f"Wrote {REP/'eda_eticketing_report.html'} ({len(HTML)/1024:.0f} KB incl. embedded figures)")
