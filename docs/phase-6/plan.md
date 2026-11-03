# Phase 6 plan: the roastery app, the simulator and `roastery-data 1.0`

Draft 1, approved by the owner on 2026-11-03. Written by the lead session with Fable; to be
revised with the owner. data-docs points here from `docs/proposal-roastery/phase-6.md`.

---

## Status

| step | state |
|---|---|
| 6.0 set up | [~] local workspace done; CI waits on the GitHub repo |
| 6.1 contract A: data | [ ] |
| 6.2 contract C: architecture | [ ] |
| 6.3 app core and service layer | [ ] |
| 6.4 the teaching week through the simulator (contract B frozen) | [ ] |
| 6.5 the volume, `roastery-data 1.0` | [ ] |
| 6.6 data-docs reads the release | [ ] |

Notes:

- 2026-11-03 (6.0): the workspace is three packages, `roastery` (shop), `roastery_sim`,
  `roastery_spec`, each with an import test; ruff at 100 (72 in `packages/shop`), single
  quotes, docstrings in double quotes as ruff's Q rule wants. The GitHub repository (name,
  public) is created only on the owner's word; then CI runs and 6.0 is ticked.

---

## 0. Context

**Why.** Every route of data-docs now runs on the roastery, but its data has three separate
sources, and they do not describe one shop:

| layer | source today | state |
|---|---|---|
| tiers 1–2 (the teaching week, 30 tables) | hand-written `dataset.sql` | exact, frozen, 279 tests |
| tier 3 (8 volume tables) | formulas in `tier3.sql` | each table proves its own lesson (42 tests), but the scales disagree: `daily_sales` 18.8 bags a day, `order_values` 2.2 orders a day, `shop_days` 20 till receipts a day |
| silver and gold | `model.sql`, built from tiny only | fine for the pages; no bronze, no real nights |

**Outcome.** One simulated shop (January 2024 to the teaching week) produced by a real app,
released as the versioned dataset `roastery-data 1.0` (`tiny`, `month`, `full`). The pages
keep **the same answers**: every existing test passes unchanged on the simulator's output.
The app's code is shaped on purpose so that Design Patterns (phase 7) and DevOps (phase 8)
can be rebuilt on it.

**Not in phase 6** (each gets its own plan later, see §8): the live shop and its hosting, the
medallion pipeline package, the HTTP API beyond what the simulator needs, the storefront and
the dashboard, the groundwork project.

---

## 1. Decisions already made

