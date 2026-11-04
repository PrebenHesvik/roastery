# Contract C: the architecture of the shop app

This file is the shape of the shop app, `roastery`, before its code is written. The owner reads it before step 6.3 starts. Phase 7 reads it to point the 35 Design Patterns pages at the app's modules. The decisions behind it (C1–C18) are in `docs/phase-6/6.2-architecture.md`. Each choice has its record in `docs/adr/`.

## 1. Layers

Written in U5.

## 2. Module map

Written in U5.

## 3. Pattern map

One row per Design Patterns page, in the order of data-docs' `content/docs/patterns/meta.json`, grouped as the route groups them.

How to read a row:

- **module**: the page's home, `roastery/<module>.py`, named as in ADR 0001's `LAYERS`. "none" means the page has no home; the second table says why.
- **parts**: the top-level names the page will show. They retell what the page shows from `firm` today. They are intended; they freeze only at phase 7's pin (C16).
- **requirement**: what the page's example proves, and with which rows.
- **fit**: strong (the shop has the need on its own), partial (it has it, but something must be added), weak (the need is made up for the page). A partial or weak row says what closes it, or why it stays.

The rows of `pricing_rules`, `subscription_events`, `stock_movements` and `shipments` are new in 1.0. They are in `month` and `full`, not in `tiny`, so a row cites the table, never a row id.

### How does good code think?

| page | module | parts | requirement | fit |
|---|---|---|---|---|
| one-reason-to-change | `vat` | `vat_of`, `scheme_for`; `parsing.parse_line` | A VAT change edits `vat.py` only: phase 8 changes `scheme_for` and the rate rows, not the callers (C10). A new column in the till's file edits `parsing.py` only (C13). The twin's `process(row)` reads, prices, adds VAT and prints the receipt, so the VAT change edits it in four places | strong |
| depend-on-abstractions | `ports` | `OrderRepository` (a Protocol), `OrderStore` (an ABC); `reports.sales_by_customer` | `sales_by_customer` gives the same rows from the memory store and sqlite: C-01 has O-101, O-104 and O-108. The ABC refuses a store with a method missing. The twin's sqlite-bound service must be patched in its test | strong |
| composition-over-inheritance | `pricing` | `with_discount`, `per_rule`; the twin's `PricingRule`, `Subscriber`, `Campaign`, `SubscriberCampaign` | `with_discount(percent, list_price)` wraps the list price with a `pricing_rules` row (subscriber or campaign). Template method: `PricingRule` with hooks. The twin needs a subclass per mix | partial: `pricing_rules` holds each percent (G3 closed), but nothing in the data says two rules stack on one line. The walk states the stacking order as the page's choice |
| pure-core-imperative-shell | `fulfilment` | `order.late_orders` (pure); `Fulfilment.late_shipments` (the shell) | `late_orders(orders, events, today)`: paid or invoiced (S13), not shipped within two working days. A counter sale never ships: O-104 ends at `Paid` (C5). The shell reads the store and `local_date(clock.now(), zone)` (C8). The twin moves "late" to working days and patches the clock | strong |
| errors | `customers` | `UnknownCustomer`, `NoCountry`, `country_of`, `find_customer`; `result.Ok`, `Err`, `partition` | `country_of` returns a `Result` (C6). C-05 is known and has no country; C-07 was erased, yet O-107 names them. `None` cannot tell the two apart. The caller gives C-05's O-105 Norway's rate on purpose, not as a fallback in the lookup (C10) | strong |

### How do I build objects?

