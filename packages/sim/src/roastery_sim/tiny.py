"""Tiny's 30 tables from one play: gather, derive, cut, assemble (6.4, W1, W21).

`inputs` gathers every uncut table the world holds, by name: the app's tables, the feed's
and the provider's rows, the outside systems' rows and the two csv files parsed into text
rows. The export writer's faults (a later module) take that mapping and give one back.
`assemble` derives `dated_lines`, `latest_stock` and `customer_months` with the rules of
`roastery_spec.derivations`, cuts each table as contract A's `cut` says, and projects it to
contract A's `columns`.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
from collections.abc import Callable, Collection, Mapping
from types import MappingProxyType
from typing import Final

import duckdb
from roastery.pipeline import Rows
from roastery_spec.contract import TABLES, Table
from roastery_spec.derivations import C01_YEAR, DATED_LINES, LATEST_STOCK

from roastery_sim.play import Played
from roastery_sim.script import CAST

TINY: Final = tuple(t for t in TABLES if 'tiny' in t.extracts)
"""The 30 tables tiny holds, in contract order."""

RAW: Final = ('raw_customers', 'raw_lines')
"""The csv export's two files, each `<name>.csv`, parsed into text rows."""

# The cuts, as contract A's sentences state them ------------------------

ORDERS: Final = tuple(o.value for o in CAST.orders)
"""The orders of the cast, O-101 to O-108: their lines, payments and events go with them."""
CAST_CUSTOMERS: Final = tuple(c.value for c in CAST.customers)
"""The cast's customers, C-07 among them: the cast's changes are theirs."""
CUSTOMERS: Final = tuple(c for c in CAST_CUSTOMERS if c != 'C-07')
"""The six named customers, C-01 to C-06: C-07 is erased, so `customers` has no row of them."""
SUBSCRIPTIONS: Final = tuple(s.value for s in CAST.subscriptions)
"""The subscriptions of the cast, S-1 to S-7."""
MONTHS_OF: Final = ('C-01',)
"""`customer_months` is C-01's."""

RAW_CUSTOMERS: Final = ('C-01', 'C-02', 'C-03', 'C-04', 'C-05')
RAW_LINES: Final = ('L-01', 'L-02', 'L-03', 'L-06', 'L-07')
VISITORS: Final = ('V-1', 'V-2', 'V-3', 'V-4')

STOCK_DAYS: Final = tuple(dt.date(2026, 10, day) for day in range(5, 10))
STOCK_PRODUCTS: Final = ('P-10', 'P-20')
FX_DAYS: Final = tuple(dt.date(2026, 10, day) for day in range(2, 8))
EXTRACT_NIGHTS: Final = (dt.date(2026, 10, 8), dt.date(2026, 10, 9))

TILL_MEMBERS: Final = (1001, 1002, 1003, 1004, 1005, 1006)
"""The listed club members."""
TRIAL_RECEIPT: Final = 'R-5001'
"""The trial day's receipt, rung before the club list came into the till: no member."""

REFERENCE: Final = tuple(t.name for t in TINY if t.cut == 'whole reference')

DERIVED_FROM: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        'dated_lines': ('order_lines', 'orders'),
        'latest_stock': ('stock_daily',),
        'customer_months': ('orders', 'order_lines', 'subscriptions'),
    }
)
"""Each derived table and the uncut tables its rule reads."""

_SPECS: Final = MappingProxyType({t.name: t for t in TABLES})


# Gather ------------------------------------------------------------------


def _parse(name: str, text: str | None) -> Rows:
    """A csv file of the export as `Rows` of text: an empty cell stays ''."""
    columns = tuple(c.name for c in _SPECS[name].columns)
    if text is None:  # a play stopped before the csv export ran
        return Rows(name, columns, ())
    found = list(csv.reader(io.StringIO(text, newline='')))
    if not found or tuple(found[0]) != columns:
        raise ValueError(f'{name}.csv: header {found[:1]} is not {columns}')
    for row in found[1:]:
        if len(row) != len(columns):
            raise ValueError(f'{name}.csv: a row has {len(row)} cells, not {len(columns)}')
    return Rows(name, columns, tuple(tuple(row) for row in found[1:]))


