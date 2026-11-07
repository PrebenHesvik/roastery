# 0016. The HTTP adapter

Status: accepted by the owner, 2026-11-07 (step 7.0, decisions F1, F2, F4 and F5 of `docs/phase-7/plan.md`)

## Context

Phase 7 puts a storefront in front of the shop (plan §0). The storefront needs HTTP; the shop has none. ADR 0013 placed the pieces: framework-free handlers in `packages/shop` (`api.py`, `middleware.py`, `idempotency.py`), and FastAPI as "a thin package outside `packages/shop`" that turns HTTP into the handlers' dicts. ADR 0002 keeps the framework out of the shop: the shop is stdlib plus tzdata, and data-docs installs whatever it depends on.

ADR 0013 said the API comes "with the live shop", bringing the wall clock, the real feed, the mailer and the carrier client. Phase 7 builds a thinner thing first (plan §0): local only, a sandbox payment, no hosting, no relay (F5). So the adapter is real, but most of its ports still get fakes.

What the built code fixes:

- **Contract B does not move** (plan §1): no new `ShopError`, no field on `App` or `Settings`, no method on a pinned class, no edit to `checkout.py`. `contract_b.txt` and tiny's sha256 stay byte-identical.
- **The shop reads no wall clock** (ADR 0008). `Clock` is a port (`ports.py:650`); the only adapter in the package is `FakeClock`.
- **A unit of work refuses re-entry.** Every unit of work of a store shares one `_Gate` (`uow.py:57`); a second `__enter__` while one is open raises `RuntimeError`. The sqlite store holds one connection.
- **The settings are strict.** `Settings.from_env` (`settings.py:157`) rejects any `ROASTERY_*` name no field reads (`unknown_names`, `settings.py:194`). `Settings` requires `database_url`, `provider_url` and `provider_key` (`settings.py:140`), even when the provider is a fake.
- **Ids are drawn through the `Ids` port** (`ports.py:655`). `SequentialIds` (`repository.py:2530`) keeps its counters in memory, so a new process starts again at 1. `payment` is not an `IdKind` (`ports.py:51`): the provider makes payment ids, not the app.
- **`Customers.register`** (`customers.py:91`) takes the e-mail before it draws the customer id, and `Email` (`customer.py:37`) accepts `example.invalid` only (C25).
- **The catalogue** the shop sells is the simulator's setup (`script.py:651`): categories, P-10 to P-21, the prices, campaigns K-1 and K-2, the opening stock. Its ids are the script's.

## Decision

### Two packages, two halves

| where | module | what |
|---|---|---|
| `packages/shop` (`roastery`) | `api.py` | handlers: a request dict in, a response dict out; `STATUS`; the edge's own errors |
| | `idempotency.py` | the `Keys` protocol, an in-memory twin, `once()` |
| | `middleware.py` | `logged`, `timed` (it reads the `Clock` port) |
| | `storefront.py` | the read side and the quote (ADR 0017), in the service row |
| `packages/api` (`roastery_api`) | `app.py` | FastAPI: routes that parse, take the lock, call a handler, render |
| | `live.py` | the live wiring, below |
| | `clock.py` | `SystemClock`, the one wall clock |
| | `state.py` | the API's own sqlite tables, below |
| | `fx.py` | display rates (ADR 0018) |
| | `openapi.py` | writes the OpenAPI document (ADR 0019) |
| | `__main__.py` | `python -m roastery_api seed` |

`api.py`, `idempotency.py` and `middleware.py` are already rows of `LAYERS` (`architecture.py:64`) and wait in `AWAITING` (`packages/shop/tests/test_architecture.py:21`). ADR 0013 planned them "before phase 7"; they come in 7.1. `cli` stays in `AWAITING`.

`packages/api` depends on `roastery`, `fastapi` and `uvicorn`. `roastery-sim` is a dev dependency only: the `seed` command imports it inside the command, and nothing the server runs imports it. The shop gains no dependency.

