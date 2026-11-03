-- The roastery's tables. Invented rows: never read from data/.
-- Each row holds one thing on purpose, named in docs/proposal-coffee-roaster.md.
-- App stamps are UTC; till_receipts.sold_at is Bergen time. Money is DECIMAL(7, 2).

-- The four tables every page uses, and the lines with their order's day.

-- table: customers | key: customer_id | grain: One row per customer, as the shop holds them today.
CREATE TABLE customers (
    customer_id VARCHAR,
    name VARCHAR,
    country VARCHAR,
    postal_code VARCHAR,
    joined DATE
);
INSERT INTO customers VALUES
    ('C-01', 'Ingrid', 'NO', '0150', DATE '2024-03-01'),
    ('C-02', 'Åsa', 'SE', '21119', DATE '2025-01-15'),
    ('C-03', 'Mikkel', 'DK', '8000', DATE '2025-06-02'),
    ('C-04', 'Aino', 'FI', '33100', DATE '2025-06-02'),
    ('C-05', 'Lars', NULL, NULL, DATE '2026-02-10'),
    ('C-06', 'Mona', 'NO', '5003', DATE '2026-10-09');

-- table: products | key: product_id | grain: One row per product the shop lists.
CREATE TABLE products (
    product_id VARCHAR,
    product_name VARCHAR,
    kind VARCHAR,
    category_id VARCHAR,
    weight_g INTEGER
);
INSERT INTO products VALUES
    ('P-10', 'Morning roast', 'beans', 'CAT-11', 250),
    ('P-11', 'Dark espresso', 'beans', 'CAT-12', 1000),
    ('P-12', 'Decaf', 'beans', 'CAT-11', 250),
    ('P-20', 'Hand grinder', 'equipment', 'CAT-22', NULL),
    ('P-21', 'Pour-over kettle', 'equipment', 'CAT-23', NULL);

-- table: orders | key: order_id | grain: One row per order, dated on the customer's clock.
CREATE TABLE orders (
    order_id VARCHAR,
    customer_id VARCHAR,
    order_date DATE,
    channel VARCHAR
);
INSERT INTO orders VALUES
    ('O-101', 'C-01', DATE '2026-10-05', 'web'),
    ('O-102', 'C-02', DATE '2026-10-05', 'web'),
    ('O-103', 'C-03', DATE '2026-10-06', 'web'),
    ('O-104', 'C-01', DATE '2026-10-06', 'shop'),
    ('O-105', 'C-05', DATE '2026-10-07', 'web'),
    ('O-106', 'C-04', DATE '2026-10-07', 'web'),
    ('O-107', 'C-07', DATE '2026-10-07', 'web'),
    ('O-108', 'C-01', DATE '2026-10-09', 'web');

-- table: order_lines | key: line_id | grain: One row per order line: an order, a product, a quantity, in NOK.
CREATE TABLE order_lines (
    line_id VARCHAR,
    order_id VARCHAR,
    product_id VARCHAR,
    qty INTEGER,
    unit_price DECIMAL(7, 2)
);
INSERT INTO order_lines VALUES
    ('L-01', 'O-101', 'P-10', 2, 129.00),
    ('L-02', 'O-101', 'P-20', 1, 899.00),
    ('L-03', 'O-102', 'P-11', 1, 349.00),
    ('L-04', 'O-103', 'P-10', 3, 129.00),
    ('L-05', 'O-103', 'P-10', 3, 129.00),
    ('L-06', 'O-104', 'P-21', 1, 549.00),
    ('L-07', 'O-105', 'P-11', NULL, 349.00),
    ('L-08', 'O-107', 'P-10', 1, 129.00),
    ('L-09', 'O-102', 'P-99', 1, 199.00),
    ('L-11', 'O-108', 'P-10', 1, 129.00),
    ('L-12', 'O-108', 'P-11', 1, 0.00);

