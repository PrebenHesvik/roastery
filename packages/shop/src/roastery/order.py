"""An order's life: one class per status of the feed (ADR 0005).

An order is placed, then paid or invoiced, then shipped, then
delivered; or it is cancelled before it ships. Each status is its
own class, so a state holds only what is true in it: only a paid
order has a payment id, and a shipped order carries how it was
settled. `TRANSITIONS` is the one table of legal moves, keyed on
the feed's own six words.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import (
    Final,
    Literal,
    Protocol,
    Self,
    assert_never,
    overload,
)

from roastery.clock import ZONES, local_date
from roastery.errors import IllegalTransition
from roastery.ids import (
    COUNTRIES,
    Country,
    CustomerId,
    LineId,
    OrderId,
    PaymentId,
    ProductId,
    ShipmentId,
)
from roastery.money import Money, Qty

Channel = Literal['web', 'shop']
"""Where the order was made; 'shop' is the counter."""

CHANNELS: Final[tuple[Channel, ...]] = ('shop', 'web')
"""The values of Channel, sorted, for a check at run time."""

Action = Literal['pay', 'invoice', 'ship', 'deliver', 'cancel']
"""What can be done to an order; each is a function below."""

Status = Literal[
    'placed',
    'paid',
    'invoiced',
    'shipped',
    'delivered',
    'cancelled',
]
"""The feed's word for each state: the class name in lower case."""


@dataclass(frozen=True)
class OrderLine:
    """One product on an order, at the price it was sold for.

    The quantity is negative on a credit order's line only, and
    `credit` is the one way to make one (ADR 0004).
    """

    line_id: LineId
    product_id: ProductId
    qty: Qty
    unit_price: Money

    @classmethod
    def of(
        cls,
        *,
        line_id: str,
        product_id: str,
        qty: int,
        unit_price: str,
        currency: str = 'NOK',
    ) -> Self:
        """From plain values, for tests and walks."""
        return cls(
            LineId(line_id),
            ProductId(product_id),
            _at_least_one(Qty(qty)),
            Money.of(unit_price, currency),
        )

    @classmethod
    def from_payload(
        cls,
        line_id: LineId,
        payload: Mapping[str, object],
        list_price: Money,
    ) -> Self:
        """From the web shop's JSON line, at the API's edge.

        `productId` and `qty` are required. The line takes the
        list price unless the payload gives a `price`, as text,
        in the list price's currency.
        """
        qty = _present(payload, 'qty')
        if isinstance(qty, bool) or not isinstance(qty, int):
            raise TypeError(f'qty must be a whole number: {qty!r}')
        price = list_price
        if 'price' in payload:
            text = _text(payload, 'price')
            price = Money.of(text, list_price.currency)
        return cls(
            line_id,
            ProductId(_text(payload, 'productId')),
            _at_least_one(Qty(qty)),
            price,
        )

    @classmethod
    def at_counter(
        cls,
        line_id: LineId,
        product_id: ProductId,
        qty: Qty,
        rung: Money,
    ) -> Self:
        """A counter sale, at the price the till rang.

        A counter line never takes the list price: L-06 sold at
        549.00 the day before P-21's list price started.
        """
        return cls(line_id, product_id, _at_least_one(qty), rung)

    def credit(self, line_id: LineId) -> OrderLine:
        """The line handed back: the same product and unit price,
        the quantity negated (S14). The one negative line."""
        if self.qty.value < 0:
            raise ValueError(
                f'line {self.line_id} is a credit: it cannot be '
                f'credited'
            )
        return OrderLine(
            line_id,
            self.product_id,
            Qty(-self.qty.value),
            self.unit_price,
        )


def _at_least_one(qty: Qty) -> Qty:
    """The quantity of a sale: one or more."""
    if qty.value < 1:
        raise ValueError(f'qty must be 1 or more: {qty.value}')
    return qty


def _present(source: Mapping[str, object], key: str) -> object:
    """The value under `key`; raises when it is missing."""
    if key not in source:
        raise ValueError(f'missing {key}')
    return source[key]


def _text(source: Mapping[str, object], key: str) -> str:
    """The text under `key`; raises when it is missing or not text."""
    value = _present(source, key)
    if not isinstance(value, str):
        raise TypeError(f'{key} must be text, not {value!r}')
    return value


@overload
def line_for(
    channel: Literal['web'],
) -> Callable[[LineId, Mapping[str, object], Money], OrderLine]: ...


@overload
def line_for(
    channel: Literal['shop'],
) -> Callable[[LineId, ProductId, Qty, Money], OrderLine]: ...


