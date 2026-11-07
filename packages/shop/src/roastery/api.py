"""The shop's HTTP edge without a framework (ADR 0013, 0016).

A handler takes a request mapping and the deps and returns a
response mapping; the FastAPI package turns HTTP into the one and
the other into HTTP. No web framework is imported here.

The request keys a handler reads:

- `path`: the route's parameters (`id`, `order_id`);
- `body`: the parsed JSON body, a mapping;
- `guest`: the guest number `<n>` of checkout, drawn by the API
  from its own counter (F1, ADR 0016);
- `key` and `role`: the `Idempotency-Key` and the caller's role,
  read by `idempotency.once` and `middleware.require_role`.

A response is `{'status', 'content_type', 'body'}`, the body made
of text, numbers, lists and mappings only. An error is
problem+json (RFC 9457) with `code`, the class name raised.

A client never names a price: an item's body has a product id and
a quantity, and `Item` is built with `price=None`.
"""

from __future__ import annotations

import datetime as dt
import functools
import re
from collections.abc import Callable, Mapping
from dataclasses import fields, is_dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Final, Protocol

from roastery.checkout import Checkout, Item, PlaceOrder
from roastery.clock import ZONES
from roastery.customer import Email
from roastery.customers import Customers
from roastery.errors import (
    AlreadyCredited,
    DuplicateId,
    IllegalSubscriptionMove,
    IllegalTransition,
    KeyReused,
    NoAddress,
    NoOpenInvoice,
    NoPrice,
    NoSuchCustomer,
    NotCreditable,
    NothingToRefund,
    NotShippable,
    OutOfStock,
    PaymentMismatch,
    PeriodOverlap,
    UnknownId,
    UnknownProduct,
    WrongKind,
)
from roastery.ids import (
    Country,
    CustomerId,
    OrderId,
    PostalCode,
    ProductId,
)
from roastery.money import Money, Qty
from roastery.ports import ProviderRefused, ProviderUnavailable
from roastery.storefront import Asked, Quoted, Storefront

type Request = Mapping[str, object]
type Response = Mapping[str, object]
type Handler[D] = Callable[[Request, D], Response]

JSON: Final = 'application/json'
PROBLEM: Final = 'application/problem+json'


class RequestValidationError(Exception):
    """A request that does not parse: a 400 (ADR 0006)."""


class PriceChanged(Exception):
    """The re-quote differs from the total the buyer confirmed:
    a 409 that carries the new quote. Nothing was written."""

    def __init__(self, quote: Quoted, confirmed: Money) -> None:
        self.quote = quote
        self.confirmed = confirmed
        super().__init__(
            f'the total is {quote.gross.amount}, not {confirmed.amount}'
        )


class Forbidden(Exception):
    """The caller lacks the role the handler needs: a 403."""

    def __init__(self, role: str) -> None:
        self.role = role
        super().__init__(f'this needs the role {role!r}')


class Orphaned(Exception):
    """`register` committed and `place` failed (F2). The cause is
    the refusal; `customer_id` is the guest left without an order,
    for the API's orphan log. Not a status: `problem` shows the
    cause."""

    def __init__(self, customer_id: CustomerId) -> None:
        self.customer_id = customer_id
        super().__init__(f'{customer_id} was registered, not placed')


STATUS: Final[Mapping[type[Exception], int]] = MappingProxyType(
    {
        IllegalTransition: 409,
        IllegalSubscriptionMove: 409,
        NotShippable: 409,
        NoAddress: 409,
        NotCreditable: 409,
        AlreadyCredited: 409,
        NoOpenInvoice: 409,
        NothingToRefund: 409,
        PaymentMismatch: 409,
        KeyReused: 409,
        DuplicateId: 409,
        OutOfStock: 409,
        PeriodOverlap: 409,
        UnknownId: 404,
        NoSuchCustomer: 404,
        UnknownProduct: 422,
        WrongKind: 422,
        NoPrice: 422,
        ProviderRefused: 402,
        ProviderUnavailable: 503,
        # the edge's own refusals (ADR 0016)
        PriceChanged: 409,
        RequestValidationError: 400,
        Forbidden: 403,
    }
)
"""The status of each refusal: ADR 0006's table, the provider's
port errors (ADR 0011) and the edge's own."""


