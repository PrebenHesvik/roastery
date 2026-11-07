"""The one wall clock, and the moment a request holds (ADR 0008, ADR 0016, F8).

The shop reads no wall clock: its services read the `Clock` port. `SystemClock` is the
only adapter in the repository that reads the real time. The services get a
`RequestClock`, which reads it once as a request takes the lock and gives that moment to
every `now()` until the request ends, so a checkout's re-quote, `register` and `place`
see one moment and price on one day.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from contextlib import contextmanager

from roastery.ports import Clock


class SystemClock:
    """The wall clock, in UTC."""

    def now(self) -> dt.datetime:
        return dt.datetime.now(dt.UTC)


class RequestClock:
    """One reading of `source` per request.

    Inside `held()` every `now()` gives the moment read when it began; outside one, `now()`
    reads `source` afresh. Not thread-safe on its own: the API's lock holds one request at
    a time.
    """

    def __init__(self, source: Clock) -> None:
        self._source = source
        self._moment: dt.datetime | None = None

    def now(self) -> dt.datetime:
        if self._moment is not None:
            return self._moment
        return self._source.now()

    @contextmanager
    def held(self) -> Iterator[dt.datetime]:
        """The request's moment, read once and held until the block ends."""
        if self._moment is not None:
            raise RuntimeError('a request moment is held already')
        self._moment = self._source.now()
        try:
            yield self._moment
        finally:
            self._moment = None
