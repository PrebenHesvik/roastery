"""The baseline: data-docs' dataset files, frozen here, built into a data folder."""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from importlib import resources
from pathlib import Path

import duckdb

_HERE = resources.files('roastery_spec') / 'baseline'
_TABLE = re.compile(r'^--\s*table:\s*(\w+)\s*\|\s*key:\s*([\w, ]+?)\s*\|\s*grain:\s*(.+?)\s*$')


def tables(text: str) -> list[dict]:
    """The tables of a dataset file: name, key, grain and the statements that make each."""
    found: list[dict] = []
    for line in text.splitlines():
        head = _TABLE.match(line)
        if head:
            name, key, grain = head.groups()
            found.append(
                {
                    'name': name,
                    'key': [k.strip() for k in key.split(',')],
                    'grain': grain,
                    'sql': [],
                }
            )
        elif found:
            found[-1]['sql'].append(line)
    return found


def database(
    found: list[dict], reverse: bool = False, con: duckdb.DuckDBPyConnection | None = None
) -> duckdb.DuckDBPyConnection:
    """A database holding the tables; `reverse` fills each one last row first.

    A new in-memory database is made unless `con` is given, which then gets the tables.
    """
    con = con or duckdb.connect()
    for table in found:
        con.execute('\n'.join(table['sql']))
        if reverse:
            name = table['name']
            con.execute(f'CREATE TABLE _reversed AS SELECT * FROM {name} ORDER BY rowid DESC')
            con.execute(f'DROP TABLE {name}')
            con.execute(f'ALTER TABLE _reversed RENAME TO {name}')
    return con


def _text(name: str) -> str:
    return (_HERE / name).read_text(encoding='utf-8')


def provenance() -> dict:
    """What PROVENANCE.toml records."""
    return tomllib.loads(_text('PROVENANCE.toml'))


def build(out: Path) -> dict[str, int]:
    """Build the baseline into a data folder: one parquet file per table and `manifest.json`.

    Any `*.parquet` already in `out` is removed first. Returns each table's row count, in file
    order (dataset.sql, then tier3.sql).
    """
    # One thread and a fixed row group size keep the parquet bytes the same on every run.
    con = duckdb.connect()
    con.execute('SET threads = 1')
    con.execute('SET preserve_insertion_order = true')
    try:
        found = tables(_text('dataset.sql'))
        database(found, con=con)
        later = tables(_text('tier3.sql'))
        database(later, con=con)
        out.mkdir(parents=True, exist_ok=True)
        for stale in out.glob('*.parquet'):
            stale.unlink()
        counts: dict[str, int] = {}
        hashes: dict[str, str] = {}
        for table in found + later:
            name = table['name']
            order = 'ALL' if table['key'] == ['none'] else ', '.join(table['key'])
            target = out / f'{name}.parquet'
            con.execute(
                f"COPY (SELECT * FROM {name} ORDER BY {order}) TO '{target.as_posix()}' "
                '(FORMAT parquet, ROW_GROUP_SIZE 100000)'
            )
            row = con.execute(f'SELECT count(*) FROM {name}').fetchone()
            counts[name] = row[0] if row else 0
            hashes[target.name] = hashlib.sha256(target.read_bytes()).hexdigest()
    finally:
        con.close()
    origin = provenance()
    manifest = {
        'extract': 'baseline',
        'serves': ['tiny', 'month', 'full'],
        'tables': counts,
        'sha256': dict(sorted(hashes.items())),
        'baseline': {
            'commit': origin['commit'],
            'dataset_sql_sha256': origin['dataset_sql']['sha256'],
            'tier3_sql_sha256': origin['tier3_sql']['sha256'],
        },
    }
    # Not sort_keys: `tables` keeps the file order; `sha256` is sorted above.
    (out / 'manifest.json').write_bytes((json.dumps(manifest, indent=2) + '\n').encode('utf-8'))
    return counts