-- table: dated_lines | key: line_id | grain: One row per order line, with its order's day. The pages call it order_lines.dated.
-- Pages and the catalog call it order_lines.dated; a dot cannot be part of a table's name.
-- Derived from order_lines joined to orders; the rows are written out so the table stands alone.
CREATE TABLE dated_lines (
    line_id VARCHAR,
    product_id VARCHAR,
    order_date DATE,
    qty INTEGER,
    unit_price DECIMAL(7, 2)
);
INSERT INTO dated_lines VALUES
    ('L-01', 'P-10', DATE '2026-10-05', 2, 129.00),
    ('L-02', 'P-20', DATE '2026-10-05', 1, 899.00),
    ('L-03', 'P-11', DATE '2026-10-05', 1, 349.00),
    ('L-04', 'P-10', DATE '2026-10-06', 3, 129.00),
    ('L-05', 'P-10', DATE '2026-10-06', 3, 129.00),
    ('L-06', 'P-21', DATE '2026-10-06', 1, 549.00),
    ('L-07', 'P-11', DATE '2026-10-07', NULL, 349.00),
    ('L-08', 'P-10', DATE '2026-10-07', 1, 129.00),
    ('L-09', 'P-99', DATE '2026-10-05', 1, 199.00),
    ('L-11', 'P-10', DATE '2026-10-09', 1, 129.00),
    ('L-12', 'P-11', DATE '2026-10-09', 1, 0.00);


-- table: prices | key: product_id, valid_from | grain: One row per product and period a list price held.
CREATE TABLE prices (
    product_id VARCHAR,
    price DECIMAL(7, 2),
    valid_from DATE,
    valid_to DATE
);
INSERT INTO prices VALUES
    ('P-10', 119.00, DATE '2024-01-01', DATE '2026-10-01'),
    ('P-10', 129.00, DATE '2026-10-01', NULL),
    ('P-11', 329.00, DATE '2024-01-01', DATE '2026-10-05'),
    ('P-11', 349.00, DATE '2026-10-05', NULL),
    ('P-20', 899.00, DATE '2025-06-01', NULL),
    ('P-21', 549.00, DATE '2026-10-07', NULL);

-- table: fx_rates | key: currency, rate_date | grain: One row per currency and banking day, 2 to 7 October 2026: kroner for one unit.
CREATE TABLE fx_rates (
    currency VARCHAR,
    rate_date DATE,
    nok_per_unit DECIMAL(8, 4)
);
INSERT INTO fx_rates VALUES
    ('DKK', DATE '2026-10-02', 1.5580),
    ('EUR', DATE '2026-10-02', 11.6200),
    ('EUR', DATE '2026-10-05', 11.6400),
    ('EUR', DATE '2026-10-06', 11.6100),
    ('EUR', DATE '2026-10-07', 11.6300),
    ('SEK', DATE '2026-10-02', 1.0610),
    ('SEK', DATE '2026-10-05', 1.0600),
    ('SEK', DATE '2026-10-06', 1.0620);

-- table: payments | key: none | grain: One row per message from the payment provider (no key: PAY-1 came twice).
CREATE TABLE payments (
    payment_id VARCHAR,
    order_id VARCHAR,
    currency VARCHAR,
    amount DECIMAL(9, 2),
    paid_on DATE
);
INSERT INTO payments VALUES
    ('PAY-1', 'O-101', 'NOK', 1157.00, DATE '2026-10-05'),
    ('PAY-1', 'O-101', 'NOK', 1157.00, DATE '2026-10-05'),
    ('PAY-2', 'O-102', 'SEK', 516.98, DATE '2026-10-05'),
    ('PAY-3', 'O-103', 'DKK', 248.40, DATE '2026-10-06'),
    ('PAY-4', 'O-104', 'NOK', 549.00, DATE '2026-10-06'),
    ('PAY-5', 'O-105', 'NOK', 349.00, DATE '2026-10-07'),
    ('PAY-6', 'O-108', 'NOK', 129.00, DATE '2026-10-09');

