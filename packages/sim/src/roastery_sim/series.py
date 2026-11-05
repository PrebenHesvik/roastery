"""The outside series of the volume: weather, door counter, old till, bank rates, new-till walk-ins.

Pure functions that give fact tuples. The weather, the door counts and the old till's totals
restate `shop_days` in tier3.sql day by day (the same integer formulas), so on its window they
equal it; they run back to 1 January 2024 and, for the first two, on to 31 October 2026.
"""

from __future__ import annotations

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal
from random import Random

from roastery_sim.outside import DoorCount, FxRate, TillDayTotal, TillReceipt, WeatherDay
from roastery_sim.script import FX

ORIGIN = dt.date(2024, 10, 1)
"""Day 0 of tier3.sql's formulas."""
FIRST_DAY = dt.date(2024, 1, 1)
LAST_DAY = dt.date(2026, 10, 31)
OLD_TILL_LAST_DAY = dt.date(2026, 10, 9)
"""The old till counts the anonymous walk-ins to 9 October; the new till's receipts of the week
are the club members' (and R-5001), and it takes the walk-ins from 10 October."""
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
    """The old till's receipts from 1 Jan 2024 to 9 Oct 2026; none on a Sunday."""
    return tuple(TillDayTotal(d, _receipts(d)) for d in _days(FIRST_DAY, OLD_TILL_LAST_DAY))


FX_KEPT = (dt.date(2026, 10, 2), dt.date(2026, 10, 7))
"""The script's days: its eight rows are kept as they are and no other row falls in them."""
FX_DAILY = 50
"""A banking day's move: up to this many hundredths of a percent either way."""
FX_PULL = 250
"""Each day a rate gives back 1/FX_PULL of its distance from the script's level: it is
mostly within a few percent of it, at most about ten over the span. Integers only, so every
machine draws the same rates."""


def _walk(rng: Random, start: Decimal, days: list[dt.date]) -> list[tuple[dt.date, Decimal]]:
    """A seeded random walk from `start` over `days`, in hundredths of a percent of it."""
    off = 0
    out = []
    for day in days:
        pull = abs(off) // FX_PULL
        off += rng.randrange(-FX_DAILY, FX_DAILY + 1) - (pull if off > 0 else -pull)
        rate = start * (10000 + off) / 10000
        out.append((day, rate.quantize(Decimal('0.0001'), ROUND_HALF_UP)))
    return out


def fx(*, seed: int) -> tuple[FxRate, ...]:
    """A rate per currency for every banking day (Monday to Friday) from 1 Jan 2024 to 31 Oct 2026.

    The script's eight rows of 2 to 7 October 2026 are kept as they are and no other row falls
    in those days. Each currency walks at random from its script rows, back in time from its
    first and forward from its last: a few tenths of a percent a day, pulled back to that level.
    """
    rng = Random(f'fx {seed}')
    rows = list(FX)
    banking = [d for d in _days(FIRST_DAY, LAST_DAY) if d.weekday() < 5]
    before = [d for d in banking if d < FX_KEPT[0]]
    after = [d for d in banking if d > FX_KEPT[1]]
    for currency in sorted({r.currency for r in FX}):
        kept = sorted((r.rate_date, r.nok_per_unit) for r in FX if r.currency == currency)
        back = _walk(rng, kept[0][1], before[::-1])
        ahead = _walk(rng, kept[-1][1], after)
        rows += [FxRate(currency, day, rate) for day, rate in (*back, *ahead)]
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
