# Contract C: the architecture of the shop app

This file is the shape of the shop app, `roastery`, before its code is written. The owner reads it before step 6.3 starts. Phase 7 reads it to point the 35 Design Patterns pages at the app's modules. The decisions behind it (C1–C24) are in `docs/phase-6/6.2-architecture.md`. Each choice has its record in `docs/adr/`.

## 1. Layers

Imports point inward: a module may import only the modules of its own layer and of the layers `INWARD` lists for it. The service and the adapters both stand on the ports and never import each other; only `bootstrap` sees them all, and only the adapters and `bootstrap` see the vendor.

A layer is a row of `LAYERS`, not a folder: `roastery` is one flat package. `architecture.py` reads these two tables, and `check_direction` fails on an import that points outward (ADR 0001, ADR 0015).

```python
PACKAGE: Final = 'roastery'
"""The package whose modules the graph holds."""

LAYERS: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        'core': (
            'catalogue',
            'clock',
            'commands',
            'errors',
            'events',
            'ids',
            'money',
            'order',
            'parsing',
            'pipeline',
            'pricing',
            'result',
            'subscription',
            'vat',
        ),
        'ports': ('ports',),
        'vendor': ('provider_sdk',),
        'adapters': (
            'cache',
            'exports',
            'fakes',
            'outbox',
            'provider',
            'repository',
            'resilience',
            'uow',
        ),
        'service': (
            'checkout',
            'customers',
            'fulfilment',
            'listing',
            'payments',
            'reports',
            'stock',
            'subscriptions',
        ),
        'api': ('api', 'cli', 'idempotency', 'middleware'),
        'bootstrap': ('bootstrap', 'settings'),
        'checks': ('architecture', 'contracts'),
    }
)
"""The modules of each layer, sorted; a module is in one row."""
```

```python
INWARD: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        'core': ('core',),
        'ports': ('core', 'ports'),
        'vendor': ('vendor',),
        'adapters': ('core', 'ports', 'vendor', 'adapters'),
        'service': ('core', 'ports', 'service'),
        'api': ('core', 'ports', 'service', 'api'),
        'bootstrap': (
            'core',
            'ports',
            'vendor',
            'adapters',
            'service',
            'api',
            'bootstrap',
        ),
        'checks': ('core', 'ports', 'checks'),
    }
)
"""The layers each layer may import: its own and those inside it.

The service and the adapters both stand on the ports, and neither
imports the other. Only adapters and bootstrap see the vendor.
"""
```

## 2. Module map

40 modules, in the order of `LAYERS`: the layers from the inside out, and the modules of each layer sorted by name. The last column is the ADR that owns the module.

