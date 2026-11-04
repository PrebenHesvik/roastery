"""VAT: a share of the one gross price, on the rate of its day.

Every buyer pays the same gross price; VAT is the part of it the
shop owes (ADR 0010). A Norwegian sale is `domestic`, at Norway's
rate for the product's kind on the order's day. A foreign sale is
an `export` at 0 %. The rates are dated rows, never constants, and
the lookup is strict: it has no default country. Which country an
order is taxed in is the caller's choice (`checkout.order_country`).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Final, Literal

from roastery.catalogue import KINDS, Kind
from roastery.ids import COUNTRIES, Country
from roastery.money import Money
from roastery.order import Order

Scheme = Literal['domestic', 'export']
"""How a sale is taxed: Norway's VAT, or an export at 0 %."""

SCHEMES: Final[tuple[Scheme, ...]] = ('domestic', 'export')

TaxKind = Literal['food', 'standard']
"""The tax's kind, as `vat_rates.kind` holds it."""

TAX_KINDS: Final[tuple[TaxKind, ...]] = ('food', 'standard')

TAX_KIND: Final[Mapping[Kind, TaxKind]] = MappingProxyType(
    {'beans': 'food', 'equipment': 'standard'}
)
"""The tax's kind of each product kind (`vat.md`: roasted coffee
is food; equipment is at the standard rate)."""


def scheme_for(order: Order, on: dt.date) -> Scheme:
    """How this order is taxed on this day (C22).

    Every foreign order of the simulated years is an export. Phase
    8's IOSS change edits this body only; the callers stay.
    """
    return 'domestic' if order.head.country == 'NO' else 'export'


@dataclass(frozen=True)
class VatRate:
    """A row of `vat_rates`: a rate in per cent, on its days.

    `start_assumed`: `vat.md` does not say when the rate began, so
    `valid_from` is the first day the shop trades (ADR 0010).
    """

    country: Country
    kind: TaxKind
    rate: Decimal
    valid_from: dt.date
    valid_to: dt.date | None  # the first day it no longer holds
    start_assumed: bool = False

    def __post_init__(self) -> None:
        if self.country not in COUNTRIES:
            raise ValueError(f'country must be one of {COUNTRIES}')
        if self.kind not in TAX_KINDS:
            raise ValueError(f'kind must be one of {TAX_KINDS}')
        if not isinstance(self.rate, Decimal) or self.rate < 0:
            raise ValueError('rate must be a Decimal of 0 or more')
        if self.valid_to is not None and (
            self.valid_to <= self.valid_from
        ):
            raise ValueError('a period must end after it starts')

    def covers(self, on: dt.date) -> bool:
        """Is `on` in the half-open period: from, up to but not to."""
        return self.valid_from <= on and (
            self.valid_to is None or on < self.valid_to
        )


FIRST_DAY: Final = '2024-01-01'
"""The first day of `prices`, the earliest the shop trades: the
start of a rate `vat.md` does not date (its open point 3)."""


def _seed(
    country: Country,
    kind: TaxKind,
    rate: str,
    valid_from: str | None,
    valid_to: str | None,
) -> VatRate:
    """A seed row from the table's text; a start of None is one
    `vat.md` does not date, given FIRST_DAY and marked."""
    return VatRate(
        country,
        kind,
        Decimal(rate),
        dt.date.fromisoformat(valid_from or FIRST_DAY),
        None if valid_to is None else dt.date.fromisoformat(valid_to),
        start_assumed=valid_from is None,
    )


SEED_RATES: Final[tuple[VatRate, ...]] = (
    _seed('DK', 'food', '25', None, None),  # DK-rate
    _seed('DK', 'standard', '25', None, None),  # DK-rate
    _seed('FI', 'food', '14', None, '2026-01-01'),  # FI-rates
    _seed('FI', 'food', '13.5', '2026-01-01', None),  # FI-changes
    _seed('FI', 'standard', '24', None, '2024-09-01'),  # FI-changes
    _seed('FI', 'standard', '25.5', '2024-09-01', None),  # FI-changes
    _seed('NO', 'food', '15', '2012-01-01', None),  # NO-hb5
    _seed('NO', 'standard', '25', None, None),  # NO-rates
    _seed('SE', 'food', '12', None, '2026-04-01'),  # SE-rates
    _seed('SE', 'food', '6', '2026-04-01', '2028-01-01'),  # SE-news
    _seed('SE', 'standard', '25', None, None),  # SE-rates
)
"""ADR 0010's seed table, copied from `docs/facts/vat.md`, with its
source keys; sorted by country, kind and first day."""


class VatRates:
    """The dated rows, read from the store once per command."""

    def __init__(self, rows: Iterable[VatRate]) -> None:
        ordered = sorted(
            rows,
            key=lambda row: (row.country, row.kind, row.valid_from),
        )
        for before, after in zip(ordered, ordered[1:], strict=False):
            same = (before.country, before.kind) == (
                after.country,
                after.kind,
            )
            if same and (
                before.valid_to is None
                or before.valid_to > after.valid_from
            ):
                raise ValueError(
                    f'{after.country} {after.kind}: two rates on '
                    f'{after.valid_from}'
                )
        self._rows = tuple(ordered)

    def rate_on(
        self, country: Country, kind: Kind, on: dt.date
    ) -> Decimal:
        """The rate in per cent for a product kind on a day.

        Strict: no default country, no default kind, and a day no
        row covers raises LookupError.
        """
        if country is None:
            raise TypeError('country is None: the caller decides it')
        if country not in COUNTRIES:
            raise ValueError(f'country must be one of {COUNTRIES}')
        if kind not in KINDS:
            raise ValueError(f'kind must be one of {KINDS}')
        tax_kind = TAX_KIND[kind]
        for row in self._rows:
            if (row.country, row.kind) == (country, tax_kind) and (
                row.covers(on)
            ):
                return row.rate
        raise LookupError(f'no {country} {tax_kind} rate on {on}')


def vat_of(gross: Money, rate: Decimal, scheme: Scheme) -> Money:
    """The VAT share of a gross price, to the øre (A12).

    An export owes none: zero in the gross's currency. A domestic
    sale owes `gross * rate / (100 + rate)`; a negative gross (a
    credit line) gives a negative share.
    """
    match scheme:
        case 'export':
            return Money(Decimal('0.00'), gross.currency)
        case 'domestic':
            share = gross.amount * rate / (100 + rate)
            return Money(share, gross.currency).to_ore()
        case _:
            raise ValueError(f'scheme must be one of {SCHEMES}')
