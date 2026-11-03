-- Tier 3 of the roastery: tables made by a formula, written once and built to parquet files
-- that DuckDB, Polars and Spark all read (`uv run python -m data_docs_export.roastery_data`).
-- The statements run in a DuckDB that already holds the tier 1 and tier 2 tables of dataset.sql.
-- Integers only, no random numbers; every division is of non-negative numbers, so floor and
-- truncation agree. Every day-counted table counts its days within 2024-10-01 .. 2026-09-30
-- (`deliveries` by the order's day: an order of 30 September ships on 1 October, still before
-- the teaching week); `subscribers` may start earlier (1 January 2024) and `budget` runs ahead
-- to December 2026.

-- table: daily_sales | key: sale_date, product_id | grain: One row per day and product with a price that day, 1 October 2024 to 30 September 2026.
-- This formula builds the table from the roastery's dataset, and runs on it.
CREATE TABLE daily_sales AS
WITH days AS (
    SELECT n, DATE '2024-10-01' + n::INTEGER AS sale_date FROM range(0, 730) t(n)
),
base(product_id, p, base) AS (
    VALUES ('P-10', 10, 16), ('P-11', 11, 6), ('P-20', 20, 1), ('P-21', 21, 1)
),
grid AS (
    SELECT d.sale_date, b.product_id, b.base,
        [2, 2, 2, 3, 4, 3, 1][isodow(d.sale_date)] AS w,
        CASE WHEN month(d.sale_date) = 12 AND day(d.sale_date) <= 23 THEN b.base ELSE 0 END AS dec,
        -- the second year grows by a quarter of the base, ramped in over October to December 2025
        b.base * least(greatest(d.n - 365, 0), 90) // 360 AS growth,
        (d.n * 7919 + b.p * 104729) % 5 - 2 AS noise
    FROM days d CROSS JOIN base b
)
SELECT g.sale_date,
    g.product_id,
    greatest(0, g.base * g.w // 4 + g.dec + g.growth + g.noise)::INTEGER AS qty,
    (greatest(0, g.base * g.w // 4 + g.dec + g.growth + g.noise) * p.price)::DECIMAL(7, 2) AS amount
FROM grid g
JOIN prices p ON p.product_id = g.product_id
    AND g.sale_date >= p.valid_from AND (p.valid_to IS NULL OR g.sale_date < p.valid_to)
ORDER BY g.sale_date, g.product_id;

-- table: order_values | key: order_no | grain: One order of 2026 (600, 1 January to 30 September), web or shop.
-- This formula builds the table from the roastery's dataset, and runs on it.
CREATE TABLE order_values AS
WITH o AS (
    SELECT i,
        DATE '2026-01-01' + ((i - 1) * 273 // 600)::INTEGER AS placed,
        CASE WHEN i % 5 = 0 THEN 'shop' ELSE 'web' END AS channel,
        CASE WHEN (i * 7919) % 100 < 55 THEN 1
             WHEN (i * 7919) % 100 < 80 THEN 2
             WHEN (i * 7919) % 100 < 93 THEN 4
             ELSE 10 END AS band,
        CASE WHEN (i * 104729) % 3 = 0 THEN 'P-11' ELSE 'P-10' END AS coffee
    FROM range(1, 601) t(i)
),
b AS (
    -- the shop is closed on Sunday: a shop order that would fall there is rung up on Monday
    SELECT i, placed + CASE WHEN channel = 'shop' AND isodow(placed) = 7 THEN 1 ELSE 0 END
            AS order_date,
        channel,
        CASE WHEN i = 600 THEN 48
             WHEN channel = 'shop' THEN least(band, 2)
             ELSE band END AS bags,
        CASE WHEN i = 600 THEN 'P-10' ELSE coffee END AS coffee
    FROM o
)
SELECT b.i::INTEGER AS order_no,
    b.order_date,
    b.channel,
    (CASE WHEN b.i = 300 THEN -899
          ELSE b.bags * pc.price
               + CASE WHEN b.i % 11 = 0 AND b.channel = 'web' THEN pg.price ELSE 0 END
     END)::DECIMAL(7, 2) AS amount,
    CASE WHEN b.i = 300 THEN 'refund'
         WHEN b.bags >= 4 AND b.i % 3 = 0 THEN 'unpaid'
         ELSE 'paid' END AS status
FROM b
JOIN prices pc ON pc.product_id = b.coffee
    AND b.order_date >= pc.valid_from AND (pc.valid_to IS NULL OR b.order_date < pc.valid_to)
JOIN prices pg ON pg.product_id = 'P-20'
    AND b.order_date >= pg.valid_from AND (pg.valid_to IS NULL OR b.order_date < pg.valid_to)
ORDER BY b.i;

-- table: budget | key: month, kind | grain: One row per month and product kind, October 2024 to December 2026 (set ahead, as budgets are).
-- This formula builds the table from the roastery's dataset, and runs on it.
-- A round number of whole kroner per kind and year (October to September), doubled in December,
-- set near what a month sells, so some months beat the budget and some miss it: beans 70,000 in
-- the first year and 95,000 from October 2025; equipment 0 until the grinder's first price (June
-- 2025), then 18,000. Whole kroner, as the owner's sheet has them.
CREATE TABLE budget AS
WITH m AS (
    SELECT (DATE '2024-10-01' + INTERVAL (m) MONTH)::DATE AS month FROM range(0, 27) t(m)
)
SELECT m.month,
    k.kind,
    CASE WHEN k.kind = 'beans' AND m.month < DATE '2025-10-01' THEN 70000
         WHEN k.kind = 'beans' THEN 95000
         WHEN m.month < DATE '2025-06-01' THEN 0
         ELSE 18000 END
        * CASE WHEN month(m.month) = 12 THEN 2 ELSE 1 END AS budget_nok
FROM m
CROSS JOIN (VALUES ('beans'), ('equipment')) k(kind)
ORDER BY month, kind;

-- table: checkout_test | key: visitor_no | grain: One visitor of the product page in a 40-day test of two versions, A and B.
-- This formula builds the table from the roastery's dataset, and runs on it.
CREATE TABLE checkout_test AS
SELECT i::INTEGER AS visitor_no,
    ((i - 1) // 100 + 1)::INTEGER AS test_day,
    CASE WHEN i % 2 = 0 THEN 'A' ELSE 'B' END AS variant,
    (i * i * 7919 + i * 104729) % 1009 < CASE WHEN i % 2 = 0 THEN 121 ELSE 151 END AS converted
FROM range(1, 4001) t(i)
ORDER BY i;

-- table: subscribers | key: subscription_id | grain: One subscription (240), started 2024 to September 2026 and counted on 30 September 2026.
-- This formula builds the table from the roastery's dataset, and runs on it.
CREATE TABLE subscribers AS
WITH s AS (
    SELECT i,
        DATE '2024-01-01' + ((i - 1) * 1000 // 240)::INTEGER AS started
    FROM range(1, 241) t(i)
),
k AS (
    SELECT i, started, (i * 7919) % 31 + 6 * (year(started) - 2024) AS months_kept FROM s
)
SELECT i::INTEGER AS subscription_id,
    CASE WHEN i % 3 = 0 THEN 'P-11' ELSE 'P-10' END AS product_id,
    started,
    CASE WHEN (started + INTERVAL (months_kept) MONTH)::DATE > DATE '2026-09-30' THEN NULL
         ELSE (started + INTERVAL (months_kept) MONTH)::DATE END AS ended
FROM k
ORDER BY i;

-- table: visits | key: visit_id | grain: One visit to the web shop (3,600), 1 October 2024 to 30 September 2026, with the furthest step it reached.
-- This formula builds the table from the roastery's dataset, and runs on it.
CREATE TABLE visits AS
WITH cells(slot, country, source, n) AS (
    VALUES (0, 'SE', 'newsletter', 13), (1, 'SE', 'ads', 2), (2, 'DK', 'newsletter', 2),
        (3, 'DK', 'ads', 13), (4, 'NO', 'newsletter', 20), (5, 'NO', 'ads', 20),
        (6, 'FI', 'ads', 2)
),
slots(slot, s) AS (
    SELECT c.slot, u.s
    FROM cells c, LATERAL (SELECT unnest(range(c.n)) AS s) u
),
-- 72 positions in a cycle of visits (50 visits each), each in one cell; 5 steps through them in
-- a mixed order, so the cells spread over the whole period
cycle AS (
    SELECT row_number() OVER (ORDER BY slot, s) - 1 AS pos, slot FROM slots
),
v AS (
    SELECT i,
        c.slot
    FROM range(1, 3601) t(i)
    JOIN cycle c ON c.pos = ((i - 1) * 5) % 72
),
w AS (
    SELECT v.i, ce.country,
        -- Finland: 100 of the 3,600 visits, 4 of them from the newsletter
        CASE WHEN ce.country = 'FI' AND ((v.i - 1) // 72) % 25 = 0 THEN 'newsletter'
             ELSE ce.source END AS source,
        (v.i * v.i * 7919 + v.i * 104729) % 1009 AS r
    FROM v JOIN (SELECT DISTINCT slot, country, source FROM cells) ce ON ce.slot = v.slot
)
SELECT i::INTEGER AS visit_id,
    DATE '2024-10-01' + ((i - 1) * 730 // 3600)::INTEGER AS visit_date,
    country,
    source,
    (1 + (r < c1)::INTEGER + (r < c2)::INTEGER + (r < c3)::INTEGER)::INTEGER AS reached
FROM (
    SELECT w.*,
        (CASE w.source WHEN 'newsletter' THEN 700 ELSE 500 END) + sh AS c1,
        (CASE w.source WHEN 'newsletter' THEN 450 ELSE 250 END) + sh AS c2,
        (CASE w.source WHEN 'newsletter' THEN 200 ELSE 50 END) + sh AS c3
    FROM w
    CROSS JOIN LATERAL (
        SELECT CASE w.country WHEN 'DK' THEN 60 WHEN 'NO' THEN 20 ELSE 0 END AS sh
    ) z
) q
ORDER BY i;

-- table: deliveries | key: order_no | grain: One web order of order_values, shipped the day after it was placed.
-- This formula builds the table from the roastery's dataset, and runs on it.
CREATE TABLE deliveries AS
SELECT o.order_no,
    CASE o.order_no % 10
        WHEN 1 THEN 'NO' WHEN 2 THEN 'NO' WHEN 3 THEN 'NO' WHEN 4 THEN 'NO'
        WHEN 6 THEN 'SE' WHEN 7 THEN 'SE' WHEN 8 THEN 'DK' ELSE 'FI' END AS country,
    o.order_date + 1 AS shipped_on,
    -- the same mean (3) everywhere; Norway the widest spread (Bergen the next day, the far north
    -- in five), Sweden, Denmark and Finland two to four days; order 297 is lost for three weeks
    (CASE WHEN o.order_no = 297 THEN 21
          WHEN o.order_no % 10 IN (1, 2, 3, 4) THEN 1 + 2 * ((o.order_no * 7) % 3)
          ELSE 2 + (o.order_no * 7) % 3 END)::INTEGER AS days
FROM order_values o
WHERE o.channel = 'web'
ORDER BY o.order_no;

-- table: shop_days | key: shop_date | grain: One day of the Bergen shop, 1 October 2024 to 30 September 2026; Sundays are closed.
-- This formula builds the table from the roastery's dataset, and runs on it.
CREATE TABLE shop_days AS
WITH days AS (
    SELECT n, DATE '2024-10-01' + n::INTEGER AS shop_date FROM range(0, 730) t(n)
),
d AS (
    SELECT n, shop_date,
        [2, 2, 2, 3, 4, 3, 1][isodow(shop_date)] AS w,
        isodow(shop_date) AS dow,
        CASE WHEN month(shop_date) = 12 AND day(shop_date) <= 23 THEN 15 ELSE 0 END AS dec,
        CASE WHEN (n * 7919) % 10 < 7 THEN (n * 104729) % 23 ELSE 0 END AS rain_mm
    FROM days
),
f AS (
    -- the noise cycles every five days, so it does not line up with the weekdays
    SELECT *,
        CASE WHEN dow = 7 THEN 0
             ELSE 30 + 6 * w + dec - rain_mm + (n * 31) % 5 - 2 END AS walk_ins
    FROM d
)
SELECT shop_date,
    rain_mm::INTEGER AS rain_mm,
    walk_ins::INTEGER AS walk_ins,
    (CASE WHEN dow = 7 THEN 0 ELSE walk_ins * 3 // 5 + (n * 17) % 3 END)::INTEGER AS receipts
FROM f
ORDER BY shop_date;
