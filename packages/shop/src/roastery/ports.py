"""What the app asks of the world, as Protocols: no store, no clock.

A port names the calls a service makes and nothing else. Any class
with those methods satisfies it, without inheriting from it. The
repositories take domain objects in and give them back; a listing is
a tuple, sorted by its key. A store that raises on an unknown id
raises `UnknownId`, and on a taken one `DuplicateId` (ADR 0003).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol

from roastery.catalogue import (
    BeanDetails,
    Category,
    EquipmentDetails,
    Product,
)
from roastery.commands import Command
from roastery.customer import Customer, CustomerChange, Email
from roastery.events import StatusChanged
from roastery.ids import (
    BagId,
    CampaignId,
    Country,
    CustomerId,
    MovementId,
    OrderId,
    PaymentId,
    PostalCode,
    ProductId,
    PurchaseId,
    RuleId,
    ShipmentId,
    SubscriptionId,
)
from roastery.money import Money
from roastery.order import Order, Payment
from roastery.pipeline import ExportLine
from roastery.pricing import Discount, Price
from roastery.subscription import Subscription
from roastery.vat import VatRate

Source = Literal['scripted', 'simulator', 'visitor']

IdKind = Literal[
    'customer',
    'order',
    'line',
    'event',
    'product',
    'category',
    'campaign',
    'subscription',
    'sub_event',
    'shipment',
    'bag',
    'movement',
    'purchase',
    'rule',
]

MovementReason = Literal[
    'roasted', 'sold', 'shipped', 'written_off', 'counted'
]
"""Why stock moved, as `stock_movements.reason` holds it."""


# The rows the ports speak, which have no home in core ------------


@dataclass(frozen=True)
class Booking:
    """What an order's row holds beside the order itself.

    `order_date` is the day on the customer's clock, `vat_amount`
    the VAT share of all its lines (ADR 0010), and `at` the moment
    its lines were stamped.
    """

    order_date: dt.date
    vat_amount: Money
    at: dt.datetime


@dataclass(frozen=True)
class Movement:
    """One row of `stock_movements`: signed, in is positive."""

    movement_id: MovementId
    product_id: ProductId
    moved_at: dt.datetime  # UTC
    reason: MovementReason
    qty: int


@dataclass(frozen=True)
class Count:
    """One row of `stock_daily`: a product's balance for a day."""

    product_id: ProductId
    stock_date: dt.date
    on_hand: int
    counted_at: dt.datetime  # UTC


@dataclass(frozen=True)
class GreenPurchase:
    """One row of `green_purchases`: green coffee, bought by kilo."""

    purchase_id: PurchaseId
    bought_on: dt.date
    origin: str
    kg: Decimal
    nok_per_kg: Money


@dataclass(frozen=True)
class Cost:
    """One row of `product_costs`: what a product cost, per period."""

    product_id: ProductId
    valid_from: dt.date
    valid_to: dt.date | None  # the first day it no longer holds
    green: Money
    packaging: Money
    roasting: Money


@dataclass(frozen=True)
class Shipment:
    """One row of `shipments`: an order's parcel."""

    shipment_id: ShipmentId
    order_id: OrderId
    shipped_on: dt.date
    promised_by: dt.date
    delivered_on: dt.date | None


@dataclass(frozen=True)
class BagShipment:
    """One row of `subscription_shipments`: a month's bag."""

    bag_id: BagId
    subscription_id: SubscriptionId
    product_id: ProductId
    shipped_on: dt.date
    qty: int


@dataclass(frozen=True)
class Campaign:
    """One row of `campaigns`, with its `campaign_products`."""

    campaign_id: CampaignId
    name: str
    discount_pct: int
    first_day: dt.date
    last_day: dt.date  # the last day it holds
    product_ids: tuple[ProductId, ...]


@dataclass(frozen=True)
class ExtractRow:
    """One row of `customer_extracts`: a customer as of a night."""

    extract_date: dt.date
    customer_id: CustomerId
    country: Country | None
    postal_code: PostalCode | None


# The repositories, one per aggregate (A9) -----------------------