def inputs(played: Played) -> Mapping[str, Rows]:
    """Every uncut table of the world, by name, `source` still on the app's tables."""
    gathered = [
        *played.tables.values(),
        played.feed,
        played.payments,
        *played.outside,
        *(_parse(name, played.csv.get(f'{name}.csv')) for name in RAW),
    ]
    tables: dict[str, Rows] = {}
    for rows in gathered:
        if rows.name in tables:
            raise ValueError(f'table {rows.name} is given twice')
        tables[rows.name] = rows
    return MappingProxyType(tables)


# Derive ------------------------------------------------------------------


def _cell(value: object) -> object:
    """A value as DuckDB takes it: a UTC moment loses its zone, which DuckDB would read in
    the session's own."""
    if isinstance(value, dt.datetime) and value.tzinfo is not None:
        if value.utcoffset() != dt.timedelta(0):
            raise ValueError(f'moment {value!r} is not in UTC')
        return value.replace(tzinfo=None)
    return value


def _load(con: duckdb.DuckDBPyConnection, rows: Rows) -> None:
    """The table on contract A's columns, typed as contract A types them."""
    columns = _SPECS[rows.name].columns
    con.execute(f'CREATE TABLE {rows.name} ({", ".join(f"{c.name} {c.type}" for c in columns)})')
    projected = _project(rows)
    if projected.rows:
        marks = ', '.join('?' for _ in columns)
        con.executemany(
            f'INSERT INTO {rows.name} VALUES ({marks})',
            [tuple(_cell(v) for v in row) for row in projected.rows],
        )


def _derive(name: str, sql: str, tables: Mapping[str, Rows]) -> Rows:
    """The derived table: its rule run in DuckDB over the uncut tables it reads."""
    con = duckdb.connect()
    try:
        con.execute("SET TimeZone = 'UTC'")
        for source in DERIVED_FROM[name]:
            _load(con, _table(tables, source))
        columns = tuple(c.name for c in _SPECS[name].columns)
        found = con.execute(f'SELECT {", ".join(columns)} FROM ({sql})').fetchall()
        return Rows(name, columns, tuple(tuple(row) for row in found))
    finally:
        con.close()


# Cut and assemble ----------------------------------------------------------


def _table(tables: Mapping[str, Rows], name: str) -> Rows:
    if name not in tables:
        raise ValueError(f'no table {name} to cut tiny from')
    return tables[name]


def _project(rows: Rows) -> Rows:
    """The rows on contract A's columns, in its order: `added` and `source` dropped."""
    columns = tuple(c.name for c in _SPECS[rows.name].columns)
    missing = [c for c in columns if c not in rows.columns]
    if missing:
        raise ValueError(f'table {rows.name} lacks {missing}')
    at = [rows.columns.index(c) for c in columns]
    return Rows(rows.name, columns, tuple(tuple(row[i] for i in at) for row in rows.rows))


def _key(value: object) -> object:
    """A raw cell as a key to match: the export's text may carry blanks, a tab, a no-break
    space or the wrong case around the id (W11); the cell itself is kept as it is."""
    return value.strip().upper() if isinstance(value, str) else value


def _keep(rows: Rows, test: Callable[[Mapping[str, object]], bool]) -> Rows:
    kept = tuple(row for row in rows.rows if test(dict(zip(rows.columns, row, strict=True))))
    return Rows(rows.name, rows.columns, kept)


def _within(column: str, wanted: Collection[object]) -> Callable[[Mapping[str, object]], bool]:
    return lambda row: row[column] in wanted


def _raw_within(column: str, wanted: Collection[str]) -> Callable[[Mapping[str, object]], bool]:
    return lambda row: _key(row[column]) in wanted