### The live wiring

`live.py` builds one wiring per process, as `bootstrap.main` does for the cli (`bootstrap.py:296`):

| port | adapter | why |
|---|---|---|
| store | `sqlite_store(connection, clock=clock, price_ttl=settings.price_ttl)` (`bootstrap.py:188`) | one store, so one price cache (C38) |
| `clock` | `roastery_api.clock.RequestClock` over `SystemClock` (`dt.datetime.now(dt.UTC)`), below | the shop reads no wall clock (ADR 0008); the caller brings it (ADR 0013) |
| `ids` | `state.CountedIds`, below | survives a restart |
| `source` | `'visitor'` (`ports.py:49`) | a live request is a visitor's |
| `feed` | `fakes.ClosedFeed` (`fakes.py:192`) | no relay (F5); outbox rows wait, as under the cli |
| `provider` | `fakes.FakeProvider(refund_ids=())` (`fakes.py:54`) | no real payments (F5); no refunds offered, so no refund id |
| `notifier`, `labels` | `roastery_api.live.LogNotifier`, `LogLabels`: write a log line, keep nothing | `FakeNotifier` and `FakeLabels` (`fakes.py:128`, `fakes.py:142`) keep every call in a list, which grows without end in a server |

`wire` is called once (`bootstrap.py:222`). Beside it, `live.py` builds the `Storefront` on the same store: `Storefront(store.unit_of_work('visitor'), clock, standard_rules().rules)` (`uow.py:240`, `pricing.py:301`), the same call `wire` makes for `Checkout` (`bootstrap.py:253`). The handlers get a small frozen dataclass holding `App` and the `Storefront`; it satisfies the handlers' `Deps` protocols (ADR 0013). `App` gets no field.

**The clock, once per request.** `SystemClock` reads the wall clock. The services get `RequestClock`, which reads `SystemClock` once when a request takes the lock, and returns that moment to every `now()` until the request ends. A checkout re-quotes, registers and places; all three then see the same moment, so the day the quote priced is the day `place` prices (ADR 0017), even across the buyer's midnight. `timed` (middleware) is given `SystemClock` itself, or every request would take no time.

The connection is opened with `check_same_thread=False`. FastAPI runs a plain `def` route on its thread pool, so the thread that calls is not the one that opened. The lock below makes that safe. Every route is a plain `def`, never `async def`, so the lock never blocks the event loop.

### One lock, one worker

`live.py` holds one `threading.Lock` for the process. Every request takes it, reads included, for the whole call: idempotency lookup, the service calls, the key's write.

- The `Storefront`'s unit of work and `App`'s share the store's `_Gate` (`uow.py:57`). Two requests at once would open two units of work, and the second raises `RuntimeError`, a 500. A read is no exception: a quote open while a checkout begins is the same clash.
- uvicorn runs with one worker. A second process has its own lock, its own gate and its own counters; the lock means nothing across processes.
- The cost is throughput, which a local shop does not need. 7.2's done-when includes 20 parallel requests, all answered.

### Settings: `SHOP_API_*`

The shop's settings stay `ROASTERY_*`, read by `Settings.from_env`, unchanged. The API's own names cannot share that prefix: `unknown_names` would reject them. They are `SHOP_API_*`, read once in `roastery_api`'s entry point into its own frozen `ApiSettings`, with the same rule: every problem listed, unknown `SHOP_API_*` names refused.

| name | default | what |
|---|---|---|
| `SHOP_API_STATE_URL` | none (required) | `sqlite:///` and the state db's path |
| `SHOP_API_CORS_ORIGINS` | `http://localhost:5173` | the allowlist, comma-separated |

`ROASTERY_PROVIDER_URL` and `ROASTERY_PROVIDER_KEY` are required by `Settings` though `FakeProvider` reads neither. The dev environment sets placeholders, as `play` does (`play.py:154`): `https://provider.example.invalid` and `not-a-key`. Making them optional would change a field of `Settings`, which contract B pins.

