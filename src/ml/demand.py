"""Boarding demand models shared by the crowding pipeline and the experiment (ML_PLAN.md §1b, M1).

Cells are (route, stop position, hour, day type): every (route, position, hour) the GTFS timetable
serves plus any seen in the ticket window, x 3 day types. Rates are mobile-ticket boardings per day
(hour = ticket purchase hour).

  B0  today's approach: average over all days (no day types)
  B2  empirical Bayes (hierarchical Poisson-Gamma). Each cell is shrunk toward
      [route x hour x day-type volume] x [the route's stop share in that time band]. Those are
      shrunk toward route volume x the network's hourly profile, and route volume toward
      scheduled trips x network passengers per trip. The demand model chosen by
      src/ml/compare_models.py (27% lower route-hour error than B0 on the held-out week).

b2_daytype_factors() turns B2 into the (route, hour, day type) multiplier that
src/model/crowding.py applies to its monthly load profiles.
Data source: Delhi Transport Stack (DoT, GNCTD), License v1.0.
"""
from __future__ import annotations
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ml.daytypes import DAY_TYPES, day_type
from model.crowding import GTFS, load_resolved_tickets

MONTH = "2026-10"
# time bands: 0 = 05-10, 1 = 11-15, 2 = 16-20, 3 = 21-04
BAND = np.array([3] * 5 + [0] * 6 + [1] * 5 + [2] * 5 + [3] * 3)
NB = 4
# smoothing strengths tuned on 1-17 -> 18-24 Oct (tuned_params.B2 in reports/ml_model_comparison.json)
B2_TUNED = {"k0": 0.3, "kA": 3.0, "kB": 100.0, "kS0": 30.0, "kS": 300.0, "kC": 30.0}


@dataclass
class Static:
    routes: list[str]
    P: int                    # position slots per route (longest route)
    stop_of: np.ndarray       # route * P + pos -> stop code (-1 = none)
    n_stops: np.ndarray       # per route
    trips_day: np.ndarray     # per route: scheduled trips per day
    direction: np.ndarray     # per route: 0 UP, 1 DOWN, 2 other
    night: np.ndarray         # per route: night service "(NS)"
    stop_lat: np.ndarray
    stop_lon: np.ndarray
    stop_routes: np.ndarray   # per stop: route variants stopping there
    stop_sched: np.ndarray    # (stop, hour): buses per day leaving the stop, all routes
    sched_keys: np.ndarray    # sorted (route, pos, hour) keys the timetable serves
    sched_n: np.ndarray       # buses per day for each of those keys


def load_static(seqs: dict, tph: dict) -> Static:
    routes = sorted(seqs)
    rcode = {r: i for i, r in enumerate(routes)}
    P = max(len(s) for s in seqs.values())
    stops = pd.read_csv(GTFS / "stops.txt", dtype={"stop_id": str})
    scode = {s: i for i, s in enumerate(stops.stop_id)}
    pos_table = pd.DataFrame([(r, sid, p) for r, seq in seqs.items() for sid, p in seq.items()],
                             columns=["route_short_name", "stop_id", "pos"])
    s_of_pos = pos_table.stop_id.map(scode)
    assert s_of_pos.notna().all(), "route sequence stop missing from stops.txt"
    stop_of = np.full(len(routes) * P, -1, np.int64)
    stop_of[pos_table.route_short_name.map(rcode).to_numpy() * P + pos_table.pos.to_numpy()] = s_of_pos.to_numpy(int)
    stop_routes = np.zeros(len(scode))
    n = pos_table.groupby("stop_id").route_short_name.nunique()
    stop_routes[n.index.map(scode).to_numpy(int)] = n.to_numpy()

    trips = pd.read_csv(GTFS / "trips.txt", dtype=str, usecols=["route_id", "trip_id"])
    rts = pd.read_csv(GTFS / "routes.txt", dtype=str, usecols=["route_id", "route_short_name"])
    st = pd.read_csv(GTFS / "stop_times.txt", dtype=str, usecols=["trip_id", "stop_id", "departure_time"])
    st = st.drop_duplicates(["trip_id", "stop_id"])
    st["hour"] = st.departure_time.str.split(":").str[0].astype(int) % 24
    s = st.stop_id.map(scode).fillna(-1).to_numpy(int)
    ok = s >= 0
    stop_sched = np.bincount(s[ok] * 24 + st.hour.to_numpy()[ok], minlength=len(scode) * 24)
    st = st.merge(trips, on="trip_id").merge(rts, on="route_id").merge(pos_table, on=["route_short_name", "stop_id"])
    key3 = (st.route_short_name.map(rcode).to_numpy() * P + st.pos.to_numpy()) * 24 + st.hour.to_numpy()
    sched_keys, sched_n = np.unique(key3, return_counts=True)
    return Static(
        routes=routes, P=P, stop_of=stop_of,
        n_stops=np.array([len(seqs[r]) for r in routes]),
        trips_day=np.array([sum(tph.get(r, {}).values()) for r in routes], float),
        direction=np.array([0 if r.endswith("UP") else 1 if r.endswith("DOWN") else 2 for r in routes]),
        night=np.array(["(NS)" in r.upper() for r in routes], np.int8),
        stop_lat=stops.stop_lat.to_numpy(float), stop_lon=stops.stop_lon.to_numpy(float),
        stop_routes=stop_routes, stop_sched=stop_sched.reshape(-1, 24).astype(float),
        sched_keys=sched_keys, sched_n=sched_n.astype(float))


