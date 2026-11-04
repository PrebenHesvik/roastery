"""The till's rows parsed once, at the edge: a sale, or a reason.

A parsed line is a type of its own, so the code after the parser
takes a ParsedLine and checks nothing again: its product is one the
shop lists, its amount is Money, its moment is UTC (ADR 0012).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from roastery.ids import ProductId
from roastery.money import Money
from roastery.result import Err, Ok

CURRENCY = 'NOK'
"""The till rings kroner: the shop in Bergen."""


@dataclass(frozen=True)
class ParsedLine:
    receipt_id: str
    line_no: int
    product_id: ProductId
    grams: int | None  # loose beans only
    amount: Money
    sold_at: dt.datetime  # UTC, from Bergen time


@dataclass(frozen=True)
class Reject:
    """A till line that did not parse, and the first reason why."""

    receipt_id: str
    line_no: str  # as the file has it
    reason: str


type Parsed[T] = tuple[Ok[T] | Err[Reject], ...]
"""What a parser gives: one answer per row, in the rows' order."""


def _moment(text: str, shop_zone: ZoneInfo) -> dt.datetime:
    """Bergen time as UTC; a moment with its own offset is refused."""
    moment = dt.datetime.fromisoformat(text)
    if moment.tzinfo is not None:
        raise ValueError('sold_at must be local time, no offset')
    return moment.replace(tzinfo=shop_zone).astimezone(dt.UTC)


def _line(
    row: Mapping[str, str],
    sold: Mapping[str, dt.datetime],
    codes: Mapping[str, ProductId | None],
) -> ParsedLine:
    """One till line, or ValueError naming the first thing wrong."""
    receipt_id = row.get('receipt_id', '')
    if receipt_id not in sold:
        raise ValueError(f'no receipt {receipt_id!r}')
    line_no = int(row.get('line_no', ''))
    ean = row.get('ean', '')
    if ean not in codes:
        raise ValueError(f'code {ean} is not a till code')
    product_id = codes[ean]
    if product_id is None:
        raise ValueError(f'code {ean} has no product')
    grams_text = row.get('grams', '')
    grams = int(grams_text) if grams_text else None
    if grams is not None and grams <= 0:
        raise ValueError('grams must be above zero')
    try:
        amount = Money(Decimal(row.get('amount', '')), CURRENCY)
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f'amount: {error}') from error
    return ParsedLine(
        receipt_id, line_no, product_id, grams, amount, sold[receipt_id]
    )


def parse_till(
    receipts: Iterable[Mapping[str, str]],
    lines: Iterable[Mapping[str, str]],
    codes: Mapping[str, ProductId | None],
    shop_zone: ZoneInfo,
) -> Parsed[ParsedLine]:
    """Every till line, a sale or a Reject; rows keep order."""
    sold: dict[str, dt.datetime] = {}
    for receipt in receipts:
        try:
            sold[receipt['receipt_id']] = _moment(
                receipt['sold_at'], shop_zone
            )
        except (KeyError, ValueError):
            continue  # its lines are rejected: no receipt
    answers: list[Ok[ParsedLine] | Err[Reject]] = []
    for row in lines:
        try:
            answers.append(Ok(_line(row, sold, codes)))
        except ValueError as error:
            reject = Reject(
                row.get('receipt_id', ''),
                row.get('line_no', ''),
                str(error),
            )
            answers.append(Err(reject))
    return tuple(answers)
