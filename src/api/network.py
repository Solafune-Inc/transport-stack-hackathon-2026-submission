"""Every Delhi bus route as geometry + crowding + timetable, for the live API.

For each GTFS route (e.g. 623UP) this loads the canonical stop sequence the crowding model uses
(so stop positions line up with crowding_segments.csv), the shape of a trip that follows it,
each stop's distance along that shape, the per-hour occupancy of every segment, and one service
day of departures per stop position. On top of that:

- `locate()` puts a GPS fix on its route (snapped position, distance along it, segment);
- `stop_info()` lists every route number through a stop, in both directions, with the expected
  crowding of arriving buses and the next departures;
- `plan()` finds direct buses between two stops (either side of the road), with crowding, and
  with `transfers=True` also trips with one change of bus (api/journeys.py).

Crowding depends on the day type (`d`: 0 weekday, 1 Saturday, 2 Sunday/holiday; ml/daytypes.py)
of the day the bus runs, from the crowding_*_daytype.csv tables of src/model/crowding.py.
"""
from __future__ import annotations
import datetime as dt
import json
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from api.journeys import TransferPlanner
from data.routes import crowding_hours, norm_name, project_stops, route_parts, simplify, to_xy
from ml.daytypes import DAY_TYPES, day_type_of
from model.crowding import build_route_sequences, level_of

ROOT = Path(__file__).resolve().parents[2]
GTFS = ROOT / "data" / "delhi_buses_static_gtfs"
ETK = ROOT / "data" / "eticketing"

MAX_OFF_ROUTE_M = 200     # farther than this from the route's shape -> not snapped, no crowding
SAME_STOP_M = 400         # stops with the same name this close are one place (both sides of a road)
DAY = 86400


@dataclass
class RouteGeom:
    short: str
    route_id: str
    canonical_trip: str
    stop_ids: list[str]
    stop_dist: np.ndarray   # metres along the shape, one per stop position
    pts: np.ndarray         # shape points [[lat, lon]]
    cum: np.ndarray         # metres along the shape at each point
    x: np.ndarray
    y: np.ndarray
    lat0: float

    def __post_init__(self):
        self.dx, self.dy = np.diff(self.x), np.diff(self.y)
        l2 = self.dx * self.dx + self.dy * self.dy
        self.l2 = np.where(l2 == 0, 1e-9, l2)


