"""The eight tier-3 tables as the targets the simulator's world must fit (6.5, U1, V9).

`build` loads `dataset.sql` and then `tier3.sql` of the baseline into one DuckDB, after it has
checked both files against PROVENANCE.toml. `Targets` holds the eight tables as `Rows`, typed
views for the allocator, and `demand`, the daily_sales formula for any day of 2024-01-01 to
2026-10-31.
"""

from __future__ import annotations

import hashlib
import operator
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from importlib import resources
from types import MappingProxyType
from typing import Final, NamedTuple

import duckdb
from roastery.pipeline import Rows
from roastery_spec import baseline

TABLES: Final = (
    'daily_sales',
    'order_values',
    'budget',
    'checkout_test',
    'subscribers',
    'visits',
    'deliveries',
    'shop_days',
)
"""The eight tier-3 tables, in the order of tier3.sql."""

FIRST: Final = date(2024, 1, 1)
LAST: Final = date(2026, 10, 31)
"""The days `demand` answers for."""

_ORIGIN: Final = date(2024, 10, 1)
_BASE: Final = MappingProxyType({'P-10': 16, 'P-11': 6, 'P-20': 1, 'P-21': 1})
_WEEK: Final = (2, 2, 2, 3, 4, 3, 1)
"""The weekday weight, Monday first."""


class Lesson(NamedTuple):
    """One order of order_values, with the formula's own composition."""

    order_no: int
    order_date: date
    channel: str
    bags: int
    coffee: str
    p20: bool
    amount: Decimal
    status: str


class Subscriber(NamedTuple):
    subscription_id: int
    product_id: str
    started: date
    ended: date | None


class Visit(NamedTuple):
    visit_id: int
    visit_date: date
    country: str
    source: str
    reached: int


class Visitor(NamedTuple):
    """One row of checkout_test."""

    visitor_no: int
    test_day: int
    variant: str
    converted: bool


class Delivery(NamedTuple):
    order_no: int
    country: str
    shipped_on: date
    days: int


class ShopDay(NamedTuple):
    shop_date: date
    rain_mm: int
    walk_ins: int
    receipts: int


class Price(NamedTuple):
    product_id: str
    price: Decimal
    valid_from: date
    valid_to: date | None


def _cmod(a: int, b: int) -> int:
    """`a % b` as DuckDB has it: the sign of `a`, not of `b`."""
    r = abs(a) % b
    return -r if a < 0 else r


def _price(prices: tuple[Price, ...], product: str, day: date) -> Decimal | None:
    for p in prices:
        if p.product_id == product and p.valid_from <= day:
            if p.valid_to is None or day < p.valid_to:
                return p.price
    return None


@dataclass(frozen=True)
class Targets:
    """The eight tables and the views of them the allocator reads."""

    tables: Mapping[str, Rows]
    prices: tuple[Price, ...]
    daily_sales: Mapping[tuple[date, str], int]
    lessons: tuple[Lesson, ...]
    subscribers: tuple[Subscriber, ...]
    visits: tuple[Visit, ...]
    checkout_test: tuple[Visitor, ...]
    deliveries: tuple[Delivery, ...]
    shop_days: tuple[ShopDay, ...]

    @property
    def budget(self) -> Rows:
        return self.tables['budget']

    def demand(self, day: date, product: str) -> int | None:
        """The bags the daily_sales formula sells of a product on a day; None with no price."""
        if not FIRST <= day <= LAST:
            raise ValueError(f'{day} is outside {FIRST} to {LAST}')
        if _price(self.prices, product, day) is None:
            return None
        n = (day - _ORIGIN).days
        base = _BASE[product]
        december = base if day.month == 12 and day.day <= 23 else 0
        growth = base * min(max(n - 365, 0), 90) // 360
        # SQL's % on the window; before it Python's floored %, as `series` extends its rows,
        # so the noise keeps its -2 to 2 and the orders take no step in May 2024
        mod = _cmod if n >= 0 else operator.mod
        noise = mod(n * 7919 + int(product[2:]) * 104729, 5) - 2
        return max(0, base * _WEEK[day.isoweekday() - 1] // 4 + december + growth + noise)


def _check(name: str, expected: str) -> str:
    data = (resources.files('roastery_spec') / 'baseline' / name).read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(f'{name} differs from PROVENANCE.toml')
    return data.decode('utf-8')


def _lessons(rows: Rows, prices: tuple[Price, ...]) -> tuple[Lesson, ...]:
    found = []
    for order_no, order_date, channel, amount, status in rows.rows:
        i = int(order_no)  # type: ignore[call-overload]
        placed = date(2026, 1, 1) + timedelta(days=(i - 1) * 273 // 600)
        shop = i % 5 == 0
        r = (i * 7919) % 100
        band = 1 if r < 55 else 2 if r < 80 else 4 if r < 93 else 10
        coffee = 'P-11' if (i * 104729) % 3 == 0 else 'P-10'
        day = placed + timedelta(days=1 if shop and placed.isoweekday() == 7 else 0)
        bags = min(band, 2) if shop else band
        if i == 600:
            bags, coffee = 48, 'P-10'
        p20 = i % 11 == 0 and not shop
        list_price = _price(prices, coffee, day)
        extra = _price(prices, 'P-20', day)
        if list_price is None or extra is None:
            raise ValueError(f'order {i}: no list price on {day}')
        composed = Decimal(-899) if i == 300 else bags * list_price + (extra if p20 else 0)
        if composed != amount or day != order_date or ('shop' if shop else 'web') != channel:
            raise ValueError(f'order {i}: the formula gives {composed}, the table {amount}')
        found.append(Lesson(i, day, str(channel), bags, coffee, p20, amount, str(status)))
    return tuple(found)


def build() -> Targets:
    """The targets, from the baseline's two files; raises if either differs from PROVENANCE."""
    origin = baseline.provenance()
    dataset = _check('dataset.sql', origin['dataset_sql']['sha256'])
    tier3 = _check('tier3.sql', origin['tier3_sql']['sha256'])
    con = duckdb.connect()
    try:
        con.execute('SET threads = 1')
        con.execute("SET TimeZone = 'UTC'")
        baseline.database(baseline.tables(dataset), con=con)
        found = baseline.tables(tier3)
        baseline.database(found, con=con)
        tables = {}
        for table in found:
            name = table['name']
            order = ', '.join(table['key'])
            cursor = con.execute(f'SELECT * FROM {name} ORDER BY {order}')
            columns = tuple(d[0] for d in cursor.description)
            tables[name] = Rows(name, columns, tuple(tuple(r) for r in cursor.fetchall()))
        prices = tuple(
            Price(*r)
            for r in con.execute('SELECT * FROM prices ORDER BY product_id, valid_from').fetchall()
        )
    finally:
        con.close()
    if tuple(tables) != TABLES:
        raise ValueError(f'tier3.sql holds {tuple(tables)}, not {TABLES}')
    return Targets(
        tables=MappingProxyType(tables),
        prices=prices,
        daily_sales=MappingProxyType({(r[0], r[1]): r[2] for r in tables['daily_sales'].rows}),
        lessons=_lessons(tables['order_values'], prices),
        subscribers=tuple(Subscriber(*r) for r in tables['subscribers'].rows),
        visits=tuple(Visit(*r) for r in tables['visits'].rows),
        checkout_test=tuple(Visitor(*r) for r in tables['checkout_test'].rows),
        deliveries=tuple(Delivery(*r) for r in tables['deliveries'].rows),
        shop_days=tuple(ShopDay(*r) for r in tables['shop_days'].rows),
    )
