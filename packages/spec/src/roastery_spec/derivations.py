"""The derived tables of tiny, each as SQL on the tables of the extract it is derived from.

One statement of each rule: `tests/test_extracts.py` holds tiny to it, and the simulator's tiny
writer derives the tables with it (6.4, W21).
"""

from __future__ import annotations

from typing import Final

DATED_LINES: Final = """SELECT l.line_id, l.product_id, o.order_date, l.qty, l.unit_price
        FROM order_lines l JOIN orders o USING (order_id)"""

LATEST_STOCK: Final = """SELECT product_id, stock_date, on_hand
        FROM (SELECT * FROM stock_daily QUALIFY row_number()
        OVER (PARTITION BY product_id, stock_date ORDER BY counted_at DESC) = 1)"""

# C-01's year from the orders and lines of full: every month, all five columns.
C01_YEAR: Final = """
    WITH months AS (
        SELECT unnest(generate_series(DATE '2025-11-01', DATE '2026-10-01',
            INTERVAL 1 MONTH))::DATE AS month
    ),
    bought AS (
        SELECT date_trunc('month', o.order_date)::DATE AS month,
            count(DISTINCT o.order_id) AS orders, sum(l.qty * l.unit_price) AS spend
        FROM orders o LEFT JOIN order_lines l USING (order_id)
        WHERE o.customer_id = 'C-01'
        GROUP BY ALL
    )
    SELECT 'C-01' AS customer_id, m.month,
        coalesce(b.orders, 0)::INTEGER AS orders,
        coalesce(b.spend, 0)::DECIMAL(7, 2) AS spend_nok,
        EXISTS (SELECT 1 FROM subscriptions s WHERE s.customer_id = 'C-01'
            AND s.started <= m.month AND (s.ended IS NULL OR m.month < s.ended)) AS subscribed
    FROM months m LEFT JOIN bought b USING (month)
    ORDER BY m.month
"""
