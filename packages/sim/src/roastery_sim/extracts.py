"""The volume's two extracts, `full` and `month`, as `Rows` (6.5, V2, V5, V9, V13, W37).

`full` is the play's snapshot after the 10 Oct 07:00 relay; `month` is its end, cut to October
2026. Each gathers the world's uncut tables as `tiny.inputs` does, gives the panel's customers
and the lesson rows the ids their handles were played under (V4), adds the outside series,
applies the export writer's faults (so tiny's rows are in both, cell for cell), cuts, and
projects every table to contract A's `columns + added`, with `source` last where the app
database stamps it. `full` adds the eight tier-3 tables from the targets (V9). The derived
tables (`dated_lines`, `latest_stock`, `customer_months`) are tiny's alone.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final
from zoneinfo import ZoneInfo

from roastery.pipeline import Rows
from roastery_spec.contract import TABLES, Extract

from roastery_sim import faults, outside, tiny, world
from roastery_sim.play import Played
from roastery_sim.targets import Targets
from roastery_sim.world import Volume

SNAPSHOT: Final = dt.datetime(2026, 10, 10, 7, 0, tzinfo=dt.UTC)
"""`full` is what the play held after its last step at or before this moment (V2)."""
MONTH: Final = (dt.date(2026, 10, 1), dt.date(2026, 10, 31))
"""The days `month` holds (the owner's answer 1)."""

SHOP_ZONE: Final = ZoneInfo('Europe/Oslo')
"""The till's `sold_at` is Bergen time, naive."""

LESSON_IDS: Final = ('lesson_set', 'row_no', 'shop_id')

_SPECS: Final = MappingProxyType({t.name: t for t in TABLES})

type Test = Callable[[Mapping[str, object]], bool]


@dataclass(frozen=True)
class Written:
    """One extract: its tables in contract order and the faults they hold."""

    name: Extract
    tables: tuple[Rows, ...]
    defects: tuple[faults.Defect, ...]


# Gather --------------------------------------------------------------------


def _resolve(handles: Mapping[str, str], cast: frozenset[str], value: str | None) -> str | None:
    """A tracker's customer: the id its handle was played under, or a cast id as it is."""
    if value is None or value in cast:
        return value
    if value not in handles:
        raise ValueError(f'customer {value!r} is neither a handle nor one of the cast')
    return handles[value]


def inputs(volume: Volume, played: Played) -> dict[str, Rows]:
    """Every uncut table of the played world, by name, handles resolved."""
    tables = dict(tiny.inputs(played))
    handles, cast = played.handles, world.cast_ids()
    events = (
        dataclasses.replace(e, customer_id=_resolve(handles, cast, e.customer_id))
        for e in volume.tracker
    )
    tables['web_events'] = outside.web_events(events)
    for rows in (
        outside.web_visits(volume.web_visits),
        outside.weather_days(volume.weather),
        outside.door_counts(volume.door_counts),
        outside.till_day_totals(volume.till_day_totals),
    ):
        tables[rows.name] = rows
    missing = sorted({h for _, _, h in volume.lesson_ids} - set(handles))
    if missing:
        raise ValueError(f'lesson handles never played: {missing[:5]}')
    lessons = tuple((s, n, handles[h]) for s, n, h in volume.lesson_ids)
    tables['lesson_ids'] = Rows('lesson_ids', LESSON_IDS, lessons)
    return tables


def at_snapshot(played: Played, moment: dt.datetime) -> Played:
    """The play as its snapshot at `moment` holds it; the world's facts are cut later."""
    held = played.snapshots.get(moment)
    if held is None:
        raise ValueError(f'the play has no snapshot at {moment}')
    return dataclasses.replace(
        played, tables=held.tables, feed=held.feed, payments=held.payments, csv=held.csv
    )


# Cut ------------------------------------------------------------------------


def _day(value: object) -> dt.date:
    """A cell's day: a date as it is, a UTC moment's UTC date, a naive moment's own date."""
    if isinstance(value, dt.datetime):
        if value.tzinfo is not None and value.utcoffset() != dt.timedelta(0):
            raise ValueError(f'moment {value!r} is not in UTC')
        return value.date()
    if isinstance(value, dt.date):
        return value
    raise TypeError(f'{value!r} has no day')


def _days(column: str, first: dt.date, last: dt.date) -> Test:
    return lambda row: first <= _day(row[column]) <= last


def _until(column: str, moment: dt.datetime) -> Test:
    """Stamped at or before the moment; a naive stamp is read as shop time (the till's)."""
    local = moment.astimezone(SHOP_ZONE).replace(tzinfo=None)

    def test(row: Mapping[str, object]) -> bool:
        value = row[column]
        if not isinstance(value, dt.datetime):
            raise TypeError(f'{column}: {value!r} is not a moment')
        return value <= (local if value.tzinfo is None else moment)

    return test


def _keep(rows: Rows, test: Test) -> Rows:
    kept = tuple(row for row in rows.rows if test(dict(zip(rows.columns, row, strict=True))))
    return Rows(rows.name, rows.columns, kept)


def _of(rows: Rows, column: str) -> Test:
    """In one of the ids the kept rows hold in `column` (a line by its order, ...)."""
    at = rows.columns.index(column)
    held = frozenset(row[at] for row in rows.rows)
    return lambda row: row[column] in held


MONTH_DAYS: Final[Mapping[str, str]] = MappingProxyType(
    {
        'orders': 'order_date',
        'payments': 'paid_on',
        'order_events': 'event_at',
        'fx_rates': 'rate_date',
        'stock_daily': 'stock_date',
        'stock_movements': 'moved_at',
        'customer_extracts': 'extract_date',
        'customer_changes': 'changed_at',
        'shipments': 'shipped_on',
        'subscription_events': 'event_at',
        'subscription_shipments': 'shipped_on',
        'green_purchases': 'bought_on',
        'web_events': 'event_at',
        'web_visits': 'visit_date',
        'weather_days': 'shop_date',
        'door_counts': 'shop_date',
        'till_day_totals': 'shop_date',
        'till_receipts': 'sold_at',
        'till_members': 'listed_on',
    }
)
"""V5: the dated facts of `month`, each by its own day (a UTC stamp's UTC date; the till's
Bergen time its own)."""

BY_PARENT: Final[Mapping[str, tuple[str, str]]] = MappingProxyType(
    {
        'order_lines': ('orders', 'order_id'),
        'line_stamps': ('orders', 'order_id'),
        'till_lines': ('till_receipts', 'receipt_id'),
    }
)
"""V5: the lines and stamps of either extract, by the order (or receipt) kept."""

_CLOSED: Final = SNAPSHOT.date() - dt.timedelta(days=1)
"""The last day closed before the snapshot."""

FULL_UNTIL: Final[Mapping[str, Test]] = MappingProxyType(
    {
        'web_events': _until('event_at', SNAPSHOT),
        'till_receipts': _until('sold_at', SNAPSHOT),
        'web_visits': _days('visit_date', dt.date.min, _CLOSED),
        'fx_rates': _days('rate_date', dt.date.min, _CLOSED),
        'weather_days': _days('shop_date', dt.date.min, _CLOSED),
        'door_counts': _days('shop_date', dt.date.min, _CLOSED),
        'till_day_totals': _days('shop_date', dt.date.min, _CLOSED),
        'till_members': _days('listed_on', dt.date.min, SNAPSHOT.date()),
    }
)
"""The outside systems' facts as the snapshot's moment knows them: a stamped fact at or
before it, a day's total or rate of a day closed before it, a nightly list of its own day.
The app's tables, the feed and the provider's rows are the snapshot's already."""


def _cut(tables: Mapping[str, Rows], dated: Mapping[str, Test]) -> dict[str, Rows]:
    """The dated tables by their tests, then the lines and stamps by their parents."""
    cut = {
        name: _keep(rows, dated[name]) if name in dated else rows for name, rows in tables.items()
    }
    for name, (parent, column) in BY_PARENT.items():
        cut[name] = _keep(cut[name], _of(cut[parent], column))
    return cut


# Project and assemble ---------------------------------------------------------


def _project(rows: Rows) -> Rows:
    """The rows on contract A's `columns + added`, then the app's `source` if they carry it."""
    spec = _SPECS[rows.name]
    columns = tuple(c.name for c in (*spec.columns, *spec.added))
    if 'source' in rows.columns and 'source' not in columns:  # `visits` has its own
        columns += ('source',)
    missing = [c for c in columns if c not in rows.columns]
    if missing:
        raise ValueError(f'table {rows.name} lacks {missing}')
    at = [rows.columns.index(c) for c in columns]
    return Rows(rows.name, columns, tuple(tuple(row[i] for i in at) for row in rows.rows))


def _assemble(name: Extract, tables: Mapping[str, Rows], log: tuple[faults.Defect, ...]) -> Written:
    """The extract's tables in contract order; the log cut to the rows it holds (W39)."""
    found = []
    for spec in TABLES:
        if name not in spec.extracts:
            continue
        if spec.name not in tables:
            raise ValueError(f'no table {spec.name} for {name}')
        found.append(_project(tables[spec.name]))
    return Written(name, tuple(found), _held(log, found))


def _held(log: tuple[faults.Defect, ...], found: list[Rows]) -> tuple[faults.Defect, ...]:
    """The entries whose row the extract holds; a dropped order's, when it holds the order."""
    tables = {rows.name: rows for rows in found}
    orders = tables['orders']
    held = _of(orders, 'order_id')
    kept = []
    for entry in log:
        rows = tables[entry.table]
        if entry.kind == 'dropped':
            if held({'order_id': entry.key}):
                kept.append(entry)
        elif entry.table in tiny.RAW:
            at = rows.columns.index(faults.TABLE_KEYS[entry.table][0])
            if any(_raw(row[at]) == entry.key for row in rows.rows):
                kept.append(entry)
        else:
            columns = faults.TABLE_KEYS[entry.table]
            ats = [rows.columns.index(c) for c in columns]
            keys = {', '.join(faults.text(row[i]) for i in ats) for row in rows.rows}
            if entry.key in keys:
                kept.append(entry)
    return tuple(kept)


def _raw(value: object) -> object:
    return value.strip().upper() if isinstance(value, str) else value


def full(volume: Volume, played: Played, targets: Targets) -> Written:
    """The snapshot after 10 Oct 07:00, faulted, with the outside facts it knows and the
    tier-3 tables of the targets."""
    tables, log = faults.apply(inputs(volume, at_snapshot(played, SNAPSHOT)))
    cut = _cut(tables, FULL_UNTIL)
    cut.update(targets.tables)
    return _assemble('full', cut, log)


def month(volume: Volume, played: Played) -> Written:
    """The end of the play, faulted, cut to October 2026 (V5): dated facts by their day,
    lines and stamps by their order, the state and reference tables whole."""
    tables, log = faults.apply(inputs(volume, played))
    dated = {name: _days(column, *MONTH) for name, column in MONTH_DAYS.items()}
    return _assemble('month', _cut(tables, dated), log)


def scripted_events(volume: Volume, played: Played) -> dict[str, object]:
    """What the world planted on purpose, for both manifests (V13), ids as played."""
    key = volume.key
    if key is None:
        raise ValueError('the volume has no key')
    handles = played.handles
    lessons = {n: handles[h] for s, n, h in volume.lesson_ids if s == 'order_values'}
    return {
        'finland_week': [d.isoformat() for d in key.finland_week],
        'test_days': [d.isoformat() for d in key.test_days],
        'business_accounts': sorted(handles[h] for h in key.business),
        'business_lessons': [{'order_no': n, 'order_id': lessons[n]} for n in key.misfits],
        'lost_parcel': {'order_no': key.lost_parcel, 'order_id': lessons[key.lost_parcel]},
        'refund': {'order_no': key.refund, 'order_id': lessons[key.refund]},
    }
