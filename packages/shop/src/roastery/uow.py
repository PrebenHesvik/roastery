"""The two stores and their units of work (ADR 0003).

A store is the app's tables: a set of dicts or a sqlite connection.
A unit of work is one transaction over all of them, stamping every
row it writes with its `source`. Leaving its block always undoes
what was not committed. Two units over one store see each other's
commits; they are used one at a time, and opening one while another
is open raises RuntimeError, on both stores.

Each store holds the one price cache of its prices (C31, C38). A
unit of work evicts the products whose price it changed when its
commit has succeeded, never when it is undone (A22).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any, Self

from roastery.cache import CachedPrices, UnitPrices
from roastery.outbox import InMemoryOutbox, SqliteOutbox
from roastery.ports import Clock, Source
from roastery.repository import (
    MemoryCatalogue,
    MemoryCosts,
    MemoryCustomers,
    MemoryExtracts,
    MemoryOrders,
    MemoryPayments,
    MemoryPrices,
    MemoryPurchases,
    MemoryRules,
    MemoryShipments,
    MemoryStock,
    MemorySubscriptions,
    MemoryVatRates,
    SqliteCatalogue,
    SqliteCosts,
    SqliteCustomers,
    SqliteExtracts,
    SqliteOrders,
    SqlitePayments,
    SqlitePrices,
    SqlitePurchases,
    SqliteRules,
    SqliteShipments,
    SqliteStock,
    SqliteSubscriptions,
    SqliteVatRates,
    Tables,
    memory_sources,
    sqlite_sources,
)


class _Gate:
    """Whether a unit of work of the store is open."""

    def __init__(self) -> None:
        self.is_open = False

    def enter(self) -> None:
        if self.is_open:
            raise RuntimeError('a unit of work of this store is open')
        self.is_open = True

    def leave(self) -> None:
        self.is_open = False


class InMemoryUnitOfWork:
    """The units of work on dicts.

    It copies each table's dict when the block opens and at each
    commit, and puts the copies back when the block ends, so what
    was written after the last commit is gone. The repositories
    hold the dicts themselves, and the copies go back into them.
    """

    def __init__(
        self,
        tables: Tables,
        gate: _Gate,
        cache: CachedPrices,
        source: Source,
    ) -> None:
        self.source = source
        self._tables = tables
        self._gate = gate
        self._kept: dict[str, dict[Any, Any]] = {}
        self.customers = MemoryCustomers(tables, source)
        self.orders = MemoryOrders(tables, source)
        self.payments = MemoryPayments(tables, source)
        self.catalogue = MemoryCatalogue(tables, source)
        self._prices = UnitPrices(MemoryPrices(tables, source), cache)
        self.prices = self._prices
        self.costs = MemoryCosts(tables, source)
        self.rules = MemoryRules(tables, source)
        self.subscriptions = MemorySubscriptions(tables, source)
        self.stock = MemoryStock(tables, source)
        self.shipments = MemoryShipments(tables, source)
        self.purchases = MemoryPurchases(tables, source)
        self.vat_rates = MemoryVatRates(tables, source)
        self.extracts = MemoryExtracts(tables, source)
        self.outbox = InMemoryOutbox(tables, source)
        self._open = False

    def __enter__(self) -> Self:
        self._gate.enter()
        self._kept = self._tables.snapshot()
        self._open = True
        return self

    def __exit__(self, *exc: object) -> None:
        self._tables.restore(self._kept)
        self._open = False
        self._prices.discarded()
        self._gate.leave()

    def commit(self) -> None:
        if not self._open:
            raise RuntimeError('commit needs an open unit of work')
        self._kept = self._tables.snapshot()
        self._prices.committed()

    def sources(self, table: str) -> Mapping[tuple[str, ...], Source]:
        return memory_sources(self._tables, table)


class SqliteUnitOfWork:
    """One sqlite transaction over every table.

    `__enter__` runs BEGIN; `commit` commits; `__exit__` always
    rolls back, so a write made after the last commit is undone
    too. It needs a connection in sqlite3's default mode, where a
    write after a commit opens a new transaction.
    """

    def __init__(
        self,
        connection: sqlite3.Connection,
        gate: _Gate,
        cache: CachedPrices,
        source: Source,
    ) -> None:
        self.source = source
        self._db = connection
        self._gate = gate
        self.customers = SqliteCustomers(connection, source)
        self.orders = SqliteOrders(connection, source)
        self.payments = SqlitePayments(connection, source)
        self.catalogue = SqliteCatalogue(connection, source)
        self._prices = UnitPrices(
            SqlitePrices(connection, source), cache
        )
        self.prices = self._prices
        self.costs = SqliteCosts(connection, source)
        self.rules = SqliteRules(connection, source)
        self.subscriptions = SqliteSubscriptions(connection, source)
        self.stock = SqliteStock(connection, source)
        self.shipments = SqliteShipments(connection, source)
        self.purchases = SqlitePurchases(connection, source)
        self.vat_rates = SqliteVatRates(connection, source)
        self.extracts = SqliteExtracts(connection, source)
        self.outbox = SqliteOutbox(connection, source)
        self._open = False

    def __enter__(self) -> Self:
        self._gate.enter()
        try:
            self._db.execute('BEGIN')
        except BaseException:
            self._gate.leave()
            raise
        self._open = True
        return self

    def __exit__(self, *exc: object) -> None:
        self._db.rollback()
        self._open = False
        self._prices.discarded()
        self._gate.leave()

    def commit(self) -> None:
        if not self._open:
            raise RuntimeError('commit needs an open unit of work')
        self._db.commit()
        self._prices.committed()

    def sources(self, table: str) -> Mapping[tuple[str, ...], Source]:
        return sqlite_sources(self._db, table)


class InMemoryStore:
    """The app's tables as dicts, with their one price cache.

    For tests, walks and the week alone (C32): the unit of work
    copies the dicts, which is quadratic over a long run.
    """

    def __init__(self, *, clock: Clock, price_ttl: int) -> None:
        self.tables = Tables.seeded()
        self.prices = CachedPrices(clock, price_ttl)
        self._gate = _Gate()

    def unit_of_work(self, source: Source) -> InMemoryUnitOfWork:
        return InMemoryUnitOfWork(
            self.tables, self._gate, self.prices, source
        )


class SqliteStore:
    """The app's tables on a connection, with their one price cache.

    The caller opens the connection, makes the tables with
    `create_tables`, and closes it. The connection must be in
    sqlite3's default transaction mode.
    """

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        clock: Clock,
        price_ttl: int,
    ) -> None:
        legacy = sqlite3.LEGACY_TRANSACTION_CONTROL
        if (
            connection.autocommit is not legacy
            or connection.isolation_level is None
        ):
            raise ValueError(
                "needs a connection in sqlite3's default mode"
            )
        self._db = connection
        self.prices = CachedPrices(clock, price_ttl)
        self._gate = _Gate()

    def unit_of_work(self, source: Source) -> SqliteUnitOfWork:
        return SqliteUnitOfWork(
            self._db, self._gate, self.prices, source
        )