| module | layer | its job | ADR |
|---|---|---|---|
| `catalogue` | core | `Product`, `Kind`, `BeanDetails`, `EquipmentDetails`, the category path | [0004](adr/0004-domain-types.md) |
| `clock` | core | `local_date(now, zone)` and the zone of each country: days from moments, as a pure function | [0008](adr/0008-the-clock.md) |
| `commands` | core | the subscription commands as data; apply, replay, the command log | [0011](adr/0011-contract-b.md) |
| `errors` | core | `ShopError` and its 17 members, the one closed family | [0006](adr/0006-errors.md) |
| `events` | core | `OrderPlaced`, `OrderPaid`, `StatusChanged`; the in-process `EventBus` | [0009](adr/0009-events-outbox-relay.md) |
| `ids` | core | the id value types: `CustomerId`, `ProductId`, `CategoryId`, `OrderId`, `LineId`, `EventId`, `Country`, `PostalCode`, `AccountKind` | [0004](adr/0004-domain-types.md) |
| `money` | core | `Money(amount, currency)` on `Decimal`, `Qty`, rounding to the øre | [0004](adr/0004-domain-types.md) |
| `order` | core | `OrderLine`, one class per feed status, `TRANSITIONS` | [0005](adr/0005-order-states.md) |
| `parsing` | core | payloads and till rows into `ParsedLine` or `Reject` | [0012](adr/0012-outside-systems-and-the-till.md) |
| `pipeline` | core | the export's stages as generators | [0001](adr/0001-flat-package-and-layers.md) |
| `pricing` | core | `Rule`, `list_price`, `subscriber`, `campaign`, the rule registry | [0001](adr/0001-flat-package-and-layers.md) |
| `result` | core | `Ok`, `Err`, `partition` | [0006](adr/0006-errors.md) |
| `subscription` | core | `Subscription`, its periods, `bags_due(on)` | [0011](adr/0011-contract-b.md) |
| `vat` | core | `vat_of`, `scheme_for`, the rate rows' type | [0010](adr/0010-vat.md) |
| `ports` | ports | every port, with the errors of the ports | [0003](adr/0003-persistence.md) |
| `provider_sdk` | vendor | the payment provider's SDK stand-in: camelCase, minor units, `ProviderApiError` | [0002](adr/0002-no-dependencies.md) |
| `cache` | adapters | the price cache in front of the price store, with its TTL | [0013](adr/0013-wiring-and-the-api.md) |
| `exports` | adapters | the csv export (`raw_*`) and the customer extract, written through `pipeline` | [0003](adr/0003-persistence.md) |
| `fakes` | adapters | the working fakes: `FakeClock`, `FakeProvider`, `FakeFeed`, `ClosedFeed` | [0013](adr/0013-wiring-and-the-api.md) |
| `outbox` | adapters | outbox rows in memory and in sqlite; `relay` in batches to the `StatusFeed` | [0009](adr/0009-events-outbox-relay.md) |
| `provider` | adapters | the `PaymentProvider` port on the SDK: minor units to `Money`, SDK errors to port errors | [0002](adr/0002-no-dependencies.md) |
| `repository` | adapters | every store twice, memory and sqlite; the schema; the `Ids` adapters | [0003](adr/0003-persistence.md) |
| `resilience` | adapters | retry with backoff, `CircuitBreaker` | [0013](adr/0013-wiring-and-the-api.md) |
| `uow` | adapters | the two `Store` adapters and their units of work, memory and sqlite | [0003](adr/0003-persistence.md) |
| `checkout` | service | `Checkout`: place, cancel, `credit_for` (the facade) | [0011](adr/0011-contract-b.md) |
| `customers` | service | `Customers`: register, change, erase | [0011](adr/0011-contract-b.md) |
| `fulfilment` | service | `Fulfilment`: ship, deliver, `late_shipments` | [0011](adr/0011-contract-b.md) |
| `listing` | service | `Catalogue`: categories, products, prices, rules, campaigns | [0011](adr/0011-contract-b.md) |
| `payments` | service | `Payments`: a provider message handled once, invoice, settle | [0011](adr/0011-contract-b.md) |
| `reports` | service | the read side: rows, never frames | [0002](adr/0002-no-dependencies.md) |
| `stock` | service | `Stock`: the movements (roast, write-off) and the count at close | [0011](adr/0011-contract-b.md) |
| `subscriptions` | service | `Subscriptions`: the commands run, with a reason each | [0011](adr/0011-contract-b.md) |
| `api` | api | handlers: a request dict in, a response dict out; `ShopError` to statuses | [0013](adr/0013-wiring-and-the-api.md) |
| `cli` | api | the nightly jobs as a command, for the CronJob | [0013](adr/0013-wiring-and-the-api.md) |
| `idempotency` | api | the key store: the same key twice, one effect | [0013](adr/0013-wiring-and-the-api.md) |
| `middleware` | api | `logged`, `timed`, `require_role` around a handler | [0013](adr/0013-wiring-and-the-api.md) |
| `bootstrap` | bootstrap | the one place that wires: `wire`, the two stores, `main` | [0013](adr/0013-wiring-and-the-api.md) |
| `settings` | bootstrap | `ROASTERY_*` read once into `Settings` | [0014](adr/0014-settings.md) |
| `architecture` | checks | `import_graph`, `LAYERS`, `INWARD`, `check_direction`, `unplaced` | [0015](adr/0015-checks-and-names.md) |
| `contracts` | checks | the store promises, run on both stores | [0015](adr/0015-checks-and-names.md) |

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

One line per decision record in `docs/adr/`: the choice in a few words, and the decisions it settles.

