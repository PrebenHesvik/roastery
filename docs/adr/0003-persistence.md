# 0003. Persistence

Status: accepted, 2026-11-04 (step 6.2, decisions C3, C20, C25, C26, C31 and C32)

## Context

The app keeps customers, orders, payments, stock, subscriptions and prices. Every write that matters downstream is seen by another system:

- a status change goes to the status feed, through the outbox (ADR 0009);
- a change to a customer is a row of `customer_changes`, the change log the Pipeline pages read;
- the nightly extracts are copies of the app's tables.

So a change and its record must be kept together, or not at all. If the order is kept and its outbox row is lost, the feed never hears of it. If a customer moves and the change row is lost, the log is wrong for good.

The pages show the repository and the unit of work. A page can show them only if they are code in the app, not inside a library. The `contract-tests` page runs the same checks on two stores, and the `repository` page swaps one store for the other. One adapter would make the repository seam hypothetical; two make it real.

Plan §5 recommends the standard library's `sqlite3` behind hand-written repositories.

## Decision

### Two stores behind the same ports

Every store is a port in `ports.py` with two adapters in `repository.py`: a dict in memory and a table in sqlite. They take domain objects in and give domain objects back. Rows and SQL stay inside `repository.py`. Neither commits: the unit of work decides.

```python
class OrderRepository(Protocol):
    """Orders by id; an id is taken once."""

    def add(self, order: Order) -> None:
        """Keep a new order; DuplicateId if the id is taken."""
        ...

    def get(self, order_id: OrderId) -> Order:
        """The order; UnknownId if there is none."""
        ...

    def save(self, order: Order) -> None:
        """Keep the order's new state over its old one."""
        ...

    def all(self) -> list[Order]:
        """Every order, sorted by order id."""
        ...
```

| rule | memory | sqlite |
|---|---|---|
| a listing is sorted by its key | `sorted(..., key=...)` | `ORDER BY` on every `SELECT` that returns more than one row |
| a duplicate id is refused | `DuplicateId` | `DuplicateId` (the primary key; the `IntegrityError` is turned into it) |
| an unknown id | `UnknownId`, a `ShopError` (ADR 0006) | the same |
| money | `Decimal` | `TEXT` holding the decimal, read back with `Decimal(text)`; never `REAL` |
| a moment | an aware `datetime` in UTC | `TEXT`, ISO 8601 in UTC |
| a day | `date` | `TEXT`, ISO 8601 |

### The schema is the app's own

`repository.py` holds the schema (`SCHEMA`, `create_tables`). The app database is designed for the app: its tables and columns serve the services. It is not contract A.

Contract A's app-database tables are projections of it, written by `exports.py` (ADR 0001): a column may be renamed, cut or derived on the way out. The app may hold what no extract shows; `orders.vat_amount` is one such column (C18, ADR 0010).

### A unit of work holds the change and its records

A unit of work is one transaction over every repository. It has two more stores that no service may forget:

- `uow.outbox`: a status change adds its `StatusChanged` row here (ADR 0009);
- the customers store writes its own `customer_changes` row on every insert, update and erase.

```python
class UnitOfWork(Protocol):
    """One transaction over every store of the app.

    Open it with `with`, write through its stores, call
    commit(). Leaving the block undoes what was not committed.
    """

    customers: CustomerRepository
    orders: OrderRepository
    outbox: Outbox
    ...

    def __enter__(self) -> UnitOfWork: ...

    def __exit__(self, *exc: object) -> None: ...

    def commit(self) -> None: ...
```

The change log is written by the store, not by the service. The customers store promises it, so a caller cannot change a customer without a change row. `contracts.py` checks that promise on both stores (ADR 0015).

```python
class CustomerRepository(Protocol):
    """Customers by id, with the change log they write."""

    def add(self, customer: Customer, at: dt.datetime) -> None:
        """Keep a new customer, and an insert row in the log."""
        ...

    def change(self, customer: Customer, at: dt.datetime) -> None:
        """Keep the new values, and an update row in the log."""
        ...

    def erase(self, customer_id: CustomerId, at: dt.datetime) -> None:
        """Remove the customer; a delete row with the key only."""
        ...

    def changes(self) -> list[CustomerChange]:
        """The log, sorted by seq."""
        ...
```

`Customer` and `CustomerChange` are core types in `roastery/customer.py` (ADR 0001). A customer carries an e-mail (C25), ending in `example.invalid`; it reaches contract A only in `raw_customers`, through the csv export. `customer_changes` has no e-mail column, so the log row of an update carries the country and postal code as they are after it, whatever changed: every update writes one row, as `contract.md` says ("every insert, update and delete").

`seq` is given by the store, from 1 up, as `MAX(seq) + 1` inside the transaction. Memory and sqlite give the same numbers. An erase is a tombstone: its row carries the key, and its country and postal code are empty. Orders keep the customer's id after an erase (O-107 still names C-07).

### One store, a unit of work per wiring

