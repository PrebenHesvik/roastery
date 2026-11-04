"""The subscription commands as data, and the rules of their order.

A command is a frozen object, the `subscription_events` row it
becomes, so the table is the log. Its `day` is the customer's day of
`event_at`, in the zone `started` is dated by (ADR 0008): the
service works it out, so check(), apply() and replay() stay pure.
check() says whether a move may follow; apply() makes the
subscription after it; replay() rebuilds the state from the start
and the events only (ADR 0011).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import ClassVar, NoReturn, assert_never

from roastery.errors import IllegalSubscriptionMove
from roastery.ids import SubEventId, SubscriptionId
from roastery.subscription import Period, Subscription, month_of


@dataclass(frozen=True)
class _Move:
    """The columns every `subscription_events` row has."""

    event_id: SubEventId
    subscription_id: SubscriptionId
    reason: str
    event_at: dt.datetime  # UTC
    day: dt.date  # event_at on the customer's clock
    EVENT_TYPE: ClassVar[str]


@dataclass(frozen=True)
class Skip(_Move):
    """No bag in the month of `day`."""

    EVENT_TYPE = 'skip'


@dataclass(frozen=True)
class Pause(_Move):
    """No bag from `day` until a resume."""

    EVENT_TYPE = 'pause'


@dataclass(frozen=True)
class Resume(_Move):
    """Bags again from `day`."""

    EVENT_TYPE = 'resume'


@dataclass(frozen=True)
class Cancel(_Move):
    """Ended on `day`."""

    EVENT_TYPE = 'cancel'


Command = Skip | Pause | Resume | Cancel
"""Every move on a subscription, as data."""


def _refuse(sub: Subscription, state: str, action: str) -> NoReturn:
    raise IllegalSubscriptionMove(sub.subscription_id, state, action)


def check(
    sub: Subscription,
    move: type[Command],
    day: dt.date,
    *,
    shipped_months: frozenset[dt.date],
) -> None:
    """Raises IllegalSubscriptionMove if `move` may not follow.

    A service checks before it draws the event's id (A35); apply()
    checks the same way. `shipped_months` holds the first days of
    the months whose bag already shipped: the shipments know it,
    the events do not (A15).
    """
    state = sub.state
    action = move.EVENT_TYPE
    month = month_of(day)
    if state == 'cancelled':
        _refuse(sub, state, action)
    if move in (Skip, Pause) and state != 'running':
        _refuse(sub, state, action)
    if move is Resume and state != 'paused':
        _refuse(sub, state, action)
    if move is Skip and month in shipped_months:
        _refuse(sub, f'shipped for {month:%Y-%m}', action)
    if move is Skip and month in sub.skipped:
        _refuse(sub, f'skipped for {month:%Y-%m}', action)


def _closed(sub: Subscription, day: dt.date) -> tuple[Period, ...]:
    """The periods with the open one ending on `day`."""
    *before, last = sub.periods
    return (*before, replace(last, end=day))


def apply(
    sub: Subscription,
    command: Command,
    *,
    shipped_months: frozenset[dt.date],
) -> Subscription:
    """The subscription after the command; raises if it may not.

    The command is checked first, as check() does it.
    """
    if command.subscription_id != sub.subscription_id:
        raise ValueError(
            f'{command.event_id} is a move of '
            f'{command.subscription_id}, not {sub.subscription_id}'
        )
    day = command.day
    check(sub, type(command), day, shipped_months=shipped_months)
    match command:
        case Skip():
            return replace(sub, skipped=sub.skipped | {month_of(day)})
        case Pause():
            return replace(sub, periods=_closed(sub, day))
        case Resume():
            opened = (*sub.periods, Period(day, None))
            return replace(sub, periods=opened)
        case Cancel():
            periods = sub.periods
            if sub.state == 'running':
                periods = _closed(sub, day)
            return replace(sub, periods=periods, ended=day)
        case _:
            assert_never(command)


def replay(
    sub: Subscription, commands: Iterable[Command]
) -> Subscription:
    """The commands applied in order of `event_at`, from `sub`.

    `sub` is the subscription as `subscriptions.started` has it. The
    events happened, so no shipped month is checked again.
    """
    for command in sorted(commands, key=lambda c: c.event_at):
        sub = apply(sub, command, shipped_months=frozenset())
    return sub