- [0001](adr/0001-flat-package-and-layers.md): a flat package; a layer is a row of `LAYERS`, not a folder (C1, C14, C20, C24).
- [0002](adr/0002-no-dependencies.md): the standard library plus `tzdata`; rows out, frames stay in data-docs (C2, C19).
- [0003](adr/0003-persistence.md): `sqlite3` repositories with a memory twin; a unit of work that holds the outbox row (C3).
- [0004](adr/0004-domain-types.md): frozen dataclasses, id types, `Money`, a `Qty` that is never zero (C4).
- [0005](adr/0005-order-states.md): six classes keyed on the feed's statuses; the settlement carried; undoing a sale is a `sold` movement (C5, C21, C22).
- [0006](adr/0006-errors.md): the closed `ShopError` family in `errors.py`; `Result` for questions with two kinds of answer (C6, C20).
- [0007](adr/0007-ids-and-provenance.md): an `Ids` port with two adapters; `source` as a wiring argument (C7).
- [0008](adr/0008-the-clock.md): `now()` in UTC; local dates by zone as a pure function; `tzdata` for the zones (C8, C19).
- [0009](adr/0009-events-outbox-relay.md): an in-process bus; outbox rows; batches; a failed batch waits (C9).
- [0010](adr/0010-vat.md): dated rate rows; one gross price; `scheme_for(order, on)`; no country means Norway, explicitly (C10, C18, C22).
- [0011](adr/0011-contract-b.md): contract B: services on `App`, commands, jobs; a snapshot test pins it at 6.4 (C12, C23, C24).
- [0012](adr/0012-outside-systems-and-the-till.md): what the simulator writes alone; the till file is reconciled, never stocked (C11, C13, C21).
- [0013](adr/0013-wiring-and-the-api.md): one `bootstrap.wire`; the simulator as the second driving adapter; framework-free handlers (C14).
- [0014](adr/0014-settings.md): `ROASTERY_*`, read once and typed; VAT never a setting (C15, C19).
- [0015](adr/0015-checks-and-names.md): `architecture.py`, `contracts.py`, the teachability test; module names frozen now, parts at the phase 7 pin (C16, C17).

## 5. Contract B

Contract B is what the simulator calls on the app: the services on `App`, the two commands, the jobs, and the errors each call raises. It is decision C12; the record is ADR 0011. 6.3 builds it, and 6.4 freezes it at its tag. After `roastery-data 1.0`, a change to it is a new data version.

How to read it:

