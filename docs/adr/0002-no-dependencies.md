# 0002. Stdlib plus tzdata in the shop

Status: accepted, 2026-11-04 (step 6.2, decisions C2 and C19)

## Context

Data-docs pins a `shop` release in phase 7 and imports `roastery` from it. Whatever the shop depends on, data-docs installs too, at the version the shop asks for. Data-docs already pins polars, duckdb and others for its own routes; a second pin of the same library from the shop can clash with them.

The `layers` page shows a violation: an inner module that reaches outward. That lesson needs an app whose inner modules import nothing outside the standard library, so the one bad import stands out.

The teaching app today, `firm`, uses the standard library only. Its `frames.py` (the bridge to polars) sits beside it, and `reports.py` returns rows.

## Decision

`packages/shop` has one runtime dependency, `tzdata`, and nothing else (C19, an amendment to C2). `tzdata` is a data package (PEP 615), not a library: `zoneinfo` reads the IANA time zones from it where the system has none. Its `pyproject.toml` lists `tzdata` alone, with a lower bound set in 6.3; the workspace's `uv.lock` pins the exact version (ADR 0008). The rest is the standard library.

- Storage is the standard library's `sqlite3` (ADR 0003).
- Money is `decimal.Decimal`; time is `datetime` with `zoneinfo`, whose zone data comes from `tzdata` (ADR 0008).
- The payment provider's SDK is a stand-in module, `provider_sdk.py`, in the vendor layer. It plays a library from outside the app without being one.
- `reports.py` returns rows: frozen dataclasses in sorted tuples. It never returns a frame. Polars stays in data-docs' `frames.py`, which turns the rows into frames for a page.

```python
@dataclass(frozen=True)
class SalesByKind:
    """One kind's sales: the read side's row."""

    kind: Kind
    lines: int
    qty: int
    amount: Money


def sales_by_kind(uow: UnitOfWork) -> tuple[SalesByKind, ...]:
    """The sales of each kind, sorted by kind."""
    ...
```

Tools that do not ship with the app (pytest, ruff) are dev dependencies of the workspace. They are not runtime dependencies.

Why `tzdata` is allowed: on Windows `ZoneInfo('Europe/Oslo')` raises `ZoneInfoNotFoundError` without it (`zoneinfo.TZPATH` is empty), and a slim container image may lack the system database too. C8 names zones (`ROASTERY_SHOP_ZONE`, a zone per country), so the app and its tests need them. Fixed offsets would get summer time wrong. `tzdata` holds data and no code, and data-docs' environment already has it.

## Alternatives refused

| alternative | why not |
|---|---|
| `reports.py` returns polars frames | The pin would pull polars into data-docs at the shop's version, beside data-docs' own pin. The app would hold a library it uses only to show tables. The read side's lesson (rows from the store) does not need it. |
| An ORM (SQLAlchemy) for the stores | It hides the repository and the unit of work, which are the patterns the pages show (ADR 0003), and it is a large dependency for six tables of rows. |
| A web framework (FastAPI) in the shop now | The handlers are framework-free so the pages show them (ADR 0013). A framework comes later as a thin adapter in its own package, with the live shop. |
| Pydantic for settings and payloads | `Settings.from_env` is one short module of the standard library and is itself the `configuration` page's lesson (ADR 0014). Parsing payloads by hand is the `parse-dont-validate` page. |
| The real payment provider's SDK | It needs network and keys, and changes on its own schedule. The stand-in has the shape the `adapter` page needs (camelCase, minor units, its own error). |

## Consequences

- The pin adds no library to data-docs but `tzdata`, which data-docs already has.
- A third-party import anywhere in `roastery` is a review finding. 6.3 may add a test that the package's `dependencies` name `tzdata` and nothing else (the name, not the bound).
- The FastAPI adapter of the live shop lives outside `packages/shop` and calls `api.py`'s handlers.
- `frames.py` in data-docs knows the row types of `reports.py`. A renamed field there is a page change (ADR 0015).

## Pages served

| page | what it shows |
|---|---|
| `layers` | an inner module with only standard-library imports; the one bad import is the lesson |
| `cqrs-lite` | `sales_by_kind` and `sales_by_country` returning rows; data-docs' `frames.py` shows them as a frame |
| `adapter` | `provider_sdk.py` as the outside library, `provider.py` as the adapter that stops its shape |
| `repository` | hand-written stores on `sqlite3`, no ORM between the reader and the SQL |
