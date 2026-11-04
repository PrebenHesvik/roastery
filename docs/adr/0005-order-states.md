# 0005. The order's states

Status: accepted, 2026-11-04 (step 6.2, decisions C5, C21 and C22)

## Context

An order moves through statuses, and two tables see each move:

- `order_events` (system: status feed) holds one row per status change: placed, paid or
  invoiced, shipped, delivered, cancelled. The app sends them through its outbox (ADR 0009).
- The `state-machine` page reads `order_events` and teaches one table of legal moves. So the
  app's table and the feed's statuses must be the same six names, or the page argues against
  its own data.

The data fixes the moves:

| row | what it forces |
|---|---|
| O-101: E-01 placed, E-02 paid, E-03 shipped, E-04 delivered | the full path of a paid web order |
| O-104: E-09 placed, E-10 paid, PAY-4; channel `shop` | a counter sale ends at paid; it is never shipped |
| O-106: E-11 placed, E-12 cancelled; L-10 in `line_stamps` with `is_deleted` true at E-12's moment | a cancel soft-deletes the lines; the order had a line when it was placed |
| `order_values.status = 'unpaid'` (S13) | an order on invoice ships before it is paid; its invoice can still be open on 30 September 2026 |
| order 300, `amount` -899, `status` refund (S14) | a return is a credit order of its own, at the counter, with a negative line and a negative payment |

S13 adds `invoiced` to the statuses: business accounts always pay by invoice, and consumers
may pay later. An invoiced order is shipped and delivered like a paid one. When the invoice is
paid, the feed shows nothing new: no status in the feed means "invoice paid".

The firm's `timesheet.py` is the model: one class per state, a `TRANSITIONS` mapping, a
`check` that raises, and a `describe` that uses `match` with `assert_never`.

## Decision

`roastery/order.py` holds **one frozen class per feed status**: `Placed`, `Paid`,
`Invoiced`, `Shipped`, `Delivered`, `Cancelled`. `Order` is their union. What every state
shares sits in a `Head`.

```python
@dataclass(frozen=True)
class Head:
    order_id: OrderId
    customer_id: CustomerId
    channel: Channel
    country: Country  # as order_country chose it
    lines: tuple[OrderLine, ...]  # one or more
    credit_of: OrderId | None  # set on a credit order only


@dataclass(frozen=True)
class Placed:
    head: Head


@dataclass(frozen=True)
class Paid:
    head: Head
    payment_id: PaymentId


@dataclass(frozen=True)
class Invoiced:
    head: Head


@dataclass(frozen=True)
class Shipped:
    settled: Paid | Invoiced
    shipment_id: ShipmentId

    @property
    def head(self) -> Head:
        return self.settled.head


@dataclass(frozen=True)
class Delivered:
    settled: Paid | Invoiced
    shipment_id: ShipmentId

    @property
    def head(self) -> Head: ...


@dataclass(frozen=True)
class Cancelled:
    head: Head
    reason: str


Order = Placed | Paid | Invoiced | Shipped | Delivered | Cancelled
```

- A `Head` with no lines is refused when it is built.
- `country` is the country `order_country` chose when the order was placed (C22), so `scheme_for(order, on)` reads it from the order. It is never `None`: a customer with no country gets Norway there, explicitly (ADR 0010).
- Only a `Paid` order, or one shipped or delivered from `Paid`, has a payment id.
- **The settlement is carried.** `Shipped` and `Delivered` hold the `Paid` or `Invoiced` they
  came from. It is fixed at the move and never changes after it.

**The table of legal moves** is keyed on exactly the six class names:

| from | action | to |
|---|---|---|
| `Placed` | `pay` | `Paid` |
| `Placed` | `invoice` | `Invoiced` |
| `Placed` | `cancel` | `Cancelled` |
| `Paid` | `ship` | `Shipped` |
| `Paid` | `cancel` | `Cancelled` |
| `Invoiced` | `ship` | `Shipped` |
| `Invoiced` | `cancel` | `Cancelled` |
| `Shipped` | `deliver` | `Delivered` |

