"""The money rules a quiet mistake would break."""

from __future__ import annotations

from decimal import Decimal

import pytest

from roastery.money import Money, Qty


def test_money_of_two_currencies_does_not_add() -> None:
    nok = Money.of('548.00', 'NOK')
    sek = Money.of('516.98', 'SEK')  # PAY-2
    with pytest.raises(ValueError):
        nok + sek


def test_to_ore_rounds_half_up() -> None:
    assert Money.of('1.005', 'NOK').to_ore().amount == Decimal('1.01')
    assert Money.of('1.004', 'NOK').to_ore().amount == Decimal('1.00')


def test_to_ore_rounds_a_negative_to_the_mirror() -> None:
    assert Money.of('-1.005', 'NOK').to_ore().amount == Decimal('-1.01')


def test_qty_refuses_zero() -> None:
    with pytest.raises(ValueError):
        Qty(0)
