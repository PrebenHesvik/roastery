"""The script of the teaching week, as data (6.4, W1).

The world the simulator plays through the shop app: every call as a
`Step` in strict moment order, with the wiring that makes it and the
scripted ids it draws; the jobs on their schedule (W4); the feed's
refusals (W5); and the facts of the outside systems (W17). Nothing
here runs the app: `play` gives each step to exactly one call of
contract B, or to the provider's log and then `handle_message`.

The setup is on 2024-01-01 from 08:00 UTC, one minute a step (W23).
The customers and subscriptions come at their own moments, C-01's
year through the `simulator` wiring (W7), one relay closes the year
(1 October 12:00), then the week (§4) and its jobs (W4). The script
plays no refusal (W27), never runs `ship_subscription_bags` (W9) and
sets no subscriber discount (A14). The writer's planted rows (L-05,
L-09, the 26, the 06:30 resend, the raw cells) are not here: they
are the export writer's, after a correct app (D10).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from types import MappingProxyType
from typing import Final, Literal

from roastery.catalogue import BeanDetails, EquipmentDetails
from roastery.checkout import Item, PlaceOrder
from roastery.customer import Email
from roastery.ids import (
    AccountKind,
    CategoryId,
    Country,
    CustomerId,
    EventId,
    OrderId,
    PaymentId,
    PostalCode,
    ProductId,
    SubscriptionId,
)
from roastery.money import Money, Qty
from roastery.payments import PaymentMessage
from roastery.ports import IdKind

from roastery_sim.outside import (
    FxRate,
    Manager,
    ProductCode,
    TillLine,
    TillMember,
    TillReceipt,
    WebEvent,
)

Wiring = Literal['scripted', 'simulator']
"""Which of the two wirings over the one store makes the call (C7)."""


# The actions: one frozen type per kind of step ---------------------


@dataclass(frozen=True)
class Register:
    """`customers.register`; the customer id is the step's."""

    name: str
    email: Email | None
    country: Country | None
    postal_code: PostalCode | None
    account_kind: AccountKind = 'consumer'


@dataclass(frozen=True)
class Change:
    """`customers.change`: the whole contact after the change."""

    customer_id: CustomerId
    email: Email | None
    country: Country | None
    postal_code: PostalCode | None


@dataclass(frozen=True)
class Erase:
    """`customers.erase`; open subscriptions are cancelled with it."""

    customer_id: CustomerId


@dataclass(frozen=True)
class Subscribe:
    """`subscriptions.subscribe`, started on the customer's day."""

    customer_id: CustomerId
    product_id: ProductId


@dataclass(frozen=True)
class CancelSubscription:
    """`subscriptions.cancel`, ended on the customer's day."""

    subscription_id: SubscriptionId
    reason: str


@dataclass(frozen=True)
class AddCategory:
    """`catalogue.add_category`."""

    name: str
    parent_id: CategoryId | None
    sort_order: int


@dataclass(frozen=True)
class AddProduct:
    """`catalogue.add_product`; kind and weight follow the details."""

    name: str
    category_id: CategoryId
    details: BeanDetails | EquipmentDetails


@dataclass(frozen=True)
class SetPrice:
    """`catalogue.set_price`."""

    product_id: ProductId
    price: Money
    valid_from: dt.date


@dataclass(frozen=True)
class AddCampaign:
    """`catalogue.add_campaign`."""

    name: str
    discount_pct: int
    first_day: dt.date
    last_day: dt.date
    product_ids: tuple[ProductId, ...]


@dataclass(frozen=True)
class Roast:
    """`stock.roast`: bags in."""

    product_id: ProductId
    bags: Qty


@dataclass(frozen=True)
class Stocktake:
    """`stock.stocktake`: the level counted."""

    product_id: ProductId
    on_hand: int


@dataclass(frozen=True)
class Place:
    """`checkout.place`."""

    order: PlaceOrder


@dataclass(frozen=True)
class Pay:
    """The provider's message: `ProviderLog.deliver`, then
    `payments.handle_message` with what it gives back (W22).

    A redelivery is a second step with the same message.
    """

    message: PaymentMessage


