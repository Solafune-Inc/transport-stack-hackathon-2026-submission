"""Crowding model — turn e-ticketing boardings/alightings into per-vehicle load profiles.

Method (PLAN.md §3), now on REAL data:
  For a route+direction (e.g. 717AUP) and a time band (hour of day), aggregate the
  month's mobile-ticket boardings and alightings onto the route's GTFS stop sequence,
  then walk the sequence accumulating on-board load:

     load(after stop i) = Σ_{j<=i} boardings(j)  −  Σ_{j<=i} alightings(j)

  Because mobile ticketing is only a ~COVERAGE sample and the figure above is a monthly
  total, convert to a *per-vehicle* load for an average bus in that hour:

     per_vehicle_load(i) = load(i) / COVERAGE / trips_month(route, hour)
     occupancy           = per_vehicle_load(i) / CAPACITY
     crowding_level      = bucket(occupancy)

  trips_month comes from the GTFS schedule (scheduled trips starting in that hour × days).
  COVERAGE, CAPACITY and the buckets are documented assumptions (see constants) — the
  model is most trustworthy as a *relative* ordering (which route-hours/segments are more
  crowded), which is what the journey planner needs.

  Day types (ML_PLAN.md §1b, P1-2): the monthly profile averages weekdays, Saturdays and
  Sundays/holidays together. Each (route, hour) profile is multiplied by a factor per day type,
  which keeps the load >= 0 and back to 0 at the terminus:
     b2       (default) the B2 demand model's boardings per day on that day type over the monthly
              average, per route-hour (src/ml/demand.py; chosen in src/ml/compare_models.py)
     network  rate(hour, day type) / rate(hour, all days), the same for every route
  A route-hour is high-confidence only with >= MIN_TRIPS_DAY scheduled buses/day and
  >= MIN_PAX_MONTH ticketed passengers in the month (sparse cells are noisy).

Inputs : data/eticketing/October-Delhi.csv, data/eticketing/stop_resolution.csv,
         data/delhi_buses_static_gtfs/
Outputs: data/eticketing/crowding_segments.csv   (route,hour,pos,stop_id,load,per_vehicle_load,occupancy,level)
         data/eticketing/crowding_route_hour.csv  (route,hour -> peak occupancy + level + n_segments)
         data/eticketing/crowding_stop_hour.csv   (stop_id,hour -> estimated boardings/alightings per day)
         data/eticketing/crowding_*_daytype.csv   the three tables above per day type (served by the API)
         data/eticketing/crowding_model.json      which day-type model wrote them
         data/eticketing/crowding_operator.csv    weekday route-hours over capacity, for operators
         reports/crowding_metrics.json
         notebooks/figures/crowd_*.png
Run:    python src/model/crowding.py [--daytype-model b2|network]
Data source: Delhi Transport Stack (DoT, GNCTD) — License v1.0.
"""
from __future__ import annotations
import argparse, datetime as dt, json, sys, time
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

if __package__ in (None, ""):  # run as a script: make src/ importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml.daytypes import DAY_TYPES, day_type  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
GTFS = ROOT / "data" / "delhi_buses_static_gtfs"
ETK = ROOT / "data" / "eticketing" / "October-Delhi.csv"
RESOLVE = ROOT / "data" / "eticketing" / "stop_resolution.csv"
OUT_SEG = ROOT / "data" / "eticketing" / "crowding_segments.csv"
OUT_RH = ROOT / "data" / "eticketing" / "crowding_route_hour.csv"
OUT_STOP = ROOT / "data" / "eticketing" / "crowding_stop_hour.csv"
OUT_SEG_D = ROOT / "data" / "eticketing" / "crowding_segments_daytype.csv"
OUT_RH_D = ROOT / "data" / "eticketing" / "crowding_route_hour_daytype.csv"
OUT_STOP_D = ROOT / "data" / "eticketing" / "crowding_stop_hour_daytype.csv"
OUT_MODEL = ROOT / "data" / "eticketing" / "crowding_model.json"
OUT_OPS = ROOT / "data" / "eticketing" / "crowding_operator.csv"
FIG = ROOT / "notebooks" / "figures"; FIG.mkdir(parents=True, exist_ok=True)
REP = ROOT / "reports"; REP.mkdir(exist_ok=True)

