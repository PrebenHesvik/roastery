"""The API's own sqlite tables, apart from the shop's (ADR 0016).

What the shop's data contract must not hold lives here: an order's private link, the
guest's real name, e-mail and street address, the id counter, the stored idempotent
replies and the orphan log. This db holds personal data: it is never committed, never
exported and never read by the spec.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import secrets
import sqlite3
from typing import Final

from roastery.idempotency import Stored
from roastery.ids import PREFIXES, CustomerId, OrderId
from roastery.ports import Clock
from roastery.repository import WIDTHS

SCHEMA: Final = """
CREATE TABLE IF NOT EXISTS order_links (
    token_hash TEXT PRIMARY KEY,
    order_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS guests (
    customer_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    street TEXT NOT NULL,
    postal_code TEXT NOT NULL,
    city TEXT NOT NULL,
    country TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS counters (
    kind TEXT PRIMARY KEY,
    next INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS idempotency (
    scope TEXT NOT NULL,
    key TEXT NOT NULL,
    body_hash TEXT NOT NULL,
    status INTEGER NOT NULL,
    reply TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (scope, key)
);
CREATE TABLE IF NOT EXISTS orphans (
    customer_id TEXT PRIMARY KEY,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

SQLITE_URL: Final = 'sqlite:///'
"""What a database URL starts with; the path follows."""

TOKEN_BYTES: Final = 24
"""An order link's randomness: 24 bytes, 32 characters, 192 bits."""

UNPADDED: Final = ('payment', 'guest')
"""The counted kinds that are not `IdKind`s: `PAY-n`, as the script's PAY-1, and the guest's
bare number. Every other kind has `SequentialIds`' width."""


class UnknownToken(Exception):
    """No order has this link: a 404. The edge's own refusal, not a `ShopError`."""

    def __init__(self) -> None:
        super().__init__('no order has this link')


def connect(url: str) -> sqlite3.Connection:
    """A connection to the sqlite file a `sqlite:///` URL names.

    Opened for any thread: FastAPI calls from its pool, and the API's one lock lets one
    call in at a time (ADR 0016).
    """
    if not url.startswith(SQLITE_URL):
        raise ValueError(f'the database URL must start {SQLITE_URL}')
    return sqlite3.connect(url.removeprefix(SQLITE_URL), check_same_thread=False)


def hash_token(token: str) -> str:
    """What the db keeps of a link's token: its sha256, in hex."""
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def _stamp(at: dt.datetime) -> str:
    return at.astimezone(dt.UTC).isoformat()


class State:
    """The state db's tables, on one connection. Each write commits before it returns."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._db = connection
        self._db.executescript(SCHEMA)
        self._db.commit()

    def number(self, kind: str) -> int:
        """The next number of `kind`, counted from 1; committed before it is given, so a
        restart never gives it again. A draw whose use rolls back leaves a harmless gap."""
        row = self._db.execute('SELECT next FROM counters WHERE kind = ?', (kind,)).fetchone()
        number = 1 if row is None else int(row[0])
        self._db.execute(
            'INSERT INTO counters (kind, next) VALUES (?, ?)'
            ' ON CONFLICT (kind) DO UPDATE SET next = excluded.next',
            (kind, number + 1),
        )
        self._db.commit()
        return number

    def link(self, order_id: OrderId, at: dt.datetime) -> str:
        """A new private link to the order: its token. Only the token's hash is stored."""
        token = secrets.token_urlsafe(TOKEN_BYTES)
        self._db.execute(
            'INSERT INTO order_links (token_hash, order_id, created_at) VALUES (?, ?, ?)',
            (hash_token(token), str(order_id), _stamp(at)),
        )
        self._db.commit()
        return token

    def order_of(self, token: str) -> OrderId:
        """The order the token links to; UnknownToken if none."""
        row = self._db.execute(
            'SELECT order_id FROM order_links WHERE token_hash = ?', (hash_token(token),)
        ).fetchone()
        if row is None:
            raise UnknownToken
        return OrderId(row[0])

    def add_guest(
        self,
        customer_id: CustomerId,
        *,
        name: str,
        email: str,
        street: str,
        postal_code: str,
        city: str,
        country: str,
        at: dt.datetime,
    ) -> None:
        """The guest's real contact and street address (F1, F4)."""
        self._db.execute(
            'INSERT INTO guests (customer_id, name, email, street, postal_code, city, country,'
            ' created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (str(customer_id), name, email, street, postal_code, city, country, _stamp(at)),
        )
        self._db.commit()

    def add_orphan(self, customer_id: CustomerId, reason: str, at: dt.datetime) -> None:
        """A guest registered whose order was never placed (F2)."""
        self._db.execute(
            'INSERT OR IGNORE INTO orphans (customer_id, reason, created_at) VALUES (?, ?, ?)',
            (str(customer_id), reason, _stamp(at)),
        )
        self._db.commit()

    def orphans(self) -> tuple[tuple[str, str], ...]:
        """(customer_id, reason) of every orphan, by customer id."""
        rows = self._db.execute(
            'SELECT customer_id, reason FROM orphans ORDER BY customer_id'
        ).fetchall()
        return tuple((str(each), str(reason)) for each, reason in rows)

    def guest(self, customer_id: CustomerId) -> dict[str, str] | None:
        """The guest's stored contact, or None."""
        cursor = self._db.execute(
            'SELECT name, email, street, postal_code, city, country FROM guests'
            ' WHERE customer_id = ?',
            (str(customer_id),),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(zip((each[0] for each in cursor.description), row, strict=True))


class CountedIds:
    """The API's `Ids`: `SequentialIds`' shape, counted in the state db, so a restart goes
    on where the last process stopped (ADR 0016)."""

    def __init__(self, state: State) -> None:
        self._state = state

    def next(self, kind: str) -> str:
        number = self._state.number(kind)
        prefix = PREFIXES[kind]
        if kind in UNPADDED:
            return f'{prefix}-{number}'
        return f'{prefix}-{number:0{WIDTHS[kind]}d}'  # type: ignore[index]


class SqliteKeys:
    """`idempotency.Keys` on the state db: the reply kept as JSON text."""

    def __init__(self, connection: sqlite3.Connection, clock: Clock) -> None:
        self._db = connection
        self._clock = clock

    def get(self, scope: str, key: str) -> Stored | None:
        row = self._db.execute(
            'SELECT body_hash, reply FROM idempotency WHERE scope = ? AND key = ?',
            (scope, key),
        ).fetchone()
        if row is None:
            return None
        return Stored(row[0], json.loads(row[1]))

    def put(self, scope: str, key: str, stored: Stored) -> None:
        reply = stored.reply
        self._db.execute(
            'INSERT INTO idempotency (scope, key, body_hash, status, reply, created_at)'
            ' VALUES (?, ?, ?, ?, ?, ?)',
            (
                scope,
                key,
                stored.body_hash,
                reply['status'],
                json.dumps(reply, sort_keys=True, separators=(',', ':')),
                _stamp(self._clock.now()),
            ),
        )
        self._db.commit()