class CustomerRepository(Protocol):
    """Customers by id, with the change log they write."""

    def add(self, customer: Customer, at: dt.datetime) -> None:
        """Keep a new customer, and an insert row in the log.

        DuplicateId if the id is taken; then no row is written.
        """
        ...

    def get(self, customer_id: CustomerId) -> Customer:
        """The customer; UnknownId if there is none."""
        ...

    def change(self, customer: Customer, at: dt.datetime) -> None:
        """Keep the new values, and an update row in the log.

        Every call writes a row, with the country and postal code
        as they are after it. UnknownId if there is no customer.
        """
        ...

    def erase(self, customer_id: CustomerId, at: dt.datetime) -> None:
        """Remove the customer; a delete row with the key only.

        UnknownId if there is no customer.
        """
        ...

    def all(self) -> tuple[Customer, ...]:
        """Every customer, sorted by customer id."""
        ...

    def changes(self) -> tuple[CustomerChange, ...]:
        """The log, sorted by seq. Seq is given by the store, from
        1 up, one more than the highest; a rolled-back change
        leaves no gap."""
        ...

    def source_of(self, customer_id: CustomerId) -> Source:
        """The source the customer was written under."""
        ...


class OrderRepository(Protocol):
    """Orders by id, with their lines and their stamps."""

    def add(self, order: Order, booking: Booking) -> None:
        """Keep a new order, its lines and its booking.

        DuplicateId if the id is taken.
        """
        ...

    def get(self, order_id: OrderId) -> Order:
        """The order, in the state it was saved in; UnknownId if
        there is none."""
        ...

    def save(self, order: Order) -> None:
        """Keep the order's new state over its old one.

        UnknownId if the order was never added.
        """
        ...

    def all(self) -> tuple[Order, ...]:
        """Every order, sorted by order id."""
        ...

    def booking(self, order_id: OrderId) -> Booking:
        """The booking it was added with; UnknownId if none."""
        ...

    def credits_of(self, order_id: OrderId) -> tuple[Order, ...]:
        """The credit orders whose `credit_of` is this order,
        sorted by order id."""
        ...

    def mark_deleted(self, order_id: OrderId, at: dt.datetime) -> None:
        """Mark every line of the order deleted, stamped `at`
        (a cancel). UnknownId if there is no such order."""
        ...

    def deleted_at(self, order_id: OrderId) -> dt.datetime | None:
        """When a cancel marked the order's lines deleted, or None.

        UnknownId if there is no such order."""
        ...

    def lines(self) -> tuple[ExportLine, ...]:
        """Every line of every order with its deletion flag,
        sorted by line id."""
        ...

    def source_of(self, order_id: OrderId) -> Source:
        """The source the order was written under."""
        ...


class PaymentRepository(Protocol):
    """The app's own record of each payment, once (A11)."""

    def add(self, payment: Payment) -> None:
        """Keep a payment; DuplicateId if its id is taken."""
        ...

    def find(self, payment_id: PaymentId) -> Payment | None:
        """The payment, or None: a redelivery asks first."""
        ...

    def of(self, order_id: OrderId) -> tuple[Payment, ...]:
        """The payments that name the order, sorted by id."""
        ...


class CatalogueRepository(Protocol):
    """Categories, products and their details, and campaigns."""

    def add_category(self, category: Category) -> None:
        """Keep a category; DuplicateId if its id is taken."""
        ...

    def categories(self) -> tuple[Category, ...]:
        """Every category, sorted by category id."""
        ...

    def add_product(
        self, product: Product, details: BeanDetails | EquipmentDetails
    ) -> None:
        """Keep a product and its subtype row together.

        DuplicateId if the id is taken.
        """
        ...

    def product(self, product_id: ProductId) -> Product:
        """The product; UnknownId if the shop lists none."""
        ...

    def products(self) -> tuple[Product, ...]:
        """Every product, sorted by product id."""
        ...

    def details(
        self, product_id: ProductId
    ) -> BeanDetails | EquipmentDetails:
        """The product's subtype row; UnknownId if none."""
        ...

    def add_campaign(self, campaign: Campaign) -> None:
        """Keep a campaign and one `campaign_products` row for
        each product. DuplicateId if its id is taken."""
        ...

    def campaigns(self) -> tuple[Campaign, ...]:
        """Every campaign, sorted by campaign id, each with its
        products once, sorted by product id."""
        ...


class PriceRepository(Protocol):
    """List prices by product and period (half-open)."""

    def of(self, product_id: ProductId) -> tuple[Price, ...]:
        """The product's price rows, sorted by `valid_from`."""
        ...

    def add(self, price: Price) -> None:
        """Keep a price row."""
        ...

    def close(self, product_id: ProductId, valid_to: dt.date) -> None:
        """End the product's open row on `valid_to`."""
        ...


