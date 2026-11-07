# 0017. The storefront's read side and the quote

Status: accepted by the owner, 2026-11-07 (step 7.0, decisions F2, F3 and F6 of `docs/phase-7/plan.md`)

## Context

The shop's services write. `Checkout.place` prices a line inside its own unit of work and returns the order (`checkout.py:156`); nothing answers "what does this cost today?" before an order exists. `architecture.md` §5 lists the reads the pages call (`country_of`, `late_shipments`, `reports`); none of them is a product list or a price. The storefront needs four reads: the products, one product, a quote for a cart, and an order's status.

What the built code fixes:

- **Pricing is pure core.** `Sale` (`pricing.py:103`) carries the product, the day, the price rows, the discount rows and the customer's subscriptions. `per_rule` (`pricing.py:207`) picks one rule, the larger percent winning; `price_lines` (`pricing.py:230`) prices a sequence of sales and raises `NoPrice` when no rule holds; `rule_named` (`pricing.py:259`) finds `list`. `Checkout.__init__` composes them (`checkout.py:146`): `per_rule` over every rule but `list`, with `list` as the default.
- **The day is the buyer's.** `place` dates an order `local_date(now, ZONES[country])` (`checkout.py`, in `place`; `clock.py:18`, `clock.py:29`), and a web order's country is the customer's (`order_country`, `checkout.py:110`).
- **VAT, as built**, differs from ADR 0010's sketch. `VatRates.rate_on(country, kind, on)` (`vat.py:149`) is a method; `vat_of(gross, rate, scheme)` (`vat.py:172`) is a module function that takes the rate, not a country and a day. `scheme_for(order, on)` (`vat.py:42`) takes an `Order`. `_vat_amount` (`checkout.py:384`) is the one caller: no lookup for an export, per-line shares for a domestic order.
- **P-12 Decaf has no price row** (`script.py:627`). `list_price` raises `NoPrice` for it (`pricing.py:142`). F6: it shows as "coming soon".
- **Contract B is frozen** (plan §1). `checkout.py` cannot be edited and `App` gets no field.

## Decision

### `storefront.py`, a service

`roastery/storefront.py` is a new module in the service row of `LAYERS` (`architecture.py:54`). It imports core and ports only, like `checkout`. `architecture.md` §1–2 gain its row in 7.1.

```python
class Storefront:
    """What a buyer may read: the products, a quote, an order.

    Reads only. Each call opens one unit of work and commits
    nothing. Prices come from the rules, never from the caller.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        clock: Clock,
        rules: Mapping[str, Rule],
    ) -> None: ...

    def products(self) -> tuple[Listed, ...]: ...
    def product(self, product_id: ProductId) -> Listed: ...
    def quote(
        self, country: Country, items: Sequence[Asked]
    ) -> Quoted: ...
    def order(self, order_id: OrderId) -> Shown: ...
```

It is not on `App`: a field of `App` changes contract B. The API builds it beside `wire`, on the same store (ADR 0016). The simulator never sees it.

The value types (`Listed`, `Asked`, `Quoted`, `QuotedLine`, `Shown`) are frozen dataclasses in `storefront.py`. 7.1 settles their fields; what they carry:

| type | carries |
|---|---|
| `Listed` | `Product`, its details (`uow.catalogue.details`, `ports.py:326`), today's unit price and percent, or `None` when no rule prices it; `in_stock` |
| `Asked` | a product id and a `Qty`. No price: there is no field for one |
| `QuotedLine` | product, qty, unit price, percent, gross, the Norwegian VAT share, the destination's rate, bags on hand |
| `Quoted` | the country, the day, the scheme, the lines, the total gross and the total VAT, all `Money` in NOK |
| `Shown` | the order's status (`order.status`, `order.py:309`), country, day, lines and total |

### The quote reuses checkout's pieces

`quote(country, items)`, in one unit of work:

1. `day = local_date(self._clock.now(), ZONES[country])`, as `place` does for a web order.
2. Each product by `uow.catalogue.product`; an unknown id raises `UnknownProduct`, as `_product` does in checkout.
3. One `Sale` per item: `Sale(GUEST, product, day, uow.prices.of(id), uow.rules.all(), ())`, then `price_lines(sales, self._price)`. A product with no price raises `NoPrice` (422).
4. `self._price` is composed in `__init__` exactly as `Checkout.__init__` does (`checkout.py:146`): `per_rule` over the rules but `list`, `rule_named('list', rules)` the default. The code repeats those six lines; `checkout.py` cannot be edited to share them.
5. VAT per line: the scheme (below); for `domestic`, `VatRates(uow.vat_rates.all()).rate_on(country, product.kind, day)`, then `vat_of(unit_price.times(qty), rate, scheme)` (`money.py:61`). For `export`, `vat_of` gives zero with no lookup, as in `_vat_amount`.
6. For a foreign country, the destination's own rate for the line, `rate_on(country, kind, day)`, so ADR 0018 can estimate import VAT. It is reported, never added to the price.
7. Bags on hand per product: `uow.stock.on_hand(product_id)` (`ports.py:449`), summed per product as `_check_stock` does (`checkout.py:370`).

**The guest's sale.** A guest has no `CustomerId` before `register`, and `Sale` needs one. `GUEST` is a constant `CustomerId('C-0')`, and `subscriptions` is `()`. The `subscriber` rule then never holds. That is what `place` will see: a guest registered a moment before has no subscription, so `uow.subscriptions.of_customer` returns `()` and the price is the same. `C-0` is never stored; the counter's customer ids start at 1.