def _stock(row: Mapping[str, object]) -> bool:
    """A count of P-10 or P-20 on a day of 5 to 9 October."""
    return row['stock_date'] in STOCK_DAYS and row['product_id'] in STOCK_PRODUCTS


def _receipt(row: Mapping[str, object]) -> bool:
    """A listed member's receipt, or the trial day's."""
    return row['member_no'] in TILL_MEMBERS or row['receipt_id'] == TRIAL_RECEIPT


def _renumbered(rows: Rows) -> Rows:
    """The change log's rows in `seq` order, `seq` numbered again from 1."""
    at = rows.columns.index('seq')
    ordered = sorted(rows.rows, key=lambda row: row[at])  # type: ignore[arg-type, return-value]
    renumbered = tuple((*row[:at], n, *row[at + 1 :]) for n, row in enumerate(ordered, 1))
    return Rows(rows.name, rows.columns, renumbered)


def _sorted(rows: Rows, spec: Table) -> Rows:
    """The rows by key, then the other columns, None first (as the text sorts them)."""
    first = [rows.columns.index(k) for k in spec.key]
    order = first + [i for i in range(len(rows.columns)) if i not in first]

    def place(row: tuple[object, ...]) -> tuple:
        return tuple((row[i] is not None, row[i]) for i in order)

    return Rows(rows.name, rows.columns, tuple(sorted(rows.rows, key=place)))


def assemble(tables: Mapping[str, Rows]) -> tuple[Rows, ...]:
    """Tiny's 30 tables in contract order, each on contract A's columns, its rows sorted.

    `tables` holds the uncut tables, faulted or not, by name; names tiny does not read are
    ignored, and a derived table given is derived again. `customer_months` reads the uncut
    year: tiny's cut keeps none of C-01's earlier orders.
    """
    orders = _within('order_id', ORDERS)
    cut_lines = _keep(_project(_table(tables, 'order_lines')), orders)
    lines = {row[0] for row in cut_lines.rows}
    cut_receipts = _keep(_project(_table(tables, 'till_receipts')), _receipt)
    receipt_ids = {row[0] for row in cut_receipts.rows}
    derived = {
        'dated_lines': lambda: _derive('dated_lines', DATED_LINES, tables),
        'latest_stock': lambda: _derive('latest_stock', LATEST_STOCK, tables),
        'customer_months': lambda: _derive('customer_months', C01_YEAR, tables),
    }
    cuts: dict[str, Callable[[Mapping[str, object]], bool]] = {
        'customers': _within('customer_id', CUSTOMERS),
        'orders': orders,
        'order_lines': orders,
        'dated_lines': _within('line_id', lines),
        'fx_rates': _within('rate_date', FX_DAYS),
        'payments': orders,
        'order_events': orders,
        'stock_daily': _stock,
        'latest_stock': _stock,
        'customer_extracts': _within('extract_date', EXTRACT_NIGHTS),
        'customer_changes': _within('customer_id', CAST_CUSTOMERS),
        'line_stamps': orders,
        'raw_customers': _raw_within('customer_id', RAW_CUSTOMERS),
        'raw_lines': _raw_within('line_id', RAW_LINES),
        'web_events': _within('visitor_id', VISITORS),
        'subscriptions': _within('subscription_id', SUBSCRIPTIONS),
        'till_receipts': _receipt,
        'till_lines': _within('receipt_id', receipt_ids),
        'till_members': _within('member_no', TILL_MEMBERS),
        'customer_months': _within('customer_id', MONTHS_OF),
    }
    assembled: list[Rows] = []
    for spec in TINY:
        if spec.name in derived:
            rows = derived[spec.name]()
        else:
            rows = _project(_table(tables, spec.name))
        if spec.name in cuts:
            rows = _keep(rows, cuts[spec.name])
        elif spec.name not in REFERENCE:
            raise ValueError(f'no cut for {spec.name}: {spec.cut}')
        if spec.name == 'customer_changes':
            rows = _renumbered(rows)
        assembled.append(_sorted(rows, spec))
    return tuple(assembled)
