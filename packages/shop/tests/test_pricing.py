"""The pricing rules a quiet mistake would break.

Prices, products, campaigns and subscriptions are dataset.sql's.
`pricing_rules` is not in tiny, so the rule rows (PR-1 to PR-3)
and the subscriber percents are made up for the tests.
"""

from __future__ import annotations

import datetime as dt

import pytest

from roastery.catalogue import Product
from roastery.errors import NoPrice
from roastery.ids import (
    CategoryId,
    CustomerId,
    ProductId,
    RuleId,
    SubscriptionId,
)
from roastery.money import Money
from roastery.pricing import (
    RULES,
    Discount,
    DuplicateRule,
    Price,
    Quote,
    Sale,
    list_price,
    per_rule,
    price_lines,
    standard_rules,
)
from roastery.subscription import Period, Subscription

P10 = Product(
    ProductId('P-10'),
    'Morning roast',
    'beans',
    CategoryId('CAT-11'),
    250,
)
P20 = Product(
    ProductId('P-20'),
    'Hand grinder',
    'equipment',
    CategoryId('CAT-22'),
    None,
)
P21 = Product(
    ProductId('P-21'),
    'Pour-over kettle',
    'equipment',
    CategoryId('CAT-23'),
    None,
)


def _price(
    product: str, amount: str, start: str, end: str | None
) -> Price:
    return Price(
        ProductId(product),
        Money.of(amount, 'NOK'),
        dt.date.fromisoformat(start),
        None if end is None else dt.date.fromisoformat(end),
    )


PRICES = (
    _price('P-10', '119.00', '2024-01-01', '2026-10-01'),
    _price('P-10', '129.00', '2026-10-01', None),
    _price('P-20', '899.00', '2025-06-01', None),
    _price('P-21', '549.00', '2026-10-07', None),
)

# K-1, Autumn espresso: 10 %, 12 to 25 October; valid_to is
# last_day + 1.
K1 = Discount(
    RuleId('PR-1'),
    'campaign',
    10,
    dt.date(2026, 10, 12),
    dt.date(2026, 10, 26),
    frozenset({ProductId('P-11'), ProductId('P-20')}),
)
# K-2, Brew at home: 15 %, 16 to 29 November.
K2 = Discount(
    RuleId('PR-2'),
    'campaign',
    15,
    dt.date(2026, 11, 16),
    dt.date(2026, 11, 30),
    frozenset(
        {ProductId('P-10'), ProductId('P-20'), ProductId('P-21')}
    ),
)

# S-7: C-07's, ended 2026-10-09. S-1: C-01's, still running.
S7 = Subscription(
    SubscriptionId('S-7'),
    CustomerId('C-07'),
    ProductId('P-10'),
    dt.date(2025, 3, 1),
    (Period(dt.date(2025, 3, 1), dt.date(2026, 10, 9)),),
    frozenset(),
    dt.date(2026, 10, 9),
)
S1 = Subscription.begin(
    SubscriptionId('S-1'),
    CustomerId('C-01'),
    ProductId('P-10'),
    dt.date(2024, 4, 1),
)


def _subscriber_rule(percent: int) -> Discount:
    return Discount(
        RuleId('PR-3'), 'subscriber', percent, dt.date(2026, 1, 1), None
    )


def _quote(
    product: Product,
    on: dt.date,
    *,
    customer: str = 'C-01',
    discounts: tuple[Discount, ...] = (),
    subscriptions: tuple[Subscription, ...] = (),
) -> Quote:
    sale = Sale(
        CustomerId(customer),
        product,
        on,
        PRICES,
        discounts,
        subscriptions,
    )
    (quote,) = price_lines([sale], per_rule(RULES, list_price))
    return quote


@pytest.mark.parametrize(
    ('on', 'price'),
    [
        (dt.date(2026, 9, 30), '119.00'),
        (dt.date(2026, 10, 1), '129.00'),
    ],
)
def test_the_list_price_holds_in_half_open_periods(
    on: dt.date, price: str
) -> None:
    assert _quote(P10, on).unit_price == Money.of(price, 'NOK')


def test_no_list_price_raises_no_price() -> None:
    # L-06 sold P-21 on 6 October; its list price starts on 7th.
    with pytest.raises(NoPrice) as raised:
        _quote(P21, dt.date(2026, 10, 6))
    assert raised.value.product_id == ProductId('P-21')


@pytest.mark.parametrize(
    ('on', 'price'),
    [
        (dt.date(2026, 10, 25), '809.10'),
        (dt.date(2026, 10, 26), '899.00'),
    ],
)
def test_a_campaign_holds_through_its_last_day(
    on: dt.date, price: str
) -> None:
    quote = _quote(P20, on, discounts=(K1,))
    assert quote.unit_price == Money.of(price, 'NOK')


@pytest.mark.parametrize(
    ('product', 'on', 'price'),
    [
        (P10, dt.date(2026, 10, 8), '116.10'),  # beans, running
        (P10, dt.date(2026, 10, 9), '129.00'),  # S-7 has ended
        (P20, dt.date(2026, 10, 8), '899.00'),  # equipment
    ],
)
def test_the_subscriber_rule_takes_a_running_beans_line(
    product: Product, on: dt.date, price: str
) -> None:
    quote = _quote(
        product,
        on,
        customer='C-07',
        discounts=(_subscriber_rule(10),),
        subscriptions=(S7,),
    )
    assert quote.unit_price == Money.of(price, 'NOK')


@pytest.mark.parametrize(
    ('subscriber_pct', 'percent', 'price'),
    [(10, 15, '109.65'), (20, 20, '103.20')],
)
def test_the_larger_percent_wins_and_none_stack(
    subscriber_pct: int, percent: int, price: str
) -> None:
    # C-01 subscribes (S-1) and buys P-10 during K-2 (15 %).
    quote = _quote(
        P10,
        dt.date(2026, 11, 20),
        discounts=(K2, _subscriber_rule(subscriber_pct)),
        subscriptions=(S1,),
    )
    assert (quote.percent, quote.unit_price) == (
        percent,
        Money.of(price, 'NOK'),
    )


def test_a_discount_on_half_an_ore_rounds_half_up() -> None:
    # A made-up list price: none of dataset.sql's lands on half an
    # øre at K-2's 15 %. 12.50 less 15 % is 10.625: half up gives
    # 10.63, where half even or down would give 10.62 (A3).
    sale = Sale(
        CustomerId('C-01'),
        P21,
        dt.date(2026, 11, 20),
        (_price('P-21', '12.50', '2026-10-07', None),),
        (K2,),
        (),
    )
    (quote,) = price_lines([sale], per_rule(RULES, list_price))
    assert (quote.percent, quote.unit_price) == (
        15,
        Money.of('10.63', 'NOK'),
    )


def test_a_rule_name_registered_twice_raises() -> None:
    registry = standard_rules()
    with pytest.raises(DuplicateRule):
        registry.add('list', list_price)
