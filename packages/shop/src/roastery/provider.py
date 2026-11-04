"""The `PaymentProvider` port on the provider's SDK.

The SDK counts in minor units and speaks camelCase; the app speaks
`Money` and `PaymentId`. This adapter is the one place the two meet:
kroner become minor units on the way out, and the SDK's errors become
the port's on the way back (ADR 0002, ADR 0011).
"""

from __future__ import annotations

from decimal import Decimal

from roastery.ids import PaymentId
from roastery.money import Money
from roastery.ports import ProviderRefused, ProviderUnavailable
from roastery.provider_sdk import ProviderApiError, ProviderClient

MINOR = Decimal(100)
"""Minor units to the unit, for every currency the shop sells in."""

DECLINED = 402
"""The status of a decline."""

DOWN = 500
"""The first status of a provider that is down."""


def to_minor(money: Money) -> int:
    """Whole minor units: 899.00 NOK is 89900, rounded to the øre."""
    return int(money.to_ore().amount * MINOR)


def to_money(minor: int, currency: str) -> Money:
    """The money of a count of minor units: 51698 SEK is 516.98."""
    return Money(Decimal(minor).scaleb(-2), currency)


class ProviderPayments:
    """The port, on a `ProviderClient`."""

    def __init__(self, client: ProviderClient) -> None:
        self._client = client

    def refund(
        self, payment_id: PaymentId, amount: Money, *, key: str
    ) -> PaymentId:
        """Ask for `amount` back; the refund's id.

        The amount is what goes back, above zero. A 402 is a decline
        (ProviderRefused); a status of 500 or more, or a call that
        never got through, is ProviderUnavailable. Any other status
        is a mistake in the request, and the SDK's error is raised.
        """
        if amount.amount <= 0:
            raise ValueError(f'a refund is above zero: {amount}')
        request = {
            'amountMinor': to_minor(amount),
            'currency': amount.currency,
            'idempotencyKey': key,
            'paymentId': str(payment_id),
        }
        try:
            reply = self._client.createRefund(request)
        except ProviderApiError as error:
            if error.status == DECLINED:
                raise ProviderRefused(str(error)) from error
            if error.status >= DOWN:
                raise ProviderUnavailable(str(error)) from error
            raise
        except (ConnectionError, TimeoutError) as error:
            raise ProviderUnavailable(str(error)) from error
        return PaymentId(str(reply['refundId']))
