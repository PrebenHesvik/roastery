"""The claims of the tables roastery-data 1.0 adds (6.1 section 5), and the definition claims.

No data folder holds these tables yet, so every claim here is deselected and listed under
"awaiting data"; they run first in step 6.5, on the simulator's `full`. A definition claim
recomputes a tier 3 table from the world's tables, cell for cell (D15).

The teaching week is 5 to 9 October 2026 (plan section 4.2). The cast is C-01 to C-07.
"""

from __future__ import annotations

from roastery_spec.claims import claim

CAST = ('C-01', 'C-02', 'C-03', 'C-04', 'C-05', 'C-06', 'C-07')
CAST_SQL = ', '.join(f"'{c}'" for c in CAST)
WEEK = "DATE '2026-10-05'"
COUNTED_ON = "DATE '2026-09-30'"


def rows(con, sql: str) -> list[tuple]:
    return con.execute(sql).fetchall()


def one(con, sql: str):
    return con.execute(sql).fetchone()[0]


def same_rows(con, left: str, right: str) -> tuple[list[tuple], list[tuple]]:
    """The rows only `left` has and the rows only `right` has, duplicates counted."""
    only_left = rows(con, f'({left}) EXCEPT ALL ({right}) ORDER BY ALL LIMIT 10')
    only_right = rows(con, f'({right}) EXCEPT ALL ({left}) ORDER BY ALL LIMIT 10')
    return only_left, only_right


# subscription_events


@claim('full', ['subscription_events'])
def test_subscription_events_types_are_skip_pause_resume_cancel(full):
    found = {r[0] for r in rows(full, 'SELECT DISTINCT event_type FROM subscription_events')}
    assert found <= {'skip', 'pause', 'resume', 'cancel'}
    assert found


@claim('full', ['subscription_events'])
def test_subscription_events_reason_is_never_null(full):
    assert one(full, 'SELECT count(*) FROM subscription_events WHERE reason IS NULL') == 0


@claim('full', ['subscription_events', 'subscriptions'])
def test_subscription_events_belong_to_a_subscription(full):
    sql = """
        SELECT count(*) FROM subscription_events e
        WHERE e.subscription_id NOT IN (SELECT subscription_id FROM subscriptions)
    """
    assert one(full, sql) == 0


@claim('full', ['subscription_events', 'subscribers', 'lesson_ids'])
def test_subscription_events_cancel_on_every_ended_subscribers_day(full):
    """Every ended subscribers row has one cancel, on its `ended` day (through lesson_ids)."""
    sql = """
        SELECT s.subscription_id, count(e.event_id) AS cancels
        FROM subscribers s
        LEFT JOIN lesson_ids l ON l.lesson_set = 'subscribers' AND l.row_no = s.subscription_id
        LEFT JOIN subscription_events e ON e.subscription_id = l.shop_id
            AND e.event_type = 'cancel' AND e.event_at::DATE = s.ended
        WHERE s.ended IS NOT NULL
        GROUP BY s.subscription_id
        HAVING count(e.event_id) <> 1
        ORDER BY s.subscription_id
    """
    assert rows(full, sql) == []
    assert one(full, 'SELECT count(*) FROM subscribers WHERE ended IS NOT NULL') > 0


# subscription_shipments


@claim('full', ['subscription_shipments'])
def test_subscription_shipments_at_most_one_per_subscription_and_month(full):
    sql = """
        SELECT subscription_id, date_trunc('month', shipped_on) AS m, count(*)
        FROM subscription_shipments
        GROUP BY ALL HAVING count(*) > 1
    """
    assert rows(full, sql) == []


@claim('full', ['subscription_shipments'])
def test_subscription_shipments_qty_above_zero(full):
    assert one(full, 'SELECT count(*) FROM subscription_shipments WHERE qty <= 0') == 0


@claim('full', ['subscription_shipments', 'subscriptions'])
def test_subscription_shipments_only_while_the_subscription_runs(full):
    """A bag ships on or after `started` and before `ended` (the half-open period)."""
    sql = """
        SELECT b.shipment_id FROM subscription_shipments b
        LEFT JOIN subscriptions s ON s.subscription_id = b.subscription_id
        WHERE s.subscription_id IS NULL
           OR b.shipped_on < s.started
           OR (s.ended IS NOT NULL AND b.shipped_on >= s.ended)
           OR b.product_id <> s.product_id
        ORDER BY b.shipment_id LIMIT 10
    """
    assert rows(full, sql) == []