class Network:
    def __init__(self):
        t0 = time.time()
        self.seqs, self.tph = build_route_sequences()
        routes = pd.read_csv(GTFS / "routes.txt", dtype=str)
        self.short_of_route_id = dict(zip(routes.route_id, routes.route_short_name))
        self.desc_of = dict(zip(routes.route_short_name, routes.route_desc.fillna("")))
        trips = pd.read_csv(GTFS / "trips.txt", dtype=str, usecols=["route_id", "trip_id", "shape_id"])
        st = pd.read_csv(GTFS / "stop_times.txt", dtype=str,
                         usecols=["trip_id", "stop_id", "stop_sequence", "departure_time"])
        st["stop_sequence"] = st.stop_sequence.astype(int)
        st = st.sort_values(["trip_id", "stop_sequence"])
        order_of = st.groupby("trip_id", sort=False).stop_id.agg(lambda s: tuple(dict.fromkeys(s)))
        self.n_routes_at = st.merge(trips[["trip_id", "route_id"]], on="trip_id").groupby("stop_id").route_id.nunique()

        # first trip (trips.txt order) that reproduces the canonical sequence, as in the export
        want = {short: tuple(seq) for short, seq in self.seqs.items()}
        canonical = {}
        for rid, tid, shape_id in trips.itertuples(index=False):
            short = self.short_of_route_id.get(rid)
            if short in want and short not in canonical and order_of.get(tid) == want[short]:
                canonical[short] = (rid, tid, shape_id)

        stops = pd.read_csv(GTFS / "stops.txt", dtype=str)
        stops["stop_lat"] = stops.stop_lat.astype(float)
        stops["stop_lon"] = stops.stop_lon.astype(float)
        self.stops = stops.set_index("stop_id")[["stop_name", "stop_lat", "stop_lon"]]
        stop_ll = self.stops[["stop_lat", "stop_lon"]]
        shapes = pd.read_csv(GTFS / "shapes.txt", dtype={"shape_id": str}).sort_values(
            ["shape_id", "shape_pt_sequence"])
        shape_pts = {sid: g[["shape_pt_lat", "shape_pt_lon"]].to_numpy(float)
                     for sid, g in shapes.groupby("shape_id", sort=False)}

        self.routes: dict[str, RouteGeom] = {}
        for short, (rid, tid, shape_id) in canonical.items():
            pts = shape_pts.get(shape_id)
            order = list(self.seqs[short])
            if pts is None or len(pts) < 2:
                continue
            cum, stop_d, _ = project_stops(pts, stop_ll.loc[order].to_numpy(float))
            lat0 = float(np.mean(pts[:, 0]))
            x, y = to_xy(pts[:, 0], pts[:, 1], lat0)
            self.routes[short] = RouteGeom(short, rid, tid, order, stop_d, pts, cum, x, y, lat0)

        self._index_stops()
        self._build_timetable(st, trips)
        del st

        self._load_crowding()
        self.transfers = TransferPlanner(self)
        self.load_seconds = round(time.time() - t0, 1)

    def _load_crowding(self):
        """Crowding by (route, day type, hour); without the day-type tables (crowding.py not re-run
        yet) every day type gets the whole-month average."""
        def table(name: str, **dtype) -> pd.DataFrame | None:
            daytype_csv, all_days_csv = ETK / f"{name}_daytype.csv", ETK / f"{name}.csv"
            if daytype_csv.exists():
                t = pd.read_csv(daytype_csv, dtype={"daytype": str, **dtype})
            elif all_days_csv.exists():
                t = pd.concat([pd.read_csv(all_days_csv, dtype=dtype).assign(daytype=n) for n in DAY_TYPES])
            else:
                return None
            return t.assign(d=t.daytype.map({n: i for i, n in enumerate(DAY_TYPES)}).astype(int))

        model_json = ETK / "crowding_model.json"
        self.model = json.loads(model_json.read_text()) if model_json.exists() else {"daytype_model": "none"}
        seg = table("crowding_segments", route=str, stop_id=str)
        rh = table("crowding_route_hour", route=str)
        self.seg_by_route = {k: g for k, g in seg.groupby(["route", "d"])}
        self.rh_by_route = {k: g.set_index("hour") for k, g in rh.groupby(["route", "d"])}
        self.occ: dict[tuple[str, int, int], np.ndarray] = {}
        pos, occ = seg.pos.to_numpy(int), seg.occupancy.to_numpy(float)
        for (route, d, hour), ix in seg.groupby(["route", "d", "hour"], sort=False).indices.items():
            geom = self.routes.get(route)
            if geom is None:
                continue
            a = np.zeros(len(geom.stop_ids))
            a[pos[ix]] = occ[ix]
            self.occ[(route, int(d), int(hour))] = a
        # confidence depends on scheduled buses and the month's tickets, not on the day type
        self.confidence = {(r, int(h)): c for r, h, c in
                           rh[rh.d == 0][["route", "hour", "confidence"]].itertuples(index=False)}
        self.busyness: dict[str, np.ndarray] = {}
        busy = table("crowding_stop_hour", stop_id=str)
        if busy is not None:
            for sid, g in busy.groupby("stop_id"):
                a = np.zeros((len(DAY_TYPES), 24, 2))
                a[g.d.to_numpy(int), g.hour.to_numpy(int)] = g[["boardings", "alightings"]].to_numpy(float)
                self.busyness[sid] = a

    def _index_stops(self):
        """stop -> route variants stopping there; route number -> its variants; names -> stops."""
        self.pos_of = {short: {sid: i for i, sid in enumerate(g.stop_ids)} for short, g in self.routes.items()}
        self.number_of, self.direction_of = {}, {}
        self.variants_at: dict[str, list[str]] = {}
        self.variants_of: dict[str, list[str]] = {}
        for short in sorted(self.routes):
            number, direction = route_parts(short)
            self.number_of[short], self.direction_of[short] = number, direction
            self.variants_of.setdefault(number, []).append(short)
            for sid in self.pos_of[short]:
                self.variants_at.setdefault(sid, []).append(short)
        for vs in self.variants_of.values():   # UP before DOWN, main variant before 2, 3
            vs.sort(key=lambda v: (self.direction_of[v] != "UP", len(v), v))
        self.stops["norm"] = self.stops.stop_name.map(norm_name)
        self.by_name = self.stops.groupby("norm").groups

    def _build_timetable(self, st: pd.DataFrame, trips: pd.DataFrame):
        """route -> int32 [trips x stop positions] departure seconds (-1 = not served), one service day."""
        first = st.drop_duplicates(["trip_id", "stop_id"]).merge(trips[["trip_id", "route_id"]], on="trip_id")
        first["short"] = first.route_id.map(self.short_of_route_id)
        pos = pd.DataFrame([(short, sid, i) for short, p in self.pos_of.items() for sid, i in p.items()],
                           columns=["short", "stop_id", "pos"])
        first = first.merge(pos, on=["short", "stop_id"])
        hms = first.departure_time.str.split(":", expand=True).astype(int).to_numpy()
        first["dep"] = hms[:, 0] * 3600 + hms[:, 1] * 60 + hms[:, 2]
        self.timetable: dict[str, np.ndarray] = {}
        for short, g in first.groupby("short", sort=False):
            codes, uniq = pd.factorize(g.trip_id)
            m = np.full((len(uniq), len(self.routes[short].stop_ids)), -1, np.int32)
            m[codes, g.pos.to_numpy(int)] = g.dep.to_numpy(np.int32)
            m = m[(m >= 0).sum(axis=1) >= 2]
            start = np.where(m >= 0, m, np.iinfo(np.int32).max).min(axis=1)
            self.timetable[short] = m[np.argsort(start, kind="stable")]

    def next_departures(self, short: str, pos: int, t: int, n: int = 3) -> list[int]:
        """Next scheduled departures from stop position `pos` at or after t (seconds since midnight,
        may be > 86400 for tomorrow)."""
        m = self.timetable.get(short)
        if m is None:
            return []
        col = m[:, pos]
        col = col[col >= 0]
        return [int(x) for x in np.sort(t + np.mod(col - t, DAY))[:n]]

    def stop_group(self, stop_id: str) -> list[str]:
        """The stop and same-named stops within SAME_STOP_M (e.g. the stop across the road)."""
        if stop_id not in self.stops.index:
            return []
        row = self.stops.loc[stop_id]
        ids = list(self.by_name.get(row.norm, [stop_id]))
        ll = self.stops.loc[ids, ["stop_lat", "stop_lon"]].to_numpy(float)
        x, y = to_xy(ll[:, 0], ll[:, 1], row.stop_lat)
        x0, y0 = to_xy(row.stop_lat, row.stop_lon, row.stop_lat)
        near = np.hypot(x - x0, y - y0) <= SAME_STOP_M
        return [sid for sid, ok in zip(ids, near) if ok and sid in self.variants_at] or [stop_id]

    def stops_payload(self) -> dict:
        """Every stop at least one route stops at: [id, name, lat, lon, route variants]."""
        rows = [[sid, r.stop_name, round(float(r.stop_lat), 5), round(float(r.stop_lon), 5),
                 len(self.variants_at[sid])]
                for sid, r in self.stops.iterrows() if sid in self.variants_at]
        return {"fields": ["id", "name", "lat", "lon", "n_routes"], "stops": rows}

    def _hour_occ(self, short: str, d: int, hour: int, a: int, b: int) -> float:
        """Worst expected occupancy over segments [a, b) of a route in that hour (0 = no tickets)."""
        occ = self.occ.get((short, d, hour))
        return float(occ[a:b].max()) if occ is not None and b > a else 0.0

    def stop_info(self, stop_id: str, t: int, d: int) -> dict | None:
        """The stop, its busyness by hour, and every route number through it in all directions,
        for day type d."""
        if stop_id not in self.variants_at:
            return None
        hour = (t // 3600) % 24
        r = self.stops.loc[stop_id]
        busy = self.busyness.get(stop_id)
        numbers = sorted({self.number_of[v] for v in self.variants_at[stop_id]},
                         key=lambda n: (len(n), n))
        routes = []
        for number in numbers:
            for v in self.variants_of[number]:
                p = self.pos_of[v].get(stop_id)
                n = len(self.routes[v].stop_ids)
                served = p is not None
                occ = self.occ.get((v, d, hour))
                routes.append({
                    "id": v, "number": number, "direction": self.direction_of[v],
                    "description": self.desc_of.get(v, ""), "serves": served, "pos": p, "n_stops": n,
                    "occ": float(occ[p - 1]) if served and p > 0 and occ is not None else None,
                    "confidence": self.confidence.get((v, hour), "none"),
                    "next": self.next_departures(v, p, t) if served and p < n - 1 else [],
                })
        return {
            "stop": {"id": stop_id, "name": r.stop_name, "lat": round(float(r.stop_lat), 5),
                     "lon": round(float(r.stop_lon), 5), "n_routes_all": int(self.n_routes_at.get(stop_id, 0))},
            "t": int(t), "daytype": DAY_TYPES[d],
            "busyness": None if busy is None else [[round(float(b), 1), round(float(a), 1)] for b, a in busy[d]],
            "routes": routes,
        }

    def plan(self, from_id: str, to_id: str, t: int, date: dt.date, window_min: int = 120,
             max_options: int = 80, transfers: bool = False) -> dict:
        """Direct buses from one stop to another (each with its same-named stops nearby), leaving
        within `window_min` after t on `date`, with the worst expected crowding on the ride. Each
        bus gets the day type of the day it departs (after midnight: the next day's).
        transfers=True adds trips with one change, and every option gets `legs` and `changes`."""
        froms, tos = self.stop_group(from_id), self.stop_group(to_id)
        d_of = [day_type_of(date + dt.timedelta(days=k)) for k in range(3 + window_min * 60 // DAY)]
        options, served, routes = [], [], {}
        candidates = {v for s in froms for v in self.variants_at.get(s, [])}
        candidates &= {v for s in tos for v in self.variants_at.get(s, [])}
        for v in sorted(candidates):
            pos = self.pos_of[v]
            pairs = [(pos[a], pos[b], a, b) for a in froms if a in pos for b in tos if b in pos and pos[b] > pos[a]]
            if not pairs:
                continue
            fp, tp, fs, ts = min(pairs, key=lambda q: q[1] - q[0])
            served.append(v)
            routes[v] = {"number": self.number_of[v], "direction": self.direction_of[v],
                         "description": self.desc_of.get(v, "")}
            m = self.timetable.get(v)
            if m is None:
                continue
            d, a = m[:, fp], m[:, tp]
            ok = (d >= 0) & (a >= d)
            for trip in np.flatnonzero(ok):
                depart = int(t + (int(d[trip]) - t) % DAY)
                if depart - t > window_min * 60:
                    continue
                arrive = depart + int(a[trip] - d[trip])
                hour = (depart // 3600) % 24
                daytype = d_of[depart // DAY]
                occ = self._hour_occ(v, daytype, hour, fp, tp)
                options.append({"routeId": v, "trip": int(trip), "fromPos": fp, "toPos": tp,
                                "fromStop": fs, "toStop": ts, "depart": depart, "arrive": arrive,
                                "occ": round(occ, 3), "level": level_of(occ),
                                "confidence": self.confidence.get((v, hour), "none"),
                                "daytype": DAY_TYPES[daytype]})
        options.sort(key=lambda o: (o["arrive"], o["depart"]))
        options = options[:max_options]
        if transfers:
            name = self.stops.stop_name
            for o in options:
                o["legs"] = [{**o, "fromName": name.get(o["fromStop"], o["fromStop"]),
                              "toName": name.get(o["toStop"], o["toStop"])}]
                o["changes"], o["walk_m"], o["walk_s"] = 0, 0, 0
            changes = self.transfers.one_change(froms, tos, t, d_of, window_min * 60, options)
            for o in changes:
                for leg in o["legs"]:
                    v = leg["routeId"]
                    routes.setdefault(v, {"number": self.number_of[v], "direction": self.direction_of[v],
                                          "description": self.desc_of.get(v, "")})
            options = sorted(options + changes, key=lambda o: (o["arrive"], o["depart"]))
        return {"from": froms, "to": tos, "t": int(t), "daytype": DAY_TYPES[d_of[0]], "served_by": served,
                "routes": routes, "options": options}

    def locate(self, short: str, lat: float, lon: float):
        """(lat, lon, dist_m, segment position) of the fix snapped onto the route, or None."""
        g = self.routes.get(short)
        if g is None:
            return None
        px, py = to_xy(lat, lon, g.lat0)
        ax, ay = g.x[:-1], g.y[:-1]
        t = np.clip(((px - ax) * g.dx + (py - ay) * g.dy) / g.l2, 0, 1)
        d = np.hypot(ax + t * g.dx - px, ay + t * g.dy - py)
        i = int(np.argmin(d))
        if d[i] > MAX_OFF_ROUTE_M:
            return None
        s = float(g.cum[i] + t[i] * (g.cum[i + 1] - g.cum[i]))
        a, b = g.pts[i], g.pts[i + 1]
        pos = int(np.clip(np.searchsorted(g.stop_dist, s, side="right") - 1, 0, len(g.stop_ids) - 2))
        return float(a[0] + t[i] * (b[0] - a[0])), float(a[1] + t[i] * (b[1] - a[1])), s, pos

    def crowding_at(self, short: str, d: int, hour: int, pos: int):
        """(occupancy, 1 = high / 0 = low confidence) for a segment, or (None, None) if no tickets."""
        a = self.occ.get((short, d, hour))
        if a is None:
            return None, None
        return float(a[pos]), 1 if self.confidence.get((short, hour)) == "high" else 0

    @lru_cache(maxsize=3072)
    def route_detail(self, short: str, d: int) -> dict | None:
        """One route: simplified shape, stops along it and 24 hours of segment crowding (day type d)."""
        g = self.routes.get(short)
        if g is None:
            return None
        empty = pd.DataFrame(columns=["hour", "pos", "occupancy"])
        return {
            "route": {
                "id": short, "number": self.number_of[short], "direction": self.direction_of[short],
                "description": self.desc_of.get(short, ""), "canonical_trip": g.canonical_trip,
                "shape": simplify(g.pts, g.cum),
                "stops": [{"stop_id": s, "dist_m": int(round(x))} for s, x in zip(g.stop_ids, g.stop_dist)],
                "trips_per_day": int(sum(self.tph.get(short, {}).values())),
            },
            "daytype": DAY_TYPES[d],
            "crowding": crowding_hours(len(g.stop_ids), self.seg_by_route.get((short, d), empty),
                                       self.rh_by_route.get((short, d), empty.set_index("hour")),
                                       self.tph.get(short, {})),
        }