@dataclass(frozen=True)
class Ship:
    """`fulfilment.ship`. `play` keeps the shipment id it returns."""

    order_id: OrderId
    promised_by: dt.date


@dataclass(frozen=True)
class Deliver:
    """`fulfilment.deliver` of the shipment `ship` returned for the order."""

    order_id: OrderId


@dataclass(frozen=True)
class CancelOrder:
    """`checkout.cancel`."""

    order_id: OrderId
    reason: str


@dataclass(frozen=True)
class Relay:
    """`jobs.relay`."""


@dataclass(frozen=True)
class CountAtClose:
    """`jobs.count_at_close`."""


@dataclass(frozen=True)
class NightlyExtract:
    """`jobs.nightly_extract`."""


@dataclass(frozen=True)
class CsvExport:
    """`jobs.csv_export`."""


type Action = (
    Register
    | Change
    | Erase
    | Subscribe
    | CancelSubscription
    | AddCategory
    | AddProduct
    | SetPrice
    | AddCampaign
    | Roast
    | Stocktake
    | Place
    | Pay
    | Ship
    | Deliver
    | CancelOrder
    | Relay
    | CountAtClose
    | NightlyExtract
    | CsvExport
)
"""Every kind of step; each is one call of contract B."""

JOBS: Final = (Relay, CountAtClose, NightlyExtract, CsvExport)
"""The action types that are jobs of contract B."""

_NO_IDS: Final[Mapping[IdKind, tuple[str, ...]]] = MappingProxyType({})


@dataclass(frozen=True)
class Step:
    """One call at one moment, through one wiring.

    `ids` names, per kind, the scripted ids the call draws, in the
    order it draws them. Kinds the script does not list (movement,
    rule, sub_event, shipment) fall to the shared sequence, and a
    `simulator` step lists none.
    """

    at: dt.datetime
    wiring: Wiring
    action: Action
    ids: Mapping[IdKind, tuple[str, ...]] = field(default=_NO_IDS)

    def __post_init__(self) -> None:
        if self.at.tzinfo is None or self.at.utcoffset() != dt.timedelta(0):
            raise ValueError(f'a step is at a UTC moment: {self.at!r}')
        if self.wiring == 'simulator' and self.ids:
            raise ValueError(f'a simulator step draws no scripted id: {self}')


# Ids ---------------------------------------------------------------

_SEQUENCE: Final[Mapping[IdKind, tuple[str, int]]] = MappingProxyType(
    {
        'customer': ('C', 5),
        'order': ('O', 6),
        'line': ('L', 7),
        'event': ('E', 7),
        'product': ('P', 3),
        'category': ('CAT', 3),
        'campaign': ('K', 3),
        'subscription': ('S', 5),
        'sub_event': ('SE', 6),
        'shipment': ('SH', 6),
        'bag': ('SB', 6),
        'movement': ('M', 7),
        'purchase': ('GP', 5),
        'rule': ('PR', 4),
    }
)
"""Each kind's prefix and the sequence's fixed width (ADR 0007's table)."""

PLANTED: Final = ('L-05', 'L-09')
"""The ids the export writer plants; the sequence never makes them."""


def hidden(kind: IdKind, n: int) -> str:
    """The `n`th id of the shared sequence, at its width (E-0000101).

    The scripted wiring draws O-103's, O-105's and O-107's events as
    hidden ids; the writer drops those rows by `order_id` (W6).
    """
    prefix, width = _SEQUENCE[kind]
    return f'{prefix}-{n:0{width}d}'


def _ids(**kinds: tuple[str, ...]) -> Mapping[IdKind, tuple[str, ...]]:
    """A step's scripted ids, by kind."""
    known = set(_SEQUENCE)
    for kind in kinds:
        if kind not in known:
            raise ValueError(f'no such id kind: {kind}')
    return MappingProxyType(dict(kinds))  # type: ignore[arg-type]


def scripted_ids(steps: Iterable[Step]) -> Mapping[IdKind, tuple[str, ...]]:
    """Per kind, the `scripted` wiring's ids in step order (W6)."""
    drawn: dict[IdKind, list[str]] = {}
    for step in steps:
        if step.wiring != 'scripted':
            continue
        for kind, ids in step.ids.items():
            drawn.setdefault(kind, []).extend(ids)
    return MappingProxyType({kind: tuple(ids) for kind, ids in drawn.items()})


