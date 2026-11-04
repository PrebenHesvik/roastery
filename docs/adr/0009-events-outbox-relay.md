# 0009. Events, the outbox and the relay

Status: accepted, 2026-11-04 (step 6.2, decision C9)

## Context

Two kinds of telling happen when an order changes.

- **Inside the app.** When an order is paid, other parts react: the receipt, the next subscription bag. The part that pays should not import them all.
- **Outside the app.** Every status change goes to the status feed, an outside system. `order_events` is that feed: one row per change, with `event_at` (when it happened, UTC) and `loaded_at` (when the feed took it).

The feed is where the data shows the cost of sending. Three rows of `dataset.sql` must come out of the mechanism, not be typed in:

| event | order | status | event_at | loaded_at |
|---|---|---|---|---|
| E-08 | O-102 | delivered | 8 Oct 12:00 | 10 Oct 07:00 |
| E-09 | O-104 | placed | 6 Oct 15:20 | 6 Oct 15:45 |
| E-10 | O-104 | paid | 6 Oct 15:21 | 6 Oct 15:30 |

E-08 is two days late. E-10 lands before E-09, and E-09 lands once. Gap G15 of the map asked for a reason. The reason is the one a real outbox gives: E-09's batch failed and was sent again, while the batch after it went.

The teaching app today, `firm`, has an `EventBus` in `events.py`, an outbox in `outbox.py` and a `relay` that sends one row at a time and stops at the first failure. Stopping cannot land E-10 before E-09.

## Decision

### The bus, in core

`events.py` (core) holds the events and an in-process `EventBus`, as firm's:

- `subscribe(event_type, handler)`; handlers are called in the order they subscribed;
- `publish(event)` calls each handler of the event's class before it returns;
- a handler that raises does not stop the others: when all have run, `publish` raises `HandlersFailed` naming each failure;
- nothing is queued or retried; the handlers live in the bus object only (no module state).

`bootstrap.wire` makes the bus and subscribes the handlers (ADR 0013). The service publishes after its commit, as firm's `approve_sheet` does. So a handler sees only what is kept, and a handler that fails cannot undo the change.

A handler writes no row of contract A. What must be kept with the change is written in the change's unit of work. A handler is for work that may fail on its own: the receipt, the next bag's booking.

### The outbox

Every status change of an order is a `StatusChanged` row in the outbox, written in the change's unit of work (ADR 0003). The order's new state and its row are kept together or not at all. Paying an open invoice adds a payment and no status event (ADR 0005).

```python
@dataclass(frozen=True)
class StatusChanged:
    """An order moved to a status of the feed, at a moment."""

    event_id: EventId
    order_id: OrderId
    status: Status
    event_at: dt.datetime
```

`event_id` comes from the `Ids` port (ADR 0007), and `event_at` is the clock's `now()` at the change (ADR 0008).

```sql
CREATE TABLE IF NOT EXISTS outbox (
    position INTEGER PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    order_id TEXT NOT NULL,
    status TEXT NOT NULL,
    event_at TEXT NOT NULL,
    batch INTEGER,
    sent INTEGER NOT NULL DEFAULT 0
)
```

`position` is given by `add`, from 1 up. `batch` is empty until the relay puts the row in a batch. A batch keeps its rows: a waiting batch is sent again as it was, and new rows never join it. The memory outbox has the same fields and the same rules.

```python
@dataclass(frozen=True)
class Batch:
    """Rows sent together: all are taken, or none."""

    number: int
    events: tuple[StatusChanged, ...]


class Outbox(Protocol):
    """StatusChanged rows, kept in the change's transaction."""

    def add(self, event: StatusChanged) -> int:
        """Keep the event, in no batch; returns its position."""
        ...

    def form_batches(self, size: int) -> tuple[int, ...]:
        """Put the rows in no batch into new batches, by position.

        Each holds `size` rows; the last may hold fewer.
        """
        ...

    def waiting(self) -> tuple[Batch, ...]:
        """The batches not yet sent, by number."""
        ...

    def mark_sent(self, number: int) -> None: ...
```

### The feed, a port

`StatusFeed` is a port in `ports.py`. The adapter stamps `loaded_at` from its own clock as it takes a batch. `loaded_at` is the feed's column, never the app's.

```python
class FeedDown(ConnectionError):
    """The feed did not take the batch; none of it was kept."""


class StatusFeed(Protocol):
    """Where the status changes go; it stamps loaded_at."""

    def send(self, events: Sequence[StatusChanged]) -> None:
        """Take every event of the batch, or raise FeedDown."""
        ...
```

Two adapters stand at this seam, so it is real:

- `fakes.FakeFeed` keeps what it took, stamps it from the clock it is given, and refuses the batches it is told to refuse;
- the simulator's feed (in `roastery_sim`, ADR 0012) writes the status feed table, stamps `loaded_at` from the simulator's clock, and refuses the batches the script names.

### The relay

`relay` lives in `outbox.py` (adapters). It works through the `UnitOfWork` and `StatusFeed` ports, so it runs the same on both stores.

