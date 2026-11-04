# 0006. Errors

Status: accepted, 2026-11-04 (step 6.2, decision C6)

## Context

The app has two kinds of caller, and they fail in different ways:

- **The API**, which answers a person. A refusal becomes an HTTP status.
- **The simulator**, which plays a script of hundreds of calls with nobody watching. A refusal
  it does not notice is a quiet mistake: the week drifts from the frozen data and nothing
  says where. Shipping O-106, which was cancelled at E-12, must stop the script, and the
  script must be able to tell that refusal from a bug.

Plan §5 asked to weigh "a `Result` type at the edges, exceptions inside". The `errors` page
asks a sharper question with real rows: `country_of` has two ways to find no country.

| customer | what is true | what the caller needs to know |
|---|---|---|
| C-05 (Lars) | known, and has no country | the shop decides what that means (ADR 0010: Norway) |
| C-07 | erased on 9 October; O-107 still names them | no such customer now |

`None` cannot tell these apart, which is the firm's E-21 lesson ("none hides"). The firm's
`department_of` returns `Ok | Err` from `firm/result.py`.

## Decision

Four kinds of failure, four ways to report them:

| kind | how | example |
|---|---|---|
| a malformed value | `ValueError` or `TypeError`, raised where the value is built (ADR 0004) | `Qty(0)`, `OrderId('C-01')` |
| a command the shop's rules refuse | raise a member of the closed family `ShopError`; nothing is written | ship O-106 |
| a question with two kinds of answer | return a `Result`: `Ok[T] \| Err[E]` | `country_of(C-05)` |
| a bug | any other exception, never caught in `roastery` | |

**The family.** One core module holds `ShopError` and every subclass of it; no other module
defines one. ADR 0001's `LAYERS` has no module for it yet (see the open question below). The
decisions of this step already name these members:

| member | raised when | row |
|---|---|---|
| `IllegalTransition` | a move `TRANSITIONS` does not have (ADR 0005) | shipping O-106 |
| `NotShippable` | `ship` on a counter sale (ADR 0005) | O-104 |
| `DuplicateId` | the store already holds the id (ADR 0007) | |
| `KeyReused` | a payment message with a known `payment_id` and another amount | PAY-1 sent again with another amount |
| `UnknownProduct` | a line names a product the shop does not list; the whole order rolls back | P-99 (L-09's product) |
| `NoSuchCustomer` | a command names a customer the store does not hold | an order for C-07 after 9 October |

Contract B (ADR 0011, U4) lists, per service and per call, which members it raises. The list
there is the whole family; 6.3's snapshot test (C12) checks the family's module against it.

```python
class ShopError(Exception):
    """A command the shop's rules refuse; nothing was written."""


class IllegalTransition(ShopError):
    def __init__(
        self, order_id: OrderId, state: str, action: str
    ) -> None: ...


class KeyReused(ShopError):
    def __init__(self, payment_id: PaymentId) -> None: ...
```

Each member keeps the ids it names as attributes, so a test or the simulator can check them
without reading the message.

**The results.** `roastery/result.py` has `Ok[T]`, `Err[E]` and `partition`, as the firm's
`result.py` has them. Two questions use them now:

```python
@dataclass(frozen=True)
class NoCountry:
    customer_id: CustomerId


@dataclass(frozen=True)
class UnknownCustomer:
    customer_id: CustomerId


def country_of(
    customer_id: CustomerId, customers: CustomerRepository
) -> Ok[Country] | Err[NoCountry | UnknownCustomer]: ...
```

- `NoCountry` and `UnknownCustomer` are values, not exceptions. A caller matches on them,
  and `assert_never` makes it handle both.
- `NoCountry`, `UnknownCustomer` and `country_of` live in `roastery/customers.py`, the
  service that holds the customer repository.
- Parsing gives `Ok[ParsedLine] | Err[Reject]`: the till's file in ADR 0012, the firm's shape
  in `firm/parsing.py`.

**The API** maps the family to statuses in one table in `api.py` (ADR 0013). A
`ValueError` from its parse step is a 400. Anything else is a 500.

```python
STATUS: Final[Mapping[type[ShopError], int]] = MappingProxyType({
    IllegalTransition: 409,
    NotShippable: 409,
    DuplicateId: 409,
    KeyReused: 409,
    UnknownProduct: 422,
    NoSuchCustomer: 404,
})
```

## Alternatives refused

| alternative | why refused |
|---|---|
| `Result` at every edge, exceptions inside (plan §5's first idea) | every one of the simulator's calls would return an `Err` it must check. One unchecked `Err` lets O-106 "ship" and the week drifts with no error. A raise stops the script at the call that broke |
| exceptions for questions too (`country_of` raises `NoCountry`) | Lars has no country, and that is a normal answer. Every caller would wrap the call in `try`; a forgotten `except` is a 500 at checkout, the DevOps night of ADR 0010 |
| `None` for "no country" | cannot tell C-05 from C-07; the `errors` page's lesson |
| built-in exceptions for refusals (`LookupError`, `ValueError`) | the API cannot map them without also catching the bugs that raise the same types; the family cannot be pinned by the snapshot test |
| an open family, each module defining its own errors | contract B could not list them all; a new one appears without a review of the call surface it changes |
| error codes or message strings | the simulator would compare text; a reworded message breaks a script |

## Consequences

- A refused command writes nothing: the unit of work rolls back on any exception (ADR 0003).
  P-99 rolls back the order, its lines, the stock reservation and the outbox row together.
- The simulator catches `ShopError` only where its script says a refusal is expected (O-106).
  Anywhere else the run stops.
- `NoSuchCustomer` and `UnknownCustomer` are two names on purpose: one is a refusal raised by
  a command, the other a value returned by a question. U4 may rename them; both stay.
- A malformed value is not a `ShopError`. The provider's own errors (`ProviderApiError` in
  `provider_sdk.py`) stay behind the adapter in `provider.py`, which turns them into the
  shop's terms; a declined card is decided there (the `retry-and-circuit-breaker` page).
- **Open question:** ADR 0001's `LAYERS` names no home for the family. It is core (every
  layer raises or maps it), and `ports.py` holds only the ports' own errors. Either `LAYERS`
  gains a core module `errors`, or the family goes into an existing core module (`result.py`
  is the nearest). U5 decides it against `LAYERS`; this ADR does not add a module.
- Adding a member after 6.4 changes contract B, so it is a new data version (CLAUDE.md,
  Freezes).

## Pages served

| page | what it shows from this ADR |
|---|---|
| `errors` | raise, `None` or a result, on `country_of`: C-05 gives `NoCountry`, C-07 gives `UnknownCustomer`; `None` cannot tell them apart |
| `parse-dont-validate` | `Ok[ParsedLine] \| Err[Reject]` on the till's file (ADR 0012) |
| `state-machine` | `IllegalTransition` when O-106 is shipped |
| `idempotency` | `KeyReused` when PAY-1 comes back with another amount |
| `unit-of-work` | `UnknownProduct` on P-99 rolls the whole order back |
| `decorators-and-middleware` | the API's handlers turning a `ShopError` into a status in one place |
