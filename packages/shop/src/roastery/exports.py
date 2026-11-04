"""The csv export and the customer extract, read through the ports.

The export is the shop's own output: `raw_customers` and `raw_lines`
as clean text (ISO dates, `.` decimals, an empty cell for a value the
app does not hold). The export writer of the simulator adds the
faults after it (D10). Each file is written through `pipeline`'s
stages, lazily, from what the unit of work's repositories list; no
store is touched directly (ADR 0001, ADR 0003).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator, Mapping
from typing import Final

from roastery.customer import Customer
from roastery.pipeline import as_text, live_lines, pipe, to_csv
from roastery.ports import ExtractRow, UnitOfWork

CUSTOMER_COLUMNS: Final[tuple[str, ...]] = (
    'customer_id',
    'name',
    'country',
    'postal_code',
    'joined',
    'email',
)
"""The columns of `raw_customers`, in the file's order."""

CUSTOMERS_FILE: Final = 'raw_customers.csv'
LINES_FILE: Final = 'raw_lines.csv'


def customer_cells(customer: Customer) -> dict[str, str]:
    """A customer as the export's text; a missing value is ''."""
    return {
        'customer_id': str(customer.customer_id),
        'name': customer.name,
        'country': customer.country or '',
        'postal_code': str(customer.postal_code or ''),
        'joined': customer.joined.isoformat(),
        'email': str(customer.email or ''),
    }


def _customers_who_ordered(uow: UnitOfWork) -> Iterator[Customer]:
    """The customers with an order, sorted by customer id."""
    ordered = {order.head.customer_id for order in uow.orders.all()}
    for customer in uow.customers.all():
        if customer.customer_id in ordered:
            yield customer


def raw_customers(uow: UnitOfWork) -> str:
    """The text of `raw_customers`: customers who have ordered."""
    rows = (customer_cells(c) for c in _customers_who_ordered(uow))
    return ''.join(to_csv(rows, CUSTOMER_COLUMNS))


def raw_lines(uow: UnitOfWork) -> str:
    """The text of `raw_lines`: the lines no cancel deleted."""
    lines = pipe(uow.orders.lines(), live_lines, as_text, to_csv)
    return ''.join(lines)


def csv_export(uow: UnitOfWork) -> Mapping[str, str]:
    """Both files as file name to text, read in one unit of work."""
    with uow:
        return {
            CUSTOMERS_FILE: raw_customers(uow),
            LINES_FILE: raw_lines(uow),
        }


def nightly_extract(uow: UnitOfWork, day: dt.date) -> int:
    """Make every customer's country and postal code the copy of
    `day`, replacing an earlier copy of it. The rows written.

    The day is the shop's today, which the caller works out from
    the clock (A17); a run twice gives the same rows.
    """
    with uow:
        rows = tuple(
            ExtractRow(
                day,
                customer.customer_id,
                customer.country,
                customer.postal_code,
            )
            for customer in uow.customers.all()
        )
        uow.extracts.replace(day, rows)
        uow.commit()
    return len(rows)
