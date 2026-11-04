"""What the shop sells: products, their kinds and the category tree."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Literal

from roastery.ids import CategoryId, ProductId

Kind = Literal['beans', 'equipment']
"""As `products.kind` holds it."""

KINDS: Final[tuple[Kind, ...]] = ('beans', 'equipment')


@dataclass(frozen=True)
class BeanDetails:
    """What only beans have."""

    weight_g: int
    origin: str
    roast: str
    process: str

    def __post_init__(self) -> None:
        if isinstance(self.weight_g, bool) or not isinstance(
            self.weight_g, int
        ):
            raise TypeError('weight must be whole grams')
        if self.weight_g <= 0:
            raise ValueError('weight must be above zero')


@dataclass(frozen=True)
class EquipmentDetails:
    """What only equipment has."""

    warranty_months: int
    material: str

    def __post_init__(self) -> None:
        if isinstance(self.warranty_months, bool) or not isinstance(
            self.warranty_months, int
        ):
            raise TypeError('warranty must be whole months')
        if self.warranty_months < 0:
            raise ValueError('warranty must not be negative')


@dataclass(frozen=True)
class Product:
    """A product the shop lists.

    `weight_g` is null for equipment: it does not apply.
    """

    product_id: ProductId
    name: str
    kind: Kind
    category_id: CategoryId
    weight_g: int | None

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f'kind must be one of {KINDS}')
        if (self.kind == 'beans') != (self.weight_g is not None):
            raise ValueError('only beans have a weight')


@dataclass(frozen=True)
class Category:
    """One node of the category tree; the roots have no parent."""

    category_id: CategoryId
    name: str
    parent_id: CategoryId | None
    sort_order: int


def category_path(
    category_id: CategoryId,
    categories: Mapping[CategoryId, Category],
) -> tuple[Category, ...]:
    """The categories from the root down to `category_id`.

    A tree that names a missing parent, or loops, is a bug in
    the data: ValueError.
    """
    path: list[Category] = []
    here: CategoryId | None = category_id
    while here is not None:
        if here not in categories or len(path) > len(categories):
            raise ValueError(f'no path to category {category_id}')
        path.append(categories[here])
        here = categories[here].parent_id
    return tuple(reversed(path))
