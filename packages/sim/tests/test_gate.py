"""The gate: the simulator's tiny is `dataset.sql`, and what tiny's cut never sees is typed right.

The cell comparison holds the 30 tiny tables. The app's 23 tables are also held whole, uncut,
against contract A's columns and types: `month` and `full` (6.5) carry the rows tiny drops.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import get_args

import pytest
from roastery.pipeline import Rows
from roastery.ports import Source
from roastery_sim import build, dataset_sql, faults, gate, play, tiny
from roastery_spec import baseline, claims
from roastery_spec.contract import TABLES

BASELINE = (Path(baseline.__file__).parent / 'baseline' / 'dataset.sql').read_text(encoding='utf-8')
SPECS = {t.name: t for t in TABLES}
DECIMAL = re.compile(r'^DECIMAL\((\d+),(\d+)\)$')


@cache
def _built() -> build.Built:
    return build.build()


def _loaded(text: str) -> dict[str, Rows]:
    """The text's tables as rows, read back through DuckDB."""
    con = baseline.database(baseline.tables(text))
    try:
        found = {}
        for (name,) in con.execute('SHOW TABLES').fetchall():
            cursor = con.execute(f'SELECT * FROM {name}')
            columns = tuple(d[0] for d in cursor.description)
            found[name] = Rows(name, columns, tuple(tuple(r) for r in cursor.fetchall()))
        return found
    finally:
        con.close()


def test_the_simulators_tiny_is_the_baseline() -> None:
    text = _built().text
    assert len(baseline.tables(text)) == 30
    assert gate.differences(text, BASELINE) == []


def test_the_gate_sees_the_unfaulted_play() -> None:
    text = dataset_sql.render(tiny.assemble(tiny.inputs(play.play())), seed=0)
    found = gate.differences(text, BASELINE)
    assert {d.table for d in found} == {
        'order_lines',
        'line_stamps',
        'dated_lines',
        'order_events',
        'stock_daily',
        'raw_customers',
        'raw_lines',
    }


def test_the_gate_counts_a_repeated_row() -> None:
    # PAY-1 was delivered twice: a text that holds it once differs, though EXCEPT would not see it
    payments = _loaded(BASELINE)['payments']
    first = next(i for i, row in enumerate(payments.rows) if row[0] == 'PAY-1')
    once = payments.rows[:first] + payments.rows[first + 1 :]
    assert len([row for row in once if row[0] == 'PAY-1']) == 1
    text = dataset_sql.render([Rows('payments', payments.columns, once)], seed=0)
    found = gate.differences(text, BASELINE, tables=('payments',))
    assert [(d.table, d.what) for d in found] == [
        ('payments', 'count'),
        ('payments', 'rows only in theirs'),
    ]
    assert found[1].detail.startswith("1: ('PAY-1'")


def test_the_data_folder_owes_nothing(tmp_path: Path) -> None:
    built = _built()
    build.write(built, tmp_path, seed=0, shop_version='0.0.0')
    data = tmp_path / 'data'
    manifest = json.loads((data / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest['extract'] == 'tiny'
    assert claims.owed(data) == ()
    assert manifest['defects'] == [d.as_dict() for d in built.defects]
    assert (tmp_path / 'tiny.sql').read_bytes() == built.text.encode('utf-8')


def _fits(value: object, kind: str) -> bool:
    """Whether a value has the Python type of its contract type, exactly."""
    if kind == 'VARCHAR':
        return isinstance(value, str)
    if kind == 'INTEGER':
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == 'BOOLEAN':
        return isinstance(value, bool)
    if kind == 'DATE':
        return isinstance(value, dt.date) and not isinstance(value, dt.datetime)
    if kind == 'TIMESTAMP':
        return (
            isinstance(value, dt.datetime)
            and value.utcoffset() == dt.timedelta(0)
            and value.second == value.microsecond == 0
        )
    scale = DECIMAL.match(kind)
    if scale is None:
        raise ValueError(f'unknown type {kind}')
    return (
        isinstance(value, Decimal)
        and value.is_finite()
        and value.as_tuple().exponent == -int(scale.group(2))
    )


@pytest.mark.parametrize('store', ['memory', 'sqlite'])
def test_the_app_tables_have_contract_as_columns_and_types(store: str) -> None:
    tables = play.play(store=store).tables  # type: ignore[arg-type]
    assert set(tables) == {t.name for t in TABLES if t.system.startswith('app database')}
    sources = set(get_args(Source))
    for name, rows in tables.items():
        spec = SPECS[name]
        columns = spec.columns + spec.added
        stamped = () if name == 'kinds' else ('source',)
        assert rows.columns == tuple(c.name for c in columns) + stamped, name
        for row in rows.rows:
            assert len(row) == len(rows.columns), name
            for column, value in zip(columns, row, strict=False):
                if value is not None:
                    assert _fits(value, column.type), (name, column.name, value)
            if stamped:
                assert row[-1] in sources, (name, row)


def _holds(tables: dict[str, Rows], entry: faults.Defect) -> bool:
    """Whether tiny holds the entry: its order is a cast order, or its row is in tiny's table."""
    if entry.kind == 'dropped':
        return entry.key in tiny.ORDERS
    rows = tables[entry.table]
    if entry.table in tiny.RAW:
        at = rows.columns.index(faults.TABLE_KEYS[entry.table][0])
        return any(str(row[at]).strip().upper() == entry.key for row in rows.rows)
    return any(faults.key_of(rows, row) == entry.key for row in rows.rows)


def test_the_manifest_holds_the_defects_tiny_holds() -> None:
    built = _built()
    _, log = faults.apply(tiny.inputs(play.play()))
    held = _loaded(built.text)
    assert built.defects == tuple(e for e in log if _holds(held, e))
    # the resend of 7 October sends every product; tiny's stock is P-10's and P-20's alone
    left = {(e.table, e.kind, e.key.split(', ')[0]) for e in log if e not in built.defects}
    assert left == {
        ('stock_daily', 'resent', 'P-11'),
        ('stock_daily', 'resent', 'P-12'),
        ('stock_daily', 'resent', 'P-21'),
    }
