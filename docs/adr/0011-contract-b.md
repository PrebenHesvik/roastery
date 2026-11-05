# 0011. Contract B: the simulator's call surface

Status: accepted, 2026-11-04 (step 6.2, decisions C12, C23, C25, C27, C29, C30 and C37 to C39)

## Context

The simulator plays three years of trade through the app (ADR 0013). Every row of an app-database table must come from a call the app offers, and every row of another system must have a writer that is not the app. Contract B is the list of those calls. 6.4 freezes it, and after `roastery-data 1.0` a change to it is a new data version (plan §2).

Four things shape it:

- **The rows.** Each table of contract A has a system (`contract.md`). The 23 app-database tables need a call each. The 16 tables of the 10 other systems need a writer. Two of those systems are the app's own output: the status feed and the csv export. The other eight are outside systems the simulator plays, and each needs a way to reach the app. The 11 derived tables need the query that derives them.
- **The earlier ADRs.** Ids come through the `Ids` port and `source` is a wiring argument (ADR 0007), so no call takes either. The order's day comes from the clock and the order's zone (ADR 0008), so no call takes a date for "today". Errors are one closed family (ADR 0006).
- **The deep-module rule** (`codebase-design`). A service should hide a lot behind a few calls with small parameters. The deletion test applies to each call: a call the simulator never needs is not in contract B.
- **Two gaps the pattern map left open** (6.2 Notes). The `idempotency` page needs a named error for a redelivery with another amount. The `adapter` and `retry-and-circuit-breaker` pages need a call from the app out to the payment provider. Every payment call so far is inbound.

## Decision

### The surface

Contract B is the fenced block in `architecture.md` §5, with the table of what each call raises. In numbers: 7 services and 27 calls; 2 commands, plus 2 frozen records (`Item` and `Receipt`); 6 jobs (`app_tables` added in 6.4, W2); `App.failures()`; and 18 members of `ShopError`.

**It is the whole surface the simulator imports** (C27), not only the services. A name the simulator imports and the snapshot does not cover could change under 6.4's tag. So the block also holds:

| what | from | why the simulator imports it |
|---|---|---|
| `wire`, `Source` | `bootstrap`, `ports` | it wires the app twice over one store (ADR 0007) |
| `sqlite_store`, `memory_store` | `bootstrap` | the store both wirings share, with its one price cache (C38). sqlite for `month` and `full`; either for the week alone (C32) |
| `SequentialIds`, `ScriptedIds`, `IdKind` | `repository`, `ports` | the two `Ids` adapters (ADR 0007) |
| `FakeClock` | `fakes` | the simulator's clock: it moves it through three years |
| `FakeProvider`, `FakeNotifier`, `FakeLabels` | `fakes` | the provider it plays (a working fake: the payments it holds, refunds by its rules, the negative messages to deliver), and the two handlers' ports (C26) |
| `Settings` | `settings` | built directly, as the tests do (ADR 0014) |
| `StatusFeed`, `FeedDown`, `StatusChanged`, `Relayed` | `ports`, `events` | its own feed adapter, and what `jobs.relay` returns (ADR 0009) |
| `CollectingBus`, `HandlerFailure` | `events` | `App.events`, and what `App.failures()` returns (C29) |

`Relayed` is a port type in `ports.py`, so the simulator imports no adapter module for a type.

| service | module | calls |
|---|---|---|
| `Customers` | `customers` | `register`, `change`, `erase` |
| `Catalogue` | `listing` | `add_category`, `add_product`, `set_price`, `set_cost`, `add_campaign`, `set_subscriber_discount` |
| `Checkout` | `checkout` | `place(PlaceOrder)`, `cancel`, `credit_for` |
| `Payments` | `payments` | `handle_message(PaymentMessage)`, `invoice`, `settle(PaymentMessage)`, `refund` |
| `Fulfilment` | `fulfilment` | `ship`, `deliver` |
| `Subscriptions` | `subscriptions` | `subscribe`, `skip`, `pause`, `resume`, `cancel` |
| `Stock` | `stock` | `roast`, `write_off`, `stocktake`, `buy_green` |
| `App.jobs` | `bootstrap` | `relay`, `ship_subscription_bags`, `count_at_close`, `nightly_extract`, `csv_export`, `app_tables` |

