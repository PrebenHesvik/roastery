"""Tables as text: the dataset.sql format, with headers and no prose (W20)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Final

from roastery.pipeline import Rows
from roastery_spec.contract import TABLES, Table

_DECIMAL: Final = re.compile(r'^DECIMAL\((\d+),(\d+)\)$')
_PIECES: Final = re.compile(r'[^\x00-\x1f\x7f-\xa0]+|[\x00-\x1f\x7f-\xa0]')


def _text(value: str) -> str:
    if not value:
        return "''"
    pieces = []
    for part in _PIECES.findall(value):
        if len(part) == 1 and (ord(part) < 0x20 or 0x7F <= ord(part) <= 0xA0):
            pieces.append(f'chr({ord(part)})')
        else:
            pieces.append("'" + part.replace("'", "''") + "'")
    return ' || '.join(pieces)


def _stamp(value: datetime) -> str:
    if value.tzinfo is not None:
        if value.utcoffset() != timedelta(0):
            raise ValueError(f'timestamp {value!r} has an offset other than UTC')
        value = value.replace(tzinfo=None)
    if value.second or value.microsecond:
        raise ValueError(f'timestamp {value!r} has seconds; tiny stamps are whole minutes')
    return f"TIMESTAMP '{value:%Y-%m-%d %H:%M}'"


def _decimal(value: Decimal, kind: str) -> str:
    found = _DECIMAL.match(kind)
    if found is None:
        raise ValueError(f'unknown decimal type {kind}')
    width, scale = int(found.group(1)), int(found.group(2))
    if not value.is_finite():
        raise ValueError(f'decimal {value!r} is not finite')
    step = Decimal(1).scaleb(-scale)
    fixed = value.quantize(step)
    if fixed != value:
        raise ValueError(f'decimal {value!r} has more than {scale} places')
    text = f'{fixed:f}'
    if len(text.lstrip('-').replace('.', '').lstrip('0') or '0') > width:
        raise ValueError(f'decimal {value!r} does not fit {kind}')
    return text


def _value(value: object, kind: str) -> str:
    if value is None:
        return 'NULL'
    if kind == 'VARCHAR' and isinstance(value, str):
        return _text(value)
    if kind == 'INTEGER' and isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if kind == 'BOOLEAN' and isinstance(value, bool):
        return 'true' if value else 'false'
    if kind == 'DATE' and isinstance(value, date) and not isinstance(value, datetime):
        return f"DATE '{value:%Y-%m-%d}'"
    if kind == 'TIMESTAMP' and isinstance(value, datetime):
        return _stamp(value)
    if kind.startswith('DECIMAL') and isinstance(value, Decimal):
        return _decimal(value, kind)
    raise ValueError(f'{value!r} ({type(value).__name__}) does not fit {kind}')


def _order(row: tuple[object, ...], places: Sequence[int]) -> tuple:
    return tuple((row[i] is not None, row[i]) for i in places)


def _table(rows: Rows, spec: Table) -> list[str]:
    names = tuple(c.name for c in spec.columns)
    if tuple(rows.columns) != names:
        raise ValueError(f'table {rows.name}: columns {tuple(rows.columns)} are not {names}')
    for row in rows.rows:
        if len(row) != len(names):
            raise ValueError(f'table {rows.name}: a row has {len(row)} values, not {len(names)}')
    key = ', '.join(spec.key) or 'none'
    out = [f'-- table: {rows.name} | key: {key} | grain: {spec.grain}']
    out.append(f'CREATE TABLE {rows.name} (')
    out.append(',\n'.join(f'    {c.name} {c.type}' for c in spec.columns))
    out.append(');')
    # The key sorts the rows; the other columns break a tie, so a repeated key is still
    # placed the same way whatever order the rows came in.
    first = [names.index(k) for k in spec.key]
    rest = [i for i in range(len(names)) if i not in first]
    try:
        ordered = sorted(rows.rows, key=lambda r: _order(r, first + rest))
    except TypeError as error:
        raise ValueError(f'table {rows.name}: values do not compare: {error}') from error
    lines = []
    for row in ordered:
        cells = ', '.join(_value(v, c.type) for v, c in zip(row, spec.columns, strict=True))
        lines.append(f'    ({cells})')
    if lines:
        out.append(f'INSERT INTO {rows.name} VALUES')
        out.append(',\n'.join(lines) + ';')
    out.append('')
    return out


def render(tables: Sequence[Rows], *, seed: int) -> str:
    """The tables as dataset text: a preamble, then a header, CREATE TABLE and INSERT each.

    Rows are sorted by the table's key (all columns for a keyless table, None first). A table
    with no rows is written as its CREATE TABLE alone: `VALUES` with no row is not SQL.
    """
    known = {t.name: t for t in TABLES}
    lines = [f'-- roastery-data tiny, written by roastery_sim, seed {seed}', '']
    for rows in tables:
        if rows.name not in known:
            raise ValueError(f'table {rows.name} is not in the contract')
        lines.extend(_table(rows, known[rows.name]))
    # A blank line follows each table but the last: the text ends in one newline.
    return '\n'.join(lines).rstrip('\n') + '\n'