@claim('full', ['subscription_shipments', 'subscription_events'])
def test_subscription_shipments_none_in_a_skipped_or_paused_month(full):
    """No bag in the month a skip is dated in, nor while a pause holds.

    A pause holds from its event until the subscription's next resume. A skip is dated in the
    month whose bag it skips.
    """
    skipped = """
        SELECT b.shipment_id FROM subscription_shipments b
        JOIN subscription_events e ON e.subscription_id = b.subscription_id
            AND e.event_type = 'skip'
            AND date_trunc('month', e.event_at) = date_trunc('month', b.shipped_on)
    """
    paused = """
        SELECT b.shipment_id FROM subscription_shipments b
        JOIN subscription_events p ON p.subscription_id = b.subscription_id
            AND p.event_type = 'pause' AND p.event_at::DATE <= b.shipped_on
        WHERE NOT EXISTS (
            SELECT 1 FROM subscription_events r
            WHERE r.subscription_id = p.subscription_id AND r.event_type = 'resume'
              AND r.event_at > p.event_at AND r.event_at::DATE <= b.shipped_on
        )
    """
    assert rows(full, skipped) == []
    assert rows(full, paused) == []


@claim('full', ['subscription_shipments'])
def test_subscription_shipments_october_bags_of_p10_p20_ship_before_5_october(full):
    """The October 2026 bags are out before the teaching week's opening stock (4.2)."""
    sql = f"""
        SELECT shipment_id FROM subscription_shipments
        WHERE product_id IN ('P-10', 'P-20')
          AND date_trunc('month', shipped_on) = DATE '2026-10-01'
          AND shipped_on >= {WEEK}
    """
    assert rows(full, sql) == []


# stock_movements

BALANCE = """
    SELECT product_id, sum(qty) FROM stock_movements
    WHERE product_id IN ('P-10', 'P-20') AND {where}
    GROUP BY product_id ORDER BY product_id
"""


@claim('full', ['stock_movements'])
def test_stock_movements_reasons_are_the_five(full):
    found = {r[0] for r in rows(full, 'SELECT DISTINCT reason FROM stock_movements')}
    assert found <= {'roasted', 'sold', 'shipped', 'written_off', 'counted'}
    assert found


@claim('full', ['stock_movements'])
def test_stock_movements_open_the_week_with_42_and_5(full):
    """Before 5 October, after the October subscription bags: P-10 = 42, P-20 = 5 (4.2)."""
    found = rows(full, BALANCE.format(where=f'moved_at < {WEEK}'))
    assert found == [('P-10', 42), ('P-20', 5)]


@claim('full', ['stock_movements', 'stock_daily'])
def test_stock_movements_balance_at_close_is_latest_stock(full):
    """Each close of 5 to 9 October: the sum of movements is that day's latest count.

    latest_stock is tiny's; on full it is stock_daily's latest count per product and day (tiny's
    `latest_stock`: 40, 37, 36, 60, 59 and 4 a day). A movement counts towards the day its
    `moved_at` falls on, as the counts' days do.
    """
    sql = f"""
        WITH latest AS (
            SELECT product_id, stock_date, on_hand FROM stock_daily
            WHERE product_id IN ('P-10', 'P-20')
              AND stock_date BETWEEN {WEEK} AND DATE '2026-10-09'
            QUALIFY row_number() OVER (
                PARTITION BY product_id, stock_date ORDER BY counted_at DESC) = 1
        )
        SELECT l.product_id, l.stock_date, l.on_hand, sum(m.qty) AS balance
        FROM latest l
        LEFT JOIN stock_movements m ON m.product_id = l.product_id
            AND m.moved_at::DATE <= l.stock_date
        GROUP BY ALL
        ORDER BY l.product_id, l.stock_date
    """
    found = rows(full, sql)
    assert len(found) == 10
    assert [(p, d, on_hand) for p, d, on_hand, _ in found] == [
        (p, d, balance) for p, d, _, balance in found
    ]


