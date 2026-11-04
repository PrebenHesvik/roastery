"""The csv export and the customer extract, read through the ports.

The export is the shop's own output: `raw_customers` and `raw_lines`
as clean text (ISO dates, `.` decimals, an empty cell for a value the
app does not hold). The export writer of the simulator adds the
faults after it (D10). Each file is written through `pipeline`'s
stages, lazily, from what the unit of work's repositories list; no
store is touched directly (ADR 0001, ADR 0003).

`app_tables` reads the app's own tables back as contract A names
them (W2): the app db has its own schema, and each `Projection`
here maps one of its tables to contract A's columns (A33, C3).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from roastery.catalogue import (
    KIND_NAMES,
    BeanDetails,
    EquipmentDetails,
)
from roastery.customer import Customer
from roastery.money import Money
from roastery.pipeline import Rows, as_text, live_lines, pipe, to_csv
from roastery.ports import ExtractRow, UnitOfWork

CUSTOMER_COLUMNS: Final[tuple[str, ...]] = (
    'customer_id',
    'name',
    'country',
    'postal_code',
    'joined',
    'email',
)
"""The columns of `raw_customers`, in the file's order."""

CUSTOMERS_FILE: Final = 'raw_customers.csv'
LINES_FILE: Final = 'raw_lines.csv'


def customer_cells(customer: Customer) -> dict[str, str]:
    """A customer as the export's text; a missing value is ''."""
    return {
        'customer_id': str(customer.customer_id),
        'name': customer.name,
        'country': customer.country or '',
        'postal_code': str(customer.postal_code or ''),
        'joined': customer.joined.isoformat(),
        'email': str(customer.email or ''),
    }


def _customers_who_ordered(uow: UnitOfWork) -> Iterator[Customer]:
    """The customers with an order, sorted by customer id."""
    ordered = {order.head.customer_id for order in uow.orders.all()}
    for customer in uow.customers.all():
        if customer.customer_id in ordered:
            yield customer


def raw_customers(uow: UnitOfWork) -> str:
    """The text of `raw_customers`: customers who have ordered."""
    rows = (customer_cells(c) for c in _customers_who_ordered(uow))
    return ''.join(to_csv(rows, CUSTOMER_COLUMNS))


def raw_lines(uow: UnitOfWork) -> str:
    """The text of `raw_lines`: the lines no cancel deleted."""
    lines = pipe(uow.orders.lines(), live_lines, as_text, to_csv)
    return ''.join(lines)


def csv_export(uow: UnitOfWork) -> Mapping[str, str]:
    """Both files as file name to text, read in one unit of work."""
    with uow:
        return {
            CUSTOMERS_FILE: raw_customers(uow),
            LINES_FILE: raw_lines(uow),
        }


def nightly_extract(uow: UnitOfWork, day: dt.date) -> int:
    """Make every customer's country and postal code the copy of
    `day`, replacing an earlier copy of it. The rows written.

    The day is the shop's today, which the caller works out from
    the clock (A17); a run twice gives the same rows.
    """
    with uow:
        rows = tuple(
            ExtractRow(
                day,
                customer.customer_id,
                customer.country,
                customer.postal_code,
            )
            for customer in uow.customers.all()
        )
        uow.extracts.replace(day, rows)
        uow.commit()
    return len(rows)


# The app's tables as contract A names them (W2, A33) --------------

type Cells = Mapping[str, object]
"""One row: contract A's column names to their Python values."""

CENT: Final = Decimal('0.01')
"""The scale of every amount the app tables hold: DECIMAL(7,2)."""


def _cents(amount: Decimal) -> Decimal:
    return amount.quantize(CENT)


def _nok(money: Money) -> Decimal:
    """The amount of a `*_nok` column; another currency is a bug."""
    if money.currency != 'NOK':
        raise ValueError(f'a NOK column holds {money.currency}')
    return _cents(money.amount)


def _utc(moment: dt.datetime) -> dt.datetime:
    return moment.astimezone(dt.UTC)


def _text(value: object | None) -> str | None:
    """An id or a postal code as its text; None stays None."""
    return None if value is None else str(value)


