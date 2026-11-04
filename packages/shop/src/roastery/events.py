"""Events: what happened, as data, and a bus that passes them on.

An event is a frozen object named in the past tense. The part that
made it publishes it after its commit, and does not know who
listens; each listener subscribes to the events it cares about
(ADR 0009).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from roastery.ids import EventId, OrderId

if TYPE_CHECKING:
    from roastery.order import Status


@dataclass(frozen=True)
class OrderPlaced:
    """An order was placed; a handler reads the rest from the store."""

    order_id: OrderId


@dataclass(frozen=True)
class OrderPaid:
    """An order was paid."""

    order_id: OrderId


@dataclass(frozen=True)
class OrderInvoiced:
    """An order was put on invoice."""

    order_id: OrderId


@dataclass(frozen=True)
class StatusChanged:
    """An order moved to a status of the feed, at a moment."""

    event_id: EventId
    order_id: OrderId
    status: Status
    event_at: dt.datetime


Event = OrderPlaced | OrderPaid | OrderInvoiced | StatusChanged
"""Every event the shop publishes or sends."""

Handler = Callable[[Any], None]
"""A listener: it is given the event, and returns nothing."""


@dataclass(frozen=True)
class HandlerFailure:
    """One handler that raised after its call was kept."""

    handler: str  # the handler's qualified name
    event: str  # the event's class name
    error: str  # repr of what it raised


class HandlersFailed(Exception):
    """Handlers raised; every other handler of the event still ran."""

    def __init__(self, failures: Sequence[HandlerFailure]) -> None:
        self.failures = tuple(failures)
        said = '; '.join(
            f'{failure.handler} raised {failure.error}'
            for failure in self.failures
        )
        super().__init__(
            f'{len(self.failures)} handlers failed: {said}'
        )


class EventBus:
    """Handlers by event type, called in the order they subscribed.

    publish() calls each handler of the event's own class (not of a
    base class) one after another, before it returns. A handler that
    raises does not stop the others; when all have run, publish
    raises HandlersFailed naming each failure. Nothing is queued or
    retried, and the handlers live in this object only.
    """

    def __init__(self) -> None:
        self._handlers: dict[type[Event], list[Handler]] = {}

    def subscribe[E: Event](
        self, event_type: type[E], handler: Callable[[E], None]
    ) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    def publish(self, event: object) -> int:
        """Call the event's handlers; returns how many were called."""
        handlers = tuple(self._handlers.get(type(event), ()))
        failures: list[HandlerFailure] = []
        for handler in handlers:
            try:
                handler(event)
            except Exception as error:
                name = getattr(handler, '__qualname__', repr(handler))
                failures.append(
                    HandlerFailure(
                        name, type(event).__name__, repr(error)
                    )
                )
        if failures:
            raise HandlersFailed(failures)
        return len(handlers)


class CollectingBus:
    """Publishes on a bus; keeps what its handlers raised."""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._failures: list[HandlerFailure] = []

    def publish(self, event: object) -> None:
        """bus.publish; a HandlersFailed is kept, not raised."""
        try:
            self._bus.publish(event)
        except HandlersFailed as failed:
            self._failures.extend(failed.failures)

    def failures(self) -> tuple[HandlerFailure, ...]:
        """What the handlers raised since the wiring, in order."""
        return tuple(self._failures)
