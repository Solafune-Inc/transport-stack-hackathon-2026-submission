"""EDA of the Delhi mobile e-ticketing dataset (October 2026).

The real Problem-2 crowding input (replaces the removed synthetic data). This EDA
reports facts observed in the data plus the hypotheses derived from them (see the HTML
report); the organizer's ~4-5% coverage figure is cited as context, not used to rescale
anything here. Crucially the data carries BOTH start_stop_name and end_stop_name, so
boardings AND alightings are observed — no alighting estimation needed for this source.

Schema (one row = one ticket):
  passenger_count int | amount str(INR) | vehicle_number str/NULL | ticket_type_id int
  end_stop_name str | route str(e.g. 8UP/433DOWN) | start_stop_name str
  created_at timestamp(+05:30 IST) | is_ac bool

Runs the full file, prints a structured report, writes figures to notebooks/figures/
and machine-readable metrics to reports/eda_eticketing_metrics.json.

Run:  python src/eda_eticketing.py
Data source: Delhi Transport Stack (DoT, GNCTD) — mobile e-ticketing — License v1.0.
"""
from __future__ import annotations
import json, time
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "data" / "eticketing" / "October-Delhi.csv"
GTFS = ROOT / "data" / "delhi_buses_static_gtfs"
RT = ROOT / "data" / "realtime"
FIG = ROOT / "notebooks" / "figures"
REP = ROOT / "reports"
FIG.mkdir(parents=True, exist_ok=True); REP.mkdir(exist_ok=True)

M = {}
t0 = time.time()
def h(t): print("\n" + "=" * 72 + f"\n{t}\n" + "=" * 72)
def rec(k, v): M[k] = v; return v
def savefig(name):
    p = FIG / name; plt.tight_layout(); plt.savefig(p, dpi=110); plt.close()
    print(f"  fig -> {p.relative_to(ROOT)}")


def load() -> pd.DataFrame:
    h("LOAD")
    df = pd.read_csv(
        CSV,
        dtype={"passenger_count": "Int64", "amount": "string", "vehicle_number": "string",
               "ticket_type_id": "Int64", "end_stop_name": "string", "route": "string",
               "start_stop_name": "string", "is_ac": "string"},
        na_values=["NULL", ""], keep_default_na=True,
    )
    print(f"  rows={len(df):,}  cols={list(df.columns)}  mem={df.memory_usage(deep=True).sum()/1e6:.0f} MB")
    # types
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    df["is_ac"] = df["is_ac"].map({"True": True, "False": False}).astype("boolean")
    df["created_at"] = pd.to_datetime(df["created_at"], format="ISO8601", utc=True
                                      ).dt.tz_convert("Asia/Kolkata")
    df["hour"] = df["created_at"].dt.hour
    df["date"] = df["created_at"].dt.date
    df["dow"] = df["created_at"].dt.day_of_week        # 0=Mon
    df["is_weekend"] = df["dow"] >= 5
    # route direction
    df["direction"] = np.where(df.route.str.endswith("UP"), "UP",
                        np.where(df.route.str.endswith("DOWN"), "DOWN", "other"))
    df["route_base"] = (df.route.str.replace("DOWN$", "", regex=True)
                               .str.replace("UP$", "", regex=True))
    return df


def overview(df):
    h("1. OVERVIEW & DATA QUALITY")
    rec("rows", len(df))
    rec("date_min", str(df.created_at.min())); rec("date_max", str(df.created_at.max()))
    print(f"  tickets: {len(df):,}")
    print(f"  period : {df.created_at.min()}  ->  {df.created_at.max()}")
    miss = {c: int(df[c].isna().sum()) for c in df.columns}
    rec("missing", miss)
    print("  missing per column:")
    for c, n in miss.items():
        print(f"    {c:<16} {n:>10,}  ({100*n/len(df):.1f}%)")
    dup = int(df.duplicated().sum()); rec("duplicate_rows", dup)
    print(f"  fully-duplicate rows: {dup:,}")
    rec("passenger_count_value_counts",
        {str(k): int(v) for k, v in df.passenger_count.value_counts().head(10).items()})
    print(f"  passenger_count: mean={df.passenger_count.mean():.2f} "
          f"max={df.passenger_count.max()} (top values: "
          f"{dict(df.passenger_count.value_counts().head(5))})")
    rec("total_passengers", int(df.passenger_count.sum()))
    print(f"  total passengers (sum of passenger_count): {int(df.passenger_count.sum()):,}")


