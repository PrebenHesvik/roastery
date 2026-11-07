"""The live wiring: one store, one lock, one moment per request (ADR 0016).

`Live` wires the shop as `bootstrap.main` does for the cli, with the API's adapters: the
sqlite store on the shop db, a `RequestClock` over the wall clock, ids counted in the
state db, `ClosedFeed` (no relay, F5), `FakeProvider` (no real payments, F5), and a
notifier and labels that write a log line and keep nothing. A `Storefront` stands beside
`App` on the same store.

Every request takes the one lock for its whole call: the storefront's unit of work and
`App`'s share the store's gate, which refuses re-entry. Run one worker.
"""

from __future__ import annotations

import datetime as dt
import logging
import sqlite3
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from roastery.api import (
    PROBLEM,
    STATUS,
    Handler,
    Orphaned,
    Request,
    Response,
    checkout_handler,
    order_handler,
    problem,
)
from roastery.bootstrap import App, sqlite_store, wire
from roastery.checkout import Checkout
from roastery.customer import Email
from roastery.customers import Customers
from roastery.fakes import ClosedFeed, FakeProvider
from roastery.idempotency import Stored, digest, once
from roastery.ids import CustomerId, OrderId, PostalCode
from roastery.middleware import logged, stack, timed
from roastery.payments import Payments
from roastery.ports import Clock
from roastery.pricing import standard_rules
from roastery.settings import Settings, SettingsError
from roastery.storefront import Storefront

from roastery_api.clock import RequestClock, SystemClock
from roastery_api.settings import ApiSettings, shop_settings
from roastery_api.state import CountedIds, SqliteKeys, State, UnknownToken, connect

CHECKOUT_SCOPE: Final = 'POST /checkout'
"""The idempotency scope of the checkout route."""

LOG: Final = 'roastery_api'
"""The logger's name: the notifier, the labels, the handlers and the orphans write here."""


class LogNotifier:
    """The confirmation e-mail as a log line; nothing kept (a server would grow)."""

    def __init__(self, log: logging.Logger) -> None:
        self._log = log

    def send(self, to: Email, *, subject: str, body: str) -> None:
        self._log.info('mail to %s: %s', to, subject)


class LogLabels:
    """The shipping label as a log line; nothing kept."""

    def __init__(self, log: logging.Logger) -> None:
        self._log = log

    def request(self, order_id: OrderId, *, postal_code: PostalCode) -> None:
        self._log.info('label for %s to %s', order_id, postal_code)


@dataclass(frozen=True)
class Deps:
    """What the handlers get: `App`, the storefront beside it, and the provider the
    sandbox hands its messages to. It satisfies `roastery.api.Deps`."""

    app: App
    storefront: Storefront
    provider: FakeProvider

    @property
    def customers(self) -> Customers:
        return self.app.customers

    @property
    def checkout(self) -> Checkout:
        return self.app.checkout

    @property
    def payments(self) -> Payments:
        return self.app.payments


def render(error: BaseException) -> Response:
    """The problem+json reply for a refusal: `roastery.api.problem`, and the API's own
    `UnknownToken` (404). Anything else is a 500 with no detail."""
    if isinstance(error, UnknownToken):
        body = {
            'type': 'about:blank',
            'title': 'Unknown token',
            'status': 404,
            'code': 'UnknownToken',
            'detail': str(error),
        }
        return {'status': 404, 'content_type': PROBLEM, 'body': body}
    return problem(error)


def _refusals(handler: Handler[Deps]) -> Handler[Deps]:
    """A refusal becomes its reply inside the handler, so `once` keeps a 4xx (ADR 0016)."""

    def wrapped(request: Request, deps: Deps) -> Response:
        try:
            return handler(request, deps)
        except (*STATUS, UnknownToken) as error:
            return render(error)

    wrapped.__name__ = handler.__name__
    return wrapped