### The state db

A second sqlite file, apart from the shop's. It holds what the shop's data contract must not. Plan 7.2 names the first three tables; `idempotency` and `orphans` are added here, for the key store and F2's log:

| table | columns | why |
|---|---|---|
| `order_links` | `token`, `order_id`, `created_at` | the order's private link. Order ids are sequential and guessable, so they are never the link. `token` is `secrets.token_urlsafe(24)` (32 characters, 192 bits) |
| `guests` | `customer_id`, `name`, `email`, `street`, `postal_code`, `city`, `country`, `created_at` | the guest's real contact and street address (F1, F4). `Customer` holds a postal code and an `example.invalid` e-mail only |
| `counters` | `kind`, `next` | the id counter, below |
| `idempotency` | `scope`, `key`, `body_hash`, `status`, `reply`, `created_at` | the stored replies, below |
| `orphans` | `customer_id`, `reason`, `created_at` | a guest registered whose order was never placed (F2) |

**The id counter.** `state.CountedIds` is the API's `Ids` adapter. Each `next(kind)` reads `counters`, adds one and commits in the state db before it returns. A draw whose shop unit of work then rolls back leaves a gap; a gap is harmless, a repeat is a `DuplicateId`. Its ids have `SequentialIds`' shape, at the same `WIDTHS` (`repository.py:104`). `WIDTHS` has no `payment` or `guest`; 7.2 picks their widths (the script's `PAY-1` is unpadded). The table also counts two kinds that are not `IdKind`s:

- `payment`: the sandbox's `PAY-n` (ADR 0018);
- `guest`: the `<n>` of `guest-<n>@example.invalid`. `register` needs the e-mail before it draws the `CustomerId`, so `<n>` cannot be the customer's number.

The API runs on its own shop db, made by `seed`. Pointing it at a simulator's `month` or `full` db is not supported: its counters would start below the ids already there.

### Guest checkout

Guests have no login (plan §0). Checkout is two service calls, `register` then `place`, because `place` takes a `CustomerId` and contract B is frozen (F2). In order, under the lock:

1. Parse. A client price is never read: the body's items are product ids and quantities, and `Item` is built with `price=None` (`checkout.py:82`). A test in 7.1 sends a price and sees the list price charged.
2. Re-quote with `Storefront.quote` (ADR 0017). If the total differs from the one the client confirmed, answer 409 `PriceChanged` with the new quote. Nothing is written.
3. Stock pre-check from the same quote: a short line answers 409 `OutOfStock` (`errors.py:150`). Nothing is written.
4. `customers.register(name, email=guest-<n>@example.invalid, country=..., postal_code=...)`. The shop's `name` is `Guest <n>`; the real name is in `guests`. It commits.
5. `checkout.place(PlaceOrder(customer_id, 'web', items))`.
6. Write `guests` and `order_links`; reply 201 with the token.

Steps 4 and 5 are two units of work. If `place` refuses (a race the lock rules out, or a bug), the customer stays: a row in `orphans` and a log line. It is not erased. Erasing writes a tombstone to `customer_changes`, which is contract A's data; an orphan is one customer with no orders, which the data already has.

### The seed

`python -m roastery_api seed` fills an empty shop db with the simulator's catalogue. It reuses, it does not copy. The whole seed is in the simulator; the API's command opens the connection, makes the counter and calls it:

- a new `roastery_sim.seed.catalogue(connection, *, then: Ids)` opens a `sqlite_store` on the connection, with a `FakeClock`, and wires it;
- that wiring's ids are `ScriptedIds(script.scripted_ids(steps), then=then)` (`repository.py:2556`, `script.py:470`): the script's ids for categories, products and campaigns, and the API's counter for the rest (the stock's movement ids);
- it runs the setup's steps (`script._setup`, `script.py:651`) through the play's own dispatch (`play._do`, `play.py:381`), the clock moved to each step's moment from `SETUP` (2024-01-01 08:00 UTC), so the seeded rows are the simulator's;
- it runs only when `uow.catalogue.products()` (`ports.py:322`) is empty; otherwise it says so and returns.

