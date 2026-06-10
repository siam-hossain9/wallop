"""A deliberately misbehaving HTTP server for demos.

It cycles through a scripted incident so every wallop effect shows up
within ~40 seconds: healthy traffic, a latency creep, an error storm, a
full meltdown, then recovery. Great for GIFs; also handy as a chaos
target for testing real clients.
"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass

from aiohttp import web


@dataclass
class Phase:
    name: str
    until: float  # seconds into the cycle
    delay: tuple[float, float]  # min/max artificial latency, seconds
    error_rate: float  # probability of a 5xx
    hang_rate: float = 0.0  # probability of hanging (client times out)


CYCLE: list[Phase] = [
    Phase("healthy", 10.0, (0.004, 0.040), 0.004),
    Phase("latency creep", 18.0, (0.080, 0.450), 0.03),
    Phase("error storm", 27.0, (0.030, 0.200), 0.40),
    Phase("meltdown", 34.0, (0.300, 1.200), 0.65, hang_rate=0.05),
    Phase("recovery", 42.0, (0.010, 0.090), 0.02),
]
CYCLE_LENGTH = CYCLE[-1].until
NOT_FOUND_RATE = 0.025  # a constant trickle of 404s, for orange ricochets


def phase_at(t: float) -> Phase:
    t = t % CYCLE_LENGTH
    for phase in CYCLE:
        if t < phase.until:
            return phase
    return CYCLE[-1]


def build_app(rng: random.Random | None = None, clock=time.monotonic) -> web.Application:
    rng = rng or random.Random()
    started = clock()

    async def chaos(request: web.Request) -> web.Response:
        phase = phase_at(clock() - started)
        if rng.random() < phase.hang_rate:
            await asyncio.sleep(3600)  # let the client's timeout fire
        await asyncio.sleep(rng.uniform(*phase.delay))
        roll = rng.random()
        if roll < phase.error_rate:
            status = rng.choice((500, 502, 503))
            return web.json_response(
                {"phase": phase.name, "ok": False}, status=status
            )
        if roll < phase.error_rate + NOT_FOUND_RATE:
            return web.json_response({"error": "not found"}, status=404)
        return web.json_response({"phase": phase.name, "ok": True})

    async def healthz(_request: web.Request) -> web.Response:
        return web.json_response({"ok": True})

    app = web.Application()
    app.router.add_route("*", "/healthz", healthz)
    app.router.add_route("*", "/{tail:.*}", chaos)
    return app


async def start_server(port: int = 0) -> tuple[web.AppRunner, int]:
    """Start the chaos server; returns (runner, bound_port)."""
    runner = web.AppRunner(build_app(), access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    bound_port = site._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
    return runner, bound_port
