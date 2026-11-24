"""Verification report for e-ticketing -> GTFS stop resolution.

Lets you eyeball match quality: coverage, method breakdown, the fuzzy matches that
need a human check (top by volume + riskiest by lowest score), what stayed unresolved,
and a spatial scatter of resolved stops coloured by method.

Run:  python src/make_stop_resolution_report.py  ->  reports/stop_resolution_report.html
Reads data/eticketing/stop_resolution.csv + reports/stop_resolution_metrics.json.
"""
import base64, io, json
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
REP = ROOT / "reports"
CSV = ROOT / "data" / "eticketing" / "stop_resolution.csv"
M = json.loads((REP / "stop_resolution_metrics.json").read_text())

df = pd.read_csv(CSV)
df["vehicle_safe"] = None  # placeholder (unused) to keep columns stable if re-read

COLOR = {"exact_route": "#2b8a3e", "fuzzy_route": "#f08c00",
         "exact_global": "#1971c2", "fuzzy_global": "#9c36b5", "unresolved": "#adb5bd"}

def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

def stat(n, l):
    return f'<div class="stat"><div class="n">{n}</div><div class="l">{l}</div></div>'

def match_table(sub, cols_note=""):
    rows = ""
    for r in sub.itertuples():
        rows += (f"<tr><td>{esc(r.stop_name)}</td>"
                 f"<td class='arrow'>&rarr;</td>"
                 f"<td>{esc(r.gtfs_stop_name)}</td>"
                 f"<td class='mono'>{esc(r.route)}</td>"
                 f"<td class='num'>{r.score}</td>"
                 f"<td class='num'>{int(r.occurrences):,}</td></tr>")
    return (f"<table><tr><th>e-ticket stop</th><th></th><th>GTFS stop</th>"
            f"<th>route</th><th class='num'>score</th><th class='num'>occ</th></tr>{rows}</table>"
            f"<p class='sub'>{cols_note}</p>")

def unresolved_table(sub):
    rows = "".join(f"<tr><td>{esc(r.stop_name)}</td><td class='mono'>{esc(r.route)}</td>"
                   f"<td class='num'>{int(r.occurrences):,}</td></tr>" for r in sub.itertuples())
    return f"<table><tr><th>e-ticket stop</th><th>route</th><th class='num'>occ</th></tr>{rows}</table>"

# --- spatial scatter of resolved stops, coloured by method ---
res = df[df.method != "unresolved"].dropna(subset=["lat", "lon"])
plt.figure(figsize=(8, 8))
for m in ["exact_route", "fuzzy_route", "exact_global", "fuzzy_global"]:
    s = res[res.method == m]
    if len(s):
        plt.scatter(s.lon, s.lat, s=4, c=COLOR[m], alpha=0.4, label=f"{m} ({len(s):,})", linewidths=0)
plt.legend(markerscale=3, fontsize=9, loc="upper right")
plt.title("Resolved e-ticketing stops by match method")
plt.xlabel("lon"); plt.ylabel("lat"); plt.gca().set_aspect(1.1)
buf = io.BytesIO(); plt.tight_layout(); plt.savefig(buf, format="png", dpi=110); plt.close()
scatter_uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

fuzzy = df[df.method.isin(["fuzzy_route", "fuzzy_global"])]
top_fuzzy = fuzzy.sort_values("occurrences", ascending=False).head(50)
risky = fuzzy.sort_values(["score", "occurrences"], ascending=[True, False]).head(50)
unresolved = df[df.method == "unresolved"].sort_values("occurrences", ascending=False).head(50)

mb = M["method_distinct"]; mo = M["method_occ_pct"]
method_rows = "".join(
    f"<tr><td><span class='dot' style='background:{COLOR[m]}'></span>{m}</td>"
    f"<td class='num'>{mb.get(m,0):,}</td><td class='num'>{mo.get(m,0)}%</td></tr>"
    for m in ["exact_route", "fuzzy_route", "exact_global", "fuzzy_global", "unresolved"])

