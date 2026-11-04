"""The export writer's faults, added after a correct app, and the defect log (6.4, D10, W11).

`apply` takes the uncut tables `tiny.inputs` gathers and gives them back with every planted
row and cell the baseline holds, beside a log naming each one: what the app wrote and what
the writer sent instead. It is pure: the tables given are not changed. The planted values
are the constants below, each as `dataset.sql` has it; the values a fault keeps or copies
(L-04's row, O-102's moment, the app's counts) are read from the app's rows.

`csv_text` writes a faulted csv file as the landing holds it (W12).
"""

from __future__ import annotations

import csv
import datetime as dt
import io
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Final, Literal

from roastery.pipeline import Rows

Kind = Literal['duplicate', 'orphan', 'null', 'dropped', 'wrong', 'resent', 'text']

TAB: Final = chr(9)
NBSP: Final = chr(160)

# order_lines and line_stamps -----------------------------------------------

DUPLICATE: Final = ('L-05', 'L-04')
"""L-05 is a copy of L-04, on O-103: P-10 three times at 129.00."""
NULL_QTY: Final = 'L-07'
"""L-07's quantity is lost: NULL in `order_lines` and in `line_stamps`."""
ORPHAN: Final = 'L-09'
ORPHAN_ORDER: Final = 'O-102'
ORPHAN_PRODUCT: Final = 'P-99'
"""L-09 names a product the shop never listed, on O-102, stamped at O-102's moment."""
ORPHAN_QTY: Final = 1
ORPHAN_PRICE: Final = Decimal('199.00')

# order_events --------------------------------------------------------------

HIDDEN_ORDERS: Final = ('O-103', 'O-105', 'O-107')
"""Every event of these orders is dropped, by `order_id` (W6): the feed never sent them."""

# stock_daily ---------------------------------------------------------------

STOCK_DAY: Final = dt.date(2026, 10, 7)
WRONG_PRODUCT: Final = 'P-10'
WRONG_COUNT: Final = 26
"""The first send of 7 October: P-10's count at close, 36, sent as 26."""
RESENT_AT: Final = dt.datetime(2026, 10, 8, 6, 30, tzinfo=dt.UTC)
"""The recount: every product of the day sent again with the app's counts (ADR 0011)."""

# raw_customers and raw_lines: (the clean id, column, the text written) -----

RAW_CUSTOMERS: Final[tuple[tuple[str, str, str | None], ...]] = (
    ('C-01', 'customer_id', 'C-01 '),
    ('C-01', 'country', 'no'),
    ('C-01', 'postal_code', '150'),
    ('C-01', 'joined', '01.03.2024'),
    ('C-01', 'email', ' Ingrid@Example.invalid'),
    ('C-02', 'customer_id', 'c-02'),
    ('C-02', 'country', ' SE'),
    ('C-03', 'customer_id', TAB + 'C-03'),
    ('C-03', 'email', 'mikkel@example.invalid '),
    ('C-04', 'customer_id', 'C-04' + NBSP),
    ('C-04', 'joined', '02.06.2025'),
    ('C-05', 'email', None),
)
"""Twelve cells. C-05's e-mail: the export writes '' for every missing value (A17); the
writer sends NULL there, beside the '' of its country and postal code."""

RAW_LINES: Final[tuple[tuple[str, str, str | None], ...]] = (
    ('L-01', 'unit_price', '129,00'),
    ('L-02', 'product_id', ' p-20'),
    ('L-03', 'unit_price', '349'),
    ('L-06', 'unit_price', '549,00'),
    ('L-07', 'qty', 'n/a'),
)
"""Five cells."""

TABLE_KEYS: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        'order_lines': ('line_id',),
        'line_stamps': ('line_id',),
        'order_events': ('order_id',),
        'stock_daily': ('product_id', 'stock_date', 'counted_at'),
        'raw_customers': ('customer_id',),
        'raw_lines': ('line_id',),
    }
)
"""What a log entry's `key` names in each table: `order_events` is logged per order, and a
raw table's key is the clean id (the cell itself may carry the fault)."""