def temporal(df):
    h("2. TEMPORAL PATTERNS (peak / off-peak — the crowding validation story)")
    daily = df.groupby("date").size()
    rec("daily_min", int(daily.min())); rec("daily_max", int(daily.max()))
    rec("daily_mean", float(daily.mean())); rec("n_days", int(daily.size))
    print(f"  days covered: {daily.size}  | tickets/day min={daily.min():,} "
          f"mean={daily.mean():,.0f} max={daily.max():,}")

    byhour = df.groupby("hour").size()
    rec("tickets_by_hour", {int(k): int(v) for k, v in byhour.items()})
    peak_h = int(byhour.idxmax())
    rec("peak_hour", peak_h)
    print(f"  busiest hour: {peak_h}:00  ({byhour.max():,} tickets)")
    print("  hourly profile:", {int(k): int(v) for k, v in byhour.items()})

    wk = df.groupby("is_weekend").size()
    rec("weekday_tickets", int(wk.get(False, 0))); rec("weekend_tickets", int(wk.get(True, 0)))
    wk_per_day = df.groupby(["is_weekend", "date"]).size().groupby("is_weekend").mean()
    rec("weekday_per_day", float(wk_per_day.get(False, float("nan"))))
    rec("weekend_per_day", float(wk_per_day.get(True, float("nan"))))
    print(f"  avg tickets/day — weekday={wk_per_day.get(False, float('nan')):,.0f} "
          f"weekend={wk_per_day.get(True, float('nan')):,.0f}")

    # figures
    plt.figure(figsize=(9, 3.2))
    byhour.plot(kind="bar", color="#1971c2")
    plt.title("E-ticketing volume by hour of day (Oct 2026, IST)")
    plt.xlabel("hour"); plt.ylabel("tickets"); savefig("etk_tickets_by_hour.png")

    plt.figure(figsize=(10, 3.2))
    daily.plot(color="#2f9e44", marker="o", ms=3)
    plt.title("Daily e-ticketing volume (Oct 2026)")
    plt.xlabel("date"); plt.ylabel("tickets"); plt.xticks(rotation=45, ha="right")
    savefig("etk_tickets_by_date.png")

    dow = df.groupby("dow").size().reindex(range(7))
    plt.figure(figsize=(7, 3.2))
    dow.plot(kind="bar", color="#f08c00")
    plt.title("E-ticketing volume by day of week")
    plt.xticks(range(7), ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], rotation=0)
    plt.ylabel("tickets"); savefig("etk_tickets_by_dow.png")


def routes(df):
    h("3. ROUTES  (joinability to GTFS route_short_name)")
    rec("distinct_routes", int(df.route.nunique()))
    rec("distinct_route_base", int(df.route_base.nunique()))
    print(f"  distinct route strings: {df.route.nunique():,}  "
          f"(base routes ignoring UP/DOWN: {df.route_base.nunique():,})")
    dirc = df.direction.value_counts()
    rec("direction_counts", {str(k): int(v) for k, v in dirc.items()})
    print(f"  direction split: {dict(dirc)}")

    top = df.route.value_counts().head(15)
    rec("top_routes", {str(k): int(v) for k, v in top.items()})
    print("  top 15 routes by ticket volume:")
    for r, n in top.items():
        print(f"    {r:<12} {n:>9,}")

    # match to GTFS route_short_name
    gtfs_routes = pd.read_csv(GTFS / "routes.txt", dtype=str)
    gset = set(gtfs_routes.route_short_name.dropna().str.strip())
    uniq = df.route.dropna().unique()
    matched = sum(1 for r in uniq if r in gset)
    rec("route_match_gtfs_pct", round(100 * matched / len(uniq), 1))
    # volume-weighted match
    vol = df.route.value_counts()
    vol_matched = int(vol[[r for r in vol.index if r in gset]].sum())
    rec("route_match_gtfs_volpct", round(100 * vol_matched / len(df), 1))
    print(f"  routes matching GTFS route_short_name: {matched}/{len(uniq)} "
          f"({100*matched/len(uniq):.1f}% of distinct, "
          f"{100*vol_matched/len(df):.1f}% of tickets)")

    plt.figure(figsize=(9, 3.6))
    top.iloc[::-1].plot(kind="barh", color="#1971c2")
    plt.title("Top 15 routes by e-ticket volume")
    plt.xlabel("tickets"); savefig("etk_top_routes.png")


def stops(df):
    h("4. STOPS  (boarding = start, alighting = end — both observed!)")
    rec("distinct_start_stops", int(df.start_stop_name.nunique()))
    rec("distinct_end_stops", int(df.end_stop_name.nunique()))
    print(f"  distinct boarding stops: {df.start_stop_name.nunique():,}  "
          f"alighting stops: {df.end_stop_name.nunique():,}")
    topb = df.start_stop_name.value_counts().head(10)
    topa = df.end_stop_name.value_counts().head(10)
    rec("top_boarding_stops", {str(k): int(v) for k, v in topb.items()})
    rec("top_alighting_stops", {str(k): int(v) for k, v in topa.items()})
    print("  top boarding stops:", {k: int(v) for k, v in topb.head(5).items()})
    print("  top alighting stops:", {k: int(v) for k, v in topa.head(5).items()})

    gstops = pd.read_csv(GTFS / "stops.txt", dtype=str)
    gset = set(gstops.stop_name.dropna().str.strip().str.lower())
    for col, key in [("start_stop_name", "start"), ("end_stop_name", "end")]:
        uniq = df[col].dropna().str.strip().str.lower().unique()
        matched = sum(1 for s in uniq if s in gset)
        rec(f"{key}_stop_match_gtfs_pct", round(100 * matched / len(uniq), 1))
        print(f"  {col} matching GTFS stop_name (exact, lower): "
              f"{matched}/{len(uniq)} ({100*matched/len(uniq):.1f}%)")


