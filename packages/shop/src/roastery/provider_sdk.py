"""A stand-in for the payment provider's SDK: its shape, not the app's.

It speaks the provider's language: camelCase names, amounts in
minor units (whole øre), and its own error with an HTTP status. It
imports nothing of roastery, as a package from PyPI would not. A real
SDK sends each call over the network; this one hands it to the
`handler` it is given, so a test answers without a network (ADR 0002).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Final

Handler = Callable[[str, Mapping[str, object]], Mapping[str, object]]
"""The wire: a route and a payload in, the provider's reply out."""

REFUNDS: Final = 'POST /v1/refunds'
"""The route a refund is sent to."""

FIELDS: Final[tuple[str, ...]] = (
    'amountMinor',
    'currency',
    'idempotencyKey',
    'paymentId',
)
"""What a refund request must hold, sorted."""


class ProviderApiError(Exception):
    """The provider's one error: an HTTP status and its message.

    402 is a decline; a status of 500 or more is the provider
    being down.
    """

    def __init__(self, status: int, message: str) -> None:
        super().__init__(f'[{status}] {message}')
        self.status = status


class ProviderClient:
    """Version 1 of the provider's client: one call, createRefund.

    A request names the payment as `paymentId`, counts `amountMinor`
    in whole minor units (89900 for 899.00 NOK) and carries an
    `idempotencyKey`. The reply holds a `refundId`.
    """

    def __init__(self, handler: Handler) -> None:
        self._handler = handler

    def createRefund(
        self, payload: Mapping[str, object]
    ) -> Mapping[str, object]:
        """Ask for money back; the reply names the refund."""
        self._check(payload)
        return self._handler(REFUNDS, dict(payload))

    def _check(self, payload: Mapping[str, object]) -> None:
        for field in FIELDS:
            if field not in payload:
                raise ProviderApiError(400, f'missing field {field}')
        minor = payload['amountMinor']
        if isinstance(minor, bool) or not isinstance(minor, int):
            raise ProviderApiError(
                422, 'amountMinor must be a whole number'
            )
        if minor < 1:
            raise ProviderApiError(422, 'amountMinor must be positive')
