"""Day types (src/ml/daytypes.py) and the day a live bus's GPS fix belongs to (src/api/feed.py)."""
import datetime as dt

import numpy as np
import pandas as pd

from api.feed import IST_OFFSET_S, ist_day_type
from ml.daytypes import HOLIDAYS, day_type, day_type_of

IST = dt.timezone(dt.timedelta(seconds=IST_OFFSET_S))


def test_known_october_dates():
    cases = {dt.date(2026, 10, 2): 2,     # Gandhi Jayanti (Friday)
             dt.date(2026, 10, 20): 2,    # Dussehra (Tuesday)
             dt.date(2026, 10, 23): 0,    # Friday
             dt.date(2026, 10, 24): 1,    # Saturday
             dt.date(2026, 10, 25): 2}    # Sunday
    for date, want in cases.items():
        assert day_type_of(date) == want, date


def test_scalar_matches_vectorised():
    dates = list(pd.date_range("2026-10-01", "2026-12-31").date)
    assert [day_type_of(d) for d in dates] == day_type(dates).tolist()


def test_holidays_count_as_sundays():
    assert all(day_type_of(d) == 2 for d in HOLIDAYS)


def test_october_day_counts():
    assert np.bincount(day_type(pd.date_range("2026-10-01", periods=31)), minlength=3).tolist() == [20, 5, 6]


def test_gps_fix_after_midnight_takes_the_next_days_type():
    before = dt.datetime(2026, 10, 24, 23, 59, tzinfo=IST).timestamp()    # Saturday night
    after = dt.datetime(2026, 10, 25, 0, 1, tzinfo=IST).timestamp()       # Sunday
    assert ist_day_type(int(before + IST_OFFSET_S) // 86400) == 1
    assert ist_day_type(int(after + IST_OFFSET_S) // 86400) == 2
