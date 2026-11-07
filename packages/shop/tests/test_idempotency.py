"""The same key twice gives one effect (ADR 0016)."""

from __future__ import annotations

import pytest

from roastery.api import Request, RequestValidationError, Response
from roastery.errors import KeyReused
from roastery.idempotency import MemoryKeys, digest, once


class Counting:
    """A handler that counts its calls and answers with the count."""

    def __init__(self, status: int = 201) -> None:
        self.calls = 0
        self.status = status

    def __call__(self, request: Request, deps: object) -> Response:
        self.calls += 1
        return {'status': self.status, 'body': {'n': self.calls}}


def _request(key: str | None, body: object) -> dict:
    return {'key': key, 'body': body}


def test_same_key_and_body_gives_the_stored_reply() -> None:
    handler = Counting()
    wrapped = once(handler, MemoryKeys(), scope='checkout')
    first = wrapped(_request('k1', {'a': 1, 'b': 2}), None)
    again = wrapped(_request('k1', {'b': 2, 'a': 1}), None)
    assert handler.calls == 1
    assert again == first == {'status': 201, 'body': {'n': 1}}


def test_same_key_and_another_body_is_key_reused() -> None:
    handler = Counting()
    wrapped = once(handler, MemoryKeys(), scope='checkout')
    wrapped(_request('k1', {'a': 1}), None)
    with pytest.raises(KeyReused) as raised:
        wrapped(_request('k1', {'a': 2}), None)
    assert raised.value.key == 'k1'
    assert handler.calls == 1


def test_a_new_key_runs_again() -> None:
    handler = Counting()
    wrapped = once(handler, MemoryKeys(), scope='checkout')
    wrapped(_request('k1', {}), None)
    wrapped(_request('k2', {}), None)
    assert handler.calls == 2


def test_the_scope_is_the_route() -> None:
    keys = MemoryKeys()
    one, two = Counting(), Counting()
    once(one, keys, scope='checkout')(_request('k', {}), None)
    once(two, keys, scope='payment')(_request('k', {'x': 1}), None)
    assert (one.calls, two.calls) == (1, 1)


def test_a_4xx_is_stored() -> None:
    handler = Counting(status=409)
    wrapped = once(handler, MemoryKeys())
    wrapped(_request('k', {}), None)
    wrapped(_request('k', {}), None)
    assert handler.calls == 1


def test_a_5xx_is_not_stored_so_a_retry_runs() -> None:
    handler = Counting(status=503)
    wrapped = once(handler, MemoryKeys())
    wrapped(_request('k', {}), None)
    wrapped(_request('k', {}), None)
    assert handler.calls == 2


@pytest.mark.parametrize('key', [None, ''])
def test_a_missing_key_is_a_400(key: str | None) -> None:
    wrapped = once(Counting(), MemoryKeys())
    with pytest.raises(RequestValidationError):
        wrapped(_request(key, {}), None)


def test_the_digest_ignores_key_order() -> None:
    assert digest({'a': 1, 'b': [1, 2]}) == digest(
        {'b': [1, 2], 'a': 1}
    )
    assert digest({'a': 1}) != digest({'a': 2})
