"""The storefront's read side: the products, a quote, an order.

`Storefront` answers what a buyer may read before and after an
order (ADR 0017). It writes nothing: each call opens one unit of
work and commits nothing. A price comes from the rules, never from
the caller: `Asked` has no field for one.

The quote prices a cart as `Checkout.place` would for a guest on
the buyer's day: the same rules composed the same way, the same
`Sale`, and the scheme from `vat.scheme_for` over a draft order
that is never stored (F8). The API reads the clock once per
request; each call here reads the clock it is given once.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from roastery.catalogue import BeanDetails, EquipmentDetails, Product
from roastery.clock import ZONES, local_date
from roastery.errors import (
    NoPrice,
    OutOfStock,
    UnknownId,
    UnknownProduct,
)
from roastery.ids import Country, CustomerId, LineId, OrderId, ProductId
from roastery.money import Money, Qty
from roastery.order import Head, OrderLine, Placed, Status, status
from roastery.ports import Clock, UnitOfWork
from roastery.pricing import (
    Quote,
    Rule,
    Sale,
    per_rule,
    price_lines,
    rule_named,
)
from roastery.vat import Scheme, VatRates, scheme_for, vat_of

GUEST: Final = 'C-0'
"""The customer id of a quote's buyer: no one yet. Text, as module
state holds no call. Never stored; the counter's customer ids start
at 1. It holds no subscription, as a guest registered a moment
before `place` holds none."""

DRAFT: Final = 'O-0'
"""The id of the draft order a quote hands `scheme_for`."""

DRAFT_LINE: Final = 'L-0'
"""The id of each line of that draft."""


def _zero() -> Money:
    return Money(Decimal('0.00'), 'NOK')


@dataclass(frozen=True)
class Listed:
    """A product as the storefront lists it, on Norway's day.

    `unit_price` and `percent` are None when no rule prices it
    (P-12): "coming soon" (F6). A listed price is a guide; the
    quote, on the buyer's day, is the price.
    """

    product: Product
    details: BeanDetails | EquipmentDetails
    unit_price: Money | None
    percent: int | None  # 0: the list price
    in_stock: bool


@dataclass(frozen=True)
class Asked:
    """A line of a cart: a product and a quantity, and no price."""

    product_id: ProductId
    qty: Qty  # 1 or more


@dataclass(frozen=True)
class QuotedLine:
    """A cart's line priced on the buyer's day.

    `vat` is the Norwegian VAT share of `gross` (0.00 for an
    export). `rate` is the destination's rate for the product's
    kind, in per cent, reported and never added to the price; None
    when no rate row covers the day. `on_hand` is the product's
    bags, all of them, however many lines name it.
    """

    product: Product
    qty: Qty
    unit_price: Money
    percent: int  # 0: the list price
    gross: Money
    vat: Money
    rate: Decimal | None
    on_hand: int


@dataclass(frozen=True)
class Quoted:
    """A cart priced for a country on its day, all in NOK.

    The lines are in the cart's order, as `place` keeps them.
    """

    country: Country
    day: dt.date
    scheme: Scheme
    lines: tuple[QuotedLine, ...]
    gross: Money
    vat: Money

    def check_stock(self) -> None:
        """OutOfStock unless every product's bags are on hand, two
        lines of one product counted together, as `place` checks.
        The first short product by id is named."""
        wanted: dict[ProductId, int] = {}
        held: dict[ProductId, int] = {}
        for line in self.lines:
            product_id = line.product.product_id
            wanted[product_id] = (
                wanted.get(product_id, 0) + line.qty.value
            )
            held[product_id] = line.on_hand
        for product_id in sorted(wanted, key=str):
            if wanted[product_id] > held[product_id]:
                raise OutOfStock(
                    product_id, wanted[product_id], held[product_id]
                )


@dataclass(frozen=True)
class Shown:
    """An order as its buyer may see it: no customer field."""

    order_id: OrderId
    status: Status
    country: Country
    day: dt.date  # order_date, on the buyer's clock
    lines: tuple[OrderLine, ...]
    total: Money


class Storefront:
    """What a buyer may read: the products, a quote, an order.

    Reads only. Each call opens one unit of work and commits
    nothing. Prices come from the rules, never from the caller.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        clock: Clock,
        rules: Mapping[str, Rule],
    ) -> None:
        self._uow = uow
        self._clock = clock
        # As Checkout.__init__ composes them (ADR 0017): a change
        # there is made here too; the equality test catches a miss.
        default = rule_named('list', rules)
        self._price = per_rule(
            {
                name: rule
                for name, rule in rules.items()
                if name != 'list'
            },
            default,
        )

    def products(self) -> tuple[Listed, ...]:
        """Every product, sorted by id, priced on Norway's day."""
        day = local_date(self._clock.now(), ZONES['NO'])
        with self._uow as uow:
            return tuple(
                self._listed(uow, product, day)
                for product in uow.catalogue.products()
            )

    def product(self, product_id: ProductId) -> Listed:
        """One product on Norway's day; UnknownProduct if none."""
        day = local_date(self._clock.now(), ZONES['NO'])
        with self._uow as uow:
            return self._listed(uow, _product(uow, product_id), day)

    def quote(self, country: Country, items: Sequence[Asked]) -> Quoted:
        """The cart priced for a guest in `country` on its day.

        UnknownProduct for an id the shop does not list; NoPrice
        for a product no rule prices on the day. A short line is
        reported in `on_hand`, not refused: see `check_stock`.
        """
        if not items:
            raise ValueError('a quote needs one item or more')
        for item in items:
            if item.qty.value < 1:
                raise ValueError(f'qty must be 1 or more: {item}')
        day = local_date(self._clock.now(), ZONES[country])
        with self._uow as uow:
            products = [
                _product(uow, item.product_id) for item in items
            ]
            discounts = uow.rules.all()
            quotes = price_lines(
                (
                    Sale(
                        CustomerId(GUEST),
                        product,
                        day,
                        uow.prices.of(product.product_id),
                        discounts,
                        (),
                    )
                    for product in products
                ),
                self._price,
            )
            draft = Placed(
                Head(
                    OrderId(DRAFT),
                    CustomerId(GUEST),
                    'web',
                    country,
                    tuple(
                        OrderLine(
                            LineId(DRAFT_LINE),
                            item.product_id,
                            item.qty,
                            quote.unit_price,
                        )
                        for item, quote in zip(
                            items, quotes, strict=True
                        )
                    ),
                    None,
                )
            )
            scheme = scheme_for(draft, day)
            rates = VatRates(uow.vat_rates.all())
            lines = tuple(
                _line(
                    item,
                    product,
                    quote,
                    scheme,
                    _rate(rates, scheme, country, product, day),
                    uow.stock.on_hand(product.product_id),
                )
                for item, product, quote in zip(
                    items, products, quotes, strict=True
                )
            )
        gross = _zero()
        vat = _zero()
        for line in lines:
            gross += line.gross
            vat += line.vat
        return Quoted(country, day, scheme, lines, gross, vat)

    def order(self, order_id: OrderId) -> Shown:
        """The order's status, country, day, lines and total.

        UnknownId if the store holds no such order. The API calls
        it only with an id a token found (ADR 0016).
        """
        with self._uow as uow:
            order = uow.orders.get(order_id)
            booking = uow.orders.booking(order_id)
        head = order.head
        total = _zero()
        for line in head.lines:
            total += line.unit_price.times(line.qty)
        return Shown(
            head.order_id,
            status(order),
            head.country,
            booking.order_date,
            head.lines,
            total,
        )

    def _listed(
        self, uow: UnitOfWork, product: Product, day: dt.date
    ) -> Listed:
        """The product priced alone: NoPrice gives None (F6)."""
        product_id = product.product_id
        sale = Sale(
            CustomerId(GUEST),
            product,
            day,
            uow.prices.of(product_id),
            uow.rules.all(),
            (),
        )
        try:
            (quote,) = price_lines((sale,), self._price)
        except NoPrice:
            price, percent = None, None
        else:
            price, percent = quote.unit_price, quote.percent
        return Listed(
            product,
            uow.catalogue.details(product_id),
            price,
            percent,
            uow.stock.on_hand(product_id) > 0,
        )


