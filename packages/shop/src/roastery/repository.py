"""The app's tables, kept twice: in dicts and in sqlite (ADR 0003).

Every repository of `ports` has a memory adapter and a sqlite one.
They take domain objects in and give them back; rows and SQL stay
in this module. Neither commits: the unit of work decides (`uow`).

The schema is the app's own, not contract A. It keeps contract A's
column names where a table is the same thing, and adds what only
the app holds: `source` on every row a unit of work writes, an
order's `vat_amount`, `credit_of` and cancel reason. The two Ids
adapters, `SequentialIds` and `ScriptedIds`, stand here too
(ADR 0007).

A store keeps what it is given. It does not look for the customer
behind an order or the product behind a movement: the services do.
A taken id raises `DuplicateId`, a missing one `UnknownId`; a
refused call writes nothing, on both stores.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields, replace
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Final

from roastery.catalogue import (
    BeanDetails,
    Category,
    EquipmentDetails,
    Kind,
    Product,
)
from roastery.commands import (
    Cancel,
    Command,
    Pause,
    Resume,
    Skip,
    replay,
)
from roastery.customer import (
    Customer,
    CustomerChange,
    Email,
    Op,
)
from roastery.errors import DuplicateId, UnknownId
from roastery.events import StatusChanged
from roastery.ids import (
    PREFIXES,
    BagId,
    CampaignId,
    CategoryId,
    CustomerId,
    LineId,
    MovementId,
    OrderId,
    PaymentId,
    PostalCode,
    ProductId,
    PurchaseId,
    RuleId,
    ShipmentId,
    SubEventId,
    SubscriptionId,
)
from roastery.money import Money, Qty
from roastery.order import (
    Cancelled,
    Delivered,
    Head,
    Invoiced,
    Order,
    OrderLine,
    Paid,
    Payment,
    Placed,
    Shipped,
    status,
)
from roastery.pipeline import ExportLine
from roastery.ports import (
    BagShipment,
    Booking,
    Campaign,
    Cost,
    Count,
    ExtractRow,
    GreenPurchase,
    IdKind,
    Ids,
    Movement,
    Shipment,
    Source,
)
from roastery.pricing import Discount, Price
from roastery.subscription import Subscription
from roastery.vat import SEED_RATES, VatRate

KIND_NAMES: Final[Mapping[Kind, str]] = MappingProxyType(
    {'beans': 'Coffee beans', 'equipment': 'Brewing equipment'}
)
"""`kinds.kind_name` of each product kind, as the baseline has it."""

WIDTHS: Final[Mapping[IdKind, int]] = MappingProxyType(
    {
        'customer': 5,
        'order': 6,
        'line': 7,
        'event': 7,
        'product': 3,
        'category': 3,
        'campaign': 3,
        'subscription': 5,
        'sub_event': 6,
        'shipment': 6,
        'bag': 6,
        'movement': 7,
        'purchase': 5,
        'rule': 4,
    }
)
"""The fixed width of the background trade's ids (ADR 0007, A6)."""

SCHEMA: Final = """
CREATE TABLE IF NOT EXISTS kinds (
    kind TEXT PRIMARY KEY,
    kind_name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS vat_rates (
    country TEXT NOT NULL,
    kind TEXT NOT NULL,
    rate TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    start_assumed INTEGER NOT NULL,
    PRIMARY KEY (country, kind, valid_from)
);
CREATE TABLE IF NOT EXISTS customers (
    customer_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT,
    country TEXT,
    postal_code TEXT,
    account_kind TEXT NOT NULL,
    joined TEXT NOT NULL,
    source TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS customer_changes (
    seq INTEGER PRIMARY KEY,
    op TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    country TEXT,
    postal_code TEXT,
    changed_at TEXT NOT NULL,
    source TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    country TEXT NOT NULL,
    credit_of TEXT,
    order_date TEXT NOT NULL,
    vat_amount TEXT NOT NULL,
    vat_currency TEXT NOT NULL,
    booked_at TEXT NOT NULL,
    status TEXT NOT NULL,
    payment_id TEXT,
    settled TEXT,
    shipment_id TEXT,
    cancel_reason TEXT,
    source TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS order_lines (
    line_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    line_no INTEGER NOT NULL,
    product_id TEXT NOT NULL,
    qty INTEGER NOT NULL,
    unit_price TEXT NOT NULL,
    currency TEXT NOT NULL,
    source TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS line_stamps (
    line_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    qty INTEGER NOT NULL,
    is_deleted INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    source TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS payments (
    payment_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    amount TEXT NOT NULL,
    currency TEXT NOT NULL,
    paid_on TEXT NOT NULL,
    source TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS categories (
    category_id TEXT PRIMARY KEY,
    category_name TEXT NOT NULL,
    parent_id TEXT,
    sort_order INTEGER NOT NULL,
    source TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS products (
    product_id TEXT PRIMARY KEY,
    product_name TEXT NOT NULL,
    kind TEXT NOT NULL,
    category_id TEXT NOT NULL,
    weight_g INTEGER,
    source TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bean_details (
    product_id TEXT PRIMARY KEY,
    origin TEXT NOT NULL,
    roast TEXT NOT NULL,
    process TEXT NOT NULL,
    source TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS equipment_details (
    product_id TEXT PRIMARY KEY,
    warranty_months INTEGER NOT NULL,
    material TEXT NOT NULL,
    source TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS campaigns (
    campaign_id TEXT PRIMARY KEY,
    campaign_name TEXT NOT NULL,
    discount_pct INTEGER NOT NULL,
    first_day TEXT NOT NULL,
    last_day TEXT NOT NULL,
    source TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS campaign_products (
    campaign_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    source TEXT NOT NULL,
    PRIMARY KEY (campaign_id, product_id)
);
CREATE TABLE IF NOT EXISTS prices (
    product_id TEXT NOT NULL,
    price TEXT NOT NULL,
    currency TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    source TEXT NOT NULL,
    PRIMARY KEY (product_id, valid_from)
);
CREATE TABLE IF NOT EXISTS product_costs (
    product_id TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    green TEXT NOT NULL,
    packaging TEXT NOT NULL,
    roasting TEXT NOT NULL,
    currency TEXT NOT NULL,
    source TEXT NOT NULL,
    PRIMARY KEY (product_id, valid_from)
);
CREATE TABLE IF NOT EXISTS pricing_rules (
    rule_id TEXT PRIMARY KEY,
    rule_kind TEXT NOT NULL,
    percent INTEGER NOT NULL,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    campaign_id TEXT,
    source TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS subscriptions (
    subscription_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    started TEXT NOT NULL,
    ended TEXT,
    source TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS subscription_events (
    event_id TEXT PRIMARY KEY,
    subscription_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    reason TEXT NOT NULL,
    event_at TEXT NOT NULL,
    source TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS subscription_shipments (
    bag_id TEXT PRIMARY KEY,
    subscription_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    shipped_on TEXT NOT NULL,
    qty INTEGER NOT NULL,
    source TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS stock_movements (
    movement_id TEXT PRIMARY KEY,
    product_id TEXT NOT NULL,
    moved_at TEXT NOT NULL,
    reason TEXT NOT NULL,
    qty INTEGER NOT NULL,
    source TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS stock_daily (
    product_id TEXT NOT NULL,
    stock_date TEXT NOT NULL,
    on_hand INTEGER NOT NULL,
    counted_at TEXT NOT NULL,
    source TEXT NOT NULL,
    PRIMARY KEY (product_id, stock_date, counted_at)
);
CREATE TABLE IF NOT EXISTS shipments (
    shipment_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    shipped_on TEXT NOT NULL,
    promised_by TEXT NOT NULL,
    delivered_on TEXT,
    source TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS green_purchases (
    purchase_id TEXT PRIMARY KEY,
    bought_on TEXT NOT NULL,
    origin TEXT NOT NULL,
    kg TEXT NOT NULL,
    nok_per_kg TEXT NOT NULL,
    currency TEXT NOT NULL,
    source TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS customer_extracts (
    extract_date TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    country TEXT,
    postal_code TEXT,
    source TEXT NOT NULL,
    PRIMARY KEY (extract_date, customer_id)
);
CREATE TABLE IF NOT EXISTS outbox (
    position INTEGER PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    order_id TEXT NOT NULL,
    status TEXT NOT NULL,
    event_at TEXT NOT NULL,
    batch INTEGER,
    sent INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL
);
"""
"""The app database: its own schema, not contract A (ADR 0003)."""


