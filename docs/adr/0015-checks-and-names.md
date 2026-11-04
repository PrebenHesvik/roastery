# 0015. Checks and names

Status: accepted, 2026-11-04 (step 6.2, decisions C16 and C17)

## Context

The architecture is only as good as what holds it. Three rules can drift without a test:

- imports point inward (ADR 0001);
- the memory store and the sqlite store keep the same promises (ADR 0003);
- the code stays teachable: pages show it on a phone, and the data must come out the same from the same seed.

Plan §5 point 4 asks for the teachability rules to be enforced by ruff and a test: 72 characters, no module state, no wall clock, sorted listings.

The pages also bind to names. A page shows `roastery/pricing.py`, part `list_price`, with notes on its line numbers. Data-docs' exporter (`patterns_export._parts`) cuts a module into its top-level functions, classes and assignments by name. A renamed module or part breaks a page; a moved line breaks a note.

## Decision

### `architecture.py`: the direction rule

`architecture.py` (checks) holds `PACKAGE`, `LAYERS` and `INWARD` (ADR 0001), and three functions, as firm's:

```python
def import_graph(package_dir: Path) -> list[ImportEdge]:
    """Every import between roastery's modules, sorted by edge.

    Each module is read with `ast`, never run. Every import
    counts: one inside a function or under TYPE_CHECKING too.
    """
    ...


def check_direction(
    edges: Iterable[ImportEdge],
    allowed: Mapping[str, Collection[str]] = INWARD,
) -> list[Violation]:
    """The edges whose target layer `allowed` does not list."""
    ...


def unplaced(package_dir: Path) -> list[str]:
    """The modules on disk that no row of LAYERS names, sorted."""
    ...
```

Firm's special cases for `without/` are gone (ADR 0001). `import_graph` globs `*.py` in the one folder and leaves out `__init__.py`. An `import roastery` followed by `roastery.x` is not seen; the code writes `from roastery import x` or `from roastery.x import y`.

A test in `packages/shop/tests` asserts:

- `check_direction(import_graph(dir)) == []`;
- `unplaced(dir) == []`;
- no module is in two rows of `LAYERS`;
- every name in `LAYERS` that has no file yet is in the test's `AWAITING` list. The list shrinks as 6.3 builds, and is empty before the release phase 7 pins.

### `contracts.py`: both stores, one suite

`contracts.py` (checks) holds the promises of each store port as checks any adapter can be run by, as firm's `check_line_repository`:

```python
def check_orders(
    make: Callable[[], UnitOfWork],
) -> list[Check]:
    """Run every order check on a new, empty store."""
    ...
```

Each check gets a new, empty store from `make` and raises `Broken` when the store does something the port does not promise. The test runs every suite on `memory_store` and on `sqlite_store` over `:memory:`, and asserts the two give the same `Check` rows, all passed. The promises include, for every store:

- add, then get, gives back an equal object;
- a second add of the same id raises `DuplicateId`, and the first is kept;
- a listing is sorted by its key, whatever the order of adding;
- an unknown id raises the store's `UnknownId`, a `ShopError`;
- leaving a unit of work without commit undoes every write: the change, its outbox row and its `customer_changes` row;
- the outbox: a waiting batch keeps its rows (ADR 0009); the change log: `seq` from 1 up, a tombstone carries the key only (ADR 0003).

`contracts.py` imports only core and ports, so it is run by a store, never wired to one.

### The teachability test

One test reads every module of `roastery` with `ast` and fails, naming the module and line, on each of these:

| rule | how it is found |
|---|---|
| no module state | a top-level assignment whose value is a list, dict or set display, a comprehension, or a call other than `MappingProxyType`, `NewType`, `frozenset`, `tuple`, `Decimal` or `TypeVar`; a `global` statement anywhere |
| no wall clock | a call of `datetime.now`, `datetime.utcnow`, `datetime.today`, `date.today`, `time.time`, `time.time_ns`, `time.monotonic`, `time.perf_counter` |
| no unseeded randomness | a call of a `random` module function (`random.random`, `random.choice`, ...), `random.Random()` with no seed, `uuid.uuid1`, `uuid.uuid4`, `os.urandom`, or any use of `secrets` |
| listings sorted | a SQL string that begins with `SELECT` and has no `ORDER BY`, unless the call that runs it ends in `.fetchone()` |
| 72 characters | ruff's `E501`, with `line-length = 72` in `packages/shop/ruff.toml`; CI runs `ruff check` |

Memory listings are held by `contracts.py`, which checks the order on both stores.

Time comes through the `Clock` port (ADR 0008), ids through the `Ids` port (ADR 0007). No module of `roastery` holds a wall-clock adapter, so the test needs no exemption. The caller brings the clock: the simulator its own, a test `FakeClock`, the cli the moment it is given (ADR 0013), the live shop its UTC clock outside `packages/shop`.

### Names: frozen in two steps

| what | frozen | a change after that means |
|---|---|---|
| the module names of `LAYERS` | now, by contract C | a new ADR and a page change |
| the top-level parts each page shows (listed in `architecture.md` §3 as intended) | at phase 7's pin of a `shop` release | a page change in data-docs, a new `shop` release, a new pin |
| the line numbers a page's notes name | at the same pin | the same |

Before the pin, 6.3 and 6.4 may rename a part or move a line freely: no page reads them yet. A part listed in the pattern map that 6.3 names differently is fixed in `architecture.md` §3 in the same commit.

After the pin, a rename is a page change: the page's `<PatternsCode name part>` and its notes move with it, and data-docs pins the new release.

## Alternatives refused

| alternative | why not |
|---|---|
| import-linter for the layers | A dependency (ADR 0002), and the check leaves the code the `layers` page runs. |
| Review instead of a test for the teachability rules | One `datetime.now` in three years of simulated trade makes the data differ by run, and nobody sees it in review. The determinism check would fail with no pointer to the line. |
| Contract tests on the sqlite store only | The memory store is what the walks and most tests use; if it drifts, they tell lies about sqlite. The suite on both is the `contract-tests` page's lesson. |
| Freeze the parts now, with the module names | 6.3 has not written them. A freeze before the code would force names chosen blind, or a stream of ADRs. Pages bind at the pin, so the parts freeze there. |
| Freeze nothing until phase 7 | 6.3 writes against module names, and the pattern map names a home for each page. A module renamed after 6.3 would ripple through the map, the ADRs and contract B. |
| A wall-clock adapter in `roastery`, exempt in the test | One exemption becomes two. The caller always has a clock to give; the app need never hold one. |

## Consequences

- 6.3 writes the three tests (direction, contracts on both stores, teachability) before the modules they guard, and keeps them green.
- `AWAITING` lists the unbuilt modules; it is empty before phase 7's pin.
- A module-level constant is `Final` and immutable: a tuple, a frozenset, a `MappingProxyType`.
- The pattern map in `architecture.md` §3 is kept in step with the code until the pin; after it, data-docs is.
- Contract B's snapshot test (ADR 0011) is a fourth check of the same kind: a list committed, compared with the code.

## Pages served

| page | what it shows |
|---|---|
| `layers` | `import_graph` as a frame; `check_direction` finding the one violation |
| `contract-tests` | the same checks on the memory and sqlite stores, a frame of `check`, `memory`, `sqlite`; a store that lists in insertion order fails `all is ordered` |
| `fakes-over-mocks` | the fake held honest by the contract suite |
| `pure-core-imperative-shell` | why the core never reads the clock: the teachability test's wall-clock rule |
| `index` | the app's names, frozen at the pin |
