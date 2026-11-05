"""The landing ties to the data: what a pipeline reads from the files is month's own rows."""

from __future__ import annotations

import dataclasses
import json

import duckdb
from roastery_sim import build, extracts, faults, landings, tiny


def _read(path: str, columns: tuple[str, ...]) -> list[tuple[object, ...]]:
    """A landing csv as a pipeline reads it: all text, a quoted empty field stays ''."""
    con = duckdb.connect()
    found = con.execute(
        f"SELECT * FROM read_csv('{path}', all_varchar = true, header = true, "
        'allow_quoted_nulls = false)'
    )
    assert tuple(d[0] for d in found.description) == columns
    return found.fetchall()


def test_the_landing_is_the_months_rows(volume: build.PlayedVolume, tmp_path) -> None:
    month = extracts.month(volume.world, volume.played)
    landings.write(volume, tmp_path, month=month)
    tables = {rows.name: rows for rows in month.tables}

    events = tables['order_events']
    fed = [
        json.loads(line)
        for path in sorted((tmp_path / 'feed').iterdir())
        for line in path.read_text(encoding='utf-8').splitlines()
    ]
    expected = {
        row[0]: dict(zip(landings.FEED_KEYS, (landings._cell(v) for v in row), strict=True))
        for row in events.rows
    }
    assert {e['event_id']: e for e in fed} == expected
    assert len(fed) == len(expected)

    export = volume.played.csv_exports[landings.FAULTED_NIGHT]
    faulted, _ = faults.apply(tiny.inputs(dataclasses.replace(volume.played, csv=export)))
    for name in tiny.RAW:
        rows = faulted[name]
        path = (tmp_path / 'csv' / str(landings.FAULTED_NIGHT) / f'{name}.csv').as_posix()
        assert _read(path, rows.columns) == [tuple(row) for row in rows.rows]
    customers = _read(
        (tmp_path / 'csv' / '2026-10-09' / 'raw_customers.csv').as_posix(),
        faulted['raw_customers'].columns,
    )
    c05 = next(row for row in customers if row[0].strip().upper() == 'C-05')
    assert c05[faulted['raw_customers'].columns.index('email')] is None
    assert c05[faulted['raw_customers'].columns.index('country')] == ''


def test_a_file_is_stamped_in_the_manifest(volume: build.PlayedVolume, tmp_path) -> None:
    landings.write(volume, tmp_path)
    loads = json.loads((tmp_path / 'loads.json').read_text(encoding='utf-8'))
    files = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob('*') if p.is_file())
    assert [e['_source_file'] for e in loads] == [f for f in files if f != 'loads.json']
