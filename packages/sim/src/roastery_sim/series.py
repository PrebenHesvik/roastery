"""The outside series of the volume: weather, door counter, old till, bank rates, new-till walk-ins.

Pure functions that give fact tuples. The weather, the door counts and the old till's totals
restate `shop_days` in tier3.sql day by day (the same integer formulas), so on its window they
equal it; they run back to 1 January 2024 and, for the first two, on to 31 October 2026.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from random import Random

from roastery_sim.outside import DoorCount, FxRate, TillDayTotal, TillReceipt, WeatherDay
from roastery_sim.script import FX

ORIGIN = dt.date(2024, 10, 1)
"""Day 0 of tier3.sql's formulas."""
FIRST_DAY = dt.date(2024, 1, 1)
LAST_DAY = dt.date(2026, 10, 31)
OLD_TILL_LAST_DAY = dt.date(2026, 10, 5)
"""The new till starts on 6 October."""
WALK_IN_FIRST_DAY = dt.date(2026, 10, 10)

WEEKDAY_WEIGHT = (2, 2, 2, 3, 4, 3, 1)
"""Monday to Sunday: tier3.sql's `w`."""
SHOP_OPENS = 10 * 60
SHOP_CLOSES = 17 * 60
"""Minutes after midnight, Bergen time, between which a walk-in pays."""


def _days(first: dt.date, last: dt.date) -> list[dt.date]:
    return [first + dt.timedelta(days=n) for n in range((last - first).days + 1)]


def _rain(n: int) -> int:
    # Python's % floors, so days before the origin stay non-negative; for n >= 0 it is SQL's.
    return (n * 104729) % 23 if (n * 7919) % 10 < 7 else 0


def _walk_ins(day: dt.date) -> int:
    n = (day - ORIGIN).days
    if day.isoweekday() == 7:
        return 0
    w = WEEKDAY_WEIGHT[day.weekday()]
    december = 15 if day.month == 12 and day.day <= 23 else 0
    return 30 + 6 * w + december - _rain(n) + (n * 31) % 5 - 2


def _receipts(day: dt.date) -> int:
    if day.isoweekday() == 7:
        return 0
    n = (day - ORIGIN).days
    return _walk_ins(day) * 3 // 5 + (n * 17) % 3


def weather() -> tuple[WeatherDay, ...]:
    """Rain for every day from 1 Jan 2024 to 31 Oct 2026."""
    return tuple(WeatherDay(d, _rain((d - ORIGIN).days)) for d in _days(FIRST_DAY, LAST_DAY))


def door_counts() -> tuple[DoorCount, ...]:
    """Walk-ins for every day from 1 Jan 2024 to 31 Oct 2026; none on a Sunday."""
    return tuple(DoorCount(d, _walk_ins(d)) for d in _days(FIRST_DAY, LAST_DAY))


def till_day_totals() -> tuple[TillDayTotal, ...]:
    """The old till's receipts from 1 Jan 2024 to 5 Oct 2026; none on a Sunday."""
    return tuple(TillDayTotal(d, _receipts(d)) for d in _days(FIRST_DAY, OLD_TILL_LAST_DAY))


_FX_BASE = (
    ('DKK', Decimal('1.5580'), 2),
    ('EUR', Decimal('11.6200'), 10),
    ('SEK', Decimal('1.0610'), 1),
)


def fx() -> tuple[FxRate, ...]:
    """A rate per currency for every banking day (Monday to Friday) from 1 Jan 2024 to 31 Oct 2026.

    The script's eight rows of 2 to 7 October 2026 are kept as they are and no other row falls
    in those days. A generated rate is the currency's base plus a small steady wobble.
    """
    window = (dt.date(2026, 10, 2), dt.date(2026, 10, 7))
    rows = list(FX)
    for day in _days(FIRST_DAY, LAST_DAY):
        if day.weekday() > 4 or window[0] <= day <= window[1]:
            continue
        n = (day - ORIGIN).days
        for code, (currency, base, step) in enumerate(_FX_BASE):
            wobble = ((n * 7919 + code * 104729) % 41 - 20) * step
            rows.append(FxRate(currency, day, base + Decimal(wobble) / 10000))
    return tuple(sorted(rows, key=lambda r: (r.currency, r.rate_date)))


def walk_in_receipts(*, seed: int) -> tuple[TillReceipt, ...]:
    """The new till's anonymous walk-in receipts, 10 to 31 October 2026.

    A day has as many receipts as the old till's formula gives for it (never more than the
    door count); a Sunday has none. Each is stamped in Bergen time on a whole minute between
    10:00 and 17:00 and is numbered R-6001 on, in time order.
    """
    rng = Random(seed)
    out: list[TillReceipt] = []
    for day in _days(WALK_IN_FIRST_DAY, LAST_DAY):
        minutes = sorted(rng.sample(range(SHOP_OPENS, SHOP_CLOSES), _receipts(day)))
        for minute in minutes:
            at = dt.datetime.combine(day, dt.time(minute // 60, minute % 60))
            out.append(TillReceipt(f'R-{6001 + len(out)}', None, at))
    return tuple(out)