@claim('full', ['stock_movements'])
def test_stock_movements_balance_is_never_negative(full):
    sql = """
        WITH running AS (
            SELECT product_id, moved_at,
                sum(qty) OVER (PARTITION BY product_id ORDER BY moved_at
                    RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS balance
            FROM stock_movements
        )
        SELECT product_id, min(balance) FROM running
        GROUP BY product_id HAVING min(balance) < 0
    """
    assert rows(full, sql) == []


# green_purchases


@claim('full', ['green_purchases'])
def test_green_purchases_kg_above_zero(full):
    sql = 'SELECT count(*) FROM green_purchases WHERE kg <= 0 OR nok_per_kg <= 0'
    assert one(full, sql) == 0
    assert one(full, 'SELECT count(*) FROM green_purchases') > 0


@claim('full', ['green_purchases', 'stock_movements', 'products'])
def test_green_purchases_kilos_bought_at_least_kilos_roasted(full):
    """Green kilos bought cover the roasted bags' weight (roasting only loses weight)."""
    bought = one(full, 'SELECT sum(kg) FROM green_purchases')
    roasted = one(
        full,
        """
        SELECT sum(m.qty * p.weight_g) / 1000 FROM stock_movements m
        JOIN products p USING (product_id)
        WHERE m.reason = 'roasted'
        """,
    )
    assert roasted and roasted > 0
    assert bought >= roasted


# product_costs


@claim('full', ['product_costs'])
def test_product_costs_periods_are_half_open_and_never_overlap(full):
    ordered = """
        SELECT count(*) FROM product_costs WHERE valid_to IS NOT NULL AND valid_to <= valid_from
    """
    overlap = """
        SELECT a.product_id, a.valid_from, b.valid_from FROM product_costs a
        JOIN product_costs b ON a.product_id = b.product_id AND a.valid_from < b.valid_from
        WHERE a.valid_to IS NULL OR a.valid_to > b.valid_from
    """
    assert one(full, ordered) == 0
    assert rows(full, overlap) == []


@claim('full', ['product_costs', 'prices'])
def test_product_costs_below_list_price_in_every_prices_period(full):
    """Where a cost period and a price period meet, the cost is below the price."""
    sql = """
        SELECT c.product_id, c.valid_from, p.valid_from FROM product_costs c
        JOIN prices p ON p.product_id = c.product_id
            AND (c.valid_to IS NULL OR p.valid_from < c.valid_to)
            AND (p.valid_to IS NULL OR c.valid_from < p.valid_to)
        WHERE c.green_nok + c.packaging_nok + c.roasting_nok >= p.price
    """
    assert rows(full, sql) == []
    priced = (
        'SELECT count(*) FROM prices WHERE product_id IN (SELECT product_id FROM product_costs)'
    )
    assert one(full, priced) > 0


# shipments


@claim('full', ['shipments'])
def test_shipments_delivered_on_or_after_shipped(full):
    sql = """
        SELECT count(*) FROM shipments
        WHERE delivered_on < shipped_on OR promised_by < shipped_on
    """
    assert one(full, sql) == 0


@claim('full', ['shipments', 'orders'])
def test_shipments_belong_to_web_orders(full):
    sql = """
        SELECT s.shipment_id FROM shipments s
        LEFT JOIN orders o USING (order_id)
        WHERE o.order_id IS NULL OR o.channel <> 'web'
        LIMIT 10
    """
    assert rows(full, sql) == []


@claim('full', ['shipments', 'lesson_ids'])
def test_shipments_order_297_takes_21_days(full):
    sql = """
        SELECT s.delivered_on - s.shipped_on FROM shipments s
        JOIN lesson_ids l ON l.lesson_set = 'order_values' AND l.shop_id = s.order_id
        WHERE l.row_no = 297
    """
    assert rows(full, sql) == [(21,)]


@claim('full', ['deliveries', 'order_values', 'lesson_ids', 'shipments', 'orders', 'customers'])
def test_deliveries_is_derived_from_shipments(full):
    """deliveries = the web orders of order_values, their parcel's days and country (S8, S9)."""
    world = """
        SELECT v.order_no, c.country, s.shipped_on, (s.delivered_on - s.shipped_on)::INTEGER
        FROM order_values v
        JOIN lesson_ids l ON l.lesson_set = 'order_values' AND l.row_no = v.order_no
        JOIN orders o ON o.order_id = l.shop_id
        JOIN customers c ON c.customer_id = o.customer_id
        JOIN shipments s ON s.order_id = o.order_id
        WHERE v.channel = 'web'
    """
    table = 'SELECT order_no, country, shipped_on, days FROM deliveries'
    assert same_rows(full, table, world) == ([], [])


