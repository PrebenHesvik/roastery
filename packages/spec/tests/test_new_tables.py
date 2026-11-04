"""The claims of the tables roastery-data 1.0 adds (6.1 section 5), and the definition claims.

No data folder holds these tables yet, so a claim that needs one is deselected and listed
under "awaiting data"; they run first in step 6.5, on the simulator's `full`. A definition claim
recomputes a tier 3 table from the world's tables, cell for cell (D15).

The claims on the teaching week inside the volume (plan 4.2) and on the erased customers (S15)
need only baseline tables: they run now, where they hold trivially, and bite on month and full.
The export writer's faults, the defect log and `scripted_events` (S11) are tested in 6.4's
simulator tests, not here.

The teaching week is 5 to 9 October 2026 (plan section 4.2). The cast is C-01 to C-07.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from roastery_spec.claims import claim

CAST = ('C-01', 'C-02', 'C-03', 'C-04', 'C-05', 'C-06', 'C-07')
CAST_SQL = ', '.join(f"'{c}'" for c in CAST)
WEEK = "DATE '2026-10-05'"
COUNTED_ON = "DATE '2026-09-30'"
WEEK_END = "DATE '2026-10-09'"
WINDOW = "DATE '2024-10-01' AND DATE '2026-09-30'"
LESSON_ORDER = "JOIN lesson_ids l ON l.lesson_set = 'order_values' AND l.row_no = v.order_no"


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


@claim('full', ['stock_movements'])
def test_stock_movements_count_nothing_for_p10_p20_from_5_to_9_october(full):
    """No `counted` movement for P-10 or P-20 in the teaching week (S19).

    Each day's on_hand is the closing balance of the movements; the 26 sent on 7 October is the
    export writer's fault, and no count moved the stock to 36.
    """
    sql = f"""
        SELECT movement_id FROM stock_movements
        WHERE reason = 'counted' AND product_id IN ('P-10', 'P-20')
          AND moved_at::DATE BETWEEN {WEEK} AND {WEEK_END}
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
    nulls = """
        SELECT product_id, valid_from FROM product_costs
        WHERE green_nok IS NULL OR packaging_nok IS NULL OR roasting_nok IS NULL
    """
    assert rows(full, nulls) == []
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


# customers.account_kind (D7, S17)


@claim('full', ['customers.account_kind'])
def test_customers_account_kind_is_consumer_or_business(full):
    found = {r[0] for r in rows(full, 'SELECT DISTINCT account_kind FROM customers')}
    assert found == {'consumer', 'business'}