def _product(uow: UnitOfWork, product_id: ProductId) -> Product:
    """The product; UnknownProduct if the shop lists none."""
    try:
        return uow.catalogue.product(product_id)
    except UnknownId:
        raise UnknownProduct(product_id) from None


def _rate(
    rates: VatRates,
    scheme: Scheme,
    country: Country,
    product: Product,
    day: dt.date,
) -> Decimal | None:
    """The country's rate for the product's kind on the day.

    At home the lookup is strict, as `place`'s: a day no row
    covers raises LookupError. For an export the rate is only
    reported, so a day no row covers gives None and the line
    still sells (ADR 0010).
    """
    if scheme == 'domestic':
        return rates.rate_on(country, product.kind, day)
    try:
        return rates.rate_on(country, product.kind, day)
    except LookupError:
        return None


def _line(
    item: Asked,
    product: Product,
    quote: Quote,
    scheme: Scheme,
    rate: Decimal | None,
    on_hand: int,
) -> QuotedLine:
    """A priced line and its VAT share, as `place` books it: an
    export's share is zero, whatever its rate."""
    gross = quote.unit_price.times(item.qty)
    vat = vat_of(gross, Decimal(0) if rate is None else rate, scheme)
    return QuotedLine(
        product,
        item.qty,
        quote.unit_price,
        quote.percent,
        gross,
        vat,
        rate,
        on_hand,
    )