# --- documented assumptions ---
COVERAGE = 0.045        # mobile ticketing ≈ 4–5% of ticket sales (EDA / organizer note)
CAPACITY = 60           # standard Delhi bus: ~35 seated + ~25 standing (documented constant)
DAYS = 31               # October
MIN_TRIPS_DAY = 2       # route-hours with fewer scheduled trips/day are low-confidence
                        # (tiny denominator -> unstable per-vehicle estimate)
MIN_PAX_MONTH = 30      # ... and so are route-hours with fewer ticketed passengers in the month
                        # (median route-hour has 21: "Low" there often means "few mobile tickets")
MIN_ROUTE_HOURS = 20    # hourly validation means need this many high-confidence route-hours
                        # (at 01:00 only one night route qualifies)
# occupancy buckets (per-vehicle load / capacity)
LEVELS = [(0.50, "Low"), (0.80, "Medium"), (1.00, "High"), (float("inf"), "Very High")]

M = {}
def rec(k, v): M[k] = v; return v
def h(t): print("\n" + "=" * 72 + f"\n{t}\n" + "=" * 72)
def savefig(name):
    p = FIG / name; plt.tight_layout(); plt.savefig(p, dpi=110); plt.close()
    print(f"  fig -> {p.relative_to(ROOT)}")


def level_of(occ: float) -> str:
    for thr, name in LEVELS:
        if occ < thr:
            return name
    return LEVELS[-1][1]


def levels_of(occ) -> np.ndarray:
    """level_of() for an array of occupancies."""
    names = np.array([name for _, name in LEVELS])
    return names[np.searchsorted([thr for thr, _ in LEVELS[:-1]], np.asarray(occ, float), side="right")]


def confidence_of(trips_day, pax_month) -> np.ndarray:
    """'high' if the route-hour has enough scheduled buses and enough ticketed passengers."""
    ok = (np.asarray(trips_day) >= MIN_TRIPS_DAY) & (np.asarray(pax_month) >= MIN_PAX_MONTH)
    return np.where(ok, "high", "low")


def build_route_sequences():
    """route_short_name -> {stop_id: position} using the longest trip of that route."""
    routes = pd.read_csv(GTFS / "routes.txt", dtype=str)
    r2short = dict(zip(routes.route_id, routes.route_short_name))
    trips = pd.read_csv(GTFS / "trips.txt", dtype=str, usecols=["route_id", "trip_id"])
    t2short = {t: r2short.get(r) for t, r in zip(trips.trip_id, trips.route_id)}
    st = pd.read_csv(GTFS / "stop_times.txt", dtype=str,
                     usecols=["trip_id", "stop_id", "stop_sequence", "departure_time"])
    st["stop_sequence"] = pd.to_numeric(st.stop_sequence, errors="coerce")
    st["short"] = st.trip_id.map(t2short)
    st = st.dropna(subset=["short"])

    # trips/hour (frequency): hour of each trip's first departure
    firsts = st.sort_values("stop_sequence").groupby("trip_id").first()
    firsts["hour"] = pd.to_numeric(firsts.departure_time.str.slice(0, 2), errors="coerce") % 24
    trips_per_hour = (firsts.dropna(subset=["hour"])
                      .groupby(["short", "hour"]).size().astype(int))  # per service day
    tph = {}
    for (short, hr), n in trips_per_hour.items():
        tph.setdefault(short, {})[int(hr)] = int(n)

    # canonical sequence = longest trip per route
    n_stops = st.groupby("trip_id").size()
    seqs = {}
    # pick, per short, the trip_id with the most stops
    trip_short = st.groupby("trip_id").short.first()
    best = (pd.DataFrame({"short": trip_short, "n": n_stops}).dropna()
            .sort_values("n").groupby("short").tail(1))
    best_trips = set(best.index)
    sub = st[st.trip_id.isin(best_trips)].sort_values(["trip_id", "stop_sequence"])
    for tid, g in sub.groupby("trip_id"):
        short = g.short.iloc[0]
        seq = {}
        for sid in g.stop_id:
            if sid not in seq:
                seq[sid] = len(seq)      # first occurrence = position
        seqs[short] = seq
    return seqs, tph


