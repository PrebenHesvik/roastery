"""The script of the week: its order, its jobs' days, its ids and its stock."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from roastery.ids import CustomerId, OrderId, PostalCode, ProductId
from roastery.ports import IdKind
from roastery.repository import SequentialIds
from roastery_sim import script
from roastery_sim.script import (
    CancelOrder,
    Change,
    CountAtClose,
    CsvExport,
    NightlyExtract,
    Place,
    Roast,
    Stocktake,
)

OSLO = ZoneInfo('Europe/Oslo')


def _oct(day: int, hour: int, minute: int = 0) -> dt.datetime:
    return dt.datetime(2026, 10, day, hour, minute, tzinfo=dt.UTC)


def test_steps_are_strictly_sorted_and_none_at_midnight_utc() -> None:
    steps = script.steps()
    moments = [step.at for step in steps]
    assert all(before < after for before, after in zip(moments, moments[1:], strict=False))
    assert all(at.utcoffset() == dt.timedelta(0) for at in moments)
    assert not [at for at in moments if at.time() == dt.time(0, 0)]


def test_each_copy_runs_on_the_day_it_copies() -> None:
    steps = script.steps()
    extracts = [s.at for s in steps if isinstance(s.action, NightlyExtract)]
    exports = [s.at for s in steps if isinstance(s.action, CsvExport)]
    counts = [s.at for s in steps if isinstance(s.action, CountAtClose)]
    assert [at.astimezone(OSLO).date() for at in extracts] == [
        dt.date(2026, 10, 8),
        dt.date(2026, 10, 9),
    ]
    assert [at.astimezone(OSLO).date() for at in exports] == [dt.date(2026, 10, 9)]
    # the count runs the UTC day after the day it counts: 5 to 9 October
    assert [at.date() - dt.timedelta(days=1) for at in counts] == [
        dt.date(2026, 10, day) for day in range(5, 10)
    ]
    [moved] = [
        s.at
        for s in steps
        if isinstance(s.action, Change)
        and s.action.customer_id == CustomerId('C-01')
        and s.action.postal_code == PostalCode('0150')
    ]
    assert moved == _oct(9, 18, 5)
    for at in (extracts[1], *exports):
        assert moved < at < _oct(9, 22)


def test_scripted_ids_are_the_fixture_lists() -> None:
    def hidden(n: int) -> str:
        return f'E-{n:07d}'

    assert dict(script.scripted_ids(script.steps())) == {
        'customer': ('C-01', 'C-02', 'C-07', 'C-03', 'C-04', 'C-05', 'C-06'),
        'category': ('CAT-1', 'CAT-11', 'CAT-12', 'CAT-2', 'CAT-21', 'CAT-22', 'CAT-23'),
        'product': ('P-10', 'P-11', 'P-12', 'P-20', 'P-21'),
        'campaign': ('K-1', 'K-2'),
        'subscription': ('S-1', 'S-2', 'S-7', 'S-4', 'S-5', 'S-3', 'S-6'),
        'order': ('O-101', 'O-102', 'O-103', 'O-104', 'O-106', 'O-105', 'O-107', 'O-108'),
        'line': ('L-01', 'L-02', 'L-03', 'L-04', 'L-06', 'L-10', 'L-07', 'L-08', 'L-11', 'L-12'),
        'event': (
            # 5 Oct: O-101 placed 08:12, paid 08:13; O-102 placed 21:50, paid 21:52
            'E-01',
            'E-02',
            'E-05',
            'E-06',
            # 6 Oct: O-103 placed 10:20, paid 10:21 (dropped); O-101 shipped 13:40;
            # O-104 placed 15:20, paid 15:21; O-106 placed 21:30
            hidden(101),
            hidden(102),
            'E-03',
            'E-09',
            'E-10',
            'E-11',
            # 7 Oct: O-106 cancelled 06:00; O-102 shipped 09:00;
            # O-105 placed 11:05, paid 11:06, O-107 placed 16:40 (dropped)
            'E-12',
            'E-07',
            hidden(103),
            hidden(104),
            hidden(105),
            # 8 Oct: O-101 delivered 10:05, O-102 12:00; 9 Oct: O-108 placed 19:30, paid 19:31
            'E-04',
            'E-08',
            'E-13',
            'E-14',
        ),
    }


def test_the_stock_by_arithmetic_is_the_count_at_close() -> None:
    held: dict[ProductId, int] = {}
    placed: dict[OrderId, Place] = {}
    on_day: dict[tuple[ProductId, dt.date], int] = {}
    days = [dt.date(2026, 10, day) for day in range(5, 10)]

    def close_days_before(moment: dt.datetime) -> None:
        for day in days:
            if dt.datetime.combine(day + dt.timedelta(days=1), dt.time(), dt.UTC) <= moment:
                for product_id in (ProductId('P-10'), ProductId('P-20')):
                    on_day.setdefault((product_id, day), held.get(product_id, 0))

    for step in script.steps():
        close_days_before(step.at)
        match step.action:
            case Roast(product_id, bags):
                held[product_id] = held.get(product_id, 0) + bags.value
            case Stocktake(product_id, on_hand):
                held[product_id] = on_hand
            case Place(order) as action:
                for item in order.items:
                    held[item.product_id] = held.get(item.product_id, 0) - item.qty.value
                if step.wiring == 'scripted':
                    placed[OrderId(step.ids['order'][0])] = action
            case CancelOrder(order_id, _):
                for item in placed[order_id].order.items:
                    held[item.product_id] += item.qty.value
            case _:
                pass
        assert all(qty >= 0 for qty in held.values()), step
    close_days_before(_oct(11, 0))
    p10, p20 = ProductId('P-10'), ProductId('P-20')
    assert [on_day[p10, day] for day in days] == [40, 37, 36, 60, 59]
    assert [on_day[p20, day] for day in days] == [4, 4, 4, 4, 4]


def test_sequence_widths_are_the_apps_first_ids() -> None:
    kinds: tuple[IdKind, ...] = tuple(script._SEQUENCE)
    for kind in kinds:
        assert script.hidden(kind, 1) == SequentialIds({}).next(kind)