def _customers(uow: UnitOfWork) -> Iterator[Cells]:
    for customer in uow.customers.all():
        yield {
            'customer_id': str(customer.customer_id),
            'name': customer.name,
            'country': customer.country,
            'postal_code': _text(customer.postal_code),
            'joined': customer.joined,
            'account_kind': customer.account_kind,
            'source': uow.customers.source_of(customer.customer_id),
        }


def _products(uow: UnitOfWork) -> Iterator[Cells]:
    for product in uow.catalogue.products():
        yield {
            'product_id': str(product.product_id),
            'product_name': product.name,
            'kind': product.kind,
            'category_id': str(product.category_id),
            'weight_g': product.weight_g,
            'source': uow.catalogue.product_source(product.product_id),
        }


def _orders(uow: UnitOfWork) -> Iterator[Cells]:
    """The order's head and its booking's day; the status, the
    payment, the shipment and the VAT stay in the app."""
    for order in uow.orders.all():
        head = order.head
        yield {
            'order_id': str(head.order_id),
            'customer_id': str(head.customer_id),
            'order_date': uow.orders.booking(head.order_id).order_date,
            'channel': head.channel,
            'source': uow.orders.source_of(head.order_id),
        }


def _order_lines(uow: UnitOfWork) -> Iterator[Cells]:
    """The lines no cancel deleted (as `raw_lines`)."""
    for line in live_lines(uow.orders.lines()):
        yield {
            'line_id': str(line.line_id),
            'order_id': str(line.order_id),
            'product_id': str(line.product_id),
            'qty': line.qty.value,
            'unit_price': _cents(line.unit_price.amount),
            'source': uow.orders.source_of(line.order_id),
        }


def _line_stamps(uow: UnitOfWork) -> Iterator[Cells]:
    """Every line, deleted ones too: a deleted line is stamped
    with its cancel, a live one with its booking."""
    for line in uow.orders.lines():
        deleted = uow.orders.deleted_at(line.order_id)
        if line.is_deleted and deleted is not None:
            stamp = deleted
        else:
            stamp = uow.orders.booking(line.order_id).at
        yield {
            'line_id': str(line.line_id),
            'order_id': str(line.order_id),
            'qty': line.qty.value,
            'is_deleted': line.is_deleted,
            'updated_at': _utc(stamp),
            'source': uow.orders.source_of(line.order_id),
        }


def _prices(uow: UnitOfWork) -> Iterator[Cells]:
    for product in uow.catalogue.products():
        for price in uow.prices.of(product.product_id):
            yield {
                'product_id': str(price.product_id),
                'price': _cents(price.price.amount),
                'valid_from': price.valid_from,
                'valid_to': price.valid_to,
                'source': uow.prices.source_of(
                    price.product_id, price.valid_from
                ),
            }


def _stock_daily(uow: UnitOfWork) -> Iterator[Cells]:
    for count in uow.stock.all_counts():
        yield {
            'product_id': str(count.product_id),
            'stock_date': count.stock_date,
            'on_hand': count.on_hand,
            'counted_at': _utc(count.counted_at),
            'source': uow.stock.count_source(
                count.product_id, count.stock_date, count.counted_at
            ),
        }


def _customer_extracts(uow: UnitOfWork) -> Iterator[Cells]:
    for row in uow.extracts.all():
        yield {
            'extract_date': row.extract_date,
            'customer_id': str(row.customer_id),
            'country': row.country,
            'postal_code': _text(row.postal_code),
            'source': uow.extracts.source_of(
                row.extract_date, row.customer_id
            ),
        }


def _customer_changes(uow: UnitOfWork) -> Iterator[Cells]:
    """The log; each row has the source of the unit that wrote it,
    not the customer's."""
    for change in uow.customers.changes():
        yield {
            'seq': change.seq,
            'op': change.op,
            'customer_id': str(change.customer_id),
            'country': change.country,
            'postal_code': _text(change.postal_code),
            'changed_at': _utc(change.changed_at),
            'source': uow.customers.change_source(change.seq),
        }


