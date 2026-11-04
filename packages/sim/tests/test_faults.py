"""The export writer's faults: the log names what was planted, in the app's rows and the writer's.

That the faulted play is tiny, cell for cell, is the gate's test (`test_gate.py`).
"""

from __future__ import annotations

import csv
import datetime as dt
import io
from collections import Counter
from collections.abc import Mapping
from functools import cache

from roastery.pipeline import Rows
from roastery_sim import faults, play, tiny

ADDED = ('duplicate', 'orphan', 'resent')
"""The kinds whose row the app has not got."""


@cache
def _faulted() -> tuple[Mapping[str, Rows], Mapping[str, Rows], tuple[faults.Defect, ...]]:
    given = tiny.inputs(play.play())
    faulted, log = faults.apply(given)
    return given, faulted, log


def _found(tables: Mapping[str, Rows], entry: faults.Defect) -> list[tuple[object, ...]]:
    """The rows of the entry's table at its key; a raw table's id is matched as tiny cuts it."""
    rows = tables[entry.table]
    raw = entry.table in tiny.RAW

    def key(row: tuple[object, ...]) -> str:
        if raw:
            at = rows.columns.index(faults.TABLE_KEYS[entry.table][0])
            return str(row[at]).strip().upper()
        return faults.key_of(rows, row)

    return [row for row in rows.rows if key(row) == entry.key]


def _cell(tables: Mapping[str, Rows], entry: faults.Defect) -> str:
    (row,) = _found(tables, entry)
    return faults.text(row[tables[entry.table].columns.index(entry.column)])


def test_the_log_names_each_fault_where_it_is() -> None:
    given, faulted, log = _faulted()
    assert list(log) == sorted(log, key=lambda d: (d.table, d.key, d.column))
    assert len(set(log)) == len(log)
    for entry in log:
        assert set(entry.as_dict()) == {'table', 'key', 'column', 'kind', 'app', 'written'}
        if entry.kind == 'dropped':
            assert entry.written == ''
            assert _found(faulted, entry) == []
            ids = {str(row[0]) for row in _found(given, entry)}
            assert ids == set(entry.app.split(', ')), entry
        elif entry.kind in ADDED:
            assert entry.column == '' and entry.app == ''
            assert _found(given, entry) == []
            (row,) = _found(faulted, entry)
            assert faults.row_text(faulted[entry.table], row) == entry.written, entry
        else:
            assert entry.column != ''
            assert _cell(given, entry) == entry.app, entry
            assert _cell(faulted, entry) == entry.written, entry
    counts = Counter((d.table, d.kind) for d in log)
    assert counts[('raw_customers', 'text')] + counts[('raw_customers', 'null')] == 12
    assert counts[('raw_lines', 'text')] == 5
    assert counts[('order_events', 'dropped')] == 3


def test_the_correct_app_holds_none_of_the_faults() -> None:
    given, _, _ = _faulted()
    for name in ('order_lines', 'line_stamps'):
        rows = given[name]
        lines = {row[0]: row for row in rows.rows}
        assert 'L-05' not in lines and 'L-09' not in lines, name
        assert lines['L-07'][rows.columns.index('qty')] == 1, name
    stock = given['stock_daily']
    on_hand, counted = stock.columns.index('on_hand'), stock.columns.index('counted_at')
    assert all(row[on_hand] != 26 for row in stock.rows)
    assert all(row[counted].time() != dt.time(6, 30) for row in stock.rows)  # type: ignore[union-attr]


def test_no_fault_touches_c01s_year() -> None:
    given, faulted, log = _faulted()
    assert not any(d.key.startswith(('O-0000', 'L-0000')) for d in log)
    for name, rows in given.items():
        if 'source' in rows.columns:
            at = rows.columns.index('source')
            year = Counter(row for row in rows.rows if row[at] == 'simulator')
            again = Counter(row for row in faulted[name].rows if row[at] == 'simulator')
        else:
            year = Counter(row for row in rows.rows if str(row[0]).startswith('L-0000'))
            again = Counter(row for row in faulted[name].rows if str(row[0]).startswith('L-0000'))
        assert year == again, name


def test_apply_leaves_its_input_as_it_was() -> None:
    given = tiny.inputs(play.play())
    before = {name: rows.rows for name, rows in given.items()}
    faults.apply(given)
    assert {name: rows.rows for name, rows in given.items()} == before


def test_csv_text_tells_null_from_empty() -> None:
    _, faulted, _ = _faulted()
    rows = faulted['raw_customers']
    found = list(
        csv.reader(io.StringIO(faults.csv_text(rows), newline=''), quoting=csv.QUOTE_NOTNULL)
    )
    assert tuple(found[0]) == rows.columns
    assert [tuple(row) for row in found[1:]] == list(rows.rows)
    assert '\r' not in faults.csv_text(rows)


def _changes(
    given: Mapping[str, Rows], faulted: Mapping[str, Rows]
) -> Counter[tuple[str, str, str]]:
    """Every difference between the two mappings, table by table, as (table, key, column).

    A row only one side holds has column ''; a row both sides hold under one key but with other
    cells has one change per cell. Rows are matched by the log's key; a raw table's, by place.
    """
    found: Counter[tuple[str, str, str]] = Counter()
    for name, was in given.items():
        now = faulted[name]
        before = Counter(was.rows) - Counter(now.rows)
        after = Counter(now.rows) - Counter(was.rows)
        if name == 'order_events':
            for row in (*before.elements(), *after.elements()):
                found[(name, str(row[was.columns.index('order_id')]), '')] += 1
            continue
        if name in tiny.RAW:  # the key cell itself may be dirty: the rows are matched by place
            assert len(was.rows) == len(now.rows), name
            for old, new in zip(was.rows, now.rows, strict=True):
                for at, column in enumerate(was.columns):
                    if old[at] != new[at]:
                        found[(name, faults.key_of(was, old), column)] += 1
            continue
        left = {faults.key_of(was, row): row for row in before.elements()}
        right = {faults.key_of(now, row): row for row in after.elements()}
        for key in left.keys() | right.keys():
            if key in left and key in right:
                for at, column in enumerate(was.columns):
                    if left[key][at] != right[key][at]:
                        found[(name, key, column)] += 1
            else:
                found[(name, key, '')] += 1
    return found


def test_the_log_names_every_change_and_only_changes() -> None:
    given, faulted, log = _faulted()
    assert set(faulted) == set(given)
    changes = _changes(given, faulted)
    # order_events is logged once per order, however many events the order lost
    named = Counter((d.table, d.key, d.column) for d in log)
    dropped = {(d.table, d.key, d.column) for d in log if d.kind == 'dropped'}
    for entry in dropped:
        assert changes[entry] > 0, f'{entry} is logged but nothing was dropped'
        named[entry] = changes[entry]
    assert changes == named
    assert all(count == 1 for key, count in named.items() if key not in dropped)
