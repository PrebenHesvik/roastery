"""Contract A: every table of roastery-data, as one source of truth.

`contract.md` is rendered from `TABLES` (`python -m roastery_spec.render`), and the tests check
the module against the baseline and against that file.

The fields of a `Table`:

- `name`: the table's name, as the files and the pages have it.
- `tier`: 1 (the four shop tables and the lines with their day), 2 (the tailor-made tables of
  the teaching week), 3 (the volume tables, made by a formula until the simulator writes them)
  or 'new' (the tables 1.0 adds, drafted in 6.1-contract.md section 5).
- `system`: where the rows are born. One of `SYSTEMS`, optionally followed by ': ' and a short
  detail, as 'derived: the web shop's order lines'.
- `grain`: what one row is. For a baseline table it is the header sentence of its `.sql` file,
  word for word.
- `key`: the columns that make a row unique; `()` for the two tables that have none.
- `columns`: the columns of tiny (or of the first extract that holds the table), in order.
- `added`: columns that `month` and `full` carry beyond tiny's, since 1.0. Tiny's columns are
  frozen (D13), so a new column on a tiny table lives here, never in `columns`. Only
  `customers.kind` (D7) is one today.
- `cut`: how tiny cuts the table out of the world. One of `CUTS`, optionally followed by ': '
  and what it names.
- `lives_in`: for a tiny table, where the extracts test finds its rows: `same(month)` or
  `same(full)` (the rows are there as they are, on tiny's columns), `derived(<query idea>)`
  (tiny computes it from other tables) or `landing` (raw text, cleaned only by the pages).
  None for a table tiny does not hold.
- `extracts`: which of tiny, month and full hold the table.
- `since`: 'baseline' for the 38 tables data-docs reads today, '1.0' for the new ones.
- `definition`: what the table is in the world, in a sentence or two.
- `lessons`: (page, what that page's argument needs from this table). A table can pass every
  number and still break a page whose argument it no longer carries (D15).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Tier = Literal[1, 2, 3, 'new']
Extract = Literal['tiny', 'month', 'full']

TYPES = (
    'VARCHAR',
    'INTEGER',
    'BOOLEAN',
    'DATE',
    'TIMESTAMP',
    'DECIMAL(7,2)',
    'DECIMAL(8,4)',
    'DECIMAL(9,2)',
)

SYSTEMS = {
    'app database': "the shop app's own tables, and the nightly copies it keeps",
    'status feed': 'the order status messages, each stamped with the moment it was loaded',
    'payment provider': 'the messages the payment provider sends, redeliveries included',
    'web tracking': 'what visitors did on the web shop, one event at a time',
    'csv export': "the shop's csv export, every column text, with the faults it had",
    'till': "the Bergen shop's new till, from 6 October 2026: its codes, members and receipts",
    'outside feed': 'outside the shop: bank rates, weather, the door counter, the old till',
    "owner's sheet": 'numbers the owner sets by hand, never simulated',
    'derived': 'computed from other tables; the detail names them',
}

CUTS = ('by key', 'by named list', 'by day window', 'whole reference', 'none')

ALL: tuple[Extract, ...] = ('tiny', 'month', 'full')
LATER: tuple[Extract, ...] = ('month', 'full')
FULL: tuple[Extract, ...] = ('full',)
TINY: tuple[Extract, ...] = ('tiny',)

MONTH = 'same(month)'


@dataclass(frozen=True)
class Column:
    """One column: its name and its DuckDB type, as DESCRIBE prints it."""

    name: str
    type: str


@dataclass(frozen=True)
class Table:
    """One table of the contract; the module docstring explains each field."""

    name: str
    tier: Tier
    system: str
    grain: str
    key: tuple[str, ...]
    columns: tuple[Column, ...]
    cut: str
    lives_in: str | None
    extracts: tuple[Extract, ...]
    since: Literal['baseline', '1.0']
    definition: str
    lessons: tuple[tuple[str, str], ...]
    added: tuple[Column, ...] = ()


def _cols(spec: str) -> tuple[Column, ...]:
    """Columns from 'name TYPE, name TYPE'; a DECIMAL's comma has no space after it."""
    found = []
    for part in spec.split(', '):
        name, kind = part.split(' ', 1)
        found.append(Column(name, kind))
    return tuple(found)


