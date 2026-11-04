"""The read side: rows out of the store, never a frame.

Each report reads through a unit of work and writes nothing. A row
is a frozen dataclass and a report is a sorted tuple of them, so the
memory store and sqlite give the same rows (ADR 0002, C2). An order
that was cancelled has no sale; a credit order is a negative one
and nets the sale it returns.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Final

from roastery.catalogue import Kind, Product
from roastery.customers import NoCountry, UnknownCustomer, country_of
from roastery.ids import Country, CustomerId, LineId, ProductId
from roastery.money import Money
from roastery.order import Cancelled, Order, OrderLine
from roastery.parsing import Parsed, ParsedLine, Reject
from roastery.ports import UnitOfWork
from roastery.result import Err, Ok

SALES_BY_COUNTRY: Final = ('country', 'orders', 'amount')
"""The columns of `SalesByCountry`, in the order its rows read."""


@dataclass(frozen=True)
class SalesByKind:
    """One kind's sales in one currency: the read side's row."""

    kind: Kind
    lines: int
    qty: int
    amount: Money


@dataclass(frozen=True)
class SalesByCountry:
    """A customer country's sales; no country is its own row."""

    country: Country | None
    orders: int
    amount: Money


@dataclass(frozen=True)
class SalesByCustomer:
    """One customer's sales."""

    customer_id: CustomerId
    orders: int
    amount: Money


def kind_of_line(
    line: OrderLine, products: Mapping[ProductId, Product]
) -> Kind:
    """Beans or equipment: the kind of the line's product."""
    return products[line.product_id].kind


def _sales(uow: UnitOfWork) -> tuple[Order, ...]:
    """The orders that sold something: every one but a cancel."""
    return tuple(
        order
        for order in uow.orders.all()
        if not isinstance(order, Cancelled)
    )


def _amount(order: Order) -> Money | None:
    """The order's lines at their prices; None for no line."""
    total: Money | None = None
    for line in order.head.lines:
        each = line.unit_price.times(line.qty)
        total = each if total is None else total + each
    return total


def sales_by_kind(uow: UnitOfWork) -> tuple[SalesByKind, ...]:
    """The sales of each kind and currency, sorted by both."""
    with uow:
        products = {p.product_id: p for p in uow.catalogue.products()}
        orders = _sales(uow)
    found: dict[tuple[Kind, str], tuple[int, int, Money]] = {}
    for order in orders:
        for line in order.head.lines:
            kind = kind_of_line(line, products)
            money = line.unit_price.times(line.qty)
            key = (kind, money.currency)
            lines, qty, total = found.get(
                key, (0, 0, Money.of(0, key[1]))
            )
            found[key] = (
                lines + 1,
                qty + line.qty.value,
                total + money,
            )
    return tuple(
        SalesByKind(kind, *found[kind, currency])
        for kind, currency in sorted(found)
    )


def sales_by_country(
    uow: UnitOfWork,
) -> tuple[SalesByCountry, ...]:
    """The sales of each customer country, sorted by country.

    It reads the customer's country, not the order's (C10): an
    order of a customer with no country, or of one erased, counts
    under no country, which sorts last.
    """
    with uow:
        orders = _sales(uow)
        countries: dict[CustomerId, Country | None] = {}
        for order in orders:
            who = order.head.customer_id
            if who not in countries:
                match country_of(who, uow.customers):
                    case Ok(country):
                        countries[who] = country
                    case Err(NoCountry() | UnknownCustomer()):
                        countries[who] = None
    found: dict[tuple[Country | None, str], tuple[int, Money]] = {}
    for order in orders:
        money = _amount(order)
        if money is None:
            continue
        key = (countries[order.head.customer_id], money.currency)
        count, total = found.get(key, (0, Money.of(0, key[1])))
        found[key] = (count + 1, total + money)
    keys = sorted(found, key=lambda k: (k[0] is None, k[0] or '', k[1]))
    return tuple(SalesByCountry(key[0], *found[key]) for key in keys)


def sales_by_customer(
    uow: UnitOfWork,
) -> tuple[SalesByCustomer, ...]:
    """The sales of each customer, sorted by customer id."""
    with uow:
        orders = _sales(uow)
    found: dict[tuple[str, str], tuple[int, Money]] = {}
    for order in orders:
        money = _amount(order)
        if money is None:
            continue
        key = (str(order.head.customer_id), money.currency)
        count, total = found.get(key, (0, Money.of(0, key[1])))
        found[key] = (count + 1, total + money)
    return tuple(
        SalesByCustomer(CustomerId(who), *found[who, currency])
        for who, currency in sorted(found)
    )


@dataclass(frozen=True)
class ShopLine:
    """A line of a counter order, as the till is set against."""

    line_id: LineId
    product_id: ProductId
    placed_at: dt.datetime  # UTC


@dataclass(frozen=True)
class Reconciliation:
    """The till against the shop's counter orders."""

    matched: tuple[tuple[ParsedLine, LineId], ...]
    walk_ins: tuple[ParsedLine, ...]  # no shop order matches
    unmatched: tuple[LineId, ...]  # a shop line not rung
    rejects: tuple[Reject, ...]


def shop_lines(uow: UnitOfWork, day: dt.date) -> tuple[ShopLine, ...]:
    """The lines of the `shop` orders booked on `day`, by line id."""
    with uow:
        found = [
            ShopLine(line.line_id, line.product_id, booking.at)
            for order in uow.orders.all()
            if order.head.channel == 'shop'
            and not isinstance(order, Cancelled)
            and order.head.credit_of is None
            for booking in [uow.orders.booking(order.head.order_id)]
            if booking.order_date == day
            for line in order.head.lines
        ]
    return tuple(sorted(found, key=lambda each: str(each.line_id)))


def reconcile_till(
    sales: Parsed[ParsedLine],
    lines: Iterable[ShopLine],
    within: dt.timedelta,
) -> Reconciliation:
    """Set the till's sales against the counter's order lines.

    A till line matches the shop line of the same product placed
    within `within` of it, the nearest first; a line matches once.
    The till has no customer, so the match is never by customer.
    Pure: it moves no stock and writes no order (C13, ADR 0012).
    """
    free = sorted(lines, key=lambda each: str(each.line_id))
    matched: list[tuple[ParsedLine, LineId]] = []
    walk_ins: list[ParsedLine] = []
    rejects: list[Reject] = []
    for answer in sales:
        match answer:
            case Err(reject):
                rejects.append(reject)
            case Ok(sale):
                near = [
                    (
                        abs(each.placed_at - sale.sold_at),
                        str(each.line_id),
                    )
                    for each in free
                    if each.product_id == sale.product_id
                    and abs(each.placed_at - sale.sold_at) <= within
                ]
                if not near:
                    walk_ins.append(sale)
                    continue
                best = LineId(min(near)[1])
                matched.append((sale, best))
                free = [each for each in free if each.line_id != best]
    return Reconciliation(
        tuple(matched),
        tuple(walk_ins),
        tuple(each.line_id for each in free),
        tuple(rejects),
    )
