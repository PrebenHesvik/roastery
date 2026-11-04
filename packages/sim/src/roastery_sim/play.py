"""Play the script through the shop app (6.4, W1, W10).

One clock, one store and two wirings of the app over it (C7, ADR
0007): `scripted` draws the week's hand-written ids, `simulator` the
shared sequence. Each step of `script.steps()` is one call of
contract B, made at the step's moment through its wiring. After each
UTC day's last step the handlers' failures of both wirings are read;
any failure stops the play (W10). What comes back is the app's
tables, the feed's and the provider's rows and the outside systems'
rows, all correct: the faults and the cut are later modules'.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal

from roastery.bootstrap import App, memory_store, sqlite_store, wire
from roastery.events import HandlerFailure
from roastery.fakes import FakeClock, FakeLabels, FakeNotifier, FakeProvider
from roastery.ids import OrderId, ShipmentId
from roastery.pipeline import Rows
from roastery.ports import Labels, Notifier, Relayed, Source
from roastery.repository import ScriptedIds, SequentialIds
from roastery.settings import Positive, Secret, Settings, Url

from roastery_sim import outside, script
from roastery_sim.feed import Feed
from roastery_sim.outside import ProviderLog
from roastery_sim.script import (
    AddCampaign,
    AddCategory,
    AddProduct,
    CancelOrder,
    CancelSubscription,
    Change,
    CountAtClose,
    CsvExport,
    Deliver,
    Erase,
    NightlyExtract,
    Pay,
    Place,
    Register,
    Relay,
    Roast,
    SetPrice,
    Ship,
    Step,
    Stocktake,
    Subscribe,
)

RELAY_BATCH = Positive(5)
"""Events per relay batch (W5): the Settings default, stated."""


class PlayStopped(Exception):
    """A handler failed on `day`: the play stops there, giving nothing (W10)."""

    def __init__(self, day: dt.date, failures: Sequence[HandlerFailure]) -> None:
        super().__init__(f'{len(failures)} handler failures on {day}: {list(failures)}')
        self.day = day
        self.failures = tuple(failures)


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
    till_members: the outside systems' writers over the script's facts."""
    csv: Mapping[str, str]
    """`csv_export`'s files, file name to text; empty if it did not run."""
    relays: tuple[tuple[dt.datetime, Relayed], ...]
    """Each relay run's moment and result, in order."""
    seed: int