def skip_set(steps: Iterable[Step]) -> frozenset[str]:
    """What the shared sequence skips: every scripted id (the hidden
    ones among them) and the writer's planted L-05 and L-09 (W6)."""
    listed = scripted_ids(steps)
    return frozenset(each for ids in listed.values() for each in ids) | frozenset(PLANTED)


# Moments -----------------------------------------------------------


def _utc(year: int, month: int, day: int, hour: int, minute: int, second: int = 0) -> dt.datetime:
    return dt.datetime(year, month, day, hour, minute, second, tzinfo=dt.UTC)


def _oct(day: int, hour: int, minute: int, second: int = 0) -> dt.datetime:
    """A moment of October 2026, in UTC."""
    return _utc(2026, 10, day, hour, minute, second)


SETUP: Final = _utc(2024, 1, 1, 8, 0)
"""The setup's first moment (W23); each setup step takes the next minute."""

REFUSE: Final[Mapping[EventId, dt.datetime]] = MappingProxyType(
    {
        EventId('E-09'): _oct(6, 15, 45),
        EventId('E-08'): _oct(10, 7, 0),
    }
)
"""The feed refuses a batch holding the event while now is before this (W5)."""


# The cast ----------------------------------------------------------

C01: Final = CustomerId('C-01')
C02: Final = CustomerId('C-02')
C03: Final = CustomerId('C-03')
C04: Final = CustomerId('C-04')
C05: Final = CustomerId('C-05')
C06: Final = CustomerId('C-06')
C07: Final = CustomerId('C-07')
P10: Final = ProductId('P-10')
P11: Final = ProductId('P-11')
P12: Final = ProductId('P-12')
P20: Final = ProductId('P-20')
P21: Final = ProductId('P-21')


@dataclass(frozen=True)
class Cast:
    """The week's customers, orders and subscriptions, for tiny's cut (W21)."""

    customers: tuple[CustomerId, ...]
    orders: tuple[OrderId, ...]
    subscriptions: tuple[SubscriptionId, ...]


CAST: Final = Cast(
    customers=(C01, C02, C03, C04, C05, C06, C07),
    orders=tuple(OrderId(f'O-10{n}') for n in range(1, 9)),
    subscriptions=tuple(SubscriptionId(f'S-{n}') for n in range(1, 8)),
)
"""C-07 is in the cast though erased: `customer_changes` and the 8 October copy name them."""


def _email(name: str) -> Email:
    return Email(f'{name}@example.invalid')


# (customer id, moment, name, e-mail, country, postal code): §4, raw_customers lower-cased
_CUSTOMERS: Final = (
    (C01, _utc(2024, 3, 1, 9, 0), 'Ingrid', _email('ingrid'), 'NO', '7010'),
    (C02, _utc(2025, 1, 15, 14, 30), 'Åsa', _email('asa'), 'SE', '21119'),
    (C07, _utc(2025, 2, 20, 11, 10), 'Tor', _email('tor'), 'NO', '0450'),
    (C03, _utc(2025, 6, 2, 8, 45), 'Mikkel', _email('mikkel'), 'DK', '8000'),
    (C04, _utc(2025, 6, 2, 19, 20), 'Aino', _email('aino'), 'FI', '33100'),
    (C05, _utc(2026, 2, 10, 13, 0), 'Lars', None, None, None),
    (C06, _oct(9, 10, 14), 'Mona', None, 'NO', '5003'),
)

# (subscription id, customer, product, started, ended or None): `subscriptions`
_SUBSCRIPTIONS: Final = (
    ('S-1', C01, P10, dt.date(2024, 4, 1), None),
    ('S-2', C02, P11, dt.date(2025, 2, 1), dt.date(2025, 8, 1)),
    ('S-7', C07, P10, dt.date(2025, 3, 1), None),  # ended 2026-10-09 by C-07's erase
    ('S-4', C03, P10, dt.date(2025, 7, 1), dt.date(2026, 1, 1)),
    ('S-5', C04, P11, dt.date(2025, 7, 1), dt.date(2025, 10, 1)),
    ('S-3', C02, P11, dt.date(2025, 9, 1), None),
    ('S-6', C04, P10, dt.date(2025, 9, 15), None),
)
SUBSCRIBE_AT: Final = dt.time(10, 0)
"""Subscribe and cancel at 10:00 UTC on the day; a second on one day takes the next minute."""