def load_tickets(seqs: dict, st: Static, df: pd.DataFrame | None = None):
    """Resolved boardings as (route, pos, hour) keys with their day of month and passengers.
    `df`: the month's tickets from load_resolved_tickets(), if already loaded."""
    rcode = {r: i for i, r in enumerate(st.routes)}
    df = (load_resolved_tickets(seqs) if df is None else df).dropna(subset=["board_pos"])
    assert df.created_at.str.slice(0, 7).eq(MONTH).all()
    r = df.route.map(rcode)
    assert r.notna().all()
    day = df.created_at.str.slice(8, 10).astype(int).to_numpy()
    key3 = (r.to_numpy(int) * st.P + df.board_pos.to_numpy(int)) * 24 + df.hour.to_numpy(int)
    dt_of_day = np.zeros(32, int)
    dt_of_day[1:] = day_type(pd.date_range(f"{MONTH}-01", periods=31))
    tk = {"key3": key3, "key4": key3 * 3 + dt_of_day[day], "day": day, "pax": df.pax.to_numpy(float)}
    return tk, dt_of_day


class Fold:
    """Cells (route, pos, hour, day type) for one training window, with their group codes."""

    def __init__(self, st: Static, tk: dict, train_days: np.ndarray, dt_of_day: np.ndarray):
        self.st, self.dt_of_day, self.R = st, dt_of_day, len(st.routes)
        k3 = np.union1d(st.sched_keys, np.unique(tk["key3"][np.isin(tk["day"], train_days)]))
        self.n3 = len(k3)
        self.keys = (k3[:, None] * 3 + np.arange(3)).ravel()
        self.n = len(self.keys)
        self.i3 = np.arange(self.n) // 3
        self.d = self.keys % 3
        key3 = self.keys // 3
        self.h = key3 % 24
        self.rp = key3 // 24
        self.pos = self.rp % st.P
        self.r = self.rp // st.P
        self.s = st.stop_of[self.rp]
        assert (self.s >= 0).all()
        self.band = BAND[self.h]
        self.g_rh = self.r * 24 + self.h
        self.g_rhd = self.g_rh * 3 + self.d
        self.g_rpb = self.rp * NB + self.band
        self.g_rb = self.r * NB + self.band
        self.g_hd = self.h * 3 + self.d
        self.g_shd = self.s * 72 + self.g_hd
        self.g_sb = self.s * NB + self.band
        i = np.minimum(np.searchsorted(st.sched_keys, key3), len(st.sched_keys) - 1)
        self.sched = np.where(st.sched_keys[i] == key3, st.sched_n[i], 0.0)
        self.stop_sched = st.stop_sched[self.s, self.h]
        self.relpos = self.pos / np.maximum(st.n_stops[self.r] - 1, 1)

    def counts(self, tk: dict, days: np.ndarray):
        """Passengers per cell over `days`, days per day type, and passengers outside the cells."""
        sel = np.isin(tk["day"], days)
        k, pax = tk["key4"][sel], tk["pax"][sel]
        i = np.minimum(np.searchsorted(self.keys, k), self.n - 1)
        hit = self.keys[i] == k
        y = np.bincount(i[hit], weights=pax[hit], minlength=self.n)
        E = np.bincount(self.dt_of_day[days], minlength=3).astype(float)
        return y, E, float(pax[~hit].sum()), float(pax.sum())


