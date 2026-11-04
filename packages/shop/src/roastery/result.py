"""A question with two kinds of answer returns Ok or Err."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class Ok[T]:
    """The answer, found."""

    value: T


@dataclass(frozen=True)
class Err[E]:
    """The answer is a reason, not a value."""

    error: E


def partition[T, E](
    results: Iterable[Ok[T] | Err[E]],
) -> tuple[list[T], list[E]]:
    """The values of the Ok and the errors of the Err, in order."""
    values: list[T] = []
    errors: list[E] = []
    for result in results:
        match result:
            case Ok(value):
                values.append(value)
            case Err(error):
                errors.append(error)
    return values, errors
