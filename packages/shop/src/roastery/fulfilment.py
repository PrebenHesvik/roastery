"""Getting an order to the customer: ship, deliver, and what is late.

`Fulfilment` moves a paid or invoiced web order to shipped and then
delivered, each with its outbox row in the same unit of work. It
writes no stock movement: the bags left at place (C21). `confirm`
and `label` are the two handlers of the paid and invoiced events
(C26, C39); they write nothing and reach the world through a port.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, replace
from zoneinfo import ZoneInfo

from roastery import order as orders
from roastery.clock import ZONES, local_date
from roastery.errors import NoAddress, NotShippable, UnknownId
from roastery.events import OrderInvoiced, OrderPaid, StatusChanged
from roastery.ids import EventId, OrderId, ShipmentId
from roastery.order import Invoiced, Order, Paid, Status, late_orders
from roastery.ports import (
    Clock,
    Ids,
    Labels,
    Notifier,
    Shipment,
    UnitOfWork,
)


@dataclass(frozen=True)
class _Settlement:
    """When an order was settled: what `late_orders` reads."""

    order_id: OrderId
    status: Status
    event_at: dt.datetime


class Fulfilment:
    def __init__(
        self,
        uow: UnitOfWork,
        clock: Clock,
        ids: Ids,
        shop_zone: ZoneInfo,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids
        self._shop_zone = shop_zone

    def ship(
        self, order_id: OrderId, *, promised_by: dt.date
    ) -> ShipmentId:
        """Shipped, and a shipments row. No stock movement:
        the bags left at place. NoAddress for an order whose
        customer has no postal code (C39)."""
        now = self._clock.now()
        with self._uow as uow:
            order = uow.orders.get(order_id)
            head = order.head
            if head.channel == 'shop':
                raise NotShippable(order_id)
            orders.check(order, 'ship')
            try:
                customer = uow.customers.get(head.customer_id)
            except UnknownId:
                raise NoAddress(order_id) from None
            if customer.postal_code is None:
                raise NoAddress(order_id)
            shipment_id = ShipmentId(self._ids.next('shipment'))
            uow.orders.save(orders.ship(order, shipment_id))
            uow.shipments.add(
                Shipment(
                    shipment_id,
                    order_id,
                    local_date(now, ZONES[head.country]),
                    promised_by,
                    None,
                )
            )
            uow.outbox.add(
                StatusChanged(
                    EventId(self._ids.next('event')),
                    order_id,
                    'shipped',
                    now,
                )
            )
            uow.commit()
        return shipment_id

    def deliver(self, shipment_id: ShipmentId) -> None:
        """Delivered; delivered_on on the shipments row."""
        now = self._clock.now()
        with self._uow as uow:
            shipment = uow.shipments.get(shipment_id)
            order = uow.orders.get(shipment.order_id)
            delivered = orders.deliver(order)
            day = local_date(now, ZONES[order.head.country])
            uow.orders.save(delivered)
            uow.shipments.save(replace(shipment, delivered_on=day))
            uow.outbox.add(
                StatusChanged(
                    EventId(self._ids.next('event')),
                    shipment.order_id,
                    'delivered',
                    now,
                )
            )
            uow.commit()

    def late_shipments(self) -> tuple[Order, ...]:
        """Web orders settled and not shipped in two working days.

        The shell around `order.late_orders`: it reads the orders,
        works out the shop's day from the clock and passes both in.
        The feed rows leave the outbox once sent, so the day an
        order was settled is read from what the store keeps: the
        payment's day for a paid order, the booking's day for an
        invoiced one (an invoice written later than its order is
        counted from the order's day).
        """
        today = local_date(self._clock.now(), self._shop_zone)
        with self._uow as uow:
            settled: list[_Settlement] = []
            everything = uow.orders.all()
            for order in everything:
                if not isinstance(order, Paid | Invoiced):
                    continue
                order_id = order.head.order_id
                day = uow.orders.booking(order_id).order_date
                state: Status = 'invoiced'
                if isinstance(order, Paid):
                    state = 'paid'
                    days = [
                        p.paid_on for p in uow.payments.of(order_id)
                    ]
                    day = min(days, default=day)
                noon = dt.datetime.combine(
                    day, dt.time(12), tzinfo=dt.UTC
                )
                settled.append(_Settlement(order_id, state, noon))
        return late_orders(everything, settled, today)


def confirm(
    event: OrderPaid | OrderInvoiced,
    *,
    uow: UnitOfWork,
    notifier: Notifier,
) -> None:
    """The confirmation e-mail, when the customer has an address.

    Never for a credit order. It runs after the commit that
    published the event, so the unit of work is free. A customer
    the store no longer holds (erased) has no address to write to.
    """
    with uow:
        order = uow.orders.get(event.order_id)
        head = order.head
        if head.credit_of is not None:
            return
        try:
            customer = uow.customers.get(head.customer_id)
        except UnknownId:
            return
    if customer.email is None:
        return
    what = 'paid' if isinstance(event, OrderPaid) else 'invoiced'
    notifier.send(
        customer.email,
        subject=f'Your order {head.order_id}',
        body=(
            f'Hello {customer.name}. Your order {head.order_id} '
            f'is {what}. We ship it as soon as we can.'
        ),
    )


def label(
    event: OrderPaid | OrderInvoiced,
    *,
    uow: UnitOfWork,
    labels: Labels,
) -> None:
    """The shipping label, for a web order with a postal code.

    A counter sale and a credit order get none, and neither does an
    order whose customer has no postal code: `ship` refuses it.
    """
    with uow:
        order = uow.orders.get(event.order_id)
        head = order.head
        if head.channel != 'web' or head.credit_of is not None:
            return
        try:
            customer = uow.customers.get(head.customer_id)
        except UnknownId:
            return
    if customer.postal_code is None:
        return
    labels.request(head.order_id, postal_code=customer.postal_code)
