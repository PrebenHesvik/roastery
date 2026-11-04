"""The outbox: status changes kept in the change's transaction.

A service adds the `StatusChanged` row in its unit of work, so the
row is kept with the order's new state or not at all (C26). `relay`
sends the rows later, in batches, through the `StatusFeed` port
(ADR 0009). A batch keeps its rows: a waiting batch is offered
again as it was, and new rows never join it.
"""

from __future__ import annotations

import sqlite3
from dataclasses import replace

from roastery.errors import DuplicateId, UnknownId
from roastery.events import StatusChanged
from roastery.ids import EventId, OrderId
from roastery.ports import (
    Batch,
    FeedDown,
    Relayed,
    Source,
    StatusFeed,
    UnitOfWork,
)
from roastery.repository import (
    OutboxRow,
    Tables,
    moment_from,
    moment_text,
)


def _chunks(size: int, items: list[int]) -> list[list[int]]:
    """`items` cut into runs of `size`; the last may be shorter."""
    if size < 1:
        raise ValueError(f'a batch holds one row or more: {size}')
    return [items[at : at + size] for at in range(0, len(items), size)]


class InMemoryOutbox:
    """The outbox in a dict, by position."""

    def __init__(self, tables: Tables, source: Source) -> None:
        self._t = tables
        self._source = source

    def add(self, event: StatusChanged) -> int:
        held = (row.event.event_id for row in self._t.outbox.values())
        if event.event_id in held:
            raise DuplicateId('event', str(event.event_id))
        position = max(self._t.outbox, default=0) + 1
        self._t.outbox[position] = OutboxRow(
            event, None, False, self._source
        )
        return position

    def form_batches(self, size: int) -> tuple[int, ...]:
        loose = sorted(
            at
            for at, row in self._t.outbox.items()
            if row.batch is None
        )
        last = max(
            (row.batch or 0 for row in self._t.outbox.values()),
            default=0,
        )
        made: list[int] = []
        for number, run in enumerate(_chunks(size, loose), last + 1):
            for at in run:
                row = self._t.outbox[at]
                self._t.outbox[at] = replace(row, batch=number)
            made.append(number)
        return tuple(made)

    def waiting(self) -> tuple[Batch, ...]:
        numbers = sorted(
            {
                row.batch
                for row in self._t.outbox.values()
                if row.batch is not None and not row.sent
            }
        )
        return tuple(
            Batch(
                number,
                tuple(
                    self._t.outbox[at].event
                    for at in sorted(self._t.outbox)
                    if self._t.outbox[at].batch == number
                ),
            )
            for number in numbers
        )

    def mark_sent(self, number: int) -> None:
        held = [
            at
            for at, row in self._t.outbox.items()
            if row.batch == number and not row.sent
        ]
        if not held:
            raise UnknownId('batch', str(number))
        for at in held:
            self._t.outbox[at] = replace(self._t.outbox[at], sent=True)


class SqliteOutbox:
    """The outbox in the `outbox` table of the connection.

    It commits nothing: `add` writes in the caller's transaction.
    """

    def __init__(
        self, connection: sqlite3.Connection, source: Source
    ) -> None:
        self._db = connection
        self._source = source

    def add(self, event: StatusChanged) -> int:
        taken = self._db.execute(
            'SELECT 1 FROM outbox WHERE event_id = ?',
            (str(event.event_id),),
        ).fetchone()
        if taken is not None:
            raise DuplicateId('event', str(event.event_id))
        (last,) = self._db.execute(
            'SELECT COALESCE(MAX(position), 0) FROM outbox'
        ).fetchone()
        self._db.execute(
            'INSERT INTO outbox (position, event_id, order_id, status,'
            ' event_at, batch, sent, source)'
            ' VALUES (?, ?, ?, ?, ?, NULL, 0, ?)',
            (
                last + 1,
                str(event.event_id),
                str(event.order_id),
                event.status,
                moment_text(event.event_at),
                self._source,
            ),
        )
        return last + 1

    def form_batches(self, size: int) -> tuple[int, ...]:
        loose = [
            at
            for (at,) in self._db.execute(
                'SELECT position FROM outbox WHERE batch IS NULL'
                ' ORDER BY position'
            ).fetchall()
        ]
        (last,) = self._db.execute(
            'SELECT COALESCE(MAX(batch), 0) FROM outbox'
        ).fetchone()
        made: list[int] = []
        for number, run in enumerate(_chunks(size, loose), last + 1):
            for at in run:
                self._db.execute(
                    'UPDATE outbox SET batch = ? WHERE position = ?',
                    (number, at),
                )
            made.append(number)
        return tuple(made)

    def waiting(self) -> tuple[Batch, ...]:
        numbers = [
            number
            for (number,) in self._db.execute(
                'SELECT DISTINCT batch FROM outbox'
                ' WHERE batch IS NOT NULL AND sent = 0 ORDER BY batch'
            ).fetchall()
        ]
        return tuple(
            Batch(number, self._events(number)) for number in numbers
        )

    def mark_sent(self, number: int) -> None:
        marked = self._db.execute(
            'UPDATE outbox SET sent = 1 WHERE batch = ? AND sent = 0',
            (number,),
        )
        if marked.rowcount == 0:
            raise UnknownId('batch', str(number))

    def _events(self, number: int) -> tuple[StatusChanged, ...]:
        rows = self._db.execute(
            'SELECT event_id, order_id, status, event_at FROM outbox'
            ' WHERE batch = ? ORDER BY position',
            (number,),
        ).fetchall()
        return tuple(
            StatusChanged(
                EventId(event_id),
                OrderId(order_id),
                status,
                moment_from(event_at),
            )
            for event_id, order_id, status, event_at in rows
        )


def relay(uow: UnitOfWork, feed: StatusFeed, *, size: int) -> Relayed:
    """Form new batches, then offer each waiting one to the feed.

    A batch the feed refuses waits for the next run; the batches
    after it still go. A batch is marked sent only after the feed
    took it: at least once, never lost, perhaps twice.
    """
    with uow:
        uow.outbox.form_batches(size)
        uow.commit()
    with uow:
        batches = uow.outbox.waiting()
    sent: list[int] = []
    waiting: list[int] = []
    for batch in batches:
        try:
            feed.send(batch.events)
        except FeedDown:
            waiting.append(batch.number)
            continue
        with uow:
            uow.outbox.mark_sent(batch.number)
            uow.commit()
        sent.append(batch.number)
    return Relayed(tuple(sent), tuple(waiting))
