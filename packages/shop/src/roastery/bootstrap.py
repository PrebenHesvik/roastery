"""The one place that wires: each port gets its adapter here.

The services, the core and the jobs name only ports. Which store,
which feed, which provider and which ids stand behind them is
chosen once, by the caller, and passed to `wire`; `wire` is the
same for every caller (ADR 0013). The registry, the bus and the
protected provider are built inside it, a new set per wiring, so
nothing is module state. Nothing in roastery imports this module
but a caller at the very edge: the entry point, a test or the
simulator.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sqlite3
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from roastery import exports, fulfilment, outbox
from roastery.checkout import Checkout
from roastery.clock import local_date
from roastery.customers import Customers
from roastery.events import (
    CollectingBus,
    EventBus,
    HandlerFailure,
    OrderInvoiced,
    OrderPaid,
)
from roastery.fakes import (
    ClosedFeed,
    FakeClock,
    FakeLabels,
    FakeNotifier,
    FakeProvider,
)
from roastery.fulfilment import Fulfilment
from roastery.listing import Catalogue
from roastery.payments import Payments
from roastery.pipeline import Rows
from roastery.ports import (
    Clock,
    IdKind,
    Ids,
    Labels,
    Notifier,
    PaymentProvider,
    Relayed,
    Source,
    StatusFeed,
    Store,
    UnitOfWork,
)
from roastery.pricing import standard_rules
from roastery.repository import create_tables
from roastery.resilience import CircuitBreaker, ProtectedProvider
from roastery.settings import Settings, SettingsError
from roastery.stock import Stock, count_closed_day
from roastery.subscriptions import (
    Subscriptions,
    ship_subscription_bags,
)
from roastery.uow import InMemoryStore, SqliteStore

ATTEMPTS: Final = 3
"""Tries of one refund, the first included (ADR 0011)."""

BACKOFF: Final = 0.5
"""Seconds before the second try; doubled before each next one."""

JITTER_SEED: Final = 0
"""The seed of the retry's jitter: the same waits on every run."""

FAILURE_THRESHOLD: Final = 3
"""Refunds failed in a row, after all their tries, that open the
breaker."""

RESET_AFTER_SECONDS: Final = 60
"""How long the breaker stays open before it tries once again."""

CLI_JOBS: Final = (
    'count_at_close',
    'csv_export',
    'nightly_extract',
)
"""The jobs `main` runs: those that draw no id and publish no
event, so the cli needs no script and no handler. Not `relay`:
the cli has no feed to send to, and a relay would still form and
commit batches that can never go."""

SQLITE_URL: Final = 'sqlite:///'
"""What ROASTERY_DATABASE_URL starts with; the path follows."""


def _no_sleep(seconds: float) -> None:
    """The retry's wait: none. The wall clock never runs here."""


