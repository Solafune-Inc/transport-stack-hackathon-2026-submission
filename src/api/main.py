"""API for the mobile app: Delhi GTFS-RT bus positions, stops, routes, crowding and trip planning.

The Transport Stack API key stays here, on the server; phones only talk to this API.
Times `t` are seconds since midnight in Delhi (IST); they default to now. Crowding is the October
average for the day type (weekday / Saturday / Sunday-holiday) of `date` (YYYY-MM-DD, default today
in Delhi); a bus departing after midnight gets the next day's.

    GET /api/health            status: vehicles, feed age, last upstream error
    GET /api/stops             every stop a route stops at: [id, name, lat, lon, route variants]
    GET /api/stops/{id}[?t=&date=]  one stop: busyness by hour + every route number through it, both
                               directions (serves it?, expected crowding arriving, next departures)
    GET /api/routes?ids=A,B[&date=]  several routes at once: {"routes": {id: same as /api/routes/{id}}}
    GET /api/shapes?ids=A,B    route lines only: {"shapes": {id: [[lat, lon, dist_m], ...]}} (for
                               moving buses along their road between GPS reports)
    GET /api/plan?from=&to=[&t=&date=&transfers=1]  direct buses between two stops (same-named stops
                               across the road count too) leaving within 2 h, with the worst crowding
                               on the ride; transfers=1 adds trips with one change of bus (change at
                               the same stop or walk <= 250 m) and gives every option its `legs`,
                               `changes`, `walk_m` and `walk_s`
    GET /api/live[?since=T]    every live bus (204 if no feed newer than T): [key, route, lat, lon, dist_m, pos, kmh, ts, occ, conf,
                               prev_ts, prev_lat, prev_lon, prev_dist_m]
                               (snapped onto its route; occ = expected occupancy of the segment it
                               is on, for the hour and day type of its GPS fix; conf 1/0 = high/low confidence;
                               prev_* = its previous GPS fix on the same route, or nulls)
    GET /api/routes/{route}[?date=]  one route (e.g. 623UP): shape, stops along it, 24 h segment crowding

Run (from the repo root, conda env transport-stack):
    python src/api/main.py                    # http://0.0.0.0:8787, reachable from phones on the Wi-Fi
    python src/api/main.py --port 8788 --refresh 20

Needs data/ (GTFS + crowding outputs from src/model/crowding.py) and .env with
TRANSPORTSTACK_API_KEY (and optionally TRANSPORTSTACK_RT_URL).
Data source: Delhi Transport Stack (DoT, GNCTD) — License Agreement v1.0.
Third-party libs: FastAPI, uvicorn, gtfs-realtime-bindings (protobuf), pandas, numpy.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

if __package__ in (None, ""):  # run as a script: make src/ importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI, HTTPException, Query  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.middleware.gzip import GZipMiddleware  # noqa: E402
from fastapi.responses import Response  # noqa: E402

from api.feed import LiveFeed  # noqa: E402
from api.network import Network  # noqa: E402
from ml.daytypes import DAY_TYPES, day_type_of  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
IST_OFFSET_S = 5.5 * 3600
MAX_ROUTES_PER_REQUEST = 300
DEFAULT_RT_URL = ("https://dts-backend.transportstack.in/api/dataset/otd/get-file"
                  "?agency=delhi-buses&category=realtime_gtfs&filename=VehiclePositions.pb")


def load_env(path: Path = ROOT / ".env") -> dict:
    env = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def settings() -> dict:
    env = {**load_env(), **os.environ}
    return {"url": env.get("TRANSPORTSTACK_RT_URL") or DEFAULT_RT_URL,
            "key": env.get("TRANSPORTSTACK_API_KEY", ""),
            "refresh": float(env.get("LIVE_REFRESH_S", "15"))}


STATE: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = settings()
    print("Loading routes, shapes and crowding for all routes ...", flush=True)
    network = Network()
    print(f"  {len(network.routes):,} routes ready ({network.load_seconds}s)", flush=True)
    STATE["network"] = network
    STATE["stops_json"] = json.dumps(network.stops_payload(), separators=(",", ":")).encode()
    if cfg["key"]:
        feed = LiveFeed(cfg["url"], cfg["key"], network, cfg["refresh"])
        feed.start()
        STATE["feed"] = feed
        print("  polling GTFS-RT around each expected publish (~25 s)", flush=True)
    else:
        print("  ! TRANSPORTSTACK_API_KEY missing in .env — /api/live will return 503", flush=True)
    yield


app = FastAPI(title="Delhi Bus Crowding — live API", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=2048)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])


@app.get("/api/health")
def health():
    feed: LiveFeed | None = STATE.get("feed")
    network: Network | None = STATE.get("network")
    status = feed.snapshot()[1] if feed else {"error": "TRANSPORTSTACK_API_KEY missing in .env"}
    return {"ok": bool(feed and feed.body), "routes_loaded": len(network.routes) if network else 0,
            "daytype_today": DAY_TYPES[day_type_of(ist_today())],
            "crowding_model": network.model.get("daytype_model") if network else None, **status}


@app.get("/api/live")
def live(since: int | None = None):
    """All live buses. With ?since=<feed_time> it answers 204 (no body) until a newer feed exists,
    so apps can check every couple of seconds for almost no data."""
    feed: LiveFeed | None = STATE.get("feed")
    if feed is None:
        raise HTTPException(503, "Live feed disabled: TRANSPORTSTACK_API_KEY missing in .env")
    body, status = feed.snapshot()
    if body is None:
        raise HTTPException(503, f"Waiting for the first GTFS-RT fetch ({status.get('error') or 'in progress'})")
    headers = {"Cache-Control": "no-store", "X-Feed-Time": str(status["feed_time"])}
    if since is not None and status["feed_time"] <= since and not status["error"]:
        return Response(status_code=204, headers=headers)
    return Response(body, media_type="application/json", headers=headers)


def ist_now() -> int:
    return int((time.time() + IST_OFFSET_S) % 86400)


def ist_today() -> dt.date:
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=IST_OFFSET_S)).date()


def day_seconds(t: int | None) -> int:
    return ist_now() if t is None else t % 86400


def service_date(date: str | None) -> dt.date:
    """The `date` query parameter (YYYY-MM-DD), default today in Delhi."""
    if date is None:
        return ist_today()
    try:
        return dt.date.fromisoformat(date)
    except ValueError:
        raise HTTPException(422, f"date must be YYYY-MM-DD, got {date!r}") from None


@app.get("/api/stops")
def stops():
    return Response(STATE["stops_json"], media_type="application/json",
                    headers={"Cache-Control": "public, max-age=3600"})


@app.get("/api/stops/{stop_id}")
def stop(stop_id: str, t: int | None = None, date: str | None = None):
    info = STATE["network"].stop_info(stop_id, day_seconds(t), day_type_of(service_date(date)))
    if info is None:
        raise HTTPException(404, f"Unknown stop {stop_id!r} (or no route stops there)")
    return info


@app.get("/api/routes")
def routes(ids: str = Query(..., description="comma-separated route ids, e.g. 623UP,623DOWN"),
           date: str | None = None):
    wanted = list(dict.fromkeys(i for i in ids.split(",") if i))[:MAX_ROUTES_PER_REQUEST]
    network: Network = STATE["network"]
    d = day_type_of(service_date(date))
    return {"routes": {r: x for r in wanted if (x := network.route_detail(r, d)) is not None}}


@app.get("/api/shapes")
def shapes(ids: str = Query(..., description="comma-separated route ids, e.g. 623UP,623DOWN")):
    wanted = list(dict.fromkeys(i for i in ids.split(",") if i))[:MAX_ROUTES_PER_REQUEST]
    network: Network = STATE["network"]
    d = day_type_of(ist_today())   # shapes don't depend on it; shares route_detail's cache
    return {"shapes": {r: x["route"]["shape"] for r in wanted if (x := network.route_detail(r, d)) is not None}}


@app.get("/api/routes/{route}")
def route(route: str, date: str | None = None):
    detail = STATE["network"].route_detail(route, day_type_of(service_date(date)))
    if detail is None:
        raise HTTPException(404, f"Unknown route {route!r} (use the GTFS route_short_name, e.g. 623UP)")
    return detail


@app.get("/api/plan")
def plan(from_: str = Query(..., alias="from"), to: str = Query(...), t: int | None = None,
         date: str | None = None, transfers: bool = False):
    network: Network = STATE["network"]
    for sid in (from_, to):
        if sid not in network.variants_at:
            raise HTTPException(404, f"Unknown stop {sid!r} (or no route stops there)")
    return network.plan(from_, to, day_seconds(t), service_date(date), transfers=transfers)


def main(argv=None):
    import uvicorn
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0", help="0.0.0.0 = reachable from phones on the same Wi-Fi")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--refresh", type=float, help="fallback seconds between GTFS-RT fetches when the feed is late (default 15)")
    a = ap.parse_args(argv)
    if a.refresh:
        os.environ["LIVE_REFRESH_S"] = str(a.refresh)
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