_TIER_1 = (
    Table(
        name='customers',
        tier=1,
        system='app database',
        grain='One row per customer, as the shop holds them today.',
        key=('customer_id',),
        columns=_cols(
            'customer_id VARCHAR, name VARCHAR, country VARCHAR, postal_code VARCHAR, joined DATE'
        ),
        added=_cols('kind VARCHAR'),
        cut='by key: the six named customers, C-01 to C-06',
        lives_in=MONTH,
        extracts=ALL,
        since='baseline',
        definition=(
            "The shop's customers as the app holds them at the end of the teaching week. C-07 was"
            ' erased on 9 October, so no row names them. From 1.0, month and full add `kind`:'
            ' consumer or business (D7).'
        ),
        lessons=(
            ('sql/joins', 'C-06 has not ordered, the row an anti-join finds; O-107 names C-07.'),
            ('sql/nulls', 'C-05 has no country and no postal code: the null in a dimension.'),
            ('sql/ranking', 'C-03 and C-04 joined the same day: a tie for every ranking.'),
            ('sql/text', "C-02's Å is two bytes; Oslo's postal code starts with a zero."),
            ('modeling/survivorship', "C-01's move on 9 October, which other systems missed."),
        ),
    ),
    Table(
        name='products',
        tier=1,
        system='app database',
        grain='One row per product the shop lists.',
        key=('product_id',),
        columns=_cols(
            'product_id VARCHAR, product_name VARCHAR, kind VARCHAR, category_id VARCHAR,'
            ' weight_g INTEGER'
        ),
        cut='whole reference',
        lives_in=MONTH,
        extracts=ALL,
        since='baseline',
        definition=('The five products the shop lists: three coffees and two pieces of equipment.'),
        lessons=(
            ('sql/joins', 'No P-99, though L-09 names it; P-12 is never sold.'),
            ('sql/group-by', '`kind` is the column to group by; categories hold the full tree.'),
            ('modeling/nulls-and-types', '`weight_g` is null for equipment: "does not apply".'),
            ('modeling/supertypes-and-subtypes', '`kind` splits beans from equipment.'),
        ),
    ),
    Table(
        name='orders',
        tier=1,
        system='app database',
        grain="One row per order, dated on the customer's clock.",
        key=('order_id',),
        columns=_cols('order_id VARCHAR, customer_id VARCHAR, order_date DATE, channel VARCHAR'),
        cut='by key: the orders of the cast, O-101 to O-108',
        lives_in=MONTH,
        extracts=ALL,
        since='baseline',
        definition=(
            'Every order placed in the app, on the web or at the counter (channel `shop`), dated'
            " on the customer's own clock."
        ),
        lessons=(
            ('sql/joins', 'O-106 has no lines; O-107 names C-07, who is erased: the orphan.'),
            (
                'polars/time-zones-and-durations',
                "O-106 is 7 October on Aino's Helsinki clock, still 6 October in Bergen.",
            ),
            (
                'modeling/slowly-changing-dimensions',
                'C-01 ordered before her move and after it (O-108): type 2 has both sides.',
            ),
        ),
    ),
    Table(
        name='order_lines',
        tier=1,
        system='app database',
        grain='One row per order line: an order, a product, a quantity, in NOK.',
        key=('line_id',),
        columns=_cols(
            'line_id VARCHAR, order_id VARCHAR, product_id VARCHAR, qty INTEGER,'
            ' unit_price DECIMAL(7,2)'
        ),
        cut='by key: the lines of the cast',
        lives_in=MONTH,
        extracts=ALL,
        since='baseline',
        definition=(
            'What each order bought: a product, a quantity and the price paid, in kroner. The'
            ' export writer plants L-04/L-05, L-07 and L-09 (plan 4.2).'
        ),
        lessons=(
            ('sql/duplicates', 'L-04 and L-05 are one line twice; the payment and stock prove it.'),
            ('sql/nulls', 'L-07 has no qty: `sum` skips it, `count(*)` does not.'),
            ('sql/joins', 'L-09 names P-99, which products lacks: an inner join loses it.'),
            ('modeling/nulls-and-types', 'L-12 is a free sample at 0.00: a zero, not a null.'),
        ),
    ),
    Table(
        name='dated_lines',
        tier=1,
        system='derived: order_lines joined to orders',
        grain=(
            "One row per order line, with its order's day. The pages call it order_lines.dated."
        ),
        key=('line_id',),
        columns=_cols(
            'line_id VARCHAR, product_id VARCHAR, order_date DATE, qty INTEGER,'
            ' unit_price DECIMAL(7,2)'
        ),
        cut='by key: the lines of the cast',
        lives_in="derived(order_lines joined to orders on order_id, with the order's day)",
        extracts=TINY,
        since='baseline',
        definition=(
            "The order lines with their order's day beside them, written out so the table"
            ' stands alone.'
        ),
        lessons=(
            ('sql/running-totals', "A running total by day needs each line's day."),
            ('sql/asof-and-range-joins', "Each line's day finds the price that held on it."),
            ('sql/pivot-and-unpivot', 'Sales by product and day, from one narrow table.'),
        ),
    ),
)

