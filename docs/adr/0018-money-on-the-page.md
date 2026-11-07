# 0018. Money on the page

Status: accepted by the owner, 2026-11-07 (step 7.0, decisions F3 and F5 of `docs/phase-7/plan.md`)

## Context

The shop sells to Norway, Sweden, Denmark and Finland, and stores every price in NOK (`PRODUCT.md`, Operating Context). A buyer in Stockholm wants to see kronor, one in Helsinki euros. The page must also say what VAT the price holds, and that differs by country.

What the records fix:

- **`Money` never converts** (ADR 0004). Turning SEK into NOK needs `fx_rates`, an outside feed (ADR 0012); conversion lives in a report, not in the value. `Money` takes any three-letter currency (`money.py:20`); `in_nok` refuses a hand price in another (`checkout.py:82`).
- **Orders are in NOK.** Every price row, every order line, every payment. `Item` refuses a non-NOK price.
- **One gross price for every buyer** (ADR 0010). VAT is a share of the price, never added on top. A Norwegian sale is `domestic`, at 15 % on beans and 25 % on equipment; a foreign sale is an `export` at 0 % Norwegian VAT (`vat.py:42`).
- **What the foreign buyer pays at the border** (`docs/facts/vat.md`): without IOSS, the buyer's country collects its own VAT at import, and the carrier bills the buyer with a handling charge on top. From 2026-11-01 a Union handling fee of EUR 2 per item applies to every distance sale from outside the EU. Danish coffee excise (7.67 kr per kg roasted) comes on top for Denmark, and who pays it is open (`vat.md` open point 1); "the app must not promise a landed price for Danish buyers".
- **IOSS** is a business choice the live shop makes, not this phase (F3, ADR 0010).
- **The simulator's rates.** `script.FX` (`script.py:929`) holds the bank's rates as `FxRate(currency, rate_date, nok_per_unit)` (`outside.py:79`), several dates per currency, the last in October 2026.
- **No real payments** (F5). The storefront needs a payment step to walk through, and the order must end `paid`.

## Decision

### Fixed display rates

`roastery_api/fx.py` holds one rate per currency: the latest of each in `script.FX`.

| currency | NOK per unit | rate date in `script.FX` |
|---|---|---|
| SEK | 1.0620 | 2026-10-06 |
| DKK | 1.5580 | 2026-10-02 |
| EUR | 11.6300 | 2026-10-07 |
| NOK | 1 | |

The rates are copied into `fx.py` as constants, with the date. `roastery-sim` is a dev dependency (ADR 0016), so the server cannot import `script.FX`. A dev test imports it and checks that the constants are the latest row of each currency, so a change to the script's facts fails the test rather than drifting quietly.

A rate is a fact of a day, not of every day. The page says the amounts are approximate and the order is charged in NOK.

### Converting

```python
def display(amount: Money, currency: Currency) -> Money:
    """A NOK amount shown in another currency, to the cent.

    NOK divided by the currency's NOK per unit, rounded half up
    by `to_ore`. For the page only: never stored, never charged.
    """
```

- The direction: `nok_per_unit` is what one unit costs in kroner, so the shown amount is NOK ÷ rate. P-10 at 129.00 NOK is SEK 121.47, DKK 82.80, EUR 11.09.
- Rounding is `Money.to_ore` (`money.py:64`): two places, half away from zero. It is the shop's one rounding rule, used here on a value the shop never keeps.
- `display` lives in `roastery_api`, outside `roastery`. `Money` gains no method and the shop no conversion, so ADR 0004 holds: conversion lives at the edge that shows it, like a report.
- Each amount the page shows is converted on its own: the unit price, the line, the total. The shown lines may differ from the shown total by a cent; the NOK amounts add up exactly.
- The API sends both: every amount as NOK, and as the display currency. The storefront formats them with `Intl.NumberFormat` (ADR 0019).

The display currency follows the buyer's country: NO NOK, SE SEK, DK DKK, FI EUR. A buyer outside Norway sees the NOK amount beside it at checkout and on the payment page, since that is what is charged.

### VAT on the page, by country

The quote (ADR 0017) gives the Norwegian VAT share of each line, and for a foreign country the destination's own rate. The page says:

| country | the price line says | below the total |
|---|---|---|
| NO | "incl. VAT": 15 % on beans, 25 % on equipment, with the VAT amount | the order's VAT, from the quote |
| SE | "No Norwegian VAT" | "Swedish import VAT is due on delivery: about SEK x. The carrier's fee and the EU handling fee come on top." |
| FI | "No Norwegian VAT" | the same, for Finland, in EUR |
| DK | "No Norwegian VAT" | "Danish VAT, coffee excise and fees are due on delivery." No amount |

