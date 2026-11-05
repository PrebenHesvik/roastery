"""The `month` extract's nightly landings: the raw files each outside system would hand a
pipeline (6.5, V14, V25).

Five shapes, under `landing/`: the status feed as one jsonl file a night, the shop's csv
export a folder a night (the whole customer list, and the lines new since the export before:
`raw_customers` loads by merge, `raw_lines` by append), the new till's csv a file a day from
6 October, the three outside series as one csv each, and `loads.json`, the manifest. A file
holds its rows as the system wrote them and nothing the pipeline adds: `_source_file` and
`_loaded_at` are the pipeline's stamp, and `loads.json` says what each file's stamp is. Every
file is UTF-8 with LF line ends; a key or column order is fixed; no path of the machine is in
any.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import shutil
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Final

from roastery.pipeline import Rows

from roastery_sim import extracts, faults
from roastery_sim.extracts import FAULTED_NIGHT

if TYPE_CHECKING:
    from roastery_sim.build import PlayedVolume

FIRST_NIGHT: Final = dt.date(2026, 10, 1)
LAST_NIGHT: Final = dt.date(2026, 10, 31)
FIRST_TILL_DAY: Final = dt.date(2026, 10, 6)
"""The new till's first day with a file (the plan's shape table)."""
PICKUP: Final = dt.time(2, 0)
"""A night's files are picked up at 02:00 UTC the next day, after the night's jobs (the
nightly run of `pipeline_runs`)."""

# Where each file loads: the columns of the `loads` table of model.sql, then ours.
Strategy = tuple[str, str, str, str]
FEED: Final[Strategy] = ('order_events', 'append', 'event_id', 'loaded_at')
CUSTOMERS: Final[Strategy] = ('raw_customers', 'merge', 'customer_id', '_source_file')
LINES: Final[Strategy] = ('raw_lines', 'append', 'line_id', '_source_file')
TILL: Final[Strategy] = ('till_lines', 'append', 'receipt_id, line_no', '_source_file')
SERIES: Final[Mapping[str, Strategy]] = {
    'weather_days': ('weather_days', 'merge', 'shop_date', '_source_file'),
    'door_counts': ('door_counts', 'merge', 'shop_date', '_source_file'),
    'till_day_totals': ('till_day_totals', 'merge', 'shop_date', '_source_file'),
}

FILE_OF: Final[Mapping[str, str]] = {
    'weather_days': 'weather',
    'door_counts': 'door_counts',
    'till_day_totals': 'till_day_totals',
}
"""The series file of each table."""

FEED_KEYS: Final = ('event_id', 'order_id', 'status', 'event_at', 'loaded_at')
TILL_COLUMNS: Final = (
    'receipt_id',
    'member_no',
    'sold_at',
    'line_no',
    'ean',
    'grams',
    'amount',
)


def _cell(value: object) -> str:
    """A value as a landing writes it: '' for none, a UTC moment `...Z`, a till moment naive."""
    if value is None:
        return ''
    if isinstance(value, dt.datetime):
        if value.tzinfo is None:
            return value.isoformat(sep=' ')
        return value.astimezone(dt.UTC).strftime('%Y-%m-%dT%H:%M:%SZ')
    if isinstance(value, Decimal):
        return f'{value:f}'
    return str(value)


def _csv(columns: Sequence[str], rows: Iterable[Sequence[object]]) -> str:
    out = io.StringIO(newline='')
    writer = csv.writer(out, lineterminator='\n')
    writer.writerow(columns)
    writer.writerows([_cell(v) for v in row] for row in rows)
    return out.getvalue()


def _count(text: str) -> int:
    """The rows of a csv text, its header left out (a quoted newline is not a row)."""
    return len(list(csv.reader(io.StringIO(text, newline='')))) - 1


def _jsonl(rows: Rows) -> dict[dt.date, str]:
    """The feed's events by the UTC day of `loaded_at`, one object a line: a night's file is
    what that day's relays loaded (the last at 23:30 UTC), picked up at PICKUP the next day.
    month's `order_events` is cut by the same day, so the files hold it exactly."""
    at = rows.columns.index('loaded_at')
    nights: dict[dt.date, list[str]] = defaultdict(list)
    for row in rows.rows:
        entry = {key: _cell(row[rows.columns.index(key)]) for key in FEED_KEYS}
        nights[row[at].astimezone(dt.UTC).date()].append(json.dumps(entry, ensure_ascii=False))
    return {night: '\n'.join(lines) + '\n' for night, lines in nights.items()}


def _picked_up(night: dt.date) -> dt.datetime:
    return dt.datetime.combine(night + dt.timedelta(days=1), PICKUP, tzinfo=dt.UTC)


