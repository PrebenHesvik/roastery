"""A data folder from dataset text: one parquet file per table and `manifest.json`."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import duckdb
from roastery_spec import baseline


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
                '(FORMAT parquet, ROW_GROUP_SIZE 100000)'
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