-- table: order_events | key: event_id | grain: One row per status change of an order, stamped in UTC, with the moment it was loaded.
CREATE TABLE order_events (
    event_id VARCHAR,
    order_id VARCHAR,
    status VARCHAR,
    event_at TIMESTAMP,
    loaded_at TIMESTAMP
);
INSERT INTO order_events VALUES
    ('E-01', 'O-101', 'placed', TIMESTAMP '2026-10-05 08:12', TIMESTAMP '2026-10-05 08:15'),
    ('E-02', 'O-101', 'paid', TIMESTAMP '2026-10-05 08:13', TIMESTAMP '2026-10-05 08:15'),
    ('E-03', 'O-101', 'shipped', TIMESTAMP '2026-10-06 13:40', TIMESTAMP '2026-10-06 14:00'),
    ('E-04', 'O-101', 'delivered', TIMESTAMP '2026-10-08 10:05', TIMESTAMP '2026-10-08 11:00'),
    ('E-05', 'O-102', 'placed', TIMESTAMP '2026-10-05 21:50', TIMESTAMP '2026-10-05 22:00'),
    ('E-06', 'O-102', 'paid', TIMESTAMP '2026-10-05 21:52', TIMESTAMP '2026-10-05 22:00'),
    ('E-07', 'O-102', 'shipped', TIMESTAMP '2026-10-07 09:00', TIMESTAMP '2026-10-07 09:15'),
    ('E-08', 'O-102', 'delivered', TIMESTAMP '2026-10-08 12:00', TIMESTAMP '2026-10-10 07:00'),
    ('E-09', 'O-104', 'placed', TIMESTAMP '2026-10-06 15:20', TIMESTAMP '2026-10-06 15:45'),
    ('E-10', 'O-104', 'paid', TIMESTAMP '2026-10-06 15:21', TIMESTAMP '2026-10-06 15:30'),
    ('E-11', 'O-106', 'placed', TIMESTAMP '2026-10-06 21:30', TIMESTAMP '2026-10-06 21:45'),
    ('E-12', 'O-106', 'cancelled', TIMESTAMP '2026-10-07 06:00', TIMESTAMP '2026-10-07 06:15'),
    ('E-13', 'O-108', 'placed', TIMESTAMP '2026-10-09 19:30', TIMESTAMP '2026-10-09 19:45'),
    ('E-14', 'O-108', 'paid', TIMESTAMP '2026-10-09 19:31', TIMESTAMP '2026-10-09 19:45');

-- table: stock_daily | key: product_id, stock_date, counted_at | grain: One row per product, working day and count, P-10 and P-20, 5 to 9 October: the bags or boxes on the shelf at close; counted_at is UTC (16:00 is 18:00 at close in Bergen, summer time).
-- The warehouse sends a whole day at a time. The day of 7 October was sent twice: the count
-- at close said 26 bags of P-10, and a recount the next morning said 36. A reader takes the
-- latest count of each day:
--   SELECT * FROM stock_daily
--   QUALIFY row_number() OVER (PARTITION BY product_id, stock_date ORDER BY counted_at DESC) = 1
CREATE TABLE stock_daily (
    product_id VARCHAR,
    stock_date DATE,
    on_hand INTEGER,
    counted_at TIMESTAMP
);
INSERT INTO stock_daily VALUES
    ('P-10', DATE '2026-10-05', 40, TIMESTAMP '2026-10-05 16:00'),
    ('P-10', DATE '2026-10-06', 37, TIMESTAMP '2026-10-06 16:00'),
    ('P-10', DATE '2026-10-07', 26, TIMESTAMP '2026-10-07 16:00'),
    ('P-10', DATE '2026-10-07', 36, TIMESTAMP '2026-10-08 06:30'),
    ('P-10', DATE '2026-10-08', 60, TIMESTAMP '2026-10-08 16:00'),
    ('P-10', DATE '2026-10-09', 59, TIMESTAMP '2026-10-09 16:00'),
    ('P-20', DATE '2026-10-05', 4, TIMESTAMP '2026-10-05 16:00'),
    ('P-20', DATE '2026-10-06', 4, TIMESTAMP '2026-10-06 16:00'),
    ('P-20', DATE '2026-10-07', 4, TIMESTAMP '2026-10-07 16:00'),
    ('P-20', DATE '2026-10-07', 4, TIMESTAMP '2026-10-08 06:30'),
    ('P-20', DATE '2026-10-08', 4, TIMESTAMP '2026-10-08 16:00'),
    ('P-20', DATE '2026-10-09', 4, TIMESTAMP '2026-10-09 16:00');

