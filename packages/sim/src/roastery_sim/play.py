"""Play a world through the shop app (6.4, W1, W10; 6.5, V1, V4).

One clock, one store and two wirings of the app over it (C7, ADR
0007): `scripted` draws the week's hand-written ids, `simulator` the
shared sequence. Each step of the world is one call of contract B,
made at the step's moment through its wiring. After each UTC day's
last step the handlers' failures of both wirings are read; any
failure stops the play (W10). A step that names a handle gets the id
the call under that handle returned (V4). What comes back is the
app's tables, the feed's and the provider's rows and the outside
systems' rows, all correct, and the same read at each snapshot
moment asked for: the faults and the cut are later modules'.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final, Literal
from zoneinfo import ZoneInfo

from roastery.bootstrap import App, memory_store, sqlite_store, wire
from roastery.events import HandlerFailure
from roastery.fakes import FakeClock, FakeLabels, FakeNotifier, FakeProvider
from roastery.ids import CustomerId, LineId, OrderId, PaymentId, ShipmentId, SubscriptionId
from roastery.money import Money
from roastery.payments import PaymentMessage
from roastery.pipeline import Rows
from roastery.ports import IdKind, Ids, Labels, Notifier, Relayed, Source
from roastery.repository import ScriptedIds, SequentialIds
from roastery.settings import Positive, Secret, Settings, Url

from roastery_sim import outside, script
from roastery_sim.feed import Feed
from roastery_sim.outside import ProviderLog
from roastery_sim.script import (
    AddCampaign,
    AddCategory,
    AddProduct,
    BuyGreen,
    CancelOrder,
    CancelSubscription,
    Change,
    CountAtClose,
    Credit,
    CsvExport,
    CustomerRef,
    Deliver,
    Erase,
    Invoice,
    NightlyExtract,
    OrderRef,
    Pause,
    Pay,
    Place,
    Refund,
    Register,
    Relay,
    Resume,
    Roast,
    SetCost,
    SetPrice,
    SetSubscriberDiscount,
    Settle,
    Ship,
    ShipBags,
    Skip,
    Step,
    Stocktake,
    Subscribe,
    SubscriptionRef,
    World,
    WriteOff,
)

RELAY_BATCH = Positive(5)
"""Events per relay batch (W5): the Settings default, stated."""


class _DrawLog:
    """The `Ids` port with a record of what it gave, kind by kind (W6)."""

    def __init__(self, inner: Ids) -> None:
        self._inner = inner
        self.drawn: dict[IdKind, list[str]] = {}

    def next(self, kind: IdKind) -> str:
        each = self._inner.next(kind)
        self.drawn.setdefault(kind, []).append(each)
        return each

    def take(self) -> dict[IdKind, list[str]]:
        """What was drawn since the last take."""
        drawn, self.drawn = self.drawn, {}
        return drawn


class PlayStopped(Exception):
    """A handler failed on `day`: the play stops there, giving nothing (W10)."""

    def __init__(self, day: dt.date, failures: Sequence[HandlerFailure]) -> None:
        super().__init__(f'{len(failures)} handler failures on {day}: {list(failures)}')
        self.day = day
        self.failures = tuple(failures)


SHOP_ZONE: Final = ZoneInfo('Europe/Oslo')
"""The shop's own day: an export is filed under the night (the Oslo date) it ran in."""


@dataclass(frozen=True)
class Snapshot:
    """The app's tables, the feed's and the provider's rows, and the last `csv_export`'s files
    (empty if none had run), at one moment of the play."""

    tables: Mapping[str, Rows]
    feed: Rows
    payments: Rows
    csv: Mapping[str, str]


@dataclass(frozen=True)
class Played:
    """Everything one play gives, correct and uncut."""

    tables: Mapping[str, Rows]
    """The app's tables (`Jobs.app_tables()`), read once at the end."""
    feed: Rows
    """`order_events`, as the feed took them."""
    payments: Rows
    """`payments`, as the provider sent them."""
    outside: tuple[Rows, ...]
    """fx_rates, managers, web_events, product_codes, till_receipts, till_lines,
    till_members: the outside systems' writers over the world's facts."""
    csv: Mapping[str, str]
    """`csv_export`'s files, file name to text; empty if it did not run."""
    csv_exports: Mapping[dt.date, Mapping[str, str]]
    """Every `csv_export` of the play, by the night (Oslo date) it ran in."""
    relays: tuple[tuple[dt.datetime, Relayed], ...]
    """Each relay run's moment and result, in order."""
    seed: int
    handles: Mapping[str, str]
    """Each handle the world names, to the id its call returned (V4)."""
    snapshots: Mapping[dt.datetime, Snapshot]
    """For each snapshot moment asked for, what the play held after its last step at or
    before that moment."""


