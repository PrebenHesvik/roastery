"""The handlers on both stores (ADR 0016).

The shop is wired as the API wires it: `App` over the store, and a
`Storefront` beside it. Every row of `STATUS` is checked, and a
client's price is shown never to reach the order.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pytest

from roastery.api import (
    STATUS,
    Forbidden,
    Orphaned,
    PriceChanged,
    RequestValidationError,
    checkout_handler,
    order_handler,
    plain,
    problem,
    product_handler,
    products_handler,
    quote_handler,
)
from roastery.bootstrap import App, wire
from roastery.catalogue import BeanDetails, EquipmentDetails
from roastery.checkout import Checkout
from roastery.customers import Customers
from roastery.errors import (
    AlreadyCredited,
    DuplicateId,
    IllegalSubscriptionMove,
    IllegalTransition,
    KeyReused,
    NoAddress,
    NoOpenInvoice,
    NoPrice,
    NoSuchCustomer,
    NotCreditable,
    NothingToRefund,
    NotShippable,
    OutOfStock,
    PaymentMismatch,
    PeriodOverlap,
    ShopError,
    UnknownId,
    UnknownProduct,
    WrongKind,
)
from roastery.fakes import (
    FakeClock,
    FakeFeed,
    FakeLabels,
    FakeNotifier,
    FakeProvider,
)
from roastery.ids import (
    CustomerId,
    LineId,
    OrderId,
    PaymentId,
    ProductId,
    SubscriptionId,
)
from roastery.money import Money, Qty
from roastery.ports import (
    ProviderRefused,
    ProviderUnavailable,
    Store,
)
from roastery.pricing import standard_rules
from roastery.repository import ScriptedIds, SequentialIds
from roastery.settings import Secret, Settings, Url
from roastery.storefront import Storefront

P10 = ProductId('P-10')
P20 = ProductId('P-20')
OCTOBER = dt.datetime(2026, 10, 5, 9, 0, tzinfo=dt.UTC)


@dataclass(frozen=True)
class Deps:
    """What the API hands the handlers."""

    customers: Customers
    checkout: Checkout
    storefront: Storefront


def _nok(amount: str) -> Money:
    return Money.of(amount, 'NOK')


@pytest.fixture
def shop(
    store: Store, clock: FakeClock
) -> tuple[Deps, App, Store, FakeClock]:
    settings = Settings(
        database_url=Url('sqlite:///:memory:'),
        provider_url=Url('https://provider.example.invalid'),
        provider_key=Secret('not-a-key'),
    )
    ids = ScriptedIds(
        {'product': ('P-10', 'P-20')}, then=SequentialIds({})
    )
    app = wire(
        settings,
        store,
        clock=clock,
        ids=ids,
        source='visitor',
        feed=FakeFeed(clock),
        provider=FakeProvider(refund_ids=[PaymentId('PAY-300')]),
        notifier=FakeNotifier(),
        labels=FakeLabels(),
    )
    clock.set(dt.datetime(2026, 10, 1, 7, 0, tzinfo=dt.UTC))
    beans = app.catalogue.add_category(
        'Beans', parent_id=None, sort_order=1
    )
    gear = app.catalogue.add_category(
        'Gear', parent_id=None, sort_order=2
    )
    app.catalogue.add_product(
        'Morning roast',
        category_id=beans,
        details=BeanDetails(250, 'Brazil', 'medium', 'dry'),
    )
    app.catalogue.add_product(
        'Hand grinder',
        category_id=gear,
        details=EquipmentDetails(24, 'steel'),
    )
    app.catalogue.set_price(
        P10, price=_nok('129.00'), valid_from=dt.date(2024, 1, 1)
    )
    app.catalogue.set_price(
        P20, price=_nok('899.00'), valid_from=dt.date(2024, 1, 1)
    )
    app.stock.roast(P10, bags=Qty(42))
    app.stock.stocktake(P20, on_hand=5)
    clock.set(OCTOBER)
    storefront = Storefront(
        store.unit_of_work('visitor'), clock, standard_rules().rules
    )
    deps = Deps(app.customers, app.checkout, storefront)
    return deps, app, store, clock


def _body(
    items: list[dict[str, Any]], total: str, **more: Any
) -> dict[str, Any]:
    return {
        'country': 'NO',
        'postal_code': '0150',
        'items': items,
        'total': {'amount': total, 'currency': 'NOK'},
        **more,
    }


def _request(body: Mapping[str, object], guest: int = 1) -> dict:
    return {'body': body, 'guest': guest}


# STATUS ----------------------------------------------------------

_ROWS: list[tuple[Exception, int]] = [
    (IllegalTransition(OrderId('O-1'), 'paid', 'ship'), 409),
    (
        IllegalSubscriptionMove(
            SubscriptionId('S-1'),
            'active',
            'resume',
        ),
        409,
    ),
    (NotShippable(OrderId('O-1')), 409),
    (NoAddress(OrderId('O-1')), 409),
    (NotCreditable(OrderId('O-1'), 'placed'), 409),
    (AlreadyCredited(LineId('L-1')), 409),
    (NoOpenInvoice(OrderId('O-1')), 409),
    (NothingToRefund(OrderId('O-1')), 409),
    (PaymentMismatch(PaymentId('PAY-1')), 409),
    (KeyReused('k'), 409),
    (DuplicateId('order', 'O-1'), 409),
    (OutOfStock(P10, 3, 2), 409),
    (PeriodOverlap('price', 'P-10', dt.date(2026, 1, 1)), 409),
    (UnknownId('order', 'O-9'), 404),
    (NoSuchCustomer(CustomerId('C-9')), 404),
    (UnknownProduct(P10), 422),
    (WrongKind(P10, 'beans'), 422),
    (NoPrice(P10, dt.date(2026, 1, 1)), 422),
    (ProviderRefused('declined'), 402),
    (ProviderUnavailable('down'), 503),
    (RequestValidationError('bad'), 400),
    (Forbidden('staff'), 403),
]


def _subclasses(base: type) -> set[type]:
    found = set()
    for each in base.__subclasses__():
        found.add(each)
        found |= _subclasses(each)
    return found


def test_status_holds_every_shop_error() -> None:
    assert _subclasses(ShopError) <= set(STATUS)
    assert {ProviderRefused, ProviderUnavailable} <= set(STATUS)


def test_every_status_row_is_checked() -> None:
    checked = {type(error) for error, _ in _ROWS} | {PriceChanged}
    assert checked == set(STATUS)


@pytest.mark.parametrize(
    ('error', 'status'),
    _ROWS,
    ids=[type(error).__name__ for error, _ in _ROWS],
)
def test_problem_json_per_status_row(
    error: Exception, status: int
) -> None:
    reply = problem(error)
    assert reply['status'] == status
    assert reply['content_type'] == 'application/problem+json'
    body = reply['body']
    assert isinstance(body, dict)
    assert body['code'] == type(error).__name__
    assert body['status'] == status
    assert body['type'] == 'about:blank'
    assert body['detail'] == str(error)


def test_problem_carries_the_errors_attributes() -> None:
    body = problem(OutOfStock(P10, 3, 2))['body']
    assert body == {
        'type': 'about:blank',
        'title': 'Out of stock',
        'status': 409,
        'code': 'OutOfStock',
        'detail': 'product P-10: 3 wanted, 2 on hand',
        'product_id': 'P-10',
        'wanted': 3,
        'on_hand': 2,
    }


def test_an_unknown_error_is_a_500_without_detail() -> None:
    reply = problem(ZeroDivisionError('secret'))
    assert reply['status'] == 500
    assert reply['body'] == {
        'type': 'about:blank',
        'title': 'Internal error',
        'status': 500,
        'code': 'InternalError',
    }


# reads -----------------------------------------------------------


def test_products_are_listed_and_sorted(shop) -> None:
    deps, *_ = shop
    reply = products_handler({}, deps)
    assert reply['status'] == 200
    products = reply['body']['products']
    assert [each['product']['product_id'] for each in products] == [
        'P-10',
        'P-20',
    ]
    assert products[0]['unit_price'] == {
        'amount': '129.00',
        'currency': 'NOK',
    }


def test_product_and_its_404(shop) -> None:
    deps, *_ = shop
    found = product_handler({'path': {'id': 'P-20'}}, deps)
    assert found['status'] == 200
    assert found['body']['product']['name'] == 'Hand grinder'
    missing = product_handler({'path': {'id': 'P-99'}}, deps)
    assert missing['status'] == 404
    assert missing['body']['code'] == 'UnknownId'


def test_a_malformed_product_id_is_a_400(shop) -> None:
    deps, *_ = shop
    reply = product_handler({'path': {'id': 'banana'}}, deps)
    assert reply['status'] == 400
    assert reply['body']['code'] == 'RequestValidationError'


def test_quote_prices_the_cart(shop) -> None:
    deps, *_ = shop
    body = _body([{'product_id': 'P-10', 'qty': 2}], '258.00')
    reply = quote_handler(_request(body), deps)
    assert reply['status'] == 200
    assert reply['body']['gross'] == {
        'amount': '258.00',
        'currency': 'NOK',
    }


def test_quote_of_an_unknown_product_is_422(shop) -> None:
    deps, *_ = shop
    body = _body([{'product_id': 'P-99', 'qty': 1}], '1.00')
    reply = quote_handler(_request(body), deps)
    assert reply['status'] == 422
    assert reply['body']['code'] == 'UnknownProduct'


@pytest.mark.parametrize(
    'body',
    [
        None,
        {'country': 'NO', 'items': []},
        {'country': 'XX', 'items': [{'product_id': 'P-10', 'qty': 1}]},
        {'country': 'NO', 'items': [{'product_id': 'P-10', 'qty': 0}]},
        {
            'country': 'NO',
            'items': [{'product_id': 'P-10', 'qty': 1.5}],
        },
        {'country': 'NO', 'items': [{'product_id': 10, 'qty': 1}]},
    ],
)
def test_a_body_that_does_not_parse_is_a_400(shop, body) -> None:
    deps, *_ = shop
    reply = quote_handler({'body': body}, deps)
    assert reply['status'] == 400
    assert reply['body']['code'] == 'RequestValidationError'


# checkout --------------------------------------------------------


def _orders(store: Store) -> list[OrderId]:
    with store.unit_of_work('scripted') as uow:
        return [
            OrderId(f'O-{n}')
            for n in range(1, 20)
            if _has(uow, OrderId(f'O-{n}'))
        ]


def _has(uow, order_id: OrderId) -> bool:
    try:
        uow.orders.get(order_id)
    except UnknownId:
        return False
    return True


def test_checkout_places_the_order_for_a_pseudonym(shop) -> None:
    deps, app, store, _ = shop
    body = _body([{'product_id': 'P-10', 'qty': 2}], '258.00')
    reply = checkout_handler(_request(body, guest=7), deps)
    assert reply['status'] == 201
    placed = reply['body']
    assert placed['total'] == {'amount': '258.00', 'currency': 'NOK'}
    with store.unit_of_work('scripted') as uow:
        customer = uow.customers.get(CustomerId(placed['customer_id']))
        order = uow.orders.get(OrderId(placed['order_id']))
    assert customer.name == 'Guest 7'
    assert customer.email is not None
    assert customer.email.value == 'guest-7@example.invalid'
    assert order.head.channel == 'web'
    assert deps.storefront.order(order.head.order_id).total == _nok(
        '258.00'
    )


def test_a_client_price_never_reaches_the_order(shop) -> None:
    deps, app, store, _ = shop
    cheat = {'product_id': 'P-10', 'qty': 2, 'price': '1.00'}
    body = _body([cheat], '258.00', price='1.00')
    reply = checkout_handler(_request(body), deps)
    assert reply['status'] == 201
    with store.unit_of_work('scripted') as uow:
        order = uow.orders.get(OrderId(reply['body']['order_id']))
    (line,) = order.head.lines
    assert line.unit_price == _nok('129.00')  # the list price
    # and a total built from the cheat is the price that changed
    low = _body([cheat], '2.00')
    changed = checkout_handler(_request(low, guest=2), deps)
    assert changed['status'] == 409
    assert changed['body']['code'] == 'PriceChanged'


def test_a_changed_price_is_409_and_writes_nothing(shop) -> None:
    deps, app, store, _ = shop
    body = _body([{'product_id': 'P-10', 'qty': 2}], '100.00')
    reply = checkout_handler(_request(body), deps)
    assert reply['status'] == 409
    problem_body = reply['body']
    assert problem_body['code'] == 'PriceChanged'
    assert problem_body['quote']['gross']['amount'] == '258.00'
    assert _orders(store) == []
    with store.unit_of_work('scripted') as uow:
        assert uow.customers.all() == ()


def test_out_of_stock_is_409_and_writes_nothing(shop) -> None:
    deps, app, store, _ = shop
    body = _body([{'product_id': 'P-20', 'qty': 6}], '5394.00')
    reply = checkout_handler(_request(body), deps)
    assert reply['status'] == 409
    assert reply['body']['code'] == 'OutOfStock'
    assert reply['body']['on_hand'] == 5
    assert _orders(store) == []
    with store.unit_of_work('scripted') as uow:
        assert uow.customers.all() == ()


def test_checkout_needs_a_guest_number(shop) -> None:
    deps, *_ = shop
    body = _body([{'product_id': 'P-10', 'qty': 1}], '129.00')
    reply = checkout_handler({'body': body}, deps)
    assert reply['status'] == 400


def test_an_order_is_read_back(shop) -> None:
    deps, *_ = shop
    body = _body([{'product_id': 'P-10', 'qty': 1}], '129.00')
    placed = checkout_handler(_request(body), deps)['body']
    reply = order_handler(
        {'path': {'order_id': placed['order_id']}}, deps
    )
    assert reply['status'] == 200
    assert reply['body']['total'] == placed['total']
    assert 'customer_id' not in reply['body']
    missing = order_handler({'path': {'order_id': 'O-999'}}, deps)
    assert missing['status'] == 404


def test_a_refused_place_after_register_is_orphaned(shop) -> None:
    deps, app, store, _ = shop

    class Refusing:
        def place(self, command: object) -> object:
            raise OutOfStock(P10, 1, 0)

    broken = Deps(deps.customers, Refusing(), deps.storefront)  # type: ignore[arg-type]
    body = _body([{'product_id': 'P-10', 'qty': 1}], '129.00')
    with pytest.raises(Orphaned) as raised:
        checkout_handler(_request(body), broken)
    assert str(raised.value.customer_id) == 'C-00001'
    shown = problem(raised.value)  # the cause, not a 500
    assert shown['status'] == 409
    assert shown['body']['code'] == 'OutOfStock'


def test_plain_refuses_what_it_cannot_render() -> None:
    assert plain({'a': (1, Qty(2), _nok('1.50'))}) == {
        'a': [1, 2, {'amount': '1.50', 'currency': 'NOK'}]
    }
    with pytest.raises(TypeError):
        plain(object())
