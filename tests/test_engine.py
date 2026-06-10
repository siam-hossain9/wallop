import asyncio

import pytest
from aiohttp import web

from wallop.engine import LoadEngine
from wallop.stats import RequestResult, StatsCollector


@pytest.fixture
async def test_server():
    """Deterministic server: /ok -> 200, /missing -> 404, /boom -> 500,
    /slow -> 200 after 5s (for timeout tests)."""

    async def ok(_request):
        return web.json_response({"ok": True})

    async def missing(_request):
        return web.json_response({}, status=404)

    async def boom(_request):
        return web.json_response({}, status=500)

    async def slow(_request):
        await asyncio.sleep(5)
        return web.json_response({"ok": True})

    app = web.Application()
    app.router.add_get("/ok", ok)
    app.router.add_get("/missing", missing)
    app.router.add_get("/boom", boom)
    app.router.add_get("/slow", slow)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}"
    await runner.cleanup()


async def run_engine(url, **kwargs):
    stats = StatsCollector()
    started, completed = [], []

    def on_start(request_id):
        stats.record_start()
        started.append(request_id)

    def on_complete(request_id, result):
        stats.record(result)
        completed.append((request_id, result))

    engine = LoadEngine(url, on_start=on_start, on_complete=on_complete, **kwargs)
    await engine.run()
    return stats, started, completed


async def test_engine_completes_requested_total(test_server):
    stats, started, completed = await run_engine(
        f"{test_server}/ok", concurrency=5, total=30
    )
    assert stats.total == 30
    assert len(started) == 30
    assert len(completed) == 30
    assert stats.class_counts["2xx"] == 30
    assert stats.in_flight == 0
    assert all(r.latency > 0 for _, r in completed)
    assert all(r.bytes_read > 0 for _, r in completed)


async def test_engine_every_start_gets_a_completion(test_server):
    _, started, completed = await run_engine(
        f"{test_server}/ok", concurrency=8, total=40
    )
    assert sorted(started) == sorted(request_id for request_id, _ in completed)


async def test_engine_records_status_codes(test_server):
    stats_404, _, completed = await run_engine(
        f"{test_server}/missing", concurrency=3, total=9
    )
    assert stats_404.class_counts["4xx"] == 9
    assert all(r.status == 404 for _, r in completed)

    stats_500, _, _ = await run_engine(f"{test_server}/boom", concurrency=3, total=9)
    assert stats_500.class_counts["5xx"] == 9


async def test_engine_timeout_reported_as_timeout(test_server):
    stats, _, completed = await run_engine(
        f"{test_server}/slow", concurrency=2, total=2, timeout=0.3
    )
    assert stats.class_counts["timeout"] == 2
    assert all(r.status == -1 and r.error == "timeout" for _, r in completed)


async def test_engine_dropped_connection_is_transport_error():
    # a server that accepts and immediately hangs up -> transport error
    async def slam_door(_reader, writer):
        writer.close()

    server = await asyncio.start_server(slam_door, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        stats, _, completed = await run_engine(
            f"http://127.0.0.1:{port}/", concurrency=2, total=4, timeout=2.0
        )
    finally:
        server.close()
        await server.wait_closed()
    assert stats.class_counts["error"] == 4
    assert all(r.status == 0 for _, r in completed)
    assert all(r.error for _, r in completed)


async def test_engine_duration_stops_run(test_server):
    stats, _, _ = await run_engine(
        f"{test_server}/ok", concurrency=4, duration=0.5
    )
    assert stats.total > 0


async def test_engine_rate_limit_roughly_respected(test_server):
    loop = asyncio.get_running_loop()
    t0 = loop.time()
    stats, _, _ = await run_engine(
        f"{test_server}/ok", concurrency=10, total=20, rate=40.0
    )
    elapsed = loop.time() - t0
    assert stats.total == 20
    # 20 requests at 40 rps should take roughly 0.5s; allow generous slack
    assert elapsed >= 0.35


async def test_engine_stop_event_halts_workers(test_server):
    engine = LoadEngine(f"{test_server}/ok", concurrency=4)
    task = asyncio.create_task(engine.run())
    await asyncio.sleep(0.3)
    engine.stop()
    await asyncio.wait_for(task, timeout=5.0)
    assert task.done()


async def test_demo_server_phases():
    from wallop.demoserver import CYCLE_LENGTH, phase_at

    assert phase_at(0.0).name == "healthy"
    assert phase_at(12.0).name == "latency creep"
    assert phase_at(20.0).name == "error storm"
    assert phase_at(30.0).name == "meltdown"
    assert phase_at(40.0).name == "recovery"
    assert phase_at(CYCLE_LENGTH + 1.0).name == "healthy"  # cycles


async def test_demo_server_serves_traffic():
    from wallop.demoserver import start_server

    runner, port = await start_server()
    try:
        stats, _, _ = await run_engine(
            f"http://127.0.0.1:{port}/", concurrency=5, total=25, timeout=3.0
        )
        assert stats.total == 25
        assert stats.class_counts["2xx"] > 0  # healthy phase
    finally:
        await runner.cleanup()
