"""Trips with one change of bus, for GET /api/plan?transfers=1.

From stop group A to stop group B, leaving within a window after t:
  leg 1   a route through A, ridden to a transfer stop x after A;
  change  at x, or walk to a stop y within WALK_M (straight line x WALK_DETOUR, at WALK_SPEED);
  leg 2   a route with a different number from y to B.
Routes that already go from A to B directly are left to the direct planner (Network.plan).

Each candidate (route 1, x, y, route 2) is first ranked by scheduled ride + walk time (the median
trip's times along each route); the best PATTERNS_PER_PAIR per route pair are then checked against
the timetable: the second bus must leave y at least MIN_CHANGE_S after the rider can be there, with
at most MAX_WAIT_S of waiting. Each leg gets the crowding of its own stretch, hour and day type.
Options that another option beats on every count (leaves no earlier, arrives no later, no more
changes, no more crowded) are dropped.
"""
from __future__ import annotations
import warnings
from bisect import bisect_left

import numpy as np

from data.routes import to_xy
from ml.daytypes import DAY_TYPES
from model.crowding import LEVELS, level_of

DAY = 86400
WALK_M = 250              # longest walk between two stops to change buses
WALK_DETOUR = 1.3         # street distance / straight-line distance
WALK_SPEED = 1.2          # m/s
MIN_CHANGE_S = 120        # time to get off one bus and be ready for the next
MAX_WAIT_S = 30 * 60      # longest wait for the second bus
PATTERNS_PER_PAIR = 3     # transfer points checked per (route 1, route 2)
MAX_OPTIONS = 30
CONF_RANK = {"none": 0, "low": 1, "high": 2}
LEVEL_RANK = {name: i for i, (_, name) in enumerate(LEVELS)}


