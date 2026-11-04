"""Claims: a test that names the extract it runs on and the tables it needs (6.1 S6).

A claim whose tables are not in its extract's data folder is not skipped: the plugin in
`tests/conftest_claims.py` deselects it and lists it under "awaiting data". A need is a table
name (`shipments`) or a table and a column (`customers.kind`), for the columns 1.0 adds.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import TypeVar

import duckdb

from roastery_spec import baseline
from roastery_spec.contract import TABLES, Extract

F = TypeVar('F', bound=Callable)

ATTRIBUTE = 'roastery_claim'


@dataclass(frozen=True)
class Claim:
    """The extract a claim runs on, and the tables (or table.column) it reads."""

    extract: Extract
    tables: tuple[str, ...]


def claim(extract: Extract, tables: Iterable[str]) -> Callable[[F], F]:
    """Mark a test as a claim on `extract` that reads `tables`."""
    needs = tuple(tables)
    if extract not in ('tiny', 'month', 'full'):
        raise ValueError(f'unknown extract: {extract}')
    if not needs:
        raise ValueError('a claim names at least one table')

    def mark(test: F) -> F:
        setattr(test, ATTRIBUTE, Claim(extract, needs))
        return test

    return mark


def claim_of(test: object) -> Claim | None:
    """The claim a test carries, or None."""
    found = getattr(test, ATTRIBUTE, None)
    return found if isinstance(found, Claim) else None


def _baseline_names() -> set[str]:
    here = resources.files('roastery_spec') / 'baseline'
    names: set[str] = set()
    for file in ('dataset.sql', 'tier3.sql'):
        text = (here / file).read_text(encoding='utf-8')
        names.update(table['name'] for table in baseline.tables(text))
    return names


def _parquet_columns(folder: Path, table: str) -> set[str]:
    path = (folder / f'{table}.parquet').as_posix()
    con = duckdb.connect()
    try:
        rows = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{path}')").fetchall()
    finally:
        con.close()
    return {row[0] for row in rows}


def awaiting(needs: Iterable[str], folder: Path | None) -> tuple[str, ...]:
    """The needs a data folder does not hold, sorted; `folder` None is the baseline.

    A folder's tables are its manifest's; a column is read from the table's parquet file. The
    baseline is not built for this: its tables are the headers of its two `.sql` files and its
    columns are the contract's `columns` (never `added`, which only 1.0 data carries).
    """
    if folder is None:
        names = _baseline_names()
        columns = {t.name: {c.name for c in t.columns} for t in TABLES if t.name in names}
    else:
        manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
        names = set(manifest['tables'])
        columns = {}
    missing = []
    for need in needs:
        table, _, column = need.partition('.')
        if table not in names:
            missing.append(need)
        elif column:
            if table not in columns:
                columns[table] = _parquet_columns(folder, table) if folder else set()
            if column not in columns[table]:
                missing.append(need)
    return tuple(sorted(missing))
