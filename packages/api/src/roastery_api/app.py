"""FastAPI over the shop's handlers: parse, lock, call, render (ADR 0016).

A route parses the request with its pydantic model, hands a plain request to a
`roastery.api` handler through `Live.call` (the one lock, the request's moment), and
renders the reply: the handler's body, with the display amounts beside the NOK ones
(ADR 0018). Every error is problem+json; a body that does not parse is a 400. Every route
is a plain `def`, so the lock never blocks the event loop.

`app` is what `uvicorn roastery_api.app:app` runs: it reads the environment and wires
itself when the server starts. Tests build their own with `create_app`.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from http import HTTPStatus
from typing import Annotated, Any

from fastapi import FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from roastery.api import (
    PROBLEM,
    Handler,
    product_handler,
    products_handler,
    quote_handler,
)
from roastery.api import Response as Reply
from starlette.exceptions import HTTPException
from starlette.types import Receive, Scope, Send

from roastery_api import fx, schemas
from roastery_api.live import LOG, Deps, Live, open_live
from roastery_api.sandbox import payments_handler
from roastery_api.settings import DEFAULT_ORIGINS

PROBLEMS: Mapping[int | str, dict[str, Any]] = {
    status: {
        'model': schemas.Problem,
        'content': {PROBLEM: {'schema': {'$ref': '#/components/schemas/Problem'}}},
    }
    for status in (400, 402, 404, 409, 422, 500, 503)
}
"""Every route may answer a problem; the document names the codes each one gives."""

IdempotencyKey = Annotated[
    str,
    Header(
        alias='Idempotency-Key',
        min_length=1,
        max_length=255,
        description='One key per attempt: the same key and body give the same reply.',
    ),
]


CountryQuery = Annotated[
    schemas.Country, Query(description="The buyer's country: its currency and VAT wording.")
]


def _problems(*statuses: int) -> dict[int | str, dict[str, Any]]:
    return {status: PROBLEMS[status] for status in statuses}


def _problem(status: int, code: str, detail: str | None) -> JSONResponse:
    body = {
        'type': 'about:blank',
        'title': HTTPStatus(status).phrase,
        'status': status,
        'code': code,
    }
    if detail is not None:
        body['detail'] = detail
    return JSONResponse(body, status_code=status, media_type=PROBLEM)


def _render(reply: Reply, page: Callable[[Any], Any] | None = None) -> JSONResponse:
    """The handler's reply as HTTP; a success's body through `page`, if given."""
    status: int = reply['status']  # type: ignore[assignment]
    body: Any = reply['body']
    if status < 300 and page is not None:
        body = page(body)
    elif body.get('code') == 'PriceChanged':
        body = {**body, 'quote': fx.quote_page(body['quote'])}
    return JSONResponse(body, status_code=status, media_type=str(reply['content_type']))


def create_app(
    live: Live | None,
    *,
    origins: tuple[str, ...] = (DEFAULT_ORIGINS,),
    owns: bool = False,
) -> FastAPI:
    """The API on `live`; with `owns`, the wiring is closed when the server stops.

    `live` may be None only to read the OpenAPI document: every route then fails.
    """

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        if owns and live is not None:
            live.close()

    api = FastAPI(
        title='Sydvest Kaffebrenneri',
        version='0.1.0',
        summary='The shop over HTTP: the catalogue, a quote, guest checkout, a test payment.',
        lifespan=lifespan,
    )
    api.add_middleware(
        CORSMiddleware,
        allow_origins=list(origins),
        allow_methods=['GET', 'POST'],
        allow_headers=['Content-Type', 'Idempotency-Key'],
        allow_credentials=False,
    )

    @api.exception_handler(RequestValidationError)
    def _unparsed(_: Request, error: RequestValidationError) -> JSONResponse:
        detail = '; '.join(
            f'{".".join(str(each) for each in problem["loc"])}: {problem["msg"]}'
            for problem in error.errors()
        )
        return _problem(400, 'RequestValidationError', detail)

    @api.exception_handler(HTTPException)
    def _http(_: Request, error: HTTPException) -> JSONResponse:
        code = HTTPStatus(error.status_code).phrase.title().replace(' ', '').replace('-', '')
        return _problem(error.status_code, code, None)

    def wired() -> Live:
        if live is None:
            raise RuntimeError('this app has no wiring: it only describes the API')
        return live

    handlers: dict[str, Handler[Deps]] = {}
    if live is not None:
        handlers['checkout'] = live.idempotent(live.guest_checkout(), 'POST /checkout')
        handlers['pay'] = live.idempotent(
            payments_handler(live.state, live.ids, live.clock), 'POST /sandbox/payments'
        )
        handlers['order'] = live.order_by_token()

    @api.get(
        '/products',
        response_model=schemas.ProductList,
        responses=_problems(400),
        operation_id='listProducts',
    )
    def list_products(country: CountryQuery = 'NO') -> JSONResponse:
        """Every product, priced on Norway's day; also in the country's currency."""
        reply = wired().call(products_handler, {})
        return _render(reply, lambda body: fx.listing_page(body, country))

    @api.get(
        '/products/{product_id}',
        response_model=schemas.ProductPage,
        responses=_problems(400, 404),
        operation_id='getProduct',
    )
    def get_product(product_id: str, country: CountryQuery = 'NO') -> JSONResponse:
        """One product; 404 `UnknownId`."""
        reply = wired().call(product_handler, {'path': {'id': product_id}})
        return _render(reply, lambda body: fx.product_page(body, country))

    @api.post(
        '/quote',
        response_model=schemas.Quote,
        responses=_problems(400, 422),
        operation_id='quoteCart',
    )
    def quote(body: schemas.QuoteRequest) -> JSONResponse:
        """The cart priced for the country on its day, with the VAT the page shows."""
        reply = wired().call(quote_handler, {'body': body.model_dump(mode='json')})
        return _render(reply, fx.quote_page)

    @api.post(
        '/checkout',
        status_code=201,
        response_model=schemas.PlacedOrder,
        responses=_problems(400, 409, 422),
        operation_id='checkout',
    )
    def place_order(body: schemas.CheckoutRequest, key: IdempotencyKey) -> JSONResponse:
        """A guest's order. 409 `PriceChanged` (with the new quote), `OutOfStock` or
        `KeyReused`; nothing is written on a refusal."""
        request = {'body': body.model_dump(mode='json'), 'key': key}
        reply = wired().call(handlers['checkout'], request)
        return _render(reply, fx.placed_page)

    @api.post(
        '/sandbox/payments',
        status_code=201,
        response_model=schemas.SandboxPayment,
        responses=_problems(400, 402, 404, 409, 503),
        operation_id='payInSandbox',
    )
    def sandbox_payment(body: schemas.SandboxPaymentRequest, key: IdempotencyKey) -> JSONResponse:
        """A test payment: no money moves. 402 `ProviderRefused` on decline, 503
        `ProviderUnavailable` on outage, 409 `IllegalTransition` for a paid order."""
        request = {'body': body.model_dump(mode='json'), 'key': key}
        reply = wired().call(handlers['pay'], request)
        return _render(reply)

    @api.get(
        '/orders/{token}',
        response_model=schemas.Order,
        responses=_problems(404),
        operation_id='getOrder',
    )
    def get_order(token: str) -> JSONResponse:
        """The order its private link names; 404 `UnknownToken`."""
        reply = wired().call(handlers['order'], {'path': {'token': token}})
        return _render(reply, fx.order_page)

    def openapi() -> dict[str, Any]:
        """FastAPI's document without its default 422s: a body that does not parse is a
        400 problem here, and 422 means `UnknownProduct`, `WrongKind` or `NoPrice`."""
        if api.openapi_schema is None:
            document = get_openapi(
                title=api.title,
                version=api.version,
                summary=api.summary,
                routes=api.routes,
            )
            for operations in document['paths'].values():
                for operation in operations.values():
                    default = operation['responses'].get('422', {})
                    if 'HTTPValidationError' in str(default):
                        del operation['responses']['422']
            schemas_ = document.get('components', {}).get('schemas', {})
            for name in ('HTTPValidationError', 'ValidationError'):
                schemas_.pop(name, None)
            api.openapi_schema = document
        return api.openapi_schema

    api.openapi = openapi  # type: ignore[method-assign]
    return api


class _FromEnv:
    """The ASGI app uvicorn runs: wired from the environment when the server starts, so
    importing this module reads nothing and opens nothing."""

    def __init__(self) -> None:
        self._app: FastAPI | None = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self._app is None:
            log = logging.getLogger(LOG)
            if not log.handlers:
                log.addHandler(logging.StreamHandler())
                log.setLevel(logging.INFO)
            live, settings = open_live(os.environ)
            self._app = create_app(live, origins=settings.cors_origins, owns=True)
        await self._app(scope, receive, send)


app = _FromEnv()
