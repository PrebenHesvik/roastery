"""The export's lines through stages that pull one at a time.

Each stage takes an iterable and yields: live_lines drops the lines
a cancel deleted, as_text turns each into the export's text
columns, to_csv turns the rows into the file's lines. Chained,
nothing runs until the end is asked for an item; then each stage
asks the one before it for one item, so a stop at the end stops the
reading (ADR 0001).
"""

from __future__ import annotations

import csv
import io
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from functools import reduce
from typing import Any, Final

from roastery.ids import LineId, OrderId, ProductId
from roastery.money import Money, Qty

Stage = Callable[[Iterable[Any]], Iterable[Any]]
"""A step of a pipeline: items in, items out."""

LINE_COLUMNS: Final[tuple[str, ...]] = (
    'line_id',
    'order_id',
    'product_id',
    'qty',
    'unit_price',
)
"""The columns of `raw_lines`, in the file's order."""


@dataclass(frozen=True)
class Rows:
    """One table as contract A names it: its columns and rows.

    The values are Python's: str, int, bool, Decimal, date, a UTC
    datetime, or None. The rows keep the order they were given.
    """

    name: str
    columns: tuple[str, ...]
    rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class ExportLine:
    """An order line as the store holds it, with its deletion."""

    line_id: LineId
    order_id: OrderId
    product_id: ProductId
    qty: Qty
    unit_price: Money
    is_deleted: bool


def read(text: Iterable[str]) -> Iterator[dict[str, str]]:
    """A CSV file's lines as rows; the first line names the cells."""
    yield from csv.DictReader(text)


def live_lines(lines: Iterable[ExportLine]) -> Iterator[ExportLine]:
    """Only the lines no cancel deleted."""
    for line in lines:
        if not line.is_deleted:
            yield line


def as_text(
    lines: Iterable[ExportLine],
) -> Iterator[dict[str, str]]:
    """Each line as the export's cells: text, `.` decimals."""
    for line in lines:
        yield {
            'line_id': str(line.line_id),
            'order_id': str(line.order_id),
            'product_id': str(line.product_id),
            'qty': str(line.qty.value),
            'unit_price': f'{line.unit_price.amount:.2f}',
        }


def to_csv(
    rows: Iterable[Mapping[str, str]],
    columns: tuple[str, ...] = LINE_COLUMNS,
) -> Iterator[str]:
    """The header, then each row as a line of the file (with LF)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator='\n')

    def line_of(cells: Iterable[str]) -> str:
        buffer.seek(0)
        buffer.truncate()
        writer.writerow(cells)
        return buffer.getvalue()

    yield line_of(columns)
    for row in rows:
        yield line_of(row[column] for column in columns)


def pipe(source: Iterable[Any], *stages: Stage) -> Iterable[Any]:
    """The source through each stage, in turn: b(a(s)) for a, b.

    It only chains them: with generator stages, nothing runs until
    an item is asked for at the end.
    """
    return reduce(lambda items, stage: stage(items), stages, source)


def line_id_of(
    item: str | Mapping[str, object] | ExportLine,
) -> str:
    """The line an item is about, whichever stage made the item.

    A CSV line gives its first cell, a row its 'line_id' cell, an
    ExportLine its line_id.
    """
    if isinstance(item, str):
        return item.split(',', 1)[0].strip()
    if isinstance(item, Mapping):
        return str(item.get('line_id'))
    return str(item.line_id)


class Trace:
    """Who handled which line, when: a note as a stage takes an item.

    watch(name, stage) is the stage, noting each item as the stage
    takes it from the one before. The notes are numbered in the
    order they were made, so they show the order of the work.
    """

    def __init__(self) -> None:
        self._notes: list[str] = []

    def watch(self, name: str, stage: Stage) -> Stage:
        def watched(items: Iterable[Any]) -> Iterable[Any]:
            return stage(self._taken(name, items))

        return watched

    def _taken(self, name: str, items: Iterable[Any]) -> Iterator[Any]:
        for item in items:
            number = len(self._notes) + 1
            self._notes.append(f'{number} {name} {line_id_of(item)}')
            yield item

    @property
    def notes(self) -> tuple[str, ...]:
        return tuple(self._notes)

    def text(self) -> str:
        return '\n'.join(self._notes)