def create_tables(connection: sqlite3.Connection) -> None:
    """Make the tables and seed `kinds` and `vat_rates` (A18).

    Safe to run again: a table that exists is left as it is and a
    seed row that exists is not written twice. The seeds are
    committed, so the first unit of work can begin.
    """
    connection.executescript(SCHEMA)
    for kind in sorted(KIND_NAMES):
        connection.execute(
            'INSERT OR IGNORE INTO kinds VALUES (?, ?)',
            (kind, KIND_NAMES[kind]),
        )
    for rate in SEED_RATES:
        connection.execute(
            'INSERT OR IGNORE INTO vat_rates VALUES (?, ?, ?, ?, ?, ?)',
            (
                rate.country,
                rate.kind,
                str(rate.rate),
                rate.valid_from.isoformat(),
                _day(rate.valid_to),
                int(rate.start_assumed),
            ),
        )
    connection.commit()


# Text in, text out ----------------------------------------------


def moment_text(moment: dt.datetime) -> str:
    """UTC, ISO 8601: text that sorts as the moments do."""
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError('a moment must be timezone-aware')
    return moment.astimezone(dt.UTC).isoformat()


def moment_from(text: str) -> dt.datetime:
    return dt.datetime.fromisoformat(text)


def _day(day: dt.date | None) -> str | None:
    return None if day is None else day.isoformat()


def _date(text: str) -> dt.date:
    return dt.date.fromisoformat(text)


def _date_or_none(text: str | None) -> dt.date | None:
    return None if text is None else dt.date.fromisoformat(text)


def _money(text: str, currency: str) -> Money:
    return Money(Decimal(text), currency)


def _ids(items: Sequence[object]) -> tuple[str, ...]:
    return tuple(str(item) for item in items)


# What the memory store holds ---------------------------------------


@dataclass(frozen=True)
class OrderRow:
    """An order, its booking, and the cancel that deleted its lines."""

    order: Order
    booking: Booking
    source: Source
    deleted_at: dt.datetime | None = None


@dataclass(frozen=True)
class OutboxRow:
    """One row of the outbox: the event, its batch, whether sent."""

    event: StatusChanged
    batch: int | None
    sent: bool
    source: Source


@dataclass
class Tables:
    """One dict per table: what a memory store holds.

    The units of work copy each dict at open and put the copies
    back (A22). Values are frozen, so a shallow copy is a copy.
    """

    customers: dict[str, tuple[Customer, Source]] = field(
        default_factory=dict
    )
    changes: dict[int, tuple[CustomerChange, Source]] = field(
        default_factory=dict
    )
    orders: dict[str, OrderRow] = field(default_factory=dict)
    line_owner: dict[str, str] = field(default_factory=dict)
    payments: dict[str, tuple[Payment, Source]] = field(
        default_factory=dict
    )
    categories: dict[str, tuple[Category, Source]] = field(
        default_factory=dict
    )
    products: dict[
        str, tuple[Product, BeanDetails | EquipmentDetails, Source]
    ] = field(default_factory=dict)
    campaigns: dict[str, tuple[Campaign, Source]] = field(
        default_factory=dict
    )
    prices: dict[tuple[str, dt.date], tuple[Price, Source]] = field(
        default_factory=dict
    )
    costs: dict[tuple[str, dt.date], tuple[Cost, Source]] = field(
        default_factory=dict
    )
    rules: dict[str, tuple[Discount, str | None, Source]] = field(
        default_factory=dict
    )
    subscriptions: dict[str, tuple[Subscription, Source]] = field(
        default_factory=dict
    )
    sub_events: dict[str, tuple[Command, Source]] = field(
        default_factory=dict
    )
    bags: dict[str, tuple[BagShipment, Source]] = field(
        default_factory=dict
    )
    movements: dict[str, tuple[Movement, Source]] = field(
        default_factory=dict
    )
    counts: dict[
        tuple[str, dt.date, dt.datetime], tuple[Count, Source]
    ] = field(default_factory=dict)
    shipments: dict[str, tuple[Shipment, Source]] = field(
        default_factory=dict
    )
    purchases: dict[str, tuple[GreenPurchase, Source]] = field(
        default_factory=dict
    )
    vat_rates: dict[tuple[str, str, dt.date], VatRate] = field(
        default_factory=dict
    )
    extracts: dict[tuple[dt.date, str], tuple[ExtractRow, Source]] = (
        field(default_factory=dict)
    )
    outbox: dict[int, OutboxRow] = field(default_factory=dict)

    @classmethod
    def seeded(cls) -> Tables:
        """Empty tables with the VAT rows the schema seeds (A18)."""
        tables = cls()
        for rate in SEED_RATES:
            key = (rate.country, rate.kind, rate.valid_from)
            tables.vat_rates[key] = rate
        return tables

    def snapshot(self) -> dict[str, dict[Any, Any]]:
        """A copy of every dict, by table name."""
        return {
            each.name: dict(getattr(self, each.name))
            for each in fields(self)
        }

    def restore(self, kept: Mapping[str, dict[Any, Any]]) -> None:
        """Put the copies back, into the dicts the repositories
        already hold."""
        for each in fields(self):
            table = getattr(self, each.name)
            table.clear()
            table.update(kept[each.name])


# Orders: one row of the app, six states --------------------------


def _flat(
    order: Order,
) -> tuple[str, str | None, str | None, str | None, str | None]:
    """The columns that tell the states apart: payment id, how it
    was settled, shipment id, cancel reason."""
    match order:
        case Paid(payment_id=payment_id):
            return status(order), str(payment_id), None, None, None
        case Shipped(settled=settled, shipment_id=shipment_id) | (
            Delivered(settled=settled, shipment_id=shipment_id)
        ):
            if isinstance(settled, Paid):
                paid = str(settled.payment_id)
                return (
                    status(order),
                    paid,
                    'paid',
                    str(shipment_id),
                    None,
                )
            return (
                status(order),
                None,
                'invoiced',
                str(shipment_id),
                None,
            )
        case Cancelled(reason=reason):
            return status(order), None, None, None, reason
        case _:
            return status(order), None, None, None, None


def _rebuild(
    head: Head,
    word: str,
    payment_id: str | None,
    settled: str | None,
    shipment_id: str | None,
    reason: str | None,
) -> Order:
    """The state a row of `orders` stands for."""
    match word:
        case 'placed':
            return Placed(head)
        case 'invoiced':
            return Invoiced(head)
        case 'paid':
            return Paid(head, PaymentId(str(payment_id)))
        case 'shipped' | 'delivered':
            by: Paid | Invoiced = (
                Paid(head, PaymentId(str(payment_id)))
                if settled == 'paid'
                else Invoiced(head)
            )
            arrive = Shipped if word == 'shipped' else Delivered
            return arrive(by, ShipmentId(str(shipment_id)))
        case 'cancelled':
            return Cancelled(head, str(reason))
        case _:
            raise ValueError(f'the feed has no status {word!r}')


def _refuse_lines_taken(order: Order, taken: Sequence[str]) -> None:
    """DuplicateId for the first line id already held."""
    for line in order.head.lines:
        if str(line.line_id) in taken:
            raise DuplicateId('line', str(line.line_id))


# Memory adapters ------------------------------------------------------


class _MemoryRepo:
    """What every memory repository holds: the tables, the source."""

    def __init__(self, tables: Tables, source: Source) -> None:
        self._t = tables
        self._source = source


class MemoryCustomers(_MemoryRepo):
    def add(self, customer: Customer, at: dt.datetime) -> None:
        key = str(customer.customer_id)
        if key in self._t.customers:
            raise DuplicateId('customer', key)
        self._t.customers[key] = (customer, self._source)
        self._log('insert', customer, at)

    def get(self, customer_id: CustomerId) -> Customer:
        return self._held(customer_id)[0]

    def change(self, customer: Customer, at: dt.datetime) -> None:
        key = str(customer.customer_id)
        _, source = self._held(customer.customer_id)
        self._t.customers[key] = (customer, source)
        self._log('update', customer, at)

    def erase(self, customer_id: CustomerId, at: dt.datetime) -> None:
        self._held(customer_id)
        del self._t.customers[str(customer_id)]
        row = CustomerChange(
            self._next_seq(), 'delete', customer_id, None, None, at
        )
        self._t.changes[row.seq] = (row, self._source)

    def all(self) -> tuple[Customer, ...]:
        keys = sorted(self._t.customers)
        return tuple(self._t.customers[key][0] for key in keys)

    def changes(self) -> tuple[CustomerChange, ...]:
        return tuple(
            self._t.changes[seq][0] for seq in sorted(self._t.changes)
        )

    def source_of(self, customer_id: CustomerId) -> Source:
        return self._held(customer_id)[1]

    def _held(self, customer_id: CustomerId) -> tuple[Customer, Source]:
        key = str(customer_id)
        if key not in self._t.customers:
            raise UnknownId('customer', key)
        return self._t.customers[key]

    def _next_seq(self) -> int:
        return max(self._t.changes, default=0) + 1

    def _log(self, op: Op, customer: Customer, at: dt.datetime) -> None:
        row = CustomerChange(
            self._next_seq(),
            op,
            customer.customer_id,
            customer.country,
            customer.postal_code,
            at,
        )
        self._t.changes[row.seq] = (row, self._source)


