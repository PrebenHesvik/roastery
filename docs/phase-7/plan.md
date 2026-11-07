# Phase 7 plan: the storefront, and the thin API it stands on

Draft 1, approved by the owner on 2026-11-07. The owner reordered §8 of `docs/phase-6/plan.md`:
the storefront comes first, as the live shop's front end; Design Patterns waits until the server
has been through real refactoring (F7).

---

## Start here

1. Read **Status** below: the first step that is not ticked is the current one.
2. Read `CLAUDE.md` at the repository root: the rules, the freezes, how agents are briefed.
3. The decisions (F1–F9 and each ADR) are made. A change is a new numbered row, with its reason.
4. Contract B does not move in this phase: `packages/shop/tests/contract_b.txt` and
   `packages/sim/tests/tiny.sha256` stay byte-identical, so there is no new data version.
5. Before the context runs low, write where you stand into Status and Notes.

---

## Status

| step | state |
|---|---|
| 7.0 decisions and design direction | [x] ADRs 0016–0019 accepted 2026-11-07; Sydvest chosen |
| 7.1 the shop's HTTP edge (`packages/shop`) | [ ] |
| 7.2 `packages/api`: FastAPI on sqlite | [ ] |
| 7.3 the contract to TypeScript | [ ] |
| 7.4 the storefront shell (`apps/storefront`) | [ ] |
| 7.5 the shop flow | [ ] |
| 7.6 close: review, `DESIGN.md`, CI, `shop-0.2.0` | [ ] |

Notes:

- 2026-11-07 (7.0): `PRODUCT.md` is written. The direction round dealt the coastal-ferry timetable ("Departures from Bergen") as the roll and Sydvest as Claude's pick; the owner chose **Sydvest**, and named the shop **Sydvest Kaffebrenneri** (wordmark "Sydvest"). The direction contract is in `.impeccable/surfaces/apps-storefront-src-pages-home-tsx.md`, and the chosen first-viewport sketch is `.impeccable/mocks/decision/model-pick.html`. Code-led: no image generation here. ADRs 0016–0019 are written and accepted by the owner (F8, F9 added; F1 amended). They found the plan off in five places, each kept as an open point in its ADR: VAT is `VatRates.rate_on` and a module `vat_of`; `local_date` is in `clock.py`; `SequentialIds` counts in memory, so the state db keeps a counter; `fx.py` copies `script.FX`'s latest rates and a dev test pins them; ADR 0013's "built before phase 7" is stale.

---

## 0. Context

No HTTP API exists. `packages/shop` is a service layer (`App`, `bootstrap.wire`) on sqlite and
in-memory stores. Its services have no read calls, there is no cart, and there is no step that
starts a payment. ADR 0013 plans framework-free handlers in the shop (`api.py`, `middleware.py`,
`idempotency.py`) and FastAPI as a thin package outside it.

The owner decided on 2026-11-07:
- a thin API first: FastAPI, sqlite, run locally, with a fake sandbox payment; hosting, real
  payments and the live trickle come later;
- the storefront in React, English copy ready for translation, guest checkout with no logins;
- a dark theme by default and a light one. The mood: Bergen's dark, rainy, cozy autumn;
- Claude designs the site and proposes the shop's name. The roaster has none in either repo.

The outcome:
- a runnable local shop, the API on :8000 and the storefront on :5173;
- browse, cart, checkout, pay, then order status, tested end to end;
- a committed visual identity (`PRODUCT.md`, `DESIGN.md`).

## 1. Constraints

- Contract B is byte-identical. That means:
  - no new `ShopError` subclass;
  - no field added to `App` or `Settings`;
  - no method added to a pinned class;
  - no edit to `checkout.py`.

  The phase is released as `shop-0.2.0`, on the owner's word.
- `CLAUDE.md`'s rules hold. `packages/shop` reads no wall clock; the API package supplies it.
- The API's settings use the `SHOP_API_*` prefix, because `Settings.from_env` rejects unknown
  `ROASTERY_*` names.

## 2. Decisions

| # | decision | why |
|---|---|---|
| F1 | `Email` stays `@example.invalid` (C25). Guest checkout registers the pseudonym `guest-<n>@example.invalid` and the name `Guest <n>`; the guest's real name, e-mail and address live only in the API's own state db (the name amended by the owner, 2026-11-07) | the shop's data contract does not move; the extracts never hold a guest's personal data |
| F2 | Guest checkout is two calls: `register` commits before `place`. A stock pre-check runs first; an orphan customer is logged, not erased | `place` takes a `CustomerId`; contract B is frozen |
| F3 | Only Norway shows "incl. VAT". Sweden and Finland are told "no Norwegian VAT; import VAT on delivery", with an estimate; Denmark gets no landed price (coffee excise) | ADR 0010 and `docs/facts/vat.md`; IOSS is left for the live shop |
| F4 | The street address is kept in the API's state db | `Customer` holds only a postal code |
| F5 | Out of scope: subscriptions, business accounts, refunds, real payments, hosting, the outbox relay (`ClosedFeed`) | guests cannot manage a subscription; the live shop plans the rest |
| F6 | P-12 Decaf has no price row and shows as "coming soon", with no add-to-cart | the catalogue as it is |
| F7 | The storefront is phase 7. Design Patterns, the live shop, DevOps and the medallion pipeline are renumbered when each is planned | the owner, 2026-11-07: pages should teach a server changed under pressure, not the first build |
| F8 | The API reads the wall clock once per request (`RequestClock`), and a quote builds a throwaway draft order so `vat.scheme_for` prices it (ADR 0016, 0017) | the re-quote and `place` price on the same day; VAT has one home for phase 8's IOSS |
| F9 | The fake provider's required settings take placeholder values (ADR 0016) | nothing reads them until real payments |

