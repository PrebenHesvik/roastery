"""The outbox and the relay, on both stores (ADR 0009).

A batch the feed refuses waits while the next one goes, which is how
E-10 lands before E-09. The rows are those of the frozen week:
E-09 (O-104 placed, 6 October 15:20) and E-10 (O-104 paid, 15:21).
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path

import pytest

from roastery.customer import Customer
from roastery.events import StatusChanged
from roastery.fakes import FakeClock, FakeFeed
from roastery.ids import CustomerId, EventId, OrderId
from roastery.order import Status
from roastery.outbox import relay
from roastery.ports import Relayed, Store
from roastery.repository import SequentialIds, create_tables
from roastery.uow import SqliteStore


def _at(day: int, hour: int, minute: int) -> dt.datetime:
    return dt.datetime(2026, 10, day, hour, minute, tzinfo=dt.UTC)


def _event(
    number: int, status: Status, when: dt.datetime
) -> StatusChanged:
    return StatusChanged(
        EventId(f'E-{number:02d}'),
        OrderId('O-104'),
        status,
        when,
    )


E09 = _event(9, 'placed', _at(6, 15, 20))
E10 = _event(10, 'paid', _at(6, 15, 21))


def _add(store: Store, *events: StatusChanged) -> None:
    uow = store.unit_of_work('scripted')
    with uow:
        for event in events:
            uow.outbox.add(event)
        uow.commit()


def _sent(feed: FakeFeed) -> list[tuple[str, dt.datetime]]:
    return [(str(e.event_id), at) for e, at in feed.taken()]


def test_a_refused_batch_waits_and_the_next_batch_goes(
    store: Store, clock: FakeClock
) -> None:
    events = [_event(n, 'placed', _at(5, 8, n)) for n in (1, 2, 3)]
    _add(store, *events)
    feed = FakeFeed(clock, refuse={EventId('E-02'): _at(5, 12, 0)})
    uow = store.unit_of_work('scripted')
    first = relay(uow, feed, size=1)
    assert first == Relayed(sent=(1, 3), waiting=(2,))
    assert [str(e.event_id) for e, _ in feed.taken()] == [
        'E-01',
        'E-03',
    ]
    clock.set(_at(5, 12, 0))
    second = relay(uow, feed, size=1)
    assert second == Relayed(sent=(2,), waiting=())
    assert [str(e.event_id) for e, _ in feed.taken()] == [
        'E-01',
        'E-03',
        'E-02',
    ]


@pytest.mark.parametrize('size', [1, 5])
def test_e10_lands_before_e09_and_e09_lands_once(
    store: Store, clock: FakeClock, size: int
) -> None:
    feed = FakeFeed(clock, refuse={E09.event_id: _at(6, 15, 45)})
    uow = store.unit_of_work('scripted')
    _add(store, E09)
    clock.set(_at(6, 15, 20))
    assert relay(uow, feed, size=size) == Relayed((), (1,))
    _add(store, E10)
    clock.set(_at(6, 15, 30))
    assert relay(uow, feed, size=size) == Relayed((2,), (1,))
    assert _sent(feed) == [('E-10', _at(6, 15, 30))]
    clock.set(_at(6, 15, 45))
    assert relay(uow, feed, size=size) == Relayed((1,), ())
    assert _sent(feed) == [
        ('E-10', _at(6, 15, 30)),
        ('E-09', _at(6, 15, 45)),
    ]
    clock.set(_at(6, 16, 0))
    assert relay(uow, feed, size=size) == Relayed((), ())
    assert len(feed.taken()) == 2


def test_a_unit_left_without_commit_leaves_no_outbox_row(
    store: Store, clock: FakeClock
) -> None:
    uow = store.unit_of_work('scripted')
    with uow:
        assert uow.outbox.add(E09) == 1
    feed = FakeFeed(clock)
    assert relay(uow, feed, size=5) == Relayed((), ())
    assert feed.taken() == ()
    with uow:
        assert uow.outbox.add(E10) == 1
        uow.commit()
    assert relay(uow, feed, size=5) == Relayed((1,), ())
    assert [str(e.event_id) for e, _ in feed.taken()] == ['E-10']


def test_sequential_ids_skip_the_planted_lines() -> None:
    skip = frozenset({'L-05', 'L-09'})
    ids = SequentialIds({'line': 4}, skip)
    made = [ids.next('line') for _ in range(5)]
    assert made == [
        'L-0000004',
        'L-0000006',
        'L-0000007',
        'L-0000008',
        'L-0000010',
    ]


def test_a_file_backed_store_keeps_what_was_committed(
    tmp_path: Path, clock: FakeClock
) -> None:
    path = tmp_path / 'shop.db'
    ada = Customer(
        CustomerId('C-01'),
        'Ada',
        None,
        'NO',
        None,
        'consumer',
        dt.date(2024, 4, 1),
    )
    first = sqlite3.connect(path)
    try:
        create_tables(first)
        written = SqliteStore(first, clock=clock, price_ttl=60)
        uow = written.unit_of_work('scripted')
        with uow:
            uow.customers.add(ada, _at(5, 9, 0))
            uow.outbox.add(E09)
            uow.commit()
    finally:
        first.close()
    second = sqlite3.connect(path)
    try:
        create_tables(second)
        reopened = SqliteStore(second, clock=clock, price_ttl=60)
        uow = reopened.unit_of_work('scripted')
        with uow:
            assert uow.customers.all() == (ada,)
            assert [b.events for b in uow.outbox.waiting()] == []
            assert uow.outbox.form_batches(5) == (1,)
            assert uow.outbox.waiting()[0].events == (E09,)
    finally:
        second.close()