# pricing_rules


@claim('full', ['pricing_rules'])
def test_pricing_rules_kinds_are_subscriber_and_campaign(full):
    found = {r[0] for r in rows(full, 'SELECT DISTINCT rule_kind FROM pricing_rules')}
    assert found == {'subscriber', 'campaign'}


@claim('full', ['pricing_rules', 'campaigns'])
def test_pricing_rules_one_rule_per_campaign_on_its_days(full):
    """Each campaign's discount is one campaign rule, half-open: valid_to is the day after."""
    sql = """
        SELECT k.campaign_id, count(r.rule_id) FROM campaigns k
        LEFT JOIN pricing_rules r ON r.rule_kind = 'campaign'
            AND r.percent = k.discount_pct
            AND r.valid_from = k.first_day AND r.valid_to = k.last_day + 1
        GROUP BY k.campaign_id HAVING count(r.rule_id) <> 1
    """
    assert rows(full, sql) == []
    count = "SELECT count(*) FROM pricing_rules WHERE rule_kind = 'campaign'"
    assert one(full, count) == one(full, 'SELECT count(*) FROM campaigns')


@claim('full', ['pricing_rules'])
def test_pricing_rules_at_most_one_subscriber_rule_on_any_day(full):
    sql = """
        SELECT a.rule_id, b.rule_id FROM pricing_rules a
        JOIN pricing_rules b ON a.rule_id < b.rule_id
            AND a.rule_kind = 'subscriber' AND b.rule_kind = 'subscriber'
            AND (a.valid_to IS NULL OR b.valid_from < a.valid_to)
            AND (b.valid_to IS NULL OR a.valid_from < b.valid_to)
    """
    assert rows(full, sql) == []


# customers.kind


@claim('full', ['customers.kind'])
def test_customers_kind_is_consumer_or_business(full):
    found = {r[0] for r in rows(full, 'SELECT DISTINCT kind FROM customers')}
    assert found == {'consumer', 'business'}


@claim(
    'full',
    ['customers.kind', 'order_values', 'lesson_ids', 'orders', 'order_lines', 'products'],
)
def test_customers_kind_large_order_values_orders_are_business(full):
    """The 10-bag orders and the café's 48 (order 600) are business (D7); bags are beans."""
    sql = """
        SELECT v.order_no, sum(li.qty) AS bags, any_value(c.kind) AS kind
        FROM order_values v
        JOIN lesson_ids l ON l.lesson_set = 'order_values' AND l.row_no = v.order_no
        JOIN orders o ON o.order_id = l.shop_id
        JOIN customers c ON c.customer_id = o.customer_id
        JOIN order_lines li ON li.order_id = o.order_id
        JOIN products p ON p.product_id = li.product_id AND p.kind = 'beans'
        GROUP BY v.order_no
        HAVING sum(li.qty) >= 10
        ORDER BY v.order_no
    """
    found = rows(full, sql)
    assert (600, 48, 'business') in found
    assert any(bags == 10 for _, bags, _ in found)
    assert [r for r in found if r[2] != 'business'] == []


# weather_days, door_counts, till_day_totals


@claim('full', ['weather_days'])
def test_weather_days_rain_never_negative(full):
    sql = 'SELECT count(*) FROM weather_days WHERE rain_mm < 0 OR rain_mm IS NULL'
    assert one(full, sql) == 0


@claim('full', ['door_counts'])
def test_door_counts_none_on_sundays(full):
    """The shop is closed on Sundays: the door counter counts nobody."""
    sql = 'SELECT count(*) FROM door_counts WHERE isodow(shop_date) = 7 AND walk_ins <> 0'
    assert one(full, sql) == 0


@claim('full', ['till_day_totals'])
def test_till_day_totals_none_on_sundays(full):
    sql = 'SELECT count(*) FROM till_day_totals WHERE isodow(shop_date) = 7 AND receipts <> 0'
    assert one(full, sql) == 0


