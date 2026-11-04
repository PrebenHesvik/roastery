"""The app as wire builds it, driven through App on both stores.

Each test wires the app with the fakes, sets the shop up through
the services themselves (the products and prices of dataset.sql,
stock on hand, C-01, C-04 and C-05), then plays the rows of the
week the lesson needs, at their moments and with their ids.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import pytest

from roastery.bootstrap import App, wire
from roastery.catalogue import BeanDetails, EquipmentDetails
from roastery.checkout import Item, PlaceOrder
from roastery.customer import Email
from roastery.errors import IllegalTransition, NoAddress, NotShippable
from roastery.fakes import (
    FakeClock,
    FakeFeed,
    FakeLabels,
    FakeNotifier,
    FakeProvider,
)
from roastery.ids import (
    CustomerId,
    EventId,
    LineId,
    OrderId,
    PaymentId,
    PostalCode,
    ProductId,
)
from roastery.money import Money, Qty
from roastery.order import PaymentMessage, status
from roastery.ports import (
    IdKind,
    Ids,
    Notifier,
    PaymentProvider,
    ProviderRefused,
    ProviderUnavailable,
    Relayed,
    Source,
    StatusFeed,
    Store,
)
from roastery.repository import ScriptedIds, SequentialIds
from roastery.settings import Secret, Settings, Url

C01 = CustomerId('C-01')
C04 = CustomerId('C-04')
C05 = CustomerId('C-05')
P10 = ProductId('P-10')
P11 = ProductId('P-11')
P20 = ProductId('P-20')
P21 = ProductId('P-21')
O101 = OrderId('O-101')
O104 = OrderId('O-104')
O105 = OrderId('O-105')
O106 = OrderId('O-106')
E09 = EventId('E-09')
E10 = EventId('E-10')
PAY1 = PaymentId('PAY-1')
REFUND_ID = PaymentId('PAY-300')


def _at(day: int, hour: int, minute: int = 0) -> dt.datetime:
    """A moment of October 2026, in UTC."""
    return dt.datetime(2026, 10, day, hour, minute, tzinfo=dt.UTC)


def _nok(amount: str) -> Money:
    return Money.of(amount, 'NOK')


def _paid(
    order_id: OrderId, payment_id: str, amount: str, day: int
) -> PaymentMessage:
    """The provider's message for a payment of October 2026."""
    return PaymentMessage(
        PaymentId(payment_id),
        order_id,
        _nok(amount),
        dt.date(2026, 10, day),
    )


def _ids(script: Mapping[IdKind, Sequence[str]]) -> Ids:
    """The set-up's ids and the test's, then a sequence."""
    listed: dict[IdKind, Sequence[str]] = {
        'customer': ('C-01', 'C-04', 'C-05'),
        'product': ('P-10', 'P-11', 'P-20', 'P-21'),
        **script,
    }
    return ScriptedIds(listed, then=SequentialIds({}))


@dataclass
class _Shop:
    app: App
    labels: FakeLabels


def _wire(
    store: Store,
    clock: FakeClock,
    ids: Ids,
    *,
    source: Source = 'scripted',
    feed: StatusFeed | None = None,
    provider: PaymentProvider | None = None,
    notifier: Notifier | None = None,
) -> _Shop:
    """The app wired over the store; a fake at every other port."""
    settings = Settings(
        database_url=Url('sqlite:///:memory:'),
        provider_url=Url('https://provider.example.invalid'),
        provider_key=Secret('not-a-key'),
    )
    labels = FakeLabels()
    app = wire(
        settings,
        store,
        clock=clock,
        ids=ids,
        source=source,
        feed=feed or FakeFeed(clock),
        provider=provider or FakeProvider(refund_ids=[REFUND_ID]),
        notifier=notifier or FakeNotifier(),
        labels=labels,
    )
    return _Shop(app, labels)


def _set_up(app: App, clock: FakeClock) -> None:
    """The catalogue, the stock and three customers, on 1 October.

    The prices are dataset.sql's: P-21 has none before 7 October.
    C-01 has an e-mail here, so `confirm` has someone to write to;
    C-05 has no country and no postal code, as in the week.
    """
    clock.set(_at(1, 7))
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
        (P11, '349.00', dt.date(2026, 10, 5)),
        (P20, '899.00', dt.date(2025, 6, 1)),
        (P21, '549.00', dt.date(2026, 10, 7)),
    ):
        app.catalogue.set_price(
            product_id, price=_nok(price), valid_from=valid_from
        )
    app.stock.roast(P10, bags=Qty(42))
    app.stock.roast(P11, bags=Qty(10))
    app.stock.stocktake(P20, on_hand=5)
    app.stock.stocktake(P21, on_hand=3)
    app.customers.register(
        'Ingrid',
        email=Email('ingrid@example.invalid'),
        country='NO',
        postal_code=PostalCode('0150'),
    )
    app.customers.register(
        'Aino',
        email=None,
        country='FI',
        postal_code=PostalCode('33100'),
    )
    app.customers.register(
        'Lars', email=None, country=None, postal_code=None
    )


