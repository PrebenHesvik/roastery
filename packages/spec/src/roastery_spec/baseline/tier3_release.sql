-- The roastery release's tier 3 tables, read by `build.tier3()`. The folder of the release is
-- bound at run time as the DuckDB variable `release`; each table is one parquet file in it, read in the order of its key.

-- table: daily_sales | key: sale_date, product_id | grain: One row per day and product with a price that day, 1 October 2024 to 30 September 2026, of the web shop's consumer sales.
CREATE TABLE daily_sales AS SELECT * FROM read_parquet(getvariable('release') || '/daily_sales.parquet') ORDER BY sale_date, product_id;

-- table: order_values | key: order_no | grain: One order of 2026 (600, 1 January to 30 September), web or shop.
CREATE TABLE order_values AS SELECT * FROM read_parquet(getvariable('release') || '/order_values.parquet') ORDER BY order_no;

-- table: budget | key: month, kind | grain: One row per month and product kind, October 2024 to December 2026 (set ahead, as budgets are).
CREATE TABLE budget AS SELECT * FROM read_parquet(getvariable('release') || '/budget.parquet') ORDER BY month, kind;

-- table: checkout_test | key: visitor_no | grain: One visitor of the product page in a 40-day test of two versions, A and B.
CREATE TABLE checkout_test AS SELECT * FROM read_parquet(getvariable('release') || '/checkout_test.parquet') ORDER BY visitor_no;

-- table: subscribers | key: subscription_id | grain: One subscription (240) of the other subscribers, outside the teaching week's cast, started 2024 to September 2026 and counted on 30 September 2026.
CREATE TABLE subscribers AS SELECT * FROM read_parquet(getvariable('release') || '/subscribers.parquet') ORDER BY subscription_id;

-- table: visits | key: visit_id | grain: One visit to the web shop (3,600), 1 October 2024 to 30 September 2026, with the furthest step it reached.
CREATE TABLE visits AS SELECT * FROM read_parquet(getvariable('release') || '/visits.parquet') ORDER BY visit_id;

-- table: deliveries | key: order_no | grain: One web order of order_values, shipped the day after it was placed.
CREATE TABLE deliveries AS SELECT * FROM read_parquet(getvariable('release') || '/deliveries.parquet') ORDER BY order_no;

-- table: shop_days | key: shop_date | grain: One day of the Bergen shop, 1 October 2024 to 30 September 2026; Sundays are closed.
CREATE TABLE shop_days AS SELECT * FROM read_parquet(getvariable('release') || '/shop_days.parquet') ORDER BY shop_date;