`play.play` cannot be reused: it builds its own store, settings and clock (`play.py:154`).

### The endpoints

| method and path | handler | reply |
|---|---|---|
| `GET /products` | `Storefront.products()` | 200, a list |
| `GET /products/{id}` | `Storefront.product(id)` | 200; 404 `UnknownId` |
| `POST /quote` | `Storefront.quote(country, items)` | 200; 422 `UnknownProduct` |
| `POST /checkout` | the guest checkout above; `Idempotency-Key` required | 201 with the token; 409 `PriceChanged`, `OutOfStock`; 422 |
| `POST /sandbox/payments` | ADR 0018; `Idempotency-Key` required | 201 paid; 402 `ProviderRefused`; 503 `ProviderUnavailable` |
| `GET /orders/{token}` | `state` then `Storefront.order(id)` | 200; 404 `UnknownToken` |

`Storefront.product(id)` lets the repository's `UnknownId` (`ports.py:318`) through, which `STATUS` maps to 404: the id is the resource. `quote` turns an unknown id in a body into `UnknownProduct`, 422, as checkout does. Both follow ADR 0006 as it stands.

### Errors: problem+json

Every error is `application/problem+json` (RFC 9457):

```json
{"type": "about:blank", "title": "Out of stock", "status": 409,
 "code": "OutOfStock", "detail": "P-10: 3 asked, 2 on hand"}
```

- `code` is the class name of what was raised. The storefront switches on `code`, never on `title` or `detail`.
- `STATUS` (ADR 0006) maps the `ShopError` family. `api.py` adds the port errors, as ADR 0013 says: `ProviderRefused` (`ports.py:680`) 402 and `ProviderUnavailable` (`ports.py:684`) 503. Its key type widens from `type[ShopError]` to `type[Exception]`.
- The edge's own refusals are plain exceptions, not `ShopError`s: `PriceChanged` (409) in `api.py`, where the checkout handler re-quotes, and `UnknownToken` (404) in `roastery_api.state`, where tokens live. Contract B's test fails if any module but `errors.py` defines a `ShopError`; these are not part of the shop's rules.
- A body that does not parse is a 400 (ADR 0006), with `code` `RequestValidationError`. FastAPI's default 422 for it is replaced: 422 already means `UnknownProduct`, `WrongKind` and `NoPrice`.
- Anything else is a 500 with `code` `InternalError` and no detail. The traceback goes to the log.

### Idempotency

`POST /checkout` and `POST /sandbox/payments` require an `Idempotency-Key` header; a request without it is a 400. `POST /quote` is a read and takes none.

`idempotency.py` defines `Keys` and `once(keys, scope, key, body, call)`; `state.py` gives the sqlite `Keys`. Under the lock:

- a new key: run the call, store its status and reply with a hash of the canonical body;
- the same key and body: the stored reply, not run again;
- the same key, another body: 409 `KeyReused` (`errors.py:104`);
- 2xx and 4xx replies are stored. A 5xx is not, so a retry after an outage runs again.

The scope is the route, so one key on two routes is two entries.

### CORS

FastAPI's `CORSMiddleware` with the `SHOP_API_CORS_ORIGINS` list, methods `GET` and `POST`, headers `Content-Type` and `Idempotency-Key`, no credentials. No wildcard.

## Alternatives refused