class MemoryOrders(_MemoryRepo):
    def add(self, order: Order, booking: Booking) -> None:
        key = str(order.head.order_id)
        if key in self._t.orders:
            raise DuplicateId('order', key)
        _refuse_lines_taken(order, tuple(self._t.line_owner))
        self._t.orders[key] = OrderRow(order, booking, self._source)
        for line in order.head.lines:
            self._t.line_owner[str(line.line_id)] = key

    def get(self, order_id: OrderId) -> Order:
        return self._row(order_id).order

    def save(self, order: Order) -> None:
        row = self._row(order.head.order_id)
        self._t.orders[str(order.head.order_id)] = replace(
            row, order=order
        )

    def all(self) -> tuple[Order, ...]:
        keys = sorted(self._t.orders)
        return tuple(self._t.orders[key].order for key in keys)

    def booking(self, order_id: OrderId) -> Booking:
        return self._row(order_id).booking

    def credits_of(self, order_id: OrderId) -> tuple[Order, ...]:
        return tuple(
            order
            for order in self.all()
            if order.head.credit_of == order_id
        )

    def mark_deleted(self, order_id: OrderId, at: dt.datetime) -> None:
        row = self._row(order_id)
        self._t.orders[str(order_id)] = replace(row, deleted_at=at)

    def deleted_at(self, order_id: OrderId) -> dt.datetime | None:
        return self._row(order_id).deleted_at

    def lines(self) -> tuple[ExportLine, ...]:
        found = [
            ExportLine(
                line.line_id,
                row.order.head.order_id,
                line.product_id,
                line.qty,
                line.unit_price,
                row.deleted_at is not None,
            )
            for row in self._t.orders.values()
            for line in row.order.head.lines
        ]
        return tuple(sorted(found, key=lambda line: str(line.line_id)))

    def source_of(self, order_id: OrderId) -> Source:
        return self._row(order_id).source

    def _row(self, order_id: OrderId) -> OrderRow:
        key = str(order_id)
        if key not in self._t.orders:
            raise UnknownId('order', key)
        return self._t.orders[key]


class MemoryPayments(_MemoryRepo):
    def add(self, payment: Payment) -> None:
        key = str(payment.payment_id)
        if key in self._t.payments:
            raise DuplicateId('payment', key)
        self._t.payments[key] = (payment, self._source)

    def find(self, payment_id: PaymentId) -> Payment | None:
        held = self._t.payments.get(str(payment_id))
        return None if held is None else held[0]

    def of(self, order_id: OrderId) -> tuple[Payment, ...]:
        found = [
            payment
            for payment, _ in self._t.payments.values()
            if payment.order_id == order_id
        ]
        return tuple(sorted(found, key=lambda p: str(p.payment_id)))


def _check_details(
    product: Product, details: BeanDetails | EquipmentDetails
) -> None:
    """Beans come with bean details, equipment with its own."""
    beans = isinstance(details, BeanDetails)
    if (product.kind == 'beans') != beans:
        raise ValueError(
            f'product {product.product_id} is {product.kind}: '
            f'it cannot take {type(details).__name__}'
        )


class MemoryCatalogue(_MemoryRepo):
    def add_category(self, category: Category) -> None:
        key = str(category.category_id)
        if key in self._t.categories:
            raise DuplicateId('category', key)
        self._t.categories[key] = (category, self._source)

    def categories(self) -> tuple[Category, ...]:
        keys = sorted(self._t.categories)
        return tuple(self._t.categories[key][0] for key in keys)

    def add_product(
        self, product: Product, details: BeanDetails | EquipmentDetails
    ) -> None:
        key = str(product.product_id)
        _check_details(product, details)
        if key in self._t.products:
            raise DuplicateId('product', key)
        self._t.products[key] = (product, details, self._source)

    def product(self, product_id: ProductId) -> Product:
        key = str(product_id)
        if key not in self._t.products:
            raise UnknownId('product', key)
        return self._t.products[key][0]

    def products(self) -> tuple[Product, ...]:
        keys = sorted(self._t.products)
        return tuple(self._t.products[key][0] for key in keys)

    def add_campaign(self, campaign: Campaign) -> None:
        key = str(campaign.campaign_id)
        if key in self._t.campaigns:
            raise DuplicateId('campaign', key)
        self._t.campaigns[key] = (campaign, self._source)


class MemoryPrices(_MemoryRepo):
    def of(self, product_id: ProductId) -> tuple[Price, ...]:
        found = [
            price
            for (key, _), (price, _) in self._t.prices.items()
            if key == str(product_id)
        ]
        return tuple(sorted(found, key=lambda p: p.valid_from))

    def add(self, price: Price) -> None:
        key = (str(price.product_id), price.valid_from)
        if key in self._t.prices:
            raise DuplicateId('price', f'{key[0]} {key[1]}')
        self._t.prices[key] = (price, self._source)

    def close(self, product_id: ProductId, valid_to: dt.date) -> None:
        opened = [
            key
            for key, (price, _) in self._t.prices.items()
            if key[0] == str(product_id) and price.valid_to is None
        ]
        if not opened:
            raise UnknownId('price', str(product_id))
        key = max(opened, key=lambda each: each[1])
        price, source = self._t.prices[key]
        self._t.prices[key] = (
            replace(price, valid_to=valid_to),
            source,
        )


def _one_currency(cost: Cost) -> str:
    """A cost row has one currency; its three parts must agree."""
    currencies = {
        cost.green.currency,
        cost.packaging.currency,
        cost.roasting.currency,
    }
    if len(currencies) != 1:
        raise ValueError('a cost row is in one currency')
    return currencies.pop()


class MemoryCosts(_MemoryRepo):
    def of(self, product_id: ProductId) -> tuple[Cost, ...]:
        found = [
            cost
            for (key, _), (cost, _) in self._t.costs.items()
            if key == str(product_id)
        ]
        return tuple(sorted(found, key=lambda c: c.valid_from))

    def add(self, cost: Cost) -> None:
        _one_currency(cost)
        key = (str(cost.product_id), cost.valid_from)
        if key in self._t.costs:
            raise DuplicateId('cost', f'{key[0]} {key[1]}')
        self._t.costs[key] = (cost, self._source)

    def close(self, product_id: ProductId, valid_to: dt.date) -> None:
        opened = [
            key
            for key, (cost, _) in self._t.costs.items()
            if key[0] == str(product_id) and cost.valid_to is None
        ]
        if not opened:
            raise UnknownId('cost', str(product_id))
        key = max(opened, key=lambda each: each[1])
        cost, source = self._t.costs[key]
        _check_period(cost.valid_from, valid_to)
        self._t.costs[key] = (replace(cost, valid_to=valid_to), source)


def _check_period(valid_from: dt.date, valid_to: dt.date) -> None:
    """A closed period ends after it starts (as `Price` holds)."""
    if valid_to <= valid_from:
        raise ValueError('a period must end after it starts')


def _check_rule(rule: Discount, campaign_id: CampaignId | None) -> None:
    """Only a campaign's rule names a campaign, and it must."""
    if (rule.rule_kind == 'campaign') != (campaign_id is not None):
        raise ValueError('only a campaign rule names its campaign')