_TIER_2 = (
    Table(
        name='prices',
        tier=2,
        system='app database',
        grain='One row per product and period a list price held.',
        key=('product_id', 'valid_from'),
        columns=_cols('product_id VARCHAR, price DECIMAL(7,2), valid_from DATE, valid_to DATE'),
        cut='whole reference',
        lives_in=MONTH,
        extracts=ALL,
        since='baseline',
        definition=(
            'The list price of each product and the days it held. `valid_to` is the first day'
            ' it no longer holds (half-open); null means it still holds.'
        ),
        lessons=(
            (
                'sql/asof-and-range-joins',
                'P-21 has no price on 6 October, the day of L-06: a range join finds nothing.',
            ),
            (
                'sql/join-fan-out',
                'P-11 changes on 5 October, the day of L-03: with BETWEEN, L-03 counts twice.',
            ),
            ('modeling/slowly-changing-dimensions', 'A type 2 table the reader has queried.'),
            ('patterns/cache-aside', 'A price read often and changed rarely.'),
        ),
    ),
    Table(
        name='fx_rates',
        tier=2,
        system='outside feed: bank rates',
        grain=('One row per currency and banking day, 2 to 7 October 2026: kroner for one unit.'),
        key=('currency', 'rate_date'),
        columns=_cols('currency VARCHAR, rate_date DATE, nok_per_unit DECIMAL(8,4)'),
        cut='by day window: 2 to 7 October 2026',
        lives_in=MONTH,
        extracts=ALL,
        since='baseline',
        definition='What one Swedish krone, Danish krone or euro cost in kroner, on banking days.',
        lessons=(
            (
                'sql/asof-and-range-joins',
                "No weekend rows; DKK has only Friday's rate, so later payments take it as of.",
            ),
            ('polars/time-zones-and-durations', 'The missing days: forward fill or interpolate.'),
            (
                'modeling/facts-from-several-systems',
                'NOK is not in it: kroner payments need `coalesce(rate, 1)`.',
            ),
        ),
    ),
    Table(
        name='payments',
        tier=2,
        system='payment provider',
        grain=('One row per message from the payment provider (no key: PAY-1 came twice).'),
        key=(),
        columns=_cols(
            'payment_id VARCHAR, order_id VARCHAR, currency VARCHAR, amount DECIMAL(9,2),'
            ' paid_on DATE'
        ),
        cut='by key: the payments of the cast',
        lives_in=MONTH,
        extracts=ALL,
        since='baseline',
        definition=(
            'Every message the payment provider sent, in the currency the customer paid. The'
            ' provider redelivered PAY-1; O-107 was never paid.'
        ),
        lessons=(
            ('sql/duplicates', 'PAY-1 came twice: the provider redelivered it.'),
            ('patterns/idempotency', 'The same message handled twice must count once.'),
            (
                'modeling/facts-from-several-systems',
                'Converted as of, each payment is its order total: PAY-5 says L-07 was one.',
            ),
            ('pipeline/reruns', 'A rerun of the load must not add PAY-1 again.'),
        ),
    ),
    Table(
        name='order_events',
        tier=2,
        system='status feed',
        grain=(
            'One row per status change of an order, stamped in UTC, with the moment it was loaded.'
        ),
        key=('event_id',),
        columns=_cols(
            'event_id VARCHAR, order_id VARCHAR, status VARCHAR, event_at TIMESTAMP,'
            ' loaded_at TIMESTAMP'
        ),
        cut='by key: the events of the cast',
        lives_in=MONTH,
        extracts=ALL,
        since='baseline',
        definition=(
            "The app's status changes (placed, paid, shipped, delivered, cancelled), sent"
            ' through its outbox. The export writer drops the events of O-103, O-105 and O-107.'
        ),
        lessons=(
            (
                'pipeline/late-and-out-of-order',
                'E-08 happened on 8 October and loaded on 10 October; E-10 loaded before E-09.',
            ),
            ('modeling/accumulating-snapshots', 'O-101 goes through every stage.'),
            (
                'polars/time-zones-and-durations',
                'E-11 at 21:30 UTC is 7 October in Helsinki, the date orders holds for O-106.',
            ),
            ('pipeline/load-checks', 'No events for O-103, O-105 and O-107: a fact not complete.'),
            ('patterns/state-machine', 'The statuses an order may pass through, in order.'),
        ),
    ),
    Table(
        name='stock_daily',
        tier=2,
        system='app database',
        grain=(
            'One row per product, working day and count, P-10 and P-20, 5 to 9 October: the bags'
            ' or boxes on the shelf at close; counted_at is UTC (16:00 is 18:00 at close in'
            ' Bergen, summer time).'
        ),
        key=('product_id', 'stock_date', 'counted_at'),
        columns=_cols('product_id VARCHAR, stock_date DATE, on_hand INTEGER, counted_at TIMESTAMP'),
        cut='by day window: 5 to 9 October 2026, P-10 and P-20 only (D13)',
        lives_in=MONTH,
        extracts=ALL,
        since='baseline',
        definition=(
            "The shop's stock count at close of each working day, from the app's stock service"
            ' (S10), sent a whole day at a time. The export writer sends 7 October twice: the'
            ' count at close, and a recount next morning.'
        ),
        lessons=(
            ('modeling/grain', "A periodic snapshot: the week's stock is Friday's, not a sum."),
            ('sql/lag-and-lead', 'P-10 falls by 3 on 6 October where the lines say 6.'),
            ('pipeline/partition-overwrite', '7 October came twice; the latest count wins.'),
        ),
    ),
    Table(
        name='latest_stock',
        tier=2,
        system='derived: stock_daily, the latest count of each day',
        grain=(
            'One row per product and working day, the latest count of that day. The pages call'
            ' it stock_daily.latest.'
        ),
        key=('product_id', 'stock_date'),
        columns=_cols('product_id VARCHAR, stock_date DATE, on_hand INTEGER'),
        cut='by day window: 5 to 9 October 2026, P-10 and P-20 only',
        lives_in='derived(stock_daily, the row with the latest counted_at per product and day)',
        extracts=TINY,
        since='baseline',
        definition='The stock at close with one count per product and day: the latest one.',
        lessons=(
            ('sql/lag-and-lead', 'The change from day to day, on one count a day.'),
            ('polars/pivot-and-unpivot', 'P-10 and P-20 as columns, one row per day.'),
        ),
    ),
    Table(
        name='customer_extracts',
        tier=2,
        system='app database: nightly copies of customers',
        grain=(
            'One row per customer in each of two nightly copies, 8 and 9 October, of the'
            " shop's customer table."
        ),
        key=('extract_date', 'customer_id'),
        columns=_cols(
            'extract_date DATE, customer_id VARCHAR, country VARCHAR, postal_code VARCHAR'
        ),
        cut='by named list: the nights of 8 and 9 October',
        lives_in=MONTH,
        extracts=ALL,
        since='baseline',
        definition=(
            "The app's customer table as copied each night. The second night is customers"
            ' exactly, in the columns they share.'
        ),
        lessons=(
            (
                'pipeline/change-detection',
                'One row changed (C-01), one is new (C-06), one is gone (C-07).',
            ),
            ('pipeline/change-detection', "C-05's nulls must not count as a change."),
            ('pipeline/deletes', 'C-07 is gone the second night: erased, the order kept.'),
            ('pipeline/full-reload', 'Each night replaces the whole table.'),
        ),
    ),
    Table(
        name='customer_changes',
        tier=2,
        system='app database: the change log of customers',
        grain=(
            'One row per change the app wrote to its customers table; seq numbers the changes'
            ' in the order the app wrote them.'
        ),
        key=('seq',),
        columns=_cols(
            'seq INTEGER, op VARCHAR, customer_id VARCHAR, country VARCHAR, postal_code VARCHAR,'
            ' changed_at TIMESTAMP'
        ),
        cut="by key: the cast's changes, seq renumbered from 1",
        lives_in='same(full)',
        extracts=ALL,
        since='baseline',
        definition=(
            "Every insert, update and delete on the app's customers, from the first customer"
            ' on. The extracts test compares it without `seq`, and checks the order by `seq`.'
        ),
        lessons=(
            ('pipeline/change-log', "C-07's delete is a tombstone that carries the key only."),
            ('pipeline/merge', 'C-01 moves twice in one batch (a typo, fixed three minutes on).'),
            (
                'pipeline/replay',
                'Folded to midnight before 9 October it is the copy of 8 October.',
            ),
        ),
    ),
    Table(
        name='line_stamps',
        tier=2,
        system='app database: order lines with their stamps',
        grain=(
            "One row per row of the app's order lines table, deleted rows kept, with the moment"
            ' it last changed.'
        ),
        key=('line_id',),
        columns=_cols(
            'line_id VARCHAR, order_id VARCHAR, qty INTEGER, is_deleted BOOLEAN,'
            ' updated_at TIMESTAMP'
        ),
        cut='by key: the lines of the cast, L-10 included',
        lives_in=MONTH,
        extracts=ALL,
        since='baseline',
        definition=(
            "The app's order lines as its own bookkeeping holds them: soft-deleted rows stay,"
            ' and each row has the moment it last changed.'
        ),
        lessons=(
            ('pipeline/deletes', "L-10 was O-106's line, marked deleted when Aino cancelled."),
            ('pipeline/reading-a-live-source', '`updated_at` is the high-water mark of a load.'),
            ('modeling/model-tests', 'Without the deleted row it is order_lines.'),
        ),
    ),
    Table(
        name='raw_customers',
        tier=2,
        system='csv export',
        grain=(
            "One row per customer who has ordered (C-01 to C-05) in the shop's csv export, as of"
            " after C-01's move on 9 October, every column text (no key: the text is as the"
            ' export gave it); C-06 has no order and C-07 is erased, so neither is in it.'
        ),
        key=(),
        columns=_cols(
            'customer_id VARCHAR, name VARCHAR, country VARCHAR, postal_code VARCHAR,'
            ' joined VARCHAR, email VARCHAR'
        ),
        cut='by key: C-01 to C-05',
        lives_in='landing',
        extracts=ALL,
        since='baseline',
        definition=(
            "The customers in the shop's csv export, as text with its stray spaces, cases and"
            ' two date formats. Cleaned, it is C-01 to C-05 of customers exactly.'
        ),
        lessons=(
            ('sql/text', "DuckDB's trim leaves C-03's tab and takes C-04's no-break space."),
            ('sql/dates', '`joined` comes in two formats.'),
            ('modeling/nulls-and-types', 'Postal code 150 must be padded to 0150, not cast.'),
            ('pipeline/reading-files', 'Cleaned, the rows end on customers the reader knows.'),
        ),
    ),
    Table(
        name='raw_lines',
        tier=2,
        system='csv export',
        grain=(
            "Five lines (L-01, L-02, L-03, L-06, L-07) of the shop's csv export, every column text."
        ),
        key=('line_id',),
        columns=_cols(
            'line_id VARCHAR, order_id VARCHAR, product_id VARCHAR, qty VARCHAR, unit_price VARCHAR'
        ),
        cut='by named list: L-01, L-02, L-03, L-06, L-07',
        lives_in='landing',
        extracts=ALL,
        since='baseline',
        definition=(
            "Order lines in the shop's csv export, every column text. Cleaned, they are those"
            ' five rows of order_lines exactly.'
        ),
        lessons=(
            ('sql/types-and-cast', "'129,00' fails a cast; 'n/a' is the null really missing."),
            ('pipeline/landing-files', 'The text as the export gave it, kept before cleaning.'),
            ('polars/selectors', 'Every column is text until a selector casts it.'),
        ),
    ),
    Table(
        name='web_events',
        tier=2,
        system='web tracking',
        grain='One row per thing one of four visitors did on the web shop, stamped in UTC.',
        key=('event_id',),
        columns=_cols(
            'event_id VARCHAR, visitor_id VARCHAR, customer_id VARCHAR, event VARCHAR,'
            ' event_at TIMESTAMP'
        ),
        cut='by named list: the visitors V-1 to V-4',
        lives_in=MONTH,
        extracts=ALL,
        since='baseline',
        definition=(
            'What visitors did on the web shop: a view, a cart, a checkout. A checkout is'
            ' followed within two minutes by a placed event.'
        ),
        lessons=(
            ('sql/lag-and-lead', 'V-2 comes back after 45 minutes: a 30-minute gap rule.'),
            (
                'sql/counting-and-conditional-sums',
                'The funnel: four view, four reach the cart, three check out.',
            ),
            ('sql/nulls', 'V-2 never logs in: `customer_id` is null.'),
            ('pipeline/streaming', 'Events arrive one at a time, stamped in UTC.'),
        ),
    ),
    Table(
        name='subscriptions',
        tier=2,
        system='app database',
        grain=(
            'One row per subscription: a customer, a product every month, from a first day to'
            ' the day it stopped.'
        ),
        key=('subscription_id',),
        columns=_cols(
            'subscription_id VARCHAR, customer_id VARCHAR, product_id VARCHAR, started DATE,'
            ' ended DATE'
        ),
        cut='by key: the subscriptions of the cast, S-1 to S-7',
        lives_in=MONTH,
        extracts=ALL,
        since='baseline',
        definition=(
            "The cast's subscriptions: one bag a month, from a first day to the day it stopped"
            " (null while it runs). Everyone else's are subscribers (D8)."
        ),
        lessons=(
            ('sql/dates', 'C-02 stopped and came back; C-04 has two that overlap.'),
            ('sql/asof-and-range-joins', 'Active on a day: a count of periods that hold.'),
            ('modeling/measures', 'Active subscriptions are semi-additive.'),
            ('patterns/command', 'Starting and stopping a subscription as commands.'),
        ),
    ),
    Table(
        name='categories',
        tier=2,
        system='app database',
        grain=(
            "One row per category; parent_id points one level up, sort_order is the shop's order."
        ),
        key=('category_id',),
        columns=_cols(
            'category_id VARCHAR, category_name VARCHAR, parent_id VARCHAR, sort_order INTEGER'
        ),
        cut='whole reference',
        lives_in=MONTH,
        extracts=ALL,
        since='baseline',
        definition='The tree of product categories, as the shop shows it.',
        lessons=(
            (
                'modeling/dimension-design',
                'A ragged tree: the hand grinder three levels down, the kettle two.',
            ),
            ('dax/patterns', '`sort_order` is the one order of the tree, set in one place.'),
        ),
    ),
    Table(
        name='kinds',
        tier=2,
        system='app database',
        grain='One row per kind of product, so a budget by kind relates to products through it.',
        key=('kind',),
        columns=_cols('kind VARCHAR, kind_name VARCHAR'),
        cut='whole reference',
        lives_in=MONTH,
        extracts=ALL,
        since='baseline',
        definition='The two kinds of product, beans and equipment.',
        lessons=(
            ('modeling/conformed-dimensions', 'Budget and sales meet on kind.'),
            ('dax/relationships', 'A budget by kind filters products through this table.'),
        ),
    ),
    Table(
        name='campaign_products',
        tier=2,
        system='app database',
        grain='One row per campaign and product in it.',
        key=('campaign_id', 'product_id'),
        columns=_cols('campaign_id VARCHAR, campaign_name VARCHAR, product_id VARCHAR'),
        cut='whole reference',
        lives_in=MONTH,
        extracts=ALL,
        since='baseline',
        definition='Which products each campaign holds: many to many.',
        lessons=(
            (
                'sql/join-fan-out',
                'The hand grinder is in both: sales per campaign add to more than all sales.',
            ),
            ('modeling/normalization', '`campaign_name` repeats on every row of a campaign.'),
            ('dax/relationships', 'A bridge and its filter direction.'),
        ),
    ),
    Table(
        name='campaigns',
        tier=2,
        system='app database',
        grain='One row per campaign, with its discount and its days.',
        key=('campaign_id',),
        columns=_cols(
            'campaign_id VARCHAR, campaign_name VARCHAR, discount_pct INTEGER, first_day DATE,'
            ' last_day DATE'
        ),
        cut='whole reference',
        lives_in=MONTH,
        extracts=ALL,
        since='baseline',
        definition='The campaigns the shop ran: a discount on its products, on its days.',
        lessons=(
            ('modeling/multivalued-dimensions', 'The dimension on the far side of the bridge.'),
            ('modeling/ownership-and-change', 'Who owns a campaign and its days.'),
        ),
    ),
    Table(
        name='product_codes',
        tier=2,
        system='till',
        grain='One row per code the till knows, and the product it is.',
        key=('ean',),
        columns=_cols('ean VARCHAR, product_id VARCHAR'),
        cut='whole reference',
        lives_in=MONTH,
        extracts=ALL,
        since='baseline',
        definition="The till's barcodes and the product each one is.",
        lessons=(
            ('modeling/conforming-codes', 'Dark espresso has two codes: box and loose beans.'),
            ('modeling/key-mapping', 'One code the till knows has no product.'),
        ),
    ),
    Table(
        name='till_receipts',
        tier=2,
        system='till',
        grain=(
            "One row per till receipt of a listed member, and the trial day's one receipt,"
            ' sold_at in Bergen time.'
        ),
        key=('receipt_id',),
        columns=_cols('receipt_id VARCHAR, member_no INTEGER, sold_at TIMESTAMP'),
        cut="by named list: the listed members' receipts and R-5001",
        lives_in=MONTH,
        extracts=ALL,
        since='baseline',
        definition=(
            "The new till's receipts, in Bergen time. R-5001, rung on the trial day, is the only"
            ' one in the teaching week before 7 October (D12).'
        ),
        lessons=(
            (
                'modeling/combining-sources',
                "R-5001 is O-104's kettle: matched by moment and product, not by customer.",
            ),
            ('modeling/key-mapping', "R-5002 names Mikkel's second member number."),
            ('modeling/time-in-a-model', 'R-5004 names Hilde before she is listed.'),
            ('pyspark/time-zones-and-durations', 'sold_at is Bergen time; the app stamps UTC.'),
        ),
    ),
    Table(
        name='till_lines',
        tier=2,
        system='till',
        grain='One row per line of those receipts.',
        key=('receipt_id', 'line_no'),
        columns=_cols(
            'receipt_id VARCHAR, line_no INTEGER, ean VARCHAR, grams INTEGER, amount DECIMAL(7,2)'
        ),
        cut='by named list: the lines of those receipts',
        lives_in=MONTH,
        extracts=ALL,
        since='baseline',
        definition='What each till receipt sold, by barcode; grams only for loose beans.',
        lessons=(
            ('modeling/facts-from-several-systems', 'A second sales fact, with its own keys.'),
            ('modeling/conforming-codes', 'A line reaches a product only through its code.'),
            ('patterns/parse-dont-validate', 'A till line parsed once into a sale.'),
        ),
    ),
    Table(
        name='till_members',
        tier=2,
        system='till',
        grain=(
            "One row per listed member in each nightly list of the shop's club: the first list"
            ' holds every member, later ones those who joined.'
        ),
        key=('member_no', 'listed_on'),
        columns=_cols(
            'member_no INTEGER, name VARCHAR, email VARCHAR, postal_code VARCHAR, listed_on DATE'
        ),
        cut='by named list: the listed club members',
        lives_in=MONTH,
        extracts=ALL,
        since='baseline',
        definition=(
            "The till's club list, sent each night. The till was never told that Ingrid moved or"
            ' that C-07 was erased.'
        ),
        lessons=(
            ('modeling/key-mapping', 'Mikkel signed up twice; Sindre has no web account.'),
            ('modeling/survivorship', 'The till still has Ingrid at her old postal code.'),
            ('pipeline/personal-data-and-access', 'Erased in the shop, still listed in the till.'),
        ),
    ),
    Table(
        name='customer_months',
        tier=2,
        system='derived: orders, order_lines and subscriptions of C-01',
        grain=(
            'One row per month of C-01, November 2025 to October 2026: orders, spend in NOK and'
            " whether a subscription ran; spend_nok counts the orders' lines only, not the"
            " subscription's monthly charge (a month can show 0.00 with subscribed true)."
        ),
        key=('customer_id', 'month'),
        columns=_cols(
            'customer_id VARCHAR, month DATE, orders INTEGER, spend_nok DECIMAL(7,2),'
            ' subscribed BOOLEAN'
        ),
        cut='by key: C-01',
        lives_in=(
            'derived(full: per month, the orders and line spend of C-01, and whether S-1 ran)'
        ),
        extracts=TINY,
        since='baseline',
        definition=(
            "C-01's year, month by month: how many orders, what they spent and whether her"
            ' subscription ran. Her year is scripted at the old prices (plan 4.2).'
        ),
        lessons=(('modeling/mini-dimensions', "C-01's months cross the band edges often."),),
    ),
    Table(
        name='bean_details',
        tier=2,
        system='app database',
        grain='One row per product of the kind beans, with what only beans have.',
        key=('product_id',),
        columns=_cols('product_id VARCHAR, origin VARCHAR, roast VARCHAR, process VARCHAR'),
        cut='whole reference',
        lives_in=MONTH,
        extracts=ALL,
        since='baseline',
        definition='What only coffee has: origin, roast and process.',
        lessons=(('modeling/supertypes-and-subtypes', 'The subtype table of beans.'),),
    ),
    Table(
        name='equipment_details',
        tier=2,
        system='app database',
        grain='One row per product of the kind equipment, with what only equipment has.',
        key=('product_id',),
        columns=_cols('product_id VARCHAR, warranty_months INTEGER, material VARCHAR'),
        cut='whole reference',
        lives_in=MONTH,
        extracts=ALL,
        since='baseline',
        definition='What only equipment has: a warranty and a material.',
        lessons=(('modeling/supertypes-and-subtypes', 'The subtype table of equipment.'),),
    ),
    Table(
        name='managers',
        tier=2,
        system="owner's sheet",
        grain='One row per country and the person who sees its customers.',
        key=('country',),
        columns=_cols('manager VARCHAR, country VARCHAR'),
        cut='whole reference',
        lives_in=MONTH,
        extracts=ALL,
        since='baseline',
        definition='Who looks after the customers of each country.',
        lessons=(
            ('dax/security', 'Row-level security: a manager sees one country.'),
            ('modeling/nulls-and-types', 'C-05 has no country, so no manager sees her.'),
        ),
    ),
)

