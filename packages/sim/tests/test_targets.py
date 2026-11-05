"""The targets: the baseline's eight tier-3 tables, and `demand` as the daily_sales formula."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import duckdb
from roastery_sim import targets
from roastery_spec import baseline


def test_the_tables_equal_the_baseline_build(tmp_path: Path) -> None:
    baseline.build(tmp_path)
    found = targets.build()
    assert tuple(found.tables) == targets.TABLES
    for name, rows in found.tables.items():
        path = (tmp_path / f'{name}.parquet').as_posix()
        cursor = duckdb.connect().execute(f"SELECT * FROM '{path}'")
        assert rows.columns == tuple(d[0] for d in cursor.description)
        assert sorted(rows.rows, key=repr) == sorted(map(tuple, cursor.fetchall()), key=repr), name
    assert len(found.lessons) == 600  # each lesson's composition is checked at build


def test_demand_is_daily_sales_on_the_window() -> None:
    found = targets.build()
    for n in range(730):
        day = date(2024, 10, 1) + timedelta(days=n)
        for product in ('P-10', 'P-11', 'P-20', 'P-21'):
            assert found.demand(day, product) == found.daily_sales.get((day, product)), (
                day,
                product,
            )