@claim(
    'full',
    [
        'customers.account_kind',
        'order_values',
        'lesson_ids',
        'orders',
        'order_lines',
        'products',
    ],
)
def test_customers_account_kind_large_order_values_orders_are_business(full):
    """The 10-bag orders and the café's 48 (order 600) are business (D7); bags are beans."""
    sql = """
        SELECT v.order_no, sum(li.qty) AS bags, any_value(c.account_kind) AS kind
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


# order_values: the amount, the status (S13) and order 300 (S14), through lesson_ids


@claim('full', ['order_values', 'lesson_ids', 'order_lines'])
def test_order_values_amount_is_the_sum_of_the_orders_lines(full):
    sql = f"""
        SELECT v.order_no, v.amount, sum(li.qty * li.unit_price) FROM order_values v
        {LESSON_ORDER}
        LEFT JOIN order_lines li ON li.order_id = l.shop_id
        GROUP BY v.order_no, v.amount
        HAVING sum(li.qty * li.unit_price) IS DISTINCT FROM v.amount
        ORDER BY v.order_no LIMIT 10
    """
    assert rows(full, sql) == []
    assert one(full, f'SELECT count(*) FROM order_values v {LESSON_ORDER}') == 600


@claim('full', ['order_values', 'lesson_ids', 'payments', 'order_events'])
def test_order_values_status_follows_from_payments_and_invoices(full):
    """refund: a negative payment; paid: a payment by 30 September 2026; unpaid: an invoice
    still open that day, an `invoiced` event and no payment by then (S13, S14).

    Payments are in the customer's currency, so only their sign and day are read, never their
    amount against `amount`; a redelivered message changes nothing (EXISTS, not a sum).
    """
    sql = f"""
        WITH derived AS (
            SELECT v.order_no, v.status, CASE
                WHEN EXISTS (SELECT 1 FROM payments p
                    WHERE p.order_id = l.shop_id AND p.amount < 0) THEN 'refund'
                WHEN EXISTS (SELECT 1 FROM payments p
                    WHERE p.order_id = l.shop_id AND p.paid_on <= {COUNTED_ON}) THEN 'paid'
                WHEN EXISTS (SELECT 1 FROM order_events e
                    WHERE e.order_id = l.shop_id AND e.status = 'invoiced'
                      AND e.event_at::DATE <= {COUNTED_ON}) THEN 'unpaid'
            END AS found
            FROM order_values v {LESSON_ORDER}
        )
        SELECT order_no, status, found FROM derived
        WHERE found IS DISTINCT FROM status ORDER BY order_no LIMIT 10
    """
    assert rows(full, sql) == []
    assert one(full, f'SELECT count(*) FROM order_values v {LESSON_ORDER}') == 600


@claim('full', ['customers.account_kind', 'orders', 'order_events'])
def test_orders_of_a_business_account_go_on_invoice(full):
    """A business account always pays by invoice: each order is invoiced once, never paid (S13).

    Before the teaching week, where the export writer drops no event; an order cancelled
    before it was invoiced is left out.
    """
    sql = f"""
        SELECT o.order_id FROM orders o
        JOIN customers c USING (customer_id)
        LEFT JOIN order_events e USING (order_id)
        WHERE c.account_kind = 'business' AND o.order_date < {WEEK}
          AND NOT EXISTS (SELECT 1 FROM order_events x
              WHERE x.order_id = o.order_id AND x.status = 'cancelled')
        GROUP BY o.order_id
        HAVING count(*) FILTER (WHERE e.status = 'invoiced') <> 1
            OR count(*) FILTER (WHERE e.status = 'paid') > 0
        ORDER BY o.order_id LIMIT 10
    """
    business = f"""
        SELECT count(*) FROM orders JOIN customers USING (customer_id)
        WHERE account_kind = 'business' AND order_date < {WEEK}
    """
    assert rows(full, sql) == []
    assert one(full, business) > 0


@claim('full', ['order_values', 'lesson_ids', 'orders', 'order_lines', 'payments'])
def test_order_values_300_is_a_return_at_the_counter(full):
    """Order 300's refund is a credit order: at the counter, one negative line for the product
    returned and a negative payment, after a sale of that product to the same customer (the
    original sale it is linked to) (S14).
    """
    order = one(
        full, "SELECT shop_id FROM lesson_ids WHERE lesson_set = 'order_values' AND row_no = 300"
    )
    held = f"SELECT channel, order_date FROM orders WHERE order_id = '{order}'"
    assert rows(full, held) == [('shop', date(2026, 5, 18))]
    lines = rows(
        full, f"SELECT product_id, qty, unit_price FROM order_lines WHERE order_id = '{order}'"
    )
    assert len(lines) == 1
    product, qty, price = lines[0]
    assert qty < 0
    assert qty * price == Decimal('-899.00')
    paid = f"SELECT DISTINCT currency, amount FROM payments WHERE order_id = '{order}'"
    assert rows(full, paid) == [('NOK', Decimal('-899.00'))]
    original = f"""
        SELECT count(*) FROM orders o
        JOIN order_lines li USING (order_id)
        WHERE o.customer_id = (SELECT customer_id FROM orders WHERE order_id = '{order}')
          AND o.order_id <> '{order}' AND o.order_date <= DATE '2026-05-18'
          AND li.product_id = '{product}' AND li.qty > 0
    """
    assert one(full, original) > 0


# Finland's drop (S11): no table names it; the claim finds it in the orders.


@claim('full', ['orders', 'customers.account_kind'])
def test_orders_finland_drops_below_half_in_one_week(full):
    """A week of Finland's consumer orders below half the mean of the four weeks around it.

    Consumer orders only: a business account's bulk order would blur a weekly count (D7).
    The weeks are ISO weeks; the four around a week are the two before and the two after.
    Their mean is at least 10 orders, so a sparse week of none cannot pass for the drop.
    """
    sql = """
        WITH weeks AS (
            SELECT date_trunc('week', o.order_date) AS week, count(*) AS n
            FROM orders o JOIN customers c USING (customer_id)
            WHERE c.country = 'FI' AND c.account_kind = 'consumer'
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
        SELECT week, n, mean FROM around WHERE mean >= 10 AND n < mean / 2 ORDER BY week
    """
    assert rows(full, sql) != []
    named = """
        SELECT count(*) FROM duckdb_tables()
        WHERE table_name LIKE '%drop%' OR table_name LIKE '%scripted%'
    """
    assert one(full, named) == 0


# Definition claims: a tier 3 table recomputed from the world (6.1 section 5, D15).


@claim('full', ['daily_sales', 'orders', 'order_lines', 'customers.account_kind', 'prices'])
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
            WHERE o.channel = 'web' AND c.account_kind = 'consumer'
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
        WHERE o.channel = 'web' AND c.account_kind = 'consumer'
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


# The teaching week inside the volume (plan 4.2), on month and on full: from 5 to 9 October
# no customer outside the cast buys P-10 or P-20, the till sells neither, and the till rings
# only R-5001, on 6 October, before it goes live on 7 October.

OUTSIDE_CAST_BUYS = f"""
    SELECT li.line_id FROM order_lines li JOIN orders o USING (order_id)
    WHERE (o.customer_id IS NULL OR o.customer_id NOT IN ({CAST_SQL}))
      AND li.product_id IN ('P-10', 'P-20')
      AND o.order_date BETWEEN {WEEK} AND {WEEK_END}
    ORDER BY 1 LIMIT 10
"""

TILL_SELLS = f"""
    SELECT t.receipt_id, t.line_no FROM till_lines t
    JOIN till_receipts h USING (receipt_id)
    JOIN product_codes p USING (ean)
    WHERE p.product_id IN ('P-10', 'P-20')
      AND h.sold_at::DATE BETWEEN {WEEK} AND {WEEK_END}
    ORDER BY ALL
"""

TILL_BEFORE_LIVE = """
    SELECT receipt_id, sold_at::DATE FROM till_receipts
    WHERE sold_at < TIMESTAMP '2026-10-07 00:00' ORDER BY ALL
"""
R_5001 = [('R-5001', date(2026, 10, 6))]


@claim('month', ['orders', 'order_lines'])
def test_week_no_customer_outside_the_cast_buys_p10_or_p20_in_month(month):
    assert rows(month, OUTSIDE_CAST_BUYS) == []


@claim('full', ['orders', 'order_lines'])
def test_week_no_customer_outside_the_cast_buys_p10_or_p20_in_full(full):
    assert rows(full, OUTSIDE_CAST_BUYS) == []


@claim('month', ['till_lines', 'till_receipts', 'product_codes'])
def test_week_the_till_sells_no_p10_or_p20_in_month(month):
    assert rows(month, TILL_SELLS) == []


@claim('full', ['till_lines', 'till_receipts', 'product_codes'])
def test_week_the_till_sells_no_p10_or_p20_in_full(full):
    assert rows(full, TILL_SELLS) == []


@claim('month', ['till_receipts'])
def test_week_the_till_rings_only_r_5001_before_7_october_in_month(month):
    assert rows(month, TILL_BEFORE_LIVE) == R_5001


@claim('full', ['till_receipts'])
def test_week_the_till_rings_only_r_5001_before_7_october_in_full(full):
    assert rows(full, TILL_BEFORE_LIVE) == R_5001


# The erased customers (S15)


@claim('full', ['orders', 'customers', 'customer_changes'])
def test_customers_none_with_an_order_in_the_volume_window_is_erased(full):
    """Only C-07 is erased, on 9 October 2026; every order of the volume window keeps its
    customer, so a join to the end-of-week customers loses none (S15).
    """
    erased = "SELECT customer_id, changed_at::DATE FROM customer_changes WHERE op = 'delete'"
    assert rows(full, erased) == [('C-07', date(2026, 10, 9))]
    orphans = f"""
        SELECT o.order_id FROM orders o
        LEFT JOIN customers c USING (customer_id)
        WHERE o.order_date BETWEEN {WINDOW} AND c.customer_id IS NULL
        ORDER BY 1 LIMIT 10
    """
    assert rows(full, orphans) == []


# web_visits (S18): the visits of web_events, and the two tier 3 tables derived from them


@claim('full', ['web_visits', 'web_events.visit_id'])
def test_web_visits_hold_their_events_by_the_30_minute_rule(full):
    """Every event names a visit of its visitor; a visit starts after more than 30 minutes
    without an event (the rule of `sql/lag-and-lead`) and is dated by its first event.
    """
    orphans = """
        SELECT e.event_id FROM web_events e LEFT JOIN web_visits v USING (visit_id)
        WHERE v.visit_id IS NULL OR v.visitor_id <> e.visitor_id
        ORDER BY 1 LIMIT 10
    """
    empty = """
        SELECT v.visit_id FROM web_visits v
        WHERE NOT EXISTS (SELECT 1 FROM web_events e WHERE e.visit_id = v.visit_id)
        ORDER BY 1 LIMIT 10
    """
    gaps = """
        WITH ordered AS (
            SELECT event_id, visit_id, event_at,
                lag(event_at) OVER w AS before_at, lag(visit_id) OVER w AS before_visit
            FROM web_events WINDOW w AS (PARTITION BY visitor_id ORDER BY event_at, event_id)
        )
        SELECT event_id FROM ordered
        WHERE before_at IS NOT NULL
          AND (event_at - before_at > INTERVAL 30 MINUTE) <> (visit_id <> before_visit)
        ORDER BY 1 LIMIT 10
    """
    dated = """
        SELECT v.visit_id FROM web_visits v
        JOIN (SELECT visit_id, min(event_at)::DATE AS first_day FROM web_events GROUP BY 1)
            USING (visit_id)
        WHERE first_day <> v.visit_date
        ORDER BY 1 LIMIT 10
    """
    kinds = """
        SELECT count(*) FROM web_visits
        WHERE referrer NOT IN ('newsletter', 'ads') OR variant NOT IN ('A', 'B')
    """
    assert rows(full, orphans) == []
    assert rows(full, empty) == []
    assert rows(full, gaps) == []
    assert rows(full, dated) == []
    assert one(full, kinds) == 0


@claim('full', ['visits', 'web_visits', 'web_events.visit_id', 'orders', 'order_events'])
def test_visits_are_the_web_visits_with_a_referrer(full):
    """visits = the web_visits of the window with a referrer, called source there (S18).

    reached is the visit's furthest step: 1 a view, 2 a cart, 3 a checkout, and 4 when the
    visit's customer placed an order within two minutes of the visit's checkout (the `placed`
    event of order_events, as web_events' definition has it).
    """
    world = f"""
        WITH steps AS (
            SELECT visit_id, max(CASE event WHEN 'view' THEN 1 WHEN 'cart' THEN 2
                WHEN 'checkout' THEN 3 END) AS step
            FROM web_events GROUP BY visit_id
        ),
        ordered AS (
            SELECT DISTINCT e.visit_id FROM web_events e
            JOIN orders o ON o.customer_id = e.customer_id
            JOIN order_events p ON p.order_id = o.order_id AND p.status = 'placed'
            WHERE e.event = 'checkout'
              AND p.event_at BETWEEN e.event_at AND e.event_at + INTERVAL 2 MINUTE
        )
        SELECT v.visit_id, v.visit_date, v.country, v.referrer,
            (CASE WHEN d.visit_id IS NOT NULL THEN 4 ELSE s.step END)::INTEGER
        FROM web_visits v
        JOIN steps s USING (visit_id)
        LEFT JOIN ordered d USING (visit_id)
        WHERE v.referrer IS NOT NULL AND v.visit_date BETWEEN {WINDOW}
    """
    table = 'SELECT visit_id, visit_date, country, source, reached FROM visits'
    assert same_rows(full, table, world) == ([], [])


@claim('full', ['checkout_test', 'web_visits', 'web_events.visit_id'])
def test_checkout_test_is_the_product_page_visitors_with_a_variant(full):
    """checkout_test = one row per visitor with a variant visit, over the 40 test days (S18).

    test_day counts from the test's first day to the visitor's first test visit; variant is the
    visitor's one variant; converted is a checkout in one of their test visits. checkout_test's
    visitor_no is a row number with no map, so the rows are compared without it.
    """
    test = """
        SELECT v.visit_id, v.visitor_id, v.visit_date, v.variant,
            EXISTS (SELECT 1 FROM web_events e
                WHERE e.visit_id = v.visit_id AND e.event = 'checkout') AS checked_out,
            EXISTS (SELECT 1 FROM web_events e
                WHERE e.visit_id = v.visit_id AND e.event = 'view') AS viewed
        FROM web_visits v WHERE v.variant IS NOT NULL
    """
    span = f'SELECT max(visit_date) - min(visit_date) + 1 FROM ({test})'
    unviewed = f'SELECT count(*) FROM ({test}) WHERE NOT viewed'
    two = f'SELECT visitor_id FROM ({test}) GROUP BY 1 HAVING count(DISTINCT variant) > 1'
    world = f"""
        WITH test AS ({test})
        SELECT (min(visit_date) - (SELECT min(visit_date) FROM test) + 1)::INTEGER,
            any_value(variant), bool_or(checked_out)
        FROM test GROUP BY visitor_id
    """
    table = 'SELECT test_day, variant, converted FROM checkout_test'
    assert one(full, span) == 40
    assert one(full, unviewed) == 0
    assert rows(full, two) == []
    assert same_rows(full, table, world) == ([], [])
