# 0012. The outside systems and the till

Status: accepted, 2026-11-04 (step 6.2, decisions C11, C13 and C21). C11 replaces plan §2's
"`log_event` with source, variant and step".

## Context

`contract.md` gives every table a **system**: where its rows are born. Most are "app
database". The others are systems the shop does not run, and a real shop would not write
their rows either: the bank publishes rates, the weather service measures rain, the till in
the Bergen shop prints receipts. In the simulated world, the simulator plays each of them.

Two of the earlier plans put such rows inside the app:

- **Plan §2's `log_event`**, a service that would append the web shop's events. But
  `contract.md` files `web_events` and `web_visits` under "web tracking", not "app database".
  Nothing in the app reads those rows; only the extracts do.
- **The till as a source of sales.** The new till's files hold line detail from 6 October
  2026 (D12). R-5001 is O-104's kettle: the same sale as L-06, rung on the till at 17:20 in
  Bergen, which is E-09's 15:20 UTC. O-104 was typed into the app and rung on the till during
  the trial. If the app booked the till's lines as sales, the kettle would be sold twice.

The `parse-dont-validate` page needs a real input to parse. Map gap G6: `raw_lines` is the
app's own export, and an app does not parse its own export. The till's file is a real input.

## Decision

**The simulator writes these without the app.** Each against `contract.md`'s system column,
word for word:

| what | tables | system | how it meets the app |
|---|---|---|---|
| provider messages | `payments` | payment provider | the simulator writes every message it sends, redeliveries included (PAY-1 twice), and delivers each to `Payments.handle_message`, or an open invoice's payment to `Payments.settle` |
| web tracking | `web_events`, `web_visits` | web tracking | none: the app never reads them. The simulator writes a visitor's checkout, then calls `Checkout.place` within two minutes (W-03 at 08:11, E-01 at 08:12) |
| the till's files | `till_receipts`, `till_lines`, `till_members`, `product_codes` | till | read by `parse_till` and reconciled (below); never booked |
| fx rates | `fx_rates` | outside feed: bank rates | none in the app; reports convert with them |
| weather | `weather_days` | outside feed: weather | none |
| the door counter | `door_counts` | outside feed: door counter | none |
| the old till's day totals | `till_day_totals` | outside feed: old till | none |
| `managers` and `budget` | `managers`, `budget` | owner's sheet | none. The owner sets these numbers by hand and they are never simulated: the simulator writes the owner's rows as given, it does not make them up |

Two systems that are not in this list, because the app makes their rows:

- **status feed** (`order_events`): what `relay` sends from the outbox to the `StatusFeed`
  port; the feed adapter stamps `loaded_at` (ADR 0009).
- **csv export** (`raw_customers`, `raw_lines`): written by `exports.py`; the faults are added
  after it by the export writer (D10).

**There is no `log_event` in the app**, and no `tracking.py` (ADR 0001).

**The till's file is parsed into a reconciliation.** Two read functions, neither in
contract B:

```python
@dataclass(frozen=True)
class ParsedLine:
    receipt_id: str
    line_no: int
    product_id: ProductId
    grams: int | None  # loose beans only
    amount: Money
    sold_at: dt.datetime  # UTC, from Bergen time


def parse_till(
    receipts: Iterable[Mapping[str, str]],
    lines: Iterable[Mapping[str, str]],
    codes: Mapping[str, ProductId | None],
    shop_zone: ZoneInfo,
) -> Parsed[ParsedLine]:
    """Every till line, a sale or a Reject; rows keep order."""
```

`parse_till` lives in `roastery/parsing.py` (core). It turns each row into an
`Ok[ParsedLine]` or an `Err[Reject]` (ADR 0006):

- `ean` reaches a product only through `product_codes`: 2000000000213 is P-21.
- A code the till knows and the shop does not list is a `Reject`: 2000000000992 (R-5003,
  line 1) has no product.
- `sold_at` is Bergen time; the parser makes it UTC with the shop's zone (ADR 0008).
- `grams` is kept for loose beans (2100000000111, P-11 by the gram).

