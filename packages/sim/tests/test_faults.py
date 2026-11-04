"""The export writer's faults: the log names what was planted, and the faulted play is tiny."""

from __future__ import annotations

import csv
import datetime as dt
import io
from collections import Counter
from collections.abc import Mapping
from functools import cache
from pathlib import Path

import duckdb
from roastery.pipeline import Rows
from roastery_sim import dataset_sql, faults, play, tiny
from roastery_spec import baseline

BASELINE = (Path(baseline.__file__).parent / 'baseline' / 'dataset.sql').read_text(encoding='utf-8')
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


# The gate's mechanics, one unit early (U9 makes it gate.py) -----------------


def _load(con: duckdb.DuckDBPyConnection, schema: str, text: str) -> list[str]:
    con.execute(f'CREATE SCHEMA {schema}')
    con.execute(f'SET schema = {schema}')
    found = baseline.tables(text)
    baseline.database(found, con=con)
    return [t['name'] for t in found]


def _count(con: duckdb.DuckDBPyConnection, sql: str) -> int:
    row = con.execute(sql).fetchone()
    assert row is not None
    return row[0]


def _differences(mine: str, theirs: str) -> list[str]:
    """Each table where the two texts differ: its names, its columns or its rows."""
    con = duckdb.connect()
    try:
        names = _load(con, 'mine', mine)
        if names != _load(con, 'theirs', theirs):
            return [f'tables: {names}']
        out = []
        for name in names:
            if con.execute(f'DESCRIBE mine.{name}').fetchall() != (
                con.execute(f'DESCRIBE theirs.{name}').fetchall()
            ):
                out.append(f'{name}: columns')
                continue
            for one, two in (('mine', 'theirs'), ('theirs', 'mine')):
                left = f'SELECT * FROM {one}.{name} EXCEPT ALL SELECT * FROM {two}.{name}'
                if _count(con, f'SELECT count(*) FROM ({left})'):
                    out.append(f'{name}: only in {one}: {con.execute(left).fetchall()}')
        return out
    finally:
        con.close()


def test_the_faulted_play_is_the_baseline() -> None:
    _, faulted, _ = _faulted()
    text = dataset_sql.render(tiny.assemble(faulted), seed=0)
    assert len(baseline.tables(text)) == 30
    assert _differences(text, BASELINE) == []
