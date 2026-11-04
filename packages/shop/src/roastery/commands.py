"""The subscription commands as data, and the rules of their order.

A command is a frozen object, the `subscription_events` row it
becomes, so the table is the log. apply() is pure: a subscription
and a command in, the subscription after out, or a refusal. replay()
rebuilds the state from the start and the events only (ADR 0011).
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
    EVENT_TYPE: ClassVar[str]


@dataclass(frozen=True)
class Skip(_Move):
    """No bag in the month of `event_at`."""

    EVENT_TYPE = 'skip'


@dataclass(frozen=True)
class Pause(_Move):
    """No bag from `event_at` until a resume."""

    EVENT_TYPE = 'pause'


@dataclass(frozen=True)
class Resume(_Move):
    """Bags again from `event_at`."""

    EVENT_TYPE = 'resume'


@dataclass(frozen=True)
class Cancel(_Move):
    """Ended on the day of `event_at`."""

    EVENT_TYPE = 'cancel'


Command = Skip | Pause | Resume | Cancel
"""Every move on a subscription, as data."""


def _refuse(sub: Subscription, state: str, action: str) -> NoReturn:
    raise IllegalSubscriptionMove(sub.subscription_id, state, action)


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

    `shipped_months` holds the first days of the months whose bag
    already shipped: the shipments know it, the events do not (A15).
    """
    if command.subscription_id != sub.subscription_id:
        raise ValueError(
            f'{command.event_id} is a move of '
            f'{command.subscription_id}, not {sub.subscription_id}'
        )
    state = sub.state
    day = command.event_at.date()
    action = command.EVENT_TYPE
    if state == 'cancelled':
        _refuse(sub, state, action)
    match command:
        case Skip():
            month = month_of(day)
            if state != 'running':
                _refuse(sub, state, action)
            if month in shipped_months:
                _refuse(sub, f'shipped for {month:%Y-%m}', action)
            if month in sub.skipped:
                _refuse(sub, f'skipped for {month:%Y-%m}', action)
            return replace(sub, skipped=sub.skipped | {month})
        case Pause():
            if state != 'running':
                _refuse(sub, state, action)
            return replace(sub, periods=_closed(sub, day))
        case Resume():
            if state != 'paused':
                _refuse(sub, state, action)
            opened = (*sub.periods, Period(day, None))
            return replace(sub, periods=opened)
        case Cancel():
            periods = sub.periods
            if state == 'running':
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