```python
@dataclass(frozen=True)
class Relayed:
    """What a run did: the batches sent and those that wait."""

    sent: tuple[int, ...]
    waiting: tuple[int, ...]


def relay(
    uow: UnitOfWork, feed: StatusFeed, *, size: int
) -> Relayed:
    """Form new batches, then offer each waiting one to the feed.

    A batch the feed refuses waits for the next run; the batches
    after it still go. A batch is marked sent only after the feed
    took it: at least once, never lost, perhaps twice.
    """
    with uow:
        uow.outbox.form_batches(size)
        uow.commit()
    with uow:
        batches = uow.outbox.waiting()
    sent: list[int] = []
    waiting: list[int] = []
    for batch in batches:
        try:
            feed.send(batch.events)
        except FeedDown:
            waiting.append(batch.number)
            continue
        with uow:
            uow.outbox.mark_sent(batch.number)
            uow.commit()
        sent.append(batch.number)
    return Relayed(tuple(sent), tuple(waiting))
```

`relay` is a job of contract B (ADR 0011). The job takes no arguments: `bootstrap` binds it to the wired store, the wired feed and `size=settings.relay_batch` (`ROASTERY_RELAY_BATCH`, ADR 0014). The service layer never calls it: service and adapters do not import each other (ADR 0001). The simulator calls the job on its schedule.

### How the week's rows arise

| row | what happened |
|---|---|
| E-10 before E-09 | At the 15:30 run on 6 October the relay forms new batches. E-09 is the last row of one batch and E-10 the first of the next. The feed refuses E-09's batch; E-10's batch goes and is stamped 15:30. At the 15:45 run, E-09's batch is offered again, as it was, and is stamped 15:45. E-09 is in the feed once. |
| E-08 late | E-08 is written at 12:00 on 8 October. Its batch is not taken until the run at 07:00 on 10 October: the feed refuses its batch at the runs on 8 and 9 October, though the relay runs both days (E-04 and E-13 are loaded then). |
| one `loaded_at` per run | Every batch a run sends gets the moment of that run (E-01 and E-02 at 08:15; E-05 and E-06 at 22:00). |

The batch boundary between E-09 and E-10 is the simulator's to make, by construction (6.4; plan risk "E-09 and E-10 land in one batch"). A simulator test holds it.

The relay did run on 8 and 9 October: E-04 is loaded at 8 October 11:00, and E-13 and E-14 at 9 October 19:45. So E-08 is late because its batch is refused on two runs, not because the relay did not run. 6.4's script names the two refused runs; the default in plan §5 says the same (`RELAY_BATCH = 5`).

### Downstream

A batch the feed took but the relay did not mark (a crash between `send` and `mark_sent`) is sent again. The feed then holds its events twice. A reader dedupes by `event_id`, the key of `order_events`. The baseline week has no such crash, so `order_events` holds each event once.

### What is not promised

- order across batches: a later batch may land first (E-10);
- exactly once: at least once, deduped by `event_id`;
- a bound on `loaded_at - event_at` (E-08 waits two days);
- a run at any given moment: the caller runs the job;
- a change of `ROASTERY_RELAY_BATCH` reshaping batches already formed.

Within a batch, events are in outbox order.

## Alternatives refused

| alternative | why not |
|---|---|
| Send at commit, no outbox | A feed that is down at commit loses the event, or fails the order. The `outbox` page's whole lesson is that the row is kept with the change. |
| firm's relay: row by row, stop at the first failure | Order is kept, so E-10 can never land before E-09. The data has E-10 first; only batches that may fail alone give it. |
| Re-form the batches at each run | A waiting batch would take in new rows, and its members would change from run to run. A batch number would mean nothing, so the script could not name "the batch the feed refuses"; rows written after the failure would share its fate. A batch that keeps its rows is one the script, the test and the reader can name. |
| `loaded_at` stamped by the app | The moment the feed took the row is the feed's fact. If the app stamped it before sending, a refused batch would carry a moment it was never loaded. |
| A message broker (Kafka, Redis streams) | A dependency (ADR 0002) and an outside process for a shop that sends a few hundred events a day. The port lets a broker stand behind it later. |
| Handlers write the store (the warehouse moves stock on `OrderPaid`) | A handler that fails after the commit leaves half a change. What must be kept goes in the unit of work; the bus is for work that may fail on its own. |

## Consequences

- The outbox and the bus are two tools: the outbox for what must reach another system, the bus for reactions inside the app.
- 6.3 writes `outbox.py` with both outboxes, `relay`, and a test per row of "How the week's rows arise", on both stores, with `FakeFeed`.
- `contracts.py` checks the outbox's promises on both stores: a rollback undoes the row; a waiting batch keeps its rows; `waiting` is sorted.
- Readers of `order_events` dedupe by `event_id` and order by `event_at`, never by `loaded_at`.
- 6.4's script names which batches the feed refuses, and when.

## Pages served

| page | what it shows |
|---|---|
| `outbox` | the `StatusChanged` row kept in the order's transaction; a refused batch that waits while the next one goes (E-10 before E-09); at least once: a batch sent twice, deduped by `event_id` |
| `observer-and-events` | `OrderPaid` with its handlers subscribed in `bootstrap`; one handler raises, the others run, `HandlersFailed` names it |
| `state-machine` | the statuses of `order_events`, one row per legal move |
| `ports-and-adapters` | `StatusFeed` with two adapters: `FakeFeed` and the simulator's feed |

The Pipeline route's `late-and-out-of-order` page reads what this mechanism makes: E-08 late, E-10 before E-09.
