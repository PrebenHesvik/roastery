"""The API's parts on their own: the rates, the clock, the settings, the seed, the orphans."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from roastery.checkout import Checkout
from roastery.errors import OutOfStock
from roastery.fakes import FakeClock
from roastery.ids import ProductId
from roastery.money import Money
from roastery.settings import SettingsError
from roastery_api import fx
from roastery_api.__main__ import main
from roastery_api.clock import RequestClock
from roastery_api.live import Live, open_live
from roastery_api.settings import ApiSettings
from roastery_api.state import CountedIds, State, connect
from roastery_sim import script
from roastery_sim.outside import FxRate

# The rates (ADR 0018) -------------------------------------------------------------------


def test_the_rates_are_the_scripts_latest_of_each_currency() -> None:
    latest: dict[str, FxRate] = {}
    for rate in script.FX:
        if rate.currency not in latest or rate.rate_date > latest[rate.currency].rate_date:
            latest[rate.currency] = rate
    copied = {
        currency: (rate.rate_date, rate.nok_per_unit)
        for currency, rate in fx.RATES.items()
        if currency != 'NOK'
    }
    assert copied == {
        currency: (rate.rate_date, rate.nok_per_unit) for currency, rate in latest.items()
    }


@pytest.mark.parametrize(
    ('currency', 'shown'),
    [('NOK', '129.00'), ('SEK', '121.47'), ('DKK', '82.80'), ('EUR', '11.09')],
)
def test_p10_is_shown_as_adr_0018_says(currency: fx.Currency, shown: str) -> None:
    assert fx.display(Money(Decimal('129.00'), 'NOK'), currency) == Money(Decimal(shown), currency)


def test_display_rounds_half_up() -> None:
    # 0.00531 NOK is exactly SEK 0.005: half up gives 0.01, banker's 0.00
    assert fx.display(Money(Decimal('0.00531'), 'NOK'), 'SEK').amount == Decimal('0.01')
    assert fx.display(Money(Decimal('0.0159'), 'NOK'), 'SEK').amount == Decimal('0.01')


def test_display_converts_nok_only() -> None:
    with pytest.raises(ValueError, match='only NOK'):
        fx.display(Money(Decimal('1.00'), 'SEK'), 'EUR')


def test_the_import_estimate_needs_every_rate() -> None:
    line = {'gross': {'amount': '899.00', 'currency': 'NOK'}, 'rate': '25.5'}
    assert fx.import_vat([line]) == Money(Decimal('229.25'), 'NOK')
    assert fx.import_vat([line, {**line, 'rate': None}]) is None


# The clock (F8) -------------------------------------------------------------------------


def test_the_request_clock_reads_the_wall_once_per_request() -> None:
    wall = FakeClock(dt.datetime(2026, 11, 15, 22, 59, 59, tzinfo=dt.UTC))
    clock = RequestClock(wall)
    with clock.held() as moment:
        wall.advance(dt.timedelta(seconds=2))  # past midnight in Oslo
        assert clock.now() == moment
    assert clock.now() == wall.now()
    with clock.held(), pytest.raises(RuntimeError), clock.held():
        pass


# Settings -------------------------------------------------------------------------------


def test_the_api_settings_list_every_problem() -> None:
    with pytest.raises(SettingsError) as raised:
        ApiSettings.from_env({'SHOP_API_ORIGINS': 'x', 'SHOP_API_CORS_ORIGINS': '*'})
    assert raised.value.problems == (
        'SHOP_API_STATE_URL is missing',
        'SHOP_API_CORS_ORIGINS takes no wildcard',
        'SHOP_API_ORIGINS is not a setting',
    )


def test_the_origins_are_a_comma_list() -> None:
    settings = ApiSettings.from_env(
        {'SHOP_API_STATE_URL': 'sqlite:///x.db', 'SHOP_API_CORS_ORIGINS': 'http://a, http://b'}
    )
    assert settings.cors_origins == ('http://a', 'http://b')


def test_open_live_lists_the_shops_problems_and_the_apis() -> None:
    with pytest.raises(SettingsError) as raised:
        open_live({'ROASTERY_TYPO': '1'})
    assert raised.value.problems == (
        'ROASTERY_DATABASE_URL is missing',
        'ROASTERY_TYPO is not a setting',
        'SHOP_API_STATE_URL is missing',
    )


# The seed -------------------------------------------------------------------------------


def test_the_seed_command_runs_once(
    fresh_env: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(['seed'], fresh_env) == 0
    assert main(['seed'], fresh_env) == 0
    assert capsys.readouterr().out.splitlines() == [
        'seeded the catalogue',
        'the catalogue is not empty: nothing seeded',
    ]


def test_the_seed_draws_its_movements_from_the_counter(env: dict[str, str]) -> None:
    state = connect(env['SHOP_API_STATE_URL'])
    try:
        assert (
            CountedIds(State(state)).next('movement') == 'M-0000005'
        )  # two roasts, two stocktakes
    finally:
        state.close()


def test_the_seeded_catalogue_is_the_scripts(client: TestClient) -> None:
    products = client.get('/products').json()['products']
    assert [each['product']['name'] for each in products] == [
        'Morning roast',
        'Dark espresso',
        'Decaf',
        'Hand grinder',
        'Pour-over kettle',
    ]
    assert {each['product']['product_id']: each['in_stock'] for each in products} == {
        'P-10': True,
        'P-11': True,
        'P-12': False,
        'P-20': True,
        'P-21': True,
    }


# Orphans (F2) ---------------------------------------------------------------------------


def test_a_refused_place_after_register_leaves_a_logged_orphan(
    client: TestClient, live: Live, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(self: Checkout, order: object) -> object:
        raise OutOfStock(ProductId('P-10'), 2, 1)

    monkeypatch.setattr(Checkout, 'place', refuse)
    body = {
        'country': 'NO',
        'items': [{'product_id': 'P-10', 'qty': 2}],
        'total': {'amount': '258.00', 'currency': 'NOK'},
        'name': 'Ola',
        'email': 'ola@example.com',
        'street': 'Torget 1',
        'postal_code': '5014',
        'city': 'Bergen',
    }
    reply = client.post('/checkout', json=body, headers={'Idempotency-Key': 'orphan-1'})
    assert reply.status_code == 409
    assert reply.json()['code'] == 'OutOfStock'
    ((customer_id, reason),) = live.state.orphans()
    assert customer_id == 'C-00001'
    assert 'OutOfStock' in reason


def test_the_sandbox_setting_is_off_unless_one() -> None:
    base = {'SHOP_API_STATE_URL': 'sqlite:///x.db'}
    assert not ApiSettings.from_env(base).sandbox
    assert ApiSettings.from_env({**base, 'SHOP_API_SANDBOX': '1'}).sandbox
    with pytest.raises(SettingsError) as raised:
        ApiSettings.from_env({**base, 'SHOP_API_SANDBOX': 'yes'})
    assert raised.value.problems == ('SHOP_API_SANDBOX must be 0 or 1',)
