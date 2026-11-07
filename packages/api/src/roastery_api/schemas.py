"""The API's bodies as pydantic models, so the OpenAPI document is whole (ADR 0016, 0019).

The requests are parsed by these models; the replies are the handlers' plain bodies, and
the models here only describe them for the document that 7.3 turns into TypeScript. An
amount is `Amount`: the number as text, never a float, and its currency.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from roastery_api.fx import Currency, DueOnDelivery, PriceLabel

Country = Literal['DK', 'FI', 'NO', 'SE']
Kind = Literal['beans', 'equipment']
OrderStatus = Literal['placed', 'paid', 'invoiced', 'shipped', 'delivered', 'cancelled']


class _Body(BaseModel):
    """A request body: keys it does not name (a `price`, above all) are not read."""

    model_config = ConfigDict(extra='ignore')


# Shared ---------------------------------------------------------------------------------


class Amount(BaseModel):
    """Money: the amount as text with its decimals, and the currency."""

    amount: str = Field(examples=['129.00'])
    currency: str = Field(examples=['NOK'])


class Problem(BaseModel):
    """An error, as RFC 9457's problem+json. Switch on `code`, never on `title`."""

    model_config = ConfigDict(extra='allow')

    type: str = 'about:blank'
    title: str
    status: int
    code: str = Field(examples=['OutOfStock'])
    detail: str | None = None


# The catalogue --------------------------------------------------------------------------


class ProductInfo(BaseModel):
    product_id: str = Field(examples=['P-10'])
    name: str
    kind: Kind
    category_id: str
    weight_g: int | None


class BeanDetails(BaseModel):
    weight_g: int
    origin: str
    roast: str
    process: str


class EquipmentDetails(BaseModel):
    warranty_months: int
    material: str


class ListedProduct(BaseModel):
    """A product on Norway's day. No price (`unit_price` null): coming soon."""

    product: ProductInfo
    details: BeanDetails | EquipmentDetails
    unit_price: Amount | None
    percent: int | None
    in_stock: bool
    display_price: Amount | None


class ProductList(BaseModel):
    country: Country
    currency: Currency
    price_label: PriceLabel
    products: list[ListedProduct]


class ProductPage(ListedProduct):
    country: Country
    currency: Currency
    price_label: PriceLabel


# The quote ------------------------------------------------------------------------------


class CartItem(_Body):
    """A cart's line: a product and a quantity. No price: the server prices it."""

    product_id: str = Field(examples=['P-10'])
    qty: int = Field(ge=1, examples=[2])


class QuoteRequest(_Body):
    country: Country
    items: list[CartItem] = Field(min_length=1)


class QuotedLine(BaseModel):
    product: ProductInfo
    qty: int
    unit_price: Amount
    percent: int
    gross: Amount
    vat: Amount
    rate: str | None
    on_hand: int
    display_unit_price: Amount
    display_gross: Amount


class VatDisplay(BaseModel):
    """What the page says of VAT (ADR 0018). The words are the storefront's copy."""

    price_label: PriceLabel
    due_on_delivery: DueOnDelivery
    norwegian_vat: Amount | None
    import_vat: Amount | None
    display_import_vat: Amount | None


class Quote(BaseModel):
    country: Country
    day: dt.date
    scheme: Literal['domestic', 'export']
    lines: list[QuotedLine]
    gross: Amount
    vat: Amount
    currency: Currency
    display_gross: Amount
    vat_display: VatDisplay


# Checkout -------------------------------------------------------------------------------


class CheckoutRequest(_Body):
    """A guest's order: the cart, the total the buyer confirmed (NOK), and the contact."""

    country: Country
    items: list[CartItem] = Field(min_length=1)
    total: Amount
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(max_length=254, pattern=r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
    street: str = Field(min_length=1, max_length=200)
    postal_code: str = Field(min_length=1, max_length=12, examples=['5003'])
    city: str = Field(min_length=1, max_length=100)

    @field_validator('postal_code')
    @classmethod
    def _digits(cls, value: str) -> str:
        """A Swedish `113 51` is `11351`: the shop keeps digits only."""
        return ''.join(value.split())


class PlacedOrder(BaseModel):
    """The order placed; `token` is its private link."""

    order_id: str
    country: Country
    total: Amount
    token: str
    currency: Currency
    display_total: Amount


# The sandbox payment ----------------------------------------------------------------------


class SandboxPaymentRequest(_Body):
    """A test payment of the order the token links to. No amount: the order's is paid."""

    token: str = Field(min_length=1)
    outcome: Literal['approve', 'decline', 'outage']


class SandboxPayment(BaseModel):
    payment_id: str = Field(examples=['PAY-1'])
    order_id: str
    status: OrderStatus
    amount: Amount


# The order ------------------------------------------------------------------------------


class OrderLine(BaseModel):
    line_id: str
    product_id: str
    qty: int
    unit_price: Amount
    display_unit_price: Amount


class Order(BaseModel):
    order_id: str
    status: OrderStatus
    country: Country
    day: dt.date
    lines: list[OrderLine]
    total: Amount
    currency: Currency
    display_total: Amount