def _customers() -> list[Step]:
    steps = []
    for customer_id, at, name, email, country, postal in _CUSTOMERS:
        code = None if postal is None else PostalCode(postal)
        action = Register(name, email=email, country=country, postal_code=code)
        steps.append(Step(at, 'scripted', action, _ids(customer=(customer_id.value,))))
    return steps


def _subscriptions() -> list[Step]:
    steps: list[Step] = []
    taken: set[dt.datetime] = set()

    def moment(day: dt.date) -> dt.datetime:
        at = dt.datetime.combine(day, SUBSCRIBE_AT, tzinfo=dt.UTC)
        while at in taken:
            at += dt.timedelta(minutes=1)
        taken.add(at)
        return at

    for sub_id, customer_id, product_id, started, _ in _SUBSCRIPTIONS:
        action = Subscribe(customer_id, product_id)
        steps.append(Step(moment(started), 'scripted', action, _ids(subscription=(sub_id,))))
    for sub_id, _, _, _, ended in _SUBSCRIPTIONS:
        if ended is not None:
            cancel = CancelSubscription(SubscriptionId(sub_id), reason='customer asked')
            steps.append(Step(moment(ended), 'scripted', cancel))
    return steps


# The catalogue and the stock (W8, W23) ------------------------------

# (category id, name, parent, sort_order): `categories`, parents first
_CATEGORIES: Final = (
    ('CAT-1', 'Beans', None, 1),
    ('CAT-11', 'Filter', 'CAT-1', 2),
    ('CAT-12', 'Espresso', 'CAT-1', 3),
    ('CAT-2', 'Equipment', None, 4),
    ('CAT-21', 'Grinders', 'CAT-2', 6),
    ('CAT-22', 'Hand grinders', 'CAT-21', 7),
    ('CAT-23', 'Kettles', 'CAT-2', 5),
)

# (product id, name, category, details): `products`, `bean_details`, `equipment_details`
_PRODUCTS: Final = (
    (P10, 'Morning roast', 'CAT-11', BeanDetails(250, 'Ethiopia', 'light', 'washed')),
    (P11, 'Dark espresso', 'CAT-12', BeanDetails(1000, 'Brazil', 'dark', 'natural')),
    (P12, 'Decaf', 'CAT-11', BeanDetails(250, 'Colombia', 'medium', 'washed')),
    (P20, 'Hand grinder', 'CAT-22', EquipmentDetails(24, 'wood')),
    (P21, 'Pour-over kettle', 'CAT-23', EquipmentDetails(12, 'steel')),
)

# (product, price in NOK, valid_from): `prices`, each product's periods in order; P-12 has none
PRICES: Final = (
    (P10, Decimal('119.00'), dt.date(2024, 1, 1)),
    (P10, Decimal('129.00'), dt.date(2026, 10, 1)),
    (P11, Decimal('329.00'), dt.date(2024, 1, 1)),
    (P11, Decimal('349.00'), dt.date(2026, 10, 5)),
    (P20, Decimal('899.00'), dt.date(2025, 6, 1)),
    (P21, Decimal('549.00'), dt.date(2026, 10, 7)),
)

# (name, discount_pct, first_day, last_day, products): `campaigns`, `campaign_products`
_CAMPAIGNS: Final = (
    ('K-1', 'Autumn espresso', 10, dt.date(2026, 10, 12), dt.date(2026, 10, 25), (P11, P20)),
    ('K-2', 'Brew at home', 15, dt.date(2026, 11, 16), dt.date(2026, 11, 29), (P10, P20, P21)),
)

# The opening stock (W8): 55 - 13 sold in C-01's year = 42 P-10; 20 - 8 = 12 P-11; 6 - 1 = 5 P-20
_STOCK: Final = (
    Roast(P10, Qty(55)),
    Roast(P11, Qty(20)),
    Stocktake(P20, 6),
    Stocktake(P21, 2),
)