def _subscriptions(uow: UnitOfWork) -> Iterator[Cells]:
    for sub in uow.subscriptions.all():
        yield {
            'subscription_id': str(sub.subscription_id),
            'customer_id': str(sub.customer_id),
            'product_id': str(sub.product_id),
            'started': sub.started,
            'ended': sub.ended,
            'source': uow.subscriptions.source_of(sub.subscription_id),
        }


def _categories(uow: UnitOfWork) -> Iterator[Cells]:
    for category in uow.catalogue.categories():
        yield {
            'category_id': str(category.category_id),
            'category_name': category.name,
            'parent_id': _text(category.parent_id),
            'sort_order': category.sort_order,
            'source': uow.catalogue.category_source(
                category.category_id
            ),
        }


def _kinds(uow: UnitOfWork) -> Iterator[Cells]:
    """Seeded with the schema, not written by a unit: no source."""
    for kind, name in KIND_NAMES.items():
        yield {'kind': kind, 'kind_name': name}


def _campaign_products(uow: UnitOfWork) -> Iterator[Cells]:
    for campaign in uow.catalogue.campaigns():
        source = uow.catalogue.campaign_source(campaign.campaign_id)
        for product_id in campaign.product_ids:
            yield {
                'campaign_id': str(campaign.campaign_id),
                'campaign_name': campaign.name,
                'product_id': str(product_id),
                'source': source,
            }


def _campaigns(uow: UnitOfWork) -> Iterator[Cells]:
    for campaign in uow.catalogue.campaigns():
        yield {
            'campaign_id': str(campaign.campaign_id),
            'campaign_name': campaign.name,
            'discount_pct': campaign.discount_pct,
            'first_day': campaign.first_day,
            'last_day': campaign.last_day,
            'source': uow.catalogue.campaign_source(
                campaign.campaign_id
            ),
        }


def _bean_details(uow: UnitOfWork) -> Iterator[Cells]:
    """The beans' subtype rows; the weight is in `products`."""
    for product in uow.catalogue.products():
        details = uow.catalogue.details(product.product_id)
        if isinstance(details, BeanDetails):
            yield {
                'product_id': str(product.product_id),
                'origin': details.origin,
                'roast': details.roast,
                'process': details.process,
                'source': uow.catalogue.product_source(
                    product.product_id
                ),
            }


def _equipment_details(uow: UnitOfWork) -> Iterator[Cells]:
    for product in uow.catalogue.products():
        details = uow.catalogue.details(product.product_id)
        if isinstance(details, EquipmentDetails):
            yield {
                'product_id': str(product.product_id),
                'warranty_months': details.warranty_months,
                'material': details.material,
                'source': uow.catalogue.product_source(
                    product.product_id
                ),
            }


def _subscription_events(uow: UnitOfWork) -> Iterator[Cells]:
    """The commands as kept; the app's `day` stays in the app."""
    subs = uow.subscriptions
    for sub in subs.all():
        for command in subs.events(sub.subscription_id):
            yield {
                'event_id': str(command.event_id),
                'subscription_id': str(command.subscription_id),
                'event_type': command.EVENT_TYPE,
                'reason': command.reason,
                'event_at': _utc(command.event_at),
                'source': subs.event_source(command.event_id),
            }


def _subscription_shipments(uow: UnitOfWork) -> Iterator[Cells]:
    """The bags; the app's `bag_id` is contract A's `shipment_id`."""
    subs = uow.subscriptions
    for sub in subs.all():
        for bag in subs.bags(sub.subscription_id):
            yield {
                'shipment_id': str(bag.bag_id),
                'subscription_id': str(bag.subscription_id),
                'product_id': str(bag.product_id),
                'shipped_on': bag.shipped_on,
                'qty': bag.qty,
                'source': subs.bag_source(bag.bag_id),
            }


def _stock_movements(uow: UnitOfWork) -> Iterator[Cells]:
    for product in uow.catalogue.products():
        for move in uow.stock.movements(product.product_id):
            yield {
                'movement_id': str(move.movement_id),
                'product_id': str(move.product_id),
                'moved_at': _utc(move.moved_at),
                'reason': move.reason,
                'qty': move.qty,
                'source': uow.stock.source_of(move.movement_id),
            }


