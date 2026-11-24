"""Route geometry + crowding helpers for the live API (src/api/network.py).

They turn a route's canonical GTFS stop sequence (the one the crowding model uses, so stop
positions line up with `crowding_segments.csv`) into a shape with distances along it, stop
distances, and per-hour occupancy arrays.
"""
from __future__ import annotations
import re

import numpy as np
import pandas as pd

SIMPLIFY_M = 4            # max deviation (m) of the simplified shape from the GTFS shape
ROUTE_RE = re.compile(r"^(.*?)(UP|DOWN)(\d*)$")


def route_parts(short: str) -> tuple[str, str | None]:
    """'623UP' -> ('623', 'UP'); '116AUP2' -> ('116A', 'UP'); 'DS CIRCULAR' -> ('DS CIRCULAR', None)."""
    m = ROUTE_RE.match(short)
    return (m.group(1), m.group(2)) if m and m.group(1) else (short, None)


def norm_name(name: str) -> str:
    """Stop name for matching both sides of a road: 'Shahdara Terminal ' -> 'shahdara terminal'."""
    return " ".join(re.sub(r"[^0-9a-z]+", " ", str(name).lower()).split())


def to_xy(lat, lon, lat0):
    """Equirectangular metres — accurate enough at city scale."""
    k = 111_320.0
    return np.asarray(lon) * k * np.cos(np.radians(lat0)), np.asarray(lat) * 110_540.0


def project_stops(shape_pts, stop_ll):
    """Cumulative shape distance (m) + monotone projected distance of each stop."""
    lat0 = float(np.mean(shape_pts[:, 0]))
    x, y = to_xy(shape_pts[:, 0], shape_pts[:, 1], lat0)
    seg = np.hypot(np.diff(x), np.diff(y))
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    sx, sy = to_xy(stop_ll[:, 0], stop_ll[:, 1], lat0)
    out, worst, start = [], 0.0, 0
    for px, py in zip(sx, sy):
        ax, ay, bx, by = x[start:-1], y[start:-1], x[start + 1:], y[start + 1:]
        dx, dy = bx - ax, by - ay
        L2 = np.where(dx * dx + dy * dy == 0, 1e-9, dx * dx + dy * dy)
        t = np.clip(((px - ax) * dx + (py - ay) * dy) / L2, 0, 1)
        dist = np.hypot(ax + t * dx - px, ay + t * dy - py)
        i = int(np.argmin(dist))
        worst = max(worst, float(dist[i]))
        out.append(float(cum[start + i] + t[i] * seg[start + i]))
        start += i
    return cum, np.maximum.accumulate(np.array(out)), worst


def simplify(shape_pts, cum, tol_m: float = SIMPLIFY_M):
    """[[lat, lon, dist_m]] of the shape simplified with Douglas-Peucker (ends always kept)."""
    lat0 = float(np.mean(shape_pts[:, 0]))
    x, y = to_xy(shape_pts[:, 0], shape_pts[:, 1], lat0)
    keep = np.zeros(len(x), bool)
    keep[[0, -1]] = True
    stack = [(0, len(x) - 1)]
    while stack:
        a, b = stack.pop()
        if b - a < 2:
            continue
        dx, dy = x[b] - x[a], y[b] - y[a]
        px, py = x[a + 1:b] - x[a], y[a + 1:b] - y[a]
        L = np.hypot(dx, dy)
        d = np.abs(px * dy - py * dx) / L if L > 0 else np.hypot(px, py)
        i = int(np.argmax(d))
        if d[i] > tol_m:
            k = a + 1 + i
            keep[k] = True
            stack += [(a, k), (k, b)]
    return [[round(float(shape_pts[i, 0]), 5), round(float(shape_pts[i, 1]), 5), int(round(cum[i]))]
            for i in np.flatnonzero(keep)]


def crowding_hours(n_stops: int, seg: pd.DataFrame, rh: pd.DataFrame, trips_by_hour: dict) -> dict:
    """24 hours of {occ per stop position, peak, level, confidence, trips_day} for one route.

    `seg` / `rh` are that route's rows of crowding_segments.csv / crowding_route_hour.csv
    (`rh` indexed by hour); hours without tickets get confidence "none" and an empty `occ`.
    """
    hours = {}
    for hr in range(24):
        occ = np.zeros(n_stops)
        g = seg[seg.hour == hr]
        occ[g.pos.to_numpy(int)] = g.occupancy.to_numpy(float)
        r = rh.loc[hr] if hr in rh.index else None
        hours[str(hr)] = {
            "occ": [round(float(o), 2) for o in occ] if r is not None else [],
            "peak": round(float(r.peak_occupancy), 3) if r is not None else 0.0,
            "level": r.level if r is not None else "Low",
            "confidence": r.confidence if r is not None else "none",
            "trips_day": int(trips_by_hour.get(hr, 0)),
        }
    return hours
