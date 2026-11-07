"""The request body's size limit: a body over 64 KiB is a 413 before anything parses it."""

from __future__ import annotations

from typing import Final

from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_BODY: Final = 64 * 1024
"""The most bytes a request body may hold."""

TOO_LARGE: Final = b"""{"type":"about:blank","title":"Content Too Large","status":413,\
"code":"ContentTooLarge","detail":"the request body is over 64 KiB"}"""


class BodyLimit:
    """ASGI middleware: reads the body up to `MAX_BODY` and refuses a larger one with a 413
    problem+json, by `Content-Length` or, for a body without one, by the bytes counted."""

    def __init__(self, app: ASGIApp, limit: int = MAX_BODY) -> None:
        self._app = app
        self._limit = limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http':
            await self._app(scope, receive, send)
            return
        declared = dict(scope['headers']).get(b'content-length', b'0')
        if not declared.isdigit() or int(declared) > self._limit:
            await self._refuse(send)
            return
        chunks: list[Message] = []
        size = 0
        while True:
            message = await receive()
            if message['type'] != 'http.request':
                await self._app(scope, receive, send)
                return
            chunks.append(message)
            size += len(message.get('body', b''))
            if size > self._limit:
                await self._refuse(send)
                return
            if not message.get('more_body', False):
                break
        replay = iter(chunks)

        async def replayed() -> Message:
            return next(replay, None) or await receive()  # type: ignore[return-value]

        await self._app(scope, replayed, send)

    @staticmethod
    async def _refuse(send: Send) -> None:
        headers = [
            (b'content-type', b'application/problem+json'),
            (b'content-length', str(len(TOO_LARGE)).encode()),
        ]
        await send({'type': 'http.response.start', 'status': 413, 'headers': headers})
        await send({'type': 'http.response.body', 'body': TOO_LARGE})