| page | module | parts | requirement | fit |
|---|---|---|---|---|
| value-objects | `money` | `Money`, `Qty`; `ids.ProductId`, `ids.PostalCode`, `ids._check_id` | Money adds only to money of its currency: PAY-2 (SEK) plus PAY-3 (DKK) raises. `Qty` refuses 0; only `Checkout.credit_for` makes a negative line (C4, S14). `PostalCode` keeps C-01's 0150. The twin sums bare floats across currencies | strong |
| parse-dont-validate | `parsing` | `ParsedLine`, `Reject`, `parse_line`, `parse_rows`, `reconcile` | The till's file is parsed once into sales (C13). Code 2000000000992 has no product: a `Reject`. Grams only for loose beans (R-5002's 250 g). `reconcile` matches R-5001 to O-104's L-06 by moment and product, and never moves stock. The twin checks grams in three callers and forgets one | strong |
| illegal-states | `order` | `Placed`, `Paid`, `Invoiced`, `Shipped`, `Delivered`, `Cancelled`, `describe` | One class per feed status (C5). `Shipped` and `Delivered` carry how the order is settled, so only a paid order has a payment and an invoiced one ships first (S13). O-106 had a line, L-10, deleted at its cancel (E-12, `line_stamps`). The twin has flags and Optionals | strong |
| factories | `order` | `OrderLine.of`, `.from_payload`, `.at_counter`, `.credit`; `line_for(channel)` | Two real channels: O-101 from the web payload, O-104 at the counter. `at_counter` takes the price rung, so L-06 sells at 549 the day before P-21's list price starts. `credit` is the one way to a negative line (S14). The twin's `__init__(source=...)` branches | strong |
| registries-and-plugins | `pricing` | `Registry`, `standard_rules`, `RULES`, `DuplicateRule`, `UnknownRule` | Rules registered by `pricing_rules.rule_kind`: `list`, `subscriber`, `campaign`. A campaign plugin registers into the registry it is given. A name twice raises | strong: `pricing_rules` closes G3 |

### Where do I put a seam?

| page | module | parts | requirement | fit |
|---|---|---|---|---|
| adapter | `provider` | `ports.PaymentProvider`, `ProviderUnavailable`, `ProviderRefused`; `provider_sdk.ProviderClient`; `ProviderPayments`, `to_money` | The SDK speaks camelCase and minor units: PAY-2's 516.98 SEK is 51698. `ProviderPayments` gives `Money`. The leak: minor units, or the refund window. The twin: SDK v2 renames `amountMinor` | strong for the translation; the error mapping needs an outbound call (see retry) |
| facade | `checkout` | `Checkout`, `Checkout.place`, `money.to_ore` | `place(PlaceOrder)`: the gross price on the day (one for every buyer, C10), the VAT share stored (C18), the order id from `Ids` (C7), the sold movement, the outbox row. O-101's total is 1157.00, PAY-1's amount. The twin has three totals | strong |
| decorators-and-middleware | `middleware` | `logged`, `timed`, `require_role`, `stack`; `api.credit_handler` | `require_role('staff')` around the credit handler: a return is staff work (S14). Built framework-free before phase 7 (C14). The twin copies timing into each handler | strong (generic) |
| repository | `repository` | `ports.OrderRepository`; `InMemoryOrderRepository`, `SqliteOrderRepository`, `create_tables` | Objects in, objects out, on both stores. `all()` lists O-101 to O-108 by `order_id`, whatever the order of insert (C17). A second O-101 raises `DuplicateId` (C7). The twin puts SQL in the service | strong |
| unit-of-work | `uow` | `ports.UnitOfWork`; `SqliteUnitOfWork`, `InMemoryUnitOfWork`; `Checkout.place` | One commit holds the order, its lines, the `sold` stock movement and the outbox row (C3). An unknown product (P-99) rolls all of it back. The twin keeps an order with no lines | strong |

### How does behaviour vary?

| page | module | parts | requirement | fit |
|---|---|---|---|---|
| strategy | `pricing` | `list_price`, `subscriber`, `campaign`, `price_lines`, `rule_named`, `RULES` | `list_price` reads `prices` on the order day: P-10 is 119, then 129 from 1 October. P-21 has no list price on 6 October, so `list_price` fails for L-06. `subscriber` and `campaign` take their percent from `pricing_rules`. An unknown name fails loudly | strong: `pricing_rules` closes G3. K-1 and K-2 run outside 5–9 October, so no teaching-week line has a discount |
| command | `commands` | `Subscribe`, `Skip`, `Pause`, `Resume`, `Cancel`; `apply`, `replay`, `CommandLog`; `Subscriptions` runs them | Each command carries its reason (`subscription_events`). Replaying the log from nothing gives the periods: S-2 stopped 1 August 2025, S-3 began a month later. Undo is retold: the shop answers a pause with a `Resume`, a new event. The twin writes audit text by hand | strong: `subscription_events` holds pause and skip |
| state-machine | `order` | `TRANSITIONS`, `IllegalTransition`, `check`, `ship`, `transitions` | `TRANSITIONS` keyed on the six statuses (C5): O-101 goes placed, paid, shipped, delivered (E-01 to E-04). Shipping O-106 after its cancel (E-12) raises. An invoiced order ships before it is paid (S13). A return is a credit order, not a state (S14). The twin has ifs in five handlers | strong |
| pipelines-and-generators | `pipeline` | `read`, `to_rows`, `with_vat`, `to_csv`, `pipe`, `Trace` | `exports.py` writes the csv export through these stages, lazily. A stop after two lines (L-01, L-02) builds two. The export's faults are added after it (D10). The twin builds three years of `full` as lists | strong: the app writes the export (G6 closed) |