`Delivered` and `Cancelled` are final: no row starts from them.

```python
Action = Literal['pay', 'invoice', 'ship', 'deliver', 'cancel']
Status = Literal[
    'placed',
    'paid',
    'invoiced',
    'shipped',
    'delivered',
    'cancelled',
]

TRANSITIONS: Final[Mapping[tuple[str, Action], str]] = MappingProxyType(
    {...}
)  # the eight rows above


def check(order: Order, action: Action) -> str:
    """The next state's name; raises IllegalTransition."""


def pay(order: Order, payment_id: PaymentId) -> Paid: ...
def invoice(order: Order) -> Invoiced: ...
def ship(order: Order, shipment_id: ShipmentId) -> Shipped: ...
def deliver(order: Order) -> Delivered: ...
def cancel(order: Order, reason: str) -> Cancelled: ...


def status(order: Order) -> Status:
    """The feed's word: the class name in lower case."""
```

- `check` raises `IllegalTransition(order_id, state, action)`, a `ShopError` (ADR 0006).
- Every move, and the placing itself, writes one `StatusChanged` outbox row whose status is
  `status(new)`, in the same transaction as the change (ADR 0003, ADR 0009). The feed's six
  words are therefore the six class names, and a test asserts the two sets are equal.

**The cases the data names:**

- **Paying an open invoice** adds a payment row and no status event. `Payments.settle` checks
  that the order is `Invoiced`, or `Shipped` or `Delivered` from `Invoiced`, and records the
  payment. The order's state object does not change. Whether an invoice is still open is read
  from the payments, not from the state:

  ```python
  def invoice_open(order: Order, paid: Iterable[Payment]) -> bool: ...
  ```

  `order_values.status = 'unpaid'` is this question asked on 30 September 2026.
- **A counter sale** (channel `shop`) goes `Placed`, then `Paid`, and stops there. O-104 is
  E-09 and E-10, paid by PAY-4. A business account's counter sale is invoiced inside `place`
  (ADR 0011), so it stops at `Invoiced` and is settled later by `Payments.settle`. The table would allow `ship` from `Paid`; the channel rule
  sits in `Fulfilment.ship`, which refuses a `shop` order with `NotShippable` (ADR 0006).
- **A credit order** (S14) is an order of its own. `Checkout.credit_for(order_id, line)`
  builds a new `Head` with channel `shop`, `credit_of` set to the sale it returns, and one
  line made by `OrderLine.credit` (a negative `Qty`, ADR 0004). It is placed and then paid by a
  negative payment, so it ends at `Paid`, like any consumer's counter sale. The original sale keeps its
  own state: there is no `returned` status. Order 300 is such an order: -899, one grinder
  (P-20) back.
- **A cancel** moves the order to `Cancelled` with a reason, and in the same transaction marks
  its lines deleted: `is_deleted` true and `updated_at` at the cancel's moment. The rows stay
  in the lines table, so `line_stamps` keeps them and `order_lines` (the lines without the
  deleted rows) does not. L-10 is O-106's line, deleted at E-12.
- **Stock moves when an order is placed**, not when it is paid. Placing writes one `sold`
  movement per line, in the same unit of work as the order, its lines and the `placed` outbox
  row. No `OrderPaid` handler writes a movement. The rows force it: O-107 was never paid, yet
  P-10's closing balance drops from 37 on 6 October to 36 on 7 October, the day O-107's L-08
  (one bag of P-10) was placed; and O-103's L-04 (three bags) takes 40 to 37 on 6 October.
- **Undoing a sale is a `sold` movement with the opposite sign** (C21). A cancel puts the
  bags back only if they left at `place`, which is always so, since stock moves when an order is
  placed; a credit order's negative line puts its bag back the same way. Contract A's five
  reasons stay: no reversal reason is added.
- **O-106 is refused.** Shipping a cancelled order is not in the table, so `ship(O-106)`
  raises `IllegalTransition`. Nothing is written.

## Alternatives refused