def _till(receipts: Rows, lines: Rows) -> dict[dt.date, tuple[str, int]]:
    """The till's file text and row count by day: a row a line, its receipt's cells first."""
    by_receipt: dict[object, list[Sequence[object]]] = defaultdict(list)
    for line in lines.rows:
        by_receipt[line[lines.columns.index('receipt_id')]].append(line)
    days: dict[dt.date, list[Sequence[object]]] = defaultdict(list)
    ids, member, sold = (receipts.columns.index(c) for c in ('receipt_id', 'member_no', 'sold_at'))
    no, ean, grams, amount = (lines.columns.index(c) for c in ('line_no', 'ean', 'grams', 'amount'))
    for receipt in sorted(receipts.rows, key=lambda r: (r[sold], r[ids])):
        day = receipt[sold].date()
        if day < FIRST_TILL_DAY:
            continue
        for line in sorted(by_receipt[receipt[ids]], key=lambda r: r[no]):
            days[day].append(
                (
                    receipt[ids],
                    receipt[member],
                    receipt[sold],
                    line[no],
                    line[ean],
                    line[grams],
                    line[amount],
                )
            )
    return {day: (_csv(TILL_COLUMNS, rows), len(rows)) for day, rows in days.items()}


def _entry(file: str, strategy: Strategy, loaded: dt.datetime, rows: int) -> dict[str, str | int]:
    table, how, keys, watermark = strategy
    return {
        'table_name': table,
        'strategy': how,
        'keys': keys,
        'watermark_column': watermark,
        '_source_file': file,
        '_loaded_at': loaded.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'rows': rows,
    }


def files(
    volume: PlayedVolume,
    month: extracts.Written | None = None,
    *,
    nightly: Mapping[dt.date, Mapping[str, str]] | None = None,
) -> dict[str, str]:
    """The landing for 1 to 31 October 2026: each file's text by its path under `landing/`,
    `loads.json` with them. `month` is the extract and `nightly` the csv exports
    (`extracts.exports`) if the caller has them already."""
    played = volume.played
    nightly = extracts.exports(played) if nightly is None else nightly
    held = month or extracts.month(volume.world, played, nightly=nightly)
    tables = {rows.name: rows for rows in held.tables}
    files: dict[str, str] = {}
    entries: list[dict[str, str | int]] = []

    def add(file: str, text: str, strategy: Strategy, loaded: dt.datetime, rows: int) -> None:
        files[file] = text
        entries.append(_entry(file, strategy, loaded, rows))

    month_ends = _picked_up(LAST_NIGHT)

    # the status feed: what each night's relays loaded, every event of month's order_events
    feed = _jsonl(tables['order_events'])
    outside = sorted(n for n in feed if not FIRST_NIGHT <= n <= LAST_NIGHT)
    if outside:
        raise ValueError(f'order_events loaded outside October: {outside[:3]}')
    for night in sorted(feed):
        count = feed[night].count('\n')
        add(f'feed/{night}.jsonl', feed[night], FEED, _picked_up(night), count)

    # the shop's csv export: the 9 October one with the writer's faults (month's raw tables),
    # the rest as written
    for night, export in sorted(nightly.items()):
        if not FIRST_NIGHT <= night <= LAST_NIGHT:
            continue
        for name, strategy in (('raw_customers', CUSTOMERS), ('raw_lines', LINES)):
            if night == FAULTED_NIGHT:
                text = faults.csv_text(tables[name])
            else:
                text = export[f'{name}.csv']
            add(f'csv/{night}/{name}.csv', text, strategy, _picked_up(night), _count(text))

    # the new till, a file a day
    for day, (text, count) in sorted(_till(tables['till_receipts'], tables['till_lines']).items()):
        if day <= LAST_NIGHT:
            add(f'till/{day}.csv', text, TILL, _picked_up(day), count)

    # the three series, whole October, picked up after the last night
    for name, strategy in SERIES.items():
        rows = tables[name]
        text = _csv(rows.columns, sorted(rows.rows, key=lambda r: r[0]))
        add(f'series/{FILE_OF[name]}.csv', text, strategy, month_ends, len(rows.rows))

    entries.sort(key=lambda e: str(e['_source_file']))
    files['loads.json'] = json.dumps(entries, indent=2, ensure_ascii=False) + '\n'
    return dict(sorted(files.items()))


def sha256(texts: Mapping[str, str]) -> dict[str, str]:
    """Each file's sha256 by its path, as `write` puts its bytes on disk."""
    return {file: hashlib.sha256(text.encode('utf-8')).hexdigest() for file, text in texts.items()}


def _clear(out: Path) -> None:
    """`out` emptied of an earlier landing; a folder holding something else is refused."""
    if not out.exists():
        return
    if any(out.iterdir()) and not (out / 'loads.json').is_file():
        raise ValueError(f'{out.name}: not a landing (no loads.json), so not cleared')
    shutil.rmtree(out)


def write(
    volume: PlayedVolume,
    out: Path,
    *,
    month: extracts.Written | None = None,
    texts: Mapping[str, str] | None = None,
) -> tuple[Path, ...]:
    """The landing under `out`, cleared first; the files written, sorted.

    `month` is the extract and `texts` the landing's files if the caller has them already.
    """
    texts = texts if texts is not None else files(volume, month)
    _clear(out)
    written = []
    for file in sorted(texts):
        path = out / file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(texts[file].encode('utf-8'))
        written.append(path)
    return tuple(written)
