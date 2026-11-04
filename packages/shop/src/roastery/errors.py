"""The closed family of refusals (ADR 0006, C20).

A command the shop's rules refuse raises a member of ShopError and
writes nothing. No other module defines one. Each member keeps the
ids it names as attributes, so a test or the simulator can check
them without reading the message.
"""

from __future__ import annotations

import datetime as dt

from roastery.ids import (
    CustomerId,
    LineId,
    OrderId,
    PaymentId,
    ProductId,
    SubscriptionId,
)


class ShopError(Exception):
    """A command the shop's rules refuse; nothing was written."""


class IllegalTransition(ShopError):
    def __init__(
        self, order_id: OrderId, state: str, action: str
    ) -> None:
        self.order_id = order_id
        self.state = state
        self.action = action
        super().__init__(
            f'order {order_id} is {state}: it cannot {action}'
        )


class IllegalSubscriptionMove(ShopError):
    def __init__(
        self,
        subscription_id: SubscriptionId,
        state: str,
        action: str,
    ) -> None:
        self.subscription_id = subscription_id
        self.state = state
        self.action = action
        super().__init__(
            f'subscription {subscription_id} is {state}: '
            f'it cannot {action}'
        )


class NotShippable(ShopError):
    def __init__(self, order_id: OrderId) -> None:
        self.order_id = order_id
        super().__init__(f'order {order_id} is a counter sale')


class NoAddress(ShopError):
    def __init__(self, order_id: OrderId) -> None:
        self.order_id = order_id
        super().__init__(
            f'order {order_id} has no postal code to ship to'
        )


class NotCreditable(ShopError):
    def __init__(self, order_id: OrderId, state: str) -> None:
        self.order_id = order_id
        self.state = state
        super().__init__(
            f'order {order_id} is {state}: it cannot be credited'
        )


class AlreadyCredited(ShopError):
    def __init__(self, line_id: LineId) -> None:
        self.line_id = line_id
        super().__init__(f'line {line_id} is already credited')


class NoOpenInvoice(ShopError):
    def __init__(self, order_id: OrderId) -> None:
        self.order_id = order_id
        super().__init__(f'order {order_id} has no open invoice')


class NothingToRefund(ShopError):
    def __init__(self, order_id: OrderId) -> None:
        self.order_id = order_id
        super().__init__(f'order {order_id} was never paid')


class PaymentMismatch(ShopError):
    def __init__(self, payment_id: PaymentId) -> None:
        self.payment_id = payment_id
        super().__init__(
            f'payment {payment_id} is already held with another amount'
        )


class KeyReused(ShopError):
    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(f'key {key!r} was used with another body')


class DuplicateId(ShopError):
    def __init__(self, kind: str, value: str) -> None:
        self.kind = kind
        self.value = value
        super().__init__(f'the store already holds {kind} {value}')


class UnknownId(ShopError):
    def __init__(self, kind: str, value: str) -> None:
        self.kind = kind
        self.value = value
        super().__init__(f'the store holds no {kind} {value}')


class NoSuchCustomer(ShopError):
    def __init__(self, customer_id: CustomerId) -> None:
        self.customer_id = customer_id
        super().__init__(f'there is no customer {customer_id}')


class UnknownProduct(ShopError):
    def __init__(self, product_id: ProductId) -> None:
        self.product_id = product_id
        super().__init__(f'the shop lists no product {product_id}')


class WrongKind(ShopError):
    def __init__(self, product_id: ProductId, kind: str) -> None:
        self.product_id = product_id
        self.kind = kind
        super().__init__(f'product {product_id} is {kind}')


class NoPrice(ShopError):
    def __init__(self, product_id: ProductId, on: dt.date) -> None:
        self.product_id = product_id
        self.on = on
        super().__init__(f'product {product_id} has no price on {on}')


class OutOfStock(ShopError):
    def __init__(
        self, product_id: ProductId, wanted: int, on_hand: int
    ) -> None:
        self.product_id = product_id
        self.wanted = wanted
        self.on_hand = on_hand
        super().__init__(
            f'product {product_id}: {wanted} wanted, {on_hand} on hand'
        )


class PeriodOverlap(ShopError):
    def __init__(
        self, table: str, key: str, valid_from: dt.date
    ) -> None:
        self.table = table
        self.key = key
        self.valid_from = valid_from
        super().__init__(
            f'{table} {key}: a period starting {valid_from} '
            f'starts inside the open one'
        )