### How do parts talk across a boundary?

| page | module | parts | requirement | fit |
|---|---|---|---|---|
| observer-and-events | `events` | `Event`, `OrderPaid`, `StatusChanged`, `EventBus`, `HandlersFailed`; `Payments.handle_message` | PAY-1 makes O-101 paid (E-02). Handlers subscribed in `bootstrap` (C9) write the `StatusChanged` outbox row and queue the confirmation (the worker queue-and-worker shows). Stock is not a handler: it moved at `place` (O-107, never paid, took a P-10 bag on 7 October). One handler raises; the others run. The twin's `handle_message` imports every handler | strong |
| outbox | `outbox` | `SqliteOutbox`, `relay`; `uow.SqliteUnitOfWork`; `ports.StatusFeed`; `fakes.FakeFeed` | The status change and its outbox row commit together (C3). `relay` sends batches of `RELAY_BATCH` rows; the feed stamps `loaded_at` (C9). E-08's batch failed on 8 and 9 October and went on the 10th, while later batches went (E-04, E-13). E-09's batch failed and went after E-10's, so E-10 loaded first (G15) | strong |
| idempotency | `payments` | `Payments.handle_message`, `PaymentMessage`; a `ShopError` for a mismatched redelivery (U4 names it); `idempotency.digest`, `IdempotencyStore`, `KeyReused` | The provider redelivered PAY-1. `handle_message` keyed on `payment_id` records it once and returns the stored reply (C12). PAY-1 again with another amount raises a `payments` error (C6); `KeyReused` belongs to the API's key store in `idempotency.py`, which `payments` may not import (ADR 0001) | strong (G5 pinned) |
| cache-aside | `cache` | `ports.PriceCache`, `CachedPrices`, `price_key`, `DictCache`; `fakes.FakeClock` | A list price read often, changed rarely (`prices`). The TTL is `PRICE_TTL` (C15). P-10 changes on 1 October; a stale entry prices a cart at 119. The twin's cache is never told of `set_price` | weak: a small shop has no load that needs a cache. It stays weak: the stale price at checkout is the honest reason |
| retry-and-circuit-breaker | `resilience` | `Transient`, `retry`, `delay`, `CircuitBreaker`; `fakes.FakeProvider` | A call to the provider retried with backoff and the same idempotency key, so a retry cannot charge twice. A breaker opens when the provider is down. A decline (402) is never retried. Jitter is seeded (C17) | partial: contract B's payment calls are all inbound. The outbound call (the refund of S14's credit, or a capture) must be named in U4 |
| queue-and-worker | none | none: the page shows files, never runs them | The order confirmation and the shipping label made by a worker after `OrderPaid` | strong (shown) |

### How do I shape an app?

| page | module | parts | requirement | fit |
|---|---|---|---|---|
| layers | `architecture` | `LAYERS`, `INWARD`, `import_graph`, `check_direction`, `unplaced`; `api.place_handler`; `bootstrap.in_memory` | The check on `roastery` itself (`modules.layers`). The violation: a scratch copy of `pricing.py` imports `repository`, core to adapters (ADR 0001) | strong |
| ports-and-adapters | `bootstrap` | `App`, `wire`, `in_memory`, `with_sqlite`; `api.place_handler` | Memory and sqlite wiring give the same frame for O-101. The second driving adapter is the simulator: it wires the app as `scripted` and as `simulator` over one store; the API wires `visitor` (C7) | strong |
| cqrs-lite | `reports` | `kind_of_line`, `sales_by_kind`, `SALES_BY_COUNTRY`, `sales_by_country` | The read side returns rows, never frames (C2). Beans (P-10, P-11) against equipment (P-20, P-21). C-05's O-105 counts under no country: C10's Norway is a VAT rule, not a fact about the customer. The write side is untouched | strong |
| configuration | `settings` | `Settings`, `PARSERS`, `SettingsError`, `unknown_names`, `url`; `bootstrap.wire` | `ROASTERY_*` read once, typed: `DATABASE_URL`, `PROVIDER_URL`, `PROVIDER_KEY` (out of the repr), `PRICE_TTL`, `SHOP_ZONE`, `RELAY_BATCH` (C15). VAT is a table, not a setting (C10) | strong |

