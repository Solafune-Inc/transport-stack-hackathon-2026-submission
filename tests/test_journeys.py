"""Trips with one change (src/api/journeys.py) on a tiny made-up network:
route 1UP  A -> B -> X,   route 2UP  Y -> C -> D,   stop Y about 100 m from X."""
from types import SimpleNamespace

import numpy as np
import pandas as pd

from api.journeys import MAX_WAIT_S, MIN_CHANGE_S, TransferPlanner, undominated, walk_s

H = 3600


def network(y_lon=77.201, second="2UP", second_number="2", y_departures=(8 * H + 22 * 60, 8 * H + 30 * 60, 9 * H + 10 * 60)):
    stops = pd.DataFrame({"stop_id": ["A", "B", "X", "Y", "C", "D"],
                          "stop_lat": [28.60, 28.60, 28.60, 28.60, 28.61, 28.62],
                          "stop_lon": [77.10, 77.15, 77.20, y_lon, 77.25, 77.30],
                          "stop_name": ["A", "B", "X", "Y", "C", "D"]}).set_index("stop_id")
    seqs = {"1UP": ["A", "B", "X"], second: ["Y", "C", "D"]}
    first = {"1UP": [8 * H, 8 * H + 30 * 60], second: list(y_departures)}
    step = {"1UP": 10 * 60, second: 15 * 60}
    timetable = {v: np.array([[d + i * step[v] for i in range(3)] for d in first[v]], np.int32) for v in seqs}
    occ = {"1UP": 0.3, second: 0.9}
    variants_at = {}
    for v, seq in seqs.items():
        for s in seq:
            variants_at.setdefault(s, []).append(v)
    net = SimpleNamespace(
        stops=stops, timetable=timetable, variants_at=variants_at,
        routes={v: SimpleNamespace(stop_ids=seq) for v, seq in seqs.items()},
        pos_of={v: {s: i for i, s in enumerate(seq)} for v, seq in seqs.items()},
        number_of={"1UP": "1", second: second_number},
        confidence={(v, h): "high" for v in seqs for h in range(24)},
        _hour_occ=lambda v, d, hour, a, b: occ[v])
    return net


def plan(net, t=7 * H + 55 * 60):
    return TransferPlanner(net).one_change(["A"], ["D"], t, [0, 0, 0], 2 * H, [])


def test_finds_the_change_and_waits_long_enough():
    opts = plan(network())
    assert len(opts) == 2
    o = opts[0]
    assert [leg["routeId"] for leg in o["legs"]] == ["1UP", "2UP"]
    assert (o["legs"][0]["fromStop"], o["legs"][0]["toStop"], o["legs"][1]["fromStop"], o["legs"][1]["toStop"]) == ("A", "X", "Y", "D")
    # arrives at X 08:20 and walks ~100 m: the 08:22 bus is too soon, so it takes the 08:30
    assert o["legs"][1]["depart"] == 8 * H + 30 * 60
    assert o["legs"][1]["depart"] - (o["legs"][0]["arrive"] + walk_s(o["walk_m"])) >= MIN_CHANGE_S
    assert 80 <= o["walk_m"] <= 120
    assert (o["changes"], o["depart"], o["arrive"]) == (1, 8 * H, 9 * H)
    assert o["level"] == "High" and o["occ"] == 0.9     # the worst leg


def test_no_option_when_the_wait_is_too_long():
    opts = plan(network(y_departures=(8 * H + 22 * 60, 9 * H + 30 * 60)))
    assert opts == [] and MAX_WAIT_S == 30 * 60


def test_no_option_when_the_walk_is_too_long():
    assert plan(network(y_lon=77.203)) == []     # ~290 m away


def test_never_changes_to_the_same_route_number():
    assert plan(network(second="1DOWN", second_number="1")) == []


def test_drops_options_another_option_beats():
    direct = [{"depart": 100, "arrive": 200, "level": "Low"}]
    later = {"depart": 90, "arrive": 210, "level": "Low", "changes": 1}
    faster = {"depart": 90, "arrive": 190, "level": "Low", "changes": 1}
    quieter = {"depart": 80, "arrive": 230, "level": "Low", "changes": 1}
    busy = {"depart": 100, "arrive": 200, "level": "High", "changes": 1}
    kept = undominated([later, faster, quieter, busy], direct)
    assert faster in kept                       # arrives before the direct bus
    assert later not in kept and quieter not in kept   # leave earlier, arrive later, and add a change
    assert busy not in kept                     # same times as the direct bus, but more crowded