class Deps(Protocol):
    """What the handlers need; the API's deps have it. `App` has
    the first two; the storefront stands beside it (ADR 0017)."""

    @property
    def customers(self) -> Customers: ...

    @property
    def checkout(self) -> Checkout: ...

    @property
    def storefront(self) -> Storefront: ...


# Rendering -------------------------------------------------------


def plain(value: object) -> Any:
    """The value as JSON would hold it: text, numbers, lists and
    mappings. Money is `{amount, currency}` with the amount as
    text, a Decimal is text, a date is ISO, an id is its text and
    a dataclass is a mapping of its fields. Anything else raises:
    nothing is guessed."""
    match value:
        case None | bool() | int() | str():
            return value
        case Money(amount=amount, currency=currency):
            return {'amount': str(amount), 'currency': currency}
        case Qty(value=count):
            return count
        case Decimal():
            return str(value)
        case dt.date():  # a datetime is a date
            return value.isoformat()
        case Mapping():
            return {str(k): plain(v) for k, v in value.items()}
        case list() | tuple():
            return [plain(each) for each in value]
    if is_dataclass(value) and not isinstance(value, type):
        if type(value).__str__ is not object.__str__:
            return str(value)  # an id, a postal code
        return {
            field.name: plain(getattr(value, field.name))
            for field in fields(value)
        }
    raise TypeError(f'not a plain value: {value!r}')


def _title(name: str) -> str:
    """`OutOfStock` is `Out of stock`."""
    words = re.sub(r'(?<!^)(?=[A-Z])', ' ', name)
    return words[:1] + words[1:].lower()


def problem(error: BaseException) -> Response:
    """The problem+json response for an error.

    An error in `STATUS` (or a subclass) gives its status, its
    class name as `code` and its attributes. Orphaned gives its
    cause. Anything else is a 500, `InternalError`, no detail: a
    bug's text is not for the client.
    """
    if isinstance(error, Orphaned) and error.__cause__:
        error = error.__cause__
    status = next(
        (
            STATUS[each]
            for each in type(error).__mro__
            if each in STATUS
        ),
        None,
    )
    body: dict[str, object] = {'type': 'about:blank'}
    if status is None:
        body.update(
            title='Internal error', status=500, code='InternalError'
        )
        return _response(500, body, PROBLEM)
    name = type(error).__name__
    body.update(
        title=_title(name),
        status=status,
        code=name,
        detail=str(error),
    )
    for key, value in sorted(vars(error).items()):
        if not key.startswith('_') and key not in body:
            body[key] = plain(value)
    return _response(status, body, PROBLEM)


def _response(
    status: int, body: object, content_type: str = JSON
) -> Response:
    return {
        'status': status,
        'content_type': content_type,
        'body': body,
    }


def _edge[D](handler: Handler[D]) -> Handler[D]:
    """A refusal the table knows becomes its response; anything
    else goes up to the API, which renders `problem(error)` and
    logs the traceback."""

    @functools.wraps(handler)
    def wrapped(request: Request, deps: D) -> Response:
        try:
            return handler(request, deps)
        except tuple(STATUS) as error:
            return problem(error)

    return wrapped


# Parsing ---------------------------------------------------------