**The scheme.** `scheme_for` takes an `Order`, and a quote has none. `quote` builds a draft `Placed(Head(OrderId('O-0'), GUEST, 'web', country, lines, None))` from the priced lines (line ids `L-0`) and calls `scheme_for(draft, day)`. The draft is a value; it is never stored. This keeps ADR 0010's rule that the scheme is decided in one place: phase 8 edits `scheme_for`'s body, and the quote follows without an edit. See open point 1.

### `products()` and `product(id)`

The day is Norway's (`ZONES['NO']`): a listing has no buyer country. Each product is priced on its own; `NoPrice` is caught per product and gives a price of `None`, so P-12 lists as "coming soon" and the list does not fail (F6). A listed price is a guide; the quote, on the buyer's day, is the price.

`in_stock` is `on_hand > 0`. The listing does not show the count.

### `order(id)`

`uow.orders.get(order_id)` and `uow.orders.booking(order_id)` (`ports.py:236`, `ports.py:252`). It shows the status word, the country, `order_date`, the lines and the total. It shows no customer field. The API calls it only with an id found by a token (ADR 0016), never with an id from the URL.

### The server owns every price

- A client price never reaches `Item`. `Asked` has no price field, and the API builds `Item(product_id, qty)` with `price=None` (`checkout.py:82`), so `place` prices it by the rules. 7.1 has a test that posts a price and sees the rule's price charged.
- The cart in the browser holds product ids and quantities (ADR 0019). The prices it shows come from `POST /quote`.
- Checkout re-quotes (ADR 0016). If the total differs from the total the buyer confirmed, it answers 409 `PriceChanged` with the new quote and writes nothing. A campaign starting at midnight (K-2, 15 % on P-10, P-20 and P-21 from 2026-11-16, `script.py:639`) is the case that will happen.
- The re-quote and `place` read the same moment. ADR 0016's `RequestClock` reads the wall clock once per request, so the day the quote used is the day `place` uses, and the price the buyer confirmed is the price charged.
- Stock is checked from the quote before `register` (F2): a short line is 409 `OutOfStock`, nothing written. `place` checks again inside its own unit of work.

### Guest registration

`register` before `place`, two units of work, not atomic (F2, ADR 0016):

- the e-mail is `guest-<n>@example.invalid`, which `Email` accepts (`customer.py:37`). C25 holds: no real address enters the shop db;
- the country is the one quoted; the postal code is the guest's, digits only (`PostalCode`, `ids.py:170`). A Swedish `113 51` is stored `11351`;
- if `place` then refuses, the customer stays and is logged as an orphan (ADR 0016).

## Alternatives refused

| alternative | why not |
|---|---|
| A `quote` method on `Checkout` | a method on a pinned class; an edit to `checkout.py` |
| Reads on `listing.Catalogue` | `Catalogue` is in contract B; a new method changes it |
| Extracting the rule composition into `pricing.py` and calling it from both | `checkout.py` cannot change in this phase. The six lines are repeated; a test pins that both price a cart alike |
| `scheme = 'domestic' if country == 'NO' else 'export'` in the quote | ADR 0010 refused deciding the scheme in each caller: the IOSS change would then edit two places, and the quote would drift from the order |
| A price from the client, checked by the server | a check can be wrong in one place; a price that is never read cannot be trusted by mistake |
| Pricing at the shop's zone for every buyer | `place` uses the buyer's zone; a Finnish buyer's quote could differ from the order across Helsinki's midnight |
| Hiding P-12 | F6: the catalogue as it is; "coming soon" is a state the storefront designs for |
| A storefront read model (a separate table kept by events) | the outbox does not run here (F5), and the reads are small |

## Consequences

- The service row grows to nine modules. `test_architecture.py`'s `AWAITING` keeps only `cli`.
- The quote and `place` share the pure core (`Sale`, `per_rule`, `price_lines`, `rule_named`, `local_date`, `VatRates`, `vat_of`, `scheme_for`) but not the composition. A change to how `Checkout` composes rules must be made in `Storefront` too; the equality test catches a miss.
- Phase 8's IOSS change to `scheme_for` reaches the quote through the draft order. If IOSS needs the order's value in EUR, the draft carries the lines.
- The listing's prices are on Norway's day; a buyer in Finland may see a quote differ from the list for an hour around midnight. The quote is the price.
- `quote` reports the destination's VAT rate for an export line. The shop still charges no foreign VAT; ADR 0018 decides what the page says.

## Open points

1. **The draft order for `scheme_for`.** It needs placeholder ids (`O-0`, `L-0`, `C-0`) that pass the id types' shape check and are never stored. The alternative, restating the one-line rule, breaks ADR 0010. **Settled 2026-11-07:** the owner accepted the draft order (F8).
2. **ADR 0010's sketch is stale.** It shows `VatRates.vat_of(gross, country, kind, on, scheme)`; the code has `rate_on` on `VatRates` and a module `vat_of(gross, rate, scheme)`. This ADR cites the code. ADR 0010 is not edited here.
3. **The plan lists `local_date` among pricing's functions.** It is in `clock.py` (`clock.py:29`), core, so the import is allowed; only the plan's wording is off.

## Pages served

Phase 7 writes no pages (F7). When Design Patterns is planned, this ADR offers:

| page | what it shows |
|---|---|
| `pure-core-imperative-shell` | the same core priced twice, by `Checkout` and by `Storefront`, from two shells |
| `facade` | `quote`: one call over prices, rules, VAT, stock and the day |
| `errors` | `NoPrice` caught per product in a listing, raised for a cart |