def _green_purchases(uow: UnitOfWork) -> Iterator[Cells]:
    for purchase in uow.purchases.all():
        yield {
            'purchase_id': str(purchase.purchase_id),
            'bought_on': purchase.bought_on,
            'origin': purchase.origin,
            'kg': _cents(purchase.kg),
            'nok_per_kg': _nok(purchase.nok_per_kg),
            'source': uow.purchases.source_of(purchase.purchase_id),
        }


def _product_costs(uow: UnitOfWork) -> Iterator[Cells]:
    """The three amounts, in NOK; the app's currency column goes."""
    for product in uow.catalogue.products():
        for cost in uow.costs.of(product.product_id):
            yield {
                'product_id': str(cost.product_id),
                'valid_from': cost.valid_from,
                'valid_to': cost.valid_to,
                'green_nok': _nok(cost.green),
                'packaging_nok': _nok(cost.packaging),
                'roasting_nok': _nok(cost.roasting),
                'source': uow.costs.source_of(
                    cost.product_id, cost.valid_from
                ),
            }


def _shipments(uow: UnitOfWork) -> Iterator[Cells]:
    for shipment in uow.shipments.all():
        yield {
            'shipment_id': str(shipment.shipment_id),
            'order_id': str(shipment.order_id),
            'shipped_on': shipment.shipped_on,
            'promised_by': shipment.promised_by,
            'delivered_on': shipment.delivered_on,
            'source': uow.shipments.source_of(shipment.shipment_id),
        }


def _pricing_rules(uow: UnitOfWork) -> Iterator[Cells]:
    """The rules; the campaign a rule names stays in the app."""
    for rule in uow.rules.all():
        yield {
            'rule_id': str(rule.rule_id),
            'rule_kind': rule.rule_kind,
            'percent': rule.percent,
            'valid_from': rule.valid_from,
            'valid_to': rule.valid_to,
            'source': uow.rules.source_of(rule.rule_id),
        }


@dataclass(frozen=True)
class Projection:
    """One app table as contract A names it.

    `columns` are contract A's `columns`, then its `added`, then
    `source` where the app stamps the rows; `key` is contract A's.
    """

    name: str
    columns: tuple[str, ...]
    key: tuple[str, ...]
    read: Callable[[UnitOfWork], Iterable[Cells]]


