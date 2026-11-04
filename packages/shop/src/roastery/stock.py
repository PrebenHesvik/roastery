"""The shop's stock: what comes in, what goes out, what is counted.

Every change is a signed movement, in is positive. `Stock` writes
the roasted, written-off and counted ones, and the green coffee
bought. A sale (and its undoing) is checkout's, a subscription's
bag is the job's (C21). Below the class sits the arithmetic of the
count at close, which the job of that name calls (A16).
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Final
from zoneinfo import ZoneInfo

from roastery.catalogue import Product
from roastery.clock import local_date
from roastery.errors import (
    OutOfStock,
    UnknownId,
    UnknownProduct,
    WrongKind,
)
from roastery.ids import MovementId, ProductId, PurchaseId
from roastery.money import Money, Qty, in_nok, two_places
from roastery.ports import (
    Clock,
    Count,
    GreenPurchase,
    Ids,
    Movement,
    MovementReason,
    StockRepository,
    UnitOfWork,
)

CLOSE: Final = (18, 0)
"""The shop closes at 18:00 (hour, minute) in the shop's zone."""


def closing_moment(day: dt.date, shop_zone: ZoneInfo) -> dt.datetime:
    """The moment the shop closed on `day`, in UTC.

    It is the stamp of that day's count, whenever the count runs
    (C23): 18:00 in Bergen is 16:00 UTC in October.
    """
    hour, minute = CLOSE
    close = dt.datetime(
        day.year, day.month, day.day, hour, minute, tzinfo=shop_zone
    )
    return close.astimezone(dt.UTC)


def last_closed_day(now: dt.datetime) -> dt.date:
    """The last UTC day that has ended: the day before `now`'s."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('now must be timezone-aware')
    return now.astimezone(dt.UTC).date() - dt.timedelta(days=1)


def on_hand(
    stock: StockRepository, product_id: ProductId, day: dt.date
) -> int:
    """The balance at the end of the UTC day `day`: every movement
    made on that day or before (S19, ADR 0011)."""
    midnight = dt.datetime.combine(
        day + dt.timedelta(days=1), dt.time(), tzinfo=dt.UTC
    )
    return stock.on_hand(product_id, before=midnight)


def count_closed_day(
    uow: UnitOfWork, clock: Clock, shop_zone: ZoneInfo
) -> int:
    """Write `stock_daily` for the last closed day; the rows
    written (A16).

    One row for each product the shop lists, zero balances
    included, stamped with the day's close. A product already
    counted with that stamp is left alone, so a rerun writes none.
    """
    day = last_closed_day(clock.now())
    counted_at = closing_moment(day, shop_zone)
    written = 0
    with uow:
        done = {
            count.product_id
            for count in uow.stock.counts(day)
            if count.counted_at == counted_at
        }
        for product in uow.catalogue.products():
            if product.product_id in done:
                continue
            uow.stock.add_count(
                Count(
                    product.product_id,
                    day,
                    on_hand(uow.stock, product.product_id, day),
                    counted_at,
                )
            )
            written += 1
        uow.commit()
    return written


class Stock:
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

    def roast(self, product_id: ProductId, *, bags: Qty) -> None:
        """A roasted movement: bags in."""
        _above_zero(bags)
        now = self._clock.now()
        with self._uow as uow:
            product = _product(uow, product_id)
            if product.kind != 'beans':
                raise WrongKind(product_id, product.kind)
            self._move(uow, product_id, 'roasted', bags.value, now)
            uow.commit()

    def write_off(self, product_id: ProductId, *, qty: Qty) -> None:
        """A written_off movement: qty out."""
        _above_zero(qty)
        now = self._clock.now()
        with self._uow as uow:
            _product(uow, product_id)
            held = uow.stock.on_hand(product_id)
            if qty.value > held:
                raise OutOfStock(product_id, qty.value, held)
            self._move(uow, product_id, 'written_off', -qty.value, now)
            uow.commit()

    def stocktake(self, product_id: ProductId, *, on_hand: int) -> None:
        """A counted movement of the difference found, if any.
        Equipment comes in this way (no reason fits better)."""
        if isinstance(on_hand, bool) or not isinstance(on_hand, int):
            raise TypeError('on_hand must be a whole number')
        if on_hand < 0:
            raise ValueError('on_hand must not be negative')
        now = self._clock.now()
        with self._uow as uow:
            _product(uow, product_id)
            found = on_hand - uow.stock.on_hand(product_id)
            if found != 0:
                self._move(uow, product_id, 'counted', found, now)
            uow.commit()

    def buy_green(
        self, *, origin: str, kg: Decimal, nok_per_kg: Money
    ) -> None:
        """A green_purchases row, bought today; ValueError for a
        kg or a price with a third place, or a price not in NOK."""
        if not isinstance(kg, Decimal):
            raise TypeError('kg must be a Decimal')
        if not kg.is_finite() or kg <= 0:
            raise ValueError(f'kg must be above zero: {kg}')
        two_places(kg, 'kg')
        in_nok(nok_per_kg, 'nok_per_kg')
        now = self._clock.now()
        purchase = GreenPurchase(
            PurchaseId(self._ids.next('purchase')),
            local_date(now, self._shop_zone),
            origin,
            kg,
            nok_per_kg,
        )
        with self._uow as uow:
            uow.purchases.add(purchase)
            uow.commit()

    def _move(
        self,
        uow: UnitOfWork,
        product_id: ProductId,
        reason: MovementReason,
        qty: int,
        now: dt.datetime,
    ) -> None:
        uow.stock.add(
            Movement(
                MovementId(self._ids.next('movement')),
                product_id,
                now,
                reason,
                qty,
            )
        )


def _above_zero(qty: Qty) -> None:
    """A roast or a write-off moves one or more."""
    if qty.value < 1:
        raise ValueError(f'qty must be 1 or more: {qty.value}')


def _product(uow: UnitOfWork, product_id: ProductId) -> Product:
    """The product; UnknownProduct if the shop lists none."""
    try:
        return uow.catalogue.product(product_id)
    except UnknownId:
        raise UnknownProduct(product_id) from None
