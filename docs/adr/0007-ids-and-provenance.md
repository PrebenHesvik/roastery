# 0007. Ids and provenance

Status: accepted, 2026-11-04 (step 6.2, decisions C7 and C30). Replaces plan §2's "caller-supplied
ids for scripted rows".

## Context

The frozen week names its rows: O-101 to O-108, L-01 to L-12, E-01 to E-14, C-01 to C-07.
The simulator plays that week through the app, and the app's rows must come out with those
ids. Plan §2 proposed that the caller passes the id in. That covers an order, but not the
ids the app makes on its own inside a call:

- a status event (E-01 to E-14) is made by the order's move, as an outbox row;
- a stock movement is made by a sale, a roast or a count;
- a shipment is made by `ship`.

No caller sees those ids before they exist, so no caller can pass them in.

The ids also do not follow time. E-05 (O-102 placed, 5 October 21:50 UTC) happens before
E-03 (O-101 shipped, 6 October 13:40). The app asks for event ids in the order things
happen; the frozen ids are numbered by order.

The rows also carry where they came from (`source`, D13): `scripted` for the teaching week,
`simulator` for the trade around it, `visitor` for the live shop. That is a fact about the
caller, not about an order.

## Decision

**Every id the app's tables key on comes through the `Ids` port** in `roastery/ports.py`.

```python
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


class Ids(Protocol):
    def next(self, kind: IdKind) -> str:
        """A fresh id of this kind, as PREFIX-digits."""
```

The prefix of each kind is one table in `roastery/ids.py`. The ones the data already shows:

| kind | prefix | example |
|---|---|---|
| customer | `C` | C-05 |
| order | `O` | O-104 |
| line | `L` | L-10 |
| event | `E` | E-09 |
| product | `P` | P-21 |
| category | `CAT` | CAT-11 |
| campaign | `K` | K-1 |
| subscription | `S` | S-1 |

The new tables have no rows yet. Their prefixes are in contract B's id table
(`architecture.md` §5): `SE`, `SH`, `SB`, `M`, `GP`, `PR`. Each differs from every prefix
above and from the outside systems' (`PAY`, `R`, `W`, `V`).

**The background trade's ids have a fixed width per kind** (C30), wider than any id of the
script, so a background id and a scripted id never meet:

| kind | width | first background id |
|---|---|---|
| customer | 5 | C-00001 |
| order | 6 | O-000001 |
| line | 7 | L-0000001 |
| event | 7 | E-0000001 |
| product | 3 | P-001 |
| category | 3 | CAT-001 |
| campaign | 3 | K-001 |
| subscription | 5 | S-00001 |
| sub_event | 6 | SE-000001 |
| shipment | 6 | SH-000001 |
| bag | 6 | SB-000001 |
| movement | 7 | M-0000001 |
| purchase | 5 | GP-00001 |
| rule | 4 | PR-0001 |

The widths hold three years of trade with room. The script's ids keep their own shape
(C-01, O-101, L-12, K-1, S-7): they are the frozen rows'.

**Nothing promises that sorting by id is sorting by time.** `C-00001` sorts before `C-01`,
and E-05 happened before E-03. A reader orders by a moment (`event_at`, `updated_at`), never
by an id.

**Ids the app does not make** are stored as they arrive, never through `Ids`:

| id | made by | system in `contract.md` |
|---|---|---|
| `payment_id` (PAY-1) | the provider | payment provider |
| `receipt_id` (R-5001), `member_no`, `ean` | the till | till |
| `event_id` (W-01), `visitor_id` (V-1), `visit_id` | the tracker | web tracking |

`customer_changes.seq` is not an id either: the store writes it as a counter in the change's
transaction (ADR 0003).

**Two adapters** stand at the seam, so it is a real one. Both live in `roastery/repository.py`,
beside the stores (ADR 0001):

```python
class SequentialIds:
    """The next number of each kind, skipping the reserved."""

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
```

- The API wires `SequentialIds`, started from the highest number of each kind in the store.
- The simulator wires `ScriptedIds`. Its list for `event` is in the order the script makes
  the calls: E-01, E-02, E-05, E-06, E-03, and so on. When a kind's list is used up, it asks
  `then`.
- The simulator wires the app twice over one store (below). Both wirings share one
  `SequentialIds`. Its `skip` set is every id of the script and every id the defect log plants
  (L-05, L-09, ...), so the sequence never makes an id the export writer will also write. With
  the widths above the two cannot meet anyway; the skip set holds the rule if a width is ever
  changed.

**The store refuses a duplicate id.** An insert whose key exists raises `DuplicateId(kind,
value)`, a `ShopError` (ADR 0006): sqlite through its primary key, the memory twin through
its dict. The contract suite runs this check on both stores (ADR 0015).

**`source` is a wiring argument.** The domain and the services never see it.

```python
Source = Literal['scripted', 'simulator', 'visitor']


def wire(
    store: Store, clock: Clock, ids: Ids, source: Source
) -> App: ...
```

- The unit of work stamps `source` on every row it writes (ADR 0003).
- The simulator wires `scripted` (with `ScriptedIds`) and `simulator` (with the shared
  `SequentialIds`) over the same store and clock. Each call of its script goes to one of the
  two.
- The API wires `visitor`.

## Alternatives refused

| alternative | why refused |
|---|---|
| caller-supplied ids (plan §2) | covers orders and customers, not E-01 to E-14, movements or shipments, which the app makes inside a call. Every command would also grow id parameters that the API's callers do not have |
| the store's autoincrement | cannot make O-101 at the week's moment; the memory twin and sqlite would number differently; ties the domain's ids to one adapter |
| `uuid4` | not the `PREFIX-digits` shape the frozen rows have; not deterministic (CLAUDE.md: the same seed gives the same bytes; no unseeded `random`) |
| ids rewritten after the run, mapping the app's ids onto the script's | the outbox, the feed and `line_stamps` would hold other ids than `orders`; a mapping layer hides drift instead of refusing it |
| `ScriptedIds` alone, with no fallback | the trade around the week, and any call the script did not foresee, would have no id |
| `source` on the commands or the domain types | every command grows a parameter the API always sets the same way; the `ports-and-adapters` page would show `scripted` inside domain code |
| one wiring with `source` switched per call | the wiring would hold state that changes between calls; two wirings over one store say the same with no state |

## Consequences

- An `Ids` adapter decides the id; the service only asks for one. Contract B's commands take
  no id for a row the app makes (ADR 0011).
- The script must list each kind's ids in the order of its calls. 6.4 builds that list from
  the frozen rows' moments (`event_at`, `updated_at`), not from the ids' numbers.
- Rows the export writer plants (L-05, L-09, D10) are not in the script: the app never makes
  them, and `SequentialIds` skips their ids (C30). A script that asks the app for L-09 would
  raise `UnknownProduct` on P-99.
- `lesson_ids` maps order 300 to the `O-...` id the app gave the credit order (S9). That id
  comes from the same sequence, so it has the same shape.
- A duplicate is loud. If 6.4's script and the sequence ever meet, the run stops at the call.
- `source` reaches an extract only where a page needs it (D13).

## Pages served

| page | what it shows from this ADR |
|---|---|
| `ports-and-adapters` | `Ids` with two adapters, and the simulator wiring the app twice as the second driving adapter beside the API |
| `depend-on-abstractions` | a service that asks `Ids.next` and does not know which adapter answers |
| `fakes-over-mocks` | `SequentialIds` as a working fake in a test: real ids, no recorded calls |
| `contract-tests` | `DuplicateId` checked on the memory store and on sqlite |
| `repository` | the store refusing a second O-101 |
