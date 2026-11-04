"""Payments on both stores: once per payment id, and the refund.

The shop is the one test_checkout builds: P-10 and P-20 at their
October prices, stock on hand, C-01 in Norway. O-101 is placed at
E-01 and PAY-1 (1157.00 NOK, 5 October) is its payment.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, replace
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from roastery.catalogue import BeanDetails, EquipmentDetails
from roastery.checkout import Checkout, Item, PlaceOrder
from roastery.customers import Customers
from roastery.errors import (
    AlreadyCredited,
    IllegalTransition,
    NoOpenInvoice,
    NotCreditable,
    NothingToRefund,
    PaymentMismatch,
)
from roastery.events import CollectingBus, EventBus
from roastery.fakes import FakeClock, FakeProvider
from roastery.fulfilment import Fulfilment
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
from roastery.order import Cancelled, Paid, Payment
from roastery.payments import PaymentMessage, Payments, Receipt
from roastery.ports import IdKind, Ids, Store, UnitOfWork
from roastery.pricing import RULES
from roastery.repository import ScriptedIds, SequentialIds
from roastery.stock import Stock
from roastery.vat import vat_of

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
    fulfilment: Fulfilment


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
        Fulfilment(uow, clock, ids, BERGEN),
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
        Payment(
            PAY_1.payment_id, O101, PAY_1.amount, PAY_1.paid_on, 'paid'
        ),
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


def _vat(uow: UnitOfWork, order_id: OrderId) -> Money:
    with uow:
        return uow.orders.booking(order_id).vat_amount


def _moves(
    uow: UnitOfWork, product_id: ProductId
) -> list[tuple[str, int]]:
    with uow:
        return [
            (move.reason, move.qty)
            for move in uow.stock.movements(product_id)
        ]


def _credited(shop: _Shop) -> OrderId:
    """O-101 paid by PAY-1, and L-02's grinder handed back."""
    shop.checkout.place(_o101())
    shop.payments.handle_message(PAY_1)
    shop.provider.take(PAY_1)
    return shop.checkout.credit_for(O101, line_id=LineId('L-02'))


def _cafe_invoice(shop: _Shop) -> OrderId:
    """Café Bryggen's 10 bags, placed and invoiced at once."""
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
    return invoiced.head.order_id


def test_a_foreign_sale_credited_owes_no_vat(
    store: Store, clock: FakeClock
) -> None:
    shop = _shop(store, clock)
    finland = shop.customers.register(
        'Aino',
        email=None,
        country='FI',
        postal_code=PostalCode('00100'),
    )
    sale = shop.checkout.place(
        PlaceOrder(finland, 'web', (Item(P20, Qty(1)),))
    )
    sale_id = sale.head.order_id
    shop.payments.handle_message(
        PaymentMessage(
            PaymentId('PAY-4'),
            sale_id,
            Money.of('77.40', 'EUR'),
            dt.date(2026, 10, 5),
        )
    )
    line_id = sale.head.lines[0].line_id
    credit_id = shop.checkout.credit_for(sale_id, line_id=line_id)
    with shop.uow as uow:
        assert uow.orders.get(credit_id).head.country == 'FI'
    # A40: the credit corrects an export, so it is one too.
    assert _vat(shop.uow, sale_id) == Money.of('0.00', 'NOK')
    assert _vat(shop.uow, credit_id) == Money.of('0.00', 'NOK')


def test_a_norwegian_sale_credited_nets_its_line_to_zero(
    store: Store, clock: FakeClock
) -> None:
    shop = _shop(store, clock)
    credit_id = _credited(shop)
    # L-02's share in O-101's 213.45: 899.00 * 25 / 125 = 179.80.
    line = vat_of(Money.of('899.00', 'NOK'), Decimal(25), 'domestic')
    assert line == Money.of('179.80', 'NOK')
    credit = _vat(shop.uow, credit_id)
    assert credit == Money.of('-179.80', 'NOK')
    assert credit + line == Money.of('0.00', 'NOK')


def test_a_credited_sale_cannot_be_cancelled(
    store: Store, clock: FakeClock
) -> None:
    shop = _shop(store, clock)
    _credited(shop)
    shop.ids.kinds.clear()
    with pytest.raises(IllegalTransition) as raised:
        shop.checkout.cancel(O101, reason='changed their mind')
    assert (raised.value.state, raised.value.action) == (
        'paid',
        'cancel',
    )
    with shop.uow as uow:
        assert isinstance(uow.orders.get(O101), Paid)
    assert _moves(shop.uow, P20) == [
        ('counted', 5),
        ('sold', -1),
        ('sold', 1),
    ]
    assert _statuses(shop.uow) == ['placed', 'paid', 'placed']
    assert shop.ids.kinds == []