class MemoryRules(_MemoryRepo):
    def add(
        self, rule: Discount, *, campaign_id: CampaignId | None = None
    ) -> None:
        key = str(rule.rule_id)
        _check_rule(rule, campaign_id)
        if key in self._t.rules:
            raise DuplicateId('rule', key)
        if campaign_id is not None and (
            str(campaign_id) not in self._t.campaigns
        ):
            raise UnknownId('campaign', str(campaign_id))
        named = None if campaign_id is None else str(campaign_id)
        self._t.rules[key] = (rule, named, self._source)

    def close(self, rule_id: RuleId, valid_to: dt.date) -> None:
        key = str(rule_id)
        if key not in self._t.rules:
            raise UnknownId('rule', key)
        rule, campaign, source = self._t.rules[key]
        _check_period(rule.valid_from, valid_to)
        closed = replace(rule, valid_to=valid_to)
        self._t.rules[key] = (closed, campaign, source)

    def all(self) -> tuple[Discount, ...]:
        found: list[Discount] = []
        for key in sorted(self._t.rules):
            rule, campaign, _ = self._t.rules[key]
            if campaign is not None:
                held = self._t.campaigns[campaign][0].product_ids
                rule = replace(rule, product_ids=frozenset(held))
            found.append(rule)
        return tuple(found)


class MemorySubscriptions(_MemoryRepo):
    def add(self, sub: Subscription) -> None:
        key = str(sub.subscription_id)
        if key in self._t.subscriptions:
            raise DuplicateId('subscription', key)
        self._t.subscriptions[key] = (sub, self._source)

    def get(self, subscription_id: SubscriptionId) -> Subscription:
        key = str(subscription_id)
        if key not in self._t.subscriptions:
            raise UnknownId('subscription', key)
        started = self._t.subscriptions[key][0]
        held = sorted(
            (
                command
                for command, _ in self._t.sub_events.values()
                if command.subscription_id == subscription_id
            ),
            key=lambda c: (c.event_at, str(c.event_id)),
        )
        return replay(started, held)

    def of_customer(
        self, customer_id: CustomerId
    ) -> tuple[Subscription, ...]:
        return tuple(
            self.get(sub.subscription_id)
            for sub in self._started()
            if sub.customer_id == customer_id
        )

    def all(self) -> tuple[Subscription, ...]:
        return tuple(
            self.get(sub.subscription_id) for sub in self._started()
        )

    def record(self, command: Command) -> None:
        key = str(command.event_id)
        if str(command.subscription_id) not in self._t.subscriptions:
            raise UnknownId(
                'subscription', str(command.subscription_id)
            )
        if key in self._t.sub_events:
            raise DuplicateId('sub_event', key)
        self._t.sub_events[key] = (command, self._source)

    def bags(
        self, subscription_id: SubscriptionId
    ) -> tuple[BagShipment, ...]:
        found = [
            bag
            for bag, _ in self._t.bags.values()
            if bag.subscription_id == subscription_id
        ]
        return tuple(
            sorted(found, key=lambda b: (b.shipped_on, str(b.bag_id)))
        )

    def add_bag(self, bag: BagShipment) -> None:
        key = str(bag.bag_id)
        if key in self._t.bags:
            raise DuplicateId('bag', key)
        self._t.bags[key] = (bag, self._source)

    def _started(self) -> list[Subscription]:
        keys = sorted(self._t.subscriptions)
        return [self._t.subscriptions[key][0] for key in keys]


class MemoryStock(_MemoryRepo):
    def add(self, movement: Movement) -> None:
        key = str(movement.movement_id)
        if key in self._t.movements:
            raise DuplicateId('movement', key)
        self._t.movements[key] = (movement, self._source)

    def on_hand(
        self,
        product_id: ProductId,
        *,
        before: dt.datetime | None = None,
    ) -> int:
        return sum(
            move.qty
            for move in self.movements(product_id)
            if before is None or move.moved_at < before
        )

    def movements(self, product_id: ProductId) -> tuple[Movement, ...]:
        found = [
            move
            for move, _ in self._t.movements.values()
            if move.product_id == product_id
        ]
        return tuple(
            sorted(
                found, key=lambda m: (m.moved_at, str(m.movement_id))
            )
        )

    def add_count(self, count: Count) -> None:
        key = (
            str(count.product_id),
            count.stock_date,
            count.counted_at,
        )
        if key in self._t.counts:
            raise DuplicateId(
                'count', f'{key[0]} {key[1]} {moment_text(key[2])}'
            )
        self._t.counts[key] = (count, self._source)

    def counts(self, stock_date: dt.date) -> tuple[Count, ...]:
        found = [
            count
            for count, _ in self._t.counts.values()
            if count.stock_date == stock_date
        ]
        return tuple(
            sorted(
                found, key=lambda c: (str(c.product_id), c.counted_at)
            )
        )

    def source_of(self, movement_id: MovementId) -> Source:
        key = str(movement_id)
        if key not in self._t.movements:
            raise UnknownId('movement', key)
        return self._t.movements[key][1]


class MemoryShipments(_MemoryRepo):
    def add(self, shipment: Shipment) -> None:
        key = str(shipment.shipment_id)
        if key in self._t.shipments:
            raise DuplicateId('shipment', key)
        self._t.shipments[key] = (shipment, self._source)

    def get(self, shipment_id: ShipmentId) -> Shipment:
        key = str(shipment_id)
        if key not in self._t.shipments:
            raise UnknownId('shipment', key)
        return self._t.shipments[key][0]

    def save(self, shipment: Shipment) -> None:
        key = str(shipment.shipment_id)
        if key not in self._t.shipments:
            raise UnknownId('shipment', key)
        source = self._t.shipments[key][1]
        self._t.shipments[key] = (shipment, source)


class MemoryPurchases(_MemoryRepo):
    def add(self, purchase: GreenPurchase) -> None:
        key = str(purchase.purchase_id)
        if key in self._t.purchases:
            raise DuplicateId('purchase', key)
        self._t.purchases[key] = (purchase, self._source)

    def all(self) -> tuple[GreenPurchase, ...]:
        keys = sorted(self._t.purchases)
        return tuple(self._t.purchases[key][0] for key in keys)


class MemoryVatRates(_MemoryRepo):
    def all(self) -> tuple[VatRate, ...]:
        return tuple(
            self._t.vat_rates[key] for key in sorted(self._t.vat_rates)
        )


def _extract_keys(
    day: dt.date, rows: Sequence[ExtractRow]
) -> list[tuple[dt.date, str]]:
    """The rows' keys; a row of another day, or twice, is refused."""
    keys: list[tuple[dt.date, str]] = []
    for row in rows:
        if row.extract_date != day:
            raise ValueError(f'a row of {row.extract_date} in {day}')
        key = (day, str(row.customer_id))
        if key in keys:
            raise DuplicateId('extract', f'{day} {key[1]}')
        keys.append(key)
    return keys


class MemoryExtracts(_MemoryRepo):
    def replace(self, day: dt.date, rows: Sequence[ExtractRow]) -> None:
        keys = _extract_keys(day, rows)
        for key in [k for k in self._t.extracts if k[0] == day]:
            del self._t.extracts[key]
        for key, row in zip(keys, rows, strict=True):
            self._t.extracts[key] = (row, self._source)

    def on(self, day: dt.date) -> tuple[ExtractRow, ...]:
        found = [
            row
            for (when, _), (row, _) in self._t.extracts.items()
            if when == day
        ]
        return tuple(sorted(found, key=lambda r: str(r.customer_id)))


# Sqlite adapters ------------------------------------------------------


class _SqliteRepo:
    """What every sqlite repository holds: the connection and the
    source it stamps. It never commits."""

    def __init__(
        self, connection: sqlite3.Connection, source: Source
    ) -> None:
        self._db = connection
        self._source = source

    def _rows(
        self, sql: str, params: Sequence[object] = ()
    ) -> list[tuple[Any, ...]]:
        return self._db.execute(sql, params).fetchall()

    def _exists(
        self, table: str, where: str, params: Sequence[object]
    ) -> bool:
        found = self._db.execute(
            f'SELECT 1 FROM {table} WHERE {where}', params
        ).fetchone()
        return found is not None

    def _taken(
        self,
        kind: str,
        table: str,
        column: str,
        value: str,
    ) -> None:
        if self._exists(table, f'{column} = ?', (value,)):
            raise DuplicateId(kind, value)

    def _missing(
        self, kind: str, table: str, column: str, value: str
    ) -> None:
        if not self._exists(table, f'{column} = ?', (value,)):
            raise UnknownId(kind, value)