def _setup() -> list[Step]:
    """The catalogue and the stock, one minute a step from SETUP."""
    made: list[tuple[Action, Mapping[IdKind, tuple[str, ...]]]] = []
    for category_id, name, parent, sort_order in _CATEGORIES:
        parent_id = None if parent is None else CategoryId(parent)
        made.append((AddCategory(name, parent_id, sort_order), _ids(category=(category_id,))))
    for product_id, name, category, details in _PRODUCTS:
        action = AddProduct(name, CategoryId(category), details)
        made.append((action, _ids(product=(product_id.value,))))
    for product_id, price, valid_from in PRICES:
        made.append((SetPrice(product_id, Money(price, 'NOK'), valid_from), _NO_IDS))
    for campaign_id, name, pct, first, last, products in _CAMPAIGNS:
        action = AddCampaign(name, pct, first, last, products)
        made.append((action, _ids(campaign=(campaign_id,))))
    made.extend((action, _NO_IDS) for action in _STOCK)
    return [
        Step(SETUP + dt.timedelta(minutes=n), 'scripted', action, ids)
        for n, (action, ids) in enumerate(made)
    ]


def list_price(product_id: ProductId, day: dt.date) -> Decimal:
    """The list price that holds on `day`, from PRICES."""
    held = [price for pid, price, valid_from in PRICES if pid == product_id and valid_from <= day]
    if not held:
        raise ValueError(f'{product_id} has no price on {day}')
    return held[-1]


# C-01's year (W7) ---------------------------------------------------

# (day, ((product, qty), ...)): one web order each, at list price
YEAR: Final = (
    (dt.date(2025, 11, 12), ((P10, 2),)),
    (dt.date(2025, 12, 3), ((P20, 1),)),
    (dt.date(2025, 12, 10), ((P11, 1),)),
    (dt.date(2025, 12, 17), ((P10, 1),)),
    (dt.date(2025, 12, 22), ((P10, 1),)),
    (dt.date(2026, 2, 11), ((P10, 1),)),
    (dt.date(2026, 3, 4), ((P10, 1),)),
    (dt.date(2026, 3, 18), ((P11, 1),)),
    (dt.date(2026, 4, 15), ((P11, 1),)),
    (dt.date(2026, 5, 6), ((P11, 1),)),
    (dt.date(2026, 5, 13), ((P11, 1),)),
    (dt.date(2026, 5, 27), ((P10, 3),)),
    (dt.date(2026, 7, 8), ((P10, 1),)),
    (dt.date(2026, 7, 22), ((P10, 1),)),
    (dt.date(2026, 8, 12), ((P11, 2),)),
    (dt.date(2026, 9, 9), ((P10, 2),)),
    (dt.date(2026, 9, 23), ((P11, 1),)),
)
YEAR_PLACED: Final = dt.time(10, 0)
YEAR_PAID: Final = dt.time(10, 1)
YEAR_PAYMENT_FIRST: Final = 1001
"""The year's payments are PAY-1001 to PAY-1017: clear of PAY-1..PAY-6 and the tests' PAY-300."""


def _year() -> list[Step]:
    """17 web orders of C-01 through the simulator wiring, each paid a
    minute later. Its orders are the sequence's first: O-000001 on
    (nothing draws an order from the sequence before them)."""
    steps = []
    for n, (day, lines) in enumerate(YEAR, 1):
        items = tuple(Item(product_id, Qty(qty)) for product_id, qty in lines)
        total = sum((list_price(pid, day) * qty for pid, qty in lines), Decimal('0.00'))
        message = PaymentMessage(
            PaymentId(f'PAY-{YEAR_PAYMENT_FIRST + n - 1}'),
            OrderId(hidden('order', n)),
            Money(total, 'NOK'),
            day,
        )
        placed = dt.datetime.combine(day, YEAR_PLACED, tzinfo=dt.UTC)
        paid = dt.datetime.combine(day, YEAR_PAID, tzinfo=dt.UTC)
        steps.append(Step(placed, 'simulator', Place(PlaceOrder(C01, 'web', items))))
        steps.append(Step(paid, 'simulator', Pay(message)))
    return steps


