"""Cap upstream response bodies before the SDK parses them."""

from typing import cast

import httpx2

MAX_WIRE_BYTES = 1048576


class ResponseTooLarge(Exception):
    pass


class LimitedStream(httpx2.AsyncByteStream):
    def __init__(self, original: httpx2.AsyncByteStream) -> None:
        self.original = original

    async def __aiter__(self):  # type: ignore[no-untyped-def]
        total = 0
        async for chunk in self.original:
            total += len(chunk)
            if total > MAX_WIRE_BYTES:
                raise ResponseTooLarge("Upstream response exceeds wire-size limit")
            yield chunk

    async def aclose(self) -> None:
        await self.original.aclose()


class LimitedTransport(httpx2.AsyncBaseTransport):
    def __init__(self) -> None:
        self.inner = httpx2.AsyncHTTPTransport(
            trust_env=False,
            limits=httpx2.Limits(max_connections=4, max_keepalive_connections=2),
            retries=0,
        )

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        response = await self.inner.handle_async_request(request)
        length = response.headers.get("content-length")
        if length and length.isdigit() and int(length) > MAX_WIRE_BYTES:
            await response.aclose()
            raise ResponseTooLarge("Upstream response exceeds wire-size limit")
        response.stream = LimitedStream(cast(httpx2.AsyncByteStream, response.stream))
        return response

    async def aclose(self) -> None:
        await self.inner.aclose()