-- table: latest_stock | key: product_id, stock_date | grain: One row per product and working day, the latest count of that day. The pages call it stock_daily.latest.
-- Pages and the catalog call it stock_daily.latest; a dot cannot be part of a table's name.
-- Derived from stock_daily (the latest count of each product and day); the rows are written out
-- so the table stands alone.
CREATE TABLE latest_stock (
    product_id VARCHAR,
    stock_date DATE,
    on_hand INTEGER
);
INSERT INTO latest_stock VALUES
    ('P-10', DATE '2026-10-05', 40),
    ('P-10', DATE '2026-10-06', 37),
    ('P-10', DATE '2026-10-07', 36),
    ('P-10', DATE '2026-10-08', 60),
    ('P-10', DATE '2026-10-09', 59),
    ('P-20', DATE '2026-10-05', 4),
    ('P-20', DATE '2026-10-06', 4),
    ('P-20', DATE '2026-10-07', 4),
    ('P-20', DATE '2026-10-08', 4),
    ('P-20', DATE '2026-10-09', 4);

-- table: customer_extracts | key: extract_date, customer_id | grain: One row per customer in each of two nightly copies, 8 and 9 October, of the shop's customer table.
CREATE TABLE customer_extracts (
    extract_date DATE,
    customer_id VARCHAR,
    country VARCHAR,
    postal_code VARCHAR
);
INSERT INTO customer_extracts VALUES
    (DATE '2026-10-08', 'C-01', 'NO', '7010'),
    (DATE '2026-10-08', 'C-02', 'SE', '21119'),
    (DATE '2026-10-08', 'C-03', 'DK', '8000'),
    (DATE '2026-10-08', 'C-04', 'FI', '33100'),
    (DATE '2026-10-08', 'C-05', NULL, NULL),
    (DATE '2026-10-08', 'C-07', 'NO', '0450'),
    (DATE '2026-10-09', 'C-01', 'NO', '0150'),
    (DATE '2026-10-09', 'C-02', 'SE', '21119'),
    (DATE '2026-10-09', 'C-03', 'DK', '8000'),
    (DATE '2026-10-09', 'C-04', 'FI', '33100'),
    (DATE '2026-10-09', 'C-05', NULL, NULL),
    (DATE '2026-10-09', 'C-06', 'NO', '5003');

-- table: customer_changes | key: seq | grain: One row per change the app wrote to its customers table; seq numbers the changes in the order the app wrote them.
-- Each customer is inserted on the day they joined. On 9 October C-06 joins, C-07 is erased
-- (the tombstone carries the key only), and C-01 moves twice in one batch: a typo, 0510,
-- fixed three minutes later. Folded to the newest row per customer, without the deletes, it
-- is the copy of 9 October; folded up to midnight before, it is the copy of 8 October.
CREATE TABLE customer_changes (
    seq INTEGER,
    op VARCHAR,
    customer_id VARCHAR,
    country VARCHAR,
    postal_code VARCHAR,
    changed_at TIMESTAMP
);
INSERT INTO customer_changes VALUES
    (1, 'insert', 'C-01', 'NO', '7010', TIMESTAMP '2024-03-01 09:00'),
    (2, 'insert', 'C-02', 'SE', '21119', TIMESTAMP '2025-01-15 14:30'),
    (3, 'insert', 'C-07', 'NO', '0450', TIMESTAMP '2025-02-20 11:10'),
    (4, 'insert', 'C-03', 'DK', '8000', TIMESTAMP '2025-06-02 08:45'),
    (5, 'insert', 'C-04', 'FI', '33100', TIMESTAMP '2025-06-02 19:20'),
    (6, 'insert', 'C-05', NULL, NULL, TIMESTAMP '2026-02-10 13:00'),
    (7, 'insert', 'C-06', 'NO', '5003', TIMESTAMP '2026-10-09 10:14'),
    (8, 'delete', 'C-07', NULL, NULL, TIMESTAMP '2026-10-09 14:30'),
    (9, 'update', 'C-01', 'NO', '0510', TIMESTAMP '2026-10-09 18:02'),
    (10, 'update', 'C-01', 'NO', '0150', TIMESTAMP '2026-10-09 18:05');

