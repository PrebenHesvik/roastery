# Contract C: the architecture of the shop app

This file is the shape of the shop app, `roastery`, before its code is written. The owner reads it before step 6.3 starts. Phase 7 reads it to point the 35 Design Patterns pages at the app's modules. The decisions behind it (C1–C32) are in `docs/phase-6/6.2-architecture.md`. Each choice has its record in `docs/adr/`.

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
            'customer',
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

41 modules, in the order of `LAYERS`: the layers from the inside out, and the modules of each layer sorted by name. The last column is the ADR that owns the module.

| module | layer | its job | ADR |
|---|---|---|---|
| `catalogue` | core | `Product`, `Kind`, `BeanDetails`, `EquipmentDetails`, the category path | [0004](adr/0004-domain-types.md) |
| `clock` | core | `local_date(now, zone)` and the zone of each country: days from moments, as a pure function | [0008](adr/0008-the-clock.md) |
| `commands` | core | the subscription commands as data, each the `subscription_events` row it becomes; `apply`, `replay` | [0011](adr/0011-contract-b.md) |
| `customer` | core | `Customer`, `Email` (optional on the customer, C37) and `CustomerChange`: the customer as the app holds it, and its change log's row | [0004](adr/0004-domain-types.md) |
| `errors` | core | `ShopError` and its 18 members, the one closed family | [0006](adr/0006-errors.md) |
| `events` | core | `OrderPlaced`, `OrderPaid`, `OrderInvoiced`, `StatusChanged`; the in-process `EventBus`; `CollectingBus` and `HandlerFailure` (C29) | [0009](adr/0009-events-outbox-relay.md) |
| `ids` | core | the id value types, one per kind of ADR 0007 and the provider's: `CustomerId`, `OrderId`, `LineId`, `EventId`, `ProductId`, `CategoryId`, `CampaignId`, `SubscriptionId`, `SubEventId`, `ShipmentId`, `BagId`, `MovementId`, `PurchaseId`, `RuleId`, `PaymentId`; and `Country`, `PostalCode`, `AccountKind` | [0004](adr/0004-domain-types.md) |
| `money` | core | `Money(amount, currency)` on `Decimal`, `Qty`, rounding to the øre | [0004](adr/0004-domain-types.md) |
| `order` | core | `OrderLine`, one class per feed status, `TRANSITIONS` | [0005](adr/0005-order-states.md) |
| `parsing` | core | payloads and till rows into `ParsedLine` or `Reject` | [0012](adr/0012-outside-systems-and-the-till.md) |
| `pipeline` | core | the export's stages as generators | [0001](adr/0001-flat-package-and-layers.md) |
| `pricing` | core | `Rule`, `list_price`, `subscriber`, `campaign`; `Registry` and `standard_rules`, which `wire` calls (no registry in module state) | [0001](adr/0001-flat-package-and-layers.md) |
| `result` | core | `Ok`, `Err`, `partition` | [0006](adr/0006-errors.md) |
| `subscription` | core | `Subscription`, its periods, `bags_due(on)` | [0011](adr/0011-contract-b.md) |
| `vat` | core | `vat_of`, `scheme_for`, the rate rows' type | [0010](adr/0010-vat.md) |
| `ports` | ports | every port, with the errors of the ports: the repositories, `Store`, `UnitOfWork`, `Outbox`, `Clock`, `Ids`, `StatusFeed`, `PaymentProvider`, `PriceRepository`, `Notifier`, `Labels`; the relay's result `Relayed` | [0003](adr/0003-persistence.md) |
| `provider_sdk` | vendor | the payment provider's SDK stand-in: camelCase, minor units, `ProviderApiError` | [0002](adr/0002-no-dependencies.md) |
| `cache` | adapters | `CachedPrices`, the one price cache of a store, in front of its prices, with its TTL (C31) | [0003](adr/0003-persistence.md) |
| `exports` | adapters | the csv export (`raw_*`) and the customer extract, written through `pipeline` | [0003](adr/0003-persistence.md) |
| `fakes` | adapters | the working fakes: `FakeClock`, `FakeProvider`, `FakeFeed`, `ClosedFeed`, `FakeNotifier`, `FakeLabels` | [0013](adr/0013-wiring-and-the-api.md) |
| `outbox` | adapters | outbox rows in memory and in sqlite; `relay` in batches to the `StatusFeed` | [0009](adr/0009-events-outbox-relay.md) |
| `provider` | adapters | the `PaymentProvider` port on the SDK: minor units to `Money`, SDK errors to port errors | [0002](adr/0002-no-dependencies.md) |
| `repository` | adapters | every store twice, memory and sqlite; the schema; the `Ids` adapters `SequentialIds` and `ScriptedIds` | [0003](adr/0003-persistence.md) |
| `resilience` | adapters | retry with backoff, `CircuitBreaker` | [0013](adr/0013-wiring-and-the-api.md) |
| `uow` | adapters | the two `Store` adapters and their units of work, memory and sqlite | [0003](adr/0003-persistence.md) |
| `checkout` | service | `Checkout`: place, cancel, `credit_for` (the facade) | [0011](adr/0011-contract-b.md) |
| `customers` | service | `Customers`: register, change, erase | [0011](adr/0011-contract-b.md) |
| `fulfilment` | service | `Fulfilment`: ship, deliver, `late_shipments`; the handlers `confirm` and `label` (C26) | [0011](adr/0011-contract-b.md) |
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
- A part outside the home module is written with its module: `listing.Catalogue.add_campaign` is the `Catalogue` service, in `listing.py`; `catalogue.Product` is the core type, in `catalogue.py` (C24). A class's method is written with its class (`Fulfilment.late_shipments`).
- **parts**: the top-level names the page will show. They retell what the page shows from `firm` today. They are intended; they freeze only at phase 7's pin (C16).
- **requirement**: what the page's example proves, and with which rows.
- **fit**: strong (the shop has the need on its own), partial (it has it, but something must be added), weak (the need is made up for the page). A partial or weak row says what closes it, or why it stays.