`Catalogue` lives in a new service module, `listing.py`. `catalogue.py` is a core module of ADR 0001 (`Product`, `Kind`), and a service that writes through the unit of work cannot be core. ADR 0001's service row needs this module (see Consequences).

### Rules every call keeps

- **No id, no source, no clock.** A call returns the id of a row it made when the caller needs it later: `CustomerId`, `CategoryId`, `ProductId`, `OrderId` (from `place` and `credit_for`), `ShipmentId`, `SubscriptionId`. Otherwise it returns `None`. A date argument is a fact about the row, never "today": `valid_from`, a campaign's days, the carrier's `promised_by`.
- **Commands** are frozen dataclasses only where a call carries lines (`PlaceOrder` with its `Item`s) or mirrors a row another system wrote (`PaymentMessage`, one row of `payments`). Other calls take keyword arguments.
- **One unit of work per call.** When a call raises, nothing is written.

### Choices made against the data

**Placing.** `Checkout.place` is the one call for web and counter orders. An `Item` with no price is priced by the list price on the order's day, with the rules that hold. An `Item` with a price is priced by hand: the till's 549.00 for L-06, the free sample's 0.00 for L-12. The order's country comes from `order_country` (ADR 0010), and the order's zone and day follow from it (ADR 0008).

**C22 holds.** `place` builds the `Placed` order first, then takes each line's VAT share with `scheme_for(order, on)`. The order carries the country `order_country` chose, so phase 8 can widen `scheme_for` without changing contract B.

**Invoices (S13).** A business account's order is invoiced inside `place`: one unit of work, two outbox rows (`placed`, then `invoiced`). So the claim "each business order invoiced once, never paid" follows from the call, and does not depend on the script remembering. A consumer who pays later is put on invoice by `Payments.invoice(order_id)`. S13 says consumers may pay later, and contract A has their orders: of the 33 `unpaid` orders of `order_values` (an invoice still open on 30 September 2026), 20 are web orders of 4 bags, and D7 makes only the 10-bag orders and the café's 48 business. So `invoice` stays. It could go only if 6.4 made every one of those buyers a business account. An open invoice is paid by `Payments.settle(message)`: a payment row and no status event (ADR 0005). `settle` refuses an order with no open invoice (`NoOpenInvoice`), and `handle_message` refuses to pay an invoiced order (`IllegalTransition`). So a message delivered to the wrong call is loud.

**Idempotency.** `handle_message` and `settle` record a `payment_id` once and return the same `Receipt` for every delivery: PAY-1 twice, recorded once. A known `payment_id` with another order or amount raises **`PaymentMismatch`**. It compares a message with the payment stored under its id, never with the order's total. Payments are in the customer's currency, and they pay the lines the customer saw, planted ones included: PAY-2 is 516.98 SEK for 548.00 NOK of lines, L-03's 349.00 and the planted L-09's 199.00, while the app's O-102 holds L-03 only. So nothing in the app compares a payment with an order's total. That is the name the map's `idempotency` row asked for. `KeyReused` stays for the API's key store in `idempotency.py`: the same key with another body. Both live in `errors.py` (C20), which every layer may import.

**The outbound call.** It is `Payments.refund(order_id) -> PaymentId`. It asks the provider for the money back through the `PaymentProvider` port: `provider.refund(payment_id, amount, key=f'refund-{order_id}')`.

