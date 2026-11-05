# roastery-data changelog

Each version of the data is a GitHub release of this repository, tagged `roastery-data-<version>`.
A version's zips are built by `uv run python -m roastery_sim tiny`, `volume` and `release`; the
same commit gives the same bytes on every machine (CI checks it on Linux).

## 1.0.0 (2026-11-05)

The first release: the roaster's world played through the shop app (`shop` 0.1.1, contract B
frozen at `shop-0.1.0`) by the simulator (step 6.5, `docs/phase-6/6.5-volume.md`).

### The three extracts

| zip | holds | tables | rows | size |
|---|---|---|---|---|
| `roastery-data-1.0.0-tiny.zip` | the teaching week, 5–9 October 2026, and C-01's year: every row known by hand (`tiny.sql`, `data/`, `landing/`) | 30 | 220 | 27 KB |
| `roastery-data-1.0.0-month.zip` | October 2026, every system, with the nightly landings (`data/`, `landing/`) | 39 | 60,733 | 0.86 MB |
| `roastery-data-1.0.0-full.zip` | 1 January 2024 to 10 October 2026, 07:00 UTC (the end of the teaching week) | 47 | 296,466 | 1.77 MB |

Each `data/` folder holds one parquet file per table and `manifest.json`: the data version, the
seed (0), the versions of `roastery`, `roastery-sim`, `roastery-spec` and DuckDB, the sha256 of
each file and of `dataset.sql` and `tier3.sql`, the row counts, the defect log and the scripted
events. month's manifest also gives the sha256 of each of its 112 landing files.

sha256 of the zips:

```
e01244abc7a065db308907756343e6447edba35a8a110758fb3158c81d1e3815  roastery-data-1.0.0-full.zip
01efbe7bbf4790e7c18665782a3dbad06978774942a657f5f1960e12da7a79c9  roastery-data-1.0.0-month.zip
fa728cbbcecdf3fc47577117bd8f883be141d3dbe9ba0e6f828907a3f2326dec  roastery-data-1.0.0-tiny.zip
```

### What is new against the baseline

- **The tier-3 tables are the world's, not a formula's.** `daily_sales`, `order_values`,
  `subscribers`, `visits`, `checkout_test`, `deliveries` and `shop_days` are what the shop's own
  orders, payments, parcels, subscriptions, web visits and outside series add up to. Every number
  the pages teach from them is unchanged. `budget` is the owner's sheet.
- **Twelve new tables** (contract A, since 1.0):
  - `subscription_events`, `subscription_shipments`, `stock_movements`, `green_purchases`,
    `product_costs`, `shipments`, `pricing_rules`;
  - `web_visits`, `lesson_ids`;
  - the outside series `weather_days`, `door_counts`, `till_day_totals`.
- **Two new columns** on tiny's tables, in month and full only: `customers.account_kind`
  (consumer or business) and `web_events.visit_id`.
- **Landings** (month): the status feed as one jsonl file per UTC day of loading; the shop's
  nightly csv export (`raw_customers` whole, `raw_lines` as the lines new since the last export;
  9 October's carries the planted faults); the till's file per day from 6 October; the door
  counter, weather and old till's totals as csv series; `loads.json` names each file's table,
  load strategy, keys and watermark, as `model.sql`'s `loads` does (`raw_customers`, `till_lines`
  and the three series are not in `model.sql`; their rows are the simulator's). API pages are not
  landed yet.
- **Reading the csv landings:** an empty quoted cell (`""`) is an empty string and a bare empty
  cell is NULL (9 October's export tells C-05's e-mail apart this way). DuckDB's `read_csv` reads
  both as NULL unless it is given `allow_quoted_nulls = false`.

### Planted faults and the answer key

The faults are added after a correct app, as in tiny: 32 entries in each manifest's `defects`.
Among them:
- a duplicated line (L-05);
- a NULL quantity (L-07);
- a line for an unknown product (L-09);
- the order events of O-103, O-105 and O-107, which are never delivered;
- 7 October's stock count sent twice, the second time as a recount at 06:30 on 8 October;
- dirty cells in `raw_customers` and `raw_lines`.

`scripted_events` names what a lesson finds:
- Finland's drop, 20–26 April 2026;
- the checkout test, 2 March to 10 April 2026;
- the eight business accounts;
- the 13 small lesson orders that belong to them;
- the lost parcel, order 297;
- the refund, order 300.

### Known limits

- Tiny's grain sentences are kept word for word for `customer_extracts` ("two nightly copies")
  and `till_receipts` ("of a listed member"). In month the extracts run every October night, and
  the till also rings anonymous walk-ins.
- Parcels ship and deliver on Sundays too: `deliveries` ships the day after the order.
- month is cut by each table's own day:
  - it holds some events, payments and shipments of September's orders;
  - orders are cut by the Bergen date, `order_events` by the UTC day it was loaded (as the feed's
    files), and other stamps by their UTC date.
- full's raw tables are 9 October's export whole; month's are that export's landed files.
- Loading `raw_customers` by merge leaves four rows whose key the faults dirtied (`'C-01 '`,
  `c-02`, a tab before C-03, a no-break space after C-04). That is the lesson the faults teach.
- The subscribers outside the cast never place web orders, so the subscriber discount (10 %, June 2024 to June 2025)
  sits in `pricing_rules` and prices no line.
- Shop-channel orders and the business accounts' trade begin in January 2026.
- O-105 is never shipped: C-05 has no postal code, and the app refuses the parcel.
- C-01's year is played at the old prices.
- The shop is closed on Sundays; the old till's totals end on 9 October.

### Built and checked by

- the spec suite on tiny, month and full: 495 checks, none waiting for data;
- the shop and simulator suites: 782 tests;
- `tiny.sha256` and `volume.sha256`, the same on Windows and Linux;
- reviewed by two independent reviews and `/code-review` before the release.