class SqliteCustomers(_SqliteRepo):
    def add(self, customer: Customer, at: dt.datetime) -> None:
        key = str(customer.customer_id)
        self._taken('customer', 'customers', 'customer_id', key)
        self._db.execute(
            'INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (
                key,
                customer.name,
                None
                if customer.email is None
                else customer.email.value,
                customer.country,
                _postal(customer.postal_code),
                customer.account_kind,
                customer.joined.isoformat(),
                self._source,
            ),
        )
        self._log('insert', customer.customer_id, customer, at)

    def get(self, customer_id: CustomerId) -> Customer:
        key = str(customer_id)
        rows = self._rows(
            'SELECT customer_id, name, email, country, postal_code,'
            ' account_kind, joined FROM customers'
            ' WHERE customer_id = ? ORDER BY customer_id',
            (key,),
        )
        if not rows:
            raise UnknownId('customer', key)
        return _customer(rows[0])

    def change(self, customer: Customer, at: dt.datetime) -> None:
        key = str(customer.customer_id)
        self._missing('customer', 'customers', 'customer_id', key)
        self._db.execute(
            'UPDATE customers SET name = ?, email = ?, country = ?,'
            ' postal_code = ?, account_kind = ?, joined = ?'
            ' WHERE customer_id = ?',
            (
                customer.name,
                None
                if customer.email is None
                else customer.email.value,
                customer.country,
                _postal(customer.postal_code),
                customer.account_kind,
                customer.joined.isoformat(),
                key,
            ),
        )
        self._log('update', customer.customer_id, customer, at)

    def erase(self, customer_id: CustomerId, at: dt.datetime) -> None:
        key = str(customer_id)
        self._missing('customer', 'customers', 'customer_id', key)
        self._db.execute(
            'DELETE FROM customers WHERE customer_id = ?', (key,)
        )
        self._log('delete', customer_id, None, at)

    def all(self) -> tuple[Customer, ...]:
        rows = self._rows(
            'SELECT customer_id, name, email, country, postal_code,'
            ' account_kind, joined FROM customers'
            ' ORDER BY customer_id'
        )
        return tuple(_customer(row) for row in rows)

    def changes(self) -> tuple[CustomerChange, ...]:
        rows = self._rows(
            'SELECT seq, op, customer_id, country, postal_code,'
            ' changed_at FROM customer_changes ORDER BY seq'
        )
        return tuple(
            CustomerChange(
                seq,
                op,
                CustomerId(who),
                country,
                _postal_code(postal_code),
                moment_from(changed_at),
            )
            for seq, op, who, country, postal_code, changed_at in rows
        )

    def source_of(self, customer_id: CustomerId) -> Source:
        key = str(customer_id)
        rows = self._rows(
            'SELECT source FROM customers WHERE customer_id = ?'
            ' ORDER BY customer_id',
            (key,),
        )
        if not rows:
            raise UnknownId('customer', key)
        return rows[0][0]

    def _log(
        self,
        op: Op,
        customer_id: CustomerId,
        customer: Customer | None,
        at: dt.datetime,
    ) -> None:
        (last,) = self._db.execute(
            'SELECT COALESCE(MAX(seq), 0) FROM customer_changes'
        ).fetchone()
        country = None if customer is None else customer.country
        postal = None if customer is None else customer.postal_code
        self._db.execute(
            'INSERT INTO customer_changes VALUES (?, ?, ?, ?, ?, ?, ?)',
            (
                last + 1,
                op,
                str(customer_id),
                country,
                _postal(postal),
                moment_text(at),
                self._source,
            ),
        )


def _postal(code: PostalCode | None) -> str | None:
    return None if code is None else code.value


def _postal_code(text: str | None) -> PostalCode | None:
    return None if text is None else PostalCode(text)


def _customer(row: tuple[Any, ...]) -> Customer:
    customer_id, name, email, country, postal, account, joined = row
    return Customer(
        CustomerId(customer_id),
        name,
        None if email is None else Email(email),
        country,
        _postal_code(postal),
        account,
        _date(joined),
    )


class SqliteOrders(_SqliteRepo):
    def add(self, order: Order, booking: Booking) -> None:
        head = order.head
        key = str(head.order_id)
        self._taken('order', 'orders', 'order_id', key)
        for line in head.lines:
            self._taken(
                'line', 'order_lines', 'line_id', str(line.line_id)
            )
        word, payment_id, settled, shipment_id, reason = _flat(order)
        self._db.execute(
            'INSERT INTO orders VALUES'
            ' (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (
                key,
                str(head.customer_id),
                head.channel,
                head.country,
                None if head.credit_of is None else str(head.credit_of),
                booking.order_date.isoformat(),
                str(booking.vat_amount.amount),
                booking.vat_amount.currency,
                moment_text(booking.at),
                word,
                payment_id,
                settled,
                shipment_id,
                reason,
                self._source,
            ),
        )
        for number, line in enumerate(head.lines, start=1):
            self._db.execute(
                'INSERT INTO order_lines VALUES'
                ' (?, ?, ?, ?, ?, ?, ?, ?)',
                (
                    str(line.line_id),
                    key,
                    number,
                    str(line.product_id),
                    line.qty.value,
                    str(line.unit_price.amount),
                    line.unit_price.currency,
                    self._source,
                ),
            )
            self._db.execute(
                'INSERT INTO line_stamps VALUES (?, ?, ?, ?, ?, ?)',
                (
                    str(line.line_id),
                    key,
                    line.qty.value,
                    0,
                    moment_text(booking.at),
                    self._source,
                ),
            )

    def get(self, order_id: OrderId) -> Order:
        key = str(order_id)
        rows = self._rows(
            'SELECT order_id, customer_id, channel, country, credit_of,'
            ' status, payment_id, settled, shipment_id, cancel_reason'
            ' FROM orders WHERE order_id = ? ORDER BY order_id',
            (key,),
        )
        if not rows:
            raise UnknownId('order', key)
        return self._order(rows[0])

    def save(self, order: Order) -> None:
        key = str(order.head.order_id)
        self._missing('order', 'orders', 'order_id', key)
        word, payment_id, settled, shipment_id, reason = _flat(order)
        self._db.execute(
            'UPDATE orders SET status = ?, payment_id = ?,'
            ' settled = ?, shipment_id = ?, cancel_reason = ?'
            ' WHERE order_id = ?',
            (word, payment_id, settled, shipment_id, reason, key),
        )

    def all(self) -> tuple[Order, ...]:
        rows = self._rows(
            'SELECT order_id, customer_id, channel, country, credit_of,'
            ' status, payment_id, settled, shipment_id, cancel_reason'
            ' FROM orders ORDER BY order_id'
        )
        return tuple(self._order(row) for row in rows)

    def booking(self, order_id: OrderId) -> Booking:
        key = str(order_id)
        rows = self._rows(
            'SELECT order_date, vat_amount, vat_currency, booked_at'
            ' FROM orders WHERE order_id = ? ORDER BY order_id',
            (key,),
        )
        if not rows:
            raise UnknownId('order', key)
        order_date, amount, currency, booked_at = rows[0]
        return Booking(
            _date(order_date),
            _money(amount, currency),
            moment_from(booked_at),
        )

    def credits_of(self, order_id: OrderId) -> tuple[Order, ...]:
        rows = self._rows(
            'SELECT order_id, customer_id, channel, country, credit_of,'
            ' status, payment_id, settled, shipment_id, cancel_reason'
            ' FROM orders WHERE credit_of = ? ORDER BY order_id',
            (str(order_id),),
        )
        return tuple(self._order(row) for row in rows)

    def mark_deleted(self, order_id: OrderId, at: dt.datetime) -> None:
        key = str(order_id)
        self._missing('order', 'orders', 'order_id', key)
        self._db.execute(
            'UPDATE line_stamps SET is_deleted = 1, updated_at = ?'
            ' WHERE order_id = ?',
            (moment_text(at), key),
        )

    def deleted_at(self, order_id: OrderId) -> dt.datetime | None:
        key = str(order_id)
        self._missing('order', 'orders', 'order_id', key)
        (stamp,) = self._db.execute(
            'SELECT MAX(updated_at) FROM line_stamps'
            ' WHERE order_id = ? AND is_deleted = 1',
            (key,),
        ).fetchone()
        return None if stamp is None else moment_from(stamp)

    def lines(self) -> tuple[ExportLine, ...]:
        rows = self._rows(
            'SELECT l.line_id, l.order_id, l.product_id, l.qty,'
            ' l.unit_price, l.currency, s.is_deleted'
            ' FROM order_lines AS l JOIN line_stamps AS s'
            ' ON s.line_id = l.line_id ORDER BY l.line_id'
        )
        return tuple(
            ExportLine(
                LineId(row[0]),
                OrderId(row[1]),
                ProductId(row[2]),
                Qty(row[3]),
                _money(row[4], row[5]),
                bool(row[6]),
            )
            for row in rows
        )

    def source_of(self, order_id: OrderId) -> Source:
        key = str(order_id)
        rows = self._rows(
            'SELECT source FROM orders WHERE order_id = ?'
            ' ORDER BY order_id',
            (key,),
        )
        if not rows:
            raise UnknownId('order', key)
        return rows[0][0]

    def _order(self, row: tuple[Any, ...]) -> Order:
        order_id, customer, channel, country, credit = row[:5]
        lines = tuple(
            OrderLine(
                LineId(line_id),
                ProductId(product_id),
                Qty(qty),
                _money(price, currency),
            )
            for line_id, product_id, qty, price, currency in self._rows(
                'SELECT line_id, product_id, qty, unit_price, currency'
                ' FROM order_lines WHERE order_id = ? ORDER BY line_no',
                (order_id,),
            )
        )
        head = Head(
            OrderId(order_id),
            CustomerId(customer),
            channel,
            country,
            lines,
            None if credit is None else OrderId(credit),
        )
        return _rebuild(head, *row[5:])


