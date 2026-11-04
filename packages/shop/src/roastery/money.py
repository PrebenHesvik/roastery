"""Money on Decimal, and a whole quantity.

Money never converts between currencies: that needs a rate, which
is an outside feed. Rounding to the øre happens in one place,
`Money.to_ore`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Final, Self

ORE: Final = Decimal('0.01')
"""One øre: the step amounts are rounded to."""


@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str  # three capitals: NOK, SEK, DKK, EUR

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            raise TypeError(
                f'amount must be a Decimal, not {self.amount!r}'
            )
        if not self.amount.is_finite():
            raise ValueError(f'amount must be finite: {self.amount}')
        if not isinstance(self.currency, str):
            raise TypeError('currency must be text')
        if re.fullmatch('[A-Z]{3}', self.currency) is None:
            raise ValueError(
                f'currency must be three capitals: {self.currency!r}'
            )

    @classmethod
    def of(cls, amount: str | int, currency: str) -> Self:
        """Money from text or a whole number, never a float."""
        if isinstance(amount, bool) or not isinstance(
            amount, (str, int)
        ):
            raise TypeError(
                f'amount must be text or int, not {amount!r}'
            )
        return cls(Decimal(amount), currency)

    def __add__(self, other: object) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        if other.currency != self.currency:
            raise ValueError(
                f'cannot add {other.currency} to {self.currency}'
            )
        return Money(self.amount + other.amount, self.currency)

    def __neg__(self) -> Money:
        return Money(-self.amount, self.currency)

    def times(self, qty: Qty) -> Money:
        return Money(self.amount * qty.value, self.currency)

    def to_ore(self) -> Money:
        """Round to two decimals, half away from zero.

        The one place the shop rounds. `.005` goes up, and `-.005`
        goes down to its mirror, which a credit line needs.
        """
        step = self.amount.quantize(ORE, rounding=ROUND_HALF_UP)
        return Money(step, self.currency)


def two_places(amount: Decimal, what: str) -> Decimal:
    """`amount`, if it has two decimals or fewer; else ValueError.

    A stored amount is DECIMAL(7,2): a third place is refused
    where it enters, never rounded away later (ADR 0004).
    """
    exponent = amount.as_tuple().exponent
    if not isinstance(exponent, int) or exponent < -2:
        raise ValueError(f'{what} has more than two places: {amount}')
    return amount


def in_nok(money: Money, what: str) -> Money:
    """`money`, if it is NOK in øre; else ValueError.

    The shop's own amounts (prices, costs, green coffee) are NOK.
    """
    if money.currency != 'NOK':
        raise ValueError(f'{what} must be NOK, not {money.currency}')
    two_places(money.amount, what)
    return money


@dataclass(frozen=True)
class Qty:
    """A whole number other than zero.

    A negative number is legal for the type; the order line's
    `credit` is the one way to make it (ADR 0004).
    """

    value: int

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(
            self.value, int
        ):
            raise TypeError('qty must be a whole number')
        if self.value == 0:
            raise ValueError('qty must not be zero')
