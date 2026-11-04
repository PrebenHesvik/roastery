"""How the shop prices a line on its day: the rule is passed in.

A rule is given a `Sale` (the product, the day and the facts the
rules read) and answers with a `Quote`, or None when it does not
hold. `list_price` always holds or raises; `subscriber` and
`campaign` take a percent off it, each from a `pricing_rules` row.
One rule prices a line: the larger percent wins, and two rules
never stack (A14). The rules are registered by `rule_kind`, in a
`Registry` that `wire` builds, one per wiring.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Final, Literal

from roastery.catalogue import Product
from roastery.errors import NoPrice
from roastery.ids import CustomerId, ProductId, RuleId
from roastery.money import Money
from roastery.subscription import Subscription

DiscountKind = Literal['campaign', 'subscriber']
"""The `rule_kind` of a `pricing_rules` row: it holds a percent."""

DISCOUNT_KINDS: Final[tuple[DiscountKind, ...]] = (
    'campaign',
    'subscriber',
)


def _covers(
    valid_from: dt.date, valid_to: dt.date | None, on: dt.date
) -> bool:
    """Is `on` in the half-open period: from, up to but not to."""
    return valid_from <= on and (valid_to is None or on < valid_to)


def _check_period(
    valid_from: dt.date, valid_to: dt.date | None
) -> None:
    if valid_to is not None and valid_to <= valid_from:
        raise ValueError('a period must end after it starts')


@dataclass(frozen=True)
class Price:
    """A row of `prices`: a product's list price on its days."""

    product_id: ProductId
    price: Money
    valid_from: dt.date
    valid_to: dt.date | None  # the first day it no longer holds

    def __post_init__(self) -> None:
        _check_period(self.valid_from, self.valid_to)

    def covers(self, on: dt.date) -> bool:
        return _covers(self.valid_from, self.valid_to, on)


@dataclass(frozen=True)
class Discount:
    """A row of `pricing_rules`, with the products it holds for.

    A campaign's rule holds for its `campaign_products`, from its
    first day up to `last_day + 1`; the subscriber rule holds for
    every beans product and names none.
    """

    rule_id: RuleId
    rule_kind: DiscountKind
    percent: int
    valid_from: dt.date
    valid_to: dt.date | None
    product_ids: frozenset[ProductId] = frozenset()

    def __post_init__(self) -> None:
        if self.rule_kind not in DISCOUNT_KINDS:
            raise ValueError(
                f'rule kind must be one of {DISCOUNT_KINDS}'
            )
        _check_percent(self.percent)
        _check_period(self.valid_from, self.valid_to)
        if (self.rule_kind == 'campaign') != bool(self.product_ids):
            raise ValueError('only a campaign rule names products')

    def covers(self, on: dt.date) -> bool:
        return _covers(self.valid_from, self.valid_to, on)


def _check_percent(percent: int) -> None:
    if isinstance(percent, bool) or not isinstance(percent, int):
        raise TypeError(f'percent must be a whole number: {percent!r}')
    if not 0 <= percent <= 100:
        raise ValueError(f'percent must be from 0 to 100: {percent}')


@dataclass(frozen=True)
class Sale:
    """A line asked for on its day: what a rule is given.

    The facts are read from the store by the caller; a rule only
    reads them. `subscriptions` are the customer's.
    """

    customer_id: CustomerId
    product: Product
    on: dt.date
    prices: tuple[Price, ...]
    discounts: tuple[Discount, ...]
    subscriptions: tuple[Subscription, ...]


@dataclass(frozen=True)
class Quote:
    """A line's unit price, and the percent taken off the list."""

    product_id: ProductId
    unit_price: Money
    percent: int  # 0: the list price


Rule = Callable[[Sale], Quote | None]
"""A pricing rule: a sale in, its quote out, or None if it does not
hold."""


def list_price(sale: Sale) -> Quote:
    """The list price on the sale's day; NoPrice when none holds."""
    product_id = sale.product.product_id
    held = [
        row
        for row in sale.prices
        if row.product_id == product_id and row.covers(sale.on)
    ]
    if not held:
        raise NoPrice(product_id, sale.on)
    if len(held) > 1:
        raise ValueError(f'{product_id} has two prices on {sale.on}')
    return Quote(product_id, held[0].price, 0)