def load_resolved_tickets(seqs):
    """Return tickets with board_pos / alight_pos on their route's sequence."""
    res = pd.read_csv(RESOLVE, usecols=["route", "stop_name", "stop_id", "method"],
                      dtype={"route": str, "stop_name": str, "stop_id": str, "method": str})
    res = res[res.method != "unresolved"]
    key2sid = {(r.route, r.stop_name): r.stop_id for r in res.itertuples()}

    df = pd.read_csv(ETK, usecols=["route", "start_stop_name", "end_stop_name",
                                   "created_at", "passenger_count"],
                     dtype={"route": "string", "start_stop_name": "string",
                            "end_stop_name": "string", "passenger_count": "Int64"})
    df["hour"] = pd.to_numeric(df.created_at.str.slice(11, 13), errors="coerce")
    df = df.dropna(subset=["hour"]); df["hour"] = df.hour.astype(int)
    df["pax"] = df.passenger_count.fillna(1).astype(int)

    def sid(route, name):
        return key2sid.get((route, name))
    df["board_sid"] = [sid(r, s) for r, s in zip(df.route, df.start_stop_name)]
    df["alight_sid"] = [sid(r, s) for r, s in zip(df.route, df.end_stop_name)]

    def pos(route, s):
        seq = seqs.get(route)
        return seq.get(s) if (seq and s is not None) else None
    df["board_pos"] = [pos(r, s) for r, s in zip(df.route, df.board_sid)]
    df["alight_pos"] = [pos(r, s) for r, s in zip(df.route, df.alight_sid)]
    return df


def stop_busyness(df):
    """Estimated people boarding / alighting per day at each stop and hour, all routes.

    Every resolved ticket counts at its stop (whatever its route's sequence), scaled up by the
    mobile-ticket share and averaged over the month. Alightings are counted in the hour the
    ticket was bought.
    """
    scale = 1.0 / COVERAGE / DAYS
    b = df.dropna(subset=["board_sid"]).groupby(["board_sid", "hour"]).pax.sum().rename("boardings")
    a = df.dropna(subset=["alight_sid"]).groupby(["alight_sid", "hour"]).pax.sum().rename("alightings")
    b.index.names = a.index.names = ["stop_id", "hour"]
    out = pd.concat([b, a], axis=1).fillna(0) * scale
    return out.round(1).reset_index()