| # | decision | by | date |
|---|---|---|---|
| D1 | The work lives outside data-docs, in `roastery`, one uv workspace repo in the owner's own GitHub | owner | 2026-11-03 |
| D2 | data-docs stays a stand-alone learning app that reads a **pinned** data release | owner | 2026-11-03 |
| D3 | Phase 6 has its own plan document (this one), split into sub-phases | owner | 2026-11-03 |
| D4 | The answers stay the same: `test_roastery_dataset.py` and `test_roastery_tier3.py` pass unchanged on the simulator's output | owner | 2026-11-03 |
| D5 | stats-polars merges into data-docs **before** data-docs switches to the simulator's data (option b) | owner | 2026-11-03 |
| D6 | v0.12.0 is released once the stats-polars and JavaScript sessions are done | owner | 2026-11-03 |
| D7 | **Business accounts**: customers get a `kind` (consumer, business). `daily_sales` counts consumer sales only; the large `order_values` orders (10 bags, the café's 48) belong to business accounts | owner | 2026-11-03 |
| D8 | **`subscribers`** = the subscriptions of every customer outside the teaching week's cast; all 240 rows and their claims stay exact | owner | 2026-11-03 |
| D9 | The app's architecture is a contract for the **Design Patterns** route: each of its 35 pages gets a real home module, chosen on purpose | owner | 2026-11-03 |
| D10 | Faults are injected by the export writer after a correct app, with a defect log (master plan, decision 7) | plan | 2026-10-28 |
| D11 | Subscription bags ship as their own table `subscription_shipments`, not as `orders` rows (reverses gap fix G7 in `map-patterns-devops.md`): orders rows would break tiny's exact 8 orders and `customer_months` | Claude + Fable | 2026-11-03 |
| D12 | The till story: the old till left only day totals (`shop_days.receipts`); the new till, with line detail, starts on 6 October 2026 (R-5001). Account customers at the counter are app orders (channel `shop`) throughout; only anonymous walk-ins went through the old till. What the old till sold is not in the data, and the pages say so | Claude + Fable | 2026-11-03 |
| D13 | **Frozen columns stay frozen.** `tiny` keeps its exact columns. The new columns live in the app database and in `month` and `full`, and the tiny ⊂ month test compares on tiny's columns only:<br>• `customers.kind` (D7);<br>• `source` (`scripted`, `simulator`, `visitor`), which is a live-shop need: it lives in the app database and the live shop, and the frozen extracts carry it only where a page needs it.<br>Each cut is exact per table: `stock_daily` in tiny is the day window **and** P-10/P-20 only, so the warehouse's count of every product is projected | Claude + Fable | 2026-11-03 |
| D14 | D4 holds as written: `test_roastery_tier3.py` asserts no header text, so a changed grain sentence (D7, D8) does not break it | checked | 2026-11-03 |

---

## 2. Three contracts, settled before the code they bind

Phase 6 is deliberate because three things depend on each other. Each is written down and
agreed before the code it binds.

| contract | what it fixes | who depends on it | where it lives |
|---|---|---|---|
| **A. Data contract** | every table: grain, columns, types, keys, the cut of `tiny`, the claims | every data-docs page; the simulator's acceptance | `packages/spec` (tests + `contract.md`) |
| **B. Simulator call surface** | the service functions the simulator calls, and their signatures | the simulator; a change after 1.0 is a new data version | `packages/shop`, frozen at 6.4's end |
| **C. Architecture contract** | which pattern lives in which module, layers, the persistence and wiring choices | the Design Patterns pages (phase 7), DevOps (phase 8) | `docs/architecture.md` + ADRs in `docs/adr/` |

**Answer to "won't app features depend on the dataset?"** Yes, in both directions, and that is why A and B are co-designed:

- **Data → app.** Every app-made row needs an app feature:
  - caller-supplied ids for scripted rows (O-101, PAY-1…);
  - channel `web | shop`;
  - the customer `kind` (D7);
  - `log_event` with source, variant and step;
  - stock movements with a reason;
  - promised and actual delivery;
  - VAT by kind;
  - the `Clock` port everywhere;
  - a `source` column on every row (`scripted | simulator | visitor`).
- **App → data.**
  - The app's bookkeeping makes rows no hand would write: `updated_at`, tombstones, the change log's interleaved counter (hence `seq` is renumbered by the tiny writer), and outbox batches (hence E-08 is late and E-10 arrives out of order).
  - Rows **not** made by the app: the old till's day totals, the door counter, the weather, the new till's files, FX rates and the provider's redelivery. The simulator writes these as external systems.
- **Storefront and dashboard add no rows**, so they cannot change the data. That is why they can wait.

---

## 3. The repository

```
roastery/                    uv workspace, Python 3.13, ruff (72 chars in packages/shop)
  packages/
    spec/        the data contract: contract.md, claims as pytest, parametrised on a data folder
    shop/        the app: domain, service layer, stores (memory, sqlite); API later
    sim/         the simulator, the external systems, the export writer, the defect log
  apps/          later: storefront, management dashboard (own plans)
  docs/
    phase-6/plan.md        this file
    architecture.md        contract C: the pattern map, layers, choices
    adr/                   one file per architecture choice
    data-changelog.md      roastery-data versions
  .github/workflows/       CI: ruff, pytest, determinism check (DevOps comes in phase 8)
```

Rules carried over from data-docs:
- shown code has 72-character lines, no module state, no wall clock;
- e-mails end in `example.invalid`;
- sorted outputs;
- money is `Decimal`.

---

## 4. Contract A in detail: one world under the frozen claims

The rule: **the tier 3 formulas stop being outputs and become the simulator's scripts.**
Whatever is scripted is exact by construction.

### 4.1 How each tier 3 table becomes a cut of the world

| table | definition in the world | exact |
|---|---|---|
| `daily_sales` | per day and product, the sum of **consumer** order lines (web and shop) at list price. The formula is the simulator's **demand schedule**: the quota it fills with generated orders | yes, by scripting |
| `order_values` | a **lesson set**: 600 scripted orders of 2026, consumer and business (D7), played inside the wider trade | yes |
| `budget` | a reference table, hand-set like `prices`; never simulated | yes |
| `checkout_test` | every visitor of the product page during a scripted 40-day A/B test; `variant` sits on the web event; `converted` = reached the checkout step, not an order placed | yes |
| `visits` | the **attributed panel**: visits with a source (newsletter, ads); direct traffic has no source and is outside the panel | yes |
| `subscribers` | the subscriptions of every customer outside the cast (D8) | yes |
| `deliveries` | the shipments of the lesson set's 480 web orders, promised and actual day; order 297 lost for 21 days | yes |
| `shop_days` | three outside systems: the door counter (walk-ins), a weather feed (rain), the old till's day totals (receipts) (D12) | yes |

### 4.2 The teaching week inside the volume (from the master plan's phase 6 outline)

- From 5 to 9 October, no customer outside the cast buys P-10 or P-20.
- Opening stock is P-10 = 42 and P-20 = 5 on 5 October, after the October subscription shipments.
- The scripted rows carry their hand-written ids.
- C-01's year (November 2025 to September 2026) is scripted at the old prices.
- The till rings only R-5001 on 6 October.
- The export writer drops the events of O-103, O-105 and O-107, sends the 7 October stock twice, and plants L-04/L-05, L-07, L-09 and O-106. All are listed in the defect log.

### 4.3 New tables (the signals the later ideas need; adding one after 1.0 is a new version)

| table | grain | for |
|---|---|---|
| `subscription_events` | one skip, pause, resume or cancel, with a reason | MRR and churn with a cause; closes the `command` page's gap |
| `subscription_shipments` | one bag shipped to a subscriber (D11) | MRR, stock |
| `stock_movements` | one movement: roasted, sold, shipped, written off, counted | stock flow, forecasting |
| `green_purchases` | green coffee bought by the kilo | purchase planning |
| `product_costs` | cost per product and period (green, bag, roasting) | margin |
| `shipments` | one parcel, promised and actual day | late delivery as a fact |
| `pricing_rules` | the subscriber discount, campaign percentages | closes gap G3 (strategy, composition, registries pages) |
| `customers.kind` | a column, consumer or business (D7) | D7; B2B and margin lessons |
| scripted country drop | a known day when Finland's orders drop | the anomaly alert (later) |

Each new table gets a grain, columns (at most 6) and a claim in `packages/spec` before the
simulator writes it.

### 4.4 The extracts and their storage

| extract | shape | where |
|---|---|---|
| `tiny` | the teaching week; stays in data-docs' `dataset.sql`, `polars_frames.py`, `spark_frames.py` | data-docs (the source of truth); the sim's tiny writer is tested against it |
| `month` | October 2026, every system, nightly landings | zip of parquet + `manifest.json` (seed, versions, rows, sha256, defect log), a GitHub release asset of `roastery` |
| `full` | January 2024 to the teaching week | the same |

The shape of each system:

| system | shape |
|---|---|
| app database | tables, the end snapshot plus nightly copies |
| status feed | jsonl with `loaded_at` |
| csv exports | all text, with the faults |
| API pages | json, paged |
| till | csv, one file per day from 6 October |
| door counter and weather | csv series |

The nightly landings are written so that the medallion plan (§8) can run on them. Each landing is stamped `_source_file` and `_loaded_at`, and a `loads` manifest matches the `loads` table in `model.sql`.

---

## 5. Contract C in detail: the architecture, for Design Patterns

The 35 pages of `docs/proposal-roastery/map-patterns-devops.md` §1 are the requirement list.
Step 6.2 turns them into `docs/architecture.md`:

1. **The pattern map.** For every page: the pattern, its home module in `roastery`, its fit (strong, partial or weak), and the naive twin that stays in data-docs (`without/`). The module map of `map-patterns-devops.md` §2 is the starting point, not yet binding.
2. **The partial fits closed by the new data:**
   - `strategy`, `composition-over-inheritance` and `registries-and-plugins` get `pricing_rules`.
   - `command` gets `subscription_events`.
   - `parse-dont-validate` parses the new till's files.
   - `cache-aside` stays honest: a stale price at checkout.
3. **The choices that shape every page, one ADR each, chosen for teaching as well as for running:**

| choice | recommendation to weigh in 6.2 |
|---|---|
| persistence | stdlib `sqlite3` behind hand-written repositories and a unit of work (no ORM, so the patterns show) |
| domain types | frozen dataclasses, value objects, one class per order state |
| errors | a `Result` type at the edges, exceptions inside |
| events | an in-process EventBus plus an outbox table and relay |
| time | the `Clock` port; the app never reads the wall clock |
| wiring | one `bootstrap.py`; the simulator is the second driving adapter beside the API |
| the API | framework-free handlers first (the pages show them); a FastAPI adapter comes with the live shop plan |
| settings | `ROASTERY_*`, read once, typed |
| checks | `architecture.py` (layers, import direction) and the contract suite on both stores |

4. **Teachability rules** are enforced by ruff and a test in the repo: 72 characters, no module state, no wall clock, sorted listings.

The **`codebase-design`** skill runs for the seams. The owner reads `architecture.md` before
6.3 writes the code.

---

## 6. The sub-phases

Each step ends with checks that pass. Models follow data-docs' `CLAUDE.md` table: `opus` for
judgment and teaching, `sonnet` for building to a clear spec, `haiku` for sweeps.

### 6.0 Set up (lead)
- `roastery`: git init, the uv workspace, ruff, pytest, CI skeleton; this plan committed as `docs/phase-6/plan.md`.
- data-docs: a short `docs/proposal-roastery/phase-6.md` that points to the plan and lists only the data-docs side (6.6). The master plan's phase table says "6: planned". This is committed on a fresh branch from `main`, never on `claude/javascript-route`.
- **Done when:** `uv run python -m pytest` runs (empty) in `roastery`; CI is green.

### 6.1 Contract A: the data contract (`packages/spec`)
- `contract.md`: every table of §4 (existing and new) with grain, columns, types, keys, its cut of `tiny`, its definition in the world (§4.1), and its system of origin (app or outside).
- The claims as tests, lifted from `tests/test_roastery_dataset.py` and `tests/test_roastery_tier3.py` and **parametrised on a data folder**, plus a claim for every new table.
- The "tiny ⊂ month" test (every row, except `customer_changes.seq`), on tiny's columns only (D13).
- `research` skill: the VAT facts (master plan, decision 11), written as a facts note before `vat.py`. The scope covers consumers **and** business buyers abroad (D7: a Swedish café pays VAT differently from a Swedish consumer), by kind (food, standard).
- **Done when:** the spec suite runs green against today's `dataset.sql` + `tier3.sql` output for every existing claim. The new tables' claims are skipped by data folder, not by marker, until the simulator writes them. The owner has read `contract.md`.
- Agent: `opus` for `contract.md`; `sonnet` to port the tests.

### 6.2 Contract C: the architecture (`docs/architecture.md`, ADRs)
- The pattern map, the closed gaps, the ADRs of §5, and the **call surface** (contract B) as typed signatures.
- **Done when:** every one of the 35 pages has a home module or a named reason; the owner has read it.
- Agent: `opus` + `codebase-design`; a review by a second `opus` agent that sees only the pages and the document.

### 6.3 The app core and the service layer (`packages/shop`)
- The core (ids, money, catalogue, order, subscription, pricing, vat, events, result), the ports, the memory and sqlite stores, the unit of work, the outbox, the provider SDK stand-in and adapter, the fakes, and the services the simulator calls.
- No API yet.
- **Done when:** the unit and contract suites pass on both stores; `architecture.py` passes. Contract B is a candidate here; it is frozen only after 6.4 proves it.
- Agents: one `sonnet` agent per module group against the ADRs; `opus` for `order`, `pricing` and `vat`.

### 6.4 The teaching week through the simulator (`packages/sim`, first part)
- The simulator plays **only** the scripted week (and C-01's year) through the service layer; the outside systems for those days; the export writer with the faults and the defect log; the tiny writer.
- **The gate.** The tiny writer emits `dataset.sql`'s own format. Two checks:
  1. **Cell equality:** DuckDB loads the simulator's tiny and data-docs' `dataset.sql`, and every table is equal cell for cell (the real guard: a ported test that drifts could pass silently).
  2. **The ported claims:** the spec's lifted claims pass on the simulator's tiny. data-docs' own `test_roastery_dataset.py` (279) reads the literal `dataset.sql` and stays green, untouched.
- **Done when:** both checks pass. This is the fastest feedback, and it proves contract B, which is then frozen (tag `shop 0.1.0`).

### 6.5 The volume, and `roastery-data 1.0`
- The demand schedule, the cast of customers (consumer and business), the lesson sets, the panels, the outside series, the signals of §4.3, nightly landings, `month` and `full`, the manifest.
- **Determinism is a gate:** two builds on two machines give the same sha256.
- **Done when:**
  - `test_roastery_tier3.py` passes unchanged on the tables derived from `full`;
  - the tiny ⊂ month test passes;
  - every new table's claim passes;
  - the release asset `roastery-data-1.0.0` is published with its changelog.

### 6.6 data-docs reads the release (waits on D5 and D6)
- A pinned version file; a cached, checksummed download into a gitignored folder; `roastery_data/build.py` reads the release.
- `tier3.sql` is replaced, not just deleted. `stats_export.py` lists it in `DATASETS` and the runners read its `-- table: X | key | grain` headers. A `tier3_release.sql` keeps the eight headers, each table now `CREATE TABLE x AS SELECT * FROM read_parquet(...)` from the release.
- The grain sentences change where D7 and D8 change a definition (`daily_sales` "consumer sales", `subscribers` "the other subscribers").
- A `haiku` sweep finds every page sentence that reads `daily_sales` as "all sales" or `subscribers` as "every subscriber" (Statistics, DAX, Data Modeling); an `opus` agent rewrites them.
- **Done when:**
  - the full suite passes;
  - `npm run export` shows no change in `generated/*.json` beyond the grain sentences;
  - every changed page is read by the `language-reviewer`;
  - `/code-review` has run;
  - the change is merged and released.

### Order and parallel work

```
6.0 ─► 6.1 contract A ─┬─► 6.3 app ─► 6.4 week ─► 6.5 volume ─► 6.6 data-docs switch
       6.2 contract C ─┘                                         (after stats-polars,
                                                                  JavaScript and v0.12.0)
```

6.0 to 6.5 never touch data-docs, so they can run while the other two sessions work.

---

## 7. How a session works

- **The lead** plans, briefs, checks and commits; one agent per unit; the brief has the five parts of data-docs' `CLAUDE.md`.
- **Status** sits at the top of `docs/phase-6/plan.md`: a box per step, a hash each, Notes. A box is ticked in the commit that finishes its step.
- **Reviews:** the advisor before a sub-phase is called done; `/code-review` before 6.5's release and 6.6's merge; `security-review` on `packages/shop` before 6.5.
- **Owner reads:** `contract.md` (6.1), `architecture.md` (6.2), the release notes (6.5). Nothing is pushed or released without the owner's word.

---

## 8. Planned separately later

| plan | why separate | what phase 6 already gives it |
|---|---|---|
| **The medallion pipeline** (`packages/lake` + new or changed Pipeline and Data Modeling pages) | it is a product of its own: bronze → silver → gold run night by night on `month` (DuckDB or Polars, Delta optional); the 168 code fences become run code; bronze is built instead of standing in. Phase 4's objection ("a second pipeline beside the app's repo") is gone | nightly landings with `_source_file` and `_loaded_at`, a `loads` manifest, the defect log per landing, gold names as `model.sql` has them |
| **The live shop** (hosting, database, trickle, sandbox payments, FastAPI adapter) | needs the stack and hosting decisions; no page reads it | the service layer, the simulator's deterministic per-day play, the `source` column |
| **Design Patterns on the app** (phase 7) | page work in data-docs | contract C and a pinned `shop` release |
| **DevOps** (phase 8) | page work plus real workflows | the repo, its CI |
| **Storefront and dashboard** (phase 9, `apps/`) | design work; adds no rows | the API, the gold tables |
| **The groundwork project** | its own repo | `full`, the defect log as the answer key |

---

## 9. Still to settle (none blocks 6.0 or 6.1)

| item | needed by | default if not settled |
|---|---|---|
| **tell the stats-polars session now**: `daily_sales` reads "consumer sales" (D7) and `subscribers` "the other subscribers" (D8), so its pages are written that way once | its next page | the owner passes it on, or the lead sends it |
| the 40 days of the checkout test | 6.5 | Claude and Fable pick them, outside every December and the teaching week |
| the day of Finland's drop, and its size | 6.5 | a weekday in spring 2026, orders halve for a week |
| the number of business accounts and their share of sales | 6.1 | as many as the lesson set needs, a few cafés and offices |
| the repo's name and visibility on GitHub | 6.0 | `roastery`, public |
| the VAT facts | 6.3 (`vat.py`) | researched in 6.1 |

---

## 10. Verification

- `roastery`: `uv run python -m pytest` (spec, shop, sim); the determinism job (build twice, compare sha256); ruff.
- Against data-docs, without editing it:
  - **tiny:** cell equality between the simulator's tiny and `dataset.sql`, loaded into DuckDB;
  - **tier 3:** the spec's ported claims on the tables derived from `full`;
  - data-docs' own two test files stay green on its literal files.
- After 6.6 in data-docs: `uv run python -m pytest`, `npm run export` (diff `generated/`), `npm run types:check`, `npm run check:links`, `npm run build`.

---

## 11. Risks

| risk | guard |
|---|---|
| a script collision not yet found (like D7 and D8) | 6.1 runs every claim against a data folder before the simulator exists; 6.4 proves the week before the volume |
| non-determinism (hash seeds, Decimal, sort order, parquet metadata) | a sha256 gate in CI from 6.4 on |
| contract B changes after 1.0 | frozen at 6.4's end; a change is a new data version with a changelog |
| the app grows for the pages, not the shop | contract C names a reason for each module; `premature-pattern` is a page, not a practice |
| the plan drifts from the master plan | 6.0 writes the pointer; the master plan's phase 6 outline is corrected in the same commit |