# The week (§4) -------------------------------------------------------


def _order(
    at: dt.datetime,
    customer_id: CustomerId,
    channel: Literal['web', 'shop'],
    items: Sequence[Item],
    *,
    order: str,
    lines: Sequence[str],
    event: str,
) -> Step:
    """`place`: it draws the order, each line in item order, a
    movement per line (the sequence's) and the `placed` event."""
    ids = _ids(order=(order,), line=tuple(lines), event=(event,))
    return Step(at, 'scripted', Place(PlaceOrder(customer_id, channel, tuple(items))), ids)


def _pay(
    at: dt.datetime, payment: str, order: str, amount: str, currency: str, event: str | None
) -> Step:
    """A provider message; `event` None for a redelivery, which draws none."""
    message = PaymentMessage(
        PaymentId(payment), OrderId(order), Money(Decimal(amount), currency), at.date()
    )
    ids = _NO_IDS if event is None else _ids(event=(event,))
    return Step(at, 'scripted', Pay(message), ids)


def _nok(amount: str) -> Money:
    return Money(Decimal(amount), 'NOK')


def _week() -> list[Step]:
    typo = Change(C01, email=_email('ingrid'), country='NO', postal_code=PostalCode('0510'))
    fixed = Change(C01, email=_email('ingrid'), country='NO', postal_code=PostalCode('0150'))
    one = Qty(1)
    return [
        # 5 October
        _order(
            _oct(5, 8, 12),
            C01,
            'web',
            (Item(P10, Qty(2)), Item(P20, one)),
            order='O-101',
            lines=('L-01', 'L-02'),
            event='E-01',
        ),
        _pay(_oct(5, 8, 13), 'PAY-1', 'O-101', '1157.00', 'NOK', 'E-02'),
        _pay(_oct(5, 8, 14), 'PAY-1', 'O-101', '1157.00', 'NOK', None),  # the redelivery
        _order(
            _oct(5, 21, 50),
            C02,
            'web',
            (Item(P11, one),),
            order='O-102',
            lines=('L-03',),
            event='E-05',
        ),
        _pay(_oct(5, 21, 52), 'PAY-2', 'O-102', '516.98', 'SEK', 'E-06'),
        # 6 October
        _order(
            _oct(6, 10, 20),
            C03,
            'web',
            (Item(P10, Qty(3)),),
            order='O-103',
            lines=('L-04',),
            event=hidden('event', 101),
        ),
        _pay(_oct(6, 10, 21), 'PAY-3', 'O-103', '248.40', 'DKK', hidden('event', 102)),
        Step(
            _oct(6, 13, 40),
            'scripted',
            Ship(OrderId('O-101'), promised_by=dt.date(2026, 10, 8)),
            _ids(event=('E-03',)),
        ),
        _order(
            _oct(6, 15, 20),
            C01,
            'shop',
            (Item(P21, one, _nok('549.00')),),
            order='O-104',
            lines=('L-06',),
            event='E-09',
        ),
        _pay(_oct(6, 15, 21), 'PAY-4', 'O-104', '549.00', 'NOK', 'E-10'),
        _order(
            _oct(6, 21, 30),
            C04,
            'web',
            (Item(P11, one),),
            order='O-106',
            lines=('L-10',),
            event='E-11',
        ),
        # 7 October
        Step(
            _oct(7, 6, 0),
            'scripted',
            CancelOrder(OrderId('O-106'), reason='changed their mind'),
            _ids(event=('E-12',)),
        ),
        Step(
            _oct(7, 9, 0),
            'scripted',
            Ship(OrderId('O-102'), promised_by=dt.date(2026, 10, 9)),
            _ids(event=('E-07',)),
        ),
        _order(
            _oct(7, 11, 5),
            C05,
            'web',
            (Item(P11, one),),
            order='O-105',
            lines=('L-07',),
            event=hidden('event', 103),
        ),
        _pay(_oct(7, 11, 6), 'PAY-5', 'O-105', '349.00', 'NOK', hidden('event', 104)),
        _order(
            _oct(7, 16, 40),
            C07,
            'web',
            (Item(P10, one),),
            order='O-107',
            lines=('L-08',),
            event=hidden('event', 105),
        ),
        # 8 October
        Step(_oct(8, 7, 0), 'scripted', Roast(P10, Qty(24))),
        Step(_oct(8, 10, 5), 'scripted', Deliver(OrderId('O-101')), _ids(event=('E-04',))),
        Step(_oct(8, 12, 0), 'scripted', Deliver(OrderId('O-102')), _ids(event=('E-08',))),
        # 9 October (C-06 registers at 10:14, with the customers)
        Step(_oct(9, 14, 30), 'scripted', Erase(C07)),
        Step(_oct(9, 18, 2), 'scripted', typo),
        Step(_oct(9, 18, 5), 'scripted', fixed),
        _order(
            _oct(9, 19, 30),
            C01,
            'web',
            (Item(P10, one), Item(P11, one, _nok('0.00'))),
            order='O-108',
            lines=('L-11', 'L-12'),
            event='E-13',
        ),
        _pay(_oct(9, 19, 31), 'PAY-6', 'O-108', '129.00', 'NOK', 'E-14'),
    ]


