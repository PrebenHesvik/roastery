"""The API end to end through HTTP, on a fresh seeded sqlite pair (7.2's done-when)."""

from __future__ import annotations

import hashlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from roastery.fakes import FakeClock
from roastery_api.__main__ import seed
from roastery_api.app import _FromEnv, create_app
from roastery_api.live import Live, open_live

P10_TWICE = [{'product_id': 'P-10', 'qty': 2}]


def contact(country: str = 'NO', postal_code: str = '5003') -> dict[str, str]:
    return {
        'country': country,
        'name': 'Kari Nordmann',
        'email': 'kari@example.com',
        'street': 'Strandkaien 2',
        'postal_code': postal_code,
        'city': 'Bergen',
    }


def quote(client: TestClient, country: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    reply = client.post('/quote', json={'country': country, 'items': items})
    assert reply.status_code == 200, reply.text
    return reply.json()


def checkout(
    client: TestClient,
    key: str,
    items: list[dict[str, Any]] = P10_TWICE,
    country: str = 'NO',
    total: dict[str, str] | None = None,
) -> Any:
    if total is None:
        total = quote(client, country, items)['gross']
    body = {**contact(country), 'items': items, 'total': total}
    return client.post('/checkout', json=body, headers={'Idempotency-Key': key})


def pay(client: TestClient, token: str, outcome: str, key: str) -> Any:
    return client.post(
        '/sandbox/payments',
        json={'token': token, 'outcome': outcome},
        headers={'Idempotency-Key': key},
    )


# The walk -------------------------------------------------------------------------------


def test_seed_quote_checkout_approve_and_the_order_reads_paid(client: TestClient) -> None:
    listing = client.get('/products', params={'country': 'NO'})
    assert listing.status_code == 200
    products = {each['product']['product_id']: each for each in listing.json()['products']}
    assert sorted(products) == ['P-10', 'P-11', 'P-12', 'P-20', 'P-21']
    assert products['P-10']['unit_price'] == {'amount': '129.00', 'currency': 'NOK'}
    assert products['P-12']['unit_price'] is None  # coming soon (F6)

    quoted = quote(client, 'NO', P10_TWICE)
    assert quoted['gross'] == {'amount': '258.00', 'currency': 'NOK'}
    assert quoted['vat_display']['price_label'] == 'incl_vat'

    placed = checkout(client, 'walk-1')
    assert placed.status_code == 201, placed.text
    token = placed.json()['token']
    assert len(token) == 32

    paid = pay(client, token, 'approve', 'pay-1')
    assert paid.status_code == 201, paid.text
    assert paid.json()['status'] == 'paid'
    assert paid.json()['amount'] == {'amount': '258.00', 'currency': 'NOK'}
    assert paid.json()['payment_id'] == 'PAY-1'

    order = client.get(f'/orders/{token}')
    assert order.status_code == 200
    assert order.json()['status'] == 'paid'
    assert order.json()['total'] == {'amount': '258.00', 'currency': 'NOK'}
    assert 'customer_id' not in order.json()


def test_the_guest_is_a_pseudonym_in_the_shop_and_real_in_the_state_db(
    client: TestClient, live: Live, env: dict[str, str]
) -> None:
    placed = checkout(client, 'guest-1').json()
    assert 'customer_id' not in placed
    shop = sqlite3.connect(env['ROASTERY_DATABASE_URL'].removeprefix('sqlite:///'))
    try:
        customer_id, name, email = shop.execute(
            'SELECT c.customer_id, c.name, c.email FROM customers c'
            ' JOIN orders o ON o.customer_id = c.customer_id WHERE o.order_id = ?',
            (placed['order_id'],),
        ).fetchone()
    finally:
        shop.close()
    assert name == 'Guest 1'
    assert email == 'guest-1@example.invalid'
    kept = live.state.guest(customer_id)
    assert kept is not None
    assert kept['email'] == 'kari@example.com'
    assert kept['street'] == 'Strandkaien 2'


# The sandbox ----------------------------------------------------------------------------


def test_decline_is_402_and_is_kept_and_the_order_stays_placed(client: TestClient) -> None:
    token = checkout(client, 'decline-1').json()['token']
    first = pay(client, token, 'decline', 'pay-d')
    assert first.status_code == 402
    assert first.headers['content-type'] == 'application/problem+json'
    assert first.json()['code'] == 'ProviderRefused'
    assert pay(client, token, 'decline', 'pay-d').json() == first.json()
    assert client.get(f'/orders/{token}').json()['status'] == 'placed'
    assert pay(client, token, 'approve', 'pay-again').status_code == 201


def test_outage_is_503_and_not_kept_so_the_same_key_runs_again(client: TestClient) -> None:
    token = checkout(client, 'outage-1').json()['token']
    down = pay(client, token, 'outage', 'pay-o')
    assert down.status_code == 503
    assert down.json()['code'] == 'ProviderUnavailable'
    assert client.get(f'/orders/{token}').json()['status'] == 'placed'
    # not kept: the same key with another body is not KeyReused, it runs
    assert pay(client, token, 'approve', 'pay-o').status_code == 201


def test_paying_twice_gives_the_kept_reply_and_a_new_key_is_409(client: TestClient) -> None:
    token = checkout(client, 'twice-1').json()['token']
    first = pay(client, token, 'approve', 'pay-t')
    assert pay(client, token, 'approve', 'pay-t').json() == first.json()
    again = pay(client, token, 'approve', 'pay-t2')
    assert again.status_code == 409
    assert again.json()['code'] == 'IllegalTransition'


# Idempotency ----------------------------------------------------------------------------


def test_the_same_key_and_body_give_the_same_reply_and_one_order(
    client: TestClient, env: dict[str, str]
) -> None:
    first = checkout(client, 'same-1')
    second = checkout(client, 'same-1')
    assert first.status_code == second.status_code == 201
    replayed = second.json()
    token = replayed.pop('token')
    assert {**replayed, 'token': first.json()['token']} == first.json()
    # the replay's link works, and it is the order's one link now
    assert client.get(f'/orders/{token}').json()['order_id'] == first.json()['order_id']
    assert client.get(f'/orders/{first.json()["token"]}').status_code == 404
    shop = sqlite3.connect(env['ROASTERY_DATABASE_URL'].removeprefix('sqlite:///'))
    try:
        (orders,) = shop.execute('SELECT count(*) FROM orders').fetchone()
    finally:
        shop.close()
    assert orders == 1


def test_the_same_key_with_another_body_is_409_key_reused(client: TestClient) -> None:
    assert checkout(client, 'reused-1').status_code == 201
    other = checkout(client, 'reused-1', items=[{'product_id': 'P-20', 'qty': 1}])
    assert other.status_code == 409
    assert other.json()['code'] == 'KeyReused'


def test_a_post_without_a_key_is_400(client: TestClient) -> None:
    body = {**contact(), 'items': P10_TWICE, 'total': {'amount': '258.00', 'currency': 'NOK'}}
    reply = client.post('/checkout', json=body)
    assert reply.status_code == 400
    assert reply.json()['code'] == 'RequestValidationError'


# Refusals -------------------------------------------------------------------------------


def test_a_changed_total_is_409_with_the_new_quote_and_nothing_written(
    client: TestClient, live: Live
) -> None:
    stale = {'amount': '238.00', 'currency': 'NOK'}
    reply = checkout(client, 'stale-1', total=stale)
    assert reply.status_code == 409
    assert reply.json()['code'] == 'PriceChanged'
    assert reply.json()['quote']['gross'] == {'amount': '258.00', 'currency': 'NOK'}
    assert reply.json()['quote']['display_gross'] == {'amount': '258.00', 'currency': 'NOK'}
    assert live.state.orphans() == ()


def test_a_short_line_is_409_out_of_stock(client: TestClient) -> None:
    reply = checkout(client, 'short-1', items=[{'product_id': 'P-21', 'qty': 3}])
    assert reply.status_code == 409
    assert reply.json()['code'] == 'OutOfStock'


def test_a_client_price_is_never_read(client: TestClient) -> None:
    items = [{'product_id': 'P-10', 'qty': 1, 'unit_price': '1.00', 'price': '1.00'}]
    assert quote(client, 'NO', items)['gross']['amount'] == '129.00'


def test_unknowns(client: TestClient) -> None:
    token = client.get('/orders/not-a-token-anyone-was-given')
    assert token.status_code == 404
    assert token.json()['code'] == 'UnknownToken'
    assert pay(client, 'nope', 'approve', 'pay-u').json()['code'] == 'UnknownToken'
    product = client.get('/products/P-99')
    assert product.status_code == 404
    assert product.json()['code'] == 'UnknownId'
    unknown = client.post(
        '/quote', json={'country': 'NO', 'items': [{'product_id': 'P-99', 'qty': 1}]}
    )
    assert unknown.status_code == 422
    assert unknown.json()['code'] == 'UnknownProduct'
    coming = client.post(
        '/quote', json={'country': 'NO', 'items': [{'product_id': 'P-12', 'qty': 1}]}
    )
    assert coming.status_code == 422
    assert coming.json()['code'] == 'NoPrice'
    assert client.get('/nowhere').json()['code'] == 'NotFound'


def test_a_body_that_does_not_parse_is_400(client: TestClient) -> None:
    for body in ({'items': P10_TWICE}, {'country': 'US', 'items': P10_TWICE}, {'country': 'NO'}):
        reply = client.post('/quote', json=body)
        assert reply.status_code == 400
        assert reply.headers['content-type'] == 'application/problem+json'
        assert reply.json()['code'] == 'RequestValidationError'


# Money on the page ----------------------------------------------------------------------


def test_norway_shows_nok_incl_vat(client: TestClient) -> None:
    quoted = quote(client, 'NO', P10_TWICE)
    assert quoted['currency'] == 'NOK'
    assert quoted['scheme'] == 'domestic'
    assert quoted['vat_display'] == {
        'price_label': 'incl_vat',
        'due_on_delivery': 'nothing',
        'norwegian_vat': {'amount': '33.65', 'currency': 'NOK'},
        'import_vat': None,
        'display_import_vat': None,
    }


def test_sweden_shows_sek_no_norwegian_vat_and_an_import_estimate(client: TestClient) -> None:
    listing = client.get('/products', params={'country': 'SE'}).json()
    assert listing['currency'] == 'SEK'
    assert listing['price_label'] == 'no_norwegian_vat'
    p10 = next(p for p in listing['products'] if p['product']['product_id'] == 'P-10')
    assert p10['display_price'] == {'amount': '121.47', 'currency': 'SEK'}

    quoted = quote(client, 'SE', [{'product_id': 'P-10', 'qty': 1}])
    assert quoted['scheme'] == 'export'
    assert quoted['vat'] == {'amount': '0.00', 'currency': 'NOK'}
    assert quoted['display_gross'] == {'amount': '121.47', 'currency': 'SEK'}
    # 129.00 x 6 % = 7.74 NOK, shown once as SEK 7.29
    assert quoted['vat_display'] == {
        'price_label': 'no_norwegian_vat',
        'due_on_delivery': 'import_vat_estimate',
        'norwegian_vat': None,
        'import_vat': {'amount': '7.74', 'currency': 'NOK'},
        'display_import_vat': {'amount': '7.29', 'currency': 'SEK'},
    }


def test_denmark_shows_dkk_and_no_landed_amount(client: TestClient) -> None:
    quoted = quote(
        client, 'DK', [{'product_id': 'P-10', 'qty': 1}, {'product_id': 'P-20', 'qty': 1}]
    )
    assert quoted['currency'] == 'DKK'
    assert quoted['lines'][0]['display_unit_price'] == {'amount': '82.80', 'currency': 'DKK'}
    assert quoted['vat_display'] == {
        'price_label': 'no_norwegian_vat',
        'due_on_delivery': 'vat_excise_and_fees',
        'norwegian_vat': None,
        'import_vat': None,
        'display_import_vat': None,
    }


def test_finland_shows_eur_and_the_order_shows_both(client: TestClient) -> None:
    quoted = quote(client, 'FI', [{'product_id': 'P-10', 'qty': 1}])
    assert quoted['display_gross'] == {'amount': '11.09', 'currency': 'EUR'}
    assert quoted['vat_display']['due_on_delivery'] == 'import_vat_estimate'
    placed = checkout(client, 'fi-1', items=[{'product_id': 'P-10', 'qty': 1}], country='FI')
    assert placed.status_code == 201, placed.text
    assert placed.json()['display_total'] == {'amount': '11.09', 'currency': 'EUR'}
    order = client.get(f'/orders/{placed.json()["token"]}').json()
    assert order['total'] == {'amount': '129.00', 'currency': 'NOK'}
    assert order['display_total'] == {'amount': '11.09', 'currency': 'EUR'}


# Concurrency and restarts -----------------------------------------------------------------


def test_twenty_parallel_requests_are_all_answered(client: TestClient) -> None:
    def one(n: int) -> int:
        match n % 4:
            case 0:
                return checkout(
                    client, f'parallel-{n}', items=[{'product_id': 'P-10', 'qty': 1}]
                ).status_code
            case 1:
                return client.get('/products', params={'country': 'SE'}).status_code
            case 2:
                return client.post('/quote', json={'country': 'DK', 'items': P10_TWICE}).status_code
            case _:
                return client.get('/products/P-20').status_code

    with ThreadPoolExecutor(max_workers=20) as pool:
        statuses = list(pool.map(one, range(20)))
    assert statuses == [201 if n % 4 == 0 else 200 for n in range(20)]


def test_a_reopened_db_raises_no_duplicate_id_and_the_ids_go_on(
    fresh_env: dict[str, str], wall: FakeClock
) -> None:
    env = fresh_env
    assert seed(env)
    placed = []
    for run in range(2):
        live, _ = open_live(env, wall=wall)
        try:
            with TestClient(create_app(live, sandbox=True)) as client:
                reply = checkout(client, f'restart-{run}')
                assert reply.status_code == 201, reply.text
                placed.append(reply.json())
                paid = pay(client, reply.json()['token'], 'approve', f'pay-restart-{run}')
                assert paid.status_code == 201, paid.text
                placed[-1]['payment_id'] = paid.json()['payment_id']
        finally:
            live.close()
        assert not seed(env)  # a seeded db is left as it is
    assert [each['order_id'] for each in placed] == ['O-000001', 'O-000002']
    assert [each['payment_id'] for each in placed] == ['PAY-1', 'PAY-2']


# CORS -----------------------------------------------------------------------------------


def test_cors_allows_the_listed_origin_only(client: TestClient) -> None:
    asked = {
        'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'Idempotency-Key, Content-Type',
    }
    allowed = client.options('/checkout', headers={'Origin': 'http://localhost:5173', **asked})
    assert allowed.headers['access-control-allow-origin'] == 'http://localhost:5173'
    other = client.options('/checkout', headers={'Origin': 'https://elsewhere.example', **asked})
    assert 'access-control-allow-origin' not in other.headers


def test_the_openapi_document_names_every_route(client: TestClient) -> None:
    document = client.get('/openapi.json').json()
    assert sorted(document['paths']) == [
        '/checkout',
        '/orders/{token}',
        '/products',
        '/products/{product_id}',
        '/quote',
        '/sandbox/payments',
    ]
    assert 'HTTPValidationError' not in document['components']['schemas']


def test_the_server_entry_wires_itself_from_the_environment(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    with TestClient(_FromEnv()) as http:
        assert http.get('/products').status_code == 200


# Gate, limits, hashed tokens, orphans -----------------------------------------------------


def test_the_sandbox_route_does_not_exist_without_the_setting(live: Live) -> None:
    with TestClient(create_app(live)) as off:
        reply = off.post(
            '/sandbox/payments',
            json={'token': 'x', 'outcome': 'approve'},
            headers={'Idempotency-Key': 'k'},
        )
        assert reply.status_code == 404
        assert '/sandbox/payments' not in off.get('/openapi.json').json()['paths']


def test_the_server_entry_mounts_the_sandbox_only_on_one(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    asked = {'json': {'token': 'x', 'outcome': 'approve'}, 'headers': {'Idempotency-Key': 'k'}}
    with TestClient(_FromEnv()) as off:
        assert off.post('/sandbox/payments', **asked).status_code == 404
    monkeypatch.setenv('SHOP_API_SANDBOX', '1')
    with TestClient(_FromEnv()) as on:
        assert on.post('/sandbox/payments', **asked).status_code == 404  # UnknownToken
        assert on.post('/sandbox/payments', **asked).json()['code'] == 'UnknownToken'


def test_the_limits_refuse_long_carts_big_quantities_and_long_text(client: TestClient) -> None:
    many = [{'product_id': 'P-10', 'qty': 1}] * 51
    assert client.post('/quote', json={'country': 'NO', 'items': many}).status_code == 400
    big = [{'product_id': 'P-10', 'qty': 1000}]
    assert client.post('/quote', json={'country': 'NO', 'items': big}).status_code == 400
    fifty = [{'product_id': 'P-10', 'qty': 999}] * 50
    assert client.post('/quote', json={'country': 'NO', 'items': fifty}).status_code in (200, 422)
    total = quote(client, 'NO', P10_TWICE)['gross']
    body = {**contact(), 'items': P10_TWICE, 'total': total, 'city': 'B' * 101}
    reply = client.post('/checkout', json=body, headers={'Idempotency-Key': 'long'})
    assert reply.status_code == 400


def test_a_body_over_64_kib_is_a_413_problem_before_parsing(client: TestClient) -> None:
    padding = 'x' * (64 * 1024)
    reply = client.post('/quote', json={'country': 'NO', 'items': P10_TWICE, 'padding': padding})
    assert reply.status_code == 413
    assert reply.headers['content-type'] == 'application/problem+json'
    assert reply.json()['code'] == 'ContentTooLarge'

    def chunks() -> Any:
        yield b'{"country":"NO","items":['
        yield b' ' * (64 * 1024)
        yield b']}'

    streamed = client.post('/quote', content=chunks())
    assert streamed.status_code == 413


def test_the_state_db_keeps_only_the_hash_of_a_token(
    client: TestClient, env: dict[str, str]
) -> None:
    token = checkout(client, 'hash-1').json()['token']
    state = sqlite3.connect(env['SHOP_API_STATE_URL'].removeprefix('sqlite:///'))
    try:
        (stored,) = state.execute('SELECT token_hash FROM order_links').fetchone()
    finally:
        state.close()
    assert stored == hashlib.sha256(token.encode()).hexdigest()
    assert token not in stored
    assert client.get(f'/orders/{token}').status_code == 200
    assert client.get(f'/orders/{stored}').status_code == 404


def test_a_failed_state_write_after_the_commit_is_an_orphan_and_the_retry_places_no_order(
    client: TestClient, live: Live, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = live.state.add_guest
    calls: list[int] = []

    def flaky(*args: Any, **kwargs: Any) -> None:
        calls.append(1)
        if len(calls) == 1:
            raise sqlite3.OperationalError('disk I/O error')
        real(*args, **kwargs)

    monkeypatch.setattr(live.state, 'add_guest', flaky)
    first = checkout(client, 'orphan-1')
    assert first.status_code == 500
    assert first.json()['code'] == 'InternalError'
    orphans = live.state.orphans()
    assert len(orphans) == 1
    assert 'O-000001' in orphans[0][1]

    retry = checkout(client, 'orphan-1')
    assert retry.status_code == 500
    assert retry.json() == first.json()
    assert len(calls) == 1  # the retry did not place again

    later = checkout(client, 'orphan-2')
    assert later.status_code == 201
    assert later.json()['order_id'] == 'O-000002'


def test_a_failed_link_after_the_commit_is_linked_on_retry_and_places_no_order(
    client: TestClient, live: Live, env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    real = live.state.link
    calls: list[int] = []

    def flaky(order_id: Any, at: Any) -> str:
        calls.append(1)
        if len(calls) == 1:
            raise sqlite3.OperationalError('disk I/O error')
        return real(order_id, at)

    monkeypatch.setattr(live.state, 'link', flaky)
    first = checkout(client, 'link-1')
    assert first.status_code == 500
    assert first.json()['code'] == 'InternalError'

    retry = checkout(client, 'link-1')
    assert retry.status_code == 201
    assert retry.json()['order_id'] == 'O-000001'
    assert client.get(f'/orders/{retry.json()["token"]}').status_code == 200
    assert live.state.orphans() == ()
    shop = sqlite3.connect(env['ROASTERY_DATABASE_URL'].removeprefix('sqlite:///'))
    try:
        (orders,) = shop.execute('SELECT count(*) FROM orders').fetchone()
    finally:
        shop.close()
    assert orders == 1


def every_cell(url: str) -> list[str]:
    """Every value in every table of the sqlite db at `url`, as text."""
    db = sqlite3.connect(url.removeprefix('sqlite:///'))
    try:
        tables = db.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        return [
            str(cell)
            for (table,) in tables
            for row in db.execute(f'SELECT * FROM "{table}"').fetchall()
            for cell in row
        ]
    finally:
        db.close()


def test_no_row_of_the_state_db_holds_a_token_not_even_a_kept_reply(
    client: TestClient, env: dict[str, str]
) -> None:
    first = checkout(client, 'kept-1').json()['token']
    replayed = checkout(client, 'kept-1').json()['token']
    assert first != replayed
    cells = every_cell(env['SHOP_API_STATE_URL'])
    assert any('O-000001' in cell for cell in cells)  # the kept reply is there
    for token in (first, replayed):
        assert not any(token in cell for cell in cells)
    assert not any(replayed in cell for cell in every_cell(env['ROASTERY_DATABASE_URL']))


def test_a_new_state_db_beside_an_old_shop_db_goes_on_after_the_shops_ids(
    fresh_env: dict[str, str], wall: FakeClock, tmp_path: Path
) -> None:
    env = fresh_env
    assert seed(env)
    live, _ = open_live(env, wall=wall)
    try:
        with TestClient(create_app(live, sandbox=True)) as client:
            token = checkout(client, 'old-1').json()['token']
            assert pay(client, token, 'approve', 'pay-old-1').status_code == 201
    finally:
        live.close()

    fresh = tmp_path / 'other'
    fresh.mkdir()
    env = {**env, 'SHOP_API_STATE_URL': f'sqlite:///{(fresh / "state.db").as_posix()}'}
    assert not seed(env)  # the seed raises the counters even when it plays nothing
    live, _ = open_live(env, wall=wall)
    try:
        with TestClient(create_app(live, sandbox=True)) as client:
            reply = checkout(client, 'new-1')
            assert reply.status_code == 201, reply.text
            assert reply.json()['order_id'] == 'O-000002'
            paid = pay(client, reply.json()['token'], 'approve', 'pay-new-1')
            assert paid.status_code == 201, paid.text
            assert paid.json()['payment_id'] == 'PAY-2'
        assert live.state.number('guest') == 3
    finally:
        live.close()
