"""The customer as the app holds it, and its change log's row."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Final, Literal

from roastery.ids import (
    COUNTRIES,
    AccountKind,
    Country,
    CustomerId,
    PostalCode,
)

DOMAIN: Final = 'example.invalid'
"""The one domain an address may have: none can reach an inbox."""

ACCOUNT_KINDS: Final[tuple[AccountKind, ...]] = (
    'business',
    'consumer',
)

Op = Literal['insert', 'update', 'delete']
"""What a log row says was done, as `customer_changes.op` holds it."""

OPS: Final[tuple[Op, ...]] = ('delete', 'insert', 'update')


@dataclass(frozen=True)
class Email:
    """An address at example.invalid (C25)."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise TypeError('e-mail must be text')
        name, at, domain = self.value.partition('@')
        if not name or not at or domain != DOMAIN:
            raise ValueError(
                f'e-mail must look like name@{DOMAIN}: {self.value!r}'
            )
        if any(char.isspace() for char in name) or '@' in domain:
            raise ValueError(
                f'e-mail has a stray character: {self.value!r}'
            )

    def __str__(self) -> str:
        return self.value


def _check_country(country: object) -> None:
    if country is not None and country not in COUNTRIES:
        raise ValueError(f'country must be one of {COUNTRIES}')


@dataclass(frozen=True)
class Customer:
    customer_id: CustomerId
    name: str
    email: Email | None  # C-05 has none (C37)
    country: Country | None
    postal_code: PostalCode | None
    account_kind: AccountKind
    joined: dt.date

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError('name must be text that is not blank')
        _check_country(self.country)
        if self.account_kind not in ACCOUNT_KINDS:
            raise ValueError(
                f'account kind must be one of {ACCOUNT_KINDS}'
            )


@dataclass(frozen=True)
class CustomerChange:
    """One row of the change log (ADR 0003).

    The country and postal code are those after the change; a
    delete is a tombstone that carries the key only.
    """

    seq: int
    op: Op
    customer_id: CustomerId
    country: Country | None
    postal_code: PostalCode | None
    changed_at: dt.datetime

    def __post_init__(self) -> None:
        if self.op not in OPS:
            raise ValueError(f'op must be one of {OPS}')
        _check_country(self.country)
        if self.op == 'delete' and (
            self.country is not None or self.postal_code is not None
        ):
            raise ValueError('a delete carries the key only')
