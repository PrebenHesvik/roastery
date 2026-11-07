# 0019. The storefront

Status: accepted by the owner, 2026-11-07 (step 7.0, decisions F1, F3, F5 and F6 of `docs/phase-7/plan.md`)

## Context

The owner chose React for the storefront, English copy ready for translation, guest checkout with no logins, and a dark theme by default with a light one (plan §0). It runs locally on :5173 against the API on :8000 (ADR 0016).

What the other records fix:

- **The server owns every price, VAT line and stock state** (ADR 0017, `PRODUCT.md` principle 1). The page never computes a price; it shows what `POST /quote` returns.
- **Money on the page** is ADR 0018: NOK and a display currency per country, the VAT wording per country, no landed price for Denmark.
- **Errors** are problem+json with a `code` that is the class name (ADR 0016). The page switches on `code`.
- **`POST /checkout` and `POST /sandbox/payments` require an `Idempotency-Key`** (ADR 0016).
- **The visual world is chosen**: Sydvest Kaffebrenneri (`PRODUCT.md`, Brand Commitments). Its direction contract is in `.impeccable/surfaces/apps-storefront-src-pages-home-tsx.md`, with the picked sketch at `.impeccable/mocks/decision/model-pick.html`. `DESIGN.md` is written in 7.6 from the built pages. This ADR names where the world lives; it does not restate it.
- **The repository is Python.** `CLAUDE.md`'s line lengths and ruff rules govern `packages/`; the storefront is the first TypeScript.

## Decision

### Where and what

