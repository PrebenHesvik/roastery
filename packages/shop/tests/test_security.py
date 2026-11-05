"""What the security review before 6.5 found: each closed here."""

from __future__ import annotations

import dataclasses
import datetime as dt

import pytest

from roastery.customer import Customer
from roastery.ids import CustomerId
from roastery.settings import Secret, Settings

ENV = {
    'ROASTERY_DATABASE_URL': 'sqlite://shop.db',
    'ROASTERY_PROVIDER_URL': 'https://provider.invalid',
    'ROASTERY_PROVIDER_KEY': 'k-123-not-shown',
}


def test_the_key_is_never_printed_and_reveal_gives_it() -> None:
    settings = Settings.from_env(ENV)
    key = settings.provider_key
    shown = [
        str(key),
        repr(key),
        f'{key}',
        repr(settings),
        str(dataclasses.asdict(settings)),
    ]
    assert not any('k-123-not-shown' in text for text in shown)
    assert key.reveal() == 'k-123-not-shown'
    assert key == Secret('k-123-not-shown')


@pytest.mark.parametrize(
    'name', ['=HYPERLINK("x")', '+1', '-2', '@SUM(A1)', 'Ann\tLee']
)
def test_a_name_that_starts_a_formula_is_refused(name: str) -> None:
    with pytest.raises(ValueError, match='formula'):
        Customer(
            CustomerId('C-99'),
            name,
            None,
            None,
            None,
            'consumer',
            dt.date(2026, 1, 1),
        )
