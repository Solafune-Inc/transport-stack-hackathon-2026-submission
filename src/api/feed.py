"""Background poller for the Delhi GTFS-RT VehiclePositions feed.

Transport Stack publishes a new feed about every 25 s (measured 24–33 s) and sends no ETag or
Last-Modified, so every check downloads the whole file (~0.3–0.7 MB). Rather than polling blindly,
the poller learns the publishing rhythm: after a new feed it waits until shortly before the next
one is due, then checks every FAST_POLL_S until it appears (about 6 requests a minute, each new
feed picked up within a few seconds); if the feed is late it falls back to every `refresh` s.

Each new feed is snapped onto the routes, gets the expected crowding of each bus's segment (for
the hour and day type of its GPS fix, IST), and is kept as one ready-to-send JSON body, so any number of app
clients cost no extra upstream requests. Vehicle ids (registration plates) are replaced by salted
hashes that are stable only while the server runs.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import http.client
import json
import secrets
import statistics
import threading
import time
import urllib.parse
from functools import lru_cache

from google.transit import gtfs_realtime_pb2

from api.network import Network
from ml.daytypes import day_type_of

FIELDS = ["key", "route", "lat", "lon", "dist_m", "pos", "kmh", "ts", "occ", "conf",
          "prev_ts", "prev_lat", "prev_lon", "prev_dist_m"]
IST_OFFSET_S = 5 * 3600 + 30 * 60
FAST_POLL_S = 4           # check this often while a new feed is due
EARLY_S = 6               # start checking this long before the next feed is due
LATE_S = 30               # give up fast checks this long after it was due
DEFAULT_PERIOD_S = 27


@lru_cache(maxsize=8)
def ist_day_type(ist_day: int) -> int:
    """Day type of a day number (days since 1970-01-01, IST)."""
    return day_type_of(dt.date(1970, 1, 1) + dt.timedelta(days=ist_day))


class LiveFeed:
    def __init__(self, url: str, api_key: str, network: Network, refresh: float = 15.0):
        self.url, self.api_key, self.network, self.refresh = url, api_key, network, refresh
        self._salt = secrets.token_bytes(16)
        self._lock = threading.Lock()
        self.body: bytes | None = None      # JSON object body without the leading "{"
        self.stats: dict = {}
        self.fetched_at = 0.0
        self.feed_time = 0
        self.error: str | None = None
        self.upstream_requests = 0
        # vehicle key -> (route, [latest fix, previous fix]); a fix is (ts, lat, lon, dist_m)
        self._history: dict[str, tuple[str | None, list[tuple]]] = {}
        self._header_gaps: list[int] = []   # recent seconds between published feeds
        self._new_at = 0.0                  # local time the current feed was first seen
        self._conn: http.client.HTTPConnection | None = None   # reused: saves ~1 s of TLS per poll

    def start(self) -> None:
        threading.Thread(target=self._loop, name="gtfs-rt-poller", daemon=True).start()

    @property
    def period(self) -> float:
        """Typical seconds between published feeds (median of recent gaps)."""
        return statistics.median(self._header_gaps) if self._header_gaps else DEFAULT_PERIOD_S

    def next_delay(self, now: float) -> float:
        """Seconds to wait before the next upstream check."""
        if not self._new_at or not self._header_gaps:
            return FAST_POLL_S                    # just started: find the publishing rhythm first
        due = self._new_at + self.period          # when the next feed should appear (local clock)
        if now < due - EARLY_S:
            return max(FAST_POLL_S, due - EARLY_S - now)
        if now < due + LATE_S:
            return FAST_POLL_S
        return self.refresh

    def _loop(self) -> None:
        while True:
            try:
                self.refresh_once()
            except Exception as e:  # keep serving the last good feed
                with self._lock:
                    self.error = f"{type(e).__name__}: {e}"
            time.sleep(self.next_delay(time.time()))

    def _download(self) -> bytes:
        """GET the feed over a kept-alive connection, reconnecting once if the server dropped it."""
        u = urllib.parse.urlsplit(self.url)
        path = u.path + (f"?{u.query}" if u.query else "")
        for attempt in (0, 1):
            if self._conn is None:
                cls = http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection
                self._conn = cls(u.netloc, timeout=30)
            try:
                self._conn.request("GET", path, headers={"x-api-key": self.api_key})
                resp = self._conn.getresponse()
                data = resp.read()
            except (http.client.HTTPException, OSError):
                self._conn.close()
                self._conn = None
                if attempt:
                    raise
                continue
            if resp.status != 200:
                raise RuntimeError(f"upstream HTTP {resp.status}")
            return data
        raise RuntimeError("unreachable")

    def _key(self, vehicle_id: str) -> str:
        return hashlib.blake2b(vehicle_id.encode(), key=self._salt, digest_size=5).hexdigest()

    def refresh_once(self) -> bool:
        """Fetch the feed once; True if it was a newer feed (rebuilt), False if unchanged."""
        raw = self._download()
        self.upstream_requests += 1
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(raw)
        header_ts = int(feed.header.timestamp)
        if header_ts <= self.feed_time:       # not republished yet: nothing to rebuild
            with self._lock:
                self.fetched_at, self.error = time.time(), None
            return False
        if self.feed_time:
            self._header_gaps = (self._header_gaps + [header_ts - self.feed_time])[-8:]
        self._new_at = time.time()

        rows, on_route, off_route, unknown = [], 0, 0, 0
        history = {}
        for e in feed.entity:
            if not e.HasField("vehicle"):
                continue
            v = e.vehicle
            lat, lon = v.position.latitude, v.position.longitude
            if lat == 0 and lon == 0:
                continue
            ts = int(v.timestamp) or header_ts
            short = self.network.short_of_route_id.get(v.trip.route_id)
            dist = pos = occ = conf = None
            if short is None:
                unknown += 1
            else:
                loc = self.network.locate(short, lat, lon)
                if loc is None:
                    off_route += 1
                else:
                    on_route += 1
                    lat, lon, dist, pos = loc
                    local = ts + IST_OFFSET_S
                    occ, conf = self.network.crowding_at(short, ist_day_type(local // 86400),
                                                         (local // 3600) % 24, pos)
            key = self._key(v.vehicle.id or e.id)
            fix = (ts, round(lat, 5), round(lon, 5), None if dist is None else int(round(dist)))
            # the previous distinct fix on the same route lets clients animate from the first response
            old_route, old = self._history.get(key, (None, []))
            fixes = old if old_route == short else []
            if not fixes or ts > fixes[0][0]:
                fixes = [fix] + fixes[:1]
            history[key] = (short, fixes)
            prev = fixes[1] if len(fixes) > 1 else (None, None, None, None)
            rows.append([key, short, fix[1], fix[2], fix[3], pos, round(v.position.speed * 3.6, 1), ts,
                         None if occ is None else round(occ, 3), conf, *prev])
        self._history = history

        stats = {"vehicles": len(rows), "on_route": on_route, "off_route": off_route,
                 "unknown_route": unknown, "routes": len({r[1] for r in rows if r[1]})}
        body = json.dumps({"feed_time": header_ts, "fields": FIELDS,
                           "stats": stats, "vehicles": rows}, separators=(",", ":")).encode()
        with self._lock:
            self.body, self.stats, self.feed_time = body[1:], stats, header_ts
            self.fetched_at, self.error = time.time(), None
        return True

    def snapshot(self) -> tuple[bytes | None, dict]:
        """(JSON body with a fresh server clock, status) — body is None before the first fetch."""
        with self._lock:
            body, error, fetched_at = self.body, self.error, self.fetched_at
            status = {"feed_time": self.feed_time,
                      "fetched_age_s": round(time.time() - fetched_at, 1) if fetched_at else None,
                      "feed_age_s": round(time.time() - self.feed_time, 1) if self.feed_time else None,
                      "feed_period_s": round(self.period, 1),
                      "error": error, "upstream_requests": self.upstream_requests, **self.stats}
        if body is None:
            return None, status
        head = json.dumps({"now": int(time.time()), "fetched_at": int(fetched_at), "error": error},
                          separators=(",", ":"))[:-1]
        return head.encode() + b"," + body, status
