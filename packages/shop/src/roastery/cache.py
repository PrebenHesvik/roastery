"""The price cache of a store: one per store, in front of its prices.

`DictCache` keeps values until a moment. `CachedPrices` reads a
product's price rows through it, for as long as the TTL says.
`UnitPrices` is what a unit of work offers as `prices`: it reads
through the store's cache and tells it, when the unit commits, which
products changed (C31, C38, A22). The cache is a concrete class: it
has one adapter, so a port would be hypothetical.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterable

from roastery.ids import ProductId
from roastery.ports import Clock, PriceRepository, Source
from roastery.pricing import Price


def price_key(product_id: ProductId) -> str:
    """The key a product's price rows are kept under."""
    return f'price:{product_id}'


class DictCache[V]:
    """Values by key, each good until the moment it was put with."""

    def __init__(self) -> None:
        self._entries: dict[str, tuple[V, dt.datetime]] = {}

    def get(self, key: str, now: dt.datetime) -> V | None:
        """The value, or None if there is none or it has expired."""
        entry = self._entries.get(key)
        if entry is None or now >= entry[1]:
            return None
        return entry[0]

    def put(self, key: str, value: V, until: dt.datetime) -> None:
        self._entries[key] = (value, until)

    def evict(self, key: str) -> None:
        self._entries.pop(key, None)

    def keys(self) -> tuple[str, ...]:
        """The keys held, expired or not, sorted."""
        return tuple(sorted(self._entries))


class CachedPrices:
    """A product's price rows, kept for `ttl` seconds (C31).

    One per store, built by the store from its clock and TTL, so
    every unit of work of the store, whatever its source, reads
    through it and sees one eviction.
    """

    def __init__(self, clock: Clock, ttl: int) -> None:
        self._clock = clock
        self._ttl = dt.timedelta(seconds=ttl)
        self._cache: DictCache[tuple[Price, ...]] = DictCache()

    def read(
        self,
        product_id: ProductId,
        load: Callable[[ProductId], tuple[Price, ...]],
    ) -> tuple[Price, ...]:
        """The rows from the cache, or from `load` and then kept."""
        now = self._clock.now()
        key = price_key(product_id)
        held = self._cache.get(key, now)
        if held is not None:
            return held
        loaded = load(product_id)
        self._cache.put(key, loaded, now + self._ttl)
        return loaded

    def evict(self, product_ids: Iterable[ProductId]) -> None:
        for product_id in product_ids:
            self._cache.evict(price_key(product_id))

    def keys(self) -> tuple[str, ...]:
        """The products held, for a test or a frame."""
        return self._cache.keys()


class UnitPrices:
    """The prices of one unit of work.

    A read goes through the store's cache, except for a product
    this unit has changed: its rows are not committed yet, so they
    are read from the table and never kept. `committed` evicts the
    changed products once the commit has succeeded; `discarded`
    forgets them when the unit ends, with nothing evicted.
    """

    def __init__(
        self, inner: PriceRepository, cache: CachedPrices
    ) -> None:
        self._inner = inner
        self._cache = cache
        self._changed: set[ProductId] = set()

    def of(self, product_id: ProductId) -> tuple[Price, ...]:
        if product_id in self._changed:
            return self._inner.of(product_id)
        return self._cache.read(product_id, self._inner.of)

    def add(self, price: Price) -> None:
        self._inner.add(price)
        self._changed.add(price.product_id)

    def close(self, product_id: ProductId, valid_to: dt.date) -> None:
        self._inner.close(product_id, valid_to)
        self._changed.add(product_id)

    def source_of(
        self, product_id: ProductId, valid_from: dt.date
    ) -> Source:
        """From the table: a source is never cached."""
        return self._inner.source_of(product_id, valid_from)

    def committed(self) -> None:
        """The commit succeeded: evict what this unit changed."""
        self._cache.evict(self._changed)
        self._changed.clear()

    def discarded(self) -> None:
        """The unit ended: its changes are undone or were kept."""
        self._changed.clear()
