"""The order's state machine holds the moves the feed shows."""

from __future__ import annotations

import ast
import datetime as dt
from pathlib import Path
from typing import get_args

import pytest

import roastery
from roastery.errors import IllegalTransition
from roastery.ids import CustomerId, OrderId, PaymentId, ShipmentId
from roastery.money import Money
from roastery.order import (
    TRANSITIONS,
    Action,
    Cancelled,
    Delivered,
    Head,
    Invoiced,
    Order,
    OrderLine,
    Paid,
    Payment,
    Placed,
    Shipped,
    cancel,
    deliver,
    invoice,
    invoice_open,
    pay,
    ship,
    status,
)

PACKAGE_DIR = Path(roastery.__file__).parent

# ADR 0005's table of legal moves, written out from the ADR, so
# the grid checks TRANSITIONS and the moves against it.
ALLOWED = {
    ('placed', 'pay'): 'paid',
    ('placed', 'invoice'): 'invoiced',
    ('placed', 'cancel'): 'cancelled',
    ('paid', 'ship'): 'shipped',
    ('paid', 'cancel'): 'cancelled',
    ('invoiced', 'ship'): 'shipped',
    ('invoiced', 'cancel'): 'cancelled',
    ('shipped', 'deliver'): 'delivered',
}

STATES = (
    'placed',
    'paid',
    'invoiced',
    'shipped',
    'delivered',
    'cancelled',
)

# O-101 as dataset.sql has it: C-01, web, L-01 and L-02.
HEAD = Head(
    order_id=OrderId('O-101'),
    customer_id=CustomerId('C-01'),
    channel='web',
    country='NO',
    lines=(
        OrderLine.of(
            line_id='L-01',
            product_id='P-10',
            qty=2,
            unit_price='129.00',
        ),
        OrderLine.of(
            line_id='L-02',
            product_id='P-20',
            qty=1,
            unit_price='899.00',
        ),
    ),
    credit_of=None,
)
PAID = Paid(HEAD, PaymentId('PAY-1'))
SHIPPED = Shipped(PAID, ShipmentId('SH-1'))
ONE_OF_EACH: dict[str, Order] = {
    'placed': Placed(HEAD),
    'paid': PAID,
    'invoiced': Invoiced(HEAD),
    'shipped': SHIPPED,
    'delivered': Delivered(PAID, ShipmentId('SH-1')),
    'cancelled': Cancelled(HEAD, 'changed her mind'),
}


def _move(order: Order, action: Action) -> Order:
    match action:
        case 'pay':
            return pay(order, PaymentId('PAY-1'))
        case 'invoice':
            return invoice(order)
        case 'ship':
            return ship(order, ShipmentId('SH-1'))
        case 'deliver':
            return deliver(order)
        case 'cancel':
            return cancel(order, 'changed her mind')


@pytest.mark.parametrize('action', get_args(Action))
@pytest.mark.parametrize('state', STATES)
def test_each_pair_of_the_grid(state: str, action: Action) -> None:
    order = ONE_OF_EACH[state]
    if (state, action) in ALLOWED:
        moved = _move(order, action)
        assert status(moved) == ALLOWED[state, action]
        assert moved.head == order.head
        return
    with pytest.raises(IllegalTransition) as caught:
        _move(order, action)
    error = caught.value
    assert (error.order_id, error.state, error.action) == (
        OrderId('O-101'),
        state,
        action,
    )


def test_o106_cannot_ship_after_its_cancel() -> None:
    # dataset.sql: O-106 by C-04 (FI) on the web, placed at E-11
    # with L-10 (one bag), cancelled at E-12. L-10's product is
    # 6.4's choice (ADR 0005): any bean but P-10.
    placed = Placed(
        Head(
            order_id=OrderId('O-106'),
            customer_id=CustomerId('C-04'),
            channel='web',
            country='FI',
            lines=(
                OrderLine.of(
                    line_id='L-10',
                    product_id='P-11',
                    qty=1,
                    unit_price='349.00',
                ),
            ),
            credit_of=None,
        )
    )
    cancelled = cancel(placed, 'cancelled by the customer')
    with pytest.raises(IllegalTransition) as caught:
        ship(cancelled, ShipmentId('SH-1'))
    error = caught.value
    assert (error.order_id, error.state, error.action) == (
        OrderId('O-106'),
        'cancelled',
        'ship',
    )


def test_the_feed_words_are_the_table_words() -> None:
    feed = {status(order) for order in ONE_OF_EACH.values()}
    table = {state for state, _ in TRANSITIONS} | set(
        TRANSITIONS.values()
    )
    assert feed == table
    assert len(feed) == 6


def _negative_qty_calls(tree: ast.Module) -> list[str]:
    """The qualified name around each `Qty(` given a negative."""
    found: list[str] = []

    def is_negative(node: ast.expr) -> bool:
        return isinstance(node, ast.UnaryOp) and isinstance(
            node.op, ast.USub
        )

    def visit(node: ast.AST, scope: tuple[str, ...]) -> None:
        if isinstance(
            node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
        ):
            scope = (*scope, node.name)
        if isinstance(node, ast.Call):
            func = node.func
            name = (
                func.id
                if isinstance(func, ast.Name)
                else func.attr
                if isinstance(func, ast.Attribute)
                else ''
            )
            values = [*node.args[:1]] + [
                word.value
                for word in node.keywords
                if word.arg == 'value'
            ]
            if name == 'Qty' and any(map(is_negative, values)):
                found.append('.'.join(scope))
        for child in ast.iter_child_nodes(node):
            visit(child, scope)

    visit(tree, ())
    return found


def test_only_credit_makes_a_negative_qty() -> None:
    found = {
        (path.stem, where)
        for path in sorted(PACKAGE_DIR.glob('*.py'))
        for where in _negative_qty_calls(
            ast.parse(path.read_text(encoding='utf-8'))
        )
    }
    assert found == {('order', 'OrderLine.credit')}


def test_an_invoice_is_open_until_a_payment_names_it() -> None:
    invoiced = Invoiced(HEAD)
    other = Payment(
        PaymentId('PAY-2'),
        OrderId('O-102'),
        Money.of('516.98', 'SEK'),
        dt.date(2026, 10, 5),
        'paid',
    )
    assert invoice_open(invoiced, [other])
    mine = Payment(
        PaymentId('PAY-1'),
        OrderId('O-101'),
        Money.of('1', 'NOK'),
        dt.date(2026, 10, 5),
        'invoiced',
    )
    assert not invoice_open(invoiced, [other, mine])
