# 0004. Domain types

Status: accepted, 2026-11-04 (step 6.2, decisions C4 and C25)

## Context

The domain is the inner layer of `roastery`. Every service, store and page reads its types.
Three things in the data push on them:

- **Ids look alike.** `C-01`, `O-101`, `L-01` and `P-10` are all short text. A bare `str`
  lets an order id land where a customer id belongs, and nobody notices.
- **Money comes in four currencies.** PAY-2 is in SEK and PAY-3 in DKK. Two bare numbers add
  without complaint, and the sum means nothing.
- **A return needs a negative line.** Order 300 of `order_values` is a refund of -899: a
  credit order with one negative line for the grinder returned (S14). Every other line in
  the data has a quantity of 1 or more.

Two rows look like a reason for a looser type, and are not:

- L-07 has no `qty` in `order_lines`. That is a fault the export writer plants after a
  correct app (D10, plan 4.2). In the app, O-105's line has its quantity; PAY-5 (349.00 for
  one bag of P-11) says it was one.
- L-12 is a free sample at 0.00. A price of zero is a real price, so `Money` allows zero.

The firm's teaching app already has this style in `firm/domain.py`: small frozen classes that
check themselves when they are built. The `value-objects` page reads it.

## Decision

The domain types are **frozen dataclasses** that check themselves in `__post_init__`. They
live in the core modules of ADR 0001's `LAYERS`:

| module | types |
|---|---|
| `roastery/ids.py` | the id types, `Country`, `PostalCode`, `Email`, `AccountKind` |
| `roastery/customer.py` | `Customer`, `CustomerChange` |
| `roastery/money.py` | `Money`, `Qty`, rounding to the øre |
| `roastery/catalogue.py` | `Product`, `Kind`, `BeanDetails`, `EquipmentDetails` |
| `roastery/order.py` | `OrderLine`, `Channel`, the order's states (ADR 0005) |

A malformed value raises `ValueError` or `TypeError` when it is built; a refused command is
a different thing (ADR 0006).

**Ids are value types**, one class per kind, each holding a `value: str` and checking its
shape `PREFIX-digits`:

| type | prefix | example |
|---|---|---|
| `CustomerId` | `C` | C-05 |
| `OrderId` | `O` | O-104 |
| `LineId` | `L` | L-06 |
| `ProductId` | `P` | P-21 |
| `EventId` | `E` | E-09 |
| `PaymentId` | `PAY` | PAY-1 |
| `SubscriptionId` | `S` | S-1 |
| `CategoryId` | `CAT` | CAT-11 |
| `CampaignId` | `K` | K-1 |
| `SubEventId`, `ShipmentId`, `BagId`, `MovementId`, `PurchaseId`, `RuleId` | the prefixes of contract B's id table (ADR 0007) | |

One type per kind of ADR 0007's `IdKind`, and `PaymentId` for the provider's ids. The background trade's ids have a fixed width per kind (ADR 0007); the type checks the prefix and the digits, not the width.

A `NewType` is refused: it is a name for the type checker and checks nothing at run time.

```python
@dataclass(frozen=True)
class OrderId:
    value: str

    def __post_init__(self) -> None:
        _check_id(self.value, 'O', 'order id')

    def __str__(self) -> str:
        return self.value
```

**Money** is an amount and a currency, on `Decimal`. It adds only to the same currency.

```python
@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str          # three capitals: NOK, SEK, DKK, EUR

    @classmethod
    def of(cls, amount: str | int, currency: str) -> Money: ...

    def __add__(self, other: object) -> Money: ...
    def __neg__(self) -> Money: ...
    def times(self, qty: Qty) -> Money: ...
    def to_ore(self) -> Money: ...    # quantize 0.01, half up
```

- `amount` must be a `Decimal`; a `float` is refused with `TypeError`.
- Zero is allowed (L-12). A negative amount is allowed (a refund is a negative payment, S14).
- `Money.of` takes text or an int, never a float, so `0.1` cannot sneak in.

**Qty** is a whole number other than zero.

```python
@dataclass(frozen=True)
class Qty:
    value: int

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(
            self.value, int
        ):
            raise TypeError('qty must be a whole number')
        if self.value == 0:
            raise ValueError('qty must not be zero')
```

`Qty` itself allows a negative number. What keeps it rare is the line's factories:

```python
@dataclass(frozen=True)
class OrderLine:
    line_id: LineId
    product_id: ProductId
    qty: Qty
    unit_price: Money

    @classmethod
    def of(cls, *, line_id: str, product_id: str,
           qty: int, unit_price: str) -> Self: ...
    @classmethod
    def from_payload(cls, payload: Mapping[str, object]
                     ) -> Self: ...
    @classmethod
    def at_counter(cls, *, line_id: str, product_id: str,
                   qty: int, unit_price: str) -> Self: ...
    def credit(self, line_id: LineId) -> OrderLine: ...
```

