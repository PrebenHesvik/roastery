"""A data folder: one parquet file per table and `manifest.json`.

`write` builds tiny's from its dataset text; `write_rows` builds month's and full's straight
from `Rows` (W37).
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import tempfile
from collections.abc import Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Final

import duckdb
from roastery.pipeline import Rows
from roastery_spec import baseline, contract


def write(
    text: str,
    out: Path,
    *,
    extract: str,
    seed: int,
    until: str | None = None,
    defects: Sequence[Mapping[str, str]],
    shop_version: str,
) -> dict:
    """Build the folder and return its manifest.

    The settings are those of `roastery_spec.baseline.build`: one thread, a fixed row group size,
    rows ordered by key. `until` is None for a whole play, else the ISO moment it stopped at.
    The manifest keeps a fixed key order, with `sha256` sorted by file name.
    """
    found = baseline.tables(text)
    con = duckdb.connect()
    con.execute('SET threads = 1')
    con.execute('SET preserve_insertion_order = true')
    try:
        baseline.database(found, con=con)
        out.mkdir(parents=True, exist_ok=True)
        for stale in out.glob('*.parquet'):
            stale.unlink()
        counts: dict[str, int] = {}
        hashes: dict[str, str] = {}
        for table in found:
            name = table['name']
            order = 'ALL' if table['key'] == ['none'] else ', '.join(table['key'])
            target = out / f'{name}.parquet'
            con.execute(
                f"COPY (SELECT * FROM {name} ORDER BY {order}) TO '{target.as_posix()}' "
                f'(FORMAT parquet, ROW_GROUP_SIZE {ROW_GROUP_SIZE})'
            )
            row = con.execute(f'SELECT count(*) FROM {name}').fetchone()
            counts[name] = row[0] if row else 0
            hashes[target.name] = hashlib.sha256(target.read_bytes()).hexdigest()
    finally:
        con.close()
    manifest = {
        'extract': extract,
        'serves': [extract],
        'tables': counts,
        'sha256': dict(sorted(hashes.items())),
        'seed': seed,
        'until': until,
        'shop': shop_version,
        'defects': [dict(d) for d in defects],
    }
    (out / 'manifest.json').write_bytes((json.dumps(manifest, indent=2) + '\n').encode('utf-8'))
    return manifest


ROW_GROUP_SIZE: Final = 100_000
PACKAGES: Final = ('roastery', 'roastery-sim', 'roastery-spec')
"""The workspace's packages whose versions a volume manifest names, in this order."""


def _type_of(name: str, column: str) -> str:
    """A column's DuckDB type as contract A gives it; `source` is text."""
    if column == 'source':
        return 'VARCHAR'
    spec = contract.by_name()[name]
    for each in (*spec.columns, *spec.added):
        if each.name == column:
            return each.type
    raise ValueError(f'{name}.{column} is not in contract A')


def _cell(value: object, kind: str, where: str) -> str | None:
    """A value as the csv text DuckDB reads back exactly; its Python type must be the column's.

    A moment is UTC (written naive, seconds kept) or naive shop time (the till's); a decimal
    with more places than its scale is refused, never rounded.
    """
    if value is None:
        return None
    if kind == 'VARCHAR' and isinstance(value, str):
        return value
    if kind == 'BOOLEAN' and isinstance(value, bool):
        return 'true' if value else 'false'
    if kind == 'INTEGER' and isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if kind == 'TIMESTAMP' and isinstance(value, dt.datetime):
        if value.tzinfo is not None:
            if value.utcoffset() != dt.timedelta(0):
                raise ValueError(f'{where}: moment {value!r} is not in UTC')
            value = value.replace(tzinfo=None)
        return value.isoformat(sep=' ')
    if kind == 'DATE' and isinstance(value, dt.date) and not isinstance(value, dt.datetime):
        return value.isoformat()
    if kind.startswith('DECIMAL') and isinstance(value, Decimal):
        scale = int(kind.rstrip(')').split(',')[1])
        exponent = value.as_tuple().exponent
        if not isinstance(exponent, int) or exponent < -scale:
            raise ValueError(f'{where}: {value!r} has more places than {kind}')
        return f'{value:f}'
    raise TypeError(f'{where}: {value!r} is no {kind}')


