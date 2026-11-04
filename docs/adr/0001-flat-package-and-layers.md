# 0001. A flat package and its layers

Status: accepted, 2026-11-04 (step 6.2, decisions C1 and C14)

## Context

The Design Patterns pages show the app's code. A page names a module, such as `roastery/pricing.py`, and a part of it, such as `list_price`. Phase 7 binds each page to those names and to their line numbers.

Three facts shape the package:

- Every shown line in `packages/shop` is at most 72 characters (its `ruff.toml`). A long import path eats that width (gap G16 of the map).
- The `layers` page reads the import graph with `ast`, and `import_graph` globs `*.py` in one folder.
- The app has layers (core, ports, adapters, service, api), and a rule that imports point inward. The rule needs a home that a test can read.

The teaching app the pages know today, `firm`, is one flat folder with a `LAYERS` table in `architecture.py`. The first module map (`map-patterns-devops.md` §2) keeps that shape.

## Decision

`roastery` is one flat package: `packages/shop/src/roastery/*.py`. There are no subpackages. A layer is a row of `LAYERS` in `architecture.py`, not a folder. `PACKAGE = 'roastery'`. There is no `without/` folder in the app: the naive twins stay in data-docs.

The api modules (`api`, `middleware`, `idempotency`, `cli`) get their row now (C14). They are built before phase 7, framework-free (ADR 0013).

### The layers

`LAYERS` maps each layer to its modules, sorted by name. A module sits in exactly one row.

```python
PACKAGE: Final = 'roastery'
"""The package whose modules the graph holds."""

LAYERS: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        'core': (
            'catalogue',
            'clock',
            'commands',
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

38 modules in 8 layers: core 13, ports 1, vendor 1, adapters 8, service 7, api 4, bootstrap 2, checks 2.

`INWARD` lists the layers each layer may import. The rows go from the inside out.

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

`layer_of` reads `LAYERS` the other way round:

```python
def layer_of(module: str) -> str:
    """The module's layer; raises ValueError when it has none."""
    ...