def compute_segments(df, seqs, tph):
    """Per (route,hour): cumulative load along positions -> per-vehicle load, occupancy, level."""
    usable = df.dropna(subset=["board_pos", "alight_pos"]).copy()
    usable["board_pos"] = usable.board_pos.astype(int)
    usable["alight_pos"] = usable.alight_pos.astype(int)
    rec("tickets_total", int(len(df)))
    rec("tickets_usable", int(len(usable)))
    rec("tickets_usable_pct", round(100 * len(usable) / len(df), 1))
    # keep only sane direction (board before alight along the sequence)
    forward = usable[usable.board_pos < usable.alight_pos]
    rec("tickets_forward_pct", round(100 * len(forward) / len(usable), 1))

    board = forward.groupby(["route", "hour", "board_pos"]).pax.sum()
    alight = forward.groupby(["route", "hour", "alight_pos"]).pax.sum()

    rows = []
    groups = sorted(set(board.index.droplevel(2)) | set(alight.index.droplevel(2)))
    for (route, hour) in groups:
        seq = seqs.get(route)
        if not seq:
            continue
        n = len(seq)
        b = np.zeros(n); a = np.zeros(n)
        try:
            for pos, v in board.loc[(route, hour)].items(): b[int(pos)] = v
        except KeyError: pass
        try:
            for pos, v in alight.loc[(route, hour)].items(): a[int(pos)] = v
        except KeyError: pass
        load = np.cumsum(b) - np.cumsum(a)          # sampled monthly on-board load by segment
        trips_day = tph.get(route, {}).get(int(hour), 0)
        trips_month = trips_day * DAYS
        if trips_month <= 0:
            continue
        pvl = load / COVERAGE / trips_month          # per-vehicle load
        # confidence: a per-vehicle estimate needs enough scheduled buses/hour (with too few GTFS
        # trips the denominator is tiny and the estimate blows up) and enough tickets (with a
        # handful of passengers a month the profile is mostly noise).
        pax_month = float(b.sum())
        conf = str(confidence_of(trips_day, pax_month))
        id_by_pos = {p: s for s, p in seq.items()}
        for i in range(n):
            if load[i] <= 0:
                continue
            occ = pvl[i] / CAPACITY
            rows.append((route, int(hour), i, id_by_pos.get(i),
                         round(float(load[i]), 1), round(float(pvl[i]), 1),
                         round(float(occ), 3), level_of(occ), trips_day, pax_month, conf))
    seg = pd.DataFrame(rows, columns=["route", "hour", "pos", "stop_id",
                                      "load_sampled", "per_vehicle_load", "occupancy",
                                      "level", "trips_day", "pax_month", "confidence"])
    return seg, forward


def network_daytype_factors(df) -> pd.DataFrame:
    """(hour, daytype, factor): network boardings per day in that hour on that day type, over
    boardings per day in that hour across the whole month. The B2 model's day-type layer (and
    step P1-2): on held-out days it cut route-hour error 22% vs the monthly average."""
    b = df.dropna(subset=["board_pos"])
    dates = b.created_at.str.slice(0, 10)
    uniq = dates.unique()
    dmap = dict(zip(uniq, day_type(uniq)))
    n_days = np.bincount(list(dmap.values()), minlength=3)
    assert n_days.sum() == DAYS, f"expected {DAYS} days of tickets, got {n_days.sum()}"
    d = dates.map(dmap).to_numpy(int)
    hd = np.bincount(b.hour.to_numpy(int) * 3 + d, weights=b.pax.to_numpy(float), minlength=72).reshape(24, 3)
    per_day_d = hd / n_days
    per_day = hd.sum(axis=1, keepdims=True) / DAYS
    fac = np.divide(per_day_d, per_day, out=np.ones_like(per_day_d), where=per_day > 0)
    hours, dts = np.meshgrid(np.arange(24), np.arange(3), indexing="ij")
    out = pd.DataFrame({"hour": hours.ravel(), "daytype": np.array(DAY_TYPES)[dts.ravel()],
                        "factor": fac.ravel()})
    out.attrs["n_days"] = dict(zip(DAY_TYPES, n_days.tolist()))
    return out


def scale_by_daytype(seg, factors):
    """Segment and route-hour tables per day type: each (route, hour) profile times its factor.

    `factors` has (hour, daytype, factor), or (route, hour, daytype, factor) covering every
    route-hour in `seg`. A positive factor keeps the load >= 0 and 0 at the terminus.
    """
    keys = ["route", "hour"] if "route" in factors else ["hour"]
    s = seg.merge(factors, on=keys)
    s["per_vehicle_load"] = (s.per_vehicle_load * s.factor).round(1)
    s["occupancy"] = (s.occupancy * s.factor).round(3)
    s["level"] = levels_of(s.occupancy)
    s = s.sort_values(["route", "daytype", "hour", "pos"], kind="stable")
    seg_d = s[["route", "daytype", "hour", "pos", "stop_id", "per_vehicle_load", "occupancy", "level"]]
    rh_d = (s.groupby(["route", "daytype", "hour"], sort=False)
            .agg(peak_occupancy=("occupancy", "max"), peak_per_vehicle_load=("per_vehicle_load", "max"),
                 trips_day=("trips_day", "first"), pax_month=("pax_month", "first"),
                 n_segments=("pos", "count"), confidence=("confidence", "first")).reset_index())
    rh_d.insert(len(rh_d.columns) - 1, "level", levels_of(rh_d.peak_occupancy))
    return seg_d.reset_index(drop=True), rh_d