class CostRepository(Protocol):
    """What a product cost, by product and period (half-open)."""

    def of(self, product_id: ProductId) -> tuple[Cost, ...]:
        """The product's cost rows, sorted by `valid_from`."""
        ...

    def add(self, cost: Cost) -> None:
        """Keep a cost row."""
        ...

    def close(self, product_id: ProductId, valid_to: dt.date) -> None:
        """End the product's open row on `valid_to`."""
        ...


class RuleRepository(Protocol):
    """The `pricing_rules` rows, as the pricing rules read them."""

    def add(
        self, rule: Discount, *, campaign_id: CampaignId | None = None
    ) -> None:
        """Keep a rule; a campaign's rule names its campaign.

        DuplicateId if the id is taken.
        """
        ...

    def close(self, rule_id: RuleId, valid_to: dt.date) -> None:
        """End the rule on `valid_to`; UnknownId if none."""
        ...

    def all(self) -> tuple[Discount, ...]:
        """Every rule, sorted by rule id. A campaign's rule comes
        back with the products of its campaign."""
        ...


class SubscriptionRepository(Protocol):
    """Subscriptions, their events and their bags (A9)."""

    def add(self, sub: Subscription) -> None:
        """Keep a new subscription, as `Subscription.begin` makes
        it. DuplicateId if the id is taken."""
        ...

    def get(self, subscription_id: SubscriptionId) -> Subscription:
        """The subscription as its events leave it: `started`,
        then `replay`. UnknownId if there is none."""
        ...

    def of_customer(
        self, customer_id: CustomerId
    ) -> tuple[Subscription, ...]:
        """The customer's subscriptions, sorted by id."""
        ...

    def all(self) -> tuple[Subscription, ...]:
        """Every subscription, sorted by id."""
        ...

    def record(self, command: Command) -> None:
        """Keep the command as a `subscription_events` row. A
        Cancel also sets `ended` to its `day`."""
        ...

    def events(
        self, subscription_id: SubscriptionId
    ) -> tuple[Command, ...]:
        """Its commands as kept, by `event_at` then event id."""
        ...

    def bags(
        self, subscription_id: SubscriptionId
    ) -> tuple[BagShipment, ...]:
        """The bags shipped, sorted by day then bag id."""
        ...

    def add_bag(self, bag: BagShipment) -> None:
        """Keep a shipped bag; DuplicateId if its id is taken."""
        ...


class StockRepository(Protocol):
    """Stock movements and the daily counts."""

    def add(self, movement: Movement) -> None:
        """Keep a movement; DuplicateId if its id is taken."""
        ...

    def on_hand(
        self,
        product_id: ProductId,
        *,
        before: dt.datetime | None = None,
    ) -> int:
        """The signed sum of the product's movements made before
        `before` (strictly), or of all of them. 0 if none."""
        ...

    def movements(self, product_id: ProductId) -> tuple[Movement, ...]:
        """The product's movements, oldest first, then by id."""
        ...

    def add_count(self, count: Count) -> None:
        """Keep a count; DuplicateId if the product, day and
        stamp are taken."""
        ...

    def counts(self, stock_date: dt.date) -> tuple[Count, ...]:
        """The day's counts, sorted by product then stamp."""
        ...

    def all_counts(self) -> tuple[Count, ...]:
        """Every count, sorted by product, day, then stamp."""
        ...

    def source_of(self, movement_id: MovementId) -> Source:
        """The source the movement was written under."""
        ...


class ShipmentRepository(Protocol):
    """Parcels of orders."""

    def add(self, shipment: Shipment) -> None:
        """Keep a shipment; DuplicateId if its id is taken."""
        ...

    def get(self, shipment_id: ShipmentId) -> Shipment:
        """The shipment; UnknownId if there is none."""
        ...

    def save(self, shipment: Shipment) -> None:
        """Keep the new state (`delivered_on`) over the old."""
        ...

    def all(self) -> tuple[Shipment, ...]:
        """Every shipment, sorted by shipment id."""
        ...


class PurchaseRepository(Protocol):
    """Green coffee bought."""

    def add(self, purchase: GreenPurchase) -> None:
        """Keep a purchase; DuplicateId if its id is taken."""
        ...

    def all(self) -> tuple[GreenPurchase, ...]:
        """Every purchase, sorted by purchase id."""
        ...


class VatRateRepository(Protocol):
    """The dated VAT rows, seeded with the schema (A18)."""

    def all(self) -> tuple[VatRate, ...]:
        """Every row, sorted by country, kind and first day."""
        ...


