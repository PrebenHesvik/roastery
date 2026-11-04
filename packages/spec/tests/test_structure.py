"""The shape of the data folders: tables, row counts, keys and order independence.

Counts and keys are claims about the data; the tables a folder must hold come from the contract.
"""

from __future__ import annotations

import json

import pytest
from roastery_spec.contract import TABLES, by_name

ROWS = {
    'customers': 6,
    'products': 5,
    'orders': 8,
    'order_lines': 11,
    'dated_lines': 11,
    'prices': 6,
    'fx_rates': 8,
    'payments': 7,
    'order_events': 14,
    'stock_daily': 12,
    'latest_stock': 10,
    'customer_extracts': 12,
    'customer_changes': 10,
    'line_stamps': 12,
    'raw_customers': 5,
    'raw_lines': 5,
    'web_events': 12,
    'subscriptions': 7,
    'categories': 7,
    'kinds': 2,
    'campaign_products': 5,
    'campaigns': 2,
    'product_codes': 6,
    'till_receipts': 4,
    'till_lines': 6,
    'till_members': 6,
    'customer_months': 12,
    'bean_details': 3,
    'equipment_details': 2,
    'managers': 4,
}

COUNTS = {
    'daily_sales': 1947,
    'order_values': 600,
    'budget': 54,
    'checkout_test': 4000,
    'subscribers': 240,
    'visits': 3600,
    'deliveries': 480,
    'shop_days': 730,
}

# The SQL below is copied from test_tiny_claims.py: the two files are read apart.
# the latest count of a product on a day wins: a recount is sent again with a later counted_at
LATEST = """(SELECT * FROM stock_daily QUALIFY row_number() OVER
    (PARTITION BY product_id, stock_date ORDER BY counted_at DESC) = 1)"""

# the log folded to the state before a cut: the newest change of each customer, deletes dropped
FOLD = """SELECT customer_id, country, postal_code FROM customer_changes
    WHERE changed_at < TIMESTAMP '{cut}'
    QUALIFY row_number() OVER (PARTITION BY customer_id ORDER BY seq DESC) = 1
    AND op <> 'delete'"""

# the shop's csv export, cleaned: ids stripped of every space kind, dates read in both forms
CLEAN_CUSTOMERS = r"""
SELECT upper(trim(regexp_replace(customer_id, '[\s\x{00A0}]', '', 'g'))) AS customer_id,
    name,
    nullif(upper(trim(country)), '') AS country,
    CASE WHEN upper(trim(country)) = 'NO' THEN lpad(postal_code, 4, '0')
         ELSE nullif(postal_code, '') END AS postal_code,
    coalesce(try_strptime(joined, '%d.%m.%Y'), try_strptime(joined, '%Y-%m-%d'))::DATE AS joined
FROM raw_customers"""


def rows(con, query: str) -> list[tuple]:
    return con.execute(query).fetchall()


ORDERED = {
    'sales by product': """SELECT product_id, sum(qty * unit_price) FROM order_lines
        GROUP BY 1 ORDER BY 1""",
    'latest count': f'SELECT product_id, stock_date, on_hand FROM {LATEST} ORDER BY 1, 2',
    'change by lag': f"""SELECT stock_date, on_hand - lag(on_hand) OVER (ORDER BY stock_date)
        FROM {LATEST} WHERE product_id = 'P-10' ORDER BY 1""",
    'folded log': FOLD.format(cut='9999-01-01') + ' ORDER BY 1',
    'sessions': """SELECT visitor_id, event_id, event_at FROM web_events
        ORDER BY visitor_id, event_at""",
    'categories': 'SELECT category_id FROM categories ORDER BY sort_order',
    'cleaned export': CLEAN_CUSTOMERS + ' ORDER BY 1',
}


@pytest.mark.parametrize('extract', ['tiny', 'month', 'full'])
def test_a_manifest_lists_the_contract_tables_of_its_extract(folders, extract):
    manifest = json.loads((folders[extract] / 'manifest.json').read_text(encoding='utf-8'))
    listed = set(manifest['tables'])
    assert listed <= set(by_name())
    # the baseline serves all three extracts at once; a real extract holds its own tables
    here = {
        t.name
        for t in TABLES
        if t.since == 'baseline' and (manifest['extract'] == 'baseline' or extract in t.extracts)
    }
    assert {n for n in listed if by_name()[n].since == 'baseline'} == here


def test_every_table_holds_its_rows(tiny):
    got = {n: rows(tiny, f'SELECT count(*) FROM {n}')[0][0] for n in ROWS}
    assert got == ROWS


def test_every_tier_3_table_holds_its_rows(full):
    got = {n: rows(full, f'SELECT count(*) FROM {n}')[0][0] for n in COUNTS}
    assert got == COUNTS


def test_only_payments_and_raw_customers_have_no_key():
    keyless = sorted(t.name for t in TABLES if not t.key)
    assert keyless == ['payments', 'raw_customers']


@pytest.mark.parametrize(
    'table', [t for t in TABLES if t.key and t.since == 'baseline'], ids=lambda t: t.name
)
def test_a_declared_key_is_made_of_columns_and_is_unique(request, table):
    con = request.getfixturevalue('tiny' if 'tiny' in table.extracts else 'full')
    columns = {r[0] for r in rows(con, f'DESCRIBE {table.name}')}
    assert set(table.key) <= columns
    key = ', '.join(table.key)
    assert rows(con, f'SELECT {key} FROM {table.name} GROUP BY ALL HAVING count(*) > 1') == []


@pytest.mark.parametrize('name', list(ORDERED))
def test_a_query_that_orders_its_result_answers_the_same_on_reversed_tables(
    tiny, tiny_reversed, name
):
    assert rows(tiny_reversed, ORDERED[name]) == rows(tiny, ORDERED[name])
