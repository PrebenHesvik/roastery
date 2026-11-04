"""Which bags a subscription owes, and what a failing handler does.

The subscription moves decide which bags ship; the bus decides
whether a handler's failure reaches the caller (ADR 0009, 0011).
"""

from __future__ import annotations

import datetime as dt

import pytest

from roastery.commands import (
    Cancel,
    Command,
    Pause,
    Resume,
    Skip,
    apply,
    replay,
)
from roastery.errors import IllegalSubscriptionMove
from roastery.events import (
    CollectingBus,
    EventBus,
    HandlersFailed,
    OrderPaid,
)
from roastery.ids import (
    CustomerId,
    OrderId,
    ProductId,
    SubEventId,
    SubscriptionId,
)
from roastery.subscription import Subscription

NONE_SHIPPED: frozenset[dt.date] = frozenset()


def day(text: str) -> dt.date:
    return dt.date.fromisoformat(text)


def sub(number: int, started: str) -> Subscription:
    return Subscription.begin(
        SubscriptionId(f'S-{number}'),
        CustomerId('C-02'),
        ProductId('P-11'),
        day(started),
    )


def move[C: Command](kind: type[C], sub_id: str, at: str) -> C:
    moment = dt.datetime.fromisoformat(at).replace(tzinfo=dt.UTC)
    return kind(SubEventId('SE-1'), SubscriptionId(sub_id), '', moment)


def test_replay_of_s2_stops_on_the_first_of_august() -> None:
    s2 = sub(2, '2025-02-01')  # dataset.sql: ended 2025-08-01
    stopped = replay(s2, [move(Cancel, 'S-2', '2025-08-01T09:00')])
    assert stopped.ended == day('2025-08-01')
    assert stopped.bags_due(day('2025-07-31'))
    assert not stopped.bags_due(day('2025-08-01'))


def test_replay_of_s3_owes_nothing_until_the_first_of_september() -> (
    None
):
    s3 = replay(sub(3, '2025-09-01'), [])  # dataset.sql: started it
    assert not s3.bags_due(day('2025-08-31'))
    assert s3.bags_due(day('2025-09-01'))
    assert s3.ended is None


def test_a_skip_in_its_month_means_no_bag_that_month() -> None:
    s1 = sub(1, '2024-04-01')
    skipped = apply(
        s1,
        move(Skip, 'S-1', '2026-10-07T08:00'),
        shipped_months=NONE_SHIPPED,
    )
    assert not skipped.bags_due(day('2026-10-20'))
    assert skipped.bags_due(day('2026-11-02'))


def test_pause_then_resume_owes_nothing_in_between() -> None:
    s1 = sub(1, '2024-04-01')
    moves: list[Command] = [
        move(Pause, 'S-1', '2026-10-10T08:00'),
        move(Resume, 'S-1', '2026-11-03T08:00'),
    ]
    back = replay(s1, moves)
    assert back.bags_due(day('2026-10-09'))
    assert not back.bags_due(day('2026-10-20'))
    assert back.bags_due(day('2026-11-03'))
    assert back.ended is None


def test_a_skip_of_a_shipped_month_is_refused() -> None:
    s1 = sub(1, '2024-04-01')
    with pytest.raises(IllegalSubscriptionMove) as refused:
        apply(
            s1,
            move(Skip, 'S-1', '2026-10-07T08:00'),
            shipped_months=frozenset({day('2026-10-01')}),
        )
    assert refused.value.subscription_id == s1.subscription_id


@pytest.mark.parametrize('after', [Skip, Pause, Resume, Cancel])
def test_any_move_after_a_cancel_is_refused(
    after: type[Command],
) -> None:
    cancelled = replay(
        sub(7, '2025-03-01'), [move(Cancel, 'S-7', '2026-10-09T10:00')]
    )
    with pytest.raises(IllegalSubscriptionMove):
        apply(
            cancelled,
            move(after, 'S-7', '2026-10-10T10:00'),
            shipped_months=NONE_SHIPPED,
        )


class Calls:
    """Records which handlers ran, for one test."""

    def __init__(self) -> None:
        self.ran: list[str] = []

    def confirm(self, event: OrderPaid) -> None:
        self.ran.append('confirm')

    def label(self, event: OrderPaid) -> None:
        self.ran.append('label')
        raise RuntimeError('carrier is down')

    def audit(self, event: OrderPaid) -> None:
        self.ran.append('audit')


def bus_with(calls: Calls) -> EventBus:
    bus = EventBus()
    bus.subscribe(OrderPaid, calls.confirm)
    bus.subscribe(OrderPaid, calls.label)
    bus.subscribe(OrderPaid, calls.audit)
    return bus


def test_one_handler_raises_the_others_run_and_the_error_names_it() -> (
    None
):
    calls = Calls()
    with pytest.raises(HandlersFailed) as failed:
        bus_with(calls).publish(OrderPaid(OrderId('O-101')))
    assert calls.ran == ['confirm', 'label', 'audit']
    (only,) = failed.value.failures
    assert only.handler == 'Calls.label'
    assert only.event == 'OrderPaid'
    assert 'carrier is down' in only.error


def test_a_collecting_bus_keeps_the_failure_and_returns() -> None:
    calls = Calls()
    bus = CollectingBus(bus_with(calls))
    bus.publish(OrderPaid(OrderId('O-101')))
    assert calls.ran == ['confirm', 'label', 'audit']
    (only,) = bus.failures()
    assert only.handler == 'Calls.label'
