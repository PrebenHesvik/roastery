"""The same key twice gives one effect (ADR 0013, 0016).

`once(handler, keys)` wraps a handler. A new key runs it and keeps
the reply; the same key with the same body returns the kept reply
and does not run it again; the same key with another body is
`KeyReused`. A 5xx reply is not kept, so a retry after an outage
runs again; a handler that raises keeps nothing either.

The body is what is hashed, not the whole request: a retry's
`guest` number or role differ and must not make a new body.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol

from roastery.api import (
    Handler,
    Request,
    RequestValidationError,
    Response,
    plain,
)
from roastery.errors import KeyReused


@dataclass(frozen=True)
class Stored:
    """A reply kept under a key, with the hash of its body."""

    body_hash: str
    reply: Response


class Keys(Protocol):
    """The key store; the API gives it a sqlite one."""

    def get(self, scope: str, key: str) -> Stored | None: ...

    def put(self, scope: str, key: str, stored: Stored) -> None: ...


class MemoryKeys:
    """The keys in a dict: the twin for tests and walks."""

    def __init__(self) -> None:
        self._held: dict[tuple[str, str], Stored] = {}

    def get(self, scope: str, key: str) -> Stored | None:
        return self._held.get((scope, key))

    def put(self, scope: str, key: str, stored: Stored) -> None:
        self._held[(scope, key)] = stored


def digest(body: object) -> str:
    """The hash of a body, whatever the order of its keys."""
    text = json.dumps(
        plain(body), sort_keys=True, separators=(',', ':')
    )
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def once[D](
    handler: Handler[D], keys: Keys, *, scope: str | None = None
) -> Handler[D]:
    """The handler, run once per key. The scope is the route: the
    handler's name unless given, so one key on two routes is two
    entries. No key in the request is a RequestValidationError."""
    where = scope or getattr(handler, '__name__', 'handler')

    def wrapped(request: Request, deps: D) -> Response:
        key = request.get('key')
        if not isinstance(key, str) or not key:
            raise RequestValidationError('Idempotency-Key needed')
        body_hash = digest(request.get('body', {}))
        kept = keys.get(where, key)
        if kept is not None:
            if kept.body_hash != body_hash:
                raise KeyReused(key)
            return kept.reply
        reply = handler(request, deps)
        status = reply['status']
        if isinstance(status, int) and status < 500:
            keys.put(where, key, Stored(body_hash, reply))
        return reply

    return wrapped