class SqlitePayments(_SqliteRepo):
    def add(self, payment: Payment) -> None:
        key = str(payment.payment_id)
        self._taken('payment', 'payments', 'payment_id', key)
        self._db.execute(
            'INSERT INTO payments VALUES (?, ?, ?, ?, ?, ?)',
            (
                key,
                str(payment.order_id),
                str(payment.amount.amount),
                payment.amount.currency,
                payment.paid_on.isoformat(),
                self._source,
            ),
        )

    def find(self, payment_id: PaymentId) -> Payment | None:
        rows = self._rows(
            'SELECT payment_id, order_id, amount, currency, paid_on'
            ' FROM payments WHERE payment_id = ? ORDER BY payment_id',
            (str(payment_id),),
        )
        return _payment(rows[0]) if rows else None

    def of(self, order_id: OrderId) -> tuple[Payment, ...]:
        rows = self._rows(
            'SELECT payment_id, order_id, amount, currency, paid_on'
            ' FROM payments WHERE order_id = ? ORDER BY payment_id',
            (str(order_id),),
        )
        return tuple(_payment(row) for row in rows)


def _payment(row: tuple[Any, ...]) -> Payment:
    payment_id, order_id, amount, currency, paid_on = row
    return Payment(
        PaymentId(payment_id),
        OrderId(order_id),
        _money(amount, currency),
        _date(paid_on),
    )


class SqliteCatalogue(_SqliteRepo):
    def add_category(self, category: Category) -> None:
        key = str(category.category_id)
        self._taken('category', 'categories', 'category_id', key)
        parent = category.parent_id
        self._db.execute(
            'INSERT INTO categories VALUES (?, ?, ?, ?, ?)',
            (
                key,
                category.name,
                None if parent is None else str(parent),
                category.sort_order,
                self._source,
            ),
        )

    def categories(self) -> tuple[Category, ...]:
        rows = self._rows(
            'SELECT category_id, category_name, parent_id, sort_order'
            ' FROM categories ORDER BY category_id'
        )
        return tuple(
            Category(
                CategoryId(category_id),
                name,
                None if parent is None else CategoryId(parent),
                sort_order,
            )
            for category_id, name, parent, sort_order in rows
        )

    def add_product(
        self, product: Product, details: BeanDetails | EquipmentDetails
    ) -> None:
        key = str(product.product_id)
        _check_details(product, details)
        self._taken('product', 'products', 'product_id', key)
        self._db.execute(
            'INSERT INTO products VALUES (?, ?, ?, ?, ?, ?)',
            (
                key,
                product.name,
                product.kind,
                str(product.category_id),
                product.weight_g,
                self._source,
            ),
        )
        match details:
            case BeanDetails():
                self._db.execute(
                    'INSERT INTO bean_details VALUES (?, ?, ?, ?, ?)',
                    (
                        key,
                        details.origin,
                        details.roast,
                        details.process,
                        self._source,
                    ),
                )
            case EquipmentDetails():
                self._db.execute(
                    'INSERT INTO equipment_details VALUES (?, ?, ?, ?)',
                    (
                        key,
                        details.warranty_months,
                        details.material,
                        self._source,
                    ),
                )

    def product(self, product_id: ProductId) -> Product:
        key = str(product_id)
        rows = self._rows(
            'SELECT product_id, product_name, kind, category_id,'
            ' weight_g FROM products WHERE product_id = ?'
            ' ORDER BY product_id',
            (key,),
        )
        if not rows:
            raise UnknownId('product', key)
        return _product(rows[0])

    def products(self) -> tuple[Product, ...]:
        rows = self._rows(
            'SELECT product_id, product_name, kind, category_id,'
            ' weight_g FROM products ORDER BY product_id'
        )
        return tuple(_product(row) for row in rows)

    def add_campaign(self, campaign: Campaign) -> None:
        key = str(campaign.campaign_id)
        self._taken('campaign', 'campaigns', 'campaign_id', key)
        self._db.execute(
            'INSERT INTO campaigns VALUES (?, ?, ?, ?, ?, ?)',
            (
                key,
                campaign.name,
                campaign.discount_pct,
                campaign.first_day.isoformat(),
                campaign.last_day.isoformat(),
                self._source,
            ),
        )
        for product_id in sorted(set(_ids(campaign.product_ids))):
            self._db.execute(
                'INSERT INTO campaign_products VALUES (?, ?, ?)',
                (key, product_id, self._source),
            )


def _product(row: tuple[Any, ...]) -> Product:
    product_id, name, kind, category_id, weight = row
    return Product(
        ProductId(product_id),
        name,
        kind,
        CategoryId(category_id),
        weight,
    )


class SqlitePrices(_SqliteRepo):
    def of(self, product_id: ProductId) -> tuple[Price, ...]:
        rows = self._rows(
            'SELECT product_id, price, currency, valid_from, valid_to'
            ' FROM prices WHERE product_id = ? ORDER BY valid_from',
            (str(product_id),),
        )
        return tuple(_price(row) for row in rows)

    def add(self, price: Price) -> None:
        key = str(price.product_id)
        start = price.valid_from.isoformat()
        if self._exists(
            'prices', 'product_id = ? AND valid_from = ?', (key, start)
        ):
            raise DuplicateId('price', f'{key} {start}')
        self._db.execute(
            'INSERT INTO prices VALUES (?, ?, ?, ?, ?, ?)',
            (
                key,
                str(price.price.amount),
                price.price.currency,
                start,
                _day(price.valid_to),
                self._source,
            ),
        )

    def close(self, product_id: ProductId, valid_to: dt.date) -> None:
        key = str(product_id)
        rows = self._rows(
            'SELECT product_id, price, currency, valid_from, valid_to'
            ' FROM prices WHERE product_id = ? AND valid_to IS NULL'
            ' ORDER BY valid_from DESC',
            (key,),
        )
        if not rows:
            raise UnknownId('price', key)
        price = replace(_price(rows[0]), valid_to=valid_to)
        self._db.execute(
            'UPDATE prices SET valid_to = ?'
            ' WHERE product_id = ? AND valid_from = ?',
            (valid_to.isoformat(), key, price.valid_from.isoformat()),
        )


def _price(row: tuple[Any, ...]) -> Price:
    product_id, amount, currency, valid_from, valid_to = row
    return Price(
        ProductId(product_id),
        _money(amount, currency),
        _date(valid_from),
        _date_or_none(valid_to),
    )