@claim('full', ['shop_days', 'weather_days', 'door_counts', 'till_day_totals'])
def test_shop_days_is_the_join_of_the_three_series(full):
    """shop_days is the weather, the door counter and the old till side by side (D12)."""
    world = """
        SELECT w.shop_date, w.rain_mm, d.walk_ins, t.receipts
        FROM weather_days w
        JOIN door_counts d USING (shop_date)
        JOIN till_day_totals t USING (shop_date)
        WHERE w.shop_date BETWEEN DATE '2024-10-01' AND DATE '2026-09-30'
    """
    table = 'SELECT shop_date, rain_mm, walk_ins, receipts FROM shop_days'
    assert same_rows(full, table, world) == ([], [])


# lesson_ids


@claim('full', ['lesson_ids'])
def test_lesson_ids_sets_are_order_values_and_subscribers(full):
    found = {r[0] for r in rows(full, 'SELECT DISTINCT lesson_set FROM lesson_ids')}
    assert found == {'order_values', 'subscribers'}


@claim('full', ['lesson_ids', 'order_values', 'orders'])
def test_lesson_ids_every_order_values_row_has_one_order(full):
    sql = """
        SELECT v.order_no, count(l.shop_id) FROM order_values v
        LEFT JOIN lesson_ids l ON l.lesson_set = 'order_values' AND l.row_no = v.order_no
        GROUP BY v.order_no HAVING count(l.shop_id) <> 1
    """
    unknown = """
        SELECT l.row_no FROM lesson_ids l
        WHERE l.lesson_set = 'order_values'
          AND (l.shop_id NOT IN (SELECT order_id FROM orders)
               OR l.row_no NOT IN (SELECT order_no FROM order_values))
    """
    shared = """
        SELECT shop_id FROM lesson_ids WHERE lesson_set = 'order_values'
        GROUP BY shop_id HAVING count(*) > 1
    """
    assert rows(full, sql) == []
    assert rows(full, unknown) == []
    assert rows(full, shared) == []


@claim('full', ['lesson_ids', 'subscribers', 'subscriptions'])
def test_lesson_ids_every_subscribers_row_has_one_subscription(full):
    sql = """
        SELECT s.subscription_id, count(l.shop_id) FROM subscribers s
        LEFT JOIN lesson_ids l ON l.lesson_set = 'subscribers' AND l.row_no = s.subscription_id
        GROUP BY s.subscription_id HAVING count(l.shop_id) <> 1
    """
    unknown = """
        SELECT l.row_no FROM lesson_ids l
        WHERE l.lesson_set = 'subscribers'
          AND (l.shop_id NOT IN (SELECT subscription_id FROM subscriptions)
               OR l.row_no NOT IN (SELECT subscription_id FROM subscribers))
    """
    shared = """
        SELECT shop_id FROM lesson_ids WHERE lesson_set = 'subscribers'
        GROUP BY shop_id HAVING count(*) > 1
    """
    assert rows(full, sql) == []
    assert rows(full, unknown) == []
    assert rows(full, shared) == []


@claim('full', ['lesson_ids', 'order_values', 'orders'])
def test_lesson_ids_order_values_match_their_orders(full):
    """A lesson order has its shop order's day and channel."""
    sql = """
        SELECT v.order_no FROM order_values v
        JOIN lesson_ids l ON l.lesson_set = 'order_values' AND l.row_no = v.order_no
        JOIN orders o ON o.order_id = l.shop_id
        WHERE o.order_date <> v.order_date OR o.channel <> v.channel
        ORDER BY v.order_no LIMIT 10
    """
    assert rows(full, sql) == []


# Finland's drop (S11): no table names it; the claim finds it in the orders.


