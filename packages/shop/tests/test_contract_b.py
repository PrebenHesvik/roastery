"""Contract B, frozen as text (C12, C27, A19).

The whole call surface the simulator uses is rendered as one sorted
line per item and compared with contract_b.txt. Regenerate the file
on purpose with: uv run python packages/shop/tests/test_contract_b.py
--write (from the repository root), in the commit that changes the code.
"""

from __future__ import annotations

import ast
import dataclasses
import difflib
import inspect
import sys
import typing
from pathlib import Path

import roastery
from roastery.bootstrap import (
    App,
    Jobs,
    memory_store,
    sqlite_store,
    wire,
)
from roastery.catalogue import BeanDetails, EquipmentDetails
from roastery.checkout import Checkout, Item, PlaceOrder
from roastery.customer import AccountKind, Email
from roastery.customers import Customers
from roastery.errors import ShopError
from roastery.events import CollectingBus, HandlerFailure, StatusChanged
from roastery.fakes import (
    FakeClock,
    FakeLabels,
    FakeNotifier,
    FakeProvider,
)
from roastery.fulfilment import Fulfilment
from roastery.ids import (
    CategoryId,
    Country,
    CustomerId,
    EventId,
    LineId,
    OrderId,
    PaymentId,
    PostalCode,
    ProductId,
    ShipmentId,
    SubscriptionId,
)
from roastery.listing import Catalogue
from roastery.money import Money, Qty
from roastery.order import (
    Channel,
    Head,
    Invoiced,
    OrderLine,
    Placed,
    Status,
)
from roastery.payments import PaymentMessage, Payments, Receipt
from roastery.pipeline import Rows
from roastery.ports import (
    FeedDown,
    IdKind,
    Labels,
    Notifier,
    PaymentProvider,
    ProviderRefused,
    ProviderUnavailable,
    Relayed,
    Source,
    StatusFeed,
)
from roastery.repository import ScriptedIds, SequentialIds
from roastery.settings import Positive, Secret, Settings, Url
from roastery.stock import Stock
from roastery.subscriptions import Subscriptions

SNAPSHOT = Path(__file__).with_name('contract_b.txt')

CLASSES = (
    App,
    Secret,
    Jobs,
    Customers,
    Catalogue,
    Checkout,
    Payments,
    Fulfilment,
    Subscriptions,
    Stock,
    CollectingBus,
    PaymentProvider,
    StatusFeed,
    Notifier,
    Labels,
    SequentialIds,
    ScriptedIds,
    FakeClock,
    FakeProvider,
    FakeNotifier,
    FakeLabels,
)
FUNCTIONS = (wire, memory_store, sqlite_store)
DATACLASSES = (
    Item,
    PlaceOrder,
    PaymentMessage,
    Receipt,
    App,
    StatusChanged,
    HandlerFailure,
    Relayed,
    Rows,
    Settings,
    BeanDetails,
    EquipmentDetails,
    Money,
    Qty,
    Email,
    PostalCode,
    Head,
    OrderLine,
    Placed,
    Invoiced,
    CategoryId,
    CustomerId,
    EventId,
    LineId,
    OrderId,
    PaymentId,
    ProductId,
    ShipmentId,
    SubscriptionId,
)
"""Every class a contract B signature or field names, with the
fields of those it reaches (Head, OrderLine): the ids and Qty
hold one `value`, which pins what the simulator builds by
position."""
LITERALS = (
    ('Source', Source),
    ('IdKind', IdKind),
    ('Country', Country),
    ('AccountKind', AccountKind),
    ('Channel', Channel),
    ('Status', Status),
)
NEW_TYPES = (Url, Positive)
"""The constructors of Settings' field types, which the simulator
calls: each is pinned with the type it wraps."""
PORT_ERRORS = (FeedDown, ProviderRefused, ProviderUnavailable)
NOT_IN_B = frozenset({'Fulfilment.late_shipments'})
"""Reads the pages call, which architecture.md §5 keeps out."""


class _Text(str):
    """An annotation shown as the source wrote it: no quotes."""

    __slots__ = ()

    def __repr__(self) -> str:
        return str(self)


def _plain(annotation: object) -> object:
    if isinstance(annotation, str):
        return _Text(annotation)
    return annotation


