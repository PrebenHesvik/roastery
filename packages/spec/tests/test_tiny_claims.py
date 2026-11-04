"""The tiny claims of data-docs' `test_roastery_dataset.py`, ported with names and literals as
they were. They run on the tiny data folder (`--tiny`, `ROASTERY_TINY_DATA`, else the baseline).
The answers are written here, never computed from the data.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

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

CLEAN_LINES = """
SELECT line_id, order_id, upper(trim(product_id)) AS product_id,
    try_cast(qty AS INTEGER) AS qty,
    replace(unit_price, ',', '.')::DECIMAL(7, 2) AS unit_price
FROM raw_lines"""


def both_ways(left: str, right: str) -> str:
    return f'(({left}) EXCEPT ({right})) UNION ALL (({right}) EXCEPT ({left}))'


@pytest.fixture(scope='module')
def con(tiny):
    return tiny


def rows(con, query: str) -> list[tuple]:
    return con.execute(query).fetchall()


# ---- tier 1: the shop ----


def test_no_order_line_is_without_its_order(con):
    assert rows(con, 'SELECT line_id FROM order_lines ANTI JOIN orders USING (order_id)') == []


def test_the_one_line_without_a_product_is_l_09(con):
    q = 'SELECT line_id FROM order_lines ANTI JOIN products USING (product_id)'
    assert rows(con, q) == [('L-09',)]


def test_the_one_order_without_a_customer_is_o_107(con):
    q = 'SELECT order_id FROM orders ANTI JOIN customers USING (customer_id)'
    assert rows(con, q) == [('O-107',)]


def test_the_one_order_without_lines_is_o_106(con):
    q = 'SELECT order_id FROM orders ANTI JOIN order_lines USING (order_id)'
    assert rows(con, q) == [('O-106',)]


def test_the_one_customer_without_orders_is_c_06(con):
    q = 'SELECT customer_id FROM customers ANTI JOIN orders USING (customer_id)'
    assert rows(con, q) == [('C-06',)]


def test_the_one_product_never_sold_is_p_12(con):
    q = 'SELECT product_id FROM products ANTI JOIN order_lines USING (product_id)'
    assert rows(con, q) == [('P-12',)]


def test_l_04_and_l_05_are_the_same_line_twice(con):
    q = """SELECT list(line_id ORDER BY line_id) FROM order_lines
        GROUP BY order_id, product_id, qty, unit_price HAVING count(*) > 1"""
    assert rows(con, q) == [(['L-04', 'L-05'],)]


def test_every_line_has_its_list_price_on_the_day_except_three(con):
    q = """SELECT l.line_id, l.unit_price, p.price
        FROM order_lines l JOIN orders o USING (order_id)
        LEFT JOIN prices p ON p.product_id = l.product_id
            AND o.order_date >= p.valid_from
            AND (p.valid_to IS NULL OR o.order_date < p.valid_to)
        WHERE l.unit_price IS DISTINCT FROM p.price ORDER BY 1"""
    assert rows(con, q) == [
        ('L-06', Decimal('549.00'), None),
        ('L-09', Decimal('199.00'), None),
        ('L-12', Decimal('0.00'), Decimal('349.00')),
    ]


def test_inclusive_period_ends_match_l_03_twice(con):
    q = """SELECT l.line_id, count(*) FROM order_lines l JOIN orders o USING (order_id)
        JOIN prices p ON p.product_id = l.product_id
            AND o.order_date BETWEEN p.valid_from AND coalesce(p.valid_to, DATE '9999-12-31')
        GROUP BY l.line_id HAVING count(*) > 1"""
    assert rows(con, q) == [('L-03', 2)]


def test_a_payment_converted_as_of_its_day_equals_its_order_except_o_103_and_o_105(con):
    q = """
    WITH t AS (SELECT order_id, sum(qty * unit_price) AS nok FROM order_lines GROUP BY order_id),
        p AS (SELECT DISTINCT * FROM payments)
    SELECT p.order_id, round(p.amount * coalesce(f.nok_per_unit, 1), 2), t.nok
    FROM p ASOF LEFT JOIN fx_rates f ON f.currency = p.currency AND p.paid_on >= f.rate_date
    LEFT JOIN t USING (order_id)
    WHERE round(p.amount * coalesce(f.nok_per_unit, 1), 2) IS DISTINCT FROM t.nok ORDER BY 1"""
    assert rows(con, q) == [
        ('O-103', Decimal('387.01'), Decimal('774.00')),
        ('O-105', Decimal('349.00'), None),
    ]


def test_o_108_is_paid_what_its_lines_say(con):
    q = """SELECT (SELECT amount FROM payments WHERE order_id = 'O-108'),
        (SELECT sum(qty * unit_price) FROM order_lines WHERE order_id = 'O-108')"""
    assert rows(con, q) == [(Decimal('129.00'), Decimal('129.00'))]


def test_every_event_names_a_known_order(con):
    assert rows(con, 'SELECT event_id FROM order_events ANTI JOIN orders USING (order_id)') == []


def test_the_placed_day_agrees_with_order_date_in_every_zone_except_for_o_106(con):
    q = """
    SELECT e.order_id FROM order_events e JOIN orders o USING (order_id)
    LEFT JOIN customers c USING (customer_id)
    WHERE e.status = 'placed' AND (
        e.event_at::DATE <> o.order_date
        OR timezone('Europe/Oslo', e.event_at::TIMESTAMPTZ)::DATE <> o.order_date
        OR timezone(CASE c.country WHEN 'FI' THEN 'Europe/Helsinki'
            WHEN 'SE' THEN 'Europe/Stockholm' ELSE 'Europe/Oslo' END,
            e.event_at::TIMESTAMPTZ)::DATE <> o.order_date)
    ORDER BY 1"""
    assert rows(con, q) == [('O-106',)]


def test_e_08_is_late_and_e_10_is_out_of_order(con):
    q = """SELECT event_id FROM order_events e
        WHERE loaded_at - event_at > INTERVAL 1 HOUR
        OR EXISTS (SELECT 1 FROM order_events f WHERE f.order_id = e.order_id
            AND f.event_at < e.event_at AND f.loaded_at > e.loaded_at)
        ORDER BY 1"""
    assert rows(con, q) == [('E-08',), ('E-10',)]


def test_dated_lines_are_the_lines_with_their_order_day(con):
    left = 'SELECT * FROM dated_lines'
    right = """SELECT l.line_id, l.product_id, o.order_date, l.qty, l.unit_price
        FROM order_lines l JOIN orders o USING (order_id)"""
    assert rows(con, 'SELECT count(*) FROM dated_lines') == [(11,)]
    assert rows(con, both_ways(left, right)) == []


def test_two_stock_counts_on_one_day_are_the_resend_of_7_october(con):
    q = """SELECT product_id, stock_date, list(on_hand ORDER BY counted_at) FROM stock_daily
        GROUP BY ALL HAVING count(*) > 1 ORDER BY 1"""
    assert rows(con, q) == [
        ('P-10', date(2026, 10, 7), [26, 36]),
        ('P-20', date(2026, 10, 7), [4, 4]),
    ]


def test_the_latest_count_of_each_day_gives_the_shelf(con):
    q = f"""SELECT product_id, list(on_hand ORDER BY stock_date) FROM {LATEST}
        GROUP BY 1 ORDER BY 1"""
    assert rows(con, q) == [('P-10', [40, 37, 36, 60, 59]), ('P-20', [4, 4, 4, 4, 4])]


def test_latest_stock_is_the_latest_count_of_each_day_of_stock_daily(con):
    left = 'SELECT * FROM latest_stock'
    right = f'SELECT product_id, stock_date, on_hand FROM {LATEST}'
    assert rows(con, 'SELECT count(*) FROM latest_stock') == [(10,)]
    assert rows(con, both_ways(left, right)) == []


def test_latest_stock_holds_the_recount_of_7_october_for_p_10(con):
    q = """SELECT on_hand FROM latest_stock
        WHERE product_id = 'P-10' AND stock_date = DATE '2026-10-07'"""
    assert rows(con, q) == [(36,)]


def test_p_10_falls_by_3_where_the_lines_say_6_and_by_1_on_9_october(con):
    q = f"""SELECT s.stock_date, s.on_hand - lag(s.on_hand) OVER (ORDER BY s.stock_date),
            (SELECT sum(qty) FROM dated_lines d
             WHERE d.product_id = 'P-10' AND d.order_date = s.stock_date)
        FROM {LATEST} s WHERE product_id = 'P-10' ORDER BY 1"""
    assert rows(con, q) == [
        (date(2026, 10, 5), None, 2),
        (date(2026, 10, 6), -3, 6),
        (date(2026, 10, 7), -1, 1),
        (date(2026, 10, 8), 24, None),
        (date(2026, 10, 9), -1, 1),
    ]


def test_read_raw_the_resend_makes_p_10_fall_by_11_and_rise_by_10(con):
    q = """SELECT on_hand - lag(on_hand) OVER (ORDER BY stock_date, counted_at) FROM stock_daily
        WHERE product_id = 'P-10' AND stock_date IN (DATE '2026-10-06', DATE '2026-10-07')
        ORDER BY stock_date, counted_at"""
    assert rows(con, q) == [(None,), (-11,), (10,)]


EXTRACT = 'SELECT customer_id, country, postal_code FROM customer_extracts'


@pytest.mark.parametrize(
    'cut, night',
    [('2026-10-10 00:00', '2026-10-09'), ('2026-10-09 00:00', '2026-10-08')],
)
def test_the_change_log_folded_before_a_cut_equals_that_nights_extract(con, cut, night):
    folded = FOLD.format(cut=cut)
    extract = f"{EXTRACT} WHERE extract_date = DATE '{night}'"
    assert rows(con, both_ways(folded, extract)) == []


def test_the_whole_change_log_folded_equals_customers(con):
    folded = FOLD.format(cut='9999-01-01')
    shop = 'SELECT customer_id, country, postal_code FROM customers'
    assert rows(con, both_ways(folded, shop)) == []


def test_the_extracts_differ_in_one_changed_one_new_and_one_gone_customer(con):
    q = """WITH a AS (SELECT * FROM customer_extracts WHERE extract_date = DATE '2026-10-08'),
        b AS (SELECT * FROM customer_extracts WHERE extract_date = DATE '2026-10-09')
    SELECT coalesce(a.customer_id, b.customer_id),
        CASE WHEN a.customer_id IS NULL THEN 'new' WHEN b.customer_id IS NULL THEN 'gone'
             WHEN a.postal_code IS DISTINCT FROM b.postal_code
               OR a.country IS DISTINCT FROM b.country THEN 'changed' END AS what
    FROM a FULL JOIN b USING (customer_id) WHERE what IS NOT NULL ORDER BY 1"""
    assert rows(con, q) == [('C-01', 'changed'), ('C-06', 'new'), ('C-07', 'gone')]


def test_the_last_extract_equals_customers_in_the_columns_they_share(con):
    extract = f"{EXTRACT} WHERE extract_date = DATE '2026-10-09'"
    shop = 'SELECT customer_id, country, postal_code FROM customers'
    assert rows(con, both_ways(extract, shop)) == []


def test_the_change_log_holds_one_delete_seven_inserts_and_two_updates(con):
    q = 'SELECT op, count(*) FROM customer_changes GROUP BY 1 ORDER BY 1'
    assert rows(con, q) == [('delete', 1), ('insert', 7), ('update', 2)]


def test_c_01_was_changed_twice_on_9_october_a_typo_and_then_the_fix(con):
    q = """SELECT postal_code, strftime(changed_at, '%H:%M') FROM customer_changes
        WHERE customer_id = 'C-01' AND op = 'update' ORDER BY seq"""
    assert rows(con, q) == [('0510', '18:02'), ('0150', '18:05')]


def test_the_delete_is_a_tombstone_of_c_07_with_only_its_key(con):
    q = """SELECT customer_id, changed_at::DATE, country, postal_code FROM customer_changes
        WHERE op = 'delete'"""
    assert rows(con, q) == [('C-07', date(2026, 10, 9), None, None)]


def test_a_known_customer_is_inserted_on_the_day_it_joined(con):
    q = """SELECT count(*) FILTER (WHERE x.changed_at::DATE = c.joined), count(*)
        FROM customer_changes x JOIN customers c USING (customer_id) WHERE x.op = 'insert'"""
    assert rows(con, q) == [(6, 6)]


def test_c_07_was_inserted_on_or_before_the_day_s_7_started(con):
    q = """SELECT x.changed_at::DATE <= s.started FROM customer_changes x
        JOIN subscriptions s USING (customer_id) WHERE x.op = 'insert' AND customer_id = 'C-07'"""
    assert rows(con, q) == [(True,)]


def test_seq_follows_changed_at(con):
    q = """SELECT count(*) FROM (SELECT seq, row_number() OVER (ORDER BY changed_at) AS r
        FROM customer_changes) WHERE seq <> r"""
    assert rows(con, q) == [(0,)]


def test_a_watermark_at_9_october_sees_c_01_and_c_06_and_misses_the_deleted_c_07(con):
    q = """SELECT customer_id, max(changed_at) FROM customer_changes WHERE op <> 'delete'
        GROUP BY 1 HAVING max(changed_at) >= TIMESTAMP '2026-10-09' ORDER BY 1"""
    assert rows(con, q) == [
        ('C-01', datetime(2026, 10, 9, 18, 5)),
        ('C-06', datetime(2026, 10, 9, 10, 14)),
    ]


def test_line_stamps_without_the_deleted_row_equal_order_lines(con):
    left = 'SELECT line_id, order_id, qty FROM line_stamps WHERE NOT is_deleted'
    right = 'SELECT line_id, order_id, qty FROM order_lines'
    assert rows(con, both_ways(left, right)) == []
    assert rows(con, 'SELECT count(*) FROM line_stamps WHERE NOT is_deleted') == [(11,)]


def test_the_one_deleted_line_is_l_10_of_o_106_stamped_when_the_order_was_cancelled(con):
    q = """SELECT l.line_id, l.order_id, l.qty, l.updated_at = e.event_at FROM line_stamps l
        JOIN order_events e ON e.order_id = l.order_id AND e.status = 'cancelled'
        WHERE l.is_deleted"""
    assert rows(con, q) == [('L-10', 'O-106', 1, True)]


def test_a_line_is_stamped_when_its_order_was_placed(con):
    q = """SELECT l.line_id FROM line_stamps l JOIN order_events e
        ON e.order_id = l.order_id AND e.status = 'placed'
        WHERE NOT l.is_deleted AND l.updated_at <> e.event_at"""
    assert rows(con, q) == []


def test_a_line_is_stamped_on_the_day_of_its_order(con):
    q = """SELECT l.line_id FROM line_stamps l JOIN orders o USING (order_id)
        WHERE NOT l.is_deleted AND l.updated_at::DATE <> o.order_date"""
    assert rows(con, q) == []


def test_c_01_ordered_twice_before_her_move_at_18_05_on_9_october_and_once_after(con):
    q = """SELECT o.order_id,
        CASE WHEN e.event_at >= TIMESTAMP '2026-10-09 18:05' THEN 'after' ELSE 'before' END
        FROM orders o LEFT JOIN order_events e ON e.order_id = o.order_id AND e.status = 'placed'
        WHERE o.customer_id = 'C-01' ORDER BY 1"""
    assert rows(con, q) == [('O-101', 'before'), ('O-104', 'before'), ('O-108', 'after')]


# ---- tier 2: the files, the web and the rest ----


def test_the_tab_and_the_no_break_space_are_in_the_customer_ids_of_the_export(con):
    q = """SELECT name, instr(customer_id, chr(9)) > 0, instr(customer_id, chr(160)) > 0
        FROM raw_customers
        WHERE instr(customer_id, chr(9)) > 0 OR instr(customer_id, chr(160)) > 0
        ORDER BY 1"""
    assert rows(con, q) == [('Aino', False, True), ('Mikkel', True, False)]


def test_duckdb_trim_takes_off_the_no_break_space_but_leaves_the_tab(con):
    q = "SELECT name, length(trim(customer_id)) FROM raw_customers WHERE name IN ('Aino', 'Mikkel')"
    assert sorted(rows(con, q)) == [('Aino', 4), ('Mikkel', 5)]


def test_the_space_class_of_a_regex_leaves_the_no_break_space_but_takes_off_the_tab(con):
    q = r"""SELECT name, length(regexp_replace(customer_id, '\s', '', 'g')) FROM raw_customers
        WHERE name IN ('Aino', 'Mikkel') ORDER BY 1"""
    assert rows(con, q) == [('Aino', 5), ('Mikkel', 4)]


def test_raw_customers_cleaned_equal_their_tier_1_rows(con):
    shop = "SELECT * FROM customers WHERE customer_id <= 'C-05'"
    assert rows(con, both_ways(CLEAN_CUSTOMERS, shop)) == []


def test_raw_lines_cleaned_equal_their_tier_1_rows(con):
    shop = 'SELECT * FROM order_lines WHERE line_id IN (SELECT line_id FROM raw_lines)'
    assert rows(con, both_ways(CLEAN_LINES, shop)) == []


def test_a_plain_cast_of_the_raw_lines_gives_nulls_where_the_text_has_commas_or_words(con):
    q = """SELECT line_id, try_cast(unit_price AS DECIMAL(7, 2)), try_cast(qty AS INTEGER)
        FROM raw_lines ORDER BY 1"""
    assert rows(con, q) == [
        ('L-01', None, 2),
        ('L-02', Decimal('899.00'), 1),
        ('L-03', Decimal('349.00'), 1),
        ('L-06', None, 1),
        ('L-07', Decimal('349.00'), None),
    ]


def test_every_checkout_is_followed_by_a_placed_order_within_two_minutes(con):
    q = """SELECT w.event_id, EXISTS (SELECT 1 FROM orders o JOIN order_events e
            ON e.order_id = o.order_id AND e.status = 'placed'
            WHERE o.customer_id = w.customer_id
            AND e.event_at BETWEEN w.event_at AND w.event_at + INTERVAL 2 MINUTE)
        FROM web_events w WHERE w.event = 'checkout'"""
    got = rows(con, q)
    assert len(got) == 3
    assert [r[1] for r in got] == [True, True, True]


def test_a_30_minute_gap_gives_v_2_two_sessions(con):
    q = """SELECT visitor_id, max(session_no) + 1 FROM (
        SELECT visitor_id, sum(CASE WHEN gap > INTERVAL 30 MINUTE THEN 1 ELSE 0 END)
            OVER (PARTITION BY visitor_id ORDER BY event_at ROWS UNBOUNDED PRECEDING) AS session_no
        FROM (SELECT *, event_at - lag(event_at) OVER (PARTITION BY visitor_id ORDER BY event_at)
            AS gap FROM web_events)) GROUP BY 1 ORDER BY 1"""
    assert rows(con, q) == [('V-1', 1), ('V-2', 2), ('V-3', 1), ('V-4', 1)]


def test_the_funnel_is_4_views_4_carts_and_3_checkouts(con):
    q = 'SELECT event, count(DISTINCT visitor_id) FROM web_events GROUP BY 1 ORDER BY 2 DESC, 1'
    assert rows(con, q) == [('cart', 4), ('view', 4), ('checkout', 3)]


def test_a_subscription_starts_after_its_customer_joined(con):
    q = """SELECT s.subscription_id FROM subscriptions s JOIN customers c USING (customer_id)
        WHERE s.started < c.joined"""
    assert rows(con, q) == []


def test_s_5_and_s_6_overlap(con):
    q = """SELECT a.subscription_id, b.subscription_id FROM subscriptions a
        JOIN subscriptions b ON a.customer_id = b.customer_id
            AND a.subscription_id < b.subscription_id
            AND a.started < coalesce(b.ended, DATE '9999-12-31')
            AND b.started < coalesce(a.ended, DATE '9999-12-31')"""
    assert rows(con, q) == [('S-5', 'S-6')]


def test_five_subscriptions_are_active_on_1_october_2025_and_four_on_1_october_2026(con):
    q = """SELECT d, count(*) FROM (VALUES (DATE '2025-10-01'), (DATE '2026-10-01')) t(d)
        JOIN subscriptions s ON s.started <= d AND (s.ended IS NULL OR d < s.ended)
        GROUP BY d ORDER BY d"""
    assert rows(con, q) == [(date(2025, 10, 1), 5), (date(2026, 10, 1), 4)]


def test_the_category_paths_of_the_products_are_two_and_three_deep(con):
    q = """WITH RECURSIVE r AS (
        SELECT category_id, 1 AS depth FROM categories WHERE parent_id IS NULL
        UNION ALL SELECT c.category_id, r.depth + 1 FROM categories c
        JOIN r ON c.parent_id = r.category_id)
        SELECT p.product_id, r.depth FROM products p JOIN r USING (category_id) ORDER BY 1"""
    assert rows(con, q) == [('P-10', 2), ('P-11', 2), ('P-12', 2), ('P-20', 3), ('P-21', 2)]


def test_the_campaigns_add_up_to_more_than_all_sales(con):
    q = """SELECT k.campaign_name, sum(l.qty * l.unit_price) FROM order_lines l
        JOIN campaign_products k USING (product_id) GROUP BY 1
        UNION ALL SELECT 'all lines', sum(qty * unit_price) FROM order_lines ORDER BY 1"""
    assert rows(con, q) == [
        ('Autumn espresso', Decimal('1248.00')),
        ('Brew at home', Decimal('2738.00')),
        ('all lines', Decimal('3286.00')),
    ]


def test_both_campaigns_lie_outside_the_teaching_week(con):
    q = """SELECT campaign_id FROM campaigns
        WHERE first_day <= DATE '2026-10-09' AND last_day >= DATE '2026-10-05'"""
    assert rows(con, q) == []


def test_customer_months_are_12_months_of_one_customer_subscribed_throughout(con):
    q = """SELECT count(*), min(month), max(month), bool_and(subscribed),
        count(DISTINCT customer_id) FROM customer_months"""
    assert rows(con, q) == [(12, date(2025, 11, 1), date(2026, 10, 1), True, 1)]


def test_october_2026_of_customer_months_equals_tier_1_for_c_01(con):
    q = """SELECT m.orders, m.spend_nok, t.orders, t.spend FROM customer_months m,
        (SELECT count(DISTINCT o.order_id) AS orders, sum(l.qty * l.unit_price) AS spend
         FROM orders o JOIN order_lines l USING (order_id) WHERE o.customer_id = 'C-01') t
        WHERE m.month = DATE '2026-10-01'"""
    assert rows(con, q) == [(3, Decimal('1835.00'), 3, Decimal('1835.00'))]


def test_subscribed_agrees_with_s_1_being_active_on_the_first_of_the_month(con):
    q = """SELECT count(*) FROM customer_months m WHERE m.subscribed <> EXISTS (
        SELECT 1 FROM subscriptions s WHERE s.customer_id = m.customer_id
        AND s.started <= m.month AND (s.ended IS NULL OR m.month < s.ended))"""
    assert rows(con, q) == [(0,)]


def test_the_bands_change_in_every_month_to_month_step_through_seven_pairs(con):
    q = """SELECT count(*) FILTER (WHERE ob <> lag_ob OR sb <> lag_sb), count(DISTINCT (ob, sb))
        FROM (SELECT *, lag(ob) OVER (ORDER BY month) AS lag_ob,
            lag(sb) OVER (ORDER BY month) AS lag_sb
        FROM (SELECT month,
            CASE WHEN orders = 0 THEN '0' WHEN orders = 1 THEN '1' WHEN orders <= 3 THEN '2-3'
                 ELSE '4+' END AS ob,
            CASE WHEN spend_nok < 300 THEN 'under 300' WHEN spend_nok < 1000 THEN '300-999'
                 ELSE '1000+' END AS sb FROM customer_months))"""
    assert rows(con, q) == [(11, 7)]


def test_the_detail_tables_hold_the_products_of_their_kind(con):
    q = """SELECT kind, list(product_id ORDER BY product_id) FROM (
        SELECT product_id, 'beans' AS d FROM bean_details
        UNION ALL SELECT product_id, 'equipment' FROM equipment_details) x
        JOIN products USING (product_id) WHERE kind = d GROUP BY 1 ORDER BY 1"""
    assert rows(con, q) == [('beans', ['P-10', 'P-11', 'P-12']), ('equipment', ['P-20', 'P-21'])]


def test_kinds_holds_two_rows_and_every_product_kind_is_in_it(con):
    q = """SELECT (SELECT count(*) FROM kinds),
        (SELECT count(*) FROM products ANTI JOIN kinds USING (kind))"""
    assert rows(con, q) == [(2, 0)]


def test_categories_sort_by_the_shops_order_and_by_neither_name_nor_id(con):
    q = """SELECT list(category_id ORDER BY sort_order), count(DISTINCT sort_order),
        list(category_id ORDER BY sort_order) <> list(category_id ORDER BY category_name),
        list(category_id ORDER BY sort_order) <> list(category_id ORDER BY category_id)
        FROM categories"""
    assert rows(con, q) == [
        (['CAT-1', 'CAT-11', 'CAT-12', 'CAT-2', 'CAT-23', 'CAT-21', 'CAT-22'], 7, True, True)
    ]


def test_a_parent_category_sorts_before_its_children(con):
    q = """SELECT count(*) FROM categories c JOIN categories p ON c.parent_id = p.category_id
        WHERE c.sort_order < p.sort_order"""
    assert rows(con, q) == [(0,)]


def test_managers_are_four_and_their_countries_are_the_customers_countries(con):
    q = """SELECT count(*), (SELECT list(DISTINCT country ORDER BY country) FROM customers
        WHERE country IS NOT NULL) = list(country ORDER BY country) FROM managers"""
    assert rows(con, q) == [(4, True)]


def test_a_computed_bridge_puts_p_20_in_both_campaigns_at_half_weight(con):
    q = """WITH g AS (SELECT product_id, list(campaign_id ORDER BY campaign_id) AS grp,
            1 / count(*) AS w FROM campaign_products GROUP BY 1)
        SELECT b.campaign_id, g.grp, g.w FROM campaign_products b JOIN g USING (product_id)
        WHERE product_id = 'P-20' ORDER BY 1"""
    assert rows(con, q) == [('K-1', ['K-1', 'K-2'], 0.5), ('K-2', ['K-1', 'K-2'], 0.5)]


def test_weighted_campaign_sales_equal_all_sales_of_campaign_products(con):
    q = """WITH w AS (SELECT product_id, 1 / count(*) OVER (PARTITION BY product_id) AS w
            FROM campaign_products)
        SELECT round(sum(l.qty * l.unit_price * w.w), 2),
            (SELECT sum(qty * unit_price) FROM order_lines
             WHERE product_id IN (SELECT product_id FROM campaign_products))
        FROM order_lines l JOIN w USING (product_id)"""
    assert rows(con, q) == [(3087.0, Decimal('3087.00'))]


def test_campaign_products_names_agree_with_campaigns(con):
    q = """SELECT count(*) FROM campaign_products b JOIN campaigns k USING (campaign_id)
        WHERE b.campaign_name <> k.campaign_name"""
    assert rows(con, q) == [(0,)]


# ---- the till ----
# Revise with the till's tables: the owner may change them.

TILL_MEMBERS = r"""SELECT m.member_no, r.customer_id FROM till_members m LEFT JOIN
    (SELECT upper(trim(regexp_replace(customer_id, '[\s\x{00A0}]', '', 'g'))) AS customer_id,
        lower(trim(email)) AS email FROM raw_customers) r
    ON lower(trim(m.email)) = r.email"""


def test_the_till_sells_the_same_kettle_as_o_104_at_the_same_moment(con):
    q = """SELECT t.receipt_id, o.order_id FROM till_lines t
        JOIN till_receipts h USING (receipt_id)
        JOIN product_codes p USING (ean)
        JOIN order_lines l ON l.product_id = p.product_id AND l.unit_price * l.qty = t.amount
        JOIN orders o USING (order_id)
        JOIN order_events e ON e.order_id = o.order_id AND e.status = 'placed'
            AND timezone('UTC', timezone('Europe/Oslo', h.sold_at)) = e.event_at"""
    assert rows(con, q) == [('R-5001', 'O-104')]


def test_one_till_line_reaches_no_product_through_the_codes(con):
    q = """SELECT t.receipt_id, t.line_no, t.ean FROM till_lines t
        LEFT JOIN product_codes p USING (ean) LEFT JOIN products r USING (product_id)
        WHERE r.product_id IS NULL"""
    assert rows(con, q) == [('R-5003', 1, '2000000000992')]


def test_every_ean_of_the_till_is_in_product_codes(con):
    assert rows(con, 'SELECT ean FROM till_lines ANTI JOIN product_codes USING (ean)') == []


def test_p_11_has_two_codes_and_one_code_has_no_product(con):
    q = """SELECT product_id, count(*) FROM product_codes GROUP BY 1 HAVING count(*) <> 1
        ORDER BY 1 NULLS LAST"""
    assert rows(con, q) == [('P-11', 2)]
    assert rows(con, 'SELECT ean FROM product_codes WHERE product_id IS NULL') == [
        ('2000000000992',)
    ]


def test_every_receipt_numbers_its_lines_from_1(con):
    assert rows(con, 'SELECT receipt_id FROM till_lines GROUP BY 1 HAVING min(line_no) <> 1') == []


def test_a_loose_line_costs_its_grams_at_the_list_price_per_weight(con):
    q = """SELECT t.receipt_id, t.line_no, t.grams, t.amount,
            t.amount = round(t.grams * pr.price / r.weight_g, 2)
        FROM till_lines t JOIN till_receipts h USING (receipt_id)
        JOIN product_codes p USING (ean) JOIN products r USING (product_id)
        JOIN prices pr ON pr.product_id = r.product_id AND h.sold_at::DATE >= pr.valid_from
            AND (pr.valid_to IS NULL OR h.sold_at::DATE < pr.valid_to)
        WHERE t.grams IS NOT NULL ORDER BY 1, 2"""
    assert rows(con, q) == [
        ('R-5002', 1, 250, Decimal('87.25'), True),
        ('R-5003', 2, 100, Decimal('34.90'), True),
        ('R-5004', 1, 500, Decimal('174.50'), True),
    ]


def test_a_piece_is_sold_at_the_list_price_of_the_day_except_in_r_5001(con):
    q = """SELECT t.receipt_id, t.line_no, pr.price FROM till_lines t
        JOIN till_receipts h USING (receipt_id)
        JOIN product_codes p USING (ean) JOIN products r USING (product_id)
        LEFT JOIN prices pr ON pr.product_id = r.product_id AND h.sold_at::DATE >= pr.valid_from
            AND (pr.valid_to IS NULL OR h.sold_at::DATE < pr.valid_to)
        WHERE t.grams IS NULL AND pr.price IS DISTINCT FROM t.amount"""
    assert rows(con, q) == [('R-5001', 1, None)]


def test_the_till_sells_no_piece_of_p_10_or_p_20(con):
    q = """SELECT count(*) FROM till_lines t JOIN product_codes p USING (ean)
        WHERE p.product_id IN ('P-10', 'P-20') AND t.grams IS NULL"""
    assert rows(con, q) == [(0,)]


def test_the_till_has_one_receipt_on_each_of_6_7_8_and_9_october(con):
    q = """SELECT sold_at::DATE, count(*) FROM till_receipts GROUP BY 1 ORDER BY 1"""
    assert rows(con, q) == [
        (date(2026, 10, 6), 1),
        (date(2026, 10, 7), 1),
        (date(2026, 10, 8), 1),
        (date(2026, 10, 9), 1),
    ]


def test_members_match_the_export_on_a_lowered_trimmed_email_except_three(con):
    assert rows(con, TILL_MEMBERS + ' ORDER BY 1') == [
        (1001, 'C-01'),
        (1002, 'C-03'),
        (1003, 'C-03'),
        (1004, None),
        (1005, None),
        (1006, None),
    ]


def test_mikkels_two_member_numbers_are_one_customer(con):
    q = f"""SELECT customer_id, list(member_no ORDER BY member_no) FROM ({TILL_MEMBERS})
        WHERE customer_id IS NOT NULL GROUP BY 1 HAVING count(*) > 1"""
    assert rows(con, q) == [('C-03', [1002, 1003])]


def test_ingrid_is_in_the_till_with_a_capitalised_email_and_an_old_postal_code(con):
    q = """SELECT m.email, m.postal_code, c.postal_code FROM till_members m
        JOIN customers c ON c.name = m.name WHERE m.member_no = 1001"""
    assert rows(con, q) == [('Ingrid@Example.invalid', '7010', '0150')]


def test_member_1005_has_the_postal_code_c_07_had_in_the_8_october_extract(con):
    q = """SELECT m.member_no, e.customer_id FROM till_members m JOIN customer_extracts e
        ON e.postal_code = m.postal_code AND e.extract_date = DATE '2026-10-08'
        WHERE e.customer_id NOT IN (SELECT customer_id FROM customers)"""
    assert rows(con, q) == [(1005, 'C-07')]


def test_sindre_is_a_member_with_no_web_account(con):
    q = """SELECT member_no, name FROM till_members
        WHERE name NOT IN (SELECT name FROM customers)
        AND listed_on = DATE '2026-10-07' AND member_no <> 1005"""
    assert rows(con, q) == [(1004, 'Sindre')]


def test_hilde_is_listed_after_the_last_sale_day(con):
    q = """SELECT member_no, listed_on FROM till_members
        WHERE listed_on > (SELECT max(sold_at)::DATE FROM till_receipts)"""
    assert rows(con, q) == [(1006, date(2026, 10, 10))]


def test_every_receipt_has_lines_and_every_line_has_its_receipt(con):
    assert (
        rows(con, 'SELECT receipt_id FROM till_receipts ANTI JOIN till_lines USING (receipt_id)')
        == []
    )
    assert (
        rows(con, 'SELECT receipt_id FROM till_lines ANTI JOIN till_receipts USING (receipt_id)')
        == []
    )


def test_the_receipts_name_no_member_during_the_trial_then_three_members(con):
    q = 'SELECT receipt_id, member_no FROM till_receipts ORDER BY 1'
    assert rows(con, q) == [
        ('R-5001', None),
        ('R-5002', 1003),
        ('R-5003', 1004),
        ('R-5004', 1006),
    ]


def test_the_inferred_member_is_named_by_r_5004_before_any_list_holds_1006(con):
    q = """SELECT h.receipt_id, h.member_no FROM till_receipts h
        WHERE h.member_no IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM till_members m
            WHERE m.member_no = h.member_no AND m.listed_on <= h.sold_at::DATE)"""
    assert rows(con, q) == [('R-5004', 1006)]


def test_r_5002_reaches_mikkel_only_through_the_member_map(con):
    q = f"""SELECT h.receipt_id, m.customer_id FROM till_receipts h
        JOIN ({TILL_MEMBERS}) m USING (member_no) ORDER BY 1"""
    assert rows(con, q) == [('R-5002', 'C-03'), ('R-5003', None), ('R-5004', None)]


def test_every_email_of_the_dataset_ends_in_example_invalid(con):
    q = """SELECT count(*) FROM (SELECT email FROM till_members
        UNION ALL SELECT manager FROM managers
        UNION ALL SELECT email FROM raw_customers WHERE email IS NOT NULL)
        WHERE NOT lower(trim(email)) LIKE '%@example.invalid'"""
    assert rows(con, q) == [(0,)]
