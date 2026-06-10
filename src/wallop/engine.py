"""Async HTTP load generator.

A pool of worker coroutines hammers the target. Each request reports
its lifecycle through two callbacks so the UI can animate it:

    on_start(request_id)              -> a particle takes flight
    on_complete(request_id, result)   -> it lands, ricochets, or explodes
"""

from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable

import aiohttp

from .stats import RequestResult

OnStart = Callable[[int], None]
OnComplete = Callable[[int, RequestResult], None]


class LoadEngine:
    def __init__(
        self,
        url: str,
        *,
        concurrency: int = 50,
        rate: float | None = None,
        total: int | None = None,
        duration: float | None = None,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: float = 10.0,
        insecure: bool = False,
        on_start: OnStart | None = None,
        on_complete: OnComplete | None = None,
    ) -> None:
        self.url = url
        self.concurrency = max(1, concurrency)
        self.rate = rate
        self.total = total
        self.duration = duration
        self.method = method.upper()
        self.headers = headers or {}
        self.body = body
        self.timeout = timeout
        self.insecure = insecure
        self.on_start = on_start or (lambda _id: None)
        self.on_complete = on_complete or (lambda _id, _r: None)
        self.stop_event = asyncio.Event()
        self._sent = 0
        self._next_slot = 0.0
        self._pace_lock: asyncio.Lock | None = None

    def stop(self) -> None:
        self.stop_event.set()

    async def run(self) -> None:
        self._pace_lock = asyncio.Lock()
        self._next_slot = asyncio.get_running_loop().time()
        deadline = (
            time.perf_counter() + self.duration if self.duration is not None else None
        )
        timeout_cfg = aiohttp.ClientTimeout(total=self.timeout)
        connector = aiohttp.TCPConnector(
            limit=0, ssl=False if self.insecure else None
        )
        async with aiohttp.ClientSession(
            timeout=timeout_cfg,
            connector=connector,
            headers={"User-Agent": "wallop"},
        ) as session:
            workers = [
                asyncio.create_task(self._worker(session, deadline))
                for _ in range(self.concurrency)
            ]
            try:
                await asyncio.gather(*workers)
            finally:
                self.stop_event.set()
                for w in workers:
                    w.cancel()
                await asyncio.gather(*workers, return_exceptions=True)

    def _claim_request_id(self) -> int | None:
        if self.total is not None and self._sent >= self.total:
            return None
        self._sent += 1
        return self._sent

    async def _pace(self) -> None:
        """Token-bucket pacing shared across workers (when --rate is set)."""
        if not self.rate:
            return
        assert self._pace_lock is not None
        loop = asyncio.get_running_loop()
        interval = 1.0 / self.rate
        async with self._pace_lock:
            now = loop.time()
            # advance the slot; if we fell behind, allow at most one
            # interval of catch-up rather than an unbounded burst
            self._next_slot = max(self._next_slot + interval, now - interval)
            wait = self._next_slot - now
        if wait > 0:
            await asyncio.sleep(wait)

    async def _worker(self, session: aiohttp.ClientSession, deadline: float | None) -> None:
        while not self.stop_event.is_set():
            if deadline is not None and time.perf_counter() >= deadline:
                self.stop_event.set()
                return
            await self._pace()
            if self.stop_event.is_set():
                return
            request_id = self._claim_request_id()
            if request_id is None:
                return
            self.on_start(request_id)
            result = await self._fire(session)
            self.on_complete(request_id, result)

    async def _fire(self, session: aiohttp.ClientSession) -> RequestResult:
        start = time.perf_counter()
        try:
            async with session.request(
                self.method, self.url, headers=self.headers, data=self.body
            ) as resp:
                payload = await resp.read()
                return RequestResult(
                    status=resp.status,
                    latency=time.perf_counter() - start,
                    bytes_read=len(payload),
                )
        except asyncio.TimeoutError:
            return RequestResult(
                status=-1,
                latency=time.perf_counter() - start,
                error="timeout",
            )
        except asyncio.CancelledError:
            raise
        except aiohttp.ClientError as exc:
            return RequestResult(
                status=0,
                latency=time.perf_counter() - start,
                error=type(exc).__name__,
            )
        except OSError as exc:
            return RequestResult(
                status=0,
                latency=time.perf_counter() - start,
                error=type(exc).__name__,
            )
