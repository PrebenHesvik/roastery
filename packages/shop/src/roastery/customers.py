"""The customers: who they are, where they live, when they go.

`Customers` writes in one unit of work per call, and the store
writes the change log with the customer (ADR 0003). `country_of`
is a question, not a command: a customer with no country and a
customer the store does not hold are two different answers, so it
returns a `Result` (ADR 0006, C6).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from zoneinfo import ZoneInfo

from roastery.clock import ZONES, local_date
from roastery.commands import Cancel, apply, check
from roastery.customer import Customer, Email
from roastery.errors import NoSuchCustomer, UnknownId
from roastery.ids import (
    AccountKind,
    Country,
    CustomerId,
    PostalCode,
    SubEventId,
)
from roastery.ports import Clock, CustomerRepository, Ids, UnitOfWork
from roastery.result import Err, Ok
from roastery.subscription import month_of


@dataclass(frozen=True)
class NoCountry:
    """The customer is known and has no country (C-05)."""

    customer_id: CustomerId


@dataclass(frozen=True)
class UnknownCustomer:
    """The store holds no such customer (C-07, erased)."""

    customer_id: CustomerId


def country_of(
    customer_id: CustomerId, customers: CustomerRepository
) -> Ok[Country] | Err[NoCountry | UnknownCustomer]:
    """The customer's country, or why there is none.

    What a missing country means for a price is not decided here
    (C10): the caller matches on the answer.
    """
    try:
        customer = customers.get(customer_id)
    except UnknownId:
        return Err(UnknownCustomer(customer_id))
    if customer.country is None:
        return Err(NoCountry(customer_id))
    return Ok(customer.country)


def find_customer(
    customer_id: CustomerId, customers: CustomerRepository
) -> Customer:
    """The customer; NoSuchCustomer if the store holds none."""
    try:
        return customers.get(customer_id)
    except UnknownId:
        raise NoSuchCustomer(customer_id) from None


def zone_of(country: Country | None, shop_zone: ZoneInfo) -> ZoneInfo:
    """The zone of a customer's own days: the country's, and the
    shop's when the customer has no country."""
    return shop_zone if country is None else ZONES[country]


class Customers:
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

    def register(
        self,
        name: str,
        *,
        email: Email | None,
        country: Country | None,
        postal_code: PostalCode | None,
        account_kind: AccountKind = 'consumer',
    ) -> CustomerId:
        """A customer, joined today; an insert change row. An
        e-mail ends in example.invalid (C25); C-05 has none
        (C37)."""
        now = self._clock.now()
        zone = zone_of(country, self._shop_zone)
        customer = Customer(
            CustomerId(self._ids.next('customer')),
            name,
            email,
            country,
            postal_code,
            account_kind,
            local_date(now, zone),
        )
        with self._uow as uow:
            uow.customers.add(customer, now)
            uow.commit()
        return customer.customer_id

    def change(
        self,
        customer_id: CustomerId,
        *,
        email: Email | None,
        country: Country | None,
        postal_code: PostalCode | None,
    ) -> None:
        """The whole contact after the change (a move, mostly);
        an update change row with the country and postal code."""
        now = self._clock.now()
        with self._uow as uow:
            held = find_customer(customer_id, uow.customers)
            moved = replace(
                held,
                email=email,
                country=country,
                postal_code=postal_code,
            )
            uow.customers.change(moved, now)
            uow.commit()

    def erase(self, customer_id: CustomerId) -> None:
        """Gone, a tombstone row; orders keep the id. Open
        subscriptions are cancelled, reason 'erased', on the
        customer's day; each cancel is checked before any id is
        drawn (A35)."""
        now = self._clock.now()
        with self._uow as uow:
            customer = find_customer(customer_id, uow.customers)
            zone = zone_of(customer.country, self._shop_zone)
            day = local_date(now, zone)
            subs = uow.subscriptions.of_customer(customer_id)
            open_subs = [s for s in subs if s.state != 'cancelled']
            shipped = {
                sub.subscription_id: frozenset(
                    month_of(bag.shipped_on)
                    for bag in uow.subscriptions.bags(
                        sub.subscription_id
                    )
                )
                for sub in open_subs
            }
            for sub in open_subs:
                check(
                    sub,
                    Cancel,
                    day,
                    shipped_months=shipped[sub.subscription_id],
                )
            for sub in open_subs:
                cancel = Cancel(
                    SubEventId(self._ids.next('sub_event')),
                    sub.subscription_id,
                    'erased',
                    now,
                    day,
                )
                apply(
                    sub,
                    cancel,
                    shipped_months=shipped[sub.subscription_id],
                )
                uow.subscriptions.record(cancel)
            uow.customers.erase(customer_id, now)
            uow.commit()
