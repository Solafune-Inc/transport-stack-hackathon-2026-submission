"""Decode a GTFS-Realtime (protobuf) feed into readable formats.

The Transport Stack real-time bus feed is a serialized GTFS-RT `FeedMessage`
(Protocol Buffers) — NOT text, even if the file ends in .txt. Open it with the
GTFS-RT bindings, not a text editor.

Usage:
    python src/decode_gtfsrt.py test.txt              # summary to stdout
    python src/decode_gtfsrt.py test.txt --csv out.csv --json sample.json

Requires:  pip install gtfs-realtime-bindings  (in requirements.txt)
"""
from __future__ import annotations
import argparse, csv, json
from datetime import datetime, timezone
from pathlib import Path
from google.transit import gtfs_realtime_pb2
from google.protobuf.json_format import MessageToDict


def load(path: str) -> gtfs_realtime_pb2.FeedMessage:
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(Path(path).read_bytes())
    return feed


def summarize(feed):
    h = feed.header
    ts = datetime.fromtimestamp(h.timestamp, timezone.utc)
    vp = sum(1 for e in feed.entity if e.HasField("vehicle"))
    tu = sum(1 for e in feed.entity if e.HasField("trip_update"))
    al = sum(1 for e in feed.entity if e.HasField("alert"))
    print(f"GTFS-Realtime v{h.gtfs_realtime_version}  ·  feed time {ts:%Y-%m-%d %H:%M:%S} UTC")
    print(f"entities: {len(feed.entity):,}  (vehicle positions: {vp:,}, "
          f"trip updates: {tu:,}, alerts: {al:,})")


def to_csv(feed, out: str):
    cols = ["entity_id", "vehicle_id", "route_id", "trip_id", "start_time",
            "start_date", "latitude", "longitude", "bearing", "speed",
            "current_status", "timestamp_utc"]
    n = 0
    with open(out, "w", newline="") as f:
        w = csv.writer(f); w.writerow(cols)
        for e in feed.entity:
            if not e.HasField("vehicle"):
                continue
            v = e.vehicle
            ts = datetime.fromtimestamp(v.timestamp, timezone.utc).isoformat() if v.timestamp else ""
            w.writerow([e.id, v.vehicle.id, v.trip.route_id, v.trip.trip_id,
                        v.trip.start_time, v.trip.start_date,
                        v.position.latitude, v.position.longitude,
                        v.position.bearing, v.position.speed,
                        v.current_status, ts])
            n += 1
    print(f"wrote {n:,} vehicle rows -> {out}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--csv")
    ap.add_argument("--json", help="write first entity as pretty JSON (sample)")
    a = ap.parse_args(argv)
    feed = load(a.path)
    summarize(feed)
    if a.csv:
        to_csv(feed, a.csv)
    if a.json:
        sample = next((e for e in feed.entity if e.HasField("vehicle")), None)
        if sample:
            Path(a.json).write_text(json.dumps(MessageToDict(sample), indent=2))
            print(f"wrote sample entity -> {a.json}")


if __name__ == "__main__":
    main()
