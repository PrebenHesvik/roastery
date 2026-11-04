"""The VAT rules a quiet mistake would break.

The rates are ADR 0010's seed (docs/facts/vat.md); the prices are
O-101's lines in dataset.sql: 129.00 beans and 899.00 equipment.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from roastery.catalogue import Kind
from roastery.ids import COUNTRIES, Country, CustomerId, OrderId
from roastery.money import Money
from roastery.order import Head, OrderLine, Placed
from roastery.vat import SEED_RATES, VatRates, scheme_for, vat_of

RATES = VatRates(SEED_RATES)
ON = dt.date(2026, 10, 5)  # O-101's day


@pytest.mark.parametrize(
    ('country', 'kind', 'on', 'rate'),
    [
        ('FI', 'equipment', dt.date(2024, 8, 31), '24'),
        ('FI', 'equipment', dt.date(2024, 9, 1), '25.5'),
        ('SE', 'beans', dt.date(2026, 3, 31), '12'),
        ('SE', 'beans', dt.date(2026, 4, 1), '6'),
    ],
)
def test_a_rate_is_the_one_of_its_day(
    country: Country, kind: Kind, on: dt.date, rate: str
) -> None:
    assert RATES.rate_on(country, kind, on) == Decimal(rate)


def test_a_day_no_row_covers_raises() -> None:
    # Sweden's 6 % on food ends after 2027-12-31.
    with pytest.raises(LookupError):
        RATES.rate_on('SE', 'beans', dt.date(2028, 1, 1))


def test_the_lookup_refuses_no_country() -> None:
    # C-05 has no country: checkout.order_country decides, not this.
    with pytest.raises(TypeError):
        RATES.rate_on(None, 'beans', ON)  # type: ignore[arg-type]


def test_an_export_owes_nothing_in_its_currency() -> None:
    gross = Money.of('516.98', 'SEK')
    assert vat_of(gross, Decimal('25'), 'export') == Money.of(
        '0.00', 'SEK'
    )


@pytest.mark.parametrize(
    ('gross', 'kind', 'share'),
    [
        ('129.00', 'beans', '16.83'),
        ('899.00', 'equipment', '179.80'),
        ('-129.00', 'beans', '-16.83'),  # a credit line
    ],
)
def test_the_domestic_share_of_a_gross_price(
    gross: str, kind: Kind, share: str
) -> None:
    rate = RATES.rate_on('NO', kind, ON)
    assert vat_of(Money.of(gross, 'NOK'), rate, 'domestic') == (
        Money.of(share, 'NOK')
    )


@pytest.mark.parametrize('country', COUNTRIES)
def test_only_norway_is_domestic(country: Country) -> None:
    line = OrderLine.of(
        line_id='L-01', product_id='P-10', qty=2, unit_price='129.00'
    )
    head = Head(
        OrderId('O-101'),
        CustomerId('C-01'),
        'web',
        country,
        (line,),
        None,
    )
    expected = 'domestic' if country == 'NO' else 'export'
    assert scheme_for(Placed(head), ON) == expected
