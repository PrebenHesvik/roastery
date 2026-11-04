"""Retry, the breaker and the fake provider, with no real waiting.

The sleep is a list that notes the wait; the breaker reads a
FakeClock. Nothing here sleeps or reads the wall clock.
"""

from __future__ import annotations

import datetime as dt

import pytest

from roastery.fakes import FakeClock, FakeProvider, PaymentMessage
from roastery.ids import OrderId, PaymentId
from roastery.money import Money
from roastery.ports import ProviderRefused, ProviderUnavailable
from roastery.resilience import (
    CircuitBreaker,
    CircuitOpen,
    ProtectedProvider,
)

START = dt.datetime(2026, 10, 5, 8, 0, tzinfo=dt.UTC)
PAY_1 = PaymentId('PAY-1')
REFUND = PaymentId('PAY-90')
NOK = 'NOK'


def nok(amount: str) -> Money:
    return Money.of(amount, NOK)


def provider_holding_pay_1() -> FakeProvider:
    fake = FakeProvider(refund_ids=[REFUND, PaymentId('PAY-91')])
    fake.take(
        PaymentMessage(
            PAY_1,
            OrderId('O-101'),
            nok('1157.00'),
            dt.date(2026, 10, 5),
        )
    )
    return fake


def protected(fake: FakeProvider, sleeps: list[float], *, down_for=1):
    """The fake behind retry and a breaker; `sleep` notes the wait
    and brings the provider back after `down_for` waits."""

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) >= down_for:
            fake.set_down(False)

    breaker = CircuitBreaker(
        FakeClock(START), 3, dt.timedelta(minutes=1)
    )
    return ProtectedProvider(
        fake, breaker, attempts=3, backoff=0.5, sleep=sleep, seed=7
    )


class Counting:
    """A provider that always raises `error`, and counts the calls."""

    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls = 0

    def refund(self, payment_id, amount, *, key):
        self.calls += 1
        raise self.error


def test_unavailable_is_retried_with_the_same_key_for_one_refund():
    fake = provider_holding_pay_1()
    fake.set_down(True)
    sleeps: list[float] = []
    port = protected(fake, sleeps)

    got = port.refund(PAY_1, nok('899.00'), key='refund-O-300')

    assert got == REFUND
    assert len(sleeps) == 1  # one wait, then the second try worked
    assert [m.amount for m in fake.messages()] == [nok('-899.00')]
    assert (
        fake.refund(PAY_1, nok('899.00'), key='refund-O-300') == REFUND
    )
    assert len(fake.messages()) == 1


def test_a_decline_is_never_retried():
    refused = Counting(ProviderRefused('declined'))
    sleeps: list[float] = []
    breaker = CircuitBreaker(
        FakeClock(START), 3, dt.timedelta(minutes=1)
    )
    port = ProtectedProvider(
        refused,
        breaker,
        attempts=3,
        backoff=0.5,
        sleep=sleeps.append,
        seed=7,
    )

    with pytest.raises(ProviderRefused):
        port.refund(PAY_1, nok('899.00'), key='refund-O-300')

    assert refused.calls == 1
    assert sleeps == []
    assert breaker.state == 'closed'


def test_the_breaker_opens_at_its_threshold_and_does_not_call():
    clock = FakeClock(START)
    breaker = CircuitBreaker(clock, 2, dt.timedelta(seconds=30))
    down = Counting(ProviderUnavailable('down'))

    def call() -> None:
        down.refund(PAY_1, nok('1.00'), key='k')

    for _ in range(2):
        with pytest.raises(ProviderUnavailable):
            breaker.call(call)
    assert down.calls == 2
    assert breaker.state == 'open'

    with pytest.raises(CircuitOpen):
        breaker.call(call)
    assert down.calls == 2  # refused without calling

    clock.advance(dt.timedelta(seconds=30))
    assert breaker.state == 'half-open'
    assert breaker.call(lambda: 'back') == 'back'
    assert breaker.state == 'closed'


def test_the_fake_refuses_more_than_is_left_and_what_it_does_not_hold():
    fake = provider_holding_pay_1()

    with pytest.raises(ProviderRefused):
        fake.refund(PaymentId('PAY-7'), nok('1.00'), key='refund-O-301')

    fake.refund(PAY_1, nok('1000.00'), key='refund-O-302')
    with pytest.raises(ProviderRefused):
        fake.refund(PAY_1, nok('157.01'), key='refund-O-303')
    assert fake.refund(PAY_1, nok('157.00'), key='refund-O-304') == (
        PaymentId('PAY-91')
    )
    assert [str(m.order_id) for m in fake.messages()] == [
        'O-302',
        'O-304',
    ]