_TIER_3 = (
    Table(
        name='daily_sales',
        tier=3,
        system="derived: the web shop's consumer order lines",
        grain=(
            'One row per day and product with a price that day, 1 October 2024 to 30 September'
            ' 2026.'
        ),
        key=('sale_date', 'product_id'),
        columns=_cols('sale_date DATE, product_id VARCHAR, qty INTEGER, amount DECIMAL(7,2)'),
        cut='none',
        lives_in=None,
        extracts=FULL,
        since='baseline',
        definition=(
            "Per day and product, the web shop's order lines to private customers, at list"
            ' price. Counter sales and business accounts are outside it (D7, D15).'
        ),
        lessons=(
            (
                'stats/correlation',
                'Walk-ins do not cause these sales: the web shop only, so the link is a'
                ' confounder (D15).',
            ),
            ('stats/comparing-periods', 'Each December about double; the second year higher.'),
            ('dax/time-intelligence', 'Two full years for a year over year.'),
            ('dax/weeks-and-calendars', 'Friday sells about three times Sunday.'),
        ),
    ),
    Table(
        name='order_values',
        tier=3,
        system='derived: a scripted lesson set of app orders',
        grain='One order of 2026 (600, 1 January to 30 September), web or shop.',
        key=('order_no',),
        columns=_cols(
            'order_no INTEGER, order_date DATE, channel VARCHAR, amount DECIMAL(7,2),'
            ' status VARCHAR'
        ),
        cut='none',
        lives_in=None,
        extracts=FULL,
        since='baseline',
        definition=(
            'A lesson set: 600 scripted orders of 2026, consumer and business, played inside'
            " the wider trade. The large orders (10 bags, the café's 48) are business (D7)."
        ),
        lessons=(
            ('stats/mean-and-median', 'A skewed basket: the mean above the median.'),
            ('stats/outliers', 'One café order of 48 bags is the one big value.'),
            ('stats/samples-and-bias', 'Refunds and unpaid orders change the sample.'),
        ),
    ),
    Table(
        name='budget',
        tier=3,
        system="owner's sheet",
        grain=(
            'One row per month and product kind, October 2024 to December 2026 (set ahead, as'
            ' budgets are).'
        ),
        key=('month', 'kind'),
        columns=_cols('month DATE, kind VARCHAR, budget_nok INTEGER'),
        cut='none',
        lives_in=None,
        extracts=FULL,
        since='baseline',
        definition=(
            'What the owner planned to sell, per month and kind, in whole kroner. Hand-set like'
            ' prices; never simulated.'
        ),
        lessons=(
            ('dax/relationships', 'Budget by month and kind; actuals by day and product.'),
            ('dax/patterns', 'Actual against budget: some months beat it, some miss.'),
        ),
    ),
    Table(
        name='checkout_test',
        tier=3,
        system='derived: web tracking during a 40-day test',
        grain=('One visitor of the product page in a 40-day test of two versions, A and B.'),
        key=('visitor_no',),
        columns=_cols('visitor_no INTEGER, test_day INTEGER, variant VARCHAR, converted BOOLEAN'),
        cut='none',
        lives_in=None,
        extracts=FULL,
        since='baseline',
        definition=(
            'Every visitor of the product page during a scripted A/B test. `variant` sits on'
            ' the web event; converted means reached the checkout, not an order placed.'
        ),
        lessons=(
            ('stats/ab-tests', 'B converts better, about 2.7 standard errors apart.'),
            ('stats/ab-tests', 'After two days the gap is a fluke; A against A is equal.'),
            ('stats/confidence-intervals', 'An interval for each variant.'),
        ),
    ),
    Table(
        name='subscribers',
        tier=3,
        system='derived: the subscriptions of everyone outside the cast',
        grain=(
            'One subscription (240), started 2024 to September 2026 and counted on 30 September'
            ' 2026.'
        ),
        key=('subscription_id',),
        columns=_cols('subscription_id INTEGER, product_id VARCHAR, started DATE, ended DATE'),
        cut='none',
        lives_in=None,
        extracts=FULL,
        since='baseline',
        definition=(
            "The subscriptions of every customer outside the teaching week's cast, as they"
            ' stood on 30 September 2026 (D8).'
        ),
        lessons=(
            ('stats/cohorts', 'Retention by start month: later cohorts stay longer.'),
            ('dax/semi-additive', 'Active subscribers on a day do not add over days.'),
        ),
    ),
    Table(
        name='visits',
        tier=3,
        system='derived: web tracking, the attributed visits',
        grain=(
            'One visit to the web shop (3,600), 1 October 2024 to 30 September 2026, with the'
            ' furthest step it reached.'
        ),
        key=('visit_id',),
        columns=_cols(
            'visit_id INTEGER, visit_date DATE, country VARCHAR, source VARCHAR, reached INTEGER'
        ),
        cut='none',
        lives_in=None,
        extracts=FULL,
        since='baseline',
        definition=(
            'The attributed panel: visits with a source (newsletter, ads). Direct traffic has'
            ' no source and is outside it.'
        ),
        lessons=(
            ('stats/funnels', 'The furthest step each visit reached, one to four.'),
            ('stats/simpsons-paradox', 'The sources reverse between the parts and the total.'),
            ('stats/small-numbers', 'A Finnish cell of four newsletter visits.'),
        ),
    ),
    Table(
        name='deliveries',
        tier=3,
        system="derived: shipments of the lesson set's web orders (S8)",
        grain='One web order of order_values, shipped the day after it was placed.',
        key=('order_no',),
        columns=_cols('order_no INTEGER, country VARCHAR, shipped_on DATE, days INTEGER'),
        cut='none',
        lives_in=None,
        extracts=FULL,
        since='baseline',
        definition=(
            "The parcels of order_values' 480 web orders: days from shipped to delivered."
            ' From 1.0 it is derived from shipments (S8).'
        ),
        lessons=(
            ('stats/spread', 'Norway and Finland: the same mean, another spread.'),
            ('stats/percentiles', 'Order 297, lost in Sweden for 21 days: the long tail.'),
        ),
    ),
    Table(
        name='shop_days',
        tier=3,
        system='derived: door counter, weather and old till',
        grain=(
            'One day of the Bergen shop, 1 October 2024 to 30 September 2026; Sundays are closed.'
        ),
        key=('shop_date',),
        columns=_cols('shop_date DATE, rain_mm INTEGER, walk_ins INTEGER, receipts INTEGER'),
        cut='none',
        lives_in=None,
        extracts=FULL,
        since='baseline',
        definition=(
            'Three outside systems side by side: the door counter (walk-ins), a weather feed'
            " (rain) and the old till's day totals (receipts). From 1.0 it is their join (D12)."
        ),
        lessons=(
            ('stats/correlation', 'Rain and walk-ins move against each other.'),
            ('stats/correlation', 'Walk-ins against bags sold: a confounder, not a cause.'),
        ),
    ),
)

