# roastery

A small coffee roaster in Bergen, as software: the shop app, the simulator that runs three
years of its trade through the app, the data contract its extracts are held to, and the web
shop of Sydvest Kaffebrenneri with the API it stands on. The extracts are released as
`roastery-data`, read by the data-docs learning site.

| package | import | what |
|---|---|---|
| `packages/shop` | `roastery` | the app: domain, service layer, stores, the HTTP handlers |
| `packages/sim` | `roastery_sim` | the simulator, the outside systems, the export writer |
| `packages/spec` | `roastery_spec` | the data contract and its claims, as tests |
| `packages/api` | `roastery_api` | the HTTP API: FastAPI over the shop, on sqlite |
| `apps/storefront` | - | the web shop: React, Vite, TypeScript |

The current plan is `docs/phase-7/plan.md`.

    uv sync
    uv run python -m pytest
    uv run ruff check

## Run the shop

The API, with a sandbox payment and a seeded catalogue (sqlite files of your choosing):

    export ROASTERY_DATABASE_URL=sqlite:///shop.db SHOP_API_STATE_URL=sqlite:///state.db
    uv run python -m roastery_api seed
    SHOP_API_SANDBOX=1 uv run python -m uvicorn roastery_api.app:app --no-access-log

The storefront (Node 26), in another shell:

    cd apps/storefront
    npm ci
    npm run dev

It proxies `/api` to `http://127.0.0.1:8000`. If that port is taken, start the API with
`--port 8700` and the storefront with `STOREFRONT_API_URL=http://127.0.0.1:8700 npm run dev`.

On Windows, use `python -m uvicorn`; the generated `uvicorn.exe` can be refused. A state db
made before 2026-11-07 must be re-seeded (order links are stored hashed).

    npm run lint && npm run typecheck && npm test && npm run build   # the storefront's checks
    npm run e2e                                                      # Playwright on the real API
