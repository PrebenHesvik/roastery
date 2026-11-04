# 0013. Wiring and the API

Status: accepted, 2026-11-04 (step 6.2, decision C14, and the bootstrap)

## Context

The app has ports with two adapters each: memory and sqlite stores, `FakeProvider` and the SDK-backed provider, `FakeFeed` and the simulator's feed, a sequence and a script for ids (ADR 0007). Something has to choose, once, which adapter stands at each port.

Two callers drive the app:

- **the API**, which a web shop and a till would call;
- **the simulator**, which plays three years of trade through the same services.

The `ports-and-adapters` page needs both to call the same service layer, through the same wiring. It explains why the simulator exists: it is the second driving adapter, the one that makes that seam real.

The pages show the API's handlers, its middleware and its idempotency store. A framework would hide them, and add a dependency (ADR 0002). Plan 6.3 builds no API; the pages still need its home named now (C14).

The DevOps route (phase 8) adds a feature flag, `vat-by-country`, asked per customer country. The flag must be something a test can set, not a call to a service.

## Decision

### One `wire`

`bootstrap.py` is the one place that wires. Nothing in `roastery` imports it but the very edge (the entry point, a test, the simulator).

```python
def wire(
    settings: Settings,
    store: Store,
    *,
    clock: Clock,
    ids: Ids,
    source: Source,
    feed: StatusFeed,
    provider: PaymentProvider,
) -> App:
    """The services on the store, the same for every caller.

    Takes a unit of work from the store, stamping `source`;
    makes the bus and subscribes the handlers; puts the price
    cache in front of the prices for settings.price_ttl; puts
    retry and the breaker around the provider; and binds the
    jobs to the store, the feed and the batch size.
    """
    ...
```

`App` holds the services and the jobs of contract B (ADR 0011). `wire` is the same for every caller; what differs is passed in. ADR 0007's sketch of `wire` shows only the arguments it owns; this is the whole signature.

| argument | API | simulator | a test or a walk |
|---|---|---|---|
| `store` | `sqlite_store(connection)` | one `sqlite_store(connection)` or `memory_store()`, shared by its two wirings | `memory_store()` |
| `clock` | the caller's UTC clock | the simulator's clock | `FakeClock` |
| `ids`, `source` | ADR 0007 | ADR 0007 | ADR 0007 |
| `feed` | the caller's feed | the simulator's feed | `FakeFeed` |
| `provider` | `ProviderPayments` on the SDK, from `PROVIDER_URL` and `PROVIDER_KEY` | `FakeProvider` | `FakeProvider` |

`wire` wraps the `PaymentProvider` it is given in `resilience`'s retry and `CircuitBreaker`, so every caller gets the same protected port, whatever stands behind it. A decline (`ProviderRefused`) is never retried; `ProviderUnavailable` is retried, and passes through when the retries run out or the breaker is open (ADR 0011).

`source` and the `Ids` adapter are wiring arguments: ADR 0007 owns them and their two adapters. The domain never sees them.

### Memory and sqlite

```python
def memory_store() -> InMemoryStore:
    """The app's tables as dicts: for a test, or a walk."""
    ...


def sqlite_store(connection: sqlite3.Connection) -> SqliteStore:
    """The app's tables on a connection in sqlite3's default mode.

    The mode is checked first (ADR 0003), then the tables are
    made if they are not there. The caller opens and closes
    the connection.
    """
    ...
```

The two differ in the store and nothing else. Wired on either, the same calls give the same rows: the `ports-and-adapters` page runs both and shows one frame.

### The jobs

The relay and the exports are adapters' functions (`outbox.relay`, `exports`). The service layer cannot import them (ADR 0001), so `wire` binds them: `relay()` calls `outbox.relay(uow, feed, size=settings.relay_batch)` with the wiring's own unit of work. A job takes no clock and no store; both are wired in (C12).

### The API: framework-free handlers

`api.py` holds handlers: a request dict in, a response dict out. A handler reads the request, calls a service on `App`, and turns a `ShopError` into a status (ADR 0006). It maps the provider's port errors too: `ProviderRefused` to 402 and `ProviderUnavailable` to 503 (ADR 0011). No web framework is imported. The rules stay in the service and the core.

```python
type Request = Mapping[str, object]
type Response = Mapping[str, object]


class Deps(Protocol):
    """What a handler needs; App has it."""

    @property
    def checkout(self) -> Checkout: ...


def place_handler(request: Request, deps: Deps) -> Response:
    """POST /orders: 201 with the order, or the error's status."""
    ...
```

