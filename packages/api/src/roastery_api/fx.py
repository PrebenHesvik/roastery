"""Money on the page: display rates and what the page says of VAT (ADR 0018).

The shop's amounts are NOK, and `Money` never converts (ADR 0004). The page shows each
amount also in the buyer's currency, at a fixed rate: the latest of each currency in the
simulator's `script.FX`, copied here because the server does not import the simulator. A
dev test pins the copy to the script. A converted amount is for the page only: never
stored, never charged.

The functions here take the handlers' plain bodies (text amounts, as `roastery.api.plain`
renders them) and add the display amounts beside the NOK ones.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Final, Literal

from roastery.ids import Country
from roastery.money import Money

Currency = Literal['NOK', 'SEK', 'DKK', 'EUR']


@dataclass(frozen=True)
class Rate:
    """What one unit of a currency cost in NOK, on the day the bank said so."""

    currency: Currency
    rate_date: dt.date | None
    nok_per_unit: Decimal


RATES: Final[Mapping[Currency, Rate]] = MappingProxyType(
    {
        'DKK': Rate('DKK', dt.date(2026, 10, 2), Decimal('1.5580')),
        'EUR': Rate('EUR', dt.date(2026, 10, 7), Decimal('11.6300')),
        'NOK': Rate('NOK', None, Decimal('1')),
        'SEK': Rate('SEK', dt.date(2026, 10, 6), Decimal('1.0620')),
    }
)
"""The display rates: `script.FX`'s latest row of each currency (a test pins them)."""

CURRENCIES: Final[Mapping[Country, Currency]] = MappingProxyType(
    {'DK': 'DKK', 'FI': 'EUR', 'NO': 'NOK', 'SE': 'SEK'}
)
"""The display currency of each buyer country."""

PriceLabel = Literal['incl_vat', 'no_norwegian_vat']
"""What a price line says: Norway's "incl. VAT", or "No Norwegian VAT" (F3)."""

DueOnDelivery = Literal['nothing', 'import_vat_estimate', 'vat_excise_and_fees']
"""What the page says below the total: nothing for Norway; an estimate of import VAT for
Sweden and Finland; for Denmark, VAT, coffee excise and fees with no amount (F3)."""


def currency_of(country: Country) -> Currency:
    """The buyer country's display currency."""
    return CURRENCIES[country]


def price_label(country: Country) -> PriceLabel:
    """Only Norway's prices hold Norwegian VAT."""
    return 'incl_vat' if country == 'NO' else 'no_norwegian_vat'


def due_on_delivery(country: Country) -> DueOnDelivery:
    """What is due at the door, by country (ADR 0018's table)."""
    if country == 'NO':
        return 'nothing'
    if country == 'DK':
        return 'vat_excise_and_fees'
    return 'import_vat_estimate'


def display(amount: Money, currency: Currency) -> Money:
    """A NOK amount shown in another currency, to the cent.

    NOK divided by the currency's NOK per unit, rounded half up by `to_ore`. For the page
    only: never stored, never charged.
    """
    if amount.currency != 'NOK':
        raise ValueError(f'only NOK is shown in another currency, not {amount.currency}')
    if currency == 'NOK':
        return amount
    rate = RATES[currency].nok_per_unit
    return Money(amount.amount / rate, currency).to_ore()


# The handlers' plain bodies -------------------------------------------------------------

type Body = dict[str, Any]


def _money(plain: Mapping[str, Any]) -> Money:
    return Money(Decimal(plain['amount']), plain['currency'])


def _shown(plain: Mapping[str, Any] | None, currency: Currency) -> Body | None:
    """A plain NOK amount in the display currency, plain again."""
    if plain is None:
        return None
    shown = display(_money(plain), currency)
    return {'amount': str(shown.amount), 'currency': shown.currency}


def _plain(amount: Money) -> Body:
    return {'amount': str(amount.amount), 'currency': amount.currency}


def listing_page(body: Mapping[str, Any], country: Country) -> Body:
    """`GET /products`: each product's price also in the country's currency."""
    currency = currency_of(country)
    return {
        'country': country,
        'currency': currency,
        'price_label': price_label(country),
        'products': [listed_page(each, country) for each in body['products']],
    }


def listed_page(listed: Mapping[str, Any], country: Country) -> Body:
    """One listed product, its price shown in the country's currency (None: coming soon)."""
    return {**listed, 'display_price': _shown(listed['unit_price'], currency_of(country))}


def product_page(body: Mapping[str, Any], country: Country) -> Body:
    """`GET /products/{id}`: the product, its price in the country's currency."""
    return {
        **listed_page(body, country),
        'country': country,
        'currency': currency_of(country),
        'price_label': price_label(country),
    }


def import_vat(lines: list[Mapping[str, Any]]) -> Money | None:
    """The estimate of the destination's VAT on the goods, in NOK (ADR 0018).

    For each line, gross times the destination's rate on the day over 100, to the øre;
    summed. None when a line's rate is not known for the day: no estimate then, rather
    than half of one.
    """
    total = Money(Decimal('0.00'), 'NOK')
    for line in lines:
        if line['rate'] is None:
            return None
        gross = _money(line['gross'])
        total += Money(gross.amount * Decimal(line['rate']) / 100, 'NOK').to_ore()
    return total


def quote_page(body: Mapping[str, Any]) -> Body:
    """`POST /quote`: every amount also in the buyer's currency, and the VAT display.

    Each amount is converted on its own, so the shown lines may differ from the shown
    total by a cent; the NOK amounts add up exactly.
    """
    country: Country = body['country']
    currency = currency_of(country)
    due = due_on_delivery(country)
    estimate = import_vat(body['lines']) if due == 'import_vat_estimate' else None
    return {
        **body,
        'currency': currency,
        'lines': [
            {
                **line,
                'display_unit_price': _shown(line['unit_price'], currency),
                'display_gross': _shown(line['gross'], currency),
            }
            for line in body['lines']
        ],
        'display_gross': _shown(body['gross'], currency),
        'vat_display': {
            'price_label': price_label(country),
            'due_on_delivery': due,
            'norwegian_vat': body['vat'] if country == 'NO' else None,
            'import_vat': None if estimate is None else _plain(estimate),
            'display_import_vat': (
                None if estimate is None else _plain(display(estimate, currency))
            ),
        },
    }


def order_page(body: Mapping[str, Any]) -> Body:
    """`GET /orders/{token}`: the order, its amounts also in the buyer's currency."""
    currency = currency_of(body['country'])
    return {
        **body,
        'currency': currency,
        'lines': [
            {**line, 'display_unit_price': _shown(line['unit_price'], currency)}
            for line in body['lines']
        ],
        'display_total': _shown(body['total'], currency),
    }


def placed_page(body: Mapping[str, Any]) -> Body:
    """`POST /checkout`'s 201: the total also in the buyer's currency."""
    currency = currency_of(body['country'])
    return {**body, 'currency': currency, 'display_total': _shown(body['total'], currency)}
