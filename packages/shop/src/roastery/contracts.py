"""The promises of the stores, as checks any store can be run by.

Run the same suites on the memory store and on sqlite: when both
give the same rows, all passed, a test that uses the memory store
tells the truth about sqlite (ADR 0015). Each check gets a new,
empty store from `make`: a unit of work that is not yet open, which
the check enters with `with` as many times as it needs.

A store keeps what it is given and refuses what it is told to
refuse. It does not look for a customer behind an order or a
product behind a movement: the services do that. A taken id raises
`DuplicateId` and a missing one `UnknownId`, naming the kind
('order', 'customer', ...) and the id as text.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Final

from roastery.catalogue import (
    BeanDetails,
    Category,
    EquipmentDetails,
    Product,
)
from roastery.commands import Skip
from roastery.customer import Customer, Email
from roastery.errors import DuplicateId, ShopError, UnknownId
from roastery.events import StatusChanged
from roastery.ids import (
    BagId,
    CampaignId,
    CategoryId,
    Country,
    CustomerId,
    EventId,
    LineId,
    MovementId,
    OrderId,
    PaymentId,
    PostalCode,
    ProductId,
    PurchaseId,
    RuleId,
    ShipmentId,
    SubEventId,
    SubscriptionId,
)
from roastery.money import Money
from roastery.order import (
    Head,
    Order,
    OrderLine,
    Placed,
    cancel,
    deliver,
    invoice,
    pay,
    ship,
)
from roastery.ports import (
    BagShipment,
    Booking,
    Campaign,
    Cost,
    Count,
    ExtractRow,
    GreenPurchase,
    Movement,
    MovementReason,
    Shipment,
    UnitOfWork,
)
from roastery.pricing import Discount, Price
from roastery.subscription import Subscription


@dataclass(frozen=True)
class Check:
    """One promise, whether the store kept it, and what it did."""

    name: str
    passed: bool
    detail: str


class Broken(AssertionError):
    """The store did something the port does not promise."""


type Run = Callable[[UnitOfWork], str]
"""One check: given a store, it returns what it saw, or raises."""


# What the checks write ------------------------------------------


def _moment(
    day: int = 5, hour: int = 9, minute: int = 0
) -> dt.datetime:
    """A moment of the frozen week, in UTC."""
    return dt.datetime(2026, 10, day, hour, minute, tzinfo=dt.UTC)


def _customer(
    number: int,
    *,
    country: Country | None = 'NO',
    postal_code: str | None = '7010',
    email: bool = True,
) -> Customer:
    return Customer(
        CustomerId(f'C-{number:02d}'),
        f'Customer {number}',
        Email(f'c{number:02d}@example.invalid') if email else None,
        country,
        None if postal_code is None else PostalCode(postal_code),
        'consumer',
        dt.date(2024, 4, 1),
    )


def _order(order_id: str, *line_ids: str) -> Placed:
    """A web order of C-01: the first line is 2 bags of P-10 at
    129.00, each other line a P-20 at 899.00."""
    lines = tuple(
        OrderLine.of(
            line_id=line_id,
            product_id='P-20' if number else 'P-10',
            qty=1 if number else 2,
            unit_price='899.00' if number else '129.00',
        )
        for number, line_id in enumerate(line_ids)
    )
    head = Head(
        OrderId(order_id), CustomerId('C-01'), 'web', 'NO', lines, None
    )
    return Placed(head)


def _credit(order_id: str, line_id: str, of: Order) -> Placed:
    """The credit order that hands back the first line of `of`."""
    line = of.head.lines[0].credit(LineId(line_id))
    head = Head(
        OrderId(order_id),
        of.head.customer_id,
        'shop',
        of.head.country,
        (line,),
        of.head.order_id,
    )
    return Placed(head)


def _booking(day: int = 5) -> Booking:
    return Booking(
        dt.date(2026, 10, day),
        Money.of('231.40', 'NOK'),
        _moment(day, 21, 50),
    )


def _event(number: int) -> StatusChanged:
    return StatusChanged(
        EventId(f'E-{number:02d}'),
        OrderId('O-101'),
        'placed',
        _moment(5, 8, number),
    )


def _movement(
    number: int,
    product: str,
    reason: MovementReason,
    qty: int,
    when: dt.datetime,
) -> Movement:
    return Movement(
        MovementId(f'M-{number}'), ProductId(product), when, reason, qty
    )


def _refused(
    error: type[ShopError], call: Callable[[], object], what: str
) -> ShopError:
    """The refusal `call` raises; Broken if it raises none."""
    try:
        call()
    except error as refusal:
        return refusal
    raise Broken(f'{what} was not refused with {error.__name__}')


def _taken(call: Callable[[], object], kind: str, value: str) -> None:
    """`call` must raise DuplicateId naming this kind and id."""
    refusal = _refused(DuplicateId, call, f'a second {value}')
    assert isinstance(refusal, DuplicateId)
    if (refusal.kind, refusal.value) != (kind, value):
        raise Broken(
            f'DuplicateId named {refusal.kind} {refusal.value}'
        )


def _missing(call: Callable[[], object], kind: str, value: str) -> None:
    """`call` must raise UnknownId naming this kind and id."""
    refusal = _refused(UnknownId, call, f'unknown {value}')
    assert isinstance(refusal, UnknownId)
    if (refusal.kind, refusal.value) != (kind, value):
        raise Broken(f'UnknownId named {refusal.kind} {refusal.value}')


def _listed(items: Sequence[object]) -> str:
    return ', '.join(str(item) for item in items)


# Orders ---------------------------------------------------------


def _walk(uow: UnitOfWork, placed: Order, *states: Order) -> None:
    """Add `placed`, save each state and read it back, commit."""
    order_id = placed.head.order_id
    with uow:
        uow.orders.add(placed, _booking())
        for state in states:
            uow.orders.save(state)
            if uow.orders.get(order_id) != state:
                raise Broken(f'{order_id} came back changed')
        uow.commit()
    with uow:
        if uow.orders.get(order_id) != states[-1]:
            raise Broken(f'{order_id} changed when the unit ended')


def every_state_comes_back_as_saved(uow: UnitOfWork) -> str:
    first = _order('O-101', 'L-01', 'L-02')
    paid = pay(first, PaymentId('PAY-1'))
    shipped = ship(paid, ShipmentId('SH-1'))
    _walk(uow, first, paid, shipped, deliver(shipped))
    second = _order('O-102', 'L-03')
    on_invoice = ship(invoice(second), ShipmentId('SH-2'))
    _walk(uow, second, invoice(second), on_invoice)
    third = _order('O-103', 'L-04')
    _walk(uow, third, cancel(third, 'changed my mind'))
    return 'paid, invoiced, shipped, delivered and cancelled'


def an_order_keeps_its_prices_and_booking(uow: UnitOfWork) -> str:
    order = _order('O-101', 'L-01', 'L-02')
    with uow:
        uow.orders.add(order, _booking())
        uow.commit()
    with uow:
        lines = uow.orders.get(OrderId('O-101')).head.lines
        prices = [str(line.unit_price.amount) for line in lines]
        if prices != ['129.00', '899.00']:
            raise Broken(f'the prices came back as {prices}')
        if uow.orders.booking(OrderId('O-101')) != _booking():
            raise Broken('the booking came back changed')
    return 'prices to the ore, VAT share and moments in UTC'


def a_credit_order_keeps_its_negative_line(uow: UnitOfWork) -> str:
    sale = _order('O-101', 'L-01', 'L-02')
    credit = _credit('O-109', 'L-13', sale)
    with uow:
        uow.orders.add(sale, _booking())
        uow.orders.add(credit, _booking(8))
        uow.commit()
    with uow:
        back = uow.orders.get(OrderId('O-109'))
        if back != credit or back.head.lines[0].qty.value != -2:
            raise Broken('O-109 came back changed')
        if uow.orders.credits_of(OrderId('O-101')) != (credit,):
            raise Broken('O-101 does not list its credit order')
        if uow.orders.credits_of(OrderId('O-109')) != ():
            raise Broken('O-109 lists a credit order')
    return 'O-109 credits O-101 with a line of -2'


def a_second_add_is_refused(uow: UnitOfWork) -> str:
    first = _order('O-101', 'L-01')
    with uow:
        uow.orders.add(first, _booking())
        _taken(
            lambda: uow.orders.add(
                _order('O-101', 'L-02'), _booking(6)
            ),
            'order',
            'O-101',
        )
        uow.commit()
    with uow:
        if uow.orders.get(OrderId('O-101')) != first:
            raise Broken('the first O-101 was overwritten')
        if uow.orders.booking(OrderId('O-101')) != _booking():
            raise Broken('the first booking was overwritten')
    return 'DuplicateId: the first O-101 is kept'


def all_is_ordered(uow: UnitOfWork) -> str:
    with uow:
        for number, line in (('O-103', 'L-03'), ('O-101', 'L-01')):
            uow.orders.add(_order(number, line), _booking())
        uow.orders.add(_order('O-102', 'L-02'), _booking())
        uow.commit()
        ids = _listed(
            [order.head.order_id for order in uow.orders.all()]
        )
    if ids != 'O-101, O-102, O-103':
        raise Broken(f'listed {ids}')
    return f'listed {ids}'


def an_unknown_id_is_refused(uow: UnitOfWork) -> str:
    absent = OrderId('O-199')
    with uow:
        orders = uow.orders
        _missing(lambda: orders.get(absent), 'order', 'O-199')
        _missing(lambda: orders.booking(absent), 'order', 'O-199')
        _missing(
            lambda: orders.save(_order('O-199', 'L-99')),
            'order',
            'O-199',
        )
        _missing(
            lambda: orders.mark_deleted(absent, _moment()),
            'order',
            'O-199',
        )
    return 'get, booking, save and mark_deleted: UnknownId'


def a_cancel_marks_lines_not_the_order(uow: UnitOfWork) -> str:
    with uow:
        uow.orders.add(_order('O-106', 'L-10', 'L-11'), _booking(6))
        uow.orders.add(_order('O-107', 'L-08'), _booking(7))
        uow.orders.mark_deleted(OrderId('O-106'), _moment(7, 6))
        uow.commit()
    with uow:
        flags = [
            f'{line.line_id} {line.is_deleted}'
            for line in uow.orders.lines()
        ]
        kept = len(uow.orders.get(OrderId('O-106')).head.lines)
    if flags != ['L-08 False', 'L-10 True', 'L-11 True'] or kept != 2:
        raise Broken(f'lines listed as {flags}; O-106 holds {kept}')
    return 'L-10 and L-11 deleted, sorted by line id; O-106 keeps both'


ORDERS: Final = (
    every_state_comes_back_as_saved,
    an_order_keeps_its_prices_and_booking,
    a_credit_order_keeps_its_negative_line,
    a_second_add_is_refused,
    all_is_ordered,
    an_unknown_id_is_refused,
    a_cancel_marks_lines_not_the_order,
)
"""Every order check, in the order a table of them sorts."""


# Customers ------------------------------------------------------


def add_then_get(uow: UnitOfWork) -> str:
    known = _customer(1)
    bare = _customer(5, country=None, postal_code=None, email=False)
    with uow:
        uow.customers.add(known, _moment())
        uow.customers.add(bare, _moment(5, 10))
        uow.commit()
    with uow:
        if uow.customers.get(known.customer_id) != known:
            raise Broken('C-01 came back changed')
        if uow.customers.get(bare.customer_id) != bare:
            raise Broken('C-05 came back changed')
    return 'C-01 and C-05, who has no e-mail and no address, equal'


def seq_runs_from_one_across_units(uow: UnitOfWork) -> str:
    with uow:
        uow.customers.add(_customer(1), _moment(5))
        uow.commit()
    with uow:
        uow.customers.add(_customer(2, country='SE'), _moment(6))
        moved = replace(_customer(1), postal_code=PostalCode('0150'))
        uow.customers.change(moved, _moment(9))
        uow.commit()
    with uow:
        log = uow.customers.changes()
    rows = [(row.seq, row.op, str(row.customer_id)) for row in log]
    expected = [
        (1, 'insert', 'C-01'),
        (2, 'insert', 'C-02'),
        (3, 'update', 'C-01'),
    ]
    if rows != expected:
        raise Broken(f'the log reads {rows}')
    if [row.changed_at for row in log] != [
        _moment(d) for d in (5, 6, 9)
    ]:
        raise Broken('a row lost the moment of its change')
    return 'seq 1, 2, 3: insert C-01, insert C-02, update C-01'


def every_update_writes_a_row(uow: UnitOfWork) -> str:
    first = _customer(1)
    with uow:
        uow.customers.add(first, _moment(5))
        new_mail = replace(first, email=Email('new@example.invalid'))
        uow.customers.change(new_mail, _moment(6))
        uow.customers.change(new_mail, _moment(7))
        uow.commit()
    with uow:
        log = uow.customers.changes()
        held = uow.customers.get(first.customer_id)
    if [row.op for row in log] != ['insert', 'update', 'update']:
        raise Broken(f'the log reads {[row.op for row in log]}')
    after = (log[2].country, log[2].postal_code)
    if after != (first.country, first.postal_code):
        raise Broken('an update row lost the country or postal code')
    if held != new_mail:
        raise Broken('the new e-mail was not kept')
    return (
        'two updates, two rows, each with the country and postal code'
    )


def an_erase_leaves_a_tombstone(uow: UnitOfWork) -> str:
    with uow:
        uow.customers.add(_customer(1), _moment(5))
        uow.customers.add(_customer(7, postal_code='0450'), _moment(5))
        uow.customers.erase(CustomerId('C-07'), _moment(9))
        uow.commit()
    with uow:
        log = uow.customers.changes()
        left = _listed([c.customer_id for c in uow.customers.all()])
        erased = CustomerId('C-07')
        _missing(lambda: uow.customers.get(erased), 'customer', 'C-07')
    last = log[-1]
    key_only = (last.country, last.postal_code) == (None, None)
    if (last.op, str(last.customer_id)) != ('delete', 'C-07'):
        raise Broken(f'the last row is {last.op} {last.customer_id}')
    if not key_only or last.changed_at != _moment(9):
        raise Broken('the tombstone holds more than the key and moment')
    if left != 'C-01' or len(log) != 3:
        raise Broken(f'left {left}, with {len(log)} rows in the log')
    return 'delete row for C-07 with the key only; C-07 is gone'


def a_customer_second_add_is_refused(uow: UnitOfWork) -> str:
    first = _customer(1)
    with uow:
        uow.customers.add(first, _moment(5))
        _taken(
            lambda: uow.customers.add(
                _customer(1, country='SE'), _moment(6)
            ),
            'customer',
            'C-01',
        )
        uow.commit()
    with uow:
        if uow.customers.get(first.customer_id) != first:
            raise Broken('the first C-01 was overwritten')
        rows = len(uow.customers.changes())
    if rows != 1:
        raise Broken(f'the refused add left {rows} rows in the log')
    return 'DuplicateId: the first C-01 and one log row are kept'


def customers_are_listed_in_order(uow: UnitOfWork) -> str:
    with uow:
        for number in (3, 1, 2):
            uow.customers.add(_customer(number), _moment(5))
        uow.commit()
        ids = _listed([c.customer_id for c in uow.customers.all()])
    if ids != 'C-01, C-02, C-03':
        raise Broken(f'listed {ids}')
    return f'listed {ids}'


def a_missing_customer_is_refused(uow: UnitOfWork) -> str:
    absent = _customer(9)
    with uow:
        _missing(
            lambda: uow.customers.get(absent.customer_id),
            'customer',
            'C-09',
        )
        _missing(
            lambda: uow.customers.change(absent, _moment()),
            'customer',
            'C-09',
        )
        _missing(
            lambda: uow.customers.erase(absent.customer_id, _moment()),
            'customer',
            'C-09',
        )
        rows = len(uow.customers.changes())
    if rows:
        raise Broken(f'a refused call left {rows} rows in the log')
    return 'get, change and erase: UnknownId, and no log row'


CUSTOMERS: Final = (
    add_then_get,
    seq_runs_from_one_across_units,
    every_update_writes_a_row,
    an_erase_leaves_a_tombstone,
    a_customer_second_add_is_refused,
    customers_are_listed_in_order,
    a_missing_customer_is_refused,
)
"""Every customer check, in the order a table of them sorts."""


# The outbox -----------------------------------------------------


def positions_run_from_one(uow: UnitOfWork) -> str:
    with uow:
        first = [uow.outbox.add(_event(n)) for n in (1, 2)]
        uow.commit()
    with uow:
        later = uow.outbox.add(_event(3))
        uow.commit()
    if [*first, later] != [1, 2, 3]:
        raise Broken(f'positions {first} then {later}')
    return 'positions 1, 2 in one unit and 3 in the next'


def batches_are_cut_by_size(uow: UnitOfWork) -> str:
    with uow:
        for number in range(1, 6):
            uow.outbox.add(_event(number))
        made = uow.outbox.form_batches(2)
        again = uow.outbox.form_batches(2)
        uow.commit()
    with uow:
        waiting = uow.outbox.waiting()
    sizes = [len(batch.events) for batch in waiting]
    rows = [event for batch in waiting for event in batch.events]
    if made != (1, 2, 3) or again != () or sizes != [2, 2, 1]:
        raise Broken(f'formed {made} then {again}; sizes {sizes}')
    if rows != [_event(n) for n in range(1, 6)]:
        raise Broken('the rows are not those added, in position order')
    return (
        'five rows in batches of 2, 2 and 1; a second call forms none'
    )


def a_waiting_batch_keeps_its_rows(uow: UnitOfWork) -> str:
    with uow:
        for number in (1, 2, 3):
            uow.outbox.add(_event(number))
        uow.outbox.form_batches(2)
        uow.commit()
    with uow:
        for number in (4, 5):
            uow.outbox.add(_event(number))
        made = uow.outbox.form_batches(2)
        uow.commit()
    with uow:
        held = {b.number: b.events for b in uow.outbox.waiting()}
    expected = {
        1: (_event(1), _event(2)),
        2: (_event(3),),
        3: (_event(4), _event(5)),
    }
    if made != (3,) or held != expected:
        raise Broken(f'formed {made}; the batches hold {held}')
    return 'E-03 stays alone in batch 2; E-04 and E-05 start batch 3'


def sent_batches_leave_and_numbers_stay(uow: UnitOfWork) -> str:
    with uow:
        for number in (1, 2, 3, 4):
            uow.outbox.add(_event(number))
        uow.outbox.form_batches(1)
        uow.outbox.mark_sent(2)
        uow.commit()
    with uow:
        waiting = [batch.number for batch in uow.outbox.waiting()]
        _missing(lambda: uow.outbox.mark_sent(2), 'batch', '2')
        _missing(lambda: uow.outbox.mark_sent(9), 'batch', '9')
        uow.outbox.add(_event(5))
        made = uow.outbox.form_batches(1)
    if waiting != [1, 3, 4] or made != (5,):
        raise Broken(f'waiting {waiting}; the next batch is {made}')
    return 'batch 2 sent: 1, 3, 4 wait, and the next batch is 5'


OUTBOX: Final = (
    positions_run_from_one,
    batches_are_cut_by_size,
    a_waiting_batch_keeps_its_rows,
    sent_batches_leave_and_numbers_stay,
)
"""Every outbox check, in the order a table of them sorts."""


# The unit of work -----------------------------------------------


class _Abort(Exception):
    """Raised inside a block to see what the store does with it."""


def _write_everything(uow: UnitOfWork) -> None:
    """A change, its log row, its stock and its outbox row."""
    uow.customers.add(_customer(1), _moment())
    uow.orders.add(_order('O-101', 'L-01'), _booking())
    when = _moment(5, 10)
    uow.stock.add(_movement(1, 'P-10', 'sold', -2, when))
    uow.outbox.add(_event(1))


def _held(uow: UnitOfWork) -> list[int]:
    """How many of each kind of row the store holds: customers,
    log rows, orders, movements, waiting outbox rows."""
    with uow:
        waiting = sum(len(b.events) for b in uow.outbox.waiting())
        unbatched = uow.outbox.form_batches(1)
        return [
            len(uow.customers.all()),
            len(uow.customers.changes()),
            len(uow.orders.all()),
            len(uow.stock.movements(ProductId('P-10'))),
            waiting + len(unbatched),
        ]


def leaving_without_commit_undoes_everything(uow: UnitOfWork) -> str:
    with uow:
        _write_everything(uow)
    if (held := _held(uow)) != [0, 0, 0, 0, 0]:
        raise Broken(f'the store holds {held} after the block')
    return 'no customer, log row, order, movement or outbox row'


def commit_keeps_everything(uow: UnitOfWork) -> str:
    with uow:
        _write_everything(uow)
        uow.commit()
    if (held := _held(uow)) != [1, 1, 1, 1, 1]:
        raise Broken(f'the store holds {held} after the commit')
    return 'one customer, log row, order, movement and outbox row'


def a_write_after_the_last_commit_is_undone(uow: UnitOfWork) -> str:
    with uow:
        uow.customers.add(_customer(1), _moment())
        uow.commit()
        uow.customers.add(_customer(2), _moment())
        uow.outbox.add(_event(1))
    if (held := _held(uow)) != [1, 1, 0, 0, 0]:
        raise Broken(f'the store holds {held}')
    return 'C-01 kept; C-02, its log row and its outbox row undone'


def a_block_that_raises_undoes_everything(uow: UnitOfWork) -> str:
    try:
        with uow:
            _write_everything(uow)
            raise _Abort
    except _Abort:
        pass
    else:
        raise Broken('the block swallowed the error')
    if (held := _held(uow)) != [0, 0, 0, 0, 0]:
        raise Broken(f'the store holds {held} after the error')
    return 'the error went on, and nothing was kept'


def a_rolled_back_change_leaves_no_gap(uow: UnitOfWork) -> str:
    with uow:
        uow.customers.add(_customer(1), _moment())
    with uow:
        uow.customers.add(_customer(2), _moment())
        uow.commit()
    with uow:
        seqs = [row.seq for row in uow.customers.changes()]
    if seqs != [1]:
        raise Broken(f'the log reads seq {seqs}')
    return 'the first kept change is seq 1'


def a_unit_cannot_be_opened_twice(uow: UnitOfWork) -> str:
    with uow:
        try:
            with uow:
                pass
        except RuntimeError:
            pass
        else:
            raise Broken('a unit of work opened twice at once')
    with uow:
        uow.customers.all()
    return 'RuntimeError, and the unit works again after it'


UNIT_OF_WORK: Final = (
    leaving_without_commit_undoes_everything,
    commit_keeps_everything,
    a_write_after_the_last_commit_is_undone,
    a_block_that_raises_undoes_everything,
    a_rolled_back_change_leaves_no_gap,
    a_unit_cannot_be_opened_twice,
)
"""Every unit-of-work check, in the order a table of them sorts."""


# Stock ----------------------------------------------------------


def _stock_week(uow: UnitOfWork) -> None:
    """P-10 and P-20 as the frozen week moves them."""
    with uow:
        uow.stock.add(
            _movement(1, 'P-10', 'roasted', 42, _moment(5, 7))
        )
        uow.stock.add(_movement(2, 'P-10', 'sold', -2, _moment(5, 12)))
        uow.stock.add(_movement(3, 'P-10', 'sold', -3, _moment(6, 9)))
        uow.stock.add(_movement(4, 'P-20', 'counted', 5, _moment(5, 7)))
        uow.stock.add(_movement(5, 'P-20', 'sold', -1, _moment(5, 12)))
        uow.commit()


def on_hand_is_the_signed_sum(uow: UnitOfWork) -> str:
    _stock_week(uow)
    with uow:
        sums = [
            uow.stock.on_hand(ProductId(product))
            for product in ('P-10', 'P-20', 'P-11')
        ]
    if sums != [37, 4, 0]:
        raise Broken(f'on hand {sums}')
    return 'P-10 37, P-20 4, and P-11 with no movement 0'


def on_hand_before_a_moment_leaves_out_that_moment(
    uow: UnitOfWork,
) -> str:
    _stock_week(uow)
    p10 = ProductId('P-10')
    with uow:
        seen = [
            uow.stock.on_hand(p10, before=_moment(5, 12)),
            uow.stock.on_hand(p10, before=_moment(5, 12, 1)),
            uow.stock.on_hand(p10, before=_moment(6, 0)),
        ]
    if seen != [42, 40, 40]:
        raise Broken(f'on hand before the moments: {seen}')
    return 'a sale at 12:00 is in the balance from 12:01, not at 12:00'


def movements_are_listed_oldest_first(uow: UnitOfWork) -> str:
    noon = _moment(5, 12)
    with uow:
        uow.stock.add(_movement(3, 'P-10', 'sold', -1, noon))
        uow.stock.add(_movement(2, 'P-10', 'roasted', 6, _moment(5, 7)))
        uow.stock.add(_movement(1, 'P-10', 'sold', -2, noon))
        uow.commit()
        ids = _listed(
            [
                m.movement_id
                for m in uow.stock.movements(ProductId('P-10'))
            ]
        )
    if ids != 'M-2, M-1, M-3':
        raise Broken(f'listed {ids}')
    return f'listed {ids}: by moment, then by id'


def a_second_movement_add_is_refused(uow: UnitOfWork) -> str:
    with uow:
        uow.stock.add(_movement(1, 'P-10', 'roasted', 6, _moment()))
        _taken(
            lambda: uow.stock.add(
                _movement(1, 'P-10', 'sold', -1, _moment(6))
            ),
            'movement',
            'M-1',
        )
        uow.commit()
        left = uow.stock.on_hand(ProductId('P-10'))
    if left != 6:
        raise Broken(
            f'the refused movement changed the balance: {left}'
        )
    return 'DuplicateId: M-1 stays a roast of 6'


def a_day_may_be_counted_twice(uow: UnitOfWork) -> str:
    day = dt.date(2026, 10, 7)
    first = Count(ProductId('P-10'), day, 26, _moment(7, 16))
    recount = Count(ProductId('P-10'), day, 36, _moment(8, 6, 30))
    other = Count(ProductId('P-20'), day, 4, _moment(7, 16))
    with uow:
        for count in (recount, other, first):
            uow.stock.add_count(count)
        _refused(
            DuplicateId,
            lambda: uow.stock.add_count(first),
            'the same count again',
        )
        uow.commit()
    with uow:
        listed = uow.stock.counts(day)
        empty = uow.stock.counts(dt.date(2026, 10, 8))
    if listed != (first, recount, other) or empty != ():
        raise Broken('the counts of 7 October are not listed in order')
    return 'P-10 at 16:00, P-10 recounted next morning, then P-20'


STOCK: Final = (
    on_hand_is_the_signed_sum,
    on_hand_before_a_moment_leaves_out_that_moment,
    movements_are_listed_oldest_first,
    a_second_movement_add_is_refused,
    a_day_may_be_counted_twice,
)
"""Every stock check, in the order a table of them sorts."""


# Source ---------------------------------------------------------


def _sources(uow: UnitOfWork) -> list[str]:
    return [
        uow.customers.source_of(CustomerId('C-01')),
        uow.orders.source_of(OrderId('O-101')),
        uow.stock.source_of(MovementId('M-1')),
    ]


def rows_read_back_with_the_source(uow: UnitOfWork) -> str:
    with uow:
        _write_everything(uow)
        seen = _sources(uow)
        uow.commit()
    if seen != [uow.source] * 3:
        raise Broken(
            f'{uow.source} wrote rows that read back as {seen}'
        )
    return f'customer, order and movement read back as {uow.source}'


def the_source_outlives_the_commit(uow: UnitOfWork) -> str:
    with uow:
        _write_everything(uow)
        uow.commit()
    with uow:
        seen = _sources(uow)
    if seen != [uow.source] * 3:
        raise Broken(
            f'{uow.source} wrote rows that read back as {seen}'
        )
    return f'after the commit the rows still read back as {uow.source}'


def _day(day: int) -> dt.date:
    """A day of October 2026."""
    return dt.date(2026, 10, day)


def _nok(amount: str) -> Money:
    return Money.of(amount, 'NOK')


def _p10() -> ProductId:
    """The product the checks write their rows about."""
    return ProductId('P-10')


def _write_one_of_each(uow: UnitOfWork) -> None:
    """One row of every table whose source the export reads."""
    uow.customers.add(_customer(1), _moment())
    uow.catalogue.add_category(
        Category(CategoryId('CAT-1'), 'Beans', None, 1)
    )
    uow.catalogue.add_product(
        Product(
            _p10(), 'Morning roast', 'beans', CategoryId('CAT-1'), 250
        ),
        BeanDetails(250, 'Brazil', 'medium', 'dry'),
    )
    uow.catalogue.add_campaign(
        Campaign(
            CampaignId('K-1'), 'Autumn', 10, _day(5), _day(9), (_p10(),)
        )
    )
    uow.prices.add(Price(_p10(), _nok('129.00'), _day(1), None))
    uow.costs.add(
        Cost(_p10(), _day(1), None, _nok('40'), _nok('5'), _nok('10'))
    )
    uow.rules.add(
        Discount(RuleId('PR-1'), 'subscriber', 10, _day(1), None)
    )
    sub = SubscriptionId('S-1')
    uow.subscriptions.add(
        Subscription.begin(sub, CustomerId('C-01'), _p10(), _day(1))
    )
    uow.subscriptions.record(
        Skip(SubEventId('SE-1'), sub, 'away', _moment(), _day(5))
    )
    uow.subscriptions.add_bag(
        BagShipment(BagId('SB-1'), sub, _p10(), _day(5), 1)
    )
    uow.stock.add_count(Count(_p10(), _day(5), 40, _moment(5, 16)))
    uow.shipments.add(
        Shipment(
            ShipmentId('SH-1'), OrderId('O-101'), _day(6), _day(8), None
        )
    )
    uow.purchases.add(
        GreenPurchase(
            PurchaseId('GP-1'),
            _day(2),
            'Brazil',
            Decimal('60.00'),
            _nok('85.00'),
        )
    )
    extract = ExtractRow(
        _day(5), CustomerId('C-01'), 'NO', PostalCode('7010')
    )
    uow.extracts.replace(_day(5), (extract,))


def _every_source(uow: UnitOfWork) -> list[str]:
    """The source of each row `_write_one_of_each` wrote."""
    return [
        uow.customers.change_source(1),
        uow.catalogue.category_source(CategoryId('CAT-1')),
        uow.catalogue.product_source(_p10()),
        uow.catalogue.campaign_source(CampaignId('K-1')),
        uow.prices.source_of(_p10(), _day(1)),
        uow.costs.source_of(_p10(), _day(1)),
        uow.rules.source_of(RuleId('PR-1')),
        uow.subscriptions.source_of(SubscriptionId('S-1')),
        uow.subscriptions.event_source(SubEventId('SE-1')),
        uow.subscriptions.bag_source(BagId('SB-1')),
        uow.stock.count_source(_p10(), _day(5), _moment(5, 16)),
        uow.shipments.source_of(ShipmentId('SH-1')),
        uow.purchases.source_of(PurchaseId('GP-1')),
        uow.extracts.source_of(_day(5), CustomerId('C-01')),
    ]


def every_table_reads_back_its_source(uow: UnitOfWork) -> str:
    with uow:
        _write_one_of_each(uow)
        uow.commit()
    with uow:
        seen = _every_source(uow)
    if seen != [uow.source] * len(seen):
        raise Broken(
            f'{uow.source} wrote rows that read back as {seen}'
        )
    return f'{len(seen)} tables read back as {uow.source}'


def the_source_of_a_missing_row_is_refused(uow: UnitOfWork) -> str:
    p99 = ProductId('P-99')
    late = _moment(9, 16)
    with uow:
        reads: tuple[tuple[Callable[[], object], str, str], ...] = (
            (lambda: uow.customers.change_source(9), 'change', '9'),
            (
                lambda: uow.catalogue.category_source(
                    CategoryId('CAT-9')
                ),
                'category',
                'CAT-9',
            ),
            (
                lambda: uow.catalogue.product_source(p99),
                'product',
                'P-99',
            ),
            (
                lambda: uow.catalogue.campaign_source(
                    CampaignId('K-9')
                ),
                'campaign',
                'K-9',
            ),
            (
                lambda: uow.prices.source_of(p99, _day(1)),
                'price',
                'P-99 2026-10-01',
            ),
            (
                lambda: uow.costs.source_of(p99, _day(1)),
                'cost',
                'P-99 2026-10-01',
            ),
            (
                lambda: uow.rules.source_of(RuleId('PR-9')),
                'rule',
                'PR-9',
            ),
            (
                lambda: uow.subscriptions.source_of(
                    SubscriptionId('S-9')
                ),
                'subscription',
                'S-9',
            ),
            (
                lambda: uow.subscriptions.event_source(
                    SubEventId('SE-9')
                ),
                'sub_event',
                'SE-9',
            ),
            (
                lambda: uow.subscriptions.bag_source(BagId('SB-9')),
                'bag',
                'SB-9',
            ),
            (
                lambda: uow.stock.count_source(p99, _day(9), late),
                'count',
                'P-99 2026-10-09 2026-10-09T16:00:00+00:00',
            ),
            (
                lambda: uow.shipments.source_of(ShipmentId('SH-9')),
                'shipment',
                'SH-9',
            ),
            (
                lambda: uow.purchases.source_of(PurchaseId('GP-9')),
                'purchase',
                'GP-9',
            ),
            (
                lambda: uow.extracts.source_of(
                    _day(9), CustomerId('C-09')
                ),
                'extract',
                '2026-10-09 C-09',
            ),
        )
        for call, kind, value in reads:
            _missing(call, kind, value)
    return f'{len(reads)} source reads: UnknownId naming the row'


SOURCE: Final = (
    rows_read_back_with_the_source,
    the_source_outlives_the_commit,
    every_table_reads_back_its_source,
    the_source_of_a_missing_row_is_refused,
)
"""Every source check, in the order a table of them sorts."""


# The listings the export reads (W2) -----------------------------


def _campaign(number: int, *products: str) -> Campaign:
    return Campaign(
        CampaignId(f'K-{number}'),
        f'Campaign {number}',
        10 * number,
        _day(5),
        _day(9),
        tuple(ProductId(each) for each in products),
    )


def campaigns_are_listed_with_their_products(uow: UnitOfWork) -> str:
    with uow:
        uow.catalogue.add_campaign(_campaign(2, 'P-20', 'P-10'))
        uow.catalogue.add_campaign(_campaign(1, 'P-11'))
        uow.commit()
    with uow:
        listed = uow.catalogue.campaigns()
    if listed != (_campaign(1, 'P-11'), _campaign(2, 'P-10', 'P-20')):
        raise Broken(f'listed {listed}')
    return 'K-1, then K-2 with P-10 before P-20'


def details_come_back_by_kind(uow: UnitOfWork) -> str:
    beans = BeanDetails(250, 'Brazil', 'medium', 'dry')
    kettle = EquipmentDetails(12, 'steel')
    category = CategoryId('CAT-1')
    with uow:
        uow.catalogue.add_product(
            Product(_p10(), 'Morning roast', 'beans', category, 250),
            beans,
        )
        uow.catalogue.add_product(
            Product(
                ProductId('P-21'), 'Kettle', 'equipment', category, None
            ),
            kettle,
        )
        uow.commit()
    with uow:
        held = [
            uow.catalogue.details(_p10()),
            uow.catalogue.details(ProductId('P-21')),
        ]
        _missing(
            lambda: uow.catalogue.details(ProductId('P-99')),
            'product',
            'P-99',
        )
    if held != [beans, kettle]:
        raise Broken(f'the details came back as {held}')
    return 'P-10 its bean details, P-21 its equipment; P-99 UnknownId'


def _shipment(number: int, delivered: dt.date | None) -> Shipment:
    return Shipment(
        ShipmentId(f'SH-{number}'),
        OrderId(f'O-10{number}'),
        _day(6),
        _day(8),
        delivered,
    )


def shipments_are_listed_by_id(uow: UnitOfWork) -> str:
    with uow:
        uow.shipments.add(_shipment(2, None))
        uow.shipments.add(_shipment(1, None))
        uow.shipments.save(_shipment(1, _day(8)))
        uow.commit()
    with uow:
        listed = uow.shipments.all()
    if listed != (_shipment(1, _day(8)), _shipment(2, None)):
        raise Broken(f'listed {listed}')
    return 'SH-1 delivered on 8 October, then SH-2'


def all_counts_are_listed_by_product_day_and_stamp(
    uow: UnitOfWork,
) -> str:
    p20 = ProductId('P-20')
    counts = (
        Count(_p10(), _day(5), 40, _moment(5, 16)),
        Count(_p10(), _day(5), 41, _moment(6, 6)),
        Count(_p10(), _day(6), 37, _moment(6, 16)),
        Count(p20, _day(5), 4, _moment(5, 16)),
    )
    with uow:
        for count in reversed(counts):
            uow.stock.add_count(count)
        uow.commit()
    with uow:
        listed = uow.stock.all_counts()
    if listed != counts:
        raise Broken(f'listed {listed}')
    return 'P-10 on 5 October twice, P-10 on 6 October, then P-20'


def _extract(day: int, customer: str) -> ExtractRow:
    return ExtractRow(_day(day), CustomerId(customer), 'NO', None)


def all_extracts_are_listed_by_day_then_customer(
    uow: UnitOfWork,
) -> str:
    with uow:
        uow.extracts.replace(
            _day(6), (_extract(6, 'C-02'), _extract(6, 'C-01'))
        )
        uow.extracts.replace(_day(5), (_extract(5, 'C-03'),))
        uow.commit()
    with uow:
        listed = uow.extracts.all()
    expected = (
        _extract(5, 'C-03'),
        _extract(6, 'C-01'),
        _extract(6, 'C-02'),
    )
    if listed != expected:
        raise Broken(f'listed {listed}')
    return '5 October C-03, then 6 October C-01 and C-02'


READS: Final = (
    campaigns_are_listed_with_their_products,
    details_come_back_by_kind,
    shipments_are_listed_by_id,
    all_counts_are_listed_by_product_day_and_stamp,
    all_extracts_are_listed_by_day_then_customer,
)
"""Every check of a listing the export reads, in table order."""


# The suites -----------------------------------------------------


def _run(
    checks: Sequence[Run], make: Callable[[], UnitOfWork]
) -> list[Check]:
    """Run each check on a new store; a raise is a failed check."""
    results: list[Check] = []
    for check in checks:
        name = check.__name__.replace('_', ' ')
        try:
            results.append(Check(name, True, check(make())))
        except Exception as error:
            said = f'{type(error).__name__}: {error}'
            results.append(Check(name, False, said))
    return results


def check_orders(make: Callable[[], UnitOfWork]) -> list[Check]:
    """Run every order check on a new, empty store."""
    return _run(ORDERS, make)


def check_customers(make: Callable[[], UnitOfWork]) -> list[Check]:
    """Run every customer check on a new, empty store."""
    return _run(CUSTOMERS, make)


def check_outbox(make: Callable[[], UnitOfWork]) -> list[Check]:
    """Run every outbox check on a new, empty store."""
    return _run(OUTBOX, make)


def check_unit_of_work(make: Callable[[], UnitOfWork]) -> list[Check]:
    """Run every unit-of-work check on a new, empty store."""
    return _run(UNIT_OF_WORK, make)


def check_stock(make: Callable[[], UnitOfWork]) -> list[Check]:
    """Run every stock check on a new, empty store."""
    return _run(STOCK, make)


def check_source(make: Callable[[], UnitOfWork]) -> list[Check]:
    """Run every source check on a new, empty store."""
    return _run(SOURCE, make)


def check_reads(make: Callable[[], UnitOfWork]) -> list[Check]:
    """Run every check of the export's listings on a new store."""
    return _run(READS, make)