def test_a_cancelled_credit_has_nothing_to_refund(
    store: Store, clock: FakeClock
) -> None:
    shop = _shop(store, clock)
    credit_id = _credited(shop)
    shop.checkout.cancel(credit_id, reason='rung by mistake')
    with pytest.raises(NothingToRefund):
        shop.payments.refund(credit_id)
    assert shop.provider.messages() == ()


def test_a_settled_invoice_redelivered_after_ship_gets_one_receipt(
    store: Store, clock: FakeClock
) -> None:
    shop = _shop(store, clock)
    order_id = _cafe_invoice(shop)
    message = PaymentMessage(
        PaymentId('PAY-9'),
        order_id,
        Money.of('1290.00', 'NOK'),
        dt.date(2026, 10, 5),
    )
    first = shop.payments.settle(message)
    assert first == Receipt(message.payment_id, order_id, 'invoiced')
    shop.fulfilment.ship(order_id, promised_by=dt.date(2026, 10, 8))
    assert shop.payments.settle(message) == first
    assert len(_payments(shop.uow, order_id)) == 1


def test_a_refund_redelivered_after_its_credit_is_cancelled(
    store: Store, clock: FakeClock
) -> None:
    shop = _shop(store, clock)
    credit_id = _credited(shop)
    shop.payments.refund(credit_id)
    (message,) = shop.provider.messages()
    first = shop.payments.handle_message(message)
    assert first == Receipt(REFUND_ID, credit_id, 'paid')
    shop.checkout.cancel(credit_id, reason='rung by mistake')
    with shop.uow as uow:
        assert isinstance(uow.orders.get(credit_id), Cancelled)
    assert shop.payments.handle_message(message) == first
    assert len(_payments(shop.uow, credit_id)) == 1


def test_settle_refuses_an_amount_of_zero_or_less(
    store: Store, clock: FakeClock
) -> None:
    shop = _shop(store, clock)
    order_id = _cafe_invoice(shop)
    for amount in ('-1290.00', '0.00'):
        misrouted = PaymentMessage(
            PaymentId('PAY-9'),
            order_id,
            Money.of(amount, 'NOK'),
            dt.date(2026, 10, 5),
        )
        with pytest.raises(ValueError, match='settle takes a payment'):
            shop.payments.settle(misrouted)
    assert _payments(shop.uow, order_id) == ()


def test_a_never_paid_order_is_not_creditable(
    store: Store, clock: FakeClock
) -> None:
    # O-107 (C-07, 7 October): placed on the web, never paid.
    shop = _shop(store, clock)
    shop.checkout.place(_o101())
    shop.ids.kinds.clear()
    with pytest.raises(NotCreditable) as raised:
        shop.checkout.credit_for(O101, line_id=LineId('L-01'))
    assert raised.value.state == 'placed'
    with shop.uow as uow:
        assert uow.orders.credits_of(O101) == ()
    assert _statuses(shop.uow) == ['placed']
    assert shop.ids.kinds == []


def test_a_line_is_credited_once(
    store: Store, clock: FakeClock
) -> None:
    shop = _shop(store, clock)
    _credited(shop)
    shop.ids.kinds.clear()
    with pytest.raises(AlreadyCredited):
        shop.checkout.credit_for(O101, line_id=LineId('L-02'))
    with shop.uow as uow:
        assert len(uow.orders.credits_of(O101)) == 1
    assert _moves(shop.uow, P20) == [
        ('counted', 5),
        ('sold', -1),
        ('sold', 1),
    ]
    assert shop.ids.kinds == []


def test_a_cancelled_credit_hands_nothing_back(
    store: Store, clock: FakeClock
) -> None:
    shop = _shop(store, clock)
    first = _credited(shop)
    shop.checkout.cancel(first, reason='rung by mistake')
    again = shop.checkout.credit_for(O101, line_id=LineId('L-02'))
    assert again != first
    with shop.uow as uow:
        credits = uow.orders.credits_of(O101)
    assert [credit.head.order_id for credit in credits] == [
        first,
        again,
    ]


def test_a_refused_ship_draws_no_id(
    store: Store, clock: FakeClock
) -> None:
    shop = _shop(store, clock)
    shop.checkout.place(_o101())
    shop.ids.kinds.clear()
    with pytest.raises(IllegalTransition):
        shop.fulfilment.ship(O101, promised_by=dt.date(2026, 10, 8))
    assert _statuses(shop.uow) == ['placed']
    assert shop.ids.kinds == []