def _o101() -> PlaceOrder:
    """O-101 as the web shop sent it: L-01 and L-02."""
    return PlaceOrder(
        C01, 'web', (Item(P10, Qty(2)), Item(P20, Qty(1)))
    )


def test_o106_cancelled_then_shipped_is_refused(
    store: Store, clock: FakeClock
) -> None:
    script: dict[IdKind, Sequence[str]] = {
        'order': ('O-106',),
        'line': ('L-10',),
        'event': ('E-11', 'E-12'),
    }
    app = _wire(store, clock, _ids(script)).app
    _set_up(app, clock)
    clock.set(_at(6, 21, 30))
    app.checkout.place(PlaceOrder(C04, 'web', (Item(P10, Qty(1)),)))
    clock.set(_at(7, 6))
    app.checkout.cancel(O106, reason='changed their mind')
    with pytest.raises(IllegalTransition) as refused:
        app.fulfilment.ship(O106, promised_by=dt.date(2026, 10, 9))
    assert (refused.value.state, refused.value.action) == (
        'cancelled',
        'ship',
    )


def test_o104_at_the_counter_is_not_shippable(
    store: Store, clock: FakeClock
) -> None:
    script: dict[IdKind, Sequence[str]] = {
        'order': ('O-104',),
        'line': ('L-06',),
    }
    app = _wire(store, clock, _ids(script)).app
    _set_up(app, clock)
    clock.set(_at(6, 15, 20))
    kettle = Item(P21, Qty(1), price=_nok('549.00'))
    app.checkout.place(PlaceOrder(C01, 'shop', (kettle,)))
    with pytest.raises(NotShippable):
        app.fulfilment.ship(O104, promised_by=dt.date(2026, 10, 8))


def test_o105_of_c05_is_paid_and_has_no_address(
    store: Store, clock: FakeClock
) -> None:
    script: dict[IdKind, Sequence[str]] = {
        'order': ('O-105',),
        'line': ('L-07',),
    }
    shop = _wire(store, clock, _ids(script))
    app = shop.app
    _set_up(app, clock)
    clock.set(_at(7, 11, 5))
    app.checkout.place(PlaceOrder(C05, 'web', (Item(P11, Qty(1)),)))
    app.payments.handle_message(_paid(O105, 'PAY-5', '349.00', 7))
    assert shop.labels.requested() == ()
    with pytest.raises(NoAddress):
        app.fulfilment.ship(O105, promised_by=dt.date(2026, 10, 9))


class _BrokenMail:
    """A Notifier whose mail server is down."""

    def send(self, to: Email, *, subject: str, body: str) -> None:
        raise ConnectionError('the mail server is down')


def test_a_failing_handler_is_kept_and_the_payment_stands(
    store: Store, clock: FakeClock
) -> None:
    script: dict[IdKind, Sequence[str]] = {
        'order': ('O-101',),
        'line': ('L-01', 'L-02'),
    }
    shop = _wire(store, clock, _ids(script), notifier=_BrokenMail())
    app = shop.app
    _set_up(app, clock)
    clock.set(_at(5, 8, 12))
    app.checkout.place(_o101())
    clock.set(_at(5, 8, 13))
    receipt = app.payments.handle_message(
        _paid(O101, 'PAY-1', '1157.00', 5)
    )
    assert receipt.status == 'paid'
    with store.unit_of_work('scripted') as uow:
        assert uow.payments.find(PAY1) is not None
        assert status(uow.orders.get(O101)) == 'paid'
    [failure] = app.failures()
    assert failure.handler.rsplit('.', 1)[-1] == 'confirm'
    assert failure.event == 'OrderPaid'
    # the other handler still ran
    assert shop.labels.requested() == (O101,)


def test_the_relay_lands_e10_before_e09_and_e09_once(
    store: Store, clock: FakeClock
) -> None:
    """ADR 0009: the script runs the relay between E-09 and E-10,
    so E-09's batch is formed before E-10 exists."""
    feed = FakeFeed(clock, refuse={E09: _at(6, 15, 45)})
    script: dict[IdKind, Sequence[str]] = {
        'order': ('O-104',),
        'line': ('L-06',),
        'event': ('E-09', 'E-10'),
    }
    app = _wire(store, clock, _ids(script), feed=feed).app
    _set_up(app, clock)
    clock.set(_at(6, 15, 20))
    kettle = Item(P21, Qty(1), price=_nok('549.00'))
    app.checkout.place(PlaceOrder(C01, 'shop', (kettle,)))
    clock.set(_at(6, 15, 20) + dt.timedelta(seconds=30))
    assert app.jobs.relay() == Relayed((), (1,))
    clock.set(_at(6, 15, 21))
    app.payments.handle_message(_paid(O104, 'PAY-4', '549.00', 6))
    clock.set(_at(6, 15, 30))
    assert app.jobs.relay() == Relayed((2,), (1,))
    clock.set(_at(6, 15, 45))
    assert app.jobs.relay() == Relayed((1,), ())
    clock.set(_at(6, 16))
    assert app.jobs.relay() == Relayed((), ())
    landed = [
        (event.event_id, event.status, loaded_at)
        for event, loaded_at in feed.taken()
    ]
    assert landed == [
        (E10, 'paid', _at(6, 15, 30)),
        (E09, 'placed', _at(6, 15, 45)),
    ]