def _load(con: duckdb.DuckDBPyConnection, rows: Rows, scratch: Path) -> None:
    """The rows as a table typed as contract A types them, through a csv file: a NULL is a
    bare empty field, '' a quoted one, so the text cells come back as they went."""
    kinds = [_type_of(rows.name, c) for c in rows.columns]
    path = scratch / f'{rows.name}.csv'
    with path.open('w', encoding='utf-8', newline='') as file:
        writer = csv.writer(file, quoting=csv.QUOTE_NOTNULL, lineterminator='\n')
        writer.writerow(rows.columns)
        for n, row in enumerate(rows.rows):
            where = f'{rows.name} row {n}'
            writer.writerow([_cell(v, k, where) for v, k in zip(row, kinds, strict=True)])
    columns = ', '.join(f"'{c}': '{k}'" for c, k in zip(rows.columns, kinds, strict=True))
    con.execute(
        f"CREATE TABLE {rows.name} AS SELECT * FROM read_csv('{path.as_posix()}', "
        f'header = true, auto_detect = false, columns = {{{columns}}}, '
        "delim = ',', quote = '\"', escape = '\"', allow_quoted_nulls = false)"
    )


def write_rows(
    tables: Sequence[Rows],
    out: Path,
    *,
    extract: str,
    seed: int,
    version: str,
    packages: Mapping[str, str],
    defects: Sequence[Mapping[str, str]],
    scripted_events: Mapping[str, object],
    landing: Mapping[str, str] | None = None,
) -> dict:
    """The data folder of `month` or `full` straight from `Rows` (W37); its manifest.

    The settings are `write`'s: UTC, one thread, a fixed row group size, rows ordered by
    contract A's key (a keyless table by all its columns). The manifest (plan §4.4, §5) keeps a
    fixed key order: `write`'s keys with the data `version` after `serves` and `until` null;
    then the versions of the three `packages` (`shop` is roastery's), DuckDB's, and the
    sha256 of the baseline's two files from PROVENANCE.toml; then the defects,
    `scripted_events`, and, for month, `landing`: every landing file's sha256 by its path.
    """
    if set(packages) != set(PACKAGES):
        raise ValueError(f'the package versions name {sorted(packages)}, not {list(PACKAGES)}')
    origin = baseline.provenance()
    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    con.execute('SET threads = 1')
    con.execute('SET preserve_insertion_order = true')
    try:
        out.mkdir(parents=True, exist_ok=True)
        for stale in out.glob('*.parquet'):
            stale.unlink()
        counts: dict[str, int] = {}
        hashes: dict[str, str] = {}
        with tempfile.TemporaryDirectory() as scratch:
            for rows in tables:
                if rows.name in counts:
                    raise ValueError(f'table {rows.name} is given twice')
                _load(con, rows, Path(scratch))
                key = contract.by_name()[rows.name].key
                order = ', '.join(key) if key else 'ALL'
                target = out / f'{rows.name}.parquet'
                con.execute(
                    f"COPY (SELECT * FROM {rows.name} ORDER BY {order}) TO '{target.as_posix()}' "
                    f'(FORMAT parquet, ROW_GROUP_SIZE {ROW_GROUP_SIZE})'
                )
                counts[rows.name] = len(rows.rows)
                hashes[target.name] = hashlib.sha256(target.read_bytes()).hexdigest()
    finally:
        con.close()
    manifest = {
        'extract': extract,
        'serves': [extract],
        'version': version,
        'tables': counts,
        'sha256': dict(sorted(hashes.items())),
        'seed': seed,
        'until': None,
        'shop': packages['roastery'],
        'packages': {name: packages[name] for name in PACKAGES},
        'duckdb': duckdb.__version__,
        'baseline': {
            'dataset.sql': origin['dataset_sql']['sha256'],
            'tier3.sql': origin['tier3_sql']['sha256'],
        },
        'defects': [dict(d) for d in defects],
        'scripted_events': dict(scripted_events),
    }
    if landing is not None:
        manifest['landing'] = dict(sorted(landing.items()))
    (out / 'manifest.json').write_bytes((json.dumps(manifest, indent=2) + '\n').encode('utf-8'))
    return manifest