### How do I test the design?

| page | module | parts | requirement | fit |
|---|---|---|---|---|
| fakes-over-mocks | `fakes` | `FakeProvider`, `FakeClock`; `repository.InMemoryOrderRepository`; `Fulfilment.late_shipments` | `FakeProvider` declines one card and redelivers a message, as the provider did with PAY-1. A mock passes wrongly: it takes kroner where the SDK wants minor units | strong |
| contract-tests | `contracts` | `check_order_repository`, `all_is_ordered`; `ports.OrderRepository` | The same suite on the memory and sqlite stores (C17). A fake that lists in insertion order fails `all_is_ordered`. The provider fake against a sandbox is said in words | strong |

### Why does it hurt?

| page | module | parts | requirement | fit |
|---|---|---|---|---|
| god-object | none | the twin's `ShopManager`; it reuses `CachedPrices`, `Checkout`, `ProviderPayments`, `parse_rows` | One class reads the till file, keeps orders, prices, caches prices, takes payments and writes the export. A discount field set at checkout changes the export | strong |
| anaemic-model | none | the twin's `Order`, `ShippingService`, `RefundService`; for contrast `order.Paid`, `order.ship` | `Order` has a public `status`. `ShippingService` ships only paid or invoiced orders (S13). `RefundService` credits anything not cancelled, so O-107, never paid, gets a credit. In the app, `credit_for` refuses it (S14) | strong |
| premature-pattern | none | the twin's `price_overbuilt`, `ShippingStrategyFactory`, `ShippingEngineBuilder`; for contrast `pricing.price_lines` | Shipping built as a strategy, a factory and a builder for one flat fee to all four countries; pricing earned its strategy | partial: no table holds a shipping fee, and every payment equals its lines (PAY-1 is O-101's 1157.00). Closed if the fee is 0 to all four countries: the overbuilt engine computes a constant |

### Practise

| page | module | parts | requirement | fit |
|---|---|---|---|---|
| recall | none | none | Every card checked again; keys renamed to the shop | none: it follows the other pages |

### The twins, and the pages with no home

The twin stays in data-docs (C1). Its file name is the one the page uses today; phase 7 renames it with the page.

| page | twin in data-docs, or the reason |
|---|---|
| one-reason-to-change | `without/god_function.py` |
| depend-on-abstractions | `without/service.py` |
| composition-over-inheritance | `without/billing_inheritance.py` |
| pure-core-imperative-shell | `without/clock.py` |
| errors | `without/errors.py` |
| value-objects | `without/values.py` |
| parse-dont-validate | `without/parsing.py` |
| illegal-states | `without/timesheet.py` |
| factories | `without/factories.py` |
| registries-and-plugins | none; the without walk builds it |
| adapter | `without/payroll.py`, `without/vendor_v2.py` |
| facade | `without/invoicing.py` |
| decorators-and-middleware | `without/middleware.py` |
| repository | `without/service.py` |
| unit-of-work | `without/uow.py` |
| strategy | `without/billing.py` |
| command | `without/commands.py` |
| state-machine | `without/timesheet.py` |
| pipelines-and-generators | `without/pipeline.py` |
| observer-and-events | `without/events.py` |
| outbox | `without/outbox.py` |
| idempotency | `without/idempotency.py` |
| cache-aside | `without/cache.py` |
| retry-and-circuit-breaker | `without/resilience.py` |
| queue-and-worker | no module: shown only (CodeRead, Diff); no walk runs it |
| layers | `without/api.py` |
| ports-and-adapters | `without/api.py` |
| cqrs-lite | `without/reports.py` |
| configuration | `without/settings.py` |
| fakes-over-mocks | none; the without walk builds the mock |
| contract-tests | `without/drifting_fake.py` |
| god-object | no module: the twin `without/firm_manager.py` is the subject |
| anaemic-model | no module: the twin `without/anaemic.py` is the subject |
| premature-pattern | no module: the twin `without/overbuilt.py` is the subject |
| recall | no module: decks of cards, no code |

### What changed from map §1

Each row of map §1 (`map-patterns-devops.md`) that this map changes, and why.