HTML = f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Stop Resolution — Verification</title>
<style>
  :root {{ --bg:#fff; --fg:#1b1f24; --muted:#5b6670; --card:#f6f8fa; --border:#e2e6ea;
           --accent:#0b7285; --good:#2b8a3e; --warn:#e8590c; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg:#0f1317; --fg:#e6edf3; --muted:#9aa4ad; --card:#161b22; --border:#2a3038;
             --accent:#38bdf0; --good:#51cf66; --warn:#ff922b; }} }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--fg);
    font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }}
  .wrap {{ max-width:1000px; margin:0 auto; padding:2.5rem 1.25rem 4rem; }}
  h1 {{ margin:0 0 .25rem; font-size:1.9rem; }} h2 {{ margin:2.2rem 0 .5rem; font-size:1.25rem;
    border-bottom:2px solid var(--border); padding-bottom:.3rem; }}
  .sub {{ color:var(--muted); font-size:.9rem; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(130px,1fr)); gap:.7rem; margin:1rem 0; }}
  .stat {{ background:var(--card); border:1px solid var(--border); border-radius:10px; padding:.8rem .95rem; }}
  .stat .n {{ font-size:1.5rem; font-weight:700; }}
  .stat .l {{ color:var(--muted); font-size:.72rem; text-transform:uppercase; letter-spacing:.04em; }}
  table {{ border-collapse:collapse; width:100%; margin:.4rem 0 1rem; font-size:.88rem; }}
  th,td {{ text-align:left; padding:.35rem .6rem; border-bottom:1px solid var(--border); vertical-align:top; }}
  th {{ color:var(--muted); font-weight:600; }}
  td.num, th.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  td.mono {{ font-family:ui-monospace,Menlo,monospace; font-size:.82rem; color:var(--muted); }}
  td.arrow {{ color:var(--muted); padding:0 .2rem; }}
  .dot {{ display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:.4rem; vertical-align:middle; }}
  figure {{ margin:1rem 0; background:var(--card); border:1px solid var(--border); border-radius:10px; padding:1rem; }}
  figure img {{ max-width:100%; height:auto; display:block; margin:0 auto; }}
  .key {{ background:var(--card); border-left:4px solid var(--accent); border-radius:8px; padding:.8rem 1.1rem; margin:1rem 0; }}
  details {{ margin:.6rem 0; }} summary {{ cursor:pointer; color:var(--accent); font-weight:600; }}
  code {{ background:var(--card); padding:.1rem .35rem; border-radius:4px; font-size:.85em; }}
  footer {{ margin-top:3rem; color:var(--muted); font-size:.8rem; border-top:1px solid var(--border); padding-top:1rem; }}
</style></head><body><div class="wrap">

<h1>Stop Resolution — Verification</h1>
<div class="sub">e-ticketing <code>(route, stop_name)</code> &rarr; GTFS <code>stop_id</code> + coordinates
&middot; from <code>src/resolve_stops.py</code></div>

<div class="grid">
  {stat(f"{M['ticket_weighted_resolved_pct']}%", "Resolved (ticket-wtd)")}
  {stat(f"{M['distinct_resolved_pct']}%", "Resolved (distinct)")}
  {stat(f"{M['distinct_pairs']:,}", "Distinct pairs")}
  {stat(f"{M['total_occurrences']:,}", "Total occurrences")}
</div>

<h2>1 &middot; Method breakdown</h2>
<table><tr><th>Method</th><th class="num">Distinct pairs</th><th class="num">% of tickets</th></tr>
{method_rows}</table>
<div class="key sub">
  <b>How to read:</b> <b>exact_route</b> = name matched a stop the GTFS route serves (trust).
  <b>fuzzy_route</b> = closest name on that route (check below). <b>*_global</b> = matched any
  GTFS stop when the route had no candidate. <b>unresolved</b> = no confident match (left out
  on purpose — a wrong stop is worse than none).
</div>

<h2>2 &middot; Spatial sanity</h2>
<figure><img src="{scatter_uri}" alt="resolved stops scatter">
  <figcaption class="sub">Resolved stops by method. Should fill the Delhi NCR footprint with
  no stray points; fuzzy/global (orange/blue/purple) are the ones to spot-check.</figcaption></figure>

<h2>3 &middot; Fuzzy matches — top by volume (eyeball these)</h2>
<p class="sub">The highest-impact fuzzy matches. Each row: the e-ticket name and the GTFS
stop it was mapped to. Most should read as obviously the same place.</p>
{match_table(top_fuzzy)}

<h2>4 &middot; Riskiest matches — lowest score (most likely wrong)</h2>
<p class="sub">Lowest-confidence matches, by volume. If any of these look wrong, the
threshold or abbreviation list can be tuned.</p>
{match_table(risky)}

<h2>5 &middot; Unresolved — top by volume (what's still missing)</h2>
<p class="sub">Mostly ambiguous abbreviations (e.g. <code>S.J.</code> = Safdarjung?) or stops
possibly absent from GTFS. Total unresolved: {mo.get('unresolved',0)}% of tickets.</p>
{unresolved_table(unresolved)}

<footer>
  Source: Delhi Transport Stack (DoT, GNCTD), License v1.0. Raw/derived data gitignored.
  Reproduce: <code>python src/resolve_stops.py &amp;&amp; python src/make_stop_resolution_report.py</code>.
</footer>
</div></body></html>"""

OUT = REP / "stop_resolution_report.html"
OUT.write_text(HTML, encoding="utf-8")
print(f"Wrote {OUT} ({len(HTML)/1024:.0f} KB)")