- **The estimate**, Sweden and Finland: for each line, gross × the destination's rate on the day ÷ 100, to the øre in NOK, summed, then converted once. Import VAT is levied on the goods' value, so it is added to the value, unlike the Norwegian share, which is inside the price. Today that is 6 % on beans and 25 % on equipment in Sweden, 13.5 % and 25.5 % in Finland, from the dated rows (ADR 0010, `vat.py:109`).
- The estimate is of VAT on the goods only. It leaves out the EUR 2 handling fee, any customs duty and the carrier's charge, and VAT on those. The page says so in words, not in a footnote.
- **Denmark gets no landed amount.** Coffee excise is open (`vat.md` open point 1). Equipment carries no excise, but one rule per country is clearer than one per line, and a Danish cart with beans and a grinder would show half an estimate.
- **IOSS is not offered.** No destination VAT is charged at checkout, for any country.
- The words are copy in `en.json` (ADR 0019); the amounts come from the API. No rate is written in the storefront.

### The sandbox payment

`POST /sandbox/payments` plays the payment provider (F5). Its body names the order's token and an outcome: `approve`, `decline` or `outage`. It names no amount.

- **The amount is the order's.** The API reads the stored order (`Storefront.order`, ADR 0017) and sums `line.unit_price.times(line.qty)` (`money.py:61`): `Money` in NOK, exactly what `place` stored. Never the display amount, never a figure from the client.
- **Approve.** A `PaymentMessage(PAY-n, order_id, amount, paid_on)` (`order.py:453`). `PAY-n` comes from the state db's counter (ADR 0016), since the provider makes payment ids and `payment` is not an `IdKind`. `paid_on` is `local_date(now, ZONES[order.head.country])`, the buyer's day, as the order's. The API gives the message to `FakeProvider.take` (`fakes.py:66`), so the provider holds it as a real one would, and then to `Payments.handle_message` (`payments.py:68`). The order is `paid`; the handlers send the confirmation and ask for the label (log lines, ADR 0016). 201.
- **Decline.** `ProviderRefused` (`ports.py:680`), raised before any write: 402. The order stays `placed`. The buyer may try again.
- **Outage.** `ProviderUnavailable` (`ports.py:684`): 503. Not stored under the idempotency key (ADR 0016), so "try again" with the same key runs again.
- **Twice.** The same key gives the stored 201. A new key on a paid order reaches `handle_message`, which refuses to pay a paid order: 409 `IllegalTransition`.

The payment page says, in its heading, that it is a test payment and no money moves.

## Alternatives refused

| alternative | why not |
|---|---|
| Prices stored per currency | `prices` is frozen (ADR 0010); the buyer's price would vary by rate; the order total would need a rate per order |
| `Money.convert(rate)` | ADR 0004: `Money` never converts. A conversion in the value spreads to every caller |
| Live bank rates | an outside feed with no port (ADR 0012), and a hosted service; the live shop decides |
| Importing `script.FX` at run time | the server would need the simulator installed |
| Converting the NOK total line by line and summing | the shown total would not be the NOK total converted; one rule (convert each shown amount) is simpler to read |
| Banker's rounding for display | the shop rounds half up in one place (`to_ore`); two rules would show two answers for one amount |
| A landed price for every country | Denmark's excise is open; a promise the shop cannot keep |
| No estimate for Sweden and Finland | F3: the buyer should not meet an unexplained bill at the door |
| The amount in the sandbox request | a client could pay 1 kr for a grinder; the server owns every amount |
| Charging in the display currency | orders are NOK; a SEK payment against a NOK order is a `PaymentMismatch` waiting to happen |

## Consequences

- The shop's data stays NOK only. No converted amount is stored anywhere, in the shop db or the state db.
- The rates are from early October 2026 and grow older each day; the page says the amounts are approximate. A live rate is the live shop's work.
- The Swedish and Finnish estimates follow the dated rows: Sweden's food rate changes again after 2027-12-31 (ADR 0010), and the estimate follows when the row is added.
- When the live shop chooses IOSS, the page's foreign rows change, and `scheme_for` with them (ADR 0010).
- The sandbox exercises the real `handle_message`: the order's states, the outbox rows and the handlers are those a real payment makes.

## Open points

1. **The Norwegian "incl. VAT" rule** rests on consumer law that `vat.md` did not confirm (its open point 8). The display follows it; the source is to be read before the live shop.
2. **Finland's import handling** (who bills the buyer, the carrier's fee) is not confirmed (`vat.md` open point 6). The estimate is of VAT only, which `vat.md` does confirm.
3. **The plan puts `fx.py` on `script.FX`** while making `roastery-sim` a dev dependency. This ADR copies the rates and pins them with a dev test. The owner confirms.

## Pages served

Phase 7 writes no pages (F7). When Design Patterns is planned, this ADR offers:

| page | what it shows |
|---|---|
| `value-objects` | `Money` refusing to convert; the conversion at the edge, for display |
| `idempotency` | a double click on "pay" paying once |
