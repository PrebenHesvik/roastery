# roastery

A small coffee roaster in Bergen, as software: the shop app, the simulator that runs three
years of its trade through the app, and the data contract its extracts are held to. The
extracts are released as `roastery-data`, read by the data-docs learning site.

| package | import | what |
|---|---|---|
| `packages/shop` | `roastery` | the app: domain, service layer, stores |
| `packages/sim` | `roastery_sim` | the simulator, the outside systems, the export writer |
| `packages/spec` | `roastery_spec` | the data contract and its claims, as tests |

The plan is `docs/phase-6/plan.md`.

    uv sync
    uv run python -m pytest
    uv run ruff check
