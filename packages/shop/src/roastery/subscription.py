"""A subscription and the days it owes a bag.

A subscription is one bag of beans a month. It runs in periods
(half-open, as every period of the shop: the day it stopped is not
in it), so a pause closes one and a resume opens the next. A skipped
month owes nothing. `commands.apply` makes the next value; this
module only holds one and answers (ADR 0011).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Literal, Self

from roastery.ids import CustomerId, ProductId, SubscriptionId

State = Literal['cancelled', 'paused', 'running']
"""Where a subscription stands; `state` gives it."""


def month_of(day: dt.date) -> dt.date:
    """The first day of the month `day` falls in."""
    return day.replace(day=1)


@dataclass(frozen=True)
class Period:
    """Days a subscription runs: from `start`, up to but not `end`."""

    start: dt.date
    end: dt.date | None  # None: still open

    def __post_init__(self) -> None:
        if self.end is not None and self.end < self.start:
            raise ValueError('a period must not end before it starts')

    def covers(self, on: dt.date) -> bool:
        return self.start <= on and (self.end is None or on < self.end)


@dataclass(frozen=True)
class Subscription:
    subscription_id: SubscriptionId
    customer_id: CustomerId
    product_id: ProductId
    started: dt.date
    periods: tuple[Period, ...]  # when it runs, oldest first
    skipped: frozenset[dt.date]  # first days of months with no bag
    ended: dt.date | None  # the day of the cancel

    def __post_init__(self) -> None:
        if any(month != month_of(month) for month in self.skipped):
            raise ValueError('a skipped month is its first day')

    @classmethod
    def begin(
        cls,
        subscription_id: SubscriptionId,
        customer_id: CustomerId,
        product_id: ProductId,
        started: dt.date,
    ) -> Self:
        """As `subscriptions.started` has it: running, none skipped."""
        return cls(
            subscription_id,
            customer_id,
            product_id,
            started,
            (Period(started, None),),
            frozenset(),
            None,
        )

    @property
    def state(self) -> State:
        if self.ended is not None:
            return 'cancelled'
        if self.periods and self.periods[-1].end is None:
            return 'running'
        return 'paused'

    def bags_due(self, on: dt.date) -> bool:
        """Does `on` owe its month's bag: running, month not skipped.

        Whether the bag already shipped is the shipments' fact, not
        this value's.
        """
        return month_of(on) not in self.skipped and any(
            period.covers(on) for period in self.periods
        )