class Jobs:
    """Bound by wire to the store, the feed and the settings.

    No argument, no clock: the wired Clock gives the moment.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        *,
        clock: Clock,
        ids: Ids,
        feed: StatusFeed,
        settings: Settings,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids
        self._feed = feed
        self._settings = settings

    def relay(self) -> Relayed:
        """Outbox batches to the StatusFeed (ADR 0009)."""
        return outbox.relay(
            self._uow, self._feed, size=self._settings.relay_batch
        )

    def ship_subscription_bags(self) -> int:
        """This month's bags not yet shipped, skipped or
        paused; a shipped movement each. The bags shipped."""
        return ship_subscription_bags(
            self._uow, self._clock, self._ids, self._settings.shop_zone
        )

    def count_at_close(self) -> int:
        """stock_daily for the last closed shop day: every
        product's balance by the UTC day, stamped at the day's
        close (18:00 in the shop zone), not at now (C23). The
        rows written."""
        return count_closed_day(
            self._uow, self._clock, self._settings.shop_zone
        )

    def nightly_extract(self) -> int:
        """customer_extracts for tonight. The rows written."""
        day = local_date(self._clock.now(), self._settings.shop_zone)
        return exports.nightly_extract(self._uow, day)

    def csv_export(self) -> Mapping[str, str]:
        """raw_customers and raw_lines: file name to text."""
        return exports.csv_export(self._uow)

    def app_tables(self) -> Mapping[str, Rows]:
        """Contract A's app-database tables as the app holds them:
        table name to its rows, sorted by key (W2)."""
        return exports.app_tables(self._uow)


@dataclass(frozen=True)
class App:
    customers: Customers
    catalogue: Catalogue
    checkout: Checkout
    payments: Payments
    fulfilment: Fulfilment
    subscriptions: Subscriptions
    stock: Stock
    jobs: Jobs
    events: CollectingBus  # the wiring's one bus (C29)

    def failures(self) -> tuple[HandlerFailure, ...]:
        """What the handlers raised since wire, in order (C29):
        self.events.failures(). The calls that published the
        events returned, and their rows are kept."""
        return self.events.failures()


def memory_store(*, clock: Clock, price_ttl: int) -> InMemoryStore:
    """The app's tables as dicts, with their one price cache
    (C31, C38). For tests, walks and the week alone (C32)."""
    return InMemoryStore(clock=clock, price_ttl=price_ttl)


def sqlite_store(
    connection: sqlite3.Connection, *, clock: Clock, price_ttl: int
) -> SqliteStore:
    """The app's tables on the connection, with their one price
    cache (C38). For month and full (C32)."""
    store = SqliteStore(connection, clock=clock, price_ttl=price_ttl)
    create_tables(connection)
    return store


def _protect(
    provider: PaymentProvider, clock: Clock
) -> PaymentProvider:
    """The provider with the retry inside and the breaker outside.

    A decline is never retried; an outage is tried ATTEMPTS times
    with the same key, and the breaker reads the wired clock. The
    wait between tries is none: the wall clock is the caller's.
    """
    breaker = CircuitBreaker(
        clock,
        FAILURE_THRESHOLD,
        dt.timedelta(seconds=RESET_AFTER_SECONDS),
    )
    return ProtectedProvider(
        provider,
        breaker,
        attempts=ATTEMPTS,
        backoff=BACKOFF,
        sleep=_no_sleep,
        seed=JITTER_SEED,
    )


def wire(
    settings: Settings,
    store: Store,
    *,
    clock: Clock,
    ids: Ids,
    source: Source,
    feed: StatusFeed,
    provider: PaymentProvider,
    notifier: Notifier,
    labels: Labels,
) -> App:
    """The services on the store, the same for every caller
    (ADR 0013). No TTL: the cache came with the store, built
    from the same clock and Settings (C38). The simulator
    calls it twice over one store."""
    uow = store.unit_of_work(source)
    zone = settings.shop_zone

    def confirm(event: OrderPaid | OrderInvoiced) -> None:
        fulfilment.confirm(event, uow=uow, notifier=notifier)

    def label(event: OrderPaid | OrderInvoiced) -> None:
        fulfilment.label(event, uow=uow, labels=labels)

    bus = EventBus()
    bus.subscribe(OrderPaid, confirm)
    bus.subscribe(OrderPaid, label)
    bus.subscribe(OrderInvoiced, confirm)
    bus.subscribe(OrderInvoiced, label)
    events = CollectingBus(bus)
    rules = standard_rules().rules
    protected = _protect(provider, clock)
    return App(
        customers=Customers(uow, clock, ids, zone),
        catalogue=Catalogue(uow, ids),
        checkout=Checkout(uow, clock, ids, events, rules),
        payments=Payments(uow, clock, ids, events, protected),
        fulfilment=Fulfilment(uow, clock, ids, zone),
        subscriptions=Subscriptions(uow, clock, ids, zone),
        stock=Stock(uow, clock, ids, zone),
        jobs=Jobs(
            uow, clock=clock, ids=ids, feed=feed, settings=settings
        ),
        events=events,
    )


class _NoIds:
    """The cli's ids: its jobs draw none, so a draw is a bug."""

    def next(self, kind: IdKind) -> str:
        raise RuntimeError(f'the cli draws no id, asked for {kind}')


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='roastery', description='Run one nightly job.'
    )
    parser.add_argument('job', choices=CLI_JOBS)
    parser.add_argument(
        '--at',
        required=True,
        type=dt.datetime.fromisoformat,
        help='the moment to run at, with its offset',
    )
    parser.add_argument(
        '--out',
        type=Path,
        help='the folder csv_export writes its files into',
    )
    return parser


def main(argv: Sequence[str], env: Mapping[str, str]) -> int:
    """Read the settings, wire on sqlite, run the cli's command.

    The command is given the moment to run at (`--at`): main
    wires a FakeClock set to it, so a rerun gives the same rows.
    No cli job relays, so the feed is ClosedFeed; the notifier,
    the labels and the provider are fakes, since no cli job
    publishes an event or asks for a refund.
    """
    args = _parser().parse_args(list(argv))
    if args.at.tzinfo is None:
        print('--at needs an offset, such as +00:00', file=sys.stderr)
        return 2
    if args.job == 'csv_export' and args.out is None:
        print('csv_export needs --out', file=sys.stderr)
        return 2
    try:
        settings = Settings.from_env(env)
    except SettingsError as error:
        print(error, file=sys.stderr)
        return 2
    if not settings.database_url.startswith(SQLITE_URL):
        print(
            f'the database URL must start {SQLITE_URL}', file=sys.stderr
        )
        return 2
    clock = FakeClock(args.at)
    connection = sqlite3.connect(
        settings.database_url.removeprefix(SQLITE_URL)
    )
    try:
        store = sqlite_store(
            connection, clock=clock, price_ttl=settings.price_ttl
        )
        app = wire(
            settings,
            store,
            clock=clock,
            ids=_NoIds(),
            source='visitor',
            feed=ClosedFeed(),
            provider=FakeProvider(refund_ids=()),
            notifier=FakeNotifier(),
            labels=FakeLabels(),
        )
        done = getattr(app.jobs, args.job)()
    finally:
        connection.close()
    if args.job == 'csv_export':
        args.out.mkdir(parents=True, exist_ok=True)
        for name, text in sorted(done.items()):
            (args.out / name).write_text(
                text, encoding='utf-8', newline='\n'
            )
        print(f'wrote {len(done)} files to {args.out}')
        return 0
    print(done)
    return 0


def main_from_os() -> int:
    """The script entry: the only place the environment is read."""
    return main(sys.argv[1:], os.environ)