def with_discount(percent: int, rule: Rule) -> Rule:
    """The rule's price less a whole percent: a rule wraps a rule.

    It wraps `list_price`; rounded to the øre once, by `to_ore`.
    """
    _check_percent(percent)
    keep = Decimal(100 - percent) / 100

    def discounted(sale: Sale) -> Quote | None:
        base = rule(sale)
        if base is None:
            return None
        amount = base.unit_price.amount * keep
        price = Money(amount, base.unit_price.currency).to_ore()
        return Quote(base.product_id, price, percent)

    return discounted


def _subscribes(sale: Sale) -> bool:
    """A subscription of the customer runs on the sale's day.

    A skipped month still runs; a pause or a cancel ends a period.
    """
    return any(
        sub.customer_id == sale.customer_id
        and any(period.covers(sale.on) for period in sub.periods)
        for sub in sale.subscriptions
    )


def _best(
    sale: Sale, kind: DiscountKind, product_id: ProductId | None
) -> Quote | None:
    """The list price less the largest percent of `kind` that holds."""
    percents = [
        row.percent
        for row in sale.discounts
        if row.rule_kind == kind
        and row.covers(sale.on)
        and (product_id is None or product_id in row.product_ids)
    ]
    if not percents:
        return None
    return with_discount(max(percents), list_price)(sale)


def subscriber(sale: Sale) -> Quote | None:
    """A beans line of a subscriber, while a subscriber rule holds."""
    if sale.product.kind != 'beans' or not _subscribes(sale):
        return None
    return _best(sale, 'subscriber', None)


def campaign(sale: Sale) -> Quote | None:
    """A line of a product in a campaign, on the campaign's days."""
    return _best(sale, 'campaign', sale.product.product_id)


def per_rule(rules: Mapping[str, Rule], default: Rule) -> Rule:
    """The one rule with the larger percent, or the default.

    A rule picks a rule: each quote is taken off the list price,
    and one quote prices the line, so two rules never stack (A14).
    A tie goes to the default, then to the first name sorted
    (A31); equal percents give the same price.
    """
    chosen = tuple(sorted(rules.items()))

    def rule(sale: Sale) -> Quote | None:
        best = default(sale)
        for _name, each in chosen:
            quote = each(sale)
            if quote is None:
                continue
            if best is None or quote.percent > best.percent:
                best = quote
        return best

    return rule


def price_lines(sales: Iterable[Sale], rule: Rule) -> list[Quote]:
    """A quote per sale, in order; a sale no rule prices raises."""
    quotes: list[Quote] = []
    for sale in sales:
        quote = rule(sale)
        if quote is None:
            raise NoPrice(sale.product.product_id, sale.on)
        quotes.append(quote)
    return quotes


RULES: Final[Mapping[str, Rule]] = MappingProxyType(
    {
        'campaign': campaign,
        'list': list_price,
        'subscriber': subscriber,
    }
)
"""The standard rules, by `pricing_rules.rule_kind`; read-only."""


class UnknownRule(LookupError):
    """No rule has this name."""


class DuplicateRule(ValueError):
    """A rule of this name is already registered."""


def rule_named(name: str, rules: Mapping[str, Rule] = RULES) -> Rule:
    """The rule of this name; raises, naming the known ones."""
    if name not in rules:
        known = ', '.join(sorted(rules))
        raise UnknownRule(f'no rule {name!r}; known: {known}')
    return rules[name]


class Registry:
    """Rules by name, added by registering them: a case, no if chain.

    Each registry is its own object, built in `wire`, so a rule one
    wiring or test registers is never seen by another.
    """

    def __init__(self) -> None:
        self._rules: dict[str, Rule] = {}

    def add(self, name: str, rule: Rule) -> None:
        if name in self._rules:
            raise DuplicateRule(f'rule {name!r} is already registered')
        self._rules[name] = rule

    def register[R: Rule](self, name: str) -> Callable[[R], R]:
        """A decorator: adds the function under `name`, as it is."""

        def decorate(rule: R) -> R:
            self.add(name, rule)
            return rule

        return decorate

    def get(self, name: str) -> Rule:
        """The rule of this name; raises, naming the known ones."""
        return rule_named(name, self._rules)

    @property
    def rules(self) -> Mapping[str, Rule]:
        """A read-only copy, sorted by name."""
        return MappingProxyType(dict(sorted(self._rules.items())))


def standard_rules() -> Registry:
    """A new registry holding the three rules of RULES."""
    registry = Registry()
    for name, rule in RULES.items():
        registry.add(name, rule)
    return registry