| alternative | why not |
|---|---|
| FastAPI inside `packages/shop` | ADR 0002: data-docs installs what the shop depends on, and the `layers` page needs a shop with no framework |
| Route bodies that call `App` directly, without `api.py` | the handlers are what the `decorators-and-middleware` and `idempotency` pages show; a route is only parse, lock, call, render |
| `Storefront` as a field of `App` | a field of `App` changes contract B |
| A connection or a unit of work per request | the price cache is per store (C38), and two stores on one file would race each other's writes; the lock is simpler and enough |
| Several uvicorn workers | each has its own lock and counters; the gate and the counters are per process |
| `SystemClock` straight to the services | the re-quote and `place` would read two moments; across the buyer's midnight they price on two days, and the buyer pays a price never shown |
| `async def` routes | the lock would block the event loop; sqlite here is synchronous anyway |
| API settings under `ROASTERY_*` | `Settings.from_env` rejects names it does not read; adding fields changes contract B |
| `SequentialIds` with starts read from the shop db's highest ids | needs a read per kind at start and knowledge of every table; a counter table is one place, and covers `payment` and `guest` too |
| The order id as the order's link | sequential and guessable: anyone could read anyone's order |
| The guest's real e-mail and address in the shop db | breaks C25 and contract A's columns; the shop's data contract does not move (F1, F4) |
| One transaction for register and place | needs a new call on a pinned class or an edit to `checkout.py` |
| Erasing the orphan customer | writes a tombstone into contract A's change log for a customer nobody saw |
| A seed copied into `packages/api` | two copies of the catalogue drift; the simulator's setup is the one source |
| Importing `roastery_sim` at run time | the server would need the simulator installed; it is a dev dependency |

## Consequences

- `packages/shop` gains three modules in the api row and one in the service row. `contract_b.txt` and tiny's sha256 do not change; 7.1's done-when checks both.
- The API is safe for one process only. Hosting (later) must keep one worker, or replace the lock and the gate with something that spans processes. That is a decision for the live shop.
- Outbox rows pile up under `ClosedFeed` and wait; nothing is lost. The relay comes with the live shop.
- A guest's `customer_changes` row and the order's stamps carry the same moment, since one request reads the clock once. Each service call still reads `now()` once (`architecture.md` §5); it gets the request's moment.
- Every confirmation e-mail and shipping label is a log line. The handlers run as wired (`bootstrap.py:241`).
- An orphan customer is possible and recorded. It shows in `raw_customers` as a guest with no order.
- The shop db holds guests as `Guest <n>` with `guest-<n>@example.invalid`. Exports from it carry no real contact.
- The state db holds personal data: real names, e-mails and street addresses. It is never committed, never exported, and never read by the spec.

## Open points

1. **The seed's private names.** `script._setup` and `play._do` are private; `roastery_sim.seed` uses them inside their own package. If 7.2 prefers public names, the rename must leave tiny's sha256 unchanged.
2. **The guest's shop name.** This ADR writes `Guest <n>` into `customers.name` and keeps the real name in the state db. **Settled 2026-11-07:** the owner chose a pseudonym for both name and e-mail (F1 amended).
3. **Placeholder provider settings.** Required fields of `Settings` are given dummy values. Acceptable for a local API; the live shop replaces `FakeProvider` and gives real ones. **Settled 2026-11-07:** the owner accepted placeholders (F9).
4. **`RequestClock` is not in the plan.** The plan says "a system clock". Without a moment fixed per request, the re-quote and `place` can price on two days (ADR 0017). **Settled 2026-11-07:** the owner accepted one clock reading per request (F8).
5. **ADR 0013 said the handlers were built "before phase 7".** They were not; 7.1 builds them. ADR 0013 is not edited here.

## Pages served

Phase 7 writes no pages (F7). When Design Patterns is planned, this ADR offers:

| page | what it shows |
|---|---|
| `ports-and-adapters` | a third driving adapter: the same `wire` with `SystemClock`, `ClosedFeed`, `FakeProvider` |
| `idempotency` | `once()` and the state db's keys: one checkout for two clicks |
| `decorators-and-middleware` | `logged` and `timed` around a real handler |
