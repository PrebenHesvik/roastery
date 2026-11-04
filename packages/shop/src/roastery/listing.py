"""What the shop offers: categories, products, prices, campaigns.

`Catalogue` changes the offer in one unit of work per call. A
price, a cost and a rule each have half-open periods: a change
closes the open period on its first day and opens the next, and a
change that starts inside an earlier period is refused with
`PeriodOverlap`. A campaign's percent is given once and written
twice, to `campaigns` and to its pricing rule.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Protocol

from roastery.catalogue import (
    BeanDetails,
    Category,
    EquipmentDetails,
    Product,
)
from roastery.errors import PeriodOverlap, UnknownId, UnknownProduct
from roastery.ids import CampaignId, CategoryId, ProductId, RuleId
from roastery.money import Money
from roastery.ports import Campaign, Cost, Ids, UnitOfWork
from roastery.pricing import Discount, Price


class _Span(Protocol):
    """A row that holds for a half-open period."""

    @property
    def valid_from(self) -> dt.date: ...

    @property
    def valid_to(self) -> dt.date | None: ...


def _open_row[S: _Span](
    rows: Sequence[S], valid_from: dt.date, table: str, key: str
) -> S | None:
    """The open row a period from `valid_from` closes, if any.

    PeriodOverlap if the period would start on or before the start
    of a row, or inside one that has ended.
    """
    for row in rows:
        inside = row.valid_to is not None and valid_from < row.valid_to
        if valid_from <= row.valid_from or inside:
            raise PeriodOverlap(table, key, valid_from)
    return next((row for row in rows if row.valid_to is None), None)


class Catalogue:
    def __init__(self, uow: UnitOfWork, ids: Ids) -> None:
        self._uow = uow
        self._ids = ids

    def add_category(
        self,
        name: str,
        *,
        parent_id: CategoryId | None,
        sort_order: int,
    ) -> CategoryId:
        with self._uow as uow:
            _require_category(uow, parent_id)
            category = Category(
                CategoryId(self._ids.next('category')),
                name,
                parent_id,
                sort_order,
            )
            uow.catalogue.add_category(category)
            uow.commit()
        return category.category_id

    def add_product(
        self,
        name: str,
        *,
        category_id: CategoryId,
        details: BeanDetails | EquipmentDetails,
    ) -> ProductId:
        """products and its subtype row; the kind and weight_g
        follow from the details."""
        match details:
            case BeanDetails(weight_g=weight_g):
                kind, weight = 'beans', weight_g
            case EquipmentDetails():
                kind, weight = 'equipment', None
        with self._uow as uow:
            _require_category(uow, category_id)
            product = Product(
                ProductId(self._ids.next('product')),
                name,
                kind,
                category_id,
                weight,
            )
            uow.catalogue.add_product(product, details)
            uow.commit()
        return product.product_id

    def set_price(
        self,
        product_id: ProductId,
        *,
        price: Money,
        valid_from: dt.date,
    ) -> None:
        """Closes the open period on valid_from, opens one."""
        with self._uow as uow:
            _require_product(uow, product_id)
            held = uow.prices.of(product_id)
            opened = _open_row(
                held, valid_from, 'prices', str(product_id)
            )
            if opened is not None:
                uow.prices.close(product_id, valid_from)
            uow.prices.add(Price(product_id, price, valid_from, None))
            uow.commit()

    def set_cost(
        self,
        product_id: ProductId,
        *,
        valid_from: dt.date,
        green: Money,
        packaging: Money,
        roasting: Money,
    ) -> None:
        """Closes the open cost period, opens one."""
        with self._uow as uow:
            _require_product(uow, product_id)
            held = uow.costs.of(product_id)
            opened = _open_row(
                held, valid_from, 'product_costs', str(product_id)
            )
            if opened is not None:
                uow.costs.close(product_id, valid_from)
            uow.costs.add(
                Cost(
                    product_id,
                    valid_from,
                    None,
                    green,
                    packaging,
                    roasting,
                )
            )
            uow.commit()

    def add_campaign(
        self,
        name: str,
        *,
        discount_pct: int,
        first_day: dt.date,
        last_day: dt.date,
        product_ids: tuple[ProductId, ...],
    ) -> None:
        """campaigns, campaign_products and its pricing rule
        (percent = discount_pct, valid_to = last_day + 1)."""
        held = tuple(sorted(product_ids, key=str))
        with self._uow as uow:
            for product_id in held:
                _require_product(uow, product_id)
            campaign = Campaign(
                CampaignId(self._ids.next('campaign')),
                name,
                discount_pct,
                first_day,
                last_day,
                held,
            )
            rule = Discount(
                RuleId(self._ids.next('rule')),
                'campaign',
                discount_pct,
                first_day,
                last_day + dt.timedelta(days=1),
                frozenset(held),
            )
            uow.catalogue.add_campaign(campaign)
            uow.rules.add(rule, campaign_id=campaign.campaign_id)
            uow.commit()

    def set_subscriber_discount(
        self, percent: int | None, *, valid_from: dt.date
    ) -> None:
        """Closes the open subscriber rule; None opens none."""
        with self._uow as uow:
            held = tuple(
                sorted(
                    (
                        rule
                        for rule in uow.rules.all()
                        if rule.rule_kind == 'subscriber'
                    ),
                    key=lambda rule: rule.valid_from,
                )
            )
            opened = _open_row(
                held, valid_from, 'pricing_rules', 'subscriber'
            )
            if opened is not None:
                uow.rules.close(opened.rule_id, valid_from)
            if percent is not None:
                rule = Discount(
                    RuleId(self._ids.next('rule')),
                    'subscriber',
                    percent,
                    valid_from,
                    None,
                )
                uow.rules.add(rule)
            uow.commit()


def _require_category(
    uow: UnitOfWork, category_id: CategoryId | None
) -> None:
    """UnknownId unless the store holds the category (or none)."""
    if category_id is None:
        return
    known = {each.category_id for each in uow.catalogue.categories()}
    if category_id not in known:
        raise UnknownId('category', str(category_id))


def _require_product(uow: UnitOfWork, product_id: ProductId) -> Product:
    """The product; UnknownProduct if the shop lists none."""
    try:
        return uow.catalogue.product(product_id)
    except UnknownId:
        raise UnknownProduct(product_id) from None