The rows of `pricing_rules`, `subscription_events`, `stock_movements` and `shipments` are new in 1.0. They are in `month` and `full`, not in `tiny`, so a row cites the table, never a row id.

### How does good code think?

| page | module | parts | requirement | fit |
|---|---|---|---|---|
| one-reason-to-change | `vat` | `vat_of`, `scheme_for`; `parsing.parse_till` | A VAT change edits `vat.py` only: phase 8 changes `scheme_for` and the rate rows, not the callers (C10). A new column in the till's file edits `parsing.py` only (C13). The twin's `process(row)` reads, prices, adds VAT and prints the receipt, so the VAT change edits it in four places | strong |
| depend-on-abstractions | `ports` | `OrderRepository` (a Protocol); `reports.sales_by_customer` | `sales_by_customer` gives the same rows from the memory store and sqlite: C-01 has O-101, O-104 and O-108. The page's contrast, `OrderStore`, the same port as an ABC that refuses a store with a method missing, lives in data-docs' `without/`, not in the app: nothing in the app would use it (the deletion test). The twin's sqlite-bound service must be patched in its test | strong |
| composition-over-inheritance | `pricing` | `with_discount`, `per_rule`; the twin's `PricingRule`, `Subscriber`, `Campaign`, `SubscriberCampaign` | `with_discount(percent, list_price)` wraps the list price with a `pricing_rules` row (subscriber or campaign). Template method: `PricingRule` with hooks. The twin needs a subclass per mix | partial: `pricing_rules` holds each percent (G3 closed), but nothing in the data says two rules stack on one line. The walk states the stacking order as the page's choice |
| pure-core-imperative-shell | `fulfilment` | `order.late_orders` (pure); `Fulfilment.late_shipments` (the shell) | `late_orders(orders, events, today)`: paid or invoiced (S13), not shipped within two working days. A counter sale never ships: O-104 ends at `Paid` (C5). The shell reads the store and `local_date(clock.now(), zone)` (C8). The twin moves "late" to working days and patches the clock | strong |
| errors | `customers` | `UnknownCustomer`, `NoCountry`, `country_of`, `find_customer`; `result.Ok`, `Err`, `partition` | `country_of` returns a `Result` (C6). C-05 is known and has no country; C-07 was erased, yet O-107 names them. `None` cannot tell the two apart. The caller gives C-05's O-105 Norway's rate on purpose, not as a fallback in the lookup (C10) | strong |

### How do I build objects?

