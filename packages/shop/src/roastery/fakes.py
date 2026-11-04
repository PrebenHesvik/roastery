"""Working fakes at the ports: they keep rules, not scripts.

A fake here does what the outside system would do, in memory: the
provider holds payments and refuses what it cannot give back, the
feed refuses a batch until a moment and stamps what it takes. Each is
driven by the test or the simulator through a few plain calls, and
none of them reads the wall clock (ADR 0013).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence

from roastery.customer import Email
from roastery.events import StatusChanged
from roastery.ids import EventId, OrderId, PaymentId, PostalCode
from roastery.money import Money
from roastery.order import PaymentMessage
from roastery.ports import (
    Clock,
    FeedDown,
    ProviderRefused,
    ProviderUnavailable,
)

REFUND_KEY = 'refund-'
"""What a refund's key starts with; the order id follows (ADR 0011)."""


def _utc(moment: dt.datetime) -> dt.datetime:
    """The moment in UTC; it must be timezone-aware."""
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError('a moment must be timezone-aware')
    return moment.astimezone(dt.UTC)


class FakeClock:
    """A UTC moment that moves only when told."""

    def __init__(self, start: dt.datetime) -> None:
        self._now = _utc(start)

    def now(self) -> dt.datetime:
        return self._now

    def set(self, moment: dt.datetime) -> None:
        self._now = _utc(moment)

    def advance(self, by: dt.timedelta) -> None:
        self._now += by


class FakeProvider:
    """A working provider: the payments it holds, refunds by
    its rules, and the messages it would send."""

    def __init__(self, *, refund_ids: Sequence[PaymentId]) -> None:
        self._ids = list(refund_ids)
        self._held: dict[PaymentId, PaymentMessage] = {}
        self._left: dict[PaymentId, Money] = {}
        self._by_key: dict[str, PaymentId] = {}
        self._messages: list[PaymentMessage] = []
        self._down = False

    def take(self, message: PaymentMessage) -> None:
        """A payment the provider now holds."""
        if message.amount.amount <= 0:
            raise ValueError(f'a held payment is above zero: {message}')
        if message.payment_id in self._held:
            return  # delivered twice (PAY-1): held once
        self._held[message.payment_id] = message
        self._left[message.payment_id] = message.amount

    def set_down(self, down: bool) -> None:
        """While down, every call raises ProviderUnavailable."""
        self._down = down

    def refund(
        self, payment_id: PaymentId, amount: Money, *, key: str
    ) -> PaymentId:
        """ProviderRefused for a payment it does not hold or
        more than is left; the same key gives the same id.

        The key is `refund-` and the order the money goes back to;
        the message that follows names that order and, for want of a
        clock, the day the payment was made.
        """
        if self._down:
            raise ProviderUnavailable('the provider is down')
        if key in self._by_key:
            return self._by_key[key]
        held = self._held.get(payment_id)
        if held is None:
            raise ProviderRefused(f'no payment {payment_id}')
        left = self._left[payment_id]
        if amount.amount <= 0:
            raise ValueError(f'a refund is above zero: {amount}')
        if amount.currency != left.currency:
            raise ProviderRefused(
                f'{payment_id} is in {left.currency}, not '
                f'{amount.currency}'
            )
        if amount.amount > left.amount:
            raise ProviderRefused(
                f'{amount.amount} is more than the {left.amount} '
                f'left of {payment_id}'
            )
        if not self._ids:
            raise RuntimeError('the fake has no refund id left')
        order_id = OrderId(key.removeprefix(REFUND_KEY))
        refund_id = self._ids.pop(0)
        self._left[payment_id] = Money(
            left.amount - amount.amount, left.currency
        )
        self._by_key[key] = refund_id
        self._messages.append(
            PaymentMessage(refund_id, order_id, -amount, held.paid_on)
        )
        return refund_id

    def messages(self) -> tuple[PaymentMessage, ...]:
        """The refunds' negative messages, in order: what the
        simulator writes to payments and delivers."""
        return tuple(self._messages)


class FakeNotifier:
    """Keeps what it is asked to send; sends nothing."""

    def __init__(self) -> None:
        self._sent: list[tuple[Email, str]] = []

    def send(self, to: Email, *, subject: str, body: str) -> None:
        self._sent.append((to, subject))

    def sent(self) -> tuple[tuple[Email, str], ...]:
        """(to, subject), in the order asked."""
        return tuple(self._sent)


class FakeLabels:
    """Keeps the labels it is asked for."""

    def __init__(self) -> None:
        self._requested: list[OrderId] = []

    def request(
        self, order_id: OrderId, *, postal_code: PostalCode
    ) -> None:
        self._requested.append(order_id)

    def requested(self) -> tuple[OrderId, ...]:
        return tuple(self._requested)


class FakeFeed:
    """A status feed that keeps what it took, stamped by its clock.

    `refuse` names events the feed will not take yet: a batch that
    holds one is refused, whole, while the clock is before the moment
    listed for it. It refuses by content, never by batch number
    (C28, A23).
    """

    def __init__(
        self,
        clock: Clock,
        *,
        refuse: Mapping[EventId, dt.datetime] | None = None,
    ) -> None:
        self._clock = clock
        self._refuse = dict(refuse or {})
        self._taken: list[tuple[StatusChanged, dt.datetime]] = []

    def send(self, events: Sequence[StatusChanged]) -> None:
        """Take every event of the batch, or raise FeedDown."""
        now = self._clock.now()
        for event in events:
            until = self._refuse.get(event.event_id)
            if until is not None and now < until:
                raise FeedDown(
                    f'{event.event_id} is refused until {until}'
                )
        self._taken.extend((event, now) for event in events)

    def taken(self) -> tuple[tuple[StatusChanged, dt.datetime], ...]:
        """(event, loaded_at), in the order taken."""
        return tuple(self._taken)


class ClosedFeed:
    """A feed that refuses every batch: its rows wait (ADR 0013)."""

    def send(self, events: Sequence[StatusChanged]) -> None:
        raise FeedDown('the feed is closed')