def hourly_mean_peak(rh, min_route_hours=MIN_ROUTE_HOURS):
    """Mean route-hour peak occupancy per hour, for hours with enough route-hours to average."""
    g = rh.groupby("hour").peak_occupancy
    return g.mean()[g.size() >= min_route_hours]


def validate_and_figures(seg, rh, forward, seqs):
    h("VALIDATION")
    hi = rh[rh.confidence == "high"]        # headline stats on high-confidence route-hours
    # 1. peak occupancy by hour (route-hour peak, averaged over routes)
    by_hour = hourly_mean_peak(hi)
    rec("peak_occ_by_hour", {int(k): round(float(v), 3) for k, v in by_hour.items()})
    busiest = int(by_hour.idxmax())
    rec("busiest_hour", busiest)
    print(f"  mean peak occupancy by hour (high-conf) — busiest = {busiest}:00 ({by_hour.max():.2f})")
    print("  ", {int(k): round(float(v), 2) for k, v in by_hour.items()})

    plt.figure(figsize=(9, 3.2))
    by_hour.reindex(range(24)).plot(kind="bar", color="#c92a2a")
    plt.axhline(1.0, color="#333", ls="--", lw=.8)
    plt.title("Mean per-vehicle peak occupancy by hour (crowding validation)")
    plt.xlabel("hour"); plt.ylabel("occupancy (load/capacity)"); savefig("crowd_occ_by_hour.png")

    # 2. load-profile shape for a well-sampled busy route at a peak hour (high-confidence,
    #    plausible occupancy) — avoids degenerate low-frequency route-hours.
    vol = forward.groupby(["route", "hour"]).pax.sum().rename("vol")
    cand = hi[hi.hour.isin([8, 9, 18]) & (hi.peak_occupancy.between(0.6, 1.6))].merge(
        vol.reset_index(), on=["route", "hour"], how="left").sort_values("vol", ascending=False)
    top_rh = cand.iloc[0] if len(cand) else hi.sort_values("peak_occupancy").iloc[-1]
    tr, th = top_rh.route, int(top_rh.hour)
    prof = seg[(seg.route == tr) & (seg.hour == th)].sort_values("pos")
    rec("example_route", str(tr)); rec("example_hour", th)
    plt.figure(figsize=(9, 3.4))
    plt.plot(prof.pos, prof.per_vehicle_load, marker="o", ms=3, color="#1971c2")
    plt.axhline(CAPACITY, color="#c92a2a", ls="--", lw=.8, label=f"capacity={CAPACITY}")
    plt.title(f"Per-vehicle load profile — route {tr} @ {th:02d}:00")
    plt.xlabel("stop position along route"); plt.ylabel("passengers on board")
    plt.legend(); savefig("crowd_profile_example.png")

    # 3. route x hour peak-occupancy heatmap (top high-confidence routes by overall peak)
    top_routes = (hi.groupby("route").peak_occupancy.max().sort_values(ascending=False)
                  .head(15).index.tolist())
    mat = (hi[hi.route.isin(top_routes)]
           .pivot(index="route", columns="hour", values="peak_occupancy")
           .reindex(top_routes).reindex(columns=range(24)).fillna(0).astype(float))
    plt.figure(figsize=(10, 4.8))
    plt.imshow(mat.values, aspect="auto", cmap="YlOrRd", vmin=0, vmax=max(1.2, mat.values.max()))
    plt.colorbar(label="peak occupancy")
    plt.yticks(range(len(mat.index)), mat.index); plt.xticks(range(0, 24, 2), range(0, 24, 2))
    plt.xlabel("hour"); plt.title("Peak occupancy by route × hour (top routes)")
    savefig("crowd_route_hour_heatmap.png")

    # 4. load returns to ~0 at the end of the route? (model sanity)
    ends = []
    for (route, hour), g in forward.groupby(["route", "hour"]):
        seq = seqs.get(route)
        if not seq: continue
        n = len(seq)
        b = g.groupby("board_pos").pax.sum().sum()
        a = g.groupby("alight_pos").pax.sum().sum()
        if b > 0:
            ends.append((a) / b)   # fraction of boardings that have a recorded alighting
    frac = float(np.mean(ends)) if ends else float("nan")
    rec("mean_alight_to_board_ratio", round(frac, 3))
    print(f"  alightings / boardings (should be ~1.0 if load returns to 0): {frac:.2f}")

    # level distribution
    dist = seg.level.value_counts()
    rec("level_distribution", {k: int(v) for k, v in dist.items()})
    print(f"  segment crowding levels: {dict(dist)}")
    print("  per-vehicle load describe:")
    print(seg.per_vehicle_load.describe().round(1).to_string())
    print("  occupancy quantiles:", seg.occupancy.quantile([.5, .8, .95, .99]).round(2).to_dict())