## 3. The steps

### 7.0 Decisions and design direction (opus, with the owner)

- **ADRs:**
  - 0016: the HTTP adapter, its live wiring, the single request lock (the unit of work refuses
    re-entry), the `SHOP_API_*` prefix, the state db.
  - 0017: `storefront.py` (the read side) and the quote.
  - 0018: fx, the VAT display, the sandbox amount.
  - 0019: the front end.
- **`PRODUCT.md`** (Impeccable init), from confirmed facts only. No testimonials, no shipping
  prices.
- **The direction round:** Impeccable's `concept-seed` for the home page, on its decision page.
  The owner picks the world and the name.
  - Claude's own candidate: *Sydvest Kaffebrenneri*, oilskin yellow on wet slate.
  - Code-led: there is no image generation here, and the shop pages are Operate surfaces.
  - The direction contract goes into the surface brief.
- **Done when:** the owner has read the ADRs, the name and direction are chosen, and `PRODUCT.md`
  and the surface brief are committed.

### 7.1 The shop's HTTP edge (`packages/shop`)

| unit | model | what |
|---|---|---|
| `storefront.py` | opus | the service row of `LAYERS`; `Storefront(uow, clock, rules)`, not on `App`: `products()`, `product(id)`, `quote(country, items)`, `order(id)`; reuses `pricing.per_rule`, `rule_named`, `price_lines`, `local_date`, `vat.VatRates`, `vat_of`, `scheme_for` |
| `api.py` | sonnet | framework-free handlers and `STATUS` (ADR 0006, plus `ProviderRefused` 402 and `ProviderUnavailable` 503); a client price never reaches `Item` (a test) |
| `idempotency.py`, `middleware.py` | sonnet | the `Keys` protocol, an in-memory twin, `once()`; `logged`, `timed` |
| layers | haiku | `test_architecture.py` `AWAITING` keeps only `cli`; architecture.md §1–2 |

**Done when:** the suite and ruff are green on both stores, `contract_b.txt` and tiny's sha256 are
unchanged, and `check_direction` is clean.

### 7.2 `packages/api` (`roastery_api`)

Its parts:
- `live.py` wires `sqlite_store` and `wire` with a system clock, `ClosedFeed` and `FakeProvider`,
  under one lock per request.
- `state.py` holds the API's own tables:
  - order links: a `secrets.token_urlsafe(24)` token per order. Order ids are guessable, so they
    are never the link;
  - the guest's contact details;
  - an id counter.
- `seed` reuses the simulator's catalogue setup, as a new `roastery_sim.seed.catalogue()`, on an
  empty catalogue only. `roastery-sim` is a dev dependency.
- `fx.py` gives fixed rates from `script.FX`. Orders stay in NOK.
- The endpoints:
  - `GET /products`, `GET /products/{id}`;
  - `POST /quote`;
  - `POST /checkout`, with `Idempotency-Key`; it re-quotes and answers 409 `PriceChanged`;
  - `POST /sandbox/payments`: approve, decline (402) or outage (503);
  - `GET /orders/{token}`.

  Errors are problem+json.

**Done when:** a TestClient walk passes. Seed, quote, checkout, approve, then the order reads
`paid`. Decline gives 402. The same key gives the same reply, and another body gives 409. 20
parallel requests pass. A restart raises no `DuplicateId`.

### 7.3 The contract to TypeScript (sonnet)

`python -m roastery_api.openapi` writes `apps/storefront/openapi.json`. `openapi-typescript` turns
it into `src/api/schema.d.ts`, and `openapi-fetch` is the client. CI fails on drift.

### 7.4 The storefront shell (`apps/storefront`)

- **Stack:** Vite, React, strict TypeScript, React Router, TanStack Query.
- **Tooling:** ESLint (with jsx-a11y), Prettier, Vitest with Testing Library and MSW.
- **Theme:** tokens on `:root` with `[data-theme]`; dark is the default; a remembered toggle; AA
  contrast in both themes; a self-hosted face.
- **Copy:** `t()` with `en.json`; `Intl.NumberFormat` per currency; product copy in
  `src/content/`.

### 7.5 The shop flow

- **Routes:** `/`, `/shop`, `/shop/:id`, `/cart`, `/checkout`, `/pay/:token` (a labelled test
  payment), `/orders/:token`, `/visit` (the Bergen counter).
- **States:** loading, empty cart, out of stock, coming soon, decline, outage with retry, unknown
  token.
- **Tests:** a Playwright smoke against the real API on a fresh seeded db, approve and decline;
  screenshots at 1440 and 390 in both themes.

### 7.6 Close

1. Impeccable's detector, finish review and documenter: `DESIGN.md` and `.impeccable/design.json`.
2. `security-review` on `packages/shop` and `packages/api`, then `/code-review`, then the advisor.
3. CI: a `storefront` job (lint, typecheck, vitest, the OpenAPI drift check, build) and an `e2e`
   job.
4. Tag `shop-0.2.0`, on the owner's word.

## 4. Verification

- `uv run python -m pytest`, `uv run ruff check`, `uv run ruff format --check`. `contract_b.txt` and
  `tiny.sha256` are unchanged.
- `uv run python -m roastery_api seed`, then `uv run uvicorn roastery_api.app:app`, then
  `npm run dev` in `apps/storefront`. Walk the shop in both themes, in NO, SE and DK.
- `npm run lint`, `npm run typecheck`, `npm test`, `npm run build`, `npx playwright test`.