- **one-reason-to-change**: the second change is a column of the till's file, not of the export (C13, G6).
- **composition-over-inheritance**: still partial, for a new reason. The percents are in `pricing_rules` (G3 closed); stacking two rules is not in the data.
- **pure-core-imperative-shell**: "paid" becomes "paid or invoiced" (S13, C5); today is a local date by zone (C8).
- **errors**: C-05 gets Norway's rate from the caller, explicitly (C10). The error is a `Result` (C6).
- **value-objects**: `Qty` is any whole number but 0, negative only through `credit_for`, not "1 or more" (C4, S14). Home is `money`; the ids are in `ids`.
- **parse-dont-validate**: reads the till's file and reconciles it with the shop orders (C13). Partial becomes strong.
- **illegal-states**: six states with `Invoiced`, settlement carried (C5, S13). The G1 conflict is gone: O-106 had L-10, deleted at its cancel.
- **factories**: adds `credit` (S14); `at_counter` takes the price rung (ADR 0004).
- **registries-and-plugins**: partial becomes strong (`pricing_rules`, S12).
- **adapter**: fit qualified: the error mapping waits for an outbound call.
- **facade**: order id from `Ids` (C7); one gross price (C10); `vat_amount` stored (C18); a `sold` movement replaces "stock reserved" (§2, `stock.py`).
- **decorators-and-middleware**: the refund handler becomes the credit handler (S14); built before phase 7 (C14).
- **unit-of-work**: "stock reservation" becomes the `sold` movement; `stock_movements` has no reservation.
- **strategy**: partial becomes strong (`pricing_rules`). One gross price for every buyer (C10).
- **command**: `Stop` becomes `Cancel`; `Skip` is added; each carries a reason. Partial becomes strong (`subscription_events`).
- **state-machine**: six statuses (C5); returns are credit orders, not a state (S14).
- **pipelines-and-generators**: "strong if it writes" is settled: `exports.py` writes through `pipeline.py` (6.2's module map).
- **observer-and-events**: no warehouse (S10) and no subscription bag booked as an order (D11). The handlers write the outbox row and queue the confirmation (C9); stock moves at `place`, not at paid.
- **outbox**: the cause of E-10 before E-09 is G15, not "G17", fixed by C9's batches; E-08 is a batch that failed two days running (C9). 6.2 §5's default, "the relay does not run 8–9 October", contradicts E-04 and E-13, loaded on those days.
- **idempotency**: G5 is pinned: `handle_message` keyed on `payment_id` (C12).
- **retry-and-circuit-breaker**: strong becomes partial: contract B has no outbound provider call yet.
- **layers**: the violation imports `repository`, not sqlite, since the graph holds only `roastery` (ADR 0001).
- **ports-and-adapters**: the simulator wires the app twice, by `source` (C7).
- **cqrs-lite**: rows, never frames (C2); C-05 stays under no country.
- **configuration**: adds `ROASTERY_RELAY_BATCH` (C15, C9).
- **anaemic-model**: shipping allows invoiced orders (S13); a refund is a credit (S14).
- **premature-pattern**: strong becomes partial: no fee exists in the data.
- **god-object, anaemic-model, premature-pattern, queue-and-worker, recall**: named "no module" with a reason; map §1 gave none.

### Pages whose requirement the new app changes

Phase 7 writes these walks anew, not only renamed:

- **illegal-states** and **state-machine**: six states; an invoiced order ships before it is paid.
- **parse-dont-validate**: the till's file, reconciled against shop orders.
- **command**: skip, pause, resume and cancel, each with a reason; undo retold as a resume.
- **value-objects** and **factories**: a negative `Qty` only through `credit`.
- **errors**: `NoCountry` answered with Norway's rate by the caller.
- **facade** and **unit-of-work**: the `Ids` port, the VAT share stored, the `sold` movement.
- **outbox**: batches, and a failed batch that waits while later ones go.
- **observer-and-events**: the handlers are the outbox row and the queued confirmation; stock moves at `place`.
- **strategy**, **registries-and-plugins**, **composition-over-inheritance**: percents from `pricing_rules`, not constants.
- **anaemic-model**: a credit, not a refund.
- **premature-pattern**: a fee the data must hold (or 0).
- **retry-and-circuit-breaker**: waits on the outbound call U4 names.

## 4. Choices

Written in U5.

## 5. Contract B

Written in U4.