class SqliteCosts(_SqliteRepo):
    def of(self, product_id: ProductId) -> tuple[Cost, ...]:
        rows = self._rows(
            'SELECT product_id, valid_from, valid_to, green, packaging,'
            ' roasting, currency FROM product_costs'
            ' WHERE product_id = ? ORDER BY valid_from',
            (str(product_id),),
        )
        return tuple(_cost(row) for row in rows)

    def add(self, cost: Cost) -> None:
        currency = _one_currency(cost)
        key = str(cost.product_id)
        start = cost.valid_from.isoformat()
        if self._exists(
            'product_costs',
            'product_id = ? AND valid_from = ?',
            (key, start),
        ):
            raise DuplicateId('cost', f'{key} {start}')
        self._db.execute(
            'INSERT INTO product_costs VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (
                key,
                start,
                _day(cost.valid_to),
                str(cost.green.amount),
                str(cost.packaging.amount),
                str(cost.roasting.amount),
                currency,
                self._source,
            ),
        )

    def close(self, product_id: ProductId, valid_to: dt.date) -> None:
        key = str(product_id)
        rows = self._rows(
            'SELECT product_id, valid_from, valid_to, green, packaging,'
            ' roasting, currency FROM product_costs'
            ' WHERE product_id = ? AND valid_to IS NULL'
            ' ORDER BY valid_from DESC',
            (key,),
        )
        if not rows:
            raise UnknownId('cost', key)
        start = _cost(rows[0]).valid_from
        _check_period(start, valid_to)
        self._db.execute(
            'UPDATE product_costs SET valid_to = ?'
            ' WHERE product_id = ? AND valid_from = ?',
            (valid_to.isoformat(), key, start.isoformat()),
        )


def _cost(row: tuple[Any, ...]) -> Cost:
    (
        product_id,
        valid_from,
        valid_to,
        green,
        packaging,
        roasting,
        cur,
    ) = row
    return Cost(
        ProductId(product_id),
        _date(valid_from),
        _date_or_none(valid_to),
        _money(green, cur),
        _money(packaging, cur),
        _money(roasting, cur),
    )


class SqliteRules(_SqliteRepo):
    def add(
        self, rule: Discount, *, campaign_id: CampaignId | None = None
    ) -> None:
        key = str(rule.rule_id)
        _check_rule(rule, campaign_id)
        self._taken('rule', 'pricing_rules', 'rule_id', key)
        named = None if campaign_id is None else str(campaign_id)
        if named is not None:
            self._missing('campaign', 'campaigns', 'campaign_id', named)
        self._db.execute(
            'INSERT INTO pricing_rules VALUES (?, ?, ?, ?, ?, ?, ?)',
            (
                key,
                rule.rule_kind,
                rule.percent,
                rule.valid_from.isoformat(),
                _day(rule.valid_to),
                named,
                self._source,
            ),
        )

    def close(self, rule_id: RuleId, valid_to: dt.date) -> None:
        key = str(rule_id)
        rows = self._rows(
            'SELECT valid_from FROM pricing_rules WHERE rule_id = ?'
            ' ORDER BY rule_id',
            (key,),
        )
        if not rows:
            raise UnknownId('rule', key)
        _check_period(_date(rows[0][0]), valid_to)
        self._db.execute(
            'UPDATE pricing_rules SET valid_to = ? WHERE rule_id = ?',
            (valid_to.isoformat(), key),
        )

    def all(self) -> tuple[Discount, ...]:
        rows = self._rows(
            'SELECT rule_id, rule_kind, percent, valid_from, valid_to,'
            ' campaign_id FROM pricing_rules ORDER BY rule_id'
        )
        found: list[Discount] = []
        for rule_id, kind, percent, start, end, campaign in rows:
            held = frozenset[ProductId]()
            if campaign is not None:
                held = frozenset(
                    ProductId(product_id)
                    for (product_id,) in self._rows(
                        'SELECT product_id FROM campaign_products'
                        ' WHERE campaign_id = ? ORDER BY product_id',
                        (campaign,),
                    )
                )
            found.append(
                Discount(
                    RuleId(rule_id),
                    kind,
                    percent,
                    _date(start),
                    _date_or_none(end),
                    held,
                )
            )
        return tuple(found)


_COMMANDS: Final[Mapping[str, type[Command]]] = MappingProxyType(
    {each.EVENT_TYPE: each for each in (Skip, Pause, Resume, Cancel)}
)
"""The command class of each `subscription_events.event_type`."""


class SqliteSubscriptions(_SqliteRepo):
    def add(self, sub: Subscription) -> None:
        key = str(sub.subscription_id)
        self._taken(
            'subscription', 'subscriptions', 'subscription_id', key
        )
        self._db.execute(
            'INSERT INTO subscriptions VALUES (?, ?, ?, ?, ?, ?)',
            (
                key,
                str(sub.customer_id),
                str(sub.product_id),
                sub.started.isoformat(),
                None,
                self._source,
            ),
        )

    def get(self, subscription_id: SubscriptionId) -> Subscription:
        key = str(subscription_id)
        rows = self._rows(
            'SELECT subscription_id, customer_id, product_id, started'
            ' FROM subscriptions WHERE subscription_id = ?'
            ' ORDER BY subscription_id',
            (key,),
        )
        if not rows:
            raise UnknownId('subscription', key)
        return self._built(rows[0])

    def of_customer(
        self, customer_id: CustomerId
    ) -> tuple[Subscription, ...]:
        rows = self._rows(
            'SELECT subscription_id, customer_id, product_id, started'
            ' FROM subscriptions WHERE customer_id = ?'
            ' ORDER BY subscription_id',
            (str(customer_id),),
        )
        return tuple(self._built(row) for row in rows)

    def all(self) -> tuple[Subscription, ...]:
        rows = self._rows(
            'SELECT subscription_id, customer_id, product_id, started'
            ' FROM subscriptions ORDER BY subscription_id'
        )
        return tuple(self._built(row) for row in rows)

    def record(self, command: Command) -> None:
        key = str(command.event_id)
        sub = str(command.subscription_id)
        self._missing(
            'subscription', 'subscriptions', 'subscription_id', sub
        )
        self._taken('sub_event', 'subscription_events', 'event_id', key)
        self._db.execute(
            'INSERT INTO subscription_events VALUES (?, ?, ?, ?, ?, ?)',
            (
                key,
                sub,
                command.EVENT_TYPE,
                command.reason,
                moment_text(command.event_at),
                self._source,
            ),
        )
        if isinstance(command, Cancel):
            self._db.execute(
                'UPDATE subscriptions SET ended = ?'
                ' WHERE subscription_id = ?',
                (command.event_at.date().isoformat(), sub),
            )

    def bags(
        self, subscription_id: SubscriptionId
    ) -> tuple[BagShipment, ...]:
        rows = self._rows(
            'SELECT bag_id, subscription_id, product_id, shipped_on,'
            ' qty FROM subscription_shipments WHERE subscription_id = ?'
            ' ORDER BY shipped_on, bag_id',
            (str(subscription_id),),
        )
        return tuple(
            BagShipment(
                BagId(bag_id),
                SubscriptionId(sub),
                ProductId(product_id),
                _date(shipped_on),
                qty,
            )
            for bag_id, sub, product_id, shipped_on, qty in rows
        )

    def add_bag(self, bag: BagShipment) -> None:
        key = str(bag.bag_id)
        self._taken('bag', 'subscription_shipments', 'bag_id', key)
        self._db.execute(
            'INSERT INTO subscription_shipments VALUES'
            ' (?, ?, ?, ?, ?, ?)',
            (
                key,
                str(bag.subscription_id),
                str(bag.product_id),
                bag.shipped_on.isoformat(),
                bag.qty,
                self._source,
            ),
        )

    def _built(self, row: tuple[Any, ...]) -> Subscription:
        sub_id, customer_id, product_id, started = row
        begun = Subscription.begin(
            SubscriptionId(sub_id),
            CustomerId(customer_id),
            ProductId(product_id),
            _date(started),
        )
        events = self._rows(
            'SELECT event_id, event_type, reason, event_at'
            ' FROM subscription_events WHERE subscription_id = ?'
            ' ORDER BY event_at, event_id',
            (sub_id,),
        )
        commands = [
            _COMMANDS[event_type](
                SubEventId(event_id),
                SubscriptionId(sub_id),
                reason,
                moment_from(event_at),
            )
            for event_id, event_type, reason, event_at in events
        ]
        return replay(begun, commands)


