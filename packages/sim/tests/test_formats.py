"""The dataset text and the data folder: what can quietly break the data."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest
from roastery.pipeline import Rows
from roastery_sim.dataset_sql import render
from roastery_sim.folder import write
from roastery_spec import baseline
from roastery_spec.contract import by_name

BASELINE = (Path(baseline.__file__).parent / 'baseline' / 'dataset.sql').read_text(encoding='utf-8')


def _load_into(con: duckdb.DuckDBPyConnection, schema: str, text: str) -> None:
    con.execute(f'CREATE SCHEMA {schema}')
    con.execute(f'SET schema = {schema}')
    baseline.database(baseline.tables(text), con=con)


def _rows(con: duckdb.DuckDBPyConnection, name: str) -> Rows:
    cursor = con.execute(f'SELECT * FROM a.{name}')
    columns = tuple(d[0] for d in cursor.description)
    return Rows(name, columns, tuple(tuple(r) for r in cursor.fetchall()))


def _count(con: duckdb.DuckDBPyConnection, sql: str) -> int:
    row = con.execute(sql).fetchone()
    assert row is not None
    return row[0]


def test_round_trip_on_every_baseline_table() -> None:
    found = baseline.tables(BASELINE)
    assert len(found) == 30
    con = duckdb.connect()
    _load_into(con, 'a', BASELINE)
    text = render([_rows(con, t['name']) for t in found], seed=0)
    assert text.startswith('-- roastery-data tiny, written by roastery_sim, seed 0\n\n')
    assert text.endswith(';\n') and not text.endswith('\n\n')
    assert '\r' not in text
    again = baseline.tables(text)
    assert [(t['name'], t['key'], t['grain']) for t in again] == [
        (t['name'], t['key'], t['grain']) for t in found
    ]
    _load_into(con, 'b', text)
    for table in found:
        name = table['name']
        assert con.execute(f'DESCRIBE a.{name}').fetchall() == (
            con.execute(f'DESCRIBE b.{name}').fetchall()
        )
        assert _count(con, f'SELECT count(*) FROM a.{name}') == _count(
            con, f'SELECT count(*) FROM b.{name}'
        )
        for one, two in (('a', 'b'), ('b', 'a')):
            left = f'SELECT * FROM {one}.{name} EXCEPT ALL SELECT * FROM {two}.{name}'
            assert _count(con, f'SELECT count(*) FROM ({left})') == 0, name


def _stamp_rows(moment: datetime) -> Rows:
    """One order event stamped at the moment, loaded at the same moment."""
    row = ('E-01', 'O-101', 'placed', moment, moment)
    return Rows('order_events', tuple(c.name for c in by_name()['order_events'].columns), (row,))


def test_timestamp_with_seconds_is_refused() -> None:
    with pytest.raises(ValueError):
        render([_stamp_rows(datetime(2026, 10, 1, 8, 30, 15))], seed=0)
    with pytest.raises(ValueError):
        render([_stamp_rows(datetime(2026, 10, 1, 8, 30, 0, 5))], seed=0)
    plus_two = timezone(timedelta(hours=2))
    with pytest.raises(ValueError):
        render([_stamp_rows(datetime(2026, 10, 1, 8, 30, tzinfo=plus_two))], seed=0)
    utc = render([_stamp_rows(datetime(2026, 10, 1, 8, 30, tzinfo=UTC))], seed=0)
    assert "TIMESTAMP '2026-10-01 08:30'" in utc


def test_wrong_columns_and_wrong_types_are_refused() -> None:
    with pytest.raises(ValueError, match='customers'):
        render([Rows('customers', ('customer_id',), (('C-1',),))], seed=0)
    cols = tuple(c.name for c in by_name()['customers'].columns)
    with pytest.raises(ValueError):
        render([Rows('customers', cols, ((1, 'a', None, None, None),))], seed=0)


def test_zero_rows_parse_and_load() -> None:
    cols = tuple(c.name for c in by_name()['customers'].columns)
    text = render([Rows('customers', cols, ())], seed=0)
    con = baseline.database(baseline.tables(text))
    assert _count(con, 'SELECT count(*) FROM customers') == 0


def test_decimal_scale() -> None:
    name = next(n for n, t in by_name().items() if any(c.type == 'DECIMAL(7,2)' for c in t.columns))
    spec = by_name()[name]
    cols = tuple(c.name for c in spec.columns)

    def one(value: Decimal) -> Rows:
        row = tuple(value if c.type == 'DECIMAL(7,2)' else None for c in spec.columns)
        return Rows(name, cols, (row,))

    assert '129.00' in render([one(Decimal('129'))], seed=0)
    with pytest.raises(ValueError):
        render([one(Decimal('1.234'))], seed=0)


def test_write_baseline_folder(tmp_path: Path) -> None:
    manifest = write(
        BASELINE, tmp_path, extract='tiny', seed=0, defects=[{'id': 'd'}], shop_version='1'
    )
    assert len(list(tmp_path.glob('*.parquet'))) == 30
    saved = json.loads((tmp_path / 'manifest.json').read_text(encoding='utf-8'))
    assert saved == manifest
    assert manifest['serves'] == ['tiny']
    con = duckdb.connect()
    for name, count in manifest['tables'].items():
        path = (tmp_path / f'{name}.parquet').as_posix()
        assert _count(con, f"SELECT count(*) FROM '{path}'") == count


def test_two_writes_are_identical(tmp_path: Path) -> None:
    one, two = tmp_path / 'one', tmp_path / 'two'
    for out in (one, two):
        write(BASELINE, out, extract='tiny', seed=0, defects=[], shop_version='1')
    names = sorted(p.name for p in one.iterdir())
    assert names == sorted(p.name for p in two.iterdir())
    for name in names:
        assert (one / name).read_bytes() == (two / name).read_bytes()