- `of`, `from_payload` and `at_counter` refuse a quantity below 1.
- `credit` is the only way to a negative line. It copies the product and the unit price and
  negates the quantity. Only `Checkout.credit_for` calls it (S14, ADR 0005).

**Other values** the pages need:

| type | holds | checks |
|---|---|---|
| `Country` | `NO`, `SE`, `DK`, `FI` | one of the four |
| `PostalCode` | text | digits only, kept as text: 0150 keeps its zero (C-01) |
| `Channel` | `Literal['web', 'shop']` | a type alias, no class |
| `Kind` | `Literal['beans', 'equipment']` | as `products.kind` holds it |
| `AccountKind` | `Literal['consumer', 'business']` | a type alias, no class; in `ids.py` |
| `Email` | text | one `@`, and the domain `example.invalid` (C25): no address in the data can reach a real inbox |
| `BeanDetails` | weight, origin, roast, process | frozen dataclass in `catalogue.py`; a bean product's own fields |
| `EquipmentDetails` | warranty, material | frozen dataclass in `catalogue.py`; an equipment product's own fields |

**The customer** (`customer.py`):

```python
@dataclass(frozen=True)
class Customer:
    customer_id: CustomerId
    name: str
    email: Email
    country: Country | None
    postal_code: PostalCode | None
    account_kind: AccountKind
    joined: dt.date
```

`CustomerChange` is one row of the change log: `seq`, `op`, the id, the country and postal code after the change, and `changed_at` (ADR 0003).

A customer's country is `Country | None`: C-05 has none, and that is a fact about Lars, not
a fault. What a missing country means is said by the caller that needs one (ADR 0008,
ADR 0010).

## Alternatives refused

| alternative | why refused |
|---|---|
| plain `str` ids and `Decimal` amounts | an order id fits a customer id's slot; PAY-2 plus PAY-3 adds; the `value-objects` page has nothing to show |
| `NewType` ids | checks nothing when the code runs; `OrderId('C-01')` passes |
| a separate `ReturnQty` (or `CreditLine`) type for the negative case | one call makes it (`credit_for`), and every reader of a line would have to accept two types: a shallow module that moves the rule without hiding it. The deletion test: delete it, and the rule lives in one factory, which is where it already is |
| `Qty` of 1 or more, and the return as a positive line with a `returned` flag | the flag is a second state on every line; the sum of a credit order's lines would no longer be its amount, and order 300's -899 would have to be computed, not added |
| `qty: int \| None` to match L-07 | the null is the export writer's fault (D10). A nullable quantity in the app would let a well-built app make the dataset's defects (map gap G1) |
| `float` money | 0.1 + 0.2; rounding to the øre needs `Decimal` (CLAUDE.md: money is `Decimal`) |
| pydantic models or attrs | a third-party dependency in `packages/shop` (C2, ADR 0002) |

## Consequences

- Every port, store and service signature names these types, so contract B (ADR 0011) is
  written in them. A store turns rows into them at its edge.
- A value that fails to build is a `ValueError`, raised where it is built. The API turns it
  into a 400 at its parse step; parsing turns it into a `Reject` (ADR 0006).
- `Money` never converts. Turning SEK into NOK needs `fx_rates`, which is an outside feed
  (ADR 0012); conversion lives in a report, not in the value.
- Rounding happens in one place, `Money.to_ore`. VAT uses it per line (ADR 0010).
- The sequential id adapter must make ids of the same `PREFIX-digits` shape, or the value
  types refuse them (ADR 0007).
- `Qty` negative is legal for the type. A test in 6.3 checks that `OrderLine.credit` is the
  only call in `roastery` that makes one.

## Pages served

| page | what it shows from this ADR |
|---|---|
| `value-objects` | `Money(amount, currency)`: PAY-2 (SEK) plus PAY-3 (DKK) raises. `Qty` refuses 0. `PostalCode` keeps C-01's 0150. `ProductId('p-20')` is refused. The twin sums bare floats across currencies |
| `factories` | `OrderLine.from_payload`, `.at_counter`, `.of`, and `credit` as the one named way to a negative line |
| `illegal-states` | the state classes hold these types; a `Paid` order holds a `PaymentId` (ADR 0005) |
| `errors` | the split this ADR draws: a malformed value raises `ValueError`; a refused command raises a `ShopError` (ADR 0006) |
| `facade` | `Money.to_ore`: the total to the øre, done once |
