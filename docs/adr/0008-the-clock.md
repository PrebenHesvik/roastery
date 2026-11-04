# 0008. The clock

Status: accepted, 2026-11-04 (step 6.2, decisions C8 and C19)

## Context

The app stamps moments and dates days, and the two are not the same thing here:

- Every stamp in the app's tables is UTC: `order_events.event_at`, `line_stamps.updated_at`,
  `customer_changes.changed_at`.
- `orders.order_date` is the day "on the customer's clock" (its grain sentence).
- The till stamps `sold_at` in Bergen time (an outside system, ADR 0012).

The rows that make the difference visible:

| row | UTC | local | `order_date` |
|---|---|---|---|
| E-11, O-106 placed by C-04 (FI) | 6 October 21:30 | 7 October 00:30 in Helsinki | 2026-10-07 |
| the same moment in Bergen | | 6 October 23:30 | (not the order's date) |
| E-05, O-102 placed by C-02 (SE) | 5 October 21:50 | 5 October 23:50 in Stockholm | 2026-10-05 |
| E-09, O-104 at the counter | 6 October 15:20 | 6 October 17:20 in Bergen, R-5001's `sold_at` | 2026-10-06 |

The `polars/time-zones-and-durations` lesson rests on E-11: one moment, two dates.

The rules (CLAUDE.md): no wall clock; time comes through the `Clock` port; the same seed
gives the same bytes. The firm's `late_lines(lines, today)` takes the day as an argument
and reads no clock; the `pure-core-imperative-shell` page reads it.

## Decision

**The `Clock` port has one method**, in `roastery/ports.py`:

```python
class Clock(Protocol):
    def now(self) -> dt.datetime:
        """This moment, timezone-aware, in UTC."""
```

There is no `today()`. A day is always worked out from a moment and a zone, by a pure
function in `roastery/clock.py`:

```python
def local_date(now: dt.datetime, zone: str) -> dt.date:
    """The day `now` falls on in `zone`; `now` must be aware."""
```

- `local_date` refuses a naive `now` with `ValueError`.
- It reads no clock and no setting. The same moment and zone give the same day.

**Where the zone comes from.** One table in `roastery/clock.py`, by country:

| country | zone |
|---|---|
| NO | Europe/Oslo |
| SE | Europe/Stockholm |
| DK | Europe/Copenhagen |
| FI | Europe/Helsinki |

- At the counter (channel `shop`), the zone is `ROASTERY_SHOP_ZONE` (`Europe/Oslo`), read
  once into the settings (ADR 0014) and wired in.
- On the web, the zone is the customer's country's. The caller works the country out once,
  with `order_country` in `roastery/checkout.py` (ADR 0010), the one place that says what
  a missing country means; the zone follows from it:

```python
def order_zone(
    channel: Channel, country: Country, shop_zone: str
) -> str:
    if channel == 'shop':
        return shop_zone
    return ZONES[country]
```

- A customer with no country (C-05, O-105) gets Norway from `order_country`, so Norway's
  zone. `local_date` and `ZONES` have no fallback: an unknown key raises. The rule is said
  once, for VAT and for the date alike.
- O-105's line is stamped 7 October 11:05 UTC; it is 7 October in every one of the four zones,
  so no frozen row depends on this choice.

**Two adapters** stand at the seam:

| adapter | where | what |
|---|---|---|
| `SystemClock` | `bootstrap.py`, wired for the API | the one place in `packages/shop` that may call `dt.datetime.now(dt.UTC)` |
| `FakeClock` | `fakes.py`, wired by the simulator and the tests | a moment that only moves when told (`set`, `advance`) |

Jobs take no clock argument: the port is wired in (C12).

## Alternatives refused

| alternative | why refused |
|---|---|
| a `today()` on the clock | the day depends on whose clock. A `today()` hides the zone, and O-106 would come out as 6 October (Bergen) instead of 7 October (Helsinki) |
| stamps in local time | two stamps in two zones cannot be compared without their zones; the feed and `line_stamps` are UTC in the frozen data |
| `dt.datetime.now()` called where needed | the wall clock in the app; the simulator could not play 2024 to 2026; a test of "late" would depend on the day it runs |
| the zone as a fallback inside `local_date` (no zone means Oslo) | hides C-05's case where nobody reads it; ADR 0010's night story is exactly a hidden fallback |
| the zone stored on the customer | a second fact that must agree with the country; C-01's move on 9 October would have to change both |
| one shop-wide zone for every order | E-11 would date O-106 to 6 October; the frozen `orders` has 7 October |

## Consequences

- Every service that writes a stamp takes it from `clock.now()` once per command, so all rows
  of one unit of work share one moment.
- The rule "no `datetime.now`, `time.time` or unseeded `random`" is checked by the
  teachability test (C17, ADR 0015). `SystemClock` is its one listed exception.
- The pure functions of the domain (`late_shipments`, VAT by day) take a `dt.date` or a
  moment as an argument, never a clock.
- The till's Bergen-time `sold_at` is turned into UTC by the parser, with the shop zone
  (ADR 0012).
- `tzdata` is the shop's one runtime dependency (C19, ADR 0002). `zoneinfo` finds no zones on
  Windows without it (`ZoneInfo('Europe/Helsinki')` raises `ZoneInfoNotFoundError`), a slim image
  may lack the system database, and a system database's version can differ between machines.
  The wheel pins one version of the zone data, so a local run and CI give the same days. A
  hand-written rule for the four zones was refused: it would repeat the EU's last Sundays of
  March and October in code.

## Pages served

| page | what it shows from this ADR |
|---|---|
| `pure-core-imperative-shell` | `late_shipments(orders, events, today)` deciding with a day passed in; the shell reads `clock.now()` and works out the day. The twin patches the clock |
| `fakes-over-mocks` | `FakeClock` as a working fake: it moves only when told |
| `ports-and-adapters` | `Clock` with two adapters, wired in `bootstrap` |
| `configuration` | `ROASTERY_SHOP_ZONE` read once and passed in, never read inside `local_date` |
| `errors` | `order_country` matching `NoCountry` once; the date and the VAT both follow from it |
