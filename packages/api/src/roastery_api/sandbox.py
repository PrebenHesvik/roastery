"""The sandbox payment: the API plays the payment provider (ADR 0018, F5).

`POST /sandbox/payments` names an order's token and an outcome, never an amount. The
amount is the stored order's, in NOK. Approve hands the provider's message to the real
`Payments.handle_message`, so the order is paid by the same path a real payment takes;
decline is `ProviderRefused` (402) and outage `ProviderUnavailable` (503), both before any
write. No money moves.
"""

from __future__ import annotations

from typing import Any, Final, Literal

from roastery.api import JSON, STATUS, Handler, Request, RequestValidationError, Response
from roastery.clock import ZONES, local_date
from roastery.ids import PaymentId
from roastery.order import PaymentMessage
from roastery.ports import Clock, Ids, ProviderRefused, ProviderUnavailable

from roastery_api.live import Deps, render
from roastery_api.state import State, UnknownToken

Outcome = Literal['approve', 'decline', 'outage']

OUTCOMES: Final[tuple[Outcome, ...]] = ('approve', 'decline', 'outage')


def payments_handler(state: State, ids: Ids, clock: Clock) -> Handler[Deps]:
    """The sandbox's handler, on the state db's links and counter."""

    def sandbox_payments(request: Request, deps: Deps) -> Response:
        try:
            return _pay(request, deps)
        except (*STATUS, UnknownToken) as error:
            return render(error)

    def _pay(request: Request, deps: Deps) -> Response:
        body: Any = request.get('body')
        if not isinstance(body, dict):
            raise RequestValidationError('the body must be an object')
        token, outcome = body.get('token'), body.get('outcome')
        if not isinstance(token, str) or outcome not in OUTCOMES:
            raise RequestValidationError('the body needs a token and an outcome')
        order_id = state.order_of(token)
        shown = deps.storefront.order(order_id)
        if outcome == 'decline':
            raise ProviderRefused('the sandbox declined the payment')
        if outcome == 'outage':
            raise ProviderUnavailable('the sandbox provider is down')
        message = PaymentMessage(
            PaymentId(ids.next('payment')),  # type: ignore[arg-type]
            order_id,
            shown.total,
            local_date(clock.now(), ZONES[shown.country]),
        )
        deps.provider.take(message)
        receipt = deps.payments.handle_message(message)
        return {
            'status': 201,
            'content_type': JSON,
            'body': {
                'payment_id': str(receipt.payment_id),
                'order_id': str(receipt.order_id),
                'status': receipt.status,
                'amount': {'amount': str(shown.total.amount), 'currency': 'NOK'},
            },
        }

    return sandbox_payments
