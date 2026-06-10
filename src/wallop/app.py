"""Ties the engine, world, and renderer into a live application."""

from __future__ import annotations

import asyncio
import random
import sys
import time

from .engine import LoadEngine
from .physics import World
from .renderer import FrameBuffer, HUD_BOTTOM_ROWS, HUD_TOP_ROWS, Screen, draw_world
from .stats import RequestResult, StatsCollector, fmt_bytes, fmt_duration, fmt_latency


class App:
    def __init__(self, engine: LoadEngine, target_label: str, fps: int = 30) -> None:
        self.engine = engine
        self.target_label = target_label
        self.fps = max(5, min(60, fps))
        self.stats = StatsCollector()
        cols, lines = Screen.term_size()
        self.world = World(cols, self._field_pixel_height(lines))
        self.screen = Screen()
        self.rng = random.Random()
        engine.on_start = self._on_start
        engine.on_complete = self._on_complete

    @staticmethod
    def _field_pixel_height(term_lines: int) -> int:
        field_rows = max(5, term_lines - HUD_TOP_ROWS - HUD_BOTTOM_ROWS)
        return field_rows * 2

    # -- engine callbacks (same event loop, must stay cheap) --------------

    def _on_start(self, request_id: int) -> None:
        self.stats.record_start()
        self.world.spawn_request(request_id)

    def _on_complete(self, request_id: int, result: RequestResult) -> None:
        self.stats.record(result)
        self.world.complete_request(request_id, result.status_class)

    # -- main loop ----------------------------------------------------------

    async def run(self) -> dict:
        engine_task = asyncio.create_task(self.engine.run())
        frame_interval = 1.0 / self.fps
        self.screen.enter()
        try:
            last = time.perf_counter()
            while not engine_task.done():
                now = time.perf_counter()
                dt = min(0.1, now - last)
                last = now

                if self._quit_requested():
                    self.engine.stop()
                    break

                cols, lines = Screen.term_size()
                field_rows = max(5, lines - HUD_TOP_ROWS - HUD_BOTTOM_ROWS)
                if (cols, field_rows * 2) != (self.world.width, self.world.height):
                    self.world.resize(cols, field_rows * 2)

                snapshot = self.stats.snapshot()
                self.world.update(dt, snapshot.latency_ema)

                fb = FrameBuffer(cols, field_rows)
                shake_x = (
                    self.rng.choice((-1, 0, 1)) if self.world.shake > 0.3 else 0
                )
                draw_world(self.world, fb, shake_x)
                self.screen.draw_frame(fb, snapshot, self.target_label)

                elapsed = time.perf_counter() - now
                await asyncio.sleep(max(0.0, frame_interval - elapsed))
            await engine_task
        except (KeyboardInterrupt, asyncio.CancelledError):
            self.engine.stop()
        finally:
            engine_task.cancel()
            try:
                await engine_task
            except (asyncio.CancelledError, Exception):
                pass
            self.screen.exit()
        return self.stats.final_summary()

    # -- input ----------------------------------------------------------------

    def _quit_requested(self) -> bool:
        if not sys.stdin.isatty():
            return False
        if sys.platform == "win32":
            import msvcrt

            while msvcrt.kbhit():
                if msvcrt.getwch().lower() == "q":
                    return True
            return False
        import select

        ready, _, _ = select.select([sys.stdin], [], [], 0)
        if ready:
            ch = sys.stdin.read(1)
            if ch.lower() == "q":
                return True
        return False


def print_summary(summary: dict, target: str) -> None:
    cc = summary["class_counts"]
    status_bits = " · ".join(
        f"{k} {v:,}" for k, v in sorted(cc.items()) if v
    )
    lines = [
        "",
        "  ─────────────────────────────────────────────",
        f"  wallop summary — {target}",
        "  ─────────────────────────────────────────────",
        f"  duration   {fmt_duration(summary['elapsed'])}",
        f"  requests   {summary['total']:,}  ({summary['rps']:,.1f} req/s)",
        f"  latency    p50 {fmt_latency(summary['p50'])}   p90 {fmt_latency(summary['p90'])}"
        f"   p95 {fmt_latency(summary['p95'])}   p99 {fmt_latency(summary['p99'])}",
        f"             min {fmt_latency(summary['min'])}   max {fmt_latency(summary['max'])}",
        f"  status     {status_bits or '-'}",
        f"  data read  {fmt_bytes(summary['bytes_read'])}",
        "",
    ]
    print("\n".join(lines))
