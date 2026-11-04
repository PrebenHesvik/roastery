"""Failing politely: retry a few times, and stop calling a dead end.

`retry` tries a call again after a wait that doubles, spread by a
seeded jitter. A `CircuitBreaker` counts failures in a row, and after
enough of them refuses calls for a while, so a provider that is down
is not called on and on. Both are given what they need from outside:
the sleep, and the `Clock` port, so a test waits for nothing and the
wall clock is never read (ADR 0013).
"""

from __future__ import annotations

import datetime as dt
import random
from collections.abc import Callable
from typing import Literal

from roastery.ids import PaymentId
from roastery.money import Money
from roastery.ports import Clock, PaymentProvider, ProviderUnavailable

Transient = (ConnectionError, TimeoutError)
"""The errors worth trying again: the next call may work.

`ProviderUnavailable` is a ConnectionError, so it is one of them;
`ProviderRefused` is not, and is never retried."""


def delay(
    attempt: int, backoff: float, jitter: random.Random | None = None
) -> float:
    """The wait after a failed attempt: backoff, then twice, then 4x.

    With jitter, the wait is a random part of that, from 0 up to it,
    rounded to two places, so callers do not all retry at once. The
    generator is the caller's and seeded (`random.Random(seed)`), so
    the same seed gives the same waits. There is no cap.
    """
    full = backoff * 2 ** (attempt - 1)
    if jitter is None:
        return full
    return round(jitter.uniform(0, full), 2)


def retry[T](
    call: Callable[[], T],
    *,
    attempts: int,
    backoff: float,
    sleep: Callable[[float], None],
    jitter: random.Random | None = None,
    on: tuple[type[Exception], ...] = Transient,
) -> T:
    """The call's answer, after at most `attempts` tries.

    Only an error in `on` is tried again; any other is raised at
    once. If the last try fails too, its error is raised.
    """
    if attempts < 1:
        raise ValueError(f'attempts must be 1 or more, got {attempts}')
    for attempt in range(1, attempts):
        try:
            return call()
        except on:
            sleep(delay(attempt, backoff, jitter))
    return call()


class CircuitOpen(ProviderUnavailable):
    """The breaker is open: the call was refused, not made."""


State = Literal['closed', 'open', 'half-open']
"""Where a breaker is: calling, refusing, or trying once again."""


class CircuitBreaker:
    """Stops calling a service that keeps failing, then tries again.

    Closed: calls go through, and `failure_threshold` failures in a
    row open it. Open: each call is refused with CircuitOpen, without
    calling, until `reset_after` has passed on the clock. Half-open:
    the next call is a trial; if it works the breaker closes, and if
    it fails it opens again. Only errors in `on` count. The state
    lives in this object, so each process has a breaker of its own,
    and it serves one caller at a time.
    """

    def __init__(
        self,
        clock: Clock,
        failure_threshold: int,
        reset_after: dt.timedelta,
        on: tuple[type[Exception], ...] = Transient,
    ) -> None:
        if failure_threshold < 1 or reset_after <= dt.timedelta(0):
            raise ValueError(
                'failure_threshold must be 1 or more and reset_after'
                f' above 0, got {failure_threshold}, {reset_after}'
            )
        self._clock = clock
        self._threshold = failure_threshold
        self._reset_after = reset_after
        self._on = on
        self._failures = 0
        self._opened_at: dt.datetime | None = None

    @property
    def state(self) -> State:
        if self._opened_at is None:
            return 'closed'
        waited = self._clock.now() - self._opened_at
        if waited < self._reset_after:
            return 'open'
        return 'half-open'

    def call[T](self, call: Callable[[], T]) -> T:
        """The call's answer; refused at once while it is open."""
        state = self.state
        if state == 'open':
            raise CircuitOpen(
                f'open after {self._failures} failures'
                f' (reset after {self._reset_after})'
            )
        try:
            answer = call()
        except self._on:
            self._failures += 1
            tripped = self._failures >= self._threshold
            if state == 'half-open' or tripped:
                self._opened_at = self._clock.now()
            raise
        self._failures = 0
        self._opened_at = None
        return answer


class ProtectedProvider:
    """A `PaymentProvider` with retry and a breaker around another.

    One refund is up to `attempts` calls to the provider, each with
    the same key, so a retry cannot refund twice. The breaker counts
    a refund that failed after all its tries as one failure. A
    decline (ProviderRefused) is never retried and never counted.
    """

    def __init__(
        self,
        provider: PaymentProvider,
        breaker: CircuitBreaker,
        *,
        attempts: int,
        backoff: float,
        sleep: Callable[[float], None],
        seed: int,
    ) -> None:
        self._provider = provider
        self._breaker = breaker
        self._attempts = attempts
        self._backoff = backoff
        self._sleep = sleep
        self._jitter = random.Random(seed)

    def refund(
        self, payment_id: PaymentId, amount: Money, *, key: str
    ) -> PaymentId:
        """The refund's id; the provider's own errors pass through."""

        def attempt() -> PaymentId:
            return retry(
                lambda: self._provider.refund(
                    payment_id, amount, key=key
                ),
                attempts=self._attempts,
                backoff=self._backoff,
                sleep=self._sleep,
                jitter=self._jitter,
            )

        return self._breaker.call(attempt)