@dataclass(frozen=True, order=True)
class Defect:
    """One planted fault: where it is, its kind, and what the app wrote and the writer sent.

    `key` is the key's cells as text, joined by ', '; `column` is '' for a row-level fault.
    A value is text: 'NULL' for a NULL. A row the app has not got has `app` ''; a row the
    writer dropped has `written` ''. An added row's `written` is its cells joined by ', ',
    and a dropped order's `app` the event ids it lost.
    """

    table: str
    key: str
    column: str
    kind: Kind
    app: str
    written: str

    def as_dict(self) -> dict[str, str]:
        """The entry for the manifest, its fields in order."""
        return asdict(self)


def text(value: object) -> str:
    """A cell as the log writes it."""
    if value is None:
        return 'NULL'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, Decimal):
        return f'{value:f}'
    if isinstance(value, dt.datetime):
        if value.tzinfo is not None:
            if value.utcoffset() != dt.timedelta(0):
                raise ValueError(f'moment {value!r} is not in UTC')
            value = value.replace(tzinfo=None)
        return f'{value:%Y-%m-%d %H:%M}'
    if isinstance(value, dt.date):
        return value.isoformat()
    return str(value)


def key_of(rows: Rows, row: Sequence[object]) -> str:
    """The log's key of a row of one of the faulted tables."""
    return ', '.join(text(row[rows.columns.index(c)]) for c in TABLE_KEYS[rows.name])


def row_text(rows: Rows, row: Sequence[object]) -> str:
    """An added row as the log writes it: its cells, `source` left out."""
    return ', '.join(text(v) for c, v in zip(rows.columns, row, strict=True) if c != 'source')


# The faults, table by table ------------------------------------------------


def _table(tables: Mapping[str, Rows], name: str) -> Rows:
    if name not in tables:
        raise ValueError(f'no table {name} to fault')
    return tables[name]


def _one(rows: Rows, test: Callable[[tuple[object, ...]], bool], what: str) -> int:
    """The place of the one row the test picks: a fault on a row the app did not write, or
    on two, is refused, never skipped."""
    found = [i for i, row in enumerate(rows.rows) if test(row)]
    if len(found) != 1:
        raise ValueError(f'{rows.name}: {len(found)} rows for {what}, not 1')
    return found[0]


def _by_id(rows: Rows, value: str) -> int:
    at = rows.columns.index(TABLE_KEYS[rows.name][0])
    return _one(rows, lambda row: row[at] == value, value)


def _absent(rows: Rows, value: str) -> None:
    at = rows.columns.index(TABLE_KEYS[rows.name][0])
    if any(row[at] == value for row in rows.rows):
        raise ValueError(f'{rows.name}: the app already has {value}')


def _set(row: tuple[object, ...], at: int, value: object) -> tuple[object, ...]:
    return (*row[:at], value, *row[at + 1 :])


def _lines(rows: Rows, log: list[Defect], *, stamps: bool) -> Rows:
    """L-05 a copy of L-04, L-07's qty NULL, L-09 an orphan on O-102: in `order_lines` the
    product and price are planted, in `line_stamps` the stamp is O-102's moment."""
    out = list(rows.rows)
    line, order, qty = (rows.columns.index(c) for c in ('line_id', 'order_id', 'qty'))
    copy, of = DUPLICATE
    _absent(rows, copy)
    _absent(rows, ORPHAN)
    duplicate = _set(out[_by_id(rows, of)], line, copy)
    at = _by_id(rows, NULL_QTY)
    log.append(Defect(rows.name, NULL_QTY, 'qty', 'null', text(out[at][qty]), 'NULL'))
    out[at] = _set(out[at], qty, None)
    # The orphan is made from a line of its order: its moment and `source` are the order's.
    first = min(
        (row for row in rows.rows if row[order] == ORPHAN_ORDER),
        key=lambda row: str(row[line]),
        default=None,
    )
    if first is None:
        raise ValueError(f'{rows.name}: no line of {ORPHAN_ORDER} to plant {ORPHAN} on')
    orphan = _set(_set(first, line, ORPHAN), qty, ORPHAN_QTY)
    if not stamps:
        orphan = _set(orphan, rows.columns.index('product_id'), ORPHAN_PRODUCT)
        orphan = _set(orphan, rows.columns.index('unit_price'), ORPHAN_PRICE)
    out += [duplicate, orphan]
    log.append(Defect(rows.name, copy, '', 'duplicate', '', row_text(rows, duplicate)))
    log.append(Defect(rows.name, ORPHAN, '', 'orphan', '', row_text(rows, orphan)))
    return Rows(rows.name, rows.columns, tuple(out))