-- table: line_stamps | key: line_id | grain: One row per row of the app's order lines table, deleted rows kept, with the moment it last changed.
-- Each line is stamped at its order's moment (the placed event where order_events has one).
-- L-10 was O-106's line; it was marked deleted when Aino cancelled, at the moment of E-12.
-- Without the deleted row it is order_lines.
CREATE TABLE line_stamps (
    line_id VARCHAR,
    order_id VARCHAR,
    qty INTEGER,
    is_deleted BOOLEAN,
    updated_at TIMESTAMP
);
INSERT INTO line_stamps VALUES
    ('L-01', 'O-101', 2, false, TIMESTAMP '2026-10-05 08:12'),
    ('L-02', 'O-101', 1, false, TIMESTAMP '2026-10-05 08:12'),
    ('L-03', 'O-102', 1, false, TIMESTAMP '2026-10-05 21:50'),
    ('L-04', 'O-103', 3, false, TIMESTAMP '2026-10-06 10:20'),
    ('L-05', 'O-103', 3, false, TIMESTAMP '2026-10-06 10:20'),
    ('L-06', 'O-104', 1, false, TIMESTAMP '2026-10-06 15:20'),
    ('L-07', 'O-105', NULL, false, TIMESTAMP '2026-10-07 11:05'),
    ('L-08', 'O-107', 1, false, TIMESTAMP '2026-10-07 16:40'),
    ('L-09', 'O-102', 1, false, TIMESTAMP '2026-10-05 21:50'),
    ('L-10', 'O-106', 1, true, TIMESTAMP '2026-10-07 06:00'),
    ('L-11', 'O-108', 1, false, TIMESTAMP '2026-10-09 19:30'),
    ('L-12', 'O-108', 1, false, TIMESTAMP '2026-10-09 19:30');

-- table: raw_customers | key: none | grain: One row per customer who has ordered (C-01 to C-05) in the shop's csv export, as of after C-01's move on 9 October, every column text (no key: the text is as the export gave it); C-06 has no order and C-07 is erased, so neither is in it.
CREATE TABLE raw_customers (
    customer_id VARCHAR,
    name VARCHAR,
    country VARCHAR,
    postal_code VARCHAR,
    joined VARCHAR,
    email VARCHAR
);
INSERT INTO raw_customers VALUES
    ('C-01 ', 'Ingrid', 'no', '150', '01.03.2024', ' Ingrid@Example.invalid'),
    ('c-02', 'Åsa', ' SE', '21119', '2025-01-15', 'asa@example.invalid'),
    (chr(9) || 'C-03', 'Mikkel', 'DK', '8000', '2025-06-02', 'mikkel@example.invalid '),
    ('C-04' || chr(160), 'Aino', 'FI', '33100', '02.06.2025', 'aino@example.invalid'),
    ('C-05', 'Lars', '', '', '2026-02-10', NULL);

-- table: raw_lines | key: line_id | grain: Five lines (L-01, L-02, L-03, L-06, L-07) of the shop's csv export, every column text.
CREATE TABLE raw_lines (
    line_id VARCHAR,
    order_id VARCHAR,
    product_id VARCHAR,
    qty VARCHAR,
    unit_price VARCHAR
);
INSERT INTO raw_lines VALUES
    ('L-01', 'O-101', 'P-10', '2', '129,00'),
    ('L-02', 'O-101', ' p-20', '1', '899.00'),
    ('L-03', 'O-102', 'P-11', '1', '349'),
    ('L-06', 'O-104', 'P-21', '1', '549,00'),
    ('L-07', 'O-105', 'P-11', 'n/a', '349.00');