`apps/storefront`, an npm project of its own, outside the uv workspace (`pyproject.toml`'s members are `packages/*`).

| part | choice | why |
|---|---|---|
| build | Vite | a fast dev server and a static build; nothing to host yet |
| UI | React | the owner's choice |
| language | TypeScript, `strict: true`, plus `noUncheckedIndexedAccess` | the API's types are generated; strictness makes them bite |
| routing | React Router | the routes below; the router loads no data, TanStack Query does |
| server state | TanStack Query | products, quotes and orders are server state: cached, refetched, retried in one place |
| API client | `openapi-fetch`, typed by `openapi-typescript` | below |

The routes (plan 7.5): `/`, `/shop`, `/shop/:id`, `/cart`, `/checkout`, `/pay/:token`, `/orders/:token`, `/visit`. An unknown path is a not-found page.

### The contract to TypeScript

1. `python -m roastery_api.openapi` writes `apps/storefront/openapi.json` from the FastAPI app, sorted, with LF line ends, so the same code gives the same bytes.
2. `openapi-typescript` turns it into `src/api/schema.d.ts`.
3. `openapi-fetch`'s `createClient<paths>()` is the one client. No hand-written fetch to the API.

Both generated files are committed. CI regenerates them and fails on any difference (`git diff --exit-code`), so a change to the API that the storefront has not taken fails the build. The problem+json body is in the schema, with `code` as a string the page narrows to the codes it handles.

The base URL is `VITE_API_URL`, `http://localhost:8000` by default. The API's CORS allowlist admits `http://localhost:5173` (ADR 0016); no dev proxy.

### The cart

- The cart is in `localStorage` under one key, `sydvest.cart`, as `{ "version": 1, "country": "NO", "items": [{ "productId": "P-10", "qty": 2 }] }`.
- It holds no price, no name and no total. What it shows comes from `POST /quote`, keyed in TanStack Query on the country and the items.
- A value that does not parse, or has another `version`, is dropped and the cart starts empty. A change to the shape is a new version, never a silent reinterpretation.
- Every read and write is in `try`/`catch`: a private window or blocked storage gives an empty cart that still works for the visit.
- The country is chosen before a final price is shown (`PRODUCT.md`), and is part of the cart, since the quote depends on it.

### Checkout and the key

- One idempotency key per checkout attempt: `crypto.randomUUID()`, made when the buyer confirms, kept in `sessionStorage` with a hash of the body it was made for.
- A reload or a second click resends the same key with the same body and gets the same reply (ADR 0016).
- A changed body (another quantity, another address) is a new attempt with a new key. After a 409 `PriceChanged`, the page shows the new quote; confirming it is a new attempt.
- The key is dropped on any stored reply: a 201, and a 4xx such as 402 or 409, since the API replays a stored reply for the same key (ADR 0016). After a decline or a refusal, the next try is a new attempt with a new key. Only an outage (503), which is not stored, keeps the key for "try again".
- The pay page keeps its own key per attempt by the same rule.
- `sessionStorage` and not `localStorage`: a key belongs to one tab's attempt, not to every tab.

After checkout, the page goes to `/pay/:token`, then to `/orders/:token`. The token is the only link to the order (ADR 0016). The guest's contact is sent once, in the checkout body, and the page does not keep it.

### States the pages handle

Each is a designed state, not an error screen: loading; an empty cart; out of stock (409 `OutOfStock`, and `in_stock: false` on a listing); coming soon (a product with no price, F6: no add-to-cart); a declined payment (402 `ProviderRefused`); an outage with "try again" (503 `ProviderUnavailable`); an unknown order link (404 `UnknownToken`); a changed price (409 `PriceChanged`). Any other code shows a plain "something went wrong" and its `code`.

### Copy and numbers

- Every string the interface shows is `t('key')` from `src/i18n/en.json`. No literal copy in a component. `t()` is a small function of the app's own, with `{name}` interpolation; a library replaces it when a second language comes, and the call sites stay.
- Product copy (the beans' descriptions) is in `src/content/`, by product id. The API gives the facts (name, origin, roast, weight, price); the content gives the words. Nothing in `src/content/` names a price or a stock level.
- No copy is invented that `PRODUCT.md` lists as absent: no testimonials, reviews, shipping prices or delivery promises.
- Amounts are formatted with `Intl.NumberFormat('en', { style: 'currency', currency })`, the currency from the API's amount. Figures are tabular. No rate, no VAT percent and no rounding is written in the storefront (ADR 0018).

### Theme

- Colours, type and spacing are tokens: CSS custom properties on `:root`, with `[data-theme="dark"]` and `[data-theme="light"]`.
- Dark is the default, whatever the system says (the owner's constraint). A toggle sets the other; the choice is remembered in `localStorage`, read by a small inline script in `index.html` before the first paint, so the page never flashes the wrong theme.
- Both themes meet WCAG 2.2 AA contrast. Motion respects `prefers-reduced-motion`.
- The face is self-hosted, in `public/fonts/`: no call to a font CDN.
- The values of the tokens are the direction contract's. `DESIGN.md` and `.impeccable/design.json` record them in 7.6.

### Quality tools

| tool | what |
|---|---|
| ESLint | `typescript-eslint` strict, `eslint-plugin-react-hooks`, `eslint-plugin-jsx-a11y` |
| Prettier | formatting; ESLint does not format |
| Vitest with Testing Library | components and hooks, by role and label, as a user finds them |
| MSW | the API mocked at the network edge in unit tests, its handlers typed by `schema.d.ts` |
| Playwright | a smoke against the real API on a fresh seeded db: browse, cart, checkout, approve, order `paid`; and a decline. Screenshots at 1440 and 390 wide, in both themes |

The npm scripts are `lint`, `typecheck`, `test`, `build`. CI (7.6) runs a `storefront` job (lint, typecheck, vitest, the drift check, build) and an `e2e` job.

## Alternatives refused

| alternative | why not |
|---|---|
| Next.js or another server-rendering framework | a second server beside the API; nothing to render on a server for a local shop |
| A hand-written API client and types | they drift from the API without a sound; the generated ones fail CI |
| Redux or another global store | the state is server state (TanStack Query) plus a small cart; a store adds a layer for neither |
| Prices in the cart | stale the moment a campaign starts; the server owns them (ADR 0017) |
| The cart on the server | needs a session or a login; guests have neither (plan §0) |
| An idempotency key per page load | a reload is the case the key exists for; a key per attempt survives it |
| A new key per click | a double click would place two orders |
| An i18n library now | one language; a small `t()` keeps the call sites a library will take |
| Following `prefers-color-scheme` by default | the owner chose dark first |
| A font from a CDN | a third party on every page view, and a flash of the fallback |
| Mocking `fetch` in unit tests | MSW mocks the network, so the real client and its types run |

## Consequences

- The repository gains Node and npm. `uv run python -m pytest` is unchanged (its `testpaths` are `packages`); the storefront's checks are npm scripts and their own CI jobs.
- A change to an endpoint is a change to `openapi.json` and `schema.d.ts` in the same commit, or CI fails.
- The page cannot show a price the server did not give. A bug in a price is a bug in the shop, found by the shop's tests.
- Adding Norwegian, Swedish, Danish or Finnish is a new JSON file and a library behind `t()`. The VAT wording per country is already keyed.
- A visitor with storage blocked gets dark on each visit, which is the default anyway, and a cart that lasts the visit.
- The Playwright smoke needs Python and Node in one job: it starts the API on a fresh db, seeds it, and builds the storefront.

## Open points

1. **The Node version** is not fixed by the plan. 7.4 pins it in `.nvmrc` and `package.json`'s `engines`, to a current LTS.

## Pages served

Phase 7 writes no pages (F7). The storefront is the live shop's front end, not a teaching page. The `idempotency` page may show the key per attempt from the client's side.