def play(
    world: World | None = None,
    *,
    seed: int = 0,
    until: dt.datetime | None = None,
    store: Literal['memory', 'sqlite'] = 'memory',
    notifier: Notifier | None = None,
    labels: Labels | None = None,
    snapshots: Sequence[dt.datetime] = (),
) -> Played:
    """Play the world's steps before `until` (all, if None) and read what they made.

    The world is tiny's (`script.world()`) if none is given. Each snapshot moment is read
    after the last step at or before it; one at or after `until` is refused. Raises
    PlayStopped after a day whose steps left a handler failure. An error a step raises (a
    ShopError is a script bug) carries a note naming the step. The seed is kept; the week
    draws nothing random (W15).
    """
    if world is None:
        world = script.world()
    if until is not None and until.utcoffset() is None:
        raise ValueError(f'until is a moment with its offset: {until!r}')
    for moment in snapshots:
        if moment.utcoffset() is None:
            raise ValueError(f'a snapshot is a moment with its offset: {moment!r}')
        if until is not None and moment >= until:
            raise ValueError(f'a snapshot at {moment} is not before until {until}')
    pending = sorted(set(snapshots))
    steps = world.steps  # the ids are the whole world's, so a cut play is a prefix
    if not steps:
        raise ValueError('a world has one step or more')
    clock = FakeClock(steps[0].at)
    settings = Settings(
        database_url=Url('sqlite:///:memory:'),
        provider_url=Url('https://provider.example.invalid'),
        provider_key=Secret('not-a-key'),
        relay_batch=RELAY_BATCH,
    )
    connection = sqlite3.connect(':memory:') if store == 'sqlite' else None
    try:
        if connection is None:
            held = memory_store(clock=clock, price_ttl=settings.price_ttl)
        else:
            held = sqlite_store(connection, clock=clock, price_ttl=settings.price_ttl)
        feed = Feed(clock, refuse=world.refuse)
        provider = FakeProvider(refund_ids=world.refund_ids)
        log = ProviderLog(provider)
        sequence = SequentialIds({}, skip=script.skip_set(steps))
        listed_ids = script.scripted_ids(steps)
        draws = _DrawLog(ScriptedIds(listed_ids, sequence))
        listed = frozenset(listed_ids)
        wirings: tuple[tuple[Source, Ids], ...] = (
            ('scripted', draws),
            ('simulator', sequence),
        )
        apps: dict[str, App] = {}
        for source, ids in wirings:
            apps[source] = wire(
                settings,
                held,
                clock=clock,
                ids=ids,
                source=source,
                feed=feed,
                provider=provider,
                notifier=notifier if notifier is not None else FakeNotifier(),
                labels=labels if labels is not None else FakeLabels(),
            )
        state = _State(log)
        taken: dict[dt.datetime, Snapshot] = {}

        def snap_before(moment: dt.datetime | None) -> None:
            """Read each pending snapshot whose moment is before `moment` (None: all)."""
            while pending and (moment is None or pending[0] < moment):
                taken[pending.pop(0)] = Snapshot(
                    tables=apps['scripted'].jobs.app_tables(),
                    feed=feed.rows(),
                    payments=log.rows(),
                    csv=MappingProxyType(dict(state.csv)),
                )

        for n, step, after in _ahead(steps, until):
            snap_before(step.at)
            clock.set(step.at)
            try:
                _do(apps[step.wiring], step, state)
            except Exception as error:
                error.add_note(f'in step {n} at {step.at.isoformat()}: {step.action!r}')
                raise
            if step.wiring == 'scripted':
                _check_draws(n, step, draws.take(), listed)
            if after is None or after.at.date() != step.at.date():
                failures = apps['scripted'].failures() + apps['simulator'].failures()
                if failures:
                    raise PlayStopped(step.at.date(), failures)
        snap_before(None)
        return Played(
            tables=apps['scripted'].jobs.app_tables(),
            feed=feed.rows(),
            payments=log.rows(),
            outside=(
                outside.fx_rates(world.fx),
                outside.managers(world.managers),
                outside.web_events(world.tracker),
                outside.product_codes(world.till_codes),
                outside.till_receipts(world.till_receipts),
                outside.till_lines(world.till_lines),
                outside.till_members(world.till_members),
            ),
            csv=MappingProxyType(dict(state.csv)),
            csv_exports=MappingProxyType(dict(state.csv_exports)),
            relays=tuple(state.relays),
            seed=seed,
            handles=MappingProxyType(dict(state.handles)),
            snapshots=MappingProxyType(taken),
        )
    finally:
        if connection is not None:
            connection.close()