def play(
    *,
    seed: int = 0,
    until: dt.datetime | None = None,
    store: Literal['memory', 'sqlite'] = 'memory',
    notifier: Notifier | None = None,
    labels: Labels | None = None,
) -> Played:
    """Play the script's steps before `until` (all, if None) and read what they made.

    Raises PlayStopped after a day whose steps left a handler failure. An
    error a step raises (a ShopError is a script bug) carries a note naming
    the step. The seed is kept; the week draws nothing random (W15).
    """
    if until is not None and until.utcoffset() is None:
        raise ValueError(f'until is a moment with its offset: {until!r}')
    steps = script.steps()  # the ids are the whole script's, so a cut play is a prefix
    run = tuple(step for step in steps if until is None or step.at < until)
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
        feed = Feed(clock, refuse=script.REFUSE)
        provider = FakeProvider(refund_ids=())
        log = ProviderLog(provider)
        sequence = SequentialIds({}, skip=script.skip_set(steps))
        scripted_ids = ScriptedIds(script.scripted_ids(steps), sequence)
        wirings: tuple[tuple[Source, ScriptedIds | SequentialIds], ...] = (
            ('scripted', scripted_ids),
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
        state = _State(log, _year_orders(steps))
        for n, step in enumerate(run):
            clock.set(step.at)
            try:
                _do(apps[step.wiring], n, step, state)
            except Exception as error:
                error.add_note(f'in step {n} at {step.at.isoformat()}: {step.action!r}')
                raise
            last_of_day = n + 1 == len(run) or run[n + 1].at.date() != step.at.date()
            if last_of_day:
                failures = apps['scripted'].failures() + apps['simulator'].failures()
                if failures:
                    raise PlayStopped(step.at.date(), failures)
        return Played(
            tables=apps['scripted'].jobs.app_tables(),
            feed=feed.rows(),
            payments=log.rows(),
            outside=(
                outside.fx_rates(script.FX),
                outside.managers(script.MANAGERS),
                outside.web_events(script.TRACKER),
                outside.product_codes(script.TILL_CODES),
                outside.till_receipts(script.TILL_RECEIPTS),
                outside.till_lines(script.TILL_LINES),
                outside.till_members(script.TILL_MEMBERS),
            ),
            csv=MappingProxyType(dict(state.csv)),
            relays=tuple(state.relays),
            seed=seed,
        )
    finally:
        if connection is not None:
            connection.close()


@dataclass
class _State:
    """What the steps hand on to later steps and to the result."""

    log: ProviderLog
    year: Mapping[int, OrderId]
    """A `simulator` place's step index to the order its payment names."""
    placed: set[OrderId] = field(default_factory=set)
    shipments: dict[OrderId, ShipmentId] = field(default_factory=dict)
    relays: list[tuple[dt.datetime, Relayed]] = field(default_factory=list)
    csv: Mapping[str, str] = field(default_factory=dict)


def _year_orders(steps: Sequence[Step]) -> Mapping[int, OrderId]:
    """For each place of C-01's year (the `simulator` wiring), the order id
    the wiring's next step, its payment, names (W31)."""
    simulator = [(n, step) for n, step in enumerate(steps) if step.wiring == 'simulator']
    named: dict[int, OrderId] = {}
    for (n, step), (_, after) in zip(simulator, simulator[1:], strict=False):
        if isinstance(step.action, Place):
            if not isinstance(after.action, Pay):
                raise ValueError(f'a place of the year is not followed by its payment: {step}')
            named[n] = after.action.message.order_id
    return named


def _do(app: App, n: int, step: Step, state: _State) -> None:
    """Give the step, the script's `n`th, to the one call it names."""
    match step.action:
        case Register(name, email, country, postal_code, account_kind):
            app.customers.register(
                name,
                email=email,
                country=country,
                postal_code=postal_code,
                account_kind=account_kind,
            )
        case Change(customer_id, email, country, postal_code):
            app.customers.change(customer_id, email=email, country=country, postal_code=postal_code)
        case Erase(customer_id):
            app.customers.erase(customer_id)
        case Subscribe(customer_id, product_id):
            app.subscriptions.subscribe(customer_id, product_id=product_id)
        case CancelSubscription(subscription_id, reason):
            app.subscriptions.cancel(subscription_id, reason=reason)
        case AddCategory(name, parent_id, sort_order):
            app.catalogue.add_category(name, parent_id=parent_id, sort_order=sort_order)
        case AddProduct(name, category_id, details):
            app.catalogue.add_product(name, category_id=category_id, details=details)
        case SetPrice(product_id, price, valid_from):
            app.catalogue.set_price(product_id, price=price, valid_from=valid_from)
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
        case Place(order):
            order_id = app.checkout.place(order).head.order_id
            named = state.year.get(n)
            if named is not None and order_id != named:
                raise ValueError(f'the place gave {order_id}; its payment names {named}')
            state.placed.add(order_id)
        case Pay(message):
            if message.order_id not in state.placed:
                raise ValueError(f'{message.payment_id} pays {message.order_id}, never placed')
            app.payments.handle_message(state.log.deliver(message))
        case Ship(order_id, promised_by):
            state.shipments[order_id] = app.fulfilment.ship(order_id, promised_by=promised_by)
        case Deliver(order_id):
            if order_id not in state.shipments:
                raise ValueError(f'{order_id} is delivered, never shipped')
            app.fulfilment.deliver(state.shipments[order_id])
        case CancelOrder(order_id, reason):
            app.checkout.cancel(order_id, reason=reason)
        case Relay():
            state.relays.append((step.at, app.jobs.relay()))
        case CountAtClose():
            app.jobs.count_at_close()
        case NightlyExtract():
            app.jobs.nightly_extract()
        case CsvExport():
            state.csv = app.jobs.csv_export()
        case other:
            raise TypeError(f'no call for {other!r}')