```

### Each module's job

| layer | module | its one job |
|---|---|---|
| core | `catalogue` | `Product`, `Kind`, the category path |
| core | `clock` | `local_date(now, zone)` and the zone of each country: days from moments, as a pure function (ADR 0008) |
| core | `commands` | the subscription commands as data; apply, replay, the command log |
| core | `events` | `OrderPlaced`, `OrderPaid`, `StatusChanged`; the in-process `EventBus` (ADR 0009) |
| core | `ids` | the id value types: `CustomerId`, `ProductId`, `OrderId`, `LineId`, `EventId`, `Country`, `PostalCode` (ADR 0004) |
| core | `money` | `Money(amount, currency)` on `Decimal`, `Qty`, rounding to the øre (ADR 0004) |
| core | `order` | `OrderLine`, one class per feed status, `TRANSITIONS` (ADR 0005) |
| core | `parsing` | payloads and till rows into `ParsedLine` or `Reject` (ADR 0012) |
| core | `pipeline` | the export's stages as generators |
| core | `pricing` | `Rule`, `list_price`, `subscriber`, `campaign`, the rule registry |
| core | `result` | `Ok`, `Err`, `partition` (ADR 0006) |
| core | `subscription` | `Subscription`, its periods, `bags_due(on)` |
| core | `vat` | `vat_of`, `scheme_for`, the rate rows' type (ADR 0010) |
| ports | `ports` | every port: the repositories, `Store`, `UnitOfWork`, `Outbox`, `Clock`, `Ids`, `StatusFeed`, `PaymentProvider`, `PriceRepository`; their errors |
| vendor | `provider_sdk` | the payment provider's SDK stand-in: camelCase, minor units, `ProviderApiError` |
| adapters | `cache` | the price cache in front of the price store, with its TTL |
| adapters | `exports` | the csv export (`raw_*`) and the customer extract, written through `pipeline` |
| adapters | `fakes` | `FakeClock`, `FakeProvider`, `FakeFeed`, `ClosedFeed`: the working fakes |
| adapters | `outbox` | outbox rows in memory and in sqlite; `relay` in batches to the `StatusFeed` (ADR 0009) |
| adapters | `provider` | the `PaymentProvider` port on the SDK: minor units to `Money`, SDK errors to port errors |
| adapters | `repository` | every store twice, in memory and in sqlite; the schema; the `Ids` adapters `SequentialIds` and `ScriptedIds` (ADR 0007 names them; placed here unless it says otherwise) |
| adapters | `resilience` | retry with backoff, `CircuitBreaker` |
| adapters | `uow` | the two `Store` adapters and their units of work, memory and sqlite (ADR 0003) |
| service | `checkout` | `Checkout`: place, cancel, `credit_for` (the facade) |
| service | `customers` | `Customers`: register, change, erase |
| service | `fulfilment` | `Fulfilment`: ship, deliver, `late_shipments` |
| service | `payments` | `Payments`: a provider message handled once, invoice, settle |
| service | `reports` | the read side: rows, never frames (ADR 0002) |
| service | `stock` | `Stock`: the movements (roast, write-off) and the count at close |
| service | `subscriptions` | `Subscriptions`: the commands run, with a reason each |
| api | `api` | handlers: a request dict in, a response dict out; `ShopError` to statuses |
| api | `cli` | the nightly jobs as a command, for the CronJob |
| api | `idempotency` | the key store: the same key twice, one effect |
| api | `middleware` | `logged`, `timed`, `require_role` around a handler |
| bootstrap | `bootstrap` | the one place that wires: `wire`, the two stores, `main` (ADR 0013) |
| bootstrap | `settings` | `ROASTERY_*` read once into `Settings` (ADR 0014) |
| checks | `architecture` | `import_graph`, `LAYERS`, `INWARD`, `check_direction`, `unplaced` (ADR 0015) |
| checks | `contracts` | the store promises, run on both stores (ADR 0015) |

The map's changes, as 6.2 made them:

- No `tracking.py`: web tracking is an outside system (C11).
- `Ids` and `StatusFeed` are ports in `ports.py`, beside the others.
- `clock.py` is new: ADR 0008 puts `local_date` and the country zones there. The `Clock` port stays in `ports.py`.
- `stock.py` owns the movements and the count at close.
- `exports.py` writes the csv export and the customer extract, through `pipeline.py`.
- `frames.py` (the polars bridge), `cohesion.py` (a teaching reader of classes) and `without/` (the naive twins) stay in data-docs.

### What phase 7 re-points in data-docs

The exporter (`data_docs_export/patterns_export.py`) is wired to `firm` today. Phase 7 changes:

| today | after the pin |
|---|---|
| `APP = patterns_app/`, put on `sys.path`, holds package `firm` | `roastery` comes from a pinned `shop` release, installed as a dependency; `patterns_app/` keeps only data-docs' own modules |
| `modules()` reads `patterns_app.rglob('*.py')`, keyed `firm/billing.py` | it also reads the installed package's folder (`Path(roastery.__file__).parent`), keyed `roastery/pricing.py`: the key never names `src/` or `site-packages/` |
| `frames.py`, `cohesion.py`, `without/` inside `firm/` | in a data-docs package of their own, not named `roastery` (it would hide the installed one) and importing the pinned `roastery` |
| the docstring: "the app is `firm`, so nothing hides an installed package" | inverted: the app is installed, and the local package must not shadow it |
| `<PatternsCode name="firm/...">` on 35 pages | `name="roastery/..."`, with parts and line notes read from the pinned release |
| the walks import `from firm...` | `from roastery...`, and the twins from data-docs' own package |

## Alternatives refused

| alternative | why not |
|---|---|
| A folder per layer (`roastery/core/order.py`) | It repeats `LAYERS` in the file tree, and a check would still need the table: the deletion test says the folders add nothing. Every import gets longer (`from roastery.core.order import ...`), which costs 72-character lines. The pages key on `roastery/pricing.py`. |
| `LAYERS` as module → layer, as `firm` has it | 38 rows to read on a phone instead of 8; a layer's members are scattered. A row per layer is what C1 calls a layer. `layer_of` gives the other direction in one function. |
| Layers enforced by a tool (import-linter) | A third-party dependency (ADR 0002), and the rule leaves the code: the `layers` page shows `check_direction` running, which a tool's config cannot show. |
| A `without/` folder in the app, as `firm` has | The naive twins are wrong on purpose. Shipping them in the app puts broken code in the release that the simulator runs, and `import_graph` would need special cases for them. They stay in data-docs. |
| The api rows added in phase 7 | The pages need their home named before the code is written, and the layer rule must hold from the first api module. |

## Consequences

- `architecture.py` drops firm's `without` special cases (`_is_module`, the `without` branch of `layer_of`). An import of a name not in `LAYERS` is a `ValueError`.
- A module is added by adding a file and a name in one row. `unplaced` catches a file with no row (ADR 0015).
- The service and the adapters never import each other. A job that is an adapter's function (the relay, the exports) is bound to `App` in `bootstrap`, which may import both (ADR 0013).
- `cli` is in the api row, so it cannot import `bootstrap`. The entry point that reads the settings and wires lives in `bootstrap` and calls `cli` (ADR 0013).
- Module names are frozen now (ADR 0015). A rename after phase 7's pin is a page change.

## Pages served

| page | what it shows |
|---|---|
| `layers` | `import_graph` of `roastery` as a frame (`modules.layers` = module, layer, imports); `check_direction` finding the violation when a scratch copy of `pricing.py` imports `repository` (the sqlite store): core → adapters. The graph holds only `roastery`'s own modules, so a bare `import sqlite3` is not an edge; the walk imports the store module |
| `ports-and-adapters` | the hexagon: core and ports inside, adapters and api around them, `bootstrap` wiring them |
| `one-reason-to-change` | each module with its one job: a VAT change edits `vat.py` only |
| `index` | the app's shape, its own repository and a pinned release |