```python
@dataclass(frozen=True)
class Reconciliation:
    matched: tuple[tuple[ParsedLine, LineId], ...]
    walk_ins: tuple[ParsedLine, ...]  # no shop order matches
    unmatched: tuple[LineId, ...]  # a shop line not rung
    rejects: tuple[Reject, ...]


def reconcile_till(
    sales: Parsed[ParsedLine],
    shop_lines: Iterable[ShopLine],  # line, product, placed_at
    within: dt.timedelta,
) -> Reconciliation: ...
```

`reconcile_till` lives in `roastery/reports.py` (the read side). It sets the day's till sales
against the day's `shop` order lines, matched by moment and product: R-5001's line 1 (P-21,
549.00, 15:20 UTC) matches O-104's L-06. The till has no customer for R-5001 (`member_no` is
null), so the match is never by customer.

**The till never moves stock.** Stock moves when an order is placed: O-104's placing wrote the
kettle's `sold` movement in its own unit of work (ADR 0005). The till's R-5001 is the same
sale seen by a second system. No till line writes a movement, an order or a payment.

A return at the till is the other way round: undoing a sale is a `sold` movement with the opposite sign (C21), written by `Checkout.credit_for` or `cancel`, never by the till's file.

## Alternatives refused

| alternative | why refused |
|---|---|
| `log_event(source, variant, step)` in the app (plan §2) | the deletion test: a service that only appends rows nothing in the app reads adds nothing. Delete it, and no complexity reappears in any caller. `contract.md` already files the rows under web tracking |
| the checkout writing its own `web_events` row | the tracker's rows are the tracker's: its 30-minute visits, its `visit_id`, the visitor who never logs in (V-2). The app would have to know the A/B test's variant |
| till lines booked as orders through `Checkout.place` | R-5001 would be a second O-104. `orders` in `tiny` holds exactly eight orders (D13) |
| till lines writing `sold` movements | a second movement for the kettle; the week's frozen balances break (6.2 §6, risks) |
| the till's rows checked in each caller that reads them | the `parse-dont-validate` twin: a rule checked in three places and forgotten in one |
| ports with one adapter each for fx, weather and the door counter | one adapter is a hypothetical seam. Nothing in the app reads these feeds, so there is nothing for the seam to vary |
| the app fetching `managers` and `budget` | they are the owner's sheet, hand-set and never simulated; no app call makes them |

## Consequences

- Contract B (ADR 0011) has no call for any table in the first table above, except
  `handle_message` and `settle`, through which a provider message becomes the app's own
  payment record.
  The `payments` table is the provider's log; the app's record holds PAY-1 once.
- The simulator owns a writer for each outside system. U4's table of writers is checked
  against `contract.md`'s system column word for word.
- `parse_till` and `reconcile_till` are pure: the file's rows, the code list and the day's
  lines are arguments. The tests run them on the frozen till rows with no store.
- Which of R-5002 to R-5004's lines are walk-ins and which match a shop order is open until
  6.4 (6.2 §5): the default is to match by moment and product, as `dataset.sql` has them. The
  window `within` is fixed with it.
- What the till sells to walk-ins does not reach the app's stock through a movement. The frozen
  week holds because the till sells no bag of P-10 and no grinder (P-20) there, so
  `stock_daily` still matches `order_lines` (the `till_lines` comment in `dataset.sql`).
- The map gap G6 is closed for `parse-dont-validate`: the page parses an input the app really
  receives.

## Pages served

| page | what it shows from this ADR |
|---|---|
| `parse-dont-validate` | `parse_till`: a till row in, a `ParsedLine` or a `Reject` out; 2000000000992 is a reject; Bergen time made UTC once. The twin checks the rows in three callers |
| `ports-and-adapters` | the simulator as the outside world: it plays the provider, the tracker and the till, and drives the same services as the API |
| `idempotency` | the provider's PAY-1 delivered twice to `handle_message`, recorded once |
| `cqrs-lite` | `reconcile_till` as a read: rows in, rows out, no write |
| `depend-on-abstractions` | why fx, weather and the door counter get no port: one adapter is a hypothetical seam |