class TransferPlanner:
    """One-change search over a Network (src/api/network.py)."""

    def __init__(self, net):
        self.net = net
        self._offsets: dict[str, np.ndarray] = {}
        self.variants_set = {s: set(vs) for s, vs in net.variants_at.items()}
        self.near = self._walk_links()

    def _walk_links(self) -> dict[str, list[tuple[str, float]]]:
        """stop -> [(stop within WALK_M, metres)], itself first, for every stop a route serves."""
        ids = [s for s in self.net.variants_at if s in self.net.stops.index]
        ll = self.net.stops.loc[ids, ["stop_lat", "stop_lon"]].to_numpy(float)
        x, y = to_xy(ll[:, 0], ll[:, 1], 28.6)
        cell = np.floor(np.c_[x, y] / WALK_M).astype(int)
        grid: dict[tuple[int, int], list[int]] = {}
        for i, (cx, cy) in enumerate(cell):
            grid.setdefault((cx, cy), []).append(i)
        near = {}
        for i, (cx, cy) in enumerate(cell):
            cand = [j for dx in (-1, 0, 1) for dy in (-1, 0, 1) for j in grid.get((cx + dx, cy + dy), ())]
            d = np.hypot(x[cand] - x[i], y[cand] - y[i])
            near[ids[i]] = sorted(((ids[j], float(m)) for j, m in zip(cand, d) if m <= WALK_M), key=lambda p: p[1])
        return near

    def offsets(self, v: str) -> np.ndarray:
        """Median scheduled seconds from the route's first stop to each stop position (NaN = unknown)."""
        off = self._offsets.get(v)
        if off is None:
            m = self.net.timetable[v].astype(float)
            m[m < 0] = np.nan
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)   # positions no trip serves
                off = np.nanmedian(m - m[:, [0]], axis=0)
            self._offsets[v] = off
        return off

    def _patterns(self, froms, tos):
        """(v1, origin pos, origin stop) and the best transfer patterns per (v1, v2) pair."""
        net = self.net

        def positions(stops):
            """route -> [(position, stop)] of the given stops along it, ascending"""
            out = {}
            for s in stops:
                for v in net.variants_at.get(s, ()):
                    out.setdefault(v, []).append((net.pos_of[v][s], s))
            return {v: sorted(p) for v, p in out.items()}
        origin, dest = positions(froms), positions(tos)
        pats: dict[tuple[str, str], list[tuple]] = {}
        for v1, ops in origin.items():
            op, ostop = ops[0]
            if v1 in dest and dest[v1][-1][0] > op:
                continue                     # goes there directly
            off1 = self.offsets(v1)
            stops1 = net.routes[v1].stop_ids
            n1 = net.number_of[v1]
            for ix in range(op + 1, len(stops1)):
                if np.isnan(off1[ix]):
                    continue
                for y, walk_m in self.near.get(stops1[ix], ()):
                    for v2 in self.variants_set.get(y, set()).intersection(dest):
                        if net.number_of[v2] == n1:
                            continue
                        iy = net.pos_of[v2][y]
                        tp = next(((p, s) for p, s in dest[v2] if p > iy), None)
                        if tp is None or (v2 in origin and origin[v2][0][0] < tp[0]):
                            continue         # can't reach B after y, or goes from A to B directly
                        off2 = self.offsets(v2)
                        est = (off1[ix] - off1[op]) + walk_s(walk_m) + (off2[tp[0]] - off2[iy])
                        if np.isnan(est):
                            continue
                        pats.setdefault((v1, v2), []).append((est, walk_m, op, ostop, ix, iy, y, tp))
        return {k: sorted(p, key=lambda q: (q[0], q[1]))[:PATTERNS_PER_PAIR] for k, p in pats.items()}

    def one_change(self, froms: list[str], tos: list[str], t: int, d_of: list[int], window_s: int,
                   direct: list[dict]) -> list[dict]:
        """Options with one change, leaving within window_s after t (seconds since midnight of the
        query date; d_of[k] = day type k days later), not beaten by `direct` or each other."""
        net = self.net
        opts = []
        for (v1, v2), pats in self._patterns(froms, tos).items():
            m1, m2 = net.timetable[v1], net.timetable[v2]
            best: dict[int, tuple] = {}      # leg-1 trip -> earliest arrival via any transfer point
            for est, walk_m, op, ostop, ix, iy, y, (tp, dstop) in pats:
                d1, a1 = m1[:, op].astype(np.int64), m1[:, ix].astype(np.int64)
                trips1 = np.flatnonzero((d1 >= 0) & (a1 >= d1))
                dep1 = t + (d1[trips1] - t) % DAY
                keep = dep1 - t <= window_s
                trips1, dep1 = trips1[keep], dep1[keep]
                if not len(trips1):
                    continue
                arr_x = dep1 + (a1[trips1] - d1[trips1])
                d2, a2 = m2[:, iy].astype(np.int64), m2[:, tp].astype(np.int64)
                trips2 = np.flatnonzero((d2 >= 0) & (a2 >= d2))
                if not len(trips2):
                    continue
                tod2, ride2 = d2[trips2] % DAY, a2[trips2] - d2[trips2]
                cand = np.concatenate([tod2, tod2 + DAY, tod2 + 2 * DAY])
                order = np.argsort(cand, kind="stable")
                cand, cand_trip = cand[order], np.tile(trips2, 3)[order]
                cand_ride = np.tile(ride2, 3)[order]
                at_y = arr_x + int(round(walk_s(walk_m)))
                k = np.searchsorted(cand, at_y + MIN_CHANGE_S)
                for i in np.flatnonzero(k < len(cand)):
                    dep2 = int(cand[k[i]])
                    if dep2 - at_y[i] > MAX_WAIT_S:
                        continue
                    arrive = dep2 + int(cand_ride[k[i]])
                    trip1 = int(trips1[i])
                    if trip1 not in best or arrive < best[trip1][0]:
                        best[trip1] = (arrive, int(dep1[i]), int(arr_x[i]), dep2, int(cand_trip[k[i]]),
                                       walk_m, op, ostop, ix, iy, y, tp, dstop)
            for trip1, (arrive, dep1, arr_x, dep2, trip2, walk_m, op, ostop, ix, iy, y, tp, dstop) in best.items():
                legs = [self._leg(v1, trip1, op, ix, ostop, net.routes[v1].stop_ids[ix], dep1, arr_x, d_of),
                        self._leg(v2, trip2, iy, tp, y, dstop, dep2, arrive, d_of)]
                occ = max(leg["occ"] for leg in legs)
                conf = min((leg["confidence"] for leg in legs), key=CONF_RANK.get)
                opts.append({"routeId": v1, "trip": trip1, "fromPos": op, "toPos": ix, "fromStop": ostop,
                             "toStop": dstop, "depart": dep1, "arrive": arrive, "occ": round(occ, 3),
                             "level": level_of(occ), "confidence": conf, "daytype": legs[0]["daytype"],
                             "legs": legs, "changes": 1, "walk_m": int(round(walk_m)),
                             "walk_s": int(round(walk_s(walk_m)))})
        return sorted(undominated(opts, direct), key=lambda o: (o["arrive"], -o["depart"]))[:MAX_OPTIONS]

    def _leg(self, v, trip, a, b, from_stop, to_stop, depart, arrive, d_of) -> dict:
        net = self.net
        hour, d = (depart // 3600) % 24, d_of[depart // DAY]
        occ = net._hour_occ(v, d, hour, a, b)
        return {"routeId": v, "trip": int(trip), "fromPos": int(a), "toPos": int(b),
                "fromStop": from_stop, "toStop": to_stop,
                "fromName": net.stops.stop_name.get(from_stop, from_stop),
                "toName": net.stops.stop_name.get(to_stop, to_stop),
                "depart": int(depart), "arrive": int(arrive), "occ": round(occ, 3), "level": level_of(occ),
                "confidence": net.confidence.get((v, hour), "none"), "daytype": DAY_TYPES[d]}


def walk_s(walk_m: float) -> float:
    return walk_m * WALK_DETOUR / WALK_SPEED


def undominated(opts: list[dict], direct: list[dict]) -> list[dict]:
    """`opts` minus those another option (in `opts` or `direct`) beats or ties on every count:
    leaves no earlier, arrives no later, no more changes, crowding level no worse.

    Sweep per (changes, level) bucket, best buckets first, latest departure first: within a bucket
    an option is beaten if an earlier-kept one arrives no later; against finished buckets, if one
    leaving no earlier arrives no later (suffix minimum of arrivals by departure)."""
    pool = sorted((o.get("changes", 0), LEVEL_RANK[o["level"]], -o["depart"], o["arrive"], i)
                  for i, o in enumerate(direct + opts))
    n_direct, keep = len(direct), []
    done: list[tuple[int, int, list[int], list[int]]] = []   # (changes, level, departs asc, suffix-min arrive)
    bucket, best_arr, kept = None, float("inf"), []

    def finish():
        if kept:
            kept.sort()
            mins = [a for _, a in kept]
            for j in range(len(mins) - 2, -1, -1):
                mins[j] = min(mins[j], mins[j + 1])
            done.append((bucket[0], bucket[1], [d for d, _ in kept], mins))

    for changes, level, neg_dep, arr, i in pool:
        if (changes, level) != bucket:
            finish()
            bucket, best_arr, kept = (changes, level), float("inf"), []
        dep = -neg_dep
        if best_arr <= arr:
            continue
        beaten = False
        for c, lv, deps, mins in done:
            if c <= changes and lv <= level:
                j = bisect_left(deps, dep)
                if j < len(deps) and mins[j] <= arr:
                    beaten = True
                    break
        if beaten:
            continue
        best_arr = arr
        kept.append((dep, arr))
        if i >= n_direct:
            keep.append(opts[i - n_direct])
    return keep