-- table: web_events | key: event_id | grain: One row per thing one of four visitors did on the web shop, stamped in UTC.
CREATE TABLE web_events (
    event_id VARCHAR,
    visitor_id VARCHAR,
    customer_id VARCHAR,
    event VARCHAR,
    event_at TIMESTAMP
);
INSERT INTO web_events VALUES
    ('W-01', 'V-1', 'C-01', 'view', TIMESTAMP '2026-10-05 08:05'),
    ('W-02', 'V-1', 'C-01', 'cart', TIMESTAMP '2026-10-05 08:09'),
    ('W-03', 'V-1', 'C-01', 'checkout', TIMESTAMP '2026-10-05 08:11'),
    ('W-04', 'V-2', NULL, 'view', TIMESTAMP '2026-10-05 12:00'),
    ('W-05', 'V-2', NULL, 'view', TIMESTAMP '2026-10-05 12:45'),
    ('W-06', 'V-2', NULL, 'cart', TIMESTAMP '2026-10-05 12:47'),
    ('W-07', 'V-3', 'C-02', 'view', TIMESTAMP '2026-10-05 21:40'),
    ('W-08', 'V-3', 'C-02', 'cart', TIMESTAMP '2026-10-05 21:45'),
    ('W-09', 'V-3', 'C-02', 'checkout', TIMESTAMP '2026-10-05 21:49'),
    ('W-10', 'V-4', 'C-04', 'view', TIMESTAMP '2026-10-06 21:20'),
    ('W-11', 'V-4', 'C-04', 'cart', TIMESTAMP '2026-10-06 21:25'),
    ('W-12', 'V-4', 'C-04', 'checkout', TIMESTAMP '2026-10-06 21:28');

-- table: subscriptions | key: subscription_id | grain: One row per subscription: a customer, a product every month, from a first day to the day it stopped.
CREATE TABLE subscriptions (
    subscription_id VARCHAR,
    customer_id VARCHAR,
    product_id VARCHAR,
    started DATE,
    ended DATE
);
INSERT INTO subscriptions VALUES
    ('S-1', 'C-01', 'P-10', DATE '2024-04-01', NULL),
    ('S-2', 'C-02', 'P-11', DATE '2025-02-01', DATE '2025-08-01'),
    ('S-3', 'C-02', 'P-11', DATE '2025-09-01', NULL),
    ('S-4', 'C-03', 'P-10', DATE '2025-07-01', DATE '2026-01-01'),
    ('S-5', 'C-04', 'P-11', DATE '2025-07-01', DATE '2025-10-01'),
    ('S-6', 'C-04', 'P-10', DATE '2025-09-15', NULL),
    ('S-7', 'C-07', 'P-10', DATE '2025-03-01', DATE '2026-10-09');

-- table: categories | key: category_id | grain: One row per category; parent_id points one level up, sort_order is the shop's order.
-- sort_order is the one order of the tree, set in one place: it puts Filter before Espresso
-- and Kettles before Grinders, which neither the names nor the ids do.
CREATE TABLE categories (
    category_id VARCHAR,
    category_name VARCHAR,
    parent_id VARCHAR,
    sort_order INTEGER
);
INSERT INTO categories VALUES
    ('CAT-1', 'Beans', NULL, 1),
    ('CAT-11', 'Filter', 'CAT-1', 2),
    ('CAT-12', 'Espresso', 'CAT-1', 3),
    ('CAT-2', 'Equipment', NULL, 4),
    ('CAT-21', 'Grinders', 'CAT-2', 6),
    ('CAT-22', 'Hand grinders', 'CAT-21', 7),
    ('CAT-23', 'Kettles', 'CAT-2', 5);

-- table: kinds | key: kind | grain: One row per kind of product, so a budget by kind relates to products through it.
CREATE TABLE kinds (
    kind VARCHAR,
    kind_name VARCHAR
);
INSERT INTO kinds VALUES
    ('beans', 'Coffee beans'),
    ('equipment', 'Brewing equipment');

