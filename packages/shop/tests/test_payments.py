"""Payments on both stores: once per payment id, and the refund.

The shop is the one test_checkout builds: P-10 and P-20 at their
October prices, stock on hand, C-01 in Norway. O-101 is placed at
E-01 and PAY-1 (1157.00 NOK, 5 October) is its payment.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, replace
from zoneinfo import ZoneInfo

import pytest

from roastery.catalogue import BeanDetails, EquipmentDetails
from roastery.checkout import Checkout, Item, PlaceOrder
from roastery.customers import Customers
from roastery.errors import (
    IllegalTransition,
    NoOpenInvoice,
    NothingToRefund,
    PaymentMismatch,
)
from roastery.events import CollectingBus, EventBus
from roastery.fakes import FakeClock, FakeProvider
from roastery.ids import (
    CustomerId,
    LineId,
    OrderId,
    PaymentId,
    PostalCode,
    ProductId,
)
from roastery.listing import Catalogue
from roastery.money import Money, Qty
from roastery.order import Payment
from roastery.payments import PaymentMessage, Payments, Receipt
from roastery.ports import IdKind, Ids, Store, UnitOfWork
from roastery.pricing import RULES
from roastery.repository import ScriptedIds, SequentialIds
from roastery.stock import Stock

BERGEN = ZoneInfo('Europe/Oslo')
C01 = CustomerId('C-01')
O101 = OrderId('O-101')
P10 = ProductId('P-10')
P20 = ProductId('P-20')
PAY_1 = PaymentMessage(
    PaymentId('PAY-1'),
    O101,
    Money.of('1157.00', 'NOK'),
    dt.date(2026, 10, 5),
)
REFUND_ID = PaymentId('PAY-300')


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
    payments: Payments
    provider: FakeProvider


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
    for product_id, price in ((P10, '129.00'), (P20, '899.00')):
        catalogue.set_price(
            product_id,
            price=Money.of(price, 'NOK'),
            valid_from=dt.date(2026, 10, 1),
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
    provider = FakeProvider(refund_ids=[REFUND_ID])
    shop = _Shop(
        uow,
        ids,
        customers,
        Checkout(uow, clock, ids, bus, RULES),
        Payments(uow, clock, ids, bus, provider),
        provider,
    )
    clock.set(dt.datetime(2026, 10, 5, 8, 12, tzinfo=dt.UTC))
    return shop


def _statuses(uow: UnitOfWork) -> list[str]:
    """The outbox rows' statuses, in order; nothing is kept."""
    with uow:
        uow.outbox.form_batches(100)
        return [
            event.status
            for batch in uow.outbox.waiting()
            for event in batch.events
        ]


def _payments(
    uow: UnitOfWork, order_id: OrderId
) -> tuple[Payment, ...]:
    with uow:
        return uow.payments.of(order_id)


def test_pay_1_delivered_twice_is_kept_once(
    store: Store, clock: FakeClock
) -> None:
    shop = _shop(store, clock)
    shop.checkout.place(_o101())
    first = shop.payments.handle_message(PAY_1)
    second = shop.payments.handle_message(PAY_1)
    assert first == second == Receipt(PAY_1.payment_id, O101, 'paid')
    assert _payments(shop.uow, O101) == (
        Payment(PAY_1.payment_id, O101, PAY_1.amount, PAY_1.paid_on),
    )
    assert _statuses(shop.uow) == ['placed', 'paid']


def test_pay_1_with_another_amount_is_refused(
    store: Store, clock: FakeClock
) -> None:
    shop = _shop(store, clock)
    shop.checkout.place(_o101())
    shop.payments.handle_message(PAY_1)
    shop.ids.kinds.clear()
    other = replace(PAY_1, amount=Money.of('1157.01', 'NOK'))
    with pytest.raises(PaymentMismatch):
        shop.payments.handle_message(other)
    paid = _payments(shop.uow, O101)
    assert [payment.amount for payment in paid] == [PAY_1.amount]
    assert _statuses(shop.uow) == ['placed', 'paid']
    assert shop.ids.kinds == []


def test_a_payment_for_an_invoiced_order_goes_to_settle(
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
    invoiced = shop.checkout.place(
        PlaceOrder(cafe, 'web', (Item(P10, Qty(10)),))
    )
    order_id = invoiced.head.order_id
    message = PaymentMessage(
        PaymentId('PAY-9'),
        order_id,
        Money.of('1290.00', 'NOK'),
        dt.date(2026, 10, 5),
    )
    with pytest.raises(IllegalTransition):
        shop.payments.handle_message(message)
    assert _payments(shop.uow, order_id) == ()
    assert _statuses(shop.uow) == ['placed', 'invoiced']


def test_settle_on_a_paid_order_finds_no_open_invoice(
    store: Store, clock: FakeClock
) -> None:
    shop = _shop(store, clock)
    shop.checkout.place(_o101())
    shop.payments.handle_message(PAY_1)
    again = replace(PAY_1, payment_id=PaymentId('PAY-9'))
    with pytest.raises(NoOpenInvoice):
        shop.payments.settle(again)
    assert len(_payments(shop.uow, O101)) == 1


def test_a_never_paid_order_has_nothing_to_refund(
    store: Store, clock: FakeClock
) -> None:
    shop = _shop(store, clock)
    shop.checkout.place(_o101())
    shop.checkout.cancel(O101, reason='changed their mind')
    with pytest.raises(NothingToRefund):
        shop.payments.refund(O101)
    assert shop.provider.messages() == ()


def test_a_refund_asks_the_positive_amount_back(
    store: Store, clock: FakeClock
) -> None:
    shop = _shop(store, clock)
    shop.checkout.place(_o101())
    shop.payments.handle_message(PAY_1)
    shop.provider.take(PAY_1)
    credit_id = shop.checkout.credit_for(O101, line_id=LineId('L-02'))
    assert shop.payments.refund(credit_id) == REFUND_ID
    # The fake refuses an amount of zero or less, so the message's
    # -899.00 means refund asked 899.00 back for the grinder.
    assert shop.provider.messages() == (
        PaymentMessage(
            REFUND_ID,
            credit_id,
            Money.of('-899.00', 'NOK'),
            PAY_1.paid_on,
        ),
    )