# The jobs (W4) -------------------------------------------------------

RELAYS: Final = (
    _oct(1, 12, 0),  # closes C-01's year: its events never share a batch with the week's
    _oct(5, 8, 15),
    _oct(5, 22, 0),
    _oct(6, 14, 0),
    _oct(6, 15, 20, 30),  # after O-104's place, before PAY-4: E-09's batch alone, refused
    _oct(6, 15, 30),
    _oct(6, 15, 45),
    _oct(6, 21, 45),
    _oct(7, 6, 15),
    _oct(7, 9, 15),
    _oct(7, 22, 0),
    _oct(8, 11, 0),
    _oct(8, 22, 0),  # E-08's batch alone, refused
    _oct(9, 19, 45),
    _oct(10, 7, 0),
)
"""The relay's runs. Only 15:20:30 has seconds: that run takes nothing, so no row holds it."""

COUNTS: Final = tuple(_oct(day, 1, 0) for day in range(6, 11))
"""`count_at_close` at 01:00 UTC on 6 to 10 October counts 5 to 9 October."""

EXTRACTS: Final = (_oct(8, 21, 0), _oct(9, 21, 0))
"""`nightly_extract` at 23:00 in Oslo: the copies of 8 and 9 October."""

EXPORT: Final = _oct(9, 21, 5)
"""`csv_export` on 9 October, after C-01's 18:05 move, before Oslo's midnight."""


def _jobs() -> list[Step]:
    jobs: list[tuple[dt.datetime, Action]] = [(at, Relay()) for at in RELAYS]
    jobs += [(at, CountAtClose()) for at in COUNTS]
    jobs += [(at, NightlyExtract()) for at in EXTRACTS]
    jobs.append((EXPORT, CsvExport()))
    return [Step(at, 'scripted', action) for at, action in jobs]


def steps() -> tuple[Step, ...]:
    """The whole play, in strict moment order; none at 00:00 UTC."""
    played = sorted(
        (*_setup(), *_customers(), *_subscriptions(), *_year(), *_week(), *_jobs()),
        key=lambda step: step.at,
    )
    for before, after in zip(played, played[1:], strict=False):
        if before.at == after.at:
            raise ValueError(f'two steps at {after.at}: {before.action}, {after.action}')
    for step in played:
        if step.at.time() == dt.time(0, 0):
            raise ValueError(f'a step at midnight UTC: {step}')
    return tuple(played)


# The outside systems' facts (W17): dataset.sql's rows ----------------

FX: Final = (
    FxRate('DKK', dt.date(2026, 10, 2), Decimal('1.5580')),
    FxRate('EUR', dt.date(2026, 10, 2), Decimal('11.6200')),
    FxRate('EUR', dt.date(2026, 10, 5), Decimal('11.6400')),
    FxRate('EUR', dt.date(2026, 10, 6), Decimal('11.6100')),
    FxRate('EUR', dt.date(2026, 10, 7), Decimal('11.6300')),
    FxRate('SEK', dt.date(2026, 10, 2), Decimal('1.0610')),
    FxRate('SEK', dt.date(2026, 10, 5), Decimal('1.0600')),
    FxRate('SEK', dt.date(2026, 10, 6), Decimal('1.0620')),
)

