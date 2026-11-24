"""GTFS static feed loader for the Delhi Buses feed.

A thin, practical wrapper around the GTFS text files that the crowding model,
the journey planner, and the synthetic generator all share.

    from src.data.gtfs import GTFSFeed
    feed = GTFSFeed.load()          # defaults to data/delhi_buses_static_gtfs
    feed.stops, feed.routes, feed.trips, feed.stop_times
    seqs = feed.trip_sequences()    # {trip_id: (stop_ids[], dep_seconds[])}

Data source: Delhi Transport Stack (DoT, GNCTD), License Agreement v1.0.
"""
from __future__ import annotations
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GTFS = ROOT / "data" / "delhi_buses_static_gtfs"


def hms_to_seconds(s: pd.Series) -> pd.Series:
    """GTFS 'HH:MM:SS' -> seconds since service midnight (supports hours >= 24)."""
    parts = s.astype(str).str.split(":", expand=True).astype("float")
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


@dataclass
class GTFSFeed:
    """Loaded GTFS tables + convenience accessors."""
    stops: pd.DataFrame
    routes: pd.DataFrame
    trips: pd.DataFrame
    stop_times: pd.DataFrame
    path: Path

    # ---- loading -----------------------------------------------------------
    @classmethod
    def load(cls, path: str | Path = DEFAULT_GTFS, with_shapes: bool = False) -> "GTFSFeed":
        path = Path(path)
        if not (path / "stops.txt").exists():
            raise FileNotFoundError(
                f"GTFS feed not found at {path}. Download it from the Transport Stack "
                f"platform (see data/README.md)."
            )
        stops = pd.read_csv(path / "stops.txt", dtype=str)
        stops["stop_lat"] = pd.to_numeric(stops.stop_lat, errors="coerce")
        stops["stop_lon"] = pd.to_numeric(stops.stop_lon, errors="coerce")

        routes = pd.read_csv(path / "routes.txt", dtype=str)
        trips = pd.read_csv(path / "trips.txt", dtype=str)

        st = pd.read_csv(path / "stop_times.txt", dtype=str)
        st["stop_sequence"] = pd.to_numeric(st.stop_sequence, errors="coerce").astype("Int64")
        st["arr_s"] = hms_to_seconds(st.arrival_time)
        st["dep_s"] = hms_to_seconds(st.departure_time)

        feed = cls(stops=stops, routes=routes, trips=trips, stop_times=st, path=path)
        if with_shapes:
            _ = feed.shapes  # warm cache
        return feed

    # ---- cached derived views ---------------------------------------------
    @cached_property
    def shapes(self) -> pd.DataFrame:
        return pd.read_csv(
            self.path / "shapes.txt",
            dtype={"shape_id": str},
            converters={"shape_pt_lat": float, "shape_pt_lon": float,
                        "shape_pt_sequence": int, "shape_dist_traveled": float},
        )

    @cached_property
    def trip_to_route(self) -> pd.Series:
        return self.trips.set_index("trip_id").route_id

    @cached_property
    def route_to_agency(self) -> pd.Series:
        return self.routes.set_index("route_id").agency_id

    @cached_property
    def stop_coords(self) -> pd.DataFrame:
        return self.stops.set_index("stop_id")[["stop_lat", "stop_lon"]]

    def direction_of(self, route_id: str) -> str:
        """Infer UP/DOWN from route_long_name (direction_id is blank in this feed)."""
        name = str(self.routes.set_index("route_id").route_long_name.get(route_id, "")).upper()
        if name.endswith("DOWN"):
            return "DOWN"
        if name.endswith("UP"):
            return "UP"
        return "?"

    def trip_sequences(self) -> dict[str, tuple[np.ndarray, np.ndarray]]:
        """{trip_id: (stop_ids ordered by stop_sequence, departure_seconds)}.

        The shared primitive for crowding (load profiles) and synthetic generation.
        """
        st = self.stop_times.sort_values(["trip_id", "stop_sequence"])
        out: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        for trip_id, g in st.groupby("trip_id", sort=False):
            out[trip_id] = (g.stop_id.to_numpy(), g.dep_s.to_numpy())
        return out

    def __repr__(self) -> str:
        return (f"GTFSFeed(routes={len(self.routes):,}, stops={len(self.stops):,}, "
                f"trips={len(self.trips):,}, stop_times={len(self.stop_times):,})")