class Live:
    """The process's one wiring, its state db and its lock."""

    def __init__(
        self,
        shop: sqlite3.Connection,
        state: sqlite3.Connection,
        settings: Settings,
        *,
        wall: Clock | None = None,
    ) -> None:
        self.log = logging.getLogger(LOG)
        self.wall = wall if wall is not None else SystemClock()
        self.clock = RequestClock(self.wall)
        self._connections = (shop, state)
        self.state = State(state)
        self.ids = CountedIds(self.state)
        self.keys = SqliteKeys(state, self.clock)
        store = sqlite_store(shop, clock=self.clock, price_ttl=settings.price_ttl)
        provider = FakeProvider(refund_ids=())
        app = wire(
            settings,
            store,
            clock=self.clock,
            ids=self.ids,
            source='visitor',
            feed=ClosedFeed(),
            provider=provider,
            notifier=LogNotifier(self.log),
            labels=LogLabels(self.log),
        )
        storefront = Storefront(store.unit_of_work('visitor'), self.clock, standard_rules().rules)
        self.deps = Deps(app, storefront, provider)
        self._lock = threading.Lock()

    def call(self, handler: Handler[Deps], request: Request) -> Response:
        """The handler under the lock, at one moment, logged and timed by the wall clock.

        A refusal that escapes the handler (a missing key, a key reused) is rendered;
        anything else is a 500 whose traceback goes to the log.
        """
        run = stack(handler, logged(self.log.info), timed(self.wall, self._took))
        with self._lock, self.clock.held():
            try:
                return run(request, self.deps)
            except (*STATUS, UnknownToken) as error:
                return render(error)
            except Exception as error:
                self.log.exception('%s failed', getattr(handler, '__name__', 'handler'))
                return render(error)

    def idempotent(self, handler: Handler[Deps], scope: str) -> Handler[Deps]:
        """The handler run once per `Idempotency-Key` on `scope` (the route)."""
        kept = once(handler, self.keys, scope=scope)
        kept.__name__ = handler.__name__  # type: ignore[attr-defined]
        return kept

    def close(self) -> None:
        for connection in self._connections:
            connection.close()

    def _took(self, name: str, took: dt.timedelta) -> None:
        self.log.debug('%s took %s', name, took)

    # The API's own handlers --------------------------------------------------------------

    def guest_checkout(self) -> Handler[Deps]:
        """`checkout_handler` for a guest: the guest's number drawn from the counter, the
        real contact and street kept in the state db, the order's link made, the token in
        the reply in place of the customer id (ADR 0016). An orphan is logged and kept (F2)."""
        state, clock, log = self.state, self.clock, self.log

        def checkout(request: Request, deps: Deps) -> Response:
            number = state.number('guest')
            try:
                reply = checkout_handler({**request, 'guest': number}, deps)
            except Orphaned as error:
                state.add_orphan(error.customer_id, repr(error.__cause__), clock.now())
                log.error('orphan %s: %r', error.customer_id, error.__cause__)
                if problem(error)['status'] == 500:
                    log.error('the cause', exc_info=error.__cause__)
                return problem(error)
            if reply['status'] != 201:
                return reply
            body: dict[str, Any] = dict(reply['body'])  # type: ignore[call-overload]
            contact: Mapping[str, Any] = request['body']  # type: ignore[assignment]
            now = clock.now()
            customer_id = CustomerId(body.pop('customer_id'))
            try:
                state.add_guest(
                    customer_id,
                    name=contact['name'],
                    email=contact['email'],
                    street=contact['street'],
                    postal_code=contact['postal_code'],
                    city=contact['city'],
                    country=contact['country'],
                    at=now,
                )
                body['token'] = state.link(OrderId(body['order_id']), now)
            except Exception as error:
                return self._after_commit(request, customer_id, body['order_id'], error)
            return {**reply, 'body': body}

        return checkout

    def _after_commit(
        self, request: Request, customer_id: CustomerId, order_id: str, error: Exception
    ) -> Response:
        """The shop committed the order but the guest or the link was not written: the
        guest is logged as an orphan and a 500 is kept under the key, so a retry gets the
        same 500 and places no second order (`once` keeps no 5xx of its own)."""
        self.log.error('order %s placed, its state write failed: %r', order_id, error)
        reason = f'{order_id} placed, state write failed: {error!r}'
        failed = problem(error)
        try:
            self.state.add_orphan(customer_id, reason, self.clock.now())
        except Exception:
            self.log.exception('orphan %s not recorded', customer_id)
        key = request.get('key')
        if isinstance(key, str) and key:
            try:
                body_hash = digest(request.get('body', {}))
                self.keys.put(CHECKOUT_SCOPE, key, Stored(body_hash, failed))
            except Exception:
                self.log.exception('the reply under key %s not kept', key)
        return failed

    def order_by_token(self) -> Handler[Deps]:
        """`order_handler` for the order a token links to; 404 UnknownToken if none."""
        state = self.state

        def order(request: Request, deps: Deps) -> Response:
            token = request['path']['token']  # type: ignore[index]
            order_id = state.order_of(token)
            return order_handler({'path': {'order_id': str(order_id)}}, deps)

        return _refusals(order)


def open_live(env: Mapping[str, str], *, wall: Clock | None = None) -> tuple[Live, ApiSettings]:
    """The wiring from the environment: `ROASTERY_*` for the shop, `SHOP_API_*` for the
    API. SettingsError lists every problem of both."""
    problems: list[str] = []
    try:
        settings = shop_settings(env)
    except SettingsError as error:
        problems += error.problems
    try:
        api = ApiSettings.from_env(env)
    except SettingsError as error:
        problems += error.problems
    if problems:
        raise SettingsError(problems)
    shop = connect(settings.database_url)
    return Live(shop, connect(api.state_url), settings, wall=wall), api
