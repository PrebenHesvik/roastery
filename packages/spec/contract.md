# Contract A: the data of roastery-data

This file says what every table of `roastery-data` is: what one row means, which columns it
has, where its rows come from, and which lessons depend on it. Every later step builds
against it: the app (6.3) must be able to write each table the app makes, the simulator
(6.4, 6.5) is tuned until the claims pass, and data-docs (6.6) reads the tables by name,
grain and key.

The source of truth is code: `src/roastery_spec/contract.py`. The table blocks below are
rendered from it. Only the prose around them is written by hand. A test renders the blocks
again and fails, naming the table and the line, if this file and the code disagree.

## How to read a table

Each table has one block:

- **grain**: what one row is. For a table that exists today it is the header sentence of
  data-docs' dataset file, word for word.
- **key**: the columns that make a row unique. Two tables have no key on purpose:
  `payments` (PAY-1 came twice) and `raw_customers` (text as the export gave it).
- **system**: where the rows are born (the list is below). "derived" means computed from
  other tables.
- **tiny**: how the small extract cuts the table out of the world (below).
- **lives in**: where a tiny table's rows can be found again (below).
- **extracts**: which of `tiny`, `month` and `full` hold the table.
- **since**: `baseline` for the 38 tables data-docs reads today; `1.0` for the new ones.
- **columns**: the name and the type of each, in order. A table has at most six.
- **What it is**: the table in the world, in a sentence or two.
- **Lessons**: the pages whose argument depends on the table, and what they need from it.
  A table can pass every number and still break a page (D15), so this list is part of the
  contract. A lesson whose page is not written yet is marked `later: ...`.

## The three extracts

| extract | what it holds |
|---|---|
| `tiny` | the teaching week, 5 to 9 October 2026: the hand-written rows every page shows |
| `month` | October 2026, every system, with the nightly landings |
| `full` | January 2024 to the teaching week |

`tiny` is frozen: its tables, rows and columns stay as they are. It is not a world of its
own but a cut of the bigger one. Each table is cut one of four ways:

- **by key**: the named customers and everything keyed to them;
- **by named list**: four visitors, five csv lines, the listed club members, two nights;
- **by day window**: `fx_rates` 2 to 7 October, `stock_daily` 5 to 9 October;
- **whole reference**: `products`, `prices` and the other small lookup tables.

"none" means tiny does not hold the table.

**Lives in** says where the extracts test finds a tiny table's rows:

- `same(month)` or `same(full)`: the rows are there as they are, compared on tiny's columns;
- `derived(...)`: tiny computes the table from others, and the test does the same;
- `landing`: raw text from a file; only the pages clean it.

Two examples. `customer_months` spans November 2025 to October 2026, longer than `month`,
so it is derived from `full`. `customer_changes` starts with the first customer in 2024, so
it lives in `full`; its `seq` is renumbered in tiny, so it is compared without `seq`, and
its order by `seq` must be the same.

## The systems

| system | what it is |
|---|---|
| app database | the shop app's own tables, and the nightly copies it keeps |
| status feed | the order status messages, each with the moment it was loaded |
| payment provider | the messages the provider sends, redeliveries included |
| web tracking | what visitors did on the web shop |
| csv export | the shop's export, every column text, with its faults |
| till | the new till in the Bergen shop, from 6 October 2026 |
| outside feed | bank rates, weather, the door counter, the old till |
| owner's sheet | numbers the owner sets by hand, never simulated |
| derived | computed from other tables |

The app makes most rows. The outside feeds, the till's files and the provider's
redelivery are written by the simulator as systems of their own.

## The teaching week rule

The rows of tiers 1 and 2 are hand-written, and every page's sentences rest on them. The
simulator plays them as a scripted week inside the three years, with their own ids, and
the tests prove that `tiny` still holds exactly those rows. The faults the pages teach
(the double line, the missing quantity, the late event) are planted by the export writer
after a correct app, and listed in a defect log.

## The decisions it rests on

- **D4**: the answers stay the same. The existing tests pass unchanged on the simulator's
  output.
- **D7**: customers get an `account_kind`, consumer or business (named so by S17, so it
  cannot meet `products.kind` in a join). The large `order_values` orders are business.
- **D8**: `subscribers` holds the subscriptions of everyone outside the week's cast.
- **D11**: subscription bags ship in their own table, not as orders.
- **D12**: the old till left day totals only; the new till starts on 6 October 2026.
- **D13**: tiny's columns are frozen. New columns live in `month` and `full` only.
- **D15**: `daily_sales` is the web shop's consumer sales. Counter sales stay out, or the
  correlation page's lesson would be false.

## How to change it

1. Edit `src/roastery_spec/contract.py`.
2. Run `uv run python -m roastery_spec.render` to rewrite the blocks here.
3. Run the tests: `uv run python -m pytest packages/spec`.

The hand-written prose is edited here directly. Once `roastery-data 1.0` is released, a
change to any table is a new data version, with an entry in `docs/data-changelog.md`.

## Tier 1: the shop

The four tables every page uses, and the lines with their order's day.

<!-- tables:tier-1:start -->

### `customers`

- **grain:** One row per customer, as the shop holds them today.
- **key:** `customer_id`
- **system:** app database
- **tiny:** by key: the six named customers, C-01 to C-06
- **lives in:** same(month)
- **extracts:** tiny, month, full
- **since:** baseline

| column | type |
|---|---|
| customer_id | VARCHAR |
| name | VARCHAR |
| country | VARCHAR |
| postal_code | VARCHAR |
| joined | DATE |
| account_kind | VARCHAR, month and full only (1.0) |

**What it is.** The shop's customers as the app holds them at the end of the teaching week. C-07 was erased on 9 October, so no row names them; no customer with an order between 1 October 2024 and 30 September 2026 is erased (S15). From 1.0, month and full add `account_kind`: consumer or business (D7, S17).

**Lessons**

