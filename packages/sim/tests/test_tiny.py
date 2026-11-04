"""Tiny's assembly: on the baseline's own rows, the cut and the derivations give the rows back."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from roastery.pipeline import Rows
from roastery_sim.tiny import assemble
from roastery_spec import baseline
from roastery_spec.contract import TABLES

BASELINE = (Path(baseline.__file__).parent / 'baseline' / 'dataset.sql').read_text(encoding='utf-8')
TINY = [t.name for t in TABLES if 'tiny' in t.extracts]
DERIVED = ('dated_lines', 'latest_stock', 'customer_months')


def _baseline() -> dict[str, Rows]:
    con = baseline.database(baseline.tables(BASELINE))
    found = {}
    for name in TINY:
        cursor = con.execute(f'SELECT * FROM {name}')
        columns = tuple(d[0] for d in cursor.description)
        found[name] = Rows(name, columns, tuple(tuple(r) for r in cursor.fetchall()))
    return found


def _types(rows: Rows) -> set[tuple[str, str]]:
    return {
        (column, type(value).__name__)
        for row in rows.rows
        for column, value in zip(rows.columns, row, strict=True)
        if value is not None
    }


def _months(rows: Rows) -> list[dict[str, object]]:
    return sorted(
        (dict(zip(rows.columns, row, strict=True)) for row in rows.rows),
        key=lambda row: row['month'],  # type: ignore[arg-type, return-value]
    )


def test_assemble_on_the_baseline_is_the_identity() -> None:
    theirs = _baseline()
    # On the baseline the uncut tables are the tiny ones; the derived tables are left out, so
    # they come from their sources (order_lines, orders, stock_daily, subscriptions) alone.
    # A table tiny does not read is ignored.
    uncut = {name: rows for name, rows in theirs.items() if name not in DERIVED}
    uncut['stock_movements'] = Rows('stock_movements', ('movement_id',), ())
    mine = assemble(uncut)
    assert [rows.name for rows in mine] == TINY
    for rows in mine:
        other = theirs[rows.name]
        assert rows.columns == other.columns, rows.name
        # A Decimal equals its double, so the types are held apart: none may become a float.
        assert _types(rows) == _types(other), rows.name
        if rows.name == 'customer_months':
            continue
        assert Counter(rows.rows) == Counter(other.rows), rows.name
    # customer_months: the baseline holds only October's orders, so C-01's year cannot be
    # derived from tiny; the October row and whether a subscription ran in each month can.
    # The gate holds the whole year on the play.
    months = _months(next(r for r in mine if r.name == 'customer_months'))
    expected = _months(theirs['customer_months'])
    assert [(m['customer_id'], m['month']) for m in months] == [
        (m['customer_id'], m['month']) for m in expected
    ]
    assert [m['subscribed'] for m in months] == [m['subscribed'] for m in expected]
    assert months[-1] == expected[-1]