def line_for(
    channel: Channel,
) -> Callable[..., OrderLine]:
    """The factory a channel's lines are made with.

    The web sends a JSON line; the counter rings a price.
    """
    match channel:
        case 'web':
            return OrderLine.from_payload
        case 'shop':
            return OrderLine.at_counter
        case _:
            raise ValueError(f'channel must be one of {CHANNELS}')


@dataclass(frozen=True)
class Head:
    """What every state of an order shares."""

    order_id: OrderId
    customer_id: CustomerId
    channel: Channel
    country: Country  # as order_country chose it
    lines: tuple[OrderLine, ...]  # one or more
    credit_of: OrderId | None  # set on a credit order only

    def __post_init__(self) -> None:
        if self.channel not in CHANNELS:
            raise ValueError(f'channel must be one of {CHANNELS}')
        if self.country not in COUNTRIES:
            raise ValueError(f'country must be one of {COUNTRIES}')
        if not isinstance(self.lines, tuple) or not self.lines:
            raise ValueError(f'order {self.order_id} must have a line')
        credit = self.credit_of is not None
        if credit and self.channel != 'shop':
            raise ValueError('a credit order is made at the counter')
        if any((line.qty.value < 0) != credit for line in self.lines):
            raise ValueError(
                'a credit order has negative lines only, and no '
                'other order has one'
            )


@dataclass(frozen=True)
class Placed:
    head: Head


@dataclass(frozen=True)
class Paid:
    head: Head
    payment_id: PaymentId


@dataclass(frozen=True)
class Invoiced:
    head: Head


def _check_settled(settled: object) -> None:
    if not isinstance(settled, Paid | Invoiced):
        raise TypeError(f'settled must be Paid or Invoiced: {settled}')


@dataclass(frozen=True)
class Shipped:
    """On its way; it carries how it was settled, fixed at the move."""

    settled: Paid | Invoiced
    shipment_id: ShipmentId

    def __post_init__(self) -> None:
        _check_settled(self.settled)

    @property
    def head(self) -> Head:
        return self.settled.head


@dataclass(frozen=True)
class Delivered:
    """Arrived; final. The settlement is the one it shipped with."""

    settled: Paid | Invoiced
    shipment_id: ShipmentId

    def __post_init__(self) -> None:
        _check_settled(self.settled)

    @property
    def head(self) -> Head:
        return self.settled.head


@dataclass(frozen=True)
class Cancelled:
    """Final; its lines are marked deleted in the same unit of work."""

    head: Head
    reason: str


Order = Placed | Paid | Invoiced | Shipped | Delivered | Cancelled
"""An order is in exactly one of the six states."""

TRANSITIONS: Final[Mapping[tuple[Status, Action], Status]] = (
    MappingProxyType(
        {
            ('placed', 'pay'): 'paid',
            ('placed', 'invoice'): 'invoiced',
            ('placed', 'cancel'): 'cancelled',
            ('paid', 'ship'): 'shipped',
            ('paid', 'cancel'): 'cancelled',
            ('invoiced', 'ship'): 'shipped',
            ('invoiced', 'cancel'): 'cancelled',
            ('shipped', 'deliver'): 'delivered',
        }
    )
)
"""Every legal move: (status, action) to the next status.

Delivered and cancelled are final: no row starts from them.
"""


def status(order: Order) -> Status:
    """The feed's word: the class name in lower case."""
    match order:
        case Placed():
            return 'placed'
        case Paid():
            return 'paid'
        case Invoiced():
            return 'invoiced'
        case Shipped():
            return 'shipped'
        case Delivered():
            return 'delivered'
        case Cancelled():
            return 'cancelled'
        case _:
            assert_never(order)


def check(order: Order, action: Action) -> Status:
    """The next status; raises IllegalTransition."""
    state = status(order)
    if (state, action) not in TRANSITIONS:
        raise IllegalTransition(order.head.order_id, state, action)
    return TRANSITIONS[state, action]


def _table_disagrees(order: Order, action: Action) -> AssertionError:
    """A move the table allows and the move's own match does not."""
    return AssertionError(
        f'TRANSITIONS lets {status(order)} {action}, the move does not'
    )


def pay(order: Order, payment_id: PaymentId) -> Paid:
    check(order, 'pay')
    return Paid(order.head, payment_id)


def invoice(order: Order) -> Invoiced:
    check(order, 'invoice')
    return Invoiced(order.head)


def ship(order: Order, shipment_id: ShipmentId) -> Shipped:
    check(order, 'ship')
    match order:
        case Paid() | Invoiced():
            return Shipped(order, shipment_id)
        case _:
            raise _table_disagrees(order, 'ship')