MANAGERS: Final = (
    Manager('nora@example.invalid', 'NO'),
    Manager('sven@example.invalid', 'SE'),
    Manager('freja@example.invalid', 'DK'),
    Manager('eero@example.invalid', 'FI'),
)

TRACKER: Final = (
    WebEvent('W-01', 'V-1', 'C-01', 'view', _oct(5, 8, 5)),
    WebEvent('W-02', 'V-1', 'C-01', 'cart', _oct(5, 8, 9)),
    WebEvent('W-03', 'V-1', 'C-01', 'checkout', _oct(5, 8, 11)),
    WebEvent('W-04', 'V-2', None, 'view', _oct(5, 12, 0)),
    WebEvent('W-05', 'V-2', None, 'view', _oct(5, 12, 45)),
    WebEvent('W-06', 'V-2', None, 'cart', _oct(5, 12, 47)),
    WebEvent('W-07', 'V-3', 'C-02', 'view', _oct(5, 21, 40)),
    WebEvent('W-08', 'V-3', 'C-02', 'cart', _oct(5, 21, 45)),
    WebEvent('W-09', 'V-3', 'C-02', 'checkout', _oct(5, 21, 49)),
    WebEvent('W-10', 'V-4', 'C-04', 'view', _oct(6, 21, 20)),
    WebEvent('W-11', 'V-4', 'C-04', 'cart', _oct(6, 21, 25)),
    WebEvent('W-12', 'V-4', 'C-04', 'checkout', _oct(6, 21, 28)),
)
"""`web_events`, stamped in UTC."""

TILL_CODES: Final = (
    ProductCode('2000000000107', 'P-10'),
    ProductCode('2000000000114', 'P-11'),
    ProductCode('2100000000111', 'P-11'),
    ProductCode('2000000000206', 'P-20'),
    ProductCode('2000000000213', 'P-21'),
    ProductCode('2000000000992', None),
)


def _bergen(day: int, hour: int, minute: int) -> dt.datetime:
    """A naive moment of October 2026 in Bergen time, as the till writes it."""
    return dt.datetime(2026, 10, day, hour, minute)


TILL_RECEIPTS: Final = (
    TillReceipt('R-5001', None, _bergen(6, 17, 20)),  # no member
    TillReceipt('R-5002', 1003, _bergen(7, 10, 42)),
    TillReceipt('R-5003', 1004, _bergen(8, 12, 15)),
    TillReceipt('R-5004', 1006, _bergen(9, 15, 5)),
)

TILL_LINES: Final = (
    TillLine('R-5001', 1, '2000000000213', None, Decimal('549.00')),
    TillLine('R-5002', 1, '2100000000111', 250, Decimal('87.25')),
    TillLine('R-5002', 2, '2000000000114', None, Decimal('349.00')),
    TillLine('R-5003', 1, '2000000000992', None, Decimal('45.00')),
    TillLine('R-5003', 2, '2100000000111', 100, Decimal('34.90')),
    TillLine('R-5004', 1, '2100000000111', 500, Decimal('174.50')),
)

TILL_MEMBERS: Final = (
    TillMember(1001, 'Ingrid', 'Ingrid@Example.invalid', '7010', dt.date(2026, 10, 7)),
    TillMember(1002, 'Mikkel', 'mikkel@example.invalid', '8000', dt.date(2026, 10, 7)),
    TillMember(1003, 'Mikkel', 'Mikkel@Example.invalid', '8000', dt.date(2026, 10, 7)),
    TillMember(1004, 'Sindre', 'sindre@example.invalid', '5006', dt.date(2026, 10, 7)),
    TillMember(1005, 'Tor', 'tor@example.invalid', '0450', dt.date(2026, 10, 7)),
    TillMember(1006, 'Hilde', 'hilde@example.invalid', '5007', dt.date(2026, 10, 10)),
)
"""The club's nightly lists; the till's own spelling of the e-mails."""
