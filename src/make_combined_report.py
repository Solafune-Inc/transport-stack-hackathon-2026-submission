"""Build a single combined HTML report:
   Hackathon brief (HACKATHON.md) + Plan (PLAN.md) + full EDA (eda_report.html).

Run:  python src/make_combined_report.py  ->  reports/project_report.html
The EDA report is embedded in an isolated <iframe srcdoc> so its styling and
embedded figures are preserved with no CSS clashes. Fully self-contained.
"""
import html as _html
from pathlib import Path
import markdown

ROOT = Path(__file__).resolve().parents[1]
REP = ROOT / "reports"; REP.mkdir(exist_ok=True)

MD_EXT = ["tables", "fenced_code", "sane_lists", "toc", "attr_list"]
def md(path):
    return markdown.markdown(Path(path).read_text(encoding="utf-8"), extensions=MD_EXT)

hackathon_html = md(ROOT / "HACKATHON.md")
plan_html = md(ROOT / "PLAN.md")
eda_html = (REP / "eda_report.html").read_text(encoding="utf-8")
eda_srcdoc = _html.escape(eda_html, quote=True)

PAGE = f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Transport Stack Hackathon 2026 — Project Report</title>
<style>
  :root {{ --bg:#fff; --fg:#1b1f24; --muted:#5b6670; --card:#f6f8fa; --border:#e2e6ea;
           --accent:#0b7285; --warn:#e8590c; --hl:#fff3bf; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg:#0f1317; --fg:#e6edf3; --muted:#9aa4ad; --card:#161b22; --border:#2a3038;
             --accent:#38bdf0; --warn:#ff922b; --hl:#3a3410; }} }}
  * {{ box-sizing:border-box; }}
  html {{ scroll-behavior:smooth; }}
  body {{ margin:0; background:var(--bg); color:var(--fg);
    font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }}
  .layout {{ display:grid; grid-template-columns:230px 1fr; gap:0; }}
  nav {{ position:sticky; top:0; align-self:start; height:100vh; overflow:auto;
    border-right:1px solid var(--border); padding:1.5rem 1rem; background:var(--card); }}
  nav h2 {{ font-size:.8rem; text-transform:uppercase; letter-spacing:.05em; color:var(--muted);
    margin:0 0 .5rem; border:none; }}
  nav a {{ display:block; color:var(--fg); text-decoration:none; padding:.3rem .5rem;
    border-radius:6px; font-size:.9rem; }}
  nav a:hover {{ background:var(--border); }}
  nav a.sub {{ padding-left:1.1rem; font-size:.84rem; color:var(--muted); }}
  main {{ min-width:0; }}
  .wrap {{ max-width:900px; margin:0 auto; padding:2.5rem 1.5rem 4rem; }}
  header.hero {{ border-bottom:1px solid var(--border); margin-bottom:1rem; }}
  header.hero h1 {{ font-size:2rem; margin:0 0 .25rem; letter-spacing:-.01em; }}
  .sub {{ color:var(--muted); font-size:.93rem; }}
  section {{ padding-top:1rem; }}
  section > h1:first-of-type, .secttl {{ font-size:1.6rem; margin:2.5rem 0 .5rem;
    padding-bottom:.4rem; border-bottom:3px solid var(--accent); }}
  h1,h2,h3 {{ line-height:1.25; }}
  h2 {{ font-size:1.25rem; margin:1.8rem 0 .5rem; border-bottom:1px solid var(--border); padding-bottom:.3rem; }}
  h3 {{ font-size:1.05rem; margin:1.3rem 0 .4rem; color:var(--accent); }}
  table {{ border-collapse:collapse; width:100%; margin:.6rem 0 1.2rem; font-size:.92rem;
    display:block; overflow-x:auto; }}
  th,td {{ text-align:left; padding:.45rem .7rem; border-bottom:1px solid var(--border); }}
  th {{ color:var(--muted); font-weight:600; white-space:nowrap; }}
  code {{ background:var(--card); padding:.1rem .35rem; border-radius:4px; font-size:.88em; }}
  pre {{ background:var(--card); padding:1rem; border-radius:8px; overflow-x:auto;
    border:1px solid var(--border); font-size:.85rem; }}
  pre code {{ background:none; padding:0; }}
  blockquote {{ margin:1rem 0; padding:.5rem 1rem; border-left:4px solid var(--accent);
    background:var(--card); border-radius:6px; color:var(--muted); }}
  a {{ color:var(--accent); }}
  ul li {{ margin:.25rem 0; }}
  hr {{ border:none; border-top:1px solid var(--border); margin:2rem 0; }}
  .edaframe {{ width:100%; border:1px solid var(--border); border-radius:10px; background:var(--bg); }}
  .toolbar {{ display:flex; gap:.6rem; align-items:center; margin:.5rem 0 1rem; }}
  .toolbar a {{ font-size:.85rem; padding:.3rem .7rem; border:1px solid var(--border);
    border-radius:20px; text-decoration:none; color:var(--muted); }}
  @media (max-width:800px) {{ .layout {{ grid-template-columns:1fr; }} nav {{ position:static; height:auto; }} }}
</style></head><body>
<div class="layout">
<nav>
  <h2>Contents</h2>
  <a href="#top"><b>Overview</b></a>
  <a href="#hackathon">1 · Hackathon brief</a>
  <a href="#plan">2 · Prototype plan</a>
  <a href="#eda">3 · EDA report</a>
  <a href="#eda" class="sub">(opens embedded)</a>
</nav>
<main>
<div class="wrap">
<header class="hero" id="top">
  <h1>Transport Stack Hackathon 2026</h1>
  <div class="sub">Project report — Problem 2: Crowdedness-aware journey planner</div>
  <div class="sub">Team Solafune &middot; compiled 2026-11-12 &middot; combines the hackathon brief, the prototype plan, and the GTFS EDA</div>
</header>

<section id="hackathon">
  <div class="secttl">1 · Hackathon brief</div>
  {hackathon_html}
</section>

<hr>

<section id="plan">
  <div class="secttl">2 · Prototype plan</div>
  {plan_html}
</section>

<hr>

<section id="eda">
  <div class="secttl">3 · Exploratory Data Analysis</div>
  <div class="toolbar">
    <span class="sub">Full EDA report (embedded below, self-contained)</span>
    <a href="eda_report.html" target="_blank">Open EDA in new tab ↗</a>
  </div>
  <iframe class="edaframe" id="edaframe" srcdoc="{eda_srcdoc}" style="height:1200px"></iframe>
</section>
</div>
</main>
</div>
<script>
  // auto-size the embedded EDA iframe to its content (same-origin srcdoc)
  const f = document.getElementById("edaframe");
  function resize() {{
    try {{ f.style.height = (f.contentWindow.document.body.scrollHeight + 40) + "px"; }}
    catch (e) {{}}
  }}
  f.addEventListener("load", () => {{ resize(); setTimeout(resize, 400); }});
  window.addEventListener("resize", resize);
</script>
</body></html>"""

out = REP / "project_report.html"
out.write_text(PAGE, encoding="utf-8")
print(f"Wrote {out} ({out.stat().st_size/1e6:.1f} MB)")
