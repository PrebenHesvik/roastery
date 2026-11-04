"""The id value types: one class per kind, each checking its shape.

An id is `PREFIX-digits`. A class holds the text and refuses a
prefix that is not its own, so an order id cannot stand where a
customer id belongs. The width is not checked: the script's ids
(O-101) and the background trade's (O-000001) differ in it
(ADR 0007).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import ClassVar, Final, Literal

Country = Literal['DK', 'FI', 'NO', 'SE']
"""The four countries the shop sells to."""

COUNTRIES: Final[tuple[Country, ...]] = ('DK', 'FI', 'NO', 'SE')
"""The values of Country, sorted, for a check at run time."""

AccountKind = Literal['consumer', 'business']
"""How a customer buys; `account_kind` holds it as text."""

PREFIXES: Final[Mapping[str, str]] = MappingProxyType(
    {
        'bag': 'SB',
        'campaign': 'K',
        'category': 'CAT',
        'customer': 'C',
        'event': 'E',
        'line': 'L',
        'movement': 'M',
        'order': 'O',
        'payment': 'PAY',
        'product': 'P',
        'purchase': 'GP',
        'rule': 'PR',
        'shipment': 'SH',
        'sub_event': 'SE',
        'subscription': 'S',
    }
)
"""The prefix of each kind of id, by kind (ADR 0007).

The kinds are those of `IdKind`, and `payment`, the provider's.
"""


def _check_id(value: object, prefix: str, label: str) -> None:
    """Raise unless `value` is text shaped `prefix-digits`."""
    if not isinstance(value, str):
        raise TypeError(f'{label} must be text, not {value!r}')
    if re.fullmatch(f'{prefix}-[0-9]+', value) is None:
        raise ValueError(
            f'{label} must look like {prefix}-1: {value!r}'
        )


@dataclass(frozen=True)
class _Id:
    """What every id type shares: the text, checked at build."""

    value: str
    PREFIX: ClassVar[str]
    LABEL: ClassVar[str]

    def __post_init__(self) -> None:
        _check_id(self.value, self.PREFIX, self.LABEL)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class CustomerId(_Id):
    PREFIX = PREFIXES['customer']
    LABEL = 'customer id'


@dataclass(frozen=True)
class OrderId(_Id):
    PREFIX = PREFIXES['order']
    LABEL = 'order id'


@dataclass(frozen=True)
class LineId(_Id):
    PREFIX = PREFIXES['line']
    LABEL = 'line id'


@dataclass(frozen=True)
class EventId(_Id):
    PREFIX = PREFIXES['event']
    LABEL = 'event id'


@dataclass(frozen=True)
class ProductId(_Id):
    PREFIX = PREFIXES['product']
    LABEL = 'product id'


@dataclass(frozen=True)
class CategoryId(_Id):
    PREFIX = PREFIXES['category']
    LABEL = 'category id'


@dataclass(frozen=True)
class CampaignId(_Id):
    PREFIX = PREFIXES['campaign']
    LABEL = 'campaign id'


@dataclass(frozen=True)
class SubscriptionId(_Id):
    PREFIX = PREFIXES['subscription']
    LABEL = 'subscription id'


@dataclass(frozen=True)
class SubEventId(_Id):
    PREFIX = PREFIXES['sub_event']
    LABEL = 'subscription event id'


@dataclass(frozen=True)
class ShipmentId(_Id):
    PREFIX = PREFIXES['shipment']
    LABEL = 'shipment id'


@dataclass(frozen=True)
class BagId(_Id):
    PREFIX = PREFIXES['bag']
    LABEL = 'bag id'


@dataclass(frozen=True)
class MovementId(_Id):
    PREFIX = PREFIXES['movement']
    LABEL = 'movement id'


@dataclass(frozen=True)
class PurchaseId(_Id):
    PREFIX = PREFIXES['purchase']
    LABEL = 'purchase id'


@dataclass(frozen=True)
class RuleId(_Id):
    PREFIX = PREFIXES['rule']
    LABEL = 'pricing rule id'


@dataclass(frozen=True)
class PaymentId(_Id):
    """The provider's id for a payment (PAY-1)."""

    PREFIX = PREFIXES['payment']
    LABEL = 'payment id'


@dataclass(frozen=True)
class PostalCode:
    """Digits kept as text: 0150 keeps its zero."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise TypeError('postal code must be text')
        if not (self.value.isascii() and self.value.isdigit()):
            raise ValueError(
                f'postal code must be digits: {self.value!r}'
            )

    def __str__(self) -> str:
        return self.value