class SqliteStock(_SqliteRepo):
    def add(self, movement: Movement) -> None:
        key = str(movement.movement_id)
        self._taken('movement', 'stock_movements', 'movement_id', key)
        self._db.execute(
            'INSERT INTO stock_movements VALUES (?, ?, ?, ?, ?, ?)',
            (
                key,
                str(movement.product_id),
                moment_text(movement.moved_at),
                movement.reason,
                movement.qty,
                self._source,
            ),
        )

    def on_hand(
        self,
        product_id: ProductId,
        *,
        before: dt.datetime | None = None,
    ) -> int:
        key = str(product_id)
        if before is None:
            (total,) = self._db.execute(
                'SELECT COALESCE(SUM(qty), 0) FROM stock_movements'
                ' WHERE product_id = ?',
                (key,),
            ).fetchone()
        else:
            (total,) = self._db.execute(
                'SELECT COALESCE(SUM(qty), 0) FROM stock_movements'
                ' WHERE product_id = ? AND moved_at < ?',
                (key, moment_text(before)),
            ).fetchone()
        return int(total)

    def movements(self, product_id: ProductId) -> tuple[Movement, ...]:
        rows = self._rows(
            'SELECT movement_id, product_id, moved_at, reason, qty'
            ' FROM stock_movements WHERE product_id = ?'
            ' ORDER BY moved_at, movement_id',
            (str(product_id),),
        )
        return tuple(
            Movement(
                MovementId(movement_id),
                ProductId(pid),
                moment_from(moved_at),
                reason,
                qty,
            )
            for movement_id, pid, moved_at, reason, qty in rows
        )

    def add_count(self, count: Count) -> None:
        key = str(count.product_id)
        day = count.stock_date.isoformat()
        stamp = moment_text(count.counted_at)
        if self._exists(
            'stock_daily',
            'product_id = ? AND stock_date = ? AND counted_at = ?',
            (key, day, stamp),
        ):
            raise DuplicateId('count', f'{key} {day} {stamp}')
        self._db.execute(
            'INSERT INTO stock_daily VALUES (?, ?, ?, ?, ?)',
            (key, day, count.on_hand, stamp, self._source),
        )

    def counts(self, stock_date: dt.date) -> tuple[Count, ...]:
        rows = self._rows(
            'SELECT product_id, stock_date, on_hand, counted_at'
            ' FROM stock_daily WHERE stock_date = ?'
            ' ORDER BY product_id, counted_at',
            (stock_date.isoformat(),),
        )
        return tuple(
            Count(
                ProductId(pid), _date(day), on_hand, moment_from(stamp)
            )
            for pid, day, on_hand, stamp in rows
        )

    def source_of(self, movement_id: MovementId) -> Source:
        key = str(movement_id)
        rows = self._rows(
            'SELECT source FROM stock_movements WHERE movement_id = ?'
            ' ORDER BY movement_id',
            (key,),
        )
        if not rows:
            raise UnknownId('movement', key)
        return rows[0][0]


class SqliteShipments(_SqliteRepo):
    def add(self, shipment: Shipment) -> None:
        key = str(shipment.shipment_id)
        self._taken('shipment', 'shipments', 'shipment_id', key)
        self._db.execute(
            'INSERT INTO shipments VALUES (?, ?, ?, ?, ?, ?)',
            (
                key,
                str(shipment.order_id),
                shipment.shipped_on.isoformat(),
                shipment.promised_by.isoformat(),
                _day(shipment.delivered_on),
                self._source,
            ),
        )

    def get(self, shipment_id: ShipmentId) -> Shipment:
        key = str(shipment_id)
        rows = self._rows(
            'SELECT shipment_id, order_id, shipped_on, promised_by,'
            ' delivered_on FROM shipments WHERE shipment_id = ?'
            ' ORDER BY shipment_id',
            (key,),
        )
        if not rows:
            raise UnknownId('shipment', key)
        shipment, order, shipped, promised, delivered = rows[0]
        return Shipment(
            ShipmentId(shipment),
            OrderId(order),
            _date(shipped),
            _date(promised),
            _date_or_none(delivered),
        )

    def save(self, shipment: Shipment) -> None:
        key = str(shipment.shipment_id)
        self._missing('shipment', 'shipments', 'shipment_id', key)
        self._db.execute(
            'UPDATE shipments SET order_id = ?, shipped_on = ?,'
            ' promised_by = ?, delivered_on = ? WHERE shipment_id = ?',
            (
                str(shipment.order_id),
                shipment.shipped_on.isoformat(),
                shipment.promised_by.isoformat(),
                _day(shipment.delivered_on),
                key,
            ),
        )


class SqlitePurchases(_SqliteRepo):
    def add(self, purchase: GreenPurchase) -> None:
        key = str(purchase.purchase_id)
        self._taken('purchase', 'green_purchases', 'purchase_id', key)
        self._db.execute(
            'INSERT INTO green_purchases VALUES (?, ?, ?, ?, ?, ?, ?)',
            (
                key,
                purchase.bought_on.isoformat(),
                purchase.origin,
                str(purchase.kg),
                str(purchase.nok_per_kg.amount),
                purchase.nok_per_kg.currency,
                self._source,
            ),
        )

    def all(self) -> tuple[GreenPurchase, ...]:
        rows = self._rows(
            'SELECT purchase_id, bought_on, origin, kg, nok_per_kg,'
            ' currency FROM green_purchases ORDER BY purchase_id'
        )
        return tuple(
            GreenPurchase(
                PurchaseId(purchase_id),
                _date(bought_on),
                origin,
                Decimal(kg),
                _money(price, cur),
            )
            for purchase_id, bought_on, origin, kg, price, cur in rows
        )


class SqliteVatRates(_SqliteRepo):
    def all(self) -> tuple[VatRate, ...]:
        rows = self._rows(
            'SELECT country, kind, rate, valid_from, valid_to,'
            ' start_assumed FROM vat_rates'
            ' ORDER BY country, kind, valid_from'
        )
        return tuple(
            VatRate(
                country,
                kind,
                Decimal(rate),
                _date(start),
                _date_or_none(end),
                start_assumed=bool(assumed),
            )
            for country, kind, rate, start, end, assumed in rows
        )


class SqliteExtracts(_SqliteRepo):
    def replace(self, day: dt.date, rows: Sequence[ExtractRow]) -> None:
        _extract_keys(day, rows)
        self._db.execute(
            'DELETE FROM customer_extracts WHERE extract_date = ?',
            (day.isoformat(),),
        )
        for row in rows:
            self._db.execute(
                'INSERT INTO customer_extracts VALUES (?, ?, ?, ?, ?)',
                (
                    day.isoformat(),
                    str(row.customer_id),
                    row.country,
                    _postal(row.postal_code),
                    self._source,
                ),
            )

    def on(self, day: dt.date) -> tuple[ExtractRow, ...]:
        rows = self._rows(
            'SELECT extract_date, customer_id, country, postal_code'
            ' FROM customer_extracts WHERE extract_date = ?'
            ' ORDER BY customer_id',
            (day.isoformat(),),
        )
        return tuple(
            ExtractRow(
                _date(when),
                CustomerId(customer_id),
                country,
                _postal_code(postal),
            )
            for when, customer_id, country, postal in rows
        )


# The Ids adapters (ADR 0007, C30) -------------------------------


def _number_of(text: str) -> tuple[str, int]:
    """`L-05` as ('L', 5): a prefix and the number after it."""
    prefix, _, digits = text.rpartition('-')
    if not prefix or not digits.isdigit():
        raise ValueError(f'an id looks like PREFIX-digits: {text!r}')
    return prefix, int(digits)


class SequentialIds:
    """The next number of each kind at its fixed width,
    skipping the script's ids and the planted ones.

    `start` is the first number to give of each kind (1 if the
    kind is absent). An id of `skip` is matched by prefix and
    number, not by text: skipping L-05 skips L-0000005 too.
    """

    def __init__(
        self,
        start: Mapping[IdKind, int],
        skip: frozenset[str] = frozenset(),
    ) -> None:
        self._next: dict[IdKind, int] = dict(start)
        self._skip = frozenset(_number_of(each) for each in skip)

    def next(self, kind: IdKind) -> str:
        prefix = PREFIXES[kind]
        number = self._next.get(kind, 1)
        while (prefix, number) in self._skip:
            number += 1
        self._next[kind] = number + 1
        return f'{prefix}-{number:0{WIDTHS[kind]}d}'


class ScriptedIds:
    """The script's ids of each kind in call order, then `then`."""

    def __init__(
        self,
        script: Mapping[IdKind, Sequence[str]],
        then: Ids,
    ) -> None:
        self._script = {
            kind: tuple(ids) for kind, ids in script.items()
        }
        self._used: dict[IdKind, int] = {}
        self._then = then

    def next(self, kind: IdKind) -> str:
        listed = self._script.get(kind, ())
        used = self._used.get(kind, 0)
        if used < len(listed):
            self._used[kind] = used + 1
            return listed[used]
        return self._then.next(kind)