| page | module | parts | requirement | fit |
|---|---|---|---|---|
| value-objects | `money` | `Money`, `Qty`; `ids.ProductId`, `ids.PostalCode`, `ids._check_id` | Money adds only to money of its currency: PAY-2 (SEK) plus PAY-3 (DKK) raises. `Qty` refuses 0; only `Checkout.credit_for` makes a negative line (C4, S14). `PostalCode` keeps C-01's 0150. The twin sums bare floats across currencies | strong |
| parse-dont-validate | `parsing` | `ParsedLine`, `Reject`, `parse_till`; `reports.reconcile_till` | The till's file is parsed once into sales (C13). Code 2000000000992 has no product: a `Reject`. Grams only for loose beans (R-5002's 250 g). `reconcile_till` matches R-5001 to O-104's L-06 by moment and product, and never moves stock. The twin checks grams in three callers and forgets one | strong |
| illegal-states | `order` | `Placed`, `Paid`, `Invoiced`, `Shipped`, `Delivered`, `Cancelled`, `describe` | One class per feed status (C5). `Shipped` and `Delivered` carry how the order is settled, so only a paid order has a payment and an invoiced one ships first (S13). O-106 had a line, L-10, deleted at its cancel (E-12, `line_stamps`). The twin has flags and Optionals | strong |
| factories | `order` | `OrderLine.of`, `.from_payload`, `.at_counter`, `.credit`; `line_for(channel)` | Two real channels: O-101 from the web payload, O-104 at the counter. Each factory has its own input (ADR 0004): `from_payload` parses the web shop's JSON line at the API's edge, `at_counter` requires the price rung (L-06 sells at 549 the day before P-21's list price starts), `of` takes text for tests and walks, and `credit` is the one way to a negative line (S14). The twin's `__init__(source=...)` branches | partial: the simulator places both channels through `Item`s, so inside contract B one shape reaches `place`, and the pick by source happens only at the API's edge (`api.place_handler`). The walk runs there |
| registries-and-plugins | `pricing` | `Registry`, `standard_rules`, `RULES`, `DuplicateRule`, `UnknownRule` | Rules registered by `pricing_rules.rule_kind`: `list`, `subscriber`, `campaign`. `wire` builds the registry with `standard_rules()`, one per wiring; `RULES` is the read-only standard three, and no registry is module state (the page's "what goes wrong"; ADR 0013). A campaign plugin registers into the registry it is given. A name twice raises | strong: `pricing_rules` closes G3 |

### Where do I put a seam?

| page | module | parts | requirement | fit |
|---|---|---|---|---|
| adapter | `provider` | `ports.PaymentProvider`, `ProviderUnavailable`, `ProviderRefused`; `provider_sdk.ProviderClient`; `ProviderPayments`, `to_money` | The SDK speaks camelCase and minor units: PAY-2's 516.98 SEK is 51698. `ProviderPayments` gives `Money`. The outbound call is `Payments.refund`: order 300's -899 NOK goes out as minor units, and the SDK's 402 comes back as `ProviderRefused`. The leak: minor units, or the refund window. The twin: SDK v2 renames `amountMinor` | strong |
| facade | `checkout` | `Checkout`, `Checkout.place`, `money.Money.to_ore` | `place(PlaceOrder)`: the gross price on the day (one for every buyer, C10), the VAT share stored (C18), the order id from `Ids` (C7), the sold movement, the outbox row. O-101's total is 1157.00, PAY-1's amount. The twin has three totals | strong |
| decorators-and-middleware | `middleware` | `logged`, `timed`, `require_role`, `stack`; `api.credit_handler` | `require_role('staff')` around the credit handler: a return is staff work (S14). Built framework-free before phase 7 (C14). The twin copies timing into each handler | strong (generic) |
| repository | `repository` | `ports.OrderRepository`; `MemoryOrders`, `SqliteOrders`, `create_tables` | Objects in, objects out, on both stores. `all()` lists O-101 to O-108 by `order_id`, whatever the order of insert (C17). A second O-101 raises `DuplicateId` (C7). The twin puts SQL in the service | strong |
| unit-of-work | `uow` | `ports.UnitOfWork`; `SqliteUnitOfWork`, `InMemoryUnitOfWork`; `Checkout.place` | One commit holds the order, its lines, the `sold` stock movement and the outbox row (C3). An unknown product (P-99) rolls all of it back. The twin keeps an order with no lines | strong |

### How does behaviour vary?

| page | module | parts | requirement | fit |
|---|---|---|---|---|
| strategy | `pricing` | `list_price`, `subscriber`, `campaign`, `price_lines`, `rule_named`, `RULES` | `list_price` reads `prices` on the order day: P-10 is 119, then 129 from 1 October. P-21 has no list price on 6 October, so `list_price` fails for L-06. `subscriber` and `campaign` take their percent from `pricing_rules`. An unknown name fails loudly | strong: `pricing_rules` closes G3. K-1 and K-2 run outside 5–9 October, so no teaching-week line has a discount |
| command | `commands` | `Skip`, `Pause`, `Resume`, `Cancel`; `apply`, `replay`; `Subscriptions` builds and keeps them | Each call of `Subscriptions` builds its command, checks it with `apply` and keeps it as its `subscription_events` row, with its reason: the table is the command log. `subscribe` writes `subscriptions.started` and no command. `replay` rebuilds the periods from `subscriptions.started` and `subscription_events`: S-2 stopped 1 August 2025, S-3 began a month later. Undo is retold: the shop answers a pause with a `Resume`, a new event. The twin writes audit text by hand | strong: `subscription_events` holds pause and skip |
| state-machine | `order` | `TRANSITIONS`, `IllegalTransition`, `check`, `ship`, `transitions` | `TRANSITIONS` keyed on the six statuses (C5): O-101 goes placed, paid, shipped, delivered (E-01 to E-04). Shipping O-106 after its cancel (E-12) raises. An invoiced order ships before it is paid (S13). A return is a credit order, not a state (S14). The twin has ifs in five handlers | strong |
| pipelines-and-generators | `pipeline` | `read`, `live_lines`, `as_text`, `to_csv`, `pipe`, `Trace` | `exports.py` writes the csv export through these stages, lazily. `live_lines` drops the lines deleted at a cancel, as the page's stage drops items: O-106's L-10 never reaches `raw_lines`. `as_text` turns each line into the export's text columns. There is no VAT stage: `raw_lines` has no VAT column, and `orders.vat_amount` is never exported (C18, ADR 0010). A stop after two lines (L-01, L-02) builds two. The export's faults are added after it (D10). The twin builds three years of `full` as lists | strong: the app writes the export (G6 closed) |

### How do parts talk across a boundary?

| page | module | parts | requirement | fit |
|---|---|---|---|---|
| observer-and-events | `events` | `Event`, `OrderPaid`, `EventBus`, `HandlersFailed`, `CollectingBus`; `fulfilment.confirm`, `fulfilment.label`; `Payments.handle_message` | PAY-1 makes O-101 paid (E-02). Two handlers are subscribed in `bootstrap` (C26, C39): `confirm` hears `OrderPaid` and `OrderInvoiced`, never for a credit order, and sends the confirmation e-mail through `Notifier` when the customer has an e-mail; `label` hears the same, for web orders with a postal code only, and asks for the shipping label through `Labels`. An order without an address gets no label, and `Fulfilment.ship` refuses it (`NoAddress`): O-105 (C-05, paid, never shipped in the week). Each port's fake records. The `StatusChanged` outbox row is not a handler: `handle_message` writes it in its unit of work, the page's "not every reaction should be an event". Stock is not a handler either: it moved at `place` (O-107, never paid, took a P-10 bag on 7 October). One handler raises; the others run; `EventBus.publish` raises `HandlersFailed`. In the app, `CollectingBus` keeps it for `App.failures()`, so `handle_message` still returns (C29). The twin's `handle_message` imports every handler | strong |
| outbox | `outbox` | `SqliteOutbox`, `relay`; `uow.SqliteUnitOfWork`; `ports.StatusFeed`; `fakes.FakeFeed` | The status change and its outbox row commit together (C3). `relay` sends batches of `RELAY_BATCH` rows; the feed stamps `loaded_at` (C9). E-08's batch failed on 8 and 9 October and went on the 10th, while later batches went (E-04, E-13). E-09's batch failed and went after E-10's, so E-10 loaded first (G15) | strong |
| idempotency | `payments` | `Payments.handle_message`, `PaymentMessage`, `Receipt`; `errors.PaymentMismatch`; `idempotency.digest`, `IdempotencyStore`, `KeyReused` | The provider redelivered PAY-1. `handle_message` keyed on `payment_id` records it once and returns the stored `Receipt` (C12). PAY-1 again with another amount raises `PaymentMismatch` (C6), compared with the stored payment, never with the order's total. `KeyReused` belongs to the API's key store in `idempotency.py`; both live in `errors.py` (C20) | strong (G5 pinned) |
| cache-aside | `cache` | `ports.PriceRepository`, `CachedPrices`, `price_key`, `DictCache`; `fakes.FakeClock` | A list price read often, changed rarely (`prices`). `CachedPrices` is a concrete class in front of the store's `PriceRepository`, one per store, built by `sqlite_store` and `memory_store` (C31): both of the simulator's wirings read through it, and `set_price` evicts the entry on commit. The TTL is `PRICE_TTL` (C15). P-10 changes on 1 October; a stale entry prices a cart at 119. The twin's cache is never told of `set_price` | weak: a small shop has no load that needs a cache. It stays weak: the stale price at checkout is the honest reason |
| retry-and-circuit-breaker | `resilience` | `Transient`, `retry`, `delay`, `CircuitBreaker`; `fakes.FakeProvider`; `Payments.refund` | `Payments.refund`, the one outbound call, retried with backoff and the same key (`refund-<order_id>`), so a retry cannot refund twice. `wire` puts the retry and the breaker around the `PaymentProvider` port. A breaker opens when the provider is down. A decline (402, `ProviderRefused`) is never retried. Jitter is seeded (C17) | strong: order 300's refund and a cancel after payment need the call |
| queue-and-worker | none | none: the page shows files, never runs them | The order confirmation and the shipping label made by a worker after `OrderPaid` | strong (shown) |

### How do I shape an app?

| page | module | parts | requirement | fit |
|---|---|---|---|---|
| layers | `architecture` | `LAYERS`, `INWARD`, `import_graph`, `check_direction`, `unplaced`; `api.place_handler`; `bootstrap.memory_store` | The check on `roastery` itself (`modules.layers`). The violation: a scratch copy of `pricing.py` imports `repository`, core to adapters (ADR 0001) | strong |
| ports-and-adapters | `bootstrap` | `App`, `wire`, `memory_store`, `sqlite_store`; `api.place_handler` | Memory and sqlite wiring give the same frame for O-101. The second driving adapter is the simulator: it wires the app as `scripted` and as `simulator` over one store; the API wires `visitor` (C7) | strong |
| cqrs-lite | `reports` | `kind_of_line`, `sales_by_kind`, `SALES_BY_COUNTRY`, `sales_by_country` | The read side returns rows, never frames (C2). Beans (P-10, P-11) against equipment (P-20, P-21). `sales_by_country` reads the customer's country, not the order's: O-105's `Head.country` is `NO` (C10, the VAT's choice), while C-05 has none, so O-105 counts under no country. The write side is untouched | strong |
| configuration | `settings` | `Settings`, `PARSERS`, `SettingsError`, `unknown_names`, `url`; `bootstrap.wire` | `ROASTERY_*` read once, typed: `DATABASE_URL`, `PROVIDER_URL`, `PROVIDER_KEY` (out of the repr), `PRICE_TTL`, `SHOP_ZONE`, `RELAY_BATCH` (C15). VAT is a table, not a setting (C10) | strong |

### How do I test the design?

| page | module | parts | requirement | fit |
|---|---|---|---|---|
| fakes-over-mocks | `fakes` | `FakeProvider`, `FakeClock`; `repository.MemoryOrders`; `Fulfilment.late_shipments` | `FakeProvider` is a working fake at the `PaymentProvider` port: it holds the payments it took, refuses a refund for more than is left or for a payment it does not hold (`ProviderRefused`), gives the same refund id for the same key, can be set down (`ProviderUnavailable`), and makes the negative message the simulator delivers (order 300's -899). The minor-units mistake sits under the adapter: a mock of `provider_sdk.ProviderClient` behind `ProviderPayments` accepts 899 where the SDK wants 89900, and the test passes wrongly. A fake at the port takes `Money`, so it cannot make that mistake | strong |
| contract-tests | `contracts` | `check_orders`, `all_is_ordered`; `ports.OrderRepository` | The same suite on the memory and sqlite stores (C17). A fake that lists in insertion order fails `all_is_ordered`. The provider fake against a sandbox is said in words | strong |

### Why does it hurt?

| page | module | parts | requirement | fit |
|---|---|---|---|---|
| god-object | none | the twin's `ShopManager`; it reuses `CachedPrices`, `Checkout`, `ProviderPayments`, `parse_till` | One class reads the till file, keeps orders, prices, caches prices, takes payments and writes the export. A discount field set at checkout changes the export | strong |
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
| depend-on-abstractions | `without/service.py`; and `OrderStore`, the port as an ABC, in `without/` too (it is the page's contrast, not the app's) |
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
- **depend-on-abstractions**: the ABC contrast moves out of the app's `ports.py` into data-docs' `without/`.
- **adapter**: the error mapping is shown on the outbound call, `Payments.refund`.
- **facade**: order id from `Ids` (C7); one gross price (C10); `vat_amount` stored (C18); a `sold` movement replaces "stock reserved" (§2, `stock.py`).
- **decorators-and-middleware**: the refund handler becomes the credit handler (S14); built before phase 7 (C14).
- **unit-of-work**: "stock reservation" becomes the `sold` movement; `stock_movements` has no reservation.
- **strategy**: partial becomes strong (`pricing_rules`). One gross price for every buyer (C10).
- **command**: `Stop` becomes `Cancel`; `Skip` is added; each carries a reason. The command log is `subscription_events`, and `replay` reads it with `subscriptions.started`. Partial becomes strong.
- **state-machine**: six statuses (C5); returns are credit orders, not a state (S14).
- **pipelines-and-generators**: "strong if it writes" is settled: `exports.py` writes through `pipeline.py` (6.2's module map). The stage that drops items is `live_lines` (deleted lines); there is no VAT stage.
- **observer-and-events**: no warehouse (S10) and no subscription bag booked as an order (D11). The handlers are the confirmation e-mail and the shipping label, through `Notifier` and `Labels` (C26); the outbox row is written by the service, and stock moves at `place`, not at paid. A handler's failure is collected, never raised to the caller (C29).
- **outbox**: the cause of E-10 before E-09 is G15, not "G17", fixed by C9's batches; E-08 is a batch that failed two days running (C9). 6.2 §5's default, "the relay does not run 8–9 October", contradicts E-04 and E-13, loaded on those days.
- **idempotency**: G5 is pinned: `handle_message` keyed on `payment_id` (C12).
- **retry-and-circuit-breaker**: stays strong, on a new call: the refund (`Payments.refund`), not a charge.
- **layers**: the violation imports `repository`, not sqlite, since the graph holds only `roastery` (ADR 0001).
- **ports-and-adapters**: the simulator wires the app twice, by `source` (C7).
- **cqrs-lite**: rows, never frames (C2); C-05 stays under no country, since the report reads the customer's country.
- **cache-aside**: one cache per store, a concrete class with no port of its own (C31).
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
- **observer-and-events**: `confirm` hears `OrderPaid` and `OrderInvoiced`, never for a credit order, and sends the confirmation e-mail through `Notifier` when the customer has an e-mail; `label` hears the same, for web orders with a postal code only, and asks for the shipping label through `Labels`. An order without an address gets no label, and `Fulfilment.ship` refuses it (`NoAddress`): O-105 (C-05, paid, never shipped in the week). The outbox row is the service's; stock moves at `place`; a failed handler is collected for `App.failures()`.
- **factories**: strong becomes partial: one input shape (`Item`) inside contract B.
- **fakes-over-mocks**: the fake at the port is a working provider; the minor-units mistake is a mock under the adapter.
- **pipelines-and-generators**: the dropping stage drops deleted lines, not lines with no hours.
- **depend-on-abstractions**: the ABC is a twin in data-docs, not a port in the app.
- **strategy**, **registries-and-plugins**, **composition-over-inheritance**: percents from `pricing_rules`, not constants.
- **anaemic-model**: a credit, not a refund.
- **premature-pattern**: a fee the data must hold (or 0).
- **retry-and-circuit-breaker**: the call retried is `Payments.refund`.

## 4. Choices

One line per decision record in `docs/adr/`: the choice in a few words, and the decisions it settles.

- [0001](adr/0001-flat-package-and-layers.md): a flat package; a layer is a row of `LAYERS`, not a folder (C1, C14, C20, C24; `customer` for C25).
- [0002](adr/0002-no-dependencies.md): the standard library plus `tzdata`; rows out, frames stay in data-docs (C2, C19).
- [0003](adr/0003-persistence.md): `sqlite3` repositories with a memory twin; a unit of work that holds the outbox row; one price cache per store; sqlite for `month` and `full` (C3, C25, C31, C32).
- [0004](adr/0004-domain-types.md): frozen dataclasses, id types, `Money`, a `Qty` that is never zero; the customer with an e-mail (C4, C25).
- [0005](adr/0005-order-states.md): six classes keyed on the feed's statuses; the settlement carried; undoing a sale is a `sold` movement (C5, C21, C22).
- [0006](adr/0006-errors.md): the closed `ShopError` family in `errors.py`; `Result` for questions with two kinds of answer; a handler's failure collected, never raised (C6, C20, C29).
- [0007](adr/0007-ids-and-provenance.md): an `Ids` port with two adapters; `source` as a wiring argument; a fixed width per kind for the background's ids (C7, C30).
- [0008](adr/0008-the-clock.md): `now()` in UTC; local dates by zone as a pure function; no wall clock in the package; `tzdata` for the zones (C8, C19, C23).
- [0009](adr/0009-events-outbox-relay.md): an in-process bus with two handlers; outbox rows written by the service; batches; a batch refused by its content waits (C9, C26, C28, C29).
- [0010](adr/0010-vat.md): dated rate rows; one gross price; `scheme_for(order, on)`; no country means Norway, explicitly (C10, C18, C22).
- [0011](adr/0011-contract-b.md): contract B: services on `App`, commands, jobs, and all the simulator imports; a snapshot test pins it at 6.4 (C12, C23, C24, C25, C27).
- [0012](adr/0012-outside-systems-and-the-till.md): what the simulator writes alone; the till file is reconciled, never stocked (C11, C13, C21).
- [0013](adr/0013-wiring-and-the-api.md): one `bootstrap.wire`; the simulator as the second driving adapter; framework-free handlers; the registry and the bus built in `wire` (C14, C26, C29, C31, C32).
- [0014](adr/0014-settings.md): `ROASTERY_*`, read once and typed; VAT never a setting (C15, C19).
- [0015](adr/0015-checks-and-names.md): `architecture.py`, `contracts.py`, the teachability test; module names frozen now, parts at the phase 7 pin (C16, C17).

## 5. Contract B

Contract B is what the simulator calls on the app, and everything else it imports from it (C27): the services on `App`, the two commands, the jobs, the errors each call raises, and the wiring, the stores, the `Ids` adapters, the fakes it drives, the feed's port and the relay's result. It is decision C12; the record is ADR 0011. 6.3 builds it, and 6.4 freezes it at its tag. After `roastery-data 1.0`, a change to it is a new data version.

How to read it:

- One class per service module (ADR 0001's `LAYERS`). The services on `App` are `Customers`, `Catalogue`, `Checkout`, `Payments`, `Fulfilment`, `Subscriptions` and `Stock`; the jobs are on `App.jobs`.
- No call takes an id for a row the app makes, a `source`, or a clock. Ids come through the `Ids` port, and `source` is a wiring argument (ADR 0007). Every stamp is `clock.now()` once per call, with one exception: `jobs.count_at_close` stamps `counted_at` with the counted day's close, 18:00 in the shop zone, not the moment it runs (C23). A day is `local_date(now, zone)`: the order's zone for an order (ADR 0008), the shop's zone (`ROASTERY_SHOP_ZONE`) for the shop's own days.
- A command is a frozen dataclass only where it carries lines (`PlaceOrder`) or mirrors a row another system wrote (`PaymentMessage`). Other calls take keyword arguments.
- Every call writes in one unit of work and raises a member of `ShopError` when the shop refuses it. When it raises, nothing is written (ADR 0006). When it returns, its rows are kept, whatever its handlers do after the commit: a handler's failure is collected, never raised, and `App.failures()` lists it (C29, ADR 0009).
- The bodies are `...`. Docstrings say what a call writes; the table after the block says what it raises.

```python
"""Contract B: the calls the simulator makes on App (C12)."""

from __future__ import annotations

import datetime as dt
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol

from roastery.catalogue import BeanDetails, EquipmentDetails
from roastery.customer import Email
from roastery.ids import (
    AccountKind,
    CategoryId,
    Country,
    CustomerId,
    EventId,
    LineId,
    OrderId,
    PaymentId,
    PostalCode,
    ProductId,
    ShipmentId,
    SubscriptionId,
)
from roastery.money import Money, Qty
from roastery.order import Channel, Invoiced, Placed, Status
from roastery.pipeline import Rows
from roastery.ports import Clock, Ids, Store
from roastery.settings import Settings
from roastery.uow import InMemoryStore, SqliteStore


# roastery/checkout.py ------------------------------------------


@dataclass(frozen=True)
class Item:
    """One line asked for.

    price None: the list price on the order's day, with the
    rules that hold; a web line only. A price given: set by
    hand, as the till rang it (L-06 at 549.00) or a free sample
    (L-12 at 0.00). A counter line (channel 'shop') always
    gives its price: ValueError without one (6.4, U12).
    """

    product_id: ProductId
    qty: Qty  # 1 or more
    price: Money | None = None


@dataclass(frozen=True)
class PlaceOrder:
    """An order on the web or at the counter (channel 'shop')."""

    customer_id: CustomerId
    channel: Channel
    items: tuple[Item, ...]  # one or more


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
    amount: Money  # negative for a refund (S14)
    paid_on: dt.date


@dataclass(frozen=True)
class Receipt:
    """The stored reply: the same for every delivery."""

    payment_id: PaymentId
    order_id: OrderId
    status: str  # the order's feed word after it


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
        the bags left at place. NoAddress for an order whose
        customer has no postal code (C39)."""
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
        email: Email | None,
        country: Country | None,
        postal_code: PostalCode | None,
        account_kind: AccountKind = 'consumer',
    ) -> CustomerId:
        """A customer, joined today; an insert change row. An
        e-mail ends in example.invalid (C25); C-05 has none
        (C37)."""
        ...

    def change(
        self,
        customer_id: CustomerId,
        *,
        email: Email | None,
        country: Country | None,
        postal_code: PostalCode | None,
    ) -> None:
        """The whole contact after the change (a move, mostly);
        an update change row with the country and postal code."""
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
    ) -> None: ...

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

    def write_off(self, product_id: ProductId, *, qty: Qty) -> None:
        """A written_off movement: qty out."""
        ...

    def stocktake(self, product_id: ProductId, *, on_hand: int) -> None:
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
    ) -> CategoryId: ...

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
        close (18:00 in the shop zone), not at now (C23). The
        rows written."""
        ...

    def nightly_extract(self) -> int:
        """customer_extracts for tonight. The rows written."""
        ...

    def csv_export(self) -> Mapping[str, str]:
        """raw_customers and raw_lines: file name to text."""
        ...

    def app_tables(self) -> Mapping[str, Rows]:
        """Every app-database table of contract A, by name: its
        columns, then source; the app db's own columns projected
        away (A33, 6.4 W2). Writes nothing."""
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
    events: CollectingBus  # the wiring's one bus (C29)

    def failures(self) -> tuple[HandlerFailure, ...]:
        """What the handlers raised since wire, in order (C29):
        self.events.failures(). The calls that published the
        events returned, and their rows are kept."""
        ...


def memory_store(*, clock: Clock, price_ttl: int) -> InMemoryStore:
    """The app's tables as dicts, with their one price cache
    (C31, C38). For tests, walks and the week alone (C32)."""
    ...


def sqlite_store(
    connection: sqlite3.Connection, *, clock: Clock, price_ttl: int
) -> SqliteStore:
    """The app's tables on the connection, with their one price
    cache (C38). For month and full (C32)."""
    ...


def wire(
    settings: Settings,
    store: Store,
    *,
    clock: Clock,
    ids: Ids,
    source: Source,
    feed: StatusFeed,
    provider: PaymentProvider,
    notifier: Notifier,
    labels: Labels,
) -> App:
    """The services on the store, the same for every caller
    (ADR 0013). No TTL: the cache came with the store, built
    from the same clock and Settings (C38). The simulator
    calls it twice over one store."""
    ...


# roastery/events.py --------------------------------------------


@dataclass(frozen=True)
class StatusChanged:
    """An order moved to a status of the feed, at a moment."""

    event_id: EventId
    order_id: OrderId
    status: Status
    event_at: dt.datetime


@dataclass(frozen=True)
class HandlerFailure:
    """One handler that raised after its call was kept."""

    handler: str  # the handler's qualified name
    event: str  # the event's class name
    error: str  # repr of what it raised


class CollectingBus:
    """Publishes on a bus; keeps what its handlers raised."""

    def publish(self, event: object) -> None:
        """bus.publish; a HandlersFailed is kept, not raised."""
        ...

    def failures(self) -> tuple[HandlerFailure, ...]:
        """What the handlers raised since the wiring, in order."""
        ...


# roastery/ports.py ---------------------------------------------


Source = Literal['scripted', 'simulator', 'visitor']

IdKind = Literal[
    'customer',
    'order',
    'line',
    'event',
    'product',
    'category',
    'campaign',
    'subscription',
    'sub_event',
    'shipment',
    'bag',
    'movement',
    'purchase',
    'rule',
]


@dataclass(frozen=True)
class Relayed:
    """What a relay run did: the batches sent, those that wait.

    A port type, so the simulator imports no adapter for it."""

    sent: tuple[int, ...]
    waiting: tuple[int, ...]


class FeedDown(ConnectionError):
    """The feed did not take the batch; none of it was kept."""


class StatusFeed(Protocol):
    def send(self, events: Sequence[StatusChanged]) -> None:
        """Take every event of the batch, or raise FeedDown.
        A feed refuses by content, never by batch number."""
        ...


class Notifier(Protocol):
    def send(self, to: Email, *, subject: str, body: str) -> None:
        """The confirmation e-mail (a handler's port, C26)."""
        ...


class Labels(Protocol):
    def request(
        self, order_id: OrderId, *, postal_code: PostalCode
    ) -> None:
        """A shipping label for a web order (C26, C39)."""
        ...


# the port the outbound call goes through


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


# roastery/repository.py: the Ids adapters (ADR 0007, C30) ------


class SequentialIds:
    """The next number of each kind at its fixed width,
    skipping the script's ids and the planted ones."""

    def __init__(
        self,
        start: Mapping[IdKind, int],
        skip: frozenset[str] = frozenset(),
    ) -> None: ...

    def next(self, kind: IdKind) -> str: ...


class ScriptedIds:
    """The script's ids of each kind in call order, then `then`."""

    def __init__(
        self,
        script: Mapping[IdKind, Sequence[str]],
        then: Ids,
    ) -> None: ...

    def next(self, kind: IdKind) -> str: ...


# roastery/fakes.py: the fakes the simulator drives -------------


class FakeClock:
    """A UTC moment that moves only when told."""

    def __init__(self, start: dt.datetime) -> None: ...

    def now(self) -> dt.datetime: ...

    def set(self, moment: dt.datetime) -> None: ...

    def advance(self, by: dt.timedelta) -> None: ...


class FakeProvider:
    """A working provider: the payments it holds, refunds by
    its rules, and the messages it would send."""

    def __init__(self, *, refund_ids: Sequence[PaymentId]) -> None: ...

    def take(self, message: PaymentMessage) -> None:
        """A payment the provider now holds."""
        ...

    def set_down(self, down: bool) -> None:
        """While down, every call raises ProviderUnavailable."""
        ...

    def refund(
        self, payment_id: PaymentId, amount: Money, *, key: str
    ) -> PaymentId:
        """ProviderRefused for a payment it does not hold or
        more than is left; the same key gives the same id."""
        ...

    def messages(self) -> tuple[PaymentMessage, ...]:
        """The refunds' negative messages, in order: what the
        simulator writes to payments and delivers."""
        ...


class FakeNotifier:
    """Keeps what it is asked to send; sends nothing."""

    def send(self, to: Email, *, subject: str, body: str) -> None: ...

    def sent(self) -> tuple[tuple[Email, str], ...]:
        """(to, subject), in the order asked."""
        ...


class FakeLabels:
    """Keeps the labels it is asked for."""

    def request(
        self, order_id: OrderId, *, postal_code: PostalCode
    ) -> None: ...

    def requested(self) -> tuple[OrderId, ...]: ...


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


class NoAddress(ShopError):
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

`Settings` is imported, not repeated: its six fields are ADR 0014's, and the snapshot renders them. The simulator builds it directly. `Rows` is imported too: its three fields (`name`, `columns`, `rows`) are in `pipeline.py`, and the snapshot renders them (6.4, W2).

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
| `Fulfilment.ship` | `UnknownId`, `NotShippable`, `NoAddress`, `IllegalTransition` | O-104 is a counter sale; O-105's customer, C-05, has no postal code (C39); O-106 was cancelled at E-12 |
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
| `jobs.count_at_close`, `.nightly_extract`, `.csv_export`, `.app_tables` | none | |

`KeyReused` belongs to the API's key store (`idempotency.py`): the same key sent again with another body. No call of contract B raises it.

`PaymentMismatch` compares a message with the payment stored under its `payment_id`, never with the order's total. Nothing in the app compares a payment with an order's total: payments are in the customer's currency and pay the lines the customer saw, planted ones included. PAY-2 is 516.98 SEK for 548.00 NOK of lines, L-03's 349.00 and the planted L-09's 199.00 (P-99), while the app's O-102 holds L-03 only.

`Payments.invoice` is S13's: consumers may pay later. Of `order_values`' 33 `unpaid` orders, 20 are web orders of 4 bags, and D7 makes only the 10-bag orders and the café's 48 business, so consumers' open invoices are in contract A. A malformed value (`Qty(0)`, `OrderId('C-01')`, a `kg` of 0) raises `ValueError` or `TypeError` where it is built, and is not a `ShopError` (ADR 0004).

### The ids the app makes

The prefixes ADR 0007 leaves to this contract. Each one differs from every other prefix, and from the outside systems' `PAY`, `R`, `W` and `V`. The width is the background trade's (C30; every kind's is in ADR 0007): wider than any id of the script.

| kind | prefix | width | made by |
|---|---|---|---|
| `shipment` | `SH` | 6 | `Fulfilment.ship` |
| `bag` | `SB` | 6 | `jobs.ship_subscription_bags` |
| `movement` | `M` | 7 | every call that writes a stock movement |
| `purchase` | `GP` | 5 | `Stock.buy_green` |
| `rule` | `PR` | 4 | `Catalogue.add_campaign`, `.set_subscriber_discount` |
| `sub_event` | `SE` | 6 | `Subscriptions.skip`, `.pause`, `.resume`, `.cancel`, and `Customers.erase` |

`SequentialIds` skips every id of the script and every id the defect log plants (L-05, L-09, ...). Nothing promises that sorting by id is sorting by time: `C-00001` sorts before `C-01`, and E-05 happened before E-03.

### Who writes each table

All 50 tables of contract A, in `contract.md`'s order. The system is copied word for word from `contract.md`. "Writer" is what makes the rows:

- an app call (`Service.call` or `jobs.job`);
- the simulator, playing an outside system;
- for a derived table, the query that derives it, run by the simulator's extract writer (6.4, 6.5).

An app-database table reaches an extract as a projection of the app's schema, written by `exports.py` (ADR 0003). The writer named here is the call that makes the rows, not the projection.

| table | system | writer |
|---|---|---|
| `customers` | app database | `Customers.register` (with the e-mail, C25); `.change`; `.erase` (removes the row) |
| `products` | app database | `Catalogue.add_product` |
| `orders` | app database | `Checkout.place`; `Checkout.credit_for` (the credit order, with `credit_of` in the app db only) |
| `order_lines` | app database | `Checkout.place`; `Checkout.credit_for` (the negative line); `Checkout.cancel` marks lines deleted, so they leave `order_lines` |
| `dated_lines` | derived: order_lines joined to orders | the extract writer: `order_lines` joined to `orders` on `order_id` |
| `prices` | app database | `Catalogue.set_price` |
| `fx_rates` | outside feed: bank rates | the simulator, as the bank |
| `payments` | payment provider | the simulator, as the provider: every message it sends, redeliveries included (PAY-1 twice), each delivered to `Payments.handle_message` or `.settle`. A refund's message (order 300's -899) follows `Payments.refund`. The app keeps its own record of each payment once, in its db |
| `order_events` | status feed | `jobs.relay`, through the `StatusFeed` port; the simulator's feed adapter writes the rows and stamps `loaded_at`. The outbox rows come from `place`, `invoice`, `handle_message` (paid), `ship`, `deliver`, `cancel` and `credit_for` |
| `stock_daily` | app database | `jobs.count_at_close`: one row per product and closed day, stamped at the day's close (C23). For 7 October the app writes P-10 36 and P-20 4, both at 7 Oct 16:00. The export writer then sends the day twice (the defect log): the first send keeps the app's 16:00 stamp and plants P-10's 26; the second, the "recount", carries the app's counts (36, 4) stamped 8 Oct 06:30 |
| `latest_stock` | derived: stock_daily, the latest count of each day | the extract writer: the row with the latest `counted_at` per product and day |
| `customer_extracts` | app database: nightly copies of customers | `jobs.nightly_extract` |
| `customer_changes` | app database: the change log of customers | the customers store, inside `Customers.register` (insert), `.change` (update) and `.erase` (delete) (ADR 0003) |
| `line_stamps` | app database: order lines with their stamps | `Checkout.place` and `.credit_for` (each line at the order's moment); `Checkout.cancel` (`is_deleted`, `updated_at` at the cancel: L-10 at E-12) |
| `raw_customers` | csv export | `jobs.csv_export`, with each customer's `email` (C25); the export writer adds the faults after it (D10) |
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

6.3 writes `packages/shop/tests/test_contract_b.py`. It renders the whole surface above as text (C27), one line per item, sorted:

- for each class in the block (`App`, `Jobs`, the seven services, `CollectingBus`, `PaymentProvider`, `StatusFeed`, `Notifier`, `Labels`, `SequentialIds`, `ScriptedIds`, `FakeClock`, `FakeProvider`, `FakeNotifier`, `FakeLabels`): each public method, and `__init__`, as `Class.method` and `str(inspect.signature(...))`;
- the functions `wire`, `memory_store` and `sqlite_store`, with their signatures;
- for each dataclass (`Item`, `PlaceOrder`, `PaymentMessage`, `Receipt`, `App`, `StatusChanged`, `HandlerFailure`, `Relayed`, `Settings`, and `Rows`, added in 6.4 W2): its fields, with their names and annotations, in order;
- `Source` and `IdKind`, as their members;
- the family: every subclass of `ShopError`, followed recursively, by name, with the signature of its `__init__`; and `FeedDown`. A second assertion checks that no module of `roastery` other than `errors.py` defines a `ShopError`.

It compares the text with the committed file `packages/shop/tests/contract_b.txt` and prints the difference when they differ. The file changes only on purpose, in the same commit as the code. 6.4 pins it at its tag.

As 6.3 built it (6.3-app.md, A19 and A39), the snapshot pins a little more than the block above shows, and leaves one thing out:

- the `__init__` of each listed class as built: the seven services, `Jobs`, `CollectingBus`, `FakeNotifier` and `FakeLabels`. The block shows none, because the simulator never builds a service (`wire` does); 6.4 confirms or changes them before the tag;
- each dataclass field's default (`Item.price = None`, `Settings.price_ttl = 300`, `Settings.relay_batch = 5`);
- the port's errors `ProviderRefused` and `ProviderUnavailable` beside `FeedDown`;
- the settings' field types `Url`, `Secret` and `Positive`, which the simulator builds `Settings` with (6.4, W38); and `Jobs.app_tables` with `Rows` (6.4, W2);
- the fields of the value types the signatures name (`BeanDetails`, `EquipmentDetails`, `Money`, `Qty`, `Email`, `PostalCode`, the nine id types, `Head`, `OrderLine`, `Placed`, `Invoiced`) and the members of the literals `Country`, `AccountKind`, `Channel` and `Status`: the simulator builds and reads them, so a reordered field or a renamed one would change contract B under the tag (6.4, W41);
- not `Fulfilment.late_shipments`, a read the pages call ("Not in contract B" above): the test leaves it out by name.

The raises table above is not checked by the test. The review checks it against the family's names (6.2 U6, then each change).