def _mapping(value: object, what: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise RequestValidationError(f'{what} must be an object')
    return value


def _body(request: Request) -> Mapping[str, object]:
    return _mapping(request.get('body'), 'the body')


def _country(body: Mapping[str, object]) -> Country:
    country = body.get('country')
    for code in ZONES:
        if country == code:
            return code
    raise RequestValidationError(f'unknown country {country!r}')


def _product_id(value: object) -> ProductId:
    try:
        return ProductId(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as error:
        raise RequestValidationError(str(error)) from error


def _asked(body: Mapping[str, object]) -> tuple[Asked, ...]:
    """The items: a product id and a quantity each. Any other key,
    a `price` above all, is not read."""
    items = body.get('items')
    if not isinstance(items, list) or not items:
        raise RequestValidationError('items must be a list of one+')
    asked = []
    for each in items:
        item = _mapping(each, 'an item')
        count = item.get('qty')
        if (
            isinstance(count, bool)
            or not isinstance(count, int)
            or count < 1
        ):
            raise RequestValidationError(
                f'qty must be a whole number, 1 or more: {count!r}'
            )
        product_id = _product_id(item.get('product_id'))
        asked.append(Asked(product_id, Qty(count)))
    return tuple(asked)


def _confirmed(body: Mapping[str, object]) -> Money:
    total = _mapping(body.get('total'), 'total')
    try:
        return Money.of(
            total['amount'],  # type: ignore[arg-type]
            total['currency'],  # type: ignore[arg-type]
        )
    except (KeyError, TypeError, ArithmeticError, ValueError) as error:
        raise RequestValidationError(f'total: {error!r}') from error


def _postal(body: Mapping[str, object]) -> PostalCode:
    try:
        return PostalCode(body.get('postal_code'))  # type: ignore[arg-type]
    except (TypeError, ValueError) as error:
        raise RequestValidationError(str(error)) from error


def _guest(request: Request) -> int:
    number = request.get('guest')
    if isinstance(number, bool) or not isinstance(number, int):
        raise RequestValidationError('guest must be a number')
    if number < 1:
        raise RequestValidationError('guest must be 1 or more')
    return number


def _path(request: Request, name: str) -> str:
    value = _mapping(request.get('path'), 'path').get(name)
    if not isinstance(value, str):
        raise RequestValidationError(f'path needs {name}')
    return value


# Handlers --------------------------------------------------------


@_edge
def products_handler(request: Request, deps: Deps) -> Response:
    """GET /products: 200, every product on Norway's day."""
    listed = deps.storefront.products()
    return _response(200, {'products': plain(listed)})


@_edge
def product_handler(request: Request, deps: Deps) -> Response:
    """GET /products/{id}: 200, or 404 UnknownId."""
    product_id = _product_id(_path(request, 'id'))
    try:
        listed = deps.storefront.product(product_id)
    except UnknownProduct:
        # the id is the resource: 404, as ADR 0016 says
        raise UnknownId('product', str(product_id)) from None
    return _response(200, plain(listed))


@_edge
def quote_handler(request: Request, deps: Deps) -> Response:
    """POST /quote: 200, the cart priced; 422 UnknownProduct."""
    body = _body(request)
    quoted = deps.storefront.quote(_country(body), _asked(body))
    return _response(200, plain(quoted))


@_edge
def checkout_handler(request: Request, deps: Deps) -> Response:
    """POST /checkout: a guest's order, 201.

    In order (ADR 0016): parse; re-quote, and 409 PriceChanged if
    the total is not the one confirmed; 409 OutOfStock from the
    same quote; register the guest `Guest <n>` with
    `guest-<n>@example.invalid`, `n` from the request; place. The
    real name, e-mail and street are the API's, not the shop's
    (F1, F4). Nothing is written before the last two steps. If
    `place` refuses after `register` committed, Orphaned.
    """
    body = _body(request)
    country = _country(body)
    asked = _asked(body)
    confirmed = _confirmed(body)
    postal = _postal(body)
    number = _guest(request)
    quoted = deps.storefront.quote(country, asked)
    if quoted.gross != confirmed:
        raise PriceChanged(quoted, confirmed)
    quoted.check_stock()
    guest = deps.customers.register(
        f'Guest {number}',
        email=Email(f'guest-{number}@example.invalid'),
        country=country,
        postal_code=postal,
    )
    items = tuple(Item(each.product_id, each.qty) for each in asked)
    try:
        placed = deps.checkout.place(PlaceOrder(guest, 'web', items))
    except Exception as error:
        raise Orphaned(guest) from error
    return _response(
        201,
        {
            'order_id': plain(placed.head.order_id),
            'customer_id': plain(guest),
            'country': country,
            'total': plain(quoted.gross),
        },
    )


@_edge
def order_handler(request: Request, deps: Deps) -> Response:
    """GET /orders: 200, the order of `path.order_id` as its buyer
    may read it; 404 UnknownId. The API finds the id from the
    token."""
    try:
        order_id = OrderId(_path(request, 'order_id'))
    except ValueError as error:
        raise RequestValidationError(str(error)) from error
    return _response(200, plain(deps.storefront.order(order_id)))
