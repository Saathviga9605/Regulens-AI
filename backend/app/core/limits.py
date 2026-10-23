"""Request body size limit for upload routes (pure ASGI middleware).

Rejects oversized uploads from the Content-Length header before the body is read, and enforces the same
limit while streaming (covers chunked requests without Content-Length), so large bodies are never fully
spooled to disk. The upload service additionally enforces the exact file-size limit.
"""

import json
import re

from fastapi import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import error_body

# Room for multipart boundaries and the small form fields around the file.
MULTIPART_OVERHEAD = 64 * 1024


class PayloadTooLarge(HTTPException):
    """413. An HTTPException so FastAPI's body-parsing wrapper re-raises it instead of turning it into a 400."""

    def __init__(self, max_bytes: int) -> None:
        super().__init__(413, f"File exceeds the maximum upload size of {max_bytes} bytes.")


class UploadSizeLimitMiddleware:
    def __init__(self, app: ASGIApp, *, max_bytes: int, path_pattern: str) -> None:
        self.app = app
        self.limit = max_bytes + MULTIPART_OVERHEAD
        self.max_bytes = max_bytes
        self.pattern = re.compile(path_pattern)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST" or not self.pattern.fullmatch(scope["path"]):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        length = headers.get(b"content-length")
        if length is not None and length.isdigit() and int(length) > self.limit:
            await self._reject(scope, send)
            return

        received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.limit:
                    raise PayloadTooLarge(self.max_bytes)
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except PayloadTooLarge:
            if not response_started:
                await self._reject(scope, send)

    async def _reject(self, scope: Scope, send: Send) -> None:
        state = scope.get("state") or {}
        body = json.dumps(error_body("payload_too_large",
                                     f"File exceeds the maximum upload size of {self.max_bytes} bytes.",
                                     state.get("request_id", ""))).encode()
        await send({"type": "http.response.start", "status": 413,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
