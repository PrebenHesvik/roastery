"""The subscriptions: one bag of beans a month, and the moves on it.

Each move (skip, pause, resume, cancel) builds its command, checks
it with `commands.apply` against the subscription as its events
leave it, and keeps it: the command is the `subscription_events`
row it becomes (ADR 0011). `subscribe` writes the start and no
event. Below the class sits the arithmetic of the monthly job that
ships the bags (A15).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import replace
from zoneinfo import ZoneInfo

from roastery.clock import local_date
from roastery.commands import (
    Cancel,
    Command,
    Pause,
    Resume,
    Skip,
    apply,
)
from roastery.customers import find_customer, zone_of
from roastery.errors import (
    OutOfStock,
    UnknownId,
    UnknownProduct,
    WrongKind,
)
from roastery.ids import (
    BagId,
    CustomerId,
    MovementId,
    ProductId,
    SubEventId,
    SubscriptionId,
)
from roastery.ports import (
    BagShipment,
    Clock,
    Ids,
    Movement,
    UnitOfWork,
)
from roastery.subscription import Subscription, month_of


def shipped_months(
    uow: UnitOfWork, subscription_id: SubscriptionId
) -> frozenset[dt.date]:
    """The first days of the months whose bag already shipped:
    the shipments know it, the events do not (A15)."""
    return frozenset(
        month_of(bag.shipped_on)
        for bag in uow.subscriptions.bags(subscription_id)
    )


class Subscriptions:
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

    def subscribe(
        self, customer_id: CustomerId, *, product_id: ProductId
    ) -> SubscriptionId:
        """One bag a month of beans, started today."""
        now = self._clock.now()
        with self._uow as uow:
            customer = find_customer(customer_id, uow.customers)
            try:
                product = uow.catalogue.product(product_id)
            except UnknownId:
                raise UnknownProduct(product_id) from None
            if product.kind != 'beans':
                raise WrongKind(product_id, product.kind)
            zone = zone_of(customer.country, self._shop_zone)
            sub = Subscription.begin(
                SubscriptionId(self._ids.next('subscription')),
                customer_id,
                product_id,
                local_date(now, zone),
            )
            uow.subscriptions.add(sub)
            uow.commit()
        return sub.subscription_id

    def skip(
        self, subscription_id: SubscriptionId, *, reason: str
    ) -> None:
        """No bag in this month."""
        self._move(subscription_id, Skip, reason)

    def pause(
        self, subscription_id: SubscriptionId, *, reason: str
    ) -> None:
        """No bag until it is resumed."""
        self._move(subscription_id, Pause, reason)

    def resume(
        self, subscription_id: SubscriptionId, *, reason: str
    ) -> None:
        self._move(subscription_id, Resume, reason)

    def cancel(
        self, subscription_id: SubscriptionId, *, reason: str
    ) -> None:
        """Ended today."""
        self._move(subscription_id, Cancel, reason)

    def _move(
        self,
        subscription_id: SubscriptionId,
        command_type: type[Skip | Pause | Resume | Cancel],
        reason: str,
    ) -> None:
        """Build the command, check it against the subscription,
        keep it as its row."""
        now = self._clock.now()
        with self._uow as uow:
            sub = uow.subscriptions.get(subscription_id)
            # Checked first, with no id drawn: a refused move must
            # leave the Ids port as it was.
            trial = command_type(
                SubEventId('SE-0'), subscription_id, reason, now
            )
            apply(
                sub,
                trial,
                shipped_months=shipped_months(uow, subscription_id),
            )
            command: Command = replace(
                trial, event_id=SubEventId(self._ids.next('sub_event'))
            )
            uow.subscriptions.record(command)
            uow.commit()


def ship_subscription_bags(
    uow: UnitOfWork, clock: Clock, ids: Ids, shop_zone: ZoneInfo
) -> int:
    """Ship this month's bag to each subscription that owes one.

    The month is the shop's today. A subscription owes a bag when
    it runs and has not skipped the month (`bags_due`) and none
    shipped this month. Each bag is a `subscription_shipments` row
    and a `shipped` movement out. A bag that would take the balance
    below zero raises OutOfStock and nothing is shipped in the run.
    Returns the bags shipped; a second run in the month ships none.
    """
    now = clock.now()
    today = local_date(now, shop_zone)
    month = month_of(today)
    with uow:
        left: dict[ProductId, int] = {}
        due: list[Subscription] = []
        for sub in uow.subscriptions.all():
            if not sub.bags_due(today):
                continue
            if month in shipped_months(uow, sub.subscription_id):
                continue
            pid = sub.product_id
            if pid not in left:
                left[pid] = uow.stock.on_hand(pid)
            if left[pid] < 1:
                raise OutOfStock(pid, 1, left[pid])
            left[pid] -= 1
            due.append(sub)
        for sub in due:
            uow.subscriptions.add_bag(
                BagShipment(
                    BagId(ids.next('bag')),
                    sub.subscription_id,
                    sub.product_id,
                    today,
                    1,
                )
            )
            uow.stock.add(
                Movement(
                    MovementId(ids.next('movement')),
                    sub.product_id,
                    now,
                    'shipped',
                    -1,
                )
            )
        uow.commit()
    return len(due)