def fares(df):
    h("5. FARE / TICKET TYPE / AC")
    a = df.amount.dropna()
    rec("amount_mean", float(a.mean())); rec("amount_median", float(a.median()))
    rec("amount_max", float(a.max())); rec("revenue_total", float(a.sum()))
    print(f"  amount (INR): mean={a.mean():.2f} median={a.median():.2f} "
          f"max={a.max():.0f}  total revenue={a.sum():,.0f}")
    print(f"  amount quantiles: {a.quantile([.25,.5,.75,.95]).round(1).to_dict()}")
    ac = df.is_ac.value_counts(dropna=False)
    rec("is_ac_counts", {str(k): int(v) for k, v in ac.items()})
    print(f"  is_ac: {dict(ac)}")
    tt = df.ticket_type_id.value_counts()
    rec("ticket_type_counts", {str(k): int(v) for k, v in tt.items()})
    print(f"  ticket_type_id: {dict(tt)}")

    plt.figure(figsize=(8, 3.2))
    a.clip(upper=a.quantile(0.99)).plot(kind="hist", bins=40, color="#9c36b5")
    plt.title("Fare amount distribution (clipped at 99th pct)")
    plt.xlabel("INR"); savefig("etk_fare_distribution.png")


def vehicles(df):
    h("6. VEHICLE_NUMBER  (joinability to GTFS-RT vehicle positions)")
    nn = int(df.vehicle_number.notna().sum())
    rec("vehicle_number_present", nn)
    rec("vehicle_number_present_pct", round(100 * nn / len(df), 1))
    rec("distinct_vehicles", int(df.vehicle_number.nunique()))
    print(f"  vehicle_number present: {nn:,} ({100*nn/len(df):.1f}%)  "
          f"distinct vehicles: {df.vehicle_number.nunique():,}")
    # overlap with any RT snapshot we have
    rt_ids = set()
    for p in list(RT.glob("vehicle_history.csv")) + list(RT.glob("vehicle_positions_*.csv")):
        try:
            rt_ids |= set(pd.read_csv(p, usecols=["vehicle_id"]).vehicle_id.astype(str))
        except Exception:
            pass
    if rt_ids:
        etk_v = set(df.vehicle_number.dropna().unique())
        inter = etk_v & rt_ids
        rec("vehicles_overlap_rt", len(inter))
        rec("vehicles_overlap_rt_pct", round(100 * len(inter) / max(1, len(etk_v)), 1))
        print(f"  overlap with GTFS-RT vehicle ids: {len(inter):,} "
              f"({100*len(inter)/max(1,len(etk_v)):.1f}% of e-ticket vehicles) "
              f"[RT ids available: {len(rt_ids):,}]")
    else:
        print("  (no RT snapshot found for overlap check)")


def crowding_foundation(df):
    h("7. CROWDING FOUNDATION  (boardings per route x hour)")
    # boardings weighted by passenger_count
    g = df.dropna(subset=["route"]).groupby(["route", "hour"]).passenger_count.sum()
    top_routes = df.route.value_counts().head(12).index.tolist()
    mat = (g.reset_index()
             .pivot(index="route", columns="hour", values="passenger_count")
             .reindex(top_routes).reindex(columns=range(24)).fillna(0).astype(float))
    rec("peak_route_hour_example",
        {"route": str(mat.sum(axis=1).idxmax()),
         "peak_hour": int(mat.loc[mat.sum(axis=1).idxmax()].idxmax())})
    print(f"  built boardings matrix for top {len(top_routes)} routes x 24h")
    print(f"  busiest (route,hour) among them: route={mat.sum(axis=1).idxmax()} "
          f"hour={int(mat.loc[mat.sum(axis=1).idxmax()].idxmax())}")

    plt.figure(figsize=(10, 4.5))
    plt.imshow(mat.values, aspect="auto", cmap="YlOrRd")
    plt.colorbar(label="boardings (sum passenger_count)")
    plt.yticks(range(len(mat.index)), mat.index)
    plt.xticks(range(0, 24, 2), range(0, 24, 2))
    plt.xlabel("hour of day"); plt.title("Boardings by route x hour (top routes) — crowding seed")
    savefig("etk_boardings_route_hour.png")


def main():
    if not CSV.exists():
        raise SystemExit(f"Missing {CSV}")
    df = load()
    overview(df)
    temporal(df)
    routes(df)
    stops(df)
    fares(df)
    vehicles(df)
    crowding_foundation(df)

    rec("runtime_sec", round(time.time() - t0, 1))
    out = REP / "eda_eticketing_metrics.json"
    out.write_text(json.dumps(M, indent=2, default=str))
    h("DONE")
    print(f"  metrics -> {out.relative_to(ROOT)}  | figures -> notebooks/figures/etk_*.png")
    print(f"  runtime: {M['runtime_sec']}s")


if __name__ == "__main__":
    main()