def b0_rates(y, E, f: Fold):
    return np.bincount(f.i3, y, f.n3)[f.i3] / E.sum()


def b2_rates(y, E, f: Fold, p: dict):
    """Hierarchical Poisson-Gamma (empirical Bayes) boardings per day for every cell."""
    st, R = f.st, f.R
    Etot = E.sum()
    net_h = np.bincount(f.h, y, 24) / Etot
    with np.errstate(divide="ignore", invalid="ignore"):
        net_hd = np.bincount(f.g_hd, y, 72).reshape(24, 3) / E
        dfac = np.nan_to_num(net_hd / net_h[:, None], nan=1.0, posinf=1.0)
    prof_h = net_h / net_h.sum()
    # route volume <- scheduled trips x network passengers per scheduled trip
    present = np.bincount(f.r, minlength=R) > 0
    beta = y.sum() / Etot / max(st.trips_day[present].sum(), 1.0)
    Y_r = np.bincount(f.r, y, R)
    R_r = (Y_r + p["k0"] * beta * np.maximum(st.trips_day, 1.0)) / (Etot + p["k0"])
    # route x hour <- route volume x network hourly profile
    g = np.arange(R * 24)
    R_rh = (np.bincount(f.g_rh, y, R * 24) + p["kA"] * R_r[g // 24] * prof_h[g % 24]) / (Etot + p["kA"])
    # route x hour x day type <- route x hour x network day-type factor at that hour
    g = np.arange(R * 72)
    gh, gd = (g // 3) % 24, g % 3
    R_rhd = (np.bincount(f.g_rhd, y, R * 72) + p["kB"] * R_rh[g // 3] * dfac[gh, gd]) / (E[gd] + p["kB"])
    # stop share within route <- network profile by relative position (deciles)
    nrp = R * st.P
    rp = np.arange(nrp)
    r_of = rp // st.P
    cells = np.bincount(f.rp, minlength=nrp) > 0
    relbin = np.minimum((rp % st.P) / np.maximum(st.n_stops[r_of] - 1, 1) * 10, 9).astype(int)
    Y_rp = np.bincount(f.rp, y, nrp)
    gbin = np.bincount(relbin[cells], Y_rp[cells], 10) / np.maximum(np.bincount(relbin[cells], minlength=10), 1)
    u = np.where(cells, gbin[relbin] + 1e-9, 0.0)
    u /= np.maximum(np.bincount(r_of, u, R)[r_of], 1e-300)
    share0 = (Y_rp + p["kS0"] * u) / (Y_r[r_of] + p["kS0"])
    # ... and within route and time band <- the route's all-day share
    g = np.arange(nrp * NB)
    Y_rb = np.bincount(f.g_rb, y, R * NB)
    share = (np.bincount(f.g_rpb, y, nrp * NB) + p["kS"] * share0[g // NB]) / (Y_rb[(g // NB // st.P) * NB + g % NB] + p["kS"])
    # the cell itself <- route x hour x day type volume x stop share
    prior = R_rhd[f.g_rhd] * share[f.g_rpb]
    return (y + p["kC"] * prior) / (E[f.d] + p["kC"])


def b2_daytype_factors(seqs: dict, tph: dict, df: pd.DataFrame | None = None, params: dict = B2_TUNED) -> pd.DataFrame:
    """(route, hour, daytype, factor): B2's boardings per day on that day type over B0's monthly
    average, both summed over the route's stops and fitted on the whole month, for every route-hour
    with tickets. Multiplying a route-hour's monthly load profile by it gives B2's day-type level."""
    st = load_static(seqs, tph)
    tk, dt_of_day = load_tickets(seqs, st, df)
    days = np.arange(1, 32)
    f = Fold(st, tk, days, dt_of_day)
    y, E, _, _ = f.counts(tk, days)
    G = f.R * 72
    b0 = np.bincount(f.g_rhd, b0_rates(y, E, f), G)
    b2 = np.bincount(f.g_rhd, b2_rates(y, E, f, params), G)
    g = np.flatnonzero(b0 > 0)
    return pd.DataFrame({"route": np.array(st.routes)[g // 72], "hour": (g // 3) % 24,
                         "daytype": np.array(DAY_TYPES)[g % 3], "factor": b2[g] / b0[g]})