def b2_factors(df, seqs, tph, seg, rh, net):
    """(route, hour, daytype, factor) from the B2 demand model for every route-hour in `seg`
    (network factor for any route-hour B2 has no tickets for)."""
    from ml.demand import b2_daytype_factors   # here, not at the top: ml.demand imports this module
    full = seg[["route", "hour"]].drop_duplicates().merge(net, on="hour")
    full = full.merge(b2_daytype_factors(seqs, tph, df), on=["route", "hour", "daytype"], how="left",
                      suffixes=("_network", ""))
    rec("b2_factor_fallback_route_hours", int(full.factor.isna().sum()))
    full["factor"] = full.factor.fillna(full.factor_network)
    vol = full.merge(rh[["route", "hour", "pax_month"]], on=["route", "hour"])
    q = {}
    for lo, hi, label in ((1, 29, "1-29"), (30, 99, "30-99"), (100, np.inf, "100+")):
        f = vol.factor[vol.pax_month.between(lo, hi)]
        q[label] = dict(zip(["q05", "q25", "q50", "q75", "q95"], np.quantile(f, [.05, .25, .5, .75, .95]).round(3).tolist()))
    rec("b2_factor_quantiles_by_pax_month", q)
    print(f"  B2 factors for {len(full) // 3:,} route-hours "
          f"({M['b2_factor_fallback_route_hours']} rows fell back to the network factor); "
          f"median by monthly pax: " + ", ".join(f"{k}: {v['q50']}" for k, v in q.items()))
    return full[["route", "hour", "daytype", "factor"]]


def operator_table(rh_d) -> pd.DataFrame:
    """Weekday route-hours over capacity on their busiest stretch (high confidence), for operators:
    riders above capacity per day there (how many people an extra bus in that hour could help),
    how full that stretch would be with one more bus, and the same hour on Saturday and Sunday.
    Absolute numbers carry the 4.5% coverage assumption, so read the order, not the counts."""
    occ = rh_d[rh_d.confidence == "high"].pivot_table(index=["route", "hour"], columns="daytype",
                                                         values="peak_occupancy")
    wk = rh_d[(rh_d.daytype == "weekday") & (rh_d.confidence == "high") & (rh_d.peak_occupancy > 1.0)]
    n, load = wk.trips_day, wk.peak_per_vehicle_load
    out = pd.DataFrame({
        "route": wk.route, "hour": wk.hour, "buses_per_day": n,
        "peak_occupancy": wk.peak_occupancy, "peak_per_vehicle_load": load,
        "riders_over_capacity_per_day": ((load - CAPACITY) * n).round(0),
        "occupancy_with_one_more_bus": (load * n / (n + 1) / CAPACITY).round(2),
    })
    sat_sun = occ.reindex(pd.MultiIndex.from_frame(out[["route", "hour"]]))
    out["saturday_occupancy"] = sat_sun["saturday"].to_numpy().round(2)
    out["sunday_holiday_occupancy"] = sat_sun["sunday_holiday"].to_numpy().round(2)
    return out.sort_values("riders_over_capacity_per_day", ascending=False).reset_index(drop=True)


