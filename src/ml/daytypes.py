"""Day types for crowding: weekday, Saturday, Sunday/holiday.

Chosen from the October 2026 daily e-ticket totals: most weekdays ~98–110 k passengers, Saturdays
73–91 k, Sundays 40–57 k, and the two October public holidays (2 Oct 45.7 k, 20 Oct 56.1 k) at
Sunday level, so public holidays count as Sundays.
"""
from __future__ import annotations
import datetime as dt

import numpy as np
import pandas as pd

DAY_TYPES = ("weekday", "saturday", "sunday_holiday")

# Delhi gazetted holidays: the two in the October data, plus those in the app's demo window
# (to 11 Dec 2026). Extend from the Delhi Govt gazetted list before serving other months.
HOLIDAYS = frozenset({
    dt.date(2026, 10, 2),    # Gandhi Jayanti
    dt.date(2026, 10, 20),   # Dussehra
    dt.date(2026, 11, 24),   # Guru Nanak's Birthday
    dt.date(2026, 12, 25),   # Christmas
})


def day_type_of(date: dt.date) -> int:
    """Scalar day_type() for one date (no pandas; the API calls it per request and per bus)."""
    if date in HOLIDAYS or date.weekday() == 6:
        return 2
    return 1 if date.weekday() == 5 else 0


def day_type(dates) -> np.ndarray:
    """0 = weekday, 1 = Saturday, 2 = Sunday or public holiday, for each date."""
    d = pd.to_datetime(pd.Series(dates)).dt.normalize()
    dow = d.dt.day_of_week.to_numpy()
    holiday = d.isin(pd.to_datetime(sorted(HOLIDAYS))).to_numpy()
    return np.where(holiday | (dow == 6), 2, np.where(dow == 5, 1, 0))
