"""The storefront's reads on both stores (ADR 0017).

The shop is wired as the API wires it: `App` over the store, and a
`Storefront` beside it on the same store, with the same rules. The
catalogue is dataset.sql's: P-12 Decaf has no price (F6), and the
K-2 campaign takes 15 % off P-10, P-20 and P-21 from 16 November.
Each quote is checked against what `place` charges for the same
cart, country and moment: the quote is the price.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from decimal import Decimal

import pytest

from roastery.bootstrap import App, wire
from roastery.catalogue import BeanDetails, EquipmentDetails
from roastery.checkout import Item, PlaceOrder
from roastery.customer import Email
from roastery.errors import (
    NoPrice,
    OutOfStock,
    UnknownId,
    UnknownProduct,
)
from roastery.fakes import (
    FakeClock,
    FakeFeed,
    FakeLabels,
    FakeNotifier,
    FakeProvider,
)
from roastery.ids import (
    Country,
    OrderId,
    PaymentId,
    PostalCode,
    ProductId,
)
from roastery.money import Money, Qty
from roastery.ports import Store
from roastery.pricing import standard_rules
from roastery.repository import ScriptedIds, SequentialIds
from roastery.settings import Secret, Settings, Url
from roastery.storefront import Asked, Quoted, Storefront

P10 = ProductId('P-10')
P11 = ProductId('P-11')
P12 = ProductId('P-12')
P20 = ProductId('P-20')
P21 = ProductId('P-21')
P99 = ProductId('P-99')

POSTAL = {'DK': '2100', 'FI': '00100', 'NO': '0150', 'SE': '11351'}
"""A postal code of each country, digits only."""

OCTOBER = dt.datetime(2026, 10, 5, 9, 0, tzinfo=dt.UTC)
BEFORE_K2_IN_OSLO = dt.datetime(2026, 11, 15, 22, 30, tzinfo=dt.UTC)
"""23:30 in Oslo, Stockholm and Copenhagen on 15 November; 00:30
in Helsinki on the 16th, the first day of K-2."""


def _nok(amount: str) -> Money:
    return Money.of(amount, 'NOK')


def _wire(store: Store, clock: FakeClock) -> tuple[App, Storefront]:
    """The app over the store, and the storefront beside it."""
    settings = Settings(
        database_url=Url('sqlite:///:memory:'),
        provider_url=Url('https://provider.example.invalid'),
        provider_key=Secret('not-a-key'),
    )
    ids = ScriptedIds(
        {'product': ('P-10', 'P-11', 'P-12', 'P-20', 'P-21')},
        then=SequentialIds({}),
    )
    app = wire(
        settings,
        store,
        clock=clock,
        ids=ids,
        source='scripted',
        feed=FakeFeed(clock),
        provider=FakeProvider(refund_ids=[PaymentId('PAY-300')]),
        notifier=FakeNotifier(),
        labels=FakeLabels(),
    )
    storefront = Storefront(
        store.unit_of_work('visitor'), clock, standard_rules().rules
    )
    return app, storefront


def _set_up(app: App, clock: FakeClock) -> None:
    """The catalogue, its prices, K-2 and the stock, on 1 October.

    P-11 has no bag on hand; P-12 has bags and no price.
    """
    clock.set(dt.datetime(2026, 10, 1, 7, 0, tzinfo=dt.UTC))
    beans = app.catalogue.add_category(
        'Beans', parent_id=None, sort_order=1
    )
    gear = app.catalogue.add_category(
        'Gear', parent_id=None, sort_order=2
    )
    for name, category, details in (
        (
            'Morning roast',
            beans,
            BeanDetails(250, 'Brazil', 'medium', 'dry'),
        ),
        (
            'Dark espresso',
            beans,
            BeanDetails(1000, 'India', 'dark', 'wet'),
        ),
        ('Decaf', beans, BeanDetails(250, 'Colombia', 'medium', 'wet')),
        ('Hand grinder', gear, EquipmentDetails(24, 'steel')),
        ('Pour-over kettle', gear, EquipmentDetails(12, 'steel')),
    ):
        app.catalogue.add_product(
            name, category_id=category, details=details
        )
    for product_id, price, valid_from in (
        (P10, '119.00', dt.date(2024, 1, 1)),
        (P10, '129.00', dt.date(2026, 10, 1)),
        (P11, '329.00', dt.date(2024, 1, 1)),
        (P20, '899.00', dt.date(2025, 6, 1)),
        (P21, '549.00', dt.date(2026, 10, 1)),
    ):
        app.catalogue.set_price(
            product_id, price=_nok(price), valid_from=valid_from
        )
    app.catalogue.add_campaign(
        'K-2',
        discount_pct=15,
        first_day=dt.date(2026, 11, 16),
        last_day=dt.date(2026, 11, 29),
        product_ids=(P10, P20, P21),
    )
    app.stock.roast(P10, bags=Qty(42))
    app.stock.roast(P12, bags=Qty(8))
    app.stock.stocktake(P20, on_hand=5)
    app.stock.stocktake(P21, on_hand=3)


@pytest.fixture
def shop(store: Store, clock: FakeClock) -> tuple[App, Storefront]:
    app, storefront = _wire(store, clock)
    _set_up(app, clock)
    clock.set(OCTOBER)
    return app, storefront


def _cart() -> tuple[Asked, ...]:
    """Beans and equipment: the food rate and the standard."""
    return (Asked(P10, Qty(2)), Asked(P20, Qty(1)))


def _place(
    app: App, country: Country, cart: Sequence[Asked]
) -> OrderId:
    """The cart placed by a guest of `country`, registered first,
    as the API does (F1, F2)."""
    guest = app.customers.register(
        'Guest 1',
        email=Email('guest-1@example.invalid'),
        country=country,
        postal_code=PostalCode(POSTAL[country]),
    )
    items = tuple(Item(each.product_id, each.qty) for each in cart)
    placed = app.checkout.place(PlaceOrder(guest, 'web', items))
    return placed.head.order_id


def _assert_charged_as_quoted(
    store: Store, quoted: Quoted, order_id: OrderId
) -> None:
    """The order's lines, VAT and day are the quote's."""
    with store.unit_of_work('scripted') as uow:
        order = uow.orders.get(order_id)
        booking = uow.orders.booking(order_id)
    assert [
        (line.product_id, line.qty, line.unit_price)
        for line in order.head.lines
    ] == [
        (line.product.product_id, line.qty, line.unit_price)
        for line in quoted.lines
    ]
    assert booking.vat_amount == quoted.vat
    assert booking.order_date == quoted.day
    assert order.head.country == quoted.country


# products() and product(id) --------------------------------------


def test_the_listing_is_every_product_sorted_p12_coming_soon(
    shop: tuple[App, Storefront],
) -> None:
    _, storefront = shop
    listed = storefront.products()
    assert [
        (each.product.product_id, each.unit_price, each.percent)
        for each in listed
    ] == [
        (P10, _nok('129.00'), 0),
        (P11, _nok('329.00'), 0),
        (P12, None, None),
        (P20, _nok('899.00'), 0),
        (P21, _nok('549.00'), 0),
    ]
    assert [each.in_stock for each in listed] == [
        True,
        False,
        True,
        True,
        True,
    ]
    assert listed[0].details == BeanDetails(
        250, 'Brazil', 'medium', 'dry'
    )
    assert listed[3].details == EquipmentDetails(24, 'steel')


def test_one_product_is_listed_as_the_listing_shows_it(
    shop: tuple[App, Storefront],
) -> None:
    _, storefront = shop
    assert storefront.product(P12) == storefront.products()[2]
    with pytest.raises(UnknownProduct):
        storefront.product(P99)


def test_the_listing_prices_on_norways_day(
    shop: tuple[App, Storefront], clock: FakeClock
) -> None:
    _, storefront = shop
    clock.set(BEFORE_K2_IN_OSLO)
    assert storefront.product(P10).percent == 0
    clock.advance(dt.timedelta(hours=1))
    assert storefront.product(P10).unit_price == _nok('109.65')
    assert storefront.product(P10).percent == 15


# quote(country, items) ------------------------------------------


@pytest.mark.parametrize(
    ('country', 'scheme', 'vat', 'rates'),
    [
        ('NO', 'domestic', '213.45', ('15', '25')),
        ('SE', 'export', '0.00', ('6', '25')),
        ('DK', 'export', '0.00', ('25', '25')),
        ('FI', 'export', '0.00', ('13.5', '25.5')),
    ],
)
def test_a_quote_is_what_place_charges(
    store: Store,
    shop: tuple[App, Storefront],
    country: Country,
    scheme: str,
    vat: str,
    rates: tuple[str, str],
) -> None:
    app, storefront = shop
    quoted = storefront.quote(country, _cart())
    assert quoted.day == dt.date(2026, 10, 5)
    assert quoted.scheme == scheme
    assert quoted.gross == _nok('1157.00')
    assert quoted.vat == _nok(vat)
    assert tuple(line.rate for line in quoted.lines) == tuple(
        Decimal(rate) for rate in rates
    )
    _assert_charged_as_quoted(
        store, quoted, _place(app, country, _cart())
    )


def test_a_norwegian_line_carries_its_own_vat_share(
    shop: tuple[App, Storefront],
) -> None:
    _, storefront = shop
    quoted = storefront.quote('NO', _cart())
    assert [
        (line.gross, line.vat, line.on_hand) for line in quoted.lines
    ] == [
        (_nok('258.00'), _nok('33.65'), 42),
        (_nok('899.00'), _nok('179.80'), 5),
    ]


def test_an_export_reports_the_destinations_rate_and_adds_none(
    shop: tuple[App, Storefront],
) -> None:
    _, storefront = shop
    quoted = storefront.quote('SE', (Asked(P10, Qty(1)),))
    (line,) = quoted.lines
    assert (line.unit_price, line.gross, line.vat, line.rate) == (
        _nok('129.00'),
        _nok('129.00'),
        _nok('0.00'),
        Decimal('6'),
    )


@pytest.mark.parametrize(
    ('country', 'percent', 'unit_price'),
    [('FI', 15, '109.65'), ('NO', 0, '129.00')],
)
def test_a_campaign_starts_on_the_buyers_day(
    store: Store,
    shop: tuple[App, Storefront],
    clock: FakeClock,
    country: Country,
    percent: int,
    unit_price: str,
) -> None:
    app, storefront = shop
    app.stock.roast(P11, bags=Qty(1))
    cart = (Asked(P10, Qty(2)), Asked(P11, Qty(1)))
    clock.set(BEFORE_K2_IN_OSLO)
    quoted = storefront.quote(country, cart)
    assert [
        (line.unit_price, line.percent) for line in quoted.lines
    ] == [(_nok(unit_price), percent), (_nok('329.00'), 0)]
    _assert_charged_as_quoted(store, quoted, _place(app, country, cart))


def test_a_campaign_day_quote_is_what_place_charges_in_norway(
    store: Store, shop: tuple[App, Storefront], clock: FakeClock
) -> None:
    app, storefront = shop
    clock.set(dt.datetime(2026, 11, 20, 12, 0, tzinfo=dt.UTC))
    quoted = storefront.quote('NO', _cart())
    assert [line.unit_price for line in quoted.lines] == [
        _nok('109.65'),
        _nok('764.15'),
    ]
    assert quoted.gross == _nok('983.45')
    _assert_charged_as_quoted(store, quoted, _place(app, 'NO', _cart()))


def test_p12_has_no_price_so_it_is_not_quotable(
    shop: tuple[App, Storefront],
) -> None:
    _, storefront = shop
    with pytest.raises(NoPrice) as refused:
        storefront.quote('NO', (Asked(P10, Qty(1)), Asked(P12, Qty(1))))
    assert refused.value.product_id == P12


def test_an_unknown_product_is_not_quotable(
    shop: tuple[App, Storefront],
) -> None:
    _, storefront = shop
    with pytest.raises(UnknownProduct):
        storefront.quote('NO', (Asked(P99, Qty(1)),))


def test_a_cart_needs_a_line_of_one_bag_or_more(
    shop: tuple[App, Storefront],
) -> None:
    _, storefront = shop
    with pytest.raises(ValueError, match='one item'):
        storefront.quote('NO', ())
    with pytest.raises(ValueError, match='1 or more'):
        storefront.quote('NO', (Asked(P10, Qty(-1)),))


def test_a_short_cart_is_quoted_and_refused_as_place_refuses_it(
    store: Store, shop: tuple[App, Storefront]
) -> None:
    app, storefront = shop
    cart = (Asked(P21, Qty(2)), Asked(P10, Qty(1)), Asked(P21, Qty(2)))
    quoted = storefront.quote('NO', cart)
    assert [line.on_hand for line in quoted.lines] == [3, 42, 3]
    with pytest.raises(OutOfStock) as short:
        quoted.check_stock()
    with pytest.raises(OutOfStock) as placed:
        _place(app, 'NO', cart)
    assert (
        short.value.product_id,
        short.value.wanted,
        short.value.on_hand,
    ) == (P21, 4, 3)
    assert (
        placed.value.product_id,
        placed.value.wanted,
        placed.value.on_hand,
    ) == (P21, 4, 3)
    assert storefront.quote('NO', cart[:2]).check_stock() is None


def test_a_quote_writes_nothing(
    store: Store, shop: tuple[App, Storefront]
) -> None:
    _, storefront = shop
    storefront.quote('NO', _cart())
    storefront.products()
    with store.unit_of_work('scripted') as uow:
        assert uow.orders.all() == ()
        assert uow.customers.all() == ()
        assert uow.stock.on_hand(P10) == 42


# order(id) ------------------------------------------------------


def test_an_order_is_shown_with_its_status_day_lines_and_total(
    shop: tuple[App, Storefront], clock: FakeClock
) -> None:
    app, storefront = shop
    clock.set(dt.datetime(2026, 10, 5, 22, 30, tzinfo=dt.UTC))
    order_id = _place(app, 'FI', _cart())
    shown = storefront.order(order_id)
    assert (shown.order_id, shown.status, shown.country) == (
        order_id,
        'placed',
        'FI',
    )
    assert shown.day == dt.date(2026, 10, 6)  # Helsinki's day
    assert [line.product_id for line in shown.lines] == [P10, P20]
    assert shown.total == _nok('1157.00')
    with pytest.raises(UnknownId):
        storefront.order(OrderId('O-999'))
