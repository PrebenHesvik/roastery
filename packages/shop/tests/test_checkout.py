"""Checkout on both stores: what a call writes, what a refusal leaves.

The shop is built with the services themselves: P-10 and P-20 with
their prices from dataset.sql, 42 bags of P-10 and 5 grinders on
hand, and C-01 (Norway). O-101 is placed as E-01 placed it.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from roastery.catalogue import BeanDetails, EquipmentDetails
from roastery.checkout import Checkout, Item, PlaceOrder, order_country
from roastery.customers import Customers, country_of
from roastery.errors import NoSuchCustomer, UnknownProduct
from roastery.events import CollectingBus, EventBus, StatusChanged
from roastery.fakes import FakeClock
from roastery.ids import (
    CustomerId,
    LineId,
    OrderId,
    PostalCode,
    ProductId,
)
from roastery.listing import Catalogue
from roastery.money import Money, Qty
from roastery.order import Invoiced
from roastery.ports import IdKind, Ids, Store, UnitOfWork
from roastery.pricing import RULES
from roastery.repository import ScriptedIds, SequentialIds
from roastery.stock import Stock

BERGEN = ZoneInfo('Europe/Oslo')
C01 = CustomerId('C-01')
O101 = OrderId('O-101')
P10 = ProductId('P-10')
P20 = ProductId('P-20')
P99 = ProductId('P-99')
E01 = dt.datetime(2026, 10, 5, 8, 12, tzinfo=dt.UTC)


def _o101() -> PlaceOrder:
    """O-101 as the web shop sent it: L-01 and L-02."""
    return PlaceOrder(
        C01, 'web', (Item(P10, Qty(2)), Item(P20, Qty(1)))
    )


class _Drawn:
    """Ids that keep the kind of every id drawn."""

    def __init__(self, ids: Ids) -> None:
        self._ids = ids
        self.kinds: list[IdKind] = []

    def next(self, kind: IdKind) -> str:
        self.kinds.append(kind)
        return self._ids.next(kind)


@dataclass
class _Shop:
    uow: UnitOfWork
    ids: _Drawn
    customers: Customers
    checkout: Checkout


def _shop(store: Store, clock: FakeClock) -> _Shop:
    """The catalogue, the stock and C-01, set up on 1 October."""
    clock.set(dt.datetime(2026, 10, 1, 7, 0, tzinfo=dt.UTC))
    script: dict[IdKind, list[str]] = {
        'customer': ['C-01'],
        'product': ['P-10', 'P-20'],
        'order': ['O-101'],
        'line': ['L-01', 'L-02'],
    }
    ids = _Drawn(ScriptedIds(script, then=SequentialIds({})))
    uow = store.unit_of_work('scripted')
    catalogue = Catalogue(uow, ids)
    beans = catalogue.add_category(
        'Beans', parent_id=None, sort_order=1
    )
    gear = catalogue.add_category('Gear', parent_id=None, sort_order=2)
    catalogue.add_product(
        'Morning roast',
        category_id=beans,
        details=BeanDetails(250, 'Brazil', 'medium', 'natural'),
    )
    catalogue.add_product(
        'Hand grinder',
        category_id=gear,
        details=EquipmentDetails(24, 'steel'),
    )
    for product_id, price, valid_from in (
        (P10, '119.00', dt.date(2024, 1, 1)),
        (P10, '129.00', dt.date(2026, 10, 1)),
        (P20, '899.00', dt.date(2025, 6, 1)),
    ):
        catalogue.set_price(
            product_id,
            price=Money.of(price, 'NOK'),
            valid_from=valid_from,
        )
    stock = Stock(uow, clock, ids, BERGEN)
    stock.roast(P10, bags=Qty(42))
    stock.stocktake(P20, on_hand=5)
    customers = Customers(uow, clock, ids, BERGEN)
    customers.register(
        'Ingrid',
        email=None,
        country='NO',
        postal_code=PostalCode('0150'),
    )
    bus = CollectingBus(EventBus())
    checkout = Checkout(uow, clock, ids, bus, RULES)
    clock.set(E01)
    ids.kinds.clear()
    return _Shop(uow, ids, customers, checkout)


def _outbox(uow: UnitOfWork) -> list[StatusChanged]:
    """Every outbox row, in order; the batches are not kept."""
    with uow:
        uow.outbox.form_batches(100)
        return [
            event
            for batch in uow.outbox.waiting()
            for event in batch.events
        ]


def _moves(
    uow: UnitOfWork, product_id: ProductId
) -> list[tuple[str, int]]:
    with uow:
        return [
            (move.reason, move.qty)
            for move in uow.stock.movements(product_id)
        ]


def test_p99_rolls_the_whole_order_back(
    store: Store, clock: FakeClock
) -> None:
    shop = _shop(store, clock)
    command = PlaceOrder(
        C01, 'web', (Item(P10, Qty(2)), Item(P99, Qty(1)))
    )
    with pytest.raises(UnknownProduct):
        shop.checkout.place(command)
    with shop.uow as uow:
        assert uow.orders.all() == ()
        assert uow.orders.lines() == ()
    assert _moves(shop.uow, P10) == [('roasted', 42)]
    assert _outbox(shop.uow) == []
    assert shop.ids.kinds == []


def test_a_web_order_moves_stock_and_writes_placed(
    store: Store, clock: FakeClock
) -> None:
    shop = _shop(store, clock)
    placed = shop.checkout.place(_o101())
    assert placed.head.order_id == O101
    assert _moves(shop.uow, P10) == [('roasted', 42), ('sold', -2)]
    assert _moves(shop.uow, P20) == [('counted', 5), ('sold', -1)]
    rows = _outbox(shop.uow)
    assert [(row.order_id, row.status) for row in rows] == [
        (O101, 'placed')
    ]


def test_a_cancel_puts_the_bags_back_and_deletes_the_lines(
    store: Store, clock: FakeClock
) -> None:
    shop = _shop(store, clock)
    shop.checkout.place(_o101())
    clock.advance(dt.timedelta(hours=2))
    shop.checkout.cancel(O101, reason='changed their mind')
    assert _moves(shop.uow, P10) == [
        ('roasted', 42),
        ('sold', -2),
        ('sold', 2),
    ]
    assert _moves(shop.uow, P20) == [
        ('counted', 5),
        ('sold', -1),
        ('sold', 1),
    ]
    rows = _outbox(shop.uow)
    assert [row.status for row in rows] == ['placed', 'cancelled']
    with shop.uow as uow:
        assert [line.is_deleted for line in uow.orders.lines()] == [
            True,
            True,
        ]
        assert uow.orders.deleted_at(O101) == clock.now()


def test_order_country_is_decided_in_plain_sight(
    store: Store, clock: FakeClock
) -> None:
    shop = _shop(store, clock)
    sweden = shop.customers.register(
        'Åsa',
        email=None,
        country='SE',
        postal_code=PostalCode('21119'),
    )
    nowhere = shop.customers.register(
        'Lars', email=None, country=None, postal_code=None
    )
    with shop.uow as uow:
        at_counter = country_of(sweden, uow.customers)
        assert order_country('shop', at_counter) == 'NO'
        assert order_country('web', at_counter) == 'SE'
        no_country = country_of(nowhere, uow.customers)
        assert order_country('web', no_country) == 'NO'
        gone = country_of(CustomerId('C-07'), uow.customers)
        with pytest.raises(NoSuchCustomer):
            order_country('web', gone)


def test_a_business_order_is_placed_and_invoiced_at_once(
    store: Store, clock: FakeClock
) -> None:
    shop = _shop(store, clock)
    cafe = shop.customers.register(
        'Café Bryggen',
        email=None,
        country='NO',
        postal_code=PostalCode('5003'),
        account_kind='business',
    )
    done = shop.checkout.place(
        PlaceOrder(cafe, 'web', (Item(P10, Qty(10)),))
    )
    assert isinstance(done, Invoiced)
    rows = _outbox(shop.uow)
    order_id = done.head.order_id
    assert [(row.order_id, row.status) for row in rows] == [
        (order_id, 'placed'),
        (order_id, 'invoiced'),
    ]
    assert {row.event_at for row in rows} == {E01}


def test_o101_totals_pay_1_with_its_vat_share(
    store: Store, clock: FakeClock
) -> None:
    shop = _shop(store, clock)
    placed = shop.checkout.place(_o101())
    lines = placed.head.lines
    assert [(line.line_id, line.unit_price) for line in lines] == [
        (LineId('L-01'), Money.of('129.00', 'NOK')),
        (LineId('L-02'), Money.of('899.00', 'NOK')),
    ]
    total = sum(
        (line.unit_price.amount * line.qty.value for line in lines),
        Decimal(0),
    )
    assert total == Decimal('1157.00')  # PAY-1's amount
    with shop.uow as uow:
        booking = uow.orders.booking(O101)
    # Norway (ADR 0010): L-01 is beans at 15 %, 258.00 * 15 / 115
    # = 33.652 to 33.65; L-02 equipment at 25 %, 899.00 * 25 / 125
    # = 179.80. Each line to the øre, then summed: 213.45.
    assert booking.vat_amount == Money.of('213.45', 'NOK')
    assert booking.order_date == dt.date(2026, 10, 5)


def test_an_export_owes_no_vat_on_a_day_with_no_rate_row(
    store: Store, clock: FakeClock
) -> None:
    shop = _shop(store, clock)
    sweden = shop.customers.register(
        'Åsa',
        email=None,
        country='SE',
        postal_code=PostalCode('21119'),
    )
    # SE's food rate of 6 % ends on 1 January 2028 and vat.md has
    # no row after it; an export is zero with no lookup (ADR 0010).
    clock.set(dt.datetime(2028, 1, 3, 10, 0, tzinfo=dt.UTC))
    placed = shop.checkout.place(
        PlaceOrder(sweden, 'web', (Item(P10, Qty(1)),))
    )
    assert placed.head.country == 'SE'
    with shop.uow as uow:
        booking = uow.orders.booking(placed.head.order_id)
    assert booking.vat_amount == Money.of('0.00', 'NOK')


def test_a_counter_line_without_a_price_is_refused(
    store: Store, clock: FakeClock
) -> None:
    shop = _shop(store, clock)
    command = PlaceOrder(C01, 'shop', (Item(P20, Qty(1)),))
    with pytest.raises(ValueError, match='the till rings a price'):
        shop.checkout.place(command)
    with shop.uow as uow:
        assert uow.orders.all() == ()
    assert _moves(shop.uow, P20) == [('counted', 5)]
    assert shop.ids.kinds == []
