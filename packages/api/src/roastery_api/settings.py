"""The API's own settings: `SHOP_API_*`, read once at the edge (ADR 0016).

The shop's `Settings.from_env` refuses any `ROASTERY_*` name it does not read, so the API's
names have their own prefix and their own reader, with the shop's rule: every problem
listed at once, an unknown `SHOP_API_*` name refused.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Self

from roastery.settings import Settings, SettingsError

PREFIX: Final = 'SHOP_API_'
"""What every name of an API setting starts with."""

STATE_URL: Final = 'SHOP_API_STATE_URL'
CORS_ORIGINS: Final = 'SHOP_API_CORS_ORIGINS'
SANDBOX: Final = 'SHOP_API_SANDBOX'
DEFAULT_ORIGINS: Final = 'http://localhost:5173'

PLACEHOLDERS: Final[Mapping[str, str]] = MappingProxyType(
    {
        'ROASTERY_PROVIDER_URL': 'https://provider.example.invalid',
        'ROASTERY_PROVIDER_KEY': 'not-a-key',
    }
)
"""The provider settings `Settings` requires and `FakeProvider` never reads (F9): given
when the environment does not set them, as the play does."""


@dataclass(frozen=True)
class ApiSettings:
    """Where the state db is, which origins may call, and whether the sandbox is mounted."""

    state_url: str
    cors_origins: tuple[str, ...] = (DEFAULT_ORIGINS,)
    sandbox: bool = False

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> Self:
        """The settings in `env`; SettingsError naming every problem."""
        problems: list[str] = []
        state_url = env.get(STATE_URL, '')
        if not state_url:
            problems.append(f'{STATE_URL} is missing')
        elif not state_url.startswith('sqlite:///'):
            problems.append(f'{STATE_URL} must start sqlite:///')
        origins = tuple(
            each.strip()
            for each in env.get(CORS_ORIGINS, DEFAULT_ORIGINS).split(',')
            if each.strip()
        )
        if '*' in origins:
            problems.append(f'{CORS_ORIGINS} takes no wildcard')
        sandbox = env.get(SANDBOX, '0')
        if sandbox not in ('0', '1'):
            problems.append(f'{SANDBOX} must be 0 or 1')
        problems += [
            f'{name} is not a setting'
            for name in sorted(env)
            if name.startswith(PREFIX) and name not in (STATE_URL, CORS_ORIGINS, SANDBOX)
        ]
        if problems:
            raise SettingsError(problems)
        return cls(state_url, origins, sandbox == '1')


def shop_settings(env: Mapping[str, str]) -> Settings:
    """The shop's `Settings` from `env`, the provider placeholders filled in (F9)."""
    return Settings.from_env({**PLACEHOLDERS, **env})
