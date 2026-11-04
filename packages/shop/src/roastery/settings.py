"""The shop's settings: read once, from a mapping, at the edge.

Settings.from_env takes the environment as an argument; nothing
here reads os.environ, so a test passes a dict. Each field is read
from ROASTERY_ and its name in capitals (price_ttl is
ROASTERY_PRICE_TTL) and parsed by its type. Every problem is found
before one error is raised, so a deploy fails once, with the whole
list (ADR 0014).
"""

from __future__ import annotations

import dataclasses
import re
import typing
from collections.abc import (
    Callable,
    Collection,
    Mapping,
    Sequence,
)
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Final, NewType, Self
from zoneinfo import ZoneInfo

PREFIX: Final = 'ROASTERY_'
"""What every name of a shop setting starts with."""

Url = NewType('Url', str)
"""A URL with a scheme; it may hold a password."""

Secret = NewType('Secret', str)
"""A key or a password: never shown."""

Positive = NewType('Positive', int)
"""A whole number of 1 or more."""


class SettingsError(ValueError):
    """Settings that are missing or malformed: all of them, at once."""

    def __init__(self, problems: Sequence[str]) -> None:
        super().__init__('; '.join(problems))
        self.problems = tuple(problems)


def url(text: str) -> Url:
    """A URL with a scheme; the message never shows the value.

    A URL can hold a password, and an error is logged.
    """
    if not re.fullmatch(r'[a-z][a-z0-9+.-]*://\S+', text):
        raise ValueError('must be a URL such as scheme://host')
    return Url(text)


def secret(text: str) -> Secret:
    """Any text that is not empty; the message never shows it."""
    if not text:
        raise ValueError('must not be empty')
    return Secret(text)


def whole(text: str) -> int:
    """A whole number of 0 or more, as digits only."""
    if not re.fullmatch(r'[0-9]+', text):
        raise ValueError(f'must be a whole number, got {text!r}')
    return int(text)


def positive(text: str) -> Positive:
    """A whole number of 1 or more."""
    number = whole(text)
    if number < 1:
        raise ValueError(f'must be 1 or more, got {text!r}')
    return Positive(number)


def zone(text: str) -> ZoneInfo:
    """A zone name `zoneinfo` knows."""
    try:
        return ZoneInfo(text)
    except (KeyError, ValueError) as error:
        raise ValueError(
            f'must be a zone name, got {text!r}'
        ) from error


PARSERS: Final[Mapping[object, Callable[[str], object]]] = (
    MappingProxyType(
        {
            Url: url,
            Secret: secret,
            int: whole,
            Positive: positive,
            ZoneInfo: zone,
        }
    )
)
"""How a setting's text is parsed, by the type of its field."""


def oslo() -> ZoneInfo:
    """The shop's zone when none is set: Bergen keeps Oslo's."""
    return ZoneInfo('Europe/Oslo')


@dataclass(frozen=True)
class Settings:
    """The shop's settings; a field with a default is optional.

    The URLs and the key are left out of repr and str; asdict, vars
    and the attribute still give them. A field type PARSERS lacks
    is a bug, and raises KeyError.
    """

    database_url: Url = field(repr=False)
    provider_url: Url = field(repr=False)
    provider_key: Secret = field(repr=False)
    price_ttl: int = 300
    shop_zone: ZoneInfo = field(default_factory=oslo)
    relay_batch: Positive = Positive(5)

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> Self:
        """The settings in `env`, each parsed by its field's type.

        Raises SettingsError naming every problem: the fields' in
        their order, then the ROASTERY_ names that no field reads.
        """
        hints = typing.get_type_hints(cls)
        values: dict[str, Any] = {}
        problems: list[str] = []
        for each in dataclasses.fields(cls):
            name = env_name(each.name)
            if name not in env:
                if _required(each):
                    problems.append(f'{name} is missing')
                continue
            parse = PARSERS[hints[each.name]]
            try:
                values[each.name] = parse(env[name])
            except ValueError as error:
                problems.append(f'{name} {error}')
        problems += unknown_names(env)
        if problems:
            raise SettingsError(problems)
        return cls(**values)


def env_name(name: str) -> str:
    """The environment name of a field: ROASTERY_ and its capitals."""
    return PREFIX + name.upper()


def _required(each: dataclasses.Field[Any]) -> bool:
    """A field with no default and no default factory."""
    missing = dataclasses.MISSING
    return each.default is missing and each.default_factory is missing


def unknown_names(
    env: Mapping[str, str], known: Collection[str] | None = None
) -> list[str]:
    """ROASTERY_ names that no field reads, sorted: most are typos.

    `known` is the names the fields read; None is those of Settings.
    """
    if known is None:
        known = [env_name(f.name) for f in dataclasses.fields(Settings)]
    return [
        f'{name} is not a setting'
        for name in sorted(env)
        if name.startswith(PREFIX) and name not in known
    ]
