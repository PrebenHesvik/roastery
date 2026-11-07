"""`logged`, `timed`, `require_role` and `stack` (ADR 0013)."""

from __future__ import annotations

import datetime as dt

import pytest

from roastery.api import Request, Response
from roastery.fakes import FakeClock
from roastery.middleware import logged, require_role, stack, timed


def handle(request: Request, deps: object) -> Response:
    return {'status': 200, 'body': {'seen': request.get('x')}}


def explode(request: Request, deps: object) -> Response:
    raise ZeroDivisionError


def test_logged_writes_name_and_status() -> None:
    lines: list[str] = []
    wrapped = logged(lines.append)(handle)
    assert wrapped({'x': 1}, None)['body'] == {'seen': 1}
    assert lines == ['handle 200']
    assert wrapped.__name__ == 'handle'


def test_logged_writes_a_raise_and_raises_again() -> None:
    lines: list[str] = []
    with pytest.raises(ZeroDivisionError):
        logged(lines.append)(explode)({}, None)
    assert lines == ['explode raised ZeroDivisionError']


def test_timed_reads_the_clock_it_is_given() -> None:
    clock = FakeClock(dt.datetime(2026, 10, 5, 9, 0, tzinfo=dt.UTC))
    taken: list[tuple[str, dt.timedelta]] = []

    def slow(request: Request, deps: object) -> Response:
        clock.set(clock.now() + dt.timedelta(milliseconds=250))
        return {'status': 200, 'body': {}}

    timed(clock, lambda name, took: taken.append((name, took)))(slow)(
        {}, None
    )
    assert taken == [('slow', dt.timedelta(milliseconds=250))]


def test_timed_records_when_the_handler_raises() -> None:
    clock = FakeClock(dt.datetime(2026, 10, 5, 9, 0, tzinfo=dt.UTC))
    taken: list[str] = []
    wrapped = timed(clock, lambda name, took: taken.append(name))
    with pytest.raises(ZeroDivisionError):
        wrapped(explode)({}, None)
    assert taken == ['explode']


def test_require_role_lets_the_role_through() -> None:
    wrapped = require_role('staff')(handle)
    assert wrapped({'role': 'staff', 'x': 2}, None)['status'] == 200


@pytest.mark.parametrize('request_', [{}, {'role': 'guest'}])
def test_require_role_refuses_others_with_403(request_) -> None:
    called: list[int] = []

    def spy(request: Request, deps: object) -> Response:
        called.append(1)
        return {'status': 200, 'body': {}}

    reply = require_role('staff')(spy)(request_, None)
    assert reply['status'] == 403
    assert reply['body']['code'] == 'Forbidden'
    assert called == []


def test_stack_puts_the_first_outermost() -> None:
    lines: list[str] = []

    def tag(name: str):
        def middleware(handler):
            def wrapped(request, deps):
                lines.append(f'{name} in')
                reply = handler(request, deps)
                lines.append(f'{name} out')
                return reply

            return wrapped

        return middleware

    stack(handle, tag('a'), tag('b'))({}, None)
    assert lines == ['a in', 'b in', 'b out', 'a out']