def _signature(function: object) -> str:
    """str(inspect.signature(f)) without eval_str, quotes stripped
    from string annotations only (a string default keeps its own)."""
    sig = inspect.signature(function)  # type: ignore[arg-type]
    params = [
        p.replace(annotation=_plain(p.annotation))
        for p in sig.parameters.values()
    ]
    return str(
        sig.replace(
            parameters=params,
            return_annotation=_plain(sig.return_annotation),
        )
    )


def _own_methods(cls: type) -> list[str]:
    """The class's own public methods and __init__ (a Protocol's
    generated __init__ is not its own)."""
    lines = []
    for name, member in vars(cls).items():
        if name != '__init__' and name.startswith('_'):
            continue
        if name == '__init__' and getattr(cls, '_is_protocol', False):
            continue
        if f'{cls.__name__}.{name}' in NOT_IN_B:
            continue
        if isinstance(member, (staticmethod, classmethod)):
            member = member.__func__
        if isinstance(member, property):
            lines.append(f'{cls.__name__}.{name} = property')
        elif inspect.isfunction(member):
            lines.append(f'{cls.__name__}.{name}{_signature(member)}')
    return lines


def _family(error: type[ShopError]) -> list[str]:
    name = error.__name__
    lines = [f'{name}.__init__{_signature(error.__init__)}']
    for sub in error.__subclasses__():
        lines.extend(_family(sub))
    return lines


def render() -> str:
    """The surface as text: sorted lines, LF, one final newline."""
    lines: list[str] = []
    for cls in CLASSES:
        lines.extend(_own_methods(cls))
    for function in FUNCTIONS:
        lines.append(f'{function.__name__}{_signature(function)}')
    for cls in DATACLASSES:
        for i, field in enumerate(dataclasses.fields(cls)):
            default = (
                ''
                if field.default is dataclasses.MISSING
                else f' = {field.default!r}'
            )
            lines.append(
                f'{cls.__name__}.fields[{i:02d}] '
                f'{field.name}: {_plain(field.type)}{default}'
            )
    for name, literal in LITERALS:
        members = ', '.join(repr(m) for m in typing.get_args(literal))
        lines.append(f'{name} = {members}')
    for new_type in NEW_TYPES:
        wraps = new_type.__supertype__.__name__
        lines.append(f'{new_type.__name__} = NewType({wraps})')
    lines.extend(_family(ShopError))
    for error in PORT_ERRORS:
        name = error.__name__
        lines.append(f'{name}.__init__{_signature(error.__init__)}')
    return '\n'.join(sorted(lines)) + '\n'


def test_contract_b_matches_snapshot() -> None:
    expected = SNAPSHOT.read_bytes().decode('utf-8')
    actual = render()
    diff = ''.join(
        difflib.unified_diff(
            expected.splitlines(keepends=True),
            actual.splitlines(keepends=True),
            fromfile='contract_b.txt',
            tofile='rendered from the code',
        )
    )
    assert actual == expected, 'contract B moved:\n' + diff


def _base_name(base: ast.expr) -> str | None:
    if isinstance(base, ast.Name):
        return base.id
    if isinstance(base, ast.Attribute):
        return base.attr
    return None


def test_only_errors_py_defines_shop_errors() -> None:
    package = Path(roastery.__file__).parent
    errors = package / 'errors.py'
    strays = []
    for path in sorted(package.rglob('*.py')):
        if path == errors:
            continue
        known = {'ShopError'}
        classes = [
            node
            for node in ast.walk(ast.parse(path.read_text('utf-8')))
            if isinstance(node, ast.ClassDef)
        ]
        grew = True
        while grew:  # a subclass of a subclass, in any order
            grew = False
            for node in classes:
                bases = {_base_name(b) for b in node.bases}
                if node.name not in known and bases & known:
                    known.add(node.name)
                    grew = True
                    strays.append(f'{path.name}: {node.name}')
    assert strays == []


if __name__ == '__main__':
    if sys.argv[1:] == ['--write']:
        with SNAPSHOT.open('w', encoding='utf-8', newline='\n') as out:
            out.write(render())
    else:
        sys.stdout.write(render())
