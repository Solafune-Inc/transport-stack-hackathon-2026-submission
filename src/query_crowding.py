"""Query the crowding model — "will my bus be crowded?"

Given a route (and hour), report the per-vehicle crowding level and load profile built
from the real e-ticketing data. Optionally restrict to the leg between a boarding and an
alighting stop to answer the rider's actual question for their trip.

Run:
    python src/query_crowding.py --route 623DOWN                 # all hours, summary
    python src/query_crowding.py --route 623DOWN --hour 18       # one hour + profile
    python src/query_crowding.py --route 623DOWN --hour 18 --from "Laxmi Nagar" --to "Nehru Place Terminal"

Reads data/eticketing/crowding_segments.csv + crowding_route_hour.csv + stop_resolution.csv.
This is the crowding half of the journey planner (routing/A->B is the remaining Stage-2 piece).
"""
from __future__ import annotations
import argparse
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SEG = ROOT / "data" / "eticketing" / "crowding_segments.csv"
RH = ROOT / "data" / "eticketing" / "crowding_route_hour.csv"
RESOLVE = ROOT / "data" / "eticketing" / "stop_resolution.csv"
GTFS = ROOT / "data" / "delhi_buses_static_gtfs"

BAR = {"Low": "▁▁", "Medium": "▄▄", "High": "▆▆", "Very High": "██"}
ICON = {"Low": "🟢", "Medium": "🟡", "High": "🟠", "Very High": "🔴"}


def stop_names():
    s = pd.read_csv(GTFS / "stops.txt", dtype=str)
    return dict(zip(s.stop_id, s.stop_name))


def resolve_stop(route, name):
    r = pd.read_csv(RESOLVE, usecols=["route", "stop_name", "stop_id", "method"],
                    dtype=str)
    hit = r[(r.route == route) & (r.stop_name.str.lower() == name.lower())
            & (r.method != "unresolved")]
    return hit.stop_id.iloc[0] if len(hit) else None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--route", required=True, help="route_short_name, e.g. 623DOWN")
    ap.add_argument("--hour", type=int, help="hour of day 0-23")
    ap.add_argument("--from", dest="src", help="boarding stop name (optional)")
    ap.add_argument("--to", dest="dst", help="alighting stop name (optional)")
    a = ap.parse_args(argv)

    rh = pd.read_csv(RH)
    rr = rh[rh.route == a.route]
    if rr.empty:
        raise SystemExit(f"No crowding data for route {a.route} "
                         f"(check the route_short_name, e.g. 623DOWN / 8UP).")

    print(f"\nRoute {a.route} — crowding (per-vehicle, from Oct e-ticketing)")
    if a.hour is None:
        print("  peak occupancy by hour:")
        for r in rr.sort_values("hour").itertuples():
            conf = "" if r.confidence == "high" else "  (low-confidence: few scheduled trips)"
            print(f"    {int(r.hour):02d}:00  {ICON.get(r.level,'')} {r.level:<10} "
                  f"occ={r.peak_occupancy:>4.2f}  {BAR.get(r.level,'')}{conf}")
        busiest = rr.loc[rr.peak_occupancy.idxmax()]
        print(f"  busiest: {int(busiest.hour):02d}:00 -> {busiest.level} "
              f"(peak {busiest.peak_per_vehicle_load:.0f} pax/bus)")
        print("  tip: add --hour H for the load profile along the route.")
        return

    row = rr[rr.hour == a.hour]
    if row.empty:
        raise SystemExit(f"No data for {a.route} at {a.hour:02d}:00.")
    row = row.iloc[0]
    conf = "high" if row.confidence == "high" else "LOW (few scheduled trips — estimate noisy)"
    print(f"  {a.hour:02d}:00  {ICON.get(row.level,'')} {row.level}  "
          f"(peak {row.peak_per_vehicle_load:.0f} pax/bus, occupancy {row.peak_occupancy:.2f}; "
          f"confidence: {conf})")

    seg = pd.read_csv(SEG)
    prof = seg[(seg.route == a.route) & (seg.hour == a.hour)].sort_values("pos")
    names = stop_names()

    if a.src and a.dst:
        sid1, sid2 = resolve_stop(a.route, a.src), resolve_stop(a.route, a.dst)
        p = prof[prof.stop_id.astype(str).isin([str(sid1), str(sid2)])]
        if len(p) >= 1:
            leg = prof[(prof.pos >= p.pos.min()) & (prof.pos < p.pos.max())] if len(p) >= 2 else p
            lvl = leg.sort_values("occupancy").iloc[-1] if len(leg) else prof.iloc[0]
            print(f"\n  Your leg {a.src} -> {a.to if False else a.dst}: "
                  f"{ICON.get(lvl.level,'')} {lvl.level} "
                  f"(worst segment ~{lvl.per_vehicle_load:.0f} pax/bus)")
        else:
            print("  (could not resolve one of the stops on this route; showing full profile)")

    print("\n  load profile (passengers on board along the route):")
    mx = max(prof.per_vehicle_load.max(), 1)
    for r in prof.itertuples():
        nm = names.get(str(r.stop_id), r.stop_id)
        bar = "█" * int(round(28 * r.per_vehicle_load / mx))
        print(f"    {int(r.pos):>3} {str(nm)[:28]:<28} {r.per_vehicle_load:>5.0f} "
              f"{ICON.get(r.level,'')} {bar}")


if __name__ == "__main__":
    main()