- `sql/joins`: C-06 has not ordered, the row an anti-join finds; O-107 names C-07.
- `sql/nulls`: C-05 has no country and no postal code: the null in a dimension.
- `sql/ranking`: C-03 and C-04 joined the same day: a tie for every ranking.
- `sql/text`: C-02's Å is two bytes; Oslo's postal code starts with a zero.
- `modeling/survivorship`: C-01's move on 9 October, which other systems missed.

### `products`

- **grain:** One row per product the shop lists.
- **key:** `product_id`
- **system:** app database
- **tiny:** whole reference
- **lives in:** same(month)
- **extracts:** tiny, month, full
- **since:** baseline

| column | type |
|---|---|
| product_id | VARCHAR |
| product_name | VARCHAR |
| kind | VARCHAR |
| category_id | VARCHAR |
| weight_g | INTEGER |

**What it is.** The five products the shop lists: three coffees and two pieces of equipment.

**Lessons**

- `sql/joins`: No P-99, though L-09 names it; P-12 is never sold.
- `sql/group-by`: `kind` is the column to group by; categories hold the full tree.
- `modeling/nulls-and-types`: `weight_g` is null for equipment: "does not apply".
- `modeling/supertypes-and-subtypes`: `kind` splits beans from equipment.

### `orders`

- **grain:** One row per order, dated on the customer's clock.
- **key:** `order_id`
- **system:** app database
- **tiny:** by key: the orders of the cast, O-101 to O-108
- **lives in:** same(month)
- **extracts:** tiny, month, full
- **since:** baseline

| column | type |
|---|---|
| order_id | VARCHAR |
| customer_id | VARCHAR |
| order_date | DATE |
| channel | VARCHAR |

**What it is.** Every order placed in the app, on the web or at the counter (channel `shop`), dated on the customer's own clock. A return is a credit order at the counter, with a negative line for the product returned (S14).

**Lessons**

- `sql/joins`: O-106 has no lines; O-107 names C-07, who is erased: the orphan.
- `polars/time-zones-and-durations`: O-106 is 7 October on Aino's Helsinki clock, still 6 October in Bergen.
- `modeling/slowly-changing-dimensions`: C-01 ordered before her move and after it (O-108): type 2 has both sides.

### `order_lines`

- **grain:** One row per order line: an order, a product, a quantity, in NOK.
- **key:** `line_id`
- **system:** app database
- **tiny:** by key: the lines of the cast
- **lives in:** same(month)
- **extracts:** tiny, month, full
- **since:** baseline

| column | type |
|---|---|
| line_id | VARCHAR |
| order_id | VARCHAR |
| product_id | VARCHAR |
| qty | INTEGER |
| unit_price | DECIMAL(7,2) |

**What it is.** What each order bought: a product, a quantity and the price paid, in kroner. The export writer plants L-04/L-05, L-07 and L-09 (plan 4.2).

**Lessons**

- `sql/duplicates`: L-04 and L-05 are one line twice; the payment and stock prove it.
- `sql/nulls`: L-07 has no qty: `sum` skips it, `count(*)` does not.
- `sql/joins`: L-09 names P-99, which products lacks: an inner join loses it.
- `modeling/nulls-and-types`: L-12 is a free sample at 0.00: a zero, not a null.

### `dated_lines`