def _ahead(
    steps: Sequence[Step], until: dt.datetime | None
) -> Iterator[tuple[int, Step, Step | None]]:
    """Each step before `until` with its index and the step after it (None after the last),
    one step of look-ahead; ValueError for a step before the one it follows."""
    run = iter(steps)
    step = next(run, None)
    n = 0
    while step is not None and (until is None or step.at < until):
        after = next(run, None)
        if after is not None and after.at < step.at:
            raise ValueError(f'step {n + 1} at {after.at} is before step {n} at {step.at}')
        if after is not None and until is not None and after.at >= until:
            after = None
        yield n, step, after
        step, n = after, n + 1


@dataclass
class _State:
    """What the steps hand on to later steps and to the result."""

    log: ProviderLog
    handles: dict[str, str] = field(default_factory=dict)
    """Each handle to the id its call returned."""
    lines: dict[OrderId, tuple[LineId, ...]] = field(default_factory=dict)
    """Each order placed or credited in the play, with its lines in order."""
    shipments: dict[OrderId, ShipmentId] = field(default_factory=dict)
    relays: list[tuple[dt.datetime, Relayed]] = field(default_factory=list)
    csv: Mapping[str, str] = field(default_factory=dict)
    csv_exports: dict[dt.date, Mapping[str, str]] = field(default_factory=dict)

    def keep(self, handle: str | None, made: str) -> None:
        """`made` under `handle`; a handle names one call only."""
        if handle is None:
            return
        if handle in self.handles:
            raise ValueError(f'handle {handle!r} names {self.handles[handle]} already')
        self.handles[handle] = made

    def customer(self, ref: CustomerRef) -> CustomerId:
        """The customer a step names: its id, or the id its handle was given."""
        if isinstance(ref, CustomerId):
            return ref
        return CustomerId(self._handle(ref))

    def order(self, ref: OrderRef) -> OrderId:
        """The order a step names: its id, or the id its handle was given."""
        if isinstance(ref, OrderId):
            return ref
        return OrderId(self._handle(ref))

    def subscription(self, ref: SubscriptionRef) -> SubscriptionId:
        """The subscription a step names: its id, or the id its handle was given."""
        if isinstance(ref, SubscriptionId):
            return ref
        return SubscriptionId(self._handle(ref))

    def line(self, order_id: OrderId, line: LineId | int) -> LineId:
        """The line a credit names: its id, or the order's `line`th line from 1."""
        if isinstance(line, LineId):
            return line
        held = self.lines.get(order_id)
        if held is None:
            raise ValueError(f'{order_id} was never placed in this play')
        if not 1 <= line <= len(held):
            raise ValueError(f'{order_id} has {len(held)} lines, not a line {line}')
        return held[line - 1]

    def _handle(self, handle: str) -> str:
        found = self.handles.get(handle)
        if found is None:
            raise ValueError(f'handle {handle!r} is named before any call made it')
        return found


def _check_draws(
    n: int, step: Step, drawn: Mapping[IdKind, Sequence[str]], listed: frozenset[IdKind]
) -> None:
    """The step drew exactly the scripted ids it lists, in order (W6).

    A kind the script lists for some step is compared for every scripted
    step, so a step that draws one it does not list is caught too; the
    kinds that fall to the sequence are not compared. One id more or
    fewer would shift every later scripted id.
    """
    for kind in sorted(listed):
        want = list(step.ids.get(kind, ()))
        got = list(drawn.get(kind, ()))
        if got != want:
            raise ValueError(
                f'step {n} at {step.at.isoformat()} ({step.action!r}) drew {kind} {got}; '
                f'it lists {want}'
            )


def _message(
    state: _State, payment_id: PaymentId, ref: OrderRef, amount: Money, paid_on: dt.date
) -> PaymentMessage:
    """The provider's message for an order played here."""
    order_id = state.order(ref)
    if order_id not in state.lines:
        raise ValueError(f'{payment_id} pays {order_id}, never placed')
    return PaymentMessage(payment_id, order_id, amount, paid_on)


