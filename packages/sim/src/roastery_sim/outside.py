"""The outside systems the simulator plays for the week (ADR 0012).

Plain writers with no ports: the payment provider's log around the one
`FakeProvider`, and one frozen fact type per outside table that tiny
holds, each with a function from facts to `Rows`. A fact type's fields
are contract A's columns for its table, in order. The script fills them.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from dataclasses import astuple, dataclass, fields, replace
from decimal import Decimal

from roastery.fakes import FakeProvider
from roastery.ids import PaymentId
from roastery.payments import PaymentMessage
from roastery.pipeline import Rows

PAYMENTS = ('payment_id', 'order_id', 'currency', 'amount', 'paid_on')
"""The columns of `payments`, as contract A names them."""


class ProviderLog:
    """The payment provider's log: one `payments` row per message it sent."""

    def __init__(self, provider: FakeProvider) -> None:
        self._provider = provider
        self._log: list[PaymentMessage] = []
        self._delivered: set[PaymentId] = set()

    def deliver(self, message: PaymentMessage) -> PaymentMessage:
        """Log the message, let the provider take it, and give it back.

        A redelivery logs a second identical row; the provider holds it once.
        """
        self._log.append(message)
        self._delivered.add(message.payment_id)
        if message.amount.amount > 0:  # a refund is the provider's own: it holds no negative
            self._provider.take(message)
        return message

    def refunds(self, *, on: dt.date) -> tuple[PaymentMessage, ...]:
        """The provider's refund messages not yet delivered, in order, dated `on`.

        The fake dates a refund as its payment; a refund is the shop's act of the day it is
        delivered, so `on` (the shop's local date of that moment) replaces `paid_on`.
        """
        return tuple(
            replace(m, paid_on=on)
            for m in self._provider.messages()
            if m.payment_id not in self._delivered
        )

    def sent(self, message: PaymentMessage, *, on: dt.date) -> bool:
        """Whether the provider sent this refund message: one waiting, dated `on` (the shop's
        local date of its delivery), or one delivered already, redelivered as it was logged."""
        if message.payment_id in self._delivered:
            return message in self._log
        return message in self.refunds(on=on)

    def rows(self) -> Rows:
        """`payments`: every message delivered, in the order delivered."""
        rows = tuple(
            (m.payment_id.value, m.order_id.value, m.amount.currency, m.amount.amount, m.paid_on)
            for m in self._log
        )
        return Rows('payments', PAYMENTS, rows)


def _rows(name: str, kind: type, facts: Iterable[object]) -> Rows:
    """The facts as the table's rows; its columns are the fact type's fields."""
    columns = tuple(f.name for f in fields(kind))
    return Rows(name, columns, tuple(astuple(f) for f in facts))  # type: ignore[call-overload]


@dataclass(frozen=True)
class FxRate:
    """What one unit of a currency cost in kroner on a banking day."""

    currency: str
    rate_date: dt.date
    nok_per_unit: Decimal


@dataclass(frozen=True)
class Manager:
    """The person who sees the customers of a country."""

    manager: str
    country: str


@dataclass(frozen=True)
class WebEvent:
    """One thing a visitor did on the web shop, in UTC."""

    event_id: str
    visitor_id: str
    customer_id: str | None
    event: str
    event_at: dt.datetime
    visit_id: int | None = None


@dataclass(frozen=True)
class WebVisit:
    """One visit to the web shop; no referrer is a direct visit, no variant is outside the test."""

    visit_id: int
    visitor_id: str
    visit_date: dt.date
    country: str
    referrer: str | None
    variant: str | None


@dataclass(frozen=True)
class WeatherDay:
    """The rain that fell in Bergen on a day."""

    shop_date: dt.date
    rain_mm: int


@dataclass(frozen=True)
class DoorCount:
    """The people the door counter counted on a day."""

    shop_date: dt.date
    walk_ins: int


@dataclass(frozen=True)
class TillDayTotal:
    """The receipts the old till rang on a day."""

    shop_date: dt.date
    receipts: int


@dataclass(frozen=True)
class ProductCode:
    """A code the till knows and the product it is (None: no product)."""

    ean: str
    product_id: str | None


@dataclass(frozen=True)
class TillReceipt:
    """A till receipt; `sold_at` is Bergen time, naive; no member is None (R-5001)."""

    receipt_id: str
    member_no: int | None
    sold_at: dt.datetime


@dataclass(frozen=True)
class TillLine:
    """One line of a till receipt; grams only for loose beans."""

    receipt_id: str
    line_no: int
    ean: str
    grams: int | None
    amount: Decimal


@dataclass(frozen=True)
class TillMember:
    """One member in one nightly list of the club."""

    member_no: int
    name: str
    email: str | None
    postal_code: str | None
    listed_on: dt.date


def fx_rates(facts: Iterable[FxRate]) -> Rows:
    return _rows('fx_rates', FxRate, facts)


def managers(facts: Iterable[Manager]) -> Rows:
    return _rows('managers', Manager, facts)


def web_events(facts: Iterable[WebEvent]) -> Rows:
    return _rows('web_events', WebEvent, facts)


def product_codes(facts: Iterable[ProductCode]) -> Rows:
    return _rows('product_codes', ProductCode, facts)


def till_receipts(facts: Iterable[TillReceipt]) -> Rows:
    return _rows('till_receipts', TillReceipt, facts)


def till_lines(facts: Iterable[TillLine]) -> Rows:
    return _rows('till_lines', TillLine, facts)


def till_members(facts: Iterable[TillMember]) -> Rows:
    return _rows('till_members', TillMember, facts)


def web_visits(facts: Iterable[WebVisit]) -> Rows:
    return _rows('web_visits', WebVisit, facts)


def weather_days(facts: Iterable[WeatherDay]) -> Rows:
    return _rows('weather_days', WeatherDay, facts)


def door_counts(facts: Iterable[DoorCount]) -> Rows:
    return _rows('door_counts', DoorCount, facts)


def till_day_totals(facts: Iterable[TillDayTotal]) -> Rows:
    return _rows('till_day_totals', TillDayTotal, facts)