def test_the_count_at_close_stamps_the_day_s_close_once(
    store: Store, clock: FakeClock
) -> None:
    app = _wire(store, clock, _ids({})).app
    _set_up(app, clock)
    clock.set(_at(7, 10))
    app.checkout.place(PlaceOrder(C01, 'web', (Item(P10, Qty(2)),)))
    clock.set(_at(8, 6))
    app.checkout.place(PlaceOrder(C01, 'web', (Item(P10, Qty(1)),)))
    clock.set(_at(8, 6, 30))
    assert app.jobs.count_at_close() == 4
    assert app.jobs.count_at_close() == 0
    with store.unit_of_work('scripted') as uow:
        counts = uow.stock.counts(dt.date(2026, 10, 7))
    # 18:00 in Bergen is 16:00 UTC; 8 October's sale is not in it
    assert [
        (c.product_id, c.on_hand, c.counted_at) for c in counts
    ] == [
        (P10, 40, _at(7, 16)),
        (P11, 10, _at(7, 16)),
        (P20, 5, _at(7, 16)),
        (P21, 3, _at(7, 16)),
    ]


class _Watched:
    """A provider in front of the fake: counts the calls, and
    brings the fake back up after the first call it refused."""

    def __init__(self, fake: FakeProvider) -> None:
        self.fake = fake
        self.calls = 0

    def refund(
        self, payment_id: PaymentId, amount: Money, *, key: str
    ) -> PaymentId:
        self.calls += 1
        try:
            return self.fake.refund(payment_id, amount, key=key)
        except ProviderUnavailable:
            self.fake.set_down(False)
            raise


def _credit_l02(
    store: Store, clock: FakeClock, provider: _Watched
) -> App:
    """O-101 placed and paid; the grinder (L-02) brought back."""
    script: dict[IdKind, Sequence[str]] = {
        'order': ('O-101',),
        'line': ('L-01', 'L-02'),
    }
    app = _wire(store, clock, _ids(script), provider=provider).app
    _set_up(app, clock)
    clock.set(_at(5, 8, 12))
    app.checkout.place(_o101())
    app.payments.handle_message(_paid(O101, 'PAY-1', '1157.00', 5))
    clock.set(_at(8, 12))
    return app


def test_a_declined_refund_is_not_retried(
    store: Store, clock: FakeClock
) -> None:
    # the fake never took PAY-1, so it declines the refund
    provider = _Watched(FakeProvider(refund_ids=[REFUND_ID]))
    app = _credit_l02(store, clock, provider)
    credit_id = app.checkout.credit_for(O101, line_id=LineId('L-02'))
    with pytest.raises(ProviderRefused):
        app.payments.refund(credit_id)
    assert provider.calls == 1


def test_a_refund_while_the_provider_is_down_is_retried_once(
    store: Store, clock: FakeClock
) -> None:
    fake = FakeProvider(refund_ids=[REFUND_ID])
    fake.take(_paid(O101, 'PAY-1', '1157.00', 5))
    fake.set_down(True)
    provider = _Watched(fake)
    app = _credit_l02(store, clock, provider)
    credit_id = app.checkout.credit_for(O101, line_id=LineId('L-02'))
    assert app.payments.refund(credit_id) == REFUND_ID
    assert provider.calls == 2
    [message] = fake.messages()
    assert (message.payment_id, message.amount) == (
        REFUND_ID,
        _nok('-899.00'),
    )


def test_two_wirings_over_one_store_share_one_price_cache(
    store: Store, clock: FakeClock
) -> None:
    ids = _ids({})  # one id sequence for both, as the simulator has
    scripted = _wire(store, clock, ids, source='scripted').app
    simulator = _wire(store, clock, ids, source='simulator').app
    _set_up(scripted, clock)
    clock.set(_at(5, 9))
    one_bag = PlaceOrder(C01, 'web', (Item(P10, Qty(1)),))
    before = simulator.checkout.place(one_bag)
    scripted.catalogue.set_price(
        P10, price=_nok('139.00'), valid_from=dt.date(2026, 10, 5)
    )
    after = simulator.checkout.place(one_bag)  # inside the TTL
    assert before.head.lines[0].unit_price == _nok('129.00')
    assert after.head.lines[0].unit_price == _nok('139.00')