def _do(app: App, step: Step, state: _State) -> None:
    """Give the step to the one call it names."""
    match step.action:
        case Register(name, email, country, postal_code, account_kind, handle):
            made = app.customers.register(
                name,
                email=email,
                country=country,
                postal_code=postal_code,
                account_kind=account_kind,
            )
            state.keep(handle, made.value)
        case Change(customer_id, email, country, postal_code):
            app.customers.change(
                state.customer(customer_id), email=email, country=country, postal_code=postal_code
            )
        case Erase(customer_id):
            app.customers.erase(state.customer(customer_id))
        case Subscribe(customer_id, product_id, handle):
            made = app.subscriptions.subscribe(state.customer(customer_id), product_id=product_id)
            state.keep(handle, made.value)
        case CancelSubscription(ref, reason):
            app.subscriptions.cancel(state.subscription(ref), reason=reason)
        case Skip(ref, reason):
            app.subscriptions.skip(state.subscription(ref), reason=reason)
        case Pause(ref, reason):
            app.subscriptions.pause(state.subscription(ref), reason=reason)
        case Resume(ref, reason):
            app.subscriptions.resume(state.subscription(ref), reason=reason)
        case AddCategory(name, parent_id, sort_order):
            app.catalogue.add_category(name, parent_id=parent_id, sort_order=sort_order)
        case AddProduct(name, category_id, details):
            app.catalogue.add_product(name, category_id=category_id, details=details)
        case SetPrice(product_id, price, valid_from):
            app.catalogue.set_price(product_id, price=price, valid_from=valid_from)
        case SetCost(product_id, valid_from, green, packaging, roasting):
            app.catalogue.set_cost(
                product_id,
                valid_from=valid_from,
                green=green,
                packaging=packaging,
                roasting=roasting,
            )
        case SetSubscriberDiscount(percent, valid_from):
            app.catalogue.set_subscriber_discount(percent, valid_from=valid_from)
        case AddCampaign(name, discount_pct, first_day, last_day, product_ids):
            app.catalogue.add_campaign(
                name,
                discount_pct=discount_pct,
                first_day=first_day,
                last_day=last_day,
                product_ids=product_ids,
            )
        case Roast(product_id, bags):
            app.stock.roast(product_id, bags=bags)
        case Stocktake(product_id, on_hand):
            app.stock.stocktake(product_id, on_hand=on_hand)
        case WriteOff(product_id, qty):
            app.stock.write_off(product_id, qty=qty)
        case BuyGreen(origin, kg, nok_per_kg):
            app.stock.buy_green(origin=origin, kg=kg, nok_per_kg=nok_per_kg)
        case Place(order, handle, customer):
            if customer is not None:
                order = dataclasses.replace(order, customer_id=state.customer(customer))
            head = app.checkout.place(order).head
            state.lines[head.order_id] = tuple(line.line_id for line in head.lines)
            state.keep(handle, head.order_id.value)
        case Pay(payment_id, ref, amount, paid_on):
            message = _message(state, payment_id, ref, amount, paid_on)
            if amount.amount < 0 and message not in state.log.refunds(on=paid_on):
                raise ValueError(f'{payment_id} is a refund the provider never sent: {message}')
            app.payments.handle_message(state.log.deliver(message))
        case Settle(payment_id, ref, amount, paid_on):
            message = _message(state, payment_id, ref, amount, paid_on)
            app.payments.settle(state.log.deliver(message))
        case Invoice(ref):
            app.payments.invoice(state.order(ref))
        case Credit(ref, line, handle):
            sale = state.order(ref)
            credit = app.checkout.credit_for(sale, line_id=state.line(sale, line))
            state.lines[credit] = ()  # its one line is the sequence's; nothing names it
            state.keep(handle, credit.value)
        case Refund(ref):
            app.payments.refund(state.order(ref))
        case Ship(ref, promised_by):
            order_id = state.order(ref)
            state.shipments[order_id] = app.fulfilment.ship(order_id, promised_by=promised_by)
        case Deliver(ref):
            order_id = state.order(ref)
            if order_id not in state.shipments:
                raise ValueError(f'{order_id} is delivered, never shipped')
            app.fulfilment.deliver(state.shipments[order_id])
        case CancelOrder(ref, reason):
            app.checkout.cancel(state.order(ref), reason=reason)
        case Relay():
            state.relays.append((step.at, app.jobs.relay()))
        case ShipBags():
            app.jobs.ship_subscription_bags()
        case CountAtClose():
            app.jobs.count_at_close()
        case NightlyExtract():
            app.jobs.nightly_extract()
        case CsvExport():
            state.csv = app.jobs.csv_export()
            night = step.at.astimezone(SHOP_ZONE).date()
            if night in state.csv_exports:
                raise ValueError(f'two csv exports in the night of {night}')
            state.csv_exports[night] = state.csv
        case other:
            raise TypeError(f'no call for {other!r}')