@claim('full', ['orders', 'customers.kind'])
def test_orders_finland_drops_below_half_in_one_week(full):
    """A week of Finland's consumer orders below half the mean of the four weeks around it.

    Consumer orders only: a business account's bulk order would blur a weekly count (D7).
    The weeks are ISO weeks; the four around a week are the two before and the two after.
    """
    sql = """
        WITH weeks AS (
            SELECT date_trunc('week', o.order_date) AS week, count(*) AS n
            FROM orders o JOIN customers c USING (customer_id)
            WHERE c.country = 'FI' AND c.kind = 'consumer'
            GROUP BY ALL
        ),
        span AS (
            SELECT range::DATE AS week FROM range(
                (SELECT min(week) FROM weeks), (SELECT max(week) FROM weeks) + INTERVAL 1 WEEK,
                INTERVAL 1 WEEK)
        ),
        filled AS (
            SELECT s.week, coalesce(w.n, 0) AS n FROM span s LEFT JOIN weeks w USING (week)
        ),
        around AS (
            SELECT week, n,
                (lag(n, 2) OVER w + lag(n, 1) OVER w + lead(n, 1) OVER w + lead(n, 2) OVER w)
                    / 4 AS mean
            FROM filled WINDOW w AS (ORDER BY week)
        )
        SELECT week, n, mean FROM around WHERE mean > 0 AND n < mean / 2 ORDER BY week
    """
    assert rows(full, sql) != []
    named = """
        SELECT count(*) FROM duckdb_tables()
        WHERE table_name LIKE '%drop%' OR table_name LIKE '%scripted%'
    """
    assert one(full, named) == 0


# Definition claims: a tier 3 table recomputed from the world (6.1 section 5, D15).


@claim('full', ['daily_sales', 'orders', 'order_lines', 'customers.kind', 'prices'])
def test_daily_sales_equals_the_web_consumer_lines_at_list_price(full):
    """Per day and product with a price: the web consumer lines' bags, at list price (D7, D15).

    Every day and product with a list price has a row, a day with no line at qty 0.
    """
    world = """
        WITH days AS (
            SELECT range::DATE AS sale_date
            FROM range(DATE '2024-10-01', DATE '2026-10-01', INTERVAL 1 DAY)
        ),
        priced AS (
            SELECT d.sale_date, p.product_id, p.price FROM days d
            JOIN prices p ON d.sale_date >= p.valid_from
                AND (p.valid_to IS NULL OR d.sale_date < p.valid_to)
        ),
        sold AS (
            SELECT o.order_date AS sale_date, li.product_id, sum(li.qty) AS qty
            FROM orders o
            JOIN customers c USING (customer_id)
            JOIN order_lines li USING (order_id)
            WHERE o.channel = 'web' AND c.kind = 'consumer'
            GROUP BY ALL
        )
        SELECT p.sale_date, p.product_id, coalesce(s.qty, 0)::INTEGER,
            (coalesce(s.qty, 0) * p.price)::DECIMAL(7, 2)
        FROM priced p LEFT JOIN sold s USING (sale_date, product_id)
    """
    unpriced = """
        SELECT o.order_date, li.product_id FROM orders o
        JOIN customers c USING (customer_id)
        JOIN order_lines li USING (order_id)
        WHERE o.channel = 'web' AND c.kind = 'consumer'
          AND o.order_date BETWEEN DATE '2024-10-01' AND DATE '2026-09-30'
          AND NOT EXISTS (
            SELECT 1 FROM prices p WHERE p.product_id = li.product_id
              AND o.order_date >= p.valid_from
              AND (p.valid_to IS NULL OR o.order_date < p.valid_to))
        LIMIT 10
    """
    table = 'SELECT sale_date, product_id, qty, amount FROM daily_sales'
    assert same_rows(full, table, world) == ([], [])
    assert rows(full, unpriced) == []


@claim('full', ['subscribers', 'subscriptions', 'lesson_ids'])
def test_subscribers_are_the_subscriptions_outside_the_cast(full):
    """subscribers = everyone's subscriptions but the cast's, as they stood on 30 September 2026.

    An end after that day was not known then, so it is null (D8).
    """
    world = f"""
        SELECT s.subscription_id, s.product_id, s.started,
            CASE WHEN s.ended <= {COUNTED_ON} THEN s.ended END
        FROM subscriptions s
        WHERE s.customer_id NOT IN ({CAST_SQL}) AND s.started <= {COUNTED_ON}
    """
    table = """
        SELECT l.shop_id, s.product_id, s.started, s.ended FROM subscribers s
        JOIN lesson_ids l ON l.lesson_set = 'subscribers' AND l.row_no = s.subscription_id
    """
    assert one(full, 'SELECT count(*) FROM subscribers') == 240
    assert same_rows(full, table, world) == ([], [])