def validate_daytypes(seg_d, rh_d):
    assert (seg_d.per_vehicle_load >= 0).all(), "negative load after day-type scaling"
    rec("min_per_vehicle_load_daytype", float(seg_d.per_vehicle_load.min()))
    hi = rh_d[rh_d.confidence == "high"]
    by = pd.DataFrame({d: hourly_mean_peak(hi[hi.daytype == d]) for d in DAY_TYPES}).reindex(range(24))
    rec("peak_occ_by_hour_by_daytype",
        {d: {int(k): round(float(v), 3) for k, v in by[d].dropna().items()} for d in DAY_TYPES})
    rec("level_distribution_by_daytype",
        {d: {k: int(v) for k, v in g.level.value_counts().items()} for d, g in rh_d.groupby("daytype")})
    for hr in (9, 18):
        wk = by.loc[hr, "weekday"]
        print(f"  {hr:02d}:00 mean peak occupancy (high-conf): "
              + ", ".join(f"{d} {by.loc[hr, d]:.2f} ({by.loc[hr, d] / wk:.2f}x weekday)" for d in DAY_TYPES))
    print("  route-hour levels by day type:", M["level_distribution_by_daytype"])

    plt.figure(figsize=(9, 3.2))
    for d, color in zip(DAY_TYPES, ("#c92a2a", "#e8590c", "#1971c2")):
        plt.plot(by.index, by[d], marker="o", ms=3, color=color, label=d.replace("_", " / "))
    plt.axhline(1.0, color="#333", ls="--", lw=.8)
    plt.title("Mean per-vehicle peak occupancy by hour and day type (high-confidence route-hours)")
    plt.xlabel("hour"); plt.ylabel("occupancy (load/capacity)"); plt.legend()
    savefig("crowd_occ_by_hour_daytype.png")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--daytype-model", choices=["b2", "network"], default="b2",
                    help="where the day-type factor comes from (default: %(default)s)")
    daytype_model = ap.parse_args(argv).daytype_model
    t0 = time.time()
    h("1. GTFS route sequences + trips/hour")
    seqs, tph = build_route_sequences()
    print(f"  routes with a sequence: {len(seqs):,}  | routes with trips/hour: {len(tph):,}")
    rec("routes_with_sequence", len(seqs))

    h("2. Load resolved tickets onto route sequences")
    df = load_resolved_tickets(seqs)
    print(f"  tickets: {len(df):,}  "
          f"board_pos set: {df.board_pos.notna().mean()*100:.1f}%  "
          f"alight_pos set: {df.alight_pos.notna().mean()*100:.1f}%")

    busy = stop_busyness(df)
    busy.to_csv(OUT_STOP, index=False)
    rec("stops_with_busyness", int(busy.stop_id.nunique()))
    print(f"  stop busyness: {busy.stop_id.nunique():,} stops -> {OUT_STOP.relative_to(ROOT)}")

    h("3. Compute per-vehicle load profiles + crowding levels")
    seg, forward = compute_segments(df, seqs, tph)
    print(f"  usable tickets: {M['tickets_usable']:,} ({M['tickets_usable_pct']}%); "
          f"forward (board<alight): {M['tickets_forward_pct']}%")
    print(f"  crowding segments (load>0): {len(seg):,} over "
          f"{seg[['route','hour']].drop_duplicates().shape[0]:,} route-hours")

    rh = (seg.groupby(["route", "hour"])
          .agg(peak_occupancy=("occupancy", "max"),
               peak_per_vehicle_load=("per_vehicle_load", "max"),
               trips_day=("trips_day", "first"),
               pax_month=("pax_month", "first"),
               n_segments=("pos", "count")).reset_index())
    rh["level"] = rh.peak_occupancy.map(level_of)
    rh["confidence"] = confidence_of(rh.trips_day, rh.pax_month)
    seg.to_csv(OUT_SEG, index=False)
    rh.to_csv(OUT_RH, index=False)
    nconf = int((rh.confidence == "high").sum())
    rec("route_hours_total", len(rh)); rec("route_hours_high_conf", nconf)
    rec("route_hours_low_few_trips", int((rh.trips_day < MIN_TRIPS_DAY).sum()))
    rec("route_hours_low_few_tickets", int(((rh.trips_day >= MIN_TRIPS_DAY) & (rh.pax_month < MIN_PAX_MONTH)).sum()))
    print(f"  wrote {OUT_SEG.relative_to(ROOT)} and {OUT_RH.relative_to(ROOT)}")
    print(f"  route-hours: {len(rh):,} ({nconf:,} high-confidence; low: "
          f"{M['route_hours_low_few_trips']:,} too few scheduled trips, "
          f"{M['route_hours_low_few_tickets']:,} too few tickets)")

    validate_and_figures(seg, rh, forward, seqs)

    h(f"4. Day types ({daytype_model} factor)")
    rec("daytype_model", daytype_model)
    net = network_daytype_factors(df)
    rec("days_by_daytype", net.attrs["n_days"])
    rec("network_daytype_factor_by_hour",
        {d: [round(float(x), 3) for x in g.sort_values("hour").factor] for d, g in net.groupby("daytype")})
    factors = net
    if daytype_model == "b2":
        factors = b2_factors(df, seqs, tph, seg, rh, net)
    seg_d, rh_d = scale_by_daytype(seg, factors)
    busy_d = busy.merge(net, on="hour")
    busy_d[["boardings", "alightings"]] = busy_d[["boardings", "alightings"]].mul(busy_d.factor, axis=0).round(1)
    seg_d.to_csv(OUT_SEG_D, index=False)
    rh_d.to_csv(OUT_RH_D, index=False)
    busy_d[["stop_id", "daytype", "hour", "boardings", "alightings"]].to_csv(OUT_STOP_D, index=False)
    model = {"daytype_model": daytype_model,
             "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "daytypes": list(DAY_TYPES), "days_by_daytype": net.attrs["n_days"],
             "min_trips_day": MIN_TRIPS_DAY, "min_pax_month": MIN_PAX_MONTH}
    if daytype_model == "b2":
        from ml.demand import B2_TUNED
        model["b2_params"] = B2_TUNED
    OUT_MODEL.write_text(json.dumps(model, indent=2) + "\n")
    print(f"  wrote {OUT_SEG_D.relative_to(ROOT)}, {OUT_RH_D.relative_to(ROOT)}, "
          f"{OUT_STOP_D.relative_to(ROOT)}, {OUT_MODEL.relative_to(ROOT)}")
    validate_daytypes(seg_d, rh_d)
    ops = operator_table(rh_d)
    ops.to_csv(OUT_OPS, index=False)
    rec("operator_overloaded_weekday_route_hours", len(ops))
    rec("operator_top", ops.head(15).to_dict("records"))
    print(f"  operators: {len(ops):,} weekday route-hours over capacity (high confidence) -> "
          f"{OUT_OPS.relative_to(ROOT)}; top: "
          + ", ".join(f"{r.route} {r.hour:02d}:00" for r in ops.head(5).itertuples()))

    rec("runtime_sec", round(time.time() - t0, 1))
    (REP / "crowding_metrics.json").write_text(json.dumps(M, indent=2, default=str))
    h("DONE")
    print(f"  metrics -> reports/crowding_metrics.json  | runtime {M['runtime_sec']}s")


if __name__ == "__main__":
    main()