APP_TABLES: Final[tuple[Projection, ...]] = (
    Projection(
        'customers',
        (
            'customer_id',
            'name',
            'country',
            'postal_code',
            'joined',
            'account_kind',
            'source',
        ),
        ('customer_id',),
        _customers,
    ),
    Projection(
        'products',
        (
            'product_id',
            'product_name',
            'kind',
            'category_id',
            'weight_g',
            'source',
        ),
        ('product_id',),
        _products,
    ),
    Projection(
        'orders',
        ('order_id', 'customer_id', 'order_date', 'channel', 'source'),
        ('order_id',),
        _orders,
    ),
    Projection(
        'order_lines',
        (
            'line_id',
            'order_id',
            'product_id',
            'qty',
            'unit_price',
            'source',
        ),
        ('line_id',),
        _order_lines,
    ),
    Projection(
        'prices',
        ('product_id', 'price', 'valid_from', 'valid_to', 'source'),
        ('product_id', 'valid_from'),
        _prices,
    ),
    Projection(
        'stock_daily',
        ('product_id', 'stock_date', 'on_hand', 'counted_at', 'source'),
        ('product_id', 'stock_date', 'counted_at'),
        _stock_daily,
    ),
    Projection(
        'customer_extracts',
        (
            'extract_date',
            'customer_id',
            'country',
            'postal_code',
            'source',
        ),
        ('extract_date', 'customer_id'),
        _customer_extracts,
    ),
    Projection(
        'customer_changes',
        (
            'seq',
            'op',
            'customer_id',
            'country',
            'postal_code',
            'changed_at',
            'source',
        ),
        ('seq',),
        _customer_changes,
    ),
    Projection(
        'line_stamps',
        (
            'line_id',
            'order_id',
            'qty',
            'is_deleted',
            'updated_at',
            'source',
        ),
        ('line_id',),
        _line_stamps,
    ),
    Projection(
        'subscriptions',
        (
            'subscription_id',
            'customer_id',
            'product_id',
            'started',
            'ended',
            'source',
        ),
        ('subscription_id',),
        _subscriptions,
    ),
    Projection(
        'categories',
        (
            'category_id',
            'category_name',
            'parent_id',
            'sort_order',
            'source',
        ),
        ('category_id',),
        _categories,
    ),
    Projection('kinds', ('kind', 'kind_name'), ('kind',), _kinds),
    Projection(
        'campaign_products',
        ('campaign_id', 'campaign_name', 'product_id', 'source'),
        ('campaign_id', 'product_id'),
        _campaign_products,
    ),
    Projection(
        'campaigns',
        (
            'campaign_id',
            'campaign_name',
            'discount_pct',
            'first_day',
            'last_day',
            'source',
        ),
        ('campaign_id',),
        _campaigns,
    ),
    Projection(
        'bean_details',
        ('product_id', 'origin', 'roast', 'process', 'source'),
        ('product_id',),
        _bean_details,
    ),
    Projection(
        'equipment_details',
        ('product_id', 'warranty_months', 'material', 'source'),
        ('product_id',),
        _equipment_details,
    ),
    Projection(
        'subscription_events',
        (
            'event_id',
            'subscription_id',
            'event_type',
            'reason',
            'event_at',
            'source',
        ),
        ('event_id',),
        _subscription_events,
    ),
    Projection(
        'subscription_shipments',
        (
            'shipment_id',
            'subscription_id',
            'product_id',
            'shipped_on',
            'qty',
            'source',
        ),
        ('shipment_id',),
        _subscription_shipments,
    ),
    Projection(
        'stock_movements',
        (
            'movement_id',
            'product_id',
            'moved_at',
            'reason',
            'qty',
            'source',
        ),
        ('movement_id',),
        _stock_movements,
    ),
    Projection(
        'green_purchases',
        (
            'purchase_id',
            'bought_on',
            'origin',
            'kg',
            'nok_per_kg',
            'source',
        ),
        ('purchase_id',),
        _green_purchases,
    ),
    Projection(
        'product_costs',
        (
            'product_id',
            'valid_from',
            'valid_to',
            'green_nok',
            'packaging_nok',
            'roasting_nok',
            'source',
        ),
        ('product_id', 'valid_from'),
        _product_costs,
    ),
    Projection(
        'shipments',
        (
            'shipment_id',
            'order_id',
            'shipped_on',
            'promised_by',
            'delivered_on',
            'source',
        ),
        ('shipment_id',),
        _shipments,
    ),
    Projection(
        'pricing_rules',
        (
            'rule_id',
            'rule_kind',
            'percent',
            'valid_from',
            'valid_to',
            'source',
        ),
        ('rule_id',),
        _pricing_rules,
    ),
)
"""Contract A's 23 app-database tables, in contract.py's order.
`payments` and `order_events` are not here: the provider and the
feed write them, not the app."""


def project(uow: UnitOfWork, table: Projection) -> Rows:
    """The table's rows in its columns' order, sorted by its key
    (by every column for a table with none)."""
    rows = []
    for cells in table.read(uow):
        if set(cells) != set(table.columns):
            raise ValueError(f'{table.name} read {sorted(cells)}')
        rows.append(tuple(cells[column] for column in table.columns))
    at = [table.columns.index(c) for c in table.key or table.columns]
    rows.sort(key=lambda row: tuple(row[i] for i in at))
    return Rows(table.name, table.columns, tuple(rows))


def app_tables(uow: UnitOfWork) -> Mapping[str, Rows]:
    """Every app-database table of contract A, read in one unit
    of work: table name to its rows (W2)."""
    with uow:
        return {table.name: project(uow, table) for table in APP_TABLES}
