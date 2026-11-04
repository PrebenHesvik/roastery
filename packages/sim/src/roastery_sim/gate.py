"""The gate: two dataset texts compared cell for cell, table by table (6.4, W13).

Both texts are loaded into one DuckDB, each in its own attached database, with the grammar of
`roastery_spec.baseline`. A table differs by its presence, its columns (names and types, as
`DESCRIBE` prints them), its row count or its rows, compared as multisets with `EXCEPT ALL`
both ways: a row given twice must be there twice. The order of the rows in the text is not
compared.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from typing import Final

import duckdb
from roastery_spec import baseline

SIDES: Final = ('mine', 'theirs')
SHOWN: Final = 3
"""How many differing rows a difference names: the first few, in `ORDER BY ALL` order."""


@dataclass(frozen=True, order=True)
class Difference:
    """One way two texts differ: the table, what differs, and a short detail."""

    table: str
    what: str
    detail: str


def _load(con: duckdb.DuckDBPyConnection, side: str, text: str) -> list[str]:
    """The text's tables, made in the attached database `side`; their names in text order."""
    con.execute(f"ATTACH ':memory:' AS {side}")
    con.execute(f'USE {side}')
    found = baseline.tables(text)
    baseline.database(found, con=con)
    return [t['name'] for t in found]


def _one(con: duckdb.DuckDBPyConnection, sql: str) -> int:
    row = con.execute(sql).fetchone()
    if row is None:
        raise ValueError(f'no row from {sql}')
    return row[0]


def _columns(con: duckdb.DuckDBPyConnection, side: str, name: str) -> list[tuple[str, str]]:
    return [(row[0], row[1]) for row in con.execute(f'DESCRIBE {side}.{name}').fetchall()]


def _rows(con: duckdb.DuckDBPyConnection, name: str) -> list[Difference]:
    """The rows one side holds more often than the other, each way."""
    out = []
    for one, two in (SIDES, SIDES[::-1]):
        only = f'SELECT * FROM {one}.{name} EXCEPT ALL SELECT * FROM {two}.{name}'
        n = _one(con, f'SELECT count(*) FROM ({only})')
        if n:
            first = con.execute(f'SELECT * FROM ({only}) ORDER BY ALL LIMIT {SHOWN}').fetchall()
            shown = ', '.join(repr(row) for row in first)
            more = f', and {n - len(first)} more' if n > len(first) else ''
            out.append(Difference(name, f'rows only in {one}', f'{n}: {shown}{more}'))
    return out


def differences(
    mine: str, theirs: str, *, tables: Collection[str] | None = None
) -> list[Difference]:
    """How `mine` differs from `theirs`, sorted; [] when every table is equal.

    With `tables`, only the tables named are compared, and a name missing from a side is a
    difference. Without it, every table either text holds is.
    """
    con = duckdb.connect()
    try:
        con.execute("SET TimeZone = 'UTC'")
        names = dict(
            zip(SIDES, (_load(con, 'mine', mine), _load(con, 'theirs', theirs)), strict=True)
        )
        wanted = set(tables) if tables is not None else set(names['mine']) | set(names['theirs'])
        out: list[Difference] = []
        for name in sorted(wanted):
            absent = [side for side in SIDES if name not in names[side]]
            if absent:
                out += [Difference(name, 'table', f'not in {side}') for side in absent]
                continue
            columns = {side: _columns(con, side, name) for side in SIDES}
            if columns['mine'] != columns['theirs']:
                differ = [
                    f'{a} / {b}'
                    for a, b in zip(columns['mine'], columns['theirs'], strict=False)
                    if a != b
                ]
                counts = f'{len(columns["mine"])} / {len(columns["theirs"])} columns'
                out.append(Difference(name, 'columns', '; '.join([counts, *differ[:SHOWN]])))
                continue
            count = {side: _one(con, f'SELECT count(*) FROM {side}.{name}') for side in SIDES}
            if count['mine'] != count['theirs']:
                out.append(Difference(name, 'count', f'{count["mine"]} / {count["theirs"]}'))
            out += _rows(con, name)
        return sorted(out)
    finally:
        con.close()