class ExtractRepository(Protocol):
    """The nightly copies of customers."""

    def replace(self, day: dt.date, rows: Sequence[ExtractRow]) -> None:
        """Make the rows the day's copy; an earlier one goes."""
        ...

    def on(self, day: dt.date) -> tuple[ExtractRow, ...]:
        """The day's copy, sorted by customer id."""
        ...

    def all(self) -> tuple[ExtractRow, ...]:
        """Every night's copy, sorted by day then customer id."""
        ...


# The outbox (ADR 0009) -----------------------------------------


@dataclass(frozen=True)
class Batch:
    """Rows sent together: all are taken, or none."""

    number: int
    events: tuple[StatusChanged, ...]


class Outbox(Protocol):
    """StatusChanged rows, kept in the change's transaction."""

    def add(self, event: StatusChanged) -> int:
        """Keep the event, in no batch; returns its position,
        from 1 up."""
        ...

    def form_batches(self, size: int) -> tuple[int, ...]:
        """Put the rows in no batch into new batches, by position.

        Each holds `size` rows; the last may hold fewer. Returns
        the new numbers. A batch formed earlier is not touched.
        """
        ...

    def waiting(self) -> tuple[Batch, ...]:
        """The batches not yet sent, by number; each with the
        rows it was formed with, in position order."""
        ...

    def mark_sent(self, number: int) -> None:
        """The batch is sent. UnknownId if it is not waiting."""
        ...


@dataclass(frozen=True)
class Relayed:
    """What a relay run did: the batches sent, those that wait.

    A port type, so the simulator imports no adapter for it."""

    sent: tuple[int, ...]
    waiting: tuple[int, ...]


class FeedDown(ConnectionError):
    """The feed did not take the batch; none of it was kept."""


class StatusFeed(Protocol):
    def send(self, events: Sequence[StatusChanged]) -> None:
        """Take every event of the batch, or raise FeedDown.
        A feed refuses by content, never by batch number."""
        ...


# The unit of work and the store (ADR 0003) -----------------------


class UnitOfWork(Protocol):
    """One transaction over every store of the app.

    Open it with `with`, write through its stores, call commit().
    Leaving the block undoes what was not committed, also when the
    block raises. It can be opened again after it ended, but not
    while it is open (RuntimeError). Every row it writes is
    stamped with `source`.
    """

    source: Source
    customers: CustomerRepository
    orders: OrderRepository
    payments: PaymentRepository
    catalogue: CatalogueRepository
    prices: PriceRepository
    costs: CostRepository
    rules: RuleRepository
    subscriptions: SubscriptionRepository
    stock: StockRepository
    shipments: ShipmentRepository
    purchases: PurchaseRepository
    vat_rates: VatRateRepository
    extracts: ExtractRepository
    outbox: Outbox

    def __enter__(self) -> UnitOfWork: ...

    def __exit__(self, *exc: object) -> None: ...

    def commit(self) -> None: ...

    def sources(self, table: str) -> Mapping[tuple[str, ...], Source]:
        """The source of every row of the app table `table`, by
        the row's key as text: ids and numbers as written, a day
        as ISO, a moment as UTC ISO. A changed row keeps the
        source it was first written under (A33). ValueError for
        a table that keeps no source."""
        ...


class Store(Protocol):
    """The app's tables: one database, or one set of dicts."""

    def unit_of_work(self, source: Source) -> UnitOfWork:
        """A unit of work over these tables, stamping `source`."""
        ...


# Time and ids (ADR 0008, ADR 0007) ------------------------------


class Clock(Protocol):
    def now(self) -> dt.datetime:
        """This moment, timezone-aware, in UTC."""


class Ids(Protocol):
    def next(self, kind: IdKind) -> str:
        """A fresh id of this kind, as PREFIX-digits."""


# The outside world ----------------------------------------------


class Notifier(Protocol):
    def send(self, to: Email, *, subject: str, body: str) -> None:
        """The confirmation e-mail (a handler's port, C26)."""
        ...


class Labels(Protocol):
    def request(
        self, order_id: OrderId, *, postal_code: PostalCode
    ) -> None:
        """A shipping label for a web order (C26, C39)."""
        ...


# the port the outbound call goes through


class ProviderRefused(Exception):
    """A decline (402): never retried."""


class ProviderUnavailable(ConnectionError):
    """Down, or the breaker is open: retried."""


class PaymentProvider(Protocol):
    def refund(
        self, payment_id: PaymentId, amount: Money, *, key: str
    ) -> PaymentId:
        """The refund's id; the same key gives the same id."""
        ...
