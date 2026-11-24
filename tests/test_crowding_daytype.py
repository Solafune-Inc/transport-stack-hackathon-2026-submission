"""Day-type crowding (src/model/crowding.py) on a tiny synthetic route: R1UP with stops a-b-c-d."""
import numpy as np
import pandas as pd
import pytest

from ml.daytypes import DAY_TYPES, day_type
from model.crowding import (CAPACITY, LEVELS, compute_segments, level_of, levels_of, network_daytype_factors,
                            operator_table, scale_by_daytype)

OCT = pd.date_range("2026-10-01", periods=31)
SEQS = {"R1UP": {"a": 0, "b": 1, "c": 2, "d": 3}}
TPH = {"R1UP": {9: 4, 10: 4, 11: 1}}      # scheduled buses per day starting in each hour
PER_DAY = {0: 3, 1: 2, 2: 1}               # 09:00 riders per day: weekday / Saturday / Sunday+holiday


@pytest.fixture(scope="module")
def tickets():
    rows = []
    for day, d in zip(OCT, day_type(OCT)):
        rows += [(day, 9, 0, 2), (day, 9, 1, 3)] * PER_DAY[int(d)]
    rows += [(OCT[0], 10, 0, 1)] * 5       # few tickets: 5 passengers in the month
    rows += [(OCT[0], 11, 0, 3)] * 40      # plenty of tickets but only 1 scheduled bus
    df = pd.DataFrame(rows, columns=["date", "hour", "board_pos", "alight_pos"])
    df["route"], df["pax"] = "R1UP", 1
    df["created_at"] = df.date.dt.strftime("%Y-%m-%d") + df.hour.map(" {:02d}:15:00".format)
    return df


@pytest.fixture(scope="module")
def tables(tickets):
    seg, _ = compute_segments(tickets, SEQS, TPH)
    factors = network_daytype_factors(tickets)
    seg_d, rh_d = scale_by_daytype(seg, factors)
    return seg, factors, seg_d, rh_d


def test_network_factors_keep_the_monthly_total(tables):
    _, factors, _, _ = tables
    n_days = pd.Series(factors.attrs["n_days"])
    assert n_days.tolist() == [20, 5, 6]
    total = factors.assign(n=factors.daytype.map(n_days)).eval("n * factor").groupby(factors.hour).sum()
    assert np.allclose(total, 31)
    at9 = factors[factors.hour == 9].set_index("daytype").factor
    mean = sum(n_days[DAY_TYPES[d]] * k for d, k in PER_DAY.items()) / 31
    assert at9.to_dict() == pytest.approx({DAY_TYPES[d]: k / mean for d, k in PER_DAY.items()})


def test_loads_stay_positive_and_empty_at_the_terminus(tables):
    seg, _, seg_d, _ = tables
    assert (seg_d.per_vehicle_load >= 0).all() and (seg_d.occupancy >= 0).all()
    assert 3 not in set(seg.pos) and 3 not in set(seg_d.pos)   # everyone is off by the last stop


def test_profile_shape_is_only_scaled(tables):
    seg, factors, seg_d, _ = tables
    m = seg_d.merge(seg[["route", "hour", "pos", "occupancy"]], on=["route", "hour", "pos"],
                    suffixes=("", "_month")).merge(factors, on=["hour", "daytype"])
    assert len(m) == 3 * len(seg)
    assert np.allclose(m.occupancy, m.occupancy_month * m.factor, atol=6e-4)


def test_vectorised_levels_match_level_of():
    occ = [0, 0.49, 0.5, 0.79, 0.8, 0.99, 1.0, 5.0] + [thr for thr, _ in LEVELS[:-1]]
    assert levels_of(occ).tolist() == [level_of(o) for o in occ]


def test_confidence_needs_buses_and_tickets(tables):
    _, _, _, rh_d = tables
    conf = rh_d.groupby("hour").confidence.agg(set)
    assert conf[9] == {"high"}     # 4 buses/day, 152 passengers in the month
    assert conf[10] == {"low"}     # 4 buses/day, only 5 passengers
    assert conf[11] == {"low"}     # 40 passengers, only 1 bus/day
    assert (rh_d.groupby(["hour", "daytype"]).size() == 1).all()


def test_route_level_factors_scale_each_route_hour(tables):
    seg, _, _, _ = tables
    factors = pd.DataFrame([("R1UP", h, d, f) for h in (9, 10, 11) for d, f in zip(DAY_TYPES, (1.2, 0.9, 0.4))],
                           columns=["route", "hour", "daytype", "factor"])
    seg_d, rh_d = scale_by_daytype(seg, factors)
    at9 = rh_d[rh_d.hour == 9].set_index("daytype").peak_occupancy
    month = seg[seg.hour == 9].occupancy.max()
    assert at9.to_dict() == pytest.approx({"weekday": 1.2 * month, "saturday": 0.9 * month,
                                           "sunday_holiday": 0.4 * month}, abs=6e-4)


def test_operator_table_ranks_riders_over_capacity():
    rows = []
    for route, hour, buses, occs in (("A", 8, 4, (2.0, 1.5, 0.5)), ("B", 9, 1, (3.0, 2.0, 1.0)),
                                     ("C", 8, 6, (0.9, 0.5, 0.3))):
        for d, occ in zip(DAY_TYPES, occs):
            rows.append((route, d, hour, occ, occ * CAPACITY, buses, 100.0, "high"))
    rh_d = pd.DataFrame(rows, columns=["route", "daytype", "hour", "peak_occupancy", "peak_per_vehicle_load",
                                       "trips_day", "pax_month", "confidence"])
    ops = operator_table(rh_d)
    assert ops.route.tolist() == ["A", "B"]                      # C is under capacity on weekdays
    assert ops.riders_over_capacity_per_day.tolist() == [240, 120]   # (120 - 60) x 4, (180 - 60) x 1
    assert ops.occupancy_with_one_more_bus.tolist() == [1.6, 1.5]    # 2.0 x 4/5, 3.0 x 1/2
    assert ops.saturday_occupancy.tolist() == [1.5, 2.0]
    assert ops.sunday_holiday_occupancy.tolist() == [0.5, 1.0]
