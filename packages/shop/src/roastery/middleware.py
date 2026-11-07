"""Handlers around handlers: `logged`, `timed`, `require_role`.

Each is a function that gives a middleware, a function from a
handler to a handler. `stack` applies several. No wall clock:
`timed` reads the `Clock` port it is given (ADR 0008).
"""

from __future__ import annotations

import datetime as dt
import functools
from collections.abc import Callable

from roastery.api import (
    Forbidden,
    Handler,
    Request,
    Response,
    problem,
)
from roastery.ports import Clock


def logged[D](
    log: Callable[[str], None],
) -> Callable[[Handler[D]], Handler[D]]:
    """Log `name status` after each call, or `name raised Type`
    when the handler raises (and raise it again)."""

    def middleware(handler: Handler[D]) -> Handler[D]:
        @functools.wraps(handler)
        def wrapped(request: Request, deps: D) -> Response:
            name = handler.__name__
            try:
                reply = handler(request, deps)
            except Exception as error:
                log(f'{name} raised {type(error).__name__}')
                raise
            log(f'{name} {reply["status"]}')
            return reply

        return wrapped

    return middleware


def timed[D](
    clock: Clock,
    record: Callable[[str, dt.timedelta], None],
) -> Callable[[Handler[D]], Handler[D]]:
    """Record `name, time taken` by the clock given, also when the
    handler raises. A clock fixed per request gives zero: give it
    the real one."""

    def middleware(handler: Handler[D]) -> Handler[D]:
        @functools.wraps(handler)
        def wrapped(request: Request, deps: D) -> Response:
            start = clock.now()
            try:
                return handler(request, deps)
            finally:
                record(handler.__name__, clock.now() - start)

        return wrapped

    return middleware


def require_role[D](
    role: str,
) -> Callable[[Handler[D]], Handler[D]]:
    """403 Forbidden unless `request['role']` is `role`; the
    handler is not called."""

    def middleware(handler: Handler[D]) -> Handler[D]:
        @functools.wraps(handler)
        def wrapped(request: Request, deps: D) -> Response:
            if request.get('role') != role:
                return problem(Forbidden(role))
            return handler(request, deps)

        return wrapped

    return middleware


def stack[D](
    handler: Handler[D],
    *middleware: Callable[[Handler[D]], Handler[D]],
) -> Handler[D]:
    """The handler wrapped by each middleware; the first listed is
    the outermost, so it sees the request first."""
    for each in reversed(middleware):
        handler = each(handler)
    return handler