- For a credit order, it refunds the payment of the sale the credit order returns (`credit_of`), for the credit's amount.
- For a cancelled order that was paid, it refunds that order's payment.
- `wire` wraps the port in `resilience`'s retry, with backoff and a `CircuitBreaker`. A retry sends the same key, so a retry cannot refund twice.
- A decline (402, the port's `ProviderRefused`) is never retried. `ProviderUnavailable` is retried, and passes through when the retries run out or the breaker is open. Both are port errors, not members of `ShopError`: a decline is the provider's rule, not the shop's (ADR 0006).
- `refund` writes nothing. The provider answers with a negative message, which the simulator writes to `payments` and delivers to `handle_message`. That message moves the credit order from `Placed` to `Paid`.

So **order 300's negative payment row** is written by the simulator, as the payment provider, after `Payments.refund(credit_order_id)`. The app's own record of it is made by `handle_message`. The full return is three calls: `Checkout.credit_for` (the credit order, its negative line, its `placed` row), then `Payments.refund`, then `handle_message` with the provider's -899 NOK.

**C21, checked against the week.** Undoing a sale is a `sold` movement with the opposite sign. `place` writes one out per line, and `cancel` and `credit_for` write one back. The week's balances:

| P-10 | movement | balance at close |
|---|---|---|
| opening, after the October bags (plan 4.2) | | 42 |
| 5 Oct | L-01, 2 bags, sold | 40 |
| 6 Oct | L-04, 3 bags (L-05 is the writer's copy) | 37 |
| 7 Oct | L-08, 1 bag (O-107, 16:40 UTC) | 36 (the 26 is the writer's fault, S19) |
| 8 Oct | 24 bags roasted (`Stock.roast`, not a count: S19) | 60 |
| 9 Oct | L-11, 1 bag (19:30 UTC) | 59 |

P-20 goes from 5 to 4 on 5 October (L-02) and stays at 4. O-101 shipped on 6 October (E-03), and P-20 is still 4 on that day. So `Fulfilment.ship` writes no movement: `shipped` is the subscription bag's reason only.

O-106's cancel does put its bag back. L-10 left at `place` (E-11, 6 Oct 21:30 UTC), and the cancel writes `sold` +1 at E-12 (7 Oct 06:00). The balance claim counts a movement on the day of its `moved_at` in UTC, so L-10's bag is out at 6 October's close. If L-10 were P-10, 6 October would close at 36, not 37; if P-20, at 3, not 4. `line_stamps` has no product, so the data leaves L-10's product open, but it cannot be P-10 or P-20. **C21 holds** if 6.4 gives L-10 another product. P-11 fits (beans). P-12 would make "P-12 is never sold" true only of `order_lines`. The case that really uses the reversal is order 300: the grinder's `sold` +1 on 18 May 2026.

**Stock.**

- `roast`, `write_off` and `stocktake` write the `roasted`, `written_off` and `counted` movements.
- Equipment has no roast. It comes in through `stocktake` (`counted`), the one of the five reasons that fits a delivery that was counted in. A sixth reason would change contract A.
- `buy_green` writes `green_purchases`. The claim "kilos bought at least kilos roasted" is the script's to keep; the app does not refuse a roast for want of green coffee.
- A sale, a write-off or a bag that would take the balance below 0 raises `OutOfStock`, so "never negative" follows from the app.

**The count at close cannot use the job's own moment as written in S19.** S19 says `counted_at` stamps the count job (16:00 UTC), yet the 9 October count of 59 includes O-108 at 19:30 UTC. A job that ran at 16:00 could not have seen it. So `jobs.count_at_close` runs after the day is over, and writes `stock_daily` for the last closed shop day:

- `on_hand` is the balance of every movement whose `moved_at` falls on that day or before, by the UTC day, as the balance claim reads it. The two rules agree for the week; a sale at 23:00 UTC would fall on different days under them.
- `counted_at` is that day's close: 18:00 in `ROASTERY_SHOP_ZONE`, which is 16:00 UTC in summer. The close is a constant in `stock.py`, the job's own stamp, never the moment of the last sale. It is the one stamp of contract B that is not `clock.now()` (C23).
- **7 October, row by row.** The app writes one row per product: P-10, 36, counted at 7 Oct 16:00; P-20, 4, counted at 7 Oct 16:00. The export writer then sends the day twice (plan 4.2, the defect log). The first send keeps the app's stamp and plants the fault: P-10's 36 becomes 26. The second send is the "recount": every product of the day again, with the app's true counts (P-10 36, P-20 4), stamped 8 Oct 06:30. So none of the four 7 October rows of `stock_daily` is the app's row as written: the 16:00 pair carries the app's stamp, and the 06:30 pair the app's counts. `latest_stock` takes the 06:30 pair: P-10 36, the true count, as `contract.md` says.

**Catalogue.**

- `add_product` writes `products` and its subtype row in one call; the kind and `weight_g` follow from `BeanDetails` or `EquipmentDetails`.
- `set_price` and `set_cost` close the open period and open the next (half-open, as `prices` has them).
- `add_campaign` writes `campaigns`, `campaign_products` and the campaign's `pricing_rules` row from one `discount_pct`, with `valid_to = last_day + 1` (6.1's note). This is the one source that keeps `campaigns.discount_pct` and `pricing_rules.percent` equal.
- `set_subscriber_discount` keeps at most one subscriber rule on a day.
- `kinds` has no call. Its two rows are seeded by `create_tables` from the `Kind` type, as `vat_rates` is seeded from `vat.md`. An `add_kind` would let a third kind in, and `Kind` cannot hold it.

**Subscriptions.** `skip`, `pause`, `resume` and `cancel` each take a reason, and each writes one `subscription_events` row (the `command` page).

- Each of the four calls builds its command (`Skip`, `Pause`, `Resume`, `Cancel` in `commands.py`), checks it with `apply` against the subscription's state (`IllegalSubscriptionMove`), and keeps it: the command is the `subscription_events` row it becomes, with its reason. `subscribe` writes `subscriptions.started` and no event, so it has no command.
- `replay(subscription, events)` rebuilds the periods from `subscriptions.started` and the subscription's `subscription_events`, in order. `jobs.ship_subscription_bags` asks it whether a bag is due, and the `command` page replays S-2 and S-3 with it.
- So `commands.py` earns its keep: the log is the state, read back by the job, and the rules of which move follows which live once in `apply`. The five calls stay five, with keyword arguments (C12): a single `handle(command)` would put four more dataclasses on the snapshot, and return a `SubscriptionId` for one command and `None` for the rest.

- A skip is dated in the month it skips, so it skips this month.
- `cancel` sets `ended` to today, on the customer's clock.
- `Customers.erase` cancels the customer's open subscriptions in its unit of work, with reason `erased`: C-07 is erased on 9 October and S-7 ends that day.
- `jobs.ship_subscription_bags` ships this month's bag to every running subscription that has none yet and is not skipped or paused. It writes `subscription_shipments` and one `shipped` movement each. It takes no month: the month is the shop's today. A second run in a month ships nothing new.

**Customers.** `register` sets `joined` to today and keeps the customer's e-mail when there is one (C25, C37; C-05 has none), which reaches contract A only in `raw_customers`. `change` takes the customer's whole contact after the change: country, postal code and e-mail, never optional fields. The data's changes are moves, and `customer_changes` records the country and postal code after each update (ADR 0003). `erase` writes a tombstone. The customers store writes the change rows (ADR 0003). The `line_stamps` stamps are written by `place`, `credit_for` and `cancel`, never by a job.

**Jobs** take no argument and no clock. `wire` binds them to the store, the feed and the settings (ADR 0013). `nightly_extract` replaces tonight's `customer_extracts` copy. `csv_export` returns the two files' text, and the caller saves them; the export writer adds the faults after it (D10). `app_tables` returns every app-database table of contract A as `pipeline.Rows`, with `source` last, so the simulator reads the app back through contract B alone (6.4, W2).

**Handlers** (C39): `confirm` hears `OrderPaid` and `OrderInvoiced`, never for a credit order, and sends the confirmation e-mail through `Notifier` when the customer has an e-mail; `label` hears the same, for web orders with a postal code only, and asks for the shipping label through `Labels`. An order without an address gets no label, and `Fulfilment.ship` refuses it (`NoAddress`): O-105 (C-05, paid, never shipped in the week).

**Handler failures** (C29). A call returns once its unit of work commits, whatever its handlers do after. A handler's failure is kept by the wiring's `CollectingBus` (ADR 0009) and read with `App.failures()`. The simulator reads it after each day and stops if it is not empty: a failure is a bug in a fake, never a refusal.

**Not in contract B.** These are reads the pages call and the simulator does not: `customers.country_of`, `Fulfilment.late_shipments`, the `reports` functions (`reports.reconcile_till` among them), `parsing.parse_till`. Web tracking has no call (C11).

### The snapshot test

6.3 writes `packages/shop/tests/test_contract_b.py`. It renders the whole surface of C27, sorted:

- `str(inspect.signature(...))` of each public method of `App`, `Jobs`, the seven services, `CollectingBus`, `PaymentProvider`, `StatusFeed`, `SequentialIds`, `ScriptedIds`, `FakeClock`, `FakeProvider`, `FakeNotifier` and `FakeLabels`, and of each class's `__init__`;
- the signatures of `wire`, `sqlite_store` and `memory_store`;
- the fields of `Item`, `PlaceOrder`, `PaymentMessage`, `Receipt`, `App`, `Settings`, `Relayed`, `StatusChanged` and `HandlerFailure`;
- `Source` and `IdKind`, as their `Literal` members;
- every subclass of `ShopError`, followed recursively, with its `__init__` signature, and `FeedDown`.

It compares that text with the committed `packages/shop/tests/contract_b.txt`. A second assertion checks that no module but `errors.py` defines a member. 6.4 pins the file at its tag.

6.4 widened what the file pins before the tag: `Jobs.app_tables` and `Rows` (W2), the settings' field types `Url`, `Secret` and `Positive` (W38), and the fields of every value type a signature names (`BeanDetails`, `Money`, `Head`, the ids and the rest) with the members of `Country`, `AccountKind`, `Channel` and `Status` (W41). A name the simulator may import is pinned by its shape, not only its name: the simulator builds `BeanDetails` by position and reads `place(...).head.order_id`.

## Alternatives refused

| alternative | why not |
|---|---|
| caller-supplied ids and `source` on the commands | ADR 0007: the app makes E-01 to E-14, the movements and the shipments inside a call |
| a `month` argument on `ship_subscription_bags`, a `day` on `count_at_close` | each is the clock in disguise; the wired `Clock` gives it (C12) |
| invoicing a business account through `Payments.invoice`, called by the script | S13's "always" would rest on the script remembering; one forgotten call gives a business order a `paid` event and the claim fails far from the cause |
| one `handle_message` that also settles invoices | `settle` is named in ADR 0001 and ADR 0005. Two calls also make a misrouted message loud (`IllegalTransition`, `NoOpenInvoice`), where one call would decide quietly from the state |
| a capture call as the outbound call | nothing in the data needs one: every card payment arrives as a provider message. The refund is needed by order 300 and by a cancel after payment. One outbound call; the deletion test removes the second |
| `credit_for` or `cancel` calling the provider themselves | a call out to the provider inside the order's unit of work would hold the transaction open across a retry; and a decline would undo the credit order, which the shop has already handed over at the counter |
| `RefundRefused` as a member of `ShopError` | a decline is the provider's rule, and the adapter decides it (ADR 0006); the port's `ProviderRefused` already names it |
| a sixth movement reason (`returned`, `received`) | a change to contract A; the signed `qty` already says the direction (C21) |
| `KeyReused` for the payment redelivery too | two meanings for one name: the API's key with another body, and a provider message with another amount. The map asked for a name of its own |
| `add_kind`, `log_event` | the deletion test: a kind the `Kind` type cannot hold; web tracking is an outside system (C11) |
| `Catalogue` methods spread over `Stock` and `Checkout` | prices, rules and campaigns change for one reason (the shop's offer), and the `strategy` and `registries-and-plugins` pages read them together |
| a general `Customers.change` with optional fields | a call with every field optional says nothing of the customer after it. `change` takes the whole contact (country, postal code, e-mail); the data's changes are moves, and `customer_changes` carries the country and postal code after each |
| `Subscriptions.handle(command)` in place of four calls | four more frozen dataclasses on the snapshot, and one call returning two kinds of answer. The commands are still the log: each call builds one and keeps it |

## Consequences

- The simulator never writes an app table. It calls these 27 calls and 6 jobs, writes the outside systems' tables, and runs the derived queries in its extract writer.
- The simulator's provider must answer each refund it is asked for with a negative message, so the simulator can write it to `payments` and deliver it. `FakeProvider` is that provider: `take` gives it each payment the simulator makes, `refund` refuses more than is left, and `messages()` gives the negative messages. The snapshot covers it (C27).
- The API maps the port errors too: `ProviderRefused` to 402 and `ProviderUnavailable` to 503, beside ADR 0006's `STATUS`.
- 6.4's script must give L-10 a product other than P-10 and P-20, roast 24 bags of P-10 on 8 October, and keep cancels away from midnight UTC. Order 300's customer must be a consumer, and no credit order of a business account may fall before the week: the claim "each business order invoiced once, never paid" would see the credit order's `paid` event. The `subscribers` claim reads `event_at::DATE`, and `ended` is a local date; near midnight the two can differ.

**Changes other ADRs needed** (made when the ADRs were brought in line, step 6.2 U5):

| ADR | change |
|---|---|
| 0001 | the service row gains `listing` (the `Catalogue` service): 8 service modules, 39 in all (40 with C20's `errors`, 41 with `customer`, C33) |
| 0004 | `ids.py` gains `CategoryId` and `AccountKind` (`Literal['consumer', 'business']`); `catalogue.py` gains `BeanDetails` (weight, origin, roast, process) and `EquipmentDetails` (warranty, material) |
| 0003 | a store's `get` of an unknown id raises `UnknownId` (a `ShopError`), not a bare `LookupError` |
| 0005 | `Head` gains `country: Country`, the order's country as `order_country` chose it (C22); a business account's order is invoiced inside `place`, so a business counter sale ends at `Invoiced` (then `settle`), not at `Paid` |
| 0006 | the family is the members of §5 (17 then, 18 with C39's `NoAddress`); `KeyReused` is the API key store's; `PaymentMismatch` is the redelivery with another amount; `NoSuchCustomer` and `UnknownId` replace the stores' `Unknown...`; `STATUS` gains the new members |
| 0010 | `scheme_for(order, on)`, as C22 already says; the sketch still shows `scheme_for(country)` |
| 0013 | `wire` puts `resilience`'s retry and breaker around the `PaymentProvider` port |

## Pages served

| page | what it shows from contract B |
|---|---|
| `facade` | `Checkout.place(PlaceOrder)`: price, VAT, lines, movements and outbox behind one call |
| `unit-of-work` | `place` rolling back on P-99 (`UnknownProduct`) |
| `idempotency` | `handle_message` and PAY-1 twice, one `Receipt`; `PaymentMismatch` |
| `adapter` | `Payments.refund` through `PaymentProvider`: kroner to minor units, a 402 to `ProviderRefused` |
| `retry-and-circuit-breaker` | the refund retried with the same key; the breaker open; a decline never retried |
| `state-machine` | `ship(O-106)` raising `IllegalTransition`; `NotShippable` for O-104; `NoAddress` for O-105 |
| `command` | `Subscriptions`: each call with its reason, one `subscription_events` row |
| `anaemic-model` | `credit_for` refusing O-107 (`NotCreditable`) |
| `outbox` | `jobs.relay` |
| `pipelines-and-generators` | `jobs.csv_export` |
| `ports-and-adapters` | `App` driven by the API and by the simulator through the same calls |
| `registries-and-plugins`, `strategy` | `add_campaign` and `set_subscriber_discount` writing the rules the registry reads |
