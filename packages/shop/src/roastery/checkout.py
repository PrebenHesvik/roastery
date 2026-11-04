"""Checkout: an order placed, cancelled or credited, in one call each.

`Checkout` is the facade over what a sale touches: the customer's
country, the price on the order's day, the stock, the VAT share and
the outbox. Each call checks everything that can refuse it first,
then draws its ids, then writes in one unit of work (A35). The
events go on the bus after the commit, so a handler sees only what
is kept and its failure cannot undo the sale (C26, C29).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import assert_never

from roastery import order as orders
from roastery.catalogue import Product
from roastery.clock import ZONES, local_date
from roastery.customers import (
    NoCountry,
    UnknownCustomer,
    country_of,
    find_customer,
)
from roastery.errors import (
    AlreadyCredited,
    NoSuchCustomer,
    NotCreditable,
    OutOfStock,
    UnknownId,
    UnknownProduct,
)
from roastery.events import (
    CollectingBus,
    OrderInvoiced,
    OrderPlaced,
    StatusChanged,
)
from roastery.ids import (
    Country,
    CustomerId,
    EventId,
    LineId,
    MovementId,
    OrderId,
    ProductId,
)
from roastery.money import Money, Qty
from roastery.order import (
    Channel,
    Delivered,
    Head,
    Invoiced,
    Order,
    OrderLine,
    Paid,
    Placed,
)
from roastery.ports import (
    Booking,
    Clock,
    Ids,
    Movement,
    UnitOfWork,
)
from roastery.pricing import (
    Rule,
    Sale,
    per_rule,
    price_lines,
    rule_named,
)
from roastery.result import Err, Ok
from roastery.vat import VatRates, scheme_for, vat_of


@dataclass(frozen=True)
class Item:
    """One line asked for.

    price None: the list price on the order's day, with the
    rules that hold. A price given: set by hand, as the till
    rang it (L-06 at 549.00) or a free sample (L-12 at 0.00).
    """

    product_id: ProductId
    qty: Qty  # 1 or more
    price: Money | None = None


@dataclass(frozen=True)
class PlaceOrder:
    """An order on the web or at the counter (channel 'shop')."""

    customer_id: CustomerId
    channel: Channel
    items: tuple[Item, ...]  # one or more


def order_country(
    channel: Channel,
    found: Ok[Country] | Err[NoCountry | UnknownCustomer],
) -> Country:
    """The country an order is taxed and dated in (ADR 0010).

    Decided here, once, in plain sight: the counter is in Bergen,
    and a customer with no country (C-05's O-105) is Norway on
    purpose. The VAT lookup never falls back to a country.
    """
    if channel == 'shop':
        return 'NO'  # the counter is in Bergen
    match found:
        case Ok(country):
            return country
        case Err(NoCountry()):
            return 'NO'  # C-05's O-105: Norway, on purpose
        case Err(UnknownCustomer() as why):
            raise NoSuchCustomer(why.customer_id)
        case _:
            assert_never(found)


class Checkout:
    def __init__(
        self,
        uow: UnitOfWork,
        clock: Clock,
        ids: Ids,
        events: CollectingBus,
        rules: Mapping[str, Rule],
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids
        self._events = events
        default = rule_named('list', rules)
        self._price = per_rule(
            {
                name: rule
                for name, rule in rules.items()
                if name != 'list'
            },
            default,
        )

    def place(self, command: PlaceOrder) -> Placed | Invoiced:
        """The order, its lines, a sold movement per line, the
        VAT share and the outbox rows, in one unit of work.

        A business account's order is invoiced in the same
        unit of work (S13): placed and invoiced, two events.
        """
        if not command.items:
            raise ValueError('an order needs one item or more')
        for item in command.items:
            if item.qty.value < 1:
                raise ValueError(f'qty must be 1 or more: {item}')
        now = self._clock.now()
        with self._uow as uow:
            found = country_of(command.customer_id, uow.customers)
            country = order_country(command.channel, found)
            customer = find_customer(command.customer_id, uow.customers)
            day = local_date(now, ZONES[country])
            products = [
                _product(uow, item.product_id) for item in command.items
            ]
            prices = self._prices(uow, command, products, day)
            _check_stock(uow, command.items)
            order_id = OrderId(self._ids.next('order'))
            lines = tuple(
                OrderLine(
                    LineId(self._ids.next('line')),
                    item.product_id,
                    item.qty,
                    price,
                )
                for item, price in zip(
                    command.items, prices, strict=True
                )
            )
            placed = Placed(
                Head(
                    order_id,
                    command.customer_id,
                    command.channel,
                    country,
                    lines,
                    None,
                )
            )
            vat = _vat_amount(uow, placed, products, day)
            uow.orders.add(placed, Booking(day, vat, now))
            self._sold(uow, lines, now)
            self._status(uow, order_id, 'placed', now)
            done: Placed | Invoiced = placed
            if customer.account_kind == 'business':
                done = orders.invoice(placed)
                uow.orders.save(done)
                self._status(uow, order_id, 'invoiced', now)
            uow.commit()
        self._events.publish(OrderPlaced(order_id))
        if isinstance(done, Invoiced):
            self._events.publish(OrderInvoiced(order_id))
        return done

    def cancel(self, order_id: OrderId, *, reason: str) -> None:
        """Cancelled; its lines marked deleted; each line's bag
        back as a sold movement of the opposite sign (C21)."""
        now = self._clock.now()
        with self._uow as uow:
            cancelled = orders.cancel(uow.orders.get(order_id), reason)
            uow.orders.save(cancelled)
            uow.orders.mark_deleted(order_id, now)
            self._sold(uow, cancelled.head.lines, now, back=True)
            self._status(uow, order_id, 'cancelled', now)
            uow.commit()

    def credit_for(
        self, order_id: OrderId, *, line_id: LineId
    ) -> OrderId:
        """A credit order at the counter: one negative line for
        the line returned, its bag back (C21); placed (S14)."""
        now = self._clock.now()
        with self._uow as uow:
            sale = uow.orders.get(order_id)
            head = sale.head
            if head.credit_of is not None:
                raise NotCreditable(order_id, 'a credit order')
            if not isinstance(sale, Paid | Delivered):
                raise NotCreditable(order_id, orders.status(sale))
            line = _line(head, line_id)
            _check_not_credited(uow, sale, line)
            found = country_of(head.customer_id, uow.customers)
            country = order_country('shop', found)
            day = local_date(now, ZONES[country])
            product = _product(uow, line.product_id)
            credit_id = OrderId(self._ids.next('order'))
            back = line.credit(LineId(self._ids.next('line')))
            credit = Placed(
                Head(
                    credit_id,
                    head.customer_id,
                    'shop',
                    country,
                    (back,),
                    order_id,
                )
            )
            vat = _vat_amount(uow, credit, [product], day)
            uow.orders.add(credit, Booking(day, vat, now))
            self._sold(uow, (back,), now)
            self._status(uow, credit_id, 'placed', now)
            uow.commit()
        self._events.publish(OrderPlaced(credit_id))
        return credit_id

    def _prices(
        self,
        uow: UnitOfWork,
        command: PlaceOrder,
        products: Sequence[Product],
        day: dt.date,
    ) -> list[Money]:
        """Each item's unit price: by hand when given, else the
        pricing rules on the order's day (A14, A31)."""
        asked = [
            (index, product)
            for index, (item, product) in enumerate(
                zip(command.items, products, strict=True)
            )
            if item.price is None
        ]
        discounts = uow.rules.all()
        subscriptions = uow.subscriptions.of_customer(
            command.customer_id
        )
        quotes = price_lines(
            (
                Sale(
                    command.customer_id,
                    product,
                    day,
                    uow.prices.of(product.product_id),
                    discounts,
                    subscriptions,
                )
                for _, product in asked
            ),
            self._price,
        )
        listed = {
            index: quote.unit_price
            for (index, _), quote in zip(asked, quotes, strict=True)
        }
        return [
            listed[index] if item.price is None else item.price
            for index, item in enumerate(command.items)
        ]

    def _sold(
        self,
        uow: UnitOfWork,
        lines: Sequence[OrderLine],
        now: dt.datetime,
        *,
        back: bool = False,
    ) -> None:
        """A sold movement per line: out at place, in for a credit
        line, and the opposite sign when a cancel undoes it."""
        for line in lines:
            qty = line.qty.value if back else -line.qty.value
            uow.stock.add(
                Movement(
                    MovementId(self._ids.next('movement')),
                    line.product_id,
                    now,
                    'sold',
                    qty,
                )
            )

    def _status(
        self,
        uow: UnitOfWork,
        order_id: OrderId,
        word: orders.Status,
        now: dt.datetime,
    ) -> None:
        uow.outbox.add(
            StatusChanged(
                EventId(self._ids.next('event')), order_id, word, now
            )
        )


def _product(uow: UnitOfWork, product_id: ProductId) -> Product:
    """The product; UnknownProduct if the shop lists none."""
    try:
        return uow.catalogue.product(product_id)
    except UnknownId:
        raise UnknownProduct(product_id) from None


def _check_stock(uow: UnitOfWork, items: Sequence[Item]) -> None:
    """OutOfStock unless every product's bags are on hand, two
    lines of one product counted together."""
    wanted: dict[ProductId, int] = {}
    for item in items:
        wanted[item.product_id] = (
            wanted.get(item.product_id, 0) + item.qty.value
        )
    for product_id in sorted(wanted, key=str):
        held = uow.stock.on_hand(product_id)
        if wanted[product_id] > held:
            raise OutOfStock(product_id, wanted[product_id], held)


def _vat_amount(
    uow: UnitOfWork,
    order: Order,
    products: Sequence[Product],
    day: dt.date,
) -> Money:
    """The VAT shares of the lines, each to the øre, summed (C18).

    Each line on its own kind's rate on the order's day, under the
    order's scheme (A12, C22).
    """
    rates = VatRates(uow.vat_rates.all())
    scheme = scheme_for(order, day)
    total = Money(Decimal('0.00'), 'NOK')
    for line, product in zip(order.head.lines, products, strict=True):
        rate = rates.rate_on(order.head.country, product.kind, day)
        gross = line.unit_price.times(line.qty)
        total += vat_of(gross, rate, scheme)
    return total


def _line(head: Head, line_id: LineId) -> OrderLine:
    """The order's line; UnknownId if it has none of that id."""
    for line in head.lines:
        if line.line_id == line_id:
            return line
    raise UnknownId('line', str(line_id))


def _check_not_credited(
    uow: UnitOfWork, sale: Order, line: OrderLine
) -> None:
    """AlreadyCredited when the line was handed back before.

    A credit line names no line of the sale, so it is matched by
    what it copies: the product, the unit price and the quantity
    negated. A sale with two such lines can be credited twice. A
    cancelled credit order handed nothing back.
    """

    def same(each: OrderLine) -> bool:
        return (each.product_id, each.unit_price) == (
            line.product_id,
            line.unit_price,
        )

    sold = sum(
        1
        for each in sale.head.lines
        if same(each) and each.qty == line.qty
    )
    credited = sum(
        1
        for credit in uow.orders.credits_of(sale.head.order_id)
        if not isinstance(credit, orders.Cancelled)
        for each in credit.head.lines
        if same(each) and each.qty.value == -line.qty.value
    )
    if credited >= sold:
        raise AlreadyCredited(line.line_id)