Every app table has a `source` column (`scripted`, `simulator` or `visitor`; plan §2). The unit of work stamps it on every row it writes, from the source it was made with. The services never pass it (ADR 0007).

The simulator wires the app twice over one store (ADR 0007). So the shared thing is the store, and each wiring gets its own unit of work over it:

```python
class Store(Protocol):
    """The app's tables: one database, or one set of dicts."""

    def unit_of_work(self, source: Source) -> UnitOfWork:
        """A unit of work over these tables, stamping `source`."""
        ...
```

`uow.py` has the two adapters: `SqliteStore` (a connection) and `InMemoryStore` (the dicts). Two units of work over one store see each other's commits. They are used one at a time: the simulator plays one call after another.

**One price cache per store** (C31). Each store adapter is built with one `CachedPrices` (`cache.py`), in front of its prices, and every unit of work of that store reads list prices through it. `Catalogue.set_price` evicts the product's entry when its unit of work commits. Both wirings of the simulator share the store, so they share the cache and see one eviction: no wiring can price a cart from an entry the other made stale. The cache is a concrete class, not a port: it has one adapter, and a port with one adapter fails the deletion test. `bootstrap`'s store constructors take the clock and `price_ttl` for it (ADR 0013).

**Which store runs what** (C32). `full` and `month` are played on sqlite. The memory store serves the tests, the walks and `tiny`. The memory unit of work copies the store's dicts per call (below), which is quadratic over three years of trade.

### sqlite's transaction mode

The sqlite unit of work needs a connection in `sqlite3`'s default mode, as firm's `uow.py` does:

- `connection.autocommit` is `sqlite3.LEGACY_TRANSACTION_CONTROL`, and `isolation_level` is not `None`; the constructor raises `ValueError` otherwise;
- `__enter__` runs `BEGIN`; `commit()` commits; `__exit__` always rolls back, so a write after the last commit is undone too;
- a unit of work cannot be opened twice at once (`RuntimeError`).

The memory unit of work keeps a copy of the store's dicts when the block opens and at each commit, and puts the copy back into the store when the block ends. It has no isolation: there is one caller at a time. The copy is why the memory store is kept to small runs (C32).

The caller opens the sqlite connection and closes it. `bootstrap.sqlite_store` checks the mode, makes the tables and returns the `SqliteStore` (ADR 0013).

## Alternatives refused

| alternative | why not |
|---|---|
| An ORM (SQLAlchemy) | It is a dependency (ADR 0002). Its session is a unit of work and its mapper a repository: the patterns the pages show would sit inside the library, out of sight. |
| sqlite only, no memory twin | One adapter makes the repository seam hypothetical. The `depend-on-abstractions` and `contract-tests` pages need two stores giving the same answer, and the walks need a store with no file. |
| the memory store for `full` too | Its copy per call grows with the store: three years of trade would take hours. sqlite is the store of the long runs (C32) |
| a `PriceCache` port, or a cache per wiring | One adapter makes the port hypothetical. A cache per wiring would let one wiring's `set_price` leave the other's entry stale, and plant the cache-aside page's stale price in the data (C31) |
| The extracts' tables as the app's schema | Contract A's tables are shaped for the reader (one grain, the cast's rows, faults in the csv export). The app would carry its readers' shape, and a new extract would change the app. |
| The service writes `customer_changes` | Each command would have to remember it; one forgotten call leaves a change with no row. The store owning it is the deeper module: one place, checked on both stores. |
| A sqlite trigger writes `customer_changes` | The memory twin cannot have a trigger, so the two stores would differ in the one place the log is made. The trigger also hides the rule from the page. |
| `autocommit=False` (Python 3.12's mode) | It opens a transaction at connect and after each commit, which changes when a `BEGIN` is legal. One mode, checked at the start, is simpler; firm's walks already teach it. |
| Money as `REAL` | 129.00 kr as a float is not 129.00. Money is `Decimal` everywhere (the repo's rules). |

## Consequences

- Every store has two adapters, and 6.3 writes both. `contracts.py` runs the same checks on both (ADR 0015).
- A listing without `ORDER BY` is a bug the teachability test looks for (ADR 0015). Memory listings are sorted the same way.
- `source` is stamped by the unit of work, so no service signature carries it.
- The outbox row and the change row commit with the change or are undone with it. No handler, job or second transaction writes them (C26).
- `exports.py` owns the mapping from the app's schema to contract A. A change to an app column is a change there, not in the extracts' contract.
- A sqlite connection in another mode is refused at once, not after a half-written task.

## Pages served

| page | what it shows |
|---|---|
| `repository` | `OrderRepository` in memory and in sqlite; `all()` sorted by order id; the SQL that the service no longer holds |
| `unit-of-work` | placing an order: the order, its lines, the stock it takes and the outbox row in one commit; an unknown product (P-99) undoes all of it |
| `depend-on-abstractions` | `sales_by_customer` gives the same totals from the dict store and from sqlite |
| `contract-tests` | the same checks on both stores; a store that lists in insertion order fails |
| `outbox` | the `StatusChanged` row written in the order's transaction (ADR 0009) |