-- table: campaign_products | key: campaign_id, product_id | grain: One row per campaign and product in it.
-- The bridge's campaign_group_key and weight (0.5 and 0.5 for P-20, decision 9) are not
-- columns here: the gold build computes them (group = the set of campaigns a product is in,
-- weight = 1 / its count), because they are an allocation the model decides, not something
-- the shop's campaign list records; the twins and DAX read this table unweighted.
CREATE TABLE campaign_products (
    campaign_id VARCHAR,
    campaign_name VARCHAR,
    product_id VARCHAR
);
INSERT INTO campaign_products VALUES
    ('K-1', 'Autumn espresso', 'P-11'),
    ('K-1', 'Autumn espresso', 'P-20'),
    ('K-2', 'Brew at home', 'P-10'),
    ('K-2', 'Brew at home', 'P-20'),
    ('K-2', 'Brew at home', 'P-21');

-- table: campaigns | key: campaign_id | grain: One row per campaign, with its discount and its days.
CREATE TABLE campaigns (
    campaign_id VARCHAR,
    campaign_name VARCHAR,
    discount_pct INTEGER,
    first_day DATE,
    last_day DATE
);
INSERT INTO campaigns VALUES
    ('K-1', 'Autumn espresso', 10, DATE '2026-10-12', DATE '2026-10-25'),
    ('K-2', 'Brew at home', 15, DATE '2026-11-16', DATE '2026-11-29');

-- The Bergen shop's till: a second system with its own keys. It went live on 7 October; O-104
-- was typed into the app and rung in the till on 6 October, during the trial.

-- table: product_codes | key: ean | grain: One row per code the till knows, and the product it is.
-- Dark espresso has two codes: the box, and loose beans sold by the gram. 2000000000992 is a
-- code the till knows and the shop does not list: it has no product.
CREATE TABLE product_codes (
    ean VARCHAR,
    product_id VARCHAR
);
INSERT INTO product_codes VALUES
    ('2000000000107', 'P-10'),
    ('2000000000114', 'P-11'),
    ('2100000000111', 'P-11'),
    ('2000000000206', 'P-20'),
    ('2000000000213', 'P-21'),
    ('2000000000992', NULL);

-- table: till_receipts | key: receipt_id | grain: One row per till receipt of a listed member, and the trial day's one receipt, sold_at in Bergen time.
-- R-5001 is O-104's kettle, the same sale as L-06: 17:20 in Bergen is E-09's 15:20 UTC. It
-- was rung during the trial, before the club list came into the till, so it names no member
-- (NULL): the match to O-104 is by moment and product, not by customer.
-- R-5002 names 1003, Mikkel's second number: the sale reaches C-03 only through the map.
-- R-5003 names 1004, Sindre, who has no web account: a member's sale no customer matches.
-- R-5004 names 1006, Hilde, who joined at the counter on 9 October and is first listed on
-- 10 October: the inferred member, a fact before its dimension row.
CREATE TABLE till_receipts (
    receipt_id VARCHAR,
    member_no INTEGER,
    sold_at TIMESTAMP
);
INSERT INTO till_receipts VALUES
    ('R-5001', NULL, TIMESTAMP '2026-10-06 17:20'),
    ('R-5002', 1003, TIMESTAMP '2026-10-07 10:42'),
    ('R-5003', 1004, TIMESTAMP '2026-10-08 12:15'),
    ('R-5004', 1006, TIMESTAMP '2026-10-09 15:05');

-- table: till_lines | key: receipt_id, line_no | grain: One row per line of those receipts.
-- Every receipt numbers its lines from 1. grams is set for loose beans only. The till sells no
-- bag of Morning roast and no grinder here, so stock_daily still matches order_lines.
CREATE TABLE till_lines (
    receipt_id VARCHAR,
    line_no INTEGER,
    ean VARCHAR,
    grams INTEGER,
    amount DECIMAL(7, 2)
);
INSERT INTO till_lines VALUES
    ('R-5001', 1, '2000000000213', NULL, 549.00),
    ('R-5002', 1, '2100000000111', 250, 87.25),
    ('R-5002', 2, '2000000000114', NULL, 349.00),
    ('R-5003', 1, '2000000000992', NULL, 45.00),
    ('R-5003', 2, '2100000000111', 100, 34.90),
    ('R-5004', 1, '2100000000111', 500, 174.50);