- `middleware.py`: `logged`, `timed`, `require_role('staff')`, each a function from a handler to a handler. `timed` reads the `Clock` port.
- `idempotency.py`: the key store; the same key twice gives the stored reply, and the same key with another body is refused.
- `cli.py`: the nightly jobs as a command, for the CronJob. It takes `App` the way a handler does.

All four are built before phase 7.

`cli.py` is in the api row, so it cannot import `bootstrap`. The entry point lives in `bootstrap`:

```python
def main(argv: Sequence[str], env: Mapping[str, str]) -> int:
    """Read the settings, wire on sqlite, run the cli's command.

    The command is given the moment to run at (`--at`): the job
    runs on a fixed clock, so a rerun gives the same rows.
    """
    ...
```

The cli offers the export jobs (`nightly_extract`, `csv_export`). The relay runs where a feed is: the simulator now, the live shop later. Until then `main` wires `fakes.ClosedFeed`, a feed that refuses every batch, so a relay called from the cli loses nothing; its rows wait.

The package's script entry is `roastery = 'roastery.bootstrap:main_from_os'`, which passes `sys.argv[1:]` and `os.environ`. That one line is the only place the environment is read (ADR 0014).

### The simulator, the second driving adapter

The simulator calls `wire` and then the services on `App`, as the API's handlers do. It writes no row of an app table itself. ADR 0007 says how it wires twice over one store.

### Later: FastAPI and the live shop

A FastAPI adapter comes with the live shop plan (plan §8). It is a thin package outside `packages/shop` that turns HTTP into the handlers' dicts and calls them. It brings the wall clock and the real feed with it. Nothing in `roastery` changes for it.

### The flag client, injected

Phase 8's change asks the flag `vat-by-country` with the customer's country. The flag client is a port:

```python
class Flags(Protocol):
    """Feature flags, asked per customer country."""

    def enabled(self, flag: str, country: Country | None) -> bool:
        ...
```

It comes with phase 8, with its two adapters: a fixed set of flags (in `fakes.py`, for tests and the simulator) and the flag service's client. `wire` gets `flags` as a keyword with a default that keeps every flag off, so the simulator's call stays as it is and its data does not change. The flag is never read from the settings or the environment.

6.3 builds no `Flags`: one adapter would be a hypothetical seam.

## Alternatives refused

| alternative | why not |
|---|---|
| A wiring function per caller (`for_api`, `for_simulator`) | They would repeat the wiring, and drift. One `wire`, with what differs as arguments, keeps one place to change. |
| Services build their own adapters | A service that opens its own sqlite connection cannot be run on the memory store or by the simulator. The seam would be gone. |
| A dependency-injection container | A dependency, and it hides the wiring that the `ports-and-adapters` page shows in one function. |
| FastAPI handlers now | A dependency (ADR 0002), and the handlers would be decorators of a framework, not functions the page can call with a dict. |
| The simulator writes the app's tables directly | It would bypass the rules the app enforces, and the data would show a world no app made. The simulator calls the services, like any client. |
| `cli` in the bootstrap row | `cli` is a driving adapter, like `api`. Putting it in bootstrap would let it reach the adapters. `main` in `bootstrap` keeps the arrows inward. |
| The flag as a setting (`ROASTERY_VAT_BY_COUNTRY`) | A setting is read once at start; the change rolls out per country while the app runs. And a test needs to set it without an environment. |

## Consequences

- Every port's adapter is chosen in `wire` or passed to it. A module that makes its own adapter is a review finding.
- The API, the cli and the simulator drive the same `App`; a rule is in the service once.
- The wall clock never enters `packages/shop`: the caller brings it. The cli runs at the moment it is given (ADR 0015).
- Adding `flags` in phase 8 is a new keyword with a default; contract B's callers do not change.

## Pages served

| page | what it shows |
|---|---|
| `ports-and-adapters` | `wire` on the memory store and on sqlite giving the same frame (`orders.placed`); the simulator as the second driving adapter beside the API |
| `layers` | `api` and `cli` calling the service; `bootstrap` the only module that sees every layer |
| `decorators-and-middleware` | `logged`, `timed`, `require_role('staff')` stacked around a handler; the call log |
| `idempotency` | the key store at the API's edge; PAY-1 delivered twice, recorded once (with ADR 0011's `handle_message`) |
| `configuration` | `main` reading the settings once and handing them to `wire` (ADR 0014) |
| `fakes-over-mocks` | `FakeClock`, `FakeProvider` and `FakeFeed` passed to `wire` |
| `observer-and-events` | the handlers subscribed in `wire` |