| alternative | why refused |
|---|---|
| one `Order` class with a `status: str` and optional `payment_id`, `shipped_on` | the flags allow states the shop never has (a cancelled order with a shipment). It is the `anaemic-model` twin, and stays in data-docs as that |
| settlement as states of its own (`PaidShipped`, `InvoicedShipped`, `PaidDelivered`, ...) | eight classes for six feed words; `TRANSITIONS` would no longer be keyed on the feed's statuses, so the page's table and `order_events` disagree |
| paying an invoice as a status event (`shipped` to `paid`) | the feed would show a step back. S13's path is placed, then paid or invoiced, then shipped, then delivered; a late `paid` breaks the `state-machine` page's "statuses in order" |
| the settlement changed in place to `Paid` when an invoice is paid | the state would change with no status event, so the state and the feed tell two stories. Payments are their own rows already; the question "is it open" belongs there |
| a return as a status of the original order (`returned`, `refunded`) | no such word in the feed; order 300 is its own row in `order_values` with its own amount and status. A partial return would need a quantity on the status |
| a return as a cancel of the original | a delivered order cannot be cancelled, and the grinder was sold and delivered; the money back needs a negative payment of its own |
| hard-deleting a cancelled order's lines | L-10 must stay in `line_stamps` for the `pipeline/deletes` lesson |
| shipping a cancelled order as a silent no-op | the simulator plays O-106 from a script; a refusal must be loud and catchable by type (C6) |
| a counter-sale state (`SoldAtCounter`) | a seventh word the feed does not have; the channel already says it |

## Consequences

- The state machine has no store and no clock. Its functions take an order and give an order;
  the service writes the result, the deleted lines and the outbox row in one unit of work.
- `credit_of` is an app-db column of `orders`. `tiny`'s `orders` keeps its four columns (D13);
  whether `month` and `full` show the link is open until 1.0 (S12). `lesson_ids` maps
  order 300 to the credit order's `O-...` id (S9).
- Order 300's original sale is chosen by 6.4's script. `credit_for` refuses a line already
  credited, and a sale that is not `Paid` or `Delivered`; contract B names those errors: `AlreadyCredited` and `NotCreditable`.
- Undoing a sale is a `sold` movement with the opposite sign (C21), so `stock_movements` keeps
  its five reasons and the signed `qty` says the direction. The week's frozen balances come out
  the same: O-106's cancel puts its bag back, and 6.4 gives L-10 a product other than P-10 and
  P-20 (ADR 0011).
- A cancel of a `Paid` order needs the money back: `Payments.refund` asks the provider, and its
  negative message is delivered to `handle_message`; the cancel itself writes no payment.
- `order.late_orders` (the pure core of the `pure-core-imperative-shell` page; its shell is
  `Fulfilment.late_shipments`) must skip `shop` orders: O-104 is paid and never ships.
- The map's §1 row for `illegal-states` listed `Shipped(shipped_on)`. The class holds the
  `shipment_id` and the settlement instead; the day lives on the `shipments` row
  (`shipped_on`, `promised_by`, `delivered_on`).
- The map's gap G1 ("O-106 has no lines") is closed: O-106 was placed with L-10, and it is
  `order_lines`, not the app, that has no line for it.

## Pages served

| page | what it shows from this ADR |
|---|---|
| `illegal-states` | the six classes; only `Paid` holds a payment id; `Shipped` carries how it was settled. The twin: flags and optionals |
| `state-machine` | `TRANSITIONS` as rows, the same six words as `order_events`; O-101's full path; `ship(O-106)` refused |
| `anaemic-model` | the twin `Order` with a public `status`, where a service ships or refunds what the classes here would refuse |
| `pure-core-imperative-shell` | `late_orders(orders, events, today)` as a pure function that knows O-104 never ships |
| `unit-of-work` | placing: the order, its lines, the `sold` movements and the outbox row in one commit; a cancel: the state, the deleted lines and the outbox row |
| `outbox` | each move as one `StatusChanged` row; the feed's word is `status(order)` |
| `observer-and-events` | `Paid` (and `Invoiced`) as the moves whose events the handlers hear: the confirmation e-mail and the shipping label (C26). Stock and the outbox row are not among them: both are written in the move's unit of work |
