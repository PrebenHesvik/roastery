"""Tiny inside its extract: every tiny row is in the table its `lives_in` names (D13).

The comparison is on tiny's columns only (`columns`, never `added`). On the baseline all three
extracts are one folder, so these are identity checks there; they bite on month and full.
"""

from __future__ import annotations

import pytest
from roastery_spec.claims import claim
from roastery_spec.contract import TABLES
from roastery_spec.derivations import C01_YEAR, DATED_LINES, LATEST_STOCK

TINY = [t for t in TABLES if t.lives_in]


def _kind(table) -> str:
    return table.lives_in.split('(')[0]


def _where(table) -> str:
    """The extract a `same(...)` names; a landing table is read in month."""
    return table.lives_in.removeprefix('same(').rstrip(')') if _kind(table) == 'same' else 'month'


def _columns(table) -> str:
    return ', '.join(c.name for c in table.columns)


def _rows(con, query: str) -> list[tuple]:
    return con.execute(query).fetchall()


def _missing(tiny, other, table, query: str | None = None) -> list[tuple]:
    """Tiny rows of the table that the other extract's rows (or its derivation) lack."""
    cols = _columns(table)
    have = set(_rows(other, query or f'SELECT {cols} FROM {table.name}'))
    return [r for r in _rows(tiny, f'SELECT {cols} FROM {table.name}') if r not in have]


SAME = [t for t in TINY if _kind(t) == 'same']
LANDING = [t for t in TINY if _kind(t) == 'landing']
DERIVED = [t for t in TINY if _kind(t) == 'derived']


@pytest.mark.parametrize(
    'table', [t for t in SAME if t.name != 'customer_changes'], ids=lambda t: t.name
)
def test_every_tiny_row_of_a_same_table_is_in_its_extract(request, tiny, table):
    other = request.getfixturevalue(_where(table))
    assert _missing(tiny, other, table) == []


def test_the_tiny_change_log_is_in_full_without_seq_and_in_the_same_order(tiny, full):
    ordered = (
        'SELECT op, customer_id, country, postal_code, changed_at '
        'FROM customer_changes ORDER BY seq'
    )
    mine = _rows(tiny, ordered)
    theirs = _rows(full, ordered)
    assert [r for r in mine if r not in set(theirs)] == []
    kept = set(mine)
    assert [r for r in theirs if r in kept] == mine


@pytest.mark.parametrize('table', LANDING, ids=lambda t: t.name)
def test_every_tiny_row_of_a_landing_table_is_in_its_extract(month, tiny, table):
    assert _missing(tiny, month, table) == []


# Each derivation is stated here as SQL on the tables of the extract named in `lives_in`.
DERIVATIONS = {
    'dated_lines': (
        'month',
        DATED_LINES,
    ),
    'latest_stock': (
        'month',
        LATEST_STOCK,
    ),
    # C-01's months: whether S-1 ran on the first, and, in the month the tiny orders cover,
    # the orders and the line spend (the earlier months' orders are not in tiny's tables)
    'customer_months': (
        'full',
        """SELECT m.customer_id, m.month, m.orders, m.spend_nok, m.subscribed
        FROM customer_months m""",
    ),
}


@pytest.mark.parametrize('table', DERIVED, ids=lambda t: t.name)
def test_every_tiny_row_of_a_derived_table_follows_from_its_extract(request, tiny, table):
    where, query = DERIVATIONS[table.name]
    other = request.getfixturevalue(where)
    if table.name == 'customer_months':
        query = """
        SELECT 'C-01' AS customer_id, m AS month,
            CASE WHEN m = DATE '2026-10-01' THEN (SELECT count(DISTINCT o.order_id) FROM orders o
                WHERE o.customer_id = 'C-01'
                AND date_trunc('month', o.order_date) = m) END AS orders,
            CASE WHEN m = DATE '2026-10-01' THEN (SELECT sum(l.qty * l.unit_price)
                FROM orders o JOIN order_lines l USING (order_id)
                WHERE o.customer_id = 'C-01'
                AND date_trunc('month', o.order_date) = m) END AS spend_nok,
            EXISTS (SELECT 1 FROM subscriptions s WHERE s.customer_id = 'C-01'
                AND s.started <= m AND (s.ended IS NULL OR m < s.ended)) AS subscribed
        FROM (SELECT unnest(generate_series(DATE '2025-11-01', DATE '2026-10-01',
            INTERVAL 1 MONTH))::DATE AS m)"""
        cols = 'customer_id, month, subscribed'
        have = set(_rows(other, f'SELECT customer_id, month, subscribed FROM ({query})'))
        got = _rows(tiny, f'SELECT {cols} FROM customer_months')
        assert [r for r in got if r not in have] == []
        oct_ = "SELECT orders, spend_nok FROM customer_months WHERE month = DATE '2026-10-01'"
        assert _rows(tiny, oct_) == _rows(
            other, f"SELECT orders, spend_nok FROM ({query}) WHERE month = DATE '2026-10-01'"
        )
        return
    assert _missing(tiny, other, table, query) == []


# C-01's year from the orders and lines of full: every month, all five columns. The baseline
# holds only October's orders, so this waits for the simulator's full, which alone writes
# lesson_ids; the October check above runs now.
@claim('full', ['orders', 'order_lines', 'subscriptions', 'lesson_ids'])
def test_customer_months_is_c_01s_year_recomputed_from_full(tiny, full):
    """All twelve months of tiny's customer_months follow from full's orders and lines."""
    cols = 'customer_id, month, orders, spend_nok, subscribed'
    mine = _rows(tiny, f'SELECT {cols} FROM customer_months ORDER BY month')
    assert len(mine) == 12
    assert _rows(full, C01_YEAR) == mine