- **grain:** One row per order line, with its order's day. The pages call it order_lines.dated.
- **key:** `line_id`
- **system:** derived: order_lines joined to orders
- **tiny:** by key: the lines of the cast
- **lives in:** derived(order_lines joined to orders on order_id, with the order's day)
- **extracts:** tiny
- **since:** baseline

| column | type |
|---|---|
| line_id | VARCHAR |
| product_id | VARCHAR |
| order_date | DATE |
| qty | INTEGER |
| unit_price | DECIMAL(7,2) |

**What it is.** The order lines with their order's day beside them, written out so the table stands alone.

**Lessons**

- `sql/running-totals`: A running total by day needs each line's day.
- `sql/asof-and-range-joins`: Each line's day finds the price that held on it.
- `sql/pivot-and-unpivot`: Sales by product and day, from one narrow table.

<!-- tables:tier-1:end -->

## Tier 2: the tailor-made tables

The files, the web, the till and the rest of the teaching week. Each row has a job.

<!-- tables:tier-2:start -->

### `prices`

- **grain:** One row per product and period a list price held.
- **key:** `product_id, valid_from`
- **system:** app database
- **tiny:** whole reference
- **lives in:** same(month)
- **extracts:** tiny, month, full
- **since:** baseline

| column | type |
|---|---|
| product_id | VARCHAR |
| price | DECIMAL(7,2) |
| valid_from | DATE |
| valid_to | DATE |

**What it is.** The list price of each product and the days it held. `valid_to` is the first day it no longer holds (half-open); null means it still holds.

**Lessons**

- `sql/asof-and-range-joins`: P-21 has no price on 6 October, the day of L-06: a range join finds nothing.
- `sql/join-fan-out`: P-11 changes on 5 October, the day of L-03: with BETWEEN, L-03 counts twice.
- `modeling/slowly-changing-dimensions`: A type 2 table the reader has queried.
- `patterns/cache-aside`: A price read often and changed rarely.

### `fx_rates`

- **grain:** One row per currency and banking day, 2 to 7 October 2026: kroner for one unit.
- **key:** `currency, rate_date`
- **system:** outside feed: bank rates
- **tiny:** by day window: 2 to 7 October 2026
- **lives in:** same(month)
- **extracts:** tiny, month, full
- **since:** baseline

| column | type |
|---|---|
| currency | VARCHAR |
| rate_date | DATE |
| nok_per_unit | DECIMAL(8,4) |

**What it is.** What one Swedish krone, Danish krone or euro cost in kroner, on banking days.

**Lessons**

- `sql/asof-and-range-joins`: No weekend rows; DKK has only Friday's rate, so later payments take it as of.
- `polars/time-zones-and-durations`: The missing days: forward fill or interpolate.
- `modeling/facts-from-several-systems`: NOK is not in it: kroner payments need `coalesce(rate, 1)`.

### `payments`

- **grain:** One row per message from the payment provider (no key: PAY-1 came twice).
- **key:** `none`
- **system:** payment provider
- **tiny:** by key: the payments of the cast
- **lives in:** same(month)
- **extracts:** tiny, month, full
- **since:** baseline

| column | type |
|---|---|
| payment_id | VARCHAR |
| order_id | VARCHAR |
| currency | VARCHAR |
| amount | DECIMAL(9,2) |
| paid_on | DATE |

**What it is.** Every message the payment provider sent, in the currency the customer paid. The provider redelivered PAY-1; O-107 was never paid. A refund is a negative payment (S14); an order on invoice is paid when its invoice is (S13).

**Lessons**

- `sql/duplicates`: PAY-1 came twice: the provider redelivered it.
- `patterns/idempotency`: The same message handled twice must count once.
- `modeling/facts-from-several-systems`: Converted as of, each payment is its order total: PAY-5 says L-07 was one.
- `pipeline/reruns`: A rerun of the load must not add PAY-1 again.

### `order_events`

- **grain:** One row per status change of an order, stamped in UTC, with the moment it was loaded.
- **key:** `event_id`
- **system:** status feed
- **tiny:** by key: the events of the cast
- **lives in:** same(month)
- **extracts:** tiny, month, full
- **since:** baseline

| column | type |
|---|---|
| event_id | VARCHAR |
| order_id | VARCHAR |
| status | VARCHAR |
| event_at | TIMESTAMP |
| loaded_at | TIMESTAMP |

**What it is.** The app's status changes (placed, paid or invoiced, shipped, delivered, cancelled), sent through its outbox. An invoiced order ships before it is paid (S13). The export writer drops the events of O-103, O-105 and O-107.

**Lessons**

- `pipeline/late-and-out-of-order`: E-08 happened on 8 October and loaded on 10 October; E-10 loaded before E-09.
- `modeling/accumulating-snapshots`: O-101 goes through every stage.
- `polars/time-zones-and-durations`: E-11 at 21:30 UTC is 7 October in Helsinki, the date orders holds for O-106.
- `pipeline/load-checks`: No events for O-103, O-105 and O-107: a fact not complete.
- `patterns/state-machine`: The statuses an order may pass through, in order.

### `stock_daily`

- **grain:** One row per product, working day and count, P-10 and P-20, 5 to 9 October: the bags or boxes on the shelf at close; counted_at is UTC (16:00 is 18:00 at close in Bergen, summer time).
- **key:** `product_id, stock_date, counted_at`
- **system:** app database
- **tiny:** by day window: 5 to 9 October 2026, P-10 and P-20 only (D13)
- **lives in:** same(month)
- **extracts:** tiny, month, full
- **since:** baseline

| column | type |
|---|---|
| product_id | VARCHAR |
| stock_date | DATE |
| on_hand | INTEGER |
| counted_at | TIMESTAMP |

**What it is.** The shop's stock at close of each working day, from the app's stock service (S10), sent a whole day at a time. on_hand is the day's closing balance, counting every sale of that day; counted_at stamps the count job, not the last sale: O-108 at 19:30 UTC is in 9 October's 59, counted at 16:00 UTC (S19). The export writer sends 7 October twice: the 26 is its fault (in the defect log), the recount of 36 is the true count.

**Lessons**

- `modeling/grain`: A periodic snapshot: the week's stock is Friday's, not a sum.
- `sql/lag-and-lead`: P-10 falls by 3 on 6 October where the lines say 6.
- `pipeline/partition-overwrite`: 7 October came twice; the latest count wins.

### `latest_stock`

- **grain:** One row per product and working day, the latest count of that day. The pages call it stock_daily.latest.
- **key:** `product_id, stock_date`
- **system:** derived: stock_daily, the latest count of each day
- **tiny:** by day window: 5 to 9 October 2026, P-10 and P-20 only
- **lives in:** derived(stock_daily, the row with the latest counted_at per product and day)
- **extracts:** tiny
- **since:** baseline

| column | type |
|---|---|
| product_id | VARCHAR |
| stock_date | DATE |
| on_hand | INTEGER |

**What it is.** The stock at close with one count per product and day: the latest one.

**Lessons**

- `sql/lag-and-lead`: The change from day to day, on one count a day.
- `polars/pivot-and-unpivot`: P-10 and P-20 as columns, one row per day.

### `customer_extracts`

- **grain:** One row per customer in each of two nightly copies, 8 and 9 October, of the shop's customer table.
- **key:** `extract_date, customer_id`
- **system:** app database: nightly copies of customers
- **tiny:** by named list: the nights of 8 and 9 October
- **lives in:** same(month)
- **extracts:** tiny, month, full
- **since:** baseline

| column | type |
|---|---|
| extract_date | DATE |
| customer_id | VARCHAR |
| country | VARCHAR |
| postal_code | VARCHAR |

**What it is.** The app's customer table as copied each night. The second night is customers exactly, in the columns they share.

**Lessons**

- `pipeline/change-detection`: One row changed (C-01), one is new (C-06), one is gone (C-07).
- `pipeline/change-detection`: C-05's nulls must not count as a change.
- `pipeline/deletes`: C-07 is gone the second night: erased, the order kept.
- `pipeline/full-reload`: Each night replaces the whole table.

### `customer_changes`

- **grain:** One row per change the app wrote to its customers table; seq numbers the changes in the order the app wrote them.
- **key:** `seq`
- **system:** app database: the change log of customers
- **tiny:** by key: the cast's changes, seq renumbered from 1
- **lives in:** same(full)
- **extracts:** tiny, month, full
- **since:** baseline

| column | type |
|---|---|
| seq | INTEGER |
| op | VARCHAR |
| customer_id | VARCHAR |
| country | VARCHAR |
| postal_code | VARCHAR |
| changed_at | TIMESTAMP |

**What it is.** Every insert, update and delete on the app's customers, from the first customer on. The extracts test compares it without `seq`, and checks the order by `seq`.

**Lessons**

- `pipeline/change-log`: C-07's delete is a tombstone that carries the key only.
- `pipeline/merge`: C-01 moves twice in one batch (a typo, fixed three minutes on).
- `pipeline/replay`: Folded to midnight before 9 October it is the copy of 8 October.

### `line_stamps`

- **grain:** One row per row of the app's order lines table, deleted rows kept, with the moment it last changed.
- **key:** `line_id`
- **system:** app database: order lines with their stamps
- **tiny:** by key: the lines of the cast, L-10 included
- **lives in:** same(month)
- **extracts:** tiny, month, full
- **since:** baseline

| column | type |
|---|---|
| line_id | VARCHAR |
| order_id | VARCHAR |
| qty | INTEGER |
| is_deleted | BOOLEAN |
| updated_at | TIMESTAMP |

**What it is.** The app's order lines as its own bookkeeping holds them: soft-deleted rows stay, and each row has the moment it last changed.

**Lessons**

- `pipeline/deletes`: L-10 was O-106's line, marked deleted when Aino cancelled.
- `pipeline/reading-a-live-source`: `updated_at` is the high-water mark of a load.
- `modeling/model-tests`: Without the deleted row it is order_lines.

### `raw_customers`

- **grain:** One row per customer who has ordered (C-01 to C-05) in the shop's csv export, as of after C-01's move on 9 October, every column text (no key: the text is as the export gave it); C-06 has no order and C-07 is erased, so neither is in it.
- **key:** `none`
- **system:** csv export
- **tiny:** by key: C-01 to C-05
- **lives in:** landing
- **extracts:** tiny, month, full
- **since:** baseline

| column | type |
|---|---|
| customer_id | VARCHAR |
| name | VARCHAR |
| country | VARCHAR |
| postal_code | VARCHAR |
| joined | VARCHAR |
| email | VARCHAR |

**What it is.** The customers in the shop's csv export, as text with its stray spaces, cases and two date formats. Cleaned, it is C-01 to C-05 of customers exactly.

**Lessons**

- `sql/text`: DuckDB's trim leaves C-03's tab and takes C-04's no-break space.
- `sql/dates`: `joined` comes in two formats.
- `modeling/nulls-and-types`: Postal code 150 must be padded to 0150, not cast.
- `pipeline/reading-files`: Cleaned, the rows end on customers the reader knows.

### `raw_lines`

- **grain:** Five lines (L-01, L-02, L-03, L-06, L-07) of the shop's csv export, every column text.
- **key:** `line_id`
- **system:** csv export
- **tiny:** by named list: L-01, L-02, L-03, L-06, L-07
- **lives in:** landing
- **extracts:** tiny, month, full
- **since:** baseline

| column | type |
|---|---|
| line_id | VARCHAR |
| order_id | VARCHAR |
| product_id | VARCHAR |
| qty | VARCHAR |
| unit_price | VARCHAR |

**What it is.** Order lines in the shop's csv export, every column text. Cleaned, they are those five rows of order_lines exactly.

**Lessons**

- `sql/types-and-cast`: '129,00' fails a cast; 'n/a' is the null really missing.
- `pipeline/landing-files`: The text as the export gave it, kept before cleaning.
- `polars/selectors`: Every column is text until a selector casts it.

### `web_events`

- **grain:** One row per thing one of four visitors did on the web shop, stamped in UTC.
- **key:** `event_id`
- **system:** web tracking
- **tiny:** by named list: the visitors V-1 to V-4
- **lives in:** same(month)
- **extracts:** tiny, month, full
- **since:** baseline

| column | type |
|---|---|
| event_id | VARCHAR |
| visitor_id | VARCHAR |
| customer_id | VARCHAR |
| event | VARCHAR |
| event_at | TIMESTAMP |
| visit_id | INTEGER, month and full only (1.0) |

**What it is.** What visitors did on the web shop: a view of the product page, a cart, a checkout. A checkout is followed within two minutes by a placed event. From 1.0, month and full add `visit_id`: the web_visits row the event belongs to (S18).

**Lessons**

- `sql/lag-and-lead`: V-2 comes back after 45 minutes: a 30-minute gap rule.
- `sql/counting-and-conditional-sums`: The funnel: four view, four reach the cart, three check out.
- `sql/nulls`: V-2 never logs in: `customer_id` is null.
- `pipeline/streaming`: Events arrive one at a time, stamped in UTC.

### `subscriptions`

- **grain:** One row per subscription: a customer, a product every month, from a first day to the day it stopped.
- **key:** `subscription_id`
- **system:** app database
- **tiny:** by key: the subscriptions of the cast, S-1 to S-7
- **lives in:** same(month)
- **extracts:** tiny, month, full
- **since:** baseline

| column | type |
|---|---|
| subscription_id | VARCHAR |
| customer_id | VARCHAR |
| product_id | VARCHAR |
| started | DATE |
| ended | DATE |

**What it is.** Subscriptions: one bag a month, from a first day to the day it stopped (null while it runs). Tiny holds the cast's, full every customer's; subscribers is everyone's but the cast's (D8).

**Lessons**

- `sql/dates`: C-02 stopped and came back; C-04 has two that overlap.
- `sql/asof-and-range-joins`: Active on a day: a count of periods that hold.
- `modeling/measures`: Active subscriptions are semi-additive.
- `patterns/command`: Starting and stopping a subscription as commands.

### `categories`

- **grain:** One row per category; parent_id points one level up, sort_order is the shop's order.
- **key:** `category_id`
- **system:** app database
- **tiny:** whole reference
- **lives in:** same(month)
- **extracts:** tiny, month, full
- **since:** baseline

| column | type |
|---|---|
| category_id | VARCHAR |
| category_name | VARCHAR |
| parent_id | VARCHAR |
| sort_order | INTEGER |

**What it is.** The tree of product categories, as the shop shows it.

**Lessons**

- `modeling/dimension-design`: A ragged tree: the hand grinder three levels down, the kettle two.
- `dax/patterns`: `sort_order` is the one order of the tree, set in one place.

### `kinds`

- **grain:** One row per kind of product, so a budget by kind relates to products through it.
- **key:** `kind`
- **system:** app database
- **tiny:** whole reference
- **lives in:** same(month)
- **extracts:** tiny, month, full
- **since:** baseline

| column | type |
|---|---|
| kind | VARCHAR |
| kind_name | VARCHAR |

**What it is.** The two kinds of product, beans and equipment.

**Lessons**

- `modeling/conformed-dimensions`: Budget and sales meet on kind.
- `dax/relationships`: A budget by kind filters products through this table.

### `campaign_products`

- **grain:** One row per campaign and product in it.
- **key:** `campaign_id, product_id`
- **system:** app database
- **tiny:** whole reference
- **lives in:** same(month)
- **extracts:** tiny, month, full
- **since:** baseline

| column | type |
|---|---|
| campaign_id | VARCHAR |
| campaign_name | VARCHAR |
| product_id | VARCHAR |

**What it is.** Which products each campaign holds: many to many.

**Lessons**

- `sql/join-fan-out`: The hand grinder is in both: sales per campaign add to more than all sales.
- `modeling/normalization`: `campaign_name` repeats on every row of a campaign.
- `dax/relationships`: A bridge and its filter direction.

### `campaigns`

- **grain:** One row per campaign, with its discount and its days.
- **key:** `campaign_id`
- **system:** app database
- **tiny:** whole reference
- **lives in:** same(month)
- **extracts:** tiny, month, full
- **since:** baseline

| column | type |
|---|---|
| campaign_id | VARCHAR |
| campaign_name | VARCHAR |
| discount_pct | INTEGER |
| first_day | DATE |
| last_day | DATE |

**What it is.** The campaigns the shop ran: a discount on its products, on its days.

**Lessons**

- `modeling/multivalued-dimensions`: The dimension on the far side of the bridge.
- `modeling/ownership-and-change`: Who owns a campaign and its days.

### `product_codes`

- **grain:** One row per code the till knows, and the product it is.
- **key:** `ean`
- **system:** till
- **tiny:** whole reference
- **lives in:** same(month)
- **extracts:** tiny, month, full
- **since:** baseline

| column | type |
|---|---|
| ean | VARCHAR |
| product_id | VARCHAR |

**What it is.** The till's barcodes and the product each one is.

**Lessons**

- `modeling/conforming-codes`: Dark espresso has two codes: box and loose beans.
- `modeling/key-mapping`: One code the till knows has no product.

### `till_receipts`

- **grain:** One row per till receipt of a listed member, and the trial day's one receipt, sold_at in Bergen time.
- **key:** `receipt_id`
- **system:** till
- **tiny:** by named list: the listed members' receipts and R-5001
- **lives in:** same(month)
- **extracts:** tiny, month, full
- **since:** baseline

| column | type |
|---|---|
| receipt_id | VARCHAR |
| member_no | INTEGER |
| sold_at | TIMESTAMP |

**What it is.** The new till's receipts, in Bergen time. R-5001, rung on the trial day, is the only one in the teaching week before 7 October (D12).

**Lessons**

- `modeling/combining-sources`: R-5001 is O-104's kettle: matched by moment and product, not by customer.
- `modeling/key-mapping`: R-5002 names Mikkel's second member number.
- `modeling/time-in-a-model`: R-5004 names Hilde before she is listed.
- `pyspark/time-zones-and-durations`: sold_at is Bergen time; the app stamps UTC.

### `till_lines`

- **grain:** One row per line of those receipts.
- **key:** `receipt_id, line_no`
- **system:** till
- **tiny:** by named list: the lines of those receipts
- **lives in:** same(month)
- **extracts:** tiny, month, full
- **since:** baseline

| column | type |
|---|---|
| receipt_id | VARCHAR |
| line_no | INTEGER |
| ean | VARCHAR |
| grams | INTEGER |
| amount | DECIMAL(7,2) |

**What it is.** What each till receipt sold, by barcode; grams only for loose beans.

**Lessons**

- `modeling/facts-from-several-systems`: A second sales fact, with its own keys.
- `modeling/conforming-codes`: A line reaches a product only through its code.
- `patterns/parse-dont-validate`: A till line parsed once into a sale.

### `till_members`

- **grain:** One row per listed member in each nightly list of the shop's club: the first list holds every member, later ones those who joined.
- **key:** `member_no, listed_on`
- **system:** till
- **tiny:** by named list: the listed club members
- **lives in:** same(month)
- **extracts:** tiny, month, full
- **since:** baseline

| column | type |
|---|---|
| member_no | INTEGER |
| name | VARCHAR |
| email | VARCHAR |
| postal_code | VARCHAR |
| listed_on | DATE |

**What it is.** The till's club list, sent each night. The till was never told that Ingrid moved or that C-07 was erased.

**Lessons**

- `modeling/key-mapping`: Mikkel signed up twice; Sindre has no web account.
- `modeling/survivorship`: The till still has Ingrid at her old postal code.
- `pipeline/personal-data-and-access`: Erased in the shop, still listed in the till.

### `customer_months`

- **grain:** One row per month of C-01, November 2025 to October 2026: orders, spend in NOK and whether a subscription ran; spend_nok counts the orders' lines only, not the subscription's monthly charge (a month can show 0.00 with subscribed true).
- **key:** `customer_id, month`
- **system:** derived: orders, order_lines and subscriptions of C-01
- **tiny:** by key: C-01
- **lives in:** derived(full: per month, the orders and line spend of C-01, and whether S-1 ran)
- **extracts:** tiny
- **since:** baseline

| column | type |
|---|---|
| customer_id | VARCHAR |
| month | DATE |
| orders | INTEGER |
| spend_nok | DECIMAL(7,2) |
| subscribed | BOOLEAN |

**What it is.** C-01's year, month by month: how many orders, what they spent and whether her subscription ran. Her year is scripted at the old prices (plan 4.2).

**Lessons**

- `modeling/mini-dimensions`: C-01's months cross the band edges often.

### `bean_details`

- **grain:** One row per product of the kind beans, with what only beans have.
- **key:** `product_id`
- **system:** app database
- **tiny:** whole reference
- **lives in:** same(month)
- **extracts:** tiny, month, full
- **since:** baseline

| column | type |
|---|---|
| product_id | VARCHAR |
| origin | VARCHAR |
| roast | VARCHAR |
| process | VARCHAR |

**What it is.** What only coffee has: origin, roast and process.

**Lessons**

- `modeling/supertypes-and-subtypes`: The subtype table of beans.

### `equipment_details`

- **grain:** One row per product of the kind equipment, with what only equipment has.
- **key:** `product_id`
- **system:** app database
- **tiny:** whole reference
- **lives in:** same(month)
- **extracts:** tiny, month, full
- **since:** baseline

| column | type |
|---|---|
| product_id | VARCHAR |
| warranty_months | INTEGER |
| material | VARCHAR |

**What it is.** What only equipment has: a warranty and a material.

**Lessons**

- `modeling/supertypes-and-subtypes`: The subtype table of equipment.

### `managers`

- **grain:** One row per country and the person who sees its customers.
- **key:** `country`
- **system:** owner's sheet
- **tiny:** whole reference
- **lives in:** same(month)
- **extracts:** tiny, month, full
- **since:** baseline

| column | type |
|---|---|
| manager | VARCHAR |
| country | VARCHAR |

**What it is.** Who looks after the customers of each country.

**Lessons**

- `dax/security`: Row-level security: a manager sees one country.
- `modeling/nulls-and-types`: C-05 has no country, so no manager sees her.

<!-- tables:tier-2:end -->

## Tier 3: the volume

Made by a formula today; from 1.0 each is a cut of the simulated world (plan §4.1). They
live in `full` only, and the pages show their totals, never their rows.

<!-- tables:tier-3:start -->

### `daily_sales`

- **grain:** One row per day and product with a price that day, 1 October 2024 to 30 September 2026.
- **key:** `sale_date, product_id`
- **system:** derived: the web shop's consumer order lines
- **tiny:** none
- **lives in:** not in tiny
- **extracts:** full
- **since:** baseline

| column | type |
|---|---|
| sale_date | DATE |
| product_id | VARCHAR |
| qty | INTEGER |
| amount | DECIMAL(7,2) |

**What it is.** Per day and product, the web shop's order lines to private customers, at list price. Counter sales and business accounts are outside it (D7, D15).

**Lessons**

- `stats/correlation`: Walk-ins do not cause these sales: the web shop only, so the link is a confounder (D15).
- `stats/comparing-periods`: Each December about double; the second year higher.
- `dax/time-intelligence`: Two full years for a year over year.
- `dax/weeks-and-calendars`: Friday sells about three times Sunday.

### `order_values`

- **grain:** One order of 2026 (600, 1 January to 30 September), web or shop.
- **key:** `order_no`
- **system:** derived: a scripted lesson set of app orders
- **tiny:** none
- **lives in:** not in tiny
- **extracts:** full
- **since:** baseline

| column | type |
|---|---|
| order_no | INTEGER |
| order_date | DATE |
| channel | VARCHAR |
| amount | DECIMAL(7,2) |
| status | VARCHAR |

**What it is.** A lesson set: 600 scripted orders of 2026, consumer and business, played inside the wider trade. The large orders (10 bags, the café's 48) are business (D7). amount is the sum of the order's lines. status is paid (a payment by 30 September 2026), unpaid (an invoice still open that day: the order went on invoice, S13) or refund (order 300, a return: a credit order at the counter with a negative line and a negative payment, S14).

**Lessons**

- `stats/mean-and-median`: A skewed basket: the mean above the median.
- `stats/outliers`: One café order of 48 bags is the one big value.
- `stats/samples-and-bias`: Refunds and unpaid orders change the sample.

### `budget`

- **grain:** One row per month and product kind, October 2024 to December 2026 (set ahead, as budgets are).
- **key:** `month, kind`
- **system:** owner's sheet
- **tiny:** none
- **lives in:** not in tiny
- **extracts:** full
- **since:** baseline

| column | type |
|---|---|
| month | DATE |
| kind | VARCHAR |
| budget_nok | INTEGER |

**What it is.** The owner's target for the web shop's consumer sales, per month and kind, in whole kroner: the same scope as daily_sales (D15, S16). Hand-set like prices; never simulated.

**Lessons**

- `dax/relationships`: Budget by month and kind; actuals by day and product.
- `dax/patterns`: Actual against budget: some months beat it, some miss.
- `dax/patterns`: Like with like: the budget and daily_sales are both web consumer sales (S16).

### `checkout_test`

- **grain:** One visitor of the product page in a 40-day test of two versions, A and B.
- **key:** `visitor_no`
- **system:** derived: web tracking during a 40-day test
- **tiny:** none
- **lives in:** not in tiny
- **extracts:** full
- **since:** baseline

| column | type |
|---|---|
| visitor_no | INTEGER |
| test_day | INTEGER |
| variant | VARCHAR |
| converted | BOOLEAN |

**What it is.** Every visitor of the product page during a scripted 40-day A/B test: the web_visits with a variant. `variant` sits on the visit (S18); test_day counts from the test's first day, at the visitor's first visit in it; converted means one of the visitor's test visits reached the checkout, not an order placed.

**Lessons**

- `stats/ab-tests`: B converts better, about 2.7 standard errors apart.
- `stats/ab-tests`: After two days the gap is a fluke; A against A is equal.
- `stats/confidence-intervals`: An interval for each variant.

### `subscribers`

- **grain:** One subscription (240), started 2024 to September 2026 and counted on 30 September 2026.
- **key:** `subscription_id`
- **system:** derived: the subscriptions of everyone outside the cast
- **tiny:** none
- **lives in:** not in tiny
- **extracts:** full
- **since:** baseline

| column | type |
|---|---|
| subscription_id | INTEGER |
| product_id | VARCHAR |
| started | DATE |
| ended | DATE |

**What it is.** The subscriptions of every customer outside the teaching week's cast, as they stood on 30 September 2026 (D8).

**Lessons**

- `stats/cohorts`: Retention by start month: later cohorts stay longer.
- `dax/semi-additive`: Active subscribers on a day do not add over days.

### `visits`

- **grain:** One visit to the web shop (3,600), 1 October 2024 to 30 September 2026, with the furthest step it reached.
- **key:** `visit_id`
- **system:** derived: web tracking, the attributed visits
- **tiny:** none
- **lives in:** not in tiny
- **extracts:** full
- **since:** baseline

| column | type |
|---|---|
| visit_id | INTEGER |
| visit_date | DATE |
| country | VARCHAR |
| source | VARCHAR |
| reached | INTEGER |

**What it is.** The attributed panel: the web_visits with a referrer (newsletter, ads), which this table calls source. Direct traffic has no referrer and is outside it. reached is the furthest step of the visit's events: 1 a view, 2 a cart, 3 a checkout, 4 an order the visit's customer placed within two minutes of its checkout (S18).

**Lessons**

- `stats/funnels`: The furthest step each visit reached, one to four.
- `stats/simpsons-paradox`: The sources reverse between the parts and the total.
- `stats/small-numbers`: A Finnish cell of four newsletter visits.

### `deliveries`

- **grain:** One web order of order_values, shipped the day after it was placed.
- **key:** `order_no`
- **system:** derived: shipments of the lesson set's web orders (S8)
- **tiny:** none
- **lives in:** not in tiny
- **extracts:** full
- **since:** baseline

| column | type |
|---|---|
| order_no | INTEGER |
| country | VARCHAR |
| shipped_on | DATE |
| days | INTEGER |

**What it is.** The parcels of order_values' 480 web orders: days from shipped to delivered. From 1.0 it is derived from shipments (S8).

**Lessons**

- `stats/spread`: Norway and Finland: the same mean, another spread.
- `stats/percentiles`: Order 297, lost in Sweden for 21 days: the long tail.

### `shop_days`

- **grain:** One day of the Bergen shop, 1 October 2024 to 30 September 2026; Sundays are closed.
- **key:** `shop_date`
- **system:** derived: door counter, weather and old till
- **tiny:** none
- **lives in:** not in tiny
- **extracts:** full
- **since:** baseline

| column | type |
|---|---|
| shop_date | DATE |
| rain_mm | INTEGER |
| walk_ins | INTEGER |
| receipts | INTEGER |

**What it is.** Three outside systems side by side: the door counter (walk-ins), a weather feed (rain) and the old till's day totals (receipts). From 1.0 it is their join (D12).

**Lessons**

- `stats/correlation`: Rain and walk-ins move against each other.
- `stats/correlation`: Walk-ins against bags sold: a confounder, not a cause.

<!-- tables:tier-3:end -->

## New in 1.0 (editable until roastery-data 1.0)

The signals later lessons need. None is in `tiny`. Three more changes come with them:

- `customers` gets the column `account_kind` (consumer or business) in `month` and `full`;
  it is shown in the `customers` block above (D7, S17).
- `web_events` gets the column `visit_id` in `month` and `full`: the `web_visits` row each
  event belongs to (S18). It is shown in the `web_events` block above.
- a scripted drop: in one week, Finland's orders fall to below half the mean of the four
  weeks around it. No table names it: an alert must find it in the orders. Its day and
  size are in the release's answer key (`scripted_events`, beside the defect log) (S11).

<!-- tables:new:start -->

### `subscription_events`

- **grain:** One row per skip, pause, resume or cancel of a subscription, with a reason.
- **key:** `event_id`
- **system:** app database
- **tiny:** none
- **lives in:** not in tiny
- **extracts:** month, full
- **since:** 1.0

| column | type |
|---|---|
| event_id | VARCHAR |
| subscription_id | VARCHAR |
| event_type | VARCHAR |
| reason | VARCHAR |
| event_at | TIMESTAMP |

**What it is.** What a subscriber did to a subscription, and why.

**Lessons**

- `patterns/command`: A skip or a cancel as a command, with its reason.
- `later: MRR and churn`: Churn with a cause.

### `subscription_shipments`

- **grain:** One row per bag shipped to a subscriber.
- **key:** `shipment_id`
- **system:** app database
- **tiny:** none
- **lives in:** not in tiny
- **extracts:** month, full
- **since:** 1.0

| column | type |
|---|---|
| shipment_id | VARCHAR |
| subscription_id | VARCHAR |
| product_id | VARCHAR |
| shipped_on | DATE |
| qty | INTEGER |

**What it is.** The monthly bags, as their own table, not as orders: orders rows would break tiny's eight orders and customer_months (D11).

**Lessons**

- `later: MRR and stock`: What each subscription shipped, month by month.

### `stock_movements`

- **grain:** One row per stock movement: roasted, sold, shipped, written off or counted.
- **key:** `movement_id`
- **system:** app database
- **tiny:** none
- **lives in:** not in tiny
- **extracts:** month, full
- **since:** 1.0

| column | type |
|---|---|
| movement_id | VARCHAR |
| product_id | VARCHAR |
| moved_at | TIMESTAMP |
| reason | VARCHAR |
| qty | INTEGER |

**What it is.** Every change to the stock, signed: in is positive, out is negative. At close on 5 to 9 October the balance is latest_stock for P-10 and P-20.

**Lessons**

- `later: stock flow`: Stock as the sum of its movements.

### `green_purchases`

- **grain:** One row per purchase of green coffee, by the kilo.
- **key:** `purchase_id`
- **system:** app database
- **tiny:** none
- **lives in:** not in tiny
- **extracts:** month, full
- **since:** 1.0

| column | type |
|---|---|
| purchase_id | VARCHAR |
| bought_on | DATE |
| origin | VARCHAR |
| kg | DECIMAL(7,2) |
| nok_per_kg | DECIMAL(7,2) |

**What it is.** The unroasted coffee the roaster bought: at least the kilos it roasted.

**Lessons**

- `later: purchase planning`: Kilos bought against kilos roasted.

### `product_costs`

- **grain:** One row per product and period a cost held.
- **key:** `product_id, valid_from`
- **system:** app database
- **tiny:** none
- **lives in:** not in tiny
- **extracts:** month, full
- **since:** 1.0

| column | type |
|---|---|
| product_id | VARCHAR |
| valid_from | DATE |
| valid_to | DATE |
| green_nok | DECIMAL(7,2) |
| packaging_nok | DECIMAL(7,2) |
| roasting_nok | DECIMAL(7,2) |

**What it is.** What a product cost to make, per period: green coffee, bag and roasting. Periods are half-open, like prices.

**Lessons**

- `later: margin`: Cost below list price in every price period.

### `shipments`

- **grain:** One row per parcel, with the day it was promised and the day it arrived.
- **key:** `shipment_id`
- **system:** app database
- **tiny:** none
- **lives in:** not in tiny
- **extracts:** month, full
- **since:** 1.0

| column | type |
|---|---|
| shipment_id | VARCHAR |
| order_id | VARCHAR |
| shipped_on | DATE |
| promised_by | DATE |
| delivered_on | DATE |

**What it is.** One parcel of a web order. deliveries is derived from it for order_values' web orders, through lesson_ids: days = delivered_on minus shipped_on (S8, S9).

**Lessons**

- `stats/percentiles`: Late delivery as a fact: order 297 takes 21 days.

### `pricing_rules`

- **grain:** One row per pricing rule: the subscriber discount or a campaign percentage.
- **key:** `rule_id`
- **system:** app database
- **tiny:** none
- **lives in:** not in tiny
- **extracts:** month, full
- **since:** 1.0

| column | type |
|---|---|
| rule_id | VARCHAR |
| rule_kind | VARCHAR |
| percent | INTEGER |
| valid_from | DATE |
| valid_to | DATE |

**What it is.** The discounts the app applies, each on its days. Each campaign's discount is one rule; at most one subscriber rule holds on a day.

**Lessons**

- `patterns/strategy`: A pricing rule chosen by its kind (closes gap G3).
- `patterns/registries-and-plugins`: The rules the app knows, in one place.

### `weather_days`

- **grain:** One row per day of the Bergen shop, with the rain that fell.
- **key:** `shop_date`
- **system:** outside feed: weather
- **tiny:** none
- **lives in:** not in tiny
- **extracts:** month, full
- **since:** 1.0

| column | type |
|---|---|
| shop_date | DATE |
| rain_mm | INTEGER |

**What it is.** The weather feed's rain in Bergen, a day at a time.

**Lessons**

- `stats/correlation`: The rain in shop_days comes from here.

### `door_counts`

- **grain:** One row per day of the Bergen shop, with the people who came in.
- **key:** `shop_date`
- **system:** outside feed: door counter
- **tiny:** none
- **lives in:** not in tiny
- **extracts:** month, full
- **since:** 1.0

| column | type |
|---|---|
| shop_date | DATE |
| walk_ins | INTEGER |

**What it is.** The door counter's walk-ins, a day at a time.

**Lessons**

- `stats/correlation`: The walk-ins in shop_days come from here.

### `till_day_totals`

- **grain:** One row per day of the Bergen shop, with the receipts the old till rang.
- **key:** `shop_date`
- **system:** outside feed: old till
- **tiny:** none
- **lives in:** not in tiny
- **extracts:** month, full
- **since:** 1.0

| column | type |
|---|---|
| shop_date | DATE |
| receipts | INTEGER |

**What it is.** The old till's day totals: anonymous walk-in sales, counted only. What it sold is not in the data (D12).

**Lessons**

- `stats/correlation`: The receipts in shop_days come from here.

### `web_visits`

- **grain:** One row per visit to the web shop: a visitor's events, until more than 30 minutes pass without one, with where the visit came from and its test variant.
- **key:** `visit_id`
- **system:** web tracking
- **tiny:** none
- **lives in:** not in tiny
- **extracts:** month, full
- **since:** 1.0

| column | type |
|---|---|
| visit_id | INTEGER |
| visitor_id | VARCHAR |
| visit_date | DATE |
| country | VARCHAR |
| referrer | VARCHAR |
| variant | VARCHAR |

**What it is.** Every visit, direct traffic included. visit_date is the day of its first event (UTC). referrer is newsletter or ads, null for a direct visit; it is not called source, which D13 keeps for a row's provenance. variant is A or B for a product page visit during the 40-day test, null outside it. web_events.visit_id names the visit of each event; visits and checkout_test are derived from it (S18).

**Lessons**

- `sql/lag-and-lead`: A visit is the 30-minute gap rule, written down by the tracker.
- `stats/funnels`: visits' furthest step comes from the visit's events.
- `stats/simpsons-paradox`: The referrer splits the panel into its sources.
- `stats/ab-tests`: The variant sits on the visit; direct and test visits alike.

### `lesson_ids`

- **grain:** One row per row of a tier 3 lesson set (order_values, subscribers), with the shop's own id it stands for.
- **key:** `lesson_set, row_no`
- **system:** derived: the lesson sets of tier 3 and the shop ids they stand for
- **tiny:** none
- **lives in:** not in tiny
- **extracts:** month, full
- **since:** 1.0

| column | type |
|---|---|
| lesson_set | VARCHAR |
| row_no | INTEGER |
| shop_id | VARCHAR |

**What it is.** Tier 3 keeps its integer row numbers (order 300 is the refund, 297 the lost parcel, 600 the café); this map ties each to the shop's text id, O-... or S-... (S9).

**Lessons**

- `later: modeling/keys-and-relationships`: A sample's row number against the shop's own id: two keys, one row.

<!-- tables:new:end -->