- One class per service module (ADR 0001's `LAYERS`). The services on `App` are `Customers`, `Catalogue`, `Checkout`, `Payments`, `Fulfilment`, `Subscriptions` and `Stock`; the jobs are on `App.jobs`.
- No call takes an id for a row the app makes, a `source`, or a clock. Ids come through the `Ids` port, and `source` is a wiring argument (ADR 0007). Every stamp is `clock.now()` once per call. A day is `local_date(now, zone)`: the order's zone for an order (ADR 0008), the shop's zone (`ROASTERY_SHOP_ZONE`) for the shop's own days.
- A command is a frozen dataclass only where it carries lines (`PlaceOrder`) or mirrors a row another system wrote (`PaymentMessage`). Other calls take keyword arguments.
- Every call writes in one unit of work and raises a member of `ShopError` when the shop refuses it. When it raises, nothing is written (ADR 0006).
- The bodies are `...`. Docstrings say what a call writes; the table after the block says what it raises.

```python
"""Contract B: the calls the simulator makes on App (C12)."""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from roastery.catalogue import BeanDetails, EquipmentDetails
from roastery.ids import (
    AccountKind,
    CategoryId,
    Country,
    CustomerId,
    LineId,
    OrderId,
    PaymentId,
    PostalCode,
    ProductId,
    ShipmentId,
    SubscriptionId,
)
from roastery.money import Money, Qty
from roastery.order import Channel, Invoiced, Placed
from roastery.outbox import Relayed


# roastery/checkout.py ------------------------------------------


@dataclass(frozen=True)
class Item:
    """One line asked for.

    price None: the list price on the order's day, with the
    rules that hold. A price given: set by hand, as the till
    rang it (L-06 at 549.00) or a free sample (L-12 at 0.00).
    """

    product_id: ProductId
    qty: Qty                     # 1 or more
    price: Money | None = None


@dataclass(frozen=True)
class PlaceOrder:
    """An order on the web or at the counter (channel 'shop')."""

    customer_id: CustomerId
    channel: Channel
    items: tuple[Item, ...]      # one or more


class Checkout:
    def place(self, command: PlaceOrder) -> Placed | Invoiced:
        """The order, its lines, a sold movement per line, the
        VAT share and the outbox rows, in one unit of work.

        A business account's order is invoiced in the same
        unit of work (S13): placed and invoiced, two events.
        """
        ...

    def cancel(self, order_id: OrderId, *, reason: str) -> None:
        """Cancelled; its lines marked deleted; each line's bag
        back as a sold movement of the opposite sign (C21)."""
        ...

    def credit_for(
        self, order_id: OrderId, *, line_id: LineId
    ) -> OrderId:
        """A credit order at the counter: one negative line for
        the line returned, its bag back (C21); placed (S14)."""
        ...


# roastery/payments.py ------------------------------------------


@dataclass(frozen=True)
class PaymentMessage:
    """One message of the provider: a row of payments."""

    payment_id: PaymentId
    order_id: OrderId
    amount: Money                # negative for a refund (S14)
    paid_on: dt.date


@dataclass(frozen=True)
class Receipt:
    """The stored reply: the same for every delivery."""

    payment_id: PaymentId
    order_id: OrderId
    status: str                  # the order's feed word after it


class Payments:
    def handle_message(self, message: PaymentMessage) -> Receipt:
        """Recorded once, keyed on payment_id. A placed order
        is paid; a refund to a credit order pays it; a refund
        to a cancelled order is recorded with no event."""
        ...

    def invoice(self, order_id: OrderId) -> None:
        """A consumer's placed order put on invoice (S13)."""
        ...

    def settle(self, message: PaymentMessage) -> Receipt:
        """An open invoice paid: a payment, no status event."""
        ...

    def refund(self, order_id: OrderId) -> PaymentId:
        """The one outbound call: the money back, asked of the
        provider for a credit order (from the sale it returns)
        or a cancelled paid order. Key 'refund-<order_id>',
        retried; a decline is never retried. Writes nothing:
        the provider's message comes to handle_message."""
        ...


# roastery/fulfilment.py ----------------------------------------


class Fulfilment:
    def ship(
        self, order_id: OrderId, *, promised_by: dt.date
    ) -> ShipmentId:
        """Shipped, and a shipments row. No stock movement:
        the bags left at place."""
        ...

    def deliver(self, shipment_id: ShipmentId) -> None:
        """Delivered; delivered_on on the shipments row."""
        ...


# roastery/customers.py -----------------------------------------


class Customers:
    def register(
        self,
        name: str,
        *,
        country: Country | None,
        postal_code: PostalCode | None,
        account_kind: AccountKind = 'consumer',
    ) -> CustomerId:
        """A customer, joined today; an insert change row."""
        ...

    def change(
        self,
        customer_id: CustomerId,
        *,
        country: Country | None,
        postal_code: PostalCode | None,
    ) -> None:
        """A move; an update change row."""
        ...

    def erase(self, customer_id: CustomerId) -> None:
        """Gone, a tombstone row; orders keep the id. Open
        subscriptions are cancelled, reason 'erased'."""
        ...


# roastery/subscriptions.py -------------------------------------


class Subscriptions:
    def subscribe(
        self, customer_id: CustomerId, *, product_id: ProductId
    ) -> SubscriptionId:
        """One bag a month of beans, started today."""
        ...

    def skip(
        self, subscription_id: SubscriptionId, *, reason: str
    ) -> None:
        """No bag in this month."""
        ...

    def pause(
        self, subscription_id: SubscriptionId, *, reason: str
    ) -> None:
        """No bag until it is resumed."""
        ...

    def resume(
        self, subscription_id: SubscriptionId, *, reason: str
    ) -> None:
        ...

    def cancel(
        self, subscription_id: SubscriptionId, *, reason: str
    ) -> None:
        """Ended today."""
        ...


# roastery/stock.py ---------------------------------------------


class Stock:
    def roast(self, product_id: ProductId, *, bags: Qty) -> None:
        """A roasted movement: bags in."""
        ...

    def write_off(
        self, product_id: ProductId, *, qty: Qty
    ) -> None:
        """A written_off movement: qty out."""
        ...

    def stocktake(
        self, product_id: ProductId, *, on_hand: int
    ) -> None:
        """A counted movement of the difference found, if any.
        Equipment comes in this way (no reason fits better)."""
        ...

    def buy_green(
        self, *, origin: str, kg: Decimal, nok_per_kg: Money
    ) -> None:
        """A green_purchases row, bought today."""
        ...


# roastery/listing.py -------------------------------------------


class Catalogue:
    def add_category(
        self,
        name: str,
        *,
        parent_id: CategoryId | None,
        sort_order: int,
    ) -> CategoryId:
        ...

    def add_product(
        self,
        name: str,
        *,
        category_id: CategoryId,
        details: BeanDetails | EquipmentDetails,
    ) -> ProductId:
        """products and its subtype row; the kind and weight_g
        follow from the details."""
        ...

    def set_price(
        self,
        product_id: ProductId,
        *,
        price: Money,
        valid_from: dt.date,
    ) -> None:
        """Closes the open period on valid_from, opens one."""
        ...

    def set_cost(
        self,
        product_id: ProductId,
        *,
        valid_from: dt.date,
        green: Money,
        packaging: Money,
        roasting: Money,
    ) -> None:
        """Closes the open cost period, opens one."""
        ...

    def add_campaign(
        self,
        name: str,
        *,
        discount_pct: int,
        first_day: dt.date,
        last_day: dt.date,
        product_ids: tuple[ProductId, ...],
    ) -> None:
        """campaigns, campaign_products and its pricing rule
        (percent = discount_pct, valid_to = last_day + 1)."""
        ...

    def set_subscriber_discount(
        self, percent: int | None, *, valid_from: dt.date
    ) -> None:
        """Closes the open subscriber rule; None opens none."""
        ...


# roastery/bootstrap.py -----------------------------------------


class Jobs:
    """Bound by wire to the store, the feed and the settings.

    No argument, no clock: the wired Clock gives the moment.
    """

    def relay(self) -> Relayed:
        """Outbox batches to the StatusFeed (ADR 0009)."""
        ...

    def ship_subscription_bags(self) -> int:
        """This month's bags not yet shipped, skipped or
        paused; a shipped movement each. The bags shipped."""
        ...

    def count_at_close(self) -> int:
        """stock_daily for the last closed shop day: every
        product's balance by the UTC day, stamped at the day's
        close (18:00 in the shop zone). The rows written."""
        ...

    def nightly_extract(self) -> int:
        """customer_extracts for tonight. The rows written."""
        ...

    def csv_export(self) -> Mapping[str, str]:
        """raw_customers and raw_lines: file name to text."""
        ...


@dataclass(frozen=True)
class App:
    customers: Customers
    catalogue: Catalogue
    checkout: Checkout
    payments: Payments
    fulfilment: Fulfilment
    subscriptions: Subscriptions
    stock: Stock
    jobs: Jobs


# roastery/ports.py: the port the outbound call goes through ----


class ProviderRefused(Exception):
    """A decline (402): never retried."""


class ProviderUnavailable(ConnectionError):
    """Down, or the breaker is open: retried."""


class PaymentProvider(Protocol):
    def refund(
        self, payment_id: PaymentId, amount: Money, *, key: str
    ) -> PaymentId:
        """The refund's id; the same key gives the same id."""
        ...


# roastery/errors.py: the closed family (C6, C20) ---------------


class ShopError(Exception):
    """A command the shop's rules refuse; nothing was written."""


class IllegalTransition(ShopError):
    def __init__(
        self, order_id: OrderId, state: str, action: str
    ) -> None: ...


class IllegalSubscriptionMove(ShopError):
    def __init__(
        self,
        subscription_id: SubscriptionId,
        state: str,
        action: str,
    ) -> None: ...


class NotShippable(ShopError):
    def __init__(self, order_id: OrderId) -> None: ...


class NotCreditable(ShopError):
    def __init__(self, order_id: OrderId, state: str) -> None: ...


class AlreadyCredited(ShopError):
    def __init__(self, line_id: LineId) -> None: ...


class NoOpenInvoice(ShopError):
    def __init__(self, order_id: OrderId) -> None: ...


class NothingToRefund(ShopError):
    def __init__(self, order_id: OrderId) -> None: ...


class PaymentMismatch(ShopError):
    def __init__(self, payment_id: PaymentId) -> None: ...


class KeyReused(ShopError):
    def __init__(self, key: str) -> None: ...


class DuplicateId(ShopError):
    def __init__(self, kind: str, value: str) -> None: ...


class UnknownId(ShopError):
    def __init__(self, kind: str, value: str) -> None: ...


class NoSuchCustomer(ShopError):
    def __init__(self, customer_id: CustomerId) -> None: ...


class UnknownProduct(ShopError):
    def __init__(self, product_id: ProductId) -> None: ...


class WrongKind(ShopError):
    def __init__(self, product_id: ProductId, kind: str) -> None: ...


class NoPrice(ShopError):
    def __init__(self, product_id: ProductId, on: dt.date) -> None: ...


class OutOfStock(ShopError):
    def __init__(
        self, product_id: ProductId, wanted: int, on_hand: int
    ) -> None: ...


class PeriodOverlap(ShopError):
    def __init__(
        self, table: str, key: str, valid_from: dt.date
    ) -> None: ...
```

### What each call raises

Every member is in `roastery/errors.py` (C20). `DuplicateId` can come from any call that makes an id. It means the `Ids` adapter and the store disagree, which is a bug in the script, so the table leaves it out.

| call | raises | the row that shows it |
|---|---|---|
| `Checkout.place` | `NoSuchCustomer`, `UnknownProduct`, `NoPrice`, `OutOfStock` | an order for C-07 after 9 October; P-99 (L-09's product) rolls the whole order back; a web line for P-21 before 7 October |
| `Checkout.cancel` | `UnknownId`, `IllegalTransition` | a shipped or delivered order cannot be cancelled |
| `Checkout.credit_for` | `UnknownId`, `NotCreditable`, `AlreadyCredited` | O-107 was never paid (the `anaemic-model` page); a second credit of one line |
| `Payments.handle_message` | `UnknownId`, `PaymentMismatch`, `IllegalTransition` | PAY-1 again with another amount; a payment for an invoiced order goes to `settle` |
| `Payments.invoice` | `UnknownId`, `IllegalTransition` | |
| `Payments.settle` | `UnknownId`, `PaymentMismatch`, `NoOpenInvoice` | a paid order, or an invoice already paid |
| `Payments.refund` | `UnknownId`, `NothingToRefund`; the port's `ProviderRefused` and `ProviderUnavailable`, which are not in the family | O-106 was never paid; a decline (402) is never retried |
| `Fulfilment.ship` | `UnknownId`, `NotShippable`, `IllegalTransition` | O-104 is a counter sale; O-106 was cancelled at E-12 |
| `Fulfilment.deliver` | `UnknownId`, `IllegalTransition` | |
| `Customers.register` | none | |
| `Customers.change` | `NoSuchCustomer` | |
| `Customers.erase` | `NoSuchCustomer` | C-07 a second time |
| `Subscriptions.subscribe` | `NoSuchCustomer`, `UnknownProduct`, `WrongKind` | a subscription to a grinder |
| `Subscriptions.skip`, `.pause`, `.resume`, `.cancel` | `UnknownId`, `IllegalSubscriptionMove` | a skip after this month's bag shipped; a resume of a subscription not paused; any call after the cancel |
| `Stock.roast` | `UnknownProduct`, `WrongKind` | equipment is not roasted |
| `Stock.write_off` | `UnknownProduct`, `OutOfStock` | |
| `Stock.stocktake` | `UnknownProduct` | |
| `Stock.buy_green` | none | |
| `Catalogue.add_category`, `.add_product` | `UnknownId` | a parent or category the store does not hold |
| `Catalogue.set_price`, `.set_cost` | `UnknownProduct`, `PeriodOverlap` | a period that starts before the open one |
| `Catalogue.add_campaign` | `UnknownProduct` | |
| `Catalogue.set_subscriber_discount` | `PeriodOverlap` | |
| `jobs.relay` | none: a batch the feed refuses (`FeedDown`) waits | E-09's batch, E-08's batch (ADR 0009) |
| `jobs.ship_subscription_bags` | `OutOfStock`; nothing is shipped in that run | |
| `jobs.count_at_close`, `.nightly_extract`, `.csv_export` | none | |

`KeyReused` belongs to the API's key store (`idempotency.py`): the same key sent again with another body. No call of contract B raises it. A malformed value (`Qty(0)`, `OrderId('C-01')`, a `kg` of 0) raises `ValueError` or `TypeError` where it is built, and is not a `ShopError` (ADR 0004).

### The ids the app makes

The prefixes ADR 0007 leaves to this contract. Each one differs from every other prefix, and from the outside systems' `PAY`, `R`, `W` and `V`.

| kind | prefix | made by |
|---|---|---|
| `shipment` | `SH` | `Fulfilment.ship` |
| `bag` | `SB` | `jobs.ship_subscription_bags` |
| `movement` | `M` | every call that writes a stock movement |
| `purchase` | `GP` | `Stock.buy_green` |
| `rule` | `PR` | `Catalogue.add_campaign`, `.set_subscriber_discount` |
| `sub_event` | `SE` | `Subscriptions.skip`, `.pause`, `.resume`, `.cancel`, and `Customers.erase` |

### Who writes each table

All 50 tables of contract A, in `contract.md`'s order. The system is copied word for word from `contract.md`. "Writer" is what makes the rows:

- an app call (`Service.call` or `jobs.job`);
- the simulator, playing an outside system;
- for a derived table, the query that derives it, run by the simulator's extract writer (6.4, 6.5).

An app-database table reaches an extract as a projection of the app's schema, written by `exports.py` (ADR 0003). The writer named here is the call that makes the rows, not the projection.

| table | system | writer |
|---|---|---|
| `customers` | app database | `Customers.register`; `.change`; `.erase` (removes the row) |
| `products` | app database | `Catalogue.add_product` |
| `orders` | app database | `Checkout.place`; `Checkout.credit_for` (the credit order, with `credit_of` in the app db only) |
| `order_lines` | app database | `Checkout.place`; `Checkout.credit_for` (the negative line); `Checkout.cancel` marks lines deleted, so they leave `order_lines` |
| `dated_lines` | derived: order_lines joined to orders | the extract writer: `order_lines` joined to `orders` on `order_id` |
| `prices` | app database | `Catalogue.set_price` |
| `fx_rates` | outside feed: bank rates | the simulator, as the bank |
| `payments` | payment provider | the simulator, as the provider: every message it sends, redeliveries included (PAY-1 twice), each delivered to `Payments.handle_message` or `.settle`. A refund's message (order 300's -899) follows `Payments.refund`. The app keeps its own record of each payment once, in its db |
| `order_events` | status feed | `jobs.relay`, through the `StatusFeed` port; the simulator's feed adapter writes the rows and stamps `loaded_at`. The outbox rows come from `place`, `invoice`, `handle_message` (paid), `ship`, `deliver`, `cancel` and `credit_for` |
| `stock_daily` | app database | `jobs.count_at_close` |
| `latest_stock` | derived: stock_daily, the latest count of each day | the extract writer: the row with the latest `counted_at` per product and day |
| `customer_extracts` | app database: nightly copies of customers | `jobs.nightly_extract` |
| `customer_changes` | app database: the change log of customers | the customers store, inside `Customers.register` (insert), `.change` (update) and `.erase` (delete) (ADR 0003) |
| `line_stamps` | app database: order lines with their stamps | `Checkout.place` and `.credit_for` (each line at the order's moment); `Checkout.cancel` (`is_deleted`, `updated_at` at the cancel: L-10 at E-12) |
| `raw_customers` | csv export | `jobs.csv_export`; the export writer adds the faults after it (D10) |
| `raw_lines` | csv export | `jobs.csv_export`; the faults after it (D10) |
| `web_events` | web tracking | the simulator, as the tracker |
| `subscriptions` | app database | `Subscriptions.subscribe`; `.cancel` and `Customers.erase` set `ended` |
| `categories` | app database | `Catalogue.add_category` |
| `kinds` | app database | the schema's seed (`repository.create_tables`), from `catalogue.Kind`: two rows, `beans` and `equipment`. No call, since a third kind would break the `Kind` type (ADR 0011) |
| `campaign_products` | app database | `Catalogue.add_campaign` |
| `campaigns` | app database | `Catalogue.add_campaign` |
| `product_codes` | till | the simulator, as the till |
| `till_receipts` | till | the simulator, as the till |
| `till_lines` | till | the simulator, as the till |
| `till_members` | till | the simulator, as the till |
| `customer_months` | derived: orders, order_lines and subscriptions of C-01 | the extract writer: C-01's orders, lines and subscriptions by month |
| `bean_details` | app database | `Catalogue.add_product` (with `BeanDetails`) |
| `equipment_details` | app database | `Catalogue.add_product` (with `EquipmentDetails`) |
| `managers` | owner's sheet | the simulator writes the owner's rows as given |
| `daily_sales` | derived: the web shop's consumer order lines | the extract writer: web consumer lines at list price, by day and product |
| `order_values` | derived: a scripted lesson set of app orders | the extract writer: the lesson set's orders (through `lesson_ids`), their lines, payments and events |
| `budget` | owner's sheet | the simulator writes the owner's rows as given |
| `checkout_test` | derived: web tracking during a 40-day test | the extract writer: `web_visits` with a variant and their events |
| `subscribers` | derived: the subscriptions of everyone outside the cast | the extract writer: `subscriptions` outside the cast, through `lesson_ids` |
| `visits` | derived: web tracking, the attributed visits | the extract writer: `web_visits` with a referrer, `reached` from their events and `order_events` |
| `deliveries` | derived: shipments of the lesson set's web orders (S8) | the extract writer: `shipments` of `order_values`' web orders, through `lesson_ids` |
| `shop_days` | derived: door counter, weather and old till | the extract writer: the join of `door_counts`, `weather_days` and `till_day_totals` |
| `subscription_events` | app database | `Subscriptions.skip`, `.pause`, `.resume`, `.cancel`; `Customers.erase` (a cancel, reason `erased`) |
| `subscription_shipments` | app database | `jobs.ship_subscription_bags` |
| `stock_movements` | app database | `sold`: `Checkout.place` (out), `.cancel` and `.credit_for` (back in, C21); `roasted`: `Stock.roast`; `written_off`: `Stock.write_off`; `counted`: `Stock.stocktake`; `shipped`: `jobs.ship_subscription_bags`. `Fulfilment.ship` writes none |
| `green_purchases` | app database | `Stock.buy_green` |
| `product_costs` | app database | `Catalogue.set_cost` |
| `shipments` | app database | `Fulfilment.ship` (`shipped_on`, `promised_by`); `Fulfilment.deliver` (`delivered_on`) |
| `pricing_rules` | app database | `Catalogue.add_campaign` (`campaign`, with the same percent as `campaigns.discount_pct`); `Catalogue.set_subscriber_discount` (`subscriber`) |
| `weather_days` | outside feed: weather | the simulator, as the weather service |
| `door_counts` | outside feed: door counter | the simulator, as the door counter |
| `till_day_totals` | outside feed: old till | the simulator, as the old till |
| `web_visits` | web tracking | the simulator, as the tracker |
| `lesson_ids` | derived: the lesson sets of tier 3 and the shop ids they stand for | the simulator's extract writer, from its script: which app order or subscription each lesson row stands for. Only the simulator knows the map (the app's ids come back from `place`, `credit_for` and `subscribe`) |

### The outside systems and how they reach the app

| system | tables | how it meets the app |
|---|---|---|
| payment provider | `payments` | The simulator writes every message, then delivers it: a card payment or a refund to `Payments.handle_message`, an invoice's payment to `Payments.settle`. The app calls out to the provider once: `Payments.refund`, through the `PaymentProvider` port. The provider answers with a negative message, which comes back the same way |
| status feed | `order_events` | the output of `jobs.relay`: the outbox's batches sent to the `StatusFeed` port; the feed stamps `loaded_at` and may refuse a batch (ADR 0009) |
| web tracking | `web_events`, `web_visits` | none (C11). The simulator writes a visitor's checkout, then calls `Checkout.place` within two minutes (W-03 at 08:11, E-01 at 08:12) |
| till | `product_codes`, `till_receipts`, `till_lines`, `till_members` | read by `parsing.parse_till` and `reports.reconcile_till`, never booked: R-5001 is O-104's L-06 (ADR 0012) |
| outside feed: bank rates | `fx_rates` | none; a report converts with them |
| outside feed: weather | `weather_days` | none |
| outside feed: door counter | `door_counts` | none |
| outside feed: old till | `till_day_totals` | none |
| owner's sheet | `managers`, `budget` | none; written as the owner set them, never simulated |
| csv export | `raw_customers`, `raw_lines` | the app's own output: `jobs.csv_export` gives the text; the export writer adds the faults (D10) |

### Not in contract B

These are reads the pages call. The simulator never needs them, so they are not frozen with it: `customers.country_of`, `Fulfilment.late_shipments`, the `reports` functions (`reconcile_till` among them), `parsing.parse_till`.

### The snapshot test (C12)

6.3 writes `packages/shop/tests/test_contract_b.py`. It renders the surface above as text, one line per item, sorted:

- for each class in the block (`App`, `Jobs`, the seven services, `PaymentProvider`): each public method as `Class.method` and `str(inspect.signature(...))`;
- for each dataclass (`Item`, `PlaceOrder`, `PaymentMessage`, `Receipt`, `App`): its fields, with their names and annotations, in order;
- the family: every subclass of `ShopError`, followed recursively, by name, with the signature of its `__init__`. A second assertion checks that no module of `roastery` other than `errors.py` defines one.

It compares the text with the committed file `packages/shop/tests/contract_b.txt` and prints the difference when they differ. The file changes only on purpose, in the same commit as the code. 6.4 pins it at its tag.

The raises table above is not checked by the test. The review checks it against the family's names (6.2 U6, then each change).
