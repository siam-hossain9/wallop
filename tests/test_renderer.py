import random

from wallop.physics import World
from wallop.renderer import (
    LOWER,
    UPPER,
    FrameBuffer,
    draw_world,
    hud_lines,
    sparkline,
)
from wallop.stats import StatsSnapshot


def test_framebuffer_dimensions():
    fb = FrameBuffer(80, 20)
    assert fb.pw == 80
    assert fb.ph == 40
    assert len(fb.to_ansi_rows()) == 20


def test_half_block_mapping():
    fb = FrameBuffer(4, 2)
    red = (255, 0, 0)
    blue = (0, 0, 255)

    fb.set_pixel(0, 0, red)  # upper pixel only
    ch, fg, bg = fb.cell(0, 0)
    assert (ch, fg, bg) == (UPPER, red, None)

    fb.set_pixel(1, 1, blue)  # lower pixel only
    ch, fg, bg = fb.cell(1, 0)
    assert (ch, fg, bg) == (LOWER, blue, None)

    fb.set_pixel(2, 0, red)  # both pixels
    fb.set_pixel(2, 1, blue)
    ch, fg, bg = fb.cell(2, 0)
    assert (ch, fg, bg) == (UPPER, red, blue)

    ch, fg, bg = fb.cell(3, 0)  # empty
    assert (ch, fg, bg) == (" ", None, None)


def test_out_of_bounds_pixels_ignored():
    fb = FrameBuffer(4, 2)
    fb.set_pixel(-1, 0, (1, 2, 3))
    fb.set_pixel(0, -1, (1, 2, 3))
    fb.set_pixel(99, 0, (1, 2, 3))
    fb.set_pixel(0, 99, (1, 2, 3))
    assert all(p is None for row in fb.pixels for p in row)


def test_ansi_rows_contain_truecolor_codes():
    fb = FrameBuffer(8, 2)
    fb.set_pixel(0, 0, (10, 20, 30))
    rows = fb.to_ansi_rows()
    assert "\x1b[38;2;10;20;30m" in rows[0]
    assert UPPER in rows[0]


def test_draw_world_renders_wall_and_particles():
    world = World(60, 40, rng=random.Random(1))
    world.spawn_request(1)
    world.update(0.05, 0.1)
    fb = FrameBuffer(60, 20)
    draw_world(world, fb)
    wall_px = int(world.wall_x)
    wall_column = [fb.pixels[y][wall_px] for y in range(fb.ph)]
    assert all(c is not None for c in wall_column)
    lit = sum(1 for row in fb.pixels for p in row if p is not None)
    assert lit > fb.ph  # wall plus at least the particle


def test_sparkline_normalizes():
    line = sparkline([0.0, 5.0, 10.0], 3)
    assert len(line) == 3
    assert line[-1] == "█"
    assert sparkline([], 5) == "     "


def make_snapshot(**overrides):
    base = dict(
        elapsed=12.5,
        total=1234,
        rps=456.7,
        in_flight=50,
        p50=0.012,
        p95=0.048,
        p99=0.130,
        class_counts={"2xx": 1200, "4xx": 30, "5xx": 4},
        error_rate=0.0032,
        latency_ema=0.05,
        rps_history=[100.0, 200.0, 300.0],
    )
    base.update(overrides)
    return StatsSnapshot(**base)


def test_hud_contains_key_stats():
    top, bottom = hud_lines(make_snapshot(), "http://x/", 100)
    assert "wallop" in top
    assert "http://x/" in top
    joined = "\n".join(bottom)
    assert "457 req/s" in joined
    assert "12ms" in joined
    assert "1,200" in joined
    assert "q quit" in joined
