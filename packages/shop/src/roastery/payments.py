"""Payments: the provider's messages, invoices, and the one refund.

A message is recorded once, keyed on its `payment_id`: the same
message again gets the same `Receipt` and writes nothing, and the
same id with another order or amount is refused (`PaymentMismatch`).
It is compared with the payment stored under its id, never with the
order's total: a payment is in the customer's currency (ADR 0011).
`refund` is the app's one call out, through the `PaymentProvider`
port; it writes nothing, and the provider's negative message comes
back through `handle_message`.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from roastery import order as orders
from roastery.errors import (
    IllegalTransition,
    NoOpenInvoice,
    NothingToRefund,
    PaymentMismatch,
)
from roastery.events import (
    CollectingBus,
    OrderInvoiced,
    OrderPaid,
    StatusChanged,
)
from roastery.ids import EventId, OrderId, PaymentId
from roastery.money import Money
from roastery.order import (
    Cancelled,
    Order,
    Payment,
    PaymentMessage,
    invoice_open,
)
from roastery.ports import Clock, Ids, PaymentProvider, UnitOfWork


@dataclass(frozen=True)
class Receipt:
    """The stored reply: the same for every delivery."""

    payment_id: PaymentId
    order_id: OrderId
    status: str  # the order's feed word after it


class Payments:
    def __init__(
        self,
        uow: UnitOfWork,
        clock: Clock,
        ids: Ids,
        events: CollectingBus,
        provider: PaymentProvider,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids
        self._events = events
        self._provider = provider

    def handle_message(self, message: PaymentMessage) -> Receipt:
        """Recorded once, keyed on payment_id. A placed order
        is paid; a refund to a credit order pays it; a refund
        to a cancelled order is recorded with no event."""
        now = self._clock.now()
        payment = _payment(message)
        with self._uow as uow:
            held = uow.payments.find(message.payment_id)
            if held is not None:
                _same(held, payment)
                return _paid_receipt(
                    held, uow.orders.get(held.order_id)
                )
            order = uow.orders.get(message.order_id)
            refund = payment.amount.amount < 0
            if refund and isinstance(order, Cancelled):
                uow.payments.add(payment)
                uow.commit()
                return _paid_receipt(payment, order)
            credit = order.head.credit_of is not None
            if refund != credit:
                action = 'refund' if refund else 'pay'
                raise IllegalTransition(
                    order.head.order_id, orders.status(order), action
                )
            paid = orders.pay(order, payment.payment_id)
            uow.payments.add(payment)
            uow.orders.save(paid)
            self._status(uow, paid.head.order_id, 'paid', now)
            uow.commit()
        self._events.publish(OrderPaid(paid.head.order_id))
        return _paid_receipt(payment, paid)

    def invoice(self, order_id: OrderId) -> None:
        """A consumer's placed order put on invoice (S13)."""
        now = self._clock.now()
        with self._uow as uow:
            invoiced = orders.invoice(uow.orders.get(order_id))
            uow.orders.save(invoiced)
            self._status(uow, order_id, 'invoiced', now)
            uow.commit()
        self._events.publish(OrderInvoiced(order_id))

    def settle(self, message: PaymentMessage) -> Receipt:
        """An open invoice paid: a payment, no status event."""
        payment = _payment(message)
        with self._uow as uow:
            held = uow.payments.find(message.payment_id)
            if held is not None:
                _same(held, payment)
                order = uow.orders.get(held.order_id)
                return _receipt(held, orders.status(order))
            order = uow.orders.get(message.order_id)
            if not invoice_open(
                order, uow.payments.of(message.order_id)
            ):
                raise NoOpenInvoice(message.order_id)
            uow.payments.add(payment)
            uow.commit()
        return _receipt(payment, orders.status(order))

    def refund(self, order_id: OrderId) -> PaymentId:
        """The one outbound call: the money back, asked of the
        provider for a credit order (from the sale it returns)
        or a cancelled paid order. Key 'refund-<order_id>',
        retried; a decline is never retried. Writes nothing:
        the provider's message comes to handle_message."""
        with self._uow as uow:
            order = uow.orders.get(order_id)
            sale_id = order.head.credit_of
            if sale_id is not None:
                taken = _taken(uow.payments.of(sale_id))
                amount = -_total(order)
            elif isinstance(order, Cancelled):
                taken = _taken(uow.payments.of(order_id))
                amount = None if taken is None else taken.amount
            else:
                taken, amount = None, None
        if taken is None or amount is None:
            raise NothingToRefund(order_id)
        return self._provider.refund(
            taken.payment_id, amount, key=f'refund-{order_id}'
        )

    def _status(
        self,
        uow: UnitOfWork,
        order_id: OrderId,
        word: orders.Status,
        now: dt.datetime,
    ) -> None:
        uow.outbox.add(
            StatusChanged(
                EventId(self._ids.next('event')), order_id, word, now
            )
        )


def _payment(message: PaymentMessage) -> Payment:
    """The app's record of a message (A11)."""
    return Payment(
        message.payment_id,
        message.order_id,
        message.amount,
        message.paid_on,
    )


def _same(held: Payment, payment: Payment) -> None:
    """PaymentMismatch unless a redelivery names the same order
    and amount as the payment stored under its id."""
    if (held.order_id, held.amount) != (
        payment.order_id,
        payment.amount,
    ):
        raise PaymentMismatch(payment.payment_id)


def _receipt(payment: Payment, word: str) -> Receipt:
    return Receipt(payment.payment_id, payment.order_id, word)


def _paid_receipt(payment: Payment, order: Order) -> Receipt:
    """What handle_message answered when it took the payment.

    Worked out from the payment, not from the order's state now,
    so a redelivery after the order shipped gets the same reply:
    a refund to a cancelled order left it cancelled, and any other
    payment it took made its order paid.
    """
    refund = payment.amount.amount < 0
    if refund and isinstance(order, Cancelled):
        return _receipt(payment, 'cancelled')
    return _receipt(payment, 'paid')


def _taken(payments: tuple[Payment, ...]) -> Payment | None:
    """The payment that took money for an order, if any."""
    return next((p for p in payments if p.amount.amount > 0), None)


def _total(order: Order) -> Money:
    """The sum of the order's lines: negative for a credit order."""
    lines = order.head.lines
    total = lines[0].unit_price.times(lines[0].qty)
    for line in lines[1:]:
        total += line.unit_price.times(line.qty)
    return total
