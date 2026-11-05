"""The landing ties to the data: what a pipeline reads from the files is month's own rows."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import duckdb
import pytest
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

    # month's raw tables are the 9 October files, the faulted ones, cell for cell
    for name in tiny.RAW:
        rows = tables[name]
        path = (tmp_path / 'csv' / str(landings.FAULTED_NIGHT) / f'{name}.csv').as_posix()
        assert _read(path, rows.columns) == [tuple(row) for row in rows.rows]
    columns = tables['raw_customers'].columns
    customers = _read((tmp_path / 'csv' / '2026-10-09' / 'raw_customers.csv').as_posix(), columns)
    c05 = next(row for row in customers if row[0].strip().upper() == 'C-05')
    assert c05[columns.index('email')] is None
    assert c05[columns.index('country')] == ''


def test_a_file_is_stamped_in_the_manifest(volume: build.PlayedVolume, tmp_path) -> None:
    landings.write(volume, tmp_path)
    loads = json.loads((tmp_path / 'loads.json').read_text(encoding='utf-8'))
    files = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob('*') if p.is_file())
    assert [e['_source_file'] for e in loads] == [f for f in files if f != 'loads.json']


def _rows(text: str) -> list[list[str]]:
    """A csv text's rows, its header left out; every cell as text (a NULL reads as '')."""
    return list(csv.reader(io.StringIO(text, newline='')))[1:]


def _written(value: str) -> str:
    return '' if value == 'NULL' else value


def test_the_loads_give_the_last_nights_state(volume: build.PlayedVolume, tmp_path) -> None:
    """Each raw table's files, loaded by its strategy in `_source_file` order, are the app's
    state of the last night: `raw_lines` appended holds every line once (the five dirty cells
    of 9 October as the log has them); `raw_customers` merged on `customer_id` holds every
    customer as last exported, beside the four rows whose id the writer dirtied (W12)."""
    month = extracts.month(volume.world, volume.played)
    landings.write(volume, tmp_path, month=month)
    loads = json.loads((tmp_path / 'loads.json').read_text(encoding='utf-8'))
    loaded: dict[str, list[list[str]]] = {'raw_lines': [], 'raw_customers': []}
    merged: dict[str, list[str]] = {}
    for entry in sorted(loads, key=lambda e: e['_source_file']):
        table = entry['table_name']
        if table not in loaded:
            continue
        rows = _rows((tmp_path / entry['_source_file']).read_text(encoding='utf-8'))
        assert len(rows) == entry['rows']
        if entry['strategy'] == 'append':
            loaded[table] += rows
        else:
            assert (entry['strategy'], entry['keys']) == ('merge', 'customer_id')
            merged.update({row[0]: row for row in rows})
    loaded['raw_customers'] = list(merged.values())

    last = volume.played.csv_exports[max(volume.played.csv_exports)]
    lines = {row[0]: row for row in _rows(last['raw_lines.csv'])}
    customers = {row[0]: row for row in _rows(last['raw_customers.csv'])}
    columns = {t.name: t.columns for t in month.tables}
    dirty = [d for d in month.defects if d.table in tiny.RAW]
    assert len(dirty) == len(faults.RAW_CUSTOMERS) + len(faults.RAW_LINES)
    for d in dirty:
        if d.table == 'raw_lines':
            at = columns['raw_lines'].index(d.column)
            lines[d.key] = [*lines[d.key][:at], _written(d.written), *lines[d.key][at + 1 :]]
    ids = {
        d.written: d.key for d in dirty if d.table == 'raw_customers' and d.column == 'customer_id'
    }
    assert len(ids) == 4
    held = {row[0]: row for row in loaded['raw_customers']}
    for written, key in ids.items():
        row = held.pop(written)
        for d in dirty:
            if d.table == 'raw_customers' and d.key == key:
                assert row[columns['raw_customers'].index(d.column)] == _written(d.written)

    assert len(loaded['raw_lines']) == len(lines)
    assert sorted(loaded['raw_lines']) == sorted(lines.values())
    assert held == customers


def test_a_landing_is_written_into_a_cleared_folder(
    volume: build.PlayedVolume, tmp_path: Path
) -> None:
    landing = tmp_path / 'landing'
    landings.write(volume, landing, texts={'loads.json': '[]\n', 'feed/a.jsonl': '{}\n'})
    landings.write(volume, landing, texts={'loads.json': '[]\n'})
    assert [p.relative_to(landing).as_posix() for p in landing.rglob('*')] == ['loads.json']
    other = tmp_path / 'other'
    other.mkdir()
    (other / 'keep.txt').write_text('mine', encoding='utf-8')
    with pytest.raises(ValueError, match='not a landing'):
        landings.write(volume, other, texts={'loads.json': '[]\n'})
    assert (other / 'keep.txt').read_text(encoding='utf-8') == 'mine'