_NEW = (
    Table(
        name='subscription_events',
        tier='new',
        system='app database',
        grain='One row per skip, pause, resume or cancel of a subscription, with a reason.',
        key=('event_id',),
        columns=_cols(
            'event_id VARCHAR, subscription_id VARCHAR, event_type VARCHAR, reason VARCHAR,'
            ' event_at TIMESTAMP'
        ),
        cut='none',
        lives_in=None,
        extracts=LATER,
        since='1.0',
        definition='What a subscriber did to a subscription, and why.',
        lessons=(
            ('patterns/command', 'A skip or a cancel as a command, with its reason.'),
            ('later: MRR and churn', 'Churn with a cause.'),
        ),
    ),
    Table(
        name='subscription_shipments',
        tier='new',
        system='app database',
        grain='One row per bag shipped to a subscriber.',
        key=('shipment_id',),
        columns=_cols(
            'shipment_id VARCHAR, subscription_id VARCHAR, product_id VARCHAR,'
            ' shipped_on DATE, qty INTEGER'
        ),
        cut='none',
        lives_in=None,
        extracts=LATER,
        since='1.0',
        definition=(
            'The monthly bags, as their own table, not as orders: orders rows would break'
            " tiny's eight orders and customer_months (D11)."
        ),
        lessons=(('later: MRR and stock', 'What each subscription shipped, month by month.'),),
    ),
    Table(
        name='stock_movements',
        tier='new',
        system='app database',
        grain='One row per stock movement: roasted, sold, shipped, written off or counted.',
        key=('movement_id',),
        columns=_cols(
            'movement_id VARCHAR, product_id VARCHAR, moved_at TIMESTAMP, reason VARCHAR,'
            ' qty INTEGER'
        ),
        cut='none',
        lives_in=None,
        extracts=LATER,
        since='1.0',
        definition=(
            'Every change to the stock, signed: in is positive, out is negative. At close on 5'
            ' to 9 October the balance is latest_stock for P-10 and P-20.'
        ),
        lessons=(('later: stock flow', 'Stock as the sum of its movements.'),),
    ),
    Table(
        name='green_purchases',
        tier='new',
        system='app database',
        grain='One row per purchase of green coffee, by the kilo.',
        key=('purchase_id',),
        columns=_cols(
            'purchase_id VARCHAR, bought_on DATE, origin VARCHAR, kg DECIMAL(7,2),'
            ' nok_per_kg DECIMAL(7,2)'
        ),
        cut='none',
        lives_in=None,
        extracts=LATER,
        since='1.0',
        definition='The unroasted coffee the roaster bought: at least the kilos it roasted.',
        lessons=(('later: purchase planning', 'Kilos bought against kilos roasted.'),),
    ),
    Table(
        name='product_costs',
        tier='new',
        system='app database',
        grain='One row per product and period a cost held.',
        key=('product_id', 'valid_from'),
        columns=_cols(
            'product_id VARCHAR, valid_from DATE, valid_to DATE, green_nok DECIMAL(7,2),'
            ' packaging_nok DECIMAL(7,2), roasting_nok DECIMAL(7,2)'
        ),
        cut='none',
        lives_in=None,
        extracts=LATER,
        since='1.0',
        definition=(
            'What a product cost to make, per period: green coffee, bag and roasting. Periods'
            ' are half-open, like prices.'
        ),
        lessons=(('later: margin', 'Cost below list price in every price period.'),),
    ),
    Table(
        name='shipments',
        tier='new',
        system='app database',
        grain='One row per parcel, with the day it was promised and the day it arrived.',
        key=('shipment_id',),
        columns=_cols(
            'shipment_id VARCHAR, order_id VARCHAR, shipped_on DATE, promised_by DATE,'
            ' delivered_on DATE'
        ),
        cut='none',
        lives_in=None,
        extracts=LATER,
        since='1.0',
        definition=(
            "One parcel of a web order. deliveries is derived from it for order_values' web"
            ' orders, through lesson_ids: days = delivered_on minus shipped_on (S8, S9).'
        ),
        lessons=(('stats/percentiles', 'Late delivery as a fact: order 297 takes 21 days.'),),
    ),
    Table(
        name='pricing_rules',
        tier='new',
        system='app database',
        grain='One row per pricing rule: the subscriber discount or a campaign percentage.',
        key=('rule_id',),
        columns=_cols(
            'rule_id VARCHAR, rule_kind VARCHAR, percent INTEGER, valid_from DATE, valid_to DATE'
        ),
        cut='none',
        lives_in=None,
        extracts=LATER,
        since='1.0',
        definition=(
            "The discounts the app applies, each on its days. Each campaign's discount is one"
            ' rule; at most one subscriber rule holds on a day.'
        ),
        lessons=(
            ('patterns/strategy', 'A pricing rule chosen by its kind (closes gap G3).'),
            ('patterns/registries-and-plugins', 'The rules the app knows, in one place.'),
        ),
    ),
    Table(
        name='weather_days',
        tier='new',
        system='outside feed: weather',
        grain='One row per day of the Bergen shop, with the rain that fell.',
        key=('shop_date',),
        columns=_cols('shop_date DATE, rain_mm INTEGER'),
        cut='none',
        lives_in=None,
        extracts=LATER,
        since='1.0',
        definition="The weather feed's rain in Bergen, a day at a time.",
        lessons=(('stats/correlation', 'The rain in shop_days comes from here.'),),
    ),
    Table(
        name='door_counts',
        tier='new',
        system='outside feed: door counter',
        grain='One row per day of the Bergen shop, with the people who came in.',
        key=('shop_date',),
        columns=_cols('shop_date DATE, walk_ins INTEGER'),
        cut='none',
        lives_in=None,
        extracts=LATER,
        since='1.0',
        definition="The door counter's walk-ins, a day at a time.",
        lessons=(('stats/correlation', 'The walk-ins in shop_days come from here.'),),
    ),
    Table(
        name='till_day_totals',
        tier='new',
        system='outside feed: old till',
        grain='One row per day of the Bergen shop, with the receipts the old till rang.',
        key=('shop_date',),
        columns=_cols('shop_date DATE, receipts INTEGER'),
        cut='none',
        lives_in=None,
        extracts=LATER,
        since='1.0',
        definition=(
            "The old till's day totals: anonymous walk-in sales, counted only. What it sold is"
            ' not in the data (D12).'
        ),
        lessons=(('stats/correlation', 'The receipts in shop_days come from here.'),),
    ),
    Table(
        name='lesson_ids',
        tier='new',
        system='derived: the lesson sets of tier 3 and the shop ids they stand for',
        grain=(
            'One row per row of a tier 3 lesson set (order_values, subscribers), with the'
            " shop's own id it stands for."
        ),
        key=('lesson_set', 'row_no'),
        columns=_cols('lesson_set VARCHAR, row_no INTEGER, shop_id VARCHAR'),
        cut='none',
        lives_in=None,
        extracts=LATER,
        since='1.0',
        definition=(
            'Tier 3 keeps its integer row numbers (order 300 is the refund, 297 the lost'
            " parcel, 600 the café); this map ties each to the shop's text id, O-... or S-..."
            ' (S9).'
        ),
        lessons=(
            (
                'later: modeling/keys-and-relationships',
                "A sample's row number against the shop's own id: two keys, one row.",
            ),
        ),
    ),
)

TABLES: tuple[Table, ...] = _TIER_1 + _TIER_2 + _TIER_3 + _NEW


def by_name() -> dict[str, Table]:
    """The tables by name."""
    return {table.name: table for table in TABLES}
