"""The simulator's feed and outside writers: the critical pieces."""

from __future__ import annotations

import dataclasses
import datetime as dt
from collections.abc import Sequence

import pytest
from roastery.bootstrap import App, memory_store, wire
from roastery.catalogue import EquipmentDetails
from roastery.checkout import Item, PlaceOrder
from roastery.fakes import FakeClock, FakeLabels, FakeNotifier, FakeProvider
from roastery.ids import CustomerId, EventId, OrderId, PaymentId, PostalCode, ProductId
from roastery.money import Money, Qty
from roastery.payments import PaymentMessage
from roastery.ports import IdKind, Relayed
from roastery.repository import ScriptedIds, SequentialIds
from roastery.settings import Secret, Settings, Url
from roastery_sim import outside
from roastery_sim.feed import Feed
from roastery_spec.contract import TABLES

C01 = CustomerId('C-01')
P21 = ProductId('P-21')
O101 = OrderId('O-101')
O104 = OrderId('O-104')
E09 = EventId('E-09')
PAY1 = PaymentId('PAY-1')
REFUND_ID = PaymentId('PAY-9')


def _at(day: int, hour: int, minute: int = 0) -> dt.datetime:
    return dt.datetime(2026, 10, day, hour, minute, tzinfo=dt.UTC)


def _nok(amount: str) -> Money:
    return Money.of(amount, 'NOK')


def _paid(order_id: OrderId, payment_id: str, amount: str, day: int) -> PaymentMessage:
    return PaymentMessage(PaymentId(payment_id), order_id, _nok(amount), dt.date(2026, 10, day))


def _wire(clock: FakeClock, feed: Feed) -> App:
    script: dict[IdKind, Sequence[str]] = {
        'customer': ('C-01',),
        'product': ('P-21',),
        'order': ('O-104',),
        'line': ('L-06',),
        'event': ('E-09', 'E-10'),
    }
    settings = Settings(
        database_url=Url('sqlite:///:memory:'),
        provider_url=Url('https://provider.example.invalid'),
        provider_key=Secret('not-a-key'),
    )
    return wire(
        settings,
        memory_store(clock=clock, price_ttl=60),
        clock=clock,
        ids=ScriptedIds(script, then=SequentialIds({})),
        source='scripted',
        feed=feed,
        provider=FakeProvider(refund_ids=[REFUND_ID]),
        notifier=FakeNotifier(),
        labels=FakeLabels(),
    )


def _set_up(app: App, clock: FakeClock) -> None:
    clock.set(_at(1, 7))
    gear = app.catalogue.add_category('Gear', parent_id=None, sort_order=1)
    app.catalogue.add_product(
        'Pour-over kettle', category_id=gear, details=EquipmentDetails(12, 'steel')
    )
    app.catalogue.set_price(P21, price=_nok('549.00'), valid_from=dt.date(2026, 10, 7))
    app.stock.stocktake(P21, on_hand=3)
    app.customers.register('Ingrid', email=None, country='NO', postal_code=PostalCode('0150'))


def test_the_feed_refuses_a_batch_whole_and_takes_it_at_the_moment() -> None:
    clock = FakeClock(_at(1, 7))
    feed = Feed(clock, refuse={E09: _at(6, 15, 45)})
    app = _wire(clock, feed)
    _set_up(app, clock)
    clock.set(_at(6, 15, 20))
    app.checkout.place(PlaceOrder(C01, 'shop', (Item(P21, Qty(1), price=_nok('549.00')),)))
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
    events = feed.rows()
    assert events.name == 'order_events'
    assert [(r[0], r[2], r[4]) for r in events.rows] == [
        ('E-10', 'paid', _at(6, 15, 30)),
        ('E-09', 'placed', _at(6, 15, 45)),
    ]


def test_a_redelivered_message_is_two_rows_and_one_held_payment() -> None:
    provider = FakeProvider(refund_ids=[REFUND_ID])
    log = outside.ProviderLog(provider)
    message = _paid(O101, 'PAY-1', '1157.00', 5)
    assert log.deliver(message) is message
    log.deliver(message)
    rows = log.rows()
    assert rows.name == 'payments'
    assert (
        rows.rows == (('PAY-1', 'O-101', 'NOK', _nok('1157.00').amount, dt.date(2026, 10, 5)),) * 2
    )
    # held once: a refund of the whole amount goes through, and nothing is left for a second
    provider.refund(PAY1, _nok('1157.00'), key='refund-O-101')
    assert len(provider.messages()) == 1


def test_a_refund_asked_of_the_provider_is_waiting_to_be_delivered() -> None:
    provider = FakeProvider(refund_ids=[REFUND_ID])
    log = outside.ProviderLog(provider)
    log.deliver(_paid(O101, 'PAY-1', '1157.00', 5))
    day = dt.date(2026, 10, 9)
    assert log.refunds(on=day) == ()
    provider.refund(PAY1, _nok('100.00'), key='refund-O-101')
    [refund] = log.refunds(on=day)
    assert (refund.payment_id, refund.amount) == (REFUND_ID, _nok('-100.00'))
    assert refund.paid_on == day  # the refund's day, not the day of the sale (5 October)
    log.deliver(refund)
    assert log.refunds(on=day) == ()
    assert log.rows().rows[-1][3] == _nok('-100.00').amount
    assert log.rows().rows[-1][4] == day


FACTS = {
    'fx_rates': outside.FxRate,
    'managers': outside.Manager,
    'web_events': outside.WebEvent,
    'product_codes': outside.ProductCode,
    'till_receipts': outside.TillReceipt,
    'till_lines': outside.TillLine,
    'till_members': outside.TillMember,
}


@pytest.mark.parametrize('name', sorted(FACTS))
def test_a_fact_type_has_the_columns_of_its_table(name: str) -> None:
    [table] = [t for t in TABLES if t.name == name]
    columns = tuple(c.name for c in table.columns)
    assert tuple(f.name for f in dataclasses.fields(FACTS[name])) == columns
    assert getattr(outside, name)(()).columns == columns