-- table: till_members | key: member_no, listed_on | grain: One row per listed member in each nightly list of the shop's club: the first list holds every member, later ones those who joined.
-- The till was never told that Ingrid moved (7010) or that C-07 was erased (1005, 0450).
-- Mikkel signed up twice. Sindre has no web account. Hilde joined at the counter on 9 October
-- and is first listed the next night, after R-5004 named her.
CREATE TABLE till_members (
    member_no INTEGER,
    name VARCHAR,
    email VARCHAR,
    postal_code VARCHAR,
    listed_on DATE
);
INSERT INTO till_members VALUES
    (1001, 'Ingrid', 'Ingrid@Example.invalid', '7010', DATE '2026-10-07'),
    (1002, 'Mikkel', 'mikkel@example.invalid', '8000', DATE '2026-10-07'),
    (1003, 'Mikkel', 'Mikkel@Example.invalid', '8000', DATE '2026-10-07'),
    (1004, 'Sindre', 'sindre@example.invalid', '5006', DATE '2026-10-07'),
    (1005, 'Tor', 'tor@example.invalid', '0450', DATE '2026-10-07'),
    (1006, 'Hilde', 'hilde@example.invalid', '5007', DATE '2026-10-10');

-- table: customer_months | key: customer_id, month | grain: One row per month of C-01, November 2025 to October 2026: orders, spend in NOK and whether a subscription ran; spend_nok counts the orders' lines only, not the subscription's monthly charge (a month can show 0.00 with subscribed true).
-- Twelve months of C-01, whose orders and spend cross band edges often. October 2026 holds
-- O-101, O-104 and O-108 so far. S-1 runs the whole year.
CREATE TABLE customer_months (
    customer_id VARCHAR,
    month DATE,
    orders INTEGER,
    spend_nok DECIMAL(7, 2),
    subscribed BOOLEAN
);
INSERT INTO customer_months VALUES
    ('C-01', DATE '2025-11-01', 1, 238.00, true),
    ('C-01', DATE '2025-12-01', 4, 1466.00, true),
    ('C-01', DATE '2026-01-01', 0, 0.00, true),
    ('C-01', DATE '2026-02-01', 1, 119.00, true),
    ('C-01', DATE '2026-03-01', 2, 448.00, true),
    ('C-01', DATE '2026-04-01', 1, 329.00, true),
    ('C-01', DATE '2026-05-01', 3, 1015.00, true),
    ('C-01', DATE '2026-06-01', 0, 0.00, true),
    ('C-01', DATE '2026-07-01', 2, 238.00, true),
    ('C-01', DATE '2026-08-01', 1, 658.00, true),
    ('C-01', DATE '2026-09-01', 2, 567.00, true),
    ('C-01', DATE '2026-10-01', 3, 1835.00, true);

-- table: bean_details | key: product_id | grain: One row per product of the kind beans, with what only beans have.
CREATE TABLE bean_details (
    product_id VARCHAR,
    origin VARCHAR,
    roast VARCHAR,
    process VARCHAR
);
INSERT INTO bean_details VALUES
    ('P-10', 'Ethiopia', 'light', 'washed'),
    ('P-11', 'Brazil', 'dark', 'natural'),
    ('P-12', 'Colombia', 'medium', 'washed');

-- table: equipment_details | key: product_id | grain: One row per product of the kind equipment, with what only equipment has.
CREATE TABLE equipment_details (
    product_id VARCHAR,
    warranty_months INTEGER,
    material VARCHAR
);
INSERT INTO equipment_details VALUES
    ('P-20', 24, 'wood'),
    ('P-21', 12, 'steel');

-- table: managers | key: country | grain: One row per country and the person who sees its customers.
CREATE TABLE managers (
    manager VARCHAR,
    country VARCHAR
);
INSERT INTO managers VALUES
    ('nora@example.invalid', 'NO'),
    ('sven@example.invalid', 'SE'),
    ('freja@example.invalid', 'DK'),
    ('eero@example.invalid', 'FI');