def _events(rows: Rows, log: list[Defect]) -> Rows:
    """Every event of the hidden orders dropped; one entry per order, naming the events."""
    event, order = rows.columns.index('event_id'), rows.columns.index('order_id')
    for hidden in HIDDEN_ORDERS:
        ids = sorted(str(row[event]) for row in rows.rows if row[order] == hidden)
        if not ids:
            raise ValueError(f'{rows.name}: no event of {hidden} to drop')
        log.append(Defect(rows.name, hidden, '', 'dropped', ', '.join(ids), ''))
    kept = tuple(row for row in rows.rows if row[order] not in HIDDEN_ORDERS)
    return Rows(rows.name, rows.columns, kept)


def _stock(rows: Rows, log: list[Defect]) -> Rows:
    """7 October sent twice: first with P-10's 26, then every count of the day again at
    8 Oct 06:30, the app's own (ADR 0011)."""
    product, day, on_hand, counted = (
        rows.columns.index(c) for c in ('product_id', 'stock_date', 'on_hand', 'counted_at')
    )
    counts = [row for row in rows.rows if row[day] == STOCK_DAY]
    if any(row[counted] == RESENT_AT for row in rows.rows):
        raise ValueError(f'{rows.name}: the app already has a count at {RESENT_AT}')
    out = list(rows.rows)
    at = _one(
        rows,
        lambda row: row[product] == WRONG_PRODUCT and row[day] == STOCK_DAY,
        f'{WRONG_PRODUCT} on {STOCK_DAY}',
    )
    key = key_of(rows, out[at])
    log.append(Defect(rows.name, key, 'on_hand', 'wrong', text(out[at][on_hand]), str(WRONG_COUNT)))
    out[at] = _set(out[at], on_hand, WRONG_COUNT)
    for row in counts:
        again = _set(row, counted, RESENT_AT)
        out.append(again)
        log.append(Defect(rows.name, key_of(rows, again), '', 'resent', '', row_text(rows, again)))
    return Rows(rows.name, rows.columns, tuple(out))


def _cells(rows: Rows, planted: Sequence[tuple[str, str, str | None]], log: list[Defect]) -> Rows:
    """The raw table with its dirty cells: each found by its clean id, before any is changed."""
    out = list(rows.rows)
    places = {ident: _by_id(rows, ident) for ident, _, _ in planted}
    for ident, column, value in planted:
        at = rows.columns.index(column)
        was = out[places[ident]][at]
        kind: Kind = 'null' if value is None else 'text'
        log.append(Defect(rows.name, ident, column, kind, text(was), text(value)))
        out[places[ident]] = _set(out[places[ident]], at, value)
    return Rows(rows.name, rows.columns, tuple(out))


def apply(tables: Mapping[str, Rows]) -> tuple[Mapping[str, Rows], tuple[Defect, ...]]:
    """The tables with the export writer's faults, and the log of them, sorted.

    The other tables are given back as they came. A fault whose row the app has not written
    (a play stopped early) is refused with a `ValueError`, never skipped.
    """
    log: list[Defect] = []
    faulted = dict(tables)
    faulted['order_lines'] = _lines(_table(tables, 'order_lines'), log, stamps=False)
    faulted['line_stamps'] = _lines(_table(tables, 'line_stamps'), log, stamps=True)
    faulted['order_events'] = _events(_table(tables, 'order_events'), log)
    faulted['stock_daily'] = _stock(_table(tables, 'stock_daily'), log)
    faulted['raw_customers'] = _cells(_table(tables, 'raw_customers'), RAW_CUSTOMERS, log)
    faulted['raw_lines'] = _cells(_table(tables, 'raw_lines'), RAW_LINES, log)
    ordered = tuple(sorted(log, key=lambda d: (d.table, d.key, d.column)))
    return MappingProxyType(faulted), ordered


def csv_text(rows: Rows) -> str:
    """A faulted csv file as the landing holds it: a header, then the rows, LF endings.

    Every cell is quoted but a NULL, which is a bare empty field: `""` is '' and nothing at
    all is NULL. `csv.reader(..., quoting=csv.QUOTE_NOTNULL)` reads them back so.
    """
    out = io.StringIO(newline='')
    writer = csv.writer(out, quoting=csv.QUOTE_NOTNULL, lineterminator='\n')
    writer.writerow(rows.columns)
    writer.writerows(rows.rows)
    return out.getvalue()
