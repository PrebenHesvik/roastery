"""The simulator's status feed: the second adapter at the `StatusFeed` port.

It keeps `FakeFeed`'s rule (ADR 0009, A23): a batch that holds an event
listed in `refuse` is refused whole, with `FeedDown`, while the clock is
before that event's moment. A batch taken is stamped with the moment of
the send that took it. It keeps every event it took, in the order taken;
leaving some out of the export is the export writer's job, not the feed's.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence

from roastery.events import StatusChanged
from roastery.ids import EventId
from roastery.pipeline import Rows
from roastery.ports import Clock, FeedDown

ORDER_EVENTS = ('event_id', 'order_id', 'status', 'event_at', 'loaded_at')
"""The columns of `order_events`, as contract A names them."""


class Feed:
    """A `StatusFeed` that writes `order_events` as it takes events."""

    def __init__(self, clock: Clock, *, refuse: Mapping[EventId, dt.datetime]) -> None:
        self._clock = clock
        self._refuse = dict(refuse)
        self._taken: list[tuple[StatusChanged, dt.datetime]] = []

    def send(self, events: Sequence[StatusChanged]) -> None:
        """Take every event of the batch, or raise FeedDown."""
        now = self._clock.now()
        for event in events:
            until = self._refuse.get(event.event_id)
            if until is not None and now < until:
                raise FeedDown(f'{event.event_id} is refused until {until}')
        self._taken.extend((event, now) for event in events)

    def rows(self) -> Rows:
        """`order_events`: every event taken, in the order taken."""
        rows = tuple(
            (event.event_id.value, event.order_id.value, event.status, event.event_at, loaded_at)
            for event, loaded_at in self._taken
        )
        return Rows('order_events', ORDER_EVENTS, rows)