def deliver(order: Order) -> Delivered:
    check(order, 'deliver')
    match order:
        case Shipped(settled=settled, shipment_id=shipment_id):
            return Delivered(settled, shipment_id)
        case _:
            raise _table_disagrees(order, 'deliver')


def cancel(order: Order, reason: str) -> Cancelled:
    check(order, 'cancel')
    return Cancelled(order.head, reason)


def describe(order: Order) -> str:
    """One line per state; a state the match misses is flagged."""
    match order:
        case Placed(head=head):
            return f'{head.order_id}: placed'
        case Paid(head=head, payment_id=payment_id):
            return f'{head.order_id}: paid by {payment_id}'
        case Invoiced(head=head):
            return f'{head.order_id}: invoiced'
        case Shipped(settled=settled, shipment_id=shipment_id):
            return (
                f'{settled.head.order_id}: shipped as {shipment_id}'
                f', {_settlement(settled)}'
            )
        case Delivered(settled=settled, shipment_id=shipment_id):
            return (
                f'{settled.head.order_id}: delivered, {shipment_id}'
                f', {_settlement(settled)}'
            )
        case Cancelled(head=head, reason=reason):
            return f'{head.order_id}: cancelled ({reason})'
        case _:
            assert_never(order)


def _settlement(settled: Paid | Invoiced) -> str:
    match settled:
        case Paid(payment_id=payment_id):
            return f'paid by {payment_id}'
        case Invoiced():
            return 'on invoice'
        case _:
            assert_never(settled)


@dataclass(frozen=True)
class Transition:
    """One row of the table, named `status.action` so it sorts."""

    move: str
    state: Status
    action: Action
    to: Status


def transitions() -> tuple[Transition, ...]:
    """The table as rows, sorted by move, for a frame."""
    return tuple(
        sorted(
            (
                Transition(f'{state}.{action}', state, action, to)
                for (state, action), to in TRANSITIONS.items()
            ),
            key=lambda row: row.move,
        )
    )


@dataclass(frozen=True)
class Payment:
    """The app's record of one payment (A11).

    Negative for a refund (S14). It names its order and is never
    compared with the order's total: a payment is in the
    customer's currency (ADR 0011).
    """

    payment_id: PaymentId
    order_id: OrderId
    amount: Money
    paid_on: dt.date


def _by_invoice(order: Order) -> bool:
    """Settled, or to be settled, by an invoice."""
    match order:
        case Invoiced():
            return True
        case (
            Shipped(settled=Invoiced()) | Delivered(settled=Invoiced())
        ):
            return True
        case _:
            return False


def invoice_open(order: Order, payments: Iterable[Payment]) -> bool:
    """An invoice no payment names yet: by presence, not amount.

    Paying an invoice adds a payment and no status event, so the
    state cannot say whether it is paid; the payments do.
    """
    if not _by_invoice(order):
        return False
    order_id = order.head.order_id
    return all(payment.order_id != order_id for payment in payments)


class StatusEvent(Protocol):
    """What late_orders reads of a status event (StatusChanged)."""

    @property
    def order_id(self) -> OrderId: ...

    @property
    def status(self) -> Status: ...

    @property
    def event_at(self) -> dt.datetime: ...


LATE_AFTER: Final = 2
"""Working days an order may wait, after it is settled, to ship."""


def _working_days_after(day: dt.date, count: int) -> dt.date:
    """The day `count` working days (Monday to Friday) after."""
    while count > 0:
        day += dt.timedelta(days=1)
        if day.weekday() < 5:
            count -= 1
    return day


def late_orders(
    orders: Iterable[Order],
    events: Iterable[StatusEvent],
    today: dt.date,
) -> tuple[Order, ...]:
    """Web orders paid or invoiced and not shipped in time.

    An order is late when `today` is past the second working day
    after the day it was paid or invoiced, that day read in the
    order's own zone. A counter sale never ships (O-104), so it
    is never late. Pure: it reads no clock and asks no store.
    """
    settled_at: dict[OrderId, dt.datetime] = {}
    for event in events:
        if event.status in ('paid', 'invoiced'):
            known = settled_at.get(event.order_id)
            if known is None or event.event_at < known:
                settled_at[event.order_id] = event.event_at
    late: list[Order] = []
    for order in orders:
        if not isinstance(order, Paid | Invoiced):
            continue
        head = order.head
        if head.channel == 'shop':
            continue
        if head.order_id not in settled_at:
            raise ValueError(
                f'order {head.order_id} is {status(order)} with no '
                f'event that says so'
            )
        day = local_date(settled_at[head.order_id], ZONES[head.country])
        if today > _working_days_after(day, LATE_AFTER):
            late.append(order)
    return tuple(
        sorted(late, key=lambda order: order.head.order_id.value)
    )
